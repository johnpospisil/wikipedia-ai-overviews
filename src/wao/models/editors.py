"""P24 editors vs readers, trimmed (PREREGISTRATION.md H6) and the final Holm adjustment.

H6: log AQS active registered editors (5+ content edits a month, bots excluded; anonymous editors
left out because temporary accounts redefine them from 2025-06, P09), deseasonalised like
section 3, the P17 estimator in the full window, aggregated over event times 6..18 only; theta < 0
predicted; exact RI p and interval. P15 showed this test cannot reach 80% power even for a 26%
drop, so a non-significant result is uninformative. The full-window ATT over all event times is
shown for context.

Chart 6: active registered editors and user views per edition, indexed 2019-04..2020-03 = 100
(12-month centred means), with each edition's cohort month.

Holm: H2-H6 decision p-values (P21-P24) adjusted with Holm's method at alpha = 0.05.

Outputs: report/qa/p24_h6.csv, report/qa/holm.csv; report/figures/p24_editors.png
"""

from __future__ import annotations

import duckdb
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from wao import config
from wao.models import robust
from wao.viz.eda import COHORT_COLOUR, ORDER

QA, FIG = config.REPORT_DIR / "qa", config.REPORT_DIR / "figures"


def h6() -> pd.DataFrame:
    d = robust.panel()
    specs = [robust.Spec("H6: registered editors, event times 6..18", "H6", "full",
                         outcome="active_user", e_min=6, e_max=18),
             robust.Spec("registered editors, all event times (context)", "context", "full",
                         outcome="active_user")]  # fmt: skip
    rows = [robust.estimate(d, s) for s in specs]
    for r in rows:
        print(r["spec"], round(r["pct"], 2), round(r["ri_p"], 3), flush=True)
    return pd.DataFrame(rows)


def holm(p6: float) -> pd.DataFrame:
    src = [("H2", "quick-answer x exposure (views)", QA / "p21_h2.csv", "wcb_p", 0),
           ("H3", "mobile web - desktop (primary)", QA / "p22_h3.csv", "ri_p", 0),
           ("H4", "tail vs head (views)", QA / "p22_h4.csv", "wcb_p", 0),
           ("H5a", "search share (primary)", QA / "p23_h5.csv", "ri_p", 0),
           ("H5b", "depth (primary)", QA / "p23_h5.csv", "ri_p", 1)]  # fmt: skip
    rows = [dict(hypothesis=h, test=t, p=float(pd.read_csv(f)[c].iloc[i])) for h, t, f, c, i in src]
    rows.append(dict(hypothesis="H6", test="registered editors, e 6..18 (full)", p=p6))
    df = pd.DataFrame(rows).sort_values("p").reset_index(drop=True)
    m = len(df)
    df["holm_p"] = np.minimum(1, np.maximum.accumulate(df.p * (m - df.index)))
    df["threshold"] = 0.05 / (m - df.index)
    df["supported"] = df.holm_p < 0.05
    return df.sort_values("hypothesis")


def chart6() -> plt.Figure:
    d = duckdb.connect().execute(f"""
        select lang, month, cohort, active_user, views_desktop + views_mobile_web + views_app v
        from '{config.PANEL_DIR}/panel_lang_month.parquet'
        where core and month >= '2019-04' and month <= '2026-09' order by lang, month""").df()
    d["t"] = pd.PeriodIndex(d.month, freq="M").to_timestamp()
    fig, axes = plt.subplots(3, 4, figsize=(14, 9), sharex=True, sharey=True)
    for ax, lang in zip(axes.flat, ORDER + [None], strict=True):
        if lang is None:
            ax.axis("off")
            ax.plot([], [], color="#1f4e8c", lw=1.8, label="active registered editors (5+)")
            ax.plot([], [], color="#999999", lw=1.2, label="user views")
            ax.plot([], [], color="#c0392b", lw=1, ls="--", label="cohort month")
            ax.legend(loc="center", frameon=False, fontsize=9)
            continue
        g = d[d.lang == lang].set_index("t")
        for col, c, lw in (("active_user", "#1f4e8c", 1.8), ("v", "#999999", 1.2)):
            sm = g[col].rolling(12, center=True, min_periods=6).mean()
            base = g[col]["2019-04":"2020-03"].mean()
            ax.plot(sm.index, 100 * sm / base, color=c, lw=lw)
        coh = g.cohort.iloc[0]
        if coh != "never":
            ax.axvline(pd.Period(coh, "M").to_timestamp(), color="#c0392b", lw=1, ls="--")
        ax.axhline(100, color="#dddddd", lw=0.6, zorder=0)
        ax.set_title(f"{lang} (cohort {coh})", loc="left", fontsize=10,
                     color=COHORT_COLOUR.get(coh, "k"))  # fmt: skip
        ax.xaxis.set_major_locator(mdates.YearLocator(2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%y"))
    fig.suptitle("Chart 6: editors vs readers, index 2019-04..2020-03 = 100 (12-month centred "
                 "means; descriptive)", x=0.01, ha="left", fontsize=12,
                 fontweight="bold")  # fmt: skip
    fig.tight_layout()
    return fig


def main() -> dict:
    t = h6()
    hb = holm(float(t.ri_p.iloc[0]))
    t.round(4).to_csv(QA / "p24_h6.csv", index=False)
    hb.round(4).to_csv(QA / "holm.csv", index=False)
    chart6().savefig(FIG / "p24_editors.png", dpi=150, bbox_inches="tight")
    return dict(h6=t, holm=hb)


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    r = main()
    print(r["h6"].round(3).to_string())
    print(r["holm"].to_string())
