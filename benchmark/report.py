"""Merge harness gates and judge verdicts into report.md, and produce the human review sheet."""

import argparse
import json
import random
import statistics
from pathlib import Path

import yaml

from assistant_core.models import Route
from benchmark.costs import estimate_cost_usd
from benchmark.records import Candidate, Category, Gate, Question, QuestionResult, QuestionSet, Score, load_config, load_questions, read_jsonl

CONFIG_PATH = Path("benchmark/config.yaml")
QUESTIONS_PATH = Path("benchmark/questions.yaml")
PREVIEW_CAVEAT = "Preview builds run at 3-bit precision because the 4-bit production build does not fit the prototype machine. A high preview score is strong evidence for the production build; a low one is only weak evidence against it."


class CandidateReport:
    def __init__(self, candidate: Candidate, results: list[QuestionResult], scores: list[Score]) -> None:
        self.candidate = candidate
        self.results = results
        self.scores = scores

    def total(self, category: Category | None = None) -> int:
        return sum(score.total for score in self.scores if category is None or score.category == category)

    def ungated_total(self, category: Category | None = None) -> int:
        """Dimension points with gates ignored: what the answers earned on quality alone."""
        return sum(score.dimension_total for score in self.scores if category is None or score.category == category)

    def maximum(self, category: Category | None = None) -> int:
        return 10 * sum(1 for score in self.scores if category is None or score.category == category)

    def gated_question_count(self) -> int:
        return sum(1 for score in self.scores if score.gates)

    def gate_counts(self) -> dict[Gate, int]:
        counts: dict[Gate, int] = {}
        for score in self.scores:
            for gate in score.gates:
                counts[gate] = counts.get(gate, 0) + 1
        return counts

    def judged(self) -> list[Score]:
        return [score for score in self.scores if score.judge is not None]

    def mean_dimension(self, name: str) -> float:
        judged = self.judged()
        return statistics.fmean(getattr(score.judge, name) for score in judged) if judged else 0.0

    def finals(self) -> list:
        return [result.final for result in self.results if not result.error]

    def median_seconds(self, field: str) -> float:
        values = [getattr(transcript, field) for transcript in self.finals() if getattr(transcript, field) is not None]
        return statistics.median(values) if values else 0.0

    def mean_words(self) -> float:
        finals = self.finals()
        return statistics.fmean(len(transcript.final_answer.split()) for transcript in finals) if finals else 0.0

    def searched_count(self) -> int:
        return sum(1 for result in self.results if result.searched)

    def fully_on_gpu(self) -> str:
        flags = {result.memory_fit.fully_on_gpu for result in self.results}
        return "n/a" if flags == {None} else ("yes" if flags == {True} else "NO")

    def route_outcomes(self, question_set: QuestionSet) -> list[tuple[Question, object]]:
        """(question, decision) for every result whose final turn was routed."""
        outcomes = []
        for result in self.results:
            if result.route is not None:
                outcomes.append((question_set.by_id(result.question_id), result.route))
        return outcomes

    def score_for(self, question_id: str) -> Score | None:
        return next((score for score in self.scores if score.question_id == question_id), None)

    def api_cost_usd(self) -> float:
        calls = [stats for result in self.results for transcript in result.turns for stats in transcript.model_calls]
        baseline = estimate_cost_usd(sum(stats.prompt_tokens or 0 for stats in calls), sum(stats.output_tokens or 0 for stats in calls)) if self.candidate.provider == "anthropic" else 0.0
        judge = estimate_cost_usd(sum(score.judge_input_tokens for score in self.scores), sum(score.judge_output_tokens for score in self.scores))
        return baseline + judge


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render the benchmark report and review sheet.")
    parser.add_argument("run", help="results folder name under benchmark/results (version_1, version_2, ...)")
    parser.add_argument("--compare", help="an earlier results folder to compare against, question by question")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(CONFIG_PATH)
    question_set = load_questions(QUESTIONS_PATH)
    run_dir = Path(config.services.results_dir) / args.run
    reports = load_reports(run_dir, config.candidates)
    previous = load_reports(Path(config.services.results_dir) / args.compare, config.candidates) if args.compare else None
    (run_dir / "report.md").write_text(render_report(args.run, question_set, reports, run_dir, previous, args.compare))
    write_review_sheet(run_dir, question_set, reports, config.judge.review_sample_fraction, config.judge.review_seed)
    print(f"wrote {run_dir / 'report.md'} and {run_dir / 'review_sheet.yaml'}")


