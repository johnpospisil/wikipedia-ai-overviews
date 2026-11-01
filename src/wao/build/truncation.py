"""P11: how much search traffic the clickstream's <10 rule hides, and how much decline the rule
alone would manufacture.

Clickstream drops an (other-search, article) pair with fewer than 10 arrivals in the month, so
an article's search arrivals are either observed (>= 10) or censored (0-9). For a censored
article-month with web views v, the hidden arrivals are estimated as E[X | X <= 9] with
X ~ Binomial(v, p), p = the search-arrival rate (search arrivals / web views) of the uncensored
articles in the same edition, 2023 popularity decile and month. Uncensored articles are the
ones with more search traffic, so p (and the estimate) leans high; the bounds are 0 and
min(9, v) per censored article-month.

Simulation (pre-period 2023 only, no treated-vs-control contrast): take "true" 2023 search
arrivals (observed, or a draw from the truncated binomial where censored), thin them by a
uniform decline d (each arrival kept with probability 1 - d), re-apply the <10 rule, and compare
the decline a naive sum of published pairs would show with d. Sums use the P06 sample weights.

Outputs (report/qa/):
  p11_truncation_lang_month.csv    lang x month: observed, estimated hidden, upper bound,
                                   hidden share (point and upper)
  p11_truncation_decile_year.csv   lang x decile x year: the same
  p11_truncation_simulation.csv    lang x decile x d: naive measured decline and its bias
Run: python -m wao.build.truncation
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from wao import config
from wao.build.qa_article_month import out_path as am_path

THRESHOLD = 10
DECLINES = (0.05, 0.10, 0.20, 0.30, 0.50)
QA = config.REPORT_DIR / "qa"


def truncated_mean(n: np.ndarray, p: np.ndarray, cap: int = THRESHOLD - 1) -> np.ndarray:
    """E[X | X <= cap] for X ~ Binomial(n, p), elementwise; cap where X <= cap is ~impossible."""
    k = np.arange(cap + 1)[:, None]
    pmf = stats.binom.pmf(k, n[None, :], p[None, :])
    mass = pmf.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        m = (k * pmf).sum(axis=0) / mass
    return np.where(mass > 1e-12, m, np.minimum(cap, n))


def truncated_draw(n: np.ndarray, p: np.ndarray, rng, cap: int = THRESHOLD - 1) -> np.ndarray:
    """One draw of X | X <= cap per element (inverse CDF on the truncated pmf)."""
    k = np.arange(cap + 1)[:, None]
    pmf = stats.binom.pmf(k, n[None, :], p[None, :])
    mass = pmf.sum(axis=0)
    cdf = np.cumsum(pmf, axis=0) / np.where(mass > 0, mass, 1)
    u = rng.random(len(n))
    draw = (cdf < u[None, :]).sum(axis=0)
    return np.where(mass > 1e-12, np.minimum(draw, cap), np.minimum(cap, n))


def rates(am: pd.DataFrame) -> pd.Series:
    u = am[am.arr_search.notna()]
    g = u.groupby(["lang", "decile", "month"])
    return (g.arr_search.sum() / g.views_web.sum()).clip(upper=1).rename("p")


def impute(am: pd.DataFrame) -> pd.DataFrame:
    am = am.join(rates(am), on=["lang", "decile", "month"])
    # cells with no uncensored article: borrow the edition-month rate of the lowest decile seen
    fallback = am.groupby(["lang", "month"]).p.transform("min")
    am["p"] = am.p.fillna(fallback).fillna(0)
    cens = am.arr_search.isna()
    n = am.views_web.to_numpy(dtype=np.int64)
    am["obs"] = am.arr_search.fillna(0)
    am["hidden"] = 0.0
    am.loc[cens, "hidden"] = truncated_mean(n[cens.to_numpy()], am.p.to_numpy()[cens.to_numpy()])
    am["upper"] = np.where(cens, np.minimum(THRESHOLD - 1, n), 0)
    return am


def summarise(am: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    w = am.weight
    g = am.assign(obs_w=am.obs * w, hid_w=am.hidden * w, up_w=am.upper * w,
                  cens=am.arr_search.isna()).groupby(keys)  # fmt: skip
    out = pd.DataFrame({"observed": g.obs_w.sum(), "hidden": g.hid_w.sum(), "upper": g.up_w.sum(),
                        "censored_rows": g.cens.mean()})  # fmt: skip
    out["hidden_share"] = out.hidden / (out.observed + out.hidden)
    out["hidden_share_upper"] = out.upper / (out.observed + out.upper)
    return out


def simulate(am: pd.DataFrame, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    a = am[am.month.str.startswith("2023")].copy()
    cens = a.arr_search.isna().to_numpy()
    true = a.arr_search.fillna(0).to_numpy(dtype=np.int64)
    n = a.views_web.to_numpy(dtype=np.int64)
    true[cens] = truncated_draw(n[cens], a.p.to_numpy()[cens], rng)
    base = np.where(true >= THRESHOLD, true, 0)
    rows = []
    for d in DECLINES:
        kept = rng.binomial(true, 1 - d)
        shown = np.where(kept >= THRESHOLD, kept, 0)
        t = a.assign(base=base * a.weight, shown=shown * a.weight,
                     true_after=kept * a.weight, true_before=true * a.weight)  # fmt: skip
        for keys in (["lang", "decile"], ["lang"]):
            g = t.groupby(keys)[["base", "shown", "true_before", "true_after"]].sum()
            g["d"] = d
            g["true_decline"] = 1 - g.true_after / g.true_before
            g["naive_decline"] = 1 - g.shown / g.base
            g["bias_pp"] = 100 * (g.naive_decline - g.true_decline)
            if keys == ["lang"]:
                g["decile"] = 0  # 0 = all deciles
                g = g.set_index("decile", append=True)
            rows.append(g.reset_index())
    out = pd.concat(rows, ignore_index=True)
    return out[["lang", "decile", "d", "true_decline", "naive_decline", "bias_pp"]]


def main() -> None:
    am = impute(pd.read_parquet(am_path()))
    QA.mkdir(parents=True, exist_ok=True)
    lm = summarise(am, ["lang", "month"])
    lm.round(4).to_csv(QA / "p11_truncation_lang_month.csv")
    dy = summarise(am.assign(year=am.month.str[:4]), ["lang", "decile", "year"])
    dy.round(4).to_csv(QA / "p11_truncation_decile_year.csv")
    sim = simulate(am)
    sim.round(4).to_csv(QA / "p11_truncation_simulation.csv", index=False)
    am[["lang", "page_id", "month", "obs", "hidden", "upper"]].to_parquet(
        config.PARQUET_DIR / "qa" / "search_imputed.parquet", index=False
    )
    y23 = dy.xs("2023", level="year")[["hidden_share", "hidden_share_upper"]]
    print((100 * y23.unstack("lang").hidden_share).round(1).to_string())
    print(sim[sim.decile == 0].pivot(index="lang", columns="d", values="bias_pp").round(1))


if __name__ == "__main__":
    main()
