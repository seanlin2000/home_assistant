"""`serving launch | show | check | engine | fetch`: start the active engine (llama-server or Strata) from config/serving.toml, print what it would run,
check its files and install, name the active engine, or download the served model and its drafter."""

import argparse
import json
import os
import sys

from serving.command import build_command, printable_command
from serving.model_file import ModelFileMismatch, fetch_model_file, model_file_matches, verify_model_file
from serving.settings import PinnedFile, ServingConfig, active_engine, load_serving_config
from serving.strata import (
    SERVER_DIR,
    StrataInstallProblem,
    redacted_run_config,
    strata_command,
    strata_run_config,
    verify_strata_install,
    write_strata_run_config,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="serving", description="Serve the model with llama-server or Strata, using only the settings in config/serving.toml.")
    parser.add_argument(
        "action",
        choices=("launch", "show", "check", "engine", "fetch"),
        help=(
            "launch: check the files and replace this process with the active engine; show: print its command or run config; check: exit 1 when the launch"
            " would refuse; engine: print the active engine's name; fetch: download the model and drafter"
        ),
    )
    return parser


def main() -> None:
    action = build_parser().parse_args().action
    config = load_serving_config()
    if action == "show":
        show(config)
    elif action == "check":
        check(config)
    elif action == "engine":
        print(active_engine(config))
    elif action == "fetch":
        for pinned_file in config.served_model.pinned_files:
            fetch(pinned_file)
    else:
        launch(config)


def show(config: ServingConfig) -> None:
    engine = active_engine(config)
    print(f"engine: {engine}")
    if engine == "strata":
        print(json.dumps(redacted_run_config(strata_run_config(config)), indent=2))
    else:
        print(printable_command(build_command(config)))
    for pinned_file in config.served_model.pinned_files:
        report_pinned_file(pinned_file)


def check(config: ServingConfig) -> None:
    """What the deploy runs before restarting the engine, so a broken install stops the deploy instead of leaving launchd restarting a launch that refuses."""
    problem = launch_problem(config)
    if problem:
        sys.exit(f"serving: {problem}")
    print(f"serving: {active_engine(config)} is ready to launch")


def launch_problem(config: ServingConfig) -> str | None:
    try:
        verify_launch_files(config)
    except (ModelFileMismatch, StrataInstallProblem, FileNotFoundError) as error:
        return str(error)
    return None


def verify_launch_files(config: ServingConfig) -> None:
    for pinned_file in config.served_model.pinned_files:
        verify_model_file(pinned_file)
    if not config.server.api_key_path.is_file():
        raise FileNotFoundError(f"no API key at {config.server.api_key_path}; scripts/services.sh install creates it")
    if active_engine(config) == "strata":
        verify_strata_install(config.served_model.strata)


def report_pinned_file(pinned_file: PinnedFile) -> None:
    try:
        verify_model_file(pinned_file)
        print(f"{pinned_file.gguf_path.name} matches its pinned SHA-256 ({pinned_file.sha256[:12]}...)")
    except ModelFileMismatch as error:
        print(f"model file problem: {error}")


def fetch(pinned_file: PinnedFile) -> None:
    """A file that already matches its pinned hash is kept, so running the setup of a new Mac again does not download the model again."""
    if model_file_matches(pinned_file):
        print(f"{pinned_file.gguf_path} already matches its pinned SHA-256")
        return
    print(f"downloaded and verified {fetch_model_file(pinned_file)}")


def launch(config: ServingConfig) -> None:
    """Replace this process with the engine's server, so launchd supervises the server itself and a crash restarts it."""
    problem = launch_problem(config)
    if problem:
        sys.exit(f"serving: {problem}")
    command = strata_launch_command(config) if active_engine(config) == "strata" else build_command(config)
    print(f"serving: {printable_command(command)}", flush=True)
    os.execv(command[0], command)


def strata_launch_command(config: ServingConfig) -> list[str]:
    """Writes the run config, then moves into the server's folder, which it imports its modules from."""
    strata = config.served_model.strata
    run_config_path = write_strata_run_config(strata_run_config(config))
    os.chdir(strata.install_path / SERVER_DIR)
    return strata_command(strata, run_config_path, config.server.port)
