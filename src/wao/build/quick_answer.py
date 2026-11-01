"""P12: rule-based quick-answer label (docs/quick_answer_rubric.md) for every sample article.

Rule v1, fixed before the validation set was drawn or labelled:
  1 (quick-answer)  Wikidata coarse type is a "fact" type: human, settlement, admin_region,
                    country, chemical, astronomical, taxon, film, tv, music, video_game,
                    written_work, sports_event, structure, nature_place, organization
  0 (long-read)     event, health, list
  mixed types       other, no_p31, no_qid: 1 if the 2023 revision has an infobox and a lead no
                    longer than the edition's median lead (a bounded, fact-box subject), else 0;
                    missing text features -> label missing
Rule v3 (2026-11-01, chosen after the user's blind audit of 100 rows gave kappa 0.23 with Claude's
labels; disagreement concentrated in science and geography types). Three tiers:
  quick      core quick-answer: types both labellers mostly called quick (human, settlement,
             structure, sports_event, film, tv, music, video_game)
  long       core long-read: event, health, list, and mixed types that v1 calls long-read
  ambiguous  everything else (taxon, chemical, astronomical, nature_place, admin_region,
             country, organization, written_work, and mixed types with an infobox and short lead)
H2 contrasts quick vs long; ambiguous types enter sensitivity checks and P21's by-type estimates.
v3 was designed with the audit labels, so it is validated on a second, fresh blind audit
(wao.build.qa_validation draw2).
Inputs are pre-period only (Wikidata type from P06, 2023-12-31 features from P08).
Output: panels/quick_answer.parquet  lang, page_id, qa_rule (v1), rule_reason (v1), qa_tier (v3),
        qa_core (1 quick, 0 long, NA ambiguous), rule_version
Run: python -m wao.build.quick_answer
"""

from __future__ import annotations

import pandas as pd

from wao import config

RULE_VERSION = "v3"
FACT_TYPES = {"human", "settlement", "admin_region", "country", "chemical", "astronomical",
              "taxon", "film", "tv", "music", "video_game", "written_work", "sports_event",
              "structure", "nature_place", "organization"}  # fmt: skip
LONG_TYPES = {"event", "health", "list"}
MIXED_TYPES = {"other", "no_p31", "no_qid"}
CORE_QUICK = {"human", "settlement", "structure", "sports_event", "film", "tv", "music",
              "video_game"}  # fmt: skip


def out_path():
    return config.PANEL_DIR / "quick_answer.parquet"


def rule(f: pd.DataFrame) -> pd.DataFrame:
    """f: lang, page_id, coarse_type, has_infobox, lead_chars (one row per article)."""
    med = f.groupby("lang").lead_chars.transform("median")
    out = f[["lang", "page_id"]].copy()
    out["qa_rule"] = pd.Series(pd.NA, index=f.index, dtype="Int8")
    out["rule_reason"] = ""
    fact, long_ = f.coarse_type.isin(FACT_TYPES), f.coarse_type.isin(LONG_TYPES)
    out.loc[fact, ["qa_rule", "rule_reason"]] = [1, "fact type"]
    out.loc[long_, ["qa_rule", "rule_reason"]] = [0, "long-read type"]
    mixed = f.coarse_type.isin(MIXED_TYPES)
    known = f.has_infobox.notna() & f.lead_chars.notna()
    short_box = f.has_infobox.fillna(False).astype(bool) & (f.lead_chars <= med)
    out.loc[mixed & known & short_box, ["qa_rule", "rule_reason"]] = [1, "infobox, short lead"]
    out.loc[mixed & known & ~short_box, ["qa_rule", "rule_reason"]] = [0, "no infobox or long lead"]
    out.loc[mixed & ~known, "rule_reason"] = "missing features"
    out["qa_tier"] = "ambiguous"
    out.loc[f.coarse_type.isin(CORE_QUICK), "qa_tier"] = "quick"
    out.loc[long_ | (mixed & (out.qa_rule == 0)), "qa_tier"] = "long"
    out["qa_core"] = out.qa_tier.map({"quick": 1, "long": 0}).astype("Int8")
    out["rule_version"] = RULE_VERSION
    return out[["lang", "page_id", "qa_rule", "rule_reason", "qa_tier", "qa_core",
                "rule_version"]]  # fmt: skip


def main() -> None:
    cols = ["lang", "page_id", "coarse_type", "has_infobox", "lead_chars"]
    f = pd.read_parquet(config.PANEL_DIR / "article_features.parquet", columns=cols)
    r = rule(f)
    r.to_parquet(out_path(), index=False)
    print(r.groupby("lang").qa_tier.value_counts(normalize=True).unstack().round(3))


if __name__ == "__main__":
    main()
