"""Where a project says what to skip and what has been decided: `.stocktake.toml` at its root, or a `[tool.stocktake]` table in
`pyproject.toml` for a Python project that would rather not have another file (docs/adr/0002).

Deliberately small for now. Choosing which ecosystems to read and how long to cache belongs here too and arrives with Milestone 1
(docs/ROADMAP.md); what matters at this point is that no path belonging to any particular project is written into the source, which is exactly
what made the original un-reusable.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from stocktake.policy import Policy, policy_from_toml

CONFIG_NAME = ".stocktake.toml"

# Folders no project means to have scanned. Generic on purpose: anything project-specific belongs in that project's own config file.
DEFAULT_EXCLUDES: tuple[str, ...] = (
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    "site-packages",
    "dist",
    "build",
    "*.egg-info",
    ".tox",
    ".nox",
    ".eggs",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".idea",
    ".vscode",
)


class ConfigError(ValueError):
    """The config file could not be read. Said plainly and at once, rather than guessing at a default."""


@dataclass(frozen=True, slots=True)
class Config:
    """What one project has configured."""

    policy: Policy = field(default_factory=Policy)
    exclude: tuple[str, ...] = ()  # added to DEFAULT_EXCLUDES, never replacing them
    source: str | None = None  # the file this came from, so the report can say which one was used

    @property
    def excludes(self) -> tuple[str, ...]:
        return DEFAULT_EXCLUDES + self.exclude


def excluded(relative_path: str, patterns: Sequence[str]) -> bool:
    """Whether a path relative to the project root is one the project asked not to scan.

    A pattern matches either the whole relative path (`tests/fixtures`) or any single segment of it (`.venv`, `*.egg-info`), so the obvious
    thing to write in a config file is the thing that works.
    """
    segments = relative_path.split("/")
    return any(fnmatch(relative_path, p) or any(fnmatch(segment, p) for segment in segments) for p in patterns)


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except OSError as exc:
        raise ConfigError(f"{path}: could not be read ({exc})") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: is not valid TOML ({exc})") from exc


def _build(path: Path, table: Mapping[str, Any]) -> Config:
    exclude = table.get("exclude") or []
    if not isinstance(exclude, list) or any(not isinstance(item, str) for item in exclude):
        raise ConfigError(f"{path}: `exclude` must be a list of strings")
    policy = table.get("policy") or {}
    if not isinstance(policy, Mapping):
        raise ConfigError(f"{path}: `[policy]` must be a table")
    return Config(policy=policy_from_toml(policy), exclude=tuple(exclude), source=str(path))


def load_config(root: Path, path: Path | None = None) -> Config:
    """The config for a project: an explicitly named file, else `.stocktake.toml`, else `[tool.stocktake]` in `pyproject.toml`, else defaults.

    `.stocktake.toml` wins over `pyproject.toml` rather than merging with it, and `Config.source` records which file was used.
    """
    if path is not None:
        return _build(path, _read_toml(path))

    own = root / CONFIG_NAME
    if own.is_file():
        return _build(own, _read_toml(own))

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        table = _read_toml(pyproject).get("tool", {}).get("stocktake")
        if isinstance(table, Mapping):
            return _build(pyproject, table)

    return Config()
