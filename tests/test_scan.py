"""Walking a project: what gets read, what gets skipped, and what gets reported as unreadable.

The second half matters as much as the first. A manifest of a kind no reader understands has to be *named*, because the alternative is a
report that looks clean because it silently skipped half the project.
"""

from stocktake.config import Config
from stocktake.scan import iter_files, scan, unread_manifests

DOCKERFILE = "FROM python:3.12\nRUN pip install flask==3.0.0\n"
PYPROJECT = '[project]\nname = "x"\ndependencies = ["httpx==0.28.1"]\n'


def project(tmp_path, dockerfile=DOCKERFILE, pyproject=PYPROJECT):
    (tmp_path / "docker").mkdir()
    (tmp_path / "docker" / "Dockerfile").write_text(dockerfile, encoding="utf-8")
    if pyproject is not None:
        (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    return tmp_path


def test_every_reader_is_offered_every_file_it_is_interested_in(tmp_path):
    deps = scan(project(tmp_path), installed=lambda name: None)
    assert {(d.ecosystem, d.name, d.version, d.source) for d in deps} == {
        ("PyPI", "httpx", "0.28.1", "pyproject.toml"),
        ("PyPI", "flask", "3.0.0", "docker/Dockerfile:2"),
    }


def test_a_project_can_run_only_the_readers_it_wants(tmp_path):
    root = project(tmp_path, dockerfile=DOCKERFILE + 'RUN curl -LO "https://github.com/o/r/releases/download/v1.2.3/r.tar.gz"\n')

    everything = scan(root, installed=lambda name: None)
    assert {d.ecosystem for d in everything} == {"PyPI", "GitHub"}

    python_only = scan(root, installed=lambda name: None, groups=["python"])
    assert {d.ecosystem for d in python_only} == {"PyPI"}


def test_the_folders_nobody_means_to_scan_are_not_walked(tmp_path):
    for folder in (".git", ".venv", "node_modules", "__pycache__", "dist", "stocktake.egg-info"):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "Dockerfile").write_text("RUN pip install sneaky==1.0\n", encoding="utf-8")
    (tmp_path / "Dockerfile").write_text("RUN pip install real==1.0\n", encoding="utf-8")

    assert [d.name for d in scan(tmp_path, installed=lambda name: None)] == ["real"]


def test_a_project_can_exclude_its_own_paths_without_any_of_them_being_in_the_source(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "fixtures").mkdir()
    (tmp_path / "tests" / "fixtures" / "Dockerfile").write_text("RUN pip install fixture==1.0\n", encoding="utf-8")
    (tmp_path / "Dockerfile").write_text("RUN pip install real==1.0\n", encoding="utf-8")

    config = Config(exclude=("tests/fixtures",))
    assert [d.name for d in scan(tmp_path, config, installed=lambda name: None)] == ["real"]


def test_files_are_walked_in_a_stable_order_so_two_runs_report_the_same_thing(tmp_path):
    root = project(tmp_path)
    first = [d.source for d in scan(root, installed=lambda name: None)]
    second = [d.source for d in scan(root, installed=lambda name: None)]
    assert first == second


def test_an_excluded_file_is_not_even_opened(tmp_path):
    (tmp_path / "Dockerfile.bak").write_text("RUN pip install ignored==1.0\n", encoding="utf-8")
    (tmp_path / "Dockerfile").write_text("RUN pip install real==1.0\n", encoding="utf-8")
    walked = {p.name for p in iter_files(tmp_path, Config(exclude=("Dockerfile.bak",)).excludes)}
    assert walked == {"Dockerfile"}


def test_manifests_of_a_kind_no_reader_understands_are_named_rather_than_ignored(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "requirements-dev.txt").write_text("x==1\n", encoding="utf-8")
    (tmp_path / "a" / "package.json").write_text('{"dependencies": {"left-pad": "1.0.0"}}', encoding="utf-8")
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "package.json").write_text('{"scripts": {"test": "node --test"}}', encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "go.mod").write_text("x", encoding="utf-8")
    (tmp_path / "go.mod").write_text("module x", encoding="utf-8")

    assert unread_manifests(tmp_path) == ["a/package.json", "a/requirements-dev.txt", "go.mod"]


def test_a_manifest_a_reader_does_understand_is_not_called_unread(tmp_path):
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (tmp_path / "Dockerfile").write_text(DOCKERFILE, encoding="utf-8")
    assert unread_manifests(tmp_path) == []


def test_a_package_json_holding_no_dependencies_is_not_an_unread_manifest(tmp_path):
    (tmp_path / "package.json").write_text('{"name": "x", "scripts": {"build": "tsc"}}', encoding="utf-8")
    assert unread_manifests(tmp_path) == []


def test_a_package_json_that_is_not_valid_json_is_not_claimed_to_declare_anything(tmp_path):
    (tmp_path / "package.json").write_text("{not json", encoding="utf-8")
    assert unread_manifests(tmp_path) == []
