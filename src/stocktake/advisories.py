"""Making a list of advisories readable, and working out the one version that clears them all.

This matters more than it sounds. One real package returned ninety OSV entries for a single pinned version; printing ninety is the same as
printing none. Merging aliases, ranking by severity and naming a single upgrade target is what turns that into something a person acts on.
"""

from __future__ import annotations

from collections.abc import Sequence

from stocktake.models import SEVERITY_RANK, Advisory
from stocktake.versions import is_newer, release_tuple


def merge_advisories(items: Sequence[Advisory]) -> list[Advisory]:
    """One entry per real problem, worst first.

    Advisories that share an id or an alias are the same problem reported twice (a GHSA and its PYSEC twin), so they become one entry keeping
    the highest severity, the fullest summary and every fixed version either of them named.
    """
    groups: list[tuple[set[str], list[Advisory]]] = []
    for item in items:
        names = {item.id, *item.aliases}
        members = [item]
        for group in [g for g in groups if g[0] & names]:  # a copy, so removing from groups below is safe
            names |= group[0]
            members = group[1] + members
            groups.remove(group)
        groups.append((names, members))

    merged = []
    for names, members in groups:
        # The best-informed member speaks for the group: worst severity, then GHSA over PYSEC, then the fullest summary.
        best = max(members, key=lambda a: (a.rank, a.id.startswith("GHSA"), len(a.summary)))
        merged.append(
            Advisory(
                id=best.id,
                severity=best.severity,
                summary=best.summary or next((a.summary for a in members if a.summary), ""),
                aliases=tuple(sorted(names - {best.id})),
                fixed=tuple(sorted({f for a in members for f in a.fixed}, key=release_tuple)),
            )
        )
    return sorted(merged, key=lambda a: (-a.rank, a.id))


def fix_target(advisories: Sequence[Advisory], current: str) -> str | None:
    """The single version that clears every advisory that names a fix, or None when none of them name one.

    Per advisory, the smallest fix that is actually ahead of where we are, because a fix backported to a branch we are not on does not help us.
    Overall, the largest of those, because the upgrade has to satisfy all of them at once.
    """
    targets = []
    for advisory in advisories:
        ahead = [f for f in advisory.fixed if is_newer(f, current)] or list(advisory.fixed)
        if ahead:
            targets.append(min(ahead, key=release_tuple))
    return max(targets, key=release_tuple) if targets else None


def severity_tally(advisories: Sequence[Advisory]) -> list[tuple[str, int]]:
    """How many advisories of each severity, worst first, as `[("critical", 5), ("moderate", 36)]`, for the one-line summary on a package."""
    counts: dict[str, int] = {}
    for advisory in advisories:
        counts[advisory.label.lower()] = counts.get(advisory.label.lower(), 0) + 1
    return sorted(counts.items(), key=lambda item: -SEVERITY_RANK.get(item[0].upper(), 0))
