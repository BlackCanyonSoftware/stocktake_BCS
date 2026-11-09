"""Reading `pnpm-lock.yaml`.

Most of the care here is about which half of the file to read and what to do with a key that does not fit. pnpm's layout has changed between
major lock versions before, so the reader recognises packages by their *shape* and refuses a key it does not understand rather than passing
over it — a lock whose shape moved under us must not come back as a project with nothing in it.

The last test is the guard: it counts the package keys with a plain regular expression, independently of the reader and of the YAML subset
beneath it.
"""

import re

import pytest

from stocktake.readers.base import Context, UnreadableManifest
from stocktake.readers.pnpm import is_pnpm_lock, locked_packages, read_pnpm_lock
from stocktake.readers.yamlish import parse

LOCK = """lockfileVersion: '9.0'

settings:
  autoInstallPeers: true

importers:

  .:
    devDependencies:
      typescript:
        specifier: ^5.6.3
        version: 5.9.3

packages:

  7zip-bin@5.2.0:
    resolution: {integrity: sha512-aaaa}

  '@babel/code-frame@7.29.7':
    resolution: {integrity: sha512-bbbb}
    engines: {node: '>=6.9.0'}

  lodash@4.17.15:
    resolution: {integrity: sha512-cccc}

  typescript@5.9.3:
    resolution: {integrity: sha512-dddd}
    hasBin: true

snapshots:

  7zip-bin@5.2.0: {}

  '@babel/code-frame@7.29.7(supports-color@8.1.1)':
    dependencies:
      supports-color: 8.1.1

  lodash@4.17.15: {}

  typescript@5.9.3: {}
"""


def read(tmp_path, text=LOCK):
    path = tmp_path / "pnpm-lock.yaml"
    path.write_text(text, encoding="utf-8")
    return list(read_pnpm_lock(path, text, Context(root=tmp_path, installed=lambda name: None)))


def test_it_reads_every_package_the_lock_resolved(tmp_path):
    assert [(d.name, d.version) for d in read(tmp_path)] == [
        ("7zip-bin", "5.2.0"),
        ("@babel/code-frame", "7.29.7"),
        ("lodash", "4.17.15"),
        ("typescript", "5.9.3"),
    ]


def test_a_scoped_name_is_split_on_its_last_at_sign(tmp_path):
    """`@babel/code-frame@7.29.7` is a package beginning with `@`. Splitting on the first one would name it `` at `babel/...`."""
    found = {d.name: d.version for d in read(tmp_path)}
    assert found["@babel/code-frame"] == "7.29.7"


def test_the_snapshots_section_is_not_read(tmp_path):
    """Its keys carry peer-dependency suffixes in parentheses and name the same packages again; `packages:` is the plain list."""
    assert not any("(" in d.name or "supports-color" in d.name for d in read(tmp_path))
    assert len(read(tmp_path)) == 4, "four packages, not four plus their snapshots"


def test_every_finding_is_a_locked_npm_package_of_this_file(tmp_path):
    for dep in read(tmp_path):
        assert dep.ecosystem == "npm"
        assert dep.role == "locked"
        assert dep.spec == f"=={dep.version}"
        assert dep.source == "pnpm-lock.yaml"


def test_the_same_package_at_one_version_is_one_finding(tmp_path):
    text = LOCK.replace("  lodash@4.17.15:\n    resolution: {integrity: sha512-cccc}\n", "")
    assert len([d for d in read(tmp_path, text) if d.name == "lodash"]) == 0


# ---------- what it skips, and what it refuses ----------
@pytest.mark.parametrize("key", ["thing@link:../sibling", "other@file:../tarball.tgz", "app@workspace:*"])
def test_a_package_no_registry_knows_is_skipped(tmp_path, key):
    """A workspace sibling or a tarball is real and is not something npm can be asked about, exactly as the npm lock reader treats one."""
    text = f"lockfileVersion: '9.0'\n\npackages:\n\n  '{key}':\n    resolution: {{integrity: sha512-x}}\n"
    assert read(tmp_path, text) == []


def test_a_key_that_is_neither_is_refused_rather_than_passed_over(tmp_path):
    """The whole safety of reading a format by its shape: a layout that moved under us says so instead of reporting an empty project."""
    text = "lockfileVersion: '9.0'\n\npackages:\n\n  somethingentirelynew:\n    resolution: {integrity: sha512-x}\n"
    with pytest.raises(UnreadableManifest, match="not a name and a version"):
        read(tmp_path, text)


def test_a_lock_with_no_packages_section_is_refused_and_names_its_version(tmp_path):
    text = "lockfileVersion: '99.0'\n\nimporters:\n\n  .:\n    dependencies: {}\n"
    with pytest.raises(UnreadableManifest, match=r"lockfileVersion 99\.0"):
        read(tmp_path, text)


def test_an_older_leading_slash_key_is_still_read():
    """Earlier lock versions wrote `/name@version`. Cheap to accept, and refusing it would be refusing a file we do understand."""
    data = parse("packages:\n\n  /lodash@4.17.15:\n    resolution: {integrity: sha512-x}\n")
    assert locked_packages(data, "pnpm-lock.yaml") == [("lodash", "4.17.15")]


def test_a_config_the_yaml_subset_cannot_read_is_refused_by_it(tmp_path):
    with pytest.raises(UnreadableManifest, match="anchor"):
        read(tmp_path, "packages: &base\n  lodash@4.17.15:\n    resolution: {integrity: sha512-x}\n")


def test_only_that_filename_is_claimed(tmp_path):
    assert is_pnpm_lock(tmp_path / "pnpm-lock.yaml")
    assert not is_pnpm_lock(tmp_path / "package-lock.json")
    assert not is_pnpm_lock(tmp_path / "pnpm-workspace.yaml")


# ---------- the guard ----------
def test_no_package_in_the_lock_escapes_the_reader(tmp_path):
    """Counts the keys of `packages:` with an independent regular expression, and insists the reader agrees.

    Scoped to the `packages:` block by hand rather than by the YAML subset, so that this would still fail if that subset were wrong.
    """
    block = LOCK.split("packages:", 1)[1].split("snapshots:", 1)[0]
    expected = set()
    for line in block.splitlines():
        match = re.match(r"^  '?/?(?P<key>[^':]+)'?:\s*$", line)
        if not match:
            continue
        key = match.group("key")
        name, _, version = key.rpartition("@")
        if name and version:
            expected.add((name, version))

    found = {(d.name, d.version) for d in read(tmp_path)}
    assert expected == found, f"the reader and an independent count disagree about: {expected ^ found}"
