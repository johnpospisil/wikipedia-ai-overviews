"""P14 exploratory analysis (blinded). Called from notebooks/01_eda.ipynb.

Blinding (CLAUDE.md rule 6): per-language series and every cross-language contrast stop at
PRE_END (2024-04). Only two things run past it, and neither compares languages: the total of all
11 editions combined, and the English referral mix (one language, shares).

Outcomes come from panels/panel_lang_month.parquet (P13): clickstream search arrivals from 2019-04
(method break, P11) and `user` web views. The trend models are per language, on log monthly
values:
    y = month-of-year FE + t + (t - 2022-12)+ + shock dummies
Shock dummies: COVID 2020-03..05 (all), fa 2019-11 (Iran's week-long internet shutdown), and an en
step from 2020-05 (clickstream's automated class introduced; data_breaks.csv). HAC errors, 6 lags.

QA tables (report/qa/):
  p14_trend_models.csv     lang x outcome: annual trend before and after 2022-12 and the change
  p14_seasonal_month.csv   lang x month-of-year: seasonal factor of search arrivals (%)
  p14_weekday.csv          lang x access x weekday: 2023 daily views relative to the weekly mean
  p14_pretrends.csv        lang x window: trend of deseasonalised log search arrivals relative to
                           the leave-one-out mean of the other editions (excl. fa), with CI, and
                           the residual SD of that gap
Figures: report/figures/p14_*.png
"""

from __future__ import annotations

import duckdb
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm

from wao import config
from wao.viz.referral_mix import MIX

QA, FIG = config.REPORT_DIR / "qa", config.REPORT_DIR / "figures"
ORDER = ["en", "ja", "pt", "es", "de", "it", "pl", "zh", "fr", "ru", "fa"]
CONTROLS = ["fr", "ru", "fa"]
BASE = ("2019-04", "2020-03")
PRE_START, PRE_END, GPT = "2019-04", "2024-04", "2022-12"
WINDOWS = {"2019-04..2024-04": ("2019-04", PRE_END), "2022-12..2024-04": (GPT, PRE_END)}
COHORT_COLOUR = {"2024-09": "#1f4e8c", "2024-11": "#4f7cb8", "2025-04": "#8fa9cf",
                 "2025-06": "#b9c9e2", "2026-08": "#e6b85c", "never": "#c0392b"}  # fmt: skip
OUTCOMES = {"search": "Search arrivals", "share": "Search share", "views": "User web views"}


def _t(month: pd.Series) -> pd.Series:
    return pd.PeriodIndex(month, freq="M").to_timestamp()


def load() -> pd.DataFrame:
    d = duckdb.connect().execute(f"""
        select lang, month, role, cohort, cs_usable, search_arr, total_arr, search_share,
               views_desktop + views_mobile_web as views_web, views_desktop, views_mobile_web,
               views_app
        from '{config.PANEL_DIR}/panel_lang_month.parquet' where core order by lang, month""").df()
    d["t"] = _t(d.month)
    return d


def pre(d: pd.DataFrame) -> pd.DataFrame:
    """Usable clickstream months in the pre-period (the only window languages may be compared)."""
    return d[d.cs_usable & (d.month >= PRE_START) & (d.month <= PRE_END)].copy()


def indexed(d: pd.DataFrame, col: str) -> pd.Series:
    base = d[(d.month >= BASE[0]) & (d.month <= BASE[1])].groupby("lang")[col].mean()
    return 100 * d[col] / d.lang.map(base)


def _design(g: pd.DataFrame) -> pd.DataFrame:
    p = pd.PeriodIndex(g.month, freq="M")
    t = (p - pd.Period(PRE_START, "M")).map(lambda x: x.n) / 12
    tg = (pd.Period(GPT, "M") - pd.Period(PRE_START, "M")).n / 12
    X = pd.DataFrame({"const": 1.0, "t": t, "kink": np.maximum(t - tg, 0)}, index=g.index)
    for m in range(2, 13):
        X[f"m{m}"] = (p.month == m).astype(float)
    for m in ("2020-03", "2020-04", "2020-05"):
        X[f"d{m}"] = (g.month == m).astype(float)
    if (g.lang == "fa").all():
        X["d2019-11"] = (g.month == "2019-11").astype(float)
    if (g.lang == "en").all():
        X["en_auto"] = (g.month >= "2020-05").astype(float)
    return X


