"""P25 AI Overviews vs chatbots: decomposing the decline since ChatGPT (E1, exploratory).

Change in log search arrivals from the 12 months before ChatGPT (2021-12..2022-11) to the latest
12 months (2025-10..2026-09); 12-month sums, so seasonality cancels. For each edition l:

    total_l = pretrend_l + common + aio_l + bot_l + residual_l

  pretrend_l  the edition's own 2019-04..2022-11 trend (P14 model: month FE, COVID dummies, en
              step) extended over the 3.83 years between the window midpoints. Version B sets it to
              0, because that trend leans on the 2020 COVID peak; both versions are shown.
  aio_l       theta x (edition's mean exposure in the latest window / mean exposure of the treated
              editions), theta = the P17 full-window Callaway-Sant'Anna ATT (-8.0%, RI 95% -28% to
              +10%); P17 primary, P18 and P19 estimates are shown as alternatives.
  bot_l       measurement: the P16 spec C step at 2025-04 for English (-3.6%); for other editions
              it is not separately identified and stays inside `common` and the residual.
  common      the mean over the 9 P17 editions of (total - pretrend - aio): what every edition lost
              in the same months, i.e. the ChatGPT era, other AI search, generic search changes.
              Month fixed effects remove exactly this part in P17-P19.
  residual_l  what is left for edition l.

Intervals: Monte Carlo (20,000 draws): pre-trend slopes from their HAC intervals, theta from its
RI interval, the bot step from its HAC SE, `common` from a bootstrap over the 9 editions.

Also: English `other-external` and no-referrer shares over time (where chatbot referrals could
appear), and the share of the decline attributable to AI Overviews for English and for the 9
editions pooled. The pre-registered P16 ITS gap (-36%) is shown as an upper bound only.

Outputs: report/qa/p25_decomposition.csv, p25_aio_share.csv, p25_external.csv;
report/figures/p25_decomposition.png
"""

from __future__ import annotations

import duckdb
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from wao import config

QA, FIG = config.REPORT_DIR / "qa", config.REPORT_DIR / "figures"
EDS = ["en", "ja", "pt", "es", "de", "it", "pl", "zh", "fr"]
BASE, LATEST = ("2021-12", "2022-11"), ("2025-10", "2026-09")
YEARS = (pd.Period("2026-04", "M") - pd.Period("2022-06", "M")).n / 12  # window midpoints
DRAWS, SEED = 20_000, 25
if config.SAMPLE:  # make all SAMPLE=1 / CI: fewer draws
    DRAWS = 2_000


def _lse(lo_pct, hi_pct):
    """Normal SE on the log scale from a 95% interval in %."""
    return (np.log1p(hi_pct / 100) - np.log1p(lo_pct / 100)) / 3.92


def inputs() -> dict:
    d = duckdb.connect().execute(f"""
        select lang, month, search_arr, exposure, external_arr, empty_arr, total_arr
        from '{config.PANEL_DIR}/panel_lang_month.parquet' where core order by lang, month""").df()
    g = d.set_index(["lang", "month"])
    tot = {}
    for e in EDS:
        s = g.loc[e]
        tot[e] = np.log(s.loc[LATEST[0]:LATEST[1]].search_arr.sum() /
                        s.loc[BASE[0]:BASE[1]].search_arr.sum())  # fmt: skip
    xbar = {e: g.loc[e].loc[LATEST[0]:LATEST[1]].exposure.fillna(0).mean() for e in EDS}
    tm = pd.read_csv(QA / "p14_trend_models.csv").query("outcome == 'search'").set_index("lang")
    slope = {e: np.log1p(tm.pre_gpt[e] / 100) for e in EDS}
    slope_se = {e: _lse(tm.pre_gpt_lo[e], tm.pre_gpt_hi[e]) for e in EDS}
    p17 = pd.read_csv(QA / "p17_att.csv").query("estimator == \"Callaway-Sant'Anna\"")
    p17 = p17.set_index("window")
    th, th_se = p17.theta["full"], _lse(100 * (np.exp(p17.ri_lo95["full"]) - 1),
                                        100 * (np.exp(p17.ri_hi95["full"]) - 1))  # fmt: skip
    c = pd.read_csv(QA / "p16_its_coefs.csv")
    bot = c[(c.outcome == "search") & (c.spec == "C") & (c.term == "bot_step")].iloc[0]
    alt = {"P17 primary window (first 6 months)": p17.theta["primary"],
           "P17 full window": th,
           "P18 TWFE, 9 editions (x mean exposure)": None,
           "P19 within-concept, no fa (x mean exposure)": None}  # fmt: skip
    p18 = pd.read_csv(QA / "p18_twfe.csv").set_index("spec")
    p19 = pd.read_csv(QA / "p19_estimates.csv")
    p19 = p19[(p19.outcome == "search") & (p19.editions == "10 editions, no fa") &
              (p19.weights == "weighted")].iloc[0]  # fmt: skip
    treated_x = np.mean([xbar[e] for e in EDS if e != "fr"])
    alt["P18 TWFE, 9 editions (x mean exposure)"] = p18.beta["9 editions (P17 set)"] * treated_x
    alt["P19 within-concept, no fa (x mean exposure)"] = p19.beta * treated_x
    return dict(d=d, tot=tot, xbar=xbar, treated_x=treated_x, slope=slope, slope_se=slope_se,
                th=th, th_se=th_se, bot=bot.coef, bot_se=bot.se, alt=alt)  # fmt: skip


