"""Guards on StockTake itself.

Every other test proves the code does what it says. These prove the code has not quietly stopped covering something: a reader written and
never registered, a manifest kind nobody taught it to read, a dependency of its own that has gone bad. They are the tests that fail when
somebody adds something, which is the point.
"""

import os
import warnings
from pathlib import Path

import pytest

from stocktake import DependencyUpdateAvailable, Registries, evaluate, load_config, render_text, scan, unread_manifests
from stocktake.readers import READERS, groups

from helpers import ROOT

READER_PACKAGE = Path(__file__).resolve().parents[1] / "src" / "stocktake" / "readers"
NOT_READERS = {"__init__", "base", "pep508"}  # the protocol and the shared requirement grammar, not readers themselves


def test_every_reader_module_is_registered_so_none_can_be_written_and_never_run():
    on_disk = {path.stem for path in READER_PACKAGE.glob("*.py")} - NOT_READERS
    registered = {reader.read.__module__.rsplit(".", 1)[-1] for reader in READERS}
    assert on_disk == registered, f"these reader modules are not imported in readers/__init__.py: {on_disk - registered}"


def test_every_registered_reader_belongs_to_a_group_and_describes_itself():
    assert groups(), "no readers at all would make every report empty and clean"
    for reader in READERS:
        assert reader.group in groups()
        assert reader.description, f"{reader.read.__module__} has no description"


def test_this_project_has_no_manifest_of_a_kind_it_cannot_read_itself():
    """If this fails, StockTake has grown a dependency manifest it would not report on. Teach it to read that kind, or exclude it in config."""
    assert unread_manifests(ROOT, load_config(ROOT)).reported == ()


def test_this_projects_own_dependencies_are_found_at_all():
    """A scan of this repository that found nothing would make every other green test here meaningless."""
    found = scan(ROOT, load_config(ROOT))
    assert {d.name for d in found} >= {"pytest", "ruff", "mypy"}
    assert all(d.source == "pyproject.toml" for d in found)


def test_the_core_imports_nothing_outside_the_standard_library():
    """ADR 0001 is a promise to anyone installing this. A new third-party import in the core would break it silently."""
    allowed = {"stocktake", "packaging"}  # packaging only ever inside a try/except, as an optional nicety
    stdlib = set(__import__("sys").stdlib_module_names)
    offenders = {}
    for path in (ROOT / "src" / "stocktake").rglob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            root_module = stripped.split()[1].split(".")[0]
            if root_module not in stdlib | allowed:
                offenders[str(path.relative_to(ROOT))] = root_module
    assert offenders == {}, f"the core must not depend on anything third-party: {offenders}"


@pytest.mark.network
def test_this_projects_own_dependencies_have_no_known_vulnerabilities():
    """The live check, run against the real registries as part of the suite.

    Fails on a known vulnerability, a withdrawn release or an overdue policy entry. A newer release is a warning in the summary, never a
    failure. Skipped, not failed, when the registries cannot be reached or STOCKTAKE_OFFLINE is set.
    """
    if os.environ.get("STOCKTAKE_OFFLINE"):
        pytest.skip("STOCKTAKE_OFFLINE is set")

    config = load_config(ROOT)
    asking = Registries()
    report = evaluate(scan(ROOT, config), asking, config.policy, unread=unread_manifests(ROOT, config))
    asking.flush()

    if report.offline:
        pytest.skip(f"cannot reach the registries ({report.offline})")

    outdated = [f for f in report.findings if f.status == "outdated"]
    if outdated:
        listed = ", ".join(f"{f.dep.name} {f.dep.version}->{f.latest}" for f in outdated[:12])
        warnings.warn(
            DependencyUpdateAvailable(
                f"{len(outdated)} dependencies have a newer release: {listed}{' ...' if len(outdated) > 12 else ''}  (run `stocktake` for the full report)"
            ),
            stacklevel=1,
        )

    assert not report.failed, "\n" + render_text(report, "vulnerable")
