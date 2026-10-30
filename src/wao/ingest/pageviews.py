"""Daily pageviews for the P06 sample articles, from pageview_complete monthly files.

Files: pageviews-<YYYYMM>-<agent>.bz2 for `user` 2016-01.. and `automated` 2020-05.. (the agent
class only exists from 2020-05; before that automated traffic is inside `user`). `spider` files
stop in 2023-02 and are not used. The dumps publish no checksums: a file is verified by its
listed size and by `bzip2 -dc` exiting cleanly after decompressing all of it.

Matching (lookup built once from the sample and the 2026-10 page/redirect tables):
  id            page_id is a sample article and the title is its current title
  id_alt_title  page_id is a sample article, title differs: a redirect followed to the article
                (the dump records the target's id) or the title before a page move
  redirect_id   page_id is a redirect page (up to 2 hops) to a sample article
  null_title / null_redirect   page_id is null; title is the article's or one of its redirects
  old_id        page_id no longer exists (deleted, e.g. an earlier incarnation) and the title is
                the article's or one of its redirects
Rows whose title matches but whose page_id is a different live page are dropped (`other_page`)
and only counted. Page moves keep the page_id, so the id match follows them.

Outputs (PARQUET_DIR):
  pageview_daily/agent=<a>/month=<m>/part.parquet   lang, page_id, date, access, views
  pageview_match/agent=<a>/month=<m>/part.parquet   lang, page_id, match, access, rows, views
  logs/pageviews.jsonl                              per-file line counts, checks, seconds
Resumable: a month whose daily file exists is skipped.

Run: python -m wao.ingest.pageviews [--agents user automated] [--procs 2]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa

from wao import config, http
from wao.ingest import sql_dumps
from wao.ingest.download import WORKERS, fetch
from wao.ingest.pageview_months import ACCESS, raw_path

FIRST = {"user": "2016-01", "automated": "2020-05"}
FREE_MARGIN = 30e9  # stop downloading when Drive3 would drop below this
BATCH = 500_000
KEEP = ("lang", "page_id", "match", "access", "pid", "packed", "total")


def lookup_path() -> Path:
    return config.PARQUET_DIR / "pageview_lookup.parquet"


def out_path(kind: str, agent: str, month: str) -> Path:
    return config.PARQUET_DIR / kind / f"agent={agent}" / f"month={month}" / "part.parquet"


def build_lookup(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """key_type ('id' | 'title'), lang, key, page_id (canonical), match."""
    parts = []
    for lang in config.LANGS:
        page = sql_dumps.out_path("page", lang)
        redir = sql_dumps.out_path("redirect", lang)
        parts.append(
            con.execute(
                f"""
                with s as (select page_id, title from '{config.PANEL_DIR}/sample.parquet'
                           where lang = '{lang}'),
                pg as (select page_id, title from '{page}' where namespace = 0 and is_redirect),
                r as (select pg.page_id, pg.title, rd.target
                      from pg join '{redir}' rd using (page_id)),
                hop as (select r.page_id, r.title, s.page_id canon
                        from r join s on r.target = s.title
                        union
                        select r1.page_id, r1.title, s.page_id
                        from r r1 join r r2 on r1.target = r2.title join s on r2.target = s.title)
                select 'id' key_type, '{lang}' lang, page_id::varchar key, page_id, 'id' match
                from s
                union all select 'id', '{lang}', page_id::varchar, canon, 'redirect_id' from hop
                union all select 'title', '{lang}', title, page_id, 'title' from s
                union all select 'title', '{lang}', title, canon, 'redirect' from hop
                """
            ).df()
        )
    # a redirect reached both directly and in two hops can point at two articles: keep direct
    out = pd.concat(parts, ignore_index=True)
    return out.drop_duplicates(["key_type", "lang", "key"], keep="first", ignore_index=True)


def _dicts(lk: pd.DataFrame) -> tuple[dict, dict, dict]:
    ids, titles, canon_title = {}, {}, {}
    for kt, lang, key, pid, m in lk.itertuples(index=False):
        w = f"{lang}.wikipedia"
        if kt == "id":
            ids.setdefault(w, {})[key] = (pid, m)
        else:
            titles.setdefault(w, {})[key] = (pid, m)
            if m == "title":
                canon_title.setdefault(w, {})[pid] = key
    return ids, titles, canon_title


def match_lines(lines, ids: dict, titles: dict, canon_title: dict) -> tuple[list[tuple], int]:
    """Lines -> rows (lang, page_id, match, access, pid_or_None, packed, total); bad-line count.

    `old_id` candidates (title match, page_id not a sample/redirect id) come back with match
    'candidate' and their pid; the caller decides old_id vs other_page.
    """
    prefixes = tuple(f"{w} " for w in ids)
    rows, bad = [], 0
    for line in lines:
        if not line.startswith(prefixes):
            if len(line) < 20 and line.strip() in ids:  # truncated: only the wiki code
                bad += 1
            continue
        f = line.rstrip("\n").split(" ")
        if len(f) == 6:
            wiki, title, pid, access, total, packed = f
        elif len(f) == 5:
            (wiki, title, access, total, packed), pid = f, "null"
        else:
            bad += 1
            continue
        if access not in ACCESS or not total.isdigit():
            bad += 1
            continue
        lang = wiki[:-10]
        if pid != "null":
            hit = ids[wiki].get(pid)
            if hit:
                m = hit[1]
                if m == "id" and canon_title[wiki].get(hit[0]) != title:
                    m = "id_alt_title"
                rows.append((lang, hit[0], m, access, None, packed, int(total)))
            elif (hit := titles[wiki].get(title)) is not None:
                if not pid.isdigit():
                    bad += 1
                    continue
                rows.append((lang, hit[0], "candidate", access, int(pid), packed, int(total)))
        elif (hit := titles[wiki].get(title)) is not None:
            m = "null_title" if hit[1] == "title" else "null_redirect"
            rows.append((lang, hit[0], m, access, None, packed, int(total)))
    return rows, bad


_SCHEMA = pa.schema(
    [
        ("lang", pa.string()),
        ("page_id", pa.int64()),
        ("match", pa.string()),
        ("access", pa.string()),
        ("pid", pa.int64()),
        ("packed", pa.string()),
        ("total", pa.int64()),
    ]
)


def _table(rows: list[tuple]) -> pa.Table:
    cols = list(zip(*rows, strict=True)) if rows else [[] for _ in KEEP]
    arrays = [pa.array(c, t.type) for c, t in zip(cols, _SCHEMA, strict=True)]
    return pa.Table.from_arrays(arrays, schema=_SCHEMA)


def resolve_and_decode(
    con: duckdb.DuckDBPyConnection, lines: pa.Table, month: str
) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Resolve candidates against the live page tables and decode days.

    Returns (daily, match, number of lines whose daily counts don't sum to the total).
    """
    con.register("raw", lines)
    cand = con.execute("select distinct lang, pid from raw where match = 'candidate'").df()
    live = []
    for lang, g in cand.groupby("lang"):
        con.register("c", g)
        page = sql_dumps.out_path("page", lang)
        q = f"select '{lang}' lang, page_id pid from '{page}' join c on page_id = pid"
        live.append(con.execute(q).df())
    empty = pd.DataFrame({"lang": pd.Series(dtype=str), "pid": pd.Series(dtype="int64")})
    con.register("live", pd.concat(live) if live else empty)
    con.execute(
        """
        create or replace temp table m as
        select row_number() over () line, raw.lang, page_id, access, packed, total,
               case when match <> 'candidate' then match
                    when live.pid is null then 'old_id' else 'other_page' end match
        from raw left join live using (lang, pid)
        """
    )
    y, mo = int(month[:4]), int(month[5:])
    con.execute(
        """
        create or replace temp table d as
        select line, lang, page_id, access, match, total,
               unnest(regexp_extract_all(packed, '([A-_])[0-9]+', 1)) letter,
               unnest(regexp_extract_all(packed, '[A-_]([0-9]+)', 1))::bigint v
        from m
        """
    )
    bad = con.execute(
        "select count(*) from (select line, any_value(total) t, sum(v) s from d group by line) "
        "where t <> s"
    ).fetchone()[0]
    daily = con.execute(
        f"""
        select lang, page_id, make_date({y}, {mo}, ascii(letter) - 64) date, access,
               sum(v)::bigint views
        from d where match <> 'other_page'
        group by all order by lang, page_id, date, access
        """
    ).df()
    match = con.execute(
        "select lang, page_id, match, access, count(*) rows, sum(total)::bigint views "
        "from m group by all order by all"
    ).df()
    con.unregister("raw")
    return daily, match, bad


