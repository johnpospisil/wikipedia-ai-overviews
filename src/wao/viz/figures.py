"""P27: the remaining figures (plan section 6, charts 2-6) plus the robustness forest plot, each in
light and dark (PNG + SVG), in the P26 theme. Every title is the one-sentence takeaway the chart
supports; numbers in titles are computed here from the model outputs, never typed in.

  chart2_quick_long     slope chart: user web views of quick-answer vs long-read articles, the year
                        before launch (2023-08..2024-07) vs the latest 12 months, the 8 treated
                        editions vs fr + ru (P21 descriptive)
  chart3_referral_mix   stacked shares of English arrivals by referrer, 2019-04 onwards (clickstream
                        method break, P11)
  chart4_editions       small multiples: deseasonalised search arrivals per edition with fr as a
                        reference line, the months with exposure >= 0.5 shaded
  chart5_types          dot plot: effect of full exposure on views by Wikidata type, relative to
                        `human`, partially pooled (P21 EB), 95% posterior interval
  chart6_editors        active registered editors vs user views per edition (descriptive, P24)
  forest_robustness     every P20 variant in both windows against the +/-5% band

Outputs: report/figures/<name>[_dark].{png,svg}; report/qa/p27_takeaways.csv
Usage: python -m wao.viz.figures
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import duckdb  # noqa: E402
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from wao import config  # noqa: E402
from wao.viz import eda, theme  # noqa: E402

QA = config.REPORT_DIR / "qa"
SOURCE = "Data: Wikimedia clickstream, pageviews and editor statistics (CC0)."
TREATED = ["en", "ja", "pt", "es", "de", "it", "pl", "zh"]
NAMES = {"en": "English", "ja": "Japanese", "pt": "Portuguese", "es": "Spanish", "de": "German",
         "it": "Italian", "pl": "Polish", "zh": "Chinese", "fr": "French", "ru": "Russian",
         "fa": "Persian"}  # fmt: skip
TYPES = {"admin_region": "administrative regions", "astronomical": "astronomical objects",
         "chemical": "chemicals", "country": "countries", "event": "events", "film": "films",
         "health": "health", "list": "lists", "music": "music", "nature_place": "natural places",
         "no_p31": "no Wikidata type", "no_qid": "no Wikidata item", "organization":
         "organisations", "other": "other", "settlement": "cities and towns", "sports_event":
         "sports events", "structure": "buildings and structures", "taxon": "species (taxa)",
         "tv": "TV", "video_game": "video games", "written_work": "books and written works"}  # fmt: skip  # noqa: E501
pct = lambda v: 100 * (np.exp(v) - 1)  # noqa: E731
TAKEAWAYS: dict[str, str] = {}


def _panel() -> pd.DataFrame:
    d = (
        duckdb.connect()
        .execute(f"""
        select lang, month, cohort, exposure, search_arr_na, search_arr, total_arr, link_arr,
               empty_arr, internal_other_arr, external_arr, active_user,
               views_desktop + views_mobile_web + views_app as views
        from '{config.PANEL_DIR}/panel_lang_month.parquet'
        where core and month >= '2019-04' and month <= '2026-09' order by lang, month""")
        .df()
    )
    d["t"] = pd.PeriodIndex(d.month, freq="M").to_timestamp()
    return d


def _year_axis(ax, step: int = 1) -> None:
    ax.xaxis.set_major_locator(mdates.YearLocator(step))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y" if step == 1 else "'%y"))


# ----------------------------------------------------------------------------- chart 2: slope


def chart2(mode: str) -> None:
    s = pd.read_csv(QA / "p21_slope.csv")
    groups = [("high exposure (8)", "8 editions with AI Overviews", "treated"),
              ("fr + ru", "French + Russian (little or no AI Overviews)", "control")]  # fmt: skip
    q = s.set_index(["grp", "label"]).change_pct
    title = (
        "Quick-answer pages lost more views than long reads, even where AI Overviews hardly reached"
    )
    sub = (
        f"User web views, latest 12 months vs Aug 2023-Jul 2024. With AI Overviews: quick "
        f"{q['high exposure (8)', 'quick']:+.0f}%, long {q['high exposure (8)', 'long']:+.0f}%;"
        f" without: quick {q['fr + ru', 'quick']:+.0f}%, long {q['fr + ru', 'long']:+.0f}%"
    )
    TAKEAWAYS["chart2_quick_long"] = title
    with theme.use(mode) as p:
        fig, axes = plt.subplots(1, 2, figsize=(10, 5.6), sharey=True)
        fig.subplots_adjust(left=0.08, right=0.86, top=0.78, bottom=0.14, wspace=0.55)
        for ax, (g, name, role) in zip(axes, groups, strict=True):
            c = getattr(p, role)
            for lab, ls, txt in (
                ("quick", "-", "quick-answer"),
                ("long", (0, (4, 2)), "long-read"),
            ):
                v = 100 + q[g, lab]
                ax.plot([0, 1], [100, v], color=c, lw=2.4, ls=ls, marker="o", ms=8,
                        mec=p.surface, mew=2)  # fmt: skip
                theme.label_end(ax, 1, v, f"{txt} {q[g, lab]:+.0f}%", c, dx=8)
            ax.set_xticks([0, 1], ["Aug 2023-\nJul 2024", "latest\n12 months"])
            ax.set_xlim(-0.15, 1.1)
            ax.set_title(name, fontsize=10.5, color=p.ink, loc="left", pad=10)
        axes[0].set_ylabel("User web views, index (year before launch = 100)")
        axes[0].set_ylim(70, 103)
        theme.title(fig, title, sub)
        theme.source(fig, SOURCE + " P06 article sample, weighted; quick vs long = P12 v4 tiers.")
        theme.save(fig, "chart2_quick_long")


# --------------------------------------------------------------------- chart 3: referral mix

MIX = [("search_arr", "Search engines", "control"),
       ("links", "Links from other Wikipedia articles", "third"),
       ("empty_arr", "No referrer (typed, bookmarks, apps)", "band"),
       ("other", "Other websites and other pages", "grid")]  # fmt: skip


def chart3(d: pd.DataFrame, mode: str) -> None:
    e = d[d.lang == "en"].copy().set_index("t")
    e["links"] = e.link_arr
    e["other"] = e.total_arr - e.search_arr - e.link_arr - e.empty_arr
    sh = e[[c for c, _, _ in MIX]].div(e.total_arr, axis=0)
    a, b = sh.loc["2023-05":"2024-04"].mean(), sh.iloc[-12:].mean()
    title = "English Wikipedia: search still brings almost half of all arrivals"
    sub = (
        f"Share of desktop and mobile-web arrivals by referrer. Search "
        f"{100 * a.search_arr:.0f}% in the year before AI Overviews, {100 * b.search_arr:.0f}% "
        f"in the latest 12 months; article links {100 * a.links:.0f}% to {100 * b.links:.0f}%"
    )
    TAKEAWAYS["chart3_referral_mix"] = f"{title} ({sub.split('. ', 1)[1]})"
    with theme.use(mode) as p:
        fig, ax = plt.subplots(figsize=(10, 5.6))
        fig.subplots_adjust(left=0.07, right=0.70, top=0.74, bottom=0.10)
        cols = [getattr(p, r) for _, _, r in MIX]
        ax.stackplot(sh.index, *[100 * sh[c] for c, _, _ in MIX], colors=cols,
                     edgecolor=p.surface, lw=1.2)  # fmt: skip
        mid = 100 * (sh.iloc[-1].cumsum() - sh.iloc[-1] / 2)
        for (_, lab, r), y in zip(MIX, mid, strict=True):
            theme.label_end(ax, sh.index[-1], y, lab, getattr(p, r))
        for x, txt in ((pd.Timestamp("2022-11-30"), "ChatGPT"),
                       (pd.Timestamp("2024-05-14"), "AI Overviews (US)"),
                       (pd.Timestamp("2025-04-01"), "bot reclassification"))[:3]:  # fmt: skip
            theme.event(ax, x, txt, y=1.06 if txt != "AI Overviews (US)" else 1.11)
        ax.set_ylim(0, 100)
        ax.set_xlim(sh.index[0], sh.index[-1])
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0f}%"))
        ax.grid(False)
        _year_axis(ax)
        theme.title(fig, title, sub)
        theme.source(fig, SOURCE + " English clickstream from 2019-04 (method change).")
        theme.save(fig, "chart3_referral_mix")


# ------------------------------------------------------------------ chart 4: small multiples


def _adjusted(d: pd.DataFrame) -> pd.DataFrame:
    """Deseasonalised search arrivals (P14 month-of-year effects), 3-month mean, index
    2023-08..2024-07 = 100."""
    p = d[(d.month >= eda.PRE_START) & (d.month <= eda.PRE_END)]
    out = []
    for lang, g in d.groupby("lang"):
        r = eda._fit(np.log(p[p.lang == lang].search_arr_na), eda._design(p[p.lang == lang]))
        s = np.array([r.params.get(f"m{m}", 0.0) for m in range(1, 13)])
        y = (
            (g.search_arr_na / np.exp(s[g.t.dt.month.values - 1]))
            .rolling(3, center=True, min_periods=2)
            .mean()
        )
        base = y[(g.month >= "2023-08") & (g.month <= "2024-07")].mean()
        out.append(g.assign(idx=100 * y / base))
    return pd.concat(out)


def chart4(a: pd.DataFrame, mode: str) -> None:
    last = a[a.month > "2025-09"].groupby("lang").idx.mean()
    tr = last[TREATED]
    title = "Search traffic fell almost everywhere, including where AI Overviews never launched"
    sub = (
        f"Seasonally adjusted search arrivals, Aug 2023-Jul 2024 = 100. Latest 12 months: "
        f"treated editions {tr.min():.0f} to {tr.max():.0f}, French {last['fr']:.0f}, "
        f"Russian {last['ru']:.0f}"
    )
    TAKEAWAYS["chart4_editions"] = f"{title} ({sub.split('. ', 1)[1]})"
    fr = a[a.lang == "fr"].set_index("t").idx
    with theme.use(mode) as p:
        fig, axes = plt.subplots(3, 4, figsize=(12, 8.4), sharex=True, sharey=True)
        fig.subplots_adjust(left=0.06, right=0.98, top=0.86, bottom=0.09, hspace=0.32, wspace=0.1)
        for ax, lang in zip(axes.flat, eda.ORDER + [None], strict=True):
            if lang is None:
                ax.axis("off")
                ax.plot([], [], color=p.treated, lw=2, label="edition (treated)")
                ax.plot([], [], color=p.ink_muted, lw=2, label="edition (ru, fa: excluded)")
                ax.plot([], [], color=p.control, lw=1.2, label="French, for reference")
                ax.fill_between([], [], color=p.band, alpha=0.5, label="exposure >= 0.5")
                ax.legend(loc="center left", fontsize=9)
                continue
            g = a[a.lang == lang].set_index("t")
            on = g.index[g.exposure.fillna(0) >= 0.5]
            if len(on):
                ax.axvspan(on.min(), g.index.max(), color=p.band, alpha=0.45, lw=0, zorder=0)
            if lang != "fr":
                ax.plot(fr.index, fr, color=p.control, lw=1.0, alpha=0.8)
            c = p.treated if lang in TREATED else p.control if lang == "fr" else p.ink_muted
            ax.plot(g.index, g.idx, color=c, lw=1.8)
            if g.idx.min() < 40:
                ax.text(0.03, 0.04, "2026: off scale (Iran outages)", transform=ax.transAxes,
                        ha="left", fontsize=8, color=p.ink_muted)  # fmt: skip
            ax.axhline(100, color=p.ink_muted, lw=0.5)
            coh = g.cohort.iloc[0]
            lab = f"from {pd.Period(coh, 'M').strftime('%b %Y')}" if coh != "never" else "never"
            if lang == "fr":
                lab = "Jul 2026 (control)"
            ax.set_title(f"{NAMES[lang]}  ·  {lab}", fontsize=9.5, color=p.ink, loc="left")
            ax.set_xlim(pd.Timestamp("2021-01-01"), g.index.max())
            _year_axis(ax, 2)
        axes[0, 0].set_ylim(40, 140)
        fig.supylabel("Search arrivals, index", fontsize=10, color=p.ink_muted, x=0.012)
        theme.title(fig, title, sub)
        theme.source(fig, SOURCE + " Shading starts in the edition's cohort month (P03).")
        theme.save(fig, "chart4_editions")


# ---------------------------------------------------------------------- chart 5: dot plot


def chart5(mode: str) -> None:
    t = pd.read_csv(QA / "p21_by_type.csv")
    tau2 = max(np.var(t.est) - np.mean(t.se**2), 0.0)
    t["psd"] = np.sqrt(tau2 * t.se**2 / (tau2 + t.se**2))  # normal-normal posterior SD
    t = pd.concat([t, pd.DataFrame([dict(coarse_type="human", eb=0.0, psd=np.nan)])])
    t = t.sort_values("eb").reset_index(drop=True)
    top = t[t.coarse_type != "human"].iloc[-1]
    title = "Kinds of article differ little; sports events and species held up best"
    sub = (
        f"Effect of full AI Overviews exposure on user views, relative to biographies "
        f"(partially pooled, 95% interval). {TYPES[top.coarse_type].capitalize()} "
        f"{pct(top.eb):+.0f}% (exploratory)"
    )
    TAKEAWAYS["chart5_types"] = f"{title} ({sub.split('. ', 1)[1]} vs biographies)"
    with theme.use(mode) as p:
        fig, ax = plt.subplots(figsize=(10, 7.2))
        fig.subplots_adjust(left=0.27, right=0.95, top=0.85, bottom=0.11)
        ax.axvspan(-5, 5, color=p.band, alpha=0.35, lw=0)
        ax.axvline(0, color=p.ink_muted, lw=0.8)
        for i, r in t.iterrows():
            if r.coarse_type == "human":
                ax.plot(0, i, "D", color=p.ink_muted, ms=7, mec=p.surface, mew=2)
                continue
            ax.plot([pct(r.eb - 1.96 * r.psd), pct(r.eb + 1.96 * r.psd)], [i, i], color=p.control,
                    lw=2)  # fmt: skip
            ax.plot(pct(r.eb), i, "o", color=p.control, ms=8, mec=p.surface, mew=2)
        ax.set_yticks(range(len(t)), [("biographies (reference)" if c == "human" else TYPES[c])
                                      for c in t.coarse_type], fontsize=9)  # fmt: skip
        ax.grid(axis="y", visible=False)
        ax.grid(axis="x", visible=True)
        ax.set_xlabel("Effect on user web views vs biographies, % (95% interval)")
        theme.title(fig, title, sub)
        theme.source(fig, SOURCE + " P06 sample, Wikidata types (P08); empirical-Bayes shrinkage.")
        theme.save(fig, "chart5_types")


# --------------------------------------------------------------- chart 6: editors vs readers


def chart6(d: pd.DataFrame, mode: str) -> None:
    rows = []
    for lang, g in d.groupby("lang"):
        g = g.set_index("t")
        for col in ("active_user", "views"):
            sm = g[col].rolling(12, center=True, min_periods=6).mean()
            rows.append(
                pd.DataFrame(
                    {"lang": lang, "col": col, "idx": 100 * sm / g[col]["2019-04":"2020-03"].mean()}
                )
            )
    x = pd.concat(rows).reset_index()
    end = x[x.t == pd.Timestamp("2026-03-01")].pivot(index="lang", columns="col", values="idx")
    slower = int((end.active_user > end.views).sum())
    title = "Editors have held up better than readers in most editions"
    sub = (
        f"12-month averages, Apr 2019-Mar 2020 = 100. By early 2026 editors are above views in "
        f"{slower} of 11 editions (descriptive; the H6 test found no AI Overviews effect)"
    )
    TAKEAWAYS["chart6_editors"] = f"{title} ({sub.split('. ', 1)[1]})"
    with theme.use(mode) as p:
        fig, axes = plt.subplots(3, 4, figsize=(12, 8.4), sharex=True, sharey=True)
        fig.subplots_adjust(left=0.06, right=0.98, top=0.86, bottom=0.09, hspace=0.32, wspace=0.1)
        for ax, lang in zip(axes.flat, eda.ORDER + [None], strict=True):
            if lang is None:
                ax.axis("off")
                ax.plot([], [], color=p.third, lw=2, label="active registered editors (5+ edits)")
                ax.plot([], [], color=p.ink_muted, lw=1.5, label="user views (all access)")
                ax.plot([], [], color=p.ink_muted, lw=0.9, ls=(0, (1, 2)), label="cohort month")
                ax.legend(loc="center left", fontsize=9)
                continue
            for col, c, lw in (("views", p.ink_muted, 1.4), ("active_user", p.third, 2.0)):
                s = x[(x.lang == lang) & (x.col == col)]
                ax.plot(s.t, s.idx, color=c, lw=lw)
            coh = d[d.lang == lang].cohort.iloc[0]
            if coh != "never":
                ax.axvline(pd.Period(coh, "M").to_timestamp(), color=p.ink_muted, lw=0.9,
                           ls=(0, (1, 2)))  # fmt: skip
            ax.axhline(100, color=p.ink_muted, lw=0.5)
            ax.set_title(NAMES[lang], fontsize=9.5, color=p.ink, loc="left")
            _year_axis(ax, 2)
        fig.supylabel("Index (Apr 2019-Mar 2020 = 100)", fontsize=10, color=p.ink_muted, x=0.012)
        theme.title(fig, title, sub)
        theme.source(fig, SOURCE + " Editors: AQS, bots excluded; anonymous editors left out "
                     "(temporary accounts from 2025-06); pt registered editors jump when IP "
                     "editing ended (2020-10).")  # fmt: skip
        theme.save(fig, "chart6_editors")


# -------------------------------------------------------------------------- forest plot


def forest(mode: str) -> None:
    r = pd.read_csv(QA / "p20_robustness.csv")
    r = r[r.pct.notna() & ~r.spec.str.startswith("+ ru, fa; fa")]
    order = list(dict.fromkeys(r.spec))
    loss = r[(r.ri_p < 0.05) & (r.pct < 0) & ~r.group.isin(["placebo", "negative control"])]
    title = ("No robustness check finds a significant loss" if loss.empty else
             f"{len(loss)} of {len(r)} robustness checks find a significant loss")  # fmt: skip
    sub = (
        f"{len(r)} estimates from the P20 variants of the staggered DiD, effect on search "
        f"arrivals, 95% RI interval. Placebo and negative controls in grey"
    )
    full = r[r.window == "full"].set_index("spec").pct
    TAKEAWAYS["forest_robustness"] = (
        f"{title}; full window {full['baseline (P17)']:+.0f}%, without French "
        f"{full['leave out fr']:+.0f}%, with a bot-reclassification step "
        f"{full['edition x post-2025-04 bot step']:+.0f}%"
    )
    with theme.use(mode) as p:
        fig, axes = plt.subplots(1, 2, figsize=(11, 11.5), sharey=True)
        fig.subplots_adjust(left=0.30, right=0.97, top=0.91, bottom=0.07, wspace=0.08)
        for ax, (w, name) in zip(
            axes,
            (("primary", "Primary window (to Feb 2025)"), ("full", "Full window (to Jul 2026)")),
            strict=True,
        ):
            ax.axvspan(-5, 5, color=p.band, alpha=0.35, lw=0)
            ax.axvline(0, color=p.ink_muted, lw=0.8)
            for _, x in r[r.window == w].iterrows():
                i = order.index(x.spec)
                grey = x.group in ("placebo", "negative control")
                c = p.ink_muted if grey else p.treated if x.group == "baseline" else p.control
                lo, hi = max(x.lo_pct, -60), min(x.hi_pct, 70)
                ax.plot([lo, hi], [i, i], color=c, lw=1.6)
                ax.plot(x.pct, i, "D" if x.group == "baseline" else "o", color=c,
                        ms=8 if x.group == "baseline" else 6, mec=p.surface, mew=1.5)  # fmt: skip
                if x.hi_pct > 70 or x.lo_pct < -60:
                    ax.annotate(
                        "clipped",
                        (hi if x.hi_pct > 70 else lo, i),
                        xytext=(3, 3),
                        textcoords="offset points",
                        fontsize=7,
                        color=p.ink_muted,
                    )
            ax.set_xlim(-62, 75)
            ax.set_title(name, fontsize=10.5, color=p.ink, loc="left")
            ax.grid(axis="y", visible=False)
            ax.grid(axis="x", visible=True)
            ax.set_xlabel("Effect on search arrivals, %")
        axes[0].set_yticks(range(len(order)), order, fontsize=8.5)
        axes[0].set_ylim(len(order) - 0.5, -0.7)
        theme.title(fig, title, sub)
        theme.source(fig, SOURCE + " Band = smallest effect of interest (+/-5%).")
        theme.save(fig, "forest_robustness")


def main() -> None:
    d = _panel()
    a = _adjusted(d)
    for mode in ("light", "dark"):
        chart2(mode)
        chart3(d, mode)
        chart4(a, mode)
        chart5(mode)
        chart6(d, mode)
        forest(mode)
    pd.Series(TAKEAWAYS, name="takeaway").rename_axis("figure").to_csv(QA / "p27_takeaways.csv")
    for k, v in TAKEAWAYS.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
