"""Run every selected question through every selected candidate and write one JSONL file per candidate under results/<date>/."""

import argparse
import asyncio
import json
import platform
import signal
import subprocess
import sys
from pathlib import Path

import httpx
import ollama
from dotenv import load_dotenv
from rich.console import Console

from assistant_core import agent_loop
from assistant_core.llm_client import LLMClient, OllamaClient
from assistant_core.models import AgentPolicy, Done, Message, Role, Transcript
from assistant_core.prompts import PROMPT_VERSION
from assistant_core.tools import McpToolBox
from benchmark.mcp_process import McpServerProcess
from benchmark.ollama_utils import delete_model, ensure_model_present, unload, warm_up
from benchmark.records import BenchmarkConfig, Candidate, MemoryFit, Question, QuestionResult, QuestionSet, append_jsonl, load_config, load_questions, read_jsonl

CONFIG_PATH = Path("benchmark/config.yaml")
QUESTIONS_PATH = Path("benchmark/questions.yaml")
console = Console()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the LLM benchmark.")
    parser.add_argument("--candidate", action="append", help="candidate key from config.yaml; repeatable; default all")
    parser.add_argument("--question", action="append", help="question id; repeatable; default all")
    parser.add_argument("--run", required=True, help="results folder name under benchmark/results, one per pass of the agent: version_1, version_2, ...")
    parser.add_argument("--force", action="store_true", help="re-run questions that already have a result")
    parser.add_argument("--delete-models", action="store_true", help="delete each Ollama model after its run to save disk")
    return parser.parse_args()


def main() -> None:
    # A plain SIGTERM would kill this process without unwinding the context managers, leaving the MCP child alive on its port.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    load_dotenv(Path(".env"))
    asyncio.run(main_async(parse_args()))


async def main_async(args: argparse.Namespace) -> None:
    config = load_config(CONFIG_PATH)
    question_set = load_questions(QUESTIONS_PATH)
    run_dir = Path(config.services.results_dir) / args.run
    candidates = [config.candidate(key) for key in args.candidate] if args.candidate else config.candidates
    questions = [question_set.by_id(qid) for qid in args.question] if args.question else question_set.questions
    await ensure_searxng(config.services.searxng_url)
    async with McpServerProcess(config.services, run_dir / "cache") as mcp_url:
        write_run_metadata(run_dir, config, question_set)
        for candidate in candidates:
            await run_candidate(candidate, questions, config, mcp_url, run_dir, args)


async def ensure_searxng(searxng_url: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{searxng_url}/search", params={"q": "ping", "format": "json"})
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise SystemExit(f"SearXNG is not answering at {searxng_url} ({error}). Start it with scripts/searxng.sh up.") from error


def write_run_metadata(run_dir: Path, config: BenchmarkConfig, question_set: QuestionSet) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "question_set_version": question_set.version,
        "prompt_version": PROMPT_VERSION,
        "policy": config.policy.model_dump(),
        "candidates": [candidate.model_dump() for candidate in config.candidates],
        "machine": platform.platform(),
        "chip": run_command(["sysctl", "-n", "machdep.cpu.brand_string"]),
        "memory_bytes": run_command(["sysctl", "-n", "hw.memsize"]),
        "ollama_version": run_command(["ollama", "--version"]),
        "git_commit": run_command(["git", "rev-parse", "--short", "HEAD"]),
    }
    (run_dir / "run_meta.json").write_text(json.dumps(metadata, indent=2))


def run_command(command: list[str]) -> str:
    try:
        return subprocess.run(command, capture_output=True, text=True, check=False).stdout.strip()
    except OSError:
        return ""


