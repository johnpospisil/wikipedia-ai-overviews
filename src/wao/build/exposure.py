"""P03: AI Overviews exposure for each Wikipedia language edition by month.

exposure[l, m] = mean over days d in month m of
    sum_c  share[l, c] * google[c] * available[c, l, d]

share[l, c]   pre-period (2023-10..2024-04) share of edition l's pageviews from country c
google[c]     pre-period mean Google search share in c (StatCounter), fixed so that any
              treatment-induced change in search behaviour can't feed back into exposure
available     1 if AI Overviews were live in c on day d AND language l was supported there

Variants: `exposure_all_users` counts only days without the signed-in-18+ restriction;
`exposure_listed` drops the Google weight. Cohort = first month with exposure >= 0.5.

Writes data/reference/language_exposure.csv and data/reference/language_cohorts.csv.
"""

from __future__ import annotations

import pandas as pd

from wao import config
from wao.ingest import search_share

MONTHS = pd.period_range("2017-11", "2026-09", freq="M")
PRE = ("2023-10", "2024-04")
COHORT_THRESHOLD = 0.5
FALLBACK_GOOGLE = 0.90  # countries StatCounter doesn't report (flagged in the output)


def load_inputs():
    ref = config.REFERENCE_DIR
    shares = pd.read_csv(ref / "country_shares.csv", keep_default_na=False)
    rollout = pd.read_csv(ref / "aio_rollout.csv", keep_default_na=False)
    support = pd.read_csv(ref / "aio_language_support.csv", keep_default_na=False)
    return shares, rollout, support


def google_pre(countries: list[str]) -> pd.DataFrame:
    path = config.REFERENCE_DIR / "search_share.csv"
    if path.exists():
        ss = pd.read_csv(path, keep_default_na=False)
        ss["share"] = pd.to_numeric(ss.share, errors="coerce")
        missing = sorted(set(countries) - set(ss.country_iso2))
        if missing:
            ss = pd.concat([ss, search_share.fetch_all(missing)], ignore_index=True)
            ss.to_csv(path, index=False)
    else:
        ss = search_share.fetch_all(countries)
        ss.to_csv(path, index=False)
    g = search_share.google_share(ss)
    g = g[(g.month >= PRE[0]) & (g.month <= PRE[1])]
    return g.groupby("country_iso2", as_index=False).google_share.mean()


def language_from(support: pd.DataFrame, wiki: str, iso2: str) -> pd.Timestamp | None:
    s = support[(support.wiki == wiki) & support.scope.isin(["all_live_countries", iso2])]
    return pd.Timestamp(s.supported_from.min()) if len(s) else None


def daily_availability(
    rollout: pd.DataFrame, support: pd.DataFrame, wiki: str, iso2: str, days: pd.DatetimeIndex
) -> tuple[pd.Series, pd.Series]:
    """(available any tier, available to all users) for one edition-country, by day."""
    zero = pd.Series(0.0, index=days)
    r = rollout[rollout.country_iso2 == iso2]
    lang = language_from(support, wiki, iso2)
    if r.empty or lang is None:
        return zero, zero
    r = r.iloc[0]
    start = max(pd.Timestamp(r.launch_date), lang)
    # removed_after = last snapshot that still listed it, so it counts as available that day.
    one = pd.Timedelta(days=1)
    end = pd.Timestamp(r.removed_after) + one if r.removed_after else days[-1] + one
    any_ = ((days >= start) & (days < end)).astype(float)
    all_start = max(pd.Timestamp(r.all_users_from), start)
    all_ = ((days >= all_start) & (days < end)).astype(float)
    return pd.Series(any_, index=days), pd.Series(all_, index=days)


def build(min_share: float = 0.001) -> tuple[pd.DataFrame, pd.DataFrame]:
    shares, rollout, support = load_inputs()
    shares = shares[shares.share >= min_share]
    g = google_pre(sorted(shares.country_iso2.unique())).set_index("country_iso2").google_share
    days = pd.date_range(MONTHS[0].start_time, MONTHS[-1].end_time.normalize(), freq="D")
    month = days.to_period("M")

    rows = []
    for wiki, sh in shares.groupby("wiki"):
        tot = pd.Series(0.0, index=days)
        tot_all = pd.Series(0.0, index=days)
        tot_listed = pd.Series(0.0, index=days)
        covered = sh.share.sum()
        fallback = 0.0
        for c, s in zip(sh.country_iso2, sh.share, strict=True):
            any_, all_ = daily_availability(rollout, support, wiki, c, days)
            gc = g.get(c)
            if gc is None or pd.isna(gc):
                gc, fallback = FALLBACK_GOOGLE, fallback + s
            tot += s * gc * any_
            tot_all += s * gc * all_
            tot_listed += s * any_
        m = (
            pd.DataFrame(
                {"exposure": tot, "exposure_all_users": tot_all, "exposure_listed": tot_listed}
            )
            .groupby(month)
            .mean()
        )
        m = m / covered  # renormalise to the countries kept
        m["wiki"] = wiki
        m["share_google_fallback"] = fallback / covered
        rows.append(m.reset_index(names="month"))
    exp = pd.concat(rows, ignore_index=True)
    exp["month"] = exp.month.astype(str)

    coh = []
    for wiki, e in exp.groupby("wiki"):
        hit = e[e.exposure >= COHORT_THRESHOLD]
        first = e[e.exposure > 0.01]
        coh.append(
            {
                "wiki": wiki,
                "cohort": hit.month.min() if len(hit) else "never",
                "first_exposed": first.month.min() if len(first) else "never",
                "exposure_2025_06": e.loc[e.month == "2025-06", "exposure"].iloc[0],
                "exposure_latest": e.exposure.iloc[-1],
                "max_exposure": e.exposure.max(),
            }
        )
    return exp, pd.DataFrame(coh).sort_values("cohort", ignore_index=True)


# Design role of each core edition (P03). Other clickstream languages: exploratory only
# (clickstream starts 2024-08, so no long pre-period).
ROLES = {
    "en": "treated",
    "ja": "treated",
    "pt": "treated",
    "es": "treated",
    "de": "treated",
    "it": "treated",
    "pl": "treated",
    "zh": "treated",
    "fr": "late_treated_control",  # cohort 2026-08; partial dose ~0.28 from 2025-05 (BE/CA/CH)
    "ru": "partial_dose",  # max ~0.46 (Yandex dominant); Yandex Neuro from 2024-04
    "fa": "ambiguous",  # ~0.96 only while Iran was listed (2025-05..09), ~0.19 otherwise
}


def main() -> None:
    exp, coh = build()
    coh["role"] = coh.wiki.map(ROLES).fillna("exploratory")
    exp.to_csv(config.REFERENCE_DIR / "language_exposure.csv", index=False)
    coh.to_csv(config.REFERENCE_DIR / "language_cohorts.csv", index=False)
    core = coh[coh.wiki.isin(config.LANGS)]
    print(core.to_string(index=False))


if __name__ == "__main__":
    main()
