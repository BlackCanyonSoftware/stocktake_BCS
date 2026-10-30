"""Comparing versions, and naming how big a jump is.

Three ecosystems, three sets of rules, and they genuinely differ enough that one function would get answers wrong:

- **PyPI** follows PEP 440. `packaging` does it properly and is used when it happens to be importable; it is not a dependency
  ([ADR 0001](adr/0001-python-with-a-standard-library-only-core.md)), so there is a fallback over the leading dotted integers.
- **npm** follows SemVer, where `1.0.0-beta` comes *before* `1.0.0`, numeric prerelease identifiers rank below alphanumeric ones, and a
  shorter prerelease ranks below a longer one with the same prefix. Judged by PEP 440's rules, some of those come out backwards.
- **GitHub release tags** are whatever the project felt like: `v2.16.0`, `262`, `2026.1`. The leading dotted integers are all that can be
  relied on, which is why that is the fallback rather than the rule.
"""

from __future__ import annotations

import re
from typing import Any

# Ecosystems whose versions follow SemVer rather than PEP 440.
SEMVER_ECOSYSTEMS = frozenset({"npm"})

_LEADING_NUMBERS = re.compile(r"\s*v?(\d+(?:\.\d+)*)")


def release_tuple(text: str) -> tuple[int, ...]:
    """The leading dotted integers of a version, so `v2.16.0` and `2.16.0` and `262` all sort sensibly. `()` when there are none."""
    match = _LEADING_NUMBERS.match(text or "")
    return tuple(int(part) for part in match.group(1).split(".")) if match else ()


def semver_key(text: str) -> tuple[tuple[int, ...], int, tuple[tuple[int, int, str], ...]]:
    """A sort key following SemVer's precedence rules.

    Build metadata (`+build`) is ignored, as SemVer says it must be. A version with no prerelease ranks above every prerelease of the same
    core version, which is the rule a naive string comparison gets backwards.
    """
    cleaned = (text or "").strip().removeprefix("v").removeprefix("=")
    core_and_pre = cleaned.partition("+")[0]
    core, _, prerelease = core_and_pre.partition("-")

    numbers = [int(part) if part.isdigit() else 0 for part in core.split(".")[:3]]
    numbers += [0] * (3 - len(numbers))

    if not prerelease:
        return (tuple(numbers), 1, ())

    # Numeric identifiers always rank below alphanumeric ones, so the first element of each says which kind it is.
    identifiers = tuple((0, int(part), "") if part.isdigit() else (1, 0, part) for part in prerelease.split("."))
    return (tuple(numbers), 0, identifiers)


def sort_key(version: str, ecosystem: str = "PyPI") -> tuple[Any, ...]:
    """A key for ordering several versions of one package — exact for npm, approximate for a PyPI prerelease."""
    return semver_key(version) if ecosystem in SEMVER_ECOSYSTEMS else release_tuple(version)


def is_newer(latest: str, current: str, ecosystem: str = "PyPI", *, moving: bool = False) -> bool:
    """Whether `latest` really is a later release than `current`, by that ecosystem's rules.

    `moving` says the version in hand is a tag its publisher advances — a GitHub Actions `@v7`, a Docker `:3.12`. Such a tag is a range
    wearing a version's clothes: it already points at the newest release beginning with it, so the comparison is made only to the precision
    actually written down. Without this, every workflow pinned to `@v7` is reported as needing `7.0.1`, which is an update that has already
    happened by itself — and a report full of things nobody needs to do is a report nobody reads.
    """
    if moving:
        depth = len(release_tuple(current))
        return bool(depth) and release_tuple(latest)[:depth] > release_tuple(current)[:depth]
    if ecosystem in SEMVER_ECOSYSTEMS:
        return semver_key(latest) > semver_key(current)
    try:
        from packaging.version import Version

        return Version(latest) > Version(current)
    except Exception:  # noqa: BLE001 - packaging absent, or a version string it refuses
        return release_tuple(latest) > release_tuple(current)


def update_kind(latest: str, current: str) -> str:
    """How big the jump is, by the first position where the two differ: `major`, `minor` or `patch`.

    The same for every ecosystem: all three number their releases the same way, whatever they do about prereleases.
    """
    new, old = release_tuple(latest), release_tuple(current)
    for index in range(max(len(new), len(old))):
        left = new[index] if index < len(new) else 0
        right = old[index] if index < len(old) else 0
        if left != right:
            return "major" if index == 0 else "minor" if index == 1 else "patch"
    return "patch"
