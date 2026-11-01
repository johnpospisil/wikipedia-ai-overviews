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

## 9. AI Overviews rollout (treatment variable, P02)

- **Country dates:** `data/reference/aio_rollout.csv` is built by `python -m wao.build.rollout` from 142 Wayback Machine snapshots (2024-05-16 to 2026-10-29) of Google's help page [support.google.com/websearch/answer/14901683](https://support.google.com/websearch/answer/14901683). Each country's first appearance is bracketed by the last snapshot without it and the first one with it. Where an official Google announcement falls in that bracket, its date is used (`wave`, `source_url`); otherwise the bracket midpoint (`date_precision` gives the bracket). `all_users_from` marks the end of the "signed-in 18+" restriction. Raw parses are in `aio_help_snapshots.csv` and `aio_country_first_seen.csv`.
- **Waves:**
  - US 2024-05-14.
  - UK, IN, JP, ID, MX, BR 2024-08-15.
  - 123 countries 2024-10-28 (signed-in 18+ until about 2025-03-25).
  - Korea about 2024-12-20 (bracket).
  - AT, BE, DE, IE, IT, PL, PT, ES, CH 2025-03-25 (adults only until 2025-05-20).
  - 95 countries 2025-05-20, including RU, UA, BY, KZ, NL, SE, HK, AF, IR.
  - Türkiye about 2026-02-10 (bracket).
  - France and its overseas territories 2026-07-22.
- **Never listed:** mainland China. **Removed:** Iran was listed only from 2025-05-30 to 2025-09-01.
- **Languages:** `aio_language_support.csv`, hand-built from the announcements. The help page only lists languages from 2025-05-30.
  - French was available only in Switzerland from 2025-03-25, elsewhere from 2025-05-20, and in France from 2026-07-22.
  - Chinese, Russian and Persian from 2025-05-20.
  - Korean is assumed to arrive with Korea; no announcement was found.
- **Caveats:**
  - Google rolls out gradually and runs A/B tests, so "listed" ≠ "shown on every query". AI Overviews appear only on some queries, and the share varies by market and over time.
  - The bracket logic assumes the page was updated within about 2 weeks of an announcement.
  - Month resolution is used in the models.
- **Other events:** `data/reference/events.csv` (sourced): chatbot launches, competing AI search (Bing Chat, ChatGPT search, Yandex Neuro 2024-04-16), Google AI Mode, Google ranking updates 2022–2026 (Search Status Dashboard), and Wikimedia measurement changes (bot reclassification of Mar–Aug 2025 traffic; the US gap in the country data). Vector 2022 skin rollout dates by language are **not yet included** because no primary source was found.

## 10. Country shares and exposure (P03)

- **Country shares** (`data/reference/country_shares.csv`, built by `python -m wao.ingest.country`): each edition's `user` pageviews by country, 2023-10..2024-04.
  - Source: AQS `pageviews/top-by-country/<wiki>.wikipedia.org/all-access/<y>/<m>`. Note the `.org`; without it the call 404s. Counts are rounded up to the next 1,000.
  - Some edition-months are missing (fr 2024-03, pl 2024-03, ja 2024-02). Those months are dropped from both the country list and the total.
  - **Protected countries are withheld** (missing ranks): Iran, mainland China, and Russia/Belarus/Kazakhstan among others. The withheld mass is the residual: AQS `user` total minus published countries. It is split across withheld countries in proportion to the DP dataset (§4, which publishes RU/BY/KZ from 2024-02-15), scaled to AQS through countries both sources publish. Whatever remains goes to IR (fa), CN (zh), or `ZZ` (unknown, treated as unexposed).
  - Residual-based share: ru 73%, fa 78%, es 6%, en 5%, others ≤2%.
  - The DP dataset on its own gave implausible shares (fa with no Iran; fr with Poland at 4%), so it is used only for the residual split.
