# Press pitches

**Status:** drafts. Nothing is sent without John. Find the right reporter on the day: someone who has recently covered zero-click search, AI Overviews or Wikipedia traffic. Send each pitch to one person, not to a general tips address if a named reporter fits. Send on the morning of launch day or the day after, once the article is live.

Each outlet's angle differs:

| Outlet | Readers | Lead with |
|---|---|---|
| Press Gazette | UK news publishers | What a careful test on public data says about the "AI Overviews is stealing our clicks" claim |
| Nieman Lab | Journalism and media researchers | Method and caution: a natural experiment, pre-registered, and a null that isn't a clean bill of health |
| Search Engine Land | SEO practitioners | Wikipedia as the one big site with public referral data; what it shows about zero-click search |

## Press Gazette

> Subject: New analysis: Wikipedia's search traffic fell almost everywhere, but not where Google's AI Overviews arrived
>
> Hi [name],
>
> Publishers say Google's AI Overviews are taking their clicks, but almost nobody publishes the traffic data to test it. Wikipedia does. I used Wikimedia's public data for 11 language editions and the fact that Google launched AI Overviews country by country, so the editions were exposed at different times.
>
> What I found:
> - Search traffic to Wikipedia fell almost everywhere, including Russian Wikipedia, where AI Overviews never launched (66 on an index where the year before launch = 100).
> - Comparing editions with and without AI Overviews in the same month, there's no loss I can attribute to it: +2.7% in the first six months (95% interval −7% to +13%).
> - A smaller loss, about 5% for English as a separate study found, fits the data. This design can only reliably detect about 10%.
>
> The takeaway for publishers: the big falls are real, but most of them happened in editions with and without AI Overviews alike.
>
> The analysis was pre-registered, and the code and data are public: https://johnpospisil.github.io/wikipedia-ai-overviews/
>
> Happy to talk or share charts.
>
> John Pospisil

## Nieman Lab

> Subject: A natural experiment on AI Overviews and Wikipedia traffic, with a careful null
>
> Hi [name],
>
> You've covered how AI search summaries affect traffic to news and reference sites. I've finished an analysis that uses Google's country-by-country rollout of AI Overviews as a natural experiment on Wikipedia, which publishes its referral data.
>
> - Search traffic fell in almost every one of 11 language editions, including in Russian, which never got AI Overviews.
> - The pre-registered estimate of the AI Overviews effect is +2.7% (95% interval −7% to +13%) in the first six months and −8.0% to July 2026 (−28% to +10%). Neither is distinguishable from zero.
> - The interesting part for researchers is why the longer window can't be trusted: by mid-2025 only French was left as a comparison, and Wikimedia's bot-detection change hit in the same month as the German, Italian and Polish launch.
>
> I think the story is that a falling traffic line isn't evidence of what caused it, and that even with a good natural experiment, the effect of AI summaries on a site like Wikipedia is smaller than this kind of data can measure.
>
> Article, code and pre-registration: https://johnpospisil.github.io/wikipedia-ai-overviews/
>
> John Pospisil

## Search Engine Land

> Subject: Wikipedia referral data: no measurable AI Overviews loss across 11 language editions
>
> Hi [name],
>
> Wikipedia is the one very large site that publishes its search referrals, by month and language. I used them, with Google's staggered AI Overviews rollout by country, to estimate how much search traffic AI Overviews took.
>
> - Search referrals fell in almost every language edition, but just as much where AI Overviews hadn't launched yet. Russian (never launched) is at 66 on an index where the year before launch = 100.
> - The estimated AI Overviews effect is +2.7% in the first six months (95% interval −7% to +13%). The design detects about 10%. English alone is −6%, close to the 5% in Khosravi & Yoganarasimhan's working paper.
> - Quick-answer pages (birth dates, capitals, release years) lost more views than long reads, but they did so in editions without AI Overviews too. So the "AIO eats quick answers" pattern isn't specific to AIO here.
>
> Caveats your readers will care about: clickstream's "search" is every search engine, not only Google, and app traffic isn't included.
>
> Full analysis and open code: https://johnpospisil.github.io/wikipedia-ai-overviews/
>
> John Pospisil
