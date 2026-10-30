"""The only module in StockTake that opens a network connection, and the cache that sits in front of it.

Two kinds of failure are told apart, and the distinction carries all the way to the exit code:

- `OfflineError` — the service could not be reached, so we know nothing about it.
- `RateLimited` — the service asked us to slow down, so that one answer is unknown while the rest of the run still stands.

Neither is ever quietly turned into "nothing found". Treating a timeout as a clean result would make a network blip look like a safe project,
which is a worse failure than any amount of noise.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from stocktake._version import __version__

TTL_SECONDS = 6 * 3600
TIMEOUT_SECONDS = 20
USER_AGENT = f"stocktake/{__version__} (+https://github.com/BlackCanyonSoftware/stocktake_BCS)"

FetchFn = Callable[[str, dict[str, Any] | None], Any]
ClockFn = Callable[[], float]


class OfflineError(RuntimeError):
    """The service could not be reached at all."""


class RateLimited(RuntimeError):
    """The service asked us to slow down. That one answer is unknown; the run is not."""


def cache_path() -> Path:
    """Where answers are kept between runs: one cache shared by every project, in the place the platform expects."""
    override = os.environ.get("STOCKTAKE_CACHE")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "stocktake" / "cache.json"


def default_fetch(url: str, body: dict[str, Any] | None = None, timeout: int = TIMEOUT_SECONDS) -> Any:
    """One request. A 404 is an answer ("no such package"); 403 and 429 are rate limiting; anything else that goes wrong is being offline.

    The only thing sent is the URL, which carries a package name, and for OSV a body of names and versions. Nothing else, ever (NFR-1).
    """
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token and "api.github.com" in url:
        headers["Authorization"] = f"Bearer {token}"  # raises GitHub's 60-an-hour anonymous limit; sent to GitHub alone
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)  # noqa: S310 - every URL here is a literal in this package
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        if exc.code in (403, 429):
            raise RateLimited(f"{url} answered {exc.code}") from exc
        raise OfflineError(f"{url} answered {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise OfflineError(str(exc)) from exc


class Cache:
    """A fetcher that remembers its answers for six hours.

    Repeated test runs should be fast and polite rather than hammering a public service, and the cache being shared across projects means
    checking five projects that all pin `requests` asks about it once.
    """

    def __init__(
        self,
        fetch: FetchFn = default_fetch,
        path: Path | None = None,
        ttl: int = TTL_SECONDS,
        now: ClockFn = time.time,
        refresh: bool = False,
    ) -> None:
        self.fetch = fetch
        self.ttl = ttl
        self.now = now
        self.refresh = refresh
        self.path = path or cache_path()
        self.entries: dict[str, dict[str, Any]] = {}
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return  # absent or damaged: start empty rather than fail. A cache is never load-bearing.
        if isinstance(loaded, dict):
            self.entries = loaded

    def _key(self, url: str, body: dict[str, Any] | None) -> str:
        if body is None:
            return url
        return url + hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]

    def get(self, url: str, body: dict[str, Any] | None = None) -> Any:
        """The cached answer if it is fresh enough, otherwise one request. Exceptions are not cached."""
        key = self._key(url, body)
        hit = self.entries.get(key)
        if hit and not self.refresh and self.now() - hit["t"] < self.ttl:
            return hit["data"]
        data = self.fetch(url, body)
        self.entries[key] = {"t": self.now(), "data": data}
        return data

    def flush(self) -> None:
        """Write the cache out, through a temporary file so an interrupted run cannot leave a damaged one behind.

        Failing to write a cache is not worth failing a run over, so an OSError here is swallowed deliberately.
        """
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.entries), encoding="utf-8")
            temporary.replace(self.path)
        except OSError:
            pass
