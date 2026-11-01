"""P16 English interrupted time series (PREREGISTRATION.md section 5.1; supporting estimator).

Log monthly English search arrivals (clickstream `other-search`, 2019-04..2026-09) and log search
share, regressed on
    trend + ChatGPT level and slope break (2022-12) + AI Overviews level and slope break (2024-05)
    + month-of-year dummies + nuisance dummies (COVID 2020-03..05; en clickstream step from 2020-05)
with HAC (Newey-West, 6 lags) errors. 2025-04 (short clickstream month) is missing.

The gap for a period is mean(actual) - mean(counterfactual), where the counterfactual is the fitted
model with the AI Overviews terms set to zero. Its SE is sqrt(a' V a), a = the period's mean of the
counterfactual design rows, so it carries the uncertainty of the extrapolated trend.

Specifications (A is the pre-registered one; the others are sensitivity checks):
  A  as above
  B  ChatGPT level break only (no slope change), so the 2019-04..2024-04 trend is extrapolated
  C  A + a step from 2025-04 (bot reclassification, P11)
  D  A with the AIO level/slope replaced by the continuous exposure (P03): the effect at full
     exposure, which allows for English being only partly treated at first (0.21 in 2024-05)
  E  A with 2025-04 rescaled by the AQS ratio instead of missing

Holdout: each spec without AIO terms, trained to 2023-04 and forecast for 2023-05..2024-04; and a
no-ChatGPT-break model trained to 2022-11 and forecast for 2022-12..2024-04.

Outputs: report/qa/p16_its_coefs.csv, p16_its_gaps.csv, p16_its_holdout.csv,
p16_its_diagnostics.csv; report/figures/p16_its_en.png
"""

from __future__ import annotations

import duckdb
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.stats.stattools import durbin_watson, jarque_bera

from wao import config

QA, FIG = config.REPORT_DIR / "qa", config.REPORT_DIR / "figures"
START, END, GPT, AIO, BOT = "2019-04", "2026-09", "2022-12", "2024-05", "2025-04"
PERIODS = {"2024-05..12": ("2024-05", "2024-12"), "2025": ("2025-01", "2025-12"),
           "2026-01..09": ("2026-01", "2026-09"), "all post": ("2024-05", "2026-09")}  # fmt: skip
SPECS = {"A": "pre-registered", "B": "no ChatGPT slope", "C": "+ bot step 2025-04",
         "D": "dose (exposure)", "E": "2025-04 rescaled"}  # fmt: skip
OUTCOMES = {"search": "log search arrivals", "share": "log search share"}
AIO_COLS = ["aio_level", "aio_slope", "exposure"]


def load(lang: str = "en") -> pd.DataFrame:
    d = duckdb.connect().execute(f"""
        select month, search_arr_na, search_arr_rs, search_share, exposure
        from '{config.PANEL_DIR}/panel_lang_month.parquet'
        where lang = '{lang}' and month between '{START}' and '{END}' order by month""").df()
    d["t"] = pd.PeriodIndex(d.month, freq="M").to_timestamp()
    return d


def _yrs(month: pd.Series, origin: str) -> np.ndarray:
    p = pd.PeriodIndex(month, freq="M")
    return np.array([(x - pd.Period(origin, "M")).n for x in p]) / 12


def design(d: pd.DataFrame, spec: str, aio: bool = True, gpt_slope: bool = True) -> pd.DataFrame:
    p = pd.PeriodIndex(d.month, freq="M")
    X = pd.DataFrame({"const": 1.0, "t": _yrs(d.month, START)}, index=d.index)
    X["gpt_level"] = (d.month >= GPT).astype(float)
    if gpt_slope and spec != "B":
        X["gpt_slope"] = np.maximum(_yrs(d.month, GPT), 0)
    if aio:
        if spec == "D":
            X["exposure"] = d.exposure.fillna(0)
        else:
            X["aio_level"] = (d.month >= AIO).astype(float)
            X["aio_slope"] = np.maximum(_yrs(d.month, AIO), 0)
    if spec == "C":
        X["bot_step"] = (d.month >= BOT).astype(float)
    for m in range(2, 13):
        X[f"m{m}"] = (p.month == m).astype(float)
    for m in ("2020-03", "2020-04", "2020-05"):
        X[f"d{m}"] = (d.month == m).astype(float)
    X["en_auto"] = (d.month >= "2020-05").astype(float)
    return X.loc[:, (X != 0).any()]


def outcome(d: pd.DataFrame, out: str, spec: str) -> pd.Series:
    if out == "share":
        y = np.log(d.search_share)
        return y if spec == "E" else y.where(d.month != BOT)
    return np.log(d.search_arr_rs if spec == "E" else d.search_arr_na)


