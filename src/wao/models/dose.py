"""P18 dose-response (PREREGISTRATION.md 5.3; supporting estimator).

Outcome as in P17 (log search arrivals minus pre-period month-of-year effects), now for all 11
core editions, 2019-04..2026-07; 2025-04 (short clickstream month) dropped for every edition, so
the panel is balanced. Exposure = the P03 continuous dose (0..1); partly exposed months (en
2024-05..08 at 0.21-0.48, es 2024-08..10, de/it/pl 2025-03, fr from 2025-04, ru and fa from
2025-05) enter at their actual dose instead of being forced into treated or untreated.

  1. TWFE: y = edition FE + month FE + beta * exposure. beta = the effect of going from 0 to full
     exposure. Inference: wild cluster bootstrap by edition (Webb, 9,999 draws; 95% interval by
     test inversion) and randomization inference permuting whole exposure paths across editions
     (9,999 draws). Specs: 11 editions (pre-registered), 9 editions (P17's set), 11 editions to
     2025-02 (P17's primary window), exposure for all users (no sign-in limit), and without fa
     (exploratory, added after seeing its weight: Iran's 2025-26 shutdowns).
  2. Binned dose: exposure bins (0, .25], (.25, .5], (.5, .75], (.75, 1] instead of the line.
  3. Imputation (Borusyak-Jaravel-Spiess): edition and month FE fitted on unexposed cells only, so
     no exposed cell is ever used as a control; tau = y - y(0) for exposed cells, averaged by bin
     and regressed on exposure. Possible only to 2025-04 (from 2025-05 every edition has some
     exposure, so later month effects are not identified without a dose model).
  4. TWFE weights (de Chaisemartin-D'Haultfoeuille): share of exposed cells that get a negative
     weight in beta.
  5. Event study by dose group (high: max exposure >= 0.85; ja 0.77; low: fr, ru, fa < 0.5),
     quarters since first exposure, edition and month FE, reference quarter -1.

Outputs: report/qa/p18_twfe.csv, p18_bins.csv, p18_weights.csv, p18_event_study.csv;
report/figures/p18_dose_response.png
"""

from __future__ import annotations

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyfixest as pf

from wao import config
from wao.models import did

QA, FIG = config.REPORT_DIR / "qa", config.REPORT_DIR / "figures"
EDS11 = did.EDS + ["ru", "fa"]
END, SHORT = "2026-07", "2025-04"
BINS = [0, 0.25, 0.5, 0.75, 1.0]
REPS, SEED = 9_999, 18
if config.SAMPLE:  # make all SAMPLE=1 / CI: fewer draws
    REPS = 999
GRID = np.round(np.arange(-0.8, 1.001, 0.005), 3)
HIGH, LOW = 0.85, 0.5


def data() -> pd.DataFrame:
    d = duckdb.connect().execute(f"""
        select l.lang, l.month, l.search_arr_na, l.exposure, l.exposure_all_users,
               c.first_exposed
        from '{config.PANEL_DIR}/panel_lang_month.parquet' l
        join read_csv('{config.REFERENCE_DIR}/language_cohorts.csv') c on c.wiki = l.lang
        where l.lang in ({",".join(f"'{e}'" for e in EDS11)})
          and l.month between '{did.START}' and '{END}' and l.month <> '{SHORT}'
        order by l.lang, l.month""").df()
    s = did.seasonal(d)
    d["moy"] = pd.PeriodIndex(d.month, freq="M").month
    d = d.merge(s, on=["lang", "moy"])
    d["y"] = np.log(d.search_arr_na) - d.s
    for c in ("exposure", "exposure_all_users"):
        d[c] = d[c].fillna(0.0)
    return d.sort_values(["lang", "month"]).reset_index(drop=True)


def _demean(M: np.ndarray) -> np.ndarray:
    return M - M.mean(1, keepdims=True) - M.mean(0, keepdims=True) + M.mean()


def beta(Y: np.ndarray, X: np.ndarray) -> float:
    xt = _demean(X)
    return float((xt * Y).sum() / (xt**2).sum())


