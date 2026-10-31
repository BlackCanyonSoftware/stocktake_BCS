"""One run of the check, and the three questions everybody asking gets the same answer to.

The command line, a project's test suite and a CI step all want the same thing: a report, and then whether it should stop the build, whether
something is worth a warning, and whether the check could be made at all.

Those rules are [ADR 0004](adr/0004-only-unsafe-findings-fail-the-build.md), and they live here exactly once. If the pytest plugin worked
them out for itself, the two would drift, and a project's test suite would start disagreeing with what `stocktake` says on the same project.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from pathlib import Path

from stocktake.config import Config, ConfigError, load_config
from stocktake.evaluate import evaluate
from stocktake.models import Dep, Report
from stocktake.readers import InstalledFn
from stocktake.readers.npm import RUN_INSTALL_NOTE
from stocktake.registries import Cache, Registries
from stocktake.report import render_text
from stocktake.scan import NO_ENVIRONMENT_NOTE, find_environment, scan, unread_manifests

# How many outdated dependencies the warning names before it stops listing and just counts. A warning nobody can read is not a warning.
NAMED_IN_WARNING = 12


def _environment_path(root: Path, named: str | None) -> Path | None:
    if named is None:
        return None
    chosen = Path(named).expanduser()
    return chosen if chosen.is_absolute() else root / chosen  # a path in a config file means a path in that project


def notes_about(deps: Sequence[Dep], environment_found: bool) -> list[str]:
    """What a reader needs to know about this run in order to judge the findings in it.

    Each note is tied to the ecosystem it is about, which is not a detail: a run against a project with no Python in it was telling its owner
    to point StockTake at a Python environment, which is advice that cannot help and makes the rest of the report look less careful than it is.
    """
    notes = []
    if not environment_found and any(d.ecosystem == "PyPI" and d.version is None and d.role != "image" for d in deps):
        # A Dockerfile's unpinned install is about what the image will build, not about which environment we looked in.
        notes.append(NO_ENVIRONMENT_NOTE)
    if any(d.ecosystem == "npm" and d.version is None for d in deps):
        notes.append(RUN_INSTALL_NOTE)
    return notes


def run_check(
    root: Path,
    *,
    config: Config | None = None,
    config_path: Path | None = None,
    environment: str | None = None,
    registries: Registries | None = None,
    installed: InstalledFn | None = None,
    today: date | None = None,
    refresh: bool = False,
) -> Report:
    """Read the project, ask the registries about what it found, and judge the answers.

    Raises `ConfigError` when the project's configuration cannot be used — including a named environment that does not exist, because someone
    who went to the trouble of naming one does not want a silent fallback to a different one.
    """
    settings = config if config is not None else load_config(root, config_path)

    environment_found = True
    lookup = installed
    if lookup is None:
        chosen = _environment_path(root, environment or settings.environment)
        found = find_environment(root, chosen)
        if chosen is not None and not found.found:
            raise ConfigError(f"no Python environment found at {chosen}")
        lookup, environment_found = found.version, found.found

    scanned = scan(root, settings, lookup)
    # Nothing to say when the caller supplied the answers itself: advice about where to find them is not ours to give.
    notes = [] if installed is not None else notes_about(scanned.deps, environment_found)

    asking = registries if registries is not None else Registries(Cache(ttl=settings.cache_ttl_seconds, refresh=refresh))
    report = evaluate(
        scanned.deps,
        asking,
        settings.policy,
        today,
        unread_manifests(root, settings),
        notes,
        settings.source,
        scanned.unreadable,
    )
    asking.flush()
    return report


def skip_reason(report: Report) -> str | None:
    """Why this check could not be made at all, or None.

    A test suite skips on this and stays green. Being unable to ask is not a finding, and turning a network blip into a red build is how a
    check like this gets switched off.
    """
    return f"cannot reach the registries ({report.offline})" if report.offline else None


def incomplete_text(report: Report) -> str | None:
    """What to say when part of the project could not be read at all, or None when all of it was.

    Kept apart from `failure_text`, which is about what was found. This is about what was never looked at, and it is the more serious of the
    two: a wrong answer gets argued with, while a missing one reads as a clean bill of health. It raises rather than skips because a test
    suite has no exit code to carry the distinction, and a warning in a pytest summary is how this became invisible in the first place
    (docs/adr/0009).
    """
    if not report.unreadable:
        return None
    count = len(report.unreadable)
    files = "file" if count == 1 else "files"
    lines = [f"StockTake could not read {count} dependency {files}, so this project was not fully checked:"]
    lines += [f"  {item.path} {item.reason}" for item in report.unreadable]
    lines.append("")
    lines.append("Fix the file, or exclude it in the project's config if it is not meant to be read.")
    return "\n".join(lines)


def update_warning(report: Report) -> str | None:
    """The "there are newer releases" message, or None when everything is current. A warning, never a failure (ADR 0004)."""
    outdated = [f for f in report.findings if f.status == "outdated"]
    if not outdated:
        return None
    listed = ", ".join(f"{f.dep.name} {f.dep.version}->{f.latest}" for f in outdated[:NAMED_IN_WARNING])
    more = " ..." if len(outdated) > NAMED_IN_WARNING else ""
    return f"{len(outdated)} dependencies have a newer release: {listed}{more}  (run `stocktake` for the full report)"


def failure_text(report: Report) -> str | None:
    """What to say when this should stop the build, or None when nothing should.

    The report itself is the message. Narrowed to what must be fixed, because a failure that also lists thirteen merely-old packages is a
    failure people learn to skim.
    """
    return "\n" + render_text(report, "vulnerable") if report.failed else None
