"""The typed contents of config/serving.toml. Every table forbids unknown keys, so a misspelt setting stops the launch instead of being ignored."""

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class EngineSettings(StrictModel):
    """The llama.cpp release the benchmark measured. `brew pin llama.cpp ggml` holds it, and the launch refuses any other (doc 10 section 3.8)."""

    llama_cpp_version: str
    llama_cpp_build: int
    ggml_version: str  # llama-server loads its compute libraries from Homebrew's separate ggml package, so pinning llama.cpp alone does not hold them


class Sampling(StrictModel):
    """How the model picks each next token, with the names llama-server takes per request."""

    temperature: float
    top_p: float
    top_k: int
    min_p: float
    presence_penalty: float
    repeat_penalty: float
    max_output_tokens: int

    def policy_fields(self) -> dict[str, float | int]:
        """The fields of an AgentPolicy these settings fill."""
        return self.model_dump()


class PinnedFile(StrictModel):
    """A GGUF file pinned to one Hugging Face revision and SHA-256, so the launch serves exactly the file the benchmark measured."""

    gguf: str
    source: str
    revision: str
    sha256: str

    @property
    def gguf_path(self) -> Path:
        return Path(self.gguf).expanduser()

    @property
    def download_url(self) -> str:
        return f"https://huggingface.co/{self.source}/resolve/{self.revision}/{self.gguf_path.name}"


class DraftModel(PinnedFile):
    """A separate small model that proposes tokens for the served model to check (-md), for a model whose own file has no draft layer."""

    gpu_layers: int | Literal["all", "auto"]  # -ngld
    max_draft_tokens: int  # --spec-draft-n-max; each step the drafter proposes up to this many tokens and the served model checks them all at once


class ModelSettings(PinnedFile):
    context_tokens: int
    conversation_tokens: int
    slots: int
    kv_unified: bool
    cache_idle_slots: bool
    gpu_layers: int | Literal["all", "auto"]
    flash_attention: Literal["on", "off", "auto"]
    prompt_cache_mib: int
    reasoning: Literal["on", "off", "auto"]
    reasoning_budget_tokens: int | None = None  # --reasoning-budget; past it the server ends the thinking block, so the answer keeps the rest of the cap
    swa_full: bool
    speculative: Literal["none", "draft-mtp", "draft-dflash"]  # --spec-type; draft-mtp uses the model file's own layer, draft-dflash needs `draft`
    draft: DraftModel | None = None
    load_mode: Literal["auto", "mmap"] = "auto"  # -lm; "mmap" keeps the file memory-mapped, which lazy_mode needs
    lazy_mode: Literal["off", "on"] = "off"  # -lzm; "on" reads per-layer embedding tables (an n-gram table) from disk on demand instead of keeping them resident
    sampling: Sampling
    thinking_sampling: Sampling | None = None  # the model maker's set for thinking mode; without one, thinking uses `sampling`

    @model_validator(mode="after")
    def require_a_draft_model_exactly_for_dflash(self) -> "ModelSettings":
        if (self.speculative == "draft-dflash") != (self.draft is not None):
            raise ValueError('speculative = "draft-dflash" needs a [draft] table, and a [draft] table needs speculative = "draft-dflash"')
        return self

    def sampling_for(self, think: bool | str | None) -> Sampling:
        """The set for answering with thinking on (a level or True) or off (False or None)."""
        return self.thinking_sampling if think not in (None, False) and self.thinking_sampling else self.sampling

    @property
    def pinned_files(self) -> list[PinnedFile]:
        """Every file the launch loads: the model, then its drafter if it has one."""
        return [self, self.draft] if self.draft else [self]


class ServingConfig(StrictModel):
    server: ServerSettings
    engine: EngineSettings
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
