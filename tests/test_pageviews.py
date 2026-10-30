"""P07: matching pageview_complete lines to sample articles, and decoding daily counts."""

from __future__ import annotations

import duckdb
import pandas as pd
import pytest

from wao.ingest import pageviews

# en sample: Paris (id 10); redirect Paris,_France (id 11) -> Paris
LOOKUP = pd.DataFrame(
    [
        ("id", "en", "10", 10, "id"),
        ("id", "en", "11", 10, "redirect_id"),
        ("title", "en", "Paris", 10, "title"),
        ("title", "en", "Paris,_France", 10, "redirect"),
    ],
    columns=["key_type", "lang", "key", "page_id", "match"],
)

LINES = [
    "de.wikipedia Paris 10 desktop 5 A5\n",  # other edition: ignored
    "en.wikipedia Paris 10 desktop 7 A3B4\n",  # id
    "en.wikipedia Paris,_France 10 mobile-web 2 C2\n",  # redirect followed: target id
    "en.wikipedia Paris,_France 11 desktop 1 A1\n",  # redirect page itself
    "en.wikipedia Paris null mobile-app 4 _4\n",  # null id, title
    "en.wikipedia Paris,_France mobile-web 3 A3\n",  # 5 columns, redirect title
    "en.wikipedia Paris 99 desktop 6 A6\n",  # deleted id 99 -> old_id
    "en.wikipedia Paris 50 desktop 8 A8\n",  # id 50 is a live different page -> dropped
    "en.wikipedia London 12 desktop 9 A9\n",  # not in sample
    "en.wikipedia Paris 10 tablet 1 A1\n",  # bad access
    "en.wikipedia\n",  # truncated
]


def test_match_lines():
    rows, bad = pageviews.match_lines(LINES, *pageviews._dicts(LOOKUP))
    got = [(r[2], r[3], r[4], r[6]) for r in rows]
    assert got == [
        ("id", "desktop", None, 7),
        ("id_alt_title", "mobile-web", None, 2),
        ("redirect_id", "desktop", None, 1),
        ("null_title", "mobile-app", None, 4),
        ("null_redirect", "mobile-web", None, 3),
        ("candidate", "desktop", 99, 6),
        ("candidate", "desktop", 50, 8),
    ]
    assert all(r[0] == "en" and r[1] == 10 for r in rows)
    assert bad == 2


@pytest.fixture
def page_table(tmp_path, monkeypatch):
    path = tmp_path / "page.parquet"
    pd.DataFrame({"page_id": [10, 11, 50], "namespace": 0}).to_parquet(path)
    monkeypatch.setattr(pageviews.sql_dumps, "out_path", lambda table, lang: path)


def test_resolve_and_decode(page_table):
    rows, _ = pageviews.match_lines(LINES, *pageviews._dicts(LOOKUP))
    daily, match, inconsistent = pageviews.resolve_and_decode(
        duckdb.connect(), pageviews._table(rows), "2024-03"
    )
    assert inconsistent == 0
    m = match.groupby("match").views.sum().to_dict()
    assert m == {
        "id": 7,
        "id_alt_title": 2,
        "redirect_id": 1,
        "null_title": 4,
        "null_redirect": 3,
        "old_id": 6,
        "other_page": 8,
    }
    d = daily.groupby(["date", "access"]).views.sum()
    assert d[(pd.Timestamp(2024, 3, 1), "desktop")] == 3 + 1 + 6  # A3 + redirect A1 + old_id A6
    assert d[(pd.Timestamp(2024, 3, 2), "desktop")] == 4
    assert d[(pd.Timestamp(2024, 3, 3), "mobile-web")] == 2
    assert d[(pd.Timestamp(2024, 3, 1), "mobile-web")] == 3
    assert d[(pd.Timestamp(2024, 3, 31), "mobile-app")] == 4
    assert daily.views.sum() == 7 + 2 + 1 + 4 + 3 + 6  # other_page excluded


def test_inconsistent_counted(page_table):
    rows, _ = pageviews.match_lines(
        ["en.wikipedia Paris 10 desktop 9 A3\n"], *pageviews._dicts(LOOKUP)
    )
    _, _, inconsistent = pageviews.resolve_and_decode(
        duckdb.connect(), pageviews._table(rows), "2024-02"
    )
    assert inconsistent == 1