def _wcb_p(Y: np.ndarray, X: np.ndarray, r: float, V: np.ndarray) -> float:
    """Restricted wild cluster bootstrap (WCR, clusters = editions) p-value for beta = r.

    Balanced panel, so the two-way FE are removed by demeaning (FWL). Under the null the
    restricted residuals are the demeaned y - r*x; each edition's residuals are multiplied by its
    Webb weight, beta and its CRV1 t-statistic are recomputed, and p = share with |t*| >= |t|."""
    G = Y.shape[0]
    xt, u = _demean(X), _demean(Y - r * X)
    sxx = (xt**2).sum()

    def tstats(Ys):  # Ys: (B, G, T) demeaned outcomes, centred on the null
        b = np.einsum("bgt,gt->b", Ys, xt) / sxx
        res = Ys - b[:, None, None] * xt[None]
        score = np.einsum("bgt,gt->bg", res, xt)
        se = np.sqrt((score**2).sum(1) * G / (G - 1)) / sxx
        return b / se

    t0 = tstats((_demean(Y) - r * xt)[None])[0]
    ts = tstats(V[:, :, None] * u[None])
    return float((np.abs(ts) >= abs(t0) - 1e-12).mean())


def wcb(Y: np.ndarray, X: np.ndarray) -> dict:
    """WCB p for beta = 0 and a 95% interval by test inversion over GRID."""
    V = did.webb(Y.shape[0], REPS, SEED)
    keep = [r for r in GRID if _wcb_p(Y, X, r, V) >= 0.05]
    return dict(beta=beta(Y, X), wcb_p=_wcb_p(Y, X, 0.0, V),
                wcb_lo=min(keep) if keep else np.nan, wcb_hi=max(keep) if keep else np.nan)


def ri(Y: np.ndarray, X: np.ndarray) -> float:
    rng = np.random.default_rng(SEED)
    b0 = beta(Y, X)
    null = np.array([beta(Y, X[rng.permutation(len(X))]) for _ in range(REPS)])
    return float(((np.abs(null) >= abs(b0) - 1e-12).sum() + 1) / (REPS + 1))


def twfe(d: pd.DataFrame) -> pd.DataFrame:
    specs = {"11 editions (pre-registered)": (EDS11, END, "exposure"),
             "9 editions (P17 set)": (did.EDS, END, "exposure"),
             "11 editions to 2025-02": (EDS11, "2025-02", "exposure"),
             "11 editions, exposure all users": (EDS11, END, "exposure_all_users"),
             "10 editions, no fa (exploratory)": ([e for e in EDS11 if e != "fa"], END,
                                                  "exposure")}  # fmt: skip
    rows = []
    for name, (eds, end, xcol) in specs.items():
        s = d[d.lang.isin(eds) & (d.month <= end)]
        Y = s.pivot(index="lang", columns="month", values="y").values
        X = s.pivot(index="lang", columns="month", values=xcol).values
        fit = pf.feols(f"y ~ {xcol} | lang + month", data=s, vcov={"CRV1": "lang"})
        w = wcb(Y, X)
        b = w["beta"]
        assert np.isclose(b, float(fit.coef()[xcol]))
        w["crv1_se"] = float(fit.se()[xcol])
        rows.append(dict(spec=name, n_editions=len(eds), end=end, **w, ri_p=ri(Y, X),
                         pct_full=100 * (np.exp(b) - 1),
                         pct_lo=100 * (np.exp(w["wcb_lo"]) - 1),
                         pct_hi=100 * (np.exp(w["wcb_hi"]) - 1)))  # fmt: skip
    return pd.DataFrame(rows)


def _bin(x: pd.Series) -> pd.Series:
    lab = pd.cut(x, BINS, labels=[f"({a:g}, {b:g}]" for a, b in zip(BINS, BINS[1:], strict=False)])
    return lab.astype(str).where(x > 0, "0")


