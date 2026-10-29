"""P05: download every clickstream file and convert it to Parquet, with per-article aggregates.

For each (lang, month) file in data/reference/clickstream_files.csv:
  1. download to RAW_DIR/clickstream/<lang>/ (resumable .part, checked against the listed size and
     with `gzip -t`); 2 connections at a time, as Wikimedia asks;
  2. parse with wao.ingest.clickstream.read (quote-wrapped titles decoded, rejects counted);
  3. write
       PARQUET_DIR/clickstream/lang=<l>/month=<m>/pairs.parquet          all (prev, curr) pairs
       PARQUET_DIR/clickstream_article/lang=<l>/month=<m>/part.parquet   per article: arrivals by
         referrer class, total arrivals, and outgoing clicks to other articles (link + link_other)
  4. write a done marker (JSON stats) so a rerun skips finished files.
At the end, PARQUET_DIR/clickstream_lang_month.parquet = totals by lang, month and referrer.

Run: python -m wao.ingest.clickstream_ingest [--langs en de] [--months 2024-01 2024-02]
Progress: make progress JOB=clickstream
"""

from __future__ import annotations

import argparse
import json
import resource
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import duckdb
import pandas as pd

from wao import config, http
from wao.ingest import clickstream

REFERRERS = ["search", "empty", "internal_other", "external", "other", "link", "link_other"]
DOWNLOAD_WORKERS = 2


def files(langs: list[str] | None = None, months: list[str] | None = None) -> pd.DataFrame:
    f = pd.read_csv(config.REFERENCE_DIR / "clickstream_files.csv")
    if langs:
        f = f[f.lang.isin(langs)]
    if months:
        f = f[f.month.isin(months)]
    # Core languages first, newest months first, so useful data lands early.
    f["core"] = f.lang.isin(config.LANGS)
    return f.sort_values(
        ["core", "month", "lang"], ascending=[False, False, True], ignore_index=True
    )


def raw_path(lang: str, name: str) -> Path:
    return config.CLICKSTREAM_DIR / lang / name


def done_marker(lang: str, month: str) -> Path:
    return config.PARQUET_DIR / "clickstream_done" / f"{lang}_{month}.json"


def download(row, ua: str) -> Path:
    p = raw_path(row.lang, row.file)
    if p.exists() and p.stat().st_size == row.bytes:
        return p
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".part")
    for attempt in range(3):
        # -C - resumes a partial download
        subprocess.run(
            ["curl", "-sfL", "--retry", "5", "-C", "-", "-A", ua, "-o", str(tmp), row.url],
            check=False,
        )
        if tmp.exists() and tmp.stat().st_size == row.bytes:
            break
        if attempt == 2:
            raise RuntimeError(f"size mismatch for {row.file}")
    subprocess.run(["gzip", "-t", str(tmp)], check=True)
    tmp.rename(p)
    return p


def convert(lang: str, month: str, path: Path, con: duckdb.DuckDBPyConnection) -> dict:
    t0 = time.time()
    tbl, stats = clickstream.read(path, con)
    con.register("cs", tbl)
    pairs = config.PARQUET_DIR / "clickstream" / f"lang={lang}" / f"month={month}"
    art = config.PARQUET_DIR / "clickstream_article" / f"lang={lang}" / f"month={month}"
    pairs.mkdir(parents=True, exist_ok=True)
    art.mkdir(parents=True, exist_ok=True)
    con.execute(
        f"COPY (SELECT prev, curr, referrer, n FROM cs) TO '{pairs}/pairs.parquet' "
        "(FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 1000000)"
    )
    pivots = ", ".join(f"sum(n) FILTER (WHERE referrer = '{r}') AS arr_{r}" for r in REFERRERS)
    con.execute(
        f"""
        COPY (
          WITH arrivals AS (
            SELECT curr AS title, {pivots}, sum(n) AS arr_total FROM cs GROUP BY curr
          ), outgoing AS (
            SELECT prev AS title, sum(n) AS out_links FROM cs
            WHERE referrer IN ('link', 'link_other') GROUP BY prev
          )
          SELECT coalesce(a.title, o.title) AS title, a.* EXCLUDE (title),
                 coalesce(o.out_links, 0) AS out_links
          FROM arrivals a FULL OUTER JOIN outgoing o USING (title)
        ) TO '{art}/part.parquet' (FORMAT parquet, COMPRESSION zstd)
        """
    )
    con.unregister("cs")
    stats |= {
        "lang": lang,
        "month": month,
        "seconds": round(time.time() - t0, 1),
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6),
        "by_referrer": {
            r["referrer"]: r["n"]
            for r in tbl.group_by("referrer")
            .aggregate([("n", "sum")])
            .rename_columns(["referrer", "n"])
            .to_pylist()
        },
    }
    m = done_marker(lang, month)
    m.parent.mkdir(parents=True, exist_ok=True)
    m.write_text(json.dumps(stats))
    return stats


def lang_month_totals() -> Path:
    out = config.PARQUET_DIR / "clickstream_lang_month.parquet"
    src = config.PARQUET_DIR / "clickstream_article" / "**" / "*.parquet"
    cols = ", ".join(f"sum(arr_{r}) AS {r}" for r in REFERRERS)
    duckdb.connect().execute(
        f"""COPY (SELECT lang, month, {cols}, sum(arr_total) AS total,
                         count(*) FILTER (WHERE arr_total > 0) AS articles
                  FROM read_parquet('{src}', hive_partitioning=true)
                  GROUP BY lang, month ORDER BY lang, month)
            TO '{out}' (FORMAT parquet)"""
    )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--langs", nargs="*")
    ap.add_argument("--months", nargs="*")
    a = ap.parse_args()
    todo = files(a.langs, a.months)
    todo = todo[[not done_marker(r.lang, r.month).exists() for r in todo.itertuples()]]
    print(f"{len(todo)} files to do ({todo.bytes.sum() / 1e9:.1f} GB)", flush=True)
    ua = http.user_agent()
    con = duckdb.connect()
    con.execute("SET memory_limit = '12GB'; SET preserve_insertion_order = false")
    t0, rows = time.time(), 0
    with ThreadPoolExecutor(DOWNLOAD_WORKERS) as pool:
        futs = {pool.submit(download, r, ua): r for r in todo.itertuples()}
        for i, fut in enumerate(as_completed(futs), 1):
            r = futs[fut]
            s = convert(r.lang, r.month, fut.result(), con)
            rows += s["rows"]
            el = time.time() - t0
            print(
                f"[{i}/{len(todo)}] {r.lang} {r.month}: {s['rows']:,} rows, "
                f"{s['rejected']} rejected, {s['seconds']}s convert | {rows / el:,.0f} rows/s "
                f"overall, peak {s['peak_rss_mb']} MB",
                flush=True,
            )
    print("lang-month totals ->", lang_month_totals())


if __name__ == "__main__":
    main()
