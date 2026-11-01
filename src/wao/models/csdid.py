"""Callaway–Sant'Anna ATT as a linear functional of the outcome matrix (pre-registered in P15).

Unconditional (no covariates), universal base period b_g (the month before the group's first
exposure; g-1 when exposure starts at the cohort month), not-yet-exposed controls:
    ATT(g,t) = mean_{i in g}(y_it - y_i,b) - mean_{j: E_j > t}(y_jt - y_j,b),   t >= g
Overall ATT = cohort aggregation (CS 2021, theta^O_sel): theta_g = mean over valid t of
ATT(g,t) with event time e = t - g in [e_min, e_max], then theta = sum_g n_g theta_g / sum_g n_g.
Cells whose month is missing (2025-04 in the primary version) are skipped.

Because the estimate is sum(W * Y) for a weight matrix W that depends only on the cohort
assignment, randomization inference over cohort permutations is a matrix product.
"""

from __future__ import annotations

from itertools import permutations

import numpy as np

NEVER = np.inf


def att_weights(G: np.ndarray, T: int, missing: np.ndarray | None = None, e_min: int = 0,
                e_max: int | None = None, E: np.ndarray | None = None,
                control: str = "exposure") -> np.ndarray:  # fmt: skip
    """W (n x T) with overall ATT = (W * Y).sum().

    G: cohort per unit as a column index (first treated period), NEVER if not treated within the
    window. E: first period with any exposure (default G); a group is the units sharing (G, E), and
    its base is the last non-missing period before E, so partly exposed months between E and G are
    neither base nor post. Controls at t: units with E > t ("exposure", not yet exposed at all) or
    with G > t ("treatment", not yet treated). Columns are consecutive months.
    """
    n = len(G)
    E = G if E is None else E
    miss = np.zeros(T, bool) if missing is None else missing
    W = np.zeros((n, T))
    groups = sorted({(g, e) for g, e in zip(G, E, strict=True) if g < T})  # treated in window
    n_tot = (G < T).sum()
    for g, e in groups:
        g, b = int(g), int(e) - 1
        while b >= 0 and miss[b]:
            b -= 1
        if b < 0:
            continue
        tr = (G == g) & (E == e)
        cells = []
        for t in range(g + e_min, T if e_max is None else min(T, g + e_max + 1)):
            if t < 0 or miss[t]:
                continue
            c = (E > t) if control == "exposure" else (G > t)
            c &= ~tr
            if c.any():
                cells.append((t, c))
        if not cells:
            continue
        wg = tr.sum() / n_tot / len(cells)
        for t, c in cells:
            W[tr, t] += wg / tr.sum()
            W[tr, b] -= wg / tr.sum()
            W[c, t] -= wg / c.sum()
            W[c, b] += wg / c.sum()
    return W


def att(Y: np.ndarray, G: np.ndarray, **kw) -> float:
    W = att_weights(G, Y.shape[1], **kw)
    return float(np.nansum(W * Y))


def assignments(G: np.ndarray, E: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Every distinct permutation of the (cohort, first exposure) labels across units, for
    randomization inference. Returns (G_perms, E_perms), one row per assignment."""
    E = G if E is None else E
    pairs = sorted(set(permutations(list(zip(G.tolist(), E.tolist(), strict=True)))))
    a = np.array(pairs)
    return a[:, :, 0], a[:, :, 1]


def ri_pvalue(stat: float, null: np.ndarray) -> float:
    """Two-sided exact RI p-value: share of assignments with |ATT| >= |observed|."""
    return float((np.abs(null) >= abs(stat) - 1e-12).mean())
