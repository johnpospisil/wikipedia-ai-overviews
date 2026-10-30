"""P07 QA and figure: how completely the sample articles are found in pageview_complete.

QA tables (report/qa/):
  p07_coverage.csv   lang x agent x month: articles found, share of the sample, share of the
                     articles already "alive" (seen in this or an earlier month), gaps (articles
                     seen before and after but not in this month)
  p07_match.csv      agent x month x match: rows, views, articles (how views were matched)
  p07_files.csv      per-file log: lines, matched rows, bad and inconsistent lines, seconds
Figure: report/figures/p07_pageview_coverage.png. Data quality only: no treated-vs-control
contrasts.
"""

from __future__ import annotations

import json

import duckdb
import matplotlib.pyplot as plt
import pandas as pd

from wao import config

P = config.PARQUET_DIR
MATCH_ORDER = ["id", "id_alt_title", "redirect_id", "null_title", "null_redirect", "old_id"]
MATCH_LABEL = {
    "id": "page_id, current title",
    "id_alt_title": "page_id, other title (redirect or pre-move)",
    "redirect_id": "redirect page_id",
    "null_title": "no page_id, title",
    "null_redirect": "no page_id, redirect title",
    "old_id": "deleted page_id, title",
}


def tables(con: duckdb.DuckDBPyConnection) -> tuple[pd.DataFrame, pd.DataFrame]:
    con.execute(f"set temp_directory='{config.TMP_DIR}'")
    seen = con.execute(
        f"""
        select lang, page_id, agent, month, sum(views) views
        from read_parquet('{P}/pageview_daily/*/*/part.parquet', hive_partitioning=true)
        group by all
        """
    ).df()
    n = pd.read_parquet(config.PANEL_DIR / "sample.parquet").groupby("lang").size()
    rows = []
    for (lang, agent), g in seen.groupby(["lang", "agent"]):
        months = sorted(g.month.unique())
        by_art = g.groupby("page_id").month.agg(["min", "max"])
        ids = g.groupby("month").page_id.agg(set)
        for m in months:
            alive = by_art["min"] <= m
            inside = by_art.index[(by_art["min"] < m) & (by_art["max"] > m)]
            rows.append(
                {
                    "lang": lang,
                    "agent": agent,
                    "month": m,
                    "found": len(ids[m]),
                    "sample": int(n[lang]),
                    "share_sample": len(ids[m]) / n[lang],
                    "share_alive": len(ids[m]) / int(alive.sum()),
                    "gaps": int(sum(i not in ids[m] for i in inside)),
                }
            )
    cov = pd.DataFrame(rows)
    match = con.execute(
        f"""
        select agent, month, match, sum(rows)::bigint rows, sum(views)::bigint views,
               count(distinct (lang, page_id)) articles
        from read_parquet('{P}/pageview_match/*/*/part.parquet', hive_partitioning=true)
        group by all order by all
        """
    ).df()
    return cov, match


def figure(cov: pd.DataFrame, match: pd.DataFrame) -> plt.Figure:
    fig, (a, b) = plt.subplots(1, 2, figsize=(13, 5))
    u = cov[cov.agent == "user"].assign(month=lambda d: pd.to_datetime(d.month))
    for lang, g in u.groupby("lang"):
        a.plot(g.month, 100 * g.share_sample, lw=1.2, label=lang)
    a.set_ylabel("Sample articles with any user view (%)")
    a.set_ylim(0, 101)
    a.set_title("Coverage: articles not yet created explain the early gap", loc="left", fontsize=11)
    a.legend(ncol=4, fontsize=8, frameon=False, loc="lower right")

    m = match[(match.agent == "user") & (match.match != "other_page")]
    w = m.pivot_table(index="month", columns="match", values="views", aggfunc="sum").fillna(0)
    w = w.reindex(columns=[c for c in MATCH_ORDER if c in w])
    share = 100 * w.div(w.sum(axis=1), axis=0)
    idx = pd.to_datetime(share.index)
    b.stackplot(idx, share.T.to_numpy(), labels=[MATCH_LABEL[c] for c in share])
    b.set_ylim(80, 100)
    b.set_ylabel("Share of matched user views (%), axis from 80%")
    b.set_title("How views were matched to the article", loc="left", fontsize=11)
    b.legend(fontsize=8, frameon=False, loc="lower left")
    fig.suptitle(
        "P07 daily pageviews for the 197k-article sample (pageview_complete, user agent)",
        x=0.01,
        ha="left",
        fontweight="bold",
    )
    fig.tight_layout()
    return fig


def main() -> None:
    cov, match = tables(duckdb.connect())
    qa = config.REPORT_DIR / "qa"
    cov.to_csv(qa / "p07_coverage.csv", index=False)
    match.to_csv(qa / "p07_match.csv", index=False)
    log = config.DATA_DIR / "logs" / "pageviews.jsonl"
    files = pd.DataFrame([json.loads(x) for x in log.read_text().splitlines()])
    files.sort_values(["agent", "month"]).drop_duplicates(["agent", "month"], keep="last").to_csv(
        qa / "p07_files.csv", index=False
    )
    out = config.FIGURE_DIR / "p07_pageview_coverage.png"
    figure(cov, match).savefig(out, dpi=160)
    print(out)


if __name__ == "__main__":
    main()
