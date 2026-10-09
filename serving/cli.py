"""`serving launch | show | fetch`: start llama-server from config/serving.toml, print the command it would run, or download the served model."""

import argparse
import os
import sys

from serving.command import build_command, printable_command
from serving.model_file import ModelFileMismatch, fetch_model_file, verify_model_file
from serving.settings import ServingConfig, load_serving_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="serving", description="Serve the model with llama-server, using only the settings in config/serving.toml.")
    parser.add_argument(
        "action", choices=("launch", "show", "fetch"), help="launch: check the model's hash and replace this process with llama-server; show: print the command; fetch: download the model"
    )
    return parser


def main() -> None:
    action = build_parser().parse_args().action
    config = load_serving_config()
    if action == "show":
        show(config)
    elif action == "fetch":
        print(f"downloaded and verified {fetch_model_file(config.served_model)}")
    else:
        launch(config)


def show(config: ServingConfig) -> None:
    print(printable_command(build_command(config)))
    try:
        verify_model_file(config.served_model)
        print(f"model file matches its pinned SHA-256 ({config.served_model.sha256[:12]}...)")
    except ModelFileMismatch as error:
        print(f"model file problem: {error}")


def launch(config: ServingConfig) -> None:
    """Replace this process with llama-server, so launchd supervises the server itself and a crash restarts it."""
    command = build_command(config)
    try:
        verify_model_file(config.served_model)
    except ModelFileMismatch as error:
        sys.exit(f"serving: {error}")
    if not config.server.api_key_path.is_file():
        sys.exit(f"serving: no API key at {config.server.api_key_path}; scripts/services.sh install creates it")
    print(f"serving: {printable_command(command)}", flush=True)
    os.execv(command[0], command)
