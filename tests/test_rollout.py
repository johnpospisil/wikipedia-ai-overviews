from datetime import date

import pandas as pd

from wao.build import rollout

AUG_2024 = """AI Overviews availability
AI Overviews are currently available:
To all users in the US who meet the
minimum age requirement
To users above the age of 18 in the UK, India, Mexico, Brazil, Indonesia, and Japan.
To users who opted into the “
AI Overviews and more
AI Overviews will become available to more users, languages, and regions over time.
"""

APR_2025 = """AI Overviews are currently available:
To all users in these countries and territories:
Americas
Canada
United States
Asia-Pacific
Korea
To all users who are 18 or older in these countries and territories:
Germany
United Kingdom
To users who opted into the “
AI Overviews will become available to more users
"""

JUN_2025 = """AI Overviews are currently available:
To all users, in the following
countries, territories
and
languages
:
Countries and territories
Europe, the Middle East & Africa
Iran
Russia
Türkiye
Languages
French
Persian (Farsi)
"AI Overviews and more" in Search Labs
AI Overviews when you search with an image or Circle to Search
"""


def test_parse_aug_2024_inline_list():
    countries, languages = rollout.parse_availability(AUG_2024)
    names = dict(countries)
    assert names["United States"] == "us_all"
    assert {"United Kingdom", "India", "Mexico", "Brazil", "Indonesia", "Japan"} <= set(names)
    assert names["Japan"] == "adult_signed_in"
    assert languages == []


def test_parse_apr_2025_tiers():
    countries, _ = rollout.parse_availability(APR_2025)
    names = dict(countries)
    assert names["Korea"] == "all"
    assert names["Germany"] == "adult_signed_in"
    assert "Americas" not in names


def test_parse_jun_2025_languages_skip_labs_line():
    countries, languages = rollout.parse_availability(JUN_2025)
    assert [c for c, _ in countries] == ["Iran", "Russia", "Türkiye"]
    assert languages == ["French", "Persian (Farsi)"]


def test_iso2_aliases():
    assert rollout._iso2("Korea") == "KR"
    assert rollout._iso2("Türkiye") == "TR"
    assert rollout._iso2("Germany") == "DE"


def test_rollout_snaps_to_announcement_and_brackets_otherwise():
    fs = pd.DataFrame(
        [
            {
                "kind": "country",
                "name": "Japan",
                "iso2": "JP",
                "first_seen": date(2024, 8, 27),
                "last_absent": date(2024, 8, 15),
                "first_tier": "adult_signed_in",
                "first_all_users": date(2025, 3, 29),
                "last_seen": date(2026, 10, 29),
            },
            {
                "kind": "country",
                "name": "Korea",
                "iso2": "KR",
                "first_seen": date(2024, 12, 22),
                "last_absent": date(2024, 12, 19),
                "first_tier": "adult_signed_in",
                "first_all_users": date(2025, 3, 29),
                "last_seen": date(2026, 10, 29),
            },
            {
                "kind": "country",
                "name": "Iran",
                "iso2": "IR",
                "first_seen": date(2025, 5, 30),
                "last_absent": date(2025, 4, 27),
                "first_tier": "all",
                "first_all_users": date(2025, 5, 30),
                "last_seen": date(2025, 9, 1),
            },
        ]
    )
    snaps = [pd.Timestamp(d) for d in ("2025-03-20", "2025-03-29", "2026-10-29")]
    r = rollout.build_rollout(fs, snaps).set_index("country_iso2")
    assert str(r.loc["JP", "launch_date"]) == "2024-08-15"
    assert str(r.loc["JP", "all_users_from"]) == "2025-03-25"
    assert r.loc["KR", "wave"] == "wayback_only"
    assert str(r.loc["IR", "launch_date"]) == "2025-05-20"
    assert str(r.loc["IR", "removed_after"]) == "2025-09-01"
