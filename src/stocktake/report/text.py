"""The report a person reads.

The layout is the design, not decoration (docs/DESIGN.md): what must be fixed comes first, `current` collapses to a count so a long clean
list cannot bury a short dirty one, the source location leads every row so the output stays greppable, and every "there is more than this"
names the exact command that shows the rest.

No colour, no box drawing, no spinners. This text lands in pytest summaries, CI logs and pipes, where all of that becomes noise — and
severity carried by the word rather than the colour is the accessible choice anyway.
"""

from __future__ import annotations

from collections.abc import Sequence

from stocktake.advisories import fix_target, severity_tally
from stocktake.models import STATUSES, Finding, Report
from stocktake.report.choices import shown_statuses

_HINT = "stocktake --only vulnerable --all-advisories"


def _source_width(findings: Sequence[Finding]) -> int:
    """Wide enough for the paths actually present, within reason, so rows line up without the file names being cut off."""
    longest = max((len(f.dep.source) for f in findings), default=0)
    return max(24, min(longest + 2, 44))


def _rows(report: Report, status: str) -> list[Finding]:
    """The findings of one status, in the order they should be acted on.

    Within `vulnerable` that is worst severity first, then most advisories: the list is read from the top and whoever reads it should meet the
    critical finding before a low one, not whichever happens to sit in a file named `a`. Every other status keeps file order, so the report
    reads the way the project is laid out.
    """
    rows = [f for f in report.findings if f.status == status]
    if status != "vulnerable":  # no other status carries a severity to sort by
        return sorted(rows, key=lambda f: (f.dep.source, f.dep.name))
    return sorted(rows, key=lambda f: (-f.rank, -len(f.advisories), f.dep.source, f.dep.name))


def _headline(report: Report) -> str:
    counts = report.counts
    line = (
        f"Dependency check {report.today}: {len(report.findings)} checked, "
        f"{counts['vulnerable']} vulnerable, {report.withdrawn_count} withdrawn, {counts['outdated']} outdated, {counts['unpinned']} unpinned"
    )
    # Both of these say the report below is partial, which matters more than anything in it, so both go on the first line.
    if report.offline:
        line += f"  [{report.offline}]"
    if report.unreadable:
        files = "file" if len(report.unreadable) == 1 else "files"
        line += f"  [{len(report.unreadable)} {files} could not be read]"
    return line


def _vulnerable_row(finding: Finding, width: int, all_advisories: bool, top: int) -> list[str]:
    dep = finding.dep
    tally = ", ".join(f"{count} {label}" for label, count in severity_tally(finding.advisories))
    plural = "advisory" if len(finding.advisories) == 1 else "advisories"
    target = fix_target(finding.advisories, dep.version or "0", dep.ecosystem)
    fix = f"; upgrade to {target} or newer" if target else "; no fixed version named"
    # Two spaces after the version: "pillow 9.0.0 52 advisories" otherwise reads as though the version were "9.0.0 52".
    withdrawn = "; withdrawn by its author" if finding.withdrawn else ""
    lines = [f"  {dep.source:<{width}} {dep.name} {dep.version}  {len(finding.advisories)} {plural} ({tally}){fix}{withdrawn}"]

    shown = finding.advisories if all_advisories else finding.advisories[:top]
    lines += [f"      {a.id} {a.label}: {a.summary}" for a in shown]
    if len(shown) < len(finding.advisories):
        lines.append(f"      ... and {len(finding.advisories) - len(shown)} more ({_HINT})")
    return lines


def render_text(report: Report, only: str = "all", all_advisories: bool = False, top: int = 5) -> str:
    """The whole report as text. `only` narrows it to what needs action; `top` is how many advisories a package shows before they are counted."""
    shown = shown_statuses(only)
    width = _source_width(report.findings)
    lines = [_headline(report)]

    if not report.findings:
        # Silence looks like success, and it almost never is. A project with no dependencies at all is far rarer than a misconfigured scan.
        # Which explanation to offer depends on why: pointing at the excludes is unhelpful advice when the real reason is listed below.
        if report.unreadable:
            why = "Every dependency file found could not be read, so nothing could be checked. The reasons are below."
        elif report.unread_manifests:
            why = (
                "Nothing could be checked: every dependency file found is of a kind StockTake has no reader for yet. They are named below."
            )
        else:
            why = "Nothing was found to check. If that is a surprise, the project's excludes or enabled ecosystems are the place to look."
        lines += ["", why]

    # Anything that affects how much of the report can be trusted comes before the findings themselves, worst first. An unreadable manifest
    # leads, because it is the one caveat that makes everything after it an incomplete answer rather than a qualified one.
    if report.unreadable:
        lines += ["", "UNREADABLE (StockTake meant to read these and could not, so nothing in them was checked)"]
        lines += [f"  {item.path} {item.reason}" for item in report.unreadable]

    for note in report.notes:
        lines += ["", f"NOTE: {note}"]

    for problem in report.policy_problems:
        lines += ["", f"POLICY: {problem}"]

    if report.unread_manifests:
        lines += ["", "UNREAD (StockTake has no reader for these yet, so nothing in them was checked)"]
        lines += [f"  {name}" for name in report.unread_manifests]

    for status in STATUSES:
        rows = _rows(report, status)
        if not rows or status not in shown:
            continue
        if status == "current":
            lines += ["", f"CURRENT: {len(rows)} up to date"]
            continue
        lines += ["", status.upper() + (" (fix these)" if status in ("vulnerable", "yanked") else "")]
        for finding in rows:
            if status == "vulnerable":
                lines += _vulnerable_row(finding, width, all_advisories, top)
                continue
            dep = finding.dep
            row = f"  {dep.source:<{width}} {dep.name} {dep.version or '(none)'}"
            if finding.latest and status in ("outdated", "held"):
                row += f" -> {finding.latest} ({finding.update})"
            lines.append(row + (f"  {finding.note}" if finding.note else ""))

    return "\n".join(lines)
