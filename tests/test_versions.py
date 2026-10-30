"""Comparing versions and naming the size of a jump."""

import itertools

import pytest

from stocktake.versions import is_newer, release_tuple, semver_key, update_kind


@pytest.mark.parametrize(
    ("latest", "current", "newer", "kind"),
    [
        ("2.0.0", "1.9.9", True, "major"),
        ("1.10.0", "1.9.9", True, "minor"),
        ("1.9.10", "1.9.9", True, "patch"),
        ("1.9.9", "1.9.9", False, "patch"),
        ("263", "262", True, "major"),  # a bare release number, as GitHub release tags often are
        ("1.0.0", "1.0.0rc1", True, "patch"),  # a release really is newer than its own candidate
        ("0.6.6", "0.7.0", False, "minor"),  # and 0.6.6 is not newer than 0.7.0, however it sorts as a string
        ("2.0", "2.0.0", False, "patch"),  # equal, written differently
    ],
)
def test_versions_are_compared_and_the_size_of_the_jump_is_named(latest, current, newer, kind):
    assert is_newer(latest, current) is newer
    if newer:
        assert update_kind(latest, current) == kind


def test_a_version_with_no_numbers_sorts_below_everything_rather_than_raising():
    assert release_tuple("") == ()
    assert release_tuple("latest") == ()
    assert is_newer("1.0", "latest") is True


def test_a_leading_v_and_extra_segments_do_not_confuse_the_comparison():
    assert release_tuple("v2.16.0") == (2, 16, 0)
    assert is_newer("v2.16.1", "2.16.0") is True


# ---------- SemVer, for npm ----------
SEMVER_ORDER = [
    "1.0.0-alpha",
    "1.0.0-alpha.1",
    "1.0.0-alpha.beta",
    "1.0.0-beta",
    "1.0.0-beta.2",
    "1.0.0-beta.11",
    "1.0.0-rc.1",
    "1.0.0",
    "1.0.1",
    "1.1.0",
    "2.0.0",
]


def test_semver_precedence_follows_the_specification():
    """The order in the SemVer specification itself, including the two rules a naive comparison gets wrong."""
    assert sorted(SEMVER_ORDER, key=semver_key) == SEMVER_ORDER


@pytest.mark.parametrize(("earlier", "later"), list(itertools.pairwise(SEMVER_ORDER)))
def test_each_semver_version_is_newer_than_the_one_before_it(earlier, later):
    assert is_newer(later, earlier, "npm") is True
    assert is_newer(earlier, later, "npm") is False


def test_a_release_is_newer_than_its_own_prerelease_which_string_order_gets_backwards():
    assert "1.0.0" < "1.0.0-beta", "as strings, the release sorts first"
    assert is_newer("1.0.0", "1.0.0-beta", "npm") is True, "as versions, it does not"


def test_a_numeric_prerelease_identifier_ranks_below_an_alphanumeric_one():
    assert is_newer("1.0.0-alpha.beta", "1.0.0-alpha.1", "npm") is True


def test_build_metadata_is_ignored_for_precedence():
    assert semver_key("1.0.0+build.99") == semver_key("1.0.0")
    assert is_newer("1.0.0+build.99", "1.0.0", "npm") is False


def test_a_short_version_is_padded_rather_than_rejected():
    assert is_newer("1.2", "1.1.9", "npm") is True
    assert is_newer("2", "1.9.9", "npm") is True


# ---------- tags that move ----------
@pytest.mark.parametrize(
    ("latest", "pinned", "newer"),
    [
        # `@v7` already points at the newest v7, so a new v7 patch is not an update anybody has to make.
        ("7.0.1", "7", False),
        ("7.1.0", "7", False),
        ("8.0.0", "7", True),
        ("7.1.3", "7.1", False),
        ("7.2.0", "7.1", True),
        ("8.0.0", "7.1", True),
    ],
)
def test_a_moving_tag_is_only_outdated_at_the_precision_it_names(latest, pinned, newer):
    assert is_newer(latest, pinned, moving=True) is newer


def test_the_moving_flag_changes_nothing_for_a_version_written_in_full():
    # The precision rule collapses to an ordinary comparison once all three numbers are named, so marking a full version as moving is
    # harmless. That is what makes the flag safe to set from a reader that cannot always tell.
    assert is_newer("7.0.1", "7.0.0", moving=False) is True
    assert is_newer("7.0.1", "7.0.0", moving=True) is True
    assert is_newer("7.0.0", "7.0.1", moving=True) is False


def test_a_moving_comparison_with_no_numbers_to_compare_claims_nothing():
    assert is_newer("1.0.0", "main", moving=True) is False