def fit(y: pd.Series, X: pd.DataFrame):
    ok = y.notna()
    return sm.OLS(y[ok], X[ok]).fit(cov_type="HAC", cov_kwds={"maxlags": 6})


def counterfactual(X: pd.DataFrame) -> pd.DataFrame:
    return X.assign(**{c: 0.0 for c in AIO_COLS if c in X})


def gaps(y: pd.Series, X: pd.DataFrame, r, d: pd.DataFrame) -> list[dict]:
    Xc, V, rows = counterfactual(X), r.cov_params(), []
    for name, (a, b) in PERIODS.items():
        m = (d.month >= a) & (d.month <= b) & y.notna()
        av = Xc[m].mean()
        g = y[m].mean() - av @ r.params
        se = float(np.sqrt(av @ V @ av))
        pct = lambda v: 100 * (np.exp(v) - 1)  # noqa: E731
        rows.append(dict(period=name, months=int(m.sum()), gap_log=g, se=se, gap_pct=pct(g),
                         lo_pct=pct(g - 1.96 * se), hi_pct=pct(g + 1.96 * se)))  # fmt: skip
    return rows


def holdout(d: pd.DataFrame, out: str) -> list[dict]:
    rows = []
    cases = [(s, "2023-04", True) for s in ("A", "B")] + [("no ChatGPT break", "2022-11", False)]
    for spec, origin, gpt in cases:
        sp = spec if spec in SPECS else "B"
        X = design(d, sp, aio=False)
        if not gpt:
            X = X.drop(columns=[c for c in X if c.startswith("gpt")])
        y = outcome(d, out, sp)
        tr = (d.month <= origin) & y.notna()
        te = (d.month > origin) & (d.month <= "2024-04")
        cols = X.columns[(X[tr] != 0).any()]
        r = sm.OLS(y[tr], X.loc[tr, cols]).fit()
        e = y[te] - X.loc[te, cols] @ r.params
        rows.append(dict(outcome=out, spec=spec, train_to=origin, test=f"{d.month[te].min()}.."
                         f"{d.month[te].max()}", n_test=int(te.sum()),
                         bias_pct=100 * (np.exp(e.mean()) - 1),
                         mape_pct=100 * np.abs(np.exp(e) - 1).mean(),
                         rmse_log=float(np.sqrt((e**2).mean()))))  # fmt: skip
    return rows


def diagnostics(r, out: str, spec: str) -> dict:
    e = r.resid
    jb = jarque_bera(e)
    return dict(outcome=out, spec=spec, n=int(r.nobs), r2=r.rsquared, resid_sd=e.std(),
                durbin_watson=durbin_watson(e),
                ljungbox_p12=float(acorr_ljungbox(e, lags=[12]).lb_pvalue.iloc[0]),
                jarque_bera_p=float(jb[1]))  # fmt: skip


def run(d: pd.DataFrame) -> dict:
    coefs, gap_rows, diag, fits = [], [], [], {}
    for out in OUTCOMES:
        for spec in SPECS:
            X, y = design(d, spec), outcome(d, out, spec)
            r = fit(y, X)
            keep = [c for c in r.params.index if not c.startswith(("m", "d20"))]
            for c in keep:
                coefs.append(dict(outcome=out, spec=spec, term=c, coef=r.params[c],
                                  se=r.bse[c], p=r.pvalues[c]))  # fmt: skip
            gap_rows += [dict(outcome=out, spec=spec, **g) for g in gaps(y, X, r, d)]
            diag.append(diagnostics(r, out, spec))
            fits[(out, spec)] = (y, X, r)
    hold = [h for out in OUTCOMES for h in holdout(d, out)]
    return dict(coefs=pd.DataFrame(coefs), gaps=pd.DataFrame(gap_rows), diag=pd.DataFrame(diag),
                hold=pd.DataFrame(hold), fits=fits)  # fmt: skip


def _band(X: pd.DataFrame, r) -> tuple[pd.Series, pd.Series]:
    Xc = counterfactual(X)[r.params.index]
    mu = Xc @ r.params
    v = np.einsum("ij,jk,ik->i", Xc.values, r.cov_params().values, Xc.values)
    se = np.sqrt(np.clip(v, 0, None))  # dummy-only rows give -1e-19
    return mu, pd.Series(se, index=X.index)


