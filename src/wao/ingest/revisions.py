"""The 2023-12-31 revision of every sample article: ids and dates from the stubs, text from the API.

Which revision: the last one with timestamp <= 2023-12-31T23:59:59Z in the stub-meta-history dump
(wao.ingest.stub_history); `created` is the article's first revision there. Only the text is
fetched: action=query&prop=revisions&revids=<50 ids>&rvprop=ids|timestamp|size|content, one
request stream. Wikimedia's 2026 limits are 200/min for a bot with a compliant User-Agent but
only 10/min for clients identified by IP alone, and in Oct 2026 this IP got the 10/min tier
despite its User-Agent, so the default pace is one request every 7 s (~8.5/min, ~8 h in all).
Revids missing from a response (the API caps a response at ~8 MB) are
retried in smaller batches; deleted or suppressed revisions get status `badrevid`/`text_hidden`.
An article with no revision before 2024 (history merged or re-imported later) gets `no_rev_2023`.
Responses are cached, so a rerun is fast; the text itself is never written out, only the
features in wao.build.wikitext.

Output: PARQUET_DIR/features/revisions/lang=<xx>.parquet
Run: python -m wao.ingest.revisions [--procs 4] [--interval 7]
"""

from __future__ import annotations

import argparse
import time
from concurrent.futures import ProcessPoolExecutor

import duckdb
import pandas as pd

from wao import config, http
from wao.build import wikitext

AS_OF = "2023-12-31 23:59:59+00"
BATCH = 50
MIN_INTERVAL = 7.0  # seconds between requests: under the 10/min tier


def out_path(lang: str):
    return config.PARQUET_DIR / "features" / "revisions" / f"lang={lang}.parquet"


def targets() -> pd.DataFrame:
    """lang, page_id, rev_id, rev_ts, rev_bytes, created, n_rev_2023 for every sample article."""
    h = config.PARQUET_DIR / "stub_history" / "*" / "*.parquet"
    con = duckdb.connect()
    con.execute("set TimeZone='UTC'")
    return con.sql(f"""
        with h as (select * from read_parquet('{h}', hive_partitioning=true)),
        a as (select lang, page_id, min(ts) created,
                     arg_max(rev_id, ts) filter (where ts <= '{AS_OF}') rev_id,
                     max(ts) filter (where ts <= '{AS_OF}') rev_ts,
                     arg_max(bytes, ts) filter (where ts <= '{AS_OF}') rev_bytes,
                     count(*) filter (where ts <= '{AS_OF}') n_rev_2023
              from h group by all)
        select s.lang, s.page_id, a.rev_id, a.rev_ts, a.rev_bytes, a.created, a.n_rev_2023
        from read_parquet('{config.PANEL_DIR / "sample.parquet"}') s
        left join a using (lang, page_id) order by 1, 2""").df()


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


def fetch(s, lang: str, revids: list[int]) -> dict[int, tuple[str, str | None]]:
    """revid -> (status, text). Shrinks the batch for revids a response left out."""
    out: dict[int, tuple[str, str | None]] = {}
    j = _get(s, lang, {"prop": "revisions", "revids": "|".join(map(str, revids)),
                       "rvprop": "ids|timestamp|size|content", "rvslots": "main"})  # fmt: skip
    if "error" in j:
        return {r: (f"error:{j['error'].get('code')}", None) for r in revids}
    q = j.get("query", {})
    for b in q.get("badrevids", {}).values():
        out[int(b["revid"])] = ("badrevid", None)
    for page in q.get("pages", []):
        for rev in page.get("revisions", []):
            main = rev.get("slots", {}).get("main", {})
            if main.get("texthidden") or "content" not in main:
                out[rev["revid"]] = ("text_hidden", None)
            else:
                out[rev["revid"]] = ("ok", main["content"])
    left = [r for r in revids if r not in out]
    if left and len(revids) > 1:
        size = max(1, len(revids) // 5)
        for i in range(0, len(left), size):
            out |= fetch(s, lang, left[i : i + size])
    elif left:
        out[left[0]] = ("not_returned", None)
    return out


def _features(item):
    revid, status, text, prefixes = item
    if status != "ok":
        return revid, {}
    try:
        return revid, wikitext.features(text, prefixes)
    except Exception as e:  # noqa: BLE001 - recorded, never silently dropped
        return revid, {"parse_error": type(e).__name__}


def run_lang(lang: str, t: pd.DataFrame, pool, interval: float = MIN_INTERVAL) -> pd.DataFrame:
    s = http.session(f"mw_{lang}", min_interval=interval)
    if config.BOT_USER:
        http.login(s, f"https://{lang}.wikipedia.org/w/api.php")
    prefixes = ns_prefixes(s, lang)
    revids = [int(r) for r in t.rev_id.dropna()]
    status, feats, t0 = {}, {}, time.time()
    for i in range(0, len(revids), BATCH):
        got = fetch(s, lang, revids[i : i + BATCH])
        status |= {r: st for r, (st, _) in got.items()}
        items = [(r, st, txt, prefixes) for r, (st, txt) in got.items()]
        feats |= dict(pool.map(_features, items, chunksize=5))
        if (i // BATCH) % 10 == 0:
            done = i + BATCH
            print(f"{lang}: {min(done, len(revids)):,}/{len(revids):,} "
                  f"({done / (time.time() - t0):.0f}/s)", flush=True)  # fmt: skip
    f = pd.DataFrame.from_dict(feats, orient="index").rename_axis("rev_id").reset_index()
    df = t.assign(status=[status.get(int(r), "?") if pd.notna(r) else "no_rev_2023"
                          for r in t.rev_id])  # fmt: skip
    df = df.merge(f, on="rev_id", how="left") if len(f) else df
    if "parse_error" in df:
        df.loc[df.parse_error.notna(), "status"] = "parse_error"
    out = out_path(lang)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    print(f"{lang}: done {len(df):,} in {(time.time() - t0) / 60:.0f} min "
          f"{df.status.value_counts().to_dict()}", flush=True)  # fmt: skip
    return df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--langs", nargs="*", default=list(config.LANGS))
    ap.add_argument("--interval", type=float, default=MIN_INTERVAL, help="seconds per request")
    a = ap.parse_args()
    t = targets()
    todo = [lang for lang in a.langs if not out_path(lang).exists()]
    with ProcessPoolExecutor(a.procs) as pool:  # parsing is CPU-bound; fetching stays serial
        for lang in todo:
            run_lang(lang, t[t.lang == lang].reset_index(drop=True), pool, a.interval)


if __name__ == "__main__":
    main()
