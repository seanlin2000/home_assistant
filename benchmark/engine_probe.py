"""Prompt and answer speed, prompt caching, and memory of one model server, through llama-server's API, so two engines serving the same model file
compare on the same Mac (the Strata trial). Each call appends one row for its label to engine_probe.jsonl and rewrites engine_probe.md from every row."""

import argparse
import asyncio
import statistics
import uuid
from pathlib import Path

from pydantic import BaseModel

from assistant_core.llama_server_client import LlamaServerClient
from assistant_core.models import AgentPolicy, Completion, GenerationStats, Message, Role, ToolSpec
from assistant_core.prompts import system_prompt
from assistant_core.router import ROUTE_SCHEMA, ROUTER_SYSTEM_PROMPT
from assistant_core.tools import McpToolBox
from benchmark.mcp_process import McpServerProcess
from benchmark.records import append_jsonl, load_config, read_jsonl
from dashboard.memory_reader import read_memory_outputs
from dashboard.memory_views import machine_memory, running_processes
from serving.settings import read_api_key

CONFIG_PATH = Path("benchmark/config.yaml")
SHORT_QUESTION = "What is 12 percent of 250?"
FOLLOW_UP_QUESTION = "And what is 15 percent of that?"
ROUTER_QUESTION = "Will it rain tomorrow?"
# About 20 tokens each: 300 of them add roughly 6,000 tokens, so the long prompt reads about twice the real prompt
PADDING_SENTENCE = "The council reviewed the harbour budget, the ferry timetable and the library roof before adjourning for the evening. "
PADDING_REPEATS = 300
DECODE_QUESTION = "Tell me a long story about a lighthouse keeper and a stray dog, in about three hundred words."
DECODE_TOKENS = 200
CACHE_HOLDS_SHARE = 0.9
GIB = 1024**3
READ_ONLY_POLICY = AgentPolicy(temperature=0, max_output_tokens=1, think=False)
DECODE_POLICY = AgentPolicy(temperature=0, max_output_tokens=DECODE_TOKENS, think=False)
ANSWER_POLICY = AgentPolicy(temperature=0, max_output_tokens=100, think=False)


class MemorySnapshot(BaseModel):
    server_bytes: int  # top's footprint of every process with the server's name; a mapped model file's clean pages are not in it
    compressed_bytes: int
    unused_bytes: int
    swap_used_bytes: int


class ProbeResult(BaseModel):
    label: str
    short_prompt_tokens: int
    short_prefill_rates: list[float]
    long_prompt_tokens: int
    long_prefill_rates: list[float]
    decode_rates: list[float]
    first_turn_prompt_tokens: int
    cached_after_router: int
    memory_before: MemorySnapshot
    memory_after: MemorySnapshot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure one model server's prompt and answer speed, prompt caching, and memory.")
    parser.add_argument("--base-url", required=True, help="e.g. http://127.0.0.1:8092")
    parser.add_argument("--api-key-file", type=Path, required=True)
    parser.add_argument("--label", required=True, help="the row's name, e.g. strata-dflash2")
    parser.add_argument("--process-name", required=True, help="the server's executable name for its memory, e.g. llama-server or strata")
    parser.add_argument("--run", required=True, help="results folder under benchmark/results")
    parser.add_argument("--repeat", type=int, default=3)
    return parser.parse_args()


def main() -> None:
    asyncio.run(probe(parse_args()))


async def probe(args: argparse.Namespace) -> None:
    config = load_config(CONFIG_PATH)
    run_dir = Path(config.services.results_dir) / args.run
    client = LlamaServerClient(args.base_url, read_api_key(args.api_key_file.expanduser()), args.label)
    async with McpServerProcess(config.services, run_dir / "cache") as mcp_url, McpToolBox(mcp_url) as toolbox:
        result = await measure(client, await toolbox.list_tools(), args)
    append_jsonl(run_dir / "engine_probe.jsonl", result)
    (run_dir / "engine_probe.md").write_text(render_table(read_jsonl(run_dir / "engine_probe.jsonl", ProbeResult)))
    print(render_table([result]))


async def measure(client: LlamaServerClient, tools: list[ToolSpec], args: argparse.Namespace) -> ProbeResult:
    memory_before = await memory_snapshot(args.process_name)
    await completion_stats(client, fresh_prompt(SHORT_QUESTION), tools, READ_ONLY_POLICY)  # the first prompt after a load also pays for reading the file
    short = [await completion_stats(client, fresh_prompt(SHORT_QUESTION), tools, READ_ONLY_POLICY) for _ in range(args.repeat)]
    long = [await completion_stats(client, fresh_prompt(PADDING_SENTENCE * PADDING_REPEATS + SHORT_QUESTION), tools, READ_ONLY_POLICY) for _ in range(args.repeat)]
    decode = [await completion_stats(client, plain_prompt(DECODE_QUESTION), tools, DECODE_POLICY) for _ in range(args.repeat)]
    first_turn, second_turn = await cache_check(client, tools)
    return ProbeResult(
        label=args.label,
        short_prompt_tokens=short[0].prompt_tokens or 0,
        short_prefill_rates=[prefill_rate(stats) for stats in short],
        long_prompt_tokens=long[0].prompt_tokens or 0,
        long_prefill_rates=[prefill_rate(stats) for stats in long],
        decode_rates=[decode_rate(stats) for stats in decode],
        first_turn_prompt_tokens=first_turn.prompt_tokens or 0,
        cached_after_router=second_turn.cached_prompt_tokens or 0,
        memory_before=memory_before,
        memory_after=await memory_snapshot(args.process_name),
    )


