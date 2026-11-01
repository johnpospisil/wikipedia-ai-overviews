"""P16 ITS: the gap recovers a known AIO break on synthetic data."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from wao.models import its


def _data(step: float = -0.15) -> pd.DataFrame:
    months = pd.period_range(its.START, its.END, freq="M").astype(str)
    d = pd.DataFrame({"month": months, "exposure": np.where(months >= its.AIO, 0.8, 0.0)})
    t = its._yrs(d.month, its.START)
    rng = np.random.default_rng(0)
    y = 20 - 0.05 * t + step * (d.month >= its.AIO) + rng.normal(0, 0.005, len(d))
    d["search_arr_na"] = np.exp(y)
    d.loc[d.month == its.BOT, "search_arr_na"] = np.nan
    d["search_arr_rs"] = np.exp(y)
    d["search_share"] = 0.45
    return d


def test_gap_recovers_step():
    d = _data()
    X, y = its.design(d, "B"), its.outcome(d, "search", "B")
    r = its.fit(y, X)
    g = {row["period"]: row for row in its.gaps(y, X, r, d)}
    assert g["all post"]["gap_log"] == pytest.approx(-0.15, abs=0.01)
    assert g["all post"]["months"] == 28  # 2025-04 missing


def test_counterfactual_zeroes_only_aio_terms():
    X = its.design(_data(), "A")
    Xc = its.counterfactual(X)
    assert (Xc[["aio_level", "aio_slope"]] == 0).all().all()
    assert (Xc.drop(columns=["aio_level", "aio_slope"]) == X.drop(columns=["aio_level",
                                                                          "aio_slope"])).all().all()
