"""scripts/strata.sh install, ensure and update, run for real against a small stand-in for Strata's repository: a git repository with one source
file, a setup.sh that writes setup's config, the server's files and a cmake that "builds" the engine by copying the sources. The script reads the
pin through the project's Python, pointed at a serving.toml that pins the stand-in, so the install check it ends with is the launch's own."""

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from serving.settings import SERVING_CONFIG_PATH, load_serving_config
from serving.strata import git_environment

STRATA_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "strata.sh"
ORIGINAL_SOURCE = "int release = 0;\n"
PATCHED_SOURCE = "int release = 1;  // STRATA_METAL_RELEASE_HOST_WEIGHTS STRATA_METAL_RELEASE_PROJECTIONS\n"
FAKE_SETUP = """#!/bin/bash
# setup.sh --gguf-dir DIR ...: writes setup's config, the server, a cmake that copies the sources into the engine, builds once, and leaves the
# experts copy a streaming Mac would get
set -e
while [[ $# -gt 0 ]]; do [[ "$1" == --gguf-dir ]] && gguf_dir="$2"; shift; done
mkdir -p terminal/serve terminal/.venv/bin terminal/.venv/lib/cmake/data/bin engine/build-metal
echo '{"args": [], "tokenizer": "/data/models/qwen/tokenizer/tokenizer.json", "model_name": "qwen"}' >engine/strata-iq3_xxs.json
touch terminal/serve/server.py
printf '#!/bin/bash\\ncat >/dev/null\\necho drafter fetched\\n' >terminal/.venv/bin/python
printf '#!/bin/bash\\necho build >>"$HOME/builds.log"\\ncat "$2"/../src/*.cpp >"$2/strata"\\n' >terminal/.venv/lib/cmake/data/bin/cmake
chmod +x terminal/.venv/bin/python terminal/.venv/lib/cmake/data/bin/cmake
terminal/.venv/lib/cmake/data/bin/cmake --build "$PWD/engine/build-metal"
touch "$gguf_dir/model.experts"
"""


def git(repository: Path, *arguments: str) -> str:
    command = ["git", "-C", str(repository), "-c", "user.name=test", "-c", "user.email=test@example.invalid", *arguments]
    return subprocess.run(command, check=True, capture_output=True, text=True, env=git_environment()).stdout.strip()


def make_executable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


class StrataStandIn:
    """The stand-in repository, a project folder holding a copy of strata.sh, and the serving.toml that pins the stand-in."""

    def __init__(self, tmp_path: Path) -> None:
        self.home = tmp_path
        self.upstream = tmp_path / "upstream"
        self.install = tmp_path / "Code" / "strata"
        self.model_dir = Path(load_serving_config().served_model.gguf.replace("~", str(tmp_path), 1)).parent  # HOME is tmp_path
        self.model_dir.mkdir(parents=True)
        self.serving_toml = tmp_path / "serving.toml"
        self.project = tmp_path / "project"
        self.make_upstream()
        self.patch = self.make_patch()
        self.make_project()
        self.pin(git(self.upstream, "rev-parse", "HEAD"))

    def make_upstream(self) -> None:
        (self.upstream / "engine" / "src").mkdir(parents=True)
        (self.upstream / "engine" / "src" / "window.cpp").write_text(ORIGINAL_SOURCE)
        (self.upstream / ".gitignore").write_text("terminal/\nengine/build-metal/\nengine/strata-iq3_xxs.json\n")
        make_executable(self.upstream / "setup.sh", FAKE_SETUP)
        git(self.upstream, "init", "--quiet")
        self.commit_upstream("v0.2.16")

    def commit_upstream(self, message: str) -> str:
        git(self.upstream, "add", ".")
        git(self.upstream, "commit", "--quiet", "-m", message)
        return git(self.upstream, "rev-parse", "HEAD")

    def make_patch(self) -> Path:
        window = self.upstream / "engine" / "src" / "window.cpp"
        window.write_text(PATCHED_SOURCE)
        patch = self.home / "release.patch"
        patch.write_text(git(self.upstream, "diff") + "\n")
        window.write_text(ORIGINAL_SOURCE)
        return patch

    def make_project(self) -> None:
        """A copy of strata.sh whose Python is this test's, with serving.toml's path moved to the stand-in's pin before anything reads it."""
        make_executable(self.project / "scripts" / "strata.sh", STRATA_SCRIPT.read_text())
        site = self.home / "site"
        site.mkdir()
        (site / "sitecustomize.py").write_text(f"from pathlib import Path\nimport serving.settings\nserving.settings.load_serving_config.__defaults__ = (Path({str(self.serving_toml)!r}),)\n")
        make_executable(self.project / ".venv" / "bin" / "python", f'#!/bin/bash\nPYTHONPATH="{site}" exec "{sys.executable}" "$@"\n')
        make_executable(self.home / "bin" / "xcode-select", "#!/bin/bash\necho /Library/Developer/CommandLineTools\n")

    def pin(self, commit: str) -> None:
        replacements = {
            "install_dir = ": f'install_dir = "{self.install}"',
            "commit = ": f'commit = "{commit}"',
            "patches = ": f'patches = ["{self.patch}"]',
        }
        lines = []
        for line in SERVING_CONFIG_PATH.read_text().splitlines():
            key = next((key for key in replacements if line.startswith(key)), None)
            lines.append(replacements.pop(key) if key else line)
        self.serving_toml.write_text("\n".join(lines) + "\n")

    def run(self, action: str) -> subprocess.CompletedProcess:
        environment = git_environment() | {"HOME": str(self.home), "PATH": f"{self.home / 'bin'}:{os.environ['PATH']}", "STRATA_REPOSITORY": str(self.upstream)}
        return subprocess.run([str(self.project / "scripts" / "strata.sh"), action], capture_output=True, text=True, env=environment, timeout=120)

    def builds(self) -> int:
        log = self.home / "builds.log"
        return len(log.read_text().splitlines()) if log.exists() else 0


