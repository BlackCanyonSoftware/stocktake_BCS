"""Reading npm: `package.json`, `package-lock.json`, and `node_modules`.

The interesting cases are the values that are not versions at all — a file path, a git URL, an alias, a GitHub shorthand — and the fact that
`package.json` almost never pins anything, so the answer has to come from what is actually installed.
"""

import json

from stocktake.readers.base import Context
from stocktake.readers.npm import is_package_json, is_package_lock, parse_npm_spec, read_package_json, read_package_lock

PACKAGE_JSON = json.dumps(
    {
        "name": "scratch",
        "version": "0.1.0",
        "dependencies": {
            "koffi": "^3.3.3",
            "left-pad": "1.3.0",
            "@scope/thing": "~2.1.0",
            "ourlib": "file:../lib",
            "forked": "git+https://example.invalid/forked.git",
            "aliased": "npm:other@^1.0.0",
            "fromgithub": "owner/repo",
            "whatever": "*",
        },
        "devDependencies": {"eslint": "^10.13.0", "@types/node": "^24.10.1"},
        "peerDependencies": {"react": ">=18"},
        "scripts": {"test": "node --test"},
    }
)

LOCK_V3 = json.dumps(
    {
        "name": "scratch",
        "lockfileVersion": 3,
        "packages": {
            "": {"name": "scratch", "version": "0.1.0", "dependencies": {"koffi": "^3.3.3"}},
            "app": {"name": "app", "version": "0.0.1"},
            "node_modules/koffi": {"version": "3.3.3", "resolved": "https://registry.npmjs.org/koffi/-/koffi-3.3.3.tgz"},
            "node_modules/@scope/thing": {"version": "2.1.4", "resolved": "https://registry.npmjs.org/@scope/thing/-/thing-2.1.4.tgz"},
            "node_modules/a/node_modules/nested": {"version": "1.0.0", "resolved": "https://registry.npmjs.org/nested/-/nested-1.0.0.tgz"},
            "node_modules/app": {"resolved": "app", "link": True},
            "node_modules/local": {"version": "1.0.0", "resolved": "file:../local"},
        },
    }
)

LOCK_V1 = json.dumps(
    {
        "name": "scratch",
        "lockfileVersion": 1,
        "dependencies": {
            "koffi": {"version": "3.3.3", "dependencies": {"nested": {"version": "1.0.0"}}},
            "ourlib": {"version": "file:../lib"},
        },
    }
)


def read_manifest(tmp_path, text=PACKAGE_JSON, installed=None):
    path = tmp_path / "package.json"
    path.write_text(text, encoding="utf-8")
    for name, version in (installed or {}).items():
        folder = tmp_path / "node_modules" / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "package.json").write_text(json.dumps({"name": name, "version": version}), encoding="utf-8")
    return list(read_package_json(path, text, Context(root=tmp_path, installed=lambda n: None)))


def read_lock(tmp_path, text=LOCK_V3):
    path = tmp_path / "package-lock.json"
    path.write_text(text, encoding="utf-8")
    return list(read_package_lock(path, text, Context(root=tmp_path, installed=lambda n: None)))


# ---------- what a value means ----------
def test_only_a_bare_three_part_version_counts_as_a_pin():
    assert parse_npm_spec("1.3.0") == ("1.3.0", "1.3.0")
    assert parse_npm_spec("=1.3.0") == ("1.3.0", "=1.3.0")
    assert parse_npm_spec("1.3.0-beta.1") == ("1.3.0-beta.1", "1.3.0-beta.1")


def test_a_range_pins_nothing_however_narrow_it_looks():
    # `1.2` really is a range in npm: it means 1.2.x.
    for value in ("^3.3.3", "~2.1.0", ">=18", ">=1 <2", "1.2", "7"):
        assert parse_npm_spec(value) == (None, value)


