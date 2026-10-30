"""P06: sampling frame and stratified article sample, using pre-period (2023) popularity only.

Frame (per core edition): main-namespace, non-redirect, non-disambiguation articles with any 2023
`user` view, excluding the main page. 2023 views (pageview_month, all access types) are assigned
to pages by page_id; rows without one are matched by title, and views of redirects are moved to
the redirect's target. Pages are those in the 2026-10 SQL dump (wao.ingest.sql_dumps), so pages
deleted since 2023 drop out; the views lost that way are reported. Popularity decile = decile of
2023 views within the edition (ties broken at random), fixed before any post-period data is used.

Two independent probability samples, combined:
  A. language sample (two-phase): phase 1 draws PHASE1 articles per edition × decile at random;
     their Wikidata coarse types (wao.ingest.wikidata_types) define phase-2 strata
     edition × decile × type, allocated proportionally to LANG_TARGET per edition with a floor of
     FLOOR per stratum (all if fewer), which oversamples small strata.
  B. concept panel: Wikidata items with a frame article in all 11 editions, stratified by
     type × item decile (2023 views summed over the editions); CONCEPT_ITEMS items with a floor of
     CONCEPT_FLOOR per stratum. A selected item brings its article in every edition.
Inclusion probabilities: pi_A = (n1/N for edition × decile) × (n2/n1 for edition × decile × type);
pi_B = m/M for the item's stratum. The draws are independent, so an article's overall
pi = pi_A + pi_B − pi_A·pi_B and weight = 1/pi (Horvitz–Thompson for edition-level totals).
P19 uses w_concept = 1/pi_B for the item panel instead.

Outputs: PANEL_DIR/sample.parquet (lang, page_id, title, qid, stratum, weight + design columns),
PARQUET_DIR/frame.parquet, report/qa/p06_*.csv.
Run: python -m wao.build.sample
"""

from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

from wao import config, http
from wao.ingest import wikidata_types

SEED = 20261029
PHASE1 = 2_500
LANG_TARGET = 12_000
FLOOR = 30
CONCEPT_ITEMS = 6_000
CONCEPT_FLOOR = 15


def main_pages() -> dict[str, str]:
    s = http.session("siteinfo", min_interval=0.5)
    out = {}
    for lang in config.LANGS:
        r = s.get(
            f"https://{lang}.wikipedia.org/w/api.php",
            params={"action": "query", "meta": "siteinfo", "format": "json"},
            timeout=60,
        )
        out[lang] = r.json()["query"]["general"]["mainpage"].replace(" ", "_")
    return out


