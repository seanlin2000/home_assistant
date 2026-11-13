"""Run macOS's memory tools for the memory tab, at most once every few seconds however many pages ask (design doc v2/13 section 3.11). The tools
run on the Mac the dashboard runs on, so a page opened from a laptop shows the serving Mac's memory."""

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Protocol

from dashboard.gguf_header import GgufHeaderError
from dashboard.memory_views import MemoryOutputs, MemoryView, memory_view
from dashboard.model_memory import ModelMemory

SNAPSHOT_SECONDS = 4.0  # the page asks every two seconds; top alone takes about half a second
COMMAND_TIMEOUT_SECONDS = 10.0
COMMANDS = {
    "top": ["top", "-l", "1", "-stats", "pid,mem,cmprs"],
    "executables": ["ps", "-axww", "-o", "pid=,comm="],
    "command_lines": ["ps", "-axww", "-o", "pid=,args="],
    "vm_stat": ["vm_stat"],
    "sysctl": ["sysctl", "-n", "hw.memsize", "vm.swapusage", "machdep.cpu.brand_string"],
    "computer_name": ["scutil", "--get", "ComputerName"],
}
ReadOutputs = Callable[[], Awaitable[MemoryOutputs]]
Clock = Callable[[], float]


class ModelMemorySource(Protocol):
    async def current(self) -> ModelMemory: ...


async def read_memory_outputs() -> MemoryOutputs:
    texts = await asyncio.gather(*(command_output(arguments) for arguments in COMMANDS.values()))
    return MemoryOutputs(**dict(zip(COMMANDS, texts)))


async def command_output(arguments: list[str]) -> str:
    process = await asyncio.create_subprocess_exec(*arguments, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    try:
        stdout, _stderr = await asyncio.wait_for(process.communicate(), COMMAND_TIMEOUT_SECONDS)
    except TimeoutError:
        process.kill()
        raise
    return stdout.decode(errors="replace")


class MemoryReader:
    """The served model is read at every reading, so a switch to another model shows at the next one, with no restart."""

    def __init__(self, read_outputs: ReadOutputs, model_memory: ModelMemorySource | None, clock: Clock = time.monotonic) -> None:
        self._read_outputs = read_outputs
        self._model_memory = model_memory
        self._clock = clock
        self._lock = asyncio.Lock()
        self._view: MemoryView | None = None
        self._taken_at = 0.0

    async def current(self) -> MemoryView:
        async with self._lock:
            if self._view is None or self._clock() - self._taken_at >= SNAPSHOT_SECONDS:
                outputs, model_memory = await asyncio.gather(self._read_outputs(), self._served_model_memory())
                self._view = memory_view(outputs, model_memory)
                self._taken_at = self._clock()
            return self._view

    async def _served_model_memory(self) -> ModelMemory | None:
        if self._model_memory is None:
            return None
        return await measured_model_memory(self._model_memory)


async def measured_model_memory(source: ModelMemorySource) -> ModelMemory | None:
    """None when the served model's files cannot be read, as when serving.toml names a file not downloaded; the tab then shows llama-server alone."""
    try:
        return await source.current()
    except (OSError, GgufHeaderError, ValueError):
        return None
