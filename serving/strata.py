"""Serve the model with Strata: check the pinned, patched install, write its run config, and build the server command (design doc v2/02 section 3.10)."""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from serving.settings import ServingConfig, StrataSettings, read_api_key

STRATA_RUN_CONFIG_PATH = Path("~/Library/Application Support/studio-assistant/strata.json").expanduser()
STRATA_ENGINE_PROCESS = "strata"
ENGINE_BINARY = Path("engine/build-metal/strata")
SERVER_DIR = Path("terminal")
SERVER_SCRIPT = Path("serve/server.py")
SERVER_PYTHON = Path("terminal/.venv/bin/python")
# Strings each patch adds to the engine; a binary without them was built before the patches were applied.
PATCH_MARKERS = (b"STRATA_METAL_RELEASE_HOST_WEIGHTS", b"STRATA_METAL_RELEASE_PROJECTIONS")
# Strata's own look-ahead in the prompt text; setup turns it off only for a Mac it streams the model on, and the trial measured with it on.
SUFFIX_DRAFT_FLAG = "--suffix-draft"
REDACTED = "<redacted>"


class StrataInstallProblem(Exception):
    """The install at install_dir is not the pinned commit with our patches built in, so the launch refuses it."""


def strata_run_config(config: ServingConfig) -> dict[str, Any]:
    """Setup's own run config with serving.toml's values on top: the context, the reasoning budget, the port and key, the drafter, the switches."""
    model = config.served_model
    strata = model.strata
    run_config = json.loads((strata.install_path / strata.setup_config).read_text())
    run_config["args"] = engine_arguments(run_config["args"], model.context_tokens, strata.conversation_cache_mib)
    run_config.update(
        host=config.server.host,
        port=config.server.port,
        api_key=read_api_key(config.server.api_key_path),
        reasoning_budget_tokens=model.reasoning_budget_tokens or 0,  # 0 is Strata's "no budget"
        parallel=1,  # one conversation slot: on Metal, Strata drafts with DFlash2 only beside a single slot
        drafting=strata.drafting,
        env=strata.env,
        open_browser=False,
    )
    return run_config


def engine_arguments(arguments: list[str], context_tokens: int, conversation_cache_mib: int) -> list[str]:
    kept = without_flag(arguments, SUFFIX_DRAFT_FLAG)
    kept = with_flag(kept, "--max-context", str(context_tokens))
    return with_flag(kept, "--conversation-cache-mib", str(conversation_cache_mib))


def without_flag(arguments: list[str], flag: str) -> list[str]:
    if flag not in arguments:
        return list(arguments)
    position = arguments.index(flag)
    return arguments[:position] + arguments[position + 2 :]


def with_flag(arguments: list[str], flag: str, value: str) -> list[str]:
    return [*without_flag(arguments, flag), flag, value]


def redacted_run_config(run_config: dict[str, Any]) -> dict[str, Any]:
    return run_config | {"api_key": REDACTED}


def write_strata_run_config(run_config: dict[str, Any]) -> Path:
    """Owner-only from the first byte, because the run config carries the API key."""
    STRATA_RUN_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(STRATA_RUN_CONFIG_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        json.dump(run_config, handle, indent=2)
    STRATA_RUN_CONFIG_PATH.chmod(0o600)
    return STRATA_RUN_CONFIG_PATH


def strata_command(strata: StrataSettings, run_config_path: Path, port: int) -> list[str]:
    """Run from the server's own folder (SERVER_DIR), which it imports its modules from."""
    return [str(strata.install_path / SERVER_PYTHON), str(SERVER_SCRIPT), "--engine", "strata", "--config", str(run_config_path), "--port", str(port)]


def verify_strata_install(strata: StrataSettings) -> None:
    problems = strata_install_problems(strata)
    if problems:
        raise StrataInstallProblem(f"Strata at {strata.install_path}: " + "; ".join(problems) + "; scripts/strata.sh check says more")


def strata_install_problems(strata: StrataSettings) -> list[str]:
    missing = missing_install_files(strata)
    if missing or not (strata.install_path / ".git").exists():
        return missing or ["not a git checkout; run scripts/strata.sh install"]
    problems = []
    head = git(strata.install_path, "rev-parse", "HEAD").stdout.strip()
    if head != strata.commit:
        problems.append(f"checked out at {head[:12]}, not the pinned {strata.commit[:12]} ({strata.release}); run scripts/strata.sh update")
    elif not tree_is_commit_plus_patches(strata):
        problems.append("the source is not the pinned commit with exactly our patches applied; run scripts/strata.sh install")
    problems += engine_build_problems(strata)
    return problems


def missing_install_files(strata: StrataSettings) -> list[str]:
    needed = [ENGINE_BINARY, SERVER_PYTHON, SERVER_DIR / SERVER_SCRIPT, Path(strata.setup_config)]
    return [f"no {path}" for path in needed if not (strata.install_path / path).exists()]


def tree_is_commit_plus_patches(strata: StrataSettings) -> bool:
    """Applies the patches to a throwaway index of the pinned commit and compares it with the working tree, so the real index is never touched."""
    with tempfile.TemporaryDirectory() as scratch:
        environment = git_environment() | {"GIT_INDEX_FILE": str(Path(scratch) / "index")}
        steps = [["read-tree", strata.commit], *(["apply", "--cached", str(patch)] for patch in strata.patch_paths), ["diff", "--quiet"]]
        return all(git(strata.install_path, *step, environment=environment).returncode == 0 for step in steps)


def engine_build_problems(strata: StrataSettings) -> list[str]:
    binary = strata.install_path / ENGINE_BINARY
    problems = []
    if not all(marker in binary.read_bytes() for marker in PATCH_MARKERS):
        problems.append(f"{ENGINE_BINARY} was built without our patches; rebuild it (scripts/strata.sh install)")
    newest_source = max((strata.install_path / path).stat().st_mtime for path in patched_files(strata))
    if binary.stat().st_mtime < newest_source:
        problems.append(f"{ENGINE_BINARY} is older than the patched sources; rebuild it (scripts/strata.sh install)")
    return problems


def patched_files(strata: StrataSettings) -> set[str]:
    """Every file the patches change, from git apply --numstat: added, deleted and path per line."""
    numstat = git(strata.install_path, "apply", "--numstat", *map(str, strata.patch_paths)).stdout
    return {line.split("\t")[2] for line in numstat.splitlines() if line}


def git(repository: Path, *arguments: str, environment: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repository), *arguments], capture_output=True, text=True, env=environment or git_environment())


def git_environment() -> dict[str, str]:
    """Without the GIT_ variables a calling git sets (a hook runs with this repository's GIT_INDEX_FILE), which would point git at the wrong index."""
    return {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
