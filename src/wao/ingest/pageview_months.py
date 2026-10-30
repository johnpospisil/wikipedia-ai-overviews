"""Monthly `user` pageview totals for every page in the core editions (all namespaces).

For each month: download pageviews-<YYYYMM>-user.bz2 (resumable, size-checked), stream it through
`bzip2 -dc` (a separate process, so decompression and parsing overlap), keep the core editions
and write PARQUET_DIR/pageview_month/month=<m>/part.parquet with
  lang, title, page_id (null where the dump has none), access, views.
Only the monthly total is read; daily counts are left to P07. A corrupt bz2 makes `bzip2` fail
and the month is not written. Rows that don't parse are counted in the log, never dropped silently.

P06 uses 2023 for the sampling frame (pre-period popularity). Run:
  python -m wao.ingest.pageview_months 2023-01 2023-02 …   (default: all of 2023)
"""

from __future__ import annotations

import argparse
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from wao import config, http
from wao.ingest.download import WORKERS, fetch

ACCESS = ("desktop", "mobile-web", "mobile-app")
BATCH = 2_000_000
SCHEMA = pa.schema(
    [
        ("lang", pa.string()),
        ("title", pa.string()),
        ("page_id", pa.int64()),
        ("access", pa.string()),
        ("views", pa.int64()),
    ]
)


def files(months: list[str], agent: str = "user") -> pd.DataFrame:
    f = pd.read_csv(config.REFERENCE_DIR / "pageview_monthly_files.csv")
    f = f[(f.agent == agent) & f.month.isin(months)]
    missing = set(months) - set(f.month)
    if missing:
        raise ValueError(f"no {agent} file listed for {sorted(missing)}")
    return f


def raw_path(name: str) -> Path:
    return config.PAGEVIEW_DIR / "monthly" / name


def out_path(month: str) -> Path:
    return config.PARQUET_DIR / "pageview_month" / f"month={month}" / "part.parquet"


def parse_lines(lines, langs=config.LANGS) -> tuple[list[tuple], int]:
    """Lines -> (lang, title, page_id, access, views) rows for the editions in `langs`."""
    prefixes = tuple(f"{lang}.wikipedia " for lang in langs)
    bare = {p.strip() for p in prefixes}
    rows, bad = [], 0
    for line in lines:
        if not line.startswith(prefixes):
            # a truncated line with only the wiki code
            if len(line) < 20 and line.strip() in bare:
                bad += 1
            continue
        f = line.split(" ")
        if len(f) == 6:
            wiki, title, pid, access, total = f[:5]
        elif len(f) == 5:
            (wiki, title, access, total), pid = f[:4], "null"
        else:
            bad += 1
            continue
        if access not in ACCESS or not total.isdigit() or not (pid == "null" or pid.isdigit()):
            bad += 1
            continue
        rows.append((wiki[:-10], title, None if pid == "null" else int(pid), access, int(total)))
    return rows, bad


def _write(writer: pq.ParquetWriter, rows: list[tuple]) -> None:
    cols = list(zip(*rows, strict=True))
    writer.write_table(pa.Table.from_arrays([pa.array(c) for c in cols], schema=SCHEMA))


def convert(month: str, path: Path) -> dict:
    t0 = time.time()
    out = out_path(month)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    proc = subprocess.Popen(["bzip2", "-dc", str(path)], stdout=subprocess.PIPE, bufsize=1 << 24)
    n, bad, views = 0, 0, 0
    buf: list[str] = []
    with pq.ParquetWriter(tmp, SCHEMA, compression="zstd") as w:
        for raw in proc.stdout:
            buf.append(raw.decode("utf-8", "replace"))
            if len(buf) >= BATCH:
                rows, b = parse_lines(buf)
                buf, bad = [], bad + b
                if rows:
                    _write(w, rows)
                    n, views = n + len(rows), views + sum(r[4] for r in rows)
        rows, b = parse_lines(buf)
        bad += b
        if rows:
            _write(w, rows)
            n, views = n + len(rows), views + sum(r[4] for r in rows)
    if proc.wait() != 0:
        tmp.unlink()
        raise RuntimeError(f"bzip2 failed on {path}")
    tmp.rename(out)
    return {"month": month, "rows": n, "bad": bad, "views": views, "s": round(time.time() - t0)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("months", nargs="*", default=[f"2023-{m:02d}" for m in range(1, 13)])
    ap.add_argument("--procs", type=int, default=4)
    a = ap.parse_args()
    todo = files([m for m in a.months if not out_path(m).exists()])
    ua = http.user_agent()
    print(f"{len(todo)} months to do ({todo.bytes.sum() / 1e9:.1f} GB)", flush=True)
    with ThreadPoolExecutor(WORKERS) as dl, ProcessPoolExecutor(a.procs) as cpu:
        paths = dl.map(
            lambda r: (r.month, fetch(r.url, raw_path(r.file), r.bytes, ua=ua)), todo.itertuples()
        )
        futs = [cpu.submit(convert, m, p) for m, p in paths]
        for f in futs:
            print(f.result(), flush=True)


if __name__ == "__main__":
    main()
