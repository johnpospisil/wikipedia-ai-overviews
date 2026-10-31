"""Which templates are infoboxes, per edition (wikitext names differ by language).

A template counts as an infobox if any of:
  1. it is sitelinked from a Wikidata item that is an instance of Q19887878 (Wikimedia infobox
     template), e.g. it: "Divisione amministrativa", ru: "Персона";
  2. its name starts with one of the edition's infobox prefixes below, or ends in " infobox"
     (pl names them "Miasto infobox");
  3. it is a redirect to a template in 1 or 2 (current redirects, via the API).
Rule 2 is applied again at match time (wao.build.features.is_infobox), so templates that no
longer exist still count. Checked against rendered HTML in P08 (report/qa/p08_infobox_check.csv).

Output: PARQUET_DIR/features/infobox_templates.parquet  lang, template, source
Run: python -m wao.ingest.infobox_templates
"""

from __future__ import annotations

from urllib.parse import unquote

import pandas as pd

from wao import config, http
from wao.build.wikitext import norm_template
from wao.ingest.revisions import ns_prefixes

PREFIXES: dict[str, tuple[str, ...]] = {
    "en": ("Infobox", "Taxobox", "Speciesbox", "Automatic taxobox", "Subspeciesbox",
           "Infraspeciesbox", "Chembox", "Drugbox", "Geobox"),
    "de": ("Infobox", "Taxobox"),
    "fr": ("Infobox", "Taxobox début"),
    "es": ("Ficha", "Infobox", "Taxobox"),
    "it": ("Infobox", "Tassobox", "Sinottico"),
    "pl": ("Infobox", "Takson infobox"),
    "pt": ("Info/", "Infobox", "Taxocaixa"),
    "ja": ("Infobox", "基礎情報", "生物分類表"),
    "ru": ("Карточка", "Таксон", "Infobox"),
    "zh": ("Infobox", "Taxobox"),
    "fa": ("جعبه اطلاعات", "Infobox", "Taxobox"),
}  # fmt: skip
SUFFIX = " infobox"
SPARQL = "https://query.wikidata.org/sparql"


def by_rule(lang: str, name: str) -> bool:
    low = name.lower()
    return low.startswith(tuple(p.lower() for p in PREFIXES[lang])) or low.endswith(SUFFIX)


def _api(s, lang: str, params: dict):
    base = {"action": "query", "format": "json", "formatversion": 2}
    cont: dict = {}
    while True:
        j = s.get(f"https://{lang}.wikipedia.org/w/api.php", params=base | params | cont,
                  timeout=60).json()  # fmt: skip
        yield j.get("query", {})
        if "continue" not in j:
            return
        cont = j["continue"]


def wikidata_templates(lang: str) -> list[str]:
    q = f"""SELECT ?a WHERE {{ ?i wdt:P31 wd:Q19887878 . ?a schema:about ?i ;
            schema:isPartOf <https://{lang}.wikipedia.org/> }}"""
    s = http.session("wdqs", min_interval=1.0)
    rows = s.get(SPARQL, params={"query": q, "format": "json"}, timeout=120).json()
    return [unquote(b["a"]["value"].rsplit("/wiki/", 1)[1]) for b in rows["results"]["bindings"]]


def build_lang(lang: str) -> pd.DataFrame:
    s = http.session(f"mw_meta_{lang}", min_interval=0.05)  # not mw_<lang>: in use by P08 fetch
    pre = ns_prefixes(s, lang)
    rows = [(n, "wikidata") for n in (norm_template(t, pre) for t in wikidata_templates(lang))]
    for p in PREFIXES[lang]:
        for q in _api(s, lang, {"list": "allpages", "apnamespace": 10, "apprefix": p,
                                "apfilterredir": "nonredirects", "aplimit": "max"}):  # fmt: skip
            rows += [(norm_template(x["title"], pre), "prefix") for x in q.get("allpages", [])]
    rows = [(n, src) for n, src in rows if "/" not in n]  # drop /doc, /sandbox subpages
    targets = sorted({n for n, _ in rows})
    for i in range(0, len(targets), 50):
        titles = "|".join(f"Template:{t}" for t in targets[i : i + 50])
        for q in _api(s, lang, {"titles": titles, "prop": "redirects", "rdnamespace": 10,
                                "rdlimit": "max"}):  # fmt: skip
            for page in q.get("pages", []):
                rows += [(norm_template(r["title"], pre), "redirect")
                         for r in page.get("redirects", [])]  # fmt: skip
    df = pd.DataFrame(rows, columns=["template", "source"]).drop_duplicates("template")
    return df.assign(lang=lang)[["lang", "template", "source"]]


def out_path():
    return config.PARQUET_DIR / "features" / "infobox_templates.parquet"


def main() -> None:
    df = pd.concat([build_lang(lang) for lang in config.LANGS], ignore_index=True)
    out_path().parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path(), index=False)
    print(df.groupby(["lang", "source"]).size().unstack(fill_value=0), flush=True)


if __name__ == "__main__":
    main()
