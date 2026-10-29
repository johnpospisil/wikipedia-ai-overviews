# Project 5: Did Google's AI Answers Hurt Wikipedia?

**Backlog ID:** AI-1 · **Difficulty:** Medium · **Data access:** Open (no keys) · **Estimated time:** 6 weeks

**Working title:** *Answered Above the Fold: Wikipedia Traffic After Google's AI Overviews*

**One-sentence pitch:** Use Wikipedia's public pageview and clickstream data to measure how much search-driven traffic to Wikipedia fell after Google rolled out AI Overviews, which kinds of articles lost the most, and whether readers who still arrive behave differently, using the staggered country/language rollout as a natural experiment.

---

## 0. Day-one access check

Before committing, confirm in one afternoon:
- [ ] Wikimedia Pageviews REST API returns per-article daily views for `en.wikipedia` with `agent=user` (e.g. `https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/Albert_Einstein/daily/20230101/20230131`). Set a descriptive `User-Agent` header with contact info, as Wikimedia's API policy requires.
- [ ] The monthly **clickstream** dumps exist for your target months and languages at `dumps.wikimedia.org/other/clickstream/`.
- [ ] The `pageview_complete` daily dumps download and parse (`dumps.wikimedia.org/other/pageview_complete/`).

If all three work, there is no access risk on this project.

## 1. The question

**Primary:** After AI Overviews launched in a given market, did *search-referred* traffic to Wikipedia articles fall more than would be expected from pre-existing trends, and more than in language editions where AI Overviews had not yet launched?

