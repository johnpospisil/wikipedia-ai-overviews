"""Resumable, verified file downloads from dumps.wikimedia.org (shared by every ingest step).

A file is downloaded to `<path>.part` with `curl -C -` (so an interrupted run resumes), checked
against the listed size and, where the dump publishes one, its md5, then optionally tested
(e.g. `gzip -t`) and only then renamed into place. A file that exists at its final path has
passed every check. Wikimedia asks for no more than 2–3 parallel connections.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from wao import http

WORKERS = 2


def md5(path: Path, chunk: int = 1 << 24) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        while b := fh.read(chunk):
            h.update(b)
    return h.hexdigest()


def fetch(
    url: str,
    path: Path,
    size: int | None = None,
    md5sum: str | None = None,
    test: list[str] | None = None,
    ua: str | None = None,
) -> Path:
    """Download `url` to `path` unless it is already there (with the right size)."""
    path = Path(path)
    if path.exists() and (size is None or path.stat().st_size == size):
        return path
    ua = ua or http.user_agent()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    for attempt in range(3):
        subprocess.run(
            ["curl", "-sfL", "--retry", "5", "-C", "-", "-A", ua, "-o", str(tmp), url],
            check=False,
        )
        if tmp.exists() and (size is None or tmp.stat().st_size == size):
            break
        if attempt == 2:
            raise RuntimeError(f"size mismatch for {url}")
    if md5sum and md5(tmp) != md5sum:
        tmp.unlink()
        raise RuntimeError(f"md5 mismatch for {url}")
    if test:
        subprocess.run([*test, str(tmp)], check=True)
    tmp.rename(path)
    return path
