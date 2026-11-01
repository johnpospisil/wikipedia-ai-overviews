"""P14 blinding guard and trend-model design (synthetic data)."""

from __future__ import annotations

import pandas as pd

from wao.viz import eda


def _panel(lang: str) -> pd.DataFrame:
    months = pd.period_range("2018-01", "2026-09", freq="M").astype(str)
    return pd.DataFrame({"lang": lang, "month": months, "cs_usable": months >= "2019-04"})


def test_pre_stops_before_launch():
    p = eda.pre(_panel("en"))
    assert p.month.min() == "2019-04" and p.month.max() == "2024-04"


def test_design_kink_and_shocks():
    X = eda._design(eda.pre(_panel("fa")))
    assert (X.loc[X.index[eda.pre(_panel("fa")).month < eda.GPT], "kink"] == 0).all()
    assert X["d2019-11"].sum() == 1 and "en_auto" not in X
    Xe = eda._design(eda.pre(_panel("en")))
    assert "d2019-11" not in Xe and Xe.en_auto.iloc[0] == 0 and Xe.en_auto.iloc[-1] == 1
