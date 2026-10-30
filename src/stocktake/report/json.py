"""The report a program reads.

Every field, stable keys, one object. `fix_target` is computed here because a caller that has to work out the upgrade target itself would
have to reimplement the rule about backported fixes, and get it wrong.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from stocktake.advisories import fix_target
from stocktake.models import Finding, Report


def _finding(finding: Finding) -> dict[str, Any]:
    return {
        **asdict(finding.dep),
        "status": finding.status,
        "severity": finding.severity,
        "latest": finding.latest,
        "update": finding.update,
        "note": finding.note,
        "advisories": [asdict(a) for a in finding.advisories],
        "fix_target": fix_target(finding.advisories, finding.dep.version or "0", finding.dep.ecosystem) if finding.advisories else None,
    }


def as_dict(report: Report) -> dict[str, Any]:
    """The report as plain data, for a caller that wants it in process rather than as text."""
    return {
        "date": report.today,
        "offline": report.offline,
        "failed": report.failed,
        "counts": report.counts,
        "notes": list(report.notes),
        "policy_problems": list(report.policy_problems),
        "unread_manifests": list(report.unread_manifests),
        # Manifests the project has accepted as unreadable. Not in the text report, because it asked not to be nagged — but never invisible.
        "accepted_unread": list(report.accepted_unread),
        "findings": [_finding(f) for f in report.findings],
    }


def render_json(report: Report) -> str:
    return json.dumps(as_dict(report), indent=2)
