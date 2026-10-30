"""`stocktake init`: writing the check into somebody else's project.

This is the one part of StockTake that creates files, so what it will and will not overwrite is tested carefully.
"""

import tomllib

import pytest

from stocktake.cli import INCOMPLETE, OK, init
from stocktake.config import CONFIG_NAME, load_config
from stocktake.init_project import EXISTS, FAILED, TEST_FILENAME, WRITTEN, init_project, template_source
from stocktake.init_project import tests_directory as find_tests_directory


def test_both_files_are_written_into_a_bare_project(tmp_path):
    written = init_project(tmp_path)
    assert [(w.path.name, w.outcome) for w in written] == [(TEST_FILENAME, WRITTEN), (CONFIG_NAME, WRITTEN)]
    assert (tmp_path / "tests" / TEST_FILENAME).is_file()
    assert (tmp_path / CONFIG_NAME).is_file()


def test_the_test_file_goes_where_the_project_already_keeps_its_tests(tmp_path):
    (tmp_path / "tests").mkdir()
    init_project(tmp_path)
    assert (tmp_path / "tests" / TEST_FILENAME).is_file()


def test_a_project_using_the_singular_test_directory_is_respected(tmp_path):
    (tmp_path / "test").mkdir()
    assert find_tests_directory(tmp_path) == tmp_path / "test"
    init_project(tmp_path)
    assert (tmp_path / "test" / TEST_FILENAME).is_file()


def test_tests_is_preferred_when_a_project_has_both(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "test").mkdir()
    assert find_tests_directory(tmp_path) == tmp_path / "tests"


def test_the_directory_can_be_named_instead(tmp_path):
    init_project(tmp_path, tmp_path / "suite" / "deps")
    assert (tmp_path / "suite" / "deps" / TEST_FILENAME).is_file()


def test_nothing_is_ever_overwritten_without_being_asked(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / TEST_FILENAME).write_text("# mine, do not touch\n", encoding="utf-8")
    (tmp_path / CONFIG_NAME).write_text('exclude = ["vendor"]\n', encoding="utf-8")

    written = init_project(tmp_path)
    assert [w.outcome for w in written] == [EXISTS, EXISTS]
    assert (tmp_path / "tests" / TEST_FILENAME).read_text(encoding="utf-8") == "# mine, do not touch\n"
    assert load_config(tmp_path).exclude == ("vendor",), "an existing config must survive untouched"


def test_force_overwrites_both(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / TEST_FILENAME).write_text("# mine\n", encoding="utf-8")
    written = init_project(tmp_path, force=True)
    assert [w.outcome for w in written] == [WRITTEN, WRITTEN]
    assert "assert_dependencies_are_safe" in (tmp_path / "tests" / TEST_FILENAME).read_text(encoding="utf-8")


def test_a_place_that_cannot_be_written_is_reported_rather_than_raising(tmp_path):
    # A directory where the test file should go: writing is impossible, and the caller is told which file and why.
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / TEST_FILENAME).mkdir()
    written = init_project(tmp_path, force=True)
    assert written[0].outcome == FAILED and written[0].detail


# ---------- what gets written ----------
def test_the_test_file_is_valid_python_that_uses_the_shared_rules():
    source = template_source()
    compile(source, TEST_FILENAME, "exec")
    assert "assert_dependencies_are_safe" in source
    assert "pytestconfig.rootpath" in source, "the project root has to come from pytest, not from the working directory"


def test_the_test_file_explains_what_it_does_to_whoever_finds_it_later():
    source = template_source()
    for promise in ("fails", "warns", "skips", "STOCKTAKE_OFFLINE", "No file is ever modified"):
        assert promise in source


def test_the_starter_config_is_valid_toml_and_changes_nothing_by_itself(tmp_path):
    init_project(tmp_path)
    text = (tmp_path / CONFIG_NAME).read_text(encoding="utf-8")
    assert tomllib.loads(text) == {}, "every key is commented out, so a fresh config behaves exactly like no config"

    config = load_config(tmp_path)
    assert config.exclude == () and config.ecosystems is None and config.policy.entries == ()


def test_the_starter_config_shows_every_key_a_project_might_want(tmp_path):
    init_project(tmp_path)
    text = (tmp_path / CONFIG_NAME).read_text(encoding="utf-8")
    for key in ("ecosystems", "exclude", "accept_unread", "environment", "ttl_hours", "ignore_advisories", "hold_back"):
        assert key in text
    assert "until" in text and "reason" in text


# ---------- the command ----------
def test_the_command_says_what_it_wrote(tmp_path):
    printed: list[str] = []
    assert init([str(tmp_path)], out=printed.append) == OK
    output = "\n".join(printed)
    assert f"wrote tests/{TEST_FILENAME}" in output
    assert f"wrote {CONFIG_NAME}" in output
    assert "Run `pytest`" in output


def test_the_command_says_what_it_left_alone(tmp_path):
    init_project(tmp_path)
    printed: list[str] = []
    assert init([str(tmp_path)], out=printed.append) == OK
    output = "\n".join(printed)
    assert "left alone" in output and "--force" in output
    assert "Run `pytest`" not in output, "nothing changed, so there is nothing to try"


def test_the_command_defaults_to_the_project_it_is_pointed_at(tmp_path):
    printed: list[str] = []
    assert init([], root=tmp_path, out=printed.append) == OK
    assert (tmp_path / "tests" / TEST_FILENAME).is_file()


def test_the_command_refuses_somewhere_that_is_not_a_directory(tmp_path, capsys):
    assert init([str(tmp_path / "nowhere")], out=lambda text: None) == INCOMPLETE
    assert "is not a directory" in capsys.readouterr().err


def test_the_command_reports_a_failure_to_write(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / TEST_FILENAME).mkdir()
    assert init([str(tmp_path), "--force"], out=lambda text: None) == INCOMPLETE


def test_the_directory_can_be_named_on_the_command_line(tmp_path):
    assert init([str(tmp_path), "--tests", "suite"], out=lambda text: None) == OK
    assert (tmp_path / "suite" / TEST_FILENAME).is_file()


def test_init_is_reached_through_the_main_entry_point(tmp_path, monkeypatch):
    from stocktake.cli import main

    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == OK
    assert (tmp_path / "tests" / TEST_FILENAME).is_file()


def test_asking_init_for_help_does_not_write_anything(tmp_path):
    with pytest.raises(SystemExit) as exit_info:
        init([str(tmp_path), "--help"], out=lambda text: None)
    assert exit_info.value.code == 0
    assert not (tmp_path / "tests").exists()
