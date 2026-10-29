"""P03 figure: AI Overviews exposure by language edition and month (one panel per edition)."""

from __future__ import annotations

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from wao import config

ORDER = ["en", "ja", "pt", "es", "de", "it", "pl", "zh", "fr", "ru", "fa"]
INK, SOFT, GREY = "#1f4e8c", "#8fa9cf", "#d5d5d5"


def main() -> None:
    e = pd.read_csv(config.REFERENCE_DIR / "language_exposure.csv")
    coh = pd.read_csv(config.REFERENCE_DIR / "language_cohorts.csv").set_index("wiki")
    cs = pd.read_csv(config.REFERENCE_DIR / "clickstream_availability.csv")
    e = e[e.month >= "2024-01"].copy()
    e["t"] = pd.PeriodIndex(e.month, freq="M").to_timestamp()
    others = e[e.wiki.isin(cs.lang) & ~e.wiki.isin(ORDER)]

    fig, axes = plt.subplots(3, 4, figsize=(13, 8.5), sharex=True, sharey=True)
    for ax, wiki in zip(axes.flat, ORDER + [None], strict=True):
        if wiki is None:
            ax.axis("off")
            ax.plot([], [], color=INK, lw=2.2, label="Exposure (any eligible users)")
            ax.plot([], [], color=SOFT, lw=1.6, ls="--", label="Exposure (all users, no sign-in)")
            ax.plot([], [], color=GREY, lw=1, label="Other 29 clickstream languages")
            ax.plot([], [], color="#c0392b", lw=1, label="Cohort month (≥ 0.5)")
            ax.legend(loc="center", frameon=False, fontsize=9)
            continue
        for _, g in others.groupby("wiki"):
            ax.plot(g.t, g.exposure, color=GREY, lw=0.7, zorder=1)
        g = e[e.wiki == wiki]
        ax.plot(g.t, g.exposure_all_users, color=SOFT, lw=1.6, ls="--", zorder=2)
        ax.plot(g.t, g.exposure, color=INK, lw=2.2, zorder=3)
        c = coh.loc[wiki, "cohort"]
        if c != "never":
            ax.axvline(pd.Period(c, "M").to_timestamp(), color="#c0392b", lw=1)
        ax.axhline(0.5, color="#999", ls=":", lw=0.8)
        ax.set_title(f"{wiki}  ·  cohort {c}", loc="left", fontsize=10, fontweight="bold")
        ax.set_ylim(0, 1)
        ax.grid(alpha=0.25)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 7]))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
    for ax in axes[:, 0]:
        ax.set_ylabel("Share of readers exposed")
    fig.suptitle(
        "How much of each Wikipedia edition's readership could see Google's AI Overviews",
        x=0.01,
        ha="left",
        fontsize=13,
        fontweight="bold",
    )
    fig.text(
        0.01,
        0.005,
        "Exposure = Σ country share of the edition's pageviews (2023-10..2024-04; AQS, with "
        "protected countries such as RU, IR estimated from the residual) × Google search share "
        "(StatCounter, same months) × AI Overviews live there in that language (Google's help "
        "page). fa: Iran was listed only 2025-05..2025-09.",
        fontsize=7.5,
        color="#555",
        wrap=True,
    )
    fig.tight_layout(rect=(0, 0.035, 1, 0.96))
    out = config.FIGURE_DIR / "p03_exposure_curves.png"
    fig.savefig(out, dpi=160)
    print(out)


if __name__ == "__main__":
    main()
