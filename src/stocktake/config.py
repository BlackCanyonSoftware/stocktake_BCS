"""Where a project says what to read, what to skip and what has been decided: `.stocktake.toml` at its root, or a `[tool.stocktake]` table in
`pyproject.toml` for a Python project that would rather not have another file (docs/adr/0002).

The point of this module is that nothing in StockTake's source knows about any particular project. The original's hard-coded exclusion list,
naming folders that exist in exactly one repository, is what made it impossible to reuse; everything of that kind lives here instead.

Every value is validated when it is read, and a file that cannot be understood is refused rather than quietly replaced by defaults — a policy
that silently stopped applying would be the one failure a policy file must not have.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from stocktake.policy import Policy, policy_from_toml
from stocktake.readers import groups as reader_groups

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

DEFAULT_CACHE_TTL_HOURS = 6.0

# Every key a config file may set, and every key `[cache]` may set. A file is refused for anything else, which is the only way a typo gets
# noticed: `excludes = [".venv"]` was read as a file with no excludes at all, and silently scanning a virtual environment looks exactly like
# scanning a project with a great many dependencies.
KNOWN_KEYS: frozenset[str] = frozenset({"exclude", "ecosystems", "accept_unread", "environment", "cache", "policy"})
KNOWN_CACHE_KEYS: frozenset[str] = frozenset({"ttl_hours"})


class ConfigError(ValueError):
    """The config file could not be read. Said plainly and at once, rather than guessing at a default."""


@dataclass(frozen=True, slots=True)
class Config:
    """What one project has configured."""

    policy: Policy = field(default_factory=Policy)
    exclude: tuple[str, ...] = ()  # added to DEFAULT_EXCLUDES, never replacing them
    ecosystems: tuple[str, ...] | None = None  # which reader groups to run; None means all of them
    accept_unread: tuple[str, ...] = ()  # manifests the project knows StockTake cannot read, and accepts
    environment: str | None = None  # the Python environment whose installed versions to use, relative to the project root
    cache_ttl_hours: float = DEFAULT_CACHE_TTL_HOURS
    source: str | None = None  # the file this came from, so it can be said which one was used

    @property
    def excludes(self) -> tuple[str, ...]:
        return DEFAULT_EXCLUDES + self.exclude

    @property
    def cache_ttl_seconds(self) -> int:
        return int(self.cache_ttl_hours * 3600)


def excluded(relative_path: str, patterns: Sequence[str]) -> bool:
    """Whether a path relative to the project root matches one of a set of patterns.

    A pattern matches either the whole relative path (`tests/fixtures`) or any single segment of it (`.venv`, `*.egg-info`), so the obvious
    thing to write in a config file is the thing that works. Used for both `exclude` and `accept_unread`.
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


def _string_list(path: Path, table: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = table.get(key) or []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ConfigError(f"{path}: `{key}` must be a list of strings")
    return tuple(value)


def _ecosystems(path: Path, table: Mapping[str, Any]) -> tuple[str, ...] | None:
    if "ecosystems" not in table:
        return None  # not mentioned means all of them, which is what a project with no config gets
    chosen = _string_list(path, table, "ecosystems")
    known = reader_groups()
    unknown = [name for name in chosen if name not in known]
    if unknown:
        raise ConfigError(f"{path}: unknown ecosystem(s) {', '.join(sorted(unknown))}; this version knows {', '.join(known)}")
    return chosen


def _cache_ttl_hours(path: Path, table: Mapping[str, Any]) -> float:
    cache = table.get("cache") or {}
    if not isinstance(cache, Mapping):
        raise ConfigError(f"{path}: `[cache]` must be a table")
    _reject_unknown_keys(path, cache, KNOWN_CACHE_KEYS, "unknown setting in `[cache]`")
    hours = cache.get("ttl_hours", DEFAULT_CACHE_TTL_HOURS)
    if isinstance(hours, bool) or not isinstance(hours, int | float) or hours <= 0:
        raise ConfigError(f"{path}: `cache.ttl_hours` must be a positive number")
    return float(hours)


def _environment(path: Path, table: Mapping[str, Any]) -> str | None:
    value = table.get("environment")
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{path}: `environment` must be a path, as a string")
    return value


def _suggest(unknown: str, known: frozenset[str]) -> str:
    """A `did you mean` for a misspelt key, when one known key is obviously what was meant.

    Silent when nothing is close enough: a wrong guess is worse than none, because it sends the reader to rewrite a line that was not the
    problem.
    """
    close = [name for name in sorted(known) if name.startswith(unknown[:4]) or unknown.startswith(name[:4]) or name == unknown.rstrip("s")]
    return f"; did you mean `{close[0]}`?" if close else ""


def _reject_unknown_keys(path: Path, table: Mapping[str, Any], known: frozenset[str], where: str) -> None:
    """Refuse a key StockTake does not recognise, rather than ignoring it.

    This module's docstring has always claimed every value is validated as it is read, and for the values named here it was true — but a key
    nobody named was not a value, so it went straight past. The whole point of refusing a config file StockTake cannot understand is that a
    setting which has silently stopped applying is the one failure a policy file must not have, and a misspelt key is exactly that.
    """
    unknown = sorted(key for key in table if key not in known)
    if not unknown:
        return
    named = ", ".join(f"`{key}`" for key in unknown)
    suggestion = _suggest(unknown[0], known) if len(unknown) == 1 else ""
    raise ConfigError(f"{path}: {where}: {named}{suggestion}. Valid: {', '.join(sorted(known))}")


def _build(path: Path, table: Mapping[str, Any]) -> Config:
    _reject_unknown_keys(path, table, KNOWN_KEYS, "unknown setting")
    policy = table.get("policy") or {}
    if not isinstance(policy, Mapping):
        raise ConfigError(f"{path}: `[policy]` must be a table")
    return Config(
        policy=policy_from_toml(policy),
        exclude=_string_list(path, table, "exclude"),
        ecosystems=_ecosystems(path, table),
        accept_unread=_string_list(path, table, "accept_unread"),
        environment=_environment(path, table),
        cache_ttl_hours=_cache_ttl_hours(path, table),
        source=str(path),
    )


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
