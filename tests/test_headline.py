"""P28: pin the headline estimates (report/qa, written by `make models` on the real data).

A rerun of the pipeline that moves any of these beyond its tolerance fails here, so a silent
change in data, code or a dependency cannot change the article's numbers unnoticed. Tolerances
are loose enough for floating-point and solver noise (the RI and bootstrap draws are seeded), tight
enough that any substantive change trips them. Update a pin only with a Deviations entry or a
dated note in DATA.md saying why it moved.
"""

from __future__ import annotations

import pandas as pd
import pytest

from wao import config

QA = config.REPO_ROOT / "report" / "qa"  # always the real outputs, never the sample path
CS = "Callaway-Sant'Anna"


def _csv(name: str) -> pd.DataFrame:
    path = QA / name
    if not path.exists():
        pytest.skip(f"{name} not built")
    return pd.read_csv(path)


@pytest.mark.parametrize(
    "window, pct, ri_p",
    [("primary", 2.65, 0.582), ("full", -7.96, 0.403)],
)
def test_h1_staggered_did(window, pct, ri_p):
    r = _csv("p17_att.csv").query("estimator == @CS").set_index("window").loc[window]
    assert r.pct == pytest.approx(pct, abs=0.5)
    assert r.ri_p == pytest.approx(ri_p, abs=0.02)
    assert r.ri_lo95 < 0 < r.ri_hi95  # H1 inconclusive: the interval spans zero


@pytest.mark.parametrize(
    "spec, pct",
    [
        ("11 editions (pre-registered)", 5.98),
        ("9 editions (P17 set)", -13.48),
        ("10 editions, no fa (exploratory)", -12.65),
    ],  # fmt: skip
)
def test_dose_response(spec, pct):
    r = _csv("p18_twfe.csv").set_index("spec").loc[spec]
    assert r.pct_full == pytest.approx(pct, abs=0.5)
    assert r.wcb_p > 0.05


@pytest.mark.parametrize(
    "editions, pct", [("11 editions (pre-registered)", -2.74), ("10 editions, no fa", -10.04)]
)
def test_within_concept_search(editions, pct):
    d = _csv("p19_estimates.csv")
    r = d[(d.outcome == "search") & (d.editions == editions) & (d.weights == "weighted")].iloc[0]
    assert r.pct == pytest.approx(pct, abs=0.5)
    assert r.wcb_p > 0.05


def test_h2_quick_answer():
    r = _csv("p21_h2.csv").iloc[0]
    assert r.pct == pytest.approx(0.54, abs=0.3)
    assert r.wcb_p == pytest.approx(0.736, abs=0.03)


def test_holm_none_supported():
    h = _csv("holm.csv")
    assert not h.supported.any()
    assert h.p.min() == pytest.approx(0.4245, abs=0.03)


def test_no_robustness_variant_finds_a_significant_loss():
    r = _csv("p20_robustness.csv")
    r = r[~r.group.isin(["placebo", "negative control"]) & r.ri_p.notna()]
    assert not ((r.ri_p < 0.05) & (r.pct < 0)).any()
    assert len(r) >= 50
