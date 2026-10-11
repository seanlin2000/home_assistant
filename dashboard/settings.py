"""Where the dashboard listens, who it answers, and how it reaches Home Assistant (design doc v2/13 section 5)."""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

from utils.http_access_utils import allowed_hosts_from_environment

PROJECT_DIR = Path(__file__).resolve().parent.parent
DASHBOARD_HOST = "0.0.0.0"  # the page is read from a laptop on the home network, and the Host header check below keeps it to names of this Mac
DASHBOARD_PORT = 8775
ALLOWED_HOSTS_VARIABLE = "DASHBOARD_ALLOWED_HOSTS"
PIPELINE_POLL_SECONDS = 5.0
STATIC_DIR = Path(__file__).resolve().parent / "static"


class HomeAssistantAccess(BaseModel):
    host: str
    token: str
    base: str


def allowed_hosts() -> list[str]:
    return allowed_hosts_from_environment(ALLOWED_HOSTS_VARIABLE, DASHBOARD_PORT)


def home_assistant_access() -> HomeAssistantAccess | None:
    """Home Assistant's address and token from .env, as the health check reads them; None turns the pipeline run collector off."""
    load_dotenv(PROJECT_DIR / ".env")
    host, token = os.environ.get("HA_HOST"), os.environ.get("HA_TOKEN")
    if not host or not token:
        return None
    return HomeAssistantAccess(host=host, token=token, base=os.environ.get("HA_BASE") or f"http://{host}")
