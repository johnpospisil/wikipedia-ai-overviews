"""Wikidata entity parsing (wbgetentities JSON): QID, truthy P31 (instance of), sitelinks.

Truthy = Wikidata's 'best rank' rule: preferred statements if any exist, otherwise normal ones;
deprecated statements and novalue/somevalue snaks are ignored.
"""

from __future__ import annotations

WBGETENTITIES = "https://www.wikidata.org/w/api.php"
BATCH = 50  # API limit for ids per call


def _truthy_items(statements: list[dict]) -> list[str]:
    ranked = [s for s in statements if s.get("rank") != "deprecated"]
    preferred = [s for s in ranked if s.get("rank") == "preferred"]
    out = []
    for s in preferred or ranked:
        snak = s.get("mainsnak", {})
        if snak.get("snaktype") != "value":
            continue
        out.append(snak["datavalue"]["value"]["id"])
    return out


def site_to_wiki(site: str) -> str | None:
    """'enwiki' -> 'en', 'zh_yuewiki' -> 'zh-yue'; non-Wikipedia sites -> None."""
    if not site.endswith("wiki") or site in {
        "commonswiki",
        "specieswiki",
        "metawiki",
        "wikidatawiki",
        "mediawikiwiki",
        "sourceswiki",
    }:
        return None
    return site[: -len("wiki")].replace("_", "-")


def parse_entity(e: dict, wikis: set[str]) -> dict | None:
    if "missing" in e or e.get("type") not in (None, "item"):
        return None
    out = {
        "qid": e["id"],
        "p31": _truthy_items(e.get("claims", {}).get("P31", [])),
        "sitelinks": {},
    }
    for site, link in e.get("sitelinks", {}).items():
        w = site_to_wiki(site)
        if w in wikis:
            out["sitelinks"][w] = link["title"]
    if "redirects" in e:
        out["redirected_from"] = e["redirects"]["from"]
    return out


def parse_response(resp: dict, wikis: set[str]) -> list[dict]:
    # A single malformed id makes the API fail the whole batch ('no-such-entity'); never treat
    # that as "no entities".
    if "error" in resp:
        raise ValueError(f"wbgetentities error: {resp['error'].get('code')}")
    out = []
    for e in resp.get("entities", {}).values():
        p = parse_entity(e, wikis)
        if p is not None:
            out.append(p)
    return out
