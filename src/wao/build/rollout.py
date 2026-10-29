"""P02: country- and language-level AI Overviews availability from Google's own help page over time.

Google's help page (support.google.com/websearch/answer/14901683) lists where AI Overviews are
available. We parse every distinct Wayback Machine snapshot of it, so each country's first
appearance is bracketed by the last snapshot without it and the first snapshot with it.

Outputs (data/reference/):
  aio_help_snapshots.csv    one row per snapshot x listed country/language (tier = age rule)
  aio_country_first_seen.csv  first-seen bracket per country, plus language first-seen rows
"""

from __future__ import annotations

import html
import re
from datetime import datetime

import pandas as pd
import pycountry

from wao import config, http

PAGE = "support.google.com/websearch/answer/14901683"
CDX = "https://web.archive.org/cdx/search/cdx"
REGION_HEADINGS = {"Americas", "Asia-Pacific", "Europe, the Middle East & Africa"}

# Names on Google's page that pycountry can't resolve on its own.
ALIASES = {
    "Korea": "KR",
    "Congo (DRC)": "CD",
    "Congo (Republic)": "CG",
    "Türkiye": "TR",
    "Kosovo": "XK",
    "Russia": "RU",
    "Taiwan": "TW",
    "Vietnam": "VN",
    "Laos": "LA",
    "Brunei": "BN",
    "Micronesia": "FM",
    "Cape Verde": "CV",
    "Côte d'Ivoire": "CI",
    "Palestine": "PS",
    "Moldova": "MD",
    "Syria": "SY",
    "Iran": "IR",
    "Bolivia": "BO",
    "Venezuela": "VE",
    "Tanzania": "TZ",
    "Macao": "MO",
    "Hong Kong": "HK",
    "U.S. Virgin Islands": "VI",
    "British Virgin Islands": "VG",
    "St. Maarten": "SX",
    "Saint Maarten": "SX",
    "Saint Martin": "MF",
    "Caribbean Netherlands": "BQ",
    "Falkland Islands (Islas Malvinas)": "FK",
    "Pitcairn Islands": "PN",
    "St. Helena, Ascension and Tristan da Cunha": "SH",
    "Heard Island and McDonald Islands": "HM",
    "Ceuta & Melilla": "EA",
    "Canary Islands": "IC",
    "Eurozone": None,
    "Vatican City": "VA",
    "Czechia": "CZ",
    "Eswatini": "SZ",
    "North Macedonia": "MK",
    "Western Sahara": "EH",
}

# Google renamed some entries between snapshots; keep one spelling so they aren't "removed".
RENAMED = {"St. Maarten": "Saint Maarten"}

# Lines that are part of the list layout, not countries.
NOT_COUNTRY = {
    "Countries and territories",
    "Languages",
    ":",
    "and",
    "countries, territories",
    "languages",
}

TIER_PATTERNS = [
    (re.compile(r"all users in the US", re.I), "us_all"),
    (re.compile(r"above the age of 18|18 or older|aged 18", re.I), "adult_signed_in"),
    (re.compile(r"To all users", re.I), "all"),
]


def snapshot_index(sess) -> pd.DataFrame:
    r = sess.get(
        CDX,
        params={
            "url": PAGE,
            "from": "2024",
            "fl": "timestamp,statuscode,digest",
            "collapse": "digest",
            "filter": "statuscode:200",
            "output": "json",
        },
        timeout=120,
    )
    r.raise_for_status()
    rows = r.json()
    return pd.DataFrame(rows[1:], columns=rows[0])


def page_text(raw: str) -> str:
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", raw, flags=re.S)
    t = html.unescape(re.sub(r"<[^>]+>", "\n", t))
    return re.sub(r"\s*\n\s*", "\n", t)


