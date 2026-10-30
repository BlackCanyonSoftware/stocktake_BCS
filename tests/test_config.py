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
