"""P12 figure: Natural Questions quick-answer rate by Wikidata coarse type, coloured by v4 tier.

Reads data/reference/nq_type_rates.csv (wao.build.quick_answer_nq) and writes
report/figures/p12_quick_answer_types.png.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd

from wao import config

FIG = config.REPORT_DIR / "figures" / "p12_quick_answer_types.png"
COLORS = {"quick": "#4c72b0", "ambiguous": "#999999", "long": "#dd8452"}


def main() -> None:
    t = pd.read_csv(config.REFERENCE_DIR / "nq_type_rates.csv").sort_values("rate")
    overall = (t.rate * t.queries).sum() / t.queries.sum()
    fig, ax = plt.subplots(figsize=(8, 7))
    y = range(len(t))
    ax.hlines(y, t.lo, t.hi, color=[COLORS[v] for v in t.v4], lw=2)
    ax.scatter(t.rate, y, color=[COLORS[v] for v in t.v4], zorder=3, s=28)
    ax.axvline(overall, color="0.4", lw=0.8, ls="--")
    ax.set_yticks(list(y), [f"{c}  ({q:,})" for c, q in zip(t.coarse_type, t.queries,
                                                             strict=True)])  # fmt: skip
    ax.set_xlabel("share of answered Google queries with a short (one-fact) answer")
    for tier, c in COLORS.items():
        ax.scatter([], [], color=c, label=f"v4 {tier}")
    ax.legend(loc="lower right", fontsize=9, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title("P12 · Quick-answer rate by Wikidata type\n(Natural Questions, 152k answered "
                 "queries; 95% CI; dashed = overall)", loc="left", fontsize=10)  # fmt: skip
    fig.tight_layout()
    FIG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG, dpi=150)


if __name__ == "__main__":
    main()
