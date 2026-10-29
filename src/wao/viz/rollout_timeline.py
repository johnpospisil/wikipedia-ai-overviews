"""P02 figure: when AI Overviews reached the markets behind our language editions."""

from __future__ import annotations

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from wao import config

# Markets that matter for the core language editions, grouped by language.
MARKETS = [
    ("en", ["US", "GB", "IN", "CA", "AU"]),
    ("ja", ["JP"]),
    ("es", ["MX", "ES", "AR", "CO"]),
    ("pt", ["BR", "PT"]),
    ("de", ["DE", "AT", "CH"]),
    ("it", ["IT"]),
    ("pl", ["PL"]),
    ("ru", ["RU", "UA", "KZ", "BY"]),
    ("zh", ["TW", "HK"]),
    ("fa", ["IR", "AF"]),
    ("fr", ["FR", "BE"]),
]
END = pd.Timestamp("2026-10-29")
ADULT, ALL = "#9db4d6", "#2f5d9e"


def lang_from(support: pd.DataFrame, wiki: str, iso2: str) -> pd.Timestamp | None:
    s = support[support.wiki == wiki]
    hits = s[(s.scope == "all_live_countries") | (s.scope == iso2)]
    return pd.Timestamp(hits.supported_from.min()) if len(hits) else None


def main() -> None:
    r = pd.read_csv(config.REFERENCE_DIR / "aio_rollout.csv", parse_dates=["launch_date"])
    sup = pd.read_csv(config.REFERENCE_DIR / "aio_language_support.csv")
    r = r.set_index("country_iso2")

    fig, ax = plt.subplots(figsize=(9, 7.5))
    y, labels = 0, []
    for wiki, isos in MARKETS:
        for iso in isos:
            row = r.loc[iso]
            start = row.launch_date
            all_from = pd.Timestamp(row.all_users_from)
            end = pd.Timestamp(row.removed_after) if pd.notna(row.removed_after) else END
            ax.barh(y, (min(all_from, end) - start).days, left=start, color=ADULT, height=0.6)
            if all_from < end:
                ax.barh(y, (end - all_from).days, left=all_from, color=ALL, height=0.6)
            lf = lang_from(sup, wiki, iso)
            if lf is not None and lf > start:
                ax.plot([max(lf, start)], [y], marker="|", ms=12, mew=2, color="#c0392b")
            labels.append(f"{wiki} · {row.market_name}")
            y += 1
        y += 0.5
    pos, k = [], 0.0
    for _, isos in MARKETS:
        for _ in isos:
            pos.append(k)
            k += 1
        k += 0.5
    ax.set_yticks(pos, labels)
    ax.invert_yaxis()
    ax.set_xlim(pd.Timestamp("2024-04-01"), END)
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
    ax.grid(axis="x", alpha=0.3)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.set_title(
        "AI Overviews rollout in the markets behind each language edition",
        loc="left",
        fontsize=12,
        fontweight="bold",
        pad=28,
    )
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    ax.legend(
        handles=[
            Patch(color=ADULT, label="Signed-in adults only"),
            Patch(color=ALL, label="All users"),
            Line2D(
                [],
                [],
                marker="|",
                ls="",
                ms=12,
                mew=2,
                color="#c0392b",
                label="That language supported (if later)",
            ),
        ],
        loc="lower left",
        bbox_to_anchor=(0, 1.0),
        ncol=3,
        frameon=False,
        fontsize=9,
    )
    fig.text(
        0.01,
        0.005,
        "Source: Google announcements; Wayback snapshots of Google's AI Overviews "
        "help page (142, 2024-05 to 2026-10). Iran listed 2025-05 to 2025-09 only.",
        fontsize=7.5,
        color="#555",
    )
    fig.tight_layout(rect=(0, 0.02, 1, 1))
    out = config.FIGURE_DIR / "p02_rollout_timeline.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=160)
    print(out)


if __name__ == "__main__":
    main()
