"""Guards on StockTake itself.

Every other test proves the code does what it says. These prove the code has not quietly stopped covering something: a reader written and
never registered, a manifest kind nobody taught it to read, a dependency of its own that has gone bad. They are the tests that fail when
somebody adds something, which is the point.
"""

import ast
import re
import sys
import tomllib
from pathlib import Path

from stocktake import load_config, scan, unread_manifests
from stocktake.readers import READERS, groups

from helpers import ROOT

READER_PACKAGE = Path(__file__).resolve().parents[1] / "src" / "stocktake" / "readers"
NOT_READERS = {"__init__", "base", "pep508", "yamlish"}  # the protocol and the shared grammars (requirements, YAML), not readers


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
    found = scan(ROOT, load_config(ROOT)).deps
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


def test_the_readme_has_no_relative_link_because_it_is_also_the_pypi_page():
    """PyPI renders README.md against `pypi.org/project/stocktake/`, where `docs/adr/...` is a 404 and a banner is a broken image.

    All 28 links and both images were relative once, and `twine check` passed anyway: it validates that the description renders, not that
    anything in it points anywhere. So the check has to live here.
    """
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    links = re.findall(r"\[[^\]\n]+\]\((?!https?://|#|mailto:)([^)\s]+)\)", text)
    images = re.findall(r'(?:src|srcset)="(?!https?://)([^"]+)"', text)
    assert not links, f"relative links in the README would be dead on PyPI: {links}"
    assert not images, f"relative images in the README would be broken on PyPI: {images}"


def test_every_file_the_readme_links_into_this_repository_exists():
    """An absolute link to our own repository is still a link that can rot; it just rots silently instead of obviously."""
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    prefix = "https://github.com/BlackCanyonSoftware/stocktake_BCS/blob/main/"
    # A link to a directory is fine: `docs/adr/` is the ADR index and GitHub renders it. The target just has to be there.
    missing = [t for t in re.findall(rf"\(\s*{re.escape(prefix)}([^)\s#]+)", text) if not (ROOT / t).exists()]
    assert not missing, f"the README links to files that are not here: {missing}"


def test_the_local_matrix_script_can_still_read_the_matrix_ci_runs():
    """`tools/matrix.py` reads its Python versions out of the CI workflow so the two cannot drift. If somebody reshapes the workflow and the
    script quietly finds nothing, the local run would pass having run nothing, which is the failure it exists to prevent.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("matrix", ROOT / "tools" / "matrix.py")
    assert spec is not None and spec.loader is not None
    matrix = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(matrix)

    versions = matrix.ci_versions()
    assert versions, "no versions found in the CI matrix"
    assert all(re.fullmatch(r"3\.\d+", v) for v in versions), versions
    assert "3.11" in versions, "the floor the package claims must be in the matrix"


def test_the_local_matrix_finds_a_uv_installed_python_without_being_told_where_it_is(tmp_path, monkeypatch):
    """A Python that `uv python install` put on the machine must not look missing.

    Reported as missing it fails the run, and a person who sees "3.14 is missing" goes and reinstalls something that was already there.
    It happened here for real: uv's short-name link was dangling, so the interpreter was installed and working and still invisible.
    """
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("matrix", ROOT / "tools" / "matrix.py")
    assert spec is not None and spec.loader is not None
    matrix = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(matrix)

    windows = sys.platform == "win32"
    root = tmp_path / "uv" / "python"
    for name in ("cpython-3.14.2-windows-x86_64-none", "cpython-3.14.10-windows-x86_64-none", "cpython-3.13.3-windows-x86_64-none"):
        folder = root / name
        executable = folder / ("python.exe" if windows else "bin/python")
        executable.parent.mkdir(parents=True)
        executable.write_text("", encoding="utf-8")
    monkeypatch.setenv("APPDATA" if windows else "XDG_DATA_HOME", str(tmp_path))

    found = matrix.uv_managed("3.14")
    assert len(found) == 2, found
    assert "3.14.10" in found[0], "newest patch first"
    assert not any("3.13" in path for path in found), "only the version asked for"
