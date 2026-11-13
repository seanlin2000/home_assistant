"""What the served model holds in RAM, measured without touching llama-server, for the memory tab (design doc v2/13 section 3.11).

Model weights: llama-server maps its model files, so how much of a file is in RAM is how many of its pages macOS holds, which mincore reports from
a mapping of our own. A model whose n-gram table stays on the SSD (Qwen 3.8 Flash Next, lazy_mode on) has only the rows read so far in RAM, so a
file's size would overstate it by tens of gigabytes. vmmap would show the same per process, but it pauses the process for a second or two.

KV cache: llama-server reports no size, so it is worked out from the model file's header as llama.cpp lays the cache out: keys and values (f16) for
every cell on each attention layer, one fixed recurrent state (f32) per slot on each recurrent layer, and for Qwen 4's sparse attention an indexer
key per cell. A layout this does not know (sliding-window layers, per-layer head counts, other indexers) gives no figure rather than a wrong one.

Prompt cache: llama-server logs its use only at trace level, so the tab shows the limit it was started with.
"""

import asyncio
import ctypes
import ctypes.util
import mmap
import os
import re
import time
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from dashboard.gguf_header import MetadataValue, read_gguf_metadata
from serving.settings import ModelSettings, load_serving_config

RESIDENCY_SECONDS = 30.0  # mincore over Flash Next's 70 GB takes about a second; what is resident changes slowly
F16_BYTES = 2
F32_BYTES = 4
MIB = 1024**2
PAGE_IN_CORE = 1
SHARD_NAME = re.compile(r"-(\d{5})-of-(\d{5})\.gguf$")
QWEN4_SPARSE_ATTENTION = "qwen4exp"
QWEN4_INDEXER_ROWS = 2  # a raw and a pooled key per cell, when its keys are pooled (llama.cpp src/models/qwen4exp.cpp)
_LIBC = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
_LIBC.mmap.restype = ctypes.c_void_p
_LIBC.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_longlong]
_LIBC.munmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
_LIBC.mincore.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_char_p]
MAP_FAILED = ctypes.c_void_p(-1).value
IN_CORE_BIT = bytes(byte & PAGE_IN_CORE for byte in range(256))


class ModelFileMemory(BaseModel):
    name: str
    resident_bytes: int
    size_bytes: int


class ModelMemory(BaseModel):
    files: list[ModelFileMemory]
    kv_cache_bytes: int | None  # None when the model's cache layout is not one model_memory works out
    context_tokens: int
    slots: int
    prompt_cache_limit_bytes: int

    @property
    def weights_bytes(self) -> int:
        return sum(model_file.resident_bytes for model_file in self.files)


class ServedModelMemory:
    """Reads config/serving.toml at every reading, so a switch to another model shows at the next one; a file's residency is kept RESIDENCY_SECONDS."""

    def __init__(self, load_model: Callable[[], ModelSettings] = lambda: load_serving_config().served_model, clock: Callable[[], float] = time.monotonic) -> None:
        self._load_model = load_model
        self._clock = clock
        self._residency: dict[Path, tuple[float, int]] = {}
        self._metadata: dict[Path, dict[str, MetadataValue]] = {}

    async def current(self) -> ModelMemory:
        model = self._load_model()
        paths = model_files(model.gguf_path)
        files = [ModelFileMemory(name=path.name, resident_bytes=await self._resident(path), size_bytes=path.stat().st_size) for path in paths]
        metadata = await self._header(paths[0])
        return ModelMemory(
            files=files,
            kv_cache_bytes=kv_cache_bytes(metadata, model.context_tokens, model.slots),
            context_tokens=model.context_tokens,
            slots=model.slots,
            prompt_cache_limit_bytes=model.prompt_cache_mib * MIB,
        )

    async def _resident(self, path: Path) -> int:
        kept = self._residency.get(path)
        if kept is None or self._clock() - kept[0] >= RESIDENCY_SECONDS:
            kept = (self._clock(), await asyncio.to_thread(resident_bytes, path))
            self._residency[path] = kept
        return kept[1]

    async def _header(self, path: Path) -> dict[str, MetadataValue]:
        if path not in self._metadata:
            self._metadata[path] = await asyncio.to_thread(read_gguf_metadata, path)
        return self._metadata[path]


