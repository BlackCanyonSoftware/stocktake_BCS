"""Comparing versions, and naming how big a jump is.

`packaging` does this properly for PyPI and is used when it happens to be importable. It is not a dependency (docs/adr/0001), so there is a
fallback that compares the leading dotted integers. The fallback is approximate for pre-releases; the cases that occur in practice are tested.
"""

from __future__ import annotations

import re

_LEADING_NUMBERS = re.compile(r"\s*v?(\d+(?:\.\d+)*)")


def release_tuple(text: str) -> tuple[int, ...]:
    """The leading dotted integers of a version, so `v2.16.0` and `2.16.0` and `262` all sort sensibly. `()` when there are none."""
    match = _LEADING_NUMBERS.match(text or "")
    return tuple(int(part) for part in match.group(1).split(".")) if match else ()


def is_newer(latest: str, current: str) -> bool:
    """Whether `latest` really is a later release than `current`."""
    try:
        from packaging.version import Version

        return Version(latest) > Version(current)
    except Exception:  # noqa: BLE001 - packaging absent, or a version string it refuses
        return release_tuple(latest) > release_tuple(current)


def update_kind(latest: str, current: str) -> str:
    """How big the jump is, by the first position where the two differ: `major`, `minor` or `patch`."""
    new, old = release_tuple(latest), release_tuple(current)
    for index in range(max(len(new), len(old))):
        left = new[index] if index < len(new) else 0
        right = old[index] if index < len(old) else 0
        if left != right:
            return "major" if index == 0 else "minor" if index == 1 else "patch"
    return "patch"
