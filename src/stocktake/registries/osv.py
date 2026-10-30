"""OSV (osv.dev): what is publicly known against an exact version.

One batched request asks about every coordinate at once, then each advisory is fetched for its detail. Withdrawn advisories — the ones whose
publishers retracted them — are left out, and what remains is merged so that a GHSA and its PYSEC twin count as one problem rather than two.

The report never says "safe" on the strength of this. OSV's coverage is good for PyPI and npm and absent for plenty else, so the honest claim
is "no known advisories" (NFR-7).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from stocktake.advisories import merge_advisories
from stocktake.models import Advisory, normalize
from stocktake.registries.base import Coordinate
from stocktake.registries.http import Cache
from stocktake.versions import release_tuple


class OSV:
    BATCH_URL = "https://api.osv.dev/v1/querybatch"
    VULN_URL = "https://api.osv.dev/v1/vulns/{id}"

    # Our ecosystem names mapped to OSV's. An ecosystem absent from here is one OSV cannot answer for, and is skipped rather than guessed at.
    ECOSYSTEMS: Mapping[str, str] = {"PyPI": "PyPI"}

    def __init__(self, cache: Cache) -> None:
        self.cache = cache

    def advisories(self, wanted: Sequence[Coordinate]) -> Mapping[Coordinate, tuple[Advisory, ...]]:
        askable = [c for c in wanted if c[0] in self.ECOSYSTEMS]
        if not askable:
            return {}
        body = {
            "queries": [
                {"package": {"name": normalize(name), "ecosystem": self.ECOSYSTEMS[eco]}, "version": version}
                for eco, name, version in askable
            ]
        }
        result = self.cache.get(self.BATCH_URL, body)

        found: dict[Coordinate, tuple[Advisory, ...]] = {}
        for (eco, name, version), entry in zip(askable, (result or {}).get("results", []), strict=False):
            advisories = []
            for vulnerability in (entry or {}).get("vulns", []):
                detail = self.cache.get(self.VULN_URL.format(id=vulnerability["id"])) or {}
                if detail.get("withdrawn"):
                    continue  # the publisher retracted it; reporting it would be a false positive
                advisories.append(self._advisory(str(vulnerability["id"]), detail, name))
            if advisories:
                found[eco, normalize(name), version] = tuple(merge_advisories(advisories))
        return found

    @staticmethod
    def _advisory(identifier: str, detail: dict[str, Any], name: str) -> Advisory:
        """One advisory, keeping only the fixed versions that belong to the package we asked about.

        An advisory often covers several packages at once, so the fixed versions have to be filtered by name or the report ends up naming an
        upgrade target from an entirely different project.
        """
        fixed = sorted(
            {
                event["fixed"]
                for affected in detail.get("affected", [])
                if normalize(str(affected.get("package", {}).get("name", name))) == normalize(name)
                for span in affected.get("ranges", [])
                for event in span.get("events", [])
                if "fixed" in event
            },
            key=release_tuple,
        )
        return Advisory(
            id=identifier,
            severity=str((detail.get("database_specific") or {}).get("severity") or ""),
            summary=(detail.get("summary") or "")[:160],  # a summary, not an essay; the id is there for the full text
            aliases=tuple(str(a) for a in detail.get("aliases") or []),
            fixed=tuple(fixed),
        )
