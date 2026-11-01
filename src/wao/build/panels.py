"""P13: the three analysis panels (Parquet, plus CSV copies under panels/csv/).

Breaks from data/reference/data_breaks.csv (P11) are applied as flags and alternative columns,
never by silently dropping rows:
  cs_usable      clickstream exists for the edition-month and month >= 2019-04 (method change)
  cs_short       2025-04: clickstream file ~5 days short. `*_na` columns set it to missing;
                 `*_rs` columns divide it by the edition's shortfall factor k (clickstream / AQS
                 web views in 2025-04 relative to the mean of 2025-03 and 2025-05; core
                 editions from P11, the core median 0.83 elsewhere)
  bot_break      month >= 2025-04 (bot reclassification lowers `user` traffic from then on)
  month_complete every day of the month present in the sample's pageview data (core editions;
                 null for the others, which have no sample)

1. panels/panel_lang_month.parquet  edition x month (40 editions; core 11 from 2016-01, others
   from 2017-11): clickstream arrivals by referrer (published pairs only) with search and link
   shares; `search_arr_corr` = search arrivals scaled up by the P11 hidden share (core);
   AQS `user` views by access and `automated` views (core); active editors and edits (P09);
   exposure and cohort (P03); Google share of the edition's readers and core-update days (P10).
2. panels/panel_article_month/lang=<xx>/part.parquet  sample article x month (one edition at a
   time, to bound memory), from the later of 2016-01 and
   the article's creation month: views by access (`user`) and `automated`; clickstream
   arrivals for clickstream months (an article starts at the earlier of its first revision and
   its first month with views: 2.6% have views before their first surviving revision, after a
   deletion and re-creation or a history merge): `arr_search` null = censored (<10 search
   arrivals that month, NOT zero; `search_censored`), P11 estimate and upper bound of the
   hidden arrivals;
   `*_pub` = sums over published pairs only (each pair >= 10, so they understate small articles);
   edits and editors (P09); static features, quick-answer label (P12) and weights (P06).
3. panels/panel_item_lang_month.parquet  concept (QID) x edition x month for the 6,000
   concepts present in all 11 core editions (P06 `in_concept_panel`), with exposure.
Run: python -m wao.build.panels
"""

from __future__ import annotations

import duckdb
import pandas as pd

from wao import config

PANEL = config.PANEL_DIR
P = config.PARQUET_DIR
REF = config.REFERENCE_DIR
CS_START, SHORT, BOT = "2019-04", "2025-04", "2025-04"
FIRST, LAST = "2016-01", "2026-09"


def shortfall() -> pd.DataFrame:
    c = pd.read_csv(config.REPORT_DIR / "qa" / "p11_clickstream_vs_aqs.csv")
    r = c.pivot(index="month", columns="lang", values="ratio")
    k = (r.loc[SHORT] / r.loc[["2025-03", "2025-05"]].mean()).rename("k")
    all_langs = pd.read_csv(REF / "language_cohorts.csv").wiki
    return k.reindex(all_langs).fillna(k.median()).rename_axis("lang").reset_index()


