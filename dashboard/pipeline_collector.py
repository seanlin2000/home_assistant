"""Copy Home Assistant's Assist pipeline runs into day files before it forgets them; it keeps only the last few in memory (design doc v2/13 section 3.3)."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from ops.pipeline_runs import PIPELINE_RUN_RETENTION_DAYS, PipelineRun, PipelineRunLog

_LOGGER = logging.getLogger(__name__)

RunPuller = Callable[[set[str]], Awaitable[list[PipelineRun]]]


class PipelineRunCollector:
    def __init__(self, log: PipelineRunLog, pull_new_runs: RunPuller) -> None:
        self._log = log
        self._pull_new_runs = pull_new_runs
        self._known: set[str] | None = None
        self._last_failure: str | None = None

    async def collect(self) -> int:
        """Append the runs not seen before and return how many there were."""
        if self._known is None:
            self._known = self.kept_run_ids()
        new_runs = await self._pull_new_runs(self._known)
        for run in new_runs:
            self._log.append(run)
            self._known.add(run.run_id)
        return len(new_runs)

    def kept_run_ids(self) -> set[str]:
        since = datetime.now(UTC).date() - timedelta(days=PIPELINE_RUN_RETENTION_DAYS)
        return {run.run_id for run in self._log.read_since(since)}

    async def collect_forever(self, interval_seconds: float) -> None:
        while True:
            await self.collect_logging_failures()
            await asyncio.sleep(interval_seconds)

    async def collect_logging_failures(self) -> None:
        """A failure is logged when it starts, not on every poll, so a Home Assistant down overnight writes one line instead of thousands."""
        try:
            await self.collect()
            self._last_failure = None
        except Exception as error:  # noqa: BLE001 - Home Assistant restarting must not stop the page; the next poll tries again
            self.note_failure(f"{type(error).__name__}: {error}")

    def note_failure(self, failure: str) -> None:
        if failure != self._last_failure:
            _LOGGER.warning("pipeline runs not collected: %s", failure)
        self._last_failure = failure
