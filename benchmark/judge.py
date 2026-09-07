"""Score every transcript in a results folder with a frontier model, using the rubric text verbatim as the judge's instructions.

Two ways to reach the judge. `--export` writes each pending case to results/<date>/judge_cases/<candidate>/<qid>.md and a manifest, so a Claude Code
subagent (see .claude/agents/benchmark-judge.md) can grade them on the user's subscription and write <qid>.verdict.json next to each; `--import` turns
those verdict files into scores. Without either flag the judge is called through the Anthropic API, which costs money and is kept for reference.
"""

import argparse
import asyncio
import json
from collections.abc import Callable
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from rich.console import Console

from assistant_core.models import Message, Transcript
from benchmark.costs import estimate_cost_usd
from benchmark.gates import harness_gates
from benchmark.records import BenchmarkConfig, Gate, JudgeConfig, JudgeVerdict, Question, QuestionResult, Score, load_config, load_questions, read_jsonl, write_jsonl

CONFIG_PATH = Path("benchmark/config.yaml")
QUESTIONS_PATH = Path("benchmark/questions.yaml")
RUBRIC_PATH = Path("benchmark/rubric.md")
JUDGE_MAX_TOKENS = 4000
SUBAGENT_JUDGE_LABEL = "claude-opus-5 (Claude Code subagent)"
console = Console()

