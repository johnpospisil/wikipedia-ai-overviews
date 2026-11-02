# Analysis validation (P29)

An independent review of P03–P27 before the article is written (2026-11-02). It covers identification, post-period leakage, few-cluster inference, truncation and bot artefacts, the Holm family, and whether each claim made so far is backed by an estimate. Every number below is read from `report/qa/` or recomputed from the panels. Nothing was changed in the analysis itself. The one fix applied is a chart title (C5).

**Verdict.** The project's conclusions hold: H1 is inconclusive, and none of H2–H6 is supported after Holm. Nothing found here would turn a null into a finding or the other way round. The risk is in the telling. The full-window −8% and the large descriptive declines are easy to read as AI Overviews effects, and the evidence does not support that reading. P30 has to carry the caveats in A1–A3 and B1–B4 next to the numbers they qualify.

## A. High: bear on how the headline is read

### A1. The de/it/pl launch month is also the bot-reclassification month

- AI Overviews reached Germany, Italy and Poland on 2025-03-25, so the de, it and pl cohort is 2025-04. Four other things also happened that month or just before:
  - Wikimedia's bot-detection change, a level break in `user` traffic in both pageviews and clickstream from 2025-04 onward (P11).
  - The short 2025-04 clickstream file, missing about 5 days.
  - The March 2025 core update (03-13..26).
  - AI Mode in Search Labs in the US (03-05).
- The reclassification moved different amounts of traffic in each edition. The share of `automated` views rose from Jan–Mar 2025 to May–Jul 2025 by:
  - de +3 pp, it +5 pp, pl +7 pp
  - en +10 pp, es +5 pp, pt +20 pp, zh +12 pp
  - fr: fell by 12 pp
  - (recomputed from `p11_bot_window.csv`)
- For de, it and pl, the AI Overviews effect and the bot break start in the same month, so the data cannot separate them. The P20 bot-step variant removes the break from every *other* edition and gives −1.3% in the full window (RI 95% −12% to +17%), against −8.0% for the baseline. de, it and pl keep their own break either way.
- **Consequence:** the full-window −8% is an upper bound on the AI Overviews effect, with a bot artefact of unknown size included. The primary window ends 2025-02 and is not affected.
- **Action (P30):** say this wherever the full-window number appears.

### A2. After 2025-06 the full window compares everything with French alone

- From 2025-06, when zh is treated, fr is the only not-yet-treated edition. In the event study, everything after about a year rests on fr.
- fr has its own problems:
  - A no-referrer surge in 2022-07..2023-08 (`data_breaks.csv`).
  - A bot trajectory opposite to every other edition (A1).
  - The ru-vs-fr negative control gives −14%, against about −4% expected from ru's dose, which suggests fr drifts *up*.
- Leaving fr out moves the full window from −8.0% to +0.2%.
- **Action (P30):** describe the full window as "the treated editions against French", never as "against untreated editions".

### A3. The primary window is biased upward by the 2023 surge

- The pre-registered 12-months-earlier placebo gives +6.3% (RI p 0.048) in the primary window, so en/es/pt's 2023 rise (P14) carries into the primary estimate.
- Rough bias-corrected value: +2.7% − 6.3% ≈ −4%. That is close to the −5% SESOI, but the interval is wide (−7% to +13% before correction).
- Rambachan–Roth M̄ = 1 includes 0, but the pre-trend test did not flag (p ≥ 0.10). The §4 main-text requirement is therefore *not* triggered.
- **Action (P30):** report the placebo next to the primary estimate. Say that a decline of about 4–5% is consistent with the data, but the design cannot confirm or rule out one of that size (the MDE is about 10%).

## B. Medium: inference and claims

### B1. The bootstrap is far too confident with 9 clusters; only RI should be read

- In the full window, the multiplier-bootstrap SE (0.029) implies t ≈ −2.9 for −8.0%. The exact RI p is 0.40, and its interval runs from −28% to +10%.
- P19 has the same split: WCB p 0.057 vs RI p 0.30.
- The pre-registration let RI decide, and that turns out to matter.
- **Action (P30):** quote RI intervals for every edition-level claim. Where only a WCB exists (H2, H4, P18, P19), say that it overstates precision with 9–11 clusters.

### B2. The §5.5 consistency rule is triggered

- The primary estimate is positive (+2.7%). Several supporting estimators come out negative:
  - Borusyak–Jaravel–Spiess −3.8% (primary window)
  - P19 within-concept −2.7% (pre-registered)
  - P16 ITS −36%
- P18 (pre-registered) is +6%, the same sign as the primary.
- **Action (P30):** state the sign disagreement next to the headline, as §5.5 requires.

### B3. H3's full-window −13% (RI p 0.008) is the only nominally significant hypothesis result

- It is not the decision test. The primary-window test gives −2.7% (p 0.52) and sits outside the Holm family by design (Deviations 2026-11-02).
- It falls in the window affected by A1 and A2. Desktop rises (+8.9%) while mobile web falls (−5.3%), and the bot change could plausibly hit the two access types differently.
- **Action (P30):** if mentioned, label it secondary and confounded. It must not appear in a headline or a social post.

### B4. Large declines hit all traffic, not search specifically

