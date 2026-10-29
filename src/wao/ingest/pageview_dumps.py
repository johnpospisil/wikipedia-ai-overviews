"""pageview_complete parsing (monthly and daily files).

Row format (space-separated): wiki_code title page_id access total counts
  - page_id is an integer or `null`; some rows lack it entirely (5 columns, a known issue).
  - counts packs (index, count) pairs as a letter followed by digits. Monthly files index days
    ('A' = day 1 … 'Z' = 26, then '[', '\\', ']', '^', '_' = 27–31); daily files index hours
    ('A' = hour 0 … 'X' = 23).
Files are sorted by wiki code across all projects, so filtering on the line prefix before
splitting is the cheap way to keep only the editions we need.
"""

from __future__ import annotations

import bz2
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

PAIR = re.compile(r"([A-_])(\d+)")
ACCESS = {"desktop", "mobile-web", "mobile-app"}


@dataclass(frozen=True, slots=True)
class Row:
    wiki: str
    title: str
    page_id: int | None
    access: str
    total: int
    counts: dict[int, int]

    @property
    def consistent(self) -> bool:
        return sum(self.counts.values()) == self.total


def decode(packed: str, base: int) -> dict[int, int]:
    """'A100B100_100' -> {base+0: 100, base+1: 100, base+30: 100}."""
    out: dict[int, int] = {}
    for letter, num in PAIR.findall(packed):
        k = ord(letter) - 65 + base
        out[k] = out.get(k, 0) + int(num)
    return out


def parse_line(line: str, kind: str = "monthly") -> Row | None:
    f = line.rstrip("\n").split(" ")
    if len(f) == 6:
        wiki, title, pid, access, total, packed = f
        page_id = None if pid == "null" else _int(pid)
        if pid != "null" and page_id is None:
            return None
    elif len(f) == 5:
        wiki, title, access, total, packed = f
        page_id = None
    else:
        return None
    t = _int(total)
    if access not in ACCESS or t is None:
        return None
    return Row(wiki, title, page_id, access, t, decode(packed, 1 if kind == "monthly" else 0))


def _int(s: str) -> int | None:
    return int(s) if s.isdigit() else None


def _open(path: Path):
    if path.suffix == ".bz2":
        return bz2.open(path, "rt", encoding="utf-8", errors="replace")
    return open(path, encoding="utf-8", errors="replace")


def iter_rows(
    path: Path,
    wikis: set[str] | None = None,
    kind: str = "monthly",
    stats: dict | None = None,
) -> Iterator[Row]:
    """Yield parsed rows, optionally only for `wikis` (e.g. {'en.wikipedia'}).

    `stats` (if given) is filled with: lines, kept, malformed, five_col, inconsistent.
    """
    s = {"lines": 0, "kept": 0, "malformed": 0, "five_col": 0, "inconsistent": 0}
    prefixes = tuple(f"{w} " for w in wikis) if wikis else None
    with _open(Path(path)) as fh:
        for line in fh:
            s["lines"] += 1
            if prefixes and not line.startswith(prefixes):
                # also catches truncated lines like 'en.wikipedia' with no fields
                if prefixes and line.rstrip("\n") in {p.strip() for p in prefixes}:
                    s["malformed"] += 1
                continue
            r = parse_line(line, kind)
            if r is None:
                s["malformed"] += 1
                continue
            if r.page_id is None and line.count(" ") == 4:
                s["five_col"] += 1
            if not r.consistent:
                s["inconsistent"] += 1
            s["kept"] += 1
            yield r
    if stats is not None:
        stats.update(s)
