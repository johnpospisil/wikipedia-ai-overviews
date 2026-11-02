"""DuckDB's log() is base 10; model outcomes must use ln() (P21 found log10 in P19 and P21)."""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "wao"
SQL_LOG = re.compile(r"(?<![\w.])log\(1 \+")


def test_no_base10_log_in_sql():
    bad = [f"{p.name}:{i}" for p in SRC.rglob("*.py")
           for i, line in enumerate(p.read_text().splitlines(), 1)
           if SQL_LOG.search(line) and ("select" in line.lower() or " as " in line
                                         or "then " in line)]  # fmt: skip
    assert not bad, bad
