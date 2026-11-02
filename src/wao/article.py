"""P30: every number quoted in report/index.qmd, read from the pipeline outputs in report/qa.

The article never types a result by hand: it shows `N["key"]` values built here, so a rerun of
the pipeline updates the text, and tests/test_article.py checks that every key the article uses
exists. Numbers from other studies (cited in the article) are the only ones typed in index.qmd.
"""

from __future__ import annotations

from functools import cache

import numpy as np
import pandas as pd

from wao import config

QA = config.REPORT_DIR / "qa"
MINUS = "−"
CS = "Callaway-Sant'Anna"


def _csv(name: str) -> pd.DataFrame:
    path = QA / f"{name}.csv"
    if not path.exists() and config.SAMPLE:
        # design tables the sample path doesn't rebuild (P06 sample, P11 truncation, P15 power)
        path = config.REPO_ROOT / "report" / "qa" / f"{name}.csv"
    return pd.read_csv(path)


def pct(x: float, digits: int = 0, sign: bool = True) -> str:
    """-7.96 -> '−8%', 2.65 -> '+3%'; sign=False drops the sign (for 'fell 8%')."""
    if x is None or x != x:
        return "n/a"
    v = round(x if sign else abs(x), digits) + 0.0  # + 0.0 turns -0.0 into 0.0
    s = f"{v:.{digits}f}%"
    if sign and v > 0:
        s = "+" + s
    return s.replace("-", MINUS)


def share(x: float, digits: int = 0) -> str:
    return f"{100 * x:.{digits}f}%"


def interval(lo: float, hi: float, digits: int = 0) -> str:
    return f"{pct(lo, digits)} to {pct(hi, digits)}"


def pval(p: float) -> str:
    return f"{p:.3f}" if p < 0.1 else f"{p:.2f}"


def log_pct(x: float) -> float:
    return 100 * (np.exp(x) - 1)


def _ri(row: pd.Series, lo: str = "lo_pct", hi: str = "hi_pct") -> str:
    return f"{pct(row['pct'])} (95% interval {interval(row[lo], row[hi])}, p = {pval(row.ri_p)})"


