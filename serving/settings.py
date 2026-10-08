"""The typed contents of config/serving.toml. Every table forbids unknown keys, so a misspelt setting stops the launch instead of being ignored."""

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SERVING_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "serving.toml"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ServerSettings(StrictModel):
    host: str
    port: int
    api_key_file: str
    model: str

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def api_key_path(self) -> Path:
        return Path(self.api_key_file).expanduser()


class Sampling(StrictModel):
    temperature: float
    max_output_tokens: int


class ModelSettings(StrictModel):
    gguf: str
    source: str
    revision: str
    sha256: str
    context_tokens: int
    conversation_tokens: int
    slots: int
    kv_unified: bool
    cache_idle_slots: bool
    gpu_layers: int | Literal["all", "auto"]
    flash_attention: Literal["on", "off", "auto"]
    prompt_cache_mib: int
    reasoning: Literal["on", "off", "auto"]
    swa_full: bool
    sampling: Sampling

    @property
    def gguf_path(self) -> Path:
        return Path(self.gguf).expanduser()

    @property
    def download_url(self) -> str:
        return f"https://huggingface.co/{self.source}/resolve/{self.revision}/{self.gguf_path.name}"


class ServingConfig(StrictModel):
    server: ServerSettings
    models: dict[str, ModelSettings] = Field(min_length=1)

    @property
    def served_model(self) -> ModelSettings:
        if self.server.model not in self.models:
            raise KeyError(f"[server] model = {self.server.model!r} names no [models.{self.server.model}] table")
        return self.models[self.server.model]


def load_serving_config(path: Path = SERVING_CONFIG_PATH) -> ServingConfig:
    return ServingConfig.model_validate(tomllib.loads(path.read_text()))


def read_api_key(path: Path) -> str:
    return path.read_text().strip()
