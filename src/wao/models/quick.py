"""P21 quick-answer vs long-read (PREREGISTRATION.md H2; confirmatory, Holm family).

Pre-registered model, article panel, all 11 core editions, `in_lang_sample`, P06 weights,
2019-04..2026-07:
    log(1 + V_it) = a_i + g_{edition x month} + q_i * d_t + beta * (q_i * x_lt) + e
V = user desktop + mobile-web views; q = `qa_nq_rate` (P12) standardised over sample articles
(weighted); x = P03 exposure; q_i * d_t = a separate q slope for every month (month dummies x q,
one month dropped, absorbed by a_i). beta < 0 predicted. p-value: restricted wild cluster bootstrap
by edition (Webb, 9,999 draws), closed form on FWL residuals.

The FWL partialling of the 87 q x month columns is done in batches: X'MX = X'(MX), so only one
batch of demeaned columns is held at a time.

Also (labelled):
  secondary   binary v4 tiers (qa_core 1 vs 0, ambiguous excluded), core x month FE
  secondary   search arrivals, 2023 deciles 8-10, censored months = P11 imputed value
  robustness  coarse type x month FE instead of q x month slopes (nests them: q is a function of
              the coarse type)
  exploratory without fa (P18); effect by coarse type and by topic group (relative to `human` and
              `Geography`), with empirical-Bayes shrinkage across types instead of bambi
  descriptive slope chart: quick vs long views, high-exposure editions vs fr + ru, the year
              before launch vs the latest 12 months

Outputs: report/qa/p21_h2.csv, p21_by_type.csv, p21_by_topic.csv, p21_slope.csv;
report/figures/p21_quick_answer.png (chart 5 + chart 2)
"""

from __future__ import annotations

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pyfixest.estimation import demean

from wao import config
from wao.models import concept, did

QA, FIG = config.REPORT_DIR / "qa", config.REPORT_DIR / "figures"
START, END, SHORT = "2019-04", "2026-07", "2025-04"
REPS, SEED, BATCH = 9_999, 21, 12
HIGH = ["en", "ja", "pt", "es", "de", "it", "pl", "zh"]
LOWC = ["fr", "ru"]


def load() -> pd.DataFrame:
    am = f"read_parquet('{config.PANEL_DIR}/panel_article_month/*/part.parquet', hive_partitioning=true)"  # noqa: E501
    d = duckdb.connect().execute(f"""
        select a.lang, a.page_id, a.month, a.weight, a.coarse_type, a.qa_nq_rate, a.qa_core,
               a.topic_group, a.decile, a.cs_usable,
               ln(1 + a.views_desktop + a.views_mobile_web) as views,
               case when a.cs_usable and a.month <> '{SHORT}'
                    then ln(1 + coalesce(a.arr_search, a.search_hidden_est)) end as search,
               coalesce(l.exposure, 0) as x
        from {am} a join '{config.PANEL_DIR}/panel_lang_month.parquet' l using (lang, month)
        where a.in_lang_sample and a.month between '{START}' and '{END}'""").df()
    art = d.groupby(["lang", "page_id"]).agg(q=("qa_nq_rate", "first"), w=("weight", "first"))
    mu = np.average(art.q, weights=art.w)
    sd = np.sqrt(np.average((art.q - mu) ** 2, weights=art.w))
    d["q"] = (d.qa_nq_rate - mu) / sd
    d["art"] = pd.factorize(d.lang + ":" + d.page_id.astype(str))[0]
    d["lm"] = pd.factorize(d.lang + d.month)[0]
    d["m"] = pd.factorize(d.month, sort=True)[0]
    return d


def _dm(cols, f, w):
    r, ok = demean(np.ascontiguousarray(cols, dtype=np.float64), f, w, tol=1e-8)
    assert ok
    return r


def _wcb(ys, xs, w, cl):
    V = did.webb(cl.max() + 1, REPS, SEED)
    return concept._wcb(ys, xs, w, cl, V)


def fit_qdelta(s: pd.DataFrame, y: str, xcol: str = "qx") -> dict:
    """beta on xcol with article + edition x month FE and q x month slopes (FWL, batched)."""
    f = np.column_stack([s.art.values, s.lm.values]).astype(np.uint64)
    w = s.weight.values
    yx = _dm(np.column_stack([s[y].values, s[xcol].values]), f, w)
    yt, xt = yx[:, 0], yx[:, 1]
    m, q = s.m.values, s.q.values
    months = np.unique(m)[1:]
    k = len(months)
    nm = m.max() + 1
    wq = w * q
    Zy = np.bincount(m, wq * yt, nm)[months]
    Zx = np.bincount(m, wq * xt, nm)[months]
    G = np.zeros((k, k))
    batches = [months[i:i + BATCH] for i in range(0, k, BATCH)]
    for bi, mb in enumerate(batches):
        B = _dm(np.column_stack([q * (m == t) for t in mb]), f, w)
        for j in range(B.shape[1]):
            G[:, bi * BATCH + j] = np.bincount(m, wq * B[:, j], nm)[months]
    G = (G + G.T) / 2
    cy, cx = np.linalg.solve(G, Zy), np.linalg.solve(G, Zx)
    ys, xs = yt.copy(), xt.copy()
    for bi, mb in enumerate(batches):
        B = _dm(np.column_stack([q * (m == t) for t in mb]), f, w)
        sl = slice(bi * BATCH, bi * BATCH + len(mb))
        ys -= B @ cy[sl]
        xs -= B @ cx[sl]
    cl = pd.factorize(s.lang)[0]
    return _wcb(ys, xs, w, cl)


