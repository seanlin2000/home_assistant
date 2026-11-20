"""Grade a TriviaBench run and write its report: accuracy overall and by topic, era, and difficulty, how often each model searched and how well
that went, and a misses sheet per candidate with the queries it ran, which is what tuning the search tool server starts from."""

import argparse
import statistics
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from benchmark.records import load_config, read_jsonl
from benchmark.run import CONFIG_PATH
from benchmark.triviabench.grading import Match, grade_answer
from benchmark.triviabench.records import Difficulty, Era, Topic, TriviaQuestion, TriviaResult, TriviaSet, TriviaSize, load_reference_answers, load_trivia_set
from benchmark.triviabench.run import TRIVIA_SET_PATH

REFERENCE_PATH = Path("benchmark/triviabench/reference/claude-opus-5-5.yaml")
REFERENCE_KEY = "claude-opus-5-5-closed-book"
ALIASES_SHOWN_IN_MISSES = 4


@dataclass(frozen=True)
class GradedAnswer:
    question: TriviaQuestion
    result: TriviaResult
    match: Match

    @property
    def correct(self) -> bool:
        return self.result.error is None and self.match != Match.NONE


class CandidateGrades:
    def __init__(self, label: str, graded: list[GradedAnswer]) -> None:
        self.label = label
        self.graded = graded

    def accuracy(self, include: Callable[[GradedAnswer], bool] = lambda graded: True) -> str:
        selected = [graded for graded in self.graded if include(graded)]
        if not selected:
            return "-"
        return f"{100 * sum(graded.correct for graded in selected) / len(selected):.1f}%"

    def correct_count(self) -> int:
        return sum(graded.correct for graded in self.graded)

    def searched_share(self) -> str:
        return f"{100 * sum(graded.result.searched for graded in self.graded) / len(self.graded):.0f}%"

    def mean_searches(self) -> str:
        return f"{statistics.fmean(len(graded.result.search_queries) for graded in self.graded):.1f}"

    def median_seconds(self) -> str:
        seconds = [graded.result.transcript.total_seconds for graded in self.graded if graded.result.transcript]
        return f"{statistics.median(seconds):.1f}" if seconds else "-"

    def error_count(self) -> int:
        return sum(graded.result.error is not None for graded in self.graded)

    def misses(self) -> list[GradedAnswer]:
        return [graded for graded in self.graded if not graded.correct]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Grade a TriviaBench run and write its report and misses sheets.")
    parser.add_argument("--run", required=True, help="results folder name under benchmark/results")
    parser.add_argument("--size", choices=[size.value for size in TriviaSize], default=TriviaSize.XS.value, help="which set to report on; an S run can be reported as XS too")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    trivia_set = load_trivia_set(TRIVIA_SET_PATH)
    size = TriviaSize(args.size)
    questions = trivia_set.of_size(size)
    results_dir = Path(load_config(CONFIG_PATH).services.results_dir) / args.run / "triviabench"
    candidates = [grade_candidate(path.stem, read_jsonl(path, TriviaResult), questions) for path in sorted(results_dir.glob("*.jsonl"))]
    for candidate in candidates:
        (results_dir / f"misses_{size.value}_{candidate.label}.md").write_text(render_misses(candidate))
    report_path = results_dir / f"report_{size.value}.md"
    report_path.write_text(render_report(args.run, size, trivia_set, questions, candidates))
    print(f"wrote {report_path} and {len(candidates)} misses sheets")


def grade_candidate(label: str, results: list[TriviaResult], questions: list[TriviaQuestion]) -> CandidateGrades:
    """The latest result per question counts; a question the run never reached is left out, so a partial run reports on what it answered."""
    latest = {result.question_id: result for result in results}
    graded = [GradedAnswer(question, latest[question.id], grade_answer(latest[question.id].answer, question.answers, question.question)) for question in questions if question.id in latest]
    return CandidateGrades(label, graded)


def reference_grades(trivia_set: TriviaSet, questions: list[TriviaQuestion]) -> tuple[CandidateGrades, str]:
    """The closed-book reference graded by the same alias matcher, and its reviewed accuracy, which credits answers the matcher cannot recognise."""
    reference = load_reference_answers(REFERENCE_PATH)
    by_id = {answer.question_id: answer for answer in reference.answers}
    results = [TriviaResult(question_id=question.id, candidate_key=REFERENCE_KEY, model=reference.answered_by) for question in questions]
    graded = [GradedAnswer(question, result, grade_answer(by_id[question.id].answer, question.answers, question.question)) for question, result in zip(questions, results)]
    reviewed = sum(by_id[question.id].reviewed_correct for question in questions) / len(questions)
    return CandidateGrades(REFERENCE_KEY, graded), f"{100 * reviewed:.1f}%"


