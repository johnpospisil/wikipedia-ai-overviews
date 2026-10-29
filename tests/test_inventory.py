import pandas as pd

from wao.ingest import inventory

LISTING = """<html><body><pre><a href="../">../</a>
<a href="2017-11/">2017-11/</a>     05-Dec-2017 10:00     -
<a href="clickstream-enwiki-2026-09.tsv.gz">clickstream-enwiki-2026-09.tsv.gz</a>  03-Oct-2026 08:26  479161129
</pre></body></html>"""


def test_parse_listing_skips_parent_and_reads_sizes():
    entries = inventory.parse_listing(LISTING)
    assert [e.name for e in entries] == ["2017-11/", "clickstream-enwiki-2026-09.tsv.gz"]
    assert entries[0].size is None
    assert entries[1].size == 479161129


def test_clickstream_filename_pattern():
    m = inventory.CLICKSTREAM_FILE.match("clickstream-enwiki-2026-09.tsv.gz")
    assert m.groups() == ("en", "2026-09")


def test_availability_matrix_finds_gaps():
    cs = pd.DataFrame(
        {
            "lang": ["en", "en", "en", "de"],
            "month": ["2018-01", "2018-02", "2018-04", "2018-02"],
            "bytes": [1, 1, 1, 1],
        }
    )
    mat = inventory.availability_matrix(cs).set_index("lang")
    assert mat.loc["en", "gaps"] == "2018-03"
    assert mat.loc["en", "months"] == 3
    assert mat.loc["de", "gaps"] == ""
