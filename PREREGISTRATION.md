# Pre-registration

**Project:** Did Google's AI Overviews hurt Wikipedia? (see [05-wikipedia-ai-overviews.md](05-wikipedia-ai-overviews.md))
**Written:** 2026-11-01, before any model is fitted on post-launch data. **Locked:** at the git commit that adds this file (tag `prereg-v1`).
**Rule:** after locking, this file is only appended to, under [Deviations](#11-deviations). Every result reported in the article is labelled *pre-registered* or *exploratory*.

## 0. What had been seen before writing this

- **No post-launch contrast between treated and untreated editions has been computed** (CLAUDE.md rule 6). Every model, slope and comparison across editions so far (P14, and the power simulation in section 9) uses months up to 2024-04 only.
- **Post-launch data that has been seen, all descriptive or data-quality:**
  - the English referral mix to 2026-09 (P05, P14: search 42–48% of arrivals throughout);
  - the total of all 11 core editions combined (P14). Search arrivals index from about 92 in 2024-04 to 73 in 2026-09 (2019-04..2020-03 = 100), with a step at the 2025-04 bot reclassification;
  - per-edition data-quality tables over the full period. These are clickstream/AQS ratios, AQS `user` and `automated` views 2024-09..2025-12 (P11 bot window), coverage (P07), censoring shares in 2023 vs 2026 (P13) and editor counts (P09).
- **Pre-period facts that shaped this design (P14):**
  - de, it and fr move in parallel (within ±2%/yr).
  - en, es and pt rise 7–13%/yr faster than the rest from 2022-12 to 2024-04, and ja falls 13%/yr faster.
  - ru (+8%/yr, then −8%/yr after its 2022 surge) and fa (+11 to +17%/yr) are not parallel.
  - Seasonality differs by edition.
- **Prior knowledge (public; sources to be checked and cited in P30):**
  - The Wikimedia Foundation reported in October 2025 that human pageviews were roughly 8% lower than a year earlier, after its bot-detection update.
  - Pew Research Center (2025) found that Google users who saw an AI summary clicked a result less often than users who did not.
  - So a decline in search referrals is expected. The open questions are **how much of it is caused by AI Overviews** rather than by trends shared across editions (chatbots, search changes), and **which articles and readers** it affects.

## 1. Research questions and hypotheses

| ID | Hypothesis (direction stated in advance) | Status |
|---|---|---|
| **H1** (primary) | Once AI Overviews became available to most of an edition's readers, its monthly search arrivals fell **below** those of editions not yet exposed | Confirmatory |
| H2 | Articles whose subjects are typically asked as **short-answer questions** lose **more** views than long-read articles | Confirmatory (Holm) |
| H3 | **Mobile-web** views fall **more** than desktop views | Confirmatory (Holm) |
| H4 | The effect differs between **tail** (2023 popularity deciles 1–5) and **head** (deciles 8–10) articles; two-sided, no direction predicted | Confirmatory (Holm) |
| H5a | The **search share** of arrivals falls | Confirmatory (Holm) |
| H5b | **Internal-navigation depth** (internal-link arrivals per external arrival) changes; two-sided | Confirmatory (Holm) |
| H6 | **Active registered editors** fall 6–18 months after exposure | Confirmatory (Holm) |
| E1 | Decomposition of the English decline since 2022-11 into pre-trend, ChatGPT era and AI Overviews (P25) | Exploratory |
| E2 | Per-type and per-topic quick-answer effects (P21, partially pooled) | Exploratory |
| E3 | Per-article reader depth and `other-external` growth (P23, P25) | Exploratory |
| E4 | The 29 newer clickstream editions | Exploratory |

## 2. Data, units and periods

- **Outcome source:** monthly Wikipedia clickstream (P05), `other-search` arrivals summed over all articles. This counts **all** search engines (P10: non-Google engines are at least 10% of it only in ru, ja and zh). Panels: `panels/panel_lang_month.parquet` and `panels/panel_article_month/` (P13).
- **Clickstream months:** from **2019-04** (method break, P11). 2025-04 is about 5 days short and is coded **missing** (primary). The rescaled version is a robustness check.
- **Treatment timing** (P03, `data/reference/language_cohorts.csv`):
  - The cohort is the first month with exposure ≥ 0.5. **First exposure** is the first month with any exposure.
  - The months between first exposure and the cohort month are **partly treated**. They are neither base nor post months in the ATT; they are shown in the event study.

| Edition | Cohort | First exposure | Base month (last month before first exposure) |
|---|---|---|---|
| en | 2024-09 | 2024-05 | 2024-04 |
| ja, pt | 2024-09 | 2024-08 | 2024-07 |
| es | 2024-11 | 2024-08 | 2024-07 |
| de, it, pl | 2025-04 | 2025-03 | 2025-02 |
| zh | 2025-06 | 2025-05 | 2025-03 (2025-04 is missing) |
| fr | 2026-08 | 2025-04 (dose 0.28 from 2025-06) | — (control) |

- **Comparison group (decided in P15):** the 9 editions above.
  - **ru and fa are excluded from the primary analysis:** they are not parallel before 2024-05 (P14), and ru reaches a dose of 0.46.
  - Both enter the dose–response analysis (P18), the within-concept design (P19) and a robustness check.
- **Primary window: 2019-04 to 2025-02.**
  - Treated groups: en, ja + pt, es.
  - Post months: 2024-09..2025-02 for en, ja and pt; 2024-11..2025-02 for es.
  - **Controls:** de, it, pl, zh and fr, all with **zero exposure** through 2025-02. In 2025-03, de, it and pl reach 0.20.
  - **Why this window:**
    1. It has five clean control editions. After 2025-05 only fr remains, and fr is partly exposed.
    2. It ends before the 2025 bot reclassification (applied from 2025-04, P11) and before the short 2025-04 clickstream month.
    3. Placebo launches centre on zero in this window but not in the full window (section 9).
- **Full window (pre-registered secondary estimand): 2019-04 to 2026-07.** All 8 treated editions; the window ends the month before fr is treated.
  - **Control rule:** not yet treated. fr is the only control after 2025-05, and it is partly exposed then, which biases the estimate towards zero.
  - **Contains:** the bot reclassification and the missing 2025-04.
  - **Reported with:** its placebo distribution (mean −2.8%, section 9).

## 3. Primary outcome and estimand

- **Outcome:** `Y = log(search arrivals) − s(edition, month of year)`.
  - `s` is the edition's month-of-year effect from the P14 trend model.
  - That model is a linear trend with a kink at 2022-12, 11 month dummies, COVID 2020-03..05 dummies, a fa 2019-11 dummy and an en step from 2020-05.
  - It is fitted per edition on 2019-04..2024-04 only, so seasonality is estimated without post-launch data. Code: `wao.models.power._deseason`.
- **Estimand (H1):** the Callaway–Sant'Anna ATT, aggregated by group (θ^O).
  - **Groups:** units sharing a (cohort, first exposure) pair: {en}, {ja, pt}, {es}.
  - **Group-time effect:** `ATT(g,t) = mean_{i∈g}(Y_it − Y_i,b_g) − mean_{j: E_j > t}(Y_jt − Y_j,b_g)` for t ≥ cohort month. Here `b_g` is the group's base month and `E_j` the first-exposure month: the controls are **not yet exposed**.
  - **Aggregation:** θ_g is the mean of ATT(g,t) over g's post months, and θ = Σ n_g θ_g / Σ n_g, giving weights en ¼, ja + pt ½, es ¼.
  - **Reported as** `100 × (exp θ − 1)` %.
  - Implemented in [src/wao/models/csdid.py](src/wao/models/csdid.py). With base g−1 and no exposure lead, it reproduces the `differences` package (ATTgt, not-yet-treated, universal base, cohort aggregation) exactly.
- **Smallest effect of interest (SESOI): −5%.**
  - It is above the design's own month-to-month wander in recent placebo windows (RMS 2.8%, section 9).
  - It is well below what an 8% fall in all human views would imply for search if search carried most of it.
  - A decline smaller than 5% is treated as not substantively meaningful, even if it is statistically distinguishable from zero.

## 4. Primary inference and decision rule

1. **p-value: exact randomization inference (RI).**
   - The 9 editions' (cohort, first-exposure) label pairs are permuted over all **30,240** distinct assignments; the window and missing months are kept.
   - Two-sided p = the share of assignments with |θ| ≥ |θ_observed|.
2. **95% interval:** test inversion of the same RI under a constant additive effect δ (the δ values not rejected at 5%).
3. **Reported, not deciding:**
   - Restricted wild cluster bootstrap with edition clusters, Webb six-point weights and 99,999 draws.
   - With 9 clusters, and 3–4 treated editions in the primary window, bootstrap and cluster-robust errors are unreliable. That is why RI decides.
4. **Event study:**
   - ATT(g, e) for e = −24..+5 (primary) and −24..+22 (full), relative to each group's base month.
   - Partly treated months are marked.
   - **Pre-trend test:** the mean absolute lead over the 12 months before the base, with an RI p-value; flagged if p < 0.10.
   - **Rambachan–Roth** relative-magnitude bounds for M̄ = 0.5, 1 and 2, and the breakdown M̄, using the bootstrap covariance.

### Decision rule for H1

| Result | Conclusion |
|---|---|
| θ < 0, RI p < 0.05, the full-window θ is also negative, **and** the RI interval excludes values above −5% | **H1 supported, effect at least the SESOI** |
| θ < 0, RI p < 0.05, the full-window θ is negative, but the interval includes values between −5% and 0 | **H1 supported; size uncertain or small** |
| θ < 0 and p < 0.05, but the full-window θ is ≥ 0 | **Not robust across windows**; reported as such in the main text |
| 90% RI interval lies entirely within (−5%, +5%) | **No effect as large as the SESOI** (equivalence) |
| Anything else | **Inconclusive** (the design's MDE is about 10%, section 9) |

- **Main text requirement:** if the pre-trend test flags (p < 0.10) and the M̄ = 1 Rambachan–Roth interval includes 0, the article must say that the result is **not robust to pre-trend violations of the size seen before 2024-05**.

## 5. Supporting estimators (all reported; they don't override section 4)

1. **English interrupted time series (P16).** Log monthly search arrivals and search share: trend, month-of-year dummies, a ChatGPT level and slope break at 2022-12, and a level and slope break at 2024-05. HAC errors with 6 lags. Results are yearly gaps against the counterfactual, plus a pre-period holdout error. English is only partly treated (0.21–0.48) until 2024-09.
2. **Sun–Abraham and Borusyak–Jaravel–Spiess imputation (P17)** on the same 9 editions and windows.
3. **Dose–response (P18).** Two-way fixed effects of Y on continuous exposure with edition and month FE, all 11 editions, 2019-04..2026-07, plus a binned-dose event study.
4. **Within-concept design (P19).** `log(views or search arrivals) ~ exposure + item×month FE + item×edition FE` on the 6,000-concept panel. Weighted (P06) and unweighted; wild bootstrap by edition.
5. **Consistency rule:** if any supporting estimator disagrees in sign with the primary estimate, the article says so next to the headline.

## 6. Secondary hypotheses: tests and decision rules

**Holm family.** The family is H2, H3, H4, H5a, H5b and H6. Each has one two-sided decision p-value, adjusted by **Holm's method at α = 0.05**. A hypothesis with a stated direction counts as supported only if it survives Holm **and** the estimate has the predicted sign.

- **H2: quick-answer vs long-read.** Article panel, all 11 core editions, `in_lang_sample` articles, P06 weights, 2019-04..2026-07.
  - **Model:** `log(1 + V_it) = α_i + γ_{edition×month} + q_i·δ_t + β·(q_i × x_lt) + ε`.
    - V is `user` desktop + mobile-web views (not censored).
    - q is `qa_nq_rate` (the Natural Questions short-answer rate of the article's Wikidata type, P12), standardised over sample articles.
    - x is the continuous P03 exposure.
    - q·δ_t is a separate q slope for every month, so trends shared by quick-answer pages everywhere are absorbed.
  - **Test:** β < 0 predicted. p-value from a wild cluster bootstrap by edition (11 clusters, Webb weights).
  - **Secondary, outside Holm:** the binary v4 contrast (`qa_core` 1 vs 0, ambiguous excluded), and search arrivals for deciles 8–10 with censored months taken from the P11 imputation.
- **H3: mobile vs desktop.** Edition level, the primary design and window. Outcome: `log(mobile-web views) − log(desktop views)`, deseasonalised as in section 3. θ < 0 predicted; RI p.
- **H4: head vs tail.** As H2, with q replaced by `tail_i` (1 if the 2023 decile is 1–5, 0 if 8–10; deciles 6–7 excluded).
  - Views are not censored, so the P11 truncation problem does not arise.
  - The truncation-corrected search arrivals (`qa/search_imputed.parquet`) are a secondary check, outside Holm.
  - Two-sided.
- **H5a: search share.** Edition level, the primary design. Outcome: log(search arrivals / all arrivals), deseasonalised. θ < 0 predicted; RI p.
- **H5b: depth.** Edition level, the primary design. Outcome: log(internal-link arrivals / (all arrivals − internal-link arrivals)), deseasonalised. Two-sided; RI p. Per-article depth (P23) is exploratory.
- **H6: editors.** Edition level, the full-window design (lags need it).
  - Outcome: log AQS active **registered** editors (5+ content edits, bots excluded), deseasonalised. Anonymous editors are excluded because temporary accounts redefine them from 2025-06 (P09).
  - Estimand: θ restricted to event times 6..18. θ < 0 predicted; RI p.
  - Stated in advance: H6 has the least power (section 9). Only en, ja, pt and es reach event time 18 inside the window.

## 7. Robustness checks (all pre-specified; one forest plot in P20)

1. Full window (section 2) for every edition-level hypothesis.
2. Adding ru and fa as never-treated controls (11 editions).
3. Base period g−1 (standard CS) instead of the pre-exposure base; not-yet-treated instead of not-yet-exposed controls.
4. Outcome without seasonal adjustment; year-over-year differenced outcome (`Y_t − Y_t−12`).
5. Edition-specific linear trends fitted on 2022-12..base and removed (the en/es/pt/ja run-up in P14).
6. Rambachan–Roth bounds (section 4) for every event study.
7. Placebo launches 12 months earlier; cohorts shifted ±1 month.
8. Pre-period starting 2023-07 (dropping 2022-11..2023-06, the ChatGPT launch window).
9. Leave one edition out (9 refits).
10. Core-update months (P10) dropped from post cells.
11. Outcome net of the edition's Google search share (P10). Google's share may itself respond to AI Overviews, so this reads as a lower bound.
12. Total `user` views (all access, and web only) instead of clickstream.
13. Full window: dropping 2025-03..2025-08. An edition × post-2025-04 bot-break term for editions not newly treated in 2025-04.
14. 2025-04 rescaled (by the edition's AQS ratio) instead of missing.
15. Truncation-corrected search arrivals (`search_arr_corr`, P11/P13).
16. Alternative exposure definitions for cohorts: `exposure_all_users`, `exposure_as_listed` (Iran treated as listed).
17. fa without 2026-04..05 (shutdowns) wherever fa enters.
18. **Negative controls:** ru and fa treated from their first exposure (2025-05). The expected effect is proportional to their dose (≤ 0.46 and ≤ 0.19), so a full-size effect there would point to a confound.

Any check that flips the H1 conclusion must be reported in the main text.

## 8. What would make the main finding wrong

- **The gap is not specific to exposure:** placebo launches in the pre-period give gaps as large as the real one, or the event-study leads are as large as the post effects.
- **It is driven by the en/es/pt run-up:** these editions rose faster than the rest in 2023 (P14). If that surge (largely mobile web) reverses after launch, a primary-window "effect" could be mean reversion. Robustness check 5 and the Rambachan–Roth bounds test this; so does whether ja, which was falling before launch, shows the same effect.
- **It is mediated by Google's falling search share:** the effect disappears in robustness check 11, which points to search-engine competition rather than AI Overviews (P10: Bing's share in Japan rose from 8% to 36% in 2025–26).
- **It appears in proportion to nothing:** the negative-control editions fall as much as the treated ones, or the dose–response slope (P18) is flat.
- **It is the bot reclassification:** the full-window effect appears only from 2025-04, and vanishes when 2025-03..08 is dropped or the break term is added.

## 9. Power and minimum detectable effect

- **Method:** placebo launches on pre-period data only (2019-04..2024-04), keeping the real structure.
  - Cohort offsets 0/0/0/+2/+7/+7/+7/+9 months.
  - Each edition's real exposure lead (en 4 months, ja, pt and es 1 month).
  - fr as the not-yet-treated edition.
  - The 2025-04 month missing where it applies.
  - The first placebo cohort is moved over every possible month: 51 starts in the primary window, 34 in the full window.
- **Measures:**
  - The **placebo ATT** (no true effect).
  - **Power:** a constant decline δ is injected into the treated post cells and tested by the exact RI of section 4.
  - **MDE** = the smallest decline with 80% power at two-sided 5%.
  - Neighbouring starts overlap, so there are only a few independent windows.
- **Files:** [src/wao/models/power.py](src/wao/models/power.py), `report/qa/p15_mde.csv`, `p15_placebo_att.csv`, `p15_power.csv`, [report/figures/p15_power.png](report/figures/p15_power.png).

| Outcome | Window | Placebo RMS | Rejection rate at δ = 0 | MDE (RI, 80% power) |
|---|---|---|---|---|
| **H1 search arrivals** | **primary** | 4.2% (2.8% for starts from 2021-07) | 9.8% | **−10%** |
| H1 search arrivals | full | 3.4% (mean −2.8%) | 0% | −13% |
| User web views | primary | 4.8% | 5.9% | −12% |
| H5a search share | primary | 3.3% | 2.0% | −13% |
| H3 mobile − desktop | primary | 6.3% | 5.9% | −24% |
| H5b depth | primary | 9.0% | 2.0% | −25% |
| H2 quick − long (edition-level approximation) | primary | 6.3% | 0% | −23% |
| H4 tail − head (edition-level approximation) | primary | 10.4% | 5.9% | not reached by −26% |
| H6 registered editors, e = 6..18 | full | 5.3% | 0% | not reached by −26% |

- **Primary outcome:** declines of about **10% or more** in the primary window would be detected with 80% power.
  - Effects between the 5% SESOI and 10% may be missed, and an equivalence conclusion is unlikely.
  - The largest placebo errors come from windows that contain COVID (2020-03..2021-01: RMS 6.5%).
- **The full window's placebos are biased negative (−2.8% on average):** fr drifts up against the treated editions (P14).
- **H2 and H4** are approximated here at edition level. The article-level models use far more information, but their power is not simulated here.
- **H4 and H6** are expected to be underpowered. A non-significant result there is reported as uninformative, not as evidence of no effect.

## 10. Decisions taken in P15 (delegated by the user)

1. **Comparison group:** ru and fa are excluded from the primary analysis (non-parallel pre-trends, P14; ru partial dose). They are used in the dose–response analysis, the within-concept design, robustness and negative controls.
2. **H2 measure:** the continuous `qa_nq_rate` is primary; the binary v4 core tiers are secondary (P12).
3. **Primary window ends 2025-02, not when the last control (fr) is treated.** This departs from the original plan (CLAUDE.md P15) for the reasons in section 2. The full window is pre-registered as the secondary estimand and is always reported next to it.
4. **Base period = month before first exposure** (not g−1), so en's partly exposed months 2024-05..08 do not contaminate its baseline.
5. **SESOI = −5%.**

## 11. Deviations

*(Append dated entries here. Each entry: what changed, why, and whether it was decided before or after seeing post-launch contrasts.)*

### 2026-11-01: English ITS nuisance terms and sensitivity specifications (clarification and addition)

- **Clarification:** the section 5.1 ITS (spec A) also includes the nuisance terms of the P14 trend model: COVID dummies for 2020-03..05 and an English clickstream step from 2020-05 (automated class introduced, `data_breaks.csv`). 2025-04 is missing, as in section 2.
- **Addition (sensitivity, labelled exploratory):** B, no ChatGPT slope change (one trend 2019-04..2024-04 extrapolated); C, A plus a step from 2025-04 (bot reclassification); D, the AIO level and slope replaced by the continuous P03 exposure; E, 2025-04 rescaled instead of missing. Period gaps are mean(actual) − mean(counterfactual), with SEs that include the trend-extrapolation uncertainty (HAC, 6 lags).
- **When:** written into the code **before the ITS was first fitted**. No post-launch English model had been run.

### 2026-11-01: How P17 implements the section 4 inference (clarification)

- **RI:** the 30,240 permutations of the label pairs are computed as specified. In the primary window, de, it, pl, zh and fr are all unexposed, so they map to **1,512 distinct assignments** (each 20 times). The p-value is identical either way. Sun–Abraham and Borusyak–Jaravel–Spiess, which need one regression per assignment, use the true assignment plus 3,000 random others.
- **Bootstrap:** the "wild cluster bootstrap" is implemented as the Callaway–Sant'Anna multiplier bootstrap on the per-edition influence functions (Webb six-point weights, 99,999 draws). It is degenerate (SE 0) for a cell with one treated and one control edition (zh in the full window), which is one more reason it doesn't decide.
- **Rambachan–Roth:** the identified-set version. The largest month-to-month change in the 12 leads before the base (point estimates) bounds each post-period step at M̄ times that, and the 95% RI interval is widened by the implied worst-case average bias. It is not the conditional/hybrid confidence set.
- **When:** all three were written into the code **before the first P17 run**. The per-edition breakdown (`p17_by_edition.csv`, exploratory) was added **after seeing the results**.

### 2026-11-01: P18 dose-response: own wild bootstrap and a no-fa specification (clarification and addition)

- **Clarification:** the pyfixest/wildboottest wild cluster bootstrap fails on this panel (a numba typing error), so the restricted wild cluster bootstrap (WCR, Webb weights, 9,999 draws, editions as clusters, CRV1 t-statistic, 95% interval by test inversion) is implemented directly in `wao.models.dose`. The panel is balanced (2025-04 dropped for every edition), so the two-way FE are removed by demeaning. Randomization inference permutes whole exposure paths across editions (9,999 draws). Decided **before** any P18 estimate was seen.
- **Addition (exploratory):** TWFE without fa. fa's search arrivals fall 30–40% from 2025-05 and up to 96% in 2026-03..05 (most likely connectivity restrictions in Iran) while its exposure is only 0.07–0.19, so in the 11-edition TWFE it acts as a low-dose comparison hit by an unrelated shock. Decided **after seeing** the pre-registered 11-edition estimate and the TWFE weights. The pre-registered estimate is still reported first.

### 2026-11-01: P19 within-concept specification details (clarification and addition)

- **Clarification:** the section 5.4 model also has **edition × month-of-year FE** (edition-specific seasonality, P14; agreed after P14) and drops 2025-04 for every edition, as in P18. Outcomes: `log(1 + user web views)`, and `log(1 + search arrivals)` with censored (<10) months set to the P11 imputed value; a second search version keeps only concept-editions never censored in 2023 (selected on the pre-period). Weighted = the P06 concept weights. Inference: the restricted wild cluster bootstrap of P18, computed in closed form on the FWL-demeaned data, and RI permuting whole exposure paths across editions (999 draws, main specifications only).
- **Addition (exploratory):** the specification without fa (P18) and P17's 9 editions, both labelled exploratory, plus a descriptive month-by-month within-concept gap (treated editions vs fr + ru).
- **When:** written into the code **before** any P19 estimate was seen, and after the P18 results.

### 2026-11-01: How P20 implements section 7 (clarification)

- **Placebo 12 months earlier:** cohort and first-exposure dates moved back 12 months, with the window capped at 2024-04 so that no real post-launch month enters a placebo post cell.
- **Edition × post-2025-04 bot step:** for every edition not newly treated in 2025-04 (all but de, it and pl), the step is the mean of 2025-05..07 minus the mean of 2025-01..03 (deseasonalised) and is subtracted from 2025-04 onward. This also removes any genuine change in those months, so it is conservative.
- **Core-update months:** core-update months from 2024-05 on are set missing, except the groups' base months.
- **Edition trends:** a linear trend per edition, fitted on 2022-12..2024-04, is removed from all months.
- **RI:** exact for up to 9 editions; with ru and fa added (11 editions), 5,000 random permutations. For the negative controls (2–3 editions) the RI interval is uninformative, and only the point estimate is read.
- **"exposure all users" in the primary window:** not estimable, because no edition reaches 0.5 all-user exposure before 2025-03.
- **When:** all decided **before** the full P20 run. Only the two P17 baselines had been reproduced.

### 2026-11-01: P21 (H2) implementation details (clarification and addition)

- **Clarification:** q is standardised over sample articles with P06 weights. The q × month slopes are 87 columns (one month dropped, absorbed by the article FE), partialled out by FWL in batches. On a 3,000-article subsample this reproduces pyfixest's `views ~ qx + i(month, q) | article + edition^month` exactly.
- **Secondary (as pre-registered):** the binary v4 contrast uses qa_core × month FE in place of slopes. The search-arrival version keeps 2023 deciles 8–10 and usable clickstream months without 2025-04.
- **Addition (robustness):** coarse type × month FE in place of the q slopes. q is a function of the coarse type (22 values), so this nests the pre-registered slopes.
- **Exploratory:** without fa (as in P18 and P19). Per-type and per-topic effects relative to `human` and `Geography` (E2) are partially pooled by **empirical-Bayes normal shrinkage** of the CRV1 estimates instead of bambi, because a Bayesian model on 10.9 M rows is impractical. Chart 2 compares 2023-08..2024-07 with 2025-08..2026-07.
- **When:** all decided **before** any P21 estimate was seen.

### 2026-11-01: Base-10 logs in P19 and P21 corrected (error fix, found after seeing results)

- **What:** DuckDB's `log()` is base 10. The P19 and P21 outcomes were built with it (`log(1 + views)`, `log(1 + search)`), so every coefficient and interval was too small by a factor of ln 10 ≈ 2.30. The p-values are unaffected (t-statistics and RI are invariant to rescaling the outcome). Both modules now use `ln()`, both were re-run in full, and a test (`tests/test_sql_logs.py`) blocks base-10 logs in SQL. All other models take logs in numpy and were not affected.
- **Effect on P19:** the corrected estimates are about 2.3 times larger (e.g. search without fa: −10.0%, not −4.5%). They agree with P17–P18 rather than being smaller, and the P19 conclusion in CLAUDE.md has been corrected.
- **When:** found during P21, after both P19 and P21 results had been seen. Nothing about the specifications changed.

### 2026-11-02: P22 (H3, H4) implementation details (clarification and addition)

- **H3:** the P17 estimator (primary window, exact RI) on log(mobile-web views) − log(desktop views), deseasonalised like section 3. The full window and each access type alone (desktop, mobile web, app) are reported alongside. The full window is the section 7 item-1 check, not the H3 decision.
- **H4:** the P21 batched estimator with q = tail indicator (2023 deciles 1–5 = 1, 8–10 = 0, 6–7 excluded), so the q × month slopes become tail × month effects. The secondary search version uses the P11 imputation for censored months.
- **Exploratory:** without fa, and the exposure effect by 2023 decile relative to decile 10 (CRV1 by edition).
- **When:** all decided **before** any P22 estimate was seen.

### 2026-11-02: P23 (H5a, H5b) implementation details (clarification and addition)

- **H5a and H5b:** the P17 estimator (primary window, exact RI; full window alongside), with the 2025-04 short month missing as for search arrivals. H5b's denominator is all arrivals minus internal-link arrivals ("external entries").
- **Exploratory (E3, selection):** at article level, 2023 deciles 8–10 and usable clickstream months: log((outgoing internal clicks + 1) / (published arrivals + 1)) on (article's standardised 2023 search share) × exposure, with article FE, edition × month FE and a share × month slope. This is the P21 batched estimator with a WCB by edition, run with and without fa. Chart 3 pools the 8 treated editions and shows fr beside them.
- **When:** decided **before** any P23 estimate was seen.