@pytest.fixture
def strata(tmp_path: Path) -> StrataStandIn:
    return StrataStandIn(tmp_path)


def assert_passes_the_launch_check(result: subprocess.CompletedProcess) -> None:
    assert result.returncode == 0, result.stderr
    assert "the pinned commit with our patches, built" in result.stdout


def test_ensure_on_an_empty_folder_installs_the_pinned_commit_patched_and_built(strata: StrataStandIn) -> None:
    assert_passes_the_launch_check(strata.run("ensure"))
    assert git(strata.install, "rev-parse", "HEAD") == git(strata.upstream, "rev-parse", "HEAD")
    assert "STRATA_METAL_RELEASE_PROJECTIONS" in (strata.install / "engine" / "build-metal" / "strata").read_text()
    assert not (strata.model_dir / "model.experts").exists()  # setup's 40 GB copy is deleted


def test_ensure_on_a_matching_install_only_checks(strata: StrataStandIn) -> None:
    strata.run("ensure")
    builds = strata.builds()
    assert_passes_the_launch_check(strata.run("ensure"))
    assert strata.builds() == builds


def test_ensure_rebuilds_a_stale_engine_without_applying_the_patches_twice(strata: StrataStandIn) -> None:
    strata.run("ensure")
    os.utime(strata.install / "engine" / "build-metal" / "strata", (0, 0))  # built before the sources last changed
    builds = strata.builds()
    assert_passes_the_launch_check(strata.run("ensure"))
    assert (strata.builds(), (strata.install / "engine" / "src" / "window.cpp").read_text()) == (builds + 1, PATCHED_SOURCE)


def test_ensure_after_the_pin_moves_updates_to_the_new_commit_and_reapplies_the_patches(strata: StrataStandIn) -> None:
    strata.run("ensure")
    (strata.upstream / "engine" / "src" / "draft.cpp").write_text("int drafted = 1;\n")
    strata.pin(strata.commit_upstream("v0.2.17"))
    assert_passes_the_launch_check(strata.run("ensure"))
    assert git(strata.install, "rev-parse", "HEAD") == git(strata.upstream, "rev-parse", "HEAD")


def test_ensure_refuses_a_change_that_is_not_ours_and_leaves_it_in_place(strata: StrataStandIn) -> None:
    strata.run("ensure")
    window = strata.install / "engine" / "src" / "window.cpp"
    window.write_text(PATCHED_SOURCE + "int stray = 1;\n")
    refused = strata.run("ensure")
    assert refused.returncode == 1
    assert "changes that are not ours" in refused.stderr
    assert "int stray = 1;" in window.read_text()
