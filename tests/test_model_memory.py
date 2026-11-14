"""What the served model holds in RAM: the GGUF header read without loading the model, the KV cache worked out from it as llama.cpp lays it out,
every shard of a split model, and the part of each file macOS holds in RAM, kept half a minute between readings."""

import struct
from pathlib import Path

from dashboard.gguf_header import MetadataValue, read_gguf_metadata
from dashboard.model_memory import ServedModelMemory, kv_cache_bytes, model_files, resident_bytes
from serving.settings import ModelSettings, load_serving_config

MIB = 1024**2
# The header of Qwen 3.8 Flash Next GSQ-RCO IQ3_XXS, as the Studio's copy reads, cut to what sizes the cache.
FLASH_NEXT_HEADER: dict[str, MetadataValue] = {
    "general.architecture": "qwen4exp",
    "qwen4exp.block_count": 48,
    "qwen4exp.embedding_length": 2560,
    "qwen4exp.attention.head_count": 24,
    "qwen4exp.attention.head_count_kv": 2,
    "qwen4exp.attention.key_length": 256,
    "qwen4exp.attention.value_length": 256,
    "qwen4exp.full_attention_interval": 4,
    "qwen4exp.ssm.conv_kernel": 4,
    "qwen4exp.ssm.state_size": 128,
    "qwen4exp.ssm.group_count": 16,
    "qwen4exp.ssm.inner_size": 6144,
    "qwen4exp.attention.indexer.key_length": 128,
    "qwen4exp.attention.compress_ratios": [0, 0, 0, 4] * 12,
}
STRING, UINT32, ARRAY = 8, 4, 9


def gguf_bytes(entries: list[tuple[str, int, bytes]]) -> bytes:
    """A GGUF file's start: magic, version, no tensors, then each key with its type and encoded value."""
    body = b"".join(gguf_string(key) + struct.pack("<I", value_type) + value for key, value_type, value in entries)
    return b"GGUF" + struct.pack("<IQQ", 3, 0, len(entries)) + body


def gguf_string(text: str) -> bytes:
    return struct.pack("<Q", len(text.encode())) + text.encode()


def served_model(gguf: Path) -> ModelSettings:
    return load_serving_config().models["qwen3.8-flash-next"].model_copy(update={"gguf": str(gguf)})


def test_the_header_keeps_short_arrays_and_steps_over_the_vocabulary(tmp_path: Path) -> None:
    vocabulary = struct.pack("<IQ", STRING, 5000) + b"".join(gguf_string(f"token{number}") for number in range(5000))
    entries = [
        ("general.architecture", STRING, gguf_string("qwen4exp")),
        ("tokenizer.ggml.tokens", ARRAY, vocabulary),
        ("qwen4exp.attention.compress_ratios", ARRAY, struct.pack("<IQ", UINT32, 4) + struct.pack("<4I", 0, 0, 0, 4)),
        ("qwen4exp.block_count", UINT32, struct.pack("<I", 48)),
    ]
    path = tmp_path / "model.gguf"
    path.write_bytes(gguf_bytes(entries))
    assert read_gguf_metadata(path) == {
        "general.architecture": "qwen4exp",
        "tokenizer.ggml.tokens": None,
        "qwen4exp.attention.compress_ratios": [0, 0, 0, 4],
        "qwen4exp.block_count": 48,
    }


def test_flash_nexts_cache_is_its_attention_and_indexer_cells_plus_a_recurrent_state_per_slot() -> None:
    attention = 12 * 34816 * (2 * (256 + 256) * 2 + 128 * 2 * 2)  # 12 attention layers: keys and values, then a raw and a pooled indexer key
    recurrent = 36 * 2 * (3 * (6144 + 2 * 16 * 128) + 128 * 6144) * 4  # 36 recurrent layers, one state per slot, f32
    assert kv_cache_bytes(FLASH_NEXT_HEADER, context_tokens=34816, slots=2) == attention + recurrent
    assert round((attention + recurrent) / MIB) == 1244  # inside the 1.36 GiB of Metal buffers vmmap showed llama-server holding


def test_a_plain_attention_model_counts_keys_and_values_on_every_layer() -> None:
    header = {"general.architecture": "llama", "llama.block_count": 32, "llama.embedding_length": 4096, "llama.attention.head_count": 32, "llama.attention.head_count_kv": 8}
    assert kv_cache_bytes(header, context_tokens=8192, slots=1) == 32 * 8192 * 8 * (128 + 128) * 2


def test_a_cache_layout_not_worked_out_gives_no_figure_rather_than_a_wrong_one() -> None:
    sliding_window = {**FLASH_NEXT_HEADER, "qwen4exp.attention.sliding_window": 512}
    per_layer_heads = {**FLASH_NEXT_HEADER, "qwen4exp.attention.head_count_kv": [2] * 48}
    other_indexer = {key.replace("qwen4exp", "deepseek4"): value for key, value in FLASH_NEXT_HEADER.items()} | {"general.architecture": "deepseek4"}
    assert [kv_cache_bytes(header, 34816, 2) for header in (sliding_window, per_layer_heads, other_indexer, {})] == [None, None, None, None]


def test_every_shard_of_a_split_model_is_measured() -> None:
    first = Path("/models/Flash-Next-IQ3_XXS-00001-of-00002.gguf")
    assert model_files(first) == [first, Path("/models/Flash-Next-IQ3_XXS-00002-of-00002.gguf")]
    assert model_files(Path("/models/gemma.gguf")) == [Path("/models/gemma.gguf")]


def test_a_file_just_written_is_in_ram_and_never_counts_past_its_pages(tmp_path: Path) -> None:
    path = tmp_path / "weights.bin"
    path.write_bytes(b"\x01" * (4 * MIB))
    assert 0 < resident_bytes(path) <= 4 * MIB


async def test_residency_is_kept_half_a_minute_and_the_header_read_once(tmp_path: Path) -> None:
    path = tmp_path / "model.gguf"
    path.write_bytes(gguf_bytes([("general.architecture", STRING, gguf_string("unknown"))]))
    now = [0.0]
    measured = ServedModelMemory(load_model=lambda: served_model(path), clock=lambda: now[0])
    first = await measured.current()
    path.write_bytes(path.read_bytes() + b"\x00" * MIB)
    now[0] += 10
    kept = await measured.current()
    now[0] += 30
    fresh = await measured.current()
    assert (first.kv_cache_bytes, first.context_tokens, first.slots, first.prompt_cache_limit_bytes) == (None, 34816, 2, 1024 * MIB)
    assert kept.files[0].resident_bytes == first.files[0].resident_bytes
    assert fresh.files[0].resident_bytes > first.files[0].resident_bytes
