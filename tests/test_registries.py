"""The registry side: the cache, and what each client makes of what it is told.

Every test here replaces the network with `FakeNet` and the cache with a file in `tmp_path`, so nothing reaches outside and nothing depends
on the real clock.
"""

import contextlib
import json
from urllib.error import HTTPError, URLError

import pytest

from stocktake.models import Advisory
from stocktake.registries import Cache, GitHub, Npm, OfflineError, PyPI, RateLimited, Versions, default_fetch
from stocktake.registries.http import RETRY_ATTEMPTS
from stocktake.registries.osv import OSV

from helpers import FakeNet, advisory_detail, registries


def cache(tmp_path, net, clock=lambda: 1000.0, **kwargs):
    return Cache(fetch=net, path=tmp_path / "cache.json", now=clock, **kwargs)


# ---------- PyPI ----------
def test_pypi_gives_the_newest_release_and_the_withdrawn_ones(tmp_path):
    net = FakeNet(pypi={"pillow": ("12.4.0", ["12.3.1"])})
    assert PyPI(cache(tmp_path, net)).latest("pillow") == Versions(latest="12.4.0", withdrawn=frozenset({"12.3.1"}))


def test_a_release_is_only_withdrawn_when_every_file_in_it_is(tmp_path):
    # One yanked wheel beside a good source distribution is still installable; calling that withdrawn would be a false failure.
    def net(url, body=None):
        return {"info": {"version": "2.0"}, "releases": {"1.0": [{"yanked": True}, {"yanked": False}], "0.9": [{"yanked": True}]}}

    assert PyPI(cache(tmp_path, net)).latest("x") == Versions(latest="2.0", withdrawn=frozenset({"0.9"}))


def test_a_release_with_no_files_is_not_called_withdrawn(tmp_path):
    def net(url, body=None):
        return {"info": {"version": "2.0"}, "releases": {"1.0": []}}

    assert PyPI(cache(tmp_path, net)).latest("x").withdrawn == frozenset()


def test_a_package_pypi_has_never_heard_of_is_none_not_an_error(tmp_path):
    assert PyPI(cache(tmp_path, FakeNet())).latest("nothere") is None


def test_the_name_is_normalised_before_it_is_asked_about(tmp_path):
    net = FakeNet(pypi={"typing-extensions": ("4.12.0", [])})
    assert PyPI(cache(tmp_path, net)).latest("Typing_Extensions") is not None


# ---------- npm ----------
def test_npm_gives_the_newest_release(tmp_path):
    net = FakeNet(npm={"koffi": "3.3.9"})
    assert Npm(cache(tmp_path, net)).latest("koffi") == Versions(latest="3.3.9")


def test_npm_is_asked_for_only_the_latest_rather_than_every_version_ever_published(tmp_path):
    net = FakeNet(npm={"koffi": "3.3.9"})
    Npm(cache(tmp_path, net)).latest("koffi")
    assert net.calls == ["https://registry.npmjs.org/koffi/latest"]


def test_a_scoped_name_keeps_its_slash_in_the_path(tmp_path):
    net = FakeNet(npm={"@babel/traverse": "7.28.0"})
    assert Npm(cache(tmp_path, net)).latest("@babel/traverse") == Versions(latest="7.28.0")
    assert net.calls == ["https://registry.npmjs.org/@babel/traverse/latest"]


def test_npm_names_are_taken_as_written_because_the_registry_is_case_sensitive(tmp_path):
    net = FakeNet(npm={"Left-Pad": "1.3.0"})
    assert Npm(cache(tmp_path, net)).latest("Left-Pad") is not None
    assert Npm(cache(tmp_path, net)).latest("left-pad") is None, "a different spelling is a different package to npm"


def test_a_package_npm_has_never_heard_of_is_none(tmp_path):
    assert Npm(cache(tmp_path, FakeNet())).latest("nothere") is None