def render_report(run_name: str, size: TriviaSize, trivia_set: TriviaSet, questions: list[TriviaQuestion], candidates: list[CandidateGrades]) -> str:
    reference, reviewed_accuracy = reference_grades(trivia_set, questions)
    sections = [
        f"# TriviaBench {size.value.upper()}: {run_name}",
        f"{len(questions)} questions, set version {trivia_set.version}. Every question was asked through the harness with the instruction "
        f'"{trivia_set.search_instruction}" appended. An answer is correct when it equals a TriviaQA alias or contains one as whole words '
        "(spoken numbers read as digits; an alias the question itself contains only counts as an exact match).",
        render_summary_table(candidates, reference, reviewed_accuracy),
        render_breakdown("Topic", [(topic.value, lambda graded, topic=topic: graded.question.topic == topic) for topic in Topic], [*candidates, reference]),
        render_breakdown("Era", [(era.value, lambda graded, era=era: graded.question.era == era) for era in Era], [*candidates, reference]),
        render_breakdown(
            "Difficulty", [(difficulty.name.lower(), lambda graded, difficulty=difficulty: graded.question.difficulty == difficulty) for difficulty in Difficulty], [*candidates, reference]
        ),
    ]
    return "\n\n".join(sections) + "\n"


def render_summary_table(candidates: list[CandidateGrades], reference: CandidateGrades, reviewed_accuracy: str) -> str:
    rows = [
        "| Candidate | Answered | Correct | Accuracy | Searched | Accuracy when searched | Accuracy without a search | Searches per question | Median seconds | Errors |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for candidate in candidates:
        rows.append(
            f"| {candidate.label} | {len(candidate.graded)} | {candidate.correct_count()} | {candidate.accuracy()} | {candidate.searched_share()} "
            f"| {candidate.accuracy(lambda graded: graded.result.searched)} | {candidate.accuracy(lambda graded: not graded.result.searched)} "
            f"| {candidate.mean_searches()} | {candidate.median_seconds()} | {candidate.error_count()} |"
        )
    rows.append(f"| {reference.label} (reference, no search) | {len(reference.graded)} | {reference.correct_count()} | {reference.accuracy()} | - | - | - | - | - | - |")
    note = f"The reference is Claude Opus 5.5 answering from memory, graded by the same matcher; after reviewing every miss by hand it scored {reviewed_accuracy}."
    return "## Summary\n\n" + "\n".join(rows) + "\n\n" + note


def render_breakdown(dimension: str, groups: list[tuple[str, Callable[[GradedAnswer], bool]]], candidates: list[CandidateGrades]) -> str:
    rows = [f"| {dimension} | Questions | " + " | ".join(candidate.label for candidate in candidates) + " |", "|---|---|" + "---|" * len(candidates)]
    for name, include in groups:
        question_count = sum(include(graded) for graded in candidates[-1].graded)
        if question_count:
            rows.append(f"| {name} | {question_count} | " + " | ".join(candidate.accuracy(include) for candidate in candidates) + " |")
    return f"## By {dimension.lower()}\n\n" + "\n".join(rows)


def render_misses(candidate: CandidateGrades) -> str:
    entries = [render_miss(graded) for graded in candidate.misses()]
    return f"# {candidate.label}: {len(entries)} misses\n\n" + "\n\n".join(entries) + "\n"


def render_miss(graded: GradedAnswer) -> str:
    question = graded.question
    queries = "; ".join(f"`{query}`" for query in graded.result.search_queries) or "none"
    answer = graded.result.error or graded.result.answer
    return (
        f"## {question.id} ({question.topic.value}, {question.era.value}, {question.difficulty.name.lower()})\n\n"
        f"- Question: {question.question}\n- Key: {', '.join(question.answers[:ALIASES_SHOWN_IN_MISSES])}\n- Answer: {answer}\n- Searches: {queries}"
    )


if __name__ == "__main__":
    main()
