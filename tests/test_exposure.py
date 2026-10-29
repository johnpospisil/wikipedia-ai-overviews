import pandas as pd

from wao.build import exposure

ROLLOUT = pd.DataFrame(
    [
        {
            "country_iso2": "CH",
            "launch_date": "2025-03-25",
            "all_users_from": "2025-05-20",
            "removed_after": "",
        },
        {
            "country_iso2": "BE",
            "launch_date": "2025-03-25",
            "all_users_from": "2025-05-20",
            "removed_after": "",
        },
        {
            "country_iso2": "IR",
            "launch_date": "2025-05-20",
            "all_users_from": "2025-05-20",
            "removed_after": "2025-09-01",
        },
    ]
)
SUPPORT = pd.DataFrame(
    [
        {"wiki": "fr", "supported_from": "2025-03-25", "scope": "CH"},
        {"wiki": "fr", "supported_from": "2025-05-20", "scope": "all_live_countries"},
        {"wiki": "fa", "supported_from": "2025-05-20", "scope": "all_live_countries"},
    ]
)
DAYS = pd.date_range("2025-03-01", "2025-10-31")


def at(s, d):
    return s.loc[pd.Timestamp(d)]


def test_french_in_switzerland_from_europe_wave():
    any_, all_ = exposure.daily_availability(ROLLOUT, SUPPORT, "fr", "CH", DAYS)
    assert at(any_, "2025-03-24") == 0 and at(any_, "2025-03-25") == 1
    assert at(all_, "2025-05-19") == 0 and at(all_, "2025-05-20") == 1


def test_french_in_belgium_waits_for_language_support():
    any_, _ = exposure.daily_availability(ROLLOUT, SUPPORT, "fr", "BE", DAYS)
    assert at(any_, "2025-04-15") == 0
    assert at(any_, "2025-05-20") == 1


def test_iran_removed_after_last_listing():
    any_, _ = exposure.daily_availability(ROLLOUT, SUPPORT, "fa", "IR", DAYS)
    assert at(any_, "2025-06-01") == 1
    assert at(any_, "2025-09-01") == 1
    assert at(any_, "2025-09-02") == 0


def test_country_never_listed_is_zero():
    any_, all_ = exposure.daily_availability(ROLLOUT, SUPPORT, "fa", "CN", DAYS)
    assert any_.sum() == 0 and all_.sum() == 0
