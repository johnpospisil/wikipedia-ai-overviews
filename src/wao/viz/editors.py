"""P09 QA and figure: editor and edit series by edition (descriptive, data quality only).

QA tables (report/qa/):
  p09_aqs_year.csv        lang x year: content edits by editor type, mean monthly active editors
                          (5+ edits) and very active (100+), registered and anonymous
  p09_reconcile_2023.csv  lang: 2023 edits estimated from the sample (Horvitz-Thompson weights)
                          vs AQS content edits, for non-bot and bot edits
  p09_perpage_check.csv   20 random sample articles: 2023 edits from the stubs vs AQS per-page
  p09_temp_accounts.csv   lang: first month with temporary-account edits in the stubs, and the
                          AQS anonymous active editors in the 6 months before and after
  p09_temp_check.csv      lang x month around the rollout: sample-estimated IP and temporary-
                          account edits vs AQS anonymous and user edits (how AQS classifies
                          temporary accounts)
  p09_gaps.csv            lang x metric: first/last AQS month and missing months
Figure: report/figures/p09_editors.png, active editors per edition 2016-2026, no launch dates
(blinding rule: no treated-vs-control contrasts before P15).
"""

from __future__ import annotations

import duckdb
import matplotlib.pyplot as plt
import pandas as pd

from wao import config, http
from wao.build.edits import out_path as edits_path
from wao.ingest.editors import AQS, out_dir

QA = config.REPORT_DIR / "qa"
FIG = config.REPORT_DIR / "figures" / "p09_editors.png"
ACTIVE = ("5..24-edits", "25..99-edits", "100..-edits")


def wide(a: pd.DataFrame) -> pd.DataFrame:
    """lang x month: edits_<type>, active_<type> (5+), very_active_<type> (100+)."""
    ed = a[a.metric == "edits"].pivot_table("value", ["lang", "month"], "editor_type")
    ed.columns = [f"edits_{c.replace('-', '_')}" for c in ed.columns]
    e = a[a.metric == "editors"]
    act = e[e.activity.isin(ACTIVE)].pivot_table("value", ["lang", "month"], "editor_type",
                                                 aggfunc="sum")  # fmt: skip
    act.columns = [f"active_{c}" for c in act.columns]
    va = e[e.activity == "100..-edits"].pivot_table("value", ["lang", "month"], "editor_type")
    va.columns = [f"very_active_{c}" for c in va.columns]
    return ed.join(act, how="outer").join(va, how="outer").fillna(0).reset_index()


def reconcile(con, w: pd.DataFrame) -> pd.DataFrame:
    s = (
        con.sql(f"""
        select e.lang, sum((edits_user + edits_anon) * s.weight) est_nonbot,
               sum(edits_bot * s.weight) est_bot, sum(edits_user + edits_anon) sample_nonbot
        from '{edits_path()}' e join '{config.PANEL_DIR / "sample.parquet"}' s using (lang, page_id)
        where month like '2023-%' group by 1""")
        .df()
        .set_index("lang")
    )
    y = w[w.month.str.startswith("2023")].groupby("lang").sum(numeric_only=True)
    s["aqs_nonbot"] = y.edits_user + y.edits_anonymous
    s["aqs_bot"] = y.edits_group_bot + y.edits_name_bot
    s["ratio_nonbot"] = s.est_nonbot / s.aqs_nonbot
    s["ratio_bot"] = s.est_bot / s.aqs_bot
    return s.round(3)


def perpage(con, n: int = 20) -> pd.DataFrame:
    pick = con.sql(f"""
        select s.lang, s.page_id, s.title, coalesce(sum(e.edits), 0) stub_edits
        from (select * from '{config.PANEL_DIR / "sample.parquet"}'
              using sample reservoir({n} rows) repeatable (9)) s
        left join (select * from '{edits_path()}' where month like '2023-%') e
          using (lang, page_id) group by all""").df()
    sess = http.session("aqs", min_interval=7.0)
    out = []
    for r in pick.itertuples():
        url = (f"{AQS}/edits/per-page/{r.lang}.wikipedia.org/{r.title}/all-editor-types/"
               "monthly/20230101/20240101")  # fmt: skip
        resp = sess.get(url, timeout=60)
        items = resp.json().get("items", []) if resp.status_code == 200 else []
        aqs = sum(x["edits"] for x in items[0]["results"]) if items else 0
        out.append({"lang": r.lang, "page_id": r.page_id, "stub_edits": int(r.stub_edits),
                    "aqs_edits": aqs, "http": resp.status_code})  # fmt: skip
    return pd.DataFrame(out)


