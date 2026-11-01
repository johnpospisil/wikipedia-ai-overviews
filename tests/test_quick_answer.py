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
    assert (r.rule_version == "v1").all()
