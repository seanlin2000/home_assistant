"""How much memory macOS moved between RAM and swap over the last minute, for the memory tab (design doc v2/13 section 3.11).

vm_stat counts the pages swapped in and out since the Mac started, so one reading says nothing about now; the change between readings a minute
apart does. The readings stay in the dashboard's own process, so the first minute after it starts covers less than a minute, and says so.
"""

from collections import deque

from pydantic import BaseModel

WINDOW_SECONDS = 60.0


class SwapCounters(BaseModel):
    """vm_stat's Swapins and Swapouts, in bytes moved since the Mac started."""

    read_back_bytes: int
    written_out_bytes: int


class SwapReading(BaseModel):
    taken_at: float  # the reader's clock, in seconds
    counters: SwapCounters


class SwapTraffic(BaseModel):
    read_back_bytes: int = 0  # read back from swap into RAM: an app waited for it
    written_out_bytes: int = 0  # written from RAM to swap to make room
    window_seconds: float = 0.0  # the span the two figures cover: a minute, or less while the dashboard has read for less


class SwapWindow:
    """The readings of the last minute, oldest first."""

    def __init__(self) -> None:
        self._readings: deque[SwapReading] = deque()

    def record(self, reading: SwapReading) -> None:
        self._readings.append(reading)
        while reading.taken_at - self._readings[0].taken_at > WINDOW_SECONDS:
            self._readings.popleft()

    def traffic(self) -> SwapTraffic:
        if not self._readings:
            return SwapTraffic()
        oldest, newest = self._readings[0], self._readings[-1]
        return SwapTraffic(
            read_back_bytes=newest.counters.read_back_bytes - oldest.counters.read_back_bytes,
            written_out_bytes=newest.counters.written_out_bytes - oldest.counters.written_out_bytes,
            window_seconds=newest.taken_at - oldest.taken_at,
        )
