"""What a reader is: something that turns one kind of file into dependencies.

A reader never touches the network, and nothing outside this package reads a project file (docs/adr/0003). That separation is what lets every
reader be tested with a string and a temporary directory, with no fake network at all.

Adding an ecosystem means a new module beside this one, imported in `__init__.py`, plus a registry client and a guard test. Nothing existing
changes.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from stocktake.models import Dep

InstalledFn = Callable[[str], str | None]


@dataclass(frozen=True, slots=True)
class Context:
    """Everything a reader may know besides the file in front of it.

    `installed` answers what version of a package is present in this environment, so a reader can report the version actually in use without
    importing `importlib.metadata` itself. That is also what makes the behaviour testable with a dictionary.
    """

    root: Path
    installed: InstalledFn

    def source(self, path: Path, line: int | None = None) -> str:
        """How a finding names where it came from: a path relative to the project root, and a line number when there is one."""
        relative = path.relative_to(self.root).as_posix()
        return f"{relative}:{line}" if line else relative


ReadFn = Callable[[Path, str, Context], Iterable[Dep]]


@dataclass(frozen=True, slots=True)
class Reader:
    """One registered reader: which group of ecosystems it belongs to, which files it wants, and how it reads them."""

    group: str  # the name a project enables in its config: "python", "binaries", "npm", "workflows", "containers"
    interested: Callable[[Path], bool]
    read: ReadFn
    description: str = ""


READERS: list[Reader] = []


def reader(group: str, interested: Callable[[Path], bool], description: str = "") -> Callable[[ReadFn], ReadFn]:
    """Register a reading function. Used as a decorator at the bottom of each reader module."""

    def register(function: ReadFn) -> ReadFn:
        first_line = (function.__doc__ or "").strip().splitlines()
        READERS.append(Reader(group, interested, function, description or (first_line[0] if first_line else function.__name__)))
        return function

    return register


def groups() -> tuple[str, ...]:
    """Every group a project could enable, in registration order."""
    seen = dict.fromkeys(r.group for r in READERS)
    return tuple(seen)
