"""npm: `package.json`, `package-lock.json`, and what is actually in `node_modules`.

The same pins-versus-ranges rule as the Python side, for the same reason. A lock file names what *will* be installed, so its version wins. A
`package.json` entry is almost always a range (`^1.2.3`), which says nothing about what is installed, so it is resolved against
`node_modules` — the npm equivalent of resolving a `pyproject.toml` range against a virtual environment
([ADR 0006](adr/0006-which-environment-an-installed-version-comes-from.md)).

**`yarn.lock` and `pnpm-lock.yaml` are not read.** Both need a YAML parser, and the core has no dependencies
([ADR 0001](adr/0001-python-with-a-standard-library-only-core.md)). A yarn or pnpm project is still checked, because its `package.json` is
read and resolved against `node_modules`, which holds the resolved truth those files describe; and both are reported as unread manifests, so
nobody is told a project is clean when half of it was skipped.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any

from stocktake.models import Dep
from stocktake.readers.base import Context, UnreadableManifest, reader

# Values that name something other than a version of this package from the registry: local code, a git repository, an alias, a tarball URL.
NOT_A_REGISTRY_VERSION = (
    "file:",
    "link:",
    "workspace:",
    "portal:",
    "patch:",
    "git+",
    "git:",
    "github:",
    "gitlab:",
    "bitbucket:",
    "npm:",
    "http://",
    "https://",
)

# Values that fix nothing at all.
ANY_VERSION = frozenset({"", "*", "x", "latest", "next"})

# Said per finding, because "not installed in this environment" reads as a Python environment and means nothing to a Node project.
NOT_INSTALLED = "not installed in node_modules, and no version is pinned"

# Said once per run, when ranges went unresolved. True whether node_modules is missing entirely or merely incomplete.
RUN_INSTALL_NOTE = (
    "Some npm dependencies are declared as a range and are not installed, so they could not be resolved to a version. "
    "Run `npm install` (or `npm ci`) where they are declared and check again."
)

EXACT = re.compile(r"^(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.+-]*)?)$")

SECTIONS = (
    ("dependencies", "runtime"),
    ("devDependencies", "dev"),
    ("optionalDependencies", "runtime"),
    ("peerDependencies", "runtime"),
)


def is_package_json(path: Path) -> bool:
    return path.name == "package.json"


def is_package_lock(path: Path) -> bool:
    return path.name == "package-lock.json"


def parse_npm_spec(value: str) -> tuple[str | None, str] | None:
    """(pinned version or None, the range as written) for one `package.json` value, or None when it is not a registry version at all.

    Only a bare three-part version is a pin. `^1.2.3`, `~1.2.3`, `1.2` and `>=1 <2` are all ranges, and `1.2` really is a range in npm — it
    means `1.2.x`.
    """
    text = (value or "").strip()
    if text.startswith(NOT_A_REGISTRY_VERSION):
        return None
    if "/" in text:
        return None  # `owner/repo`, the shorthand for a GitHub dependency
    if text.lower() in ANY_VERSION:
        return (None, "")
    exact = EXACT.match(text.removeprefix("=").removeprefix("v"))
    return (exact.group(1), text) if exact else (None, text)


def _installed_lookup(manifest_directory: Path, root: Path) -> Callable[[str], str | None]:
    """Read versions out of `node_modules`, on demand and once each.

    Looks beside the manifest first and then up towards the project root, because a workspace's dependencies are usually hoisted to the top
    of the repository rather than installed beside the `package.json` that asked for them.
    """
    places = []
    here = manifest_directory
    while True:
        places.append(here)
        if here == root or here.parent == here:
            break
        here = here.parent

    found: dict[str, str | None] = {}

    def lookup(name: str) -> str | None:
        if name not in found:
            found[name] = next((version for place in places if (version := _version_in(place / "node_modules" / name)) is not None), None)
        return found[name]

    return lookup


def _version_in(package_directory: Path) -> str | None:
    try:
        data = json.loads((package_directory / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    version = data.get("version") if isinstance(data, dict) else None
    return version if isinstance(version, str) and version else None


@reader("npm", is_package_json)
def read_package_json(path: Path, text: str, context: Context) -> Iterable[Dep]:
    """Dependencies declared in a package.json, at the version installed in node_modules."""
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise UnreadableManifest(f"is not valid JSON ({exc})") from exc
    if not isinstance(data, dict):
        raise UnreadableManifest("is valid but is not a table at the top level, so there is nothing in it a reader can use")

    installed = _installed_lookup(path.parent, context.root)
    for section, role in SECTIONS:
        entries = data.get(section)
        if not isinstance(entries, dict):
            continue
        for name, value in entries.items():
            parsed = parse_npm_spec(value if isinstance(value, str) else "")
            if parsed is None:
                continue
            pinned, spec = parsed
            version = pinned or installed(str(name))
            yield Dep("npm", str(name), version, context.source(path), spec, role, "" if version else NOT_INSTALLED)


def _locked_packages(data: dict[str, Any]) -> Iterator[tuple[str, str]]:
    """(name, version) for every registry package a package-lock.json resolved, for both lockfile layouts."""
    packages = data.get("packages")
    if isinstance(packages, dict):  # lockfileVersion 2 and 3: one flat entry per installed path
        for key, entry in packages.items():
            if "node_modules/" not in key or not isinstance(entry, dict) or entry.get("link"):
                continue  # "" is the project itself, a bare key is a workspace folder, a link is local code
            resolved = entry.get("resolved")
            if isinstance(resolved, str) and not resolved.startswith(("http://", "https://")):
                continue  # resolved from somewhere that is not a registry
            name = key.rsplit("node_modules/", 1)[-1]
            version = entry.get("version")
            if name and isinstance(version, str) and version:
                yield name, version
        return
    yield from _nested(data.get("dependencies"))  # lockfileVersion 1: a tree


def _nested(entries: object) -> Iterator[tuple[str, str]]:
    if not isinstance(entries, dict):
        return
    for name, entry in entries.items():
        if not isinstance(entry, dict):
            continue
        version = entry.get("version")
        if isinstance(version, str) and version and not version.startswith(NOT_A_REGISTRY_VERSION):
            yield str(name), version
        yield from _nested(entry.get("dependencies"))


@reader("npm", is_package_lock)
def read_package_lock(path: Path, text: str, context: Context) -> Iterable[Dep]:
    """Packages resolved by a package-lock.json."""
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise UnreadableManifest(f"is not valid JSON ({exc})") from exc
    if not isinstance(data, dict):
        raise UnreadableManifest("is valid but is not a table at the top level, so there is nothing in it a reader can use")
    # One finding per name and version. A lock file lists the same package at several depths; the extra rows say nothing new.
    for name, version in dict.fromkeys(_locked_packages(data)):
        yield Dep("npm", name, version, context.source(path), f"=={version}", "locked")
