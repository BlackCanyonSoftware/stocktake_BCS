"""Reading pins out of a Dockerfile: the pins no hosted dependency bot can see.

The last test in this module is the guard: it counts the pins with a plain regular expression, independently of the reader, and fails if the
two disagree. That pattern is not decoration — it is what caught `uv tool install maigret==0.6.6` being invisible in the original, and a
clean-looking report that quietly missed a pin is the most dangerous way for this tool to fail.
"""

import re

from stocktake.readers.base import Context, logical_lines
from stocktake.readers.dockerfile import (
    github_downloads,
    is_dockerfile,
    pip_requirements,
    read_pip_pins,
    read_release_downloads,
)

DOCKERFILE = """FROM python@sha256:abc
RUN apt-get update && apt-get install -y curl \\
    && pip install pytest ruff pillow==12.3.0 \\
       fonttools==4.66.1 \\
    && echo done
RUN pip install uv==0.12.17 && uv pip install -r /opt/req.txt && uv tool install maigret==0.6.6 && pipx install holehe==1.61
RUN pip install pygount==3.2.0  # the codebase-inspection skill
RUN pip install --no-cache-dir 'requests>=2.30' numpy==2.5.3 ./local-package git+https://example.invalid/x.git
ARG LLAMA_SWAP_VERSION=262
RUN curl -fsSL "https://github.com/mostlygeek/llama-swap/releases/download/v${LLAMA_SWAP_VERSION}/llama-swap_${LLAMA_SWAP_VERSION}_linux_amd64.tar.gz" | tar xz
RUN V=v2.16.0; curl -o /tmp/sf.zip "https://github.com/projectdiscovery/subfinder/releases/download/${V}/subfinder_${V#v}_linux_amd64.zip"; \\
    V=v2.11.0; curl -o /tmp/pi.tgz "https://github.com/sundowndev/phoneinfoga/releases/download/${V}/phoneinfoga_Linux_x86_64.tar.gz"
"""


def written(tmp_path, text=DOCKERFILE):
    """The Dockerfile on disk, plus the context a reader is given."""
    path = tmp_path / "docker" / "dev" / "Dockerfile"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path, Context(root=tmp_path, installed=lambda name: None)


def test_pip_pins_and_unpinned_installs_are_read_with_the_line_they_came_from(tmp_path):
    path, context = written(tmp_path)
    deps = list(read_pip_pins(path, DOCKERFILE, context))
    assert [(d.name, d.version, d.source.split(":")[1]) for d in deps] == [
        ("pytest", None, "2"),
        ("ruff", None, "2"),
        ("pillow", "12.3.0", "2"),
        ("fonttools", "4.66.1", "2"),
        ("uv", "0.12.17", "6"),
        ("maigret", "0.6.6", "6"),
        ("holehe", "1.61", "6"),
        ("pygount", "3.2.0", "7"),
        ("requests", None, "8"),
        ("numpy", "2.5.3", "8"),
    ]
    assert all(d.ecosystem == "PyPI" and d.role == "image" for d in deps)
    assert [d.source for d in deps[:1]] == ["docker/dev/Dockerfile:2"]


def test_a_range_is_kept_as_written_but_does_not_count_as_a_pinned_version(tmp_path):
    path, context = written(tmp_path)
    requests = next(d for d in read_pip_pins(path, DOCKERFILE, context) if d.name == "requests")
    assert (requests.spec, requests.version) == (">=2.30", None)


def test_the_line_number_is_where_the_run_started_not_where_the_continuation_ended():
    numbered = logical_lines(DOCKERFILE)
    assert numbered[1][0] == 2  # the apt-get/pip line spans lines 2 to 5
    assert "echo done" in numbered[1][1]
    assert numbered[2][0] == 6


def test_installers_other_than_plain_pip_are_recognised():
    found = pip_requirements("uv tool install maigret==0.6.6 && pipx install holehe==1.61 && uv pip install rich==13.0")
    assert found == [("maigret", "0.6.6", "==0.6.6"), ("holehe", "1.61", "==1.61"), ("rich", "13.0", "==13.0")]


def test_an_option_that_takes_a_filename_does_not_make_the_filename_look_like_a_package():
    assert pip_requirements("pip install -r /opt/req.txt") == []
    assert pip_requirements("pip install --index-url https://example.invalid/simple flask==3.0") == [("flask", "3.0", "==3.0")]


def test_local_paths_vcs_urls_and_shell_variables_are_not_registry_packages():
    assert pip_requirements("pip install ./local-package git+https://example.invalid/x.git https://e.invalid/w.whl ${EXTRA}") == []


def test_apt_get_install_is_not_a_python_installer():
    assert pip_requirements("apt-get install -y curl build-essential") == []


def test_an_unbalanced_quote_yields_nothing_rather_than_raising():
    assert pip_requirements("pip install 'broken==1.0") == []


def test_github_release_pins_resolve_their_variables_to_the_nearest_assignment(tmp_path):
    path, context = written(tmp_path)
    deps = list(read_release_downloads(path, DOCKERFILE, context))
    assert [(d.name, d.version) for d in deps] == [
        ("mostlygeek/llama-swap", "262"),
        ("projectdiscovery/subfinder", "2.16.0"),
        ("sundowndev/phoneinfoga", "2.11.0"),
    ]
    assert all(d.ecosystem == "GitHub" for d in deps)


def test_the_v0_0_0_release_where_projects_keep_model_files_is_not_a_version_pin():
    # A real false positive from the original: a "major update available" for a tag that is a file dump, not a release.
    assert github_downloads("curl -o m.onnx https://github.com/danielgatis/rembg/releases/download/v0.0.0/isnet.onnx") == []


def test_dockerfiles_are_recognised_by_their_usual_names(tmp_path):
    assert is_dockerfile(tmp_path / "Dockerfile")
    assert is_dockerfile(tmp_path / "Dockerfile.dev")
    assert is_dockerfile(tmp_path / "dev.Dockerfile")
    assert is_dockerfile(tmp_path / "Containerfile")
    assert not is_dockerfile(tmp_path / "pyproject.toml")
    assert not is_dockerfile(tmp_path / "docker-compose.yml")


def test_no_pin_written_in_the_dockerfile_escapes_the_reader(tmp_path):
    """The guard. Counts `name==version` on RUN lines with a plain regex and insists the reader found exactly those.

    If this ever fails, the report has been lying by omission, which is worse than any noisy finding.
    """
    path, context = written(tmp_path)
    expected = set()
    for _number, line in logical_lines(DOCKERFILE):
        if re.match(r"\s*RUN\b", line):
            without_comment = re.sub(r"\s#.*", "", line)
            expected |= {
                (m.group(1).lower(), m.group(2)) for m in re.finditer(r"(?<![\w.-])([A-Za-z][\w.-]*)==([0-9][\w.+-]*)", without_comment)
            }
    found = {(d.name.lower(), d.version) for d in read_pip_pins(path, DOCKERFILE, context) if d.version}
    assert expected == found, f"the reader and an independent count disagree about: {expected ^ found}"
