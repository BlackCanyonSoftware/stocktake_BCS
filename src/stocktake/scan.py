"""Walking a project and handing each file to whichever readers want it.

Two jobs, and the second matters as much as the first. One is to collect what the project declares. The other is to notice a manifest of a
kind no reader understands, because the dangerous failure for a tool like this is not a wrong answer, it is a clean-looking report that
quietly missed half the project.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from fnmatch import fnmatch
from importlib import metadata
from pathlib import Path

from stocktake.config import Config, excluded
from stocktake.models import Dep, Unread, Unreadable, normalize
from stocktake.readers import READERS, Context, InstalledFn, UnreadableManifest, read_manifest

# Files that declare dependencies in some form. A kind no registered reader is interested in gets reported as unread rather than ignored,
# which is what turns "StockTake does not support this yet" from a silent gap into something the project is told about.
MANIFEST_KINDS: tuple[str, ...] = (
    "requirements*.txt",
    "constraints*.txt",
    "Pipfile",
    "Pipfile.lock",
    "poetry.lock",
    "uv.lock",
    "pdm.lock",
    "environment.yml",
    "environment.yaml",
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lockb",
    "go.mod",
    "Cargo.toml",
    "Gemfile",
    "Gemfile.lock",
    "composer.json",
    "*.csproj",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    ".pre-commit-config.yaml",
)


VENV_NAMES = (".venv", "venv")

NO_ENVIRONMENT_NOTE = (
    "No Python environment was found for this project, so dependencies declared as a range could not be resolved to a version. "
    "Point at one with --environment PATH, or run StockTake from inside the project's own environment."
)


@dataclass(frozen=True, slots=True)
class Environment:
    """Which Python environment "what is installed" was read from, and what was in it."""

    versions: dict[str, str] | None  # None means none could be found; {} means one was found and is empty
    label: str  # where it came from, in words, for the report

    @property
    def found(self) -> bool:
        return self.versions is not None

    def version(self, name: str) -> str | None:
        return (self.versions or {}).get(normalize(name))


def _site_packages(base: Path) -> list[Path]:
    """Where an environment keeps its installed packages, on either platform."""
    return [*base.glob("Lib/site-packages"), *base.glob("lib/python*/site-packages")]


def _read_site_packages(sites: Sequence[Path]) -> dict[str, str] | None:
    """`{normalised name: version}` read from `*.dist-info` directory names, which carry both without opening a single file.

    None when there was no such directory to read at all, which is different from an environment that exists and is empty.
    """
    if not sites:
        return None
    found: dict[str, str] = {}
    for site in sites:
        try:
            entries = sorted(site.glob("*.dist-info"))
        except OSError:
            continue
        for dist_info in entries:
            name, _, version = dist_info.name.removesuffix(".dist-info").rpartition("-")
            if name and version:
                found.setdefault(normalize(name), version)
    return found


def _this_interpreter() -> dict[str, str]:
    found: dict[str, str] = {}
    for dist in metadata.distributions():
        name = dist.metadata["Name"] if dist.metadata else None
        if name:
            found.setdefault(normalize(str(name)), dist.version)
    return found


def _same_place(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return False


def _inside(root: Path, candidate: str) -> bool:
    try:
        return Path(candidate).resolve().is_relative_to(root.resolve())
    except (OSError, ValueError):
        return False


def find_environment(root: Path, environment: Path | None = None) -> Environment:
    """The environment whose installed versions should be used for the project at `root`.

    In order: one the caller named, the project's own `.venv` or `venv`, the environment active in this shell when it is this very project
    being checked, and the interpreter running StockTake when that happens to be the project's environment.

    Where none of those holds, nothing is claimed. Reporting a version out of somebody else's environment — StockTake's own, when it is
    installed as a standalone tool, or a different project's when `--root` points elsewhere — would be a wrong answer on a security check,
    which is worse than admitting we do not know (NFR-7).
    """
    if environment is not None:
        return Environment(_read_site_packages(_site_packages(environment)), str(environment))

    for name in VENV_NAMES:
        versions = _read_site_packages(_site_packages(root / name))
        if versions is not None:
            return Environment(versions, name)

    active = os.environ.get("VIRTUAL_ENV")
    if active and _same_place(root, Path.cwd()):
        versions = _read_site_packages(_site_packages(Path(active)))
        if versions is not None:
            return Environment(versions, "the active virtual environment")

    if _inside(root, os.environ.get("VIRTUAL_ENV") or sys.prefix):
        return Environment(_this_interpreter(), "the interpreter running StockTake")

    return Environment(None, "none found")


def installed_version(name: str) -> str | None:
    """The version of a package present in *this* interpreter's environment, or None when it is not installed."""
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def installed_for(root: Path, environment: Path | None = None) -> InstalledFn:
    """How to answer "what version is installed" for the project being checked."""
    return find_environment(root, environment).version


