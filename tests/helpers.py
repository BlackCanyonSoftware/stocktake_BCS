"""A stand-in for the network, and the small builders every test module uses.

The network is passed in everywhere (docs/ARCHITECTURE.md), so every test but one runs with no connection at all. `FakeNet` records the URLs
it was asked for, which is how a test can assert that a request was *not* made — the only way to prove the cache works or that a disabled
ecosystem stays quiet.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from stocktake.models import Dep
from stocktake.registries import Cache, OfflineError, RateLimited, Registries
from stocktake.registries.osv import OSV

ROOT = Path(__file__).resolve().parents[1]

# A fixed date, so a policy entry that has "run out" stays run out next year.
TODAY = date(2026, 10, 29)


class FakeNet:
    """Every registry, faked, described by what each one would answer.

    - `pypi`:    {name: (newest version, [versions whose every file is yanked])}
    - `npm`:     {name: newest version}
    - `osv`:     {(name, version): [advisory id]}
    - `details`: {advisory id: the detail document OSV would return}
    - `github`:  {"owner/repo": "v1.2.3"}
    """

    def __init__(
        self,
        pypi: dict[str, tuple[str, list[str]]] | None = None,
        osv: dict[tuple[str, str], list[str]] | None = None,
        details: dict[str, dict] | None = None,
        github: dict[str, str] | None = None,
        npm: dict[str, str] | None = None,
    ) -> None:
        self.pypi = pypi or {}
        self.npm = npm or {}
        self.osv = osv or {}
        self.details = details or {}
        self.github = github or {}
        self.calls: list[str] = []
        self.offline = False
        self.limited: set[str] = set()  # substrings of URLs that answer 429

    def __call__(self, url: str, body: dict | None = None):
        self.calls.append(url)
        if self.offline:
            raise OfflineError("no route to host")
        if any(fragment in url for fragment in self.limited):
            raise RateLimited(f"{url} answered 429")

        if url.startswith("https://pypi.org/pypi/"):
            name = url.split("/pypi/")[1].split("/")[0]
            if name not in self.pypi:
                return None
            latest, withdrawn = self.pypi[name]
            releases = {latest: [{"yanked": False}], **{v: [{"yanked": True}] for v in withdrawn}}
            return {"info": {"version": latest}, "releases": releases}

        if url.startswith("https://registry.npmjs.org/"):
            name = url.removeprefix("https://registry.npmjs.org/").removesuffix("/latest")
            return {"version": self.npm[name]} if name in self.npm else None

        if url == OSV.BATCH_URL:
            assert body is not None, "the OSV batch endpoint is a POST"
            return {
                "results": [{"vulns": [{"id": i} for i in self.osv.get((q["package"]["name"], q["version"]), [])]} for q in body["queries"]]
            }

        if url.startswith("https://api.osv.dev/v1/vulns/"):
            return self.details.get(url.rsplit("/", 1)[1])

        if url.startswith("https://api.github.com/repos/"):
            repo = url.split("/repos/")[1].split("/releases")[0]
            return {"tag_name": self.github[repo]} if repo in self.github else None

        raise AssertionError(f"the code under test asked for an unexpected URL: {url}")

    def asked_about(self, fragment: str) -> bool:
        return any(fragment in url for url in self.calls)


def registries(tmp_path: Path, net: FakeNet, clock=lambda: 1000.0, **kwargs) -> Registries:
    """Real registry clients and a real cache, with the network replaced and the cache kept in a temporary directory."""
    return Registries(Cache(fetch=net, path=tmp_path / "cache.json", now=clock, **kwargs))


def pin(name: str, version: str | None, source: str = "docker/dev/Dockerfile:1", spec: str | None = None, role: str = "image") -> Dep:
    """A pinned PyPI dependency, for the judgement tests that do not care where it came from."""
    return Dep("PyPI", name, version, source, spec if spec is not None else (f"=={version}" if version else ""), role)


def advisory_detail(summary: str = "s", severity: str = "", aliases=(), fixed=(), package: str = "", withdrawn: str = "") -> dict:
    """The shape OSV returns for one advisory, with only the parts this tool reads."""
    detail: dict = {"summary": summary, "aliases": list(aliases)}
    if severity:
        detail["database_specific"] = {"severity": severity}
    if withdrawn:
        detail["withdrawn"] = withdrawn
    if fixed:
        detail["affected"] = [
            {"package": {"name": package or "x"}, "ranges": [{"events": [{"introduced": "0"}, *({"fixed": f} for f in fixed)]}]}
        ]
    return detail


def by_name(report) -> dict:
    return {f.dep.name: f for f in report.findings}
