"""P17 estimators recover a known effect on synthetic data and agree with each other."""

from __future__ import annotations

import numpy as np
import pytest

from wao.models import did
from wao.models.csdid import NEVER

G = np.array([20, 20, 20, 22, NEVER, NEVER, NEVER, NEVER, NEVER])
E = np.array([16, 19, 19, 19, NEVER, NEVER, NEVER, NEVER, NEVER])


def _Y(effect=-0.1, partial=-0.04, seed=3):
    rng = np.random.default_rng(seed)
    T = 30
    Y = rng.normal(0, 0.01, (len(G), T)) + rng.normal(0, 1, len(G))[:, None] + \
        np.linspace(0, 0.5, T)[None, :]
    t = np.arange(T)[None, :]
    return Y + effect * (t >= G[:, None]) + partial * ((t >= E[:, None]) & (t < G[:, None]))


@pytest.mark.parametrize("rule", ["exposure", "treatment"])
def test_estimators_recover_effect(rule):
    Y, miss = _Y(), np.zeros(30, bool)
    th, _ = did.overall(did.att_gt(Y, G, E, miss, rule))
    assert th == pytest.approx(-0.1, abs=0.02)
    assert did.sun_abraham(Y, G, E, miss) == pytest.approx(-0.1, abs=0.02)
    assert did.bjs(Y, G, E, miss, rule) == pytest.approx(-0.1, abs=0.02)


def test_partial_months_not_in_post_or_base():
    cells = did.att_gt(_Y(), G, E, np.zeros(30, bool), "exposure")
    en = [c for c in cells if c["e_first"] == 16]
    assert all(c["base"] == 15 for c in en)
    assert {c["kind"] for c in en if 16 <= c["t"] < 20} == {"partial"}


def test_ri_interval_covers_truth():
    Y, miss = _Y(), np.zeros(30, bool)
    A, B, true, _, _ = did.ri(Y, G, E, miss, "exposure")
    lo, hi = did.ri_interval(A, B, true)
    assert lo <= -0.1 <= hi
