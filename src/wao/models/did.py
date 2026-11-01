"""P17 staggered difference-in-differences on the edition x month panel (PREREGISTRATION.md 2-4).

Outcome: log search arrivals minus the edition's month-of-year effects (P14 trend model, fitted on
2019-04..2024-04 only). Nine editions (ru and fa excluded). Two windows:
  primary  2019-04..2025-02, groups {en}, {ja, pt}, {es}; controls not yet exposed (de, it, pl, zh,
           fr have zero exposure throughout)
  full     2019-04..2026-07, all 8 treated editions; controls not yet treated (fr alone after
           2025-05, partly exposed); 2025-04 missing
Base month per group = last non-missing month before first exposure; partly exposed months between
first exposure and the cohort month are neither base nor post.

Estimators: Callaway-Sant'Anna (wao.models.csdid; decides), Sun-Abraham interaction-weighted and
Borusyak-Jaravel-Spiess imputation (cross-checks). Overall ATT = cohort aggregation (group-size
weights). Inference: exact randomization inference over all 30,240 assignments of the (cohort,
first exposure) label pairs (Sun-Abraham and BJS: the true one plus 3,000 random ones), a 95%
interval by inverting it under a constant additive effect, and
a multiplier (wild) bootstrap clustered by edition with Webb weights (reported, not deciding).
Pre-trends: mean absolute lead over the 12 months before the base, RI p; Rambachan-Roth
relative-magnitude bounds (identified-set version: the interval widened by the worst-case bias).

Outputs: report/qa/p17_att.csv, p17_att_gt.csv, p17_event_study.csv, p17_pretrend.csv,
p17_rr.csv, p17_h1.csv, p17_groups.csv, p17_by_edition.csv (exploratory);
report/figures/p17_event_study.png
"""

from __future__ import annotations

import duckdb
import matplotlib.dates as mdates  # noqa: F401
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from wao import config
from wao.models.csdid import NEVER, assignments, att_weights
from wao.viz import eda

QA, FIG = config.REPORT_DIR / "qa", config.REPORT_DIR / "figures"
EDS = ["en", "ja", "pt", "es", "de", "it", "pl", "zh", "fr"]
START, SHORT = "2019-04", "2025-04"
WINDOWS = {"primary": ("2025-02", "exposure"), "full": ("2026-07", "treatment")}
SESOI = np.log(0.95)
LEADS = 12
BOOT, SEED, RI_SUB = 99_999, 17, 3_000
DELTAS = np.round(np.arange(-0.60, 0.301, 0.0025), 4)


# ------------------------------------------------------------------------------------- data


def panel() -> pd.DataFrame:
    return duckdb.connect().execute(f"""
        select l.lang, l.month, l.search_arr_na, c.cohort, c.first_exposed
        from '{config.PANEL_DIR}/panel_lang_month.parquet' l
        join read_csv('{config.REFERENCE_DIR}/language_cohorts.csv') c on c.wiki = l.lang
        where l.lang in ({",".join(f"'{e}'" for e in EDS)}) and l.month >= '{START}'
        order by l.lang, l.month""").df()


def seasonal(d: pd.DataFrame) -> pd.DataFrame:
    """Month-of-year coefficients per edition from the P14 trend model on the pre-period."""
    p = d[(d.month >= eda.PRE_START) & (d.month <= eda.PRE_END)]
    rows = []
    for lang, g in p.groupby("lang"):
        r = eda._fit(np.log(g.search_arr_na), eda._design(g))
        rows += [dict(lang=lang, moy=m, s=r.params.get(f"m{m}", 0.0)) for m in range(1, 13)]
    return pd.DataFrame(rows)


def matrix(d: pd.DataFrame, end: str, rule: str):
    s = seasonal(d)
    d = d[d.month <= end].copy()
    d["moy"] = pd.PeriodIndex(d.month, freq="M").month
    d = d.merge(s, on=["lang", "moy"])
    d["y"] = np.log(d.search_arr_na) - d.s
    Y = d.pivot(index="lang", columns="month", values="y").loc[EDS]
    months = list(Y.columns)
    idx = {m: i for i, m in enumerate(months)}
    co = d.groupby("lang")[["cohort", "first_exposed"]].first().loc[EDS]
    G = np.array([idx.get(c, NEVER) if c <= end else NEVER for c in co.cohort], float)
    E = np.array([idx.get(c, NEVER) if c <= end else NEVER for c in co.first_exposed], float)
    miss = Y.isna().all(axis=0).values
    return Y.values, months, G, E, miss


