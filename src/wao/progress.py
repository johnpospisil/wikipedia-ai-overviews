"""`make progress [JOB=name] [WATCH=1]`: progress bar for a running download.

Progress is measured in bytes downloaded (finished files plus partial `.part` files) against the
total listed size, so a few large files can't make the bar race ahead or stall. With WATCH=1 it
also shows the current speed and an ETA. Later downloads add themselves to JOBS.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sqlite3
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from wao import config
from wao.ingest import country, pageview_months, pageviews, sql_dumps, stub_history


def _country_files() -> pd.DataFrame:
    # sizes unknown up front: count files instead (bytes = 1 per file)
    days = country.days(country.START, country.END)
    d = config.COUNTRY_DIR / "country_project_page"
    return pd.DataFrame({"path": [d / f"{x.isoformat()}.tsv" for x in days], "bytes": 1})


def _clickstream_files() -> pd.DataFrame:
    f = pd.read_csv(config.REFERENCE_DIR / "clickstream_files.csv")
    f["path"] = [
        config.CLICKSTREAM_DIR / lang / name for lang, name in zip(f.lang, f.file, strict=True)
    ]
    return f[["path", "bytes"]]


def _sql_files() -> pd.DataFrame:
    rows = sql_dumps.file_list()
    return pd.DataFrame(
        {
            "path": [sql_dumps.raw_path(r["lang"], r["table"]) for r in rows],
            "bytes": [r["bytes"] for r in rows],
        }
    )


def _pageview_2023_files() -> pd.DataFrame:
    f = pageview_months.files([f"2023-{m:02d}" for m in range(1, 13)])
    return pd.DataFrame({"path": [pageview_months.raw_path(n) for n in f.file], "bytes": f.bytes})


def _pageview_files() -> pd.DataFrame:
    f = pd.read_csv(config.REFERENCE_DIR / "pageview_monthly_files.csv")
    f = f[f.agent.isin(list(pageviews.FIRST)) & (f.month >= f.agent.map(pageviews.FIRST))]
    return pd.DataFrame({"path": [pageview_months.raw_path(n) for n in f.file], "bytes": f.bytes})


def _repair_files() -> pd.DataFrame:
    rows = [
        {"path": config.PAGEVIEW_DIR / "daily" / r.month / f["name"], "bytes": f["bytes"]}
        for r in pageviews.repairs().itertuples()
        for f in pageviews.daily_files(r.agent, r.month)
    ]
    return pd.DataFrame(rows)


def _stub_files() -> pd.DataFrame:
    rows = stub_history.file_list()
    return pd.DataFrame(
        {
            "path": [stub_history.raw_path(r["name"]) for r in rows],
            "bytes": [r["bytes"] for r in rows],
        }
    )


# name -> (expected files with sizes, whether `bytes` are real sizes)
JOBS: dict[str, tuple[Callable[[], pd.DataFrame], bool]] = {
    "country": (_country_files, False),
    "clickstream": (_clickstream_files, True),
    "sql": (_sql_files, True),
    "pageviews2023": (_pageview_2023_files, True),
    "pageviews": (_pageview_files, True),
    "repair": (_repair_files, True),
    "stubs": (_stub_files, True),
}


def _cached(prefix: str) -> int:
    """Responses stored in the HTTP caches whose names start with `prefix`."""
    n = 0
    for f in config.CACHE_DIR.glob(f"{prefix}*.sqlite"):
        with sqlite3.connect(f"file:{f}?mode=ro", uri=True, timeout=30) as con:
            n += con.execute("select count(*) from responses").fetchone()[0]
    return n


def _sample_size() -> int:
    return len(pd.read_parquet(config.PANEL_DIR / "sample.parquet", columns=["page_id"]))


def _logged_revisions() -> int:
    """Articles fetched so far by wao.ingest.revisions, from its log lines `xx: done/total`
    (and `xx: done N` once an edition is finished)."""
    log = config.DATA_DIR / "logs" / "revisions.log"
    best: dict[str, int] = {}
    if log.exists():
        text = log.read_text()
        for m in re.finditer(r"^(\w+): ([\d,]+)/", text, re.M):
            best[m[1]] = max(best.get(m[1], 0), int(m[2].replace(",", "")))
        for m in re.finditer(r"^(\w+): done ([\d,]+)", text, re.M):
            best[m[1]] = int(m[2].replace(",", ""))
    return sum(best.values())


def _log_lines(name: str, pattern: str) -> int:
    log = config.DATA_DIR / "logs" / name
    return len(re.findall(pattern, log.read_text(), re.M)) if log.exists() else 0


# what COUNTS jobs count (default: articles)
UNITS = {"reparse": "files", "aqs": "editions"}

# name -> (items done, items total): API jobs counted in cached responses
COUNTS: dict[str, Callable[[], tuple[int, int]]] = {
    "topics": lambda: (_cached("liftwing_"), _sample_size()),
    "revisions": lambda: (_logged_revisions(), _sample_size()),
    "reparse": lambda: (_log_lines("stub_history_reparse.log", r"'revisions'"), 82),
    "aqs": lambda: (_log_lines("editors.log", r"^\w+: [\d,]+ rows"), len(config.LANGS)),
}


def measure(name: str) -> tuple[float, float, int, int]:
    """(bytes done, bytes total, files done, files total)."""
    if name in COUNTS:
        done, total = COUNTS[name]()
        return float(done), float(total), done, total
    expected, real_sizes = JOBS[name]
    f = expected()
    done_bytes, done_files = 0.0, 0
    for p, b in zip(f.path, f.bytes, strict=True):
        p = Path(p)
        if p.exists():
            done_files += 1
            done_bytes += b
        elif real_sizes:
            part = p.with_suffix(p.suffix + ".part")
            if part.exists():
                done_bytes += min(part.stat().st_size, b)
    return done_bytes, float(f.bytes.sum()), done_files, len(f)


def fmt_eta(seconds: float) -> str:
    if seconds <= 0 or seconds != seconds:
        return "--"
    h, rem = divmod(int(seconds), 3600)
    return f"{h}h{rem // 60:02d}m" if h else f"{rem // 60}m{rem % 60:02d}s"


def render(
    name: str, done: float, total: float, nf: int, nt: int, rate: float | None, real_sizes: bool
) -> str:
    frac = done / total if total else 1.0
    width = max(10, min(40, shutil.get_terminal_size().columns - 70))
    filled = int(width * frac)
    bar = "█" * filled + "░" * (width - filled)
    eta = f"ETA {fmt_eta((total - done) / rate if rate else 0)}" if rate is not None else ""
    if name in COUNTS:
        speed = f"  {rate * 60:,.0f}/min  {eta}" if rate is not None else ""
        unit = UNITS.get(name, "articles")
        return f"{name} [{bar}] {100 * frac:5.1f}%  {nf:,}/{nt:,} {unit}{speed}"
    size = f"{done / 1e9:5.1f}/{total / 1e9:.1f} GB" if real_sizes else ""
    speed = f"  {rate / 1e6:4.1f} MB/s  {eta}" if rate is not None and real_sizes else ""
    return f"{name} [{bar}] {100 * frac:5.1f}%  {size}  {nf}/{nt} files{speed}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("job", nargs="?", default="clickstream", choices=sorted(JOBS | COUNTS))
    ap.add_argument("--watch", action="store_true", help="redraw every 5 s until done")
    a = ap.parse_args()
    real = JOBS[a.job][1] if a.job in JOBS else True
    history: list[tuple[float, float]] = []  # (time, bytes) over the last ~2 minutes
    while True:
        done, total, nf, nt = measure(a.job)
        now = time.time()
        history = [(t, b) for t, b in history if now - t <= 120] + [(now, done)]
        rate = None
        if len(history) > 1 and history[-1][0] > history[0][0]:
            rate = (history[-1][1] - history[0][1]) / (history[-1][0] - history[0][0])
        sys.stdout.write("\r\033[K" + render(a.job, done, total, nf, nt, rate, real))
        sys.stdout.flush()
        if nf >= nt or not a.watch:
            print()
            return 0
        time.sleep(5)


if __name__ == "__main__":
    raise SystemExit(main())
