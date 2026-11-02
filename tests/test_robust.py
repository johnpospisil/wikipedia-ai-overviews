"""P20: alternative cohort definitions are well formed."""

from __future__ import annotations

from wao import config
from wao.models import robust


def test_cohorts_cover_core_editions():
    for col in ("exposure", "exposure_all_users", "exposure_as_listed"):
        c = robust.cohorts(col)
        assert set(config.LANGS) <= set(c.index), col
        ok = c[(c.cohort != "never") & (c.first_exposed != "never")]
        assert (ok.first_exposed <= ok.cohort).all(), col
