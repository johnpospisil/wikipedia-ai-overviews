"""P11: truncated-binomial imputation and the truncation simulation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from wao.build.truncation import impute, simulate, truncated_draw, truncated_mean


def test_truncated_mean_matches_direct_sum():
    n, p = np.array([20, 5, 1000]), np.array([0.3, 0.5, 0.001])
    m = truncated_mean(n, p)
    for i in range(3):
        k = np.arange(0, 10)
        pmf = stats.binom.pmf(k, n[i], p[i])
        assert m[i] == pytest.approx((k * pmf).sum() / pmf.sum())
    assert (m <= 9).all() and m[1] == pytest.approx(2.5, abs=1e-9)  # n=5: X <= 9 always


def test_truncated_mean_when_x_le_9_is_impossible():
    assert truncated_mean(np.array([100000]), np.array([0.5]))[0] == 9


def test_truncated_draw_stays_in_range_and_has_right_mean():
    rng = np.random.default_rng(0)
    n, p = np.full(20000, 40), np.full(20000, 0.15)
    d = truncated_draw(n, p, rng)
    assert d.min() >= 0 and d.max() <= 9
    assert d.mean() == pytest.approx(truncated_mean(n[:1], p[:1])[0], abs=0.05)


def test_simulation_naive_decline_exceeds_true_decline_for_small_articles():
    rng = np.random.default_rng(1)
    rows = []
    for i in range(400):
        v = 60 if i < 200 else 5000  # half the articles sit near the threshold
        s = rng.binomial(v, 0.2)
        rows.append({"lang": "xx", "page_id": i, "month": "2023-05",
                     "decile": 1 if i < 200 else 10, "weight": 1.0, "views_web": v,
                     "arr_search": s if s >= 10 else np.nan})  # fmt: skip
    sim = simulate(impute(pd.DataFrame(rows)))
    small = sim[(sim.decile == 1) & (sim.d == 0.3)].iloc[0]
    big = sim[(sim.decile == 10) & (sim.d == 0.3)].iloc[0]
    assert small.bias_pp > 5  # thinning pushes pairs below 10: decline exaggerated
    assert abs(big.bias_pp) < 1
