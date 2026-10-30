"""`make progress [JOB=name] [WATCH=1]`: progress bar for a running download.

Progress is measured in bytes downloaded (finished files plus partial `.part` files) against the
total listed size, so a few large files can't make the bar race ahead or stall. With WATCH=1 it
also shows the current speed and an ETA. Later downloads add themselves to JOBS.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from wao import config
from wao.ingest import country, pageview_months, sql_dumps


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


# name -> (expected files with sizes, whether `bytes` are real sizes)
JOBS: dict[str, tuple[Callable[[], pd.DataFrame], bool]] = {
    "country": (_country_files, False),
    "clickstream": (_clickstream_files, True),
    "sql": (_sql_files, True),
    "pageviews2023": (_pageview_2023_files, True),
}


def measure(name: str) -> tuple[float, float, int, int]:
    """(bytes done, bytes total, files done, files total)."""
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
    size = f"{done / 1e9:5.1f}/{total / 1e9:.1f} GB" if real_sizes else ""
    speed = ""
    if rate is not None and real_sizes:
        speed = f"  {rate / 1e6:4.1f} MB/s  ETA {fmt_eta((total - done) / rate if rate else 0)}"
    return f"{name} [{bar}] {100 * frac:5.1f}%  {size}  {nf}/{nt} files{speed}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("job", nargs="?", default="clickstream", choices=sorted(JOBS))
    ap.add_argument("--watch", action="store_true", help="redraw every 5 s until done")
    a = ap.parse_args()
    real = JOBS[a.job][1]
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