def test_npm_reports_nothing_as_withdrawn_because_it_has_no_such_idea(tmp_path):
    # It has deprecated versions, which are far looser and would be a false failure.
    net = FakeNet(npm={"koffi": "3.3.9"})
    assert Npm(cache(tmp_path, net)).latest("koffi").withdrawn == frozenset()


# ---------- GitHub ----------
def test_github_gives_the_newest_release_tag_without_its_leading_v(tmp_path):
    net = FakeNet(github={"mostlygeek/llama-swap": "v263"})
    assert GitHub(cache(tmp_path, net)).latest("mostlygeek/llama-swap") == Versions(latest="263")


def test_a_repository_with_no_release_at_all_is_none(tmp_path):
    assert GitHub(cache(tmp_path, FakeNet())).latest("o/r") is None


# ---------- OSV ----------
def test_osv_is_asked_once_for_everything_and_answers_per_coordinate(tmp_path):
    net = FakeNet(
        osv={("a", "1.0"): ["GHSA-1"], ("b", "2.0"): ["GHSA-2"]},
        details={"GHSA-1": advisory_detail("first", "HIGH", fixed=["1.1"], package="a"), "GHSA-2": advisory_detail("second")},
    )
    found = OSV(cache(tmp_path, net)).advisories([("PyPI", "a", "1.0"), ("PyPI", "b", "2.0"), ("PyPI", "c", "3.0")])

    assert set(found) == {("PyPI", "a", "1.0"), ("PyPI", "b", "2.0")}
    assert found[("PyPI", "a", "1.0")] == (Advisory(id="GHSA-1", severity="HIGH", summary="first", fixed=("1.1",)),)
    assert net.calls.count(OSV.BATCH_URL) == 1


def test_an_ecosystem_osv_cannot_answer_for_is_not_asked_about(tmp_path):
    # OSV has no key that identifies "the amd64 tarball from this repository's releases", so it is never asked.
    net = FakeNet()
    assert OSV(cache(tmp_path, net)).advisories([("GitHub", "o/r", "1.0")]) == {}
    assert net.calls == []


def test_osv_answers_for_npm_too_and_is_asked_with_the_exact_name(tmp_path):
    net = FakeNet(
        osv={("@babel/traverse", "7.23.1"): ["GHSA-npm"]}, details={"GHSA-npm": advisory_detail("prototype pollution", "CRITICAL")}
    )
    found = OSV(cache(tmp_path, net)).advisories([("npm", "@babel/traverse", "7.23.1")])
    assert [a.id for a in found[("npm", "@babel/traverse", "7.23.1")]] == ["GHSA-npm"]


def test_a_pypi_name_is_normalised_for_osv_but_an_npm_name_is_not(tmp_path):
    net = FakeNet(
        osv={("typing-extensions", "4.0.0"): ["GHSA-py"], ("Left-Pad", "1.0.0"): ["GHSA-js"]},
        details={"GHSA-py": advisory_detail(), "GHSA-js": advisory_detail()},
    )
    found = OSV(cache(tmp_path, net)).advisories([("PyPI", "Typing_Extensions", "4.0.0"), ("npm", "Left-Pad", "1.0.0")])
    assert ("PyPI", "typing-extensions", "4.0.0") in found
    assert ("npm", "left-pad", "1.0.0") in found, "the result is keyed by the comparison name"


def test_a_withdrawn_advisory_is_not_reported(tmp_path):
    net = FakeNet(
        osv={("x", "1.0"): ["GHSA-w"]}, details={"GHSA-w": advisory_detail("published in error", withdrawn="2026-01-01T00:00:00Z")}
    )
    assert OSV(cache(tmp_path, net)).advisories([("PyPI", "x", "1.0")]) == {}


def test_only_the_fixed_versions_of_the_package_we_asked_about_are_kept(tmp_path):
    # An advisory often covers several packages at once; taking every fixed version would name an upgrade from a different project.
    detail = {
        "summary": "s",
        "affected": [
            {"package": {"name": "other"}, "ranges": [{"events": [{"fixed": "9.9"}]}]},
            {"package": {"name": "x"}, "ranges": [{"events": [{"fixed": "2.0"}]}]},
        ],
    }
    net = FakeNet(osv={("x", "1.0"): ["GHSA-1"]}, details={"GHSA-1": detail})
    found = OSV(cache(tmp_path, net)).advisories([("PyPI", "x", "1.0")])
    assert found[("PyPI", "x", "1.0")][0].fixed == ("2.0",)


