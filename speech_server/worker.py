"""Every model call on one thread, kept for the life of the server, with the results handed back to the event loop as they are made.

MLX keeps state per thread: on a fresh thread a short question took 1.2 s to transcribe instead of 0.3 s, so the models are loaded, warmed up and called
on the same thread. One thread also means two calls never run at once, which MLX does not allow.
"""

import asyncio
from collections.abc import AsyncIterator, Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol, TypeVar

import numpy as np

FINISHED = object()
Result = TypeVar("Result")


class SpeechModels(Protocol):
    @property
    def sample_rate(self) -> int: ...

    def speak(self, sentence: str, voice: str) -> Iterator[np.ndarray]: ...

    def transcribe(self, audio: np.ndarray) -> str: ...


class ModelThread:
    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mlx")

    def run(self, call: Callable[..., Result], *arguments: object) -> Result:
        """Blocks until the call has run on the model thread; for loading and warming up before the server starts."""
        return self._executor.submit(call, *arguments).result()

    async def run_async(self, call: Callable[..., Result], *arguments: object) -> Result:
        return await asyncio.get_running_loop().run_in_executor(self._executor, call, *arguments)

    async def pieces(self, make_pieces: Callable[[], Iterator[np.ndarray]]) -> AsyncIterator[np.ndarray]:
        """Runs a generator on the model thread and yields each piece on the event loop as soon as the thread produces it."""
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def produce() -> None:
            try:
                for piece in make_pieces():
                    loop.call_soon_threadsafe(queue.put_nowait, piece)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, FINISHED)

        production = loop.run_in_executor(self._executor, produce)
        while (piece := await queue.get()) is not FINISHED:
            yield piece
        await production


class SpeechWorker:
    """The models as the Wyoming handlers use them: awaitable, and always on the model thread."""

    def __init__(self, models: SpeechModels, thread: ModelThread) -> None:
        self._models = models
        self._thread = thread

    @property
    def sample_rate(self) -> int:
        return self._models.sample_rate

    async def transcribe(self, audio: np.ndarray) -> str:
        return await self._thread.run_async(self._models.transcribe, audio)

    def speak(self, sentence: str, voice: str) -> AsyncIterator[np.ndarray]:
        return self._thread.pieces(lambda: self._models.speak(sentence, voice))
