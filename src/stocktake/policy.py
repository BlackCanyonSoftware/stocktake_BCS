"""The decisions the project owner has already made: advisories accepted for now, packages held back on purpose.

Nothing here switches the check off. Every entry needs a reason and a date to look at it again, and an entry past its date both stops
suppressing whatever it covered and fails the run. That is what stops "ignore it for now" from becoming permanent by neglect (docs/adr/0004),
and it is why the escape hatch can be trusted at all.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from stocktake.models import normalize

IGNORE = "ignore_advisories"
HOLD = "hold_back"
KINDS: tuple[str, ...] = (IGNORE, HOLD)


def _as_date(value: object) -> date | None:
    """A date from whatever the config file held. TOML gives a real date; a string is accepted and read as ISO. Anything else is no date at all."""
    if isinstance(value, datetime):  # datetime subclasses date, so it has to be asked about first
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True, slots=True)
class PolicyEntry:
    """One decision, with the reason for it and the date it has to be made again."""

    kind: str  # IGNORE or HOLD
    what: str  # an advisory id (or any alias of it), or a package name
    reason: str = ""
    until: date | None = None

    @property
    def complete(self) -> bool:
        """Whether this entry says enough to be acted on at all."""
        return bool(self.reason) and self.until is not None

    def active(self, today: date) -> bool:
        """Whether this entry still suppresses anything."""
        return bool(self.reason) and self.until is not None and self.until >= today


@dataclass(frozen=True, slots=True)
class Policy:
    """Every decision for one project."""

    entries: tuple[PolicyEntry, ...] = ()

    def ignored_advisories(self, today: date) -> frozenset[str]:
        """Advisory ids and aliases currently accepted."""
        return frozenset(e.what for e in self.entries if e.kind == IGNORE and e.active(today))

    def held_packages(self, today: date) -> frozenset[str]:
        """Normalised names of packages currently held back from an update on purpose."""
        return frozenset(normalize(e.what) for e in self.entries if e.kind == HOLD and e.active(today))

    def hold_reason(self, name: str, today: date) -> str:
        """Why a package is being held back, so the report can say so. Empty when it is not held."""
        target = normalize(name)
        return next((e.reason for e in self.entries if e.kind == HOLD and e.active(today) and normalize(e.what) == target), "")

    def problems(self, today: date) -> tuple[str, ...]:
        """Entries that cannot be acted on, or whose date has passed. Each one fails the run until it is decided again."""
        problems = []
        for entry in self.entries:
            if not entry.complete:
                problems.append(f"{entry.kind}: {entry.what} needs a reason and an `until` date (YYYY-MM-DD)")
            elif entry.until is not None and entry.until < today:
                problems.append(
                    f"{entry.kind}: {entry.what} was accepted until {entry.until} and is due for a decision again ({entry.reason})"
                )
        return tuple(problems)


def policy_from_toml(table: Mapping[str, Any]) -> Policy:
    """A Policy from a config file's `[policy]` table.

    An entry missing its reason or its date is kept, not dropped, so it can be reported as the problem it is rather than silently ignored.
    """
    entries = []
    for kind, key in ((IGNORE, "id"), (HOLD, "package")):
        for raw in table.get(kind) or []:
            if not isinstance(raw, Mapping):
                continue
            what = raw.get(key) or raw.get("id") or raw.get("package") or "?"
            entries.append(PolicyEntry(kind=kind, what=str(what), reason=str(raw.get("reason") or ""), until=_as_date(raw.get("until"))))
    return Policy(tuple(entries))