# ------------------------------------------------------------------------------ estimators


def _base(e: float, miss: np.ndarray) -> int:
    b = int(e) - 1
    while b >= 0 and miss[b]:
        b -= 1
    return b


def _controls(G, E, t, rule):
    return (E > t) if rule == "exposure" else (G > t)


def att_gt(Y, G, E, miss, rule, leads_only=False, T=None):
    """All cells (group, t): ATT, event time e = t - g, kind (lead / partial / post), and the
    per-unit influence vector psi (n) used by the multiplier bootstrap."""
    T = Y.shape[1] if T is None else T
    rows = []
    for g, e in sorted({(g, e) for g, e in zip(G, E, strict=True) if g < T}):
        b = _base(e, miss)
        if b < 0:
            continue
        tr = (G == g) & (E == e)
        ts = range(max(0, b - LEADS), b) if leads_only else range(T)
        for t in ts:
            if t == b or miss[t]:
                continue
            c = _controls(G, E, max(t, b), rule) & ~tr
            if not c.any():
                continue
            dy = Y[:, t] - Y[:, b]
            a = dy[tr].mean() - dy[c].mean()
            psi = np.zeros(len(G))
            psi[tr] = (dy[tr] - dy[tr].mean()) / tr.sum()
            psi[c] = -(dy[c] - dy[c].mean()) / c.sum()
            kind = "lead" if t < b else ("partial" if t < g else "post")
            rows.append(dict(g=int(g), e_first=int(e), base=b, n=int(tr.sum()), t=t,
                             event=t - int(g), kind=kind, att=a, psi=psi))  # fmt: skip
    return rows


def overall(cells, kind="post"):
    """Cohort aggregation: mean over each group's cells, then group-size weights; returns
    (theta, psi)."""
    c = [x for x in cells if x["kind"] == kind]
    groups = sorted({(x["g"], x["e_first"]) for x in c})
    n = {k: next(x["n"] for x in c if (x["g"], x["e_first"]) == k) for k in groups}
    tot = sum(n.values())
    th, psi = 0.0, 0.0
    for k in groups:
        gc = [x for x in c if (x["g"], x["e_first"]) == k]
        th += n[k] / tot * np.mean([x["att"] for x in gc])
        psi = psi + n[k] / tot * np.mean([x["psi"] for x in gc], axis=0)
    return th, psi


def event_study(cells):
    df = pd.DataFrame([{k: v for k, v in x.items() if k != "psi"} for x in cells])
    out = []
    for e, g in df.groupby("event"):
        w = g.n / g.n.sum()
        psi = sum(wi * cells[i]["psi"] for i, wi in zip(g.index, w, strict=True))
        out.append(dict(event=e, att=(w * g.att).sum(), n_groups=len(g),
                        kind="/".join(sorted(g.kind.unique())), psi=psi))  # fmt: skip
    return out


def webb(n: int, B: int = BOOT, seed: int = SEED) -> np.ndarray:
    v = np.array([-np.sqrt(1.5), -1, -np.sqrt(0.5), np.sqrt(0.5), 1, np.sqrt(1.5)])
    return np.random.default_rng(seed).choice(v, size=(B, n))


def boot_se(psi: np.ndarray, V: np.ndarray) -> float:
    return float((V @ psi).std())


