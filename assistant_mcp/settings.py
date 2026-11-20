import os

from pydantic import BaseModel


class ToolServerSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8765
    allowed_hosts: str = ""  # comma-separated Host header values (host:port) accepted when bound to the LAN; empty means no Host check (localhost binds)


def allowed_host_list(settings: ToolServerSettings) -> list[str]:
    return [entry.strip() for entry in settings.allowed_hosts.split(",") if entry.strip()]


def tool_server_settings_from_environment() -> ToolServerSettings:
    """Environment variables prefixed ASSISTANT_MCP_ override the defaults, e.g. ASSISTANT_MCP_PORT for a benchmark run."""
    overrides = {key.removeprefix("ASSISTANT_MCP_").lower(): value for key, value in os.environ.items() if key.startswith("ASSISTANT_MCP_")}
    return ToolServerSettings(**overrides)
