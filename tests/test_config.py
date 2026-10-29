import importlib
from pathlib import Path

import pytest

from wao import check_env, config, http


def test_language_set_has_no_duplicates():
    assert len(config.LANGS) == len(set(config.LANGS))
    assert "en" in config.LANGS


def test_key_dates_are_ordered():
    assert (
        config.CHATGPT_RELEASE < config.SGE_LABS_US < config.PRE_PERIOD_END < config.AIO_US_LAUNCH
    )


def test_env_overrides_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("WAO_RAW_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("WAO_DATA_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("WAO_CONTACT", "https://example.org/me")
    reloaded = importlib.reload(config)
    try:
        assert reloaded.CLICKSTREAM_DIR == tmp_path / "raw" / "clickstream"
        assert reloaded.PARQUET_DIR == tmp_path / "out" / "parquet"
        assert reloaded.CONTACT == "https://example.org/me"
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_user_agent_includes_contact():
    ua = http.user_agent("https://example.org/me")
    assert ua.startswith("wao/") and "(https://example.org/me)" in ua


def test_user_agent_requires_contact():
    with pytest.raises(RuntimeError, match="WAO_CONTACT"):
        http.user_agent("  ")


def test_session_caches_and_sets_user_agent(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONTACT", "https://example.org/me")
    s = http.session("t", cache_dir=tmp_path)
    assert "(https://example.org/me)" in s.headers["User-Agent"]
    assert (tmp_path / "t.sqlite").exists()


def test_unmounted_volume_is_detected():
    assert not check_env.mounted(Path("/Volumes/NoSuchDrive-wao-test/data"))
    assert check_env.mounted(Path(__file__).parent / "not-yet-created")


@pytest.mark.network
def test_live_pageviews_api():
    import os

    if os.environ.get("WAO_NETWORK_TESTS") != "1" or not config.CONTACT:
        pytest.skip("network tests off or WAO_CONTACT unset")
    url = (
        f"{config.AQS_BASE}/pageviews/per-article/en.wikipedia/all-access/user/"
        "Albert_Einstein/daily/20230101/20230107"
    )
    r = http.session("tests").get(url, timeout=30)
    assert r.status_code == 200
    assert len(r.json()["items"]) == 7
