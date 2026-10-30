"""Walking a project and handing each file to whichever readers want it.

Two jobs, and the second matters as much as the first. One is to collect what the project declares. The other is to notice a manifest of a
kind no reader understands, because the dangerous failure for a tool like this is not a wrong answer, it is a clean-looking report that
quietly missed half the project.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator, Sequence
from fnmatch import fnmatch
from importlib import metadata
from pathlib import Path

from stocktake.config import Config, excluded
from stocktake.models import Dep
from stocktake.readers import READERS, Context, InstalledFn

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


def installed_version(name: str) -> str | None:
    """The version of a package present in this environment, or None when it is not installed."""
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


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


def scan(root: Path, config: Config | None = None, installed: InstalledFn | None = None, groups: Sequence[str] | None = None) -> list[Dep]:
    """Every dependency the project declares, in the order the files were walked.

    `installed` answers what is present in this environment; the default asks this interpreter. `groups` limits which readers run, which is
    how a project that only wants its Python pins checked avoids ever touching the npm registry.
    """
    config = config or Config()
    context = Context(root=root, installed=installed or installed_version)
    active = [r for r in READERS if groups is None or r.group in groups]

    deps: list[Dep] = []
    for path in iter_files(root, config.excludes):
        wanted = [r for r in active if r.interested(path)]
        if not wanted:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue  # unreadable is not the same as absent, but neither is it this tool's business to fix
        for one in wanted:
            deps.extend(one.read(path, text, context))
    return deps


def unread_manifests(root: Path, config: Config | None = None) -> list[str]:
    """Dependency manifests of a kind no registered reader understands, relative to the project root.

    Adding a reader shrinks this list on its own, which is the point: the list is derived from what the readers claim, never hard-coded.
    """
    config = config or Config()
    found = []
    for path in iter_files(root, config.excludes):
        if any(r.interested(path) for r in READERS):
            continue
        if not any(fnmatch(path.name, kind) for kind in MANIFEST_KINDS):
            continue
        if path.name == "package.json":
            try:
                if not _declares_npm_dependencies(path.read_text(encoding="utf-8", errors="replace")):
                    continue
            except OSError:
                continue
        found.append(path.relative_to(root).as_posix())
    return sorted(found)
