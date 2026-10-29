"""`make progress [JOB=name] [WATCH=1]`: progress bar for a running download.

Counts finished files against the expected number. Later downloads add themselves to JOBS.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from collections.abc import Callable
from pathlib import Path

from wao import config
from wao.ingest import country


def _country_expected() -> int:
    return len(country.days(country.START, country.END))


# name -> (directory, glob of finished files, expected count)
JOBS: dict[str, tuple[Path, str, Callable[[], int]]] = {
    "country": (config.COUNTRY_DIR / "country_project_page", "*.tsv", _country_expected),
}


def line(name: str) -> tuple[str, bool]:
    d, pattern, expected = JOBS[name]
    total = expected()
    files = list(d.glob(pattern)) if d.is_dir() else []
    n = len(files)
    size = sum(f.stat().st_size for f in d.iterdir()) / 1e9 if d.is_dir() else 0.0
    width = max(10, min(50, shutil.get_terminal_size().columns - 45))
    filled = int(width * n / total) if total else width
    pct = 100 * n / total if total else 100
    bar = "#" * filled + "-" * (width - filled)
    return f"{name:<8} [{bar}] {pct:5.1f}%  {n}/{total} files  {size:.1f} GB", n >= total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("job", nargs="?", default="country", choices=sorted(JOBS))
    ap.add_argument("--watch", action="store_true", help="redraw every 5 s until done")
    a = ap.parse_args()
    while True:
        text, done = line(a.job)
        sys.stdout.write("\r" + text)
        sys.stdout.flush()
        if done or not a.watch:
            print()
            return 0
        time.sleep(5)


if __name__ == "__main__":
    raise SystemExit(main())
