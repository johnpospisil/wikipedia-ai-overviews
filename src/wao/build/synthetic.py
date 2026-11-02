"""P28: synthetic mini-dump for `make all SAMPLE=1` (and CI), with a known effect.

Two steps, both writing only under the sample directories (WAO_*_DIR set by the Makefile):

  raw     reference CSVs (cohorts, exposure and ranking updates copied from data/reference, so the
          real rollout drives the design) and one gzip clickstream TSV per edition x month,
          2019-04..2026-09, in the real dump format. The real ingest (wao.ingest.clickstream_ingest)
          then parses them; its downloader skips files already present at the listed size.
  panels  the three analysis panels in the real schemas (P13), built from the ingested clickstream
          aggregates plus synthetic pageviews, features and labels; and p14_trend_models.csv from
          the real P14 code, which the decomposition (P25) reads.

Data-generating process (article i, edition l, month t), N articles per edition:
    log E[search] = a_i + b_l + season_l(month) + trend_l * t + common_t + u_lt + TRUE * x_lt
x = the real P03 exposure. TRUE = log(0.90): full exposure removes 10% of search arrivals; nothing
else depends on exposure (quick-answer rate, popularity, access, editors, depth: all true nulls).
Counts are Poisson; pairs under 10 are dropped from the files, as in the real dumps (so truncation
is real here too). 2025-04 is written about 5 days short (x 25/30), like the real file.

Usage: python -m wao.build.synthetic raw | panels
"""

from __future__ import annotations

import gzip
import shutil
import sys

import duckdb
import numpy as np
import pandas as pd

from wao import config

TRUE = np.log(0.90)
N, SEED = 120, 28
START, END, SHORT = "2019-04", "2026-09", "2025-04"
EDS = ["en", "ja", "pt", "es", "de", "it", "pl", "zh", "fr", "ru", "fa"]
REFS = ["language_cohorts.csv", "language_exposure.csv", "ranking_updates_monthly.csv",
        "data_breaks.csv"]  # fmt: skip
TYPES = ["human", "settlement", "film", "taxon", "organization", "sports_event", "chemical",
         "list", "music", "structure"]  # fmt: skip
TOPICS = ["Culture", "Geography", "STEM", "History_and_Society"]


def months() -> list[str]:
    return [str(p) for p in pd.period_range(START, END, freq="M")]


def _exposure() -> pd.DataFrame:
    e = pd.read_csv(config.REFERENCE_DIR / "language_exposure.csv")
    e = e[e.wiki.isin(EDS)].rename(columns={"wiki": "lang"})
    grid = pd.MultiIndex.from_product([EDS, months()], names=["lang", "month"]).to_frame(False)
    return grid.merge(e[["lang", "month", "exposure"]], how="left").fillna({"exposure": 0.0})


def articles() -> pd.DataFrame:
    """The article roster: N per edition; concept i is article i in every edition."""
    rng = np.random.default_rng(SEED)
    rows = []
    for k, lang in enumerate(EDS):
        a = rng.normal(np.log(60), 1.3, N)
        for i in range(N):
            title = '"Quoted"_Article_0' if i == 0 else f"Article_{i}"
            rows.append(dict(lang=lang, page_id=1000 * (k + 1) + i, i=i, title=title, a=a[i],
                             search_share=rng.uniform(0.35, 0.7)))  # fmt: skip
    d = pd.DataFrame(rows)
    d["decile"] = d.groupby("lang").a.transform(lambda s: pd.qcut(s, 10, labels=False) + 1)
    d["coarse_type"] = np.array(TYPES)[d.i % len(TYPES)]
    rate = dict(zip(TYPES, np.linspace(0.62, 0.84, len(TYPES)), strict=True))  # all three tiers
    d["qa_nq_rate"] = d.coarse_type.map(rate).round(4)
    d["qa_tier"] = np.where(d.qa_nq_rate >= 0.76, "quick",
                            np.where(d.qa_nq_rate <= 0.70, "long", "ambiguous"))  # fmt: skip
    d["topic_group"] = np.array(TOPICS)[d.i % len(TOPICS)]
    return d


