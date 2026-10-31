"""Article features from one revision's wikitext (no text is stored, only these numbers).

  bytes        UTF-8 length of the wikitext
  prose_chars  characters of readable text (mwparserfromhell strip_code: templates, tables,
               refs, files and markup removed; links reduced to their label)
  lead_chars   the same for the text before the first heading
  n_sections   level-2 headings (== x ==); n_headings counts all levels
  n_refs       <ref> tags with content (named re-uses <ref name=x/> are not new references)
  templates    normalised names of every template used (namespace prefix removed, first letter
               upper-cased, underscores as spaces; magic words like DEFAULTSORT: and
               cross-namespace transclusions dropped); the infobox flag is derived from these in
               wao.build.features so the template lists can change without re-fetching
  is_redirect  the revision is a redirect

Character counts are comparable within an edition, not across scripts (zh/ja vs Latin).
"""

from __future__ import annotations

import re

import mwparserfromhell

HEADING = re.compile(r"^(={2,6})[^=\n].*?\1[ \t]*$", re.M)
REF_OPEN = re.compile(r"<ref\b[^>]*?(/?)>", re.I)
REDIRECT = re.compile(
    r"^\s*#\s*(redirect|weiterleitung|redirection|redirección|rinvia|"
    r"przekieruj|redirecionamento|転送|перенаправление|重定向|تغییرمسیر)",
    re.I,
)
COMMENT = re.compile(r"<!--.*?-->", re.S)


def norm_template(name: str, ns_prefixes: tuple[str, ...] = ()) -> str:
    n = COMMENT.sub("", name).replace("_", " ").strip()
    n = re.sub(r"\s+", " ", n)
    if ":" in n:
        pre, rest = n.split(":", 1)
        if pre.strip().lower() in ns_prefixes:
            n = rest.strip()
    return n[:1].upper() + n[1:]


def features(text: str, ns_prefixes: tuple[str, ...] = ("template",)) -> dict:
    heads = [m for m in HEADING.finditer(text)]
    lead = text[: heads[0].start()] if heads else text
    code = mwparserfromhell.parse(text)
    names = set()
    for t in code.filter_templates():
        n = norm_template(str(t.name), ns_prefixes)
        if n and not n.startswith("#") and ":" not in n:  # magic words, other namespaces
            names.add(n)
    return {
        "bytes": len(text.encode("utf-8")),
        "prose_chars": len(_plain(code)),
        "lead_chars": len(_plain(mwparserfromhell.parse(lead))),
        "n_sections": sum(len(m.group(1)) == 2 for m in heads),
        "n_headings": len(heads),
        "n_refs": sum(not m.group(1) for m in REF_OPEN.finditer(text)),
        "templates": sorted(names),
        "is_redirect": bool(REDIRECT.match(text)),
    }


def _plain(code) -> str:
    s = code.strip_code(normalize=True, collapse=True)
    return re.sub(r"\s+", " ", s).strip()
