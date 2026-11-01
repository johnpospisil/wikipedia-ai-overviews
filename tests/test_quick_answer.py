"""P12: the rule-based quick-answer label."""

from __future__ import annotations

import pandas as pd

from wao.build.quick_answer import rule


def test_rule_types_and_mixed_cases():
    f = pd.DataFrame({
        "lang": ["en"] * 7,
        "page_id": range(7),
        "coarse_type": ["human", "event", "list", "other", "other", "no_p31", "no_qid"],
        "has_infobox": [False, True, True, True, True, False, None],
        "lead_chars": [5000, 100, 100, 100, 900, 100, None],
    })  # fmt: skip
    r = rule(f).set_index("page_id")
    assert r.qa_rule.tolist()[:6] == [1, 0, 0, 1, 0, 0]  # median lead is 100
    assert pd.isna(r.loc[6, "qa_rule"]) and r.loc[6, "rule_reason"] == "missing features"
    assert r.qa_tier.tolist() == ["quick", "long", "long", "ambiguous", "long", "long",
                                  "ambiguous"]  # fmt: skip
    assert r.qa_core.tolist()[:3] == [1, 0, 0] and pd.isna(r.loc[3, "qa_core"])


def test_v3_tiers_for_disputed_types():
    f = pd.DataFrame({"lang": ["en"] * 3, "page_id": range(3),
                      "coarse_type": ["taxon", "chemical", "settlement"],
                      "has_infobox": [True] * 3, "lead_chars": [100] * 3})  # fmt: skip
    assert rule(f).qa_tier.tolist() == ["ambiguous", "ambiguous", "quick"]
