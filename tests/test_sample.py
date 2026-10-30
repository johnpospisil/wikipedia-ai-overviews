import numpy as np
import pandas as pd

from wao import config
from wao.build import sample as sm


def _frame(seed=0, n_per_lang=4000, n_items=1500):
    rng = np.random.default_rng(seed)
    rows = []
    for lang in config.LANGS:
        qids = [f"Q{i}" for i in range(n_items)]  # items 0..1499 exist in every edition
        qids += [f"Q{lang}{i}" for i in range(n_per_lang - n_items - 200)] + [None] * 200
        views = rng.lognormal(5, 2, len(qids)).astype(int) + 1
        rows.append(
            pd.DataFrame(
                {
                    "lang": lang,
                    "page_id": np.arange(len(qids)),
                    "qid": qids,
                    "title": "t",
                    "views_2023": views,
                    "months_2023": 12,
                }
            )
        )
    f = pd.concat(rows, ignore_index=True)
    f["decile"] = (
        f.groupby("lang")
        .views_2023.rank(method="first")
        .pipe(lambda r: (r - 1) * 10 // f.groupby("lang").lang.transform("size") + 1)
        .astype(int)
    )
    return f


def test_draw_weights_sum_to_frame_and_concept_items_complete(monkeypatch):
    monkeypatch.setattr(sm, "PHASE1", 200)
    monkeypatch.setattr(sm, "LANG_TARGET", 600)
    monkeypatch.setattr(sm, "FLOOR", 10)
    monkeypatch.setattr(sm, "CONCEPT_ITEMS", 100)
    monkeypatch.setattr(sm, "CONCEPT_FLOOR", 3)
    frame = _frame()
    rare = {f"Q{i}" for i in range(0, 1500, 50)}  # a small type, 2% of items
    types = pd.Series({q: ("rare" if q in rare else "common") for q in frame.qid.dropna()})
    s, p1, items = sm.draw(frame, types)

    assert s.duplicated(["lang", "page_id"]).sum() == 0
    assert ((s.pi > 0) & (s.pi <= 1)).all()
    # concept items: every selected item has an article in all 11 editions
    c = s[s.in_concept_panel].groupby("qid").lang.nunique()
    assert (c == len(config.LANGS)).all() and 80 <= len(c) <= 120
    # language sample about LANG_TARGET per edition; rare type oversampled
    a = s[s.in_lang_sample]
    assert a.groupby("lang").size().between(550, 650).all()
    assert (a.coarse_type == "rare").mean() > 2 * (frame.qid.isin(rare)).mean()
    # Horvitz–Thompson: weights estimate the frame size per edition (within sampling error)
    ratio = s.groupby("lang").weight.sum() / frame.groupby("lang").size()
    assert ratio.between(0.85, 1.15).all(), ratio


def test_allocate_hits_target_with_floor():
    n1 = pd.Series([1000, 500, 20, 5])
    n2 = sm.allocate(n1, 300, 10)
    assert abs(n2.sum() - 300) <= 3 and n2.iloc[3] == 5 and n2.iloc[2] == 10