def temp_accounts(con, w: pd.DataFrame) -> pd.DataFrame:
    first = (
        con.sql(f"""
        select lang, strftime(min(ts), '%Y-%m') first_temp, count(*) temp_edits
        from read_parquet('{config.PARQUET_DIR}/stub_history/*/*.parquet', hive_partitioning=true)
        where kind = 'temp' group by 1""")
        .df()
        .set_index("lang")
    )
    for lang, m in first.first_temp.items():
        g = w[w.lang == lang].set_index("month").active_anonymous
        before = g[g.index < m].tail(6).mean()
        after = g[g.index >= m].head(6).mean()
        first.loc[lang, ["anon_active_6m_before", "anon_active_6m_after"]] = before, after
    return first.round(1)


def temp_check(con, w: pd.DataFrame, temp: pd.DataFrame) -> pd.DataFrame:
    est = con.sql(f"""
        select h.lang, strftime(ts, '%Y-%m') as month,
               sum(s.weight) filter (where kind = 'ip') est_ip,
               sum(s.weight) filter (where kind = 'temp') est_temp,
               sum(s.weight) filter (where kind = 'user' and not name_bot) est_user
        from read_parquet('{config.PARQUET_DIR}/stub_history/*/*.parquet', hive_partitioning=true) h
        join '{config.PANEL_DIR / "sample.parquet"}' s on s.lang = h.lang and s.page_id = h.page_id
        where ts >= '2024-01-01' group by all""").df()
    df = est.merge(w[["lang", "month", "edits_anonymous", "edits_user"]], on=["lang", "month"])
    keep = []
    for lang, m in temp.first_temp.items():
        start = (pd.Period(m, "M") - 6).strftime("%Y-%m")
        end = (pd.Period(m, "M") + 6).strftime("%Y-%m")
        keep.append(df[(df.lang == lang) & df.month.between(start, end)])
    return pd.concat(keep).sort_values(["lang", "month"]).fillna(0).round(0)


def gaps(a: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (lang, metric), g in a.groupby(["lang", "metric"]):
        months = pd.PeriodIndex(sorted(g.month.unique()), freq="M")
        full = pd.period_range(months.min(), months.max(), freq="M")
        miss = len(full.difference(months))
        rows.append({"lang": lang, "metric": metric, "first": str(months.min()),
                     "last": str(months.max()), "missing": miss})  # fmt: skip
    return pd.DataFrame(rows)


def figure(w: pd.DataFrame, temp: pd.DataFrame) -> None:
    langs = sorted(w.lang.unique())
    fig, axes = plt.subplots(3, 4, figsize=(16, 10), sharex=True)
    for ax, lang in zip(axes.flat, langs, strict=False):
        g = w[(w.lang == lang) & (w.month >= "2016-01")].copy()
        x = pd.to_datetime(g.month)
        ax.plot(x, g.active_user, color="#4c72b0", lw=1.4, label="registered, 5+ edits")
        ax.plot(x, g.active_anonymous, color="#dd8452", lw=1.2, label="anonymous, 5+ edits")
        ax.plot(x, g.very_active_user, color="#4c72b0", lw=1, ls="--",
                label="registered, 100+ edits")  # fmt: skip
        if lang in temp.index and temp.loc[lang, "first_temp"] >= "2016-01":
            ax.axvline(pd.Timestamp(temp.loc[lang, "first_temp"]), color="0.6", lw=0.8, ls=":")
        ax.set_title(lang, loc="left", fontsize=11)
        ax.set_ylim(0, None)
        ax.spines[["top", "right"]].set_visible(False)
    axes.flat[-1].axis("off")
    axes.flat[0].legend(fontsize=8, loc="lower left")
    fig.suptitle("P09 · Active editors per month (content pages, bots excluded; AQS). "
                 "Dotted line: first temporary-account edit (anonymous editors redefined)",
                 x=0.01, ha="left", fontsize=12)  # fmt: skip
    fig.tight_layout()
    FIG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG, dpi=150)


def main() -> None:
    con = duckdb.connect()
    con.execute("set TimeZone='UTC'")
    a = pd.read_parquet(out_dir() / "aqs_lang_month.parquet")
    w = wide(a)
    w.to_parquet(config.PANEL_DIR / "editors_lang_month.parquet", index=False)
    QA.mkdir(parents=True, exist_ok=True)
    w["year"] = w.month.str[:4]
    year = w.groupby(["lang", "year"]).agg(
        {c: "sum" if c.startswith("edits") else "mean" for c in w.columns
         if c.startswith(("edits", "active", "very_active"))}).round(0)  # fmt: skip
    year.to_csv(QA / "p09_aqs_year.csv")
    temp = temp_accounts(con, w)
    tables = {"p09_reconcile_2023": reconcile(con, w), "p09_temp_accounts": temp,
              "p09_temp_check": temp_check(con, w, temp), "p09_gaps": gaps(a),
              "p09_perpage_check": perpage(con)}  # fmt: skip
    for name, df in tables.items():
        df.to_csv(QA / f"{name}.csv")
        print(name, df, sep="\n")
    figure(w, temp)


if __name__ == "__main__":
    main()
