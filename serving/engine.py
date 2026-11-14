"""The llama.cpp release installed on this Mac, checked against the one config/serving.toml records (design_docs/v2/10_operations.md section 3.8)."""

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from serving.settings import EngineSettings

# llama-server --version prints "version: 0.9.0 (build 12110, commit cd959bae9)".
VERSION_LINE = re.compile(r"version: (\S+) \(build (\d+)")
# llama-server loads its compute libraries through this Homebrew link, which points into the installed ggml's versioned folder.
GGML_HOMEBREW_LINK = Path("/opt/homebrew/opt/ggml")
VERSION_TIMEOUT_SECONDS = 30.0
HOW_TO_UPGRADE = (
    "Homebrew holds both with `brew pin llama.cpp ggml`. An upgrade is deliberate: unpin, upgrade, pin again, run the benchmark, then record the "
    "new release in config/serving.toml [engine] (design_docs/v2/10_operations.md section 3.8)."
)


class EngineMismatch(Exception):
    """The installed llama.cpp or ggml is not the release the benchmark measured, or its version cannot be read."""


@dataclass(frozen=True)
class InstalledEngine:
    llama_cpp_version: str
    llama_cpp_build: int
    ggml_version: str


def installed_engine(program: str) -> InstalledEngine:
    version, build = llama_cpp_release(version_output(program))
    return InstalledEngine(llama_cpp_version=version, llama_cpp_build=build, ggml_version=installed_ggml_version())


def version_output(program: str) -> str:
    try:
        result = subprocess.run([program, "--version"], capture_output=True, text=True, timeout=VERSION_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise EngineMismatch(f"could not run `{program} --version`: {error}") from error
    return result.stdout + result.stderr


def llama_cpp_release(version_output_text: str) -> tuple[str, int]:
    match = VERSION_LINE.search(version_output_text)
    if match is None:
        raise EngineMismatch(f"could not read llama-server's version from: {version_output_text.strip()[:200]!r}")
    return match[1], int(match[2])


def installed_ggml_version() -> str:
    if not GGML_HOMEBREW_LINK.exists():
        raise EngineMismatch(f"{GGML_HOMEBREW_LINK} does not exist, so the installed ggml cannot be read")
    return GGML_HOMEBREW_LINK.resolve().name


def verify_engine(expected: EngineSettings, installed: InstalledEngine) -> None:
    differences = [
        f"{name} is {actual}, but config/serving.toml records {wanted}"
        for name, actual, wanted in (
            ("llama.cpp", installed.llama_cpp_version, expected.llama_cpp_version),
            ("llama.cpp's build", installed.llama_cpp_build, expected.llama_cpp_build),
            ("ggml", installed.ggml_version, expected.ggml_version),
        )
        if actual != wanted
    ]
    if differences:
        raise EngineMismatch(f"{'; '.join(differences)}. {HOW_TO_UPGRADE}")
