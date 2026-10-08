"""The typed contents of config/harness.toml, plus the host names the service answers to, which come from its launchd agent's environment."""

import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from assistant_core.models import AgentPolicy
from serving.settings import ServingConfig

HARNESS_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "harness.toml"
ALLOWED_HOSTS_VARIABLE = "HARNESS_ALLOWED_HOSTS"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ServiceSettings(StrictModel):
    host: str
    port: int
    api_key_file: str
    state_file: str
    tool_server_url: str
    conversation_quiet_minutes: float

    @property
    def api_key_path(self) -> Path:
        return Path(self.api_key_file).expanduser()

    @property
    def state_path(self) -> Path:
        return Path(self.state_file).expanduser()


class AnswerSettings(StrictModel):
    temperature: float
    word_budget: int
    max_tool_rounds: int
    tool_timeout_seconds: float


class HarnessConfig(StrictModel):
    service: ServiceSettings
    answer: AnswerSettings

    def allowed_hosts(self) -> list[str]:
        """Host header values the service answers to: the derived list from the environment, or this machine's loopback names."""
        configured = os.environ.get(ALLOWED_HOSTS_VARIABLE, "")
        hosts = [entry.strip() for entry in configured.split(",") if entry.strip()]
        return hosts or [f"localhost:{self.service.port}", f"127.0.0.1:{self.service.port}"]

    def policy(self, serving: ServingConfig) -> AgentPolicy:
        """The loop policy: the answer settings from this file, the window and output cap from the served model's settings."""
        model = serving.served_model
        return AgentPolicy(
            temperature=self.answer.temperature,
            word_budget=self.answer.word_budget,
            max_tool_rounds=self.answer.max_tool_rounds,
            tool_timeout_seconds=self.answer.tool_timeout_seconds,
            context_tokens=model.conversation_tokens,
            max_output_tokens=model.sampling.max_output_tokens,
        )


def load_harness_config(path: Path = HARNESS_CONFIG_PATH) -> HarnessConfig:
    return HarnessConfig.model_validate(tomllib.loads(path.read_text()))
