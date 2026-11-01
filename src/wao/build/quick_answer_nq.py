"""P12: score the quick-answer rule against Google's Natural Questions (NQ).

Each NQ query that its landing page answers (has a long answer) is one draw from "typical
queries landing on this article". The quick-answer rate of a group of pages is the share of
those queries that also have a short answer (one fact, or yes/no). It is computed by Wikidata
coarse type and by rule tier, with Wilson 95% intervals. NQ queries are question-style and from
2016-17 English Google, so rates are compared across groups, not read as absolute levels.

Pages: NQ title -> current en page (via the 2026 page and redirect tables) -> QID (P06 frame) ->
coarse type (the P06 rollup; types for non-sample items fetched with the same cached SPARQL
helpers and saved separately). Rule tiers for mixed types need 2023 features, so they are known
for sample articles only; mixed-type pages outside the sample form their own group.

Outputs: PARQUET_DIR/context/nq_pages.parquet  title, page_id, qid, coarse_type
         report/qa/p12_nq_types.csv   coarse_type: queries, quick-answer rate, interval, v3 tier
         report/qa/p12_nq_tiers.csv   rule (v1 binary, v3 tiers): rate by group, gap
         report/qa/p12_nq_splithalf.csv  v4 (tiers set from NQ type rates) derived on one half of
                                      the pages and scored on the other, both ways
         data/reference/nq_type_rates.csv  coarse_type, NQ quick-answer rate, interval, v4 tier
v4 tiers: a type is quick if its Wilson interval lies above the overall NQ rate, long if below,
ambiguous if it straddles it.
Run: python -m wao.build.quick_answer_nq
"""

from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

from wao import config
from wao.build.quick_answer import CORE_QUICK, FACT_TYPES, LONG_TYPES, MIXED_TYPES
from wao.ingest import wikidata_types as wt
from wao.ingest.natural_questions import out_dir as nq_dir

QA = config.REPORT_DIR / "qa"
Z = 1.96


def pages_path():
    return config.PARQUET_DIR / "context" / "nq_pages.parquet"


