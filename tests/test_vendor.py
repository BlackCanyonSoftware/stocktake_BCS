"""The single-file copy: that it is current, that it behaves like the package, and that the generator refuses to emit something broken.

The copy is a second way to run the same code, which is exactly the arrangement that drifts. Three things hold it in place: the committed
file must be what the generator produces right now, the generated module must reach the same verdict as the package on the same project, and
the generator must refuse rather than emit anything it cannot prove safe.
"""

import ast
import importlib.util
import json
import sys

import pytest

from stocktake.check import run_check
from stocktake.registries import Cache, Registries
from stocktake.report import render_json, render_sarif, render_text
from stocktake.vendor import (
    PACKAGE_ROOT,
    VENDORED_NAME,
    VendorError,
    collisions,
    core_paths,
    dependency_order,
    missing_dependencies,
    render,
    write,
)
from stocktake.vendor import _read as read_module

from helpers import ROOT, TODAY, FakeNet, advisory_detail

COMMITTED = ROOT / "vendored" / VENDORED_NAME

PROJECT = {
    "Dockerfile": "FROM python:3.12\nRUN pip install --no-cache-dir pillow==9.0.0 ruff\n",
    "pyproject.toml": '[project]\nname = "x"\ndependencies = ["httpx>=0.27"]\n',
    "requirements-dev.txt": "pytest==7.4.0\n",
    "package.json": '{"name": "x", "dependencies": {"left-pad": "1.3.0", "koffi": "^3.0.0"}}',
    ".github/workflows/ci.yml": "jobs:\n  a:\n    steps:\n      - uses: actions/checkout@v4\n      - uses: other/thing@main\n",
    "go.mod": "module x\n",
}


def fixture_project(tmp_path):
    for name, text in PROJECT.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


def fake_network():
    return FakeNet(
        pypi={"pillow": ("13.0.0", []), "httpx": ("0.28.1", []), "pytest": ("9.2.0", []), "ruff": ("0.17.3", [])},
        npm={"left-pad": "1.3.0", "koffi": "3.3.9"},
        github={"actions/checkout": "v7.0.1", "other/thing": "v2.0.0"},
        osv={("pillow", "9.0.0"): ["GHSA-1"]},
        details={"GHSA-1": advisory_detail("a real problem", "CRITICAL", fixed=["13.0.0"], package="pillow")},
    )


_loaded = None


def vendored():
    """The committed copy, loaded as its own module. Loaded once: executing it registers readers in its own registry.

    It goes into `sys.modules` before it is executed, which an ordinary `import stocktake_vendored` would do anyway. Skipping that step
    breaks `@dataclass` under postponed annotations, because the dataclass machinery looks the module up there to resolve `ClassVar`.
    """
    global _loaded
    if _loaded is None:
        name = "stocktake_vendored_under_test"
        spec = importlib.util.spec_from_file_location(name, COMMITTED)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        _loaded = module
    return _loaded


# ---------- it is current ----------
def test_the_committed_copy_is_exactly_what_the_generator_produces_now():
    """If this fails, somebody changed the core and did not run `stocktake vendor vendored/`. The copy is generated, never edited."""
    assert COMMITTED.is_file(), f"{COMMITTED} is missing; run `stocktake vendor vendored/`"
    assert COMMITTED.read_text(encoding="utf-8") == render(), (
        "the committed copy is out of date; regenerate it with `stocktake vendor vendored/`"
    )


def test_generating_it_twice_gives_the_same_bytes():
    # Nothing in the output may depend on a timestamp, a dict ordering or a filesystem ordering, or the guard above would fail at random.
    assert render() == render()


# ---------- it behaves like the package ----------
def test_the_copy_reaches_the_same_verdict_as_the_package(tmp_path):
    """The claim that matters. The whole pipeline, on a project exercising five readers, compared through all three report formats."""
    project = fixture_project(tmp_path)
    copy = vendored()

    package_report = run_check(
        project,
        registries=Registries(Cache(fetch=fake_network(), path=tmp_path / "a.json")),
        installed=lambda name: None,
        today=TODAY,
    )
    copy_report = copy.run_check(
        project,
        registries=copy.Registries(copy.Cache(fetch=fake_network(), path=tmp_path / "b.json")),
        installed=lambda name: None,
        today=TODAY,
    )

    assert render_text(package_report) == copy.render_text(copy_report)
    assert json.loads(render_json(package_report)) == json.loads(copy.render_json(copy_report))
    assert json.loads(render_sarif(package_report)) == json.loads(copy.render_sarif(copy_report))


def test_the_comparison_above_is_actually_exercising_something(tmp_path):
    """A guard on the guard: if the fixture stopped producing findings, the equivalence test would pass by saying nothing."""
    report = run_check(
        fixture_project(tmp_path),
        registries=Registries(Cache(fetch=fake_network(), path=tmp_path / "c.json")),
        installed=lambda name: None,
        today=TODAY,
    )
    counts = report.counts
    assert counts["vulnerable"] >= 1 and counts["outdated"] >= 1 and counts["unpinned"] >= 1 and counts["current"] >= 1
    assert report.unread_manifests == ("go.mod",)
    assert {f.dep.ecosystem for f in report.findings} == {"PyPI", "npm", "GitHub"}


