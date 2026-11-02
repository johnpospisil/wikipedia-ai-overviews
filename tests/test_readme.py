"""P33: README links resolve and its numbers match the pipeline's output (wao.article)."""

from __future__ import annotations

import re

import pytest

from wao import article, config

README = config.REPO_ROOT / "README.md"


def test_relative_links_exist():
    text = README.read_text()
    links = re.findall(r"\]\(([^)#]+)\)", text) + re.findall(
        r'srcset="([^"]+)"|src="([^"]+)"', text
    )
    paths = [p for group in links for p in (group if isinstance(group, tuple) else (group,)) if p]
    local = [p for p in paths if not p.startswith(("http://", "https://"))]
    assert local
    missing = [p for p in local if not (config.REPO_ROOT / p).exists()]
    assert not missing, missing


def test_numbers_match():
    if config.SAMPLE or not (config.REPORT_DIR / "qa" / "p27_numbers.csv").exists():
        pytest.skip("needs the real outputs")
    article.numbers.cache_clear()
    n = article.numbers()
    text = README.read_text()
    phrases = [
        f"effect of {n['att_primary_1']} in the first six months "
        f"(95% interval {n['att_primary_ci']})",
        f"{n['att_full_1']} to July 2026 ({n['att_full_ci']})",
        f"between {n['idx_tr_min']} and {n['idx_tr_max']} in the eight editions",
        f"and {n['idx_ru']} in Russian",
        f"detect a loss of about {n['mde_primary']}",
        f"English alone comes out at {n['en_primary']}",
        f"None of the {n['n_variants']} robustness variants",
        f"({n['quick_exposed']} vs {n['long_exposed']})",
        f"({n['quick_ctrl']} vs {n['long_ctrl']})",
        f"gives {n['h2']} per standard deviation ({n['h2_ci']})",
        f"which did {n['h4_abs']} *better*",
        f"the smallest p-value is {n['holm_min_p']}",
        f"across {n['n_variants']} robustness variants",
        f"range of {n['rob_min']} to {n['rob_max']}",
    ]
    missing = [p for p in phrases if p not in text]
    assert not missing, missing
    assert n["n_sig_loss"] == "0" and n["holm_supported"] == "0"  # "none" claims in the README