- **Google share:** `data/reference/search_share.csv` (StatCounter, all engines, monthly 2017-11..2026-09, by country). The exposure uses the pre-period mean (2023-10..2024-04), fixed so search behaviour changed by the treatment can't feed back into it.
- **Exposure:** `data/reference/language_exposure.csv` (wiki × month): `exposure`, `exposure_all_users` (no signed-in-adult restriction), `exposure_listed` (no Google weight), `exposure_as_listed` (counts Iran's 2025-05..09 help-page listing; the primary spec treats Iran as never live, decided 2026-10-29). `language_cohorts.csv` gives the cohort (first month ≥ 0.5) and design role.
- **Caveats:**
  - VPN users count where their IP is located. That's also where Google decides whether to show AI Overviews, so it's consistent.
  - The hidden `ZZ` share is treated as unexposed, a mild understatement for en and es.
  - Availability ≠ how often AI Overviews appear on Wikipedia-type queries.

## 11. Parser checks on real files (P04)

- **Clickstream en 2026-09:** 33,553,254 rows, 0 rejected, min n = 10. Titles containing `"` (13,521 rows) are written quote-wrapped with `\"` escapes and are now decoded. 18 genuine titles contain a backslash (e.g. `A\J:_Alternatives_Journal`). There were no unknown `other-*` referrers. Type `other` (780k rows) = a link no longer present in the page.
- **pageview_complete monthly user 2024-03** (3.28 GB bz2, size matches the listing): 242.7 M lines; the 11 core editions are 107.7 M rows. 0 malformed, 0 five-column, 0 rows whose daily counts don't sum to the monthly total; max day 31. **Totals equal AQS `user` all-access monthly views exactly for all 11 editions.**
  - `null` page_id: 1.3–6.8% of views, so P07 needs a title fallback.
  - mobile-app: 0.6–5.0% of views.
  - Speed: 11.0 min per file at 367k lines/s with Python's single-threaded bz2, 42 MB RAM. 129 user months + 77 automated months ≈ 38 h serial. A parallel bz2 decoder (e.g. `lbzip2`) or several files at once would cut this (decided in P07).
- **Wikidata API:** entities parse as expected. Missing items come back as `missing` and are dropped. A single malformed ID fails the whole `wbgetentities` batch (`no-such-entity`); the parser raises rather than returning nothing.

## 12. Clickstream ingest (P05)

- **Run:** `make ingest-clickstream` (`src/wao/ingest/clickstream_ingest.py`); 2026-10-29, about 3 h wall time for 1,917 files (97 GB gzip), almost all of it download at ~10 MB/s. Conversion took 50 min in total at ~705k rows/s overall; peak RSS 7.0 GB. Resumable: one done marker per file in `clickstream_done/`, partial downloads resume from `.part`.
- **Outputs (under `WAO_DATA_DIR/parquet/`):**
  - `clickstream/lang=/month=/pairs.parquet` (`prev, curr, referrer, n`): 7.42 bn rows, 84 GB (en alone 41 GB, 3.46 bn rows).
  - `clickstream_article/lang=/month=/part.parquet`: per-article arrivals by referrer class, `arr_total`, `out_links` (clicks to other articles, for P23); 25 GB.
  - `clickstream_lang_month.parquet`: 40 languages × months = 1,917 rows of totals by referrer plus the number of articles with any published arrival.
- **Checks:** 0 rejected lines in every file; no published count below 10 (the threshold holds); pairs total = article total = lang-month total (unit test). No gaps inside any language's range: en, de, es, ja, ru 2017-11 → 2026-09; fr, it, pl, pt, zh 2018-01 →; fa 2018-03 →; the other 29 languages 2024-08 →.
- **English referral mix (share of arrivals, descriptive):** search 43–46% every year 2018–2026 (2023 45.4%, 2024 46.2%, 2025 43.6%); links between articles rose from 23% (2018) to 36% (2026); no-referrer fell from 29% to 18%.
- **Breaks to handle in P11** (visible in `p05_clickstream_coverage.png` / `p05_referral_mix_en.png`):
  - **2020-06, en:** no-referrer share falls from 23% to 16%, search rises from 44% to 49%, and articles with any arrival drop from 4.8 M to 4.1 M. Consistent with the `automated` agent class Wikimedia introduced in spring 2020 removing bot traffic that had mostly arrived with no referrer. Check against events.csv.
  - **2025-03, en (and zh in 2025–26):** articles with any arrival jump from 5.6 M to 6.6 M for one month, with no-referrer up to 20%. Looks like undetected automated traffic, around the 2025 bot-detection change. zh shows several similar bright months.

## 13. Sampling frame and article sample (P06)

- **Inputs:**
  - **SQL table dumps 2026-10-01** (`page`, `page_props`, `redirect`) for the 11 editions: 6.7 GB, each file md5-checked against `dumpstatus.json` (`python -m wao.ingest.sql_dumps` → `parquet/wiki_sql/`). Namespace-0 non-redirect pages: en 7.25 M (0.38 M of them disambiguation) down to fa 1.09 M; Wikidata QIDs on 97.6–99.9% of them.
  - **pageview_complete monthly `user` files for 2023** (35 GB raw, kept for P07) → `parquet/pageview_month/month=2023-MM/` (`lang, title, page_id, access, views`; all namespaces of the 11 editions; 11 GB). 0 unparseable rows. **Totals equal the AQS `user` all-access monthly aggregate exactly** (all 11 editions, 2023-01).
- **Frame** (`parquet/frame.parquet`, 22.7 M articles; `python -m wao.build.sample`):
  - Definition: namespace-0, non-redirect, non-disambiguation pages with any 2023 `user` view; main page excluded.
  - How views are assigned to pages:
    - By `page_id`.
    - Rows without one (1.5–6.8% of views) by title.
    - Views of redirects go to the redirect's target.
  - **The frame holds 92–96% of each edition's 2023 user views.** The rest:
    - other namespaces 0.9–4.9% (de and es highest: their main pages are in the Wikipedia: namespace)
    - main page 0–1.9%
    - disambiguation pages 0.4–1.6%
    - pages missing from the 2026 dump 0.8–1.9% (deleted since 2023, or titles that never existed)
    - Full table: `report/qa/p06_view_resolution.csv`.
  - Using the 2026 page table rather than a 2023 one therefore drops at most ~2% of 2023 views, and those are mostly junk titles.
  - Articles created after 2023 are excluded by construction. The sample is a closed 2023 cohort, so composition can't change with the treatment.
  - **Popularity decile:** within each edition by total 2023 views, ties broken at random. en deciles run from 1–79 views (decile 1) to ≥17,168 (decile 10).
  - Partial-year articles (fewer than 12 months with views) are 7% of en and 42% of fa; they're mostly low-traffic months with zero views, not new pages.
- **Wikidata types** (`wao.ingest.wikidata_types`, cached SPARQL):
  - Truthy P31 for 361,539 QIDs (phase 1 plus all 111,247 items with an article in all 11 editions), and the P279 graph above them (about 50k edges).
  - Rolled up to 19 ordered coarse classes plus `other`, `no_p31` and `no_qid`.
  - Items with no P31 (concepts modelled as classes) use their own P279.
  - Weighted frame composition: human 30%, settlement 9%, other 9%, admin region 7%, organization 7%, taxon 6%, structure 5%, … chemical 0.8%, health 0.3%, country <0.1%. `other` is a long tail (largest class 0.4%: chemical-entity types, stations, family names, car models).
  - **Articles without a QID: 42,672 in the frame (0.2%)**, mostly zh, ja, pl, it.
- **Sample** (`panels/sample.parquet`, 197,453 articles; `report/qa/p06_sample_by_{lang,stratum,type}.csv`):
  - **A. Language sample, two-phase, 12,000 per edition:**
    - Phase 1: 2,500 random articles per edition × decile.
    - Phase 2: strata are edition × decile × coarse type, allocated proportionally with a floor of 30 per stratum (all if fewer), so small types are oversampled.
    - 2,262 strata.
  - **B. Concept panel:**
    - 6,000 of the 111,247 items with an article in all 11 editions, stratified by type × item decile (2023 views summed over editions), with a floor of 15.
    - Each selected item brings all 11 articles (66,000 articles).
    - It includes 1,338 humans, 66 countries, 140 chemicals and 116 health items.
  - **Weights:** π_A = (n1/N) × (n2/n1) and π_B = m/M. The two draws are independent, so π = π_A + π_B − π_A·π_B and `weight` = 1/π (Horvitz–Thompson). `w_concept` = 1/π_B is for the item panel (P19). 562 articles are in both samples.
  - **Checks:**
    - The weight sums reproduce each edition's frame size within 0.3%.
    - A 30-replicate simulation (`tests/test_sample.py`) gives unbiased totals (count ratio 1.000, views 0.995, rare-type count 1.007).
- **Performance:** about 25 min for the frame (en 5 min) when DuckDB spills to the internal SSD (`WAO_TMP_DIR`, default `$WAO_DATA_DIR/tmp`). Spilling to the external drive that also holds the input was more than 4× slower. About 45 min for the SPARQL type lookups, cached after the first run.

## 14. Daily pageviews for the sample (P07)

- **Inputs:** pageview_complete monthly files, `user` 2016-01..2026-09 (129 files) and `automated` 2020-05..2026-09 (77; the agent class only exists from 2020-05, so before that automated traffic is inside `user`). 593 GB raw, kept. `spider` files stop at 2023-02 and would add 512 GB, so they're not used. The dumps publish no checksums: each file is checked by its listed size and by `bzip2 -dc` exiting cleanly.
- **Outputs** (`python -m wao.ingest.pageviews`, resumable; `make ingest-pageviews`):
  - `parquet/pageview_daily/agent=/month=/`: `lang, page_id, date, access, views` for the 197,453 sample articles (1.5 GB).
  - `parquet/pageview_match/agent=/month=/`: the same views split by how they were matched (0.4 GB; for P11 and P13).
  - `parquet/pageview_lookup.parquet`: sample ids and titles plus every redirect (up to 2 hops) pointing at them: 332k redirects, en 83k.
- **Matching:**
  - By `page_id` first. Page moves keep the id, and views of a redirect title usually carry the target's id.
  - Then the redirect page's own id, then the title or a redirect title when `page_id` is null or belongs to a since-deleted page.
  - Rows whose title matches but whose id is another live page are dropped (0.03–0.4% of views).
  - Over 2016–2026, 9.1% of matched user views came from something other than "page_id plus current title". That share falls from 12.5% in 2016 to 4–5% in 2026: mostly older titles and redirects (`id_alt_title`), plus 0.2–2.5% with no page_id.
  - Check: for 2023-01, the id-matched totals equal P06's monthly totals exactly (182,620 articles, 307,549,484 views).
- **Coverage** (share of sample articles with any `user` view in the month; `report/qa/p07_coverage.csv`):
  - 74% in 2016, rising to 94% (2023) and 98% (2025–26). The early gap is articles not yet created.
  - Among articles already seen in that or an earlier month, coverage is 95–98% throughout. The rest are low-traffic articles with zero views that month.
- **File checks** (`report/qa/p07_files.csv`):
  - 0 rows whose daily counts don't sum to the monthly total.
  - 7,593 malformed lines in 53 billion. All are junk like `de.wikipedia \r\n` with no title, 99% of them in 2016–2019.
- **Defective dump: zh 2022-10.** The monthly `user` and `automated` files are missing about 85% of zh rows for titles sorting after about "塔尔". Only 6,271 sample articles were found, against about 15,000 in the neighbouring months, while AQS shows a normal month (407.7 M views). The daily files for that month are complete, so zh 2022-10 is rebuilt from the 62 daily files (20 GB raw under `pageview_complete/daily/`; `data/reference/pageview_repairs.csv`, `--repair`). After the repair it has 14,972 articles and 8.97 M views, against 9.18 M in 2022-09 and 9.22 M in 2022-11. A rolling-median scan of every edition-month found no other defect.
- **Flags for P11:**
  - The share of views with a null `page_id` almost vanishes in 2020-06 (0.16% vs about 1%), and falls from 2.5% to 0.4% across 2026-03..04. These are methodology changes upstream. Matching by title absorbs both, so totals are unaffected, but they mark possible breaks.
  - fa coverage dips to 81–87% in 2025-12 and 2026-03..04 (99% otherwise). Possibly Iranian internet disruptions. fa is a control language, so check this against AQS fa totals.
- **Run time:** about 17 h of processing across 2 workers, limited by downloads (about 10 MB/s, with a slow spell on 2026-10-30), roughly 4–13 min per file.

## 15. Article features at 2023-12-31 (P08)

- **Revision histories:** stub-meta-history dumps of 2026-10-01 (82 files, 246 GB raw, md5-checked) → `parquet/stub_history/lang=/` (420 MB): every revision of every sample article (27.7 M revisions; id, time, size, minor flag, editor). Editors are stored only as a 64-bit hash; IPs never leave the parser. They also feed P09's per-article edits. All 197,453 sample articles are found.
- **Which revision:** the last revision at or before 2023-12-31 23:59:59 UTC. 99.85% of articles have one. The 289 that don't (en 66, it 44, pt 35…) had their history merged or re-imported after 2023. `created` is the first revision in the dump.
- **Text:** fetched by revision id in batches of 50 (`wao.ingest.revisions`). Only derived numbers are kept, never the text. Statuses: ok 197,111 · no_rev_2023 289 · text_hidden 39 · badrevid 14 (deleted revisions). The wikitext size equals the dump's recorded size for every ok revision.
- **API access (important for reruns):**
  - Wikimedia's 2026 rate limits allow 200 requests/min for a bot with a compliant User-Agent and 10/min for a client identified by IP alone.
  - From 2026-10-30 this IP was held to the IP tier and then blocked, despite the User-Agent.
  - Logged-in requests are counted per account. `http.login` uses a bot password (`WAO_BOT_USER`, `WAO_BOT_PASS` from Special:BotPasswords), and with it the fetch ran at about 40 articles/s with no 429s (about 70 min).
- **Features** (`panels/article_features.parquet`, one row per sample article; `wao.build.wikitext`, `wao.build.features`):
  - bytes, prose_chars, lead_chars, n_sections (level 2), n_headings, n_refs (`<ref>` with content), n_templates, has_infobox, is_redirect;
  - rev_id, rev_ts, created, age_years at 2023-12-31, n_rev_2023;
  - coarse_type (Wikidata P31 rolled up, P06);
  - topic, topic_score, topic_group, topic_confident (score ≥ 0.5).
  - Character counts are comparable within an edition, not across scripts.
- **Infobox:** a template counts if it's sitelinked from a Wikidata "Wikimedia infobox template" item (Q19887878), matches the edition's name prefix (Infobox, Ficha, Info/, Карточка, 基礎情報, جعبه اطلاعات…), or redirects to one of these (`features/infobox_templates.parquet`, 23k names).
  - **Check against HTML** (20 flagged + 20 unflagged per edition, the 2023 revision rendered; `report/qa/p08_infobox_check.csv`): precision 1.00 in every edition, recall 0.92–1.00, weighted agreement 95–100%.
  - Most misses are year-page calendar and navigation boxes that use the `infobox` CSS class, plus a few templates with no infobox-type Wikidata item (it "Album", ja "大学", zh "PBB").
  - One pt helper ("Info/Partido político/lugares", a seat chart) is excluded.
  - Shares by edition: 48% for de (its articles use fewer infoboxes) to 84% for fr and ru.
- **Topics:** Lift Wing `outlink-topic-model` (64 ORES topics, threshold 0.01), all 197,453 returned ok (`features/topics.parquet`, long format).
  - The model reads the **current (2026) outlinks**, not the 2023 revision, so topic is treated as a stable property of the article.
  - 98.5–99.2% have a top topic with score ≥ 0.5.
  - Top groups: Culture 29–50%, Geography 28–44%, STEM 15–20%, History and Society 6–9%.
- **Missing:** text features 0.05–0.42% by edition; creation date and topic 0%. Distributions: `report/qa/p08_feature_summary.csv`, `p08_status.csv`, `p08_topics.csv`; figure `report/figures/p08_article_features.png`.
- **Medians** (unweighted sample):

  | | prose chars | references | age (years) |
  |---|---|---|---|
  | Lowest | fa 552, zh 457 | 1 in fa, it, pl | 8.8 (fa) |
  | Highest | de 3,136, en 3,050 | 6 in en | 15.8 (en) |

## 16. Editors and edits (P09)

- **Language level:** AQS `edits/aggregate` and `editors/aggregate`, content pages (article namespace), monthly from 2001 through 2026-09 (`wao.ingest.editors`; 132 requests at one per 7 s because AQS ignores the wiki login).
  - Raw output: `parquet/editors/aqs_lang_month.parquet`. Wide panel: `panels/editors_lang_month.parquet`, with edits by type plus `active_*` (5+ edits) and `very_active_*` (100+) for registered (`user`) and anonymous editors.
  - AQS editor types are exclusive: group-bot, then name-bot, then user or anonymous. Bots are therefore excluded from the user and anonymous series.
  - Gaps: only 9 months, all in 2001–2003 (es, fr, it, pt).
- **Article level:** `panels/article_edits_month.parquet`, sparse (a missing article-month means 0 edits). Built by `wao.build.edits` from the P08 stub histories, re-parsed with an editor `kind` (user, ip, temp, deleted) and `name_bot`.
  - Columns: edits, edits_user, edits_anon, edits_bot, edits_minor, editors (distinct non-bot), editors_user, editors_anon, bytes_delta (non-bot net size change).
  - Bots: the AQS name rule, plus current members of the local `bot` group and the global-bot group (`parquet/editors/bots.parquet`; 33–313 accounts per edition). Former bot-group members with non-bot names are missed.
  - Bot share of 2023 sample edits: de and pt 5%, en 8%, ru and fa 20%, pl 25%.
- **Checks** (`report/qa/`):
  - Per-page: 20 random sample articles' 2023 edits from the stubs equal AQS `edits/per-page` exactly (20/20; 7 with 0 edits, where AQS returns 404).
  - Weighted sample vs AQS, 2023 (`p09_reconcile_2023.csv`): Horvitz–Thompson estimates of non-bot edits are 88–101% of AQS user+anonymous content edits; bots are 88–101%. Being slightly under is expected, because AQS also counts edits to pages later deleted, redirected or moved out of the article namespace.
- **Temporary accounts** (`p09_temp_accounts.csv`, `p09_temp_check.csv`). Temporary accounts (`~2025-…`) replace IP editing. The first such edits:

  | Edition | First temp edits |
  |---|---|
  | de, fr, ja, zh, pl, fa | 2025-06 |
  | it | 2025-09 |
  | en, es | 2025-11 |
  | ru | 2026-03 |
  | pt | none (no logged-out editing) |

  - AQS anonymous **edits** continue smoothly across the switch, so AQS counts temporary accounts as anonymous and the edit series are consistent.
  - Anonymous **editor** counts change meaning, from IPs to accounts. Compare anonymous editors only before the switch, or use edits or registered editors.
  - An earlier rule treated any user name starting with "~" as temporary. Some old user names also start with "~"; fixed, and the stubs re-parsed.
- **Policy and outage breaks in the editor series:**
  - pt stopped logged-out editing in 2020-10, so anonymous edits are 0 from 2020-11 and registered active editors jump.
  - fa anonymous edits are about 0 from 2021-11 to 2022-03, probably a local IP-editing restriction.
  - fa registered active editors fall to 155 in 2026-04 (about 900 usually). Likely an Iranian internet shutdown; matches the P07 coverage dips.
- **Blinding:** the series are shown over the full period for data quality only (`report/figures/p09_editors.png`, no launch dates). Treated-vs-control contrasts wait for P15 and P24.

## 17. Search-engine context (P10)

- **Engine shares** (`wao.build.search_context`):
  - From the P03 StatCounter download (126 countries, 2017-11..2026-09). Engines are grouped into google, bing (incl. MSN), yahoo, yandex (YANDEX + YANDEX RU), baidu, naver, duckduckgo and other.
  - Junk rows (`--` country, blank engine) and all-zero country-months are dropped, and each country-month is renormalised to 1.
  - Output: `parquet/search_share.parquet`.
- **Per edition:** `data/reference/search_share_lang.csv` gives each edition's readers' engine mix. Countries are weighted by the fixed P03 reader shares, renormalised over countries with data (95–100% of weight for the core editions; the hidden `ZZ` bucket has none).
  - Every engine lands in clickstream's `other-search`.
- **Non-Google share of `other-search`, pre-period 2023-10..2024-04** (`report/qa/p10_non_google_lang.csv`). Elsewhere it is 3–10% (fa 3%, es and it 5–6%, de, en and fr 9%), mostly Bing. Three editions exceed 10%:

  | Edition | Non-Google | Main other engine |
  |---|---|---|
  | ru | 53% | Yandex 50% |
  | ja | 22% | Yahoo! Japan 12%, Bing 8% |
  | zh | 12% | Yahoo! in Taiwan and Hong Kong 4%, Baidu 2%, Bing 4% |

  Yahoo! Japan uses Google's index on its own results page, without AI Overviews.
- **Drift after 2024:**
  - Google's StatCounter share falls in most markets in 2025–26, mostly towards Bing: DE 90→83% (2023→2026 mean), BR 96→88%, PL 96→89%, IT 95→88%, US 89→85%.
  - Japan jumps: Bing 8%→36% between 2025-10 and 2026-04, and Google 80%→55% (`p10_google_share_markets.csv`).
  - StatCounter measures page views on sites carrying its tracker, so a tracker-mix artefact can't be ruled out.
  - Exposure (P03) uses the fixed pre-period shares, so it is unaffected. But in these markets `other-search` after 2025 is less Google-only than before.
- **Ranking updates:** `data/reference/ranking_updates_monthly.csv` (month: core_days, core_update, other_update_days), from `events.csv`.
  - Google's Search Status Dashboard starts 2021-11. Core updates from 2018-03 to 2021-07 were added from trade-press dating (Search Engine Roundtable; Google announced them on X), marked "press-dated". 7 of the 11 have no published end date and are given 14 days.
  - 35 of the months 2016-01..2026-09 have a core update; spam, helpful-content and reviews updates are counted separately.
- **Google Trends** (`wao.ingest.trends`; context only, never an outcome): the topic "Wikipedia" (/m/0d07ph) in 15 key countries, monthly, via the unofficial pytrends client.
  - Output: `parquet/context/google_trends.parquet`.
  - Each country is pulled for 2016-01..2026-09 and for 2021-01..2026-09. After rescaling, the two pulls differ by a median 0.4–1.4% per month, with the 90th percentile at 1.1–4.6% (highest for low-interest IR, RU and JP; `report/qa/p10_trends_noise.csv`).
  - Both pulls were on the same day and may share Google's sample, so treat this as a lower bound on the noise.
  - Trends measures searches about Wikipedia, not traffic to it.

## 18. Data quality and reconciliation (P11)

Run with `make qa`. Checks are in `tests/test_data_quality.py`, tables in `report/qa/p11_*.csv`, the figure in `report/figures/p11_reconciliation.png`, and every known break in `data/reference/data_breaks.csv`, which P13 and P20 read.

- **AQS reference series** (`wao.ingest.aqs_checks`):
  - Monthly totals per edition: user desktop, mobile-web and mobile-app, automated and spider (2016-01..2026-09).
  - Per-article user views for 200 random sample articles.
- **Checklist** (`p11_checklist.csv`):
  - PASS: P07 views by current title equal AQS per-article exactly in 99.3% of 23,114 article-months. Redirect-resolved totals are ≥ AQS for all 200 articles (1% tolerance, two zh articles off by a few views), with a median of +0.8% and p90 +38% from redirects and old titles.
  - PASS: no duplicate article × day × access × agent rows.
  - PASS: the weighted sample vs AQS `user`, 2023: de 0.87, en 0.97, es 0.90, fa 0.89, fr 0.83, it 0.97, ja 0.97, pl 0.94, pt 0.94, ru 0.93, zh 0.93. AQS also counts the Main Page and non-article pages, which are large in fr and de.
  - FAIL: clickstream 2025-04 is incomplete (see below).
- **Clickstream vs AQS web views** (desktop + mobile web, `user`):
  - After 2019-04 the ratio is stable at 0.82–0.95 by edition. It is below 1 because the <10 pairs are dropped and because of request-vs-pageview differences.
  - **Method change 2019-04:** the ratio steps up in every edition at once: ja +35%, ru +27%, fa +23%, zh +16%, fr and pl +8%, pt +7%, es +6%, de +5%, it +3%, en +2%. Non-Latin scripts gain most, consistent with a fix to percent-encoded titles. **Clickstream outcomes should start at 2019-04,** which leaves 61 pre-period months.
  - **2025-04 incomplete:** the month is 0.81–0.86 of its neighbours in every edition, and per article the clickstream/pageview ratio drops by the same factor (median 0.83 vs 0.98). AQS is smooth. About 5 days are missing.
  - Other flagged months: en 2020-05 +8% (automated agent class introduced); pl and zh 2018-07 (before 2019-04); fr 2024-08 −8%; fa 2026-04..05 (outage).
- **2025 bot reclassification:**
  - AQS automated share of views, 2024-09..2025-02 vs 2025-05..12:

    | Edition | Before | After |
    |---|---|---|
    | en | 10.7% | 22.3% |
    | pt | 10.3% | 33.6% |
    | zh | 12.9% | 32.9% |
    | pl | 7.3% | 15.5% |
    | fr | 25.1% | 17.3% |

    The rise starts in 2025-04 and persists into 2026.
  - P07 dump views equal AQS per-article in 2025-03..08 (gap 0.0%), so the dumps downloaded in 2026-10 carry the same classification.
  - The clickstream/AQS ratio is flat across the window in every edition, pt included, so clickstream uses the same `user` filter.
  - Nothing before 2025-03 was reclassified: the automated share is unchanged up to 2025-03.
  - Result: a level break in `user` traffic from 2025-04 in both outcome sources. Its size differs by edition, so month fixed effects don't absorb it.
- **Truncation (<10 rule):** `wao.build.truncation`. A censored article-month gets E[X | X ≤ 9] with X ~ Binomial(web views, p̂), where p̂ = search arrivals / web views of uncensored articles in the same edition × 2023 decile × month. The bounds are 0 and min(9, views).
  - Hidden share of search arrivals per edition: 0.4–3.1% in 2023 (upper bound 0.6–3.9%), rising to 0.6–5.3% in 2026 (upper 0.8–7.7%, highest fa, pl and zh) as traffic falls.
  - By 2023 popularity decile: deciles 1–2 are 80–100% hidden; deciles 5–6 hide 3–97% depending on the edition (ja least, fa and pl most); decile 10 hides 0%.
  - Simulation on 2023 (uniform true decline, then re-censor): at the edition level the bias is ≤0.6 pp even for a 50% decline. A true 20% decline is overstated by:

    | Decile | Bias |
    |---|---|
    | 1 | up to +80 pp (noisy: few uncensored articles) |
    | 2–5 | typically +5–40 pp |
    | 6 | +1–24 pp |
    | 7 | 0–14 pp |
    | 8 | 0–4 pp |
    | 9–10 | under 1 pp |

    ja and en are affected least.
  - **Implication:** edition-level search outcomes are safe. Tail and head-vs-tail results must use pageviews or `parquet/qa/search_imputed.parquet` (per article × month: observed, hidden, upper).

