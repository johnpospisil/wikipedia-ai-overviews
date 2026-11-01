"""Full revision history (metadata only) of the sample articles, from stub-meta-history dumps.

Source: https://dumps.wikimedia.org/<wiki>/<DUMP_DATE>/<wiki>-<DUMP_DATE>-stub-meta-history<N>.xml.gz
(md5 from dumpstatus.json; 246 GB for the 11 editions). Stubs list every revision of every page
with id, timestamp, contributor, minor flag and size, but no text. Used for:
  P08  the revision current at 2023-12-31 (its text is then fetched in batches of 50 revids) and
       the creation date (first revision);
  P09  per-article monthly edits and distinct editors.
The dumps are pretty-printed one tag per line, so a line scanner is much faster than an XML
parser. Pages outside the sample are skipped without parsing. Editors are stored as a 64-bit
hash of the user id or, for logged-out edits, of the IP/temporary account name: IPs are never
written out.

Output: PARQUET_DIR/stub_history/lang=<xx>/part-<N>.parquet
  page_id, rev_id, ts, editor (int64 hash), registered (False for IPs and temporary
  accounts), minor, bytes, kind (user | ip | temp | deleted), name_bot (registered user name
  matching Wikimedia's bot-name rule, as AQS's `name-bot` editor type)
Run: python -m wao.ingest.stub_history [--procs 4] [--reparse]  (--reparse rebuilds every part
from the raw files, e.g. after a schema change)
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from wao import config, http
from wao.ingest.download import WORKERS, fetch
from wao.ingest.sql_dumps import DUMP_DATE

NUM = re.compile(rb"<(?:id|ns)>(\d+)<")
TS = re.compile(rb"<timestamp>([^<]+)<")
TEXT_BYTES = re.compile(rb'<text bytes="(\d+)"')
INNER = re.compile(rb">([^<]*)<")
BOT_NAME = re.compile(rb"(?i)^.*bot([^a-z].*$|$)")  # mediawiki-history's isBotByName
TEMP_NAME = re.compile(rb"^~2\d{3}-")  # temporary accounts (2024-): ~2025-12345-6; older user
# names can also start with "~"
SCHEMA = pa.schema(
    [
        ("page_id", pa.int64()),
        ("rev_id", pa.int64()),
        ("ts", pa.timestamp("s", tz="UTC")),
        ("editor", pa.int64()),
        ("registered", pa.bool_()),
        ("minor", pa.bool_()),
        ("bytes", pa.int64()),
        ("kind", pa.string()),
        ("name_bot", pa.bool_()),
    ]
)


def editor_hash(key: bytes) -> int:
    return int.from_bytes(hashlib.blake2b(key, digest_size=8).digest(), "big", signed=True)


def parse(lines, page_ids: set[int]):
    """Yield (page_id, rev_id, ts, editor, registered, minor, bytes, kind, name_bot) for pages in
    `page_ids`."""
    state = "out"  # out | page_head | skip | rev
    page = ns = None
    rev: dict = {}
    for line in lines:
        s = line.strip()
        if state == "skip":
            if s == b"</page>":
                state = "out"
            continue
        if s == b"<page>":
            state, page, ns = "page_head", None, None
        elif state == "page_head":
            if s.startswith(b"<ns>"):
                ns = int(NUM.match(s).group(1))
            elif s.startswith(b"<id>"):
                page = int(NUM.match(s).group(1))
                if ns != 0 or page not in page_ids:
                    state = "skip"
            elif s == b"<revision>":
                state, rev = "rev", {"minor": False, "reg": False, "who": b"", "bytes": None}
        elif state == "rev":
            if s.startswith(b"<id>") and "id" not in rev:
                rev["id"] = int(NUM.match(s).group(1))
            elif s.startswith(b"<timestamp>"):
                rev["ts"] = TS.match(s).group(1).decode()
            elif s.startswith(b"<username>"):
                rev["name"] = INNER.search(s).group(1)
            elif s.startswith(b"<id>"):  # contributor id (after the revision id)
                rev["who"], rev["reg"] = b"u" + NUM.match(s).group(1), True
            elif s.startswith(b"<ip>"):
                rev["who"] = b"a" + INNER.search(s).group(1)
            elif s == b"<minor />" or s == b"<minor/>":
                rev["minor"] = True
            elif s.startswith(b"<text "):
                m = TEXT_BYTES.match(s)
                rev["bytes"] = int(m.group(1)) if m else None
            elif s == b"</revision>":
                who = rev["who"] or (b"a" + rev["name"] if "name" in rev else b"")
                name = rev.get("name", b"")
                if TEMP_NAME.match(name):
                    kind, rev["reg"] = "temp", False
                else:
                    kind = "user" if rev["reg"] else "ip" if who else "deleted"
                yield (
                    page,
                    rev["id"],
                    rev["ts"],
                    editor_hash(who) if who else None,
                    rev["reg"],
                    rev["minor"],
                    rev["bytes"],
                    kind,
                    kind == "user" and bool(BOT_NAME.match(name)),
                )
                state = "page_rev"
        elif state == "page_rev":
            if s == b"<revision>":
                state, rev = "rev", {"minor": False, "reg": False, "who": b"", "bytes": None}
            elif s == b"</page>":
                state = "out"


def out_path(lang: str, n: int) -> Path:
    return config.PARQUET_DIR / "stub_history" / f"lang={lang}" / f"part-{n:02d}.parquet"


def raw_path(name: str) -> Path:
    return config.RAW_DIR / "stub_history" / DUMP_DATE / name


def convert(lang: str, n: int, path: Path) -> dict:
    t0 = time.time()
    s = pd.read_parquet(config.PANEL_DIR / "sample.parquet", columns=["lang", "page_id"])
    ids = set(s.loc[s.lang == lang, "page_id"].astype(int))
    proc = subprocess.Popen(["gzip", "-dc", str(path)], stdout=subprocess.PIPE, bufsize=1 << 24)
    rows = list(parse(proc.stdout, ids))
    if proc.wait() != 0:
        raise RuntimeError(f"gzip failed on {path}")
    cols = list(zip(*rows, strict=True)) if rows else [[] for _ in SCHEMA]
    cols[2] = pd.to_datetime(pd.Series(cols[2], dtype="object"), utc=True).dt.floor("s")
    table = pa.Table.from_arrays(
        [pa.array(c, f.type) for c, f in zip(cols, SCHEMA, strict=True)], schema=SCHEMA
    )
    out = out_path(lang, n)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    pq.write_table(table, tmp, compression="zstd")
    tmp.rename(out)
    return {"lang": lang, "part": n, "revisions": len(rows), "s": round(time.time() - t0)}


def file_list(langs=config.LANGS) -> list[dict]:
    s = http.session("dumps", min_interval=1.0)
    rows = []
    for lang in langs:
        url = f"https://dumps.wikimedia.org/{lang}wiki/{DUMP_DATE}/dumpstatus.json"
        job = s.get(url, timeout=60).json()["jobs"]["xmlstubsdump"]
        if job["status"] != "done":
            raise RuntimeError(f"{lang}: stubs dump status {job['status']}")
        for name, f in job["files"].items():
            m = re.search(r"stub-meta-history(\d+)\.xml\.gz$", name)
            if m:
                rows.append(
                    {
                        "lang": lang,
                        "n": int(m.group(1)),
                        "name": name,
                        "url": "https://dumps.wikimedia.org" + f["url"],
                        "bytes": f["size"],
                        "md5": f["md5"],
                    }
                )
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--reparse", action="store_true", help="rebuild parts that already exist")
    a = ap.parse_args()
    todo = [r for r in file_list() if a.reparse or not out_path(r["lang"], r["n"]).exists()]
    # smallest first, so early files are processed while big ones download
    todo.sort(key=lambda r: r["bytes"])
    print(f"{len(todo)} files, {sum(r['bytes'] for r in todo) / 1e9:.0f} GB", flush=True)
    ua = http.user_agent()

    def get(r):
        return r, fetch(r["url"], raw_path(r["name"]), r["bytes"], r["md5"], ua=ua)

    with ThreadPoolExecutor(WORKERS) as dl, ProcessPoolExecutor(a.procs) as cpu:
        jobs = []
        for d in as_completed([dl.submit(get, r) for r in todo]):
            r, path = d.result()
            jobs.append(cpu.submit(convert, r["lang"], r["n"], path))
        for j in as_completed(jobs):
            print(j.result(), flush=True)


if __name__ == "__main__":
    main()
