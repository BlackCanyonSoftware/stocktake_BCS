"""The vocabulary of a run: a dependency as the project declares it, the judgement passed on it, and the report of all of them.

Frozen dataclasses with no behaviour beyond derived properties, so every other module can depend on this one and this one depends on nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Report order, worst first. `current` is last and collapses to a count (docs/DESIGN.md).
STATUSES: tuple[str, ...] = ("vulnerable", "yanked", "outdated", "held", "unpinned", "unknown", "current")

# The two statuses that fail a build. Being behind is not one of them (docs/adr/0004).
FAIL_STATUSES = frozenset({"vulnerable", "yanked"})

# Taken from the advisory database, never invented. An unrated advisory ranks last but is not "low".
SEVERITY_RANK: dict[str, int] = {"CRITICAL": 4, "HIGH": 3, "MODERATE": 2, "MEDIUM": 2, "LOW": 1}


class DependencyUpdateAvailable(UserWarning):
    """A pinned dependency has a newer release: a warning in the test summary, never a failure (docs/adr/0004)."""


def normalize(name: str) -> str:
    """A package name reduced to a comparison key, so names differing only in case or in `-`, `_` and `.` compare equal (PEP 503's rule).

    This is StockTake's internal key — for matching a policy entry, and for keying advisories against the dependency they belong to. It is
    deliberately the same rule for every ecosystem, because a policy entry does not say which ecosystem it means and somebody writing
    `package = "Left-Pad"` should not have to care.

    It is **not** what any registry is asked for. That is `registry_name`.
    """
    return re.sub(r"[-_.]+", "-", name).lower()


def registry_name(ecosystem: str, name: str) -> str:
    """The name as that ecosystem's registry spells it.

    PyPI normalises, and treats `Typing_Extensions` and `typing-extensions` as the same project. npm does not: names are case-sensitive, may
    be scoped (`@babel/traverse`), and asking for the wrong spelling gets a 404 rather than the package.
    """
    return normalize(name) if ecosystem == "PyPI" else name


@dataclass(frozen=True, slots=True)
class Dep:
    """One dependency, exactly as some file in the project declares it."""

    ecosystem: str  # PyPI | npm | GitHub | Docker
    name: str
    version: str | None  # pinned, resolved or installed; None when nothing fixes it
    source: str  # "docker/dev/Dockerfile:10"
    spec: str = ""  # as written, e.g. ">=8"
    # Who declared it: runtime or dev dependency of the project, baked into an image, used by CI, or resolved by a lock file (which does not
    # record which group it belongs to).
    role: str = "runtime"  # runtime | dev | image | ci | locked
    # Why there is no version to check, when the reader knows and the judge could not work it out — an action pinned to a commit SHA, say.
    note: str = ""
    # True when the "version" is a tag its publisher moves: a GitHub Actions `@v7`, or a Docker `:3.12`. Such a tag already tracks the newest
    # release beginning with it, so only a change at the precision written down is an update — `v7` to `v8` is, `v7` to `v7.0.1` is not.
    moving: bool = False


@dataclass(frozen=True, slots=True)
class Advisory:
    """One real security problem. Aliases of the same problem (a GHSA and its PYSEC twin) are merged into one of these."""

    id: str
    severity: str = ""
    summary: str = ""
    aliases: tuple[str, ...] = ()
    fixed: tuple[str, ...] = ()  # every fixed version the advisory names, oldest first

    @property
    def rank(self) -> int:
        return SEVERITY_RANK.get(self.severity.upper(), 0)

    @property
    def label(self) -> str:
        """How the severity is printed. Never blank, and never guessed at."""
        return self.severity or "unrated"


@dataclass(frozen=True, slots=True)
class Finding:
    """A dependency plus what we concluded about it."""

    dep: Dep
    status: str  # one of STATUSES
    severity: str  # fail | warn | info | ok
    latest: str | None = None
    update: str | None = None  # major | minor | patch
    advisories: tuple[Advisory, ...] = ()
    note: str = ""


@dataclass(frozen=True, slots=True)
class Unread:
    """Dependency manifests no registered reader understands, split by whether the project has said it knows."""

    reported: tuple[str, ...] = ()  # nobody has acknowledged these, so they are named in the report
    accepted: tuple[str, ...] = ()  # listed in the project's `accept_unread`: they do not nag, but they are still recorded


@dataclass(frozen=True, slots=True)
class Report:
    """Everything one run found."""

    findings: tuple[Finding, ...]
    policy_problems: tuple[str, ...] = ()
    offline: str | None = None  # None, or why nothing could be reached
    today: str = ""
    unread_manifests: tuple[str, ...] = ()  # manifests no reader understands, which the project has not acknowledged
    accepted_unread: tuple[str, ...] = ()  # the same, but accepted in the project's config: not reported, still recorded
    # Things about this run the reader needs in order to judge it, such as an environment that could not be found.
    notes: tuple[str, ...] = ()
    # The config file this run used, so a policy problem can be pointed at the file that caused it.
    config_source: str | None = None

    @property
    def failed(self) -> bool:
        """Whether this run should fail a build: something unsafe, or a policy decision that has run out."""
        return bool(self.policy_problems) or any(f.severity == "fail" for f in self.findings)

    @property
    def counts(self) -> dict[str, int]:
        """How many findings of each status, every status present even at zero, so two runs are comparable."""
        return {status: sum(1 for f in self.findings if f.status == status) for status in STATUSES}
