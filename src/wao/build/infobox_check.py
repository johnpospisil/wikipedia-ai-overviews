"""P08 check: does `has_infobox` (from template names) agree with the rendered page?

For 20 flagged and 20 unflagged articles per edition (random, seed 8), render the 2023-12-31
revision (action=parse&oldid=...; templates expand with their current code) and look for an
element with CSS class `infobox` (the class infobox templates share across editions). Writes
report/qa/p08_infobox_check.csv (one row per article) and prints precision/recall by edition,
weighting the two halves back to each edition's flagged share.

Run: python -m wao.build.infobox_check
"""

from __future__ import annotations

import re

import pandas as pd

from wao import config, http
from wao.build.features import out_path as features_path

N = 20
CLASS = re.compile(r'class="[^"]*\binfobox\b', re.I)


def out_path():
    return config.REPORT_DIR / "qa" / "p08_infobox_check.csv"


def rendered_infobox(s, lang: str, rev_id: int) -> bool | None:
    j = s.get(f"https://{lang}.wikipedia.org/w/api.php",
              params={"action": "parse", "oldid": rev_id, "prop": "text", "format": "json",
                      "formatversion": 2, "disablelimitreport": 1}, timeout=120).json()  # fmt: skip
    if "error" in j:
        return None
    return bool(CLASS.search(j["parse"]["text"]))


def main() -> None:
    f = pd.read_parquet(features_path())
    f = f[(f.status == "ok") & ~f.is_redirect.fillna(False)]
    rows = []
    for lang, g in f.groupby("lang"):
        s = http.session(f"mw_parse_{lang}", min_interval=0.35)
        http.login(s, f"https://{lang}.wikipedia.org/w/api.php")
        pick = pd.concat([g[g.has_infobox].sample(N, random_state=8),
                          g[~g.has_infobox].sample(N, random_state=8)])  # fmt: skip
        share = g.has_infobox.mean()
        for r in pick.itertuples():
            rows.append({"lang": lang, "page_id": r.page_id, "rev_id": r.rev_id,
                         "coarse_type": r.coarse_type, "flag": bool(r.has_infobox),
                         "html": rendered_infobox(s, lang, int(r.rev_id)),
                         "w": share / N if r.has_infobox else (1 - share) / N})  # fmt: skip
    df = pd.DataFrame(rows)
    out_path().parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path(), index=False)
    d = df.dropna(subset=["html"])
    tp = d[d.flag & d.html].groupby("lang").w.sum()
    summary = pd.DataFrame({
        "precision": d[d.flag].groupby("lang").html.mean(),
        "recall": tp / d[d.html].groupby("lang").w.sum(),
        "agree": d.assign(a=d.flag == d.html).groupby("lang").apply(
            lambda x: (x.a * x.w).sum() / x.w.sum(), include_groups=False),
    }).round(3)  # fmt: skip
    print(summary)


if __name__ == "__main__":
    main()
