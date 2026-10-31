"""Python lock files: `uv.lock`, `pdm.lock`, `poetry.lock` and `Pipfile.lock`.

A lock file is the most honest thing a project has about its dependencies — it names exactly what will be installed, transitively, with no
ranges to interpret. That also makes it the longest list, which is why the report collapses everything current into a count.

The three TOML formats share a shape: an array of `[[package]]` tables with a name and a version. `Pipfile.lock` is JSON and keeps its
sections apart, so where a lock file does record which group an entry serves, that is used; otherwise the role is `locked`.

Entries for the project's own code are skipped. A lock file lists the project itself as a package (`source = {editable = "."}` in uv,
`{virtual = "."}`, a `directory` source in poetry), and asking PyPI about your own unreleased package produces a confusing `unknown`.
"""

from __future__ import annotations

import json
import tomllib
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from stocktake.models import Dep
from stocktake.readers.base import Context, UnreadableManifest, reader

TOML_LOCKS = frozenset({"uv.lock", "pdm.lock", "poetry.lock"})

# A source of this kind means "code that lives in this repository", not something a registry knows about.
LOCAL_SOURCES = frozenset({"editable", "virtual", "directory", "path", "url", "git"})


def is_toml_lock(path: Path) -> bool:
    return path.name in TOML_LOCKS


def is_pipfile_lock(path: Path) -> bool:
    return path.name == "Pipfile.lock"


def _is_local(package: dict[str, Any]) -> bool:
    source = package.get("source")
    if isinstance(source, dict):
        return any(key in source for key in LOCAL_SOURCES)
    return False


def _toml_packages(data: dict[str, Any]) -> Iterator[tuple[str, str]]:
    packages = data.get("package")
    if not isinstance(packages, list):
        return
    for package in packages:
        if not isinstance(package, dict) or _is_local(package):
            continue
        name, version = package.get("name"), package.get("version")
        if isinstance(name, str) and isinstance(version, str) and name and version:
            yield name, version


@reader("python", is_toml_lock)
def read_toml_lock(path: Path, text: str, context: Context) -> Iterable[Dep]:
    """Packages resolved by a uv, pdm or poetry lock file."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise UnreadableManifest(f"is not valid TOML ({exc})") from exc
    for name, version in _toml_packages(data):
        yield Dep("PyPI", name, version, context.source(path), f"=={version}", "locked")


@reader("python", is_pipfile_lock)
def read_pipfile_lock(path: Path, text: str, context: Context) -> Iterable[Dep]:
    """Packages resolved by a Pipfile.lock, keeping the section each one came from."""
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise UnreadableManifest(f"is not valid JSON ({exc})") from exc
    if not isinstance(data, dict):
        raise UnreadableManifest("is valid but is not a table at the top level, so there is nothing in it a reader can use")
    for section, role in (("default", "locked"), ("develop", "dev")):
        entries = data.get(section)
        if not isinstance(entries, dict):
            continue
        for name, detail in entries.items():
            if not isinstance(detail, dict):
                continue
            # Pipenv writes the version as a specifier, "==2.31.0". Anything else (a git ref, a local path) has no version to check.
            spec = detail.get("version")
            version = spec.removeprefix("==") if isinstance(spec, str) and spec.startswith("==") else None
            if version is None:
                continue
            yield Dep("PyPI", str(name), version, context.source(path), f"=={version}", role)
