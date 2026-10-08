"""The model's GGUF file: check it against its pinned SHA-256, and download it from Hugging Face at its pinned revision."""

import hashlib
from pathlib import Path

import httpx

from serving.settings import ModelSettings

HASH_CHUNK_BYTES = 8 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 60.0


class ModelFileMismatch(Exception):
    """The file on disk is missing or is not the one the benchmark measured."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def verify_model_file(model: ModelSettings) -> None:
    path = model.gguf_path
    if not path.is_file():
        raise ModelFileMismatch(f"{path} does not exist; run `uv run serving fetch`")
    actual = file_sha256(path)
    if actual != model.sha256:
        raise ModelFileMismatch(f"{path} has SHA-256 {actual}, but config/serving.toml pins {model.sha256}")


def fetch_model_file(model: ModelSettings) -> Path:
    """Download into a partial file, check its hash, then move it into place, so a broken download never sits where the launcher looks."""
    path = model.gguf_path
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f"{path.name}.partial")
    with httpx.stream("GET", model.download_url, follow_redirects=True, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
        response.raise_for_status()
        with partial.open("wb") as handle:
            for chunk in response.iter_bytes(HASH_CHUNK_BYTES):
                handle.write(chunk)
    actual = file_sha256(partial)
    if actual != model.sha256:
        partial.unlink()
        raise ModelFileMismatch(f"downloaded {model.download_url} has SHA-256 {actual}, but config/serving.toml pins {model.sha256}")
    partial.replace(path)
    return path
