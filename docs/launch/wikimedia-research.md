# Wikimedia Research: wiki-research-l and the Research Showcase

**Status:** drafts. Nothing is sent without John.

## Optional: an advance note to Wikimedia Research (a few days before launch)

The analysis leans on Wikimedia's 2025 bot reclassification and its traffic statement, so it's worth giving the Foundation's research and data teams a short heads-up and a chance to flag mistakes. Send it to a contact on the Research team (see https://research.wikimedia.org/team.html) rather than to the list.

> Subject: Heads-up: a pre-registered analysis of AI Overviews and Wikipedia search traffic
>
> Hello,
>
> I've finished an analysis of whether Google's AI Overviews reduced search traffic to Wikipedia, using the staggered country rollout across 11 language editions and the public clickstream and pageview data. I plan to publish it on [date] and wanted to share it with you first, in case anything misreads Wikimedia's data. The 2025 bot-detection change matters a lot for the result.
>
> In short: search arrivals fell in almost every edition, including Russian, which never had AI Overviews. Against editions that didn't have it yet, the effect is +2.7% in the first six months (95% interval −7% to +13%) and −8.0% to July 2026 (−28% to +10%). The longer window is confounded by the April 2025 reclassification, which coincides with the German, Italian and Polish launch.
>
> Draft article: [link]. Code and pre-registration: [link]. I'd be grateful for any corrections, especially on whether clickstream uses the same `user` filter as pageviews after 2025-04.
>
> Thanks,
> John Pospisil

## wiki-research-l post (launch day or the day after)

**To:** wiki-research-l@lists.wikimedia.org (post from a subscribed address).

> Subject: [Research] Did Google's AI Overviews reduce search traffic to Wikipedia? A staggered DiD across 11 editions
>
> Hello all,
>
> I'd like to share an analysis that may interest the list: https://johnpospisil.github.io/wikipedia-ai-overviews/
>
> Google launched AI Overviews country by country (US 2024-05; most of Europe 2025-03; France 2026-07; Russia never). I translated that into an exposure measure per language edition and month: the share of the edition's readers in countries where AI Overviews was live, weighted by Google's search share, using pre-launch country shares. I then estimated a Callaway–Sant'Anna staggered DiD on monthly clickstream search arrivals for 9 editions, with exact randomization inference over launch-date assignments. The hypotheses and decision rules were pre-registered.
>
> Main results:
> - Search arrivals fell in almost every edition, including Russian (never treated). Indexed to the year before AI Overviews, the treated editions are at 56–96, Russian at 66.
> - The AI Overviews effect is not distinguishable from zero: +2.7% in the first six months (95% interval −7% to +13%), −8.0% to July 2026 (−28% to +10%). The minimum detectable effect is about 10%. English alone is −6%, in line with Khosravi & Yoganarasimhan's ~5%.
> - No support for the secondary hypotheses (quick-answer pages, mobile vs desktop, head vs tail, referral mix, editors) after Holm correction.
>
> Data issues others may run into: the 2019-04 clickstream method change; the 2025-04 clickstream file being about 5 days short; the 2025 bot reclassification as a level break in both pageviews and clickstream, of different size per edition; and the <10 truncation, which makes article-level long-tail declines look much larger than they are. They're documented in `data/reference/data_breaks.csv`.
>
> The edition and article panels (197,453 sampled articles, monthly, 2016–2026) are released on Hugging Face: https://huggingface.co/datasets/audiofreak7/wikipedia-ai-overviews-panels-2026-09. Code: https://github.com/johnpospisil/wikipedia-ai-overviews
>
> Comments and corrections are very welcome.
>
> John Pospisil

## Research Showcase pitch

The monthly Wikimedia Research Showcase (https://www.mediawiki.org/wiki/Wikimedia_Research/Showcase) features external work on Wikimedia projects. **The page said the showcases were paused from April 2026 when checked on 2026-11-02.** Check whether it has resumed. If it hasn't, send this as a "for when it resumes" note, or skip it. The page doesn't say how to propose a talk, so go through the Research team contact, a week or more after launch, once there's been some response.

> Subject: Research Showcase proposal: AI search summaries and Wikipedia traffic across language editions
>
> Hello,
>
> I'd like to propose a talk for a future Research Showcase, perhaps alongside other work on generative AI and Wikipedia readership.
>
> **Title:** Did Google's AI Overviews take Wikipedia's search traffic? Evidence from the staggered rollout across language editions
>
> **Summary:** Google launched AI Overviews country by country, so Wikipedia's language editions were exposed at different times. Using public clickstream and pageview data for 11 editions (2019–2026), a pre-registered staggered difference-in-differences finds search traffic falling almost everywhere, including in never-exposed Russian, but no loss attributable to AI Overviews: +2.7% in the first six months, with a minimum detectable effect of about 10%. The talk would cover the exposure measure, what the 2025 bot reclassification and clickstream truncation do to this kind of analysis, and what the data can and can't say about AI and Wikipedia's readers.
>
> **Materials:** article, code and pre-registration at https://github.com/johnpospisil/wikipedia-ai-overviews; panels at https://huggingface.co/datasets/audiofreak7/wikipedia-ai-overviews-panels-2026-09
>
> Thanks for considering it,
> John Pospisil
