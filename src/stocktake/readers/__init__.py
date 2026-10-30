"""Every reader, imported here so that registering one is a single line in a single place.

A test asserts that every module in this package is imported here, so a reader cannot be written and then silently never run.
"""

from stocktake.readers import dockerfile, python_project  # noqa: F401  (imported for the registration side effect)
from stocktake.readers.base import READERS, Context, InstalledFn, Reader, groups, reader

__all__ = ["READERS", "Context", "InstalledFn", "Reader", "groups", "reader"]
