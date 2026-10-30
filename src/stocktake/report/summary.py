"""One line, for a status bar or the name of a CI step.

The verdict comes first, because that is the only part that will survive being truncated into a 40-character status bar. No date: whoever is
reading a status bar knows what day it is, and the exit code already carries the answer.
"""

from __future__ import annotations

from stocktake.models import Report


def render_summary(report: Report) -> str:
    """The whole report in one line."""
    counts = report.counts
    total = len(report.findings)

    if report.offline:
        return f"stocktake: could not check ({report.offline})"

    if report.failed:
        parts = []
        if counts["vulnerable"]:
            parts.append(f"{counts['vulnerable']} vulnerable")
        if counts["yanked"]:
            parts.append(f"{counts['yanked']} withdrawn")
        if report.policy_problems:
            entries = "entry" if len(report.policy_problems) == 1 else "entries"
            parts.append(f"{len(report.policy_problems)} policy {entries} overdue")
        return f"stocktake: {', '.join(parts)} ({total} checked)"

    if not total:
        return "stocktake: nothing found to check"

    return f"stocktake: nothing unsafe, {counts['outdated']} outdated ({total} checked)"
