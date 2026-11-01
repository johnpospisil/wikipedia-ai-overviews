"""P15 power: placebo launches on pre-period data with the real cohort structure.

Only months 2019-04..2024-04 are read (blinding). The real design is shifted back in time: the
first cohort (en, ja, pt) starts at placebo month s, es at s+2, de/it/pl at s+7, zh at s+9, and
each edition's first partial exposure keeps its real lead (en 4 months before its cohort). The
primary window ends at s+5 (as 2025-02) with not-yet-exposed controls (de, it, pl, zh, fr); the full
window ends at s+22 (as 2026-07) with not-yet-treated controls (fr partly exposed from s+7).
Comparison group: these 9 editions (ru and fa excluded).

For each outcome and window: the placebo ATT at every start s (no effect exists, so it measures
how far the design wanders on its own), and power from injecting a constant effect delta into the
treated post cells and testing with exact randomization inference over all 30,240 distinct
assignments of the (cohort, first exposure) labels. MDE = smallest |delta| with power >= 80% at
two-sided alpha = 0.05.

Outcomes are deseasonalised logs (edition-specific month-of-year effects from the P14 trend
model). H2 and H4 are approximated at edition level as log ratios (quick/long views; tail/head
views) from the weighted article panel.

Outputs: report/qa/p15_placebo_att.csv, p15_power.csv, p15_mde.csv;
report/figures/p15_power.png
"""

from __future__ import annotations

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from wao import config
from wao.models.csdid import NEVER, assignments, att_weights
from wao.viz import eda

QA, FIG = config.REPORT_DIR / "qa", config.REPORT_DIR / "figures"
EDS = ["en", "ja", "pt", "es", "de", "it", "pl", "zh", "fr"]
# (cohort, first exposure) in months after the first cohort (2024-09); P03 language_cohorts.csv
OFFSET = {"en": (0, -4), "ja": (0, -1), "pt": (0, -1), "es": (2, -1), "de": (7, 6), "it": (7, 6),
          "pl": (7, 6), "zh": (9, 8), "fr": (NEVER, 7)}  # fmt: skip
SHORT = 7  # 2025-04 sits 7 months after the first cohort: clickstream month missing
LEAD = 5  # grid starts 5 months before the first cohort (en's base, 2024-04)
# window: (last month after the first cohort, control rule)
WINDOWS = {"primary": (5, "exposure"), "full": (22, "treatment")}
DELTAS = np.round(np.arange(0, 0.301, 0.0025), 4)
ALPHA = 0.05

# outcome: (description, needs clickstream short-month mask, event-time range)
OUTCOMES = {
    "search": ("H1 log search arrivals (primary)", True, (0, None)),
    "views": ("log user web views", False, (0, None)),
    "share": ("H5a log search share", True, (0, None)),
    "mob_desk": ("H3 log mobile-web minus log desktop views", False, (0, None)),
    "depth": ("H5b log internal-link arrivals per external arrival", True, (0, None)),
    "quick_long": ("H2 log quick-answer minus log long-read views", False, (0, None)),
    "tail_head": ("H4 log tail (deciles 1-5) minus log head (8-10) views", False, (0, None)),
    "editors": ("H6 log active registered editors, event time 6..18", False, (6, 18)),
}


def _deseason(p: pd.DataFrame, col: str) -> pd.Series:
    out = []
    for _, g in p.groupby("lang"):
        X = eda._design(g)
        y = np.log(g[col])
        r = eda._fit(y, X)
        m = [c for c in X if c.startswith("m")]
        out.append(y - X[m] @ r.params[m])
    return pd.concat(out)


