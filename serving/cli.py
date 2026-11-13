"""`serving launch | show | fetch`: start llama-server from config/serving.toml, print the command it would run, or download the served model and its drafter."""

import argparse
import os
import sys

from serving.command import build_command, printable_command
from serving.model_file import ModelFileMismatch, fetch_model_file, model_file_matches, verify_model_file
from serving.settings import PinnedFile, ServingConfig, load_serving_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="serving", description="Serve the model with llama-server, using only the settings in config/serving.toml.")
    parser.add_argument(
        "action",
        choices=("launch", "show", "fetch"),
        help="launch: check the model's and drafter's hashes and replace this process with llama-server; show: print the command; fetch: download the model and drafter",
    )
    return parser


def main() -> None:
    action = build_parser().parse_args().action
    config = load_serving_config()
    if action == "show":
        show(config)
    elif action == "fetch":
        for pinned_file in config.served_model.pinned_files:
            fetch(pinned_file)
    else:
        launch(config)


def show(config: ServingConfig) -> None:
    print(printable_command(build_command(config)))
    for pinned_file in config.served_model.pinned_files:
        report_pinned_file(pinned_file)


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
    """Replace this process with llama-server, so launchd supervises the server itself and a crash restarts it."""
    command = build_command(config)
    try:
        for pinned_file in config.served_model.pinned_files:
            verify_model_file(pinned_file)
    except ModelFileMismatch as error:
        sys.exit(f"serving: {error}")
    if not config.server.api_key_path.is_file():
        sys.exit(f"serving: no API key at {config.server.api_key_path}; scripts/services.sh install creates it")
    print(f"serving: {printable_command(command)}", flush=True)
    os.execv(command[0], command)