def parse_availability(text: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Return ([(country_name, tier)], [language]) from the 'AI Overviews availability' section."""
    start = text.find("AI Overviews are currently available")
    if start < 0:
        return [], []
    end_markers = [
        "AI Overviews will become available",
        "AI Overviews when you search",
        "Show only web links",
    ]
    end = min((i for m in end_markers if (i := text.find(m, start)) > 0), default=len(text))
    lines = [ln.strip() for ln in text[start:end].split("\n") if ln.strip()]

    countries: list[tuple[str, str]] = []
    languages: list[str] = []
    tier = None
    in_languages = False
    for ln in lines[1:]:
        if ln == "Languages":
            in_languages = True
            continue
        if ln.startswith("To ") or ln.startswith("To "):
            tier = next((name for pat, name in TIER_PATTERNS if pat.search(ln)), "other")
            if tier == "us_all":
                countries.append(("United States", tier))
            if tier == "adult_signed_in" and re.search(r"in the UK, ", ln):
                # Aug 2024 wording lists the countries inline.
                inline = re.sub(r".*? in the ", "", ln).rstrip(".")
                for name in re.split(r",\s*(?:and\s+)?|\s+and\s+", inline):
                    countries.append(({"UK": "United Kingdom"}.get(name, name), tier))
            in_languages = False
            continue
        if ln in REGION_HEADINGS or ln in NOT_COUNTRY or tier is None:
            continue
        if in_languages:
            if "Search Labs" not in ln and '"' not in ln and "“" not in ln:
                languages.append(ln)
        elif _iso2(ln) is not None or ln in ALIASES:
            countries.append((ln, tier))
    return countries, languages


def _iso2(name: str) -> str | None:
    if name in ALIASES:
        return ALIASES[name]
    try:
        return pycountry.countries.lookup(name).alpha_2
    except LookupError:
        return None


def collect(sess) -> pd.DataFrame:
    idx = snapshot_index(sess)
    rows = []
    for ts in idx.timestamp:
        url = f"https://web.archive.org/web/{ts}id_/https://{PAGE}"
        r = sess.get(url, timeout=120)
        if r.status_code != 200:
            continue
        countries, languages = parse_availability(page_text(r.text))
        snap = datetime.strptime(ts, "%Y%m%d%H%M%S").date()
        rows.append(
            {"snapshot": snap, "timestamp": ts, "kind": "_snapshot", "name": "", "tier": ""}
        )
        for name, tier in countries:
            name = RENAMED.get(name, name)
            rows.append(
                {"snapshot": snap, "timestamp": ts, "kind": "country", "name": name, "tier": tier}
            )
        for lang in languages:
            rows.append(
                {"snapshot": snap, "timestamp": ts, "kind": "language", "name": lang, "tier": "all"}
            )
    df = pd.DataFrame(rows)
    df["iso2"] = [
        (_iso2(n) if k == "country" else None) for k, n in zip(df.kind, df.name, strict=True)
    ]
    return df


def first_seen(snaps: pd.DataFrame) -> pd.DataFrame:
    """For each country/language: last snapshot without it, first snapshot with it."""
    dates = sorted(snaps.snapshot.unique())
    out = []
    listed = snaps[snaps.kind != "_snapshot"]
    # Languages are only listed from mid-2025; before that the bracket is open.
    lang_dates = sorted(snaps[snaps.kind == "language"].snapshot.unique())
    for (kind, name), g in listed.groupby(["kind", "name"]):
        first = g.snapshot.min()
        pool = dates if kind == "country" else lang_dates
        before = [d for d in pool if d < first]
        out.append(
            {
                "kind": kind,
                "name": name,
                "iso2": g.iso2.iloc[0],
                "first_seen": first,
                "last_absent": before[-1] if before else None,
                "first_tier": g.sort_values("snapshot").tier.iloc[0],
                "first_all_users": g[g.tier.isin(["all", "us_all"])].snapshot.min(),
                "last_seen": g.snapshot.max(),
                "n_snapshots": g.snapshot.nunique(),
            }
        )
    return pd.DataFrame(out).sort_values(["kind", "first_seen", "name"], ignore_index=True)


# Official announcements that a Wayback bracket falls into: (bracket_start, bracket_end] -> wave.
# A country whose bracket contains an announcement date gets that date; otherwise the midpoint.
GOOGLE = "https://blog.google/products/search"
WAVES = [
    ("2024-05-14", "us", f"{GOOGLE}/generative-ai-google-search-may-2024/"),
    ("2024-08-15", "six_markets", f"{GOOGLE}/new-ways-to-connect-to-the-web-with-ai-overviews/"),
    ("2024-10-28", "100_countries", f"{GOOGLE}/ai-overviews-search-october-2024/"),
    (
        "2025-03-25",
        "europe_9",
        "https://blog.google/feed/were-bringing-the-helpfulness-of-ai-overviews-to-more-countries-in-europe/",
    ),
    ("2025-05-20", "200_countries", f"{GOOGLE}/ai-overview-expansion-may-2025-update/"),
    (
        "2026-07-22",
        "france",
        "https://blog.google/intl/fr-fr/nouveautes-produits/explorez-obtenez-des-reponses/recherche-ia-apercus-mode/",
    ),
]
WAYBACK = f"https://web.archive.org/web/*/{PAGE}"


def build_rollout(fs: pd.DataFrame, snap_dates: list[pd.Timestamp]) -> pd.DataFrame:
    """Country-level launch table: official wave date where the Wayback bracket allows it."""
    c = fs[fs.kind == "country"].copy()
    waves = [(pd.Timestamp(d), name, url) for d, name, url in WAVES]
    rows = []
    for r in c.itertuples():
        first = pd.Timestamp(r.first_seen)
        absent = pd.Timestamp(r.last_absent) if pd.notna(r.last_absent) else None
        if r.iso2 == "US":
            d, wave, url, prec = waves[0][0], "us", waves[0][2], "day"
        else:
            hit = [
                w
                for w in waves
                if (absent is None or w[0] > absent - pd.Timedelta(days=14)) and w[0] <= first
            ]
            if hit:
                d, wave, url = hit[-1][0], hit[-1][1], hit[-1][2]
                prec = "day"
            else:
                d = absent + (first - absent) / 2
                wave, url, prec = (
                    "wayback_only",
                    WAYBACK,
                    f"bracket {r.last_absent}..{r.first_seen}",
                )
        # Open to all users from launch if the first listing had no age rule; otherwise snap the
        # all-users switch to an announcement date if one falls in its Wayback bracket.
        if r.first_tier in ("all", "us_all"):
            all_from = d
        else:
            seen = pd.Timestamp(r.first_all_users)
            prior = max((s for s in snap_dates if s < seen), default=seen)
            hit = [w for w in waves if prior < w[0] <= seen]
            all_from = hit[-1][0] if hit else seen
        rows.append(
            {
                "country_iso2": r.iso2,
                "market_name": r.name,
                "product": "ai_overviews",
                "launch_date": d.date(),
                "wave": wave,
                "date_precision": prec,
                "all_users_from": all_from.date(),
                "removed_after": (r.last_seen if r.last_seen < fs.last_seen.max() else ""),
                "source_url": url,
                "wayback_first_seen": r.first_seen,
                "wayback_last_absent": r.last_absent,
            }
        )
    return pd.DataFrame(rows).sort_values(["launch_date", "market_name"], ignore_index=True)


def main() -> None:
    sess = http.session("wayback", min_interval=1.0)
    snaps = collect(sess)
    config.REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    snaps.to_csv(config.REFERENCE_DIR / "aio_help_snapshots.csv", index=False)
    fs = first_seen(snaps)
    fs.to_csv(config.REFERENCE_DIR / "aio_country_first_seen.csv", index=False)
    snap_dates = sorted(pd.Timestamp(d) for d in snaps.snapshot.unique())
    build_rollout(fs, snap_dates).to_csv(config.REFERENCE_DIR / "aio_rollout.csv", index=False)
    unresolved = sorted(set(snaps[(snaps.kind == "country") & snaps.iso2.isna()].name))
    n = snaps.timestamp.nunique()
    print(f"{n} snapshots, {snaps.snapshot.min()} to {snaps.snapshot.max()}")
    print("unresolved country names:", unresolved)
    print(fs.groupby(["kind", "first_seen"]).size().to_string())


if __name__ == "__main__":
    main()