SCORE_RANGES = {"answer_quality": (0, 5), "judgment": (0, 3), "spoken_fit": (0, 2)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Judge benchmark transcripts.")
    parser.add_argument("run", help="results folder name under benchmark/results (version_1, version_2, ...)")
    parser.add_argument("--candidate", action="append", help="candidate key; repeatable; default every results file in the folder")
    parser.add_argument("--force", action="store_true", help="re-judge questions that already have a score")
    parser.add_argument("--export", action="store_true", help="write pending cases to judge_cases/ for a subagent instead of calling the API")
    parser.add_argument("--import", dest="import_verdicts", action="store_true", help="read <qid>.verdict.json files written by the subagent and score them")
    parser.add_argument("--judge-label", default=SUBAGENT_JUDGE_LABEL, help="judge_model recorded for imported verdicts")
    return parser.parse_args()


def main() -> None:
    load_dotenv(Path(".env"))
    asyncio.run(main_async(parse_args()))


async def main_async(args: argparse.Namespace) -> None:
    config = load_config(CONFIG_PATH)
    question_set = load_questions(QUESTIONS_PATH)
    run_dir = Path(config.services.results_dir) / args.run
    rubric = RUBRIC_PATH.read_text()
    if args.export:
        for results_path in results_files(run_dir, args.candidate):
            export_cases(results_path, question_set.by_id, config, rubric, args.force)
        return
    if args.import_verdicts:
        for results_path in results_files(run_dir, args.candidate):
            import_verdicts(results_path, question_set.by_id, config, args.judge_label)
        return
    client = anthropic.AsyncAnthropic()
    semaphore = asyncio.Semaphore(config.judge.concurrency)
    for results_path in results_files(run_dir, args.candidate):
        await judge_candidate(results_path, question_set.by_id, config, rubric, client, semaphore, args.force)


def results_files(run_dir: Path, candidate_keys: list[str] | None) -> list[Path]:
    if candidate_keys:
        return [run_dir / f"{key}.jsonl" for key in candidate_keys]
    return sorted(path for path in run_dir.glob("*.jsonl") if not path.name.endswith(".scores.jsonl"))


async def judge_candidate(
    results_path: Path, question_lookup: Callable[[str], Question], config: BenchmarkConfig, rubric: str, client: anthropic.AsyncAnthropic, semaphore: asyncio.Semaphore, force: bool
) -> None:
    scores_path = results_path.with_suffix(".scores.jsonl")
    results = read_jsonl(results_path, QuestionResult)
    existing = {} if force else {score.question_id: score for score in read_jsonl(scores_path, Score)}
    pending = [result for result in results if result.question_id not in existing]
    console.print(f"{results_path.stem}: judging {len(pending)} of {len(results)}")
    new_scores = await asyncio.gather(*(judge_one(question_lookup(result.question_id), result, config, rubric, client, semaphore) for result in pending))
    merged = {**existing, **{score.question_id: score for score in new_scores}}
    write_jsonl(scores_path, [merged[result.question_id] for result in results if result.question_id in merged])
    print_spend(new_scores)


def print_spend(scores: list[Score]) -> None:
    input_tokens = sum(score.judge_input_tokens for score in scores)
    output_tokens = sum(score.judge_output_tokens for score in scores)
    console.print(f"  judge usage: {input_tokens} in / {output_tokens} out, about ${estimate_cost_usd(input_tokens, output_tokens):.2f}")


async def judge_one(question: Question, result: QuestionResult, config: BenchmarkConfig, rubric: str, client: anthropic.AsyncAnthropic, semaphore: asyncio.Semaphore) -> Score:
    gates = harness_gates(question, result, config.policy.max_tool_rounds)
    if Gate.RUN_ERROR in gates:
        return Score(question_id=question.id, candidate_key=result.candidate_key, category=question.category, harness_gates=gates, judge=None, judge_error=result.error)
    async with semaphore:
        try:
            verdict, judge_model, usage = await ask_judge(client, config.judge, rubric, render_case(question, result, gates))
            return Score(
                question_id=question.id,
                candidate_key=result.candidate_key,
                category=question.category,
                harness_gates=gates,
                judge=verdict,
                judge_model=judge_model,
                judge_input_tokens=usage[0],
                judge_output_tokens=usage[1],
            )
        except (anthropic.APIError, ValueError) as error:
            return Score(question_id=question.id, candidate_key=result.candidate_key, category=question.category, harness_gates=gates, judge=None, judge_error=f"{type(error).__name__}: {error}")


async def ask_judge(client: anthropic.AsyncAnthropic, judge_config: JudgeConfig, rubric: str, case_text: str) -> tuple[JudgeVerdict, str, tuple[int, int]]:
    response = await client.messages.parse(
        model=judge_config.model,
        max_tokens=JUDGE_MAX_TOKENS,
        system=rubric,
        messages=[{"role": "user", "content": case_text}],
        output_format=JudgeVerdict,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise ValueError(f"judge returned no verdict (stop_reason={response.stop_reason})")
    return validate_ranges(response.parsed_output), response.model, (response.usage.input_tokens, response.usage.output_tokens)


def validate_ranges(verdict: JudgeVerdict) -> JudgeVerdict:
    for field, (low, high) in SCORE_RANGES.items():
        value = getattr(verdict, field)
        if not low <= value <= high:
            raise ValueError(f"judge score {field}={value} outside {low}..{high}")
    return verdict


def pending_results(results_path: Path, force: bool) -> tuple[list[QuestionResult], dict[str, Score]]:
    scores_path = results_path.with_suffix(".scores.jsonl")
    results = read_jsonl(results_path, QuestionResult)
    existing = {} if force else {score.question_id: score for score in read_jsonl(scores_path, Score)}
    return [result for result in results if result.question_id not in existing], existing


def cases_dir(results_path: Path) -> Path:
    return results_path.parent / "judge_cases" / results_path.stem


def export_cases(results_path: Path, question_lookup: Callable[[str], Question], config: BenchmarkConfig, rubric: str, force: bool) -> None:
    """One markdown file per pending case, the rubric alongside, and a manifest the subagent walks."""
    pending, _ = pending_results(results_path, force)
    folder = cases_dir(results_path)
    folder.mkdir(parents=True, exist_ok=True)
    (folder.parent / "rubric.md").write_text(rubric)
    manifest = []
    for result in pending:
        question = question_lookup(result.question_id)
        gates = harness_gates(question, result, config.policy.max_tool_rounds)
        if Gate.RUN_ERROR in gates:
            continue
        case_path = folder / f"{result.question_id}.md"
        case_path.write_text(render_case(question, result, gates))
        manifest.append({"question_id": result.question_id, "case": str(case_path), "verdict": str(folder / f"{result.question_id}.verdict.json")})
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2))
    console.print(f"{results_path.stem}: exported {len(manifest)} cases to {folder}")


