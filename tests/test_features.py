"""P08 feature logic: infobox flags, top topics, title batching, batched revision fetch."""

from __future__ import annotations

import pandas as pd

from wao.build.features import infobox_flags, top_topics
from wao.ingest import revisions
from wao.ingest.infobox_templates import _batches


def test_infobox_flags_list_rule_and_missing():
    rev = pd.DataFrame(
        {
            "lang": ["de", "de", "pl", "it"],
            "templates": [["Personendaten"], ["Infobox Ort"], ["Miasto infobox"], None],
        }
    )
    boxes = pd.DataFrame({"lang": ["it"], "template": ["Divisione amministrativa"]})
    flags = infobox_flags(rev, boxes).tolist()
    assert flags[:3] == [False, True, True]
    assert pd.isna(flags[3])


def test_infobox_flags_from_wikidata_list():
    rev = pd.DataFrame({"lang": ["ru"], "templates": [["Персона", "Примечания"]]})
    boxes = pd.DataFrame({"lang": ["ru"], "template": ["Персона"]})
    assert infobox_flags(rev, boxes).tolist() == [True]


def test_top_topics_picks_highest_and_flags_confidence():
    t = pd.DataFrame(
        {
            "lang": ["en", "en", "en"],
            "page_id": [1, 1, 2],
            "topic": ["STEM.Physics", "Culture.Media.Films", "Geography.Regions.Asia"],
            "score": [0.3, 0.9, 0.2],
        }
    )
    top = top_topics(t).set_index("page_id")
    assert top.loc[1, "topic"] == "Culture.Media.Films"
    assert top.loc[1, "topic_group"] == "Culture"
    assert bool(top.loc[1, "topic_confident"]) and not bool(top.loc[2, "topic_confident"])


def test_batches_respect_count_and_url_length():
    assert [len(b) for b in _batches([f"T{i}" for i in range(120)])] == [50, 50, 20]
    long = ["جعبه اطلاعات " * 5] * 50  # percent-encoding makes each ~300 chars
    batches = list(_batches(long, max_url=2000))
    assert sum(map(len, batches)) == 50 and max(map(len, batches)) < 50


class FakeSession:
    """Returns at most 2 revisions per call, as the API does when a response is too large."""

    def __init__(self, texts: dict[int, str | None]):
        self.texts, self.calls = texts, []

    def get(self, url, params, timeout):
        ids = [int(x) for x in params["revids"].split("|")]
        self.calls.append(ids)
        revs, bad = [], {}
        for r in ids:
            if r not in self.texts:
                bad[str(r)] = {"revid": r}
            elif len(revs) < 2:
                main = {"texthidden": True} if self.texts[r] is None else {"content": self.texts[r]}
                revs.append({"revid": r, "slots": {"main": main}})
        body = {"query": {"pages": [{"revisions": revs}]}}
        if bad:
            body["query"]["badrevids"] = bad
        return type("R", (), {"json": lambda self: body})()


def test_fetch_retries_left_out_revids_in_smaller_batches():
    texts = {i: f"text {i}" for i in range(1, 11)}
    texts[5] = None
    s = FakeSession(texts)
    got = revisions.fetch(s, "en", [*range(1, 11), 99])
    assert got[99] == ("badrevid", None)
    assert got[5] == ("text_hidden", None)
    assert all(got[i] == ("ok", f"text {i}") for i in range(1, 11) if i != 5)
    assert len(s.calls) > 1 and max(map(len, s.calls[1:])) < 11
