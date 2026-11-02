"""P26: hero chart, three alternatives, each in light and dark (PNG + SVG).

  A  hero_event      event study: search arrivals of the 8 treated editions indexed to 100 at
                     their base month, vs the not-yet-treated comparison (P17 full window,
                     Callaway-Sant'Anna; band = 95% multiplier bootstrap); the months where the
                     comparison rests on French alone are shaded
  B  hero_calendar   calendar time: deseasonalised search arrivals, 8 treated editions pooled vs
                     fr, index 2023-08..2024-07 = 100, with the rollout period shaded
  C  hero_estimates  what every design says: the effect of AI Overviews on search arrivals from
                     P17-P20 with intervals, against the -5% smallest effect of interest

Usage: python -m wao.viz.hero
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from wao import config  # noqa: E402
from wao.models import did  # noqa: E402
from wao.viz import theme  # noqa: E402

QA = config.REPORT_DIR / "qa"
SOURCE = ("Data: Wikimedia clickstream and pageviews (CC0), 9 Wikipedia editions, 2019-04 to "
          "2026-09. Exposure: share of each edition's readers in countries with Google AI "
          "Overviews.")  # fmt: skip
FR_ONLY = 9  # from event month 9 the first cohort's only comparison is fr (from 2025-06)
pct = lambda v: 100 * (np.exp(v) - 1)  # noqa: E731


def event_paths() -> pd.DataFrame:
    """Per event time: treated mean change since base, comparison mean change, ATT, bootstrap SE."""
    d = did.panel()
    end, rule = did.WINDOWS["full"]
    Y, months, G, E, miss = did.matrix(d, end, rule)
    cells = did.att_gt(Y, G, E, miss, rule)
    V = did.webb(len(G))
    rows = []
    for c in cells:
        tr = (G == c["g"]) & (E == c["e_first"])
        ctrl = did._controls(G, E, max(c["t"], c["base"]), rule) & ~tr
        dy = Y[:, c["t"]] - Y[:, c["base"]]
        rows.append(dict(event=c["event"], n=c["n"], kind=c["kind"], tr=dy[tr].mean(),
                         ctrl=dy[ctrl].mean(), att=c["att"], psi=c["psi"]))  # fmt: skip
    df = pd.DataFrame(rows)
    out = []
    for e, g in df.groupby("event"):
        w = (g.n / g.n.sum()).values
        psi = sum(wi * p for wi, p in zip(w, g.psi, strict=True))
        out.append(dict(event=e, tr=(w * g.tr).sum(), ctrl=(w * g.ctrl).sum(),
                        att=(w * g.att).sum(), se=did.boot_se(psi, V),
                        kind="post" if "post" in set(g.kind) else
                        ("partial" if "partial" in set(g.kind) else "lead")))  # fmt: skip
    return pd.DataFrame(out)


def hero_event(es: pd.DataFrame, mode: str) -> None:
    att = pd.read_csv(QA / "p17_att.csv").query("estimator == \"Callaway-Sant'Anna\"")
    att = att.set_index("window")
    with theme.use(mode) as p:
        fig, ax = plt.subplots(figsize=(10, 5.6))
        fig.subplots_adjust(left=0.07, right=0.80, top=0.80, bottom=0.14)
        e = es[(es.event >= -12) & (es.event <= 22)]
        post = e[e.event >= 0]
        cf = e.tr - e.att
        ax.fill_between(post.event, 100 * np.exp(cf[post.index] - 1.96 * post.se),
                        100 * np.exp(cf[post.index] + 1.96 * post.se), color=p.band, alpha=0.6,
                        lw=0, label="95% band")  # fmt: skip
        ax.plot(e.event, 100 * np.exp(cf), color=p.counterfactual, lw=1.8, ls=(0, (5, 2)))
        ax.plot(e.event, 100 * np.exp(e.tr), color=p.treated, lw=2.6)
        theme.event(ax, -0.5, "AI Overviews reach most readers")
        theme.event(ax, FR_ONLY - 0.5, "comparison = French only", span_end=22.5, y=0.9)
        last = e.iloc[-1]
        theme.label_end(ax, last.event, 100 * np.exp(last.tr), "Editions with AI Overviews",
                        p.treated)  # fmt: skip
        theme.label_end(ax, last.event, 100 * np.exp(last.tr - last.att),
                        "Not yet treated (counterfactual)", p.counterfactual)  # fmt: skip
        ax.axhline(100, color=p.ink_muted, lw=0.6)
        ax.set_xlim(-12.5, 22.5)
        ax.set_xlabel("Months since AI Overviews reached at least half of an edition's readers")
        ax.set_ylabel("Search arrivals, index (base month = 100)")
        theme.title(fig, "No clear dent: Wikipedia search traffic after AI Overviews",
                    f"8 treated editions vs editions not yet treated. Effect: {pct(att.theta['primary']):+.0f}% "  # noqa: E501
                    f"in the first 6 months, {pct(att.theta['full']):+.0f}% over the full window "
                    "(neither significant)")  # fmt: skip
        theme.source(fig, SOURCE)
        theme.save(fig, "hero_event")


def calendar() -> pd.DataFrame:
    d = did.panel()
    s = did.seasonal(d)
    d["moy"] = pd.PeriodIndex(d.month, freq="M").month
    d = d.merge(s, on=["lang", "moy"])
    d["adj"] = d.search_arr_na / np.exp(d.s)
    d["grp"] = np.where(d.lang == "fr", "fr", "treated")
    g = d.groupby(["grp", "month"]).adj.sum(min_count=1)  # 2025-04 stays NaN
    g = g.unstack("grp").sort_index()
    g = g.rolling(3, center=True, min_periods=2).mean()
    base = g.loc["2023-08":"2024-07"].mean()
    return 100 * g / base


def hero_calendar(c: pd.DataFrame, mode: str) -> None:
    with theme.use(mode) as p:
        fig, ax = plt.subplots(figsize=(10, 5.6))
        fig.subplots_adjust(left=0.07, right=0.80, top=0.80, bottom=0.14)
        c = c.loc["2021-01":]
        t = pd.PeriodIndex(c.index, freq="M").to_timestamp()
        ax.plot(t, c.fr, color=p.control, lw=1.8)
        ax.plot(t, c.treated, color=p.treated, lw=2.6)
        theme.event(ax, pd.Timestamp("2022-11-30"), "ChatGPT")
        theme.event(ax, pd.Timestamp("2024-05-14"), "AI Overviews rollout",
                    span_end=pd.Timestamp("2025-06-30"))  # fmt: skip
        theme.event(ax, pd.Timestamp("2025-04-01"), "bot reclassification", y=0.88)
        theme.label_end(ax, t[-1], c.treated.iloc[-1], "8 editions with AI Overviews", p.treated)
        theme.label_end(ax, t[-1], c.fr.iloc[-1], "French (mostly not yet)", p.control)
        ax.axhline(100, color=p.ink_muted, lw=0.6)
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.set_ylabel("Search arrivals, seasonally adjusted (Aug 2023-Jul 2024 = 100)")
        theme.title(fig, "Search traffic fell everywhere, a little more where AI Overviews "
                    "launched", "Seasonally adjusted, 3-month average; French is the "
                    "comparison edition")  # fmt: skip
        theme.source(fig, SOURCE)
        theme.save(fig, "hero_calendar")


def estimates() -> pd.DataFrame:
    a = pd.read_csv(QA / "p17_att.csv").query("estimator == \"Callaway-Sant'Anna\"")
    a = a.set_index("window")
    p18 = pd.read_csv(QA / "p18_twfe.csv").set_index("spec")
    p19 = pd.read_csv(QA / "p19_estimates.csv")
    p19 = p19[(p19.outcome == "search") & (p19.weights == "weighted")].set_index("editions")
    r = pd.read_csv(QA / "p20_robustness.csv")
    r = r[~r.group.isin(["placebo", "negative control"]) & r.pct.notna()
          & ~r.spec.str.startswith("Rambachan")]  # fmt: skip
    rows = [("Staggered DiD, first 6 months (primary)", pct(a.theta["primary"]),
             pct(a.ri_lo95["primary"]), pct(a.ri_hi95["primary"]), "pre-registered"),
            ("Staggered DiD, to 2026-07", pct(a.theta["full"]), pct(a.ri_lo95["full"]),
             pct(a.ri_hi95["full"]), "pre-registered"),
            ("Dose-response, full exposure", p18.pct_full["9 editions (P17 set)"],
             p18.pct_lo["9 editions (P17 set)"], p18.pct_hi["9 editions (P17 set)"], "exploratory"),
            ("Same topic across languages", p19.pct["10 editions, no fa"],
             p19.pct_lo["10 editions, no fa"], p19.pct_hi["10 editions, no fa"], "exploratory"),
            (f"{len(r)} robustness variants, both windows (range)", np.nan, r.pct.min(),
             r.pct.max(), "range")]
    return pd.DataFrame(rows, columns=["label", "pct", "lo", "hi", "status"])


def hero_estimates(est: pd.DataFrame, mode: str) -> None:
    with theme.use(mode) as p:
        fig, ax = plt.subplots(figsize=(10, 5.6))
        fig.subplots_adjust(left=0.36, right=0.96, top=0.80, bottom=0.16)
        ax.axvspan(-5, 5, color=p.band, alpha=0.35, lw=0)
        ax.text(0, -0.75, "smaller than ±5%:\nnot substantively meaningful", ha="center",
                va="top", fontsize=8.5, color=p.ink_muted)  # fmt: skip
        ax.axvline(0, color=p.ink_muted, lw=0.8)
        for i, r in est.iterrows():
            if r.status == "range":
                ax.plot([r.lo, r.hi], [i, i], color=p.counterfactual, lw=6, alpha=0.5,
                        solid_capstyle="butt")  # fmt: skip
                continue
            c = p.treated if r.status == "pre-registered" else p.control
            ax.plot([r.lo, r.hi], [i, i], color=c, lw=2)
            ax.plot(r.pct, i, "o", color=c, ms=9, mec=p.surface, mew=2)
            ax.text(r.hi + 1, i, f"{r.pct:+.0f}%", va="center", fontsize=9.5, color=p.ink)
        ax.set_yticks(range(len(est)), est.label)
        ax.set_ylim(len(est) - 0.4, -1.3)
        ax.grid(axis="y", visible=False)
        ax.grid(axis="x", visible=True)
        ax.set_xlabel("Effect of AI Overviews on Wikipedia search arrivals, % (95% interval)")
        ax.plot([], [], "o-", color=p.treated, label="pre-registered")
        ax.plot([], [], "o-", color=p.control, label="exploratory")
        ax.legend(loc="upper left", bbox_to_anchor=(0.0, 1.02), ncol=2)
        theme.title(fig, "The longer-run designs point to a loss of about 10%; none is conclusive",
                    "Estimated effect of AI Overviews on search arrivals; every interval crosses "
                    "zero")  # fmt: skip
        theme.source(fig, SOURCE)
        theme.save(fig, "hero_estimates")


def main() -> None:
    es, cal, est = event_paths(), calendar(), estimates()
    es.round(5).to_csv(QA / "p26_hero_event.csv", index=False)
    cal.round(3).to_csv(QA / "p26_hero_calendar.csv")
    est.round(3).to_csv(QA / "p26_hero_estimates.csv", index=False)
    for mode in ("light", "dark"):
        hero_event(es, mode)
        hero_calendar(cal, mode)
        hero_estimates(est, mode)


if __name__ == "__main__":
    main()