def model_files(first_file: Path) -> list[Path]:
    """A model split into shards is named name-00001-of-00003.gguf and so on; llama-server maps every shard."""
    shard = SHARD_NAME.search(first_file.name)
    if shard is None:
        return [first_file]
    count = int(shard.group(2))
    stem = first_file.name[: shard.start()]
    return [first_file.with_name(f"{stem}-{number:05d}-of-{count:05d}.gguf") for number in range(1, count + 1)]


def resident_bytes(path: Path) -> int:
    """The bytes of the file macOS holds in RAM, from mincore over a read-only mapping of our own; mapping it reads nothing from disk."""
    size = path.stat().st_size
    descriptor = os.open(path, os.O_RDONLY)
    try:
        address = _LIBC.mmap(None, size, mmap.PROT_READ, mmap.MAP_SHARED, descriptor, 0)
        if address in (None, MAP_FAILED):
            raise OSError(ctypes.get_errno(), f"mmap of {path.name} failed")
        try:
            return pages_in_core(address, size) * mmap.PAGESIZE
        finally:
            _LIBC.munmap(address, size)
    finally:
        os.close(descriptor)


def pages_in_core(address: int, size: int) -> int:
    flags = ctypes.create_string_buffer((size + mmap.PAGESIZE - 1) // mmap.PAGESIZE)
    if _LIBC.mincore(address, size, flags) != 0:
        raise OSError(ctypes.get_errno(), "mincore failed")
    return flags.raw.translate(IN_CORE_BIT).count(PAGE_IN_CORE)


def kv_cache_bytes(metadata: dict[str, MetadataValue], context_tokens: int, slots: int) -> int | None:
    """Every cell of the context pool on each attention layer, and one recurrent state per slot on each recurrent layer."""
    architecture = str(metadata.get("general.architecture", ""))
    hyperparameters = {key.removeprefix(f"{architecture}."): value for key, value in metadata.items() if key.startswith(f"{architecture}.")}
    if not cache_layout_is_known(architecture, hyperparameters):
        return None
    layers = int(hyperparameters["block_count"])
    attention_layers = layers // int(hyperparameters.get("full_attention_interval") or 1)
    recurrent_layers = layers - attention_layers
    return attention_layers * context_tokens * attention_bytes_per_cell(architecture, hyperparameters) + recurrent_layers * slots * recurrent_state_bytes(hyperparameters)


def cache_layout_is_known(architecture: str, hyperparameters: dict[str, MetadataValue]) -> bool:
    if not architecture or "block_count" not in hyperparameters or "attention.sliding_window" in hyperparameters:
        return False
    if not isinstance(hyperparameters.get("attention.head_count_kv"), int):
        return False
    has_indexer = "attention.indexer.key_length" in hyperparameters
    return not has_indexer or architecture == QWEN4_SPARSE_ATTENTION


def attention_bytes_per_cell(architecture: str, hyperparameters: dict[str, MetadataValue]) -> int:
    head_width = int(hyperparameters["embedding_length"]) // int(hyperparameters["attention.head_count"])
    key_width = int(hyperparameters.get("attention.key_length") or head_width)
    value_width = int(hyperparameters.get("attention.value_length") or head_width)
    keys_and_values = int(hyperparameters["attention.head_count_kv"]) * (key_width + value_width) * F16_BYTES
    return keys_and_values + indexer_bytes_per_cell(architecture, hyperparameters)


def indexer_bytes_per_cell(architecture: str, hyperparameters: dict[str, MetadataValue]) -> int:
    if architecture != QWEN4_SPARSE_ATTENTION or "attention.indexer.key_length" not in hyperparameters:
        return 0
    pooled = any(ratio for ratio in hyperparameters.get("attention.compress_ratios") or [])
    return int(hyperparameters["attention.indexer.key_length"]) * (QWEN4_INDEXER_ROWS if pooled else 1) * F16_BYTES


def recurrent_state_bytes(hyperparameters: dict[str, MetadataValue]) -> int:
    """llama.cpp's convolution state, (kernel - 1) x (inner + 2 x groups x state), plus its state, state x inner, both f32."""
    if "ssm.inner_size" not in hyperparameters:
        return 0
    inner, state = int(hyperparameters["ssm.inner_size"]), int(hyperparameters["ssm.state_size"])
    groups, kernel = int(hyperparameters.get("ssm.group_count") or 0), int(hyperparameters["ssm.conv_kernel"])
    return ((kernel - 1) * (inner + 2 * groups * state) + state * inner) * F32_BYTES
