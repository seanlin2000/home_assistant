"""Turn the served model's settings into the llama-server command line (design_docs/v2/02_inference_engine.md section 3.5, the flag table)."""

import shutil

from serving.settings import ModelSettings, ServerSettings, ServingConfig

LLAMA_SERVER_PROGRAM = "llama-server"
# Flags that let the server run commands, read files, call MCP servers, or change its own settings. No setting can produce them, and the launcher
# refuses a command line that contains one, so a future edit to this module cannot slip one in either.
REFUSED_FLAGS = frozenset({"--tools", "--mcp-servers-config", "--media-path", "--slot-save-path", "--props"})


def llama_server_program() -> str:
    return shutil.which(LLAMA_SERVER_PROGRAM) or f"/opt/homebrew/bin/{LLAMA_SERVER_PROGRAM}"


def build_command(config: ServingConfig) -> list[str]:
    command = [llama_server_program(), *server_flags(config.server), *model_flags(config.server.model, config.served_model)]
    refuse_dangerous_flags(command)
    return command


def server_flags(server: ServerSettings) -> list[str]:
    return ["--host", server.host, "--port", str(server.port), "--api-key-file", str(server.api_key_path), "--no-ui", "--metrics", "--jinja"]


def model_flags(alias: str, model: ModelSettings) -> list[str]:
    flags = [
        "-m",
        str(model.gguf_path),
        "--alias",
        alias,
        "-c",
        str(model.context_tokens),
        "-np",
        str(model.slots),
        "-ngl",
        str(model.gpu_layers),
        "-fa",
        model.flash_attention,
        "-cram",
        str(model.prompt_cache_mib),
        "--reasoning",
        model.reasoning,
        "--kv-unified" if model.kv_unified else "--no-kv-unified",
        "--cache-idle-slots" if model.cache_idle_slots else "--no-cache-idle-slots",
    ]
    if model.swa_full:
        flags.append("--swa-full")
    return flags


def refuse_dangerous_flags(command: list[str]) -> None:
    refused = REFUSED_FLAGS.intersection(command)
    if refused:
        raise ValueError(f"refusing to launch llama-server with {sorted(refused)}")


def printable_command(command: list[str]) -> str:
    """The command for `serving show`. The key file's path is shown; the key itself never appears on the command line."""
    return " ".join(part if " " not in part else f'"{part}"' for part in command)
