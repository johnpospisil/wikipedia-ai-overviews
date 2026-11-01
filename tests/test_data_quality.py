"""P11 data-quality checks on the real outputs (skipped when the QA tables have not been built).

Each test reads a table written by wao.viz.reconcile or wao.build.truncation (report/qa/) or
data/reference/data_breaks.csv, so `make test` stays fast; rebuild with `make qa`.
"""

from __future__ import annotations

import pandas as pd
import pytest

from wao import config

QA = config.REPORT_DIR / "qa"
BREAKS = config.REFERENCE_DIR / "data_breaks.csv"
CLICKSTREAM_START = "2019-04"  # clickstream method change, see data_breaks.csv


def _read(name: str) -> pd.DataFrame:
    path = QA / f"{name}.csv"
    if not path.exists():
        pytest.skip(f"{path.name} not built (make qa)")
    return pd.read_csv(path)


def _breaks() -> pd.DataFrame:
    b = pd.read_csv(BREAKS, dtype=str)
    b["end"] = b.end.fillna("9999-12")
    return b


def _covered(lang: str, month: str, source: str) -> bool:
    b = _breaks()
    b = b[(b.source == source) & (b.start <= month) & (b.end >= month)]
    return any(x == "all" or lang in x.split() for x in b.lang)


def test_breaks_table_is_well_formed():
    b = pd.read_csv(BREAKS, dtype=str)
    assert list(b.columns) == ["source", "lang", "start", "end", "issue", "evidence", "handling"]
    assert b.start.str.fullmatch(r"\d{4}-\d{2}").all()
    assert b.end.dropna().str.fullmatch(r"\d{4}-\d{2}").all()
    # the two breaks every later prompt must handle
    assert ((b.source == "clickstream") & (b.start == "2025-04")).any()
    assert ((b.source == "pageviews") & (b.start == "2025-04")).any()


def test_checklist_has_no_unexplained_failure():
    c = _read("p11_checklist")
    failed = c[c.status == "fail"].check.tolist()
    assert all("2025-04" in f for f in failed), failed  # the known incomplete clickstream month


def test_no_duplicate_article_days():
    c = _read("p11_checklist").set_index("check")
    assert c.loc["duplicate article-day-access rows in pageview_daily", "detail"] == "0"


def test_perarticle_views_equal_aqs():
    p = _read("p11_perarticle_check")
    p = p[p.months > 0]
    assert (p.months_equal * p.months).sum() / p.months.sum() > 0.97
    assert (p.ours_resolved >= 0.99 * p.aqs).all()  # redirects only ever add views


def test_sample_reproduces_aqs_level():
    s = _read("p11_sample_vs_aqs")
    y = s[s.month.str.startswith("2023")].groupby("lang")[["est", "aqs_user"]].sum()
    assert (y.est / y.aqs_user).between(0.80, 1.02).all()


def test_every_flagged_clickstream_month_is_documented():
    c = _read("p11_clickstream_vs_aqs")
    c = c[c.flag & (c.month >= CLICKSTREAM_START)]
    missing = [(r.lang, r.month) for r in c.itertuples()
               if not (_covered(r.lang, r.month, "clickstream")
                       or _covered(r.lang, r.month, "pageviews"))]  # fmt: skip
    assert not missing, missing


def test_clickstream_tracks_aqs_after_2019_04():
    c = _read("p11_clickstream_vs_aqs")
    c = c[(c.month >= CLICKSTREAM_START) & ~c.flag]
    assert c.ratio.between(0.75, 1.05).all()


def test_truncation_small_at_language_level():
    t = _read("p11_truncation_lang_month")
    y = t[t.month.str.startswith("2023")].groupby("lang")[["observed", "hidden"]].sum()
    assert (y.hidden / (y.observed + y.hidden) < 0.05).all()
    s = _read("p11_truncation_simulation")
    assert s[(s.decile == 0) & (s.d <= 0.3)].bias_pp.abs().max() < 1
