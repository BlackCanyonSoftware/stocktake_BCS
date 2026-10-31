"""Reading a project's config, and failing loudly when it cannot be read.

A config that cannot be parsed is said plainly and at once. Falling back to defaults would mean the project's policy silently stopped
applying, which is the one failure mode a policy file must not have.
"""

from datetime import date

import pytest

from stocktake.config import DEFAULT_EXCLUDES, Config, ConfigError, excluded, load_config

OWN_FILE = """
exclude = ["vendor", "tests/fixtures"]

[[policy.hold_back]]
package = "pillow"
reason = "12.4 changes the PNG writer"
until = 2026-12-01
"""


def test_a_project_with_no_config_at_all_gets_the_defaults(tmp_path):
    config = load_config(tmp_path)
    assert config.policy.entries == ()
    assert config.exclude == ()
    assert config.ecosystems is None, "not choosing means all of them"
    assert config.accept_unread == ()
    assert config.cache_ttl_hours == 6.0
    assert config.source is None
    assert config.excludes == DEFAULT_EXCLUDES


def test_the_projects_own_file_is_read_with_its_policy_and_excludes(tmp_path):
    (tmp_path / ".stocktake.toml").write_text(OWN_FILE, encoding="utf-8")
    config = load_config(tmp_path)
    assert config.exclude == ("vendor", "tests/fixtures")
    assert [(e.what, e.until) for e in config.policy.entries] == [("pillow", date(2026, 12, 1))]
    assert config.source is not None and config.source.endswith(".stocktake.toml")


def test_the_defaults_are_added_to_rather_than_replaced_by_what_a_project_excludes(tmp_path):
    (tmp_path / ".stocktake.toml").write_text(OWN_FILE, encoding="utf-8")
    excludes = load_config(tmp_path).excludes
    assert ".venv" in excludes and "vendor" in excludes


