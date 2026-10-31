"""SARIF 2.1.0, so an editor and GitHub's code-scanning view can put the findings on the lines they came from.

Which findings become results is a judgement, not a translation. `vulnerable` and `yanked` are errors, and so is a policy entry that has run
out. A newer release, an unpinned install and an answer we could not get are notes. `current` is not a finding at all, and `held` is a
decision the project has already recorded and does not need shown back to it. `--only` narrows this the same way it narrows the text report.

Anything about the *run* rather than about a dependency — an environment that could not be found, registries that could not be reached — goes
in the invocation's notifications, which is where SARIF puts that kind of thing, rather than being dressed up as a finding.
"""

from __future__ import annotations

import json
from typing import Any

from stocktake._version import __version__
from stocktake.advisories import fix_target
from stocktake.models import STATUSES, Finding, Report
from stocktake.report.choices import shown_statuses

SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
SARIF_VERSION = "2.1.0"
INFORMATION_URI = "https://github.com/BlackCanyonSoftware/stocktake_BCS"

# The SARIF level for each status worth reporting. A status absent from here produces no result.
LEVELS: dict[str, str] = {
    "vulnerable": "error",
    "yanked": "error",
    "outdated": "note",
    "unpinned": "note",
    "unknown": "note",
}

POLICY_RULE = "policy"
UNREAD_RULE = "unread"
UNREADABLE_RULE = "unreadable"

RULES: dict[str, tuple[str, str]] = {
    "vulnerable": ("Vulnerable dependency", "A dependency is at a version with a known published security advisory against it."),
    "yanked": ("Withdrawn release", "A dependency is at a release its own author has since withdrawn."),
    "outdated": ("Newer release available", "A newer release of this dependency exists. Being behind is not a failure."),
    "unpinned": ("No version fixed", "Nothing fixes this dependency's version, so what gets installed depends on when."),
    "unknown": ("Could not be checked", "This dependency could not be looked up, so nothing is claimed about it either way."),
    POLICY_RULE: ("Policy entry overdue", "A decision recorded in the project's config has passed the date it was to be made again."),
    UNREAD_RULE: (
        "Manifest not read",
        "This file declares dependencies of a kind StockTake has no reader for, so nothing in it was checked.",
    ),
    UNREADABLE_RULE: (
        "Manifest could not be read",
        "StockTake has a reader for this file and it failed: the file is damaged, or not text. Nothing in it was checked, so this run does "
        "not cover the whole project.",
    ),
}


def _location(source: str) -> dict[str, Any]:
    """A SARIF location from a `path` or `path:line` source. `%SRCROOT%` is the convention GitHub resolves against the repository root."""
    path, _, line = source.rpartition(":")
    if path and line.isdigit():
        region = {"region": {"startLine": int(line)}}
    else:
        path, region = source, {}
    return {"physicalLocation": {"artifactLocation": {"uri": path, "uriBaseId": "%SRCROOT%"}, **region}}


def _message(finding: Finding) -> str:
    dep = finding.dep
    where = f"{dep.name} {dep.version}" if dep.version else dep.name

    if finding.status == "vulnerable":
        plural = "advisory" if len(finding.advisories) == 1 else "advisories"
        target = fix_target(finding.advisories, dep.version or "0", dep.ecosystem)
        advice = f"Upgrade to {target} or newer." if target else "No fixed version is named."
        listed = ", ".join(advisory.id for advisory in finding.advisories[:5])
        more = f" and {len(finding.advisories) - 5} more" if len(finding.advisories) > 5 else ""
        return f"{where} has {len(finding.advisories)} known {plural} ({listed}{more}). {advice}"

    if finding.status == "yanked":
        return f"{where} is a release its author has withdrawn. The newest release is {finding.latest}."

    if finding.status == "outdated":
        return f"{where} has a newer release: {finding.latest} ({finding.update})."

    return f"{where}: {finding.note}" if finding.note else where


