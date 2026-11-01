"""P10 QA and figure: which engines sit behind each edition's `other-search` arrivals.

QA tables (report/qa/):
  p10_engines_lang_year.csv     wiki x year: mean engine shares of the edition's readers
  p10_google_share_markets.csv  key country x year: Google, Bing, Yahoo!, Yandex, Baidu, Naver
  p10_non_google_lang.csv       wiki: pre-period (2023-10..2024-04) non-Google share and the
                                largest other engine; flags editions where non-Google >= 10%
Figure: report/figures/p10_search_engines.png, engine mix per core edition 2017-11..2026-09
(StatCounter, weighted by the fixed P03 reader shares), core-update months marked. Search
engine shares are context, not an outcome.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd

from wao import config
from wao.build.search_context import ENGINES

QA = config.REPORT_DIR / "qa"
FIG = config.REPORT_DIR / "figures" / "p10_search_engines.png"
CORE = ["en", "ja", "pt", "es", "de", "it", "pl", "zh", "fr", "ru", "fa"]
MARKETS = ["US", "GB", "IN", "CA", "AU", "JP", "BR", "PT", "ES", "MX", "AR", "DE", "AT", "CH",
           "IT", "PL", "FR", "BE", "RU", "UA", "BY", "KZ", "TW", "HK", "CN", "SG", "IR",
           "KR"]  # fmt: skip
PRE = ("2023-10", "2024-04")
COLORS = {"google": "#4c72b0", "bing": "#dd8452", "yahoo": "#8172b3", "yandex": "#c44e52",
          "baidu": "#55a868", "naver": "#64b5cd", "duckduckgo": "#937860",
          "other": "#bbbbbb"}  # fmt: skip


def tables(cs: pd.DataFrame, ls: pd.DataFrame) -> dict[str, pd.DataFrame]:
    ls = ls[ls.wiki.isin(CORE)].assign(year=lambda d: d.month.str[:4])
    by_year = ls.groupby(["wiki", "year", "engine"]).share.mean().unstack("engine").fillna(0)
    m = cs[cs.country_iso2.isin(MARKETS)].assign(year=lambda d: d.month.str[:4])
    markets = (m.groupby(["country_iso2", "year", "engine"]).share.mean().unstack("engine")
               .fillna(0)[["google", "bing", "yahoo", "yandex", "baidu", "naver"]])  # fmt: skip
    pre = ls[ls.month.between(*PRE)].groupby(["wiki", "engine"]).share.mean().unstack().fillna(0)
    others = pre.drop(columns="google")
    flag = pd.DataFrame({"google": pre.google, "non_google": 1 - pre.google,
                         "largest_other": others.idxmax(axis=1),
                         "its_share": others.max(axis=1)})  # fmt: skip
    flag["non_google_ge_10pct"] = flag.non_google >= 0.10
    return {"p10_engines_lang_year": by_year.round(4), "p10_google_share_markets": markets.round(4),
            "p10_non_google_lang": flag.round(4)}  # fmt: skip


def figure(ls: pd.DataFrame, rm: pd.DataFrame) -> None:
    fig, axes = plt.subplots(3, 4, figsize=(16, 9.5), sharex=True, sharey=True)
    core_months = pd.to_datetime(rm.loc[rm.core_update, "month"])
    for ax, wiki in zip(axes.flat, CORE, strict=False):
        w = ls[ls.wiki == wiki].pivot(index="month", columns="engine", values="share")
        w = w.reindex(columns=ENGINES).fillna(0)
        x = pd.to_datetime(w.index)
        ax.stackplot(x, *[w[e] for e in ENGINES], colors=[COLORS[e] for e in ENGINES],
                     labels=ENGINES, linewidth=0)  # fmt: skip
        ax.plot(core_months, [0.015] * len(core_months), "|", color="black", ms=5)
        ax.set_title(wiki, loc="left", fontsize=11)
        ax.set_ylim(0, 1)
        ax.set_xlim(x.min(), x.max())
    axes.flat[-1].axis("off")
    h, lab = axes.flat[0].get_legend_handles_labels()
    axes.flat[-1].legend(h, lab, loc="center", fontsize=10, frameon=False)
    fig.suptitle("P10 · Search-engine mix of each edition's readers (StatCounter, weighted by "
                 "where readers are, P03). Ticks: months with a Google core update",
                 x=0.01, ha="left", fontsize=12)  # fmt: skip
    fig.tight_layout()
    FIG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG, dpi=150)


def main() -> None:
    cs = pd.read_parquet(config.PARQUET_DIR / "search_share.parquet")
    ls = pd.read_csv(config.REFERENCE_DIR / "search_share_lang.csv")
    rm = pd.read_csv(config.REFERENCE_DIR / "ranking_updates_monthly.csv")
    t = tables(cs, ls)
    QA.mkdir(parents=True, exist_ok=True)
    for name, df in t.items():
        df.to_csv(QA / f"{name}.csv")
    figure(ls, rm)
    print(t["p10_non_google_lang"].to_string())


if __name__ == "__main__":
    main()
