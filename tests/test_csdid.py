"""P15 estimator: matches the `differences` package, honours exposure leads, and RI is exact."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from wao.models.csdid import NEVER, assignments, att, att_weights, ri_pvalue

G = np.array([10, 10, 10, 12, 17, 17, 17, 19, NEVER])


def _panel(seed: int = 1, effect: float = -0.2):
    rng = np.random.default_rng(seed)
    Y = rng.normal(size=(len(G), 30)).cumsum(1)
    return Y + np.where(np.arange(30)[None, :] >= G[:, None], effect, 0)


def test_matches_differences_package():
    differences = pytest.importorskip("differences")
    Y = _panel()
    rows = [(i, t + 1, Y[i, t], G[i] + 1 if np.isfinite(G[i]) else np.nan)
            for i in range(len(G)) for t in range(Y.shape[1])]  # fmt: skip
    df = pd.DataFrame(rows, columns=["id", "t", "y", "cohort"]).set_index(["id", "t"])
    a = differences.ATTgt(data=df, cohort_column="cohort", base_period="universal")
    a.fit("y", control_group="not_yet_treated", progress_bar=False)
    ref = a.aggregate("cohort", overall=True).iloc[0, 0]
    assert att(Y, G, control="treatment") == pytest.approx(ref, abs=1e-10)


def test_recovers_constant_effect_without_noise():
    Y = np.zeros((len(G), 30)) + np.where(np.arange(30)[None, :] >= G[:, None], -0.3, 0)
    assert att(Y, G) == pytest.approx(-0.3)


def test_exposure_lead_moves_base_and_excludes_partial_months():
    E = G.copy()
    E[0] = 6  # unit 0 partly exposed from 6, cohort 10
    W = att_weights(G, 30, E=E)
    assert W[0, 5] < 0 and W[0, 9] == 0  # base is 5; month 9 is neither base nor post
    assert W[0, 6:10].sum() == 0
    assert np.isclose(W.sum(), 0)


def test_missing_month_skipped_and_weights_balance():
    miss = np.zeros(30, bool)
    miss[16] = True
    W = att_weights(G, 30, miss)
    assert np.allclose(W[:, 16], 0) and np.isclose(W.sum(), 0)


def test_assignments_and_ri():
    g, e = assignments(np.array([0, 0, 1, NEVER]))
    assert len(g) == 12 and e.shape == g.shape
    assert ri_pvalue(1.0, np.array([0.5, -1.0, 2.0, 0.1])) == 0.5
