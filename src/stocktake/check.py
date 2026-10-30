"""One run of the check, and the three questions everybody asking gets the same answer to.

The command line, a project's test suite and a CI step all want the same thing: a report, and then whether it should stop the build, whether
something is worth a warning, and whether the check could be made at all.

Those rules are [ADR 0004](adr/0004-only-unsafe-findings-fail-the-build.md), and they live here exactly once. If the pytest plugin worked
them out for itself, the two would drift, and a project's test suite would start disagreeing with what `stocktake` says on the same project.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from stocktake.config import Config, ConfigError, load_config
from stocktake.evaluate import evaluate
from stocktake.models import Report
from stocktake.readers import InstalledFn
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

    lookup = installed
    notes: list[str] = []
    if lookup is None:
        chosen = _environment_path(root, environment or settings.environment)
        found = find_environment(root, chosen)
        if chosen is not None and not found.found:
            raise ConfigError(f"no Python environment found at {chosen}")
        lookup = found.version
        if not found.found:
            notes.append(NO_ENVIRONMENT_NOTE)

    deps = scan(root, settings, lookup)
    # Only worth saying when something actually went unresolved because of it. A Dockerfile's unpinned install is about the image, not us.
    if notes and not any(d.version is None and d.role != "image" for d in deps):
        notes.clear()

    asking = registries if registries is not None else Registries(Cache(ttl=settings.cache_ttl_seconds, refresh=refresh))
    report = evaluate(deps, asking, settings.policy, today, unread_manifests(root, settings), notes)
    asking.flush()
    return report


def skip_reason(report: Report) -> str | None:
    """Why this check could not be made at all, or None.

    A test suite skips on this and stays green. Being unable to ask is not a finding, and turning a network blip into a red build is how a
    check like this gets switched off.
    """
    return f"cannot reach the registries ({report.offline})" if report.offline else None


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
