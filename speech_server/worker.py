"""Every model call on one thread, kept for the life of the server.

MLX keeps state per thread: on a fresh thread a short question took 1.2 s to transcribe instead of 0.3 s, so the model is loaded, warmed up and called
on the same thread. One thread also means two calls never run at once, which MLX does not allow.
"""

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol, TypeVar

import numpy as np

Result = TypeVar("Result")


class Recognizer(Protocol):
    def transcribe(self, audio: np.ndarray) -> str: ...


class ModelThread:
    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mlx")

    def run(self, call: Callable[..., Result], *arguments: object) -> Result:
        """Blocks until the call has run on the model thread; for loading and warming up before the server starts."""
        return self._executor.submit(call, *arguments).result()

    async def run_async(self, call: Callable[..., Result], *arguments: object) -> Result:
        return await asyncio.get_running_loop().run_in_executor(self._executor, call, *arguments)


class SpeechWorker:
    """The recognizer as the Wyoming handler uses it: awaitable, and always on the model thread."""

    def __init__(self, recognizer: Recognizer, thread: ModelThread) -> None:
        self._recognizer = recognizer
        self._thread = thread

    async def transcribe(self, audio: np.ndarray) -> str:
        return await self._thread.run_async(self._recognizer.transcribe, audio)
