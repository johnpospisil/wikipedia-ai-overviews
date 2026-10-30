# ruff: noqa: E501  (SQL dump lines are long by nature)
import gzip
from pathlib import Path

import pyarrow.parquet as pq

from wao.ingest import pageview_months, sql_dumps

FX = Path(__file__).parent / "fixtures"

PAGE_SQL = r"""-- MySQL dump
CREATE TABLE `page` (`page_id` int(8) unsigned NOT NULL);
INSERT INTO `page` VALUES
(2,0,'AWK',0,0,0.38,'20260908152532','20260914102612',79790580,18474,'wikitext',NULL),
(5,2,'AJT',0,0,0.26,'20240911233122','20240911233117',1551782,177,'wikitext',NULL),
(9,0,'O\'Brien_(1,0,\'x\',0,_film)',0,0,0.1,'2026','2026',1,1,'wikitext',NULL),
(11,0,'Zürich',1,0,0.2,'2026','2026',1,1,'wikitext',NULL),
(12,0,'Back\\slash',0,0,0.2,'2026','2026',1,1,'wikitext',NULL);
INSERT INTO `page` VALUES (13,0,'Old_style',0,0,0.1,'2026','2026',1,1,'wikitext',NULL),(14,0,'Two',0,0,0.1,'2026','2026',1,1,'wikitext',NULL);
"""
PROPS_SQL = r"""INSERT INTO `page_props` VALUES
(2,'defaultsort','Awk',NULL),
(2,'wikibase_item','Q213970',NULL),
(9,'disambiguation','',NULL),
(9,'wikibase_item','Q1',NULL),
(12,'page_image_free','a\'b.svg',NULL);
"""
REDIRECT_SQL = r"""INSERT INTO `redirect` VALUES
(11,0,'AWK','',''),
(20,0,'O\'Brien','','Section'),
(21,4,'Policy','',''),
(22,0,'Elsewhere','wikt','');
"""


def _gz(tmp_path, name, text):
    p = tmp_path / name
    with gzip.open(p, "wt", encoding="utf-8") as fh:
        fh.write(text)
    return p


def test_parse_page_handles_escapes_namespaces_and_both_insert_styles(tmp_path):
    t = sql_dumps.parse_page(_gz(tmp_path, "page.sql.gz", PAGE_SQL)).to_pylist()
    by_id = {r["page_id"]: r for r in t}
    assert set(by_id) == {2, 5, 9, 11, 12, 13, 14}
    assert by_id[9]["title"] == "O'Brien_(1,0,'x',0,_film)"  # tuple-like text inside a title
    assert by_id[12]["title"] == "Back\\slash"
    assert by_id[11]["title"] == "Zürich" and by_id[11]["is_redirect"]
    assert by_id[5]["namespace"] == 2 and by_id[5]["title"] is None


def test_parse_page_props_keeps_qid_and_disambiguation(tmp_path):
    t = sql_dumps.parse_page_props(_gz(tmp_path, "pp.sql.gz", PROPS_SQL)).to_pylist()
    assert t == [
        {"page_id": 2, "qid": "Q213970", "is_disambiguation": False},
        {"page_id": 9, "qid": "Q1", "is_disambiguation": True},
    ]


def test_parse_redirect_keeps_same_wiki_article_targets(tmp_path):
    t = sql_dumps.parse_redirect(_gz(tmp_path, "rd.sql.gz", REDIRECT_SQL)).to_pylist()
    assert t == [{"page_id": 11, "target": "AWK"}, {"page_id": 20, "target": "O'Brien"}]


def test_pageview_months_parse_lines_and_convert(tmp_path, monkeypatch):
    lines = (FX / "pageviews" / "pageviews-209901-user.txt").read_text().splitlines(True)
    rows, bad = pageview_months.parse_lines(lines, langs=("en",))
    assert len(rows) == 7 and bad == 1  # en.wiktionary excluded; truncated line counted
    assert ("en", "Some_Redirect", None, "desktop", 3) in rows
    assert ("en", "No_Page_Id_Five_Cols", None, "desktop", 5) in rows

    monkeypatch.setattr(pageview_months.config, "PARQUET_DIR", tmp_path)
    s = pageview_months.convert("2099-01", FX / "pageviews" / "pageviews-209901-user.bz2")
    t = pq.read_table(pageview_months.out_path("2099-01")).to_pylist()
    assert s["rows"] == len(t) == 9  # en 7 + de 1 + ja 1
    assert {
        "lang": "ja",
        "title": "東京都",
        "page_id": 1590,
        "access": "mobile-web",
        "views": 12,
    } in t
