"""What a registry client is: something that answers questions about a name, and never looks at the project.

The mirror image of a reader (docs/adr/0003). A reader knows what the project declares and nothing about the outside world; a client knows
the outside world and nothing about the project. Neither imports the other.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from stocktake.models import Advisory

# (ecosystem, name, version) — what we want to know about. The name is as the project wrote it; normalising is the client's business.
Coordinate = tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class Versions:
    """What a registry says about a name: the newest release, and which releases its own author has withdrawn."""

    latest: str
    withdrawn: frozenset[str] = frozenset()


@runtime_checkable
class Client(Protocol):
    """Answers "what is the newest version of this" for one ecosystem."""

    ecosystem: str

    def latest(self, name: str) -> Versions | None:
        """None when the registry has no such package. Raises OfflineError or RateLimited rather than guessing."""
        ...


@runtime_checkable
class AdvisoryClient(Protocol):
    """Answers "what is known against these exact versions", for every ecosystem at once."""

    def advisories(self, wanted: Sequence[Coordinate]) -> Mapping[Coordinate, tuple[Advisory, ...]]:
        """Only the coordinates with something against them appear in the result. An absent key means nothing known, never "safe"."""
        ...
