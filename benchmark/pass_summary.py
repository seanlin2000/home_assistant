"""Several passes of the benchmark per candidate, summed per pass and averaged over the passes, in the shape of the benchmark report artifact's
datasets: summary.json (one row per candidate), per_question.json (each question's means) and gates.json (gates hit over all passes)."""

import argparse
import json
import statistics
from collections.abc import Callable
from pathlib import Path

from assistant_core.models import Transcript
from benchmark.records import Candidate, Category, Score, load_config
from benchmark.report import CandidateReport, load_reports
from utils.generation_speed_utils import generation_speed

CONFIG_PATH = Path("benchmark/config.yaml")
TOKEN_CAP_STOP_REASON = "length"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Average several benchmark passes per candidate into the report's summary, per-question, and gate rows.")
    parser.add_argument("--candidate", action="append", required=True, help="KEY=run1,run2,...: a candidate key from config.yaml and its passes' results folders")
    parser.add_argument("--output", required=True, help="folder under benchmark/results for summary.json, per_question.json and gates.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(CONFIG_PATH)
    results_dir = Path(config.services.results_dir)
    candidates = [candidate_passes(spec, config.candidate, results_dir) for spec in args.candidate]
    output_dir = results_dir / args.output
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = [summary_row(candidate, passes) for candidate, passes in candidates]
    write_json(output_dir / "summary.json", summary)
    write_json(output_dir / "per_question.json", [row for candidate, passes in candidates for row in per_question_rows(candidate, passes)])
    write_json(output_dir / "gates.json", [row for candidate, passes in candidates for row in gate_rows(candidate, passes)])
    print(render_table(summary))


def candidate_passes(spec: str, find_candidate: Callable[[str], Candidate], results_dir: Path) -> tuple[Candidate, list[CandidateReport]]:
    key, runs = spec.split("=", 1)
    candidate = find_candidate(key)
    return candidate, [load_reports(results_dir / run, [candidate])[0] for run in runs.split(",")]


def write_json(path: Path, rows: list[dict]) -> None:
    path.write_text(json.dumps(rows, indent=2))


def summary_row(candidate: Candidate, passes: list[CandidateReport]) -> dict:
    return {"key": candidate.key, "model": candidate.label, "passes": len(passes), **score_figures(passes), **quality_figures(passes), **answer_figures(passes)}


def score_figures(passes: list[CandidateReport]) -> dict:
    """The score out of 220 with gates (each pass, its mean and range), by category, and before gates."""
    totals = [report.total() for report in passes]
    return {
        "mean": round(statistics.fmean(totals), 1),
        "low": min(totals),
        "high": max(totals),
        **{f"pass{index}": total for index, total in enumerate(totals, 1)},
        "cat_a": mean_over(passes, lambda report: report.total(Category.A)),
        "cat_b": mean_over(passes, lambda report: report.total(Category.B)),
        "before_gates": mean_over(passes, CandidateReport.ungated_total),
        "gated_questions": mean_over(passes, CandidateReport.gated_question_count),
    }


def quality_figures(passes: list[CandidateReport]) -> dict:
    """The judge's answer quality with gates ignored (each pass, its mean and range, by category), with gates, and the other two dimensions."""
    qualities = [dimension_sum(report.judged(), "answer_quality") for report in passes]
    return {
        **{f"quality_pass{index}": quality for index, quality in enumerate(qualities, 1)},
        "quality_low": min(qualities),
        "quality_high": max(qualities),
        "quality": round(statistics.fmean(qualities), 1),
        "quality_a": mean_over(passes, lambda report: dimension_sum(in_category(report.judged(), Category.A), "answer_quality")),
        "quality_b": mean_over(passes, lambda report: dimension_sum(in_category(report.judged(), Category.B), "answer_quality")),
        "quality_gated": mean_over(passes, lambda report: dimension_sum(ungated(report.judged()), "answer_quality")),
        "judgment": mean_over(passes, lambda report: dimension_sum(report.judged(), "judgment")),
        "spoken_fit": mean_over(passes, lambda report: dimension_sum(report.judged(), "spoken_fit")),
    }


def answer_figures(passes: list[CandidateReport]) -> dict:
    """Speed, length and tool use, every pass's answers pooled."""
    finals = [transcript for report in passes for transcript in report.finals()]
    speed = generation_speed([call for transcript in finals for call in transcript.model_calls])
    return {
        "prefill_tps": rounded(speed and speed.prefill_tokens_per_second, 0),
        "decode_tps": rounded(speed and speed.decode_tokens_per_second, 1),
        "words": round(mean_over(passes, CandidateReport.mean_words)),
        "median_seconds": rounded(statistics.median(transcript.total_seconds for transcript in finals) if finals else None, 1),
        "calls_per_question": round(statistics.fmean(result.tool_call_count for report in passes for result in report.results), 1),
        "over_cap_pct": round(100 * sum(1 for transcript in finals if ended_at_token_cap(transcript)) / len(finals)) if finals else 0,
        "empty_answers": mean_over(passes, lambda report: sum(1 for transcript in report.finals() if not transcript.final_answer.strip())),
    }


def mean_over(passes: list[CandidateReport], figure: Callable[[CandidateReport], float]) -> float:
    return round(statistics.fmean(figure(report) for report in passes), 1)


def rounded(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)


def dimension_sum(scores: list[Score], dimension: str) -> int:
    return sum(getattr(score.judge, dimension) for score in scores)


def in_category(scores: list[Score], category: Category) -> list[Score]:
    return [score for score in scores if score.category == category]


def ungated(scores: list[Score]) -> list[Score]:
    """The scores no gate zeroed: quality "with gates" counts a gated answer's quality as zero."""
    return [score for score in scores if not score.gates]


def ended_at_token_cap(transcript: Transcript) -> bool:
    return bool(transcript.model_calls) and transcript.model_calls[-1].stop_reason == TOKEN_CAP_STOP_REASON


def per_question_rows(candidate: Candidate, passes: list[CandidateReport]) -> list[dict]:
    question_ids = sorted({score.question_id for report in passes for score in report.judged()})
    return [question_row(candidate, question_id, [score for report in passes if (score := report.score_for(question_id)) and score.judge]) for question_id in question_ids]


def question_row(candidate: Candidate, question_id: str, scores: list[Score]) -> dict:
    return {
        "key": candidate.key,
        "question_id": question_id,
        "category": scores[0].category.value,
        "score": round(statistics.fmean(score.total for score in scores), 2),
        "before_gates": round(statistics.fmean(score.dimension_total for score in scores), 2),
        "quality": round(statistics.fmean(score.judge.answer_quality for score in scores), 2),
        "quality_gated": round(statistics.fmean(0 if score.gates else score.judge.answer_quality for score in scores), 2),
        "judgment": round(statistics.fmean(score.judge.judgment for score in scores), 2),
        "spoken_fit": round(statistics.fmean(score.judge.spoken_fit for score in scores), 2),
    }


def gate_rows(candidate: Candidate, passes: list[CandidateReport]) -> list[dict]:
    counts: dict[str, int] = {}
    for report in passes:
        for gate, count in report.gate_counts().items():
            counts[gate.value] = counts.get(gate.value, 0) + count
    return [{"key": candidate.key, "gate": gate, "count": count} for gate, count in sorted(counts.items())]


def render_table(rows: list[dict]) -> str:
    lines = [
        "| Model | Mean (low–high) | Before gates | Quality | Quality with gates | Judgment | Spoken fit | Gated questions | Prefill tok/s | Decode tok/s | Words | Over cap |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['model']} | {row['mean']:.1f} ({row['low']}–{row['high']}) | {row['before_gates']} | {row['quality']:.1f} ({row['quality_low']}–{row['quality_high']}) | {row['quality_gated']} "
            f"| {row['judgment']} | {row['spoken_fit']} | {row['gated_questions']} | {row['prefill_tps']} | {row['decode_tps']} | {row['words']} | {row['over_cap_pct']}% |"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    main()
