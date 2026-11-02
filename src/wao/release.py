# ruff: noqa: E501  (long column descriptions are data)
"""P32: the published dataset (edition and article panels, exposure) for Hugging Face.

Builds <WAO_DATA_DIR>/release/wikipedia-ai-overviews-panels-2026-09/ with Parquet + CSV tables,
a column dictionary (columns.csv), SHA-256 checksums and the data card (README.md, with Hugging
Face YAML front matter). Nothing is uploaded: the user decides. Derived counts and metrics only;
no article text (titles are included, as in Wikimedia's own CC0 pageview dumps).

Tables:
  edition_month   panels/panel_lang_month.parquet (40 editions)
  articles        one row per sample article: title, QID, sampling design, 2023-12-31 features,
                  quick-answer label (static columns of the article panel + sample.parquet)
  article_month   the time-varying columns of panels/panel_article_month (23 M rows; CSV split
                  by edition and gzipped)
  exposure        data/reference/language_exposure.csv
  cohorts         data/reference/language_cohorts.csv
  data_breaks     data/reference/data_breaks.csv

Usage: python -m wao.release
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import duckdb
import pandas as pd

from wao import config

NAME = "wikipedia-ai-overviews-panels-2026-09"
OUT = config.DATA_DIR / "release" / NAME
REF = config.REFERENCE_DIR
ARTICLE_PANEL = f"{config.PANEL_DIR}/panel_article_month/*/*.parquet"

STATIC = ["lang", "page_id", "title", "qid", "stratum", "decile", "coarse_type", "views_2023",
          "weight", "in_lang_sample", "in_concept_panel", "w_concept", "qa_tier", "qa_core",
          "qa_nq_rate", "has_infobox", "prose_chars", "lead_chars", "n_sections", "n_refs",
          "age_years", "topic_group", "topic_confident"]  # fmt: skip
MONTHLY = ["lang", "page_id", "month", "views_desktop", "views_mobile_web", "views_app",
           "views_automated", "cs_available", "cs_usable", "cs_short", "bot_break", "arr_search",
           "search_censored", "search_hidden_est", "search_hidden_upper", "arr_total_pub",
           "arr_link_pub", "out_links_pub", "edits", "edits_user", "edits_anon", "edits_bot",
           "editors"]  # fmt: skip
COUNTS = {"views_desktop", "views_mobile_web", "views_app", "views_automated", "arr_search",
          "arr_total_pub", "arr_link_pub", "out_links_pub"}  # fmt: skip

# column -> (type, meaning). Shared by every table that has the column.
COLUMNS = {
    # keys
    "lang": ("text", "Wikipedia language edition code (en, de, ...)"),
    "month": ("YYYY-MM", "Calendar month, UTC"),
    "page_id": ("id", "MediaWiki page ID in that edition (articles, article_month)"),
    "wiki": ("text", "Edition code (exposure, cohorts; same as lang)"),
    # edition_month
    "core": (
        "flag",
        "One of the 11 core editions (en ja pt es de it pl zh fr ru fa); the other 29 have clickstream only from 2024-08 and are exploratory",
    ),
    "role": (
        "text",
        "treated, late_treated_control (fr), partial_dose (ru), near_untreated_control (fa) or exploratory",
    ),
    "cohort": ("YYYY-MM", "First month with exposure >= 0.5 ('never' if not reached)"),
    "first_exposed": ("YYYY-MM", "First month with exposure > 0"),
    "exposure": (
        "share 0-1",
        "Share of the edition's readers exposed to AI Overviews: sum over countries of (2023-10..2024-04 share of the edition's pageviews) x (pre-period Google search share) x (AI Overviews live in that country and language), averaged over the days of the month",
    ),
    "exposure_all_users": (
        "share 0-1",
        "As exposure, counting only days when AI Overviews was shown to all users (not only signed-in adults)",
    ),
    "exposure_as_listed": (
        "share 0-1",
        "As exposure, counting Iran as live whenever Google's help page listed it (robustness check)",
    ),
    "exposure_listed": ("share 0-1", "As exposure without the Google-share weight (exposure only)"),
    "share_google_fallback": (
        "share 0-1",
        "Share of the edition's readers in countries with no StatCounter Google share, where a default was used (exposure only)",
    ),
    "cs_available": ("flag", "A clickstream file exists for the edition-month"),
    "cs_usable": (
        "flag",
        "Clickstream exists and month >= 2019-04 (an earlier method under-counts; use only usable months)",
    ),
    "cs_short": ("flag", "2025-04: the clickstream file is about 5 days short"),
    "bot_break": (
        "flag",
        "Month >= 2025-04: Wikimedia's new bot detection removes traffic from `user` from here on (not applied to earlier months)",
    ),
    "month_complete": (
        "flag",
        "Every day of the month is present in the pageview data (core editions; empty for the others)",
    ),
    "search_arr": (
        "count",
        "Clickstream arrivals from any search engine (other-search: Google, Bing, Yandex, ...), published pairs only",
    ),
    "total_arr": ("count", "All clickstream arrivals, published pairs only"),
    "link_arr": ("count", "Arrivals by a link from another article"),
    "link_other_arr": (
        "count",
        "Arrivals from another article without a link in its current wikitext (clickstream type 'other')",
    ),
    "internal_other_arr": (
        "count",
        "Arrivals from non-article Wikipedia pages (internal search, special pages; other-internal)",
    ),
    "external_arr": (
        "count",
        "Arrivals from other websites (other-external; includes chatbots, can't be split)",
    ),
    "empty_arr": ("count", "Arrivals with no referrer: typed, bookmarks, some apps (other-empty)"),
    "other_arr": ("count", "Arrivals from other-other"),
    "cs_articles": ("count", "Articles with at least one published clickstream pair that month"),
    "search_share": ("share 0-1", "search_arr / total_arr"),
    "link_share": ("share 0-1", "link_arr / total_arr"),
    "search_arr_na": ("count", "search_arr with 2025-04 set to missing (the analysis outcome)"),
    "search_arr_rs": (
        "count",
        "search_arr with 2025-04 divided by the edition's shortfall factor (0.81-0.86 for core editions)",
    ),
    "total_arr_na": ("count", "total_arr with 2025-04 set to missing"),
    "total_arr_rs": ("count", "total_arr with 2025-04 rescaled like search_arr_rs"),
    "search_arr_corr": (
        "count",
        "search_arr scaled up by the estimated share hidden by clickstream's <10 threshold (core editions)",
    ),
    "search_arr_corr_upper": (
        "count",
        "As search_arr_corr, using the upper bound of the hidden share",
    ),
    "views_desktop": ("count", "`user` pageviews, desktop"),
    "views_mobile_web": ("count", "`user` pageviews, mobile web"),
    "views_app": ("count", "`user` pageviews, mobile apps (not in clickstream)"),
    "views_automated": ("count", "`automated` pageviews (agent class from 2020-05; empty before)"),
    "active_user": (
        "count",
        "Active registered editors (5+ content edits that month, bots excluded; AQS)",
    ),
    "very_active_user": ("count", "Registered editors with 100+ content edits that month"),
    "active_anonymous": (
        "count",
        "Active anonymous editors (5+ edits); redefined by temporary accounts from 2025-06..2026-03 depending on edition",
    ),
    "edits_user": (
        "count",
        "Content edits by registered non-bot users (edition_month); by registered users (article_month)",
    ),
    "edits_anonymous": ("count", "Content edits by anonymous editors (edition_month)"),
    "google_share": (
        "share 0-1",
        "Google's StatCounter search share, weighted by where the edition's readers are (time-varying; context only)",
    ),
    "core_days": ("count", "Days of the month inside a Google core ranking update"),
    # articles
    "title": ("text", "Article title (canonical, as of the 2026-10 page table)"),
    "qid": ("text", "Wikidata item ID; empty if none"),
    "stratum": (
        "text",
        "Sampling stratum: edition x 2023 popularity decile x coarse Wikidata type",
    ),
    "decile": (
        "1-10",
        "2023 popularity decile within the edition (10 = most read); fixed before treatment",
    ),
    "coarse_type": (
        "text",
        "Coarse Wikidata type (about 20 classes rolled up from instance of / subclass of). Broad by design: written_work is any Wikidata 'work' subclass (books, but also software, laws, court cases, standards, journals); other is the long tail",
    ),
    "views_2023": ("count", "`user` pageviews in 2023 (sampling frame popularity)"),
    "weight": ("weight", "Horvitz-Thompson weight for the edition sample (sums to the frame size)"),
    "in_lang_sample": ("flag", "Drawn in the stratified edition sample (12,000 per edition)"),
    "in_concept_panel": (
        "flag",
        "Part of the 6,000 concepts that have an article in all 11 core editions",
    ),
    "w_concept": ("weight", "Weight for the concept panel (1 / its selection probability)"),
    "qa_tier": (
        "text",
        "Quick-answer tier from Natural Questions short-answer rates by Wikidata type (v4)",
    ),
    "qa_core": ("0/1", "1 = core quick-answer type, 0 = long read, empty = ambiguous"),
    "qa_nq_rate": (
        "share 0-1",
        "Natural Questions short-answer rate of the article's Wikidata type",
    ),
    "has_infobox": ("flag", "Infobox in the 2023-12-31 revision"),
    "prose_chars": ("count", "Prose characters in the 2023-12-31 revision"),
    "lead_chars": ("count", "Characters in the lead section, 2023-12-31 revision"),
    "n_sections": ("count", "Sections in the 2023-12-31 revision"),
    "n_refs": ("count", "References in the 2023-12-31 revision"),
    "age_years": ("years", "Article age at 2023-12-31"),
    "topic_group": (
        "text",
        "Top-level Lift Wing article topic (Culture, Geography, History_and_Society, STEM); from current outlinks",
    ),
    "topic_confident": ("flag", "Top topic score >= 0.5"),
    # article_month
    "arr_search": (
        "count",
        "Search arrivals; EMPTY when censored (fewer than 10 that month, not zero)",
    ),
    "search_censored": (
        "flag",
        "Search arrivals below clickstream's threshold of 10 (arr_search empty)",
    ),
    "search_hidden_est": ("count", "Estimated search arrivals when censored (P11 model)"),
    "search_hidden_upper": ("count", "Upper bound for censored search arrivals (9)"),
    "arr_total_pub": (
        "count",
        "Arrivals summed over published pairs only (each pair >= 10, so small articles are understated)",
    ),
    "arr_link_pub": ("count", "Arrivals from article links, published pairs only"),
    "out_links_pub": ("count", "Clicks from this article to other articles, published pairs only"),
    "edits": ("count", "Edits that month (all editors, from the revision history)"),
    "edits_anon": ("count", "Edits by IP or temporary accounts"),
    "edits_bot": ("count", "Edits by bots"),
    "editors": ("count", "Distinct non-bot editors that month"),
    # cohorts
    "exposure_2025_06": ("share 0-1", "Exposure in 2025-06 (cohorts)"),
    "exposure_latest": ("share 0-1", "Exposure in the latest month (cohorts)"),
    "max_exposure": ("share 0-1", "Highest monthly exposure (cohorts)"),
    # data_breaks
    "source": ("text", "Affected data source (data_breaks)"),
    "start": ("YYYY-MM", "First affected month (data_breaks)"),
    "end": ("YYYY-MM", "Last affected month; empty = ongoing (data_breaks)"),
    "issue": ("text", "What changed (data_breaks)"),
    "evidence": ("text", "How it was found (data_breaks)"),
    "handling": ("text", "How the panels treat it (data_breaks)"),
}


STATCOUNTER_COLUMNS = ("exposure", "exposure_all_users", "exposure_as_listed", "exposure_listed",
                       "share_google_fallback", "cohort", "first_exposed", "google_share")  # fmt: skip
LICENCE = """# Licence