def expected(art: pd.DataFrame) -> pd.DataFrame:
    """Expected search arrivals and other referrers per article-month (before Poisson draws)."""
    rng = np.random.default_rng(SEED + 2)
    m = months()
    x = _exposure()
    common = pd.Series(np.cumsum(rng.normal(-0.002, 0.02, len(m))), index=m)
    lang = pd.DataFrame({"lang": EDS, "b": rng.normal(0, 0.3, len(EDS)),
                         "trend": rng.normal(-0.02, 0.02, len(EDS))})  # fmt: skip
    season = {e: np.r_[0, rng.normal(0, 0.06, 11)] for e in EDS}
    g = x.merge(lang, on="lang")
    p = pd.PeriodIndex(g.month, freq="M")
    g["t"] = (p - pd.Period(START, "M")).map(lambda v: v.n) / 12
    g["s"] = [season[e][mm - 1] for e, mm in zip(g.lang, p.month, strict=True)]
    g["u"] = rng.normal(0, 0.03, len(g))
    g["lm"] = g.b + g.s + g.trend * g.t + common[g.month].values + g.u + TRUE * g.exposure
    g["short"] = np.where(g.month == SHORT, 25 / 30, 1.0)
    d = art.merge(g[["lang", "month", "lm", "short", "exposure"]], on="lang")
    d["mu_search"] = np.exp(d.a + d.lm) * d.short
    rest = (
        np.exp(d.a + rng.normal(0, 0.05, len(d))) * d.short * (1 - d.search_share) / d.search_share
    )
    d["mu_empty"], d["mu_link"] = 0.45 * rest, 0.45 * rest
    d["mu_external"], d["mu_internal"] = 0.06 * rest, 0.04 * rest
    return d