@cache
def numbers() -> dict[str, str]:
    N: dict[str, str] = {}

    # H1: staggered DiD (P17)
    att = _csv("p17_att").set_index(["window", "estimator"])
    for w in ("primary", "full"):
        r = att.loc[(w, CS)]
        N[f"att_{w}"] = pct(r.pct)
        N[f"att_{w}_1"] = pct(r.pct, 1)
        N[f"att_{w}_ci"] = interval(log_pct(r.ri_lo95), log_pct(r.ri_hi95))
        N[f"att_{w}_p"] = pval(r.ri_p)
        N[f"sa_{w}"] = pct(att.loc[(w, "Sun-Abraham")].pct)
        N[f"bjs_{w}"] = pct(att.loc[(w, "Borusyak-Jaravel-Spiess")].pct)
    N["pretrend_p"] = pval(_csv("p17_pretrend").set_index("window").loc["primary"].ri_p)
    ed = _csv("p17_by_edition").set_index(["window", "edition"]).pct
    for w in ("primary", "full"):
        N[f"en_{w}"] = pct(ed.loc[(w, "en")])
    N["ja_full"], N["zh_full"] = pct(ed.loc[("full", "ja")]), pct(ed.loc[("full", "zh")])

    # power (P15)
    mde = _csv("p15_mde").query("outcome == 'search'").set_index("window").mde_ri_pct
    N["mde_primary"], N["mde_full"] = pct(mde["primary"], sign=False), pct(mde["full"], sign=False)

    # robustness (P20)
    rob = _csv("p20_robustness")
    rb = rob.set_index(["spec", "window"])
    N["placebo_primary"] = pct(rb.loc[("placebo: 12 months earlier", "primary")].pct, 1)
    N["placebo_primary_p"] = pval(rb.loc[("placebo: 12 months earlier", "primary")].ri_p)
    N["no_fr_full"] = pct(rb.loc[("leave out fr", "full")].pct, 1)
    N["no_fr_primary"] = pct(rb.loc[("leave out fr", "primary")].pct, 1)
    bot = rb.loc[("edition x post-2025-04 bot step", "full")]
    N["bot_step_full"] = pct(bot.pct, 1)
    N["bot_step_full_ci"] = interval(bot.lo_pct, bot.hi_pct)
    N["ru_vs_fr"] = pct(rb.loc[("negative control: ru alone vs fr", "full")].pct)
    core = "core-update months dropped (post)"
    N["core_primary"], N["core_full"] = (pct(rb.loc[(core, w)].pct, 1) for w in ("primary", "full"))
    main = rob[~rob.group.isin(["placebo", "negative control"]) & rob.ri_p.notna()]
    N["n_variants"] = str(len(main))
    N["n_sig_loss"] = str(int(((main.ri_p < 0.05) & (main.pct < 0)).sum()))
    N["rob_min"], N["rob_max"] = pct(main.pct.min()), pct(main.pct.max())

    # dose-response (P18) and within-concept (P19)
    tw = _csv("p18_twfe").set_index("spec")
    r = tw.loc["11 editions (pre-registered)"]
    N["dose_prereg"], N["dose_prereg_p"] = pct(r.pct_full), pval(r.wcb_p)
    r = tw.loc["9 editions (P17 set)"]
    N["dose_9"], N["dose_9_ci"] = pct(r.pct_full), interval(r.pct_lo, r.pct_hi)
    N["dose_9_ri_p"] = pval(r.ri_p)
    c = _csv("p19_estimates").query("outcome == 'search' and weights == 'weighted'")
    c = c.set_index("editions")
    r = c.loc["11 editions (pre-registered)"]
    N["concept_prereg"], N["concept_prereg_ci"] = pct(r.pct), interval(r.pct_lo, r.pct_hi)
    r = c.loc["10 editions, no fa"]
    N["concept_nofa"], N["concept_nofa_ci"] = pct(r.pct), interval(r.pct_lo, r.pct_hi)
    N["concept_nofa_wcb_p"], N["concept_nofa_ri_p"] = pval(r.wcb_p), pval(r.ri_p)

    # English ITS (P16)
    g = _csv("p16_its_gaps").query("outcome == 'search' and period == 'all post'")
    g = g.set_index("spec")
    N["its_prereg"] = pct(g.loc["A"].gap_pct)
    N["its_single"] = pct(g.loc["B"].gap_pct)
    N["its_single_ci"] = interval(g.loc["B"].lo_pct, g.loc["B"].hi_pct)
    h = _csv("p16_its_holdout").query("outcome == 'search'").mape_pct
    N["its_holdout"] = f"{h.min():.0f}–{h.max():.0f}%"

    # H2 quick answer (P21)
    h2 = _csv("p21_h2").set_index("spec")
    r = h2.iloc[0]
    N["h2"], N["h2_ci"], N["h2_p"] = pct(r.pct, 1), interval(r.pct_lo, r.pct_hi, 1), pval(r.wcb_p)
    r = h2.loc["binary v4: quick vs long x exposure, views"]
    N["h2_binary"], N["h2_binary_ci"] = pct(r.pct, 1), interval(r.pct_lo, r.pct_hi)
    sl = _csv("p21_slope").set_index(["grp", "label"]).change_pct
    N["quick_exposed"], N["long_exposed"] = (pct(sl.loc[("high exposure (8)", k)])
                                             for k in ("quick", "long"))  # fmt: skip
    N["quick_ctrl"], N["long_ctrl"] = (pct(sl.loc[("fr + ru", k)]) for k in ("quick", "long"))
    ty = _csv("p21_by_type").set_index("coarse_type")
    N["sports_events"] = pct(log_pct(ty.loc["sports_event"].eb), sign=False)
    N["n_types"] = str(len(ty))

    # H3 mobile vs desktop, H4 head vs tail (P22)
    h3 = _csv("p22_h3").query("group == 'H3'").set_index("window")
    N["h3_primary"] = _ri(h3.loc["primary"])
    N["h3_full"] = _ri(h3.loc["full"])
    h4 = _csv("p22_h4").set_index("status")
    r = h4.loc["pre-registered"]
    N["h4"], N["h4_ci"], N["h4_p"] = pct(r.pct), interval(r.pct_lo, r.pct_hi), pval(r.wcb_p)
    r = h4.loc["secondary"]
    N["h4_corr"], N["h4_corr_p"] = pct(r.pct), pval(r.wcb_p)
    N["h4_abs"] = pct(h4.loc["pre-registered"].pct, sign=False)

    # H5 referral mix and depth (P23)
    h5 = _csv("p23_h5").set_index(["group", "window"])
    N["h5a"], N["h5b"] = _ri(h5.loc[("share", "primary")]), _ri(h5.loc[("depth", "primary")])
    N["h5a_full"] = _ri(h5.loc[("share", "full")])
    mix = _csv("p23_mix")
    for grp, key in (("treated (8)", "tr"), ("fr", "fr")):
        m = mix[mix.grp == grp]
        b, latest = m[(m.month >= "2023-05") & (m.month <= "2024-04")], m.tail(12)
        for col, name in (("search_arr", "search"), ("link_arr", "links")):
            N[f"mix_{key}_{name}_before"] = share(b[col].sum() / b.total_arr.sum())
            N[f"mix_{key}_{name}_latest"] = share(latest[col].sum() / latest.total_arr.sum())

    # H6 editors (P24) and Holm
    r = _csv("p24_h6").iloc[0]
    N["h6"] = _ri(r)
    holm = _csv("holm")
    N["holm_min_p"], N["holm_supported"] = pval(holm.p.min()), str(int(holm.supported.sum()))

    # P25 decomposition and external referrals
    s = _csv("p25_aio_share").set_index(["estimate", "unit"])
    N["total_en"] = pct(s.loc[("P17 full window", "en")].total_pct)
    N["total_pooled"] = pct(s.loc[("P17 full window", "8 treated pooled")].total_pct)
    N["total_en_abs"] = pct(s.loc[("P17 full window", "en")].total_pct, sign=False)
    N["total_pooled_abs"] = pct(
        s.loc[("P17 full window", "8 treated pooled")].total_pct, sign=False
    )
    N["aio_share"] = share(s.loc[("P17 full window", "8 treated pooled")].share_of_decline)
    r = s.loc[("P17 full window, RI 95% bounds", "8 treated pooled")]
    N["aio_share_range"] = f"{share(r.share_lo).replace('-', MINUS)} to {share(r.share_hi)}"
    ext = _csv("p25_external")
    before = ext[(ext.month >= "2021-12") & (ext.month <= "2022-11")].external_share.mean()
    N["ext_before"] = share(before, 1)
    N["ext_latest"] = share(ext.tail(12).external_share.mean(), 1)

    # descriptive levels behind charts 3, 4, 6 (P27)
    v = _csv("p27_numbers").set_index("key").value
    N["en_search_before"], N["en_search_latest"] = (
        share(v.en_search_before),
        share(v.en_search_latest),
    )
    N["en_links_before"], N["en_links_latest"] = share(v.en_links_before), share(v.en_links_latest)
    for lang in ("en", "es", "pt", "ru", "fr", "ja", "de", "zh"):
        N[f"idx_{lang}"] = f"{v[f'idx_latest_{lang}']:.0f}"
    for lang in ("es", "pt", "ru"):
        N[f"views_chg_{lang}"] = pct(v[f"views_chg_{lang}"])
        N[f"sshare_before_{lang}"] = share(v[f"search_share_before_{lang}"])
        N[f"sshare_latest_{lang}"] = share(v[f"search_share_latest_{lang}"])
    N["editors_above"] = f"{v.editors_above_views:.0f}"
    tr_idx = [v[f"idx_latest_{x}"] for x in ("en", "ja", "pt", "es", "de", "it", "pl", "zh")]
    N["idx_tr_min"], N["idx_tr_max"] = f"{min(tr_idx):.0f}", f"{max(tr_idx):.0f}"

    # design sizes (P06, P11, P17)
    lang = _csv("p06_sample_by_lang")
    N["n_sample"], N["n_concepts"] = f"{lang['sample'].sum():,}", f"{lang.concept_panel.max():,}"
    tr = _csv("p11_truncation_lang_month")
    tr = tr[tr.lang.isin(lang.lang) & (tr.month >= "2019-04")].groupby("lang").hidden_share.mean()
    N["trunc_range"] = f"{100 * tr.min():.1f}–{100 * tr.max():.1f}%"
    N["n_assign"] = f"{int(rb.loc[('baseline (P17)', 'full')].assignments):,}"

    # exposure and cohorts (P03)
    co = pd.read_csv(config.REPO_ROOT / "data" / "reference" / "language_cohorts.csv")
    co = co.set_index("wiki")
    N["fr_cohort"] = co.loc["fr"].cohort
    N["ru_max"] = f"{co.loc['ru'].max_exposure:.2f}"
    return N