def test_the_copy_offers_the_api_its_own_docstring_promises():
    copy = vendored()
    for name in (
        "run_check",
        "skip_reason",
        "update_warning",
        "failure_text",
        "render_text",
        "render_json",
        "render_sarif",
        "render_summary",
    ):
        assert callable(getattr(copy, name)), name


def test_the_copy_has_every_reader_registered():
    copy = vendored()
    assert copy.groups() == ("python", "binaries", "npm", "workflows")
    assert len(copy.READERS) == 10


def test_a_name_that_was_renamed_on_import_still_works_in_the_copy(tmp_path):
    """`config.py` imports `groups as reader_groups`. Dropping that import without putting the name back would raise NameError here, and
    only here — at the moment somebody's config named an ecosystem that does not exist."""
    copy = vendored()
    (tmp_path / ".stocktake.toml").write_text('ecosystems = ["nonsense"]\n', encoding="utf-8")
    with pytest.raises(copy.ConfigError, match="unknown ecosystem"):
        copy.load_config(tmp_path)


# ---------- what is in it, and what is not ----------
def test_the_copy_imports_nothing_from_stocktake():
    tree = ast.parse(COMMITTED.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("stocktake"):
            offenders.append((node.lineno, node.module))
        if isinstance(node, ast.Import):
            offenders += [(node.lineno, alias.name) for alias in node.names if alias.name.startswith("stocktake")]
    assert offenders == [], "a self-contained file cannot import the package it was made from"


def test_the_copy_leaves_out_what_a_single_file_cannot_carry():
    text = COMMITTED.read_text(encoding="utf-8")
    assert "import pytest" not in text, "the pytest plugin needs pytest"
    assert "def assert_dependencies_are_safe" not in text
    assert "def init_project" not in text
    assert "argparse" not in text, "the command line is not in it"


def test_the_copy_says_what_it_is_and_how_to_use_it():
    docstring = ast.get_docstring(ast.parse(COMMITTED.read_text(encoding="utf-8")))
    assert docstring
    assert "stocktake vendor" in docstring and "Do not edit" in docstring
    assert "run_check" in docstring and "failure_text" in docstring


def test_the_core_has_no_collisions_and_nothing_missing():
    """In one flat file the second definition of a name wins silently, which gives wrong answers rather than crashes."""
    modules = [read_module(path, PACKAGE_ROOT) for path in core_paths()]
    assert collisions(modules) == {}
    assert missing_dependencies(modules) == {}
    assert len(modules) > 20, "the copy should contain the whole core, not a handful of files"


def test_every_module_comes_after_what_it_imports_from():
    modules = [read_module(path, PACKAGE_ROOT) for path in core_paths()]
    by_name = {m.name: m for m in modules}
    placed: set[str] = set()
    for module in dependency_order(modules):
        for need in module.needs:
            expected = {need} if need in by_name else {n for n in by_name if n.startswith(need + ".")}
            assert expected <= placed | {module.name}, f"{module.name} comes before {need}"
        placed.add(module.name)


# ---------- the generator refuses rather than emitting something wrong ----------
def fake_package(tmp_path, **modules):
    root = tmp_path / "pkg"
    root.mkdir()
    for name, text in modules.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def test_it_refuses_when_two_modules_define_the_same_name(tmp_path):
    root = fake_package(tmp_path, **{"a.py": "VALUE = 1\n", "b.py": "VALUE = 2\n"})
    with pytest.raises(VendorError, match="same top-level name"):
        render(root, version="0.0.0")


def test_the_refusal_names_the_clash_and_both_files(tmp_path):
    root = fake_package(tmp_path, **{"a.py": "def thing(): ...\n", "b.py": "def thing(): ...\n"})
    with pytest.raises(VendorError, match=r"thing in stocktake\.a and stocktake\.b"):
        render(root, version="0.0.0")


def test_it_refuses_when_the_copy_would_import_something_left_out(tmp_path):
    # The real case: cli.py imports init_project.py, which is deliberately not in the copy.
    root = fake_package(tmp_path, **{"a.py": "from stocktake.init_project import init_project\n"})
    with pytest.raises(VendorError, match="does not contain"):
        render(root, version="0.0.0")


def test_it_refuses_when_modules_import_each_other_in_a_cycle(tmp_path):
    root = fake_package(tmp_path, **{"a.py": "from stocktake.b import B\nA = 1\n", "b.py": "from stocktake.a import A\nB = 2\n"})
    with pytest.raises(VendorError, match="cycle"):
        render(root, version="0.0.0")


def test_it_refuses_when_there_is_nothing_to_copy(tmp_path):
    with pytest.raises(VendorError, match="no core modules"):
        render(fake_package(tmp_path), version="0.0.0")


# ---------- writing it ----------
def test_a_directory_gets_the_default_filename(tmp_path):
    assert write(tmp_path).name == VENDORED_NAME


def test_a_filename_is_used_as_given(tmp_path):
    assert write(tmp_path / "deps" / "check.py").name == "check.py"


def test_writing_it_twice_is_how_it_is_refreshed(tmp_path):
    first = write(tmp_path)
    first.write_text("edited by hand\n", encoding="utf-8")
    assert write(tmp_path).read_text(encoding="utf-8") == render(), "regenerating is the point of the command, so it overwrites"


def test_the_written_file_is_the_committed_one(tmp_path):
    assert write(tmp_path).read_text(encoding="utf-8") == COMMITTED.read_text(encoding="utf-8")
