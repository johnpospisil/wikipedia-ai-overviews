import pandas as pd

from wao.ingest import wikidata_types as wt


def test_coarse_types_priority_cycles_and_missing():
    p279 = pd.DataFrame(
        [
            ("Q515", "Q486972"),  # city -> human settlement
            ("Q515", "Qorg"),  # city -> ... -> organization (upper-ontology noise)
            ("Qorg", "Q43229"),
            ("Qa", "Qb"),  # cycle with no root
            ("Qb", "Qa"),
            ("Qwar", "Q1190554"),
            ("Qstele", "Q811979"),  # an item with no P31, only P279
        ],
        columns=["class", "parent"],
    )
    p31 = pd.DataFrame(
        [("Q90", "Q515"), ("Q937", "Q5"), ("Q937", "Qorg"), ("Qx", "Qa"), ("Q362", "Qwar")],
        columns=["qid", "class"],
    )
    t = wt.coarse_types(["Q90", "Q937", "Qx", "Q362", "Qnone", "Qstele"], p31, p279)
    assert t.to_dict() == {
        "Q90": "settlement",  # settlement outranks organization
        "Q937": "human",  # a root class itself, no P279 edges needed
        "Qx": "other",
        "Q362": "event",
        "Qnone": "no_p31",
        "Qstele": "structure",
    }