def article_ratios() -> pd.DataFrame:
    src = config.PANEL_DIR / "panel_article_month" / "*" / "part.parquet"
    am = f"read_parquet('{src}', hive_partitioning=true)"
    return duckdb.connect().execute(f"""
        select lang, month,
          sum(w * v) filter (where qa_core = 1) quick, sum(w * v) filter (where qa_core = 0) long,
          sum(w * v) filter (where decile <= 5) tail, sum(w * v) filter (where decile >= 8) head
        from (select lang, month, qa_core, decile, weight w,
                     views_desktop + views_mobile_web v from {am}
              where in_lang_sample and month between '{eda.PRE_START}' and '{eda.PRE_END}')
        group by all""").df()  # fmt: skip


def outcomes() -> pd.DataFrame:
    p = eda.pre(eda.load())
    p = p[p.lang.isin(EDS)].merge(article_ratios(), on=["lang", "month"])
    lm = duckdb.connect().execute(f"""select lang, month, active_user, link_arr
        from '{config.PANEL_DIR}/panel_lang_month.parquet'""").df()  # fmt: skip
    p = p.merge(lm, on=["lang", "month"]).sort_values(["lang", "month"]).reset_index(drop=True)
    p["ext"] = p.total_arr - p.link_arr
    y = pd.DataFrame({"lang": p.lang, "month": p.month})
    y["search"] = _deseason(p, "search_arr")
    y["views"] = _deseason(p, "views_web")
    y["share"] = _deseason(p, "search_share")
    y["mob_desk"] = _deseason(p, "views_mobile_web") - _deseason(p, "views_desktop")
    p["depth"] = p.link_arr / p.ext
    y["depth"] = _deseason(p, "depth")
    y["quick_long"] = _deseason(p, "quick") - _deseason(p, "long")
    y["tail_head"] = _deseason(p, "tail") - _deseason(p, "head")
    y["editors"] = _deseason(p, "active_user")
    return y


