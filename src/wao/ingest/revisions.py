"""The 2023-12-31 revision of every sample article, and its first revision, via the MediaWiki API.

Per article, two cached requests (the API only answers "as of" queries one page at a time):
  1. rvstart=2023-12-31T23:59:59Z, rvdir=older, rvlimit=1, with content -> rev_id, timestamp and
     the features in wao.build.wikitext (the text itself is not kept outside the HTTP cache)
  2. rvdir=newer, rvlimit=1 -> the first revision's timestamp (article creation)
An article with no revision before 2024 (deleted and recreated since, or a history merge) gets
status `no_rev_2023`. Requests to one edition run in series (Wikimedia's API etiquette); a few
editions run at once (one stream per edition). maxlag=5 backs off when the servers are busy.

Output: PARQUET_DIR/features/revisions/lang=<xx>.parquet
Run: python -m wao.ingest.revisions [--workers 11]
"""

from __future__ import annotations

import argparse
import time
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

from wao import config, http
from wao.build import wikitext

AS_OF = "2023-12-31T23:59:59Z"


def out_path(lang: str):
    return config.PARQUET_DIR / "features" / "revisions" / f"lang={lang}.parquet"


def ns_prefixes(s, lang: str) -> tuple[str, ...]:
    """Every name of the Template namespace (local, canonical, aliases), lower-cased."""
    r = s.get(
        f"https://{lang}.wikipedia.org/w/api.php",
        params={
            "action": "query",
            "meta": "siteinfo",
            "siprop": "namespaces|namespacealiases",
            "format": "json",
            "formatversion": 2,
        },
        timeout=60,
    ).json()["query"]
    ns = r["namespaces"]["10"]
    names = {ns["name"], ns.get("canonical", "Template")}
    names |= {a["alias"] for a in r["namespacealiases"] if a["id"] == 10}
    return tuple(sorted(n.lower() for n in names))


def _get(s, lang: str, params: dict) -> dict:
    base = {"action": "query", "format": "json", "formatversion": 2, "maxlag": 5}
    for attempt in range(6):
        r = s.get(f"https://{lang}.wikipedia.org/w/api.php", params=base | params, timeout=120)
        j = r.json()
        if j.get("error", {}).get("code") == "maxlag":
            s.cache.delete(responses=[r])
            time.sleep(5 * (attempt + 1))
            continue
        return j
    return j


def article(s, lang: str, page_id: int, prefixes: tuple[str, ...]) -> dict:
    out: dict = {"lang": lang, "page_id": page_id}
    common = {"prop": "revisions", "pageids": page_id, "rvlimit": 1}
    j = _get(
        s,
        lang,
        common
        | {
            "rvstart": AS_OF,
            "rvdir": "older",
            "rvprop": "ids|timestamp|size|content",
            "rvslots": "main",
        },
    )
    if "error" in j:
        return out | {"status": f"error:{j['error'].get('code')}"}
    page = j["query"]["pages"][0]
    if page.get("missing"):
        return out | {"status": "missing"}
    revs = page.get("revisions") or []
    if not revs:
        out["status"] = "no_rev_2023"
    else:
        rev = revs[0]
        main = rev["slots"]["main"]
        out |= {"rev_id": rev["revid"], "rev_ts": rev["timestamp"], "status": "ok"}
        if main.get("texthidden") or "content" not in main:
            out["status"] = "text_hidden"
        else:
            out |= wikitext.features(main["content"], prefixes)
    j = _get(s, lang, common | {"rvdir": "newer", "rvprop": "ids|timestamp"})
    revs = (j.get("query", {}).get("pages") or [{}])[0].get("revisions") or []
    if revs:
        out["created"] = revs[0]["timestamp"]
    return out


def run_lang(lang: str, page_ids: list[int]) -> pd.DataFrame:
    s = http.session(f"mw_{lang}", min_interval=0.0)
    prefixes = ns_prefixes(s, lang)
    rows, t0 = [], time.time()
    for i, pid in enumerate(page_ids, 1):
        try:
            rows.append(article(s, lang, int(pid), prefixes))
        except Exception as e:  # noqa: BLE001 - recorded, never silently dropped
            rows.append(
                {"lang": lang, "page_id": int(pid), "status": f"exception:{type(e).__name__}"}
            )
        if i % 2000 == 0:
            print(f"{lang}: {i:,}/{len(page_ids):,} ({i / (time.time() - t0):.1f}/s)", flush=True)
    df = pd.DataFrame(rows)
    out = out_path(lang)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    print(f"{lang}: done {len(df):,} in {(time.time() - t0) / 60:.0f} min", flush=True)
    return df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=11)
    ap.add_argument("--langs", nargs="*", default=list(config.LANGS))
    a = ap.parse_args()
    s = pd.read_parquet(config.PANEL_DIR / "sample.parquet", columns=["lang", "page_id"])
    todo = [lang for lang in a.langs if not out_path(lang).exists()]
    ids = [sorted(s[s.lang == lang].page_id) for lang in todo]
    with ProcessPoolExecutor(a.workers) as pool:  # processes: parsing is CPU-bound
        list(pool.map(run_lang, todo, ids))


if __name__ == "__main__":
    main()