def load_reports(run_dir: Path, candidates: list[Candidate]) -> list[CandidateReport]:
    reports = []
    for candidate in candidates:
        results = read_jsonl(run_dir / f"{candidate.key}.jsonl", QuestionResult)
        scores = read_jsonl(run_dir / f"{candidate.key}.scores.jsonl", Score)
        if results:
            reports.append(CandidateReport(candidate, results, scores))
    return reports


def render_report(run_name: str, question_set: QuestionSet, reports: list[CandidateReport], run_dir: Path, previous: list[CandidateReport] | None = None, previous_name: str | None = None) -> str:
    baseline = next((report for report in reports if report.candidate.baseline), None)
    sections = [
        f"# LLM benchmark report, {run_name}\n\nQuestion set v{question_set.version}, {len(question_set.questions)} questions, 10 points each. Any gate failure zeroes a question.{render_run_meta(run_dir)}",
        render_summary_table(reports, baseline),
        render_gate_table(reports),
        render_router_table(question_set, reports),
        render_latency_table(reports),
        render_matrix(question_set, reports),
        render_agreement(run_dir, reports),
        render_judge(reports),
        render_spend(reports),
    ]
    if previous is not None and previous_name:
        sections.insert(2, render_comparison(reports, previous, previous_name))
    if any(report.candidate.preview for report in reports):
        sections.insert(2, f"> {PREVIEW_CAVEAT}")
    return "\n\n".join(sections) + "\n"


def render_run_meta(run_dir: Path) -> str:
    meta_path = run_dir / "run_meta.json"
    if not meta_path.exists():
        return ""
    meta = json.loads(meta_path.read_text())
    return f" System prompt v{meta.get('prompt_version', '1.1')}; question routing {'on' if meta.get('policy', {}).get('route_questions', False) else 'off'}."