def test_a_value_that_fixes_nothing_at_all_has_no_specifier_either():
    for value in ("*", "", "latest", "x"):
        assert parse_npm_spec(value) == (None, "")


def test_a_value_naming_something_other_than_a_registry_version_is_skipped():
    for value in (
        "file:../lib",
        "link:../lib",
        "workspace:*",
        "git+https://example.invalid/x.git",
        "github:owner/repo",
        "owner/repo",
        "npm:other@^1.0.0",
        "https://example.invalid/x.tgz",
    ):
        assert parse_npm_spec(value) is None, value


# ---------- package.json ----------
def test_every_dependency_section_is_read_with_the_role_it_implies(tmp_path):
    deps = read_manifest(tmp_path, installed={"koffi": "3.3.9", "eslint": "10.13.2"})
    assert [(d.name, d.version, d.spec, d.role) for d in deps] == [
        ("koffi", "3.3.9", "^3.3.3", "runtime"),
        ("left-pad", "1.3.0", "1.3.0", "runtime"),
        ("@scope/thing", None, "~2.1.0", "runtime"),
        ("whatever", None, "", "runtime"),
        ("eslint", "10.13.2", "^10.13.0", "dev"),
        ("@types/node", None, "^24.10.1", "dev"),
        ("react", None, ">=18", "runtime"),
    ]
    assert all(d.ecosystem == "npm" for d in deps)


def test_a_range_is_resolved_against_what_is_installed_in_node_modules(tmp_path):
    deps = read_manifest(tmp_path, installed={"koffi": "3.3.9"})
    assert next(d for d in deps if d.name == "koffi").version == "3.3.9"


def test_a_scoped_package_is_found_in_node_modules_too(tmp_path):
    deps = read_manifest(tmp_path, installed={"@scope/thing": "2.1.4"})
    assert next(d for d in deps if d.name == "@scope/thing").version == "2.1.4"


def test_a_pin_wins_over_what_happens_to_be_installed(tmp_path):
    deps = read_manifest(tmp_path, installed={"left-pad": "1.0.0"})
    assert next(d for d in deps if d.name == "left-pad").version == "1.3.0"


def test_nothing_installed_leaves_a_range_with_no_version_to_check(tmp_path):
    deps = read_manifest(tmp_path)
    assert next(d for d in deps if d.name == "koffi").version is None


def test_a_workspace_manifest_finds_dependencies_hoisted_to_the_repository_root(tmp_path):
    # npm installs a workspace's dependencies at the top of the repository, not beside the package.json that asked for them.
    root = tmp_path
    hoisted = root / "node_modules" / "koffi"
    hoisted.mkdir(parents=True)
    (hoisted / "package.json").write_text(json.dumps({"version": "3.3.9"}), encoding="utf-8")

    app = root / "app"
    app.mkdir()
    manifest = app / "package.json"
    text = json.dumps({"name": "app", "dependencies": {"koffi": "^3.3.3"}})
    manifest.write_text(text, encoding="utf-8")

    deps = list(read_package_json(manifest, text, Context(root=root, installed=lambda n: None)))
    assert [(d.name, d.version, d.source) for d in deps] == [("koffi", "3.3.9", "app/package.json")]


def test_a_broken_package_json_yields_nothing_rather_than_crashing_the_run(tmp_path):
    assert read_manifest(tmp_path, text="{not json") == []
    assert read_manifest(tmp_path, text='["a", "list"]') == []


def test_a_package_json_with_no_dependencies_is_fine(tmp_path):
    assert read_manifest(tmp_path, text=json.dumps({"name": "x", "scripts": {"build": "tsc"}})) == []


# ---------- package-lock.json ----------
def test_a_modern_lock_file_gives_every_resolved_registry_package(tmp_path):
    deps = read_lock(tmp_path)
    assert [(d.name, d.version, d.role) for d in deps] == [
        ("koffi", "3.3.3", "locked"),
        ("@scope/thing", "2.1.4", "locked"),
        ("nested", "1.0.0", "locked"),
    ]
    assert all(d.source == "package-lock.json" and d.spec.startswith("==") for d in deps)


