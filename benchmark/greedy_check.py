"""Greedy answers to fixed prompts, so runs of one engine can be compared word for word: the Strata release experiment asks whether giving back the
host code's weight copies changes any answer. Each call appends its answers to greedy_check.jsonl in the run's folder and prints them with their
timings; --compare-to names an earlier label and exits 1 when any answer differs from that label's."""

import argparse
import asyncio
import sys
from pathlib import Path

from pydantic import BaseModel

from assistant_core.llama_server_client import LlamaServerClient
from assistant_core.models import AgentPolicy, ToolCall, ToolSpec
from assistant_core.tools import McpToolBox
from benchmark.engine_probe import CONFIG_PATH, DECODE_QUESTION, PADDING_REPEATS, PADDING_SENTENCE, SHORT_QUESTION, completion, decode_rate, plain_prompt
from benchmark.mcp_process import McpServerProcess
from benchmark.records import append_jsonl, load_config, read_jsonl
from serving.settings import read_api_key

PROMPTS = {
    "short": SHORT_QUESTION,
    "story": DECODE_QUESTION,
    "long": PADDING_SENTENCE * PADDING_REPEATS + SHORT_QUESTION,
    "weather": "Will it rain in Paris tomorrow?",
}
GREEDY_POLICY = AgentPolicy(temperature=0, max_output_tokens=160, think=False)


class GreedyAnswer(BaseModel):
    label: str
    prompt_name: str
    text: str
    tool_calls: list[ToolCall]
    prompt_tokens: int
    time_to_first_token_seconds: float | None
    total_seconds: float
    decode_rate: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Greedy answers to fixed prompts, compared word for word with an earlier run's.")
    parser.add_argument("--base-url", required=True, help="e.g. http://127.0.0.1:8090")
    parser.add_argument("--api-key-file", type=Path, required=True)
    parser.add_argument("--label", required=True, help="this run's name, e.g. off-1")
    parser.add_argument("--run", required=True, help="results folder under benchmark/results")
    parser.add_argument("--prompts", nargs="+", choices=list(PROMPTS), default=list(PROMPTS))
    parser.add_argument("--compare-to", help="an earlier label in the same run; exit 1 when an answer differs from it")
    return parser.parse_args()


def main() -> None:
    sys.exit(asyncio.run(check(parse_args())))


async def check(args: argparse.Namespace) -> int:
    config = load_config(CONFIG_PATH)
    run_dir = Path(config.services.results_dir) / args.run
    client = LlamaServerClient(args.base_url, read_api_key(args.api_key_file.expanduser()), args.label)
    async with McpServerProcess(config.services, run_dir / "cache") as mcp_url, McpToolBox(mcp_url) as toolbox:
        tools = await toolbox.list_tools()
        answers = [await greedy_answer(client, tools, args.label, name) for name in args.prompts]
    earlier = read_jsonl(run_dir / "greedy_check.jsonl", GreedyAnswer) if args.compare_to else []
    for answer in answers:
        append_jsonl(run_dir / "greedy_check.jsonl", answer)
        print(f"{answer.prompt_name}: {answer.total_seconds:.2f} s, first token {answer.time_to_first_token_seconds}, {answer.decode_rate:.1f} tok/s: {answer.text[:80]!r}")
    if not args.compare_to:
        return 0
    differing = differing_prompts(answers, [answer for answer in earlier if answer.label == args.compare_to])
    print(f"differ from {args.compare_to}: {', '.join(differing) or 'none'}")
    return 1 if differing else 0


async def greedy_answer(client: LlamaServerClient, tools: list[ToolSpec], label: str, prompt_name: str) -> GreedyAnswer:
    result = await completion(client, plain_prompt(PROMPTS[prompt_name]), tools, GREEDY_POLICY)
    return GreedyAnswer(
        label=label,
        prompt_name=prompt_name,
        text=result.message.content,
        tool_calls=result.message.tool_calls,
        prompt_tokens=result.stats.prompt_tokens or 0,
        time_to_first_token_seconds=result.stats.time_to_first_token_seconds,
        total_seconds=result.stats.total_seconds,
        decode_rate=decode_rate(result.stats),
    )


def differing_prompts(answers: list[GreedyAnswer], reference: list[GreedyAnswer]) -> list[str]:
    """The prompts whose answer is not the reference's, word for word and call for call; a prompt the reference never answered differs too.
    Tool call ids are left out: the engine makes up a new one each time."""
    reference_by_prompt = {answer.prompt_name: answer for answer in reference}
    return [answer.prompt_name for answer in answers if answer_content(answer) != answer_content(reference_by_prompt.get(answer.prompt_name))]


def answer_content(answer: GreedyAnswer | None) -> tuple[str, list[tuple[str, dict]]] | None:
    if answer is None:
        return None
    return answer.text, [(call.name, call.arguments) for call in answer.tool_calls]