def lang_month(con) -> None:
    con.register("k", shortfall())
    core = ", ".join(f"'{x}'" for x in config.LANGS)
    con.execute(f"""
    create or replace table lm as
    with grid as (
      select c.wiki as lang, strftime(m, '%Y-%m') as month
      from read_csv('{REF}/language_cohorts.csv') c,
           generate_series(date '{FIRST}-01', date '{LAST}-01', interval 1 month) t(m)
      where c.wiki in ({core}) or strftime(m, '%Y-%m') >= '2017-11'),
    cs as (select * from '{P}/clickstream_lang_month.parquet'),
    aqs as (select lang, month,
              sum(views) filter (where agent = 'user' and access = 'desktop') views_desktop,
              sum(views) filter (where agent = 'user' and access = 'mobile-web') views_mobile_web,
              sum(views) filter (where agent = 'user' and access = 'mobile-app') views_app,
              sum(views) filter (where agent = 'automated') views_automated
            from '{P}/aqs/aggregate.parquet' group by all),
    tr as (select lang, month, observed, hidden, upper
           from read_csv('{config.REPORT_DIR}/qa/p11_truncation_lang_month.csv')),
    ss as (select wiki as lang, month, share as google_share
           from read_csv('{REF}/search_share_lang.csv') where engine = 'google'),
    days as (select lang, month, count(distinct date) n_days from (
               select lang, strftime(date, '%Y-%m') as month, date
               from read_parquet('{P}/pageview_daily/agent=user/*/part.parquet',
                                 hive_partitioning=true)) group by all)
    select g.lang, g.month, g.lang in ({core}) as core, c.role, c.cohort, c.first_exposed,
           coalesce(e.exposure, 0) exposure, coalesce(e.exposure_all_users, 0) exposure_all_users,
           coalesce(e.exposure_as_listed, 0) exposure_as_listed,
           cs.total is not null as cs_available,
           cs.total is not null and g.month >= '{CS_START}' as cs_usable,
           g.month = '{SHORT}' as cs_short, g.month >= '{BOT}' as bot_break,
           case when g.lang in ({core}) then
             coalesce(d.n_days = day(last_day(strptime(g.month || '-01', '%Y-%m-%d'))), false)
           end as month_complete,
           cs.search search_arr, cs.total total_arr, cs.link link_arr,
           cs.link_other link_other_arr, cs.internal_other internal_other_arr,
           cs.external external_arr, cs.empty empty_arr, cs.other other_arr,
           cs.articles cs_articles,
           cs.search / cs.total search_share, cs.link / cs.total link_share,
           case when g.month = '{SHORT}' then null else cs.search end search_arr_na,
           case when g.month = '{SHORT}' then cs.search / k.k else cs.search end search_arr_rs,
           case when g.month = '{SHORT}' then null else cs.total end total_arr_na,
           case when g.month = '{SHORT}' then cs.total / k.k else cs.total end total_arr_rs,
           cs.search * (1 + tr.hidden / nullif(tr.observed, 0)) search_arr_corr,
           cs.search * (1 + tr.upper / nullif(tr.observed, 0)) search_arr_corr_upper,
           a.views_desktop, a.views_mobile_web, a.views_app, a.views_automated,
           ed.active_user, ed.very_active_user, ed.active_anonymous, ed.edits_user,
           ed.edits_anonymous, ss.google_share, ru.core_days
    from grid g
    join read_csv('{REF}/language_cohorts.csv') c on c.wiki = g.lang
    left join read_csv('{REF}/language_exposure.csv') e on e.wiki = g.lang and e.month = g.month
    left join cs on cs.lang = g.lang and cs.month = g.month
    left join k on k.lang = g.lang
    left join aqs a on a.lang = g.lang and a.month = g.month
    left join tr on tr.lang = g.lang and tr.month = g.month
    left join '{PANEL}/editors_lang_month.parquet' ed on ed.lang = g.lang and ed.month = g.month
    left join ss on ss.lang = g.lang and ss.month = g.month
    left join read_csv('{REF}/ranking_updates_monthly.csv', types={{'month': 'VARCHAR'}}) ru
      on ru.month = g.month
    left join days d on d.lang = g.lang and d.month = g.month
    order by g.lang, g.month""")
    con.execute(f"copy lm to '{PANEL}/panel_lang_month.parquet' (format parquet)")


def am_dir():
    return PANEL / "panel_article_month"


AM_GLOB = f"{PANEL}/panel_article_month/*/part.parquet"


