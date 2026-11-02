"""P23 referral mix and reader behaviour (PREREGISTRATION.md H5a, H5b; E3 exploratory).

H5a: log(search arrivals / all arrivals), H5b: log(internal-link arrivals / (all arrivals -
internal-link arrivals)), i.e. internal clicks per external entry; both deseasonalised like
section 3, the P17 estimator in the primary window with exact RI (full window alongside). H5a
predicts theta < 0; H5b is two-sided.

E3 (exploratory, selection): do the readers who still arrive engage more? Article level, 2023
deciles 8-10 (clickstream pairs there are rarely below the <10 threshold): depth_it =
log((outgoing internal clicks + 1) / (published arrivals + 1)), with article and edition x month
FE, a separate month slope for s_i, and beta on s_i x exposure, where s_i is the article's 2023
search share of arrivals (standardised, P06 weights). beta > 0 would mean articles that depend on
search gain depth as exposure rises, consistent with the quick-lookup readers leaving first.

Chart 3: referral mix (stacked shares), the 8 treated editions pooled vs fr, 2019-04..2026-09.

Outputs: report/qa/p23_h5.csv, p23_depth_article.csv, p23_mix.csv;
report/figures/p23_referral_mix.png
"""

from __future__ import annotations

import duckdb
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from wao import config
from wao.models import did, quick, robust

QA, FIG = config.REPORT_DIR / "qa", config.REPORT_DIR / "figures"
TREATED = ["en", "ja", "pt", "es", "de", "it", "pl", "zh"]
MIX = [("search_arr", "Search engines", "#1f4e8c"), ("link_arr", "Links from other articles",
       "#8fa9cf"), ("empty_arr", "No referrer", "#c9c9c9"), ("internal_other_arr",
       "Other Wikipedia pages", "#e6b85c"), ("external_arr", "Other websites", "#c0392b"),
       ("rest", "Other", "#eeeeee")]  # fmt: skip
H5 = {"share": "H5a: search share", "depth": "H5b: internal clicks per external entry"}


def h5() -> pd.DataFrame:
    d = robust.panel()
    rows = []
    for w in robust.ENDS:
        for out, lab in H5.items():
            rows.append(robust.estimate(d, robust.Spec(lab, out, w, outcome=out)))
            print(w, lab, round(rows[-1]["pct"], 2), round(rows[-1]["ri_p"], 3), flush=True)
    return pd.DataFrame(rows)


def mix() -> pd.DataFrame:
    d = duckdb.connect().execute(f"""
        select case when lang in ({",".join(f"'{e}'" for e in TREATED)}) then 'treated (8)'
                    else lang end as grp, month,
               sum(search_arr) search_arr, sum(link_arr) link_arr, sum(empty_arr) empty_arr,
               sum(internal_other_arr) internal_other_arr, sum(external_arr) external_arr,
               sum(total_arr) total_arr
        from '{config.PANEL_DIR}/panel_lang_month.parquet'
        where lang in ({",".join(f"'{e}'" for e in TREATED + ["fr"])}) and month >= '{did.START}'
        group by all order by 1, 2""").df()
    d["rest"] = d.total_arr - d[[c for c, _, _ in MIX[:-1]]].sum(axis=1)
    for c, _, _ in MIX:
        d[c + "_share"] = d[c] / d.total_arr
    return d