def sun_abraham(Y, G, E, miss, T=None) -> float:
    """Interaction-weighted: unit + month FE and group x event-time dummies (reference = base
    month); units not treated in the window are the control cohort."""
    n, T = Y.shape
    groups = sorted({(g, e) for g, e in zip(G, E, strict=True) if g < T})
    rows, ys, cols = [], [], {}
    for i in range(n):
        for t in range(T):
            if np.isnan(Y[i, t]):
                continue
            rows.append((i, t))
            ys.append(Y[i, t])
    X_fe = np.zeros((len(rows), n + T - 1))
    inter = []
    for k, (g, e) in enumerate(groups):
        b = _base(e, miss)
        tr = np.flatnonzero((G == g) & (E == e))
        for t in range(T):
            if t != b and not miss[t]:
                cols[(k, t)] = len(inter)
                inter.append([(i, t) for i in tr])
    X_in = np.zeros((len(rows), len(inter)))
    pos = {r: j for j, r in enumerate(rows)}
    for j, (i, t) in enumerate(rows):
        X_fe[j, i] = 1
        if t > 0:
            X_fe[j, n + t - 1] = 1
    for c, cells in enumerate(inter):
        for it in cells:
            if it in pos:
                X_in[pos[it], c] = 1
    X = np.hstack([X_fe, X_in])
    beta = np.linalg.lstsq(X, np.array(ys), rcond=None)[0][X_fe.shape[1]:]
    tot = sum(((G == g) & (E == e)).sum() for g, e in groups)
    th = 0.0
    for k, (g, e) in enumerate(groups):
        post = [beta[cols[(k, t)]] for t in range(int(g), T) if (k, t) in cols]
        th += ((G == g) & (E == e)).sum() / tot * np.mean(post)
    return float(th)


def bjs(Y, G, E, miss, rule) -> float:
    """Imputation: unit + month FE fitted on untreated cells, Y(0) imputed for post cells."""
    n, T = Y.shape
    in_win = G < T
    untreated = np.zeros_like(Y, bool)
    for i in range(n):
        for t in range(T):
            untreated[i, t] = (t < E[i]) or (rule == "treatment" and not in_win[i])
    ok = untreated & ~np.isnan(Y)
    ii, tt = np.nonzero(ok)
    X = np.zeros((len(ii), n + T))
    X[np.arange(len(ii)), ii] = 1
    X[np.arange(len(ii)), n + tt] = 1
    coef = np.linalg.lstsq(X, Y[ok], rcond=None)[0]
    a, lam = coef[:n], coef[n:]
    groups = sorted({(g, e) for g, e in zip(G, E, strict=True) if g < T})
    tot = sum(((G == g) & (E == e)).sum() for g, e in groups)
    th = 0.0
    for g, e in groups:
        units = np.flatnonzero((G == g) & (E == e))
        taus = [Y[i, t] - a[i] - lam[t] for i in units for t in range(int(g), T)
                if not np.isnan(Y[i, t]) and ok[:, t].any()]  # fmt: skip
        th += len(units) / tot * np.mean(taus)
    return float(th)


# ---------------------------------------------------------------------------- inference


def ri(Y, G, E, miss, rule):
    """theta for every assignment, theta of the treatment indicator (for test inversion)."""
    T = Y.shape[1]
    Gp, Ep = assignments(G, E)
    W = np.stack([att_weights(g, T, miss, E=e, control=rule) for g, e in zip(Gp, Ep, strict=True)])
    Y0 = np.nan_to_num(Y)
    A = np.einsum("pij,ij->p", W, Y0)
    D = (np.arange(T)[None, :] >= G[:, None]).astype(float)
    B = np.einsum("pij,ij->p", W, D)
    true = np.flatnonzero((Gp == G).all(1) & (Ep == E).all(1))[0]
    return A, B, true, Gp, Ep


def ri_interval(A, B, true, level=0.95):
    keep = []
    for d in DELTAS:
        stat = A[true] - d * B[true]
        p = (np.abs(A - d * B) >= abs(stat) - 1e-12).mean()
        if p >= 1 - level:
            keep.append(d)
    return (min(keep), max(keep)) if keep else (np.nan, np.nan)


def ri_estimator(fn, Y, Gp, Ep, true, k: int = RI_SUB):
    """RI p for a regression-based estimator on the true assignment plus k random others."""
    rng = np.random.default_rng(SEED)
    others = np.delete(np.arange(len(Gp)), true)
    pick = np.r_[true, rng.choice(others, min(k, len(others)), replace=False)]
    vals = np.array([fn(Gp[i], Ep[i]) for i in pick])
    return vals, float((np.abs(vals) >= abs(vals[0]) - 1e-12).mean())


