"""P04: parser checks on real files (skipped unless the drive and files are present)."""

import pytest

from wao import config
from wao.ingest import clickstream

pytestmark = pytest.mark.data
EN = config.CLICKSTREAM_DIR / "en" / "clickstream-enwiki-2026-09.tsv.gz"


@pytest.mark.skipif(not EN.exists(), reason="real clickstream file not on disk")
def test_real_english_clickstream_parses_cleanly():
    tbl, stats = clickstream.read(EN)
    assert stats["rejected"] == 0
    assert stats["min_n"] == 10
    assert stats["rows"] == 33_553_254
    referrers = set(tbl.column("referrer").to_pylist()[:2_000_000])
    assert referrers <= {
        "search",
        "empty",
        "internal_other",
        "external",
        "other",
        "link",
        "link_other",
    }
    curr = tbl.column("curr").to_pylist()
    assert '"Weird_Al"_Yankovic' in curr and '"\\"Weird_Al\\"_Yankovic"' not in curr