def decompose(inp: dict, with_trend: bool) -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    th = rng.normal(inp["th"], inp["th_se"], DRAWS)
    bot = rng.normal(inp["bot"], inp["bot_se"], DRAWS)
    pre = {e: (rng.normal(inp["slope"][e], inp["slope_se"][e], DRAWS) * YEARS if with_trend
               else np.zeros(DRAWS)) for e in EDS}  # fmt: skip
    aio = {e: th * inp["xbar"][e] / inp["treated_x"] for e in EDS}
    left = np.array([inp["tot"][e] - pre[e] - aio[e] for e in EDS])  # 9 x draws
    idx = rng.integers(0, len(EDS), (DRAWS, len(EDS)))
    common = left[idx, np.arange(DRAWS)[:, None]].mean(1)
    rows = []
    for e in EDS:
        b = bot if e == "en" else np.zeros(DRAWS)
        res = inp["tot"][e] - pre[e] - common - aio[e] - b
        for comp, v in (("total change", np.full(DRAWS, inp["tot"][e])), ("own pre-trend", pre[e]),
                        ("common to all editions (ChatGPT era etc.)", common),
                        ("AI Overviews", aio[e]), ("bot reclassification", b),
                        ("edition-specific residual", res)):  # fmt: skip
            rows.append(dict(trend="2019-04..2022-11 trend" if with_trend else "no pre-trend",
                             lang=e, component=comp, log=float(np.median(v)),
                             lo=float(np.percentile(v, 2.5)), hi=float(np.percentile(v, 97.5))))
    return pd.DataFrame(rows)


def aio_share(inp: dict) -> pd.DataFrame:
    """Share of the decline since 2022-11 attributable to AI Overviews, by estimate."""
    d = inp["d"]
    pooled = d[d.lang.isin([e for e in EDS if e != "fr"])].groupby("month").search_arr.sum()
    tot_pool = np.log(pooled.loc[LATEST[0]:LATEST[1]].sum() / pooled.loc[BASE[0]:BASE[1]].sum())
    rows = []
    for name, th in inp["alt"].items():
        for unit, total, scale in (("en", inp["tot"]["en"], inp["xbar"]["en"] / inp["treated_x"]),
                                   ("8 treated pooled", tot_pool, 1.0)):  # fmt: skip
            a = th * scale
            rows.append(dict(estimate=name, unit=unit, total_pct=100 * np.expm1(total),
                             aio_pct=100 * np.expm1(a), share_of_decline=a / total))  # fmt: skip
    lo, hi = inp["th"] - 1.96 * inp["th_se"], inp["th"] + 1.96 * inp["th_se"]
    rows.append(dict(estimate="P17 full window, RI 95% bounds", unit="8 treated pooled",
                     total_pct=100 * np.expm1(tot_pool), aio_pct=np.nan,
                     share_of_decline=np.nan, share_lo=hi / tot_pool, share_hi=lo / tot_pool))
    rows.append(dict(estimate="P16 ITS pre-registered (upper bound only)", unit="en",
                     total_pct=100 * np.expm1(inp["tot"]["en"]), aio_pct=-35.6,
                     share_of_decline=np.log(1 - 0.356) / inp["tot"]["en"]))  # fmt: skip
    return pd.DataFrame(rows)


def external(inp: dict) -> pd.DataFrame:
    d = inp["d"]
    e = d[d.lang == "en"].copy()
    e["external_share"] = e.external_arr / e.total_arr
    e["empty_share"] = e.empty_arr / e.total_arr
    e = e[e.month >= "2019-04"]  # clickstream method change (P11)
    return e[["month", "external_arr", "external_share", "empty_share"]]