def figure(d: pd.DataFrame, res: dict) -> plt.Figure:
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    scale = {"search": (1e9, "Search arrivals per month (bn)"), "share": (0.01, "Search share (%)")}
    for ax, out in zip(axes[0], OUTCOMES, strict=True):
        y, X, r = res["fits"][(out, "A")]
        mu, se = _band(X, r)
        k, lab = scale[out]
        post = d.month >= AIO
        ax.plot(d.t, np.exp(y) / k, color="#222222", lw=1.3, label="actual")
        ax.plot(d.t, np.exp(r.fittedvalues.reindex(d.index)) / k, color="#1f4e8c", lw=1,
                label="fitted (A)")  # fmt: skip
        ax.plot(d.t[post], np.exp(mu[post]) / k, color="#c0392b", lw=1.5, ls="--",
                label="counterfactual: no AI Overviews (A)")  # fmt: skip
        ax.fill_between(d.t[post], np.exp(mu - 1.96 * se)[post] / k,
                        np.exp(mu + 1.96 * se)[post] / k, color="#c0392b", alpha=0.15, lw=0)
        yb, Xb, rb = res["fits"][(out, "B")]
        mub, _ = _band(Xb, rb)
        ax.plot(d.t[post], np.exp(mub[post]) / k, color="#e6b85c", lw=1.3, ls=":",
                label="counterfactual (B: no ChatGPT slope)")  # fmt: skip
        top = ax.get_ylim()[1]
        for i, (m, txt) in enumerate(((GPT, "ChatGPT"), (AIO, "AIO US"), ("2024-09", "en ≥ 0.5"),
                                      (BOT, "bot reclass"))):  # fmt: skip
            x = pd.Period(m, "M").to_timestamp()
            ax.axvline(x, color="k", lw=0.6, ls="--")
            ax.text(x, top * (1 - 0.035 * (i % 2)), txt, fontsize=7, ha="right" if i == 1 else
                    "left", va="top", backgroundcolor="white")  # fmt: skip
        ax.set_ylabel(lab)
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.legend(frameon=False, fontsize=7, loc="lower left")
        ax.set_title(f"English: {OUTCOMES[out]}", loc="left", fontsize=10, pad=14)
    ax = axes[1, 0]
    g = res["gaps"][res["gaps"].outcome == "search"]
    per = list(PERIODS)
    cols = dict(zip(SPECS, ["#1f4e8c", "#e6b85c", "#8fa9cf", "#c0392b", "#999999"], strict=True))
    for i, spec in enumerate(SPECS):
        s = g[g.spec == spec].set_index("period").loc[per]
        yv = np.arange(len(per)) + (i - 2) * 0.13
        ax.errorbar(s.gap_pct, yv, xerr=[s.gap_pct - s.lo_pct, s.hi_pct - s.gap_pct], fmt="o",
                    ms=4, lw=1, color=cols[spec], label=f"{spec}: {SPECS[spec]}")  # fmt: skip
    ax.axvline(0, color="#999999", lw=0.6)
    ax.set_yticks(range(len(per)), per)
    ax.invert_yaxis()
    ax.set_xlabel("Gap vs counterfactual, % (95% CI, HAC)")
    ax.legend(frameon=False, fontsize=7, loc="lower left")
    ax.set_title("Search arrivals: gap by period and specification", loc="left", fontsize=10)
    ax = axes[1, 1]
    y, X, r = res["fits"][("search", "A")]
    ax.bar(d.t[y.notna()], r.resid, width=20, color="#8fa9cf")
    ax.axhline(0, color="#999999", lw=0.6)
    dg = res["diag"].query("outcome == 'search' and spec == 'A'").iloc[0]
    ax.set_title(f"Residuals, spec A (DW {dg.durbin_watson:.2f}, Ljung-Box p12 "
                 f"{dg.ljungbox_p12:.2f})", loc="left", fontsize=10)  # fmt: skip
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.suptitle("P16 English interrupted time series (supporting estimator; English is only "
                 "partly exposed until 2024-09)", x=0.01, ha="left", fontsize=12,
                 fontweight="bold")  # fmt: skip
    fig.tight_layout()
    return fig


def main() -> dict:
    d = load()
    res = run(d)
    res["coefs"].round(5).to_csv(QA / "p16_its_coefs.csv", index=False)
    res["gaps"].round(4).to_csv(QA / "p16_its_gaps.csv", index=False)
    res["hold"].round(4).to_csv(QA / "p16_its_holdout.csv", index=False)
    res["diag"].round(4).to_csv(QA / "p16_its_diagnostics.csv", index=False)
    figure(d, res).savefig(FIG / "p16_its_en.png", dpi=150, bbox_inches="tight")
    return res


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    r = main()
    print(r["gaps"].round(2).to_string())
    print(r["coefs"][r["coefs"].term.str.contains("aio|gpt|exposure|bot")].round(3).to_string())
    print(r["hold"].round(2).to_string())
    print(r["diag"].round(3).to_string())
