"""Ask every TriviaBench question through the harness service, the way Home Assistant asks it, and write one JSONL file per candidate.

Each question carries the set's search instruction, so the run measures the model with its search tools: the point is to see how far the search
tool server can lift a small local model, not what the model remembers. Results append as they arrive, so an interrupted run resumes where it stopped.
"""

import argparse
import asyncio
import json
import signal
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console

from assistant_core.harness_client import HarnessClient
from assistant_core.models import Message, Role
from benchmark.records import Candidate, append_jsonl, load_config, read_jsonl
from benchmark.run import CONFIG_PATH, harness_client, harness_exchange, run_command
from benchmark.triviabench.records import TriviaQuestion, TriviaResult, TriviaSet, TriviaSize, load_trivia_set

TRIVIA_SET_PATH = Path("benchmark/triviabench/questions.yaml")
console = Console()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run TriviaBench through the harness service.")
    parser.add_argument("--size", choices=[size.value for size in TriviaSize], default=TriviaSize.XS.value, help="xs: 100 questions; s: 1,000 questions (xs included)")
    parser.add_argument("--candidate", required=True, help="a harness candidate key from benchmark/config.yaml; the harness must be serving its model")
    parser.add_argument("--run", required=True, help="results folder name under benchmark/results; TriviaBench writes into its triviabench/ subfolder")
    parser.add_argument("--force", action="store_true", help="discard this candidate's earlier results in the run and ask every question again")
    return parser.parse_args()


def main() -> None:
    # A plain SIGTERM would kill this process mid-write; exiting through Python lets the last result line finish.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    load_dotenv(Path(".env"))
    asyncio.run(main_async(parse_args()))


async def main_async(args: argparse.Namespace) -> None:
    config = load_config(CONFIG_PATH)
    candidate = harness_candidate(config.candidate(args.candidate))
    trivia_set = load_trivia_set(TRIVIA_SET_PATH)
    output_dir = Path(config.services.results_dir) / args.run / "triviabench"
    output_path = output_dir / f"{candidate.key}.jsonl"
    pending = pending_questions(trivia_set.of_size(TriviaSize(args.size)), output_path, args.force)
    write_run_metadata(output_dir, trivia_set)
    client = await healthy_harness_client(candidate)
    console.rule(f"TriviaBench {args.size.upper()}: {candidate.label}  ({len(pending)} questions to ask)")
    for question in pending:
        result = await ask_question(client, candidate, trivia_set, question)
        append_jsonl(output_path, result)
        print_result_line(question, result)


def harness_candidate(candidate: Candidate) -> Candidate:
    if candidate.provider != "harness":
        raise SystemExit(f"{candidate.key} is a {candidate.provider} candidate; TriviaBench asks through the harness service, so pick a provider: harness candidate")
    return candidate


def pending_questions(questions: list[TriviaQuestion], output_path: Path, force: bool) -> list[TriviaQuestion]:
    if force:
        output_path.unlink(missing_ok=True)
        return questions
    answered_ids = {result.question_id for result in read_jsonl(output_path, TriviaResult) if result.error is None}
    return [question for question in questions if question.id not in answered_ids]


def write_run_metadata(output_dir: Path, trivia_set: TriviaSet) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = {"question_set_version": trivia_set.version, "search_instruction": trivia_set.search_instruction, "git_commit": run_command(["git", "rev-parse", "--short", "HEAD"])}
    (output_dir / "run_meta.json").write_text(json.dumps(metadata, indent=2))


async def healthy_harness_client(candidate: Candidate) -> HarnessClient:
    client = harness_client(candidate)
    health = await client.health()
    if health.status != "ok":
        raise SystemExit(f"the harness reports {health.model_dump()}; start it with scripts/services.sh install")
    return client


async def ask_question(client: HarnessClient, candidate: Candidate, trivia_set: TriviaSet, question: TriviaQuestion) -> TriviaResult:
    """One conversation per question, so no answer leans on an earlier one. A failed question is recorded with its error and asked again on the next run."""
    conversation_id = f"triviabench-{candidate.key}-{question.id}-{uuid.uuid4().hex[:8]}"
    run_exchange = harness_exchange(client, conversation_id)
    try:
        transcript = await run_exchange([Message(role=Role.USER, content=trivia_set.spoken_question(question))])
    except Exception as error:
        return TriviaResult(question_id=question.id, candidate_key=candidate.key, model=candidate.model, error=f"{type(error).__name__}: {error}")
    return TriviaResult(question_id=question.id, candidate_key=candidate.key, model=candidate.model, transcript=transcript)


def print_result_line(question: TriviaQuestion, result: TriviaResult) -> None:
    if result.error:
        console.print(f"  {question.id} [red]error[/red] {result.error}")
        return
    searched = f"searched {len(result.search_queries)}x" if result.searched else "no search"
    console.print(f"  {question.id} {searched:<12} total={result.transcript.total_seconds:.1f}s  {result.answer[:100]}")


if __name__ == "__main__":
    main()
