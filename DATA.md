# DATA.md: sources and provenance

Every dataset the pipeline uses, with where it comes from, its licence, coverage, grain and known problems. Started in P01 (2026-10-29); later prompts add to it. Inventories of every file are in `data/reference/clickstream_files.csv` and `data/reference/pageview_monthly_files.csv` (built by `python -m wao.ingest.inventory`).

All Wikimedia requests send `User-Agent: wao/<version> (<WAO_CONTACT>) python-requests/<version>`, as Wikimedia's User-Agent policy requires.

## 1. Clickstream (main outcome)

- **Where:** `https://dumps.wikimedia.org/other/clickstream/<YYYY-MM>/clickstream-<lang>wiki-<YYYY-MM>.tsv.gz`
- **Licence:** CC0.
- **Format:** gzip TSV, no header: `prev  curr  type  n`. `prev` is an article title or one of `other-search`, `other-empty`, `other-internal`, `other-external`, `other-other`; `type` is `link`, `external` or `other`.
- **Coverage (checked 2026-10-29):** 107 months, 2017-11 to 2026-09, released early in the following month.
  - en, de, es, ja, ru from 2017-11; fr, it, zh, pl, pt from 2018-01; fa from 2018-03. **No gaps** in any of the 11 core languages.
  - 29 more languages (ar, nl, tr, uk, id, cs, sv, he, fi, ko, hu, vi, th, el, sr, ro, no, bg, ca, …) only from **2024-08**, after the US launch of AI Overviews, so they can't provide long pre-trends.
- **Size:** 98 GB for all 40 languages, 94 GB for the 11 core languages. English is 0.48 GB/month (2026-09).
- **Integrity:** no checksum files are published. Downloads are checked against the listed byte size plus `gzip -t`.
- **Known problems:**
  - **Pairs with fewer than 10 views a month are dropped** (minimum `n` = 10, confirmed). In en 2026-09, clickstream totals 5.70 B views = 93.3% of AQS `user` desktop + mobile-web views (6.11 B). The missing 6.7% is mostly that threshold. As traffic falls, the hidden share grows, which mechanically exaggerates long-tail declines (quantified in P11).
  - `other-search` = all search engines, not only Google.
  - Desktop and mobile web only; the apps are excluded and there's no access split.
  - Chatbot referrals (ChatGPT, Perplexity) land in `other-external` and can't be separated out.
  - Bot filtering: the README doesn't say whether clickstream uses the same `user` agent filter as pageviews, or whether the 2025 bot-detection change applies to it. **Open; checked in P11.**
- **en 2026-09 sanity check:** 33.6 M rows, 5.83 M distinct articles. Referral mix: other-search 44.6%, internal link 35.1%, other-empty 16.7%, other-internal 1.9%, other 0.8%, other-external 0.6%, other-other 0.3%.

## 2. Pageview complete (per-article daily views)

- **Where:** `https://dumps.wikimedia.org/other/pageview_complete/monthly/<YYYY>/<YYYY-MM>/pageviews-<YYYYMM>-<agent>.bz2` (also daily files under `/<YYYY>/<YYYY-MM>/`).
- **Licence:** CC0.
- **Format:** space-separated `wiki_code title page_id access monthly_total daily_counts`. `access` is `desktop`, `mobile-web` or `mobile-app`; `page_id` can be `null`. `daily_counts` encodes the day as a character (`A` = day 1 … `Z` = 26, then `[ \ ] ^ _` = 27–31), each followed by that day's count. In a 28,843-row check the daily counts summed exactly to `monthly_total` every time. The README warns that rows without page IDs may have 5 columns, so the parser must handle that.
- **Sorting:** rows are sorted by wiki code across all projects, so every file has to be decompressed in full to pull out the languages we need.
- **Coverage:** monthly `user` files for 129 months from 2016-01 (and earlier); `automated` from 2020 (77 months); `spider` 86 months (not needed).
- **Size from 2016-01:** user 411 GB, automated 223 GB (spider 482 GB, not downloaded). One month of `user` is about 3.3 GB of bz2.
- **Integrity:** no checksum files. Checked by listed byte size plus a full `bzip2 -t`.
- **Known problems:**
  - `automated` was introduced in 2020 and its detection rules changed in 2025.
  - Daily `automated` files are now larger than `user` files (2026-09-29: 1.04 GB vs 0.73 GB).
  - Agent classification is applied when the data is processed, so series aren't consistent across classifier changes.

## 3. Pageviews REST API (AQS)

