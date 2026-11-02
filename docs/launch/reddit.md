# Reddit

**Status:** drafts. Nothing is posted without John. Check each subreddit's rules on the day. Both limit self-promotion, so post from an account with other activity, and don't cross-post on the same day.

## r/dataisbeautiful

**Post type:** image, the small multiples: `report/figures/chart4_editions.png`. The sub requires `[OC]` in the title and a top-level comment with the source and tools within an hour.
**When:** a weekday morning, US time, a day or two after Hacker News.

**Title:**
> [OC] Search traffic to 11 Wikipedia language editions, 2021–2026, and when Google's AI Overviews arrived

**Required comment:**
> **Source:** Wikimedia clickstream and pageview dumps (CC0), 2019–2026; AI Overviews launch dates from Google's announcements and archived copies of its help page.
> **Tools:** Python (DuckDB, pandas, statsmodels), matplotlib.
>
> Each panel is one Wikipedia language edition's monthly arrivals from search engines, seasonally adjusted and indexed to Aug 2023–Jul 2024 = 100. The shading starts when AI Overviews reached at least half of that edition's readers. The thin blue line is French, which only got AI Overviews in July 2026, for reference.
>
> Search fell almost everywhere: the treated editions are at 56–96, and Russian, which never had AI Overviews, is at 66. Comparing editions by when it arrived, the effect is +2.7% in the first six months (95% interval −7% to +13%), so no loss can be pinned on AI Overviews. A loss under about 10% can't be ruled out, though.
>
> Full write-up, method and code: https://johnpospisil.github.io/wikipedia-ai-overviews/

## r/wikipedia

**Post type:** link to the article, with a short text comment. Readers there care about what it means for the project (readers, donors, editors) more than the method.
**When:** a different day from r/dataisbeautiful.

**Title:**
> Is Google's AI Overviews taking Wikipedia's readers? I compared 11 language editions by when it arrived

**Comment:**
> Wikimedia reported in 2025 that human pageviews were down about 8% and named AI search summaries as one cause. Google launched AI Overviews country by country, so the language editions got it at different times. That makes it possible to compare editions with and without it in the same month.
>
> Short version: search traffic fell almost everywhere, including Russian Wikipedia, which never had AI Overviews. Comparing editions by launch date, there's no loss I can attribute to AI Overviews: +2.7% in the first six months, −8.0% to July 2026, both with wide intervals. A small loss of about 5% for English, which another study found, fits the data.
>
> Things that may interest editors: active registered editors held up better than readers in 8 of 11 editions, and I found no AI Overviews effect on editors (though with little power). Quick-answer pages (birth dates, capitals) lost more views than long reads, but they did so in French and Russian too, where AI Overviews hardly reached.
>
> It's all public Wikimedia data, the code is open, and the hypotheses were written down before the analysis.
