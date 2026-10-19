"""Run the exchange dashboard: `uv run exchange-dashboard`, which scripts/services.sh's launchd agent does (design doc v2/13)."""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import uvicorn
from starlette.applications import Starlette

from assistant_core.harness_client import HarnessClient
from assistant_service.exchange_log import ExchangeLog, TraceLog
from dashboard.app import Converse, build_app
from dashboard.exchange_views import ExchangeStore
from dashboard.pipeline_collector import PipelineRunCollector
from dashboard.settings import DASHBOARD_HOST, DASHBOARD_PORT, PIPELINE_POLL_SECONDS, HomeAssistantAccess, allowed_hosts, harness_key, harness_url, home_assistant_access
from ops import paths
from ops.ha_client import HomeAssistant
from ops.pipeline_runs import PipelineRun, PipelineRunLog, pull_and_close

_LOGGER = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    runs = PipelineRunLog(paths.pipeline_runs_dir())
    store = ExchangeStore(ExchangeLog(paths.exchanges_dir()), TraceLog(paths.traces_dir()), runs)
    app = build_app(store, allowed_hosts(), converse=converse_for(harness_key()), lifespan=lifespan_for(collector_for(runs, home_assistant_access())))
    uvicorn.run(app, host=DASHBOARD_HOST, port=DASHBOARD_PORT, log_level="warning")


def converse_for(key: str | None) -> Converse | None:
    if key is None:
        _LOGGER.info("the harness's API key was not found, so the chat box is off")
        return None
    return HarnessClient(harness_url(), key).converse


def collector_for(runs: PipelineRunLog, access: HomeAssistantAccess | None) -> PipelineRunCollector | None:
    if access is None:
        _LOGGER.info("HA_HOST or HA_TOKEN is missing from .env, so the page shows no speech timings")
        return None

    async def pull_new_runs(known: set[str]) -> list[PipelineRun]:
        return await pull_and_close(HomeAssistant(access.host, access.token, access.base), None, known)

    return PipelineRunCollector(runs, pull_new_runs)


def lifespan_for(collector: PipelineRunCollector | None) -> Callable[[Starlette], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        polling = asyncio.create_task(collector.collect_forever(PIPELINE_POLL_SECONDS)) if collector else None
        yield
        if polling:
            polling.cancel()

    return lifespan


if __name__ == "__main__":
    main()
