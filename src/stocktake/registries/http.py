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
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from stocktake._version import __version__

TTL_SECONDS = 6 * 3600
TIMEOUT_SECONDS = 20

# One retry, for a connection that failed rather than a service that answered.
#
# This is not politeness theatre. Verifying the npm reader against a real project, two of three requests to api.github.com failed TLS
# verification while every request to pypi.org, npmjs.org and osv.dev in the same run succeeded, and a later attempt to the same three URLs
# worked. The tool behaved correctly — it reported those two as `unknown` with the reason, and never as clean — but "unknown" for a
# dependency that is in fact fine is noise, and noise is what gets a checker switched off.
#
# A service that *answered* is never retried: a 404 is a real answer, and retrying a 429 makes the rate limiting worse.
RETRY_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 0.5
USER_AGENT = f"stocktake/{__version__} (+https://github.com/BlackCanyonSoftware/stocktake_BCS)"


class FetchFn(Protocol):
    """Anything that can make one request.

    `headers` exists because an OCI container registry will not answer about a *public* image without a bearer token, which is the first
    service here needing a credential to read something anonymous (docs/adr/0012). A fake in a test may ignore it.
    """

    # Positional-only: the cache always calls a fetcher positionally, and saying so here means a stand-in is free to name its parameters
    # whatever reads best, including the leading underscore that marks one it deliberately ignores.
    def __call__(self, url: str, body: dict[str, Any] | None = ..., headers: Mapping[str, str] | None = ..., /) -> Any: ...


ClockFn = Callable[[], float]


class OfflineError(RuntimeError):
    """The service could not be reached at all."""


class RateLimited(RuntimeError):
    """The service asked us to slow down. That one answer is unknown; the run is not."""


class Unauthorized(OfflineError):
    """The service answered, and said it will not talk to us without a credential.

    A subclass of `OfflineError` on purpose. To everything upstream this is the same fact — we did not get an answer, so the finding is
    `unknown` and never clean — and nothing has to learn a fourth failure. It is a distinct type only because an OCI registry answers 401 as
    the *first half* of its normal handshake for a public image, and the client needs to tell that apart from a real refusal.
    """


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


def default_fetch(
    url: str,
    body: dict[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: int = TIMEOUT_SECONDS,
    attempts: int = RETRY_ATTEMPTS,
) -> Any:
    """One request, retried once if the connection itself failed.

    A 404 is an answer ("no such package"); 403 and 429 are rate limiting; a connection that never got that far is being offline. Only the
    last of those is worth trying again.

    The only thing sent is the URL, which carries a package name, and for OSV a body of names and versions. Nothing else, ever (NFR-1).
    `headers` adds a bearer token the caller has already obtained; it carries no identity of the user's, only permission to read a public
    image (docs/adr/0012).
    """
    sending = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token and "api.github.com" in url:
        sending["Authorization"] = f"Bearer {token}"  # raises GitHub's 60-an-hour anonymous limit; sent to GitHub alone
    if headers:
        sending.update(headers)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        sending["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=sending)  # noqa: S310 - every URL here is a literal in this package

    for attempt in range(1, max(attempts, 1) + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # a subclass of URLError, so it has to be caught first
            if exc.code == 404:
                return None
            if exc.code == 401:
                raise Unauthorized(f"{url} answered 401") from exc
            if exc.code in (403, 429):
                raise RateLimited(f"{url} answered {exc.code}") from exc
            raise OfflineError(f"{url} answered {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt >= max(attempts, 1):
                raise OfflineError(str(exc)) from exc
            time.sleep(RETRY_DELAY_SECONDS)
    raise OfflineError(f"{url} could not be reached")  # unreachable; the loop either returns or raises


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

    def get(self, url: str, body: dict[str, Any] | None = None, headers: Mapping[str, str] | None = None) -> Any:
        """The cached answer if it is fresh enough, otherwise one request. Exceptions are not cached.

        `headers` is passed on but is deliberately **not** part of the key. It says who is asking, never what is being asked for: the tag
        list of a public image is the same document whichever bearer token fetched it, and keying on the token would mean a cache that
        missed every run, since the token is new each time.
        """
        key = self._key(url, body)
        hit = self.entries.get(key)
        if hit and not self.refresh and self.now() - hit["t"] < self.ttl:
            return hit["data"]
        data = self.fetch(url, body, headers)
        self.entries[key] = {"t": self.now(), "data": data}
        return data

    def once(self, url: str, headers: Mapping[str, str] | None = None) -> Any:
        """One request whose answer is deliberately not kept.

        For a short-lived credential. An OCI token is good for minutes; this cache keeps answers for six hours, so a cached token would be
        an expired token for most of its life, and every run after the first would fail with a 401 that looks like a broken registry.
        """
        return self.fetch(url, None, headers)

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
