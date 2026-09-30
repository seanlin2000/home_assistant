"""Score every transcript in a results folder with the benchmark-judge Claude Code subagent, using the rubric text verbatim as the judge's instructions.

Judging is two steps around the subagent. `--export` writes each pending case to results/<run>/judge_cases/<candidate>/<qid>.md and a manifest, so the
subagent (see .claude/agents/benchmark-judge.md) can grade them on the user's subscription and write <qid>.verdict.json next to each; `--import` turns
those verdict files into scores. Judging never goes through the Anthropic API, so one of the two flags is required.
"""

import argparse
import json
from collections.abc import Callable
from pathlib import Path

from rich.console import Console

from assistant_core.models import Message, Transcript
from assistant_core.prompts import SILENCE_MARKER
from benchmark.gates import harness_gates
from benchmark.records import BenchmarkConfig, Gate, JudgeVerdict, Question, QuestionResult, Score, load_config, load_questions, read_jsonl, write_jsonl

CONFIG_PATH = Path("benchmark/config.yaml")
QUESTIONS_PATH = Path("benchmark/questions.yaml")
RUBRIC_PATH = Path("benchmark/rubric.md")
SUBAGENT_JUDGE_LABEL = "claude-opus-5 (Claude Code subagent)"
console = Console()

SCORE_RANGES = {"answer_quality": (0, 5), "judgment": (0, 3), "spoken_fit": (0, 2)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Judge benchmark transcripts through the benchmark-judge Claude Code subagent: --export the cases, run the subagent, then --import its verdicts.")
    parser.add_argument("run", help="results folder name under benchmark/results (version_1, version_2, ...)")
    parser.add_argument("--candidate", action="append", help="candidate key; repeatable; default every results file in the folder")
    parser.add_argument("--force", action="store_true", help="with --export, re-export questions that already have a score")
    step = parser.add_mutually_exclusive_group(required=True)
    step.add_argument("--export", action="store_true", help="write pending cases to judge_cases/ for the benchmark-judge subagent")
    step.add_argument("--import", dest="import_verdicts", action="store_true", help="read <qid>.verdict.json files written by the subagent and score them")
    parser.add_argument("--judge-label", default=SUBAGENT_JUDGE_LABEL, help="judge_model recorded for imported verdicts")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = load_config(CONFIG_PATH)
    question_set = load_questions(QUESTIONS_PATH)
    results_paths = results_files(Path(config.services.results_dir) / args.run, args.candidate)
    if args.export:
        rubric = RUBRIC_PATH.read_text()
        for results_path in results_paths:
            export_cases(results_path, question_set.by_id, config, rubric, args.force)
        return
    for results_path in results_paths:
        import_verdicts(results_path, question_set.by_id, config, args.judge_label)


def results_files(run_dir: Path, candidate_keys: list[str] | None) -> list[Path]:
    if candidate_keys:
        return [run_dir / f"{key}.jsonl" for key in candidate_keys]
    return sorted(path for path in run_dir.glob("*.jsonl") if not path.name.endswith(".scores.jsonl"))


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
    sections = [render_question(question), *(render_exchange(index, transcript) for index, transcript in enumerate(result.exchanges, start=1)), render_harness_notes(result, gates)]
    return "\n\n".join(sections)


def render_question(question: Question) -> str:
    lines = [
        f"# Question {question.id} (category {question.category.value})",
        f"What it tests: {question.tests}",
        f"Expected search behavior: {question.expected_search}",
        f"Expected reply: {question.expected_reply.value if question.expected_reply else 'an ordinary answer'}",
        f"Constraints: {question.constraints.model_dump(exclude_defaults=True) or 'none'}",
        f"Gates especially relevant here: {', '.join(gate.value for gate in question.gates_for_judge) or 'none beyond the general rules'}",
    ]
    if question.reference_sketch:
        lines.append(f"\nReference sketch (what a correct answer must contain):\n{question.reference_sketch.strip()}")
    return "\n".join(lines)


def render_exchange(index: int, transcript: Transcript) -> str:
    parts = [f"# Exchange {index}"]
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
            f"Stayed silent (the final reply was the silence marker {SILENCE_MARKER}, so nothing was spoken): {'yes' if result.final.stayed_silent else 'no'}",
            render_route_note(result),
            f"Harness gates already applied: {', '.join(gate.value for gate in gates) or 'none'}",
            "Grade the final ASSISTANT message of the last exchange as the answer. Return the structured verdict.",
        ]
    )


def render_route_note(result: QuestionResult) -> str:
    decision = result.route
    if decision is None:
        return "Router: not run"
    return f"Router decided '{decision.route.value}' by {decision.source} ({decision.detail})"


if __name__ == "__main__":
    main()
