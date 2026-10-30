"""Wikidata item types: truthy P31 (instance of) via SPARQL, rolled up to coarse classes via P279.

1. P31 for a list of QIDs: `VALUES ?item {…} ?item wdt:P31 ?class` in batches (wdt = truthy, the
   same best-rank rule as wao.ingest.wikidata).
2. The P279 (subclass of) graph above those classes, walked breadth-first with the same batching
   until no new classes appear. Every response is cached on disk.
3. Each class gets the set of coarse roots it reaches (cycle-safe); an item's coarse type is the
   FIRST entry of COARSE reached by any of its P31 classes. Order matters: Wikidata's upper
   ontology makes e.g. cities reach "organization" and many things reach "occurrence", so specific
   classes come first. Items with no P31 are usually concepts modelled as classes (e.g. "stele",
   "power series"); they are rolled up through their own P279. Items with neither are `no_p31`;
   anything that matches nothing is `other`. Articles without a QID get `no_qid` downstream.

Outputs (PARQUET_DIR/wikidata/): p31.parquet (qid, class), p279.parquet (class, parent).
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from wao import config, http

SPARQL = "https://query.wikidata.org/sparql"
BATCH = 300  # QIDs per query; keeps GET URLs well under 8 kB

COARSE: list[tuple[str, tuple[str, ...]]] = [
    ("human", ("Q5",)),
    ("list", ("Q13406463",)),  # Wikimedia list article
    ("taxon", ("Q16521",)),
    # element, compound, chemical entity, type of chemical entity
    ("chemical", ("Q11344", "Q11173", "Q43460564", "Q113145171")),
    # disease, medication, type of disease, class of anatomical entity
    ("health", ("Q12136", "Q12140", "Q112193867", "Q112826905")),
    ("film", ("Q11424",)),
    ("tv", ("Q5398426", "Q15416", "Q3464665")),  # TV series, TV program, TV season
    # album, musical work, single, song, EP
    ("music", ("Q482994", "Q105543609", "Q134556", "Q7366", "Q169930")),
    ("video_game", ("Q7889",)),
    ("written_work", ("Q47461344", "Q7725634")),  # written work, literary work
    ("sports_event", ("Q27020041", "Q16510064", "Q13406554")),  # season, event, competition
    ("country", ("Q6256", "Q3624078")),  # country, sovereign state
    ("settlement", ("Q486972",)),  # human settlement
    ("admin_region", ("Q56061",)),  # administrative territorial entity
    ("astronomical", ("Q6999",)),
    # natural geographic object, body of water, mountain, island, river
    ("nature_place", ("Q35145263", "Q15324", "Q8502", "Q23442", "Q4022")),
    # architectural structure, building, road, station
    ("structure", ("Q811979", "Q41176", "Q83620", "Q12819564")),
    ("organization", ("Q43229",)),
    ("event", ("Q1190554", "Q1656682")),  # occurrence, event
]
TYPES = [name for name, _ in COARSE] + ["other", "no_p31", "no_qid"]
ROOT_TO_TYPE = {q: name for name, qs in COARSE for q in qs}
PRIORITY = {name: i for i, name in enumerate(TYPES)}


def _session():
    return http.session("wdqs", min_interval=1.0)


def _query(s, q: str) -> list[dict]:
    r = s.get(SPARQL, params={"query": q, "format": "json"}, timeout=120)
    r.raise_for_status()
    return r.json()["results"]["bindings"]


def _pairs(s, qids: list[str], prop: str) -> list[tuple[str, str]]:
    out = []
    for i in range(0, len(qids), BATCH):
        vals = " ".join(f"wd:{q}" for q in sorted(qids[i : i + BATCH]))
        q = f"SELECT ?a ?b WHERE {{ VALUES ?a {{ {vals} }} ?a wdt:{prop} ?b }}"
        for b in _query(s, q):
            a, v = b["a"]["value"].rsplit("/", 1)[1], b["b"]["value"].rsplit("/", 1)[1]
            if v.startswith("Q"):
                out.append((a, v))
        if (i // BATCH) % 100 == 99:
            print(f"  {prop}: {i + BATCH:,}/{len(qids):,}", flush=True)
    return out


def fetch_p31(qids: Iterable[str]) -> pd.DataFrame:
    qids = sorted(set(qids))
    return pd.DataFrame(_pairs(_session(), qids, "P31"), columns=["qid", "class"])


def fetch_p279(classes: Iterable[str]) -> pd.DataFrame:
    s, seen, frontier, edges = _session(), set(), set(classes), []
    while frontier:
        seen |= frontier
        new = _pairs(s, sorted(frontier), "P279")
        edges += new
        frontier = {p for _, p in new} - seen
    return pd.DataFrame(edges, columns=["class", "parent"]).drop_duplicates()


def class_roots(p279: pd.DataFrame) -> dict[str, frozenset[str]]:
    """class -> coarse type names it reaches (itself included), handling cycles."""
    parents: dict[str, list[str]] = {}
    for c, p in p279.itertuples(index=False):
        parents.setdefault(c, []).append(p)
    memo: dict[str, frozenset[str]] = {}

    def reach(c: str) -> frozenset[str]:
        # iterative DFS over the ancestors of c
        if c in memo:
            return memo[c]
        stack, seen, hits = [c], {c}, set()
        while stack:
            x = stack.pop()
            if x in ROOT_TO_TYPE:
                hits.add(ROOT_TO_TYPE[x])
            if x in memo:
                hits |= memo[x]
                continue
            for p in parents.get(x, ()):
                if p not in seen:
                    seen.add(p)
                    stack.append(p)
        memo[c] = frozenset(hits)
        return memo[c]

    return {c: reach(c) for c in set(p279["class"]) | set(p279["parent"]) | set(ROOT_TO_TYPE)}


def coarse_types(qids: Iterable[str], p31: pd.DataFrame, p279: pd.DataFrame) -> pd.Series:
    roots = class_roots(p279)
    hits: dict[str, set[str]] = {}
    for q, c in p31.itertuples(index=False):
        hits.setdefault(q, set()).update(roots.get(c, frozenset({ROOT_TO_TYPE.get(c)}) - {None}))
    as_class = set(p279["class"])
    out = {}
    for q in qids:
        if q not in hits and q in as_class:  # no P31: use the item's own P279
            hits[q] = set(roots.get(q, frozenset()))
        if q not in hits:
            out[q] = "no_p31"
        else:
            out[q] = min(hits[q], key=PRIORITY.get) if hits[q] else "other"
    return pd.Series(out, name="coarse_type")


def lookup(qids: Iterable[str]) -> pd.DataFrame:
    """Fetch (cached) and roll up; also saves p31/p279 Parquet. Returns qid, coarse_type."""
    qids = sorted(set(qids))
    p31 = fetch_p31(qids)
    no_p31 = sorted(set(qids) - set(p31["qid"]))
    own = pd.DataFrame(_pairs(_session(), no_p31, "P279"), columns=["class", "parent"])
    p279 = pd.concat([own, fetch_p279(set(p31["class"]) | set(own["parent"]))])
    p279 = p279.drop_duplicates(ignore_index=True)
    d = config.PARQUET_DIR / "wikidata"
    d.mkdir(parents=True, exist_ok=True)
    p31.to_parquet(d / "p31.parquet")
    p279.to_parquet(d / "p279.parquet")
    return coarse_types(qids, p31, p279).rename_axis("qid").reset_index()
