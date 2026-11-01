"""P11 reconciliation: clickstream and the sample against AQS, per-article exactness, duplicates,
and the 2025 bot-reclassification window. Totals only (data quality), no treated-vs-control
contrast.

QA tables (report/qa/):
  p11_clickstream_vs_aqs.csv  lang x month: clickstream arrivals (all published pairs) and search
                              arrivals vs AQS `user` desktop + mobile-web views; ratio, its
                              deviation from a centred 13-month median, flag (|dev| > 8%)
  p11_sample_vs_aqs.csv       lang x month: sample views x P06 weights (user, all access) vs AQS
                              `user` all-access; ratio and flag as above
  p11_perarticle_check.csv    200 random articles: P07 views by current title (matches id and
                              null_title) vs AQS per-article, months equal, totals; and the
                              redirect-resolved total P07 uses
  p11_bot_window.csv          lang x month 2024-09..2025-12: AQS user and automated, both ratios,
                              per-article gap (does AQS differ from the dumps after the 2025
                              reclassification?)
  p11_checklist.csv           check, status, detail
Figure: report/figures/p11_reconciliation.png
"""

from __future__ import annotations

import duckdb
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from wao import config
from wao.ingest.aqs_checks import out_dir as aqs_dir

QA = config.REPORT_DIR / "qa"
FIG = config.REPORT_DIR / "figures" / "p11_reconciliation.png"
FLAG = 0.08
BOT_WINDOW = ("2025-03", "2025-08")


def _dev(df: pd.DataFrame, col: str) -> pd.DataFrame:
    med = df.groupby("lang")[col].transform(lambda s: s.rolling(13, center=True, min_periods=5)
                                            .median())  # fmt: skip
    df["dev"] = df[col] / med - 1
    df["flag"] = df.dev.abs() > FLAG
    return df


def clickstream_vs_aqs(agg: pd.DataFrame) -> pd.DataFrame:
    cs = pd.read_parquet(config.PARQUET_DIR / "clickstream_lang_month.parquet")
    web = (agg[(agg.agent == "user") & agg.access.isin(["desktop", "mobile-web"])]
           .groupby(["lang", "month"]).views.sum().rename("aqs_web"))  # fmt: skip
    d = cs[cs.lang.isin(config.LANGS)].set_index(["lang", "month"])[["total", "search"]]
    d = d.join(web, how="inner").reset_index().sort_values(["lang", "month"])
    d["ratio"] = d.total / d.aqs_web
    d["search_per_view"] = d.search / d.aqs_web
    return _dev(d, "ratio")


def sample_vs_aqs(con, agg: pd.DataFrame) -> pd.DataFrame:
    est = con.sql(f"""
        select v.lang, strftime(date, '%Y-%m') as month, sum(views * s.weight) est
        from read_parquet('{config.PARQUET_DIR}/pageview_daily/agent=user/*/part.parquet',
                          hive_partitioning=true) v
        join '{config.PANEL_DIR / "sample.parquet"}' s using (lang, page_id)
        group by all""").df()
    aqs = (agg[agg.agent == "user"].groupby(["lang", "month"]).views.sum()
           .rename("aqs_user").reset_index())  # fmt: skip
    d = est.merge(aqs, on=["lang", "month"]).sort_values(["lang", "month"])
    d["ratio"] = d.est / d.aqs_user
    return _dev(d, "ratio")


