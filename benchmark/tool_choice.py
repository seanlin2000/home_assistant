"""Check which tool a candidate calls first for short spoken questions, without running any tool: one model call per question and attempt, with the
harness's own system prompt, per-question note and offered tools. A wrong first pick is what sends a restaurant question to the web instead of the
restaurant tool, so this measures tool descriptions in minutes, with no judge."""

import argparse
import asyncio
import statistics
from collections import Counter
from datetime import date
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel

from assistant_core.llm_client import LLMClient
from assistant_core.models import AgentPolicy, Completion, MalformedToolCall, Message, Role, ToolCallRequest
from assistant_core.prompts import per_question_block, question_with_block, system_prompt
from assistant_core.tool_guards import GuardedToolBox, load_tool_table
from assistant_core.tools import McpToolBox
from benchmark.mcp_process import McpServerProcess
from benchmark.records import Candidate, append_jsonl, load_config
from benchmark.run import CONFIG_PATH, candidate_policy, llama_server_client

CHECKS_PATH = Path("benchmark/tool_choice.yaml")
ANSWER_DIRECTLY = "answer"
MALFORMED_CALL = "malformed call"


class ToolChoiceCheck(BaseModel):
    id: str
    question: str
    expected: list[str]  # first calls that are right; "answer" means no tool call


class FirstMove(BaseModel):
    check_id: str
    candidate_key: str
    attempt: int
    first_call: str
    arguments: dict
    correct: bool
    calls_in_first_turn: int
    thinking_tokens: int | None
    output_tokens: int | None
    stop_reason: str | None
    seconds: float
    thinking: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check which tool each candidate calls first, without running the tools.")
    parser.add_argument("--candidate", action="append", required=True, help="llama-server candidate key from config.yaml; repeatable")
    parser.add_argument("--run", required=True, help="results folder name under benchmark/results")
    parser.add_argument("--attempts", type=int, default=2, help="model calls per question")
    return parser.parse_args()


def main() -> None:
    load_dotenv(Path(".env"))
    asyncio.run(main_async(parse_args()))


async def main_async(args: argparse.Namespace) -> None:
    config = load_config(CONFIG_PATH)
    checks = load_checks(CHECKS_PATH)
    run_dir = Path(config.services.results_dir) / args.run
    async with McpServerProcess(config.services, run_dir / "cache") as mcp_url, McpToolBox(mcp_url) as toolbox:
        for key in args.candidate:
            await check_candidate(config.candidate(key), candidate_policy(config.candidate(key), config), checks, toolbox, run_dir, args.attempts)


def load_checks(path: Path) -> list[ToolChoiceCheck]:
    return [ToolChoiceCheck.model_validate(entry) for entry in yaml.safe_load(path.read_text())["checks"]]


async def check_candidate(candidate: Candidate, policy: AgentPolicy, checks: list[ToolChoiceCheck], toolbox: McpToolBox, run_dir: Path, attempts: int) -> None:
    llm = llama_server_client(candidate)
    output_path = run_dir / f"{candidate.key}.tool_choice.jsonl"
    moves = []
    for check in checks:
        for attempt in range(1, attempts + 1):
            move = await first_move(llm, toolbox, policy, check, candidate.key, attempt)
            append_jsonl(output_path, move)
            moves.append(move)
            print(f"  {candidate.key} {check.id} #{attempt}: {move.first_call} {'ok' if move.correct else 'WRONG, expected ' + ' or '.join(check.expected)}", flush=True)
    print_summary(candidate.key, moves)


async def first_move(llm: LLMClient, toolbox: McpToolBox, policy: AgentPolicy, check: ToolChoiceCheck, candidate_key: str, attempt: int) -> FirstMove:
    """The model's first turn for the question as the harness would send it, with the tools the harness would offer for it."""
    offered = await GuardedToolBox(toolbox, load_tool_table(), [Message(role=Role.USER, content=check.question)]).list_tools()
    question = question_with_block(check.question, per_question_block(date.today(), check.question))
    messages = [Message(role=Role.SYSTEM, content=system_prompt()), Message(role=Role.USER, content=question)]
    calls, malformed, completion = [], False, None
    async for event in llm.chat(messages, offered, policy):
        if isinstance(event, ToolCallRequest):
            calls.append(event.call)
        elif isinstance(event, MalformedToolCall):
            malformed = True
        elif isinstance(event, Completion):
            completion = event
    first_call = calls[0].name if calls else (MALFORMED_CALL if malformed else ANSWER_DIRECTLY)
    stats = completion.stats if completion else None
    return FirstMove(
        check_id=check.id,
        candidate_key=candidate_key,
        attempt=attempt,
        first_call=first_call,
        arguments=calls[0].arguments if calls else {},
        correct=first_call in check.expected,
        calls_in_first_turn=len(calls),
        thinking_tokens=stats.thinking_tokens if stats else None,
        output_tokens=stats.output_tokens if stats else None,
        stop_reason=stats.stop_reason if stats else None,
        seconds=round(stats.total_seconds, 1) if stats else 0.0,
        thinking=completion.message.thinking if completion else "",
    )


def print_summary(candidate_key: str, moves: list[FirstMove]) -> None:
    correct = sum(move.correct for move in moves)
    thinking = [move.thinking_tokens for move in moves if move.thinking_tokens is not None]
    wrong = Counter(f"{move.check_id} -> {move.first_call}" for move in moves if not move.correct)
    print(f"== {candidate_key}: {correct}/{len(moves)} first calls right; mean thinking tokens {statistics.fmean(thinking) if thinking else 0:.0f}")
    for pick, count in wrong.most_common():
        print(f"   wrong: {pick} (x{count})")


if __name__ == "__main__":
    main()
