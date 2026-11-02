"""P28: `make all SAMPLE=1` must recover the effect planted in the synthetic mini-dump.

The data-generating process (src/wao/build/synthetic.py) removes 10% of search arrivals at full
AI Overviews exposure and nothing else. Run after `make all SAMPLE=1` (CI does); skipped when the
sample outputs are absent. Tolerances allow for the sampling noise of 120 articles per edition.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from wao import config

QA = config.REPO_ROOT / ".sample" / "report" / "qa"
CS = "Callaway-Sant'Anna"


def _csv(name: str) -> pd.DataFrame:
    if not (QA / "synthetic_truth.csv").exists():
        pytest.skip("run `make all SAMPLE=1` first")
    return pd.read_csv(QA / name)


def test_truth_recorded():
    assert _csv("synthetic_truth.csv").true_pct.iloc[0] == pytest.approx(-10.0)


@pytest.mark.parametrize("window", ["primary", "full"])
def test_staggered_did_finds_the_planted_loss(window):
    # binary cohorts at exposure ~0.6-0.9, so the ATT is about -6% to -9%
    r = _csv("p17_att.csv").query("estimator == @CS").set_index("window").loc[window]
    assert -14 < r.pct < -4
    assert r.ri_hi95 < 0 and r.ri_p < 0.05


def test_dose_response_brackets_the_truth():
    r = _csv("p18_twfe.csv").set_index("spec").loc["11 editions (pre-registered)"]
    assert r.pct_lo < -10 < r.pct_hi
    assert r.pct_full < 0


def test_within_concept_brackets_the_truth():
    d = _csv("p19_estimates.csv")
    r = d[(d.outcome == "search") & (d.editions == "11 editions (pre-registered)")
          & (d.weights == "weighted")].iloc[0]  # fmt: skip
    assert r.pct_lo < -10 < r.pct_hi


def test_true_nulls_are_not_rejected():
    # no quick-answer, editor or depth effect was planted
    assert _csv("p21_h2.csv").iloc[0].wcb_p > 0.01
    h6 = _csv("p24_h6.csv").iloc[0]
    assert h6.lo_pct < 0 < h6.hi_pct


def test_all_figures_written():
    decomposition = _csv("p25_decomposition.csv")  # skips before the sample is built
    figs = config.REPO_ROOT / ".sample" / "report" / "figures"
    names = ["hero_estimates", "chart2_quick_long", "chart3_referral_mix", "chart4_editions",
             "chart5_types", "chart6_editors", "forest_robustness"]  # fmt: skip
    for n in names:
        for suffix in ("", "_dark"):
            assert (figs / f"{n}{suffix}.png").exists(), n
    assert np.isfinite(decomposition.select_dtypes("number")).any().any()
