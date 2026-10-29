"""Clickstream parsing: one monthly (referrer, article, type, n) file -> Arrow table.

Format (no header, tab-separated): prev, curr, type, n. `prev` is an article title or one of the
`other-*` pseudo-referrers; `type` is link | external | other. Titles never contain tabs
(MediaWiki forbids them). A title containing '"' is written wrapped in quotes with inner quotes
backslash-escaped ("\"Weird_Al\"_Yankovic"); quoting is off in the reader and that form is
decoded explicitly. Rows that don't parse are rejected and counted, never silently dropped.
"""

from __future__ import annotations

import re
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.compute as pc

PSEUDO_REFERRERS = {
    "other-search": "search",
    "other-empty": "empty",
    "other-internal": "internal_other",  # internal non-article pages (search page, special…)
    "other-external": "external",
    "other-other": "other",
}
NAME = re.compile(r"clickstream-(\w+?)wiki-(\d{4}-\d{2})\.tsv(?:\.gz)?$")


def _unquote(col: str) -> str:
    """SQL: '"\\"Weird_Al\\"_Yankovic"' -> '"Weird_Al"_Yankovic'; other titles unchanged."""
    return (
        f"CASE WHEN length({col}) >= 2 AND starts_with({col}, '\"') AND ends_with({col}, '\"') "
        f"THEN replace({col}[2:-2], '\\\"', '\"') ELSE {col} END"
    )


def parse_name(name: str) -> tuple[str, str]:
    m = NAME.search(name)
    if not m:
        raise ValueError(f"not a clickstream file name: {name}")
    return m.group(1), m.group(2)


def read(path: Path, con: duckdb.DuckDBPyConnection | None = None) -> tuple[pa.Table, dict]:
    """Read one file. Adds `referrer`: search/empty/internal_other/external/other for pseudo
    referrers, `link` for article-to-article links, `link_other` for type 'other' (the link is
    no longer in the page, e.g. clicks from a since-edited version)."""
    con = con or duckdb.connect()
    con.execute("DROP TABLE IF EXISTS reject_errors; DROP TABLE IF EXISTS reject_scans")
    cases = " ".join(f"WHEN '{k}' THEN '{v}'" for k, v in PSEUDO_REFERRERS.items())
    tbl = con.sql(
        f"""
        WITH raw AS (
          SELECT * FROM read_csv(?, delim='\t', header=false, quote='', escape='',
                                 auto_detect=false, store_rejects=true,
                                 columns={{'prev':'VARCHAR','curr':'VARCHAR','type':'VARCHAR',
                                          'n':'BIGINT'}})
        ), dec AS (
          SELECT {_unquote("prev")} AS prev, {_unquote("curr")} AS curr, type, n FROM raw
        )
        SELECT prev, curr, type, n,
               CASE prev {cases}
                    ELSE CASE type WHEN 'other' THEN 'link_other' ELSE 'link' END END AS referrer
        FROM dec
        """,
        params=[str(path)],
    ).to_arrow_table()
    rejected = con.execute("SELECT count(DISTINCT line) FROM reject_errors").fetchall()[0][0]
    n = tbl.column("n")
    stats = {
        "rows": tbl.num_rows,
        "rejected": rejected,
        "total": pc.sum(n).as_py() or 0,
        "min_n": pc.min(n).as_py(),
    }
    return tbl, stats