**Secondary:**
- **Which articles lost most?** Hypothesis: "quick-answer" articles (definitions, dates, people's ages, simple facts, units) fall more than long-read topics (history, science explainers, ongoing events).
- **Did the referral mix change?** Clickstream gives the share of arrivals from "other-search" (mostly Google) vs internal links vs external sites. Did search's share fall, and did internal navigation hold up?
- **Is it AI Overviews or chatbots?** Separate the ChatGPT era (from Nov 2022) from the AI Overviews launch (May 2024 in the US) using timing and language variation.
- **Editors:** did edit activity follow readership down? (Readers → editors is the long-run sustainability question.)

**A finding that would be wrong if:** search referrals fall equally in languages and countries without AI Overviews, or "quick-answer" articles decline no faster than long reads.

## 2. Why now

- Google launched AI Overviews in the US in May 2024 and expanded it to more than 100 countries in late 2024, then to more countries and languages through 2025. The staggered rollout is what makes a causal design possible. **Check the exact dates and language lists against Google's announcements before publishing.**
- In 2025 the Wikimedia Foundation said human pageviews were down roughly 8% year over year, after it reclassified a lot of bot traffic, and pointed at AI search and social video. An independent, article-level measurement is valuable.
- Publishers are fighting about "zero-click search" and AI referrals. Wikipedia is the cleanest public dataset for that fight, because almost nobody else publishes traffic data.
- It's a direct sequel to your Stack Overflow project (Project 4): the same question about the knowledge commons, with the same ITS and comparison-group machinery.

## 3. Data sources

| Source | What it gives you | Grain | Where |
|---|---|---|---|
| **Wikimedia Pageviews API** | Daily views per article, split by agent (`user`, `spider`, `automated`) and access (desktop, mobile web, app) | article × day, July 2015–present | wikimedia.org/api/rest_v1 (open, no key) |
| **pageview_complete dumps** | The same data in bulk for all articles in all projects | article × day | dumps.wikimedia.org/other/pageview_complete |
| **Clickstream** | Monthly (referrer, article, count) pairs, with referrer types `other-search`, `other-external`, `other-internal`, `other-empty`, plus internal links | article pair × month, several languages (en, de, fr, es, ja, ru, fa, zh, it, pl, pt…) | dumps.wikimedia.org/other/clickstream |
| **Wikidata** | Article type (`instance of`: human, city, chemical compound, film…) for classifying articles | item | query.wikidata.org or JSON dump |
| **Wikimedia article topic model** | Predicted topic (STEM, culture, geography, history…) for each article | article | Wikimedia Lift Wing / ORES `articletopic` (check current endpoint) |
| **Edit history** | Edits and active editors per article and month | revision | MediaWiki API or `mediawiki_history` dumps |
| **AI Overviews rollout table** | Launch date by country and language | event | Hand-built from Google's announcements (cited) |
| **Google Trends** | Search interest in common query types (context only) | week | trends.google.com |

**Licensing:** Wikimedia pageview and clickstream data are CC0. Wikidata is CC0.

**Expected size:** clickstream for English is roughly 1 GB per month (gzip TSV). For per-article daily views, sample about 200k articles stratified by type and popularity rather than all 7M.

## 4. Building the dataset

1. **Rollout table:** a cited CSV of `market, language, launch_date, source_url`. This is the treatment variable, so hand-check it.
2. **Article sample:** stratified sample of articles by Wikidata type and popularity decile, in 6–10 languages, with the same Wikidata items matched across languages where possible (the same concept, e.g. "Albert Einstein", in several languages makes a powerful within-concept comparison).
3. **Article features:** length, number of sections, presence of an infobox, Wikidata type, topic, "quick-answer" label (see below), and age.
4. **"Quick-answer" label:** rule-based to start (people, places, dates, units, definitions, chemical elements). Validate against a small hand-labelled set of 300 articles, and report precision and recall.
5. **Panels:** article × month with views by access type, plus clickstream referral counts by type. Language × month aggregates for the headline.
6. **Checks:** totals compared with Wikimedia's published monthly aggregates; mark the 2025 bot-reclassification period explicitly; no duplicate article-days; redirect titles resolved to canonical pages.

## 5. Method

### Headline effect
- **Staggered difference-in-differences** at language × month: outcome = log(search referrals) from clickstream; treatment = month AI Overviews launched in markets where that language dominates. Use Callaway & Sant'Anna to handle staggered timing.
- **Within-concept design:** for the same Wikidata item across languages, compare views in languages that got AI Overviews early with languages that got it late. This removes "the topic got less interesting" as an explanation.
- **ITS for English** around May 2024, with trend and seasonality, as the readable headline.

### Heterogeneity
- Quick-answer vs long-read articles (triple difference: article type × treated language × post).
- Mobile vs desktop (AI Overviews appear on both; mobile users click through less).
- Popularity: did head articles or long-tail articles lose more?

### Robustness
- **Bot reclassification:** Wikimedia changed its bot detection in 2025. Use clickstream (which counts referrals, not agent type) as the main outcome and re-run with and without the affected months.
- Placebo launch dates; event-study pre-trends; dropping the ChatGPT launch window.
- Languages with little Google market share (e.g. Russian, where Yandex dominates) as negative controls.

### What you won't claim
That every lost view is a lost reader: some people get their answer in the AI Overview, which may be fine for them. Frame it as a question about traffic and attribution, not harm to readers.

## 6. Charts

| # | Chart | Purpose |
|---|---|---|
| **Hero** | **Search-referred traffic indexed to launch month**, treated vs not-yet-treated languages (event-study style), with confidence band | The causal headline |
| 2 | Slope chart: change in views for quick-answer vs long-read articles | What kinds of knowledge lost clicks |
| 3 | Stacked area: referral mix (search / internal / external / empty) for English, 2018–today | Where readers come from now |
| 4 | Small multiples: one language per panel, with its launch date marked | Shows the staggered rollout visually |
| 5 | Dot plot: change by Wikidata article type (humans, cities, films, chemicals…) | Fun and shareable |
| 6 | Editors vs readers: active editors per month alongside views | The sustainability angle |

**Interactive:** "Look up an article". Enter a title and see its traffic, the counterfactual and its referral mix over time.

## 7. Repo skeleton

```
wikipedia-ai-overviews/
  README.md, DATA.md, Makefile, pyproject.toml, uv.lock
  src/wao/
    ingest/pageviews_api.py, pageview_dumps.py, clickstream.py, wikidata.py, edits.py
    build/sample.py, article_features.py, quick_answer.py, panels.py
    models/staggered_did.py, within_concept.py, its.py
    viz/theme.py, figures.py
  data/reference/aio_rollout.csv (cited), quick_answer_labels.csv
  tests/          # totals vs Wikimedia aggregates, redirect handling, pinned estimates
  report/index.qmd
  app/
```

## 8. Milestones

| Week | Deliverable |
|---|---|
| 1 | Rollout table; clickstream ingest for 6+ languages; totals reconcile |
| 2 | Article sample, Wikidata types, quick-answer label with validation |
| 3 | English ITS + language-level staggered DiD; hero chart v1 |
| 4 | Within-concept design; article-type heterogeneity |
| 5 | Robustness (bot reclassification, placebos); editor analysis |
| 6 | Article + lookup app; publish |

## 9. Distribution
- Hacker News and r/wikipedia; Wikimedia's own research community (the Wikimedia Research mailing list and Wiki Research Showcase welcome outside work).
- Media and SEO newsletters care a great deal about zero-click search: Press Gazette, Nieman Lab, Search Engine Land.
- Pair with your Stack Overflow project in one "knowledge commons after AI" post.

## 10. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Rollout dates are fuzzy (gradual rollouts, A/B tests) | Use month resolution, show event studies, test ±1-month shifts |
| Bot traffic reclassification | Clickstream as main outcome; sensitivity windows |
| Languages ≠ countries | Prefer languages concentrated in one market (ja, de, pl, it); discuss en and es spillovers |
| Other shocks (TikTok, ChatGPT, Google core updates) | Event-study pre-trends; Google update dates as controls |
| Quick-answer labels are noisy | Validated rule set; report results by Wikidata type too |

## 11. Stretch goals
- Add other open traffic sources (e.g. Stack Exchange, Reddit) for a "commons index".
- Measure whether AI Overviews cite Wikipedia: run a fixed query set monthly and log the cited sources (check Google's terms of service first).
- Make it a monthly-updating tracker using the clickstream release cycle.
