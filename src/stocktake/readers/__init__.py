"""Every reader, imported here so that registering one is a single line in a single place.

A guard test asserts that every module in this package is imported here, so a reader cannot be written and then silently never run.
"""

from stocktake.readers import (  # noqa: F401  (imported for the registration side effect)
    dockerfile,
    npm,
    python_locks,
    python_project,
    python_requirements,
    workflows,
)
from stocktake.readers.base import READERS, Context, InstalledFn, Reader, groups, logical_lines, reader

__all__ = ["READERS", "Context", "InstalledFn", "Reader", "groups", "logical_lines", "reader"]