def test_aliased_duplicates_arrive_already_merged(tmp_path):
    net = FakeNet(
        osv={("x", "1.0"): ["GHSA-1", "PYSEC-1"]},
        details={
            "GHSA-1": advisory_detail("the real one", "CRITICAL", aliases=["CVE-1"], fixed=["2.0"], package="x"),
            "PYSEC-1": advisory_detail("twin", aliases=["CVE-1", "GHSA-1"]),
        },
    )
    found = OSV(cache(tmp_path, net)).advisories([("PyPI", "x", "1.0")])
    assert [a.id for a in found[("PyPI", "x", "1.0")]] == ["GHSA-1"]


def test_nothing_wanted_means_no_request_at_all(tmp_path):
    net = FakeNet()
    assert OSV(cache(tmp_path, net)).advisories([]) == {}
    assert net.calls == []


# ---------- the cache ----------
def test_answers_are_reused_for_six_hours_and_asked_again_after(tmp_path):
    net = FakeNet(pypi={"a": ("1.0", [])})
    now = [1000.0]

    PyPI(cache(tmp_path, net, lambda: now[0])).latest("a")
    assert len(net.calls) == 1

    PyPI(cache(tmp_path, net, lambda: now[0])).latest("a")
    assert len(net.calls) == 2, "a fresh Cache starts empty until one is flushed"

    kept = cache(tmp_path, net, lambda: now[0])
    PyPI(kept).latest("a")
    kept.flush()
    before = len(net.calls)

    PyPI(cache(tmp_path, net, lambda: now[0] + 3600)).latest("a")
    assert len(net.calls) == before, "an hour later, the answer comes from the cache"

    PyPI(cache(tmp_path, net, lambda: now[0] + 7 * 3600)).latest("a")
    assert len(net.calls) == before + 1, "past six hours, it is asked again"


def test_refresh_ignores_a_perfectly_fresh_cache(tmp_path):
    net = FakeNet(pypi={"a": ("1.0", [])})
    kept = cache(tmp_path, net)
    PyPI(kept).latest("a")
    kept.flush()
    before = len(net.calls)

    PyPI(cache(tmp_path, net, refresh=True)).latest("a")
    assert len(net.calls) == before + 1


def test_a_damaged_cache_file_is_ignored_rather_than_fatal(tmp_path):
    (tmp_path / "cache.json").write_text("{not json", encoding="utf-8")
    net = FakeNet(pypi={"a": ("1.0", [])})
    assert PyPI(cache(tmp_path, net)).latest("a") == Versions(latest="1.0")


def test_a_cache_file_holding_something_that_is_not_an_object_is_ignored(tmp_path):
    (tmp_path / "cache.json").write_text("[1, 2, 3]", encoding="utf-8")
    net = FakeNet(pypi={"a": ("1.0", [])})
    assert PyPI(cache(tmp_path, net)).latest("a") == Versions(latest="1.0")


def test_two_different_request_bodies_to_one_url_do_not_share_an_answer(tmp_path):
    net = FakeNet(osv={("a", "1.0"): ["GHSA-1"]}, details={"GHSA-1": advisory_detail()})
    shared = cache(tmp_path, net)
    client = OSV(shared)

    client.advisories([("PyPI", "a", "1.0")])
    first = len(net.calls)
    client.advisories([("PyPI", "b", "2.0")])
    assert len(net.calls) > first


def test_a_cache_it_cannot_write_does_not_fail_the_run(tmp_path):
    # A directory where the file should be: writing is impossible, and that is not worth failing a check over.
    (tmp_path / "cache.json").mkdir()
    net = FakeNet(pypi={"a": ("1.0", [])})
    kept = cache(tmp_path, net)
    PyPI(kept).latest("a")
    kept.flush()


