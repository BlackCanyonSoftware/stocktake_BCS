"""The judgement: a list of dependencies plus what the registries say, turned into a report.

Pure, given a `Registries` to ask. It constructs nothing, opens nothing and writes nothing, which is what makes the whole decision table
testable without a network (docs/ARCHITECTURE.md).

The decision table itself is [ADR 0004](adr/0004-only-unsafe-findings-fail-the-build.md) and is the heart of the product: vulnerable and
withdrawn releases fail, a newer release warns, and anything we could not find out is `unknown` rather than clean.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime

from stocktake.models import Advisory, Dep, Finding, Report, Unread, normalize
from stocktake.policy import Policy
from stocktake.registries import Coordinate, OfflineError, RateLimited, Registries, Versions
from stocktake.versions import is_newer, update_kind

# Enough to make a run of a few hundred dependencies quick, few enough to stay a polite guest on a free public service.
MAX_LOOKUPS_AT_ONCE = 8

# What an unpinned dependency means depends on who declared it, and the note has to say which.
UNPINNED_NOTES = {
    "image": "no version is pinned: whatever is newest when the image is built",
    "ci": "no version is pinned: whatever is newest when the workflow runs",
}
UNPINNED_DEFAULT = "not installed in this environment, and no version is pinned"

# A lookup either answers, or explains itself. The explanation is kept as a string so one failure cannot poison the whole run.
Answer = Versions | str | None


def _lookup(registries: Registries, ecosystem: str, name: str) -> Answer:
    if ecosystem not in registries.ecosystems:
        return f"no registry client for {ecosystem}"
    try:
        return registries.latest(ecosystem, name)
    except RateLimited as exc:
        return f"rate limited: {exc}"
    except OfflineError as exc:
        return f"offline: {exc}"


def _ask_about_every_name(deps: Sequence[Dep], registries: Registries) -> dict[tuple[str, str], Answer]:
    """One lookup per distinct name, several at a time. Two Dockerfiles pinning the same package ask about it once."""
    distinct = sorted({(d.ecosystem, d.name) for d in deps})
    if not distinct:
        return {}
    with ThreadPoolExecutor(max_workers=min(MAX_LOOKUPS_AT_ONCE, len(distinct))) as pool:
        answers = pool.map(lambda key: _lookup(registries, key[0], key[1]), distinct)
        return dict(zip(distinct, answers, strict=True))


def _unreachable(answers: Mapping[tuple[str, str], Answer]) -> str | None:
    """Why the run is offline, or None.

    Offline means *every* lookup failed to reach anything. One failure among many is that one name's problem, not the run's, and saying
    otherwise would throw away a perfectly good report.
    """
    failures = [a for a in answers.values() if isinstance(a, str) and a.startswith("offline")]
    return failures[0] if failures and len(failures) == len(answers) else None


def _judge(dep: Dep, answer: Answer, advisories: tuple[Advisory, ...], held: frozenset[str], hold_reason: str) -> Finding:
    """One dependency's finding. The whole decision table, in the order the questions have to be asked."""
    if dep.version is None:
        # The reader's own reason wins: it knows whether a version is missing because nothing pins one or because what pins it is a commit.
        return Finding(dep, "unpinned", "info", note=dep.note or UNPINNED_NOTES.get(dep.role, UNPINNED_DEFAULT))
    if answer is None:
        return Finding(dep, "unknown", "info", note="not found on the registry")
    if isinstance(answer, str):
        return Finding(dep, "unknown", "info", note=answer)
    if advisories:
        plural = "advisory" if len(advisories) == 1 else "advisories"
        return Finding(dep, "vulnerable", "fail", answer.latest, advisories=advisories, note=f"{len(advisories)} known {plural}")
    if dep.version in answer.withdrawn:
        return Finding(dep, "yanked", "fail", answer.latest, note="this release was withdrawn by its author")
    if is_newer(answer.latest, dep.version, dep.ecosystem, moving=dep.moving):
        kind = update_kind(answer.latest, dep.version)
        if normalize(dep.name) in held:
            return Finding(
                dep,
                "held",
                "info",
                answer.latest,
                kind,
                note=f"held back on purpose: {hold_reason}" if hold_reason else "held back on purpose",
            )
        return Finding(dep, "outdated", "warn", answer.latest, kind)
    return Finding(dep, "current", "ok", answer.latest)


def evaluate(
    deps: Sequence[Dep],
    registries: Registries,
    policy: Policy | None = None,
    today: date | None = None,
    unread: Unread | None = None,
    notes: Sequence[str] = (),
) -> Report:
    """What one run of the check found."""
    today = today or datetime.now(UTC).date()
    unread = unread or Unread()
    policy = policy or Policy()
    ignored = policy.ignored_advisories(today)
    held = policy.held_packages(today)

    answers = _ask_about_every_name(deps, registries)
    offline = _unreachable(answers)

    advisories: Mapping[Coordinate, tuple[Advisory, ...]] = {}
    if not offline:
        wanted = sorted({(d.ecosystem, d.name, d.version) for d in deps if d.version is not None})
        try:
            advisories = registries.advisories(wanted)
        except OfflineError as exc:
            offline = f"offline: {exc}"  # the names resolved but advisories could not be had: the run knows too little to pass
        except RateLimited:
            pass  # no advisory information this run; every finding stays at worst `outdated`, never falsely `current`

    findings = []
    for dep in deps:
        against = advisories.get((dep.ecosystem, normalize(dep.name), dep.version)) if dep.version is not None else None
        relevant = tuple(a for a in (against or ()) if a.id not in ignored and not (set(a.aliases) & ignored))
        findings.append(_judge(dep, answers.get((dep.ecosystem, dep.name)), relevant, held, policy.hold_reason(dep.name, today)))

    return Report(
        findings=tuple(findings),
        policy_problems=policy.problems(today),
        offline=offline,
        today=today.isoformat(),
        unread_manifests=unread.reported,
        accepted_unread=unread.accepted,
        notes=tuple(notes),
    )