def test_the_project_itself_its_workspaces_and_its_links_are_not_registry_packages(tmp_path):
    names = {d.name for d in read_lock(tmp_path)}
    assert "scratch" not in names and "app" not in names and "local" not in names


def test_a_package_nested_under_another_is_named_by_itself(tmp_path):
    # The key is "node_modules/a/node_modules/nested"; the package is "nested".
    assert "nested" in {d.name for d in read_lock(tmp_path)}


def test_the_same_name_and_version_at_two_depths_is_reported_once(tmp_path):
    text = json.dumps(
        {
            "lockfileVersion": 3,
            "packages": {
                "node_modules/dup": {"version": "1.0.0", "resolved": "https://registry.npmjs.org/dup/-/dup-1.0.0.tgz"},
                "node_modules/a/node_modules/dup": {"version": "1.0.0", "resolved": "https://registry.npmjs.org/dup/-/dup-1.0.0.tgz"},
            },
        }
    )
    assert [(d.name, d.version) for d in read_lock(tmp_path, text)] == [("dup", "1.0.0")]


def test_two_different_versions_of_one_package_are_both_reported(tmp_path):
    text = json.dumps(
        {
            "lockfileVersion": 3,
            "packages": {
                "node_modules/dup": {"version": "1.0.0", "resolved": "https://registry.npmjs.org/dup/-/dup-1.0.0.tgz"},
                "node_modules/a/node_modules/dup": {"version": "2.0.0", "resolved": "https://registry.npmjs.org/dup/-/dup-2.0.0.tgz"},
            },
        }
    )
    assert {d.version for d in read_lock(tmp_path, text)} == {"1.0.0", "2.0.0"}


def test_the_older_nested_lock_layout_is_read_too(tmp_path):
    deps = read_lock(tmp_path, LOCK_V1)
    assert [(d.name, d.version) for d in deps] == [("koffi", "3.3.3"), ("nested", "1.0.0")]
    assert "ourlib" not in {d.name for d in deps}, "a file: version is not a registry version"


def test_a_broken_lock_file_yields_nothing(tmp_path):
    assert read_lock(tmp_path, "{not json") == []
    assert read_lock(tmp_path, '["a"]') == []


def test_npm_files_are_recognised(tmp_path):
    assert is_package_json(tmp_path / "package.json")
    assert is_package_lock(tmp_path / "package-lock.json")
    assert not is_package_json(tmp_path / "package-lock.json")
    assert not is_package_lock(tmp_path / "package.json")


# ---------- the guards ----------
def test_no_dependency_in_the_manifest_escapes_the_reader(tmp_path):
    """Counts the declared names independently of the reader, excluding the values that are plainly not registry versions."""
    data = json.loads(PACKAGE_JSON)
    not_versions = ("file:", "link:", "git+", "github:", "npm:", "workspace:", "https://")
    expected = {
        name
        for section in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies")
        for name, value in data.get(section, {}).items()
        if not value.startswith(not_versions) and "/" not in value
    }
    found = {d.name for d in read_manifest(tmp_path)}
    assert expected == found, f"the reader and an independent count disagree about {expected ^ found}"


def test_no_registry_package_in_the_lock_file_escapes_the_reader(tmp_path):
    """Counts the lock file's installed paths independently of the reader."""
    data = json.loads(LOCK_V3)
    expected = {
        key.rsplit("node_modules/", 1)[-1]
        for key, entry in data["packages"].items()
        if "node_modules/" in key and not entry.get("link") and str(entry.get("resolved", "https://")).startswith("https://")
    }
    found = {d.name for d in read_lock(tmp_path)}
    assert expected == found, f"the reader and an independent count disagree about {expected ^ found}"
