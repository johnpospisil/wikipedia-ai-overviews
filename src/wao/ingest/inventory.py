"""P01: inventory of the Wikimedia dumps we depend on (what exists, and how big it is).

Writes data/reference/clickstream_availability.csv (one row per language x month file) and
data/reference/pageview_monthly_files.csv, then prints the download budget.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from wao import config, http

LISTING_ROW = re.compile(r'<a href="([^"]+)">[^<]*</a>\s+(\d{2}-\w{3}-\d{4} \d{2}:\d{2})\s+(\d+|-)')
CLICKSTREAM_FILE = re.compile(r"clickstream-(\w+?)wiki-(\d{4}-\d{2})\.tsv\.gz$")


@dataclass(frozen=True)
class Entry:
    name: str
    modified: str
    size: int | None  # None for directories


def parse_listing(html: str) -> list[Entry]:
    """Parse an nginx autoindex page into entries (skips '../')."""
    out = []
    for name, modified, size in LISTING_ROW.findall(html):
        if name == "../":
            continue
        out.append(Entry(name, modified, None if size == "-" else int(size)))
    return out


def list_dir(sess, url: str) -> list[Entry]:
    r = sess.get(url, timeout=60)
    r.raise_for_status()
    return parse_listing(r.text)


def clickstream_inventory(sess) -> pd.DataFrame:
    base = f"{config.DUMPS_BASE}/clickstream/"
    rows = []
    for month_dir in list_dir(sess, base):
        if not month_dir.name.endswith("/"):
            continue
        for e in list_dir(sess, base + month_dir.name):
            m = CLICKSTREAM_FILE.match(e.name)
            if m:
                rows.append(
                    {
                        "lang": m.group(1),
                        "month": m.group(2),
                        "file": e.name,
                        "bytes": e.size,
                        "url": base + month_dir.name + e.name,
                    }
                )
    return pd.DataFrame(rows).sort_values(["lang", "month"], ignore_index=True)


def pageview_monthly_inventory(sess) -> pd.DataFrame:
    base = f"{config.DUMPS_BASE}/pageview_complete/monthly/"
    rows = []
    for year in list_dir(sess, base):
        if not year.name.endswith("/"):
            continue
        for month in list_dir(sess, base + year.name):
            if not month.name.endswith("/"):
                continue
            for e in list_dir(sess, base + year.name + month.name):
                m = re.match(r"pageviews-(\d{6})-(user|automated|spider)\.bz2$", e.name)
                if m:
                    rows.append(
                        {
                            "month": f"{m.group(1)[:4]}-{m.group(1)[4:]}",
                            "agent": m.group(2),
                            "file": e.name,
                            "bytes": e.size,
                            "url": base + year.name + month.name + e.name,
                        }
                    )
    return pd.DataFrame(rows).sort_values(["month", "agent"], ignore_index=True)


def availability_matrix(cs: pd.DataFrame, langs=config.LANGS) -> pd.DataFrame:
    """First/last month, number of months and gaps for each language."""
    all_months = pd.period_range(cs.month.min(), cs.month.max(), freq="M").astype(str)
    out = []
    for lang, g in cs.groupby("lang"):
        have = set(g.month)
        span = [m for m in all_months if g.month.min() <= m <= g.month.max()]
        gaps = [m for m in span if m not in have]
        out.append(
            {
                "lang": lang,
                "first": g.month.min(),
                "last": g.month.max(),
                "months": len(have),
                "gaps": ";".join(gaps),
                "gb_total": g.bytes.sum() / 1e9,
                "gb_latest": g.sort_values("month").bytes.iloc[-1] / 1e9,
                "core": lang in langs,
            }
        )
    return pd.DataFrame(out).sort_values("gb_total", ascending=False, ignore_index=True)


def main() -> None:
    sess = http.session("listings")
    cs = clickstream_inventory(sess)
    pv = pageview_monthly_inventory(sess)
    config.REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    cs.to_csv(config.REFERENCE_DIR / "clickstream_files.csv", index=False)
    pv.to_csv(config.REFERENCE_DIR / "pageview_monthly_files.csv", index=False)
    mat = availability_matrix(cs)
    mat.to_csv(config.REFERENCE_DIR / "clickstream_availability.csv", index=False)

    pd.set_option("display.width", 160)
    print(
        f"Clickstream: {cs.lang.nunique()} languages, {cs.month.nunique()} months, "
        f"{cs.bytes.sum() / 1e9:,.0f} GB in all"
    )
    print(mat.head(30).to_string(index=False))
    core = cs[cs.lang.isin(config.LANGS)]
    print(f"\nCore-language clickstream: {core.bytes.sum() / 1e9:,.1f} GB")
    pv16 = pv[pv.month >= "2016-01"]
    for agent, g in pv16.groupby("agent"):
        print(
            f"pageview_complete monthly {agent:<9}: {len(g)} months, {g.bytes.sum() / 1e9:,.0f} GB"
        )


if __name__ == "__main__":
    main()