def fresh_prompt(question: str) -> list[Message]:
    """A unique first line, so no part of the prompt can come from either engine's cache."""
    return [Message(role=Role.SYSTEM, content=f"Request {uuid.uuid4().hex}.\n{system_prompt()}"), Message(role=Role.USER, content=question)]


def plain_prompt(question: str) -> list[Message]:
    return [Message(role=Role.SYSTEM, content=system_prompt()), Message(role=Role.USER, content=question)]


async def cache_check(client: LlamaServerClient, tools: list[ToolSpec]) -> tuple[GenerationStats, GenerationStats]:
    """A conversation turn, a router request in between, then the conversation's next turn: the engine must still hold the conversation's prompt."""
    conversation = plain_prompt(SHORT_QUESTION)
    first_turn = await completion(client, conversation, tools, ANSWER_POLICY)
    await client.classify(ROUTER_SYSTEM_PROMPT, f"Question: {ROUTER_QUESTION}", ROUTE_SCHEMA, ANSWER_POLICY)
    second_turn = await completion_stats(client, [*conversation, first_turn.message, Message(role=Role.USER, content=FOLLOW_UP_QUESTION)], tools, ANSWER_POLICY)
    return first_turn.stats, second_turn


async def completion_stats(client: LlamaServerClient, messages: list[Message], tools: list[ToolSpec], policy: AgentPolicy) -> GenerationStats:
    return (await completion(client, messages, tools, policy)).stats


async def completion(client: LlamaServerClient, messages: list[Message], tools: list[ToolSpec], policy: AgentPolicy) -> Completion:
    async for event in client.chat(messages, tools, policy):
        if isinstance(event, Completion):
            return event
    raise RuntimeError("the server's stream ended without a completion")


def prefill_rate(stats: GenerationStats) -> float:
    return (stats.fresh_prompt_tokens or 0) / stats.prompt_eval_seconds if stats.prompt_eval_seconds else 0.0


def decode_rate(stats: GenerationStats) -> float:
    return (stats.output_tokens or 0) / stats.generation_seconds if stats.generation_seconds else 0.0


async def memory_snapshot(process_name: str) -> MemorySnapshot:
    outputs = await read_memory_outputs()
    servers = [process for process in running_processes(outputs) if Path(process.executable).name == process_name]
    machine = machine_memory(outputs, held_by_apps=0)
    return MemorySnapshot(
        server_bytes=sum(process.memory.ram_bytes + process.memory.compressed_bytes for process in servers),
        compressed_bytes=machine.compressed_bytes,
        unused_bytes=machine.unused_bytes,
        swap_used_bytes=machine.swap_used_bytes,
    )


def render_table(results: list[ProbeResult]) -> str:
    lines = [
        "# Engine probe",
        "",
        "Medians of each label's repeats. Server memory is top's footprint, which leaves out a mapped model file's clean pages.",
        "",
        "| Label | Prefill tok/s (prompt tokens) | Prefill tok/s, long (prompt tokens) | Decode tok/s | Cached after a router request | Server memory before → after | Unused after | Swap before → after |",
        "|---|---|---|---|---|---|---|---|",
    ]
    return "\n".join(lines + [table_row(result) for result in results]) + "\n"


def table_row(result: ProbeResult) -> str:
    holds = "holds" if result.cached_after_router >= CACHE_HOLDS_SHARE * result.first_turn_prompt_tokens else "LOST"
    before, after = result.memory_before, result.memory_after
    return (
        f"| {result.label} | {statistics.median(result.short_prefill_rates):.0f} ({result.short_prompt_tokens}) | {statistics.median(result.long_prefill_rates):.0f} ({result.long_prompt_tokens}) "
        f"| {statistics.median(result.decode_rates):.1f} | {result.cached_after_router} of {result.first_turn_prompt_tokens}, {holds} "
        f"| {gib(before.server_bytes)} → {gib(after.server_bytes)} | {gib(after.unused_bytes)} | {gib(before.swap_used_bytes)} → {gib(after.swap_used_bytes)} |"
    )


def gib(size_bytes: int) -> str:
    return f"{size_bytes / GIB:.1f} GiB"


if __name__ == "__main__":
    main()