def figure(dec: pd.DataFrame, share: pd.DataFrame, ext: pd.DataFrame) -> plt.Figure:
    fig, axes = plt.subplots(1, 3, figsize=(18, 5.8), gridspec_kw={"width_ratios": [1.3, 1, 1]})
    ax = axes[0]
    comps = ["own pre-trend", "common to all editions (ChatGPT era etc.)", "AI Overviews",
             "bot reclassification", "edition-specific residual"]  # fmt: skip
    for k, (tr, c) in enumerate((("no pre-trend", "#1f4e8c"), ("2019-04..2022-11 trend",
                                                               "#e6b85c"))):  # fmt: skip
        s = dec[(dec.lang == "en") & (dec.trend == tr)].set_index("component")
        total = s.loc["total change", "log"]
        y = np.arange(len(comps) + 1) + (k - 0.5) * 0.3
        vals = [s.loc[x, "log"] for x in comps] + [total]
        lo = [s.loc[x, "lo"] for x in comps] + [total]
        hi = [s.loc[x, "hi"] for x in comps] + [total]
        v = 100 * np.expm1(np.array(vals))
        ax.barh(y, v, height=0.28, color=c, label=tr)
        ax.errorbar(v, y, xerr=[v - 100 * np.expm1(lo), 100 * np.expm1(hi) - v], fmt="none",
                    ecolor="k", lw=0.8)  # fmt: skip
    ax.set_yticks(range(len(comps) + 1), comps + ["total change (observed)"], fontsize=8)
    ax.invert_yaxis()
    ax.axvline(0, color="#999999", lw=0.6)
    ax.set_xlabel("English search arrivals, % (2021-12..2022-11 → 2025-10..2026-09)")
    ax.legend(frameon=False, fontsize=8, loc="lower left")
    ax.set_title("Decomposition for English (95% Monte Carlo intervals)", loc="left", fontsize=10)
    ax = axes[1]
    s = share[share.share_of_decline.notna() & (share.unit == "8 treated pooled")]
    y = np.arange(len(s))
    ax.barh(y, 100 * s.share_of_decline, color="#1f4e8c", height=0.5)
    b = share[share.estimate.str.startswith("P17 full window, RI")].iloc[0]
    i = list(s.estimate).index("P17 full window")
    v = 100 * s.share_of_decline.iloc[i]
    ax.errorbar(v, i, xerr=[[v - 100 * b.share_lo], [100 * b.share_hi - v]], fmt="none",
                ecolor="k", lw=1, capsize=3, label="P17 full window, RI 95% range")  # fmt: skip
    ax.set_yticks(y, s.estimate, fontsize=8)
    ax.invert_yaxis()
    ax.axvline(0, color="#999999", lw=0.6)
    ax.axvline(100, color="#999999", lw=0.6, ls=":")
    ax.set_xlim(-100, 200)
    ax.set_xlabel("% of the decline since 2022-11 attributable to AI Overviews")
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    ax.set_title("8 treated editions pooled", loc="left", fontsize=10)
    ax = axes[2]
    t = pd.PeriodIndex(ext.month, freq="M").to_timestamp()
    ax.plot(t, 100 * ext.external_share, color="#c0392b", lw=1.4, label="other websites")
    ax2 = ax.twinx()
    ax2.plot(t, 100 * ext.empty_share, color="#999999", lw=1.2, label="no referrer (right axis)")
    for m, txt in (("2022-12", "ChatGPT"), ("2024-10", "ChatGPT search"), ("2024-05", "AIO US")):
        x = pd.Period(m, "M").to_timestamp()
        ax.axvline(x, color="k", lw=0.6, ls="--")
        ax.text(x, 0.98, txt, transform=ax.get_xaxis_transform(), fontsize=7, rotation=90,
                va="top", ha="right")  # fmt: skip
    ax.set_ylabel("% of arrivals from other websites")
    ax2.set_ylabel("% with no referrer")
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, frameon=False, fontsize=8, loc="lower left")
    ax.set_title("English: where chatbot referrals could show up", loc="left", fontsize=10)
    fig.suptitle("P25 AI Overviews vs chatbots (exploratory)", x=0.01, ha="left", fontsize=12,
                 fontweight="bold")  # fmt: skip
    fig.tight_layout()
    return fig


def main() -> dict:
    inp = inputs()
    dec = pd.concat([decompose(inp, False), decompose(inp, True)])
    share, ext = aio_share(inp), external(inp)
    dec.round(5).to_csv(QA / "p25_decomposition.csv", index=False)
    share.round(4).to_csv(QA / "p25_aio_share.csv", index=False)
    ext.round(5).to_csv(QA / "p25_external.csv", index=False)
    figure(dec, share, ext).savefig(FIG / "p25_decomposition.png", dpi=150, bbox_inches="tight")
    return dict(dec=dec, share=share, ext=ext, inp=inp)


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    r = main()
    x = r["dec"][r["dec"].lang == "en"].copy()
    for c in ("log", "lo", "hi"):
        x[c] = (100 * np.expm1(x[c])).round(1)
    print(x.to_string())
    print(r["share"].round(3).to_string())
