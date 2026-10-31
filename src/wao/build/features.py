"""P08: one row of pre-period features per sample article (panels/article_features.parquet).

Inputs (all fixed at 2023-12-31 except topic):
  features/revisions/lang=*.parquet  the 2023-12-31 revision (wao.ingest.revisions): rev_id,
                                     rev_ts, created, n_rev_2023, wikitext features, templates
  features/infobox_templates.parquet infobox template names per edition
  features/topics.parquet            Lift Wing articletopic scores (current outlinks, 2026)
  panels/sample.parquet              coarse_type (Wikidata P31 rolled up, P06), decile, weight
Columns:
  lang, page_id, qid, coarse_type, decile, weight, status, rev_id, rev_ts, created,
  age_years (at 2023-12-31), n_rev_2023, bytes, prose_chars, lead_chars, n_sections,
  n_headings, n_refs, n_templates, has_infobox, is_redirect, topic, topic_score,
  topic_group (first level: Culture, Geography, History_and_Society, STEM),
  topic_confident (topic_score >= 0.5)
Text features are missing (status != ok) for articles with no revision before 2024, or whose
2023 revision was deleted or hidden (~0.3%). Character counts are comparable within an edition.

Run: python -m wao.build.features
"""

from __future__ import annotations

import pandas as pd

from wao import config
from wao.ingest.infobox_templates import by_rule

AS_OF = pd.Timestamp("2023-12-31 23:59:59", tz="UTC")
CONFIDENT = 0.5
F = config.PARQUET_DIR / "features"


def out_path():
    return config.PANEL_DIR / "article_features.parquet"


def infobox_flags(rev: pd.DataFrame, boxes: pd.DataFrame) -> pd.Series:
    """True if any template of the revision is a known infobox (list, or the naming rule)."""
    known = boxes.groupby("lang").template.agg(set).to_dict()
    flags = []
    for lang, tpls in zip(rev.lang, rev.templates, strict=True):
        if tpls is None:
            flags.append(pd.NA)
            continue
        names = known.get(lang, set())
        flags.append(any(t in names or by_rule(lang, t) for t in tpls))
    return pd.Series(flags, index=rev.index, dtype="boolean")


def top_topics(topics: pd.DataFrame) -> pd.DataFrame:
    t = topics.dropna(subset=["topic"]).sort_values("score", ascending=False)
    t = t.drop_duplicates(["lang", "page_id"])[["lang", "page_id", "topic", "score"]]
    t = t.rename(columns={"score": "topic_score"})
    t["topic_group"] = t.topic.str.split(".").str[0]
    t["topic_confident"] = t.topic_score >= CONFIDENT
    return t


def build() -> pd.DataFrame:
    rev = pd.read_parquet(F / "revisions")
    rev["lang"] = rev["lang"].astype(str)
    for c in ("rev_ts", "created"):
        rev[c] = pd.to_datetime(rev[c], utc=True)
    rev["has_infobox"] = infobox_flags(rev, pd.read_parquet(F / "infobox_templates.parquet"))
    rev["n_templates"] = rev.templates.map(lambda t: len(t) if t is not None else None)
    rev["age_years"] = (AS_OF - rev.created).dt.days / 365.25
    rev["is_redirect"] = rev.is_redirect.astype("boolean")
    cols = ["lang", "page_id", "qid", "coarse_type", "decile", "weight"]
    s = pd.read_parquet(config.PANEL_DIR / "sample.parquet", columns=cols)
    df = s.merge(rev.drop(columns=["templates", "rev_bytes", "parse_error"], errors="ignore"),
                 on=["lang", "page_id"], how="left", validate="1:1")  # fmt: skip
    df = df.merge(top_topics(pd.read_parquet(F / "topics.parquet")), on=["lang", "page_id"],
                  how="left", validate="1:1")  # fmt: skip
    df["topic_confident"] = df.topic_confident.fillna(False).astype(bool)
    return df


def main() -> None:
    df = build()
    df.to_parquet(out_path(), index=False)
    print(f"{len(df):,} articles -> {out_path()}")
    print(df.groupby("lang")[["has_infobox", "topic_confident"]].mean().round(3))


if __name__ == "__main__":
    main()