def raw() -> None:
    config.REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    for f in REFS:
        shutil.copy(config.REPO_ROOT / "data" / "reference" / f, config.REFERENCE_DIR / f)
    art = articles()
    d = expected(art)
    rng = np.random.default_rng(SEED + 3)
    files = []
    for (lang, month), g in d.groupby(["lang", "month"]):
        lines = []
        n = rng.poisson(g[["mu_search", "mu_empty", "mu_external", "mu_internal", "mu_link"]])
        for title, i, row in zip(g.title, g.i, n, strict=True):
            cur = title if not title.startswith('"') else '"\\"Quoted\\"_Article_0"'
            for ref, k in zip(("other-search", "other-empty", "other-external", "other-internal"),
                              row[:4], strict=True):  # fmt: skip
                if k >= 10:
                    lines.append(f"{ref}\t{cur}\texternal\t{k}")
            # internal links come from two other articles of the same edition
            for j, k in enumerate((row[4] // 2, row[4] - row[4] // 2)):
                if k >= 10:
                    src = (i + 7 * j + 1) % (N - 1) + 1
                    lines.append(f"Article_{src}\t{cur}\tlink\t{k}")
        name = f"clickstream-{lang}wiki-{month}.tsv.gz"
        path = config.CLICKSTREAM_DIR / lang / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        files.append(dict(lang=lang, month=month, file=name, bytes=path.stat().st_size,
                          url=f"file://{path}"))  # fmt: skip
    pd.DataFrame(files).to_csv(config.REFERENCE_DIR / "clickstream_files.csv", index=False)
    print(f"synthetic raw: {len(files)} clickstream files, {N} articles x {len(EDS)} editions")


def _article_panel(art: pd.DataFrame, d: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(SEED + 4)
    src = config.PARQUET_DIR / "clickstream_article" / "**" / "*.parquet"
    cs = (
        duckdb.connect()
        .execute(f"""
        select lang, month, title, arr_search, arr_total, coalesce(arr_link, 0) arr_link,
               out_links from read_parquet('{src}', hive_partitioning=true)""")
        .df()
    )
    p = d.merge(cs, on=["lang", "month", "title"], how="left")
    # pageviews: every arrival is a view (web) plus apps; drawn independently of the clickstream
    web = rng.poisson((p.mu_search + p.mu_empty + p.mu_link + p.mu_external + p.mu_internal)
                      / p.short)  # fmt: skip
    p["views_desktop"] = rng.binomial(web, 0.4).astype(float)
    p["views_mobile_web"] = web - p.views_desktop
    p["views_app"] = rng.poisson(0.05 * web).astype(float)
    p["views_automated"] = rng.poisson(0.1 * web).astype(float)
    p["search_censored"] = p.arr_search.isna()
    p["search_hidden_est"] = np.where(p.search_censored, 5.0, np.nan)
    p["search_hidden_upper"] = np.where(p.search_censored, 9, 0)
    p["edits"] = rng.poisson(0.5, len(p))
    out = pd.DataFrame({
        "lang": p.lang, "page_id": p.page_id, "month": p.month, "qid": "Q" + p.i.astype(str),
        "decile": p.decile, "coarse_type": p.coarse_type, "weight": 100.0, "in_lang_sample": True,
        "in_concept_panel": True, "w_concept": 1.0, "views_desktop": p.views_desktop,
        "views_mobile_web": p.views_mobile_web, "views_app": p.views_app,
        "views_automated": p.views_automated, "cs_available": True, "cs_usable": True,
        "cs_short": p.month == SHORT, "bot_break": p.month >= SHORT, "arr_search": p.arr_search,
        "search_censored": p.search_censored, "arr_total_pub": p.arr_total.fillna(0),
        "arr_link_pub": p.arr_link.fillna(0), "out_links_pub": p.out_links.fillna(0),
        "search_hidden_est": p.search_hidden_est, "search_hidden_upper": p.search_hidden_upper,
        "edits": p.edits, "edits_user": p.edits, "edits_anon": 0, "edits_bot": 0,
        "editors": np.minimum(p.edits, 1), "qa_tier": p.qa_tier,
        "qa_core": p.qa_tier.map({"quick": 1, "long": 0}).astype("Int8"),
        "qa_nq_rate": p.qa_nq_rate, "has_infobox": p.i % 2 == 0, "prose_chars": 5000.0,
        "lead_chars": 600.0, "n_sections": 8.0, "n_refs": 20.0, "age_years": 12.0,
        "topic_group": p.topic_group, "topic_confident": True})  # fmt: skip
    return out


def _lang_panel(am: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(SEED + 5)
    cs = (
        duckdb.connect()
        .execute(f"select * from '{config.PARQUET_DIR / 'clickstream_lang_month.parquet'}'")
        .df()
    )
    v = am.groupby(["lang", "month"])[["views_desktop", "views_mobile_web", "views_app",
                                       "views_automated"]].sum().reset_index()  # fmt: skip
    hid = am.groupby(["lang", "month"]).search_hidden_est.sum().rename("hidden").reset_index()
    c = pd.read_csv(config.REFERENCE_DIR / "language_cohorts.csv").rename(columns={"wiki": "lang"})
    e = pd.read_csv(config.REFERENCE_DIR / "language_exposure.csv").rename(columns={"wiki": "lang"})
    d = (cs.merge(v, on=["lang", "month"]).merge(hid, on=["lang", "month"])
         .merge(c[["lang", "cohort", "first_exposed", "role"]], on="lang")
         .merge(e[["lang", "month", "exposure", "exposure_all_users", "exposure_as_listed"]],
                on=["lang", "month"], how="left"))  # fmt: skip
    short = d.month == SHORT
    p = pd.PeriodIndex(d.month, freq="M")
    t = (p - pd.Period(START, "M")).map(lambda x: x.n).values / 12
    d = d.assign(
        core=True, cs_available=True, cs_usable=True, cs_short=short, bot_break=d.month >= SHORT,
        month_complete=True, search_arr=d.search, total_arr=d.total, link_arr=d.link,
        link_other_arr=d.link_other, internal_other_arr=d.internal_other,
        external_arr=d.external, empty_arr=d.empty, other_arr=d.other, cs_articles=d.articles,
        search_share=d.search / d.total, link_share=d.link / d.total,
        search_arr_na=d.search.where(~short), search_arr_rs=np.where(short, d.search * 30 / 25,
                                                                     d.search),
        total_arr_na=d.total.where(~short), total_arr_rs=np.where(short, d.total * 30 / 25,
                                                                  d.total),
        search_arr_corr=d.search + d.hidden, search_arr_corr_upper=d.search + 1.8 * d.hidden,
        active_user=np.round(2000 * np.exp(-0.03 * t + rng.normal(0, 0.03, len(d)))),
        very_active_user=200.0, active_anonymous=800.0, edits_user=40000.0, edits_anonymous=8000.0,
        google_share=np.where(d.lang == "ru", 0.45, 0.9), core_days=0)  # fmt: skip
    for col in ("exposure", "exposure_all_users", "exposure_as_listed"):
        d[col] = d[col].fillna(0.0)
    cols = ["lang", "month", "core", "role", "cohort", "first_exposed", "exposure",
            "exposure_all_users", "exposure_as_listed", "cs_available", "cs_usable", "cs_short",
            "bot_break", "month_complete", "search_arr", "total_arr", "link_arr",
            "link_other_arr", "internal_other_arr", "external_arr", "empty_arr", "other_arr",
            "cs_articles", "search_share", "link_share", "search_arr_na", "search_arr_rs",
            "total_arr_na", "total_arr_rs", "search_arr_corr", "search_arr_corr_upper",
            "views_desktop", "views_mobile_web", "views_app", "views_automated", "active_user",
            "very_active_user", "active_anonymous", "edits_user", "edits_anonymous",
            "google_share", "core_days"]  # fmt: skip
    return d[cols].sort_values(["lang", "month"]).reset_index(drop=True)


def _item_panel(am: pd.DataFrame, lp: pd.DataFrame) -> pd.DataFrame:
    x = lp[["lang", "month", "exposure", "cohort", "role"]]
    d = am.merge(x, on=["lang", "month"])
    return pd.DataFrame({
        "qid": d.qid, "lang": d.lang, "month": d.month, "page_id": d.page_id,
        "w_concept": d.w_concept, "coarse_type": d.coarse_type, "qa_tier": d.qa_tier,
        "qa_nq_rate": d.qa_nq_rate, "views_user": d.views_desktop + d.views_mobile_web
        + d.views_app, "views_web": d.views_desktop + d.views_mobile_web,
        "arr_search": d.arr_search, "search_censored": d.search_censored,
        "search_hidden_est": d.search_hidden_est, "cs_usable": d.cs_usable,
        "cs_short": d.cs_short, "bot_break": d.bot_break, "exposure": d.exposure,
        "cohort": d.cohort, "role": d.role})  # fmt: skip


def panels() -> None:
    from wao.viz import eda

    art = articles()
    d = expected(art)
    am = _article_panel(art, d)
    lp = _lang_panel(am)
    ip = _item_panel(am, lp)
    config.PANEL_DIR.mkdir(parents=True, exist_ok=True)
    lp.to_parquet(config.PANEL_DIR / "panel_lang_month.parquet", index=False)
    ip.to_parquet(config.PANEL_DIR / "panel_item_lang_month.parquet", index=False)
    for lang, g in am.groupby("lang"):
        out = config.PANEL_DIR / "panel_article_month" / f"lang={lang}"
        out.mkdir(parents=True, exist_ok=True)
        g.to_parquet(out / "part.parquet", index=False)
    qa = config.REPORT_DIR / "qa"
    qa.mkdir(parents=True, exist_ok=True)
    (config.REPORT_DIR / "figures").mkdir(parents=True, exist_ok=True)
    tm, _ = eda.trend_models(eda.load())
    tm.round(4).to_csv(qa / "p14_trend_models.csv", index=False)
    pd.DataFrame([dict(true_effect=TRUE, true_pct=100 * (np.exp(TRUE) - 1), n_articles=N,
                       seed=SEED)]).to_csv(qa / "synthetic_truth.csv", index=False)  # fmt: skip
    print(
        f"synthetic panels: {len(lp)} edition-months, {len(am):,} article-months, "
        f"{am.search_censored.mean():.0%} of article-months censored"
    )


if __name__ == "__main__":
    {"raw": raw, "panels": panels}[sys.argv[1]]()
