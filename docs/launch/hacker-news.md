# Hacker News

**Status:** draft. Nothing is posted without John.
**When:** a weekday, 8–10 am US Eastern. Post the link, then the first comment right away.
**Link:** https://johnpospisil.github.io/wikipedia-ai-overviews/

## Title (pick one; HN allows 80 characters)

1. **Did Google's AI Overviews take Wikipedia's search traffic? A pre-registered look** (recommended: the question is the story, and "pre-registered" signals the answer isn't spin)
2. Wikipedia search fell almost everywhere, even where AI Overviews never launched
3. Google's AI Overviews and Wikipedia: no measurable loss in 11 language editions

Avoid "AI is killing Wikipedia" or "AI Overviews didn't hurt Wikipedia". The first is what the data *don't* show; the second overstates a null that can't rule out a loss of about 5%.

## First comment

> Author here. Wikimedia said in October 2025 that human pageviews were down about 8% year on year and named AI search summaries as one cause. I wanted to know how much of that can actually be pinned on Google's AI Overviews.
>
> The useful fact is that Google launched AI Overviews country by country: the US in May 2024, then waves through 2025, France only in July 2026, Russia never. So Wikipedia's language editions were "treated" at different times. For each edition and month I built an exposure measure, the share of its readers in countries where AI Overviews was live, weighted by Google's search share there. Then I ran a staggered difference-in-differences on monthly search arrivals from Wikimedia's public clickstream data. With only nine editions, the p-values come from randomization inference (shuffling launch dates across editions) rather than standard errors.
>
> Results:
> - Search traffic fell almost everywhere. Indexed to the year before AI Overviews, the treated editions are at 56–96, and Russian, which never had it, is at 66.
> - Against editions that didn't have it yet, the effect is +2.7% in the first six months (95% interval −7% to +13%) and −8.0% to July 2026 (−28% to +10%). The second one rests on French alone as the comparison and overlaps Wikimedia's 2025 bot-reclassification break, so I read it as an upper bound.
> - The design can reliably detect a loss of about 10%. English alone comes out at −6%, close to the 5% that Khosravi & Yoganarasimhan (arXiv 2602.18455) found for English against German and French. So a small effect is plausible; this design just can't confirm it.
> - None of the "who lost" predictions held up: quick-answer pages (they lost more, but also where AI Overviews hardly reached), mobile, the long tail, the referral mix, editors.
>
> Everything was pre-registered before any post-launch comparison. The article lists every choice I made after seeing results, and an independent-review pass (validation.md) lists the weaknesses, starting with the bot-reclassification problem.
>
> Code (runs on a synthetic sample with a planted effect in about 2 minutes), pre-registration, data card: https://github.com/johnpospisil/wikipedia-ai-overviews. Happy to answer questions.
