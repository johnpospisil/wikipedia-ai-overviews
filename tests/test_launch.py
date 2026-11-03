"""P34: launch drafts fit platform limits and quote only the pipeline's numbers."""

from __future__ import annotations

import re

import pytest

from wao import article, config

LAUNCH = config.REPO_ROOT / "docs" / "launch"
# numbers quoted from elsewhere: Wikimedia's ~8% (Miller 2025), Khosravi & Yoganarasimhan's 5%,
# interval levels, and the descriptive values from P11/P12/P29 cited in the reviewer answers
CITED = {
    "8%",
    "5%",
    "95%",
    "1.1%",
    "0.7%",
    "44%",
    "37%",
    "68%",
    "63%",
    "15%",
    "0.2%",
    "1.2%",
    "0.1%",
}


def _posts(section: str, pattern: str) -> list[str]:
    text = (LAUNCH / "social.md").read_text().split(section)[1]
    return re.findall(pattern, text.split("\n## ")[0], flags=re.M)


def test_bluesky_posts_fit():
    posts = _posts("## Bluesky thread", r"^\d/ .+$")
    assert len(posts) == 6
    for p in posts:
        assert len(p) <= 300, (len(p), p[:40])


def test_x_posts_fit():
    posts = _posts("## X thread", r"^X\d/ .+$")
    assert len(posts) == 3
    for p in posts:
        assert len(p) - 1 <= 280, (len(p), p[:40])  # the "X" prefix is not posted


def test_hacker_news_titles_fit():
    text = (LAUNCH / "hacker-news.md").read_text().split("## Title")[1].split("##")[0]
    titles = [re.sub(r"\*\*(.+?)\*\*.*", r"\1", t) for t in re.findall(r"^\d\. (.+)$", text, re.M)]
    assert len(titles) == 3 and all(len(t) <= 80 for t in titles), titles


def test_drafts_quote_current_numbers():
    if config.SAMPLE or not (config.REPORT_DIR / "qa" / "p27_numbers.csv").exists():
        pytest.skip("needs the real outputs")
    article.numbers.cache_clear()
    n = article.numbers()
    known = {m for v in n.values() for m in re.findall(r"[−+]?\d+(?:\.\d+)?%", v)}
    known |= {k.lstrip("−+") for k in known}
    for f in LAUNCH.glob("*.md"):
        text = f.read_text()
        unknown = {p for p in re.findall(r"[−+]?\d+(?:\.\d+)?%", text)
                   if p not in known and p.lstrip("−+") not in CITED}  # fmt: skip
        assert not unknown, (f.name, sorted(unknown))
    hn = (LAUNCH / "hacker-news.md").read_text()
    for key in ("att_primary_1", "att_primary_ci", "att_full_1", "att_full_ci", "en_primary"):
        assert n[key] in hn, (key, n[key])
    assert f"{n['idx_tr_min']}–{n['idx_tr_max']}" in hn and f"is at {n['idx_ru']}" in hn
