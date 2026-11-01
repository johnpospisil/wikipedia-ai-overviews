"""P09: per-article monthly edits from stub revisions (bots, anonymous, size deltas)."""

from __future__ import annotations

import duckdb
import pandas as pd

from wao import config
from wao.build import edits


def test_build_counts_bots_anon_and_deltas(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PARQUET_DIR", tmp_path / "pq")
    monkeypatch.setattr(config, "PANEL_DIR", tmp_path / "panels")
    monkeypatch.setattr(config, "TMP_DIR", tmp_path / "tmp")
    (tmp_path / "pq" / "stub_history" / "lang=en").mkdir(parents=True)
    (tmp_path / "pq" / "editors").mkdir(parents=True)
    (tmp_path / "panels").mkdir()
    ts = pd.to_datetime(["2023-01-02", "2023-01-05", "2023-01-09", "2023-01-20", "2023-02-01",
                         "2023-02-03"], utc=True)  # fmt: skip
    pd.DataFrame({
        "page_id": [1] * 6, "rev_id": range(1, 7), "ts": ts,
        "editor": [10, 10, 20, 30, 40, None], "registered": [True, True, False, True, True, False],
        "minor": [False, True, False, False, False, False],
        "bytes": [100, 150, 140, 400, 410, 400],
        "kind": ["user", "user", "ip", "user", "user", "deleted"],
        "name_bot": [False, False, False, False, True, False],
    }).to_parquet(tmp_path / "pq" / "stub_history" / "lang=en" / "part-01.parquet")  # fmt: skip
    pd.DataFrame({"lang": ["en"], "editor": [30], "source": ["group-bot"]}).to_parquet(
        tmp_path / "pq" / "editors" / "bots.parquet"
    )
    edits.build(duckdb.connect())
    df = pd.read_parquet(edits.out_path()).set_index("month")
    jan, feb = df.loc["2023-01"], df.loc["2023-02"]
    assert (jan.edits, jan.edits_user, jan.edits_anon, jan.edits_bot) == (4, 2, 1, 1)
    assert (jan.editors, jan.editors_user, jan.editors_anon, jan.edits_minor) == (2, 1, 1, 1)
    assert jan.bytes_delta == 100 + 50 - 10  # the bot's +260 is left out
    assert (feb.edits, feb.edits_bot, feb.editors) == (2, 1, 0)  # name bot; deleted user
    assert feb.bytes_delta == -10
