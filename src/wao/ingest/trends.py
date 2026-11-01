"""P10 context only: Google Trends interest in the topic "Wikipedia" (/m/0d07ph) by country.

Google Trends has no open API; this uses the unofficial pytrends client, a few requests, 10 s
apart. Each series is an index (0-100, its own peak = 100) computed on a random sample of
Google searches, so values move between pulls and the scale differs between windows. To
measure that noise each country is pulled twice, for 2016-01..2026-09 and for 2021-01..2026-09;
p10_trends_noise.csv compares the overlap after rescaling the short window to the long one.
Trends counts Google searches mentioning the topic (navigational "wikipedia" queries), not
Wikipedia traffic. Context only: never an outcome.

Output: PARQUET_DIR/context/google_trends.parquet  country_iso2, window, month, interest
        report/qa/p10_trends_noise.csv
Run: python -m wao.ingest.trends
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
from pytrends.request import TrendReq

from wao import config

TOPIC = "/m/0d07ph"
COUNTRIES = ["US", "GB", "IN", "JP", "BR", "PT", "ES", "MX", "DE", "IT", "PL", "FR", "RU", "TW",
             "IR"]  # fmt: skip
WINDOWS = {"long": "2016-01-01 2026-09-30", "short": "2021-01-01 2026-09-30"}


def out_path():
    return config.PARQUET_DIR / "context" / "google_trends.parquet"


def pull() -> pd.DataFrame:
    p = TrendReq(hl="en-US", tz=0, timeout=(10, 30))
    rows = []
    for c in COUNTRIES:
        for w, tf in WINDOWS.items():
            p.build_payload([TOPIC], timeframe=tf, geo=c)
            d = p.interest_over_time()
            rows += [(c, w, i.strftime("%Y-%m"), int(v)) for i, v in d[TOPIC].items()]
            time.sleep(10)
        print(c, flush=True)
    return pd.DataFrame(rows, columns=["country_iso2", "window", "month", "interest"])


def noise(t: pd.DataFrame) -> pd.DataFrame:
    """Rescale the short window to the long one on the overlap (least squares through 0), then
    report the typical gap: noise from sampling and from rounding to integers."""
    out = []
    for c, g in t.groupby("country_iso2"):
        w = g.pivot(index="month", columns="window", values="interest").dropna()
        k = (w.long * w.short).sum() / (w.short**2).sum()
        rel = (k * w.short - w.long) / w.long.replace(0, np.nan)
        out.append({"country_iso2": c, "months": len(w), "scale": round(k, 3),
                    "median_abs_pct_gap": round(100 * rel.abs().median(), 1),
                    "p90_abs_pct_gap": round(100 * rel.abs().quantile(0.9), 1),
                    "long_min": int(w.long.min())})  # fmt: skip
    return pd.DataFrame(out)


def main() -> None:
    if out_path().exists():
        t = pd.read_parquet(out_path())
    else:
        t = pull()
        out_path().parent.mkdir(parents=True, exist_ok=True)
        t.to_parquet(out_path(), index=False)
    n = noise(t)
    n.to_csv(config.REPORT_DIR / "qa" / "p10_trends_noise.csv", index=False)
    print(n.to_string(index=False))


if __name__ == "__main__":
    main()
