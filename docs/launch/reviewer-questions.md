# Questions reviewers are likely to ask

Short answers for comment threads, each with where the evidence is. Numbers match the article (`report/qa`).

**1. "Wikimedia itself said traffic fell 8% because of AI. Why do you say no effect?"**
I don't say no effect. I say no loss can be *attributed to AI Overviews* with this design. The fall Wikimedia reported is real and shows up here too: search arrivals fell in almost every edition. But it fell about as much in editions that didn't have AI Overviews yet, and in Russian, which never got it. Wikimedia named AI search summaries as one cause among several (social video too) and did not test it. (Article: "Search fell almost everywhere".)

**2. "Khosravi & Yoganarasimhan found AI Overviews cut English search traffic 5%. Doesn't that contradict you?"**
No. English alone comes out at −6% here, close to their 5%. Their design compares the same articles in English, German and French up to December 2024. This one pools nine editions and two years. The pooled estimate can only reliably detect about 10%, so a 5% effect is consistent with both. (Article: "English, and the other study".)

**3. "Your −8% and −13% estimates point to a loss. Why not call it?"**
Because the randomization-inference intervals cross zero (−28% to +10% for the full window), and because those longer-run estimates share two problems. After June 2025 the only comparison edition is French. And Wikimedia's bot reclassification began in April 2025, the same month German, Italian and Polish were treated. Leaving French out moves −8% to +0.2%; removing the bot break from the other editions gives −1.2%. (Article: "The headline", point 3; validation.md A1–A2.)

**4. "Nine clusters is far too few for inference."**
Agreed for standard errors, which is why they don't decide anything here. The p-values and intervals come from exact randomization inference: the analysis is re-run under every possible assignment of the launch dates to the nine editions (30,240), and the real result is compared with all of them. The bootstrap would have called the full-window −8% significant; randomization inference gives p = 0.40. (Methods appendix; PREREGISTRATION.md §4.)

**5. "Clickstream's 'search' includes Bing, Yandex and others, not just Google."**
Yes. That dilutes any Google-specific effect, most in Russian (Yandex), Japanese (Yahoo! JAPAN) and Chinese. The exposure measure weights each country by Google's pre-launch share to account for it, and a robustness variant controls for Google's share over time. (DATA.md §17; P20.)

**6. "Clickstream misses the Wikipedia apps."**
It does: it covers desktop and mobile web. App views are in the pageview data, and the robustness check that uses total pageviews, apps included, gives +0.1% over the full window (p = 0.98).

**7. "What about ChatGPT and other chatbots?"**
They launched everywhere at about the same time, so a comparison across editions can't isolate them; their effect is in the decline common to all editions. Chatbot referrals land in clickstream's "other websites" bucket, which fell from 1.1% to 0.7% of English arrivals, so chatbots aren't sending many readers on. That says nothing about readers who stop at the chatbot's answer. (Article: "Chatbots don't show up in the data".)

**8. "Languages aren't countries. Spanish readers are spread over 20 countries."**
That's what the exposure measure handles: each edition's readers are split by country using Wikimedia's pageviews-by-country data from before the launch, and each country gets its own launch date. An edition counts as treated when exposure reaches one half. The dose–response design uses the continuous measure instead. (P03; DATA.md §10.)

**9. "Isn't six months too short?"**
The primary window ends when the last not-yet-treated control edition is treated, so a longer clean window doesn't exist. The full window to July 2026 is reported next to it, with its caveats.

**10. "The 2025 bot cleanup could make everything look like a decline."**
Yes, and it was not applied to earlier months, so 2025–26 traffic is compared with a base period that still includes some bots. Its size differs by edition (the share of views reclassified as automated rose by 1 to 20 percentage points). That's why the full-window estimates are read as upper bounds, and why the large descriptive falls aren't treated as effects. (validation.md A1, B4.)

**11. "Spanish search traffic is down 44%. How is that not AI?"**
Spanish *all* views fell 37% over the same period, and search's share of arrivals only moved from 68% to 63%. When every way of reaching Wikipedia falls together, the cause isn't specific to search. The steepest part of the fall comes in early 2025, during the bot reclassification. (Article: "These levels are not effects".)

**12. "How did you decide which pages are 'quick answer'?"**
Hand labels turned out to be unreliable (agreement between two raters was poor). So the label comes from Google's own Natural Questions dataset: for each Wikidata type of article, the share of real Google queries about it that have a short answer. Quick-answer pages did lose more views than long reads, but by a similar margin in editions without AI Overviews. (P12; article: "Quick-answer pages".)

**13. "Long-tail articles must have lost the most."**
Clickstream can't show that: it drops page–referrer pairs with fewer than 10 visits a month, which makes long-tail declines look much larger than they are. Using pageviews, which have no threshold, the tail did 15% better than popular articles, if anything (not significant). (P11, P22.)

**14. "Pre-registered, but did you change things after seeing the data?"**
Some things, and each is logged with its date and whether it came before or after seeing results. The largest: the English time series (pre-registered −36%) extends the 2023 English surge forward and isn't credible, so it's reported but not leaned on. A base-10 log bug in two models was found and fixed after results were seen. (PREREGISTRATION.md §11.)

**15. "So is Wikipedia fine?"**
This measures visits, not readers' welfare or Wikipedia's health. Lost clicks may cost Wikipedia donors and future editors even if readers get the right answer elsewhere. What it shows is narrower: the big falls in search traffic since 2024 aren't mainly the work of Google's AI Overviews, as far as this data can tell.