def article_month(con, lang: str) -> None:
    out = am_dir() / f"lang={lang}" / "part.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"""
    copy (
      with pv as (
        select lang, page_id, strftime(date, '%Y-%m') as month,
               sum(views) filter (where agent = 'user' and access = 'desktop') v_desktop,
               sum(views) filter (where agent = 'user' and access = 'mobile-web') v_mobile_web,
               sum(views) filter (where agent = 'user' and access = 'mobile-app') v_app,
               sum(views) filter (where agent = 'automated') v_automated
        from read_parquet('{P}/pageview_daily/*/*/part.parquet', hive_partitioning=true)
        where lang = '{lang}' group by all),
      first_pv as (select page_id, min(month) m from pv group by 1),
      art as (
        select s.lang, s.page_id, s.qid, s.decile, s.coarse_type, s.weight, s.in_lang_sample,
               s.in_concept_panel, s.w_concept,
               greatest('{FIRST}', least(coalesce(strftime(f.created, '%Y-%m'), fp.m),
                                         coalesce(fp.m, strftime(f.created, '%Y-%m'))))
                 as first_month
        from '{PANEL}/sample.parquet' s
        left join '{PANEL}/article_features.parquet' f using (lang, page_id)
        left join first_pv fp using (page_id)
        where s.lang = '{lang}'),
      grid as (
        select a.*, strftime(m, '%Y-%m') as month
        from art a, generate_series(date '{FIRST}-01', date '{LAST}-01', interval 1 month) t(m)
        where strftime(m, '%Y-%m') >= a.first_month),
      t as (select lang, key as title, page_id from '{P}/pageview_lookup.parquet'
            where key_type = 'title' and lang = '{lang}'),
      cs as (
        select c.lang, t.page_id, c.month, sum(arr_search) arr_search, sum(arr_total) arr_total,
               sum(arr_link) arr_link, sum(out_links) out_links
        from read_parquet('{P}/clickstream_article/*/*/part.parquet', hive_partitioning=true) c
        join t on t.lang = c.lang and t.title = c.title
        where c.lang = '{lang}' group by all),
      csm as (select lang, month from '{P}/clickstream_lang_month.parquet'
              where lang = '{lang}')
      select g.lang, g.page_id, g.month, g.qid, g.decile, g.coarse_type, g.weight,
             g.in_lang_sample, g.in_concept_panel, g.w_concept,
             coalesce(pv.v_desktop, 0) views_desktop, coalesce(pv.v_mobile_web, 0) views_mobile_web,
             coalesce(pv.v_app, 0) views_app,
             case when g.month >= '2020-05' then coalesce(pv.v_automated, 0) end views_automated,
             csm.month is not null as cs_available,
             csm.month is not null and g.month >= '{CS_START}' as cs_usable,
             g.month = '{SHORT}' as cs_short, g.month >= '{BOT}' as bot_break,
             case when csm.month is not null then cs.arr_search end as arr_search,
             case when csm.month is not null then cs.arr_search is null end as search_censored,
             case when csm.month is not null then coalesce(cs.arr_total, 0) end as arr_total_pub,
             case when csm.month is not null then coalesce(cs.arr_link, 0) end as arr_link_pub,
             case when csm.month is not null then coalesce(cs.out_links, 0) end as out_links_pub,
             si.hidden as search_hidden_est, si.upper as search_hidden_upper,
             coalesce(e.edits, 0) edits, coalesce(e.edits_user, 0) edits_user,
             coalesce(e.edits_anon, 0) edits_anon, coalesce(e.edits_bot, 0) edits_bot,
             coalesce(e.editors, 0) editors,
             q.qa_tier, q.qa_core, q.qa_nq_rate, f.has_infobox, f.prose_chars, f.lead_chars,
             f.n_sections, f.n_refs, f.age_years, f.topic_group, f.topic_confident
      from grid g
      left join pv using (lang, page_id, month)
      left join csm using (lang, month)
      left join cs using (lang, page_id, month)
      left join '{P}/qa/search_imputed.parquet' si using (lang, page_id, month)
      left join '{PANEL}/article_edits_month.parquet' e using (lang, page_id, month)
      left join '{PANEL}/quick_answer.parquet' q using (lang, page_id)
      left join '{PANEL}/article_features.parquet' f using (lang, page_id)
      order by g.page_id, g.month
    ) to '{out}' (format parquet, compression zstd)""")


def item_lang_month(con) -> None:
    con.execute(f"""
    copy (
      select a.qid, a.lang, a.month, a.page_id, a.w_concept, a.coarse_type, a.qa_tier,
             a.qa_nq_rate, a.views_desktop + a.views_mobile_web + a.views_app views_user,
             a.views_desktop + a.views_mobile_web views_web, a.arr_search, a.search_censored,
             a.search_hidden_est, a.cs_usable, a.cs_short, a.bot_break,
             l.exposure, l.cohort, l.role
      from read_parquet('{AM_GLOB}', hive_partitioning=true) a
      join '{PANEL}/panel_lang_month.parquet' l using (lang, month)
      where a.in_concept_panel
      order by a.qid, a.lang, a.month
    ) to '{PANEL}/panel_item_lang_month.parquet' (format parquet, compression zstd)""")


def csv_copies(con) -> None:
    out = PANEL / "csv"
    out.mkdir(exist_ok=True)
    con.execute(f"copy (from '{PANEL}/panel_lang_month.parquet') to '{out}/panel_lang_month.csv'")
    con.execute(f"""copy (from '{PANEL}/panel_item_lang_month.parquet')
                    to '{out}/panel_item_lang_month.csv.gz'""")
    for lang in config.LANGS:  # one gzipped CSV per edition keeps files manageable
        src = am_dir() / f"lang={lang}" / "part.parquet"
        con.execute(f"""copy (select '{lang}' as lang, * from '{src}')
                        to '{out}/panel_article_month_{lang}.csv.gz'""")


def main() -> None:
    con = duckdb.connect()
    con.execute("set TimeZone='UTC'")
    con.execute(f"set temp_directory='{config.TMP_DIR}'")
    con.execute("set preserve_insertion_order=false")
    lang_month(con)
    for lang in config.LANGS:
        article_month(con, lang)
        print(f"article panel {lang} done", flush=True)
    item_lang_month(con)
    csv_copies(con)
    for name, src in (("lang_month", f"'{PANEL}/panel_lang_month.parquet'"),
                      ("article_month", f"read_parquet('{AM_GLOB}')"),
                      ("item_lang_month", f"'{PANEL}/panel_item_lang_month.parquet'")):  # fmt: skip
        n = con.execute(f"select count(*) from {src}").fetchone()[0]
        print(f"panel_{name}: {n:,} rows")


if __name__ == "__main__":
    main()
