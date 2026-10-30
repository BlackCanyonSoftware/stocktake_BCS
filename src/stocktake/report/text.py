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

ONLY_CHOICES: tuple[str, ...] = ("all", "outdated", "vulnerable")

_SHOWN_FOR = {
    "all": set(STATUSES),
    "outdated": {"vulnerable", "yanked", "outdated"},
    "vulnerable": {"vulnerable", "yanked"},
}

_HINT = "stocktake --only vulnerable --all-advisories"


def _source_width(findings: Sequence[Finding]) -> int:
    """Wide enough for the paths actually present, within reason, so rows line up without the file names being cut off."""
    longest = max((len(f.dep.source) for f in findings), default=0)
    return max(24, min(longest + 2, 44))


def _rows(report: Report, status: str) -> list[Finding]:
    """The findings of one status, ordered by where they came from, so the report reads the way the project is laid out."""
    return sorted((f for f in report.findings if f.status == status), key=lambda f: (f.dep.source, f.dep.name))


def _headline(report: Report) -> str:
    counts = report.counts
    line = (
        f"Dependency check {report.today}: {len(report.findings)} checked, "
        f"{counts['vulnerable']} vulnerable, {counts['yanked']} withdrawn, {counts['outdated']} outdated, {counts['unpinned']} unpinned"
    )
    return f"{line}  [{report.offline}]" if report.offline else line


def _vulnerable_row(finding: Finding, width: int, all_advisories: bool, top: int) -> list[str]:
    dep = finding.dep
    tally = ", ".join(f"{count} {label}" for label, count in severity_tally(finding.advisories))
    plural = "advisory" if len(finding.advisories) == 1 else "advisories"
    target = fix_target(finding.advisories, dep.version or "0")
    fix = f"; upgrade to {target} or newer" if target else "; no fixed version named"
    # Two spaces after the version: "pillow 9.0.0 52 advisories" otherwise reads as though the version were "9.0.0 52".
    lines = [f"  {dep.source:<{width}} {dep.name} {dep.version}  {len(finding.advisories)} {plural} ({tally}){fix}"]

    shown = finding.advisories if all_advisories else finding.advisories[:top]
    lines += [f"      {a.id} {a.label}: {a.summary}" for a in shown]
    if len(shown) < len(finding.advisories):
        lines.append(f"      ... and {len(finding.advisories) - len(shown)} more ({_HINT})")
    return lines


def render_text(report: Report, only: str = "all", all_advisories: bool = False, top: int = 5) -> str:
    """The whole report as text. `only` narrows it to what needs action; `top` is how many advisories a package shows before they are counted."""
    shown = _SHOWN_FOR.get(only, _SHOWN_FOR["all"])
    width = _source_width(report.findings)
    lines = [_headline(report)]

    if not report.findings:
        # Silence looks like success, and it almost never is. A project with no dependencies at all is far rarer than a misconfigured scan.
        lines += [
            "",
            "Nothing was found to check. If that is a surprise, the project's excludes or enabled ecosystems are the place to look.",
        ]

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
