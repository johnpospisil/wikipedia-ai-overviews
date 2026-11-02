# LinkedIn, Bluesky and X

**Status:** drafts. Nothing is posted without John.
**When:** Bluesky and X the same day as Hacker News; LinkedIn on a weekday morning. Attach the hero chart (`report/figures/hero_estimates.png`) to LinkedIn and to post 1 of each thread, and the small multiples (`report/figures/chart4_editions.png`) to post 2.

## LinkedIn (one post)

> Did Google's AI Overviews take Wikipedia's search traffic?
>
> Wikimedia said in 2025 that human pageviews were down about 8% and named AI search summaries as one cause. Google launched AI Overviews country by country, so Wikipedia's language editions got it at different times: a natural experiment. I used Wikimedia's public data for 11 editions to test it.
>
> What I found:
> • Search traffic fell almost everywhere, including Russian Wikipedia, which never had AI Overviews.
> • Comparing editions with and without it in the same month, there's no loss I can attribute to AI Overviews: +2.7% in the first six months (95% interval −7% to +13%).
> • The design can detect a loss of about 10%. A smaller one, like the 5% another study found for English, fits the data but can't be confirmed.
>
> The analysis was pre-registered, the code is open, and the article lists everything that weakens it.
>
> https://johnpospisil.github.io/wikipedia-ai-overviews/
>
> #DataScience #CausalInference #Wikipedia #SEO #AI

## Bluesky thread (each post 300 characters or fewer; `tests/test_launch.py` checks)

1/ Did Google's AI Overviews take Wikipedia's search traffic? Google launched them country by country, so Wikipedia's language editions got them at different times. I compared 11 editions. Short answer: no loss that can be pinned on AI Overviews. 🧵

2/ Search traffic fell almost everywhere. Indexed to the year before AI Overviews, the treated editions are at 56–96. Russian Wikipedia, where AI Overviews never launched, is at 66.

3/ Against editions that didn't have it yet: +2.7% in the first six months (95% interval −7% to +13%), −8.0% to July 2026 (−28% to +10%). The longer window rests on French alone and overlaps Wikimedia's 2025 bot reclassification.

4/ That's not a clean bill of health. The design can detect about a 10% loss. English alone is −6%, close to the 5% another study (Khosravi & Yoganarasimhan) found for English. A small effect is plausible; this data can't confirm it.

5/ The predicted losers didn't lose more. Quick-answer pages fell more than long reads, but also where AI Overviews hardly reached. Mobile, the long tail and editors show nothing either. Everything was pre-registered.

6/ Article, code, pre-registration and data: https://johnpospisil.github.io/wikipedia-ai-overviews/

## X thread (each post 280 characters or fewer; `tests/test_launch.py` checks)

The link goes in the last post, because X shows posts with links less widely.

X1/ Did Google's AI Overviews take Wikipedia's search traffic? Google launched them country by country, so Wikipedia's editions got them at different times. I compared 11 editions. Short answer: no loss that can be pinned on AI Overviews. 🧵

X2/ Search traffic fell almost everywhere: the treated editions are at 56–96 on an index where the year before AI Overviews = 100. Russian Wikipedia, where AI Overviews never launched, is at 66.

X3/ Against editions without it yet: +2.7% in the first six months (95% interval −7% to +13%), −8.0% to July 2026 (−28% to +10%). The longer window rests on French alone.

X4/ Not a clean bill of health: the design detects about a 10% loss. English alone is −6%, close to the 5% another study found. A small effect is plausible but unconfirmed.

X5/ Quick-answer pages fell more than long reads, but also where AI Overviews hardly reached. Mobile, the long tail and editors show nothing either. All pre-registered.

X6/ Article, code, pre-registration and data: https://johnpospisil.github.io/wikipedia-ai-overviews/
