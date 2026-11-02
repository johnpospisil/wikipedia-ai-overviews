"""P19 within-concept design (PREREGISTRATION.md 5.4; supporting estimator).

The same Wikidata concept read in different editions in the same month:
    y_{c,l,t} = beta * exposure_{l,t} + (concept x month FE) + (concept x edition FE)
                + (edition x month-of-year FE) + e
Concept x month FE absorb anything that happens to the topic everywhere at once ("the topic got
less interesting"); concept x edition FE absorb level differences; edition x month-of-year FE
absorb edition-specific seasonality (P14). beta is identified only from how exposure differs
across editions within a month, so it is still an edition-level comparison with few clusters.

Panel: panels/panel_item_lang_month.parquet, 6,000 concepts present in all 11 core editions,
2019-04..2026-07 without 2025-04 (short clickstream month). Outcomes:
  views        log(1 + user desktop + mobile-web views)
  search       log(1 + search arrivals), censored (<10) months set to the P11 imputed value
  search_head  as search, concept-editions never censored in 2023 (selected on the pre-period)
Editions: all 11 (pre-registered), without fa (P18: Iran shock from 2025-05; exploratory), and
P17's 9. Weighted by the P06 concept weights and unweighted.

Inference: restricted wild cluster bootstrap by edition (Webb, 9,999 draws; interval by test
inversion), computed in closed form on the FWL-demeaned data; randomization inference permuting
whole exposure paths across editions (999 draws) for the main specifications.

Outputs: report/qa/p19_estimates.csv, p19_items.csv, p19_gap_by_month.csv;
report/figures/p19_within_concept.png
"""

from __future__ import annotations

import duckdb
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pyfixest.estimation import demean

from wao import config
from wao.models import did

QA, FIG = config.REPORT_DIR / "qa", config.REPORT_DIR / "figures"
START, END, SHORT = "2019-04", "2026-07", "2025-04"
EDSETS = {"11 editions (pre-registered)": did.EDS + ["ru", "fa"],
          "10 editions, no fa": did.EDS + ["ru"], "9 editions (P17 set)": did.EDS}  # fmt: skip
OUTCOMES = {"views": "log(1 + user web views)", "search": "log(1 + search arrivals), imputed",
            "search_head": "log(1 + search arrivals), never censored in 2023"}  # fmt: skip
REPS, RI_REPS, SEED = 9_999, 999, 19
GRID = np.round(np.arange(-0.6, 0.6001, 0.0025), 4)
RI_SPECS = [(o, e) for o in ("views", "search")
            for e in ("11 editions (pre-registered)", "10 editions, no fa")]


def load() -> pd.DataFrame:
    d = duckdb.connect().execute(f"""
        select qid, lang, month, w_concept, coarse_type, qa_tier, coalesce(exposure, 0) exposure,
               ln(1 + views_web) as views,
               case when cs_usable then ln(1 + coalesce(arr_search, search_hidden_est)) end
                 as search,
               bool_or(search_censored) filter (where month like '2023-%')
                 over (partition by qid, lang) as cens2023
        from '{config.PANEL_DIR}/panel_item_lang_month.parquet'
        where month between '{START}' and '{END}' and month <> '{SHORT}'""").df()
    d["search_head"] = d.search.where(d.cens2023 == False)  # noqa: E712
    d["moy"] = d.month.str[5:]
    return d


def _fe(d: pd.DataFrame) -> np.ndarray:
    return np.column_stack([pd.factorize(d.qid + d.month)[0], pd.factorize(d.qid + d.lang)[0],
                            pd.factorize(d.lang + d.moy)[0]]).astype(np.uint64)  # fmt: skip


def _dm(cols: np.ndarray, f: np.ndarray, w: np.ndarray) -> np.ndarray:
    r, ok = demean(np.ascontiguousarray(cols, dtype=np.float64), f, w, tol=1e-8)
    assert ok
    return r


def _wcb(yt, xt, w, cl, V) -> dict:
    """Closed-form WCR on demeaned data: p for beta = 0 and the 95% inversion interval."""
    G = cl.max() + 1
    sxx = (w * xt**2).sum()
    Axy = np.bincount(cl, w * xt * yt, G)
    Q = np.bincount(cl, w * xt**2, G)
    b = Axy.sum() / sxx

    def p(r):
        A = Axy - r * Q
        res0 = A - (b - r) * Q
        t0 = (b - r) / (np.sqrt((res0**2).sum() * G / (G - 1)) / sxx)
        bs = (V * A).sum(1) / sxx
        sc = V * A - bs[:, None] * Q
        ts = bs / (np.sqrt((sc**2).sum(1) * G / (G - 1)) / sxx)
        return float((np.abs(ts) >= abs(t0) - 1e-12).mean())

    keep = [r for r in GRID if p(r) >= 0.05]
    res = Axy - b * Q
    return dict(beta=b, crv1_se=float(np.sqrt((res**2).sum() * G / (G - 1)) / sxx), wcb_p=p(0.0),
                wcb_lo=min(keep) if keep else np.nan, wcb_hi=max(keep) if keep else np.nan)