def binned(d: pd.DataFrame) -> pd.DataFrame:
    d = d.assign(bin=_bin(d.exposure))
    rows = []
    fit = pf.feols("y ~ i(bin, ref='0') | lang + month", data=d, vcov={"CRV1": "lang"})
    ct = fit.tidy()
    for name, r in ct.iterrows():
        b = name.split("::", 1)[1]
        rows.append(dict(method="TWFE bins", bin=b, est=r.Estimate, lo=r["2.5%"], hi=r["97.5%"],
                         n=int((d.bin == b).sum())))  # fmt: skip
    # imputation, months where some edition is unexposed
    months = d.groupby("month").exposure.min()
    ok_m = months[months == 0].index
    s = d[d.month.isin(ok_m)].copy()
    un = s[s.exposure == 0]
    f0 = pf.feols("y ~ 1 | lang + month", data=un)
    fe = f0.fixef()
    a = pd.Series(fe["C(lang)"])
    lam = pd.Series(fe["C(month)"])
    ex = s[s.exposure > 0].copy()
    ex["tau"] = ex.y - ex.lang.map(a) - ex.month.map(lam)
    for b, g in ex.groupby("bin"):
        rows.append(dict(method="imputation bins", bin=b, est=g.tau.mean(), lo=np.nan,
                         hi=np.nan, n=len(g)))  # fmt: skip
    slope = float((ex.tau * ex.exposure).sum() / (ex.exposure**2).sum())
    rows.append(dict(method="imputation slope (to 2025-04)", bin="per unit exposure", est=slope,
                     lo=np.nan, hi=np.nan, n=len(ex)))  # fmt: skip
    return pd.DataFrame(rows)


def weights(d: pd.DataFrame) -> dict:
    Y = d.pivot(index="lang", columns="month", values="y").values
    X = d.pivot(index="lang", columns="month", values="exposure").values
    xt = _demean(X)
    w = xt * X / (xt * X).sum()  # weights on exposed cells' effects (dCDH, continuous)
    ex = X > 0
    neg = ex & (w < 0)
    return dict(exposed_cells=int(ex.sum()), negative_cells=int(neg.sum()),
                negative_weight_sum=float(w[neg].sum()), beta=beta(Y, X),
                negative_by_edition=", ".join(f"{e}:{n}" for e, n in
                                              zip(sorted(d.lang.unique()), neg.sum(1),
                                                  strict=True) if n))  # fmt: skip


def event_study(d: pd.DataFrame) -> pd.DataFrame:
    mx = d.groupby("lang").exposure.max()
    grp = np.where(mx >= HIGH, "high", np.where(mx < LOW, "low", "mid"))
    d = d.assign(group=d.lang.map(dict(zip(mx.index, grp, strict=True))))
    fe = pd.PeriodIndex(d.first_exposed, freq="M")
    e = (pd.PeriodIndex(d.month, freq="M") - fe).map(lambda x: x.n)
    d["q"] = np.clip(np.floor(np.asarray(e) / 3), -8, 6).astype(int)
    d["gq"] = d.group + "_" + d.q.astype(str)
    refs = [f"{g}_-1" for g in ("high", "mid", "low")]
    d.loc[d.gq.isin(refs), "gq"] = "ref"
    fit = pf.feols("y ~ i(gq, ref='ref') | lang + month", data=d, vcov={"CRV1": "lang"})
    rows = []
    for name, r in fit.tidy().iterrows():
        g, q = name.split("::", 1)[1].split("_")
        rows.append(dict(group=g, quarter=int(q), est=r.Estimate, lo=r["2.5%"], hi=r["97.5%"]))
    for g in ("high", "mid", "low"):
        rows.append(dict(group=g, quarter=-1, est=0.0, lo=0.0, hi=0.0))
    return pd.DataFrame(rows).sort_values(["group", "quarter"])


