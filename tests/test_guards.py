"""Guards on StockTake itself.

Every other test proves the code does what it says. These prove the code has not quietly stopped covering something: a reader written and
never registered, a manifest kind nobody taught it to read, a dependency of its own that has gone bad. They are the tests that fail when
somebody adds something, which is the point.
"""

import ast
import sys
import tomllib
from pathlib import Path

from stocktake import load_config, scan, unread_manifests
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
    assert {d.name for d in found} >= {"pytest", "ruff", "mypy"}, "its own dev dependencies, from pyproject.toml"
    assert {d.name for d in found} >= {"actions/checkout", "actions/setup-python"}, "and the actions its own CI pins"
    assert {d.source.split(":")[0] for d in found} == {"pyproject.toml", ".github/workflows/ci.yml"}


def test_the_core_imports_nothing_outside_the_standard_library():
    """ADR 0001 is a promise to anyone installing this. A new third-party import in the core would break it silently.

    Two exceptions, both deliberate: `packaging`, which is only ever imported inside a try/except as an optional nicety, and `pytest` in the
    pytest plugin, which is only ever imported under pytest. Anywhere else, an import of either is a bug.
    """
    allowed = {"stocktake", "packaging", "__future__"}
    only_in = {"pytest_plugin.py": {"pytest"}, "dependency_test_template.py": {"pytest"}}
    stdlib = set(sys.stdlib_module_names)

    offenders: dict[str, set[str]] = {}
    for path in (ROOT / "src" / "stocktake").rglob("*.py"):
        permitted = stdlib | allowed | only_in.get(path.name, set())
        # Read with the parser rather than by matching lines: `vendor.py`'s docstring shows an example `import stocktake_vendored`, which a
        # line scan counts as an import. It also means an import inside a function is seen, which is where the optional ones live.
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                roots = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                roots = [(node.module or "").split(".")[0]] if node.level == 0 else []
            else:
                continue
            for root_module in roots:
                if root_module and root_module not in permitted:
                    offenders.setdefault(str(path.relative_to(ROOT)), set()).add(root_module)

    assert offenders == {}, f"the core must not depend on anything third-party: {offenders}"


def test_this_project_runs_its_own_check_through_its_own_plugin():
    """The live check against the real registries is not written out here: `stocktake = true` in pyproject.toml makes the plugin add it.

    That is deliberate. StockTake's own suite is the plugin's first consumer, so a plugin that stops working breaks this suite before it
    reaches anybody else's. This test only guards the arrangement, so that switching the plugin off cannot pass unnoticed.
    """
    settings = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert settings["tool"]["pytest"]["ini_options"].get("stocktake") is True, "this project should check itself through its own plugin"
    assert settings["project"]["entry-points"]["pytest11"]["stocktake"] == "stocktake.pytest_plugin"