def _result(finding: Finding) -> dict[str, Any]:
    dep = finding.dep
    return {
        "ruleId": finding.status,
        "level": LEVELS[finding.status],
        "message": {"text": _message(finding)},
        "locations": [_location(dep.source)],
        # Enough to recognise the same problem across runs, and to tell two declarations of one package apart.
        "partialFingerprints": {"stocktakeFinding": f"{dep.ecosystem}/{dep.name}/{finding.status}/{dep.source}"},
    }


def _rules_used(ids: list[str]) -> list[dict[str, Any]]:
    """One rule per id actually used, in a stable order. SARIF wants every ruleId a result refers to declared here."""
    order = [*STATUSES, POLICY_RULE, UNREADABLE_RULE, UNREAD_RULE]
    return [
        {
            "id": rule_id,
            "name": RULES[rule_id][0],
            "shortDescription": {"text": RULES[rule_id][0]},
            "fullDescription": {"text": RULES[rule_id][1]},
            "help": {"text": RULES[rule_id][1]},
            "defaultConfiguration": {"level": LEVELS.get(rule_id, "error" if rule_id in (POLICY_RULE, UNREADABLE_RULE) else "note")},
        }
        for rule_id in order
        if rule_id in set(ids) and rule_id in RULES
    ]


def as_sarif(report: Report, only: str = "all") -> dict[str, Any]:
    """The report as a SARIF log, as plain data."""
    shown = shown_statuses(only)
    results = [_result(f) for f in report.findings if f.status in LEVELS and f.status in shown]

    if report.policy_problems and "vulnerable" in shown:  # an overdue policy entry fails the build, so it belongs wherever failures do
        location = [_location(report.config_source)] if report.config_source else []
        results += [
            {
                "ruleId": POLICY_RULE,
                "level": "error",
                "message": {"text": problem},
                **({"locations": location} if location else {}),
                "partialFingerprints": {"stocktakeFinding": f"policy/{problem}"},
            }
            for problem in report.policy_problems
        ]

    # Never narrowed by `only`, and an error rather than a note. Everything else here is something that was found; this is a part of the
    # project that was not looked at, which is the one thing a narrowed report must not be able to hide.
    results += [
        {
            "ruleId": UNREADABLE_RULE,
            "level": "error",
            "message": {"text": f"This file could not be read, so nothing in it was checked: it {item.reason}."},
            "locations": [_location(item.path)],
            "partialFingerprints": {"stocktakeFinding": f"unreadable/{item.path}"},
        }
        for item in report.unreadable
    ]

    if "unpinned" in shown:
        results += [
            {
                "ruleId": UNREAD_RULE,
                "level": "note",
                "message": {"text": f"{name} declares dependencies of a kind StockTake has no reader for, so nothing in it was checked."},
                "locations": [_location(name)],
                "partialFingerprints": {"stocktakeFinding": f"unread/{name}"},
            }
            for name in report.unread_manifests
        ]

    notifications: list[dict[str, Any]] = [{"level": "warning", "message": {"text": note}} for note in report.notes]
    if report.unreadable:
        files = "file" if len(report.unreadable) == 1 else "files"
        notifications.append(
            {
                "level": "error",
                "message": {"text": f"{len(report.unreadable)} dependency {files} could not be read, so this run is incomplete."},
            }
        )
    if report.offline:
        notifications.append({"level": "error", "message": {"text": f"The check could not be completed: {report.offline}"}})

    return {
        "version": SARIF_VERSION,
        "$schema": SCHEMA,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "StockTake",
                        "version": __version__,
                        "informationUri": INFORMATION_URI,
                        "rules": _rules_used([str(r["ruleId"]) for r in results]),
                    }
                },
                "invocations": [
                    {
                        # False for an unreadable manifest as well as for an unreachable registry: both mean this run did not cover the
                        # project, and code scanning showing a green run for either is the failure this field exists to prevent.
                        "executionSuccessful": report.complete,
                        **({"toolExecutionNotifications": notifications} if notifications else {}),
                    }
                ],
                "results": results,
            }
        ],
    }


def render_sarif(report: Report, only: str = "all") -> str:
    return json.dumps(as_sarif(report, only), indent=2)
