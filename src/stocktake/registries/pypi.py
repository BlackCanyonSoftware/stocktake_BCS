"""PyPI: the newest release of a package, and which of its releases have been withdrawn.

A release is counted as withdrawn only when every file in it is yanked. A release with one yanked wheel and a good source distribution is
still installable, and calling that withdrawn would be a false failure.
"""

from __future__ import annotations

from stocktake.models import normalize
from stocktake.registries.base import Versions
from stocktake.registries.http import Cache


class PyPI:
    ecosystem = "PyPI"
    URL = "https://pypi.org/pypi/{name}/json"

    def __init__(self, cache: Cache) -> None:
        self.cache = cache

    def latest(self, name: str) -> Versions | None:
        data = self.cache.get(self.URL.format(name=normalize(name)))
        if not data:
            return None
        releases = data.get("releases") or {}
        withdrawn = frozenset(version for version, files in releases.items() if files and all(f.get("yanked") for f in files))
        return Versions(latest=str(data["info"]["version"]), withdrawn=withdrawn)
