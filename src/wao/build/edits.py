"""P09: per-article monthly edits and distinct editors for the sample, from the stub histories.

Input: parquet/stub_history (every revision of every sample article, wao.ingest.stub_history)
and parquet/editors/bots.parquet. A revision is a bot edit if its editor is in the edition's
bot or global-bot group now, or the user name matches the bot-name rule (as AQS name-bot).
Output: panels/article_edits_month.parquet, sparse (a missing article-month has 0 edits):
  lang, page_id, month (YYYY-MM)
  edits            all revisions (incl. bots and suppressed contributors)
  edits_user       registered, non-bot
  edits_anon       IP or temporary account (temporary accounts from 2025, see DATA.md)
  edits_bot        bot group or bot name
  edits_minor      non-bot edits flagged minor
  editors          distinct non-bot editors (user + anon; an IP and a temp account each count)
  editors_user, editors_anon
  bytes_delta      net change in page size from non-bot edits (first revision: its size)
Run: python -m wao.build.edits
"""

from __future__ import annotations

import duckdb

from wao import config


def out_path():
    return config.PANEL_DIR / "article_edits_month.parquet"


def build(con: duckdb.DuckDBPyConnection) -> None:
    P = config.PARQUET_DIR  # noqa: N806
    con.execute("set TimeZone='UTC'")
    con.execute(f"set temp_directory='{config.TMP_DIR}'")
    con.execute(f"""
    copy (
      with r as (
        select h.lang, page_id, ts, rev_id, h.editor, kind, minor,
               bytes - coalesce(lag(bytes) over (partition by h.lang, page_id order by ts, rev_id),
                                0) as delta,
               (name_bot or b.editor is not null) as bot
        from read_parquet('{P}/stub_history/*/*.parquet', hive_partitioning=true) h
        left join (select distinct lang, editor from '{P}/editors/bots.parquet') b
          on b.lang = h.lang and b.editor = h.editor and h.kind = 'user'
      )
      select lang, page_id, strftime(ts, '%Y-%m') as month,
             count(*)::int as edits,
             count(*) filter (where kind = 'user' and not bot)::int as edits_user,
             count(*) filter (where kind in ('ip', 'temp'))::int as edits_anon,
             count(*) filter (where bot)::int as edits_bot,
             count(*) filter (where minor and not bot)::int as edits_minor,
             count(distinct editor) filter (where kind in ('user', 'ip', 'temp') and not bot)::int
               as editors,
             count(distinct editor) filter (where kind = 'user' and not bot)::int as editors_user,
             count(distinct editor) filter (where kind in ('ip', 'temp'))::int as editors_anon,
             sum(delta) filter (where not bot)::bigint as bytes_delta
      from r group by all order by lang, page_id, month
    ) to '{out_path()}' (format parquet, compression zstd)
    """)


def main() -> None:
    con = duckdb.connect()
    build(con)
    print(
        con.sql(f"""select lang, count(*) rows, count(distinct page_id) articles,
                      sum(edits) edits, round(avg(edits_bot / edits), 3) bot_share_rows
                      from '{out_path()}' group by 1 order by 1""").df()
    )


if __name__ == "__main__":
    main()