def pretrend_stat(Y, G, E, miss, rule):
    c = att_gt(Y, G, E, miss, rule, leads_only=True)
    return float(np.mean([abs(x["att"]) for x in c])) if c else np.nan


def rambachan_roth(es: pd.DataFrame, lo: float, hi: float, post_k: float) -> list[dict]:
    """Relative magnitudes: post-period violations change by at most M times the largest
    month-to-month change in the leads. The average post bias is then <= M * dmax * mean(k), k =
    months from the base."""
    leads = es[(es.kind == "lead") & (es.event >= es[es.kind == "lead"].event.max() - LEADS + 1)]
    path = np.r_[leads.sort_values("event").att.values, 0.0]
    dmax = np.abs(np.diff(path)).max()
    rows = [dict(M=m, dmax=dmax, bias=m * dmax * post_k, lo=lo - m * dmax * post_k,
                 hi=hi + m * dmax * post_k) for m in (0.5, 1.0, 2.0)]  # fmt: skip
    m_break = (-hi) / (dmax * post_k) if hi < 0 else 0.0
    rows.append(dict(M="breakdown", dmax=dmax, bias=np.nan, lo=np.nan, hi=m_break))
    return rows


# ------------------------------------------------------------------------------------ run


def run_window(d: pd.DataFrame, name: str) -> dict:
    end, rule = WINDOWS[name]
    Y, months, G, E, miss = matrix(d, end, rule)
    cells = att_gt(Y, G, E, miss, rule)
    th, psi = overall(cells)
    V = webb(len(G))
    se = boot_se(psi, V)
    assert np.isclose(th, np.nansum(att_weights(G, len(months), miss, E=E, control=rule) *
                                    np.nan_to_num(Y)))  # fmt: skip
    A, B, true, Gp, Ep = ri(Y, G, E, miss, rule)
    p = float((np.abs(A) >= abs(A[true]) - 1e-12).mean())
    lo95, hi95 = ri_interval(A, B, true, 0.95)
    lo90, hi90 = ri_interval(A, B, true, 0.90)
    _, p_sa = ri_estimator(lambda g, e: sun_abraham(Y, g, e, miss), Y, Gp, Ep, true)
    th_sa = sun_abraham(Y, G, E, miss)
    _, p_bjs = ri_estimator(lambda g, e: bjs(Y, g, e, miss, rule), Y, Gp, Ep, true)
    th_bjs = bjs(Y, G, E, miss, rule)
    pre_vals = np.array([pretrend_stat(Y, g, e, miss, rule) for g, e in zip(Gp, Ep, strict=True)])
    pre_p = float((pre_vals[~np.isnan(pre_vals)] >= pre_vals[true] - 1e-12).mean())
    es_rows = event_study(cells)
    es = pd.DataFrame([{k: v for k, v in r.items() if k != "psi"} for r in es_rows])
    es["se"] = [boot_se(r["psi"], V) for r in es_rows]
    gt = pd.DataFrame([{k: v for k, v in x.items() if k != "psi"} for x in cells])
    gt["month"] = [months[t] for t in gt.t]
    gt["base_month"] = [months[b] for b in gt.base]
    gt["group"] = [",".join(e for e, g, ef in zip(EDS, G, E, strict=True)
                            if g == r.g and ef == r.e_first) for r in gt.itertuples()]  # fmt: skip
    post = gt[gt.kind == "post"]
    post_k = float(np.average((post.t - post.base).groupby(post.group).mean(),
                              weights=post.groupby("group").n.first()))  # fmt: skip
    groups = (post.groupby("group").agg(att=("att", "mean"), n=("n", "first"), months=("t", "size"))
              .reset_index())  # fmt: skip
    groups["se"] = [boot_se(np.mean([cells[i]["psi"] for i in post.index[post.group == g]], axis=0),
                            V) for g in groups.group]  # fmt: skip
    att = [dict(window=name, estimator="Callaway-Sant'Anna", theta=th, ri_p=p, ri_lo95=lo95,
                ri_hi95=hi95, ri_lo90=lo90, ri_hi90=hi90, boot_se=se),
           dict(window=name, estimator="Sun-Abraham", theta=th_sa, ri_p=p_sa),
           dict(window=name, estimator="Borusyak-Jaravel-Spiess", theta=th_bjs, ri_p=p_bjs)]
    pre = dict(window=name, stat_mean_abs_lead=pre_vals[true], ri_p=pre_p, flagged=pre_p < 0.10)
    rr = [dict(window=name, **r) for r in rambachan_roth(es, lo95, hi95, post_k)]
    return dict(att=att, es=es.assign(window=name), gt=gt.assign(window=name),
                groups=groups.assign(window=name), pre=pre, rr=rr, months=months)


