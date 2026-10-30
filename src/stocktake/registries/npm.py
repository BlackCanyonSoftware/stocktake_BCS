"""The npm registry: the newest release of a package.

Asks for `/<name>/latest` rather than the whole packument. A popular package's full metadata document runs to megabytes of every version it
has ever published; `latest` is a few hundred bytes and answers the only question being asked.

**npm has no equivalent of a yanked release**, so `withdrawn` is always empty here. It has *deprecated* versions, which is a different and
far looser thing — maintainers deprecate for style, for renames and for "use the other one", not only for danger — and treating deprecation
as withdrawal would fail builds for reasons nobody agreed to. Known vulnerabilities come from OSV, the same as everywhere else.
"""

from __future__ import annotations

from urllib.parse import quote

from stocktake.registries.base import Versions
from stocktake.registries.http import Cache


class Npm:
    ecosystem = "npm"
    URL = "https://registry.npmjs.org/{name}/latest"

    def __init__(self, cache: Cache) -> None:
        self.cache = cache

    def latest(self, name: str) -> Versions | None:
        # A scoped name carries a slash that belongs in the path, so `@` and `/` are kept rather than escaped.
        data = self.cache.get(self.URL.format(name=quote(name, safe="@/")))
        if not data or not data.get("version"):
            return None
        return Versions(latest=str(data["version"]))
