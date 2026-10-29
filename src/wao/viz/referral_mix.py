"""P05 figures: English referral mix over time, and clickstream coverage by language and month.

Descriptive only (one language, totals), so it is allowed before pre-registration (rule 6).
"""

from __future__ import annotations

import duckdb
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from wao import config

MIX = [
    ("search", "Search engines", "#1f4e8c"),
    ("link", "Links from other articles", "#8fa9cf"),
    ("empty", "No referrer (direct, apps, privacy)", "#c9c9c9"),
    ("internal_other", "Other Wikipedia pages", "#e6b85c"),
    ("external", "Other websites", "#c0392b"),
    ("link_other", "Old links / other", "#e8e8e8"),
    ("other", "Other", "#f2f2f2"),
]


def load() -> pd.DataFrame:
    p = config.PARQUET_DIR / "clickstream_lang_month.parquet"
    df = duckdb.connect().execute(f"SELECT * FROM '{p}'").df()
    df["t"] = pd.PeriodIndex(df.month, freq="M").to_timestamp()
    return df.sort_values(["lang", "t"])


def referral_mix(df: pd.DataFrame, lang: str = "en") -> plt.Figure:
    d = df[df.lang == lang].set_index("t")
    shares = d[[k for k, _, _ in MIX]].div(d.total, axis=0).fillna(0)
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.stackplot(
        shares.index,
        *[shares[k] for k, _, _ in MIX],
        labels=[lab for _, lab, _ in MIX],
        colors=[c for _, _, c in MIX],
        lw=0,
    )
    for date, label in [("2022-11-30", "ChatGPT"), ("2024-05-14", "AI Overviews (US)")]:
        ax.axvline(pd.Timestamp(date), color="black", lw=0.8, ls="--")
        ax.text(pd.Timestamp(date), 1.01, label, ha="center", fontsize=8)
    ax.set_ylim(0, 1)
    ax.set_xlim(shares.index.min(), shares.index.max())
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.set_ylabel("Share of article arrivals")
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), frameon=False, fontsize=9)
    ax.set_title(
        f"How readers arrive at {lang} Wikipedia articles (clickstream, monthly)",
        loc="left",
        fontsize=12,
        fontweight="bold",
        pad=18,
    )
    fig.text(
        0.01,
        0.01,
        "Source: Wikimedia clickstream (desktop + mobile web; pairs with "
        "fewer than 10 views a month are not published). Descriptive totals only.",
        fontsize=7.5,
        color="#555",
    )
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    return fig


def coverage(df: pd.DataFrame) -> plt.Figure:
    """QA: is every language-month present, and does the volume look continuous?"""
    langs = list(config.LANGS) + sorted(set(df.lang) - set(config.LANGS))
    months = pd.period_range(df.month.min(), df.month.max(), freq="M").astype(str)
    piv = df.pivot_table(index="lang", columns="month", values="articles").reindex(
        index=langs, columns=months
    )
    fig, ax = plt.subplots(figsize=(12, 7.5))
    im = ax.imshow(np.log10(piv.values), aspect="auto", cmap="viridis", interpolation="nearest")
    ax.set_yticks(range(len(langs)), langs, fontsize=7)
    ticks = [i for i, m in enumerate(months) if m.endswith("-01")]
    ax.set_xticks(ticks, [months[i][:4] for i in ticks])
    ax.axhline(len(config.LANGS) - 0.5, color="white", lw=1.5)
    cb = fig.colorbar(im, ax=ax, fraction=0.025)
    cb.set_label("log10 articles with ≥1 published arrival")
    ax.set_title(
        "Clickstream coverage by language and month (white gaps = missing file)",
        loc="left",
        fontsize=12,
        fontweight="bold",
    )
    fig.tight_layout()
    return fig


def main() -> None:
    df = load()
    config.FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    for name, fig in (
        ("p05_referral_mix_en", referral_mix(df)),
        ("p05_clickstream_coverage", coverage(df)),
    ):
        out = config.FIGURE_DIR / f"{name}.png"
        fig.savefig(out, dpi=160)
        print(out)


if __name__ == "__main__":
    main()
