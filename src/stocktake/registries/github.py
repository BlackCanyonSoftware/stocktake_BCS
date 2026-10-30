"""GitHub releases: the newest release tag of a repository, for the binaries projects download instead of installing from a registry.

These get no advisory check. OSV has no key that identifies "the amd64 tarball from this repository's releases", so claiming to have checked
one would be dishonest; the report says plainly that only the newest tag is known. Mapping a binary back to the module it was built from is
tracked as later work (docs/ROADMAP.md, M6).
"""

from __future__ import annotations

from stocktake.registries.base import Versions
from stocktake.registries.http import Cache


class GitHub:
    ecosystem = "GitHub"
    URL = "https://api.github.com/repos/{repo}/releases/latest"

    def __init__(self, cache: Cache) -> None:
        self.cache = cache

    def latest(self, name: str) -> Versions | None:
        """`name` is `owner/repo`. None when there is no repository, or no release at all."""
        data = self.cache.get(self.URL.format(repo=name))
        if not data or not data.get("tag_name"):
            return None
        return Versions(latest=str(data["tag_name"]).removeprefix("v"))