def test_a_python_project_can_configure_it_in_pyproject_instead(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\n\n[tool.stocktake]\nexclude = ["vendor"]\n\n[[tool.stocktake.policy.ignore_advisories]]\nid = "GHSA-1"\nreason = "assessed"\nuntil = 2026-12-01\n',
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    assert config.exclude == ("vendor",)
    assert [e.what for e in config.policy.entries] == ["GHSA-1"]
    assert config.source is not None and config.source.endswith("pyproject.toml")


def test_the_dedicated_file_wins_over_pyproject_rather_than_merging_with_it(tmp_path):
    (tmp_path / ".stocktake.toml").write_text('exclude = ["from-own-file"]\n', encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[tool.stocktake]\nexclude = ["from-pyproject"]\n', encoding="utf-8")
    config = load_config(tmp_path)
    assert config.exclude == ("from-own-file",)
    assert config.source is not None and config.source.endswith(".stocktake.toml")


def test_a_pyproject_with_no_stocktake_table_is_not_treated_as_a_config(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
    assert load_config(tmp_path).source is None


def test_a_config_file_can_be_named_explicitly(tmp_path):
    elsewhere = tmp_path / "shared.toml"
    elsewhere.write_text('exclude = ["vendor"]\n', encoding="utf-8")
    assert load_config(tmp_path, elsewhere).exclude == ("vendor",)


def test_a_file_that_is_not_valid_toml_is_refused_and_names_itself(tmp_path):
    (tmp_path / ".stocktake.toml").write_text("exclude = [unquoted\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="not valid TOML"):
        load_config(tmp_path)


def test_an_exclude_list_of_the_wrong_shape_is_refused(tmp_path):
    (tmp_path / ".stocktake.toml").write_text('exclude = "vendor"\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="must be a list of strings"):
        load_config(tmp_path)


def test_a_policy_that_is_not_a_table_is_refused(tmp_path):
    (tmp_path / ".stocktake.toml").write_text('policy = "none"\n', encoding="utf-8")
    with pytest.raises(ConfigError, match=r"`\[policy\]` must be a table"):
        load_config(tmp_path)


def test_a_named_config_file_that_does_not_exist_is_refused_rather_than_ignored(tmp_path):
    with pytest.raises(ConfigError, match="could not be read"):
        load_config(tmp_path, tmp_path / "absent.toml")


# ---------- choosing what to read ----------
def test_a_project_can_name_the_ecosystems_it_wants_read(tmp_path):
    (tmp_path / ".stocktake.toml").write_text('ecosystems = ["python"]\n', encoding="utf-8")
    assert load_config(tmp_path).ecosystems == ("python",)


def test_naming_an_ecosystem_this_version_does_not_know_is_refused_rather_than_ignored(tmp_path):
    # A typo that silently disabled half the check would be the worst kind of failure here.
    (tmp_path / ".stocktake.toml").write_text('ecosystems = ["pythonn"]\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="unknown ecosystem"):
        load_config(tmp_path)


def test_the_refusal_says_which_ecosystems_do_exist(tmp_path):
    (tmp_path / ".stocktake.toml").write_text('ecosystems = ["rust"]\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="python"):
        load_config(tmp_path)


def test_enabling_nothing_is_allowed_and_is_not_the_same_as_saying_nothing(tmp_path):
    (tmp_path / ".stocktake.toml").write_text("ecosystems = []\n", encoding="utf-8")
    assert load_config(tmp_path).ecosystems == ()


# ---------- the cache ----------
def test_the_cache_lifetime_can_be_set_in_hours(tmp_path):
    (tmp_path / ".stocktake.toml").write_text("[cache]\nttl_hours = 0.5\n", encoding="utf-8")
    config = load_config(tmp_path)
    assert config.cache_ttl_hours == 0.5
    assert config.cache_ttl_seconds == 1800


@pytest.mark.parametrize("value", ["0", "-1", '"six"', "true"])
def test_a_cache_lifetime_that_is_not_a_positive_number_is_refused(value, tmp_path):
    (tmp_path / ".stocktake.toml").write_text(f"[cache]\nttl_hours = {value}\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="must be a positive number"):
        load_config(tmp_path)


def test_a_cache_section_of_the_wrong_shape_is_refused(tmp_path):
    (tmp_path / ".stocktake.toml").write_text('cache = "none"\n', encoding="utf-8")
    with pytest.raises(ConfigError, match=r"`\[cache\]` must be a table"):
        load_config(tmp_path)


# ---------- accepting what cannot be read ----------
def test_a_project_can_accept_manifests_it_knows_cannot_be_read(tmp_path):
    (tmp_path / ".stocktake.toml").write_text('accept_unread = ["go.mod", "vendor/*"]\n', encoding="utf-8")
    assert load_config(tmp_path).accept_unread == ("go.mod", "vendor/*")


def test_a_project_can_say_where_its_python_environment_is(tmp_path):
    (tmp_path / ".stocktake.toml").write_text('environment = "tools/env"\n', encoding="utf-8")
    assert load_config(tmp_path).environment == "tools/env"


def test_an_environment_that_is_not_a_path_is_refused(tmp_path):
    (tmp_path / ".stocktake.toml").write_text("environment = 3\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="`environment` must be a path"):
        load_config(tmp_path)


def test_an_accept_unread_list_of_the_wrong_shape_is_refused(tmp_path):
    (tmp_path / ".stocktake.toml").write_text('accept_unread = "go.mod"\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="`accept_unread` must be a list of strings"):
        load_config(tmp_path)


# ---------- the matching itself ----------
def test_an_exclude_matches_a_whole_path_or_any_single_segment_of_it():
    patterns = (".venv", "tests/fixtures", "*.egg-info")
    assert excluded(".venv", patterns)
    assert excluded("src/.venv", patterns)  # a segment anywhere
    assert excluded("tests/fixtures", patterns)  # the whole path
    assert excluded("stocktake.egg-info", patterns)  # a glob on a segment
    assert not excluded("tests/test_scan.py", patterns)
    assert not excluded("src/venv_helper.py", patterns)


def test_the_configured_excludes_are_the_defaults_plus_the_projects_own():
    assert Config(exclude=("vendor",)).excludes == (*DEFAULT_EXCLUDES, "vendor")


# ---------- a key nobody recognises ----------
def test_a_misspelt_setting_is_refused_rather_than_ignored(tmp_path):
    """`excludes = [...]` was read as a file with no excludes at all, and scanning a virtual environment by accident looks exactly like a
    project with a great many dependencies. This module has always claimed every value is validated as it is read; a key nobody named was
    not a value, so it went straight past.
    """
    path = tmp_path / ".stocktake.toml"
    path.write_text('excludes = [".venv"]\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="unknown setting: `excludes`; did you mean `exclude`"):
        load_config(tmp_path)


def test_a_setting_that_is_nothing_like_a_real_one_is_refused_without_a_guess(tmp_path):
    """A wrong guess sends the reader to rewrite the line that was not the problem, so none is offered."""
    path = tmp_path / ".stocktake.toml"
    path.write_text("nonsense = 5\n", encoding="utf-8")
    with pytest.raises(ConfigError, match=r"unknown setting: `nonsense`\. Valid: accept_unread") as caught:
        load_config(tmp_path)
    assert "did you mean" not in str(caught.value)


def test_every_unknown_setting_is_named_at_once(tmp_path):
    path = tmp_path / ".stocktake.toml"
    path.write_text("one = 1\ntwo = 2\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="`one`, `two`"):
        load_config(tmp_path)


def test_an_unknown_key_inside_cache_is_refused_too(tmp_path):
    path = tmp_path / ".stocktake.toml"
    path.write_text("[cache]\nttl = 3\n", encoding="utf-8")
    with pytest.raises(ConfigError, match=r"unknown setting in `\[cache\]`: `ttl`"):
        load_config(tmp_path)


def test_every_setting_the_docs_offer_is_accepted(tmp_path):
    """The other half of refusing unknown keys: a file using all of them must still load, or the check is worse than useless."""
    path = tmp_path / ".stocktake.toml"
    path.write_text(
        'exclude = ["vendor"]\n'
        'ecosystems = ["python"]\n'
        'accept_unread = ["go.mod"]\n'
        'environment = ".venv"\n'
        "[cache]\nttl_hours = 1\n"
        "[[policy.hold_back]]\n"
        'package = "pillow"\n'
        'reason = "r"\n'
        "until = 2026-12-01\n",
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    assert config.exclude == ("vendor",)
    assert config.ecosystems == ("python",)
    assert config.accept_unread == ("go.mod",)
    assert config.environment == ".venv"
    assert config.cache_ttl_hours == 1


def test_the_suggestion_does_not_end_in_a_question_mark_and_a_full_stop(tmp_path):
    """`did you mean `exclude`?.` is what came out before, and a stray full stop in an error message reads as a bug in the message."""
    path = tmp_path / ".stocktake.toml"
    path.write_text('excludes = [".venv"]\n', encoding="utf-8")
    with pytest.raises(ConfigError) as caught:
        load_config(tmp_path)
    assert "?. " not in str(caught.value)
    assert "`exclude`? Valid:" in str(caught.value)
