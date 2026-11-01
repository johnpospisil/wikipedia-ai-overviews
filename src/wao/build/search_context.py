"""P10: search-engine context: engine shares by country and by language edition, and a monthly
Google ranking-update indicator.

Inputs:
  data/reference/search_share.csv   StatCounter, all engines, country x month 2017-11..2026-09
                                    (wao.ingest.search_share, P03; CC BY-SA 3.0)
  data/reference/country_shares.csv where each edition's readers are (P03, pre-period, fixed)
  data/reference/events.csv         Google ranking updates (category google_ranking_update)
Outputs:
  PARQUET_DIR/search_share.parquet          country_iso2, month, engine (grouped), share
  data/reference/search_share_lang.csv      wiki, month, engine, share: the edition's readers'
                                            engine mix, weighting countries by the fixed P03
                                            reader shares (countries without StatCounter data,
                                            incl. ZZ, are dropped and the rest renormalised)
  data/reference/ranking_updates_monthly.csv month, core_days, core_update (any day in month),
                                            other_update_days (spam, helpful content, reviews)
Engine groups: google (Google itself; Yahoo! Japan shows Google's index on its own page, which
has no AI Overviews, so it stays under yahoo), bing (incl. MSN), yahoo, yandex (YANDEX,
YANDEX RU), baidu, naver, duckduckgo, other. Every group is `other-search` in clickstream.
Run: python -m wao.build.search_context
"""

from __future__ import annotations

import pandas as pd

from wao import config

GROUPS = {"Google": "google", "bing": "bing", "MSN": "bing", "Yahoo!": "yahoo",
          "YANDEX": "yandex", "YANDEX RU": "yandex", "Baidu": "baidu", "Naver": "naver",
          "DuckDuckGo": "duckduckgo"}  # fmt: skip
ENGINES = ["google", "bing", "yahoo", "yandex", "baidu", "naver", "duckduckgo", "other"]
DEFAULT_DAYS = 14  # rollout length assumed when a (pre-2021-11) update has no end date
REF = config.REFERENCE_DIR


def country_shares() -> pd.DataFrame:
    d = pd.read_csv(REF / "search_share.csv").dropna(subset=["share"])
    d = d[(d.country_iso2 != "--") & ~d.engine.str.startswith("Unnamed")]
    d["engine"] = d.engine.map(GROUPS).fillna("other")
    d = d.groupby(["country_iso2", "month", "engine"], as_index=False).share.sum()
    total = d.groupby(["country_iso2", "month"]).share.transform("sum")
    d = d[total > 0.5]  # a few country-months are all zeros: no data
    d["share"] = d.share / d.groupby(["country_iso2", "month"]).share.transform("sum")
    return d


def lang_shares(cs: pd.DataFrame) -> pd.DataFrame:
    w = pd.read_csv(REF / "country_shares.csv")[["wiki", "country_iso2", "share"]]
    w = w.rename(columns={"share": "w"})
    m = w.merge(cs, on="country_iso2")
    m["ws"] = m.w * m.share
    g = m.groupby(["wiki", "month", "engine"]).ws.sum().rename("share").reset_index()
    cover = m.drop_duplicates(["wiki", "month", "country_iso2"]).groupby(["wiki", "month"]).w.sum()
    g = g.merge(cover.rename("covered").reset_index(), on=["wiki", "month"])
    g["share"] = g.share / g.covered  # renormalise over countries with data
    return g


def ranking_monthly(start: str = "2016-01", end: str = "2026-09") -> pd.DataFrame:
    ev = pd.read_csv(REF / "events.csv")
    ev = ev[ev.category == "google_ranking_update"].copy()
    ev["start"] = pd.to_datetime(ev.date)
    ev["stop"] = pd.to_datetime(ev.end_date).fillna(ev.start + pd.Timedelta(days=DEFAULT_DAYS))
    ev["core"] = ev.event.str.contains("core update", case=False)
    days = pd.date_range(start, pd.Period(end, "M").end_time.normalize(), freq="D")
    out = pd.DataFrame({"day": days, "core": 0, "other": 0})
    for e in ev.itertuples():
        on = (out.day >= e.start) & (out.day <= e.stop)
        out.loc[on, "core" if e.core else "other"] = 1
    out["month"] = out.day.dt.strftime("%Y-%m")
    m = out.groupby("month").agg(core_days=("core", "sum"), other_update_days=("other", "sum"))
    m["core_update"] = m.core_days > 0
    return m.reset_index()[["month", "core_days", "core_update", "other_update_days"]]


def main() -> None:
    cs = country_shares()
    cs.to_parquet(config.PARQUET_DIR / "search_share.parquet", index=False)
    ls = lang_shares(cs)
    ls.round(5).to_csv(REF / "search_share_lang.csv", index=False)
    rm = ranking_monthly()
    rm.to_csv(REF / "ranking_updates_monthly.csv", index=False)
    print(f"{cs.country_iso2.nunique()} countries, {cs.month.min()}..{cs.month.max()}")
    print(rm.core_update.sum(), "months with a core update")


if __name__ == "__main__":
    main()
