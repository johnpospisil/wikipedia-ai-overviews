"""`make check-env`: confirm the drive is mounted, the env is set, and there is room to work."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from wao import config

MIN_FREE_GB = 1 if config.SAMPLE else 250


def _existing_ancestor(path: Path) -> Path:
    while not path.exists():
        path = path.parent
    return path


def mounted(path: Path) -> bool:
    """False if `path` would be created on the boot disk because its volume isn't mounted."""
    anc = _existing_ancestor(path)
    return anc not in (Path("/"), Path("/Volumes"))


def main() -> int:
    problems: list[str] = []

    print(f"Python      {sys.version.split()[0]}")
    print(f"Raw dir     {config.RAW_DIR}")
    print(f"Data dir    {config.DATA_DIR}")
    print(f"Contact     {config.CONTACT or '(not set)'}")

    if not config.CONTACT:
        problems.append("WAO_CONTACT is not set (needed for the Wikimedia User-Agent)")

    for label, path in (("raw dir", config.RAW_DIR), ("data dir", config.DATA_DIR)):
        if not mounted(path):
            print(f"\n{label} is not on a mounted volume. Is the external drive mounted?")
            return 1
        path.mkdir(parents=True, exist_ok=True)

    for label, path in (("Raw disk", config.RAW_DIR), ("Data disk", config.DATA_DIR)):
        free_gb = shutil.disk_usage(path).free / 1e9
        print(f"{label:<11} {free_gb:,.0f} GB free")
        if free_gb < MIN_FREE_GB:
            problems.append(f"{label.lower()} has under {MIN_FREE_GB} GB free")

    if problems:
        print("\nPROBLEMS:\n  - " + "\n  - ".join(problems))
        return 1
    print("\nOK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
