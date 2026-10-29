import json
from pathlib import Path

import duckdb

from wao import config
from wao.ingest import clickstream_ingest as ci

FX = Path(__file__).parent / "fixtures" / "clickstream" / "clickstream-xxwiki-2026-09.tsv.gz"


def test_convert_writes_pairs_article_aggregates_and_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PARQUET_DIR", tmp_path)
    stats = ci.convert("xx", "2026-09", FX, duckdb.connect())
    assert stats["rows"] == 14 and stats["rejected"] == 2
    assert json.loads(ci.done_marker("xx", "2026-09").read_text())["rows"] == 14

    con = duckdb.connect()
    art = tmp_path / "clickstream_article" / "lang=xx" / "month=2026-09" / "part.parquet"
    a = {
        r[0]: r
        for r in con.execute(
            f"SELECT title, arr_search, arr_link, arr_link_other, arr_total, out_links FROM '{art}'"
        ).fetchall()
    }
    # Albert_Einstein: search 180835; link 1532 (Oppenheimer); link_other 2549 (Main_Page)
    assert a["Albert_Einstein"][1] == 180835
    assert a["Albert_Einstein"][2] == 1532 and a["Albert_Einstein"][3] == 2549
    assert a["Albert_Einstein"][4] == 180835 + 49409 + 8580 + 4748 + 12 + 2549 + 1532
    # Pages that only appear as referrers still get a row with their outgoing clicks.
    assert a["Main_Page"][5] == 2549 and a["Main_Page"][4] is None
    assert a['Toys_"R"_Us'][5] == 15

    total = con.execute(f"SELECT sum(n) FROM '{tmp_path}/clickstream/**/*.parquet'").fetchone()[0]
    assert total == stats["total"]

    out = ci.lang_month_totals()
    lm = con.execute(f"SELECT search, link, total FROM '{out}'").fetchone()
    assert lm[0] == 180835 + 5000 + 777 + 321 + 999 + 10
    assert lm[2] == stats["total"]
