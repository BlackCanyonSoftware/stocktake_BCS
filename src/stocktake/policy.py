"""The decisions the project owner has already made: advisories accepted for now, a whole package accepted for now, packages held back.

Nothing here switches the check off. Every entry needs a reason and a date to look at it again, and an entry past its date both stops
suppressing whatever it covered and fails the run. That is what stops "ignore it for now" from becoming permanent by neglect (docs/adr/0004),
and it is why the escape hatch can be trusted at all.

Three kinds, and the difference between them is what is being accepted:

- `ignore_advisories` accepts **one advisory**, by id or alias. The narrowest statement, and the right one when a single advisory is not
  reachable in your use of the package.
- `ignore_package` accepts **a package at a version**, with every advisory against it. Added because the narrow form does not scale: one
  real project would have needed 58 entries for `electron` and `tar`, and the practical consequence of that is that nobody gates on the
  check at all, which is worse than a policy entry somebody has to renew (docs/adr/0011).
- `hold_back` accepts **being out of date**, and nothing else. It never suppresses a vulnerability, which is the question `ignore_package`
  exists to answer instead.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from stocktake.models import normalize

IGNORE = "ignore_advisories"
ACCEPT = "ignore_package"
HOLD = "hold_back"
KINDS: tuple[str, ...] = (IGNORE, ACCEPT, HOLD)


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

    kind: str  # IGNORE, ACCEPT or HOLD
    what: str  # an advisory id (or any alias of it), or a package name
    reason: str = ""
    until: date | None = None
    # ACCEPT only: the one version being accepted. Empty means any version of the package, which is the broader and more dangerous
    # statement, so it is never the default a reader has to infer — a config file that leaves it out is saying so deliberately.
    version: str = ""

    @property
    def complete(self) -> bool:
        """Whether this entry says enough to be acted on at all."""
        return bool(self.reason) and self.until is not None

    @property
    def subject(self) -> str:
        """What this entry is about, for a message. Carries the version where there is one, since that is half of what was accepted."""
        return f"{self.what} {self.version}" if self.version else self.what

    def covers(self, name: str, version: str | None) -> bool:
        """Whether this ACCEPT entry is about this exact dependency."""
        if normalize(self.what) != normalize(name):
            return False
        return not self.version or self.version == version

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

    def accepted_vulnerability(self, name: str, version: str | None, today: date) -> PolicyEntry | None:
        """The entry accepting this package at this version, or None.

        Matching on the version by default is the point: `electron 33.4.11` being accepted says nothing about `electron 34`, and an
        acceptance that silently carried forward to a version nobody looked at would be the one failure a policy file must not have.
        """
        return next((e for e in self.entries if e.kind == ACCEPT and e.active(today) and e.covers(name, version)), None)

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
                problems.append(f"{entry.kind}: {entry.subject} needs a reason and an `until` date (YYYY-MM-DD)")
            elif entry.until is not None and entry.until < today:
                problems.append(
                    f"{entry.kind}: {entry.subject} was accepted until {entry.until} and is due for a decision again ({entry.reason})"
                )
        return tuple(problems)


def policy_from_toml(table: Mapping[str, Any]) -> Policy:
    """A Policy from a config file's `[policy]` table.

    An entry missing its reason or its date is kept, not dropped, so it can be reported as the problem it is rather than silently ignored.
    """
    entries = []
    for kind, key in ((IGNORE, "id"), (ACCEPT, "package"), (HOLD, "package")):
        for raw in table.get(kind) or []:
            if not isinstance(raw, Mapping):
                continue
            what = raw.get(key) or raw.get("id") or raw.get("package") or "?"
            version = raw.get("version") if kind == ACCEPT else None
            entries.append(
                PolicyEntry(
                    kind=kind,
                    what=str(what),
                    reason=str(raw.get("reason") or ""),
                    until=_as_date(raw.get("until")),
                    version=str(version) if version is not None else "",
                )
            )
    return Policy(tuple(entries))