def perarticle(con) -> tuple[pd.DataFrame, pd.DataFrame]:
    a = pd.read_parquet(aqs_dir() / "per_article.parquet")
    ids = a[["lang", "page_id"]].drop_duplicates()
    con.register("ids", ids)
    ours = con.sql(f"""
        select m.lang, m.page_id, m.month,
               sum(views) filter (where match in ('id', 'null_title')) as title_views,
               sum(views) as resolved_views
        from read_parquet('{config.PARQUET_DIR}/pageview_match/agent=user/*/part.parquet',
                          hive_partitioning=true) m
        join ids using (lang, page_id) group by all""").df()
    m = a.dropna(subset=["month"]).merge(ours, on=["lang", "page_id", "month"], how="outer")
    m[["views", "title_views", "resolved_views"]] = m[["views", "title_views",
                                                       "resolved_views"]].fillna(0)  # fmt: skip
    m = m[m.month <= "2026-09"]
    m["equal"] = m.views == m.title_views
    per = m.groupby(["lang", "page_id"]).agg(
        months=("month", "size"), months_equal=("equal", "mean"), aqs=("views", "sum"),
        ours_title=("title_views", "sum"), ours_resolved=("resolved_views", "sum"))  # fmt: skip
    per["resolved_over_aqs"] = per.ours_resolved / per.aqs.replace(0, np.nan)
    return per.reset_index(), m


def bot_window(cs: pd.DataFrame, sm: pd.DataFrame, agg: pd.DataFrame, m: pd.DataFrame):
    win = ("2024-09", "2025-12")
    auto = (agg[agg.agent == "automated"].groupby(["lang", "month"]).views.sum()
            .rename("aqs_automated"))  # fmt: skip
    d = (sm.set_index(["lang", "month"])[["aqs_user", "ratio"]].rename(columns={"ratio":
         "sample_ratio"}).join(cs.set_index(["lang", "month"])[["ratio"]]
         .rename(columns={"ratio": "clickstream_ratio"})).join(auto))  # fmt: skip
    pa = m.groupby(["lang", "month"]).agg(pa_aqs=("views", "sum"), pa_ours=("title_views", "sum"))
    d = d.join(pa).reset_index()
    d["perarticle_gap"] = d.pa_ours / d.pa_aqs - 1
    return d[d.month.between(*win)]


def checklist(cs, sm, per, dup, bw) -> pd.DataFrame:
    pre = cs[cs.month.between("2018-01", "2024-04")]
    y23 = sm[sm.month.str.startswith("2023")].groupby("lang")[["est", "aqs_user"]].sum()
    y23_year = y23.est / y23.aqs_user
    exact = per[per.months > 0]
    win = bw[bw.month.between(*BOT_WINDOW)]
    r = cs.pivot(index="month", columns="lang", values="ratio")
    apr = r.loc["2025-04"] / r.loc[["2025-03", "2025-05"]].mean()
    rows = [
        ("clickstream / AQS web views, range 2018-01..2024-04",
         "info", f"{pre.ratio.min():.2f}-{pre.ratio.max():.2f} "
                 f"(median {pre.ratio.median():.2f}); flagged months {int(cs.flag.sum())}"),
        ("sample (weighted) / AQS user, 2023 (AQS also counts the Main Page and other "
         "namespaces)", "pass" if y23_year.between(0.80, 1.02).all() else "fail",
         " ".join(f"{k} {v:.2f}" for k, v in y23_year.items())),
        ("sample / AQS month-to-month stability (months >8% off the 13-month median)",
         "info", f"{int(sm.flag.sum())} of {len(sm)} edition-months"),
        ("per-article: P07 current-title views == AQS (share of article-months)",
         "pass" if exact.months_equal.mean() > 0.97 else "fail",
         f"{(exact.months_equal * exact.months).sum() / exact.months.sum():.4f} of "
         f"{int(exact.months.sum())} article-months, {len(exact)} articles"),
        ("redirect-resolved views >= AQS title views (per article, 1% tolerance)",
         "pass" if (per.ours_resolved >= 0.99 * per.aqs).all() else "fail",
         f"median resolved/AQS {per.resolved_over_aqs.median():.3f}, "
         f"p90 {per.resolved_over_aqs.quantile(0.9):.3f}"),
        ("duplicate article-day-access rows in pageview_daily", "pass" if dup == 0 else "fail",
         str(dup)),
        ("clickstream 2025-04 complete (ratio vs mean of 2025-03 and 2025-05)",
         "fail" if (apr < 0.9).any() else "pass",
         f"{apr.min():.3f}-{apr.max():.3f} of neighbouring months in every edition; consistent "
         "with ~5 missing days"),
        ("2025 bot window: per-article P07/AQS gap 2025-03..08",
         "info", f"mean {win.perarticle_gap.mean():+.3f}, max |gap| "
                 f"{win.perarticle_gap.abs().max():.3f}"),
    ]  # fmt: skip
    return pd.DataFrame(rows, columns=["check", "status", "detail"])


