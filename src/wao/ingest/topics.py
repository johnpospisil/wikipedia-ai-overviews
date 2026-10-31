"""Article topics from Lift Wing's language-agnostic `outlink-topic-model` (the articletopic model).

POST https://api.wikimedia.org/service/lw/inference/v1/models/outlink-topic-model:predict
  {"page_title": <current title>, "lang": <edition>, "threshold": 0.01}
-> scores for the 64 topics of the ORES/WikiProject taxonomy (only those >= threshold are
returned). The model reads the article's *current* outgoing links (2026), not the 2023 revision:
topic is treated as a stable property of the article. Responses are cached (POST bodies are part
of the cache key); a few workers share the load, each with its own cache file.

Output: PARQUET_DIR/features/topics.parquet  lang, page_id, topic, score  (+ status rows)
Run: python -m wao.ingest.topics [--workers 2] [--shards 4]
"""

from __future__ import annotations

import argparse
import time
import zlib
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

from wao import config, http

URL = "https://api.wikimedia.org/service/lw/inference/v1/models/outlink-topic-model:predict"
THRESHOLD = 0.01


def out_path():
    return config.PARQUET_DIR / "features" / "topics.parquet"


def predict(s, lang: str, title: str) -> tuple[str, list[dict]]:
    body = {"page_title": title, "lang": lang, "threshold": THRESHOLD}
    for attempt in range(5):
        r = s.post(URL, json=body, timeout=60)
        if r.status_code == 200:
            return "ok", r.json()["prediction"]["results"]
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(10 * (attempt + 1))
            continue
        return f"http_{r.status_code}", []
    return f"http_{r.status_code}", []


def run_shard(shard: int, rows: list[tuple[str, int, str]]) -> pd.DataFrame:
    s = http.session(f"liftwing_{shard}", min_interval=0.0, post=True)
    out, t0 = [], time.time()
    for i, (lang, pid, title) in enumerate(rows, 1):
        try:
            status, res = predict(s, lang, title)
        except Exception as e:  # noqa: BLE001 - recorded, never silently dropped
            status, res = f"exception:{type(e).__name__}", []
        if res:
            out += [(lang, pid, t["topic"], t["score"], status) for t in res]
        else:
            out.append((lang, pid, None, None, status))
        if i % 5000 == 0:
            print(
                f"shard {shard}: {i:,}/{len(rows):,} ({i / (time.time() - t0):.1f}/s)", flush=True
            )
    return pd.DataFrame(out, columns=["lang", "page_id", "topic", "score", "status"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--shards", type=int, default=4, help="cache files; keep fixed across runs")
    a = ap.parse_args()
    s = pd.read_parquet(config.PANEL_DIR / "sample.parquet", columns=["lang", "page_id", "title"])
    rows = list(s.itertuples(index=False, name=None))
    # stable sharding, so a rerun hits the same cache files
    shards = [
        [r for r in rows if zlib.crc32(f"{r[0]}{r[1]}".encode()) % a.shards == k]
        for k in range(a.shards)
    ]
    with ProcessPoolExecutor(a.workers) as pool:
        df = pd.concat(pool.map(run_shard, range(a.shards), shards), ignore_index=True)
    out_path().parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path(), index=False)
    print(df.drop_duplicates(["lang", "page_id"]).status.value_counts(), flush=True)


if __name__ == "__main__":
    main()
