"""Where the dashboard listens, who it answers, and how it reaches Home Assistant (design doc v2/13 section 5)."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

from assistant_core.llama_server_client import LlamaServerClient
from assistant_service.settings import load_harness_config
from serving.settings import load_serving_config, read_api_key
from utils.http_access_utils import allowed_hosts_from_environment

PROJECT_DIR = Path(__file__).resolve().parent.parent
DASHBOARD_HOST = "0.0.0.0"  # the page is read from a laptop on the home network, and the Host header check below keeps it to names of this Mac
DASHBOARD_PORT = 8775
ALLOWED_HOSTS_VARIABLE = "DASHBOARD_ALLOWED_HOSTS"
PIPELINE_POLL_SECONDS = 5.0
STATIC_DIR = Path(__file__).resolve().parent / "static"


@dataclass(frozen=True)
class LlamaServerAccess:
    client: LlamaServerClient
    pool_tokens: int
    conversation_tokens: int


class HomeAssistantAccess(BaseModel):
    host: str
    token: str
    base: str


def allowed_hosts() -> list[str]:
    return allowed_hosts_from_environment(ALLOWED_HOSTS_VARIABLE, DASHBOARD_PORT)


def harness_url() -> str:
    return f"http://127.0.0.1:{load_harness_config().service.port}"


def harness_key() -> str | None:
    """The harness's API key, which the chat box's questions carry; the browser never sees it. None turns the chat box off."""
    path = load_harness_config().service.api_key_path
    return path.read_text().strip() if path.exists() else None


def llama_server_access() -> LlamaServerAccess | None:
    """llama-server's address, key, and slot budget from config/serving.toml; the key stays on the Mac. None turns the prompt cache tab off."""
    serving = load_serving_config()
    key_path = serving.server.api_key_path
    if not key_path.exists():
        return None
    client = LlamaServerClient(serving.server.base_url, read_api_key(key_path), serving.server.model)
    return LlamaServerAccess(client=client, pool_tokens=serving.served_model.context_tokens, conversation_tokens=serving.served_model.conversation_tokens)


def home_assistant_access() -> HomeAssistantAccess | None:
    """Home Assistant's address and token from .env, as the health check reads them; None turns the pipeline run collector off."""
    load_dotenv(PROJECT_DIR / ".env")
    host, token = os.environ.get("HA_HOST"), os.environ.get("HA_TOKEN")
    if not host or not token:
        return None
    return HomeAssistantAccess(host=host, token=token, base=os.environ.get("HA_BASE") or f"http://{host}")
