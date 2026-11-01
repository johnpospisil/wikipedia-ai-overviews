"""P12: Google's Natural Questions (NQ; Kwiatkowski et al. 2019, CC BY-SA 3.0) as an external,
query-based check of the quick-answer label.

NQ train: 307,373 real, anonymised Google search queries (2016-17), each paired with the English
Wikipedia page a top-5 result pointed to. An annotator marked the passage that answers the query
(long answer) and, where one exists, a short answer (an entity, date, number... or yes/no).
"Has a short answer" is the rubric's "answered by one fact" (docs/quick_answer_rubric.md),
judged by Google's annotators on real queries, independent of both P12 labellers.

Only four fields are read from the Hugging Face Parquet copy (column projection over HTTP; the
page HTML is never downloaded): title, question text, has_long (the page answers the query),
has_short (short span or yes/no). Queries are kept as text only for audit; no page text.
Output: PARQUET_DIR/context/nq/part-NNN.parquet (one per source shard; resumable)
Run: python -m wao.ingest.natural_questions
"""

from __future__ import annotations

import time

import duckdb

from wao import config

BASE = ("https://huggingface.co/datasets/google-research-datasets/natural_questions/resolve/main/"
        "default/train-{:05d}-of-00287.parquet")  # fmt: skip
SHARDS = 287


def out_dir():
    return config.PARQUET_DIR / "context" / "nq"


def fetch(con, k: int) -> int:
    out = out_dir() / f"part-{k:03d}.parquet"
    if out.exists():
        return -1
    tmp = out.with_suffix(".tmp")
    con.execute(f"""
    copy (
      select id, document.title as title, question.text as question,
             annotations.long_answer[1].candidate_index >= 0 as has_long,
             len(annotations.short_answers[1].text) > 0
               or annotations.yes_no_answer[1] <> -1 as has_short
      from read_parquet('{BASE.format(k)}')
    ) to '{tmp}' (format parquet)""")
    tmp.rename(out)
    return k


def main() -> None:
    out_dir().mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("install httpfs; load httpfs")
    t0 = time.time()
    for k in range(SHARDS):
        for attempt in range(5):
            try:
                fetch(con, k)
                break
            except duckdb.Error as e:  # HTTP hiccups: back off and retry
                if attempt == 4:
                    raise
                print(f"shard {k}: {type(e).__name__}, retry", flush=True)
                time.sleep(15 * (attempt + 1))
        if k % 20 == 0:
            print(f"{k + 1}/{SHARDS} shards, {time.time() - t0:.0f} s", flush=True)
    n = con.sql(f"select count(*), avg(has_long::int), avg(has_short::int) "
                f"from '{out_dir()}/*.parquet'").fetchall()  # fmt: skip
    print(n)


if __name__ == "__main__":
    main()