def build_frame(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Creates table `frame` in con; returns the view-resolution accounting."""
    pq = config.PARQUET_DIR
    sql = pq / "wiki_sql"
    mp = pd.DataFrame(list(main_pages().items()), columns=["lang", "title"])
    con.register("main_pages", mp)
    con.execute(f"""
        CREATE OR REPLACE TABLE page AS SELECT * FROM read_parquet('{sql}/page/*/*.parquet',
            hive_partitioning=true);
        CREATE OR REPLACE TABLE props AS SELECT * FROM read_parquet(
            '{sql}/page_props/*/*.parquet', hive_partitioning=true);
        CREATE OR REPLACE TABLE redir AS SELECT * FROM read_parquet(
            '{sql}/redirect/*/*.parquet', hive_partitioning=true);
        CREATE OR REPLACE TABLE pv AS
          SELECT lang, title, page_id, sum(views) AS views, count(DISTINCT month) AS months
          FROM read_parquet('{pq}/pageview_month/*/*.parquet', hive_partitioning=true)
          WHERE month BETWEEN '2023-01' AND '2023-12'
          GROUP BY ALL;
        CREATE OR REPLACE TABLE pv_resolved AS
        WITH r1 AS (
          SELECT pv.*, coalesce(pv.page_id, t.page_id) AS pid
          FROM pv LEFT JOIN page t
            ON pv.page_id IS NULL AND t.lang = pv.lang AND t.namespace = 0 AND t.title = pv.title
        ), r2 AS (
          SELECT r1.*, p.namespace, p.is_redirect, t2.page_id AS target_id,
                 t2.is_redirect AS target_is_redirect
          FROM r1
          LEFT JOIN page p ON p.lang = r1.lang AND p.page_id = r1.pid
          LEFT JOIN redir rd ON p.is_redirect AND rd.lang = r1.lang AND rd.page_id = r1.pid
          LEFT JOIN page t2 ON t2.lang = r1.lang AND t2.namespace = 0 AND t2.title = rd.target
        )
        SELECT lang, views, months, page_id IS NULL AS no_page_id,
          CASE WHEN pid IS NULL OR namespace IS NULL THEN 'not_in_dump'
               WHEN namespace <> 0 THEN 'other_namespace'
               WHEN NOT is_redirect THEN 'article'
               WHEN target_id IS NOT NULL AND NOT target_is_redirect THEN 'redirect_resolved'
               ELSE 'redirect_unresolved' END AS status,
          CASE WHEN namespace = 0 AND NOT is_redirect THEN pid
               WHEN namespace = 0 AND NOT target_is_redirect THEN target_id END AS article_id
        FROM r2;
        CREATE OR REPLACE TABLE frame AS
        WITH v AS (
          SELECT lang, article_id AS page_id, sum(views) AS views_2023, max(months) AS months_2023
          FROM pv_resolved WHERE article_id IS NOT NULL GROUP BY ALL
        )
        SELECT v.lang, v.page_id, p.title, pp.qid, v.views_2023, v.months_2023,
               ntile(10) OVER (PARTITION BY v.lang
                               ORDER BY v.views_2023, hash(v.page_id, {SEED})) AS decile
        FROM v JOIN page p ON p.lang = v.lang AND p.page_id = v.page_id
        LEFT JOIN props pp ON pp.lang = v.lang AND pp.page_id = v.page_id
        WHERE NOT coalesce(pp.is_disambiguation, false)
          AND NOT EXISTS (SELECT 1 FROM main_pages m WHERE m.lang = v.lang AND m.title = p.title);
    """)
    acct = con.execute("""
        WITH s AS (
          SELECT lang, status, no_page_id, sum(views) AS views FROM pv_resolved GROUP BY ALL
        )
        SELECT lang, status, no_page_id, views,
               views / sum(views) OVER (PARTITION BY lang) AS share
        FROM s ORDER BY lang, views DESC
    """).df()
    excluded = con.execute("""
        SELECT r.lang, sum(r.views) AS views,
          sum(r.views) FILTER (WHERE pp.is_disambiguation) AS disambiguation_views
        FROM pv_resolved r LEFT JOIN props pp ON pp.lang = r.lang AND pp.page_id = r.article_id
        GROUP BY ALL
    """).df()
    return acct.merge(excluded[["lang", "disambiguation_views"]], on="lang", how="left")


def _key(df: pd.DataFrame, salt: str) -> np.ndarray:
    """Deterministic uniform random key per article (reproducible draws)."""
    keys = df["lang"].astype(str) + ":" + df["page_id"].astype(str) + salt
    h = pd.util.hash_pandas_object(keys, index=False)
    return (h.to_numpy() >> np.uint64(11)) / float(1 << 53)


def allocate(n1: pd.Series, target: int, floor: int) -> pd.Series:
    """n2_h = min(n1_h, max(floor, r·n1_h)), with r found so the total is about `target`."""
    if n1.sum() <= target:
        return n1.copy()
    lo, hi = 0.0, 1.0
    for _ in range(60):
        r = (lo + hi) / 2
        tot = np.minimum(n1, np.maximum(floor, np.round(r * n1))).sum()
        lo, hi = (r, hi) if tot < target else (lo, r)
    return np.minimum(n1, np.maximum(floor, np.round(hi * n1))).astype(int)


def take(df: pd.DataFrame, by: list[str], n: pd.Series, salt: str) -> pd.DataFrame:
    """Simple random sample of n[h] rows from each group h of `by`."""
    d = df.assign(_k=_key(df, salt)).sort_values("_k")
    d["_r"] = d.groupby(by).cumcount()
    d = d.join(n.rename("_n"), on=by)
    return d[d._r < d._n].drop(columns=["_k", "_r", "_n"])


def draw(frame: pd.DataFrame, types: pd.Series) -> pd.DataFrame:
    langs = list(config.LANGS)
    # --- A, phase 1: per edition × decile
    N_ld = frame.groupby(["lang", "decile"]).size().rename("N_ld")
    n1_ld = N_ld.clip(upper=PHASE1).rename("n1_ld")
    p1 = take(frame, ["lang", "decile"], n1_ld, "p1")
    p1["coarse_type"] = p1.qid.map(types).fillna("no_qid")
    # --- A, phase 2: per edition × decile × type
    n1_ldt = p1.groupby(["lang", "decile", "coarse_type"]).size().rename("n1_ldt")
    n2_ldt = pd.concat(
        [allocate(n1_ldt.loc[lang], LANG_TARGET, FLOOR) for lang in langs], keys=langs
    ).rename("n2_ldt")
    n2_ldt.index.names = n1_ldt.index.names
    a = take(p1, ["lang", "decile", "coarse_type"], n2_ldt, "p2")
    # --- B: items with a frame article in every edition
    f = frame[frame.qid.notna()]
    per_item = f.groupby("qid").agg(n_lang=("lang", "nunique"), views=("views_2023", "sum"))
    items = per_item[per_item.n_lang == len(langs)].reset_index()
    items["coarse_type"] = items.qid.map(types).fillna("no_p31")
    items["item_decile"] = (
        pd.qcut(items.views.rank(method="first"), 10, labels=False).astype(int) + 1
    )
    items["lang"], items["page_id"] = "item", items.qid  # for the random key
    M = items.groupby(["coarse_type", "item_decile"]).size().rename("M")
    m = allocate(M, CONCEPT_ITEMS, CONCEPT_FLOOR).rename("m")
    chosen = take(items, ["coarse_type", "item_decile"], m, "concept")
    pi_b = (m / M).rename("pi_b")
    b_items = chosen[["qid", "coarse_type", "item_decile"]].join(
        pi_b, on=["coarse_type", "item_decile"]
    )
    b = f.merge(b_items, on="qid")
    # --- union and inclusion probabilities
    s = pd.concat([a.assign(in_lang_sample=True), b.assign(in_concept_panel=True)])
    s = s.groupby(["lang", "page_id"], as_index=False).first()
    s[["in_lang_sample", "in_concept_panel"]] = (
        s[["in_lang_sample", "in_concept_panel"]].astype("boolean").fillna(False).astype(bool)
    )
    s["coarse_type"] = s.qid.map(types).fillna(s.qid.isna().map({True: "no_qid", False: "no_p31"}))
    s = s.join(N_ld, on=["lang", "decile"]).join(n1_ld, on=["lang", "decile"])
    s = s.join(n1_ldt, on=["lang", "decile", "coarse_type"]).join(
        n2_ldt, on=["lang", "decile", "coarse_type"]
    )
    # a stratum absent from phase 1 has no phase-2 draw; pi_2 = 1 is the floor rule's limit
    pi2 = (s.n2_ldt / s.n1_ldt).fillna(1.0)
    s["pi_a"] = s.n1_ld / s.N_ld * pi2
    # pi_B applies to every article of an all-edition item, however it was drawn
    item_pi = items[["qid", "coarse_type", "item_decile"]].join(
        pi_b, on=["coarse_type", "item_decile"]
    )
    s = s.drop(columns=["pi_b", "item_decile"]).merge(
        item_pi.drop(columns="coarse_type"), on="qid", how="left"
    )
    s["pi_b"] = s.pi_b.fillna(0.0)
    s["pi"] = s.pi_a + s.pi_b - s.pi_a * s.pi_b
    s["weight"] = 1 / s.pi
    s["w_concept"] = np.where(s.in_concept_panel, 1 / s.pi_b.where(s.pi_b > 0), np.nan)
    s["stratum"] = s.lang + "|d" + s.decile.astype(str) + "|" + s.coarse_type
    cols = [
        "lang", "page_id", "title", "qid", "stratum", "weight", "decile", "coarse_type",
        "views_2023", "months_2023", "in_lang_sample", "in_concept_panel", "item_decile",
        "pi_a", "pi_b", "pi", "w_concept",
    ]  # fmt: skip
    return s[cols].sort_values(["lang", "page_id"], ignore_index=True), p1, items


def main() -> None:
    config.PANEL_DIR.mkdir(parents=True, exist_ok=True)
    qa = config.REPORT_DIR / "qa"
    qa.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(config.DATA_DIR / "p06.duckdb"))
    con.execute("SET memory_limit = '10GB'; SET preserve_insertion_order = false")
    con.execute(f"SET temp_directory = '{config.DATA_DIR / 'tmp'}'")
    build_frame(con).to_csv(qa / "p06_view_resolution.csv", index=False)
    con.execute(f"COPY frame TO '{config.PARQUET_DIR / 'frame.parquet'}' (FORMAT parquet)")
    frame = con.execute("SELECT * FROM frame").df()
    print(f"frame: {len(frame):,} articles", flush=True)

    # QIDs needing a type: phase-1 candidates and the all-edition items (cheap superset: draw
    # phase 1 first, exactly as draw() will, so only those QIDs are looked up)
    N_ld = frame.groupby(["lang", "decile"]).size()
    p1 = take(frame, ["lang", "decile"], N_ld.clip(upper=PHASE1), "p1")
    f = frame[frame.qid.notna()]
    n_lang = f.groupby("qid").lang.nunique()
    allcore = n_lang[n_lang == len(config.LANGS)].index
    need = sorted(set(p1.qid.dropna()) | set(allcore))
    print(f"types: {len(need):,} QIDs ({len(allcore):,} in all editions)", flush=True)
    types = wikidata_types.lookup(need).set_index("qid").coarse_type

    sample, p1, items = draw(frame, types)
    sample.to_parquet(config.PANEL_DIR / "sample.parquet", index=False)
    summarise(frame, sample, items, qa)


def summarise(frame, sample, items, qa) -> None:
    by_stratum = (
        sample.groupby(["lang", "decile", "coarse_type"])
        .agg(n=("page_id", "size"), weight_sum=("weight", "sum"))
        .reset_index()
    )
    by_stratum.to_csv(qa / "p06_sample_by_stratum.csv", index=False)
    by_lang = pd.DataFrame(
        {
            "frame_articles": frame.groupby("lang").size(),
            "frame_no_qid": frame[frame.qid.isna()].groupby("lang").size(),
            "sample": sample.groupby("lang").size(),
            "lang_sample": sample[sample.in_lang_sample].groupby("lang").size(),
            "concept_panel": sample[sample.in_concept_panel].groupby("lang").size(),
            "sample_no_qid": sample[sample.qid.isna()].groupby("lang").size(),
            "weight_sum": sample.groupby("lang").weight.sum(),
        }
    ).fillna(0)
    by_lang.to_csv(qa / "p06_sample_by_lang.csv")
    by_type = pd.crosstab(sample.coarse_type, sample.lang, margins=True)
    by_type.to_csv(qa / "p06_sample_by_type.csv")
    print(by_lang.to_string())
    print(
        f"all-edition items: {len(items):,}; concept panel items: "
        f"{sample[sample.in_concept_panel].qid.nunique():,}"
    )


if __name__ == "__main__":
    main()
