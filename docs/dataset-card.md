---
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
  - config_name: edition_month
    data_files: data/edition_month.parquet
  - config_name: articles
    data_files: data/articles.parquet
  - config_name: article_month
    data_files: data/article_month.parquet
  - config_name: exposure
    data_files: data/exposure.parquet
  - config_name: cohorts
    data_files: data/cohorts.parquet
  - config_name: data_breaks
    data_files: data/data_breaks.parquet
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

| File | Rows | Columns | Months |
|---|---|---|---|
| `data/edition_month.parquet` / `.csv` | 4,522 | 42 | 2016-01 to 2026-09 |
| `data/articles.parquet` / `.csv` | 197,453 | 23 | – |
| `data/article_month.parquet` / `data/article_month_csv/article_month_<lang>.csv.gz` | 23,128,204 | 23 | 2016-01 to 2026-09 |
| `data/exposure.parquet` / `.csv` | 4,280 | 7 | 2017-11 to 2026-09 |
| `data/cohorts.parquet` / `.csv` | 40 | 7 | – |
| `data/data_breaks.parquet` / `.csv` | 18 | 7 | – |

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
@misc{pospisil2026wikipedia,
  author = {Pospisil, John},
  title  = {Wikipedia search traffic and Google AI Overviews, 2016--2026},
  year   = {2026},
  note   = {Derived from Wikimedia pageview and clickstream data. CC0},
  url    = {https://github.com/johnpospisil/wikipedia-ai-overviews}
}
```