def _fit(y: pd.Series, X: pd.DataFrame):
    return sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": 6})


def trend_models(d: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per-language trend before and after 2022-12, and the deseasonalised log search series."""
    p, rows, des = pre(d), [], []
    p["share"], p["search"], p["views"] = p.search_share, p.search_arr, p.views_web
    for lang, g in p.groupby("lang"):
        X = _design(g)
        for out in OUTCOMES:
            y = np.log(g[out])
            r = _fit(y, X)
            post = r.params.t + r.params.kink
            se_post = np.sqrt(r.cov_params().loc["t", "t"] + r.cov_params().loc["kink", "kink"]
                              + 2 * r.cov_params().loc["t", "kink"])  # fmt: skip
            pct = lambda b: 100 * (np.exp(b) - 1)  # noqa: E731
            rows.append(dict(lang=lang, outcome=out,
                             pre_gpt=pct(r.params.t), pre_gpt_lo=pct(r.params.t - 1.96 * r.bse.t),
                             pre_gpt_hi=pct(r.params.t + 1.96 * r.bse.t),
                             post_gpt=pct(post), post_gpt_lo=pct(post - 1.96 * se_post),
                             post_gpt_hi=pct(post + 1.96 * se_post),
                             change_pp=pct(post) - pct(r.params.t), change_p=r.pvalues.kink,
                             resid_sd=r.resid.std(), n=len(g)))  # fmt: skip
            if out == "search":
                drop = [c for c in X if c.startswith(("m", "d", "en_"))]
                s = y - X[drop] @ r.params[drop]
                des.append(pd.DataFrame({"lang": lang, "month": g.month, "y": s}))
    return pd.DataFrame(rows), pd.concat(des)


def seasonal_month(d: pd.DataFrame) -> pd.DataFrame:
    p, rows = pre(d), []
    for lang, g in p.groupby("lang"):
        r = _fit(np.log(g.search_arr), _design(g))
        f = np.r_[0, [r.params[f"m{m}"] for m in range(2, 13)]]
        f = 100 * (np.exp(f - f.mean()) - 1)
        rows += [dict(lang=lang, moy=m, factor=f[m - 1]) for m in range(1, 13)]
    return pd.DataFrame(rows)


def weekday(year: str = "2023") -> pd.DataFrame:
    """Weighted sample daily `user` views (P06 weights) by weekday, relative to the weekly mean."""
    con = duckdb.connect()
    con.execute("set TimeZone='UTC'")
    d = con.execute(f"""
        select v.lang, v.access, v.date, sum(v.views * s.weight) views
        from read_parquet('{config.PARQUET_DIR}/pageview_daily/agent=user/*/part.parquet',
                          hive_partitioning=true) v
        join '{config.PANEL_DIR / "sample.parquet"}' s using (lang, page_id)
        where v.month like '{year}-%' group by all""").df()
    d["dow"] = pd.to_datetime(d.date).dt.day_of_week
    w = d.groupby(["lang", "access", "dow"]).views.mean().reset_index()
    w["rel"] = 100 * (w.views / w.groupby(["lang", "access"]).views.transform("mean") - 1)
    return w


def pretrends(des: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Each language's deseasonalised log search arrivals minus the leave-one-out mean of the
    other editions except fa (fa's own swings, +12%/yr, would otherwise tilt every comparison).

    Before 2024-05 only. Gap trend in %/yr with HAC CI, and the residual SD of the gap.
    """
    w = des.pivot(index="month", columns="lang", values="y")
    ref = [c for c in ORDER if c != "fa"]
    gap = pd.DataFrame({c: w[c] - w[[x for x in ref if x != c]].mean(axis=1) for c in ORDER})
    base = gap.loc[BASE[0]:BASE[1]].mean()
    gap = 100 * (np.exp(gap - base) - 1)
    rows = []
    for name, (a, b) in WINDOWS.items():
        g = np.log1p(gap.loc[a:b] / 100)
        t = np.arange(len(g)) / 12
        for c in ORDER:
            r = sm.OLS(g[c].values, sm.add_constant(t)).fit(cov_type="HAC", cov_kwds={"maxlags": 6})
            pct = lambda b: 100 * (np.exp(b) - 1)  # noqa: E731
            rows.append(dict(lang=c, window=name, slope=pct(r.params[1]),
                             lo=pct(r.params[1] - 1.96 * r.bse[1]),
                             hi=pct(r.params[1] + 1.96 * r.bse[1]), p=r.pvalues[1],
                             resid_sd_pct=100 * r.resid.std(), n=len(g)))  # fmt: skip
    return gap.reset_index().melt(id_vars="month", var_name="lang", value_name="gap_pct"), \
        pd.DataFrame(rows)


# ----------------------------------------------------------------------------------- figures


def _fmt_years(ax) -> None:
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%y"))


def _cohort(d: pd.DataFrame) -> pd.Series:
    return d.groupby("lang").cohort.first()


def fig_trends(d: pd.DataFrame) -> plt.Figure:
    p = d[(d.month >= PRE_START) & (d.month <= PRE_END)].copy()
    p["s"], p["v"] = indexed(p, "search_arr"), indexed(p, "views_web")
    coh = _cohort(d)
    fig, axes = plt.subplots(3, 4, figsize=(13, 8.5), sharex=False, sharey=True)
    for ax, lang in zip(axes.flat, ORDER + ["all"], strict=True):
        if lang == "all":
            a = d[d.cs_usable].groupby("month")[["search_arr", "views_web"]].sum().reset_index()
            a["lang"], a["t"] = "all", _t(a.month)
            a["s"], a["v"] = indexed(a, "search_arr"), indexed(a, "views_web")
            ax.plot(a.t, a.s, color="#1f4e8c", lw=1.8)
            ax.plot(a.t, a.v, color="#999999", lw=1.2)
            for m, lab in (("2022-12", "ChatGPT"), ("2024-05", "AIO US"), ("2025-04", "bot")):
                ax.axvline(pd.Period(m, "M").to_timestamp(), color="k", lw=0.6, ls="--")
                ax.text(pd.Period(m, "M").to_timestamp(), 141, lab, fontsize=7, ha="center")
            ax.set_title("All 11 combined (total, to 2026-09)", loc="left", fontsize=10)
            _fmt_years(ax)
            continue
        g = p[p.lang == lang]
        ax.plot(g.t, g.s, color=COHORT_COLOUR[coh[lang]], lw=1.8)
        ax.plot(g.t, g.v, color="#999999", lw=1.2)
        ax.axvline(pd.Period(GPT, "M").to_timestamp(), color="k", lw=0.6, ls="--")
        ax.set_title(f"{lang}  (cohort {coh[lang]})", loc="left", fontsize=10)
        _fmt_years(ax)
    for ax in axes.flat:
        ax.axhline(100, color="#cccccc", lw=0.6, zorder=0)
        ax.set_ylim(40, 150)
    axes[0, 0].plot([], [], color="#1f4e8c", lw=1.8, label="Search arrivals (clickstream)")
    axes[0, 0].plot([], [], color="#999999", lw=1.2, label="User web views (pageviews)")
    axes[0, 0].legend(loc="lower left", frameon=False, fontsize=8)
    fig.suptitle("Long-run trends, index 2019-04..2020-03 = 100. Editions shown to 2024-04 only "
                 "(blinded); the combined total runs to 2026-09", x=0.01, ha="left",
                 fontsize=12, fontweight="bold")  # fmt: skip
    fig.tight_layout()
    return fig


def fig_seasonality(sm_: pd.DataFrame, wd: pd.DataFrame) -> plt.Figure:
    fig, (a, b) = plt.subplots(1, 2, figsize=(14, 5.2), gridspec_kw={"width_ratios": [1.25, 1]})
    h = sm_.pivot(index="lang", columns="moy", values="factor").loc[ORDER]
    im = a.imshow(h.values, cmap="RdBu", vmin=-25, vmax=25, aspect="auto")
    a.set_xticks(range(12), list("JFMAMJJASOND"))
    a.set_yticks(range(len(ORDER)), ORDER)
    for i in range(h.shape[0]):
        for j in range(12):
            a.text(j, i, f"{h.values[i, j]:+.0f}", ha="center", va="center", fontsize=7)
    fig.colorbar(im, ax=a, shrink=0.8, label="% vs annual mean")
    a.set_title("Month-of-year factor, search arrivals (2019-04..2024-04)", loc="left", fontsize=10)
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for acc, ls in (("desktop", "-"), ("mobile-web", "--")):
        for lang in ORDER:
            g = wd[(wd.lang == lang) & (wd.access == acc)].sort_values("dow")
            b.plot(g.dow, g.rel, ls=ls, lw=1, color="#1f4e8c" if acc == "desktop" else "#c0392b",
                   alpha=0.7)  # fmt: skip
            if acc == "desktop":
                b.text(6.1, g.rel.iloc[-1], lang, fontsize=7, va="center")
    b.plot([], [], color="#1f4e8c", label="desktop")
    b.plot([], [], color="#c0392b", ls="--", label="mobile web")
    b.legend(frameon=False, fontsize=8)
    b.set_xticks(range(7), days)
    b.axhline(0, color="#cccccc", lw=0.6)
    b.set_ylabel("% vs weekly mean")
    b.set_title("Weekday profile of user views, 2023 (weighted sample)", loc="left", fontsize=10)
    fig.suptitle("Seasonality: academic calendars and the working week", x=0.01, ha="left",
                 fontsize=12, fontweight="bold")  # fmt: skip
    fig.tight_layout()
    return fig


def fig_pretrends(gap: pd.DataFrame, pt: pd.DataFrame, coh: pd.Series) -> plt.Figure:
    fig, (a, b) = plt.subplots(1, 2, figsize=(14, 5.5), gridspec_kw={"width_ratios": [1.5, 1]})
    gap = gap.assign(t=_t(gap.month))
    for lang in ORDER:
        g = gap[gap.lang == lang]
        a.plot(g.t, g.gap_pct, color=COHORT_COLOUR[coh[lang]], lw=2 if lang in CONTROLS else 1.2,
               ls="--" if lang in CONTROLS else "-")  # fmt: skip
        a.text(g.t.iloc[-1] + pd.Timedelta(days=20), g.gap_pct.iloc[-1], lang, fontsize=7,
               va="center", color=COHORT_COLOUR[coh[lang]])  # fmt: skip
    a.axhline(0, color="#999999", lw=0.6)
    a.axvline(pd.Period(GPT, "M").to_timestamp(), color="k", lw=0.6, ls="--")
    _fmt_years(a)
    a.set_ylabel("% gap, deseasonalised (base 2019-04..2020-03 = 0)")
    a.set_title("Search arrivals relative to the mean of the other editions (excl. fa), "
                "pre-period only\ncontrols dashed", loc="left", fontsize=10)  # fmt: skip
    y = np.arange(len(ORDER))
    w0, w1 = WINDOWS
    for k, (w, off, mk) in enumerate(((w0, -0.17, "o"), (w1, 0.17, "s"))):
        s = pt[pt.window == w].set_index("lang").loc[ORDER]
        b.errorbar(s.slope, y + off, xerr=[s.slope - s.lo, s.hi - s.slope], fmt=mk, ms=4,
                   color=["#1f4e8c", "#c0392b"][k], lw=1, label=w)  # fmt: skip
    b.axvline(0, color="#999999", lw=0.6)
    b.set_yticks(y, ORDER)
    b.invert_yaxis()
    b.set_xlabel("Gap trend, %/yr (95% CI, HAC)")
    b.legend(frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=2)
    b.set_title("Differential pre-trend by window", loc="left", fontsize=10)
    fig.suptitle("How parallel were the languages before 2024-05?", x=0.01, ha="left",
                 fontsize=12, fontweight="bold")  # fmt: skip
    fig.tight_layout()
    return fig


def fig_referral_mix_en() -> plt.Figure:
    src = config.PARQUET_DIR / "clickstream_lang_month.parquet"
    cs = duckdb.connect().execute(f"select * from '{src}' where lang = 'en' order by month").df()
    cs["t"] = _t(cs.month)
    d = cs.set_index("t")
    shares = d[[k for k, _, _ in MIX]].div(d.total, axis=0).fillna(0)
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.stackplot(shares.index, *[shares[k] for k, _, _ in MIX], labels=[x for _, x, _ in MIX],
                 colors=[c for _, _, c in MIX], lw=0)  # fmt: skip
    marks = [("2019-04", "method change"), ("2020-05", "automated class"), ("2022-12", "ChatGPT"),
             ("2024-05", "AIO US"), ("2025-04", "short month + bot reclass")]  # fmt: skip
    for m, lab in marks:
        x = pd.Period(m, "M").to_timestamp()
        ax.axvline(x, color="k", lw=0.7, ls="--")
        ax.text(x, 1.01, lab, ha="center", fontsize=7)
    ax.axvspan(shares.index.min(), pd.Timestamp("2019-04-01"), color="white", alpha=0.45)
    ax.set_ylim(0, 1)
    ax.set_xlim(shares.index.min(), shares.index.max())
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    _fmt_years(ax)
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), frameon=False, fontsize=9)
    ax.set_title("English referral mix 2017-11..2026-09 (descriptive; faded = before the 2019-04 "
                 "method change)", loc="left", fontsize=11, fontweight="bold", pad=18)  # fmt: skip
    fig.tight_layout()
    return fig


