"""Monthly search-engine market share by country from StatCounter (CC BY-SA 3.0).

Writes data/reference/search_share.csv in long form: country_iso2, month, engine, share (0-1).
StatCounter measures page views on sites carrying its tracker, not searches; treat as a proxy.
"""

from __future__ import annotations

import io

import pandas as pd

from wao import config, http

URL = "https://gs.statcounter.com/search-engine-market-share/all/chart.php"
FROM, TO = "2017-11", "2026-09"


def fetch(sess, iso2: str, start: str = FROM, end: str = TO) -> pd.DataFrame:
    params = {
        "device": "Desktop & Mobile & Tablet & Console",
        "device_hidden": "desktop+mobile+tablet+console",
        "statType_hidden": "search_engine",
        "region_hidden": iso2,
        "granularity": "monthly",
        "statType": "Search Engine",
        "region": iso2,
        "fromInt": start.replace("-", ""),
        "toInt": end.replace("-", ""),
        "fromMonthYear": start,
        "toMonthYear": end,
        "csv": "1",
    }
    r = sess.get(URL, params=params, timeout=60)
    r.raise_for_status()
    if not r.text.startswith('"Date"'):
        return pd.DataFrame(columns=["country_iso2", "month", "engine", "share"])
    wide = pd.read_csv(io.StringIO(r.text))
    long = wide.melt(id_vars="Date", var_name="engine", value_name="share")
    long["share"] = long.share / 100
    long.insert(0, "country_iso2", iso2)
    return long.rename(columns={"Date": "month"})


def fetch_all(countries: list[str]) -> pd.DataFrame:
    sess = http.session("statcounter", min_interval=1.0)
    sess.headers["User-Agent"] = "Mozilla/5.0 " + sess.headers["User-Agent"]
    return pd.concat([fetch(sess, c) for c in countries], ignore_index=True)


def google_share(ss: pd.DataFrame) -> pd.DataFrame:
    """Google's share by country and month (Yahoo! Japan etc. are not counted as Google)."""
    g = ss[ss.engine == "Google"][["country_iso2", "month", "share"]]
    return g.rename(columns={"share": "google_share"})
