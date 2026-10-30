"""`pyproject.toml` and `Pipfile`: what a Python project *declares*, checked at the version actually present.

A declared range is not a version. `pytest>=8` tells you nothing about what is running, so where the package is installed in this environment
that installed version is what gets checked, and the range is kept alongside it as the specifier. Where it is not installed, there is nothing
to check and it is reported as unpinned instead of being quietly dropped.

(Lock files are the other way round — the pin wins there, because a lock file names what *will* be installed. See `python_locks.py`.)
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterable, Iterator
from pathlib import Path

from stocktake.models import Dep
from stocktake.readers.base import Context, reader
from stocktake.readers.pep508 import parse_requirement


def is_pyproject(path: Path) -> bool:
    return path.name == "pyproject.toml"


def is_pipfile(path: Path) -> bool:
    return path.name == "Pipfile"


def _declared(data: dict[str, object]) -> Iterator[tuple[str, str]]:
    """Every requirement string in the file, with the role it plays."""
    project = data.get("project")
    if isinstance(project, dict):
        for item in project.get("dependencies") or []:
            if isinstance(item, str):
                yield item, "runtime"
        optional = project.get("optional-dependencies")
        if isinstance(optional, dict):
            for group in optional.values():
                for item in group or []:
                    if isinstance(item, str):
                        yield item, "dev"
    # PEP 735 dependency groups, which uv writes. An entry may be `{include-group = "..."}` rather than a requirement.
    groups = data.get("dependency-groups")
    if isinstance(groups, dict):
        for group in groups.values():
            for item in group or []:
                if isinstance(item, str):
                    yield item, "dev"


@reader("python", is_pyproject)
def read_pyproject(path: Path, text: str, context: Context) -> Iterable[Dep]:
    """Dependencies declared in pyproject.toml, at the version installed in this environment."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return  # a broken pyproject.toml is that project's problem to report, not this tool's to crash on
    for entry, role in _declared(data):
        parsed = parse_requirement(entry)
        if parsed is None:
            continue
        name, pinned, spec = parsed
        yield Dep("PyPI", name, context.installed(name) or pinned, context.source(path), spec, role)


def _pipfile_spec(value: object) -> str | None:
    """The specifier a Pipfile entry holds: `"*"`, `">=2.0"`, or `{version = "==4.2", extras = [...]}`. None when there is no version at all."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        version = value.get("version")
        return version if isinstance(version, str) else None
    return None


@reader("python", is_pipfile)
def read_pipfile(path: Path, text: str, context: Context) -> Iterable[Dep]:
    """Dependencies declared in a Pipfile, at the version installed in this environment.

    Read so that a project using pipenv is not told its Pipfile is an unreadable manifest while its lock file is being read perfectly well.
    """
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return
    for section, role in (("packages", "runtime"), ("dev-packages", "dev")):
        entries = data.get(section)
        if not isinstance(entries, dict):
            continue
        for name, value in entries.items():
            spec = _pipfile_spec(value)
            if spec is None:
                continue
            tidy = "" if spec.strip() in ("*", "") else spec.strip()
            pinned = tidy.removeprefix("==") if tidy.startswith("==") else None
            yield Dep("PyPI", str(name), context.installed(str(name)) or pinned, context.source(path), tidy, role)
