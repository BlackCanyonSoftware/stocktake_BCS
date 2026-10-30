"""Walking a project: what gets read, what gets skipped, and what gets reported as unreadable.

The second half matters as much as the first. A manifest of a kind no reader understands has to be *named*, because the alternative is a
report that looks clean because it silently skipped half the project.
"""

from stocktake.config import Config
from stocktake.scan import find_environment, installed_for, iter_files, scan, unread_manifests

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


def test_the_projects_own_config_is_what_decides_which_readers_run(tmp_path):
    root = project(tmp_path, dockerfile=DOCKERFILE + 'RUN curl -LO "https://github.com/o/r/releases/download/v1.2.3/r.tar.gz"\n')

    assert {d.ecosystem for d in scan(root, Config(), installed=lambda name: None)} == {"PyPI", "GitHub"}
    assert {d.ecosystem for d in scan(root, Config(ecosystems=("python",)), installed=lambda name: None)} == {"PyPI"}
    assert scan(root, Config(ecosystems=()), installed=lambda name: None) == [], "enabling nothing reads nothing"


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
    (tmp_path / "a" / "package.json").write_text('{"dependencies": {"left-pad": "1.0.0"}}', encoding="utf-8")
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "package.json").write_text('{"scripts": {"test": "node --test"}}', encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "go.mod").write_text("x", encoding="utf-8")
    (tmp_path / "go.mod").write_text("module x", encoding="utf-8")

    assert unread_manifests(tmp_path).reported == ("a/package.json", "go.mod")


def test_writing_a_reader_takes_a_manifest_off_the_unread_list_by_itself(tmp_path):
    # The list is derived from what the readers claim to want, never from a hard-coded list of what is supported, so a reader added in
    # Milestone 1 silences the notice with no second place to update.
    (tmp_path / "requirements-dev.txt").write_text("ruff==0.14.1\n", encoding="utf-8")
    (tmp_path / "go.mod").write_text("module x", encoding="utf-8")

    assert unread_manifests(tmp_path).reported == ("go.mod",)
    assert [d.name for d in scan(tmp_path, installed=lambda name: None)] == ["ruff"]


def test_a_manifest_a_reader_does_understand_is_not_called_unread(tmp_path):
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (tmp_path / "Dockerfile").write_text(DOCKERFILE, encoding="utf-8")
    assert unread_manifests(tmp_path).reported == ()


def test_a_package_json_holding_no_dependencies_is_not_an_unread_manifest(tmp_path):
    (tmp_path / "package.json").write_text('{"name": "x", "scripts": {"build": "tsc"}}', encoding="utf-8")
    assert unread_manifests(tmp_path).reported == ()


def test_a_package_json_that_is_not_valid_json_is_not_claimed_to_declare_anything(tmp_path):
    (tmp_path / "package.json").write_text("{not json", encoding="utf-8")
    assert unread_manifests(tmp_path).reported == ()


# ---------- whose environment counts ----------
def make_venv(base, *packages, layout="Lib/site-packages"):
    site = base / layout
    site.mkdir(parents=True)
    for package in packages:
        (site / f"{package}.dist-info").mkdir()
    return base


def test_the_installed_version_comes_from_the_projects_own_environment(tmp_path):
    """Not from whatever interpreter happens to be running StockTake, which is a different environment entirely when it is installed as a tool."""
    make_venv(tmp_path / ".venv", "typing_extensions-4.12.0", "flask-3.0.0")

    environment = find_environment(tmp_path)
    assert environment.found and environment.label == ".venv"
    assert environment.versions == {"typing-extensions": "4.12.0", "flask": "3.0.0"}
    assert environment.version("Typing-Extensions") == "4.12.0", "the name is matched however it is punctuated"
    assert environment.version("absent") is None


def test_a_posix_style_virtual_environment_is_found_too(tmp_path):
    make_venv(tmp_path / ".venv", "click-8.1.7", layout="lib/python3.12/site-packages")
    assert find_environment(tmp_path).versions == {"click": "8.1.7"}


def test_a_plain_venv_directory_is_found_as_well(tmp_path):
    make_venv(tmp_path / "venv", "click-8.1.7")
    assert find_environment(tmp_path).label == "venv"


def test_a_project_with_no_environment_anybody_can_find_admits_it_does_not_know(tmp_path):
    # Reporting a version out of the wrong environment on a security check is worse than reporting that nothing is pinned.
    environment = find_environment(tmp_path)
    assert environment.found is False
    assert environment.versions is None
    assert environment.version("pytest") is None
    assert installed_for(tmp_path)("pytest") is None


def test_an_environment_that_exists_but_is_empty_is_not_the_same_as_none_at_all(tmp_path):
    make_venv(tmp_path / ".venv")
    environment = find_environment(tmp_path)
    assert environment.found is True, "an empty environment is an answer: nothing is installed"
    assert environment.versions == {}


def test_a_named_environment_is_used_in_preference_to_the_projects_own(tmp_path):
    make_venv(tmp_path / ".venv", "flask-1.0.0")
    elsewhere = make_venv(tmp_path / "elsewhere", "flask-3.0.0")
    assert find_environment(tmp_path, elsewhere).version("flask") == "3.0.0"


def test_a_named_place_that_is_not_an_environment_is_reported_as_not_found(tmp_path):
    (tmp_path / "empty").mkdir()
    assert find_environment(tmp_path, tmp_path / "empty").found is False


def test_a_declared_range_is_resolved_against_that_environment_and_not_another(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\ndependencies = ["flask>=2"]\n', encoding="utf-8")
    make_venv(tmp_path / ".venv", "flask-3.0.0")
    assert [(d.name, d.version) for d in scan(tmp_path)] == [("flask", "3.0.0")]


def test_a_project_can_accept_a_manifest_it_knows_cannot_be_read(tmp_path):
    (tmp_path / "go.mod").write_text("module x", encoding="utf-8")
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "Cargo.toml").write_text("[package]\n", encoding="utf-8")

    accepted = unread_manifests(tmp_path, Config(accept_unread=("go.mod", "vendor/*")))
    assert accepted.reported == (), "an accepted manifest stops nagging"
    assert accepted.accepted == ("go.mod", "vendor/Cargo.toml"), "but it is still recorded, so an unchecked surface cannot become invisible"


def test_accepting_a_manifest_is_not_the_same_as_excluding_it(tmp_path):
    # `exclude` means "do not look here at all"; `accept_unread` means "I know you cannot read this". The second keeps scanning the folder.
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "go.mod").write_text("module x", encoding="utf-8")
    (tmp_path / "vendor" / "Dockerfile").write_text("RUN pip install real==1.0\n", encoding="utf-8")

    config = Config(accept_unread=("vendor/go.mod",))
    assert unread_manifests(tmp_path, config).accepted == ("vendor/go.mod",)
    assert [d.name for d in scan(tmp_path, config, installed=lambda name: None)] == ["real"]
