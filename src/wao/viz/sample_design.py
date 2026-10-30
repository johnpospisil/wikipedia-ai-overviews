"""P06 figure: who is in the article sample.

Left: sample size by edition, split into the language sample, the concept panel and both.
Right: each Wikidata coarse type's share of the sample (unweighted) against its estimated share
of the frame (sampling-weighted), pooled over editions; small types sit above the diagonal
because they were oversampled. Design description only, no outcomes.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from wao import config


def figure(s: pd.DataFrame) -> plt.Figure:
    fig, (a, b) = plt.subplots(1, 2, figsize=(13, 5.5), gridspec_kw={"width_ratios": [1, 1.1]})
    langs = list(config.LANGS)
    part = (
        pd.DataFrame(
            {
                "Language sample only": s[s.in_lang_sample & ~s.in_concept_panel]
                .groupby("lang")
                .size(),
                "Both": s[s.in_lang_sample & s.in_concept_panel].groupby("lang").size(),
                "Concept panel only": s[~s.in_lang_sample & s.in_concept_panel]
                .groupby("lang")
                .size(),
            }
        )
        .reindex(langs)
        .fillna(0)
    )
    left = np.zeros(len(langs))
    for (name, col), colour in zip(part.items(), ["#1f4e8c", "#6c8ebf", "#e6b85c"], strict=True):
        a.barh(langs, col / 1e3, left=left, color=colour, label=name)
        left += col.to_numpy() / 1e3
    a.invert_yaxis()
    a.set_xlabel("Articles in sample (thousands)")
    a.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3, fontsize=9)
    a.set_title(
        f"{len(s):,} articles; {s[s.in_concept_panel].qid.nunique():,} concepts in all 11",
        loc="left",
        fontsize=11,
    )

    t = pd.DataFrame(
        {
            "sample": s.coarse_type.value_counts(normalize=True),
            "frame": s.groupby("coarse_type").weight.sum() / s.weight.sum(),
        }
    ).fillna(0)
    b.scatter(t.frame, t["sample"], s=25, color="#1f4e8c", zorder=3)
    for name, r in t.iterrows():
        b.annotate(
            name, (r.frame, r["sample"]), fontsize=8, xytext=(4, 2), textcoords="offset points"
        )
    lim = (1e-4, 0.6)
    b.plot(lim, lim, color="#999", lw=0.8, ls="--")
    b.set(xscale="log", yscale="log", xlim=lim, ylim=lim)
    b.set_xlabel("Estimated share of frame (weighted)")
    b.set_ylabel("Share of sample (unweighted)")
    b.set_title("Small types are oversampled; weights undo it", loc="left", fontsize=11)
    fig.suptitle(
        "P06 article sample: stratified by edition × 2023 popularity decile × Wikidata type",
        x=0.01,
        ha="left",
        fontweight="bold",
    )
    fig.tight_layout()
    return fig


def main() -> None:
    s = pd.read_parquet(config.PANEL_DIR / "sample.parquet")
    out = config.FIGURE_DIR / "p06_sample_design.png"
    figure(s).savefig(out, dpi=160)
    print(out)


if __name__ == "__main__":
    main()
