"""One line, for a status bar or the name of a CI step.

The verdict comes first, because that is the only part that will survive being truncated into a 40-character status bar. No date: whoever is
reading a status bar knows what day it is, and the exit code already carries the answer.

The hard part of one line is what it leaves out. This one used to say "nothing unsafe, 0 outdated (0 checked)" for a project whose only
manifest it had failed to read, and "nothing unsafe" for five dependencies it had not resolved a single version for. A line that is the only
thing anyone reads has to be either true or silent, so a run that did not cover the project says so before it says anything else
(docs/adr/0009).
"""

from __future__ import annotations

from stocktake.models import Report


def _incomplete(report: Report) -> str | None:
    """Why this run does not cover the project, in a few words, or None when it does."""
    if report.offline:
        return f"could not check ({report.offline})"
    if report.unreadable:
        files = "file" if len(report.unreadable) == 1 else "files"
        return f"{len(report.unreadable)} dependency {files} could not be read"
    if report.nothing_was_checked:
        files = "file" if len(report.unread_manifests) == 1 else "files"
        return f"nothing checked, {len(report.unread_manifests)} dependency {files} have no reader yet"
    return None


def _unsafe(report: Report) -> list[str]:
    counts = report.counts
    parts = []
    if counts["vulnerable"]:
        parts.append(f"{counts['vulnerable']} vulnerable")
    if report.withdrawn_count:
        parts.append(f"{report.withdrawn_count} withdrawn")
    if report.policy_problems:
        entries = "entry" if len(report.policy_problems) == 1 else "entries"
        parts.append(f"{len(report.policy_problems)} policy {entries} overdue")
    return parts


def _unresolved(report: Report) -> list[str]:
    """Why some rows reached no verdict. Named, because the alternative is counting them as checked.

    An `unpinned` or `unknown` finding is a dependency StockTake looked at and could say nothing about: nothing fixed a version, or the
    registry had no answer. Rolling those into the "checked" total is how "nothing unsafe, 0 outdated (5 checked)" came to be printed for a
    project where not one of the five had been resolved to a version.
    """
    counts = report.counts
    parts = []
    if counts["unpinned"]:
        parts.append(f"{counts['unpinned']} unpinned")
    if counts["unknown"]:
        parts.append(f"{counts['unknown']} not found")
    if report.unread_manifests:
        files = "file" if len(report.unread_manifests) == 1 else "files"
        parts.append(f"{len(report.unread_manifests)} unread {files}")
    return parts


def _checked(report: Report) -> str:
    """The parenthesised count: how much was actually checked, and what is unaccounted for.

    `(14 checked)` while every row reached a verdict, `(1 of 2 checked, 1 not found)` when one did not. The "of" form only appears when the
    two numbers differ, because `(14 of 14 checked)` makes a reader look for the discrepancy there isn't one of.
    """
    total = len(report.findings)
    resolved = total - report.counts["unpinned"] - report.counts["unknown"]
    counted = f"{total} checked" if resolved == total else f"{resolved} of {total} checked"
    return f"({', '.join([counted, *_unresolved(report)])})"


def _accepted(report: Report) -> list[str]:
    """Vulnerabilities the project has signed for. Named in the one line, because that line is all a CI step title shows.

    Not part of `_unsafe`: these fail nothing, which is the point of accepting them. Still said out loud, because a carried vulnerability
    that has become invisible is indistinguishable from one nobody knows about (docs/adr/0011).
    """
    count = report.counts["accepted"]
    return [f"{count} accepted"] if count else []


def render_summary(report: Report) -> str:
    """The whole report in one line."""
    total = len(report.findings)
    resolved = total - report.counts["unpinned"] - report.counts["unknown"]

    incomplete = _incomplete(report)
    unsafe = _unsafe(report)

    # An incomplete run says so even when it did find something unsafe, with the finding named after it. The caveat is what a truncated line
    # has to keep: a finding from a run that did not cover the project is a floor, not the answer.
    if incomplete:
        return f"stocktake: {', '.join([incomplete, *unsafe, *_accepted(report)])}"

    if unsafe:
        return f"stocktake: {', '.join([*unsafe, *_accepted(report)])} {_checked(report)}"

    if not total:
        # A project whose manifests are all of a kind nothing reads yet never reaches here: that is an incomplete run, and `_incomplete`
        # above answers it. This is a project with no dependency file at all, which is a different and much rarer thing.
        return "stocktake: nothing found to check"

    # "nothing unsafe" is a claim about what was actually resolved, so it is not made at all when nothing was.
    # "nothing unsafe" would be a lie with an accepted finding in hand, so the wording changes rather than the count being left out.
    carried = _accepted(report)
    unqualified = f"nothing unsafe, {report.counts['outdated']} outdated"
    qualified = f"nothing unsafe beyond what is accepted, {report.counts['outdated']} outdated"
    verdict = (qualified if carried else unqualified) if resolved else "nothing could be checked"
    return f"stocktake: {', '.join([verdict, *carried])} {_checked(report)}"
