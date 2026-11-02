"""P30: every number in report/index.qmd comes from wao.article.numbers() (report/qa outputs)."""

from __future__ import annotations

import re

import pytest

from wao import config

QMD = config.REPO_ROOT / "report" / "index.qmd"


def test_every_key_exists_and_has_a_value():
    if not (config.REPO_ROOT / "report" / "qa" / "p27_numbers.csv").exists():
        pytest.skip("figures not built")
    from wao.article import numbers

    n = numbers()
    used = set(re.findall(r'N\["([a-z0-9_]+)"\]', QMD.read_text()))
    assert used, "no N[...] references found"
    assert not used - n.keys(), f"missing keys: {sorted(used - n.keys())}"
    bad = {k: n[k] for k in used if n[k] in ("n/a", "nan") or "nan" in n[k]}
    assert not bad, bad


def test_no_hand_typed_estimates():
    # estimates appear only through N[...]; typed percentages are allowed next to a citation, plus
    # the SESOI (5%), interval levels (95%) and the "5–10%" range the decision rule refers to
    text = re.sub(r"`\{python\}[^`]*`", "", QMD.read_text())
    text = text.split("## References")[0]
    for line in text.splitlines():
        if line.startswith(("![", "    ")) or "fig-alt" in line:
            continue
        hits = re.findall(r"[−+-]?\d+(?:\.\d+)?%", line)
        if hits and "[@" not in line:
            assert set(hits) <= {"5%", "95%", "10%"}, f"typed numbers {hits} in: {line[:120]}"
