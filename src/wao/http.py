"""One HTTP session for every Wikimedia call: polite User-Agent, on-disk cache, rate limit, retries.

Wikimedia's User-Agent policy asks for a descriptive agent with contact info; requests without
one can be blocked. Responses are cached so re-running a step never re-fetches.
"""

from __future__ import annotations

import time
from pathlib import Path

import requests
import requests_cache
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from wao import __version__, config

DEFAULT_MIN_INTERVAL = 0.02  # seconds between uncached requests (~50/s, under AQS limits)


def user_agent(contact: str | None = None) -> str:
    contact = config.CONTACT if contact is None else contact.strip()
    if not contact:
        raise RuntimeError(
            "WAO_CONTACT is not set; Wikimedia requires contact info in the User-Agent"
        )
    return f"wao/{__version__} ({contact}) python-requests/{requests.__version__}"


class PoliteSession(requests_cache.CachedSession):
    """Cached session that sleeps between uncached requests."""

    def __init__(self, cache_path: Path, min_interval: float, **kwargs):
        kwargs.setdefault("allowable_codes", (200, 404))
        super().__init__(str(cache_path), backend="sqlite", **kwargs)
        self.min_interval = min_interval
        self._last = 0.0

    def request(self, *args, **kwargs):
        resp = super().request(*args, **kwargs)
        if not getattr(resp, "from_cache", False):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
        return resp


def session(
    name: str = "wikimedia",
    min_interval: float = DEFAULT_MIN_INTERVAL,
    cache_dir: Path | None = None,
    post: bool = False,
) -> PoliteSession:
    """`post=True` also caches POST responses (keyed on the body), e.g. for Lift Wing."""
    cache_dir = config.CACHE_DIR if cache_dir is None else cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    methods = ("GET", "HEAD", "POST") if post else ("GET", "HEAD")
    s = PoliteSession(cache_dir / f"{name}.sqlite", min_interval, allowable_methods=methods)
    s.headers["User-Agent"] = user_agent()
    retry = Retry(
        total=6,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        respect_retry_after_header=True,
        allowed_methods=methods,
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s
