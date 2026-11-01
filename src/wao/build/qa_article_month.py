"""P11: sample article x month with web views and clickstream search arrivals, for the
reconciliation and truncation checks (P13 builds the analysis panel properly).

  views_web     `user` views on desktop + mobile web (clickstream covers only these), P07
  views_app     `user` views in the apps (not in clickstream)
  arr_search    clickstream `other-search` arrivals, summed over every title that resolves to
                the article (current title and redirects, P07 lookup); null = no published
                pair, i.e. fewer than 10 search arrivals that month (censored)
  arr_total     all published clickstream arrivals (null if the article has none)
  decile        2023 popularity decile within the edition (P06; fixed, pre-period)
Only months with clickstream for the edition. Output: PARQUET_DIR/qa/article_month.parquet
Run: python -m wao.build.qa_article_month
"""

from __future__ import annotations

import duckdb

from wao import config


def out_path():
    return config.PARQUET_DIR / "qa" / "article_month.parquet"


def build(con: duckdb.DuckDBPyConnection) -> None:
    P = config.PARQUET_DIR  # noqa: N806
    con.execute(f"set temp_directory='{config.TMP_DIR}'")
    langs = ", ".join(f"'{x}'" for x in config.LANGS)
    out_path().parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"""
    copy (
      with v as (
        select lang, page_id, strftime(date, '%Y-%m') as month,
               sum(views) filter (where access in ('desktop', 'mobile-web')) as views_web,
               sum(views) filter (where access = 'mobile-app') as views_app
        from read_parquet('{P}/pageview_daily/agent=user/*/part.parquet', hive_partitioning=true)
        group by all
      ),
      t as (select lang, key as title, page_id from '{P}/pageview_lookup.parquet'
            where key_type = 'title'),
      c as (
        select c.lang, t.page_id, c.month, sum(arr_search) as arr_search,
               sum(arr_total) as arr_total
        from read_parquet('{P}/clickstream_article/*/*/part.parquet', hive_partitioning=true) c
        join t on t.lang = c.lang and t.title = c.title
        where c.lang in ({langs})
        group by all
      ),
      m as (select distinct lang, month from '{P}/clickstream_lang_month.parquet'
            where lang in ({langs}))
      select s.lang, s.page_id, m.month, s.decile, s.weight,
             coalesce(v.views_web, 0) as views_web, coalesce(v.views_app, 0) as views_app,
             c.arr_search, c.arr_total
      from '{config.PANEL_DIR / "sample.parquet"}' s
      join m on m.lang = s.lang
      left join v on v.lang = s.lang and v.page_id = s.page_id and v.month = m.month
      left join c on c.lang = s.lang and c.page_id = s.page_id and c.month = m.month
      order by 1, 2, 3
    ) to '{out_path()}' (format parquet, compression zstd)
    """)


def main() -> None:
    con = duckdb.connect()
    build(con)
    print(
        con.sql(f"""select lang, count(*) n, avg((arr_search is null)::int) censored,
                      sum(views_web) views from '{out_path()}' group by 1 order by 1""").df()
    )


if __name__ == "__main__":
    main()
