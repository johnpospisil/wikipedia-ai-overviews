"""P11: AQS reference series for the reconciliation checks.

  pageviews/aggregate/<wiki>/<access>/<agent>/monthly  for the 11 core editions, 2016-01..2026-09:
    user x {desktop, mobile-web, mobile-app}, automated and spider x all-access
  pageviews/per-article/<wiki>/all-access/user/<title>/monthly  for 200 random sample articles
    (seed 11), by their current title. AQS counts views of that exact title only, so it is
    compared with the P07 views matched by page_id + current title or by title alone (matches
    `id` and `null_title`), not with the redirect-resolved total.
Paced at one request per 7 s (AQS ignores the wiki login; 2026 rate limits) and cached.

Output: PARQUET_DIR/aqs/aggregate.parquet  lang, month, access, agent, views
        PARQUET_DIR/aqs/per_article.parquet  lang, page_id, title, month, views (+ http status)
Run: python -m wao.ingest.aqs_checks
"""

from __future__ import annotations

from urllib.parse import quote

import pandas as pd

from wao import config, http

AQS = "https://wikimedia.org/api/rest_v1/metrics/pageviews"
START, END = "2016010100", "2026093000"
SERIES = [("desktop", "user"), ("mobile-web", "user"), ("mobile-app", "user"),
          ("all-access", "automated"), ("all-access", "spider")]  # fmt: skip
N_ARTICLES, SEED = 200, 11


def out_dir():
    return config.PARQUET_DIR / "aqs"


def _items(s, url: str) -> tuple[int, list[dict]]:
    r = s.get(url, timeout=120)
    if r.status_code == 404:
        return 404, []
    r.raise_for_status()
    return 200, r.json()["items"]


def aggregate(s) -> pd.DataFrame:
    rows = []
    for lang in config.LANGS:
        for access, agent in SERIES:
            url = f"{AQS}/aggregate/{lang}.wikipedia/{access}/{agent}/monthly/{START}/{END}"
            _, items = _items(s, url)
            rows += [(lang, x["timestamp"][:4] + "-" + x["timestamp"][4:6], access, agent,
                      x["views"]) for x in items]  # fmt: skip
        print(f"aggregate {lang}", flush=True)
    return pd.DataFrame(rows, columns=["lang", "month", "access", "agent", "views"])


def per_article(s) -> pd.DataFrame:
    smp = pd.read_parquet(config.PANEL_DIR / "sample.parquet", columns=["lang", "page_id", "title"])
    pick = smp.sample(N_ARTICLES, random_state=SEED)
    rows = []
    for i, r in enumerate(pick.itertuples(), 1):
        url = (f"{AQS}/per-article/{r.lang}.wikipedia/all-access/user/"
               f"{quote(r.title, safe='')}/monthly/{START}/{END}")  # fmt: skip
        status, items = _items(s, url)
        if not items:
            rows.append((r.lang, r.page_id, r.title, None, None, status))
        rows += [(r.lang, r.page_id, r.title, x["timestamp"][:4] + "-" + x["timestamp"][4:6],
                  x["views"], status) for x in items]  # fmt: skip
        if i % 20 == 0:
            print(f"per-article {i}/{N_ARTICLES}", flush=True)
    return pd.DataFrame(rows, columns=["lang", "page_id", "title", "month", "views", "http"])


def main() -> None:
    s = http.session("aqs", min_interval=7.0)
    out_dir().mkdir(parents=True, exist_ok=True)
    aggregate(s).to_parquet(out_dir() / "aggregate.parquet", index=False)
    per_article(s).to_parquet(out_dir() / "per_article.parquet", index=False)


if __name__ == "__main__":
    main()
