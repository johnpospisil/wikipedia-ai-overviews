"""P08 QA and figure: feature distributions by edition, missing rates and fetch statuses.

QA tables (report/qa/):
  p08_feature_summary.csv  lang: articles, medians and quartiles of the numeric features,
                           infobox and confident-topic shares, missing rate of each feature
  p08_status.csv           lang x status: articles (ok, no_rev_2023, text_hidden, badrevid)
  p08_topics.csv           lang x topic_group: share of articles (top topic)
Figure: report/figures/p08_article_features.png. Sample-unweighted, pre-period only.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from wao import config
from wao.build.features import out_path as features_path

NUM = ["bytes", "prose_chars", "lead_chars", "n_sections", "n_refs", "n_templates",
       "age_years", "n_rev_2023"]  # fmt: skip
QA = config.REPORT_DIR / "qa"
FIG = config.REPORT_DIR / "figures" / "p08_article_features.png"


def tables(f: pd.DataFrame) -> dict[str, pd.DataFrame]:
    g = f.groupby("lang")
    summ = g.size().rename("articles").to_frame()
    for c in NUM:
        q = g[c].quantile([0.25, 0.5, 0.75]).unstack()
        summ[[f"{c}_p25", f"{c}_med", f"{c}_p75"]] = q.values
    summ["infobox_share"] = g.has_infobox.mean()
    summ["topic_confident_share"] = g.topic_confident.mean()
    summ["redirect_2023_share"] = g.is_redirect.mean()
    for c in [*NUM, "has_infobox", "topic"]:
        summ[f"miss_{c}"] = g[c].apply(lambda x: x.isna().mean())
    status = f.groupby(["lang", "status"]).size().unstack(fill_value=0)
    topics = (f.groupby("lang").topic_group.value_counts(normalize=True, dropna=False)
              .unstack(fill_value=0))  # fmt: skip
    return {"p08_feature_summary": summ.round(4), "p08_status": status,
            "p08_topics": topics.round(4)}  # fmt: skip


def figure(f: pd.DataFrame, t: dict[str, pd.DataFrame]) -> None:
    langs = sorted(f.lang.unique())
    fig, ax = plt.subplots(2, 3, figsize=(15, 8.5))
    panels = [("bytes", "Wikitext size (bytes, log)", True), ("n_refs", "References", False),
              ("age_years", "Article age at 2023-12-31 (years)", False)]  # fmt: skip
    for a, (c, title, log) in zip(ax[0], panels, strict=True):
        data = [f.loc[f.lang == lg, c].dropna() for lg in langs]
        if log:
            data = [np.log10(d.clip(lower=1)) for d in data]
        a.boxplot(data, tick_labels=langs, showfliers=False, whis=(10, 90))
        a.set_title(title, loc="left", fontsize=11)
        if c == "n_refs":
            a.set_ylim(0, None)
        if log:
            a.set_yticks([2, 3, 4, 5], ["100", "1k", "10k", "100k"])
    s = t["p08_feature_summary"]
    ax[1, 0].bar(langs, s.loc[langs, "infobox_share"], color="#4c72b0")
    ax[1, 0].set_title("Has an infobox (2023 revision)", loc="left", fontsize=11)
    ax[1, 0].set_ylim(0, 1)
    tp = t["p08_topics"].loc[langs]
    bottom = np.zeros(len(langs))
    colors = ["#4c72b0", "#dd8452", "#55a868", "#c44e52", "#8172b3"]
    for col, color in zip(tp.columns, colors, strict=False):
        ax[1, 1].bar(langs, tp[col], bottom=bottom, color=color, label=str(col).replace("_", " "))
        bottom += tp[col].values
    ax[1, 1].set_title("Top article topic (Lift Wing)", loc="left", fontsize=11)
    ax[1, 1].legend(fontsize=8, loc="lower right", framealpha=0.9)
    miss = s.loc[langs, [f"miss_{c}" for c in ["prose_chars", "age_years", "topic"]]] * 100
    miss.columns = ["text features", "creation date", "topic"]
    miss.plot.bar(ax=ax[1, 2], rot=0, color=["#4c72b0", "#dd8452", "#55a868"])
    ax[1, 2].set_title("Missing (% of sample articles)", loc="left", fontsize=11)
    ax[1, 2].legend(fontsize=8)
    for a in ax.flat:
        a.spines[["top", "right"]].set_visible(False)
    fig.suptitle("P08 · Article features of the 197k sample articles, by edition (unweighted)",
                 x=0.01, ha="left", fontsize=13)  # fmt: skip
    fig.tight_layout()
    FIG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG, dpi=150)


def main() -> None:
    f = pd.read_parquet(features_path())
    t = tables(f)
    QA.mkdir(parents=True, exist_ok=True)
    for name, df in t.items():
        df.to_csv(QA / f"{name}.csv")
    figure(f, t)
    cols = [
        "articles",
        "bytes_med",
        "prose_chars_med",
        "n_refs_med",
        "age_years_med",
        "infobox_share",
        "miss_prose_chars",
    ]
    print(t["p08_feature_summary"][cols])
    print(t["p08_status"])


if __name__ == "__main__":
    main()
