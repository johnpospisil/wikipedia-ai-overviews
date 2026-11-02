"""P22 mobile vs desktop (H3) and head vs tail (H4) (PREREGISTRATION.md section 6).

H3, edition level, the primary design and window (P17): outcome log(mobile-web views) - log(desktop
views), deseasonalised; theta < 0 predicted; exact RI p and interval. The full window and each
access type on its own (desktop, mobile web, app) are reported alongside.

H4, article level, as H2 (P21) with q replaced by tail_i = 1 if the article's 2023 popularity
decile is 1-5 and 0 if 8-10 (6-7 excluded). Decile membership is fixed in 2023 (pre-period), so
regression to the mean cannot create a post-launch difference. Outcome: log(1 + user web views),
not censored; two-sided; restricted WCB p by edition. Secondary: truncation-corrected search
arrivals (censored months set to the P11 imputed value; P11 found raw clickstream unusable below
decile 8). Exploratory: without fa, and the exposure effect by decile relative to decile 10.

Outputs: report/qa/p22_h3.csv, p22_h4.csv, p22_by_decile.csv; report/figures/p22_access_pop.png
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from wao import config
from wao.models import quick, robust

QA, FIG = config.REPORT_DIR / "qa", config.REPORT_DIR / "figures"
ACCESS = {"mob_desk": "H3: mobile web - desktop", "views_desktop": "desktop",
          "views_mobile_web": "mobile web", "views_app": "app"}  # fmt: skip


def h3() -> pd.DataFrame:
    d = robust.panel()
    rows = []
    for w in robust.ENDS:
        for out, lab in ACCESS.items():
            s = robust.Spec(lab, "H3" if out == "mob_desk" else "by access", w, outcome=out)
            rows.append(robust.estimate(d, s))
            print(w, lab, round(rows[-1]["pct"], 2), round(rows[-1]["ri_p"], 3), flush=True)
    return pd.DataFrame(rows)


def h4(d: pd.DataFrame) -> pd.DataFrame:
    s = d[(d.decile <= 5) | (d.decile >= 8)].copy()
    s["q"] = (s.decile <= 5).astype(float)
    s["qx"] = s.q * s.x
    runs = [("H4: tail x exposure, views, 11 editions", "pre-registered", s, "views"),
            ("tail x exposure, truncation-corrected search", "secondary", s, "search"),
            ("without fa, views", "exploratory", s[s.lang != "fa"], "views"),
            ("without fa, truncation-corrected search", "exploratory", s[s.lang != "fa"],
             "search")]  # fmt: skip
    rows = []
    for name, status, data, y in runs:
        r = quick.fit_qdelta(data[data[y].notna()], y)
        rows.append(dict(spec=name, status=status, **r))
        print(f"{name:50s} beta={r['beta']:+.4f} p={r['wcb_p']:.3f}", flush=True)
    out = pd.DataFrame(rows)
    pct = lambda v: 100 * (np.exp(v) - 1)  # noqa: E731
    out["pct"], out["pct_lo"], out["pct_hi"] = pct(out.beta), pct(out.wcb_lo), pct(out.wcb_hi)
    return out


def by_decile(d: pd.DataFrame) -> pd.DataFrame:
    out = []
    for y in ("views", "search"):
        g = quick.by_group(d, "decile", 10, y=y)
        out.append(g.assign(outcome=y))
    return pd.concat(out)


def figure(t3, t4, dec) -> plt.Figure:
    pct = lambda v: 100 * (np.exp(v) - 1)  # noqa: E731
    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5), gridspec_kw={"width_ratios": [1, 1, 0.9]})
    ax = axes[0]
    labs = list(ACCESS.values())
    for k, (w, c) in enumerate((("primary", "#1f4e8c"), ("full", "#c0392b"))):
        r = t3[t3.window == w].set_index("spec").loc[labs]
        y = np.arange(len(labs)) + (k - 0.5) * 0.25
        ax.errorbar(r.pct, y, xerr=[r.pct - r.lo_pct, r.hi_pct - r.pct], fmt="o", color=c, ms=4,
                    lw=1, label=f"{w} window", mfc=c)  # fmt: skip
    ax.set_yticks(range(len(labs)), labs)
    ax.invert_yaxis()
    ax.axvline(0, color="#999999", lw=0.6)
    ax.set_xlabel("ATT, % (RI 95%)")
    ax.legend(frameon=False, fontsize=8)
    ax.set_title("H3: by access type (edition level, CS)", loc="left", fontsize=10)
    ax = axes[1]
    for y, c, off in (("views", "#999999", -0.12), ("search", "#1f4e8c", 0.12)):
        g = dec[dec.outcome == y].sort_values("decile")
        ax.errorbar(g.decile + off, pct(g.est), yerr=1.96 * 100 * g.se, fmt="o", color=c, ms=4,
                    lw=1, label={"views": "user web views",
                                 "search": "search (truncation-corrected)"}[y])  # fmt: skip
    ax.axhline(0, color="#999999", lw=0.6)
    ax.set_xticks(range(1, 10))
    ax.set_xlabel("2023 popularity decile (1 = least viewed; reference = 10)")
    ax.set_ylabel("Effect of full exposure vs decile 10, %")
    ax.legend(frameon=False, fontsize=8)
    ax.set_title("By popularity decile (CRV1 95%, exploratory)", loc="left", fontsize=10)
    ax = axes[2]
    y = np.arange(len(t4))
    ax.errorbar(t4.pct, y, xerr=[t4.pct - t4.pct_lo, t4.pct_hi - t4.pct], fmt="o", color="#1f4e8c",
                ms=4, lw=1)  # fmt: skip
    ax.set_yticks(y, t4.spec, fontsize=8)
    ax.invert_yaxis()
    ax.axvline(0, color="#999999", lw=0.6)
    ax.set_xlabel("Tail (deciles 1-5) vs head (8-10), % at full exposure (WCB 95%)")
    ax.set_title("H4: head vs tail", loc="left", fontsize=10)
    fig.suptitle("P22 mobile vs desktop, head vs tail", x=0.01, ha="left", fontsize=12,
                 fontweight="bold")  # fmt: skip
    fig.tight_layout()
    return fig


def main() -> dict:
    t3 = h3()
    d = quick.load()
    t4, dec = h4(d), by_decile(d)
    t3.round(4).to_csv(QA / "p22_h3.csv", index=False)
    t4.round(5).to_csv(QA / "p22_h4.csv", index=False)
    dec.round(5).to_csv(QA / "p22_by_decile.csv", index=False)
    figure(t3, t4, dec).savefig(FIG / "p22_access_pop.png", dpi=150, bbox_inches="tight")
    return dict(t3=t3, t4=t4, dec=dec)


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    r = main()
    print(r["t3"].round(3).to_string())
    print(r["t4"].round(4).to_string())
    print(r["dec"].round(4).to_string())
