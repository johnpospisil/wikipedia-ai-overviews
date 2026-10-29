"""P03: pre-period country shares of each Wikipedia language edition's `user` pageviews.

Two Wikimedia sources, combined:

1. AQS `top-by-country` (monthly, all pages, view counts rounded up to the next 1,000). Countries
   on Wikimedia's Country and Territory Protection List are withheld (their ranks are missing).
   The withheld mass is the residual: AQS `user` total minus the published countries.
2. The differentially private `country_project_page` daily files. They publish medium- and
   higher-risk countries (e.g. RU, BY, KZ) from 2024-02-15, but never some (e.g. IR, CN).

Shares: published countries from (1); the residual is split across withheld countries in
proportion to their views in (2); whatever is left goes to the edition's never-published country
(IR for fa, CN for zh) or to "ZZ" (unknown, treated as unexposed).

Window: 2023-10..2024-04 (pre-launch; after the US gap in (2) of 2023-02-06..2023-09-19).
Writes data/reference/country_shares.csv: wiki, country_iso2, views, share, source.
"""

from __future__ import annotations

import argparse
import subprocess
from datetime import date, timedelta

import duckdb
import pandas as pd

from wao import config, http

BASE = "https://analytics.wikimedia.org/published/datasets/country_project_page"
START, END = date(2023, 10, 1), date(2024, 4, 30)
DP_FULL_COVERAGE = date(2024, 2, 15)  # medium/higher-risk countries published from here
MONTHS = [str(p) for p in pd.period_range("2023-10", "2024-04", freq="M")]
NEVER_PUBLISHED = {"fa": "IR", "zh": "CN"}


def days(start: date, end: date) -> list[date]:
    return [start + timedelta(n) for n in range((end - start).days + 1)]


def download(start: date = START, end: date = END) -> list[str]:
    out = config.COUNTRY_DIR / "country_project_page"
    out.mkdir(parents=True, exist_ok=True)
    ua = http.user_agent()
    paths = []
    for d in days(start, end):
        p = out / f"{d.isoformat()}.tsv"
        if not p.exists() or p.stat().st_size == 0:
            tmp = p.with_suffix(".part")
            subprocess.run(
                ["curl", "-sfL", "--retry", "5", "-A", ua, "-o", str(tmp), f"{BASE}/{d}.tsv"],
                check=True,
            )
            tmp.rename(p)
        paths.append(str(p))
    return paths


def dp_views(paths: list[str]) -> pd.DataFrame:
    """Views by edition and country from the DP files: wiki, country_iso2, dp_views."""
    return (
        duckdb.connect()
        .execute(
            """
        SELECT split_part(column2, '.', 1) AS wiki, column1 AS country_iso2,
               sum(column6) AS dp_views
        FROM read_csv($paths, delim='\t', header=false, quote='', escape='',
                      columns={'column0':'VARCHAR','column1':'VARCHAR','column2':'VARCHAR',
                               'column3':'BIGINT','column4':'VARCHAR','column5':'VARCHAR',
                               'column6':'DOUBLE'})
        WHERE column2 LIKE '%.wikipedia'
        GROUP BY ALL
        """,
            {"paths": paths},
        )
        .df()
    )


def aqs_views(sess, wiki: str, months: list[str] = MONTHS) -> tuple[pd.DataFrame, float]:
    """(published countries' views summed over months, total `user` views over months)."""
    rows, total = [], 0.0
    for m in months:
        p = pd.Period(m, "M")
        y, mo = m.split("-")
        r = sess.get(
            f"{config.AQS_BASE}/pageviews/top-by-country/{wiki}.wikipedia.org/all-access/{y}/{mo}",
            timeout=60,
        )
        if r.status_code != 200:
            continue  # some edition-months are missing (e.g. fr 2024-03); skip them on both sides
        for c in r.json()["items"][0]["countries"]:
            rows.append((c["country"], c["views_ceil"]))
        end = (p + 1).start_time.strftime("%Y%m%d00")
        j = sess.get(
            f"{config.AQS_BASE}/pageviews/aggregate/{wiki}.wikipedia/all-access/user/monthly/"
            f"{y}{mo}0100/{end}",
            timeout=60,
        ).json()
        total += j["items"][0]["views"] if "items" in j else 0
    pub = pd.DataFrame(rows, columns=["country_iso2", "views"])
    return pub.groupby("country_iso2", as_index=False).views.sum(), total


def combine(wiki: str, pub: pd.DataFrame, total: float, dp: pd.DataFrame) -> pd.DataFrame:
    """Published countries + residual split over withheld countries (see module docstring)."""
    out = pub.assign(source="aqs")
    residual = max(total - pub.views.sum(), 0.0)
    d = dp[(dp.wiki == wiki) & ~dp.country_iso2.isin(pub.country_iso2)]
    if residual > 0 and len(d):
        # DP counts are a different (thresholded, deduplicated) measure: scale them to AQS
        # using the countries both sources publish, then cap at the residual.
        both = pub.merge(dp[dp.wiki == wiki], on="country_iso2")
        k = both.views.sum() / both.dp_views.sum() if both.dp_views.sum() else 0.0
        est = d.assign(views=d.dp_views * k)
        if est.views.sum() > residual:
            est["views"] *= residual / est.views.sum()
        est = est[est.views > 0]
        out = pd.concat([out, est[["country_iso2", "views"]].assign(source="dp_residual")])
        residual -= est.views.sum()
    if residual > 0:
        rest = NEVER_PUBLISHED.get(wiki, "ZZ")
        out = pd.concat(
            [out, pd.DataFrame([{"country_iso2": rest, "views": residual, "source": "residual"}])]
        )
    out = out.groupby(["country_iso2", "source"], as_index=False).views.sum()
    out["share"] = out.views / total if total else 0.0
    out.insert(0, "wiki", wiki)
    return out.sort_values("share", ascending=False, ignore_index=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wikis", nargs="*", default=None, help="default: clickstream languages")
    a = ap.parse_args()
    wikis = a.wikis or list(pd.read_csv(config.REFERENCE_DIR / "clickstream_availability.csv").lang)
    paths = download(DP_FULL_COVERAGE, END)
    dp = dp_views(paths)
    sess = http.session("aqs")
    parts = []
    for w in wikis:
        pub, total = aqs_views(sess, w)
        parts.append(combine(w, pub, total, dp))
    df = pd.concat(parts, ignore_index=True)
    df.to_csv(config.REFERENCE_DIR / "country_shares.csv", index=False)
    for w in config.LANGS:
        top = df[df.wiki == w].head(5)
        print(
            w,
            " ".join(f"{c}:{s:.0%}" for c, s in zip(top.country_iso2, top.share, strict=True)),
            f"| residual-based {df[(df.wiki == w) & (df.source != 'aqs')].share.sum():.0%}",
        )


if __name__ == "__main__":
    main()