def figure(cs: pd.DataFrame, sm: pd.DataFrame) -> None:
    langs = sorted(cs.lang.unique())
    fig, axes = plt.subplots(3, 4, figsize=(16, 9.5), sharex=True)
    for ax, lang in zip(axes.flat, langs, strict=False):
        c, s = cs[cs.lang == lang], sm[(sm.lang == lang) & (sm.month >= "2016-01")]
        ax.axvspan(pd.Timestamp("2025-03-01"), pd.Timestamp("2025-08-31"), color="0.9")
        ax.axvline(pd.Timestamp("2019-04-01"), color="0.5", lw=0.8, ls="--")
        ax.plot(pd.to_datetime(c.month), c.ratio, color="#4c72b0", lw=1.3,
                label="clickstream arrivals / AQS web views")  # fmt: skip
        ax.plot(pd.to_datetime(s.month), s.ratio, color="#dd8452", lw=1.1,
                label="weighted sample / AQS user views")  # fmt: skip
        f = c[c.flag]
        ax.plot(pd.to_datetime(f.month), f.ratio, "o", ms=3.5, color="#c44e52",
                label="flagged (>8% off the 13-month median)")  # fmt: skip
        ax.set_title(lang, loc="left", fontsize=11)
        ax.set_ylim(0, 1.3)
        ax.spines[["top", "right"]].set_visible(False)
    axes.flat[-1].axis("off")
    h, lab = axes.flat[0].get_legend_handles_labels()
    axes.flat[-1].legend(h, lab, loc="center", fontsize=9, frameon=False)
    fig.suptitle("P11 · Reconciliation with AQS. Dashed: 2019-04 clickstream method change; "
                 "grey: 2025-03..08 bot reclassification window",
                 x=0.01, ha="left", fontsize=12)  # fmt: skip
    fig.tight_layout()
    FIG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG, dpi=150)


def main() -> None:
    con = duckdb.connect()
    con.execute("set TimeZone='UTC'")
    agg = pd.read_parquet(aqs_dir() / "aggregate.parquet")
    cs = clickstream_vs_aqs(agg)
    sm = sample_vs_aqs(con, agg)
    per, m = perarticle(con)
    con.execute(f"set temp_directory='{config.TMP_DIR}'")
    dup = con.execute(f"""select count(*) from (
        select lang, page_id, date, access, agent, count(*) n
        from read_parquet('{config.PARQUET_DIR}/pageview_daily/*/*/part.parquet',
                          hive_partitioning=true)
        group by all having n > 1)""").fetchone()[0]
    bw = bot_window(cs, sm, agg, m)
    QA.mkdir(parents=True, exist_ok=True)
    out = {"p11_clickstream_vs_aqs": cs, "p11_sample_vs_aqs": sm, "p11_perarticle_check": per,
           "p11_bot_window": bw, "p11_checklist": checklist(cs, sm, per, dup, bw)}  # fmt: skip
    for name, df in out.items():
        df.round(5).to_csv(QA / f"{name}.csv", index=False)
    figure(cs, sm)
    print(out["p11_checklist"].to_string(index=False))
    print(cs[cs.flag][["lang", "month", "ratio", "dev"]].to_string(index=False))


if __name__ == "__main__":
    main()
