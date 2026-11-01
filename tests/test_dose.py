"""P18: TWFE dose slope and the hand-written wild cluster bootstrap on synthetic data."""

from __future__ import annotations

import numpy as np
import pytest

from wao.models import did, dose


def _panel(b=-0.15, seed=4):
    rng = np.random.default_rng(seed)
    G, T = 11, 60
    X = np.zeros((G, T))
    for g, (start, level) in enumerate(zip(rng.integers(30, 55, G), rng.uniform(0.1, 1, G),
                                           strict=True)):  # fmt: skip
        X[g, start:] = level
    Y = rng.normal(0, 1, G)[:, None] + rng.normal(0, 0.2, T)[None] + b * X + \
        rng.normal(0, 0.02, (G, T))
    return Y, X


def test_beta_recovers_slope():
    Y, X = _panel()
    assert dose.beta(Y, X) == pytest.approx(-0.15, abs=0.02)


def test_wcb_rejects_false_null_and_accepts_truth():
    Y, X = _panel()
    V = did.webb(Y.shape[0], 1999, 1)
    assert dose._wcb_p(Y, X, 0.0, V) < 0.05
    assert dose._wcb_p(Y, X, -0.15, V) > 0.05
