"""Reading `pyproject.toml`, at the version actually installed."""

import pytest

from stocktake.readers.base import Context, UnreadableManifest
from stocktake.readers.pep508 import parse_requirement
from stocktake.readers.python_project import read_pyproject

PYPROJECT = """
[project]
name = "x"
dependencies = ["httpx>=0.27", "click==8.1.7"]

[project.optional-dependencies]
dev = ["pytest>=8", "webauthn==2.7.1", "ghost>=1"]

[dependency-groups]
lint = ["ruff>=0.14", {include-group = "dev"}]
"""


def read(tmp_path, text=PYPROJECT, installed=None):
    path = tmp_path / "pyproject.toml"
    path.write_text(text, encoding="utf-8")
    context = Context(root=tmp_path, installed=(installed or {}).get)
    return list(read_pyproject(path, text, context))


def test_dependencies_are_checked_at_the_version_installed_here_not_the_range_declared(tmp_path):
    deps = read(tmp_path, installed={"httpx": "0.28.1", "pytest": "8.3.1", "webauthn": "2.7.1", "ruff": "0.14.1"})
    assert [(d.name, d.version, d.spec, d.role) for d in deps] == [
        ("httpx", "0.28.1", ">=0.27", "runtime"),
        ("click", "8.1.7", "==8.1.7", "runtime"),
        ("pytest", "8.3.1", ">=8", "dev"),
        ("webauthn", "2.7.1", "==2.7.1", "dev"),
        ("ghost", None, ">=1", "dev"),
        ("ruff", "0.14.1", ">=0.14", "dev"),
    ]


def test_a_declared_range_with_nothing_installed_has_no_version_to_check(tmp_path):
    deps = read(tmp_path, installed={})
    assert [(d.name, d.version) for d in deps if d.name == "ghost"] == [("ghost", None)]


def test_a_pin_is_used_when_the_package_is_not_installed_here(tmp_path):
    deps = read(tmp_path, installed={})
    assert next(d for d in deps if d.name == "click").version == "8.1.7"


def test_an_include_group_entry_is_not_mistaken_for_a_package(tmp_path):
    assert not [d for d in read(tmp_path, installed={}) if d.name == "include-group"]


def test_the_source_is_the_file_with_no_line_number(tmp_path):
    assert {d.source for d in read(tmp_path, installed={})} == {"pyproject.toml"}


def test_a_broken_pyproject_is_reported_as_unreadable_rather_than_as_empty(tmp_path):
    """A manifest that cannot be parsed is not a manifest with nothing in it.

    Returning an empty list here is what let a project whose only manifest was truncated get a clean report, and it is the whole reason
    for `UnreadableManifest`: the reader claimed the file, so it has to say so when it could not read it (docs/adr/0009).
    """
    with pytest.raises(UnreadableManifest, match="not valid TOML"):
        read(tmp_path, text="[project\nname = ")


def test_a_pyproject_with_no_dependencies_at_all_is_fine(tmp_path):
    assert read(tmp_path, text='[project]\nname = "x"\nversion = "1"\n') == []


# ---------- Pipfile ----------
PIPFILE = """[[source]]
url = "https://pypi.org/simple"
verify_ssl = true

[packages]
requests = "*"
flask = ">=2.0"
django = {version = "==4.2", extras = ["bcrypt"]}
ourlib = {path = "./lib"}

[dev-packages]
pytest = "*"
"""


def read_pipfile_at(tmp_path, text=PIPFILE, installed=None):
    from stocktake.readers.python_project import read_pipfile

    path = tmp_path / "Pipfile"
    path.write_text(text, encoding="utf-8")
    return list(read_pipfile(path, text, Context(root=tmp_path, installed=(installed or {}).get)))


def test_a_pipfile_is_read_so_a_pipenv_project_is_not_told_it_is_unreadable(tmp_path):
    # Its lock file is read perfectly well, so reporting the Pipfile itself as an unreadable manifest would be a false alarm.
    deps = read_pipfile_at(tmp_path, installed={"requests": "2.32.0", "pytest": "8.0.0"})
    assert [(d.name, d.version, d.spec, d.role) for d in deps] == [
        ("requests", "2.32.0", "", "runtime"),
        ("flask", None, ">=2.0", "runtime"),
        ("django", "4.2", "==4.2", "runtime"),
        ("pytest", "8.0.0", "", "dev"),
    ]


def test_a_pipfile_entry_pointing_at_local_code_is_not_a_registry_package(tmp_path):
    assert "ourlib" not in {d.name for d in read_pipfile_at(tmp_path)}


def test_a_pipfile_wildcard_is_no_specifier_at_all(tmp_path):
    requests = next(d for d in read_pipfile_at(tmp_path) if d.name == "requests")
    assert (requests.spec, requests.version) == ("", None)


def test_a_damaged_pipfile_is_reported_as_unreadable(tmp_path):
    with pytest.raises(UnreadableManifest, match="not valid TOML"):
        read_pipfile_at(tmp_path, text="[packages\nrequests = ")


def test_a_requirement_is_reduced_to_name_pin_and_specifier():
    assert parse_requirement("pillow==12.3.0") == ("pillow", "12.3.0", "==12.3.0")
    assert parse_requirement("uvicorn[standard]>=0.30") == ("uvicorn", None, ">=0.30")
    assert parse_requirement("requests>=2.30,<3") == ("requests", None, ">=2.30,<3")
    assert parse_requirement("ruff") == ("ruff", None, "")
    assert parse_requirement('tomli; python_version < "3.11"') == ("tomli", None, "")
    assert parse_requirement("") is None
    assert parse_requirement("./local") is None