def fit_fe(s: pd.DataFrame, y: str, xcol: str, extra: str) -> dict:
    """beta on xcol with article, edition x month and an extra FE (e.g. type x month)."""
    f = np.column_stack([s.art.values, s.lm.values,
                         pd.factorize(s[extra].astype(str) + s.month)[0]]).astype(np.uint64)
    r = _dm(np.column_stack([s[y].values, s[xcol].values]), f, s.weight.values)
    return _wcb(r[:, 0], r[:, 1], s.weight.values, pd.factorize(s.lang)[0])


def h2(d: pd.DataFrame) -> pd.DataFrame:
    d = d.assign(qx=d.q * d.x)
    nofa = d[d.lang != "fa"]
    core = d[d.qa_core.notna()].assign(cx=lambda t: t.qa_core * t.x)
    head = d[(d.decile >= 8) & d.search.notna()]
    runs = [
        ("H2 primary: q x exposure, views, 11 editions", "pre-registered", lambda: fit_qdelta(d, "views")),  # noqa: E501
        ("binary v4: quick vs long x exposure, views", "secondary", lambda: fit_fe(core, "views", "cx", "qa_core")),  # noqa: E501
        ("search arrivals, deciles 8-10 (imputed censored)", "secondary", lambda: fit_qdelta(head, "search")),  # noqa: E501
        ("type x month FE instead of q slopes", "robustness", lambda: fit_fe(d, "views", "qx", "coarse_type")),  # noqa: E501
        ("without fa", "exploratory", lambda: fit_qdelta(nofa, "views")),
        ("binary v4, without fa", "exploratory", lambda: fit_fe(core[core.lang != "fa"], "views", "cx", "qa_core")),  # noqa: E501
    ]
    rows = []
    for name, status, fn in runs:
        r = fn()
        rows.append(dict(spec=name, status=status, **r))
        print(f"{name:55s} beta={r['beta']:+.4f} p={r['wcb_p']:.3f}", flush=True)
    out = pd.DataFrame(rows)
    pct = lambda v: 100 * (np.exp(v) - 1)  # noqa: E731
    out["pct"], out["pct_lo"], out["pct_hi"] = pct(out.beta), pct(out.wcb_lo), pct(out.wcb_hi)
    return out


def by_group(d: pd.DataFrame, col: str, ref, y: str = "views") -> pd.DataFrame:
    """Exposure effect for each level of col, relative to ref (article, edition x month and
    col x month FE); CRV1 by edition; empirical-Bayes shrinkage toward the precision-weighted
    mean."""
    lv = [v for v in sorted(d[col].dropna().unique()) if v != ref]
    s = d[d[col].notna() & d[y].notna()]
    f = np.column_stack([s.art.values, s.lm.values,
                         pd.factorize(s[col].astype(str) + s.month)[0]]).astype(np.uint64)
    X = np.column_stack([(s[col].values == v) * s.x.values for v in lv])
    w = s.weight.values
    r = _dm(np.column_stack([s[y].values, X]), f, w)
    yt, Xt = r[:, 0], r[:, 1:]
    XtW = Xt * w[:, None]
    A = np.linalg.inv(XtW.T @ Xt)
    b = A @ (XtW.T @ yt)
    e = yt - Xt @ b
    cl = pd.factorize(s.lang)[0]
    G = cl.max() + 1
    S = np.zeros((len(lv), len(lv)))
    for g in range(G):
        sg = (XtW[cl == g] * e[cl == g, None]).sum(0)
        S += np.outer(sg, sg)
    se = np.sqrt(np.diag(A @ S @ A) * G / (G - 1))
    tau2 = max(np.var(b) - np.mean(se**2), 0.0)
    mu = np.average(b, weights=1 / (se**2 + tau2))
    shrink = tau2 / (tau2 + se**2)
    out = pd.DataFrame({col: lv, "est": b, "se": se, "eb": mu + shrink * (b - mu)})
    nq = d.groupby(col).qa_nq_rate.first() if col == "coarse_type" else None
    if nq is not None:
        out["nq_rate"] = out[col].map(nq)
    out["n_articles"] = out[col].map(d.groupby(col).art.nunique())
    return out


