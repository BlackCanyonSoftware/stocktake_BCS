"""The report a program reads.

Every field, stable keys, one object. `fix_target` is computed here because a caller that has to work out the upgrade target itself would
have to reimplement the rule about backported fixes, and get it wrong.

Two fields exist for the benefit of whoever automates against this. `schema_version` is bumped when a key changes meaning or disappears, so a
script can refuse a shape it does not know rather than silently reading a renamed field as absent. `complete` is the one field a gate should
read first: `failed: false` on its own has always been ambiguous between "this project is fine" and "this run did not manage to look", and a
machine reader cannot tell those apart from a prose note.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from stocktake._version import __version__
from stocktake.advisories import fix_target
from stocktake.models import Finding, Report
from stocktake.report.choices import shown_statuses

# Bumped whenever a key is removed or changes meaning. Adding a key does not bump it: a reader that ignores unknown keys keeps working.
SCHEMA_VERSION = 1


def _finding(finding: Finding) -> dict[str, Any]:
    return {
        **asdict(finding.dep),
        "status": finding.status,
        "severity": finding.severity,
        "latest": finding.latest,
        "update": finding.update,
        "note": finding.note,
        # True whenever the registry says this exact release was withdrawn, including when `status` is `vulnerable` because advisories are
        # the more actionable of the two. Reading it off the status alone undercounts.
        "withdrawn": finding.withdrawn,
        "advisories": [asdict(a) for a in finding.advisories],
        "fix_target": fix_target(finding.advisories, finding.dep.version or "0", finding.dep.ecosystem) if finding.advisories else None,
    }


def _ordered(report: Report, only: str) -> list[Finding]:
    """The findings a narrowed report shows, worst first.

    The same order the text report uses, for the same reason: a consumer that takes the first few findings should get the worst few.
    """
    shown = shown_statuses(only)
    rows = [f for f in report.findings if f.status in shown]
    return sorted(rows, key=lambda f: (f.severity != "fail", -f.rank, -len(f.advisories), f.dep.source, f.dep.name))


def as_dict(report: Report, only: str = "all") -> dict[str, Any]:
    """The report as plain data, for a caller that wants it in process rather than as text."""
    return {
        "schema_version": SCHEMA_VERSION,
        "stocktake_version": __version__,
        "date": report.today,
        # Whether this run actually covers the project. False when the registries could not be reached or a manifest could not be read, and
        # the field to gate on: a clean `failed` from an incomplete run means nothing.
        "complete": report.complete,
        "offline": report.offline,
        "failed": report.failed,
        "only": only,
        "counts": report.counts,
        # Dependencies at a withdrawn release, however they are classified. `counts["yanked"]` counts only those with no advisory as well.
        "withdrawn_count": report.withdrawn_count,
        "notes": list(report.notes),
        "config_source": report.config_source,
        "policy_problems": list(report.policy_problems),
        # Manifests StockTake meant to read and could not. Never narrowed by `only`: it is why the rest of the report is partial.
        "unreadable": [asdict(item) for item in report.unreadable],
        "unread_manifests": list(report.unread_manifests),
        # Manifests the project has accepted as unreadable. Not in the text report, because it asked not to be nagged — but never invisible.
        "accepted_unread": list(report.accepted_unread),
        "findings": [_finding(f) for f in _ordered(report, only)],
    }


def render_json(report: Report, only: str = "all") -> str:
    return json.dumps(as_dict(report, only), indent=2)