def depth_article() -> pd.DataFrame:
    am = f"read_parquet('{config.PANEL_DIR}/panel_article_month/*/part.parquet', hive_partitioning=true)"  # noqa: E501
    d = duckdb.connect().execute(f"""
        with a as (
          select lang, page_id, month, weight, decile, out_links_pub, arr_total_pub, arr_search,
                 cs_usable
          from {am} where in_lang_sample and decile >= 8 and month between '{did.START}'
                and '2026-07' and month <> '2025-04'),
        s as (select lang, page_id, sum(coalesce(arr_search, 0)) / nullif(sum(arr_total_pub), 0)
                as s23
              from a where month like '2023-%' group by all)
        select a.lang, a.page_id, a.month, a.weight,
               ln((a.out_links_pub + 1) / (a.arr_total_pub + 1)) as depth, s.s23,
               coalesce(l.exposure, 0) x
        from a join s using (lang, page_id)
        join '{config.PANEL_DIR}/panel_lang_month.parquet' l using (lang, month)
        where a.cs_usable and s.s23 is not null""").df()
    art = d.groupby(["lang", "page_id"]).agg(s=("s23", "first"), w=("weight", "first"))
    mu = np.average(art.s, weights=art.w)
    sd = np.sqrt(np.average((art.s - mu) ** 2, weights=art.w))
    d["q"] = (d.s23 - mu) / sd
    d["qx"] = d.q * d.x
    d["art"] = pd.factorize(d.lang + ":" + d.page_id.astype(str))[0]
    d["lm"] = pd.factorize(d.lang + d.month)[0]
    d["m"] = pd.factorize(d.month, sort=True)[0]
    rows = []
    for name, s in (("11 editions", d), ("without fa", d[d.lang != "fa"])):
        r = quick.fit_qdelta(s, "depth")
        rows.append(dict(spec=name, articles=s.art.nunique(), mean_s23=mu, sd_s23=sd, **r))
        print(name, r, flush=True)
    out = pd.DataFrame(rows)
    out["pct"] = 100 * (np.exp(out.beta) - 1)
    out["pct_lo"], out["pct_hi"] = 100 * (np.exp(out.wcb_lo) - 1), 100 * (np.exp(out.wcb_hi) - 1)
    return out


def figure(h, mx, dep) -> plt.Figure:
    fig = plt.figure(figsize=(18, 9))
    gs = fig.add_gridspec(2, 3, height_ratios=[1.3, 1])
    for k, g in enumerate(("treated (8)", "fr")):
        ax = fig.add_subplot(gs[0, k])
        s = mx[mx.grp == g].copy()
        s["t"] = pd.PeriodIndex(s.month, freq="M").to_timestamp()
        ax.stackplot(s.t, *[s[c + "_share"] for c, _, _ in MIX], labels=[lab for _, lab, _ in MIX],
                     colors=[col for _, _, col in MIX], lw=0)  # fmt: skip
        for m, txt in (("2022-12", "ChatGPT"), ("2024-05", "AIO US"), ("2025-04", "bot reclass")):
            x = pd.Period(m, "M").to_timestamp()
            ax.axvline(x, color="k", lw=0.6, ls="--")
            ax.text(x, 1.01, txt, fontsize=7, ha="center")
        ax.set_ylim(0, 1)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        ax.set_title(f"Chart 3: referral mix, {g}", loc="left", fontsize=10, pad=14)
        if k == 1:
            ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1), frameon=False, fontsize=8)
    ax = fig.add_subplot(gs[1, 0:2])
    rows = [(f"{r.spec} ({r.window})", r.pct, r.lo_pct, r.hi_pct, r.ri_p) for r in h.itertuples()]
    rows += [(f"E3 article depth x 2023 search share, {r.spec}", r.pct, r.pct_lo, r.pct_hi,
              r.wcb_p) for r in dep.itertuples()]  # fmt: skip
    y = np.arange(len(rows))
    v = np.array([r[1] for r in rows])
    lo, hi = np.array([r[2] for r in rows]), np.array([r[3] for r in rows])
    ax.errorbar(v, y, xerr=[v - lo, hi - v], fmt="o", color="#1f4e8c", ms=4, lw=1)
    for i, r in enumerate(rows):
        ax.text(hi[i] + 0.5, i, f"p = {r[4]:.3f}", fontsize=8, va="center")
    ax.set_yticks(y, [r[0] for r in rows], fontsize=8)
    ax.invert_yaxis()
    ax.axvline(0, color="#999999", lw=0.6)
    ax.set_xlabel("% at full exposure / ATT (RI or WCB 95%)")
    ax.set_title("H5a, H5b and the article-level selection check", loc="left", fontsize=10)
    fig.suptitle("P23 referral mix and reader behaviour", x=0.01, ha="left", fontsize=12,
                 fontweight="bold")  # fmt: skip
    fig.tight_layout()
    return fig


def main() -> dict:
    h, mx, dep = h5(), mix(), depth_article()
    h.round(4).to_csv(QA / "p23_h5.csv", index=False)
    dep.round(5).to_csv(QA / "p23_depth_article.csv", index=False)
    mx.round(5).to_csv(QA / "p23_mix.csv", index=False)
    figure(h, mx, dep).savefig(FIG / "p23_referral_mix.png", dpi=150, bbox_inches="tight")
    return dict(h=h, mx=mx, dep=dep)


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    r = main()
    print(r["h"].round(3).to_string())
    print(r["dep"].round(4).to_string())