def convert(agent: str, month: str, path: Path) -> dict:
    t0 = time.time()
    ids, titles, canon_title = _dicts(pd.read_parquet(lookup_path()))
    proc = subprocess.Popen(["bzip2", "-dc", str(path)], stdout=subprocess.PIPE, bufsize=1 << 24)
    tables, buf, lines, bad = [], [], 0, 0
    for raw in proc.stdout:
        buf.append(raw.decode("utf-8", "replace"))
        if len(buf) >= BATCH:
            rows, b = match_lines(buf, ids, titles, canon_title)
            tables.append(_table(rows))
            lines, bad, buf = lines + len(buf), bad + b, []
    rows, b = match_lines(buf, ids, titles, canon_title)
    tables.append(_table(rows))
    lines, bad = lines + len(buf), bad + b
    if proc.wait() != 0:
        raise RuntimeError(f"bzip2 failed on {path}")
    con = duckdb.connect()
    con.execute(f"set memory_limit='3GB'; set threads=2; set temp_directory='{config.TMP_DIR}'")
    daily, match, inconsistent = resolve_and_decode(con, pa.concat_tables(tables), month)
    for kind, df in (("pageview_match", match), ("pageview_daily", daily)):  # daily last
        out = out_path(kind, agent, month)
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp")
        df.to_parquet(tmp, compression="zstd", index=False)
        tmp.rename(out)
    return {
        "agent": agent,
        "month": month,
        "lines": lines,
        "matched_rows": int(match.rows.sum()),
        "articles": int(daily.page_id.groupby(daily.lang).nunique().sum()),
        "views": int(daily.views.sum()),
        "bad": bad,
        "inconsistent": int(inconsistent),
        "s": round(time.time() - t0),
    }


