"""P32: the release holds derived data only, documents every column and matches its checksums."""

from __future__ import annotations

import duckdb
import pandas as pd
import pytest

from wao import config, release

FORBIDDEN = ("text", "body", "wikitext", "content", "user_name", "username", "email", "ip")
TEXT_OK = {"title"}  # titles are in Wikimedia's CC0 pageview dumps


@pytest.fixture(scope="module")
def out():
    if not (release.OUT / "SHA256SUMS").exists():
        pytest.skip("run `make release` first")
    return release.OUT


def _cols(path) -> list[str]:
    return [r[0] for r in duckdb.execute(f"describe select * from '{path}'").fetchall()]


def test_no_text_or_user_columns(out):
    for f in (out / "data").glob("*.parquet"):
        bad = [c for c in _cols(f) if c not in TEXT_OK and any(k == c or c.startswith(k + "_")
               for k in FORBIDDEN)]  # fmt: skip
        assert not bad, (f.name, bad)


def test_every_column_is_documented(out):
    for f in (out / "data").glob("*.parquet"):
        assert set(_cols(f)) <= set(release.COLUMNS), (f.name, set(_cols(f)) - set(release.COLUMNS))


def test_checksums_match(out):
    for line in (out / "SHA256SUMS").read_text().splitlines():
        digest, path = line.split("  ", 1)
        assert release.sha256(out / path) == digest, path


def test_csv_matches_parquet(out):
    d = out / "data"
    for f in d.glob("*.parquet"):
        n = duckdb.execute(f"select count(*) from '{f}'").fetchone()[0]
        csv = (f"'{d}/article_month_csv/*.csv.gz'" if f.stem == "article_month"
               else f"'{f.with_suffix('.csv')}'")  # fmt: skip
        assert duckdb.execute(f"select count(*) from read_csv({csv})").fetchone()[0] == n, f.name


def test_rows_match_the_panels(out):
    p = config.PANEL_DIR
    arts = duckdb.execute(f"select count(*) from '{out}/data/articles.parquet'").fetchone()[0]
    assert arts == len(pd.read_parquet(p / "sample.parquet", columns=["page_id"]))
    n = duckdb.execute(f"select count(*) from '{p}/panel_article_month/*/*.parquet'").fetchone()[0]
    rel = duckdb.execute(f"select count(*) from '{out}/data/article_month.parquet'").fetchone()[0]
    assert rel == n


def test_censored_search_stays_empty(out):
    bad = duckdb.execute(f"""select count(*) from '{out}/data/article_month.parquet'
                         where search_censored and arr_search is not null""").fetchone()[0]
    assert bad == 0


def test_card_licences(out):
    card = (out / "README.md").read_text()
    assert "license: other" in card and "CC0 1.0" in card and "CC BY-SA 3.0" in card
    assert "StatCounter" in card and "not affiliated" in card.lower()
    assert all(c in card for c in release.STATCOUNTER_COLUMNS)