- Latest 12 months against Aug 2023–Jul 2024 (seasonally adjusted search arrivals):
  - es 56, pt 66, zh 70, ru 66 (never treated), fr 84, ja 96
- es is a clear case:
  - Web views fell about 40% from 2023 to 2026, and search arrivals 44%.
  - The search share stayed at 63–67% throughout.
  - The pt and es falls come in early 2025, during Wikimedia's reclassification of evasive bots (mostly Brazil).
- When every referrer falls together, the cause is unlikely to be specific to search. Candidates are bot reclassification (not retroactive, P11), undetected automated traffic in the base period, and general readership trends.
- **Action (P30):** keep descriptive levels (charts 3 and 4, P25) clearly separate from causal estimates. Do not write "Spanish Wikipedia lost 44% of its search traffic to AI".

### B5. P25's attribution share is uninformative

- "51% of the pooled decline" has an RI range of −80% to 183%. The en decomposition's "edition-specific +21.8%" is a residual, not a component anyone estimated.
- **Action (P30):** quote the share only with its range, or not at all.

### C5. Chart 4 title was wrong (fixed)

- The old title, "including where AI Overviews never launched", referred to French, but fr is treated from 2026-07, inside the chart's latest 12 months.
- New title: "Search traffic fell almost everywhere, including in Russian, where AI Overviews never launched" (`src/wao/viz/figures.py`; figure and `p27_takeaways.csv` regenerated).

## C. Low

- **C1. Topics use 2026 outlinks.** Lift Wing reads current links, a post-period property. It only affects the exploratory P21 topic split.
- **C2. Survivorship.** The frame comes from the 2026-10 page table. Pages deleted since 2023 hold 0.8–1.9% of 2023 views, mostly junk titles (P06). There is no sign this is related to treatment.
- **C3. Descriptive bases include partly treated English months.** "Aug 2023–Jul 2024 = 100" includes en's US-only months 2024-05..07 (dose 0.21–0.48), which slightly understates en's decline in charts 3 and 4. The causal estimates use the month before first exposure as the base.
- **C4. RI intervals assume a constant effect.** The intervals come from test inversion under a constant additive effect, while per-edition effects range from ja +20% to zh −19% in the full window. Read the interval as a range of constant effects compatible with the data.
- **C6. Japanese exposure may be overstated late in the window.** StatCounter's Bing share in Japan rises from 8% to 36% from 2025-10 (possibly a tracker artefact). Exposure uses the pre-period Google share, so ja's dose would be overstated late in the window, which biases towards zero. ja is the positive outlier (+15% / +20%).
- **C7. Every cohort month coincides with a Google core update** (Aug 2024, Nov 2024, Mar 2025, Jun 2025). Month fixed effects absorb any common effect. Dropping the post-period core-update months changes little: primary +3.5%, full −6.3% (P20).

## D. Checks that passed

| Check | Result |
|---|---|
| Exposure uses only pre-period inputs | Country shares 2023-10..2024-04 and Google share over the same months, fixed (`build/exposure.py`). Treatment cannot feed back into exposure. |
| Sample and strata chosen before the outcome | Frame and deciles from 2023 `user` views (P06). The H4 tail is defined by 2023 decile, which guards against regression to the mean. |
| Quick-answer label is external | Natural Questions query rates by Wikidata type (P12). No Wikipedia traffic enters it. |
| Seasonality from the pre-period only | `did.seasonal` fits month-of-year terms on 2019-04..2024-04. |
| Logs | Natural logs throughout the models and panels. The P19/P21 base-10 bug has not recurred anywhere. |
| RI exactly as pre-registered | 30,240 permutations, which give 1,512 distinct assignments in the primary window (documented in Deviations 2026-11-01). The p-value includes the observed assignment. |
| Bootstrap weights | Webb six-point (`did.webb`), as pre-registered. |
| Holm | Recomputed with statsmodels: every adjusted p = 1.0. The step-down thresholds in `holm.csv` are correct, the smallest family p is 0.42, and the decision p-values match §6 and Deviations. |
| Truncation | H4 uses uncensored views. Its truncation-corrected search version (+9%, p 0.38) agrees. No raw-clickstream decile result is reported. |
| Pre-trend test | Not flagged. The §4 main-text requirement is not triggered (A3). |
| Reproducibility | `make models figures` reproduces every committed estimate exactly (P28). Pinned tests are in CI. |
| Claims in CLAUDE.md results and figure takeaways | Spot-checked against `p17_att`, `p18_twfe`, `p19_estimates`, `p20_robustness`, `p21_h2`, `p22_h3/h4`, `p23_h5`, `p24_h6`, `p25_aio_share` and `holm`: all match. The one wrong claim was chart 4's title (C5). |

## E. Proposed edits for P30 (not yet applied to CLAUDE.md)

1. Next to the headline: primary +2.7% (RI 95% −7% to +13%, p 0.58), its placebo +6.3%, and the §5.5 sign disagreement (A3, B2).
2. The full window as "treated editions vs French", an upper bound because of the coincident bot break (A1, A2).
3. RI intervals only for edition-level claims (B1).
4. A "levels are not effects" paragraph for the descriptive declines (B4, B5).
5. H3's full-window result only as secondary and confounded (B3).