def by_edition(d: pd.DataFrame) -> pd.DataFrame:
    """Exploratory: each treated edition on its own (others in its group dropped), CS overall."""
    rows = []
    for name, (end, rule) in WINDOWS.items():
        Y, months, G, E, miss = matrix(d, end, rule)
        for u in np.flatnonzero(G < len(months)):
            keep = ~((G == G[u]) & (E == E[u])) | (np.arange(len(G)) == u)
            cells = [c for c in att_gt(Y[keep], G[keep], E[keep], miss, rule)
                     if c["g"] == G[u] and c["e_first"] == E[u]]  # fmt: skip
            th, _ = overall(cells)
            rows.append(dict(window=name, edition=EDS[u], theta=th, pct=100 * (np.exp(th) - 1)))
    return pd.DataFrame(rows)


def h1(att: pd.DataFrame, pre: pd.DataFrame, rr: pd.DataFrame) -> dict:
    a = att[(att.estimator == "Callaway-Sant'Anna")].set_index("window")
    p, f = a.loc["primary"], a.loc["full"]
    sig = p.theta < 0 and p.ri_p < 0.05
    if sig and f.theta < 0 and p.ri_hi95 <= SESOI:
        verdict = "H1 supported, effect at least the SESOI"
    elif sig and f.theta < 0:
        verdict = "H1 supported; size uncertain or small"
    elif sig:
        verdict = "Not robust across windows"
    elif p.ri_lo90 > SESOI and p.ri_hi90 < -SESOI:
        verdict = "No effect as large as the SESOI (equivalence)"
    else:
        verdict = "Inconclusive"
    m1 = rr[(rr.window == "primary") & (rr.M == 1.0)].iloc[0]
    pr = pre.set_index("window").loc["primary"]
    return dict(verdict=verdict, primary_pct=100 * (np.exp(p.theta) - 1),
                ri_p=p.ri_p,
                ci95_pct=(100 * (np.exp(p.ri_lo95) - 1), 100 * (np.exp(p.ri_hi95) - 1)),
                full_pct=100 * (np.exp(f.theta) - 1), pretrend_flag=bool(pr.flagged),
                rr_m1_includes_0=bool(m1.lo <= 0 <= m1.hi),
                pretrend_warning=bool(pr.flagged and m1.lo <= 0 <= m1.hi))  # fmt: skip


