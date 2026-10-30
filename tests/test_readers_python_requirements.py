"""Reading `requirements*.txt` and `constraints*.txt`.

The format looks like "one requirement per line" and is not: continuations, hash digests, pip options and direct references all have to be
told apart from the requirements. The guard at the end of this module counts the requirements independently of the reader.
"""

import re

import pytest

from stocktake.readers.base import Context, logical_lines
from stocktake.readers.python_requirements import is_requirements_file, read_requirements, requirement_in, role_of

REQUIREMENTS = """# Production dependencies, compiled with pip-compile
--index-url https://pypi.org/simple
-r base.txt
-c constraints.txt

flask==3.0.0 \\
    --hash=sha256:aaaaaaaa \\
    --hash=sha256:bbbbbbbb
requests>=2.30,<3    # a range, so nothing is actually pinned
pillow==12.3.0
tomli==2.0.1 ; python_version < "3.11"
uvicorn[standard]==0.30.0
mypackage @ https://example.invalid/mypackage-1.0.tar.gz
-e .
ruff
"""


def read(tmp_path, text=REQUIREMENTS, name="requirements.txt", installed=None):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    context = Context(root=tmp_path, installed=(installed or {}).get)
    return list(read_requirements(path, text, context))


def test_every_requirement_is_read_with_the_line_it_is_on(tmp_path):
    deps = read(tmp_path)
    assert [(d.name, d.version, d.spec, d.source) for d in deps] == [
        ("flask", "3.0.0", "==3.0.0", "requirements.txt:6"),
        ("requests", None, ">=2.30,<3", "requirements.txt:9"),
        ("pillow", "12.3.0", "==12.3.0", "requirements.txt:10"),
        ("tomli", "2.0.1", "==2.0.1", "requirements.txt:11"),
        ("uvicorn", "0.30.0", "==0.30.0", "requirements.txt:12"),
        ("ruff", None, "", "requirements.txt:15"),
    ]
    assert all(d.ecosystem == "PyPI" for d in deps)


def test_the_pin_wins_over_what_happens_to_be_installed_here(tmp_path):
    # The opposite of pyproject.toml, deliberately: a requirements file names what *will* be installed.
    deps = read(tmp_path, installed={"pillow": "9.0.0"})
    assert next(d for d in deps if d.name == "pillow").version == "12.3.0"


def test_a_range_with_no_pin_falls_back_to_what_is_installed(tmp_path):
    deps = read(tmp_path, installed={"requests": "2.32.0"})
    assert next(d for d in deps if d.name == "requests").version == "2.32.0"
    assert next(d for d in deps if d.name == "requests").spec == ">=2.30,<3"


def test_hash_digests_do_not_become_part_of_the_version(tmp_path):
    assert next(d for d in read(tmp_path) if d.name == "flask").version == "3.0.0"


def test_pip_options_are_not_requirements():
    for option in ("-r base.txt", "-c constraints.txt", "-e .", "--index-url https://example.invalid/simple", "--no-binary :all:"):
        assert requirement_in(option) == ""


def test_a_direct_reference_has_no_version_a_registry_could_confirm():
    assert requirement_in("mypackage @ https://example.invalid/mypackage-1.0.tar.gz") == ""
    assert requirement_in("https://example.invalid/x-1.0.whl") == ""
    assert requirement_in("git+https://example.invalid/x.git#egg=x") == ""


def test_comments_and_blank_lines_hold_nothing():
    assert requirement_in("# just a comment") == ""
    assert requirement_in("") == ""
    assert requirement_in("   ") == ""
    assert requirement_in("flask==3.0.0  # pinned on purpose") == "flask==3.0.0"


@pytest.mark.parametrize(
    ("filename", "role"),
    [
        ("requirements.txt", "runtime"),
        ("requirements-dev.txt", "dev"),
        ("dev-requirements.txt", "dev"),
        ("requirements_test.txt", "dev"),
        ("requirements-ci.txt", "dev"),
        ("requirements-docs.txt", "dev"),
        ("requirements-prod.txt", "runtime"),
        # "social" contains "ci", which is why the words are matched whole rather than as substrings.
        ("requirements-social.txt", "runtime"),
    ],
)
def test_the_filename_is_the_only_hint_about_what_a_requirements_file_is_for(filename, role, tmp_path):
    assert role_of(tmp_path / filename) == role


def test_constraints_files_are_read_too(tmp_path):
    assert is_requirements_file(tmp_path / "constraints.txt")
    assert is_requirements_file(tmp_path / "requirements-dev.txt")
    assert not is_requirements_file(tmp_path / "notes.txt")
    assert not is_requirements_file(tmp_path / "pyproject.toml")


def test_an_empty_file_yields_nothing(tmp_path):
    assert read(tmp_path, text="") == []
    assert read(tmp_path, text="\n\n# only comments\n") == []


def test_no_requirement_in_the_file_escapes_the_reader(tmp_path):
    """The guard. Counts the lines that plainly hold a requirement, independently of the reader, and insists the two agree."""
    expected = set()
    for _number, line in logical_lines(REQUIREMENTS):
        bare = re.sub(r"(^|\s)#.*$", "", line).strip()
        if re.match(r"^[A-Za-z][A-Za-z0-9_.-]*\s*(\[|[<>=!~]|$)", bare):
            expected.add(re.split(r"[\s<>=!~\[;]", bare, maxsplit=1)[0].lower())
    found = {d.name.lower() for d in read(tmp_path)}
    assert expected == found, f"the reader and an independent count disagree about: {expected ^ found}"