def todo(agents: list[str]) -> pd.DataFrame:
    f = pd.read_csv(config.REFERENCE_DIR / "pageview_monthly_files.csv")
    f = f[f.agent.isin(agents) & (f.month >= f.agent.map(FIRST))]
    done = [
        out_path("pageview_daily", a, m).exists() for a, m in zip(f.agent, f.month, strict=True)
    ]
    f = f[[not d for d in done]]
    # files already on disk first, then oldest first
    f["local"] = [raw_path(n).exists() for n in f.file]
    return f.sort_values(["local", "month", "agent"], ascending=[False, True, False])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", nargs="+", default=["user", "automated"])
    ap.add_argument("--procs", type=int, default=2)
    ap.add_argument("--rebuild-lookup", action="store_true")
    a = ap.parse_args()
    if a.rebuild_lookup or not lookup_path().exists():
        lk = build_lookup(duckdb.connect())
        lk.to_parquet(lookup_path(), index=False)
        print(lk.groupby(["lang", "match"]).size().unstack(), flush=True)
    f = todo(a.agents)
    remote = f.loc[~f.local, "bytes"].sum()
    print(f"{len(f)} files to do; {remote / 1e9:.0f} GB to download", flush=True)
    ua = http.user_agent()
    log = config.DATA_DIR / "logs" / "pageviews.jsonl"
    log.parent.mkdir(exist_ok=True)

    def get(r):
        if not r.local and shutil.disk_usage(config.RAW_DIR).free < r.bytes + FREE_MARGIN:
            raise RuntimeError(f"not enough free space for {r.file}")
        return r, fetch(r.url, raw_path(r.file), r.bytes, ua=ua)

    with ThreadPoolExecutor(WORKERS) as dl, ProcessPoolExecutor(a.procs) as cpu:
        downloads = [dl.submit(get, r) for r in f.itertuples()]
        jobs = []
        for d in as_completed(downloads):
            r, path = d.result()
            jobs.append(cpu.submit(convert, r.agent, r.month, path))
        for j in as_completed(jobs):
            res = j.result()
            print(res, flush=True)
            with open(log, "a") as fh:
                fh.write(json.dumps(res) + "\n")


if __name__ == "__main__":
    main()
