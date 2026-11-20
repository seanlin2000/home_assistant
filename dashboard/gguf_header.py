"""The metadata at the head of a GGUF model file, read without loading the model: the layer counts and widths that size llama-server's KV cache.

A GGUF file starts with its key-value metadata, before any tensor. Long arrays (the tokenizer's vocabulary and merges) are stepped over rather than
kept, since no size needs them; an array of up to MAX_KEPT_ARRAY_LENGTH items, such as a per-layer setting, is kept as a list.
"""

import struct
from pathlib import Path
from typing import BinaryIO

GGUF_MAGIC = b"GGUF"
MAX_KEPT_ARRAY_LENGTH = 1024
SCALAR_FORMATS = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i", 6: "<f", 7: "<?", 10: "<Q", 11: "<q", 12: "<d"}
STRING_TYPE = 8
ARRAY_TYPE = 9
MetadataValue = int | float | bool | str | list | None


class GgufHeaderError(ValueError):
    """The file is not a GGUF model file, or its metadata uses a type this reader does not know."""


def read_gguf_metadata(path: Path) -> dict[str, MetadataValue]:
    with path.open("rb") as model_file:
        if model_file.read(len(GGUF_MAGIC)) != GGUF_MAGIC:
            raise GgufHeaderError(f"{path.name} is not a GGUF file")
        read_scalar(model_file, "<I")  # format version
        read_scalar(model_file, "<Q")  # tensor count
        entries = read_scalar(model_file, "<Q")
        return dict(read_entry(model_file) for _ in range(entries))


def read_entry(model_file: BinaryIO) -> tuple[str, MetadataValue]:
    key = read_string(model_file)
    return key, read_value(model_file, read_scalar(model_file, "<I"))


def read_value(model_file: BinaryIO, value_type: int) -> MetadataValue:
    if value_type in SCALAR_FORMATS:
        return read_scalar(model_file, SCALAR_FORMATS[value_type])
    if value_type == STRING_TYPE:
        return read_string(model_file)
    if value_type == ARRAY_TYPE:
        return read_array(model_file)
    raise GgufHeaderError(f"unknown GGUF metadata type {value_type}")


def read_array(model_file: BinaryIO) -> list | None:
    item_type, length = read_scalar(model_file, "<I"), read_scalar(model_file, "<Q")
    if length <= MAX_KEPT_ARRAY_LENGTH:
        return [read_value(model_file, item_type) for _ in range(length)]
    skip_array(model_file, item_type, length)
    return None


def skip_array(model_file: BinaryIO, item_type: int, length: int) -> None:
    if item_type in SCALAR_FORMATS:
        model_file.seek(struct.calcsize(SCALAR_FORMATS[item_type]) * length, 1)
        return
    for _ in range(length):
        if item_type == STRING_TYPE:
            model_file.seek(read_scalar(model_file, "<Q"), 1)
        else:
            read_value(model_file, item_type)


def read_string(model_file: BinaryIO) -> str:
    return model_file.read(read_scalar(model_file, "<Q")).decode(errors="replace")


def read_scalar(model_file: BinaryIO, layout: str) -> int | float | bool:
    return struct.unpack(layout, model_file.read(struct.calcsize(layout)))[0]
