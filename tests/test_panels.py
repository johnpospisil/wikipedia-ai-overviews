"""P13 panel checks on the real outputs (skipped when the panels have not been built)."""

from __future__ import annotations

import duckdb
import pandas as pd
import pytest

from wao import config

PANEL, P = config.PANEL_DIR, config.PARQUET_DIR
LM, IM = PANEL / "panel_lang_month.parquet", PANEL / "panel_item_lang_month.parquet"
AM_DIR = PANEL / "panel_article_month"
AM = f"read_parquet('{AM_DIR}/*/part.parquet', hive_partitioning=true)"


@pytest.fixture(scope="module")
def con():
    if not (LM.exists() and AM_DIR.exists() and IM.exists()):
        pytest.skip("panels not built (python -m wao.build.panels)")
    return duckdb.connect()


def one(con, q: str):
    return con.execute(q).fetchone()


def test_keys_unique(con):
    for src, keys in ((f"'{LM}'", "lang, month"), (AM, "lang, page_id, month"),
                      (f"'{IM}'", "qid, lang, month")):  # fmt: skip
        n, d = one(con, f"select count(*), count(distinct ({keys})) from {src}")
        assert n == d, src


def test_lang_month_matches_clickstream_totals(con):
    gap = one(
        con,
        f"""select max(abs(l.search_arr - c.search)) from '{LM}' l
                       join '{P}/clickstream_lang_month.parquet' c using (lang, month)""",
    )[0]
    assert gap == 0


def test_short_month_versions(con):
    d = con.execute(f"""select search_arr, search_arr_na, search_arr_rs from '{LM}'
                        where month = '2025-04' and core""").df()
    assert d.search_arr_na.isna().all()
    assert (d.search_arr_rs > d.search_arr * 1.1).all()  # k ~ 0.81-0.86
    early = one(con, f"select count(*) from '{LM}' where cs_usable and month < '2019-04'")[0]
    assert early == 0


def test_censoring_is_coded_not_zero(con):
    bad, low, hid = one(
        con,
        f"""select
        count(*) filter (where (arr_search is null) <> search_censored),
        count(*) filter (where arr_search < 10),
        max(search_hidden_est) filter (where search_censored)
        from {AM} where cs_available""",
    )
    assert bad == 0 and low == 0 and hid <= 9


def test_article_views_reconcile_with_p11(con):
    est = con.execute(f"""select lang, sum((views_desktop + views_mobile_web + views_app) * weight)
                          est from {AM} where month like '2023-%' group by 1""").df()
    p11 = pd.read_csv(config.REPORT_DIR / "qa" / "p11_sample_vs_aqs.csv")
    p11 = p11[p11.month.str.startswith("2023")].groupby("lang").est.sum()
    m = est.set_index("lang").est / p11
    assert m.between(0.999, 1.001).all(), m


def test_search_arrivals_reconcile_with_p11_table(con):
    a = one(con, f"select sum(arr_search) from {AM} where month like '2023-%'")[0]
    b = one(con, f"select sum(arr_search) from '{P}/qa/article_month.parquet' "
                 "where month like '2023-%'")[0]  # fmt: skip
    assert abs(a - b) / b < 1e-5  # one pt article-month (13 arrivals) predates the article


def test_item_panel_has_all_core_editions(con):
    n, k = one(con, f"select count(distinct qid), count(distinct (qid, lang)) from '{IM}'")
    assert k == n * len(config.LANGS)
    full = one(
        con,
        f"""select avg((k = {len(config.LANGS)})::int) from (
        select qid, month, count(distinct lang) k from '{IM}' where month like '2023-%'
        group by all)""",
    )[0]
    assert full > 0.98  # 98.4% in 2023; 100% from 2024 (some articles created during 2023)


def test_every_core_edition_month_has_pageviews(con):
    gaps = con.execute(f"""select lang, month from '{LM}' where core and not month_complete""").df()
    assert gaps.empty, gaps.to_dict("records")