# ---------- the two failures that must stay apart ----------
def test_being_unable_to_reach_a_service_raises_offline(tmp_path):
    net = FakeNet(pypi={"a": ("1.0", [])})
    net.offline = True
    with pytest.raises(OfflineError, match="no route"):
        PyPI(cache(tmp_path, net)).latest("a")


def test_being_asked_to_slow_down_raises_rate_limited_which_is_a_different_thing(tmp_path):
    net = FakeNet(github={"o/r": "v2"})
    net.limited = {"api.github.com"}
    with pytest.raises(RateLimited, match="429"):
        GitHub(cache(tmp_path, net)).latest("o/r")


def test_a_failed_request_is_not_remembered_as_an_answer(tmp_path):
    net = FakeNet(pypi={"a": ("1.0", [])})
    net.offline = True
    shared = cache(tmp_path, net)
    for _ in range(2):
        with contextlib.suppress(OfflineError):
            PyPI(shared).latest("a")
    assert len(net.calls) == 2, "an exception must not be cached as though it were an answer"


# ---------- the one retry ----------
class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def urlopen_that(monkeypatch, *outcomes):
    """Replace urlopen with one that produces each outcome in turn, and record how many times it was called."""
    calls = []

    def urlopen(request, timeout=None):
        calls.append(getattr(request, "full_url", request))
        outcome = outcomes[min(len(calls), len(outcomes)) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResponse(outcome)

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    monkeypatch.setattr("stocktake.registries.http.time.sleep", lambda _seconds: None)
    return calls


def test_a_connection_that_failed_is_tried_once_more(monkeypatch):
    """The reason this exists: on a real run, two of three requests to one host failed TLS verification and a later attempt worked."""
    calls = urlopen_that(monkeypatch, URLError("[SSL: CERTIFICATE_VERIFY_FAILED]"), {"version": "1.2.3"})
    assert default_fetch("https://registry.npmjs.org/x/latest") == {"version": "1.2.3"}
    assert len(calls) == 2


def test_a_connection_that_keeps_failing_is_reported_as_offline(monkeypatch):
    calls = urlopen_that(monkeypatch, URLError("no route to host"))
    with pytest.raises(OfflineError, match="no route"):
        default_fetch("https://pypi.org/pypi/x/json")
    assert len(calls) == RETRY_ATTEMPTS, "tried, retried, then gave up rather than hammering"


def test_a_service_that_answered_is_never_retried(monkeypatch):
    """A 404 is an answer, and retrying a 429 would make the rate limiting worse."""
    missing = urlopen_that(monkeypatch, HTTPError("https://pypi.org/pypi/x/json", 404, "Not Found", {}, None))
    assert default_fetch("https://pypi.org/pypi/x/json") is None
    assert len(missing) == 1

    limited = urlopen_that(monkeypatch, HTTPError("https://api.github.com/x", 429, "Too Many", {}, None))
    with pytest.raises(RateLimited):
        default_fetch("https://api.github.com/x")
    assert len(limited) == 1


def test_retrying_can_be_switched_off_for_one_call(monkeypatch):
    calls = urlopen_that(monkeypatch, URLError("down"))
    with pytest.raises(OfflineError):
        default_fetch("https://pypi.org/pypi/x/json", attempts=1)
    assert len(calls) == 1


# ---------- the facade ----------
def test_the_facade_routes_by_ecosystem_and_says_which_it_knows(tmp_path):
    net = FakeNet(pypi={"a": ("1.0", [])}, github={"o/r": "v3"})
    asking = registries(tmp_path, net)
    assert set(asking.ecosystems) == {"PyPI", "npm", "GitHub"}
    assert asking.latest("PyPI", "a") == Versions(latest="1.0")
    assert asking.latest("GitHub", "o/r") == Versions(latest="3")


def test_an_ecosystem_with_no_client_answers_none_rather_than_raising(tmp_path):
    assert registries(tmp_path, FakeNet()).latest("Hackage", "aeson") is None