This dataset combines two sources under different licences.

1. Columns derived from Wikimedia Foundation data (pageviews, clickstream, editor statistics,
   page tables): **CC0 1.0 Universal** (https://creativecommons.org/publicdomain/zero/1.0/).
2. Columns derived from StatCounter Global Stats search-engine shares (exposure*,
   share_google_fallback, cohort, first_exposed, google_share; the whole exposure and cohorts
   tables): **CC BY-SA 3.0** (https://creativecommons.org/licenses/by-sa/3.0/). Attribute
   "StatCounter Global Stats" and share adaptations of these columns under the same licence.

No Wikipedia article text is included.
"""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _cast(c: str) -> str:
    return f"cast(round({c}) as bigint) as {c}" if c in COUNTS else c


def build() -> dict:
    if OUT.exists():
        shutil.rmtree(OUT)
    data = OUT / "data"
    (data / "article_month_csv").mkdir(parents=True)
    con = duckdb.connect()
    con.execute("set preserve_insertion_order = false")
    stats = {}

    def save(name: str, sql: str, csv: bool = True) -> None:
        con.execute(f"create or replace table t as {sql}")
        con.execute(f"copy t to '{data}/{name}.parquet' (format parquet, compression zstd)")
        if csv:
            con.execute(f"copy t to '{data}/{name}.csv' (header)")
        cols = [r[0] for r in con.execute("describe t").fetchall()]
        n, lo, hi = con.execute(
            "select count(*), min(month), max(month) from t" if "month" in cols
            else "select count(*), null, null from t"
        ).fetchone()  # fmt: skip
        stats[name] = {"rows": n, "columns": len(cols), "months": [lo, hi] if lo else None}

    save(
        "edition_month",
        f"select * from '{config.PANEL_DIR}/panel_lang_month.parquet' order by lang, month",
    )
    static = ", ".join(f"p.{c}" for c in STATIC if c not in {"title", "stratum", "views_2023"})
    save(
        "articles",
        f"""
        select {static.replace("p.lang", "s.lang").replace("p.page_id", "s.page_id")},
               s.title, s.stratum, s.views_2023
        from (select distinct on (lang, page_id) * from read_parquet('{ARTICLE_PANEL}',
              hive_partitioning = true)) p
        join '{config.PANEL_DIR}/sample.parquet' s using (lang, page_id)
        order by s.lang, s.page_id""",
    )
    con.execute(f"create or replace table t as select {', '.join(STATIC)} from t")  # column order
    con.execute(f"copy t to '{data}/articles.parquet' (format parquet, compression zstd)")
    con.execute(f"copy t to '{data}/articles.csv' (header)")
    sel = ", ".join(_cast(c) for c in MONTHLY)
    save("article_month", f"""select {sel} from read_parquet('{ARTICLE_PANEL}', hive_partitioning = true)
                              order by lang, page_id, month""", csv=False)  # fmt: skip
    for (lang,) in con.execute("select distinct lang from t order by 1").fetchall():
        con.execute(f"""copy (select * from t where lang = '{lang}')
                        to '{data}/article_month_csv/article_month_{lang}.csv.gz' (header)""")
    save("exposure", f"select * from read_csv('{REF}/language_exposure.csv') order by wiki, month")
    save("cohorts", f"select * from read_csv('{REF}/language_cohorts.csv', all_varchar = false)")
    save("data_breaks", f"select * from read_csv('{REF}/data_breaks.csv', all_varchar = true)")

    pd.DataFrame(
        [{"column": c, "type": t, "description": d} for c, (t, d) in COLUMNS.items()]
    ).to_csv(OUT / "columns.csv", index=False)
    (OUT / "README.md").write_text(card(stats))
    (OUT / "LICENSE.md").write_text(LICENCE)
    sums = {
        str(p.relative_to(OUT)): sha256(p)
        for p in sorted(OUT.rglob("*"))
        if p.is_file() and p.name != "SHA256SUMS"
    }
    (OUT / "SHA256SUMS").write_text("".join(f"{h}  {p}\n" for p, h in sums.items()))
    size = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())
    sizes = {str(p.relative_to(OUT)): round(p.stat().st_size / 1e6, 1) for p in sorted(OUT.rglob("*")) if p.is_file()}  # fmt: skip
    out = {"dir": str(OUT), "files": stats, "sizes_mb": sizes, "total_mb": round(size / 1e6, 1)}
    (config.REPORT_DIR / "qa" / "release_summary.json").write_text(json.dumps(out, indent=2))
    return out


def _table(stats: dict) -> str:
    rows = []
    for n, s in stats.items():
        csv = (
            "`data/article_month_csv/article_month_<lang>.csv.gz`"
            if n == "article_month"
            else "`.csv`"
        )
        months = f"{s['months'][0]} to {s['months'][1]}" if s["months"] else "–"
        rows.append(f"| `data/{n}.parquet` / {csv} | {s['rows']:,} | {s['columns']} | {months} |")
    return "| File | Rows | Columns | Months |\n|---|---|---|---|\n" + "\n".join(rows)


def _dictionary() -> str:
    rows = [f"| `{c}` | {t} | {d} |" for c, (t, d) in COLUMNS.items()]
    return "| Column | Type | Meaning |\n|---|---|---|\n" + "\n".join(rows)


def card(stats: dict) -> str:
    configs = "\n".join(f"  - config_name: {n}\n    data_files: data/{n}.parquet" for n in stats)
    return f"""---
license: other
license_name: cc0-1.0-and-cc-by-sa-3.0
license_link: LICENSE.md
pretty_name: Wikipedia search traffic and Google AI Overviews, 11 language editions, 2016-2026
language:
  - en
  - de
  - es
  - fr
  - it
  - ja
  - pl
  - pt
  - ru
  - zh
  - fa
tags:
  - wikipedia
  - wikimedia
  - clickstream
  - pageviews
  - web-traffic
  - search
  - generative-ai
  - ai-overviews
  - difference-in-differences
size_categories:
  - 10M<n<100M
configs:
{configs}
---

# Wikipedia search traffic and Google AI Overviews, 2016–2026

Monthly panels of how readers reach Wikipedia (search, links, other websites, no referrer),
pageviews by access type, editors, and a measure of each language edition's exposure to
Google's AI Overviews. Covers **11 core language editions** (English, Japanese, Portuguese,
Spanish, German, Italian, Polish, Chinese, French, Russian, Persian; 29 more at edition level
from 2024-08) and a stratified sample of **197,453 articles**. These are the data behind *Did
Google's AI Overviews take Wikipedia's search traffic?* (John Pospisil, 2026).

**Derived counts and metrics only.** No article text. Article titles are included, as in
Wikimedia's own pageview dumps.

- Code, method, pre-registration and article: https://github.com/johnpospisil/wikipedia-ai-overviews
- Independent; not affiliated with or endorsed by the Wikimedia Foundation or Google.

## Files

{_table(stats)}

`columns.csv` has the column dictionary below; `SHA256SUMS` has a checksum for every file.

- **edition_month:** one row per edition and month. Clickstream arrivals by referrer, `user`
  pageviews by access, automated views, active editors and edits, exposure, cohort, Google
  search share, and flags for the known data breaks.
- **articles:** one row per sample article. Sampling design (stratum, decile, weights), Wikidata
  item and type, features of the 2023-12-31 revision, the quick-answer label, and topic.
- **article_month:** one row per sample article and month from 2016-01 (or the article's start):
  views by access, clickstream arrivals, and edits. Join to `articles` on (`lang`, `page_id`).
  The CSV is split by edition and gzipped.
- **exposure / cohorts:** the AI Overviews exposure measure for all 40 editions, and each
  edition's cohort month (first month with exposure ≥ 0.5).
- **data_breaks:** every known methodology change and data defect, with how the panels treat it.

## How it was made

- **Clickstream:** Wikimedia's monthly clickstream dumps, 2017-11 to 2026-09.
- **Pageviews:** daily `pageview_complete` dumps, 2016-01 to 2026-09. Views of redirects and
  moved pages count toward the canonical article.
- **Editors:** Wikimedia's analytics API (AQS) and the stub revision histories.
- **Exposure:** Wikimedia pageviews by country (2023-10..2024-04 shares, fixed), StatCounter
  search-engine shares (pre-period, fixed), and Google's AI Overviews rollout by country and
  language, dated from archived copies of Google's help page and official announcements. A
  sourced rollout table is in the repository (`data/reference/aio_rollout.csv`).
- **Sample:** stratified by edition × 2023 popularity decile × coarse Wikidata type,
  Horvitz–Thompson weights. It also includes 6,000 concepts present in all 11 editions.

The pipeline (`make all`) rebuilds every file from the raw dumps.

## Known limitations

- **Clickstream truncation.** Clickstream drops (referrer, article) pairs with fewer than 10
  views a month. At edition level this hides 0.5–3% of search arrivals. At article level, small
  articles' search arrivals are mostly **censored**: `arr_search` is empty, never zero, with an
  estimate in `search_hidden_est`. As traffic falls, more pairs drop below the threshold, so
  raw long-tail declines are mechanically exaggerated. Use pageviews for the long tail.
- **"Search" is every search engine.** Clickstream's `other-search` can't separate Google from
  Bing, Yandex or others. Russian (Yandex), Japanese (Yahoo! JAPAN) and Chinese have large
  non-Google shares.
- **Web only.** Clickstream covers desktop and mobile web, not the apps. Chatbot referrals land
  in `external_arr` and can't be split out.
- **Bot reclassification, 2025-04.** Wikimedia's new bot detection removes traffic from `user`
  from 2025-04 on, by different amounts per edition, and was not applied to earlier months.
  Clickstream shows the same break. See `bot_break`.
- **Clickstream method change, 2019-04.** Earlier months under-count, most for non-Latin
  scripts. Use `cs_usable`.
- **2025-04 clickstream is about 5 days short.** Use the `_na` (missing) or `_rs` (rescaled)
  columns.
- **Other breaks:** zh pageview dumps for 2022-10 and 2022-12 were defective and rebuilt from
  daily files. Persian traffic falls sharply from 2025-05 (likely Iranian connectivity
  restrictions). Temporary accounts redefine anonymous editors from 2025-06. A French
  no-referrer surge ran from 2022-07 to 2023-08. All of these are listed in `data_breaks`.
- **Sample design.** Article tables are a weighted sample, not every article. Use `weight` for
  edition totals and `w_concept` for the concept panel. Articles deleted between 2023 and the
  2026-10 page table are not in the frame (0.8–1.9% of 2023 views).
- **Topics** come from Lift Wing's model on current (2026) links, not the 2023 revision.
- **Exposure is a model**, not an observation: it assumes readers in a country search with
  Google at the country's pre-period rate and that AI Overviews appeared once it was live there.

## Licence and attribution

Two licences apply, column by column:

- **CC0 1.0:** everything derived from Wikimedia data, which Wikimedia releases under CC0. That
  covers pageviews, clickstream arrivals, editors and edits, titles, sampling design, article
  features, the quick-answer label and the flags.
- **CC BY-SA 3.0, attributing StatCounter:** the columns built from StatCounter search-engine
  shares (StatCounter Global Stats, CC BY-SA 3.0). These are `exposure`, `exposure_all_users`,
  `exposure_as_listed`, `exposure_listed`, `share_google_fallback`, `cohort`, `first_exposed`
  and `google_share`, in every table that has them, and all of the `exposure` and `cohorts`
  tables. Adaptations of these columns must keep the same licence.

Suggested attribution:

> Derived from Wikimedia Foundation pageview, clickstream and editor data (CC0) and StatCounter
> Global Stats search-engine shares (CC BY-SA 3.0). Panels by John Pospisil,
> https://github.com/johnpospisil/wikipedia-ai-overviews

Article text is CC BY-SA and is not included. The raw StatCounter series are not redistributed.
The full licence note is in `LICENSE.md`.

## Citation

```bibtex
@misc{{pospisil2026wikipedia,
  author = {{Pospisil, John}},
  title  = {{Wikipedia search traffic and Google AI Overviews, 2016--2026}},
  year   = {{2026}},
  note   = {{Derived from Wikimedia pageview and clickstream data. CC0}},
  url    = {{https://github.com/johnpospisil/wikipedia-ai-overviews}}
}}
```
"""


def main() -> None:
    print(json.dumps(build(), indent=2))


if __name__ == "__main__":
    main()
