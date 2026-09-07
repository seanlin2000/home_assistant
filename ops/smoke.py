"""The smoke test the laptop runs after a deploy (design doc 10 §3.8): one calculator question through Home Assistant's conversation API.

    uv run python -m ops.smoke            # "What is 12 percent of 250?" must come back with 30 within 60 s
    uv run python -m ops.smoke --full     # also one searched question, which needs SearXNG and the web

That single call exercises Home Assistant, the component, Ollama, and the tool server; the plain version never touches the web, so it is
safe to run as often as needed. Exit code 0 on pass, 1 on fail, with the answer printed either way.
"""

import argparse
import asyncio
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from ops.ha_client import HomeAssistant, conversation_entity_id, converse, wait_for_api

PROJECT_DIR = Path(__file__).resolve().parent.parent
CALCULATOR_QUESTION = "What is 12 percent of 250?"
CALCULATOR_EXPECTED = re.compile(r"\b(30|thirty)\b", re.IGNORECASE)
SEARCH_QUESTION = "Search the web: what is the latest stable version of Home Assistant?"
SEARCH_EXPECTED = re.compile(r"\b20\d\d\b")  # any year-style version number proves a search happened and was read


async def smoke(ha: HomeAssistant, timeout_seconds: float, full: bool) -> list[tuple[str, bool, str, float]]:
    await wait_for_api(ha, timeout_seconds=300, ok_statuses=(200,), poll_seconds=5)
    agent = await conversation_entity_id(ha)
    questions = [(CALCULATOR_QUESTION, CALCULATOR_EXPECTED)] + ([(SEARCH_QUESTION, SEARCH_EXPECTED)] if full else [])
    results = []
    for question, expected in questions:
        started = time.monotonic()
        try:
            answer = await converse(ha, question, agent, timeout_seconds=timeout_seconds)
        except Exception as error:  # noqa: BLE001 - the smoke test reports, it does not crash
            answer = f"<{type(error).__name__}: {error}>"
        elapsed = time.monotonic() - started
        results.append((question, bool(expected.search(answer)), answer, elapsed))
    return results


def main(argv: list[str] | None = None) -> int:
    load_dotenv(PROJECT_DIR / ".env")
    parser = argparse.ArgumentParser(description="Ask Home Assistant one calculator question and check the answer.")
    parser.add_argument("--full", action="store_true", help="add one searched question")
    parser.add_argument("--timeout", type=float, default=60.0, help="seconds to wait for each answer (default 60)")
    parser.add_argument("--host", default=os.environ.get("HA_HOST"), help="Home Assistant host (default HA_HOST from .env)")
    args = parser.parse_args(argv)
    if not args.host:
        print("HA_HOST is not set", file=sys.stderr)
        return 2
    ha = HomeAssistant(args.host, os.environ.get("HA_TOKEN", ""), os.environ.get("HA_BASE"))
    try:
        results = asyncio.run(run(ha, args.timeout, args.full))
    except Exception as error:  # noqa: BLE001
        print(f"smoke: FAIL before asking anything: {type(error).__name__}: {error}")
        return 1
    passed = all(ok for _, ok, _, _ in results)
    for question, ok, answer, elapsed in results:
        print(f"smoke: {'pass' if ok else 'FAIL'} {elapsed:5.1f}s  {question!r} -> {answer!r}")
    return 0 if passed else 1


async def run(ha: HomeAssistant, timeout_seconds: float, full: bool):
    try:
        return await smoke(ha, timeout_seconds, full)
    finally:
        await ha.close()


if __name__ == "__main__":
    sys.exit(main())
