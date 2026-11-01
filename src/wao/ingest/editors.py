"""P09: language-level edits and active editors (AQS), and the bot accounts of each edition.

AQS (https://wikimedia.org/api/rest_v1/metrics/, monthly, content pages = article namespace):
  edits/aggregate/<wiki>/<editor-type>/content/monthly/...       editor types user, anonymous,
                                                                group-bot, name-bot
  editors/aggregate/<wiki>/<editor-type>/content/<activity>/monthly/...  user and anonymous,
                                                                activity 1..4, 5..24, 25..99, 100..
AQS editor types are exclusive: group-bot (in the bot group at the time), then name-bot (name
matches the bot rule), then user (registered) or anonymous (IP; temporary accounts from 2025
need checking, see DATA.md). "Active editors" = 5+ content edits in the month; 100+ = very
active. AQS sits behind the 2026 rate limits and does not accept the wiki login cookie, so
requests are paced at one per 7 s (~130 requests, ~15 min) and cached.

Bots for the per-article panel (wao.build.edits): current members of the local `bot` group and
of the global-bot group (meta), by user id, hashed as in wao.ingest.stub_history. Former bots
are caught only by the name rule (stub_history.name_bot).

Output: PARQUET_DIR/editors/aqs_lang_month.parquet  lang, month, metric, editor_type,
        activity, value;  PARQUET_DIR/editors/bots.parquet  lang, editor, source
Run: python -m wao.ingest.editors
"""

from __future__ import annotations

import pandas as pd

from wao import config, http
from wao.ingest.stub_history import editor_hash

AQS = "https://wikimedia.org/api/rest_v1/metrics"
START, END = "20010101", "20261001"
EDIT_TYPES = ("user", "anonymous", "group-bot", "name-bot")
EDITOR_TYPES = ("user", "anonymous")
LEVELS = ("1..4-edits", "5..24-edits", "25..99-edits", "100..-edits")


def out_dir():
    return config.PARQUET_DIR / "editors"


def _results(s, url: str) -> list[dict]:
    r = s.get(url, timeout=120)
    if r.status_code == 404:  # AQS: no data for this combination
        return []
    r.raise_for_status()
    return r.json()["items"][0]["results"]


def aqs(langs=config.LANGS) -> pd.DataFrame:
    s = http.session("aqs", min_interval=7.0)
    rows = []
    for lang in langs:
        wiki = f"{lang}.wikipedia.org"
        for et in EDIT_TYPES:
            url = f"{AQS}/edits/aggregate/{wiki}/{et}/content/monthly/{START}/{END}"
            rows += [(lang, x["timestamp"], "edits", et, "all", x["edits"])
                     for x in _results(s, url)]  # fmt: skip
        for et in EDITOR_TYPES:
            for lv in LEVELS:
                url = f"{AQS}/editors/aggregate/{wiki}/{et}/content/{lv}/monthly/{START}/{END}"
                rows += [(lang, x["timestamp"], "editors", et, lv, x["editors"])
                         for x in _results(s, url)]  # fmt: skip
        print(f"{lang}: {len(rows):,} rows", flush=True)
    df = pd.DataFrame(rows, columns=["lang", "month", "metric", "editor_type", "activity",
                                     "value"])  # fmt: skip
    df["month"] = pd.to_datetime(df.month).dt.strftime("%Y-%m")
    return df


def _users(s, api: str, params: dict) -> list[dict]:
    base = {"action": "query", "format": "json", "formatversion": 2}
    out, cont = [], {}
    while True:
        j = s.get(api, params=base | params | cont, timeout=60).json()
        q = j.get("query", {})
        out += q.get("allusers", []) + q.get("globalallusers", []) + q.get("users", [])
        if "continue" not in j:
            return out
        cont = j["continue"]


def bots(langs=config.LANGS) -> pd.DataFrame:
    meta = "https://meta.wikimedia.org/w/api.php"
    sm = http.session("mw_meta_meta", min_interval=0.35)
    http.login(sm, meta)
    global_names = [u["name"] for u in _users(sm, meta, {"list": "globalallusers",
                    "agugroup": "global-bot", "agulimit": "max"})]  # fmt: skip
    rows = []
    for lang in langs:
        api = f"https://{lang}.wikipedia.org/w/api.php"
        s = http.session(f"mw_meta_{lang}", min_interval=0.35)
        http.login(s, api)
        local = _users(s, api, {"list": "allusers", "augroup": "bot", "aulimit": "max"})
        rows += [(lang, u["userid"], "group-bot") for u in local]
        for i in range(0, len(global_names), 50):
            found = _users(s, api, {"list": "users", "ususers": "|".join(global_names[i : i + 50])})
            rows += [(lang, u["userid"], "global-bot") for u in found if "userid" in u]
    df = pd.DataFrame(rows, columns=["lang", "user_id", "source"])
    df = df.drop_duplicates(["lang", "user_id"])
    df["editor"] = [editor_hash(b"u%d" % i) for i in df.user_id]
    return df[["lang", "editor", "source"]]


def main() -> None:
    out_dir().mkdir(parents=True, exist_ok=True)
    b = bots()
    b.to_parquet(out_dir() / "bots.parquet", index=False)
    print(b.groupby(["lang", "source"]).size().unstack(fill_value=0), flush=True)
    df = aqs()
    df.to_parquet(out_dir() / "aqs_lang_month.parquet", index=False)
    print(f"{len(df):,} rows, {df.month.min()}..{df.month.max()}")


if __name__ == "__main__":
    main()
