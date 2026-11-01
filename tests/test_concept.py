"""P19: the closed-form wild cluster bootstrap matches P18's array version."""

from __future__ import annotations

import numpy as np
import pytest

from wao.models import concept, did, dose


def test_closed_form_wcb_matches_dose_version():
    rng = np.random.default_rng(7)
    G, T = 10, 40
    X = np.zeros((G, T))
    for g in range(G):
        X[g, rng.integers(20, 38):] = rng.uniform(0.1, 1)
    Y = rng.normal(0, 1, G)[:, None] + rng.normal(0, 0.2, T)[None] - 0.1 * X + \
        rng.normal(0, 0.05, (G, T))
    V = did.webb(G, 999, 2)
    yt, xt = dose._demean(Y).ravel(), dose._demean(X).ravel()
    cl = np.repeat(np.arange(G), T)
    est = concept._wcb(yt, xt, np.ones(G * T), cl, V)
    assert est["beta"] == pytest.approx(dose.beta(Y, X))
    assert est["wcb_p"] == pytest.approx(dose._wcb_p(Y, X, 0.0, V))
