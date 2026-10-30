"""MediaWiki SQL table dumps (page, page_props, redirect) for the core editions -> Parquet.

Source: https://dumps.wikimedia.org/<wiki>/<DUMP_DATE>/<wiki>-<DUMP_DATE>-<table>.sql.gz, checked
against the md5 in that dump's dumpstatus.json. Only the columns the frame needs are kept:
  page        page_id, namespace, title (only for namespace 0), is_redirect   (all namespaces)
  page_props  page_id, qid (wikibase_item), is_disambiguation
  redirect    page_id (the redirect), target title (namespace-0 targets, same wiki only)
Titles are MySQL-escaped binary strings (\\', \\\\, \\" …); they are unescaped and decoded as
UTF-8, which matches the underscore form used in pageview and clickstream files.

The dump is the current state (2026-10), not 2023: pages deleted since 2023 drop out of the frame.
How much 2023 traffic that loses is measured in P06 (DATA.md §13).

Run: python -m wao.ingest.sql_dumps
"""

from __future__ import annotations

import gzip
import re
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from wao import config, http
from wao.ingest.download import WORKERS, fetch

DUMP_DATE = "20261001"
TABLES = ("page", "page_props", "redirect")

_STR = rb"'((?:[^'\\]|\\.)*)'"
PAGE = re.compile(rb"\((\d+),(-?\d+)," + _STR + rb",([01]),")
PROPS = re.compile(rb"\((\d+),'(wikibase_item|disambiguation)'," + _STR + rb",")
REDIRECT = re.compile(rb"\((\d+),(-?\d+)," + _STR + rb"," + _STR + rb",")
_ESC = re.compile(rb"\\(.)", re.S)
_ESC_MAP = {b"0": b"\0", b"n": b"\n", b"r": b"\r", b"Z": b"\x1a", b"t": b"\t"}


def unescape(raw: bytes) -> str:
    return _ESC.sub(lambda m: _ESC_MAP.get(m.group(1), m.group(1)), raw).decode("utf-8", "replace")


def _inserts(path: Path) -> Iterator[bytes]:
    with gzip.open(path, "rb") as fh:
        for line in fh:
            if line.startswith((b"INSERT", b"(")):
                yield line


def parse_page(path: Path) -> pa.Table:
    ids, ns, titles, redir = [], [], [], []
    for line in _inserts(path):
        for pid, n, t, r in PAGE.findall(line):
            ids.append(int(pid))
            ns.append(int(n))
            titles.append(unescape(t) if n == b"0" else None)
            redir.append(r == b"1")
    return pa.table(
        {
            "page_id": pa.array(ids, pa.int64()),
            "namespace": pa.array(ns, pa.int32()),
            "title": pa.array(titles, pa.string()),
            "is_redirect": pa.array(redir, pa.bool_()),
        }
    )


def parse_page_props(path: Path) -> pa.Table:
    qid: dict[int, str] = {}
    disambig: set[int] = set()
    for line in _inserts(path):
        for pid, name, val in PROPS.findall(line):
            if name == b"wikibase_item":
                qid[int(pid)] = val.decode()
            else:
                disambig.add(int(pid))
    ids = sorted(qid.keys() | disambig)
    return pa.table(
        {
            "page_id": pa.array(ids, pa.int64()),
            "qid": pa.array([qid.get(i) for i in ids], pa.string()),
            "is_disambiguation": pa.array([i in disambig for i in ids], pa.bool_()),
        }
    )


def parse_redirect(path: Path) -> pa.Table:
    ids, targets = [], []
    for line in _inserts(path):
        for pid, n, t, interwiki in REDIRECT.findall(line):
            if n == b"0" and not interwiki:
                ids.append(int(pid))
                targets.append(unescape(t))
    return pa.table(
        {"page_id": pa.array(ids, pa.int64()), "target": pa.array(targets, pa.string())}
    )


PARSERS = {"page": parse_page, "page_props": parse_page_props, "redirect": parse_redirect}


def out_path(table: str, lang: str) -> Path:
    return config.PARQUET_DIR / "wiki_sql" / table / f"lang={lang}" / "part.parquet"


def raw_path(lang: str, table: str) -> Path:
    return config.RAW_DIR / "sql" / DUMP_DATE / f"{lang}wiki-{DUMP_DATE}-{table}.sql.gz"


def file_list(langs=config.LANGS) -> list[dict]:
    s = http.session("dumps", min_interval=1.0)
    rows = []
    jobs = {"page": "pagetable", "page_props": "pagepropstable", "redirect": "redirecttable"}
    for lang in langs:
        url = f"https://dumps.wikimedia.org/{lang}wiki/{DUMP_DATE}/dumpstatus.json"
        status = s.get(url, timeout=60).json()["jobs"]
        for table in TABLES:
            job = status[jobs[table]]
            if job["status"] != "done":
                raise RuntimeError(f"{lang} {table}: dump status {job['status']}")
            ((name, f),) = job["files"].items()
            rows.append(
                {
                    "lang": lang,
                    "table": table,
                    "url": "https://dumps.wikimedia.org" + f["url"],
                    "bytes": f["size"],
                    "md5": f["md5"],
                }
            )
    return rows


def main() -> None:
    todo = [r for r in file_list() if not out_path(r["table"], r["lang"]).exists()]
    ua = http.user_agent()

    def get(r):
        return fetch(r["url"], raw_path(r["lang"], r["table"]), r["bytes"], r["md5"], ua=ua)

    with ThreadPoolExecutor(WORKERS) as pool:
        for r, path in zip(todo, pool.map(get, todo), strict=True):
            tbl = PARSERS[r["table"]](path)
            out = out_path(r["table"], r["lang"])
            out.parent.mkdir(parents=True, exist_ok=True)
            pq.write_table(tbl, out, compression="zstd")
            print(f"{r['lang']} {r['table']}: {tbl.num_rows:,} rows", flush=True)


if __name__ == "__main__":
    main()
