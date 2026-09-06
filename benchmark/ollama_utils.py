"""Model lifecycle around a benchmark run: make sure a tag is present, load it, check it sits on the GPU, unload it, optionally delete it."""

import subprocess

import ollama

from benchmark.records import MemoryFit


async def ensure_model_present(client: ollama.AsyncClient, model: str) -> None:
    listed = await client.list()
    if any(entry.model == model for entry in listed.models):
        return
    # The CLI shows a progress bar for multi-gigabyte downloads; the Python client would need one written by hand.
    subprocess.run(["ollama", "pull", model], check=True)


async def warm_up(client: ollama.AsyncClient, model: str, context_tokens: int) -> MemoryFit:
    await client.generate(model=model, prompt="hi", options={"num_predict": 1, "num_ctx": context_tokens}, keep_alive="10m")
    return await memory_fit(client, model)


async def memory_fit(client: ollama.AsyncClient, model: str) -> MemoryFit:
    running = await client.ps()
    for entry in running.models:
        if entry.model == model:
            return MemoryFit(model_size_bytes=entry.size, gpu_resident_bytes=entry.size_vram, fully_on_gpu=bool(entry.size and entry.size_vram and entry.size_vram >= entry.size))
    return MemoryFit()


async def unload(client: ollama.AsyncClient, model: str) -> None:
    await client.generate(model=model, prompt="", keep_alive=0)


async def delete_model(client: ollama.AsyncClient, model: str) -> None:
    await client.delete(model)