def simulate(y: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    G0 = np.array([OFFSET[e][0] for e in EDS], float) + LEAD
    E0 = np.array([OFFSET[e][1] for e in EDS], float) + LEAD
    Gp, Ep = assignments(G0, E0)
    true = np.flatnonzero((Gp == G0).all(1) & (Ep == E0).all(1))[0]
    months = y.month.unique()
    att_rows, pow_rows, cache = [], [], {}
    for out, (_, short, (e0, e1)) in OUTCOMES.items():
        M = y.pivot(index="lang", columns="month", values=out).loc[EDS].values  # 9 x 61
        for win, (end, rule) in WINDOWS.items():
            if e1 is not None and end < e1:
                continue  # H6 needs event times to 18: full window only
            L = LEAD + end + 1  # columns s-LEAD .. s+end
            miss = np.zeros(L, bool)
            if short and LEAD + SHORT < L:
                miss[LEAD + SHORT] = True
            key = (L, short, e0, e1, rule)
            if key not in cache:
                cache[key] = np.stack([att_weights(g, L, miss, e0, e1, E=e, control=rule)
                                       for g, e in zip(Gp, Ep, strict=True)])  # fmt: skip
            Ws = cache[key]
            D = (np.arange(L)[None, :] >= G0[:, None]).astype(float)
            B = np.einsum("pij,ij->p", Ws, D)
            starts = range(LEAD, M.shape[1] - end)
            Ys = np.stack([M[:, s - LEAD : s + end + 1] for s in starts])
            A = np.einsum("pij,sij->ps", Ws, Ys)
            for k, s in enumerate(starts):
                a = A[true, k]
                att_rows.append(dict(outcome=out, window=win, start=months[s], att=a,
                                     ri_p=(np.abs(A[:, k]) >= abs(a) - 1e-12).mean()))  # fmt: skip
            for d in DELTAS:
                stat = A[true] - d * B[true]
                null = A - d * B[:, None]
                p = (np.abs(null) >= np.abs(stat)[None, :] - 1e-12).mean(0)
                pow_rows.append(dict(outcome=out, window=win, delta=d,
                                     power=(p < ALPHA).mean(), n_starts=len(p)))  # fmt: skip
    return pd.DataFrame(att_rows), pd.DataFrame(pow_rows)


def mde(att_df: pd.DataFrame, pw: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (out, win), g in pw.groupby(["outcome", "window"], sort=False):
        ok = g[(g.power >= 0.8) & (g.delta > 0)]
        d = ok.delta.min() if len(ok) else np.nan
        a = att_df[(att_df.outcome == out) & (att_df.window == win)]
        rms = np.sqrt((a.att**2).mean())
        rows.append(dict(outcome=out, description=OUTCOMES[out][0], window=win,
                         n_starts=len(a), size_at_0=g[g.delta == 0].power.iloc[0],
                         placebo_rms=rms, placebo_max_abs=a.att.abs().max(),
                         mde_ri_log=d, mde_ri_pct=100 * (np.exp(-d) - 1),
                         mde_sd_pct=100 * (np.exp(-2.8 * rms) - 1)))  # fmt: skip
    return pd.DataFrame(rows)


def figure(att_df: pd.DataFrame, pw: pd.DataFrame, m: pd.DataFrame) -> plt.Figure:
    fig, (a, b) = plt.subplots(1, 2, figsize=(14, 5))
    for out, c in (("search", "#1f4e8c"), ("views", "#999999"), ("share", "#8fa9cf"),
                   ("quick_long", "#e6b85c"), ("editors", "#c0392b")):  # fmt: skip
        if out == "editors":
            g = pw[(pw.outcome == out) & (pw.window == "full")]
            a.plot(100 * (1 - np.exp(-g.delta)), g.power, color=c, lw=1.5, label=f"{out} (full)")
            continue
        for win, ls in (("primary", "-"), ("full", "--")):
            g = pw[(pw.outcome == out) & (pw.window == win)]
            a.plot(100 * (1 - np.exp(-g.delta)), g.power, color=c, ls=ls, lw=1.5,
                   label=f"{out} ({win})")  # fmt: skip
    a.axhline(0.8, color="k", lw=0.6, ls=":")
    a.axhline(ALPHA, color="k", lw=0.6, ls=":")
    a.set_xlabel("True decline injected, %")
    a.set_ylabel("Power (exact RI, two-sided 5%)")
    a.legend(frameon=False, fontsize=7, ncol=2)
    a.set_title("Power by outcome and window (placebo launches 2019-05..)", loc="left", fontsize=10)
    for win, fmt, c in (("primary", "o-", "#1f4e8c"), ("full", "s--", "#c0392b")):
        g = att_df[(att_df.outcome == "search") & (att_df.window == win)]
        b.plot(pd.PeriodIndex(g.start, freq="M").to_timestamp(), 100 * (np.exp(g.att) - 1), fmt,
               color=c, ms=3, lw=1, label=f"{win} window")  # fmt: skip
    b.axhline(0, color="#999999", lw=0.6)
    b.set_ylabel("Placebo ATT, % (no true effect)")
    b.set_xlabel("Placebo first-cohort month")
    b.legend(frameon=False, fontsize=8)
    b.set_title("Placebo ATTs, log search arrivals (primary outcome)", loc="left", fontsize=10)
    fig.suptitle("P15 power: the real cohort structure moved back into the pre-period", x=0.01,
                 ha="left", fontsize=12, fontweight="bold")  # fmt: skip
    fig.tight_layout()
    return fig


def main() -> None:
    y = outcomes()
    att_df, pw = simulate(y)
    m = mde(att_df, pw)
    att_df.round(5).to_csv(QA / "p15_placebo_att.csv", index=False)
    pw.round(4).to_csv(QA / "p15_power.csv", index=False)
    m.round(4).to_csv(QA / "p15_mde.csv", index=False)
    figure(att_df, pw, m).savefig(FIG / "p15_power.png", dpi=150, bbox_inches="tight")
    print(m.round(3).to_string())


if __name__ == "__main__":
    main()