async def run_candidate(candidate: Candidate, questions: list[Question], config: BenchmarkConfig, mcp_url: str, run_dir: Path, args: argparse.Namespace) -> None:
    output_path = run_dir / f"{candidate.key}.jsonl"
    pending = pending_questions(questions, output_path, args.force)
    if not pending:
        console.print(f"[dim]{candidate.key}: nothing to do[/dim]")
        return
    console.rule(f"{candidate.label}  ({len(pending)} questions)")
    llm = build_llm(candidate, config)
    if llm is None:
        return
    memory_fit = await prepare_model(candidate, config)
    policy = config.policy.model_copy(update={"think": candidate.think})
    async with McpToolBox(mcp_url) as toolbox:
        for question in pending:
            result = await run_question(question, candidate, llm, toolbox, policy, memory_fit)
            append_jsonl(output_path, result)
            print_result_line(question, result)
    await release_model(candidate, config, args.delete_models)


def pending_questions(questions: list[Question], output_path: Path, force: bool) -> list[Question]:
    if force:
        output_path.unlink(missing_ok=True)
        return questions
    done_ids = {result.question_id for result in read_jsonl(output_path, QuestionResult)}
    return [question for question in questions if question.id not in done_ids]


def build_llm(candidate: Candidate, config: BenchmarkConfig) -> LLMClient | None:
    if candidate.provider == "manual":
        console.print(f"[dim]Skipping {candidate.key}: manual candidates are produced by benchmark-manual, not run.[/dim]")
        return None
    return OllamaClient(candidate.model, host=config.services.ollama_host)


async def prepare_model(candidate: Candidate, config: BenchmarkConfig) -> MemoryFit:
    if candidate.provider != "ollama":
        return MemoryFit()
    client = ollama.AsyncClient(host=config.services.ollama_host)
    await ensure_model_present(client, candidate.model)
    fit = await warm_up(client, candidate.model, config.policy.context_tokens)
    if fit.fully_on_gpu is False:
        console.print(f"[yellow]{candidate.model} is not fully resident on the GPU ({fit.gpu_resident_bytes} of {fit.model_size_bytes} bytes); latency will be misleading.[/yellow]")
    return fit


async def release_model(candidate: Candidate, config: BenchmarkConfig, delete_after: bool) -> None:
    if candidate.provider != "ollama":
        return
    client = ollama.AsyncClient(host=config.services.ollama_host)
    await unload(client, candidate.model)
    if delete_after:
        await delete_model(client, candidate.model)


async def run_question(question: Question, candidate: Candidate, llm: LLMClient, toolbox: McpToolBox, policy: AgentPolicy, memory_fit: MemoryFit) -> QuestionResult:
    transcripts: list[Transcript] = []
    conversation: list[Message] = []
    try:
        for user_text in question.exchanges:
            conversation.append(Message(role=Role.USER, content=user_text))
            transcript = await run_exchange(conversation, llm, toolbox, policy)
            transcripts.append(transcript)
            conversation = list(transcript.conversation)
    except Exception as error:
        return QuestionResult(
            question_id=question.id,
            candidate_key=candidate.key,
            model=llm.model_name,
            exchanges=transcripts or [Transcript(model=llm.model_name, system_prompt="", conversation=conversation)],
            memory_fit=memory_fit,
            error=f"{type(error).__name__}: {error}",
        )
    return QuestionResult(question_id=question.id, candidate_key=candidate.key, model=llm.model_name, exchanges=transcripts, memory_fit=memory_fit)


async def run_exchange(conversation: list[Message], llm: LLMClient, toolbox: McpToolBox, policy: AgentPolicy) -> Transcript:
    async for event in agent_loop.run(conversation, llm, toolbox, policy):
        if isinstance(event, Done):
            return event.transcript
    raise RuntimeError("agent loop ended without a Done event")


def print_result_line(question: Question, result: QuestionResult) -> None:
    if result.error:
        console.print(f"  {question.id:<4} [red]error[/red] {result.error}")
        return
    final = result.final
    searched = "search" if result.searched else "no search"
    route = f"route={result.route.route.value}/{result.route.source}" if result.route else "route=off"
    console.print(
        f"  {question.id:<4} {searched:<9} {route:<24} calls={result.tool_call_count} ttft={final.time_to_first_token_seconds or 0:.1f}s total={final.total_seconds:.1f}s words={len(final.final_answer.split())}"
    )


if __name__ == "__main__":
    main()