def iter_files(root: Path, excludes: Sequence[str]) -> Iterator[Path]:
    """Every file under root, in a stable order, without descending into the folders the project excluded.

    The pruning is not an optimisation to be skipped: a single virtual environment holds tens of thousands of files, most of them manifests
    belonging to somebody else's package.
    """
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        dirnames[:] = sorted(d for d in dirnames if not excluded((here / d).relative_to(root).as_posix(), excludes))
        for name in sorted(filenames):
            path = here / name
            if not excluded(path.relative_to(root).as_posix(), excludes):
                yield path


def _declares_npm_dependencies(text: str) -> bool:
    """Whether a package.json actually declares dependencies, as opposed to being a bare manifest holding only scripts or metadata."""
    try:
        data = json.loads(text)
    except ValueError:
        return False
    return isinstance(data, dict) and any(
        data.get(key) for key in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies")
    )


@dataclass(frozen=True, slots=True)
class Scan:
    """What walking a project turned up: what it declares, and what could not be read.

    The second half is not an afterthought. A scan that returned only the dependencies had nowhere to put "I was meant to read this file and
    failed", so it dropped it, and a project whose `package.json` was truncated got a clean report (docs/adr/0009).
    """

    deps: list[Dep] = field(default_factory=list)
    unreadable: list[Unreadable] = field(default_factory=list)


def scan(root: Path, config: Config | None = None, installed: InstalledFn | None = None, groups: Sequence[str] | None = None) -> Scan:
    """Every dependency the project declares, in the order the files were walked, and every manifest that defeated its reader.

    `installed` answers what is present in the project's environment; the default works it out with `installed_for`.

    Which readers run comes from the project's `ecosystems` setting, so a project that only wants its Python pins checked never loads the npm
    reader and never asks the npm registry anything. `groups` overrides that, for tests and for a caller that knows better.
    """
    config = config or Config()
    context = Context(root=root, installed=installed or installed_for(root))
    chosen = groups if groups is not None else config.ecosystems
    active = [r for r in READERS if chosen is None or r.group in chosen]

    found = Scan()
    for path in iter_files(root, config.excludes):
        wanted = [r for r in active if r.interested(path)]
        if not wanted:
            continue
        relative = path.relative_to(root).as_posix()
        try:
            text = read_manifest(path)
        except UnreadableManifest as exc:
            found.unreadable.append(Unreadable(relative, exc.reason))
            continue
        for one in wanted:
            try:
                # Readers are generators, so the reading happens here and a failure surfaces here. Whatever a reader managed to yield before
                # giving up is kept: those dependencies are real, and the file is reported as unreadable alongside them.
                found.deps.extend(one.read(path, text, context))
            except UnreadableManifest as exc:
                found.unreadable.append(Unreadable(relative, exc.reason))
    return found


def unread_manifests(root: Path, config: Config | None = None) -> Unread:
    """Dependency manifests of a kind no registered reader understands, relative to the project root.

    Adding a reader shrinks this on its own, which is the point: it is derived from what the readers claim to be interested in, never from a
    hard-coded list of what is supported.

    A project may accept one in its config, which stops it being reported — but it is still carried in `Unread.accepted` and in the JSON
    report, because an unchecked surface that has become invisible is exactly what this tool exists to prevent.
    """
    config = config or Config()
    reported: list[str] = []
    accepted: list[str] = []
    for path in iter_files(root, config.excludes):
        if any(r.interested(path) for r in READERS):
            continue
        if not any(fnmatch(path.name, kind) for kind in MANIFEST_KINDS):
            continue
        if path.name == "package.json":
            try:
                if not _declares_npm_dependencies(read_manifest(path)):
                    continue
            except UnreadableManifest:
                pass  # it could not be read, so whether it declares anything is unknown — which is a reason to name it, not to drop it
        relative = path.relative_to(root).as_posix()
        (accepted if excluded(relative, config.accept_unread) else reported).append(relative)
    return Unread(tuple(sorted(reported)), tuple(sorted(accepted)))
