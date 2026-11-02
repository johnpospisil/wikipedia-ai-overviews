"""P20 robustness: every PREREGISTRATION.md section 7 variant of the H1 estimate.

Each row re-runs the P17 Callaway-Sant'Anna ATT (cohort aggregation, base = month before first
exposure) with one change, in the primary window (to 2025-02, not-yet-exposed controls) and/or
the full window (to 2026-07, not-yet-treated controls). Inference: randomization inference over
assignments of the (cohort, first exposure) label pairs, exact when there are at most 9 editions
and 5,000 random permutations otherwise, with the 95% interval from test inversion.

Rows that change only the inputs to the same estimator: ru/fa added as controls; base g-1;
not-yet-treated controls; no seasonal adjustment; year-over-year differences; edition linear
trends (fitted 2022-12..2024-04) removed; placebo launches 12 months earlier; cohorts +/-1 month;
pre-period from 2023-07; leave one edition out; core-update months dropped from post cells; net
of Google search share; total and web user views; bot months dropped and an edition x
post-2025-04 step; 2025-04 rescaled; truncation-corrected search; alternative exposure
definitions; fa without 2026-04..05; negative controls (ru, fa treated from 2025-05 vs fr).
Rambachan-Roth (M = 1) comes from P17.

Outputs: report/qa/p20_robustness.csv; report/figures/p20_forest.png
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from wao import config
from wao.models import did
from wao.models.csdid import NEVER, assignments, att_weights
from wao.viz import eda

QA, FIG = config.REPORT_DIR / "qa", config.REPORT_DIR / "figures"
EDS9 = did.EDS
SAMPLE, SEED = 5_000, 20
ENDS = {"primary": ("2025-02", "exposure"), "full": ("2026-07", "treatment")}
BASES = {"2024-04", "2024-07", "2025-02", "2025-03"}
BOT = ("2025-03", "2025-08")


@dataclass(frozen=True)
class Spec:
    name: str
    group: str
    window: str
    eds: tuple = tuple(EDS9)
    outcome: str = "search"  # search | views | views_web | google_net | corr | rescaled
    season: bool = True
    yoy: bool = False
    detrend: bool = False
    shift: int = 0  # months added to cohort and first-exposure dates
    base_g1: bool = False
    rule: str | None = None
    exposure_col: str = "exposure"
    drop: tuple = field(default_factory=tuple)  # months set missing for every edition
    drop_post_core: bool = False
    bot_step: bool = False
    start: str = did.START
    treated_override: dict | None = None  # lang -> (cohort, first exposure)
    note: str = ""


def panel() -> pd.DataFrame:
    return duckdb.connect().execute(f"""
        select lang, month, search_arr_na, search_arr_rs, search_arr_corr, google_share,
               views_desktop + views_mobile_web + views_app as views,
               views_desktop + views_mobile_web as views_web, views_desktop, views_mobile_web,
               views_app, total_arr_na, link_arr
        from '{config.PANEL_DIR}/panel_lang_month.parquet'
        where core and month >= '{did.START}' order by lang, month""").df()


def cohorts(col: str) -> pd.DataFrame:
    """Cohort (first month >= 0.5) and first exposure (first month > 0) per edition."""
    if col == "exposure":
        c = pd.read_csv(config.REFERENCE_DIR / "language_cohorts.csv")
        return c.set_index("wiki")[["cohort", "first_exposed"]]
    e = pd.read_csv(config.REFERENCE_DIR / "language_exposure.csv")
    out = {}
    for w, g in e.groupby("wiki"):
        g = g.sort_values("month")
        hi, pos = g[g[col] >= 0.5].month, g[g[col] > 0].month
        out[w] = (hi.min() if len(hi) else "never", pos.min() if len(pos) else "never")
    return pd.DataFrame.from_dict(out, orient="index", columns=["cohort", "first_exposed"])


def _series(d: pd.DataFrame, outcome: str) -> pd.Series:
    if outcome == "search":
        return np.log(d.search_arr_na)
    if outcome == "rescaled":
        return np.log(d.search_arr_rs)
    if outcome == "corr":
        return np.log(d.search_arr_corr).where(d.month != "2025-04")
    if outcome == "share":
        return np.log(d.search_arr_na / d.total_arr_na)
    if outcome == "depth":
        return np.log(d.link_arr / (d.total_arr_na - d.link_arr))
    if outcome == "mob_desk":
        return np.log(d.views_mobile_web) - np.log(d.views_desktop)
    if outcome == "google_net":
        return np.log(d.search_arr_na) - np.log(d.google_share)
    return np.log(d[outcome])


def matrix(d: pd.DataFrame, s: Spec):
    end, rule = ENDS[s.window]
    if s.group == "placebo":  # fake dates; keep every post cell before the real launch
        end = min(str(pd.Period(end, "M") + s.shift), eda.PRE_END)
    d = d[d.lang.isin(s.eds)].copy()
    d["y"] = _series(d, s.outcome)
    if s.season:
        pre = d[(d.month >= eda.PRE_START) & (d.month <= eda.PRE_END)]
        coefs = {}
        for lang, g in pre.groupby("lang"):
            r = eda._fit(g.y, eda._design(g))
            coefs[lang] = [0.0] + [r.params.get(f"m{m}", 0.0) for m in range(2, 13)]
        moy = pd.PeriodIndex(d.month, freq="M").month
        d["y"] = d.y - [coefs[lang][m - 1] for lang, m in zip(d.lang, moy, strict=True)]
    Y = d.pivot(index="lang", columns="month", values="y").loc[list(s.eds)]
    if s.yoy:
        Y = Y - Y.shift(12, axis=1)
    if s.detrend:
        cols = [m for m in Y.columns if "2022-12" <= m <= "2024-04"]
        t = np.arange(len(Y.columns))
        idx = [Y.columns.get_loc(m) for m in cols]
        for lang in Y.index:
            k = np.polyfit(t[idx], Y.loc[lang, cols].values, 1)[0]
            Y.loc[lang] = Y.loc[lang] - k * (t - idx[-1])
    if s.bot_step:
        pre_m = [m for m in Y.columns if "2025-01" <= m <= "2025-03"]
        post_m = [m for m in Y.columns if "2025-05" <= m <= "2025-07"]
        for lang in Y.index:
            if lang not in ("de", "it", "pl"):
                step = Y.loc[lang, post_m].mean() - Y.loc[lang, pre_m].mean()
                Y.loc[lang, [m for m in Y.columns if m >= "2025-04"]] -= step
    Y = Y.loc[:, (Y.columns >= s.start) & (Y.columns <= end)]
    months = list(Y.columns)
    idx = {m: i for i, m in enumerate(months)}
    co = cohorts(s.exposure_col)
    if s.treated_override:
        co = co.copy()
        for lang, (c, f) in s.treated_override.items():
            co.loc[lang] = (c, f)

    def pos(m):
        if m == "never":
            return NEVER
        m = str(pd.Period(m, "M") + s.shift)
        return idx.get(m, NEVER) if m <= end else NEVER

    G = np.array([pos(co.loc[e, "cohort"]) for e in s.eds], float)
    E = G.copy() if s.base_g1 else np.array([pos(co.loc[e, "first_exposed"]) for e in s.eds],
                                             float)  # fmt: skip
    E = np.minimum(E, G)
    miss = Y.isna().all(axis=0).values.copy()
    for m in s.drop:
        if m in idx:
            miss[idx[m]] = True
    if s.drop_post_core:
        core = pd.read_csv(config.REFERENCE_DIR / "ranking_updates_monthly.csv")
        for m in core[core.core_update & (core.month >= "2024-05")].month:
            if m in idx and m not in BASES:
                miss[idx[m]] = True
    Y = Y.to_numpy(dtype=float, copy=True)
    Y[:, miss] = np.nan
    return Y, months, G, E, miss, s.rule or rule


def _assign(G, E):
    if len(G) <= 9:
        return assignments(G, E)
    rng = np.random.default_rng(SEED)
    P = np.array([rng.permutation(len(G)) for _ in range(SAMPLE)])
    return np.vstack([G, G[P]]), np.vstack([E, E[P]])


def estimate(d: pd.DataFrame, s: Spec) -> dict:
    Y, months, G, E, miss, rule = matrix(d, s)
    T = len(months)
    if not (G < T).any():
        return dict(spec=s.name, group=s.group, window=s.window, theta=np.nan,
                    note="not estimable: no edition reaches the cohort threshold in this window")
    Gp, Ep = _assign(G, E)
    true = 0 if len(G) > 9 else np.flatnonzero((Gp == G).all(1) & (Ep == E).all(1))[0]
    W = np.stack([att_weights(g, T, miss, E=e, control=rule) for g, e in zip(Gp, Ep, strict=True)])
    Y0 = np.nan_to_num(Y)
    A = np.einsum("pij,ij->p", W, Y0)
    D = (np.arange(T)[None, :] >= G[:, None]).astype(float)
    B = np.einsum("pij,ij->p", W, D)
    p = float((np.abs(A) >= abs(A[true]) - 1e-12).mean())
    lo, hi = did.ri_interval(A, B, true)
    pct = lambda v: 100 * (np.exp(v) - 1)  # noqa: E731
    return dict(spec=s.name, group=s.group, window=s.window, editions=len(s.eds), theta=A[true],
                pct=pct(A[true]), lo_pct=pct(lo), hi_pct=pct(hi), ri_p=p,
                assignments=len(Gp), note=s.note)  # fmt: skip


def specs() -> list[Spec]:
    out = []
    for w in ENDS:
        b = Spec("baseline (P17)", "baseline", w)
        out += [
            b,
            replace(b, name="+ ru, fa as controls", group="sample", eds=tuple(EDS9 + ["ru", "fa"])),
            replace(b, name="+ ru, fa; fa 2026-04..05 dropped", group="sample",
                    eds=tuple(EDS9 + ["ru", "fa"]), drop=("2026-04", "2026-05")),
            replace(b, name="base g-1 (standard CS)", group="design", base_g1=True),
            replace(b, name="no seasonal adjustment", group="outcome", season=False),
            replace(b, name="year-over-year differences", group="outcome", yoy=True,
                    season=False),
            replace(b, name="edition trends 2022-12..2024-04 removed", group="trend",
                    detrend=True),
            replace(b, name="placebo: 12 months earlier", group="placebo", shift=-12),
            replace(b, name="cohorts 1 month earlier", group="timing", shift=-1),
            replace(b, name="cohorts 1 month later", group="timing", shift=1),
            replace(b, name="pre-period from 2023-07", group="design", start="2023-07",
                    note="CS uses only base and post months: identical by construction"),
            replace(b, name="core-update months dropped (post)", group="confound",
                    drop_post_core=True),
            replace(b, name="net of Google search share", group="confound", outcome="google_net"),
            replace(b, name="total user views (all access)", group="outcome", outcome="views"),
            replace(b, name="user web views", group="outcome", outcome="views_web"),
            replace(b, name="truncation-corrected search", group="outcome", outcome="corr"),
            replace(b, name="exposure all users (cohorts)", group="exposure",
                    exposure_col="exposure_all_users"),
            replace(b, name="exposure as listed (cohorts)", group="exposure",
                    exposure_col="exposure_as_listed"),
        ]
        out += [replace(b, name=f"leave out {e}", group="leave-one-out",
                        eds=tuple(x for x in EDS9 if x != e)) for e in EDS9]  # fmt: skip
    out.append(Spec("not-yet-treated controls", "design", "primary", rule="treatment"))
    f = Spec("baseline (P17)", "baseline", "full")
    out += [
        replace(f, name="bot months 2025-03..08 dropped", group="bot",
                drop=tuple(str(m) for m in pd.period_range(*BOT, freq="M"))),
        replace(f, name="edition x post-2025-04 bot step", group="bot", bot_step=True),
        replace(f, name="2025-04 rescaled", group="bot", outcome="rescaled"),
        replace(f, name="negative control: ru, fa from 2025-05 vs fr", group="negative control",
                eds=("ru", "fa", "fr"),
                treated_override={"ru": ("2025-05", "2025-05"), "fa": ("2025-05", "2025-05")},
                note="expected about dose x effect: ru 0.45, fa 0.17-0.19"),
        replace(f, name="negative control: ru alone vs fr", group="negative control",
                eds=("ru", "fr"), treated_override={"ru": ("2025-05", "2025-05")}),
    ]
    return out


def rr_rows() -> list[dict]:
    rr = pd.read_csv(QA / "p17_rr.csv")
    rr = rr[rr.M.astype(str) == "1.0"]
    pct = lambda v: 100 * (np.exp(v) - 1)  # noqa: E731
    att = pd.read_csv(QA / "p17_att.csv").query("estimator == \"Callaway-Sant'Anna\"")
    return [dict(spec="Rambachan-Roth M = 1 (P17)", group="trend", window=r.window,
                 theta=att.set_index("window").theta[r.window],
                 pct=pct(att.set_index("window").theta[r.window]), lo_pct=pct(r.lo),
                 hi_pct=pct(r.hi), ri_p=np.nan, note="interval widened by worst-case bias")
            for r in rr.itertuples()]  # fmt: skip


def figure(res: pd.DataFrame) -> plt.Figure:
    order = list(dict.fromkeys(res.spec))
    fig, axes = plt.subplots(1, 2, figsize=(15, 0.28 * len(order) + 2), sharey=True)
    y = {s: i for i, s in enumerate(order)}
    for ax, w in zip(axes, ENDS, strict=True):
        r = res[res.window == w]
        base = r[r.spec == "baseline (P17)"].pct.iloc[0]
        ax.axvline(0, color="#999999", lw=0.6)
        ax.axvline(base, color="#1f4e8c", lw=0.8, ls="--")
        ax.axvspan(-100, -5, color="#c0392b", alpha=0.04)
        for row in r.itertuples():
            c = "#c0392b" if row.group in ("placebo", "negative control") else "#1f4e8c"
            filled = (row.ri_p < 0.05) if not np.isnan(row.ri_p) else False
            ax.errorbar(row.pct, y[row.spec], xerr=[[row.pct - row.lo_pct], [row.hi_pct - row.pct]],
                        fmt="o", ms=4, lw=0.9, color=c, mfc=c if filled else "white")  # fmt: skip
        ax.set_xlim(-45, 40)
        ax.set_title(f"{w} window (dashed = P17 baseline; filled = RI p < 0.05)", loc="left",
                     fontsize=10)  # fmt: skip
        ax.set_xlabel("ATT on search arrivals, % (RI 95%)")
    axes[0].set_yticks(range(len(order)), order, fontsize=7.5)
    axes[0].invert_yaxis()
    fig.suptitle("P20 robustness: pre-registered variants of H1 (red: placebo and negative "
                 "controls, expected near 0)", x=0.01, ha="left", fontsize=12,
                 fontweight="bold")  # fmt: skip
    fig.tight_layout()
    return fig


def main() -> pd.DataFrame:
    d = panel()
    rows = []
    for s in specs():
        rows.append(estimate(d, s))
        r = rows[-1]
        pc, pv = r.get("pct", np.nan), r.get("ri_p", np.nan)
        print(f"{s.window:8s} {s.name:45s} {pc:7.2f} p={pv:.3f}", flush=True)
    res = pd.DataFrame(rows + rr_rows())
    res.round(4).to_csv(QA / "p20_robustness.csv", index=False)
    figure(res).savefig(FIG / "p20_forest.png", dpi=150, bbox_inches="tight")
    return res


if __name__ == "__main__":
    main()