- **Where:** `https://wikimedia.org/api/rest_v1/metrics/…`
- **Licence:** CC0.
- **Endpoints confirmed 2026-10-29:**
  - `pageviews/per-article/<project>/<access>/<agent>/<article>/daily/<start>/<end>` (200).
  - `pageviews/aggregate/<project>/<access>/<agent>/monthly/…` (200, `user` and `automated`). Example: en `user` 2024-01 = 8.68 B, en `automated` 2025-05 = 2.38 B.
  - `edits/per-page/<project>/<title>/user/monthly/…` (200).
  - `editors/aggregate/<project>/<editor-type>/<page-type>/<activity-level>/monthly/…`. Activity levels are `1..4-edits`, `5..24-edits`, `25..99-edits`, `100..-edits`; "5+ editors" = the sum of the top three bands.
  - `pageviews/top-by-country/…` returned 404 for de.wikipedia 2024-03; we use the published country datasets (§4) instead.
- **Use:** reconciliation targets (P11), language-level editors (P09).

## 4. Pageviews by country (differentially private)

- **Where:** `https://analytics.wikimedia.org/published/datasets/`
  - `country_project_page/<YYYY-MM-DD>.tsv`: current, **2023-02-06 to present**. Gaussian zCDP; release threshold >90 views for lower-risk countries (>550 / >1000 for medium/higher risk); 95% error ±36 views for lower-risk countries. Medium- and higher-risk countries only from 2024-02-15.
  - `country_project_page_historical/`: **2017-02-09 to 2023-02-05**. Laplace noise (ε = 1); release threshold >450 views; 95% error ±90 views.
  - `country_project_page_historical_pre_2017/` (from 2015-07-01).
- **Licence:** CC0.
- **Format:** TSV, no header: `country  country_code  project  page_id  page_title  item_id(QID)  views`.
- **Known problems:**
  - **The current dataset has no United States data from 2023-02-06 to 2023-09-19**, plus 7 missing days (2023-06-19, 2023-10-25, 2023-11-13/17/19/23/27). Country shares for exposure (P03) must avoid that window, e.g. use 2022 from the historical series or 2023-10 to 2024-04 from the current one.
  - Only pages above the release threshold appear, so per-country totals undercount the long tail. Language-level country shares are tilted toward popular pages.
  - Pages are included only if they had >150 views globally that day.
- **Size:** about 16 MB/day (current) and 3 MB/day (historical); a 12-month window is about 6 GB.

## 5. Wikidata

- **Endpoints confirmed:** SPARQL `https://query.wikidata.org/sparql` (200) and `wbgetentities` (`https://www.wikidata.org/w/api.php`, 200, up to 50 IDs per call).
- **Licence:** CC0.
- **Dumps:** `latest-all.json.bz2` is 104 GB and `latest-truthy.nt.bz2` is 44 GB. **Not downloaded.** About 200k sample items take about 4,000 `wbgetentities` calls (cached), which is much cheaper. The country dataset also gives a QID per page.

## 6. Article topic (Lift Wing)

- **Endpoint:** `POST https://api.wikimedia.org/service/lw/inference/v1/models/outlink-topic-model:predict` with `{"page_title": …, "lang": …}`. Returns topic probabilities (e.g. Albert_Einstein: STEM.STEM* 0.89, STEM.Physics 0.72, Culture.Biography 0.71). It's language-agnostic because it's based on outgoing links, but it uses the **current** link graph, not a historical one.

## 7. Search-engine market share (StatCounter)

- **Where:** `https://gs.statcounter.com/search-engine-market-share/all/<country>/chart.php?…&granularity=monthly&csv=1` (200, monthly CSV).
- **Licence:** CC BY-SA 3.0, so attribute StatCounter.
- **Known problems:**
  - It measures page views on StatCounter-tracked sites, not searches.
  - Japan: Google ~77%, Yahoo! ~14%. Yahoo! Japan uses Google's index but its own results page, which has no AI Overviews, so count only Google itself as exposed.

## 8. Download budget (Drive3: 1,163 GB free on 2026-10-29)

| Item | Size |
|---|---|
| Clickstream, 11 core languages, 2017-11 to 2026-09 | 94 GB |
| pageview_complete monthly `user`, 2016-01 to 2026-09 | 411 GB |
| pageview_complete monthly `automated`, 2020 on | 223 GB |
| Country datasets (about 2 years of daily files) | ~12 GB |
| Wikidata / Lift Wing / AQS (API, cached) | <5 GB |
| **Raw total** | **~745 GB** |
| Processed Parquet + DuckDB (estimate) | 30–60 GB |

At the ~8 MB/s seen on one connection, the pageview dumps take on the order of a day to download. Wikimedia asks for no more than 2–3 parallel connections to dumps.