def render_router_table(question_set: QuestionSet, reports: list[CandidateReport]) -> str:
    routed = [report for report in reports if report.route_outcomes(question_set)]
    if not routed:
        return "## Router\n\nNo routed results in this run."
    lines = [
        "## Router accuracy (search / calculate / answer decided before the model spoke)",
        "",
        "The rule layer is model-independent, so its row is the same for every candidate; the model layer is the candidate classifying its own question.",
        "",
        "| Candidate | Rule layer fired | Rule correct | Model layer decided | Model correct | Overall correct | Median router time | Misroutes (got, expected) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for report in routed:
        outcomes = report.route_outcomes(question_set)
        by_rule = [(question, decision) for question, decision in outcomes if decision.source == "rule"]
        by_model = [(question, decision) for question, decision in outcomes if decision.source == "model"]
        correct = [(question, decision) for question, decision in outcomes if decision.route == question.route]
        misroutes = ", ".join(f"{question.id} ({decision.route.value}, {question.route.value})" for question, decision in outcomes if decision.route != question.route) or "none"
        model_seconds = [decision.seconds for _, decision in by_model]
        lines.append(
            f"| {label(report)} | {len(by_rule)} | {count_correct(by_rule)}/{len(by_rule)} | {len(by_model)} | {count_correct(by_model)}/{len(by_model)} | {len(correct)}/{len(outcomes)} ({len(correct) / len(outcomes):.0%}) | {statistics.median(model_seconds) if model_seconds else 0:.2f} s | {misroutes} |"
        )
    return "\n".join(lines)


def count_correct(outcomes: list[tuple[Question, object]]) -> int:
    return sum(1 for question, decision in outcomes if decision.route == question.route)


def render_comparison(reports: list[CandidateReport], previous: list[CandidateReport], previous_name: str) -> str:
    lines = [
        f"## Compared with {previous_name}",
        "",
        "Totals on the questions both passes share, so new questions do not inflate the second pass.",
        "",
        "| Candidate | Shared questions | Previous | This pass | Change | Previous ungated | This pass ungated | Previous gated | This pass gated |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    earlier = {report.candidate.key: report for report in previous}
    for report in reports:
        old = earlier.get(report.candidate.key)
        if old is None:
            continue
        shared = sorted({score.question_id for score in report.scores} & {score.question_id for score in old.scores})
        before = sum(old.score_for(qid).total for qid in shared)
        after = sum(report.score_for(qid).total for qid in shared)
        gated_before = sum(1 for qid in shared if old.score_for(qid).gates)
        gated_after = sum(1 for qid in shared if report.score_for(qid).gates)
        ungated_before = sum(old.score_for(qid).dimension_total for qid in shared)
        ungated_after = sum(report.score_for(qid).dimension_total for qid in shared)
        lines.append(
            f"| {label(report)} | {len(shared)} | {before}/{10 * len(shared)} | {after}/{10 * len(shared)} | {after - before:+d} | {ungated_before}/{10 * len(shared)} | {ungated_after}/{10 * len(shared)} | {gated_before} | {gated_after} |"
        )
    return "\n".join(lines)


def render_summary_table(reports: list[CandidateReport], baseline: CandidateReport | None) -> str:
    lines = [
        "## Scores",
        "",
        "Total counts a gated question as zero; ungated total ignores the gates and sums the dimension scores, so the gap between them is what the gates cost.",
        "",
        "| Candidate | Total | Ungated total | Category A | Category B | Category C | vs baseline | Gated questions | Quality /5 | Judgment /3 | Spoken /2 | Unjudged |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for report in sorted(reports, key=lambda item: item.total(), reverse=True):
        ratio = f"{report.total() / baseline.total():.0%}" if baseline and baseline.total() else "n/a"
        unjudged = len(report.scores) - len(report.judged())
        lines.append(
            f"| {label(report)} | {report.total()}/{report.maximum()} | {report.ungated_total()}/{report.maximum()} | {report.total(Category.A)}/{report.maximum(Category.A)} | {report.total(Category.B)}/{report.maximum(Category.B)} | {category_cell(report, Category.C)} | {ratio} | {report.gated_question_count()} | {report.mean_dimension('answer_quality'):.1f} | {report.mean_dimension('judgment'):.1f} | {report.mean_dimension('spoken_fit'):.1f} | {unjudged} |"
        )
    return "\n".join(lines)


def category_cell(report: CandidateReport, category: Category) -> str:
    maximum = report.maximum(category)
    return "n/a" if maximum == 0 else f"{report.total(category)}/{maximum}"


def label(report: CandidateReport) -> str:
    return report.candidate.label + (" (preview)" if report.candidate.preview else "")


def render_gate_table(reports: list[CandidateReport]) -> str:
    gates_seen = sorted({gate for report in reports for gate in report.gate_counts()})
    if not gates_seen:
        return "## Gate failures\n\nNone."
    header = "| Candidate | " + " | ".join(gate.value for gate in gates_seen) + " |"
    lines = ["## Gate failures by type", "", header, "|---|" + "---|" * len(gates_seen)]
    for report in reports:
        counts = report.gate_counts()
        lines.append(f"| {label(report)} | " + " | ".join(str(counts.get(gate, 0)) for gate in gates_seen) + " |")
    return "\n".join(lines)


def render_latency_table(reports: list[CandidateReport]) -> str:
    lines = [
        "## Logged, not scored (prototype machine, for projection only)",
        "",
        "| Candidate | Median time to first token | Median total | Mean answer words | Questions searched | Fully on GPU |",
        "|---|---|---|---|---|---|",
    ]
    for report in reports:
        lines.append(
            f"| {label(report)} | {report.median_seconds('time_to_first_token_seconds'):.1f} s | {report.median_seconds('total_seconds'):.1f} s | {report.mean_words():.0f} | {report.searched_count()}/{len(report.results)} | {report.fully_on_gpu()} |"
        )
    return "\n".join(lines)


def render_matrix(question_set: QuestionSet, reports: list[CandidateReport]) -> str:
    header = "| Question | " + " | ".join(report.candidate.key for report in reports) + " |"
    lines = ["## Per-question scores (G = gated to zero, - = not judged)", "", header, "|---|" + "---|" * len(reports)]
    for question in question_set.questions:
        cells = [matrix_cell(report, question.id) for report in reports]
        lines.append(f"| {question.id} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def matrix_cell(report: CandidateReport, question_id: str) -> str:
    score = next((score for score in report.scores if score.question_id == question_id), None)
    if score is None or score.judge is None:
        return "-"
    return f"G ({score.dimension_total})" if score.gates else str(score.total)


def render_agreement(run_dir: Path, reports: list[CandidateReport]) -> str:
    review_path = run_dir / "review_sheet.yaml"
    if not review_path.exists():
        return "## Judge agreement\n\nReview sheet not yet filled in."
    entries = [entry for entry in yaml.safe_load(review_path.read_text())["entries"] if entry["human"]["gate_hit"] is not None]
    if not entries:
        return "## Judge agreement\n\nReview sheet not yet filled in."
    gate_matches = sum(1 for entry in entries if entry["human"]["gate_hit"] == entry["judge"]["gate_hit"])
    diffs = [abs(human_total(entry) - entry["judge"]["dimension_total"]) for entry in entries if human_total(entry) is not None]
    mean_diff = statistics.fmean(diffs) if diffs else 0.0
    return f"## Judge agreement\n\n{len(entries)} reviewed. Gate agreement {gate_matches / len(entries):.0%} (target at least 90%). Mean absolute difference in dimension total: {mean_diff:.2f} points out of 10."


def human_total(entry: dict) -> int | None:
    human = entry["human"]
    if any(human[name] is None for name in ("answer_quality", "judgment", "spoken_fit")):
        return None
    return human["answer_quality"] + human["judgment"] + human["spoken_fit"]


def render_judge(reports: list[CandidateReport]) -> str:
    """Name the judge that produced the scores. Passes judged through the API and passes judged by a Claude Code subagent used the same rubric, but they
    are different sessions of the model, so cross-pass score comparisons carry that caveat."""
    labels = sorted({score.judge_model for report in reports for score in report.scores if score.judge_model})
    if not labels:
        return "## Judge\n\nNo judged scores yet."
    return (
        "## Judge\n\nScores in this pass were produced by: "
        + ", ".join(labels)
        + ". Same rubric and output schema as every other pass; a subagent judge costs nothing but is a different session of the model than an API judge, so compare totals across passes with that in mind."
    )


def render_spend(reports: list[CandidateReport]) -> str:
    total = sum(report.api_cost_usd() for report in reports)
    return f"## Paid API spend for this run\n\nAbout ${total:.2f} (baseline run plus judging, at Claude Opus 5 list prices)."


def write_review_sheet(run_dir: Path, question_set: QuestionSet, reports: list[CandidateReport], sample_fraction: float, seed: int) -> None:
    existing = load_existing_review(run_dir / "review_sheet.yaml")
    entries = [review_entry(report, score, question_set, existing) for report in reports for score in select_for_review(report, sample_fraction, seed)]
    (run_dir / "review_sheet.yaml").write_text(yaml.safe_dump({"instructions": REVIEW_INSTRUCTIONS, "entries": entries}, sort_keys=False, allow_unicode=True, width=1000))
    (run_dir / "review_sheet.md").write_text(render_review_markdown(entries))


def select_for_review(report: CandidateReport, sample_fraction: float, seed: int) -> list[Score]:
    judged = report.judged()
    picker = random.Random(f"{seed}:{report.candidate.key}")
    sample_size = max(1, round(len(judged) * sample_fraction)) if judged else 0
    sampled = set(picker.sample([score.question_id for score in judged], sample_size))
    return [score for score in judged if score.question_id in sampled or score.harness_and_judge_disagree]


def load_existing_review(path: Path) -> dict[tuple[str, str], dict]:
    if not path.exists():
        return {}
    return {(entry["candidate"], entry["question_id"]): entry["human"] for entry in yaml.safe_load(path.read_text())["entries"]}


def review_entry(report: CandidateReport, score: Score, question_set: QuestionSet, existing: dict[tuple[str, str], dict]) -> dict:
    result = next(result for result in report.results if result.question_id == score.question_id)
    blank = {"gate_hit": None, "gates": [], "answer_quality": None, "judgment": None, "spoken_fit": None, "notes": ""}
    return {
        "candidate": report.candidate.key,
        "question_id": score.question_id,
        "why_selected": "harness and judge disagree on the search decision" if score.harness_and_judge_disagree else "random sample",
        "question": question_set.by_id(score.question_id).turns,
        "searched": result.searched,
        "spoken_answer": result.final.spoken_text or result.final.final_answer,
        "judge": {
            "gate_hit": bool(score.gates),
            "gates": [gate.value for gate in score.gates],
            "dimension_total": score.dimension_total,
            "answer_quality": score.judge.answer_quality,
            "judgment": score.judge.judgment,
            "spoken_fit": score.judge.spoken_fit,
            "reasons": [score.judge.answer_quality_reason, score.judge.judgment_reason, score.judge.spoken_fit_reason],
        },
        "human": existing.get((report.candidate.key, score.question_id), blank),
    }


REVIEW_INSTRUCTIONS = "For each entry, fill in the human block: gate_hit true/false (would you zero this answer?), the gates you would apply, and the three scores per benchmark/rubric.md. Leave a field null to skip it. Then re-run benchmark-report to compute agreement."


def render_review_markdown(entries: list[dict]) -> str:
    by_candidate: dict[str, list[dict]] = {}
    for entry in entries:
        by_candidate.setdefault(entry["candidate"], []).append(entry)
    parts = ["# Review sheet\n\nRead the answer, decide on gates and scores, then record them in review_sheet.yaml.", render_review_contents(by_candidate)]
    for candidate, candidate_entries in by_candidate.items():
        parts.append(f'<a id="{anchor(candidate)}"></a>\n\n## {candidate} ({len(candidate_entries)} to review)')
        parts.extend(render_review_entry(entry) for entry in candidate_entries)
        parts.append("[Back to top](#review-sheet)")
    return "\n\n".join(parts) + "\n"


def render_review_contents(by_candidate: dict[str, list[dict]]) -> str:
    lines = ["## Contents", ""]
    for candidate, candidate_entries in by_candidate.items():
        question_links = ", ".join(f"[{entry['question_id']}](#{anchor(candidate, entry['question_id'])})" for entry in candidate_entries)
        lines.append(f"- [{candidate}](#{anchor(candidate)}): {question_links}")
    return "\n".join(lines)


def render_review_entry(entry: dict) -> str:
    judge = entry["judge"]
    return (
        f'<a id="{anchor(entry["candidate"], entry["question_id"])}"></a>\n\n'
        f"### {entry['candidate']} / {entry['question_id']} ({entry['why_selected']})\n\n**Question:** {' / '.join(entry['question'])}\n\n**Searched:** {entry['searched']}\n\n**Spoken answer:**\n\n> {entry['spoken_answer']}\n\n**Judge:** gates={judge['gates'] or 'none'}, quality {judge['answer_quality']}/5, judgment {judge['judgment']}/3, spoken {judge['spoken_fit']}/2\n\n"
        + "\n".join(f"- {reason}" for reason in judge["reasons"])
    )


def anchor(candidate: str, question_id: str | None = None) -> str:
    slug = candidate.replace(".", "-")
    return f"review-{slug}" if question_id is None else f"review-{slug}-{question_id.lower()}"


if __name__ == "__main__":
    main()