def _ri(s: pd.DataFrame, f, w, yt) -> float:
    """Permute whole exposure paths across editions; re-demean exposure each time."""
    rng = np.random.default_rng(SEED)
    lc, eds = pd.factorize(s.lang)
    mc, mons = pd.factorize(s.month)
    E = s.pivot_table(index="lang", columns="month", values="exposure", aggfunc="first")
    E = E.reindex(index=eds, columns=mons).fillna(0).values
    xt0 = _dm(s.exposure.values[:, None], f, w)[:, 0]
    b0 = (w * xt0 * yt).sum() / (w * xt0**2).sum()
    hits = 0
    for _ in range(RI_REPS):
        x = E[rng.permutation(len(eds))[lc], mc]
        xt = _dm(x[:, None], f, w)[:, 0]
        b = (w * xt * yt).sum() / (w * xt**2).sum()
        hits += abs(b) >= abs(b0) - 1e-12
    return (hits + 1) / (RI_REPS + 1)


def estimates(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for out in OUTCOMES:
        for es_name, eds in EDSETS.items():
            s = d[d.lang.isin(eds) & d[out].notna()].reset_index(drop=True)
            f = _fe(s)
            cl = pd.factorize(s.lang)[0]
            V = did.webb(cl.max() + 1, REPS, SEED)
            for wname in ("weighted", "unweighted"):
                w = s.w_concept.values if wname == "weighted" else np.ones(len(s))
                r = _dm(np.column_stack([s[out].values, s.exposure.values]), f, w)
                est = _wcb(r[:, 0], r[:, 1], w, cl, V)
                ri_p = (_ri(s, f, w, r[:, 0]) if wname == "weighted" and (out, es_name) in RI_SPECS
                        else np.nan)  # fmt: skip
                pct = lambda v: 100 * (np.exp(v) - 1)  # noqa: E731
                rows.append(dict(outcome=out, editions=es_name, weights=wname, n=len(s),
                                 concepts=s.qid.nunique(), **est, ri_p=ri_p,
                                 pct=pct(est["beta"]), pct_lo=pct(est["wcb_lo"]),
                                 pct_hi=pct(est["wcb_hi"])))  # fmt: skip
                print(rows[-1]["outcome"], es_name, wname, round(rows[-1]["pct"], 2), flush=True)
    return pd.DataFrame(rows)


def items(d: pd.DataFrame) -> pd.DataFrame:
    c = d.groupby("qid").agg(coarse_type=("coarse_type", "first"), qa_tier=("qa_tier", "first"),
                             w=("w_concept", "first"))  # fmt: skip
    out = []
    for col in ("coarse_type", "qa_tier"):
        g = c.groupby(col).agg(concepts=("w", "size"), weight=("w", "sum")).reset_index()
        g["share"] = g.concepts / g.concepts.sum()
        g["weighted_share"] = g.weight / g.weight.sum()
        out.append(g.rename(columns={col: "value"}).assign(by=col))
    return pd.concat(out)[["by", "value", "concepts", "share", "weighted_share"]]


def gap_by_month(d: pd.DataFrame, out: str) -> pd.DataFrame:
    """Descriptive: month-by-month gap between the 8 treated editions and fr + ru (fa excluded),
    within concept and month. Point estimates only (10 clusters). Fitted with concept x month and
    concept x edition FE only (month dummies for the treated group are collinear with edition x
    month-of-year FE); the gap's own month-of-year means over 2019-04..2024-04 are then removed and
    the series is set to 0 over 2023-05..2024-04."""
    s = d[d.lang.isin(EDSETS["10 editions, no fa"]) & d[out].notna()].reset_index(drop=True)
    tr = s.lang.isin([e for e in did.EDS if e != "fr"]).values
    months = sorted(s.month.unique())[1:]  # first month is the reference
    X = np.column_stack([(tr & (s.month.values == m)).astype(float) for m in months])
    f = _fe(s)[:, :2]
    w = s.w_concept.values
    r = _dm(np.column_stack([s[out].values, X]), f, w)
    yt, Xt = r[:, 0], r[:, 1:]
    b = np.linalg.lstsq(Xt * np.sqrt(w)[:, None], yt * np.sqrt(w), rcond=None)[0]
    g = pd.DataFrame({"outcome": out, "month": months, "raw": b})
    g["moy"] = g.month.str[5:]
    pre = g[g.month <= "2024-04"].groupby("moy").raw.mean()
    g["gap"] = g.raw - g.moy.map(pre)
    g["gap"] -= g[(g.month >= "2023-05") & (g.month <= "2024-04")].gap.mean()
    return g.drop(columns="moy")


def figure(est: pd.DataFrame, gaps: pd.DataFrame) -> plt.Figure:
    pct = lambda v: 100 * (np.exp(v) - 1)  # noqa: E731
    fig, (a, b) = plt.subplots(1, 2, figsize=(16, 6), gridspec_kw={"width_ratios": [1.3, 1]})
    for out, c in (("views", "#999999"), ("search", "#1f4e8c")):
        g = gaps[gaps.outcome == out]
        a.plot(pd.PeriodIndex(g.month, freq="M").to_timestamp(), pct(g.gap), color=c, lw=1.3,
               label=OUTCOMES[out])  # fmt: skip
    for m, txt in (("2022-12", "ChatGPT"), ("2024-05", "AIO US"), ("2024-09", "en/ja/pt ≥ 0.5"),
                   ("2025-04", "de/it/pl; bot reclass")):  # fmt: skip
        x = pd.Period(m, "M").to_timestamp()
        a.axvline(x, color="k", lw=0.6, ls="--")
        a.text(x, 0.98, txt, fontsize=7, rotation=90, va="top", ha="right",
               transform=a.get_xaxis_transform())  # fmt: skip
    a.axhline(0, color="#999999", lw=0.6)
    a.xaxis.set_major_locator(mdates.YearLocator())
    a.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    a.set_ylabel("Treated editions vs fr + ru, same concept and month, %\n"
                 "(seasonality removed; 2023-05..2024-04 = 0)")
    a.legend(frameon=False, fontsize=8, loc="lower left")
    a.set_title("Within-concept gap by month (descriptive; fa excluded)", loc="left", fontsize=10)
    e = est[est.weights == "weighted"]
    rows = [(f"{r.outcome} · {r.editions}", r.pct, r.pct_lo, r.pct_hi) for r in e.itertuples()]
    p17 = pd.read_csv(QA / "p17_att.csv").query("estimator == \"Callaway-Sant'Anna\"")
    p18 = pd.read_csv(QA / "p18_twfe.csv")
    rows += [(f"P17 CS {r.window} (ATT)", r.pct, pct(r.ri_lo95), pct(r.ri_hi95))
             for r in p17.itertuples()]  # fmt: skip
    rows += [(f"P18 TWFE {r.spec}", r.pct_full, r.pct_lo, r.pct_hi) for r in p18.iloc[[0, 4]]
             .itertuples()]  # fmt: skip
    y = np.arange(len(rows))
    v = np.array([r[1] for r in rows])
    lo, hi = np.array([r[2] for r in rows]), np.array([r[3] for r in rows])
    b.errorbar(v, y, xerr=[v - lo, hi - v], fmt="o", ms=4, lw=1, color="#1f4e8c")
    b.set_yticks(y, [r[0] for r in rows], fontsize=7.5)
    b.invert_yaxis()
    b.axvline(0, color="#999999", lw=0.6)
    b.set_xlabel("Effect of full exposure, % (WCB 95%; P17: RI 95%)")
    b.set_title("Within-concept estimates (weighted) vs P17-P18", loc="left", fontsize=10)
    fig.suptitle("P19 within-concept design: 6,000 concepts in all 11 editions", x=0.01,
                 ha="left", fontsize=12, fontweight="bold")  # fmt: skip
    fig.tight_layout()
    return fig


def main(refit: bool = True) -> dict:
    d = load()
    est = estimates(d) if refit else pd.read_csv(QA / "p19_estimates.csv")
    gaps = pd.concat([gap_by_month(d, o) for o in ("views", "search")])
    it = items(d)
    est.round(5).to_csv(QA / "p19_estimates.csv", index=False)
    it.round(4).to_csv(QA / "p19_items.csv", index=False)
    gaps.round(5).to_csv(QA / "p19_gap_by_month.csv", index=False)
    figure(est, gaps).savefig(FIG / "p19_within_concept.png", dpi=150, bbox_inches="tight")
    return dict(est=est, gaps=gaps, items=it)


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    r = main()
    print(r["est"].drop(columns=["n"]).round(3).to_string())
    print(r["items"].to_string())
