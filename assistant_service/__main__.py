"""Run the harness: `uv run assistant-service`, which scripts/services.sh's launchd agent does (design doc v2/10 section 3.1)."""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import uvicorn
from starlette.applications import Starlette

from assistant_core.llama_server_client import LlamaServerClient
from assistant_service.app import AccessRules, build_app
from assistant_service.conversation_state import ConversationState
from assistant_service.exchange_log import ExchangeLog
from assistant_service.harness import SECONDS_PER_MINUTE, Harness
from assistant_service.settings import HarnessConfig, load_harness_config
from ops import paths
from serving.settings import ServingConfig, load_serving_config, read_api_key

_LOGGER = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = load_harness_config()
    serving = load_serving_config()
    harness = build_harness(config, serving)
    access = AccessRules(api_key=read_api_key(config.service.api_key_path), allowed_hosts=config.allowed_hosts())
    app = build_app(harness, access, lifespan=lifespan_for(harness))
    uvicorn.run(app, host=config.service.host, port=config.service.port, log_level="info")


def build_harness(config: HarnessConfig, serving: ServingConfig) -> Harness:
    llm = LlamaServerClient(serving.server.base_url, read_api_key(serving.server.api_key_path), serving.server.model)
    return Harness(
        llm=llm,
        tool_server_url=config.service.tool_server_url,
        policy=config.policy(serving),
        state=ConversationState(config.service.state_path),
        exchange_log=ExchangeLog(paths.exchanges_dir()),
        quiet_minutes=config.service.conversation_quiet_minutes,
    )


def lifespan_for(harness: Harness) -> Callable[[Starlette], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        await harness.warm_up()
        housekeeping = asyncio.create_task(check_in_every_minute(harness))
        yield
        housekeeping.cancel()

    return lifespan


async def check_in_every_minute(harness: Harness) -> None:
    while True:
        await asyncio.sleep(SECONDS_PER_MINUTE)
        try:
            await harness.check_in()
        except Exception:  # housekeeping must never stop the service answering questions
            _LOGGER.exception("housekeeping failed")


if __name__ == "__main__":
    main()
