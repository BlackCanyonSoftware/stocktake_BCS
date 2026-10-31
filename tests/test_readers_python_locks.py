"""Reading Python lock files: uv, pdm, poetry and pipenv.

A lock file is the most honest statement a project makes about its dependencies, and the longest. The two things worth getting right are
skipping the project's own code (every lock file lists it as a package) and keeping the group where the format records one.
"""

import json

import pytest

from stocktake.readers.base import Context, UnreadableManifest
from stocktake.readers.python_locks import is_pipfile_lock, is_toml_lock, read_pipfile_lock, read_toml_lock

UV_LOCK = """version = 1
requires-python = ">=3.11"

[[package]]
name = "myproject"
version = "0.1.0"
source = { editable = "." }

[[package]]
name = "click"
version = "8.1.7"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "flask"
version = "3.0.0"
source = { registry = "https://pypi.org/simple" }
"""

POETRY_LOCK = """[[package]]
name = "requests"
version = "2.31.0"
description = "Python HTTP for Humans."
optional = false
python-versions = ">=3.7"

[[package]]
name = "our-shared-lib"
version = "0.2.0"
source = { type = "directory", url = "../shared" }
"""

PIPFILE_LOCK = json.dumps(
    {
        "_meta": {"hash": {"sha256": "abc"}, "requires": {"python_version": "3.11"}},
        "default": {
            "requests": {"version": "==2.31.0", "hashes": ["sha256:aaa"]},
            "ourlib": {"path": "./lib"},
            "fromgit": {"git": "https://example.invalid/x.git", "ref": "abc123"},
        },
        "develop": {"pytest": {"version": "==8.0.0"}},
    }
)


def read_toml(tmp_path, text=UV_LOCK, name="uv.lock"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return list(read_toml_lock(path, text, Context(root=tmp_path, installed=lambda name: None)))


def read_json(tmp_path, text=PIPFILE_LOCK):
    path = tmp_path / "Pipfile.lock"
    path.write_text(text, encoding="utf-8")
    return list(read_pipfile_lock(path, text, Context(root=tmp_path, installed=lambda name: None)))


# ---------- the TOML locks ----------
def test_a_uv_lock_gives_every_resolved_package_at_its_locked_version(tmp_path):
    deps = read_toml(tmp_path)
    assert [(d.name, d.version, d.spec, d.role) for d in deps] == [
        ("click", "8.1.7", "==8.1.7", "locked"),
        ("flask", "3.0.0", "==3.0.0", "locked"),
    ]
    assert all(d.source == "uv.lock" for d in deps)


def test_the_projects_own_package_is_not_asked_about(tmp_path):
    # Every lock file lists the project itself. Asking PyPI about your own unreleased package produces a confusing "unknown".
    assert "myproject" not in {d.name for d in read_toml(tmp_path)}


def test_a_dependency_on_a_sibling_directory_is_not_a_registry_package(tmp_path):
    deps = read_toml(tmp_path, POETRY_LOCK, "poetry.lock")
    assert [(d.name, d.version) for d in deps] == [("requests", "2.31.0")]


def test_poetry_and_pdm_locks_are_the_same_shape_and_the_same_reader(tmp_path):
    assert is_toml_lock(tmp_path / "uv.lock")
    assert is_toml_lock(tmp_path / "pdm.lock")
    assert is_toml_lock(tmp_path / "poetry.lock")
    assert not is_toml_lock(tmp_path / "Pipfile.lock")
    assert not is_toml_lock(tmp_path / "pyproject.toml")


def test_a_damaged_lock_file_is_reported_as_unreadable_rather_than_as_empty(tmp_path):
    """A manifest that cannot be parsed is not a manifest with nothing in it.

    Returning an empty list here is what let a project whose only manifest was truncated get a clean report, and it is the whole reason
    for `UnreadableManifest`: the reader claimed the file, so it has to say so when it could not read it (docs/adr/0009).
    """
    with pytest.raises(UnreadableManifest, match="not valid TOML"):
        read_toml(tmp_path, "[[package\nname = ")


def test_a_package_entry_missing_its_name_or_version_is_skipped(tmp_path):
    assert read_toml(tmp_path, '[[package]]\nname = "x"\n\n[[package]]\nversion = "1.0"\n') == []


def test_a_lock_file_with_no_packages_at_all_is_fine(tmp_path):
    assert read_toml(tmp_path, 'version = 1\nrequires-python = ">=3.11"\n') == []


# ---------- Pipfile.lock ----------
def test_a_pipfile_lock_keeps_the_section_each_package_came_from(tmp_path):
    deps = read_json(tmp_path)
    assert [(d.name, d.version, d.role) for d in deps] == [("requests", "2.31.0", "locked"), ("pytest", "8.0.0", "dev")]


def test_a_pipfile_lock_entry_with_no_pinned_version_has_nothing_to_check(tmp_path):
    names = {d.name for d in read_json(tmp_path)}
    assert "ourlib" not in names and "fromgit" not in names


def test_pipfile_locks_are_recognised(tmp_path):
    assert is_pipfile_lock(tmp_path / "Pipfile.lock")
    assert not is_pipfile_lock(tmp_path / "Pipfile")


def test_a_pipfile_lock_that_is_not_valid_json_is_reported_as_unreadable(tmp_path):
    with pytest.raises(UnreadableManifest, match="not valid JSON"):
        read_json(tmp_path, "{not json")


def test_a_pipfile_lock_that_is_not_an_object_is_unreadable_while_a_wrong_shaped_section_is_merely_empty(tmp_path):
    """Two different things. A file that is not an object cannot be read at all; one whose `default` is a string is readable and declares nothing."""
    with pytest.raises(UnreadableManifest, match="not a table at the top level"):
        read_json(tmp_path, '["a", "list"]')
    assert read_json(tmp_path, '{"default": "not a table"}') == []


# ---------- the guards ----------
def test_no_package_in_a_toml_lock_escapes_the_reader(tmp_path):
    """Counts `[[package]]` tables and their sources independently of the reader, and insists the two agree."""
    for text, name in ((UV_LOCK, "uv.lock"), (POETRY_LOCK, "poetry.lock")):
        blocks = text.split("[[package]]")[1:]
        expected = {
            block.split('name = "')[1].split('"')[0].lower()
            for block in blocks
            if 'name = "' in block and not any(local in block for local in ("editable =", "virtual =", 'type = "directory"'))
        }
        found = {d.name.lower() for d in read_toml(tmp_path, text, name)}
        assert expected == found, f"{name}: the reader and an independent count disagree about {expected ^ found}"


def test_no_pinned_package_in_a_pipfile_lock_escapes_the_reader(tmp_path):
    """Counts the entries that carry a `==` version, independently of the reader."""
    data = json.loads(PIPFILE_LOCK)
    expected = {
        name.lower()
        for section in ("default", "develop")
        for name, detail in data.get(section, {}).items()
        if str(detail.get("version", "")).startswith("==")
    }
    found = {d.name.lower() for d in read_json(tmp_path)}
    assert expected == found, f"the reader and an independent count disagree about {expected ^ found}"


@pytest.mark.parametrize("lock", ["uv.lock", "pdm.lock", "poetry.lock"])
def test_every_toml_lock_name_is_actually_handled(lock, tmp_path):
    deps = read_toml(tmp_path, '[[package]]\nname = "click"\nversion = "8.1.7"\n', lock)
    assert [d.name for d in deps] == ["click"]
