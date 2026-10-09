"""The one place that knows where the operations files live on the Mac.

Everything goes under one directory so a single rsync from the laptop retrieves all of it (design doc 10 §3.7). STUDIO_LOG_DIR overrides the root for tests.
"""

import os
from pathlib import Path


def log_dir() -> Path:
    override = os.environ.get("STUDIO_LOG_DIR")
    return Path(override) if override else Path.home() / "Library" / "Logs" / "studio-assistant"


# The parts of assistant_core the Home Assistant component vendors: the shared event and transcript models and the harness client. The loop and the
# model clients stay on the Mac, so Home Assistant's Python never imports them (design doc v2/04 section 3.2).
VENDORED_CORE_FILES = ("assistant_core/__init__.py", "assistant_core/models.py", "assistant_core/prompts.py", "assistant_core/converse_protocol.py", "assistant_core/harness_client.py")
EXCHANGES_FOLDER = "exchanges"


def exchanges_dir() -> Path:
    return log_dir() / EXCHANGES_FOLDER


def health_json() -> Path:
    return log_dir() / "health.json"


def health_jsonl() -> Path:
    return log_dir() / "health.jsonl"


def last_good_ref() -> Path:
    return log_dir() / "last_good_ref"


def maintenance_flag() -> Path:
    """Exists while a deploy is changing things; the health check takes no action while it is present."""
    return log_dir() / "maintenance"


def deploy_lock() -> Path:
    return log_dir() / "deploy.lock"


def health_state() -> Path:
    """Consecutive-failure counts and cooldown timestamps carried from one health check to the next."""
    return log_dir() / "health_state.json"


SERVICE_LOG_NAMES = ("ollama", "llama", "mcp", "harness", "whisper", "kokoro", "health")


def service_log(name: str) -> Path:
    return log_dir() / f"{name}.log"