def figure(res: dict) -> plt.Figure:
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.2), gridspec_kw={"width_ratios": [1, 1.5, 0.8]})
    pct = lambda v: 100 * (np.exp(v) - 1)  # noqa: E731
    for ax, name in zip(axes[:2], ("primary", "full"), strict=True):
        es = res[name]["es"]
        es = es[es.event >= -24]
        cls = np.where(es.kind.str.contains("post"), "post",
                       np.where(es.kind.str.contains("partial"), "partial", "lead"))
        for kind, c in (("lead", "#8fa9cf"), ("partial", "#e6b85c"), ("post", "#1f4e8c")):
            k = es[cls == kind]
            ax.errorbar(k.event, pct(k.att), yerr=[pct(k.att) - pct(k.att - 1.96 * k.se),
                        pct(k.att + 1.96 * k.se) - pct(k.att)], fmt="o", ms=3.5, lw=0.9, color=c,
                        label={"lead": "before exposure", "partial": "partly exposed",
                               "post": "after cohort month"}[kind])  # fmt: skip
        ax.axhline(0, color="#999999", lw=0.6)
        ax.axvline(-0.5, color="k", lw=0.6, ls="--")
        a = pd.DataFrame(res["att"])
        a = a[(a.window == name) & (a.estimator == "Callaway-Sant'Anna")].iloc[0]
        ax.set_title(f"{name} window: ATT {pct(a.theta):+.1f}% (RI p = {a.ri_p:.3f}; 95% "
                     f"{pct(a.ri_lo95):+.0f}% to {pct(a.ri_hi95):+.0f}%)", loc="left",
                     fontsize=10)  # fmt: skip
        ax.set_xlabel("Months since cohort month (exposure ≥ 0.5)")
        ax.set_ylabel("Search arrivals vs not-yet-treated, %")
        ax.legend(frameon=False, fontsize=8, loc="lower left")
    ax = axes[2]
    rows = []
    for name in ("primary", "full"):
        g = res[name]["groups"]
        rows += [(f"{r.group} ({name[0]})", r.att, r.se) for r in g.itertuples()]
    y = np.arange(len(rows))
    v = np.array([r[1] for r in rows])
    s = np.array([r[2] for r in rows])
    ax.errorbar(pct(v), y, xerr=[pct(v) - pct(v - 1.96 * s), pct(v + 1.96 * s) - pct(v)], fmt="o",
                color="#1f4e8c", ms=4, lw=1)  # fmt: skip
    ax.set_yticks(y, [r[0] for r in rows], fontsize=8)
    ax.invert_yaxis()
    ax.axvline(0, color="#999999", lw=0.6)
    ax.set_xlabel("Group ATT, % (bootstrap 95%)")
    ax.set_title("By group (p = primary, f = full)", loc="left", fontsize=10)
    fig.suptitle("P17 staggered DiD: log search arrivals, 9 editions, Callaway-Sant'Anna "
                 "(hero v0)", x=0.01, ha="left", fontsize=12, fontweight="bold")  # fmt: skip
    fig.tight_layout()
    return fig


def main() -> dict:
    d = panel()
    res = {w: run_window(d, w) for w in WINDOWS}
    att = pd.DataFrame([a for w in WINDOWS for a in res[w]["att"]])
    att["pct"] = 100 * (np.exp(att.theta) - 1)
    pre = pd.DataFrame([res[w]["pre"] for w in WINDOWS])
    rr = pd.DataFrame([r for w in WINDOWS for r in res[w]["rr"]])
    res["att"], res["pre"], res["rr"] = att.to_dict("records"), pre, rr
    dec = h1(att, pre, rr)
    att.round(5).to_csv(QA / "p17_att.csv", index=False)
    pd.concat([res[w]["gt"] for w in WINDOWS]).round(5).to_csv(QA / "p17_att_gt.csv", index=False)
    pd.concat([res[w]["es"] for w in WINDOWS]).round(5).to_csv(QA / "p17_event_study.csv",
                                                               index=False)  # fmt: skip
    pd.concat([res[w]["groups"] for w in WINDOWS]).round(5).to_csv(QA / "p17_groups.csv",
                                                                   index=False)  # fmt: skip
    pre.round(5).to_csv(QA / "p17_pretrend.csv", index=False)
    rr.round(5).to_csv(QA / "p17_rr.csv", index=False)
    pd.DataFrame([dec]).to_csv(QA / "p17_h1.csv", index=False)
    figure(res).savefig(FIG / "p17_event_study.png", dpi=150, bbox_inches="tight")
    by_edition(d).round(4).to_csv(QA / "p17_by_edition.csv", index=False)
    res["h1"] = dec
    return res


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    r = main()
    print(pd.DataFrame(r["att"]).round(4).to_string())
    print(r["pre"].to_string())
    print(r["rr"].round(4).to_string())
    print(pd.concat([r[w]["groups"] for w in WINDOWS]).round(4).to_string())
    print(r["h1"])