def fig_chatgpt(tm: pd.DataFrame) -> plt.Figure:
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.8), sharey=True)
    y = np.arange(len(ORDER))
    for ax, (out, lab) in zip(axes, OUTCOMES.items(), strict=True):
        s = tm[tm.outcome == out].set_index("lang").loc[ORDER]
        for i, (a, b) in enumerate(zip(s.pre_gpt, s.post_gpt, strict=True)):
            ax.annotate("", xy=(b, i), xytext=(a, i),
                        arrowprops=dict(arrowstyle="->", color="#999999", lw=1))  # fmt: skip
        ax.errorbar(s.pre_gpt, y, xerr=[s.pre_gpt - s.pre_gpt_lo, s.pre_gpt_hi - s.pre_gpt],
                    fmt="o", color="#8fa9cf", ms=4, lw=0.8, label="2019-04..2022-11")  # fmt: skip
        ax.errorbar(s.post_gpt, y, xerr=[s.post_gpt - s.post_gpt_lo, s.post_gpt_hi - s.post_gpt],
                    fmt="o", color="#1f4e8c", ms=5, lw=0.8, label="2022-12..2024-04")  # fmt: skip
        ax.axvline(0, color="#999999", lw=0.6)
        ax.set_title(lab, loc="left", fontsize=10)
        ax.set_xlabel("Trend, %/yr (95% CI, HAC; seasonality removed)")
    axes[0].set_yticks(y, ORDER)
    axes[0].invert_yaxis()
    axes[0].legend(frameon=False, fontsize=8, loc="lower left")
    fig.suptitle("The ChatGPT era: trend before vs after 2022-12, every edition, pre-period only",
                 x=0.01, ha="left", fontsize=12, fontweight="bold")  # fmt: skip
    fig.tight_layout()
    return fig


def main() -> dict:
    QA.mkdir(parents=True, exist_ok=True)
    d = load()
    tm, des = trend_models(d)
    sm_, wd = seasonal_month(d), weekday()
    gap, pt = pretrends(des)
    tm.round(4).to_csv(QA / "p14_trend_models.csv", index=False)
    sm_.round(3).to_csv(QA / "p14_seasonal_month.csv", index=False)
    wd.round(3).to_csv(QA / "p14_weekday.csv", index=False)
    pt.round(4).to_csv(QA / "p14_pretrends.csv", index=False)
    coh = _cohort(d)
    figs = {"p14_trends": fig_trends(d), "p14_seasonality": fig_seasonality(sm_, wd),
            "p14_pretrends": fig_pretrends(gap, pt, coh), "p14_referral_mix_en":
            fig_referral_mix_en(), "p14_chatgpt_era": fig_chatgpt(tm)}  # fmt: skip
    for name, f in figs.items():
        f.savefig(FIG / f"{name}.png", dpi=150, bbox_inches="tight")
    return dict(d=d, tm=tm, sm=sm_, wd=wd, gap=gap, pt=pt, figs=figs)


if __name__ == "__main__":
    main()