def figure(tw, bins, es, p17) -> plt.Figure:
    pct = lambda v: 100 * (np.exp(v) - 1)  # noqa: E731
    fig, axes = plt.subplots(1, 3, figsize=(19, 5.6), gridspec_kw={"width_ratios": [1, 1.1, 0.75]})
    ax = axes[0]
    b0 = tw.iloc[0]
    xs = np.linspace(0, 1, 50)
    ax.plot(xs, pct(b0.beta * xs), color="#1f4e8c", lw=1.5, label="TWFE line (11 editions)")
    ax.fill_between(xs, pct(b0.wcb_lo * xs), pct(b0.wcb_hi * xs), color="#1f4e8c", alpha=0.12,
                    lw=0)  # fmt: skip
    nf = tw[tw.spec.str.startswith("10 editions")].iloc[0]
    ax.plot(xs, pct(nf.beta * xs), color="#1f4e8c", lw=1.5, ls="--", label="TWFE line, no fa")
    mids = {"(0, 0.25]": 0.125, "(0.25, 0.5]": 0.375, "(0.5, 0.75]": 0.625, "(0.75, 1]": 0.875}
    t = bins[bins.method == "TWFE bins"]
    ax.errorbar([mids[b] for b in t.bin], pct(t.est), yerr=[pct(t.est) - pct(t.lo),
                pct(t.hi) - pct(t.est)], fmt="o", color="#c0392b", ms=5, lw=1,
                label="TWFE bins (CRV1 95%)")  # fmt: skip
    m = bins[bins.method == "imputation bins"]
    ax.plot([mids[b] + 0.02 for b in m.bin], pct(m.est), "s", color="#e6b85c", ms=6,
            label="imputation bins (to 2025-04)")  # fmt: skip
    ax.axhline(0, color="#999999", lw=0.6)
    ax.set_xlabel("AI Overviews exposure (share of readers)")
    ax.set_ylabel("Search arrivals vs unexposed, %")
    ax.legend(frameon=False, fontsize=8, loc="lower left")
    ax.set_title("Dose-response (band: WCB 95%, 11 editions)", loc="left", fontsize=10)
    ax = axes[1]
    for g, c in (("high", "#1f4e8c"), ("mid", "#e6b85c"), ("low", "#c0392b")):
        s = es[es.group == g]
        off = {"high": -0.15, "mid": 0, "low": 0.15}[g]
        ax.errorbar(s.quarter + off, pct(s.est), yerr=[pct(s.est) - pct(s.lo),
                    pct(s.hi) - pct(s.est)], fmt="o-", ms=3.5, lw=0.9, color=c,
                    label={"high": "high dose (≥0.85: en es pt de it pl zh)", "mid": "ja (0.77)",
                           "low": "low dose (fr ru fa < 0.5)"}[g])  # fmt: skip
    ax.axhline(0, color="#999999", lw=0.6)
    ax.axvline(-0.5, color="k", lw=0.6, ls="--")
    ax.set_xlabel("Quarters since first exposure (ends binned)")
    ax.set_ylabel("%")
    ax.legend(frameon=False, fontsize=8, loc="lower left")
    ax.set_title("Event study by dose group (TWFE, CRV1 95%)", loc="left", fontsize=10)
    ax = axes[2]
    rows = [(r.spec, r.pct_full, r.pct_lo, r.pct_hi) for r in tw.itertuples()]
    rows += [(f"P17 CS {w} (ATT, not per unit dose)", pct(r.theta), pct(r.ri_lo95), pct(r.ri_hi95))
             for w, r in p17.iterrows()]  # fmt: skip
    y = np.arange(len(rows))
    v = np.array([r[1] for r in rows])
    ax.errorbar(v, y, xerr=[v - np.array([r[2] for r in rows]), np.array([r[3] for r in rows]) - v],
                fmt="o", color="#1f4e8c", ms=4, lw=1)  # fmt: skip
    ax.set_yticks(y, [r[0] for r in rows], fontsize=8)
    ax.invert_yaxis()
    ax.axvline(0, color="#999999", lw=0.6)
    ax.set_xlabel("Effect of full exposure, % (WCB 95%; P17: RI 95%)")
    ax.set_title("Specifications vs P17", loc="left", fontsize=10)
    fig.suptitle("P18 dose-response: log search arrivals on AI Overviews exposure", x=0.01,
                 ha="left", fontsize=12, fontweight="bold")  # fmt: skip
    fig.tight_layout()
    return fig


def main() -> dict:
    d = data()
    tw, bins = twfe(d), binned(d)
    w, es = weights(d), event_study(d)
    p17 = pd.read_csv(QA / "p17_att.csv").query("estimator == \"Callaway-Sant'Anna\"")
    p17 = p17.set_index("window")
    tw.round(5).to_csv(QA / "p18_twfe.csv", index=False)
    bins.round(5).to_csv(QA / "p18_bins.csv", index=False)
    pd.DataFrame([w]).to_csv(QA / "p18_weights.csv", index=False)
    es.round(5).to_csv(QA / "p18_event_study.csv", index=False)
    figure(tw, bins, es, p17).savefig(FIG / "p18_dose_response.png", dpi=150, bbox_inches="tight")
    return dict(tw=tw, bins=bins, w=w, es=es)


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    r = main()
    print(r["tw"].round(4).to_string())
    print(r["bins"].round(4).to_string())
    print(r["w"])
    print(r["es"].round(3).to_string())
