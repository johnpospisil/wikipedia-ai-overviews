"""P10: engine grouping, language weighting, ranking-update indicator, Trends noise."""

from __future__ import annotations

import pandas as pd
import pytest

from wao.build import search_context as sc
from wao.ingest.trends import noise


@pytest.fixture
def ref(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "REF", tmp_path)
    pd.DataFrame({
        "country_iso2": ["RU", "RU", "RU", "RU", "UA", "UA", "--", "XX"],
        "month": ["2024-01"] * 8,
        "engine": ["Google", "YANDEX", "YANDEX RU", "Unnamed: 1", "Google", "bing", "Google",
                   "Google"],
        "share": [0.40, 0.30, 0.30, None, 0.90, 0.10, 0.5, 0.0],
    }).to_csv(tmp_path / "search_share.csv", index=False)  # fmt: skip
    pd.DataFrame({"wiki": ["ru", "ru", "ru"], "country_iso2": ["RU", "UA", "ZZ"],
                  "share": [0.6, 0.2, 0.2]}).to_csv(tmp_path / "country_shares.csv",
                                                      index=False)  # fmt: skip
    return tmp_path


def test_country_shares_groups_engines_and_drops_junk(ref):
    cs = sc.country_shares().set_index(["country_iso2", "engine"]).share
    assert set(cs.index.get_level_values(0)) == {"RU", "UA"}  # "--" and all-zero XX dropped
    assert cs["RU", "yandex"] == pytest.approx(0.6)
    assert cs["UA", "bing"] == pytest.approx(0.1)


def test_lang_shares_renormalise_over_countries_with_data(ref):
    ls = sc.lang_shares(sc.country_shares()).set_index("engine").share
    # ZZ has no data: weights become RU 0.75, UA 0.25
    assert ls["google"] == pytest.approx(0.75 * 0.4 + 0.25 * 0.9)
    assert ls["yandex"] == pytest.approx(0.75 * 0.6)
    assert ls.sum() == pytest.approx(1)


def test_ranking_monthly_counts_days_and_default_length(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "REF", tmp_path)
    pd.DataFrame({
        "date": ["2024-01-25", "2024-03-10", "2024-03-01"],
        "end_date": ["2024-02-03", None, "2024-03-02"],
        "event": ["January core update", "March core update", "March spam update"],
        "category": ["google_ranking_update"] * 3, "scope": ["global"] * 3, "source_url": [""] * 3,
    }).to_csv(tmp_path / "events.csv", index=False)  # fmt: skip
    m = sc.ranking_monthly("2024-01", "2024-04").set_index("month")
    assert m.loc["2024-01", "core_days"] == 7 and m.loc["2024-02", "core_days"] == 3
    assert m.loc["2024-03", "core_days"] == 15  # no end date: 14 days after the start
    assert m.loc["2024-03", "other_update_days"] == 2
    assert not m.loc["2024-04", "core_update"]


def test_trends_noise_rescales_short_window():
    months = [f"2021-{m:02d}" for m in range(1, 7)]
    long = [40, 50, 60, 50, 40, 30]
    t = pd.DataFrame({"country_iso2": "US", "window": ["long"] * 6 + ["short"] * 6,
                      "month": months * 2, "interest": long + [2 * v for v in long]})  # fmt: skip
    n = noise(t).iloc[0]
    assert n.scale == pytest.approx(0.5) and n.median_abs_pct_gap == 0