def import_verdicts(results_path: Path, question_lookup: Callable[[str], Question], config: BenchmarkConfig, judge_label: str) -> None:
    """Turn the subagent's verdict files into scores; anything missing or malformed is reported and left unscored."""
    pending, existing = pending_results(results_path, force=False)
    folder = cases_dir(results_path)
    imported: dict[str, Score] = {}
    problems: list[str] = []
    for result in pending:
        question = question_lookup(result.question_id)
        gates = harness_gates(question, result, config.policy.max_tool_rounds)
        if Gate.RUN_ERROR in gates:
            imported[result.question_id] = Score(question_id=question.id, candidate_key=result.candidate_key, category=question.category, harness_gates=gates, judge=None, judge_error=result.error)
            continue
        verdict_path = folder / f"{result.question_id}.verdict.json"
        try:
            verdict = validate_ranges(JudgeVerdict.model_validate_json(verdict_path.read_text()))
        except (OSError, ValueError) as error:
            problems.append(f"{result.question_id}: {type(error).__name__}: {str(error)[:120]}")
            continue
        imported[result.question_id] = Score(question_id=question.id, candidate_key=result.candidate_key, category=question.category, harness_gates=gates, judge=verdict, judge_model=judge_label)
    merged = {**existing, **imported}
    results = read_jsonl(results_path, QuestionResult)
    write_jsonl(results_path.with_suffix(".scores.jsonl"), [merged[result.question_id] for result in results if result.question_id in merged])
    console.print(f"{results_path.stem}: imported {len(imported)} verdicts" + (f"; {len(problems)} problems: {problems}" if problems else ""))


def render_case(question: Question, result: QuestionResult, gates: list[Gate]) -> str:
    sections = [render_question(question), *(render_turn(index, transcript) for index, transcript in enumerate(result.turns, start=1)), render_harness_notes(result, gates)]
    return "\n\n".join(sections)


def render_question(question: Question) -> str:
    lines = [
        f"# Question {question.id} (category {question.category.value})",
        f"What it tests: {question.tests}",
        f"Expected search behavior: {question.expected_search}",
        f"Constraints: {question.constraints.model_dump(exclude_defaults=True) or 'none'}",
        f"Gates especially relevant here: {', '.join(gate.value for gate in question.gates_for_judge) or 'none beyond the general rules'}",
    ]
    if question.reference_sketch:
        lines.append(f"\nReference sketch (what a correct answer must contain):\n{question.reference_sketch.strip()}")
    return "\n".join(lines)


def render_turn(index: int, transcript: Transcript) -> str:
    parts = [f"# Turn {index}"]
    for message in transcript.conversation:
        parts.append(render_message(message))
    if transcript.truncated:
        parts.append(f"[Spoken output was cut by the word cap. The listener heard:]\n{transcript.spoken_text}")
    return "\n\n".join(parts)


def render_message(message: Message) -> str:
    if message.role.value == "user":
        return f"USER: {message.content}"
    if message.role.value == "tool":
        return f"TOOL RESULT for {message.tool_name}:\n{message.content}"
    calls = "".join(f"\nTOOL CALL {call.name}({call.arguments})" for call in message.tool_calls)
    return f"ASSISTANT: {message.content}{calls}"


def render_harness_notes(result: QuestionResult, gates: list[Gate]) -> str:
    return "\n".join(
        [
            "# Harness observations",
            f"Searched: {'yes' if result.searched else 'no'}; tool calls: {result.tool_call_count}; calculator calls: {result.calculator_call_count}",
            render_route_note(result),
            f"Harness gates already applied: {', '.join(gate.value for gate in gates) or 'none'}",
            "Grade the final ASSISTANT message of the last turn as the answer. Return the structured verdict.",
        ]
    )


def render_route_note(result: QuestionResult) -> str:
    decision = result.route
    if decision is None:
        return "Router: not run"
    return f"Router decided '{decision.route.value}' by {decision.source} ({decision.detail})"


if __name__ == "__main__":
    main()
