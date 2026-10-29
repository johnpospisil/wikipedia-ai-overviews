"""P04: parser tests on small fixtures (tests/fixtures/), written before the parsers."""

import json
from pathlib import Path

import pytest

from wao.ingest import clickstream, pageview_dumps, wikidata

FX = Path(__file__).parent / "fixtures"


# --- clickstream ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name", ["clickstream-xxwiki-2026-09.tsv", "clickstream-xxwiki-2026-09.tsv.gz"]
)
def test_clickstream_reads_plain_and_gzip(name):
    tbl, stats = clickstream.read(FX / "clickstream" / name)
    assert tbl.num_rows == 14
    assert stats["rejected"] == 2
    assert tbl.column_names == ["prev", "curr", "type", "n", "referrer"]


def test_clickstream_keeps_awkward_titles_verbatim():
    tbl, _ = clickstream.read(FX / "clickstream" / "clickstream-xxwiki-2026-09.tsv")
    curr = set(tbl.column("curr").to_pylist())
    assert {"Zürich", "東京都", '"Weird_Al"_Yankovic', "C++", "100%_(song)"} <= curr
    assert "Rock_'n'_roll" in tbl.column("prev").to_pylist()


def test_clickstream_decodes_quote_wrapped_titles():
    # Real files write titles containing '"' as "\"Weird_Al\"_Yankovic" (found in P04).
    tbl, _ = clickstream.read(FX / "clickstream" / "clickstream-xxwiki-2026-09.tsv")
    assert '"Weird_Al"_Yankovic' in tbl.column("curr").to_pylist()
    assert 'Toys_"R"_Us' in tbl.column("prev").to_pylist()
    assert not any("\\" in t for t in tbl.column("curr").to_pylist())  # no escapes left


def test_clickstream_referrer_classes():
    tbl, _ = clickstream.read(FX / "clickstream" / "clickstream-xxwiki-2026-09.tsv")
    rows = tbl.to_pylist()
    ref = {(r["prev"], r["curr"]): r["referrer"] for r in rows}
    assert ref[("other-search", "Albert_Einstein")] == "search"
    assert ref[("other-empty", "Albert_Einstein")] == "empty"
    assert ref[("other-internal", "Albert_Einstein")] == "internal_other"
    assert ref[("other-external", "Albert_Einstein")] == "external"
    assert ref[("other-other", "Albert_Einstein")] == "other"
    assert ref[("J._Robert_Oppenheimer", "Albert_Einstein")] == "link"
    assert ref[("Main_Page", "Albert_Einstein")] == "link_other"  # type 'other': link not in page


def test_clickstream_counts_are_integers_at_or_above_threshold():
    tbl, stats = clickstream.read(FX / "clickstream" / "clickstream-xxwiki-2026-09.tsv")
    n = tbl.column("n").to_pylist()
    assert all(isinstance(v, int) for v in n)
    assert stats["min_n"] == 10
    assert stats["total"] == sum(n)


def test_clickstream_filename_metadata():
    assert clickstream.parse_name("clickstream-enwiki-2026-09.tsv.gz") == ("en", "2026-09")
    assert clickstream.parse_name("clickstream-zh_yuewiki-2025-01.tsv.gz") == ("zh_yue", "2025-01")


# --- pageview_complete ---------------------------------------------------------------------


def test_decode_monthly_days_and_daily_hours():
    assert pageview_dumps.decode("A100B100_100", base=1) == {1: 100, 2: 100, 31: 100}
    assert pageview_dumps.decode("[10\\10]5^1", base=1) == {27: 10, 28: 10, 29: 5, 30: 1}
    assert pageview_dumps.decode("A10X20", base=0) == {0: 10, 23: 20}


def test_parse_line_six_columns():
    r = pageview_dumps.parse_line("en.wikipedia Albert_Einstein 736 mobile-web 450 A150O150^150")
    assert (r.wiki, r.title, r.page_id, r.access, r.total) == (
        "en.wikipedia",
        "Albert_Einstein",
        736,
        "mobile-web",
        450,
    )
    assert r.counts == {1: 150, 15: 150, 30: 150}
    assert r.consistent


def test_parse_line_null_page_id_and_five_columns():
    r = pageview_dumps.parse_line("en.wikipedia Some_Redirect null desktop 3 B3")
    assert r.page_id is None and r.total == 3
    r5 = pageview_dumps.parse_line("en.wikipedia No_Page_Id_Five_Cols desktop 5 A2C3")
    assert r5.page_id is None and r5.access == "desktop" and r5.counts == {1: 2, 3: 3}


def test_parse_line_rejects_malformed_and_flags_bad_totals():
    assert pageview_dumps.parse_line("en.wikipedia") is None
    bad = pageview_dumps.parse_line("en.wikipedia Bad_Total 99 desktop 10 A3")
    assert bad is not None and not bad.consistent


@pytest.mark.parametrize("name", ["pageviews-209901-user.txt", "pageviews-209901-user.bz2"])
def test_iter_rows_filters_wikis_and_counts(name):
    stats = {}
    rows = list(
        pageview_dumps.iter_rows(FX / "pageviews" / name, wikis={"en.wikipedia"}, stats=stats)
    )
    assert {r.wiki for r in rows} == {"en.wikipedia"}
    assert len(rows) == 7  # 'en.wiktionary' must not match the 'en.wikipedia' filter
    assert stats["five_col"] == 1
    assert stats["inconsistent"] == 1
    assert stats["malformed"] == 1
    titles = {r.title for r in rows}
    assert "Zürich" in titles


def test_iter_rows_daily_file_uses_hours():
    rows = list(
        pageview_dumps.iter_rows(FX / "pageviews" / "pageviews-20990101-user.txt", kind="daily")
    )
    assert rows[0].counts == {0: 10, 23: 20} and rows[0].consistent


# --- Wikidata ------------------------------------------------------------------------------


@pytest.fixture
def entities():
    return json.loads((FX / "wikidata" / "wbgetentities.json").read_text(encoding="utf-8"))


def test_wikidata_truthy_p31_and_sitelinks(entities):
    e = wikidata.parse_entity(entities["entities"]["Q937"], wikis={"en", "de", "zh-yue"})
    assert e["qid"] == "Q937"
    assert e["p31"] == ["Q5"]  # deprecated statement dropped
    assert e["sitelinks"] == {
        "en": "Albert Einstein",
        "de": "Albert Einstein",
        "zh-yue": "愛因斯坦",
    }  # wikiquote dropped


def test_wikidata_preferred_rank_wins_and_novalue_skipped(entities):
    e = wikidata.parse_entity(entities["entities"]["Q90"], wikis={"fr"})
    assert e["p31"] == ["Q515"]


def test_wikidata_missing_redirect_and_empty(entities):
    ents = entities["entities"]
    assert wikidata.parse_entity(ents["Q404"], wikis={"en"}) is None
    r = wikidata.parse_entity(ents["Q1000"], wikis={"en"})
    assert r["qid"] == "Q2000" and r["redirected_from"] == "Q1000"
    empty = wikidata.parse_entity(ents["Q123"], wikis={"en"})
    assert empty["p31"] == [] and empty["sitelinks"] == {}


def test_wikidata_parse_response(entities):
    out = wikidata.parse_response(entities, wikis={"en", "de", "fr"})
    assert sorted(e["qid"] for e in out) == ["Q123", "Q2000", "Q90", "Q937"]


def test_wikidata_error_response_raises():
    with pytest.raises(ValueError, match="no-such-entity"):
        wikidata.parse_response({"error": {"code": "no-such-entity"}}, wikis={"en"})
