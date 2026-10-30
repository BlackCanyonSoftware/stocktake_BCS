"""Every registry client, wired to one shared cache.

This is the wiring, and the only place that knows which concrete clients exist. `evaluate()` is handed one `Registries` and never builds one,
which is precisely why the whole test suite runs with no network at all (docs/ARCHITECTURE.md).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from stocktake.models import Advisory
from stocktake.registries.base import AdvisoryClient, Client, Coordinate, Versions
from stocktake.registries.github import GitHub
from stocktake.registries.http import (
    TTL_SECONDS,
    Cache,
    OfflineError,
    RateLimited,
    cache_path,
    default_fetch,
)
from stocktake.registries.npm import Npm
from stocktake.registries.osv import OSV
from stocktake.registries.pypi import PyPI

__all__ = [
    "OSV",
    "TTL_SECONDS",
    "AdvisoryClient",
    "Cache",
    "Client",
    "Coordinate",
    "GitHub",
    "Npm",
    "OfflineError",
    "PyPI",
    "RateLimited",
    "Registries",
    "Versions",
    "cache_path",
    "default_fetch",
]


class Registries:
    """Every registry client behind one object, sharing one cache."""

    def __init__(
        self,
        cache: Cache | None = None,
        clients: Sequence[Client] | None = None,
        advisory_client: AdvisoryClient | None = None,
    ) -> None:
        self.cache = cache if cache is not None else Cache()
        chosen = clients if clients is not None else (PyPI(self.cache), Npm(self.cache), GitHub(self.cache))
        self.clients: dict[str, Client] = {client.ecosystem: client for client in chosen}
        self.advisory_client = advisory_client if advisory_client is not None else OSV(self.cache)

    @property
    def ecosystems(self) -> tuple[str, ...]:
        return tuple(self.clients)

    def latest(self, ecosystem: str, name: str) -> Versions | None:
        """The newest version of a name, or None when the registry does not have it. Raises rather than guessing when it cannot be asked."""
        client = self.clients.get(ecosystem)
        return client.latest(name) if client is not None else None

    def advisories(self, wanted: Sequence[Coordinate]) -> Mapping[Coordinate, tuple[Advisory, ...]]:
        return self.advisory_client.advisories(wanted)

    def flush(self) -> None:
        self.cache.flush()
