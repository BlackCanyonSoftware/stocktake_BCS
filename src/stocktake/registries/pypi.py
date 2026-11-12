"""PyPI: the newest release of a package, and which of its releases have been withdrawn.

A release is counted as withdrawn only when every file in it is yanked. A release with one yanked wheel and a good source distribution is
still installable, and calling that withdrawn would be a false failure.
"""

from __future__ import annotations

from typing import Any

from stocktake.models import normalize
from stocktake.registries.base import Versions
from stocktake.registries.http import Cache


class PyPI:
    ecosystem = "PyPI"
    URL = "https://pypi.org/pypi/{name}/json"

    def __init__(self, cache: Cache) -> None:
        self.cache = cache

    @staticmethod
    def keep(data: Any) -> dict[str, Any] | None:
        """The two things read, out of a document that lists every file of every release.

        PyPI's answer for a long-lived package runs to hundreds of kilobytes of filenames, hashes and upload dates. None of it is read
        twice, so none of it is worth keeping: the cache holds the newest version and which releases are wholly yanked, and nothing else.
        """
        if not isinstance(data, dict) or "info" not in data:
            return None
        releases = data.get("releases") or {}
        return {
            "latest": str(data["info"]["version"]),
            # Withdrawn only when *every* file in the release is yanked: one yanked wheel beside a good sdist is still installable, and
            # calling that withdrawn would be a false failure.
            "withdrawn": sorted(version for version, files in releases.items() if files and all(f.get("yanked") for f in files)),
        }

    def latest(self, name: str) -> Versions | None:
        data = self.cache.get(self.URL.format(name=normalize(name)), keep=self.keep)
        if not data:
            return None
        return Versions(latest=str(data["latest"]), withdrawn=frozenset(data.get("withdrawn") or ()))