def wilson(k: np.ndarray, n: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    p = k / n
    den = 1 + Z**2 / n
    mid = (p + Z**2 / (2 * n)) / den
    half = Z * np.sqrt(p * (1 - p) / n + Z**2 / (4 * n**2)) / den
    return mid - half, mid + half


def map_pages(con) -> pd.DataFrame:
    P = config.PARQUET_DIR  # noqa: N806
    return con.sql(f"""
        with t as (select distinct replace(title, ' ', '_') as title from '{nq_dir()}/*.parquet'),
        p as (select page_id, title, is_redirect
              from '{P}/wiki_sql/page/lang=en/part.parquet' where namespace = 0),
        r as (select page_id, target from '{P}/wiki_sql/redirect/lang=en/part.parquet'),
        hit as (select t.title, p.page_id, p.is_redirect from t left join p using (title)),
        res as (select h.title,
                       case when h.is_redirect then p2.page_id else h.page_id end as page_id
                from hit h left join r on r.page_id = h.page_id and h.is_redirect
                left join p p2 on p2.title = r.target and not p2.is_redirect)
        select res.title, res.page_id, f.qid
        from res left join (select page_id, qid from '{P}/frame.parquet' where lang = 'en') f
          using (page_id)""").df()


def types(qids: list[str]) -> pd.Series:
    d = config.PARQUET_DIR / "wikidata"
    p31_old, p279_old = pd.read_parquet(d / "p31.parquet"), pd.read_parquet(d / "p279.parquet")
    new = sorted(set(qids) - set(p31_old.qid))
    p31_new = wt.fetch_p31(new)
    no_p31 = sorted(set(new) - set(p31_new.qid))
    s = wt._session()
    own = pd.DataFrame(wt._pairs(s, no_p31, "P279"), columns=["class", "parent"])
    known = set(p279_old["class"]) | set(p279_old["parent"])
    fresh = (set(p31_new["class"]) | set(own["parent"])) - known
    p279 = pd.concat([p279_old, own, wt.fetch_p279(fresh)]).drop_duplicates(ignore_index=True)
    p31 = pd.concat([p31_old, p31_new]).drop_duplicates(ignore_index=True)
    return wt.coarse_types(qids, p31, p279)


def by_type(ct: pd.Series, rule: str) -> np.ndarray:
    """Tier implied by the coarse type alone (mixed types need features: 'mixed')."""
    quick = FACT_TYPES if rule == "v1" else CORE_QUICK
    out = np.where(ct.isin(MIXED_TYPES), "mixed", "ambiguous" if rule == "v3" else "quick")
    out = np.where(ct.isin(quick), "quick", out)
    return np.where(ct.isin(LONG_TYPES), "long", out)


def v4_tiers(t: pd.DataFrame, overall: float) -> pd.Series:
    return pd.Series(np.select([t.lo > overall, t.hi < overall], ["quick", "long"], "ambiguous"),
                     index=t.index)  # fmt: skip


def split_half(nq: pd.DataFrame) -> pd.DataFrame:
    half = pd.util.hash_pandas_object(nq.title, index=False) % 2
    rows = []
    for a in (0, 1):
        fit, test = nq[half == a], nq[half != a]
        tier = v4_tiers(rates(fit, "coarse_type"), fit.has_short.mean())
        g = rates(test.assign(v4=test.coarse_type.map(tier)), "v4")
        for grp, r in g.iterrows():
            rows.append({"fit_half": a, "group": grp, "queries": r.queries, "rate": r.rate})
        for rule in ("v1", "v3"):
            for grp, r in rates(test, rule).iterrows():
                rows.append({"fit_half": a, "group": f"{rule}:{grp}", "queries": r.queries,
                             "rate": r.rate})  # fmt: skip
    return pd.DataFrame(rows)


def rates(df: pd.DataFrame, by: str) -> pd.DataFrame:
    g = df.groupby(by).agg(queries=("has_short", "size"), short=("has_short", "sum"),
                           pages=("page_id", "nunique"))  # fmt: skip
    g["rate"] = g.short / g.queries
    g["lo"], g["hi"] = wilson(g.short.to_numpy(float), g.queries.to_numpy(float))
    return g


def main() -> None:
    con = duckdb.connect()
    if pages_path().exists():
        pages = pd.read_parquet(pages_path())
    else:
        pages = map_pages(con)
        q = pages.qid.dropna().unique().tolist()
        pages = pages.merge(types(q).rename_axis("qid").reset_index(), on="qid", how="left")
        pages.loc[pages.page_id.notna() & pages.qid.isna(), "coarse_type"] = "no_qid"
        pages.to_parquet(pages_path(), index=False)
    nq = con.sql(f"""select replace(title, ' ', '_') as title, has_short
                     from '{nq_dir()}/*.parquet' where has_long""").df()  # fmt: skip
    nq = nq.merge(pages, on="title", how="left")
    mapped, typed = nq.page_id.notna().mean(), nq.coarse_type.notna().mean()
    print(f"answered queries {len(nq):,}; mapped {mapped:.1%}; typed {typed:.1%}")
    nq = nq.dropna(subset=["coarse_type"])
    overall = nq.has_short.mean()

    t = rates(nq, "coarse_type")
    t["v1"] = by_type(t.index.to_series(), "v1")
    t["v3"] = by_type(t.index.to_series(), "v3")
    t["vs_overall"] = np.select([t.lo > overall, t.hi < overall], ["above", "below"], "within")
    QA.mkdir(parents=True, exist_ok=True)
    t.sort_values("rate", ascending=False).round(4).to_csv(QA / "p12_nq_types.csv")

    # tiers: rule output where the article is in the sample (mixed types need features)
    r = pd.read_parquet(config.PANEL_DIR / "quick_answer.parquet")
    r = r[r.lang == "en"][["page_id", "qa_rule", "qa_tier"]]
    nq = nq.merge(r, on="page_id", how="left")
    nq["v1"] = by_type(nq.coarse_type, "v1")
    nq.loc[nq.qa_rule.notna(), "v1"] = nq.qa_rule.map({1: "quick", 0: "long"})
    nq["v3"] = by_type(nq.coarse_type, "v3")
    nq.loc[nq.qa_tier.notna(), "v3"] = nq.qa_tier
    rows = []
    for rule in ("v1", "v3"):
        g = rates(nq, rule).reset_index().rename(columns={rule: "group"})
        g.insert(0, "rule", rule)
        rows.append(g)
    tiers = pd.concat(rows, ignore_index=True)
    tiers["overall"] = overall
    tiers.round(4).to_csv(QA / "p12_nq_tiers.csv", index=False)
    sh = split_half(nq)
    sh.round(4).to_csv(QA / "p12_nq_splithalf.csv", index=False)
    t["v4"] = v4_tiers(t, overall)
    t.reset_index()[["coarse_type", "queries", "rate", "lo", "hi", "v4"]].round(4).to_csv(
        config.REFERENCE_DIR / "nq_type_rates.csv", index=False
    )
    print(sh.pivot(index="group", columns="fit_half", values="rate").round(3))
    print(t.sort_values("rate", ascending=False)[["queries", "rate", "lo", "hi", "v3",
                                                  "vs_overall"]].round(3).to_string())  # fmt: skip
    print(tiers.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
