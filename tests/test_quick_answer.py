"""P12: the rule-based quick-answer label."""

from __future__ import annotations

import pandas as pd

from wao.build.quick_answer import rule

NQ = pd.DataFrame({"coarse_type": ["human", "event", "list", "other", "no_p31", "no_qid", "taxon",
                                   "chemical", "settlement", "film"],
                   "rate": [0.71, 0.71, 0.69, 0.69, 0.65, 0.77, 0.67, 0.65, 0.73, 0.83],
                   "v4": ["long", "long", "long", "long", "long", "quick", "long", "long",
                          "ambiguous", "quick"]})  # fmt: skip


def test_rule_types_and_mixed_cases():
    f = pd.DataFrame({
        "lang": ["en"] * 7,
        "page_id": range(7),
        "coarse_type": ["human", "event", "list", "other", "other", "no_p31", "no_qid"],
        "has_infobox": [False, True, True, True, True, False, None],
        "lead_chars": [5000, 100, 100, 100, 900, 100, None],
    })  # fmt: skip
    r = rule(f, NQ).set_index("page_id")
    assert r.qa_rule.tolist()[:6] == [1, 0, 0, 1, 0, 0]  # median lead is 100
    assert pd.isna(r.loc[6, "qa_rule"]) and r.loc[6, "rule_reason"] == "missing features"
    assert r.qa_tier_v3.tolist() == ["quick", "long", "long", "ambiguous", "long", "long",
                                     "ambiguous"]  # fmt: skip
    assert r.qa_tier.tolist() == ["long", "long", "long", "long", "long", "long", "quick"]
    assert r.qa_nq_rate.tolist()[:2] == [0.71, 0.71] and (r.rule_version == "v4").all()


def test_tiers_for_disputed_types():
    f = pd.DataFrame({"lang": ["en"] * 4, "page_id": range(4),
                      "coarse_type": ["taxon", "chemical", "settlement", "film"],
                      "has_infobox": [True] * 4, "lead_chars": [100] * 4})  # fmt: skip
    r = rule(f, NQ)
    assert r.qa_tier_v3.tolist() == ["ambiguous", "ambiguous", "quick", "quick"]
    assert r.qa_tier.tolist() == ["long", "long", "ambiguous", "quick"]
    assert r.qa_core.isna().tolist() == [False, False, True, False]
