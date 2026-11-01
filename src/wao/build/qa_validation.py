"""P12: validation set for the quick-answer label, and its metrics.

draw   100 sample articles each from en, de, ja (seed 12), stratified by Wikidata coarse type:
       allocation proportional to sqrt(stratum size), at least 2 per type, so rare types appear.
       `val_weight` = P06 weight x (type size / type draws) undoes the oversampling.
       Each row gets the Wikidata label and description in English and in the edition's
       language (so a reader of English can audit de/ja rows), and a link. The file carries
       no rule output and no features: labels are assigned blind to the rule (frozen in v1
       before the draw). 100 rows (seed 13) are marked `in_audit` for the user's blind audit.
metrics  rule vs labels: precision, recall, F1 for quick-answer (unweighted and weighted),
       confusion by type; Claude vs user: Cohen's kappa.

draw2  (rule v3; drawn and labelled by Claude, but the user declined the round, so unused) a
       fresh set of 60 articles not in the first 300 (seed 14): 10 core-quick and 10
       core-long per edition, shuffled, tier not shown; labelled blind by the user (and Claude).
metrics2  purity of the v3 core tiers against the second-round labels, and kappa.

Files: data/reference/quick_answer_labels.csv (all 300, labels filled in by hand)
       data/reference/quick_answer_audit.csv (the 100 audit rows, without Claude's labels)
       data/reference/quick_answer_labels2.csv, quick_answer_audit2.csv (second round)
Run: python -m wao.build.qa_validation draw | metrics | draw2 | metrics2
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from wao import config, http
from wao.build.quick_answer import out_path as rule_path

LANGS = ("en", "de", "ja")
N_PER_LANG, SEED, AUDIT_N, AUDIT_SEED = 100, 12, 100, 13
REF = config.REFERENCE_DIR
LABELS, AUDIT = REF / "quick_answer_labels.csv", REF / "quick_answer_audit.csv"
LABELS2, AUDIT2 = REF / "quick_answer_labels2.csv", REF / "quick_answer_audit2.csv"
N2_PER_TIER, SEED2 = 10, 14


def allocate(sizes: pd.Series, n: int, floor: int = 2) -> pd.Series:
    w = np.sqrt(sizes)
    a = np.maximum(floor, np.floor(n * w / w.sum())).astype(int).clip(upper=sizes)
    while a.sum() < n:  # top up the largest remainders
        gap = (n * w / w.sum() - a).where(a < sizes, -np.inf)
        a[gap.idxmax()] += 1
    while a.sum() > n:
        a[(a - floor).where(a > floor, -1).idxmax()] -= 1
    return a


def wikidata(qids: list[str]) -> dict[str, dict]:
    api = "https://www.wikidata.org/w/api.php"
    s = http.session("wikidata_api", min_interval=0.35)
    http.login(s, api)
    out = {}
    for i in range(0, len(qids), 50):
        j = s.get(api, params={"action": "wbgetentities", "ids": "|".join(qids[i : i + 50]),
                               "props": "labels|descriptions", "languages": "en|de|ja",
                               "format": "json"}, timeout=60).json()  # fmt: skip
        out |= j.get("entities", {})
    return out


def draw() -> pd.DataFrame:
    cols = ["lang", "page_id", "title", "qid", "coarse_type", "weight"]
    s = pd.read_parquet(config.PANEL_DIR / "sample.parquet", columns=cols)
    rows = []
    for lang in LANGS:
        g = s[s.lang == lang]
        sizes = g.coarse_type.value_counts()
        alloc = allocate(sizes, N_PER_LANG)
        for t, k in alloc.items():
            pick = g[g.coarse_type == t].sample(k, random_state=SEED)
            rows.append(pick.assign(val_weight=pick.weight * sizes[t] / k))
    d = pd.concat(rows, ignore_index=True)
    ent = wikidata(sorted(d.qid.dropna().unique()))

    def text(q, kind, lang):
        return ent.get(q, {}).get(kind, {}).get(lang, {}).get("value", "") if q else ""

    d["en_label"] = [text(q, "labels", "en") for q in d.qid]
    d["en_description"] = [text(q, "descriptions", "en") for q in d.qid]
    d["local_description"] = [text(q, "descriptions", lg) if lg != "en" else ""
                              for q, lg in zip(d.qid, d.lang, strict=True)]  # fmt: skip
    d["url"] = "https://" + d.lang + ".wikipedia.org/wiki/" + d.title
    d = d.sample(frac=1, random_state=SEED).reset_index(drop=True)  # hide the type order
    d.insert(0, "row", range(1, len(d) + 1))
    d["in_audit"] = d.index.isin(d.sample(AUDIT_N, random_state=AUDIT_SEED).index)
    for c in ("claude_label", "claude_conf", "claude_reason", "user_label"):
        d[c] = ""
    cols = ["row", "lang", "page_id", "title", "qid", "en_label", "en_description",
            "local_description", "url", "val_weight", "in_audit", "claude_label", "claude_conf",
            "claude_reason", "user_label"]  # fmt: skip
    return d[cols]


def _describe(d: pd.DataFrame) -> pd.DataFrame:
    ent = wikidata(sorted(d.qid.dropna().unique()))

    def text(q, kind, lang):
        return ent.get(q, {}).get(kind, {}).get(lang, {}).get("value", "") if q else ""

    d["en_label"] = [text(q, "labels", "en") for q in d.qid]
    d["en_description"] = [text(q, "descriptions", "en") for q in d.qid]
    d["local_description"] = [text(q, "descriptions", lg) if lg != "en" else ""
                              for q, lg in zip(d.qid, d.lang, strict=True)]  # fmt: skip
    d["url"] = "https://" + d.lang + ".wikipedia.org/wiki/" + d.title
    return d


def draw2() -> pd.DataFrame:
    s = pd.read_parquet(config.PANEL_DIR / "sample.parquet", columns=["lang", "page_id", "title",
                                                                      "qid"])  # fmt: skip
    tiers = pd.read_parquet(rule_path(), columns=["lang", "page_id", "qa_tier"])
    used = pd.read_csv(LABELS, usecols=["lang", "page_id"])
    s = s.merge(tiers, on=["lang", "page_id"]).merge(used, how="left", indicator=True)
    s = s[s._merge == "left_only"]
    picks = [s[(s.lang == lg) & (s.qa_tier == t)].sample(N2_PER_TIER, random_state=SEED2)
             for lg in LANGS for t in ("quick", "long")]  # fmt: skip
    d = _describe(pd.concat(picks).drop(columns=["qa_tier", "_merge"]))
    d = d.sample(frac=1, random_state=SEED2).reset_index(drop=True)
    d.insert(0, "row", range(1, len(d) + 1))
    for c in ("claude_label", "claude_conf", "user_label"):
        d[c] = ""
    return d[["row", "lang", "page_id", "title", "qid", "en_label", "en_description",
              "local_description", "url", "claude_label", "claude_conf", "user_label"]]  # fmt: skip


def metrics2() -> dict[str, pd.DataFrame]:
    d = pd.read_csv(LABELS2).merge(pd.read_parquet(rule_path()), on=["lang", "page_id"])
    u = pd.read_csv(AUDIT2)[["row", "user_label"]]
    d = d.drop(columns="user_label").merge(u, on="row")
    rows = []
    for who in ("user_label", "claude_label"):
        x = d[pd.to_numeric(d[who], errors="coerce").notna()]
        for scope, g in [("all", x)] + [(lg, x[x.lang == lg]) for lg in LANGS]:
            q, lo = g[g.qa_tier == "quick"], g[g.qa_tier == "long"]
            rows.append({"labels": who.removesuffix("_label"), "scope": scope,
                         "quick_purity": q[who].astype(int).mean(),
                         "long_purity": 1 - lo[who].astype(int).mean(),
                         "n_quick": len(q), "n_long": len(lo)})  # fmt: skip
    res = {"metrics2": pd.DataFrame(rows).round(3)}
    both = d[pd.to_numeric(d.user_label, errors="coerce").notna()
             & pd.to_numeric(d.claude_label, errors="coerce").notna()]  # fmt: skip
    if len(both):
        res["agreement2"] = pd.DataFrame([{
            "n": len(both), "agree": (both.claude_label.astype(int)
                                      == both.user_label.astype(int)).mean(),
            "kappa": kappa(both.claude_label, both.user_label)}]).round(3)  # fmt: skip
    return res


def write_audit(d: pd.DataFrame) -> None:
    a = d[d.in_audit][["row", "lang", "title", "en_label", "en_description", "local_description",
                       "url", "user_label"]]  # fmt: skip
    a.to_csv(AUDIT, index=False)


def kappa(a: pd.Series, b: pd.Series) -> float:
    a, b = a.astype(int), b.astype(int)
    po = (a == b).mean()
    pe = a.mean() * b.mean() + (1 - a.mean()) * (1 - b.mean())
    return (po - pe) / (1 - pe)


def scores(y: pd.Series, r: pd.Series, w: pd.Series | None = None) -> dict:
    w = pd.Series(1.0, index=y.index) if w is None else w
    tp = (w * ((r == 1) & (y == 1))).sum()
    fp = (w * ((r == 1) & (y == 0))).sum()
    fn = (w * ((r == 0) & (y == 1))).sum()
    p, rec = tp / (tp + fp), tp / (tp + fn)
    acc = (w * (r == y)).sum() / w.sum()
    return {"precision": p, "recall": rec, "f1": 2 * p * rec / (p + rec), "accuracy": acc,
            "n": int(len(y)), "share_qa_labels": float((w * y).sum() / w.sum())}  # fmt: skip


def metrics() -> dict[str, pd.DataFrame]:
    d = pd.read_csv(LABELS)
    r = pd.read_parquet(rule_path())
    t = pd.read_parquet(config.PANEL_DIR / "sample.parquet", columns=["lang", "page_id",
                                                                      "coarse_type"])  # fmt: skip
    d = d.merge(r, on=["lang", "page_id"]).merge(t, on=["lang", "page_id"])
    d = d[d.qa_rule.notna()]
    out = []
    for who, col in (("claude", "claude_label"), ("user", "user_label")):
        x = d[pd.to_numeric(d[col], errors="coerce").notna()]
        if x.empty:
            continue
        y, rr = x[col].astype(int), x.qa_rule.astype(int)
        for scope, m in [("all", x.index)] + [(lg, x.index[x.lang == lg]) for lg in LANGS]:
            if len(m) == 0:
                continue
            out.append({"labels": who, "scope": scope, "weighted": False,
                        **scores(y[m], rr[m])})  # fmt: skip
            out.append({"labels": who, "scope": scope, "weighted": True,
                        **scores(y[m], rr[m], x.val_weight[m])})  # fmt: skip
    res = {"metrics": pd.DataFrame(out).round(3)}
    both = d[pd.to_numeric(d.user_label, errors="coerce").notna()]
    if len(both):
        res["agreement"] = pd.DataFrame([{
            "n": len(both), "agree": (both.claude_label.astype(int)
                                      == both.user_label.astype(int)).mean(),
            "kappa": kappa(both.claude_label, both.user_label)}]).round(3)  # fmt: skip
    lab = "user_label" if len(both) else "claude_label"
    z = d[pd.to_numeric(d[lab], errors="coerce").notna()]
    res["confusion_by_type"] = (z.assign(label=z[lab].astype(int), rule=z.qa_rule.astype(int))
                                .groupby(["coarse_type", "rule", "label"]).size()
                                .unstack(["rule", "label"], fill_value=0))  # fmt: skip
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["draw", "metrics", "draw2", "metrics2"])
    a = ap.parse_args()
    if a.step == "draw":
        if LABELS.exists():
            raise SystemExit(f"{LABELS} exists: the draw is done once")
        d = draw()
        d.to_csv(LABELS, index=False)
        write_audit(d)
        print(d.groupby("lang").size().to_dict(), int(d.in_audit.sum()), "in audit")
    elif a.step == "draw2":
        if LABELS2.exists():
            raise SystemExit(f"{LABELS2} exists: the draw is done once")
        d = draw2()
        d.to_csv(LABELS2, index=False)
        d[["row", "lang", "title", "en_label", "en_description", "local_description", "url",
           "user_label"]].to_csv(AUDIT2, index=False)  # fmt: skip
        print(d.groupby("lang").size().to_dict())
    else:
        for name, df in (metrics() if a.step == "metrics" else metrics2()).items():
            df.to_csv(config.REPORT_DIR / "qa" / f"p12_{name}.csv")
            print(name, df, sep="\n")


if __name__ == "__main__":
    main()