def slope(d: pd.DataFrame) -> pd.DataFrame:
    s = d[d.qa_core.notna() & d.lang.isin(HIGH + LOWC)].copy()
    s["period"] = np.where((s.month >= "2023-08") & (s.month <= "2024-07"), "before",
                           np.where(s.month >= "2025-08", "latest", None))  # fmt: skip
    s = s[s.period.notna()]
    s["grp"] = np.where(s.lang.isin(HIGH), "high exposure (8)", "fr + ru")
    s["v"] = np.expm1(s.views) * s.weight
    t = s.groupby(["grp", "qa_core", "period"]).v.sum().unstack("period")
    t["change_pct"] = 100 * (t.latest / t.before - 1)
    return t.reset_index().assign(label=lambda x: np.where(x.qa_core == 1, "quick", "long"))


def figure(h, ty, tp, sl) -> plt.Figure:
    pct = lambda v: 100 * (np.exp(v) - 1)  # noqa: E731
    fig, axes = plt.subplots(1, 3, figsize=(19, 6.5), gridspec_kw={"width_ratios": [1, 1, 0.7]})
    ax = axes[0]
    t = ty.sort_values("nq_rate")
    y = np.arange(len(t))
    ax.errorbar(pct(t.est), y, xerr=1.96 * 100 * t.se, fmt="o", color="#bbbbbb", ms=3, lw=0.8,
                label="raw (CRV1 95%)")  # fmt: skip
    ax.plot(pct(t.eb), y, "o", color="#1f4e8c", ms=5, label="partially pooled (EB)")
    ax.set_yticks(y, [f"{c} ({r:.2f})" for c, r in zip(t.coarse_type, t.nq_rate, strict=True)],
                  fontsize=8)  # fmt: skip
    ax.axvline(0, color="#999999", lw=0.6)
    ax.set_xlabel("Effect of full exposure on views vs `human` articles, %")
    ax.set_title("Chart 5: by Wikidata type (sorted by NQ short-answer rate)", loc="left",
                 fontsize=10)  # fmt: skip
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    ax = axes[1]
    for grp, ls in (("high exposure (8)", "-"), ("fr + ru", "--")):
        for lab, c in (("quick", "#c0392b"), ("long", "#1f4e8c")):
            r = sl[(sl.grp == grp) & (sl.label == lab)].iloc[0]
            ax.plot([0, 1], [0, r.change_pct], ls=ls, color=c, marker="o", lw=1.6)
            ax.text(1.03, r.change_pct, f"{lab}, {grp}: {r.change_pct:+.1f}%", fontsize=8,
                    va="center", color=c)  # fmt: skip
    ax.set_xticks([0, 1], ["2023-08..2024-07", "2025-08..2026-07"])
    ax.set_xlim(-0.1, 2.4)
    ax.axhline(0, color="#999999", lw=0.6)
    ax.set_ylabel("Change in user web views, % (weighted)")
    ax.set_title("Chart 2: quick vs long, before and after", loc="left", fontsize=10)
    ax = axes[2]
    rows = [(r.spec, r.pct, r.pct_lo, r.pct_hi) for r in h.itertuples()]
    yy = np.arange(len(rows))
    v = np.array([r[1] for r in rows])
    lo, hi = np.array([r[2] for r in rows]), np.array([r[3] for r in rows])
    ax.errorbar(v, yy, xerr=[v - lo, hi - v], fmt="o", color="#1f4e8c", ms=4, lw=1)
    ax.set_yticks(yy, [r[0] for r in rows], fontsize=7.5)
    ax.invert_yaxis()
    ax.axvline(0, color="#999999", lw=0.6)
    ax.set_xlabel("% per SD of q (binary: quick vs long) at full exposure (WCB 95%)")
    ax.set_title("H2 estimates", loc="left", fontsize=10)
    fig.suptitle("P21 quick-answer vs long-read articles", x=0.01, ha="left", fontsize=12,
                 fontweight="bold")  # fmt: skip
    fig.tight_layout()
    return fig


def main() -> dict:
    d = load()
    h = h2(d)
    ty = by_group(d, "coarse_type", "human")
    tp = by_group(d[d.topic_group.notna()], "topic_group", "Geography")
    sl = slope(d)
    h.round(5).to_csv(QA / "p21_h2.csv", index=False)
    ty.round(5).to_csv(QA / "p21_by_type.csv", index=False)
    tp.round(5).to_csv(QA / "p21_by_topic.csv", index=False)
    sl.round(4).to_csv(QA / "p21_slope.csv", index=False)
    figure(h, ty, tp, sl).savefig(FIG / "p21_quick_answer.png", dpi=150, bbox_inches="tight")
    return dict(h=h, ty=ty, tp=tp, sl=sl)


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    r = main()
    print(r["h"].round(4).to_string())
    print(r["ty"].round(4).to_string())
    print(r["tp"].round(4).to_string())
    print(r["sl"].round(2).to_string())
