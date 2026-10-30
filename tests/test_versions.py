"""Comparing versions and naming the size of a jump."""

import pytest

from stocktake.versions import is_newer, release_tuple, update_kind


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
