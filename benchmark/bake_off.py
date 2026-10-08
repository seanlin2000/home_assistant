"""The M1 engine bake-off: the same questions on two candidates, several runs each, judged against M1's exit criteria (design doc v2/02 section 3.7).

Each run is a results folder holding one JSONL file per candidate, and optionally its scores. The noise band of a category is the spread of the
baseline's scores across its runs; the candidate passes on score when its mean is at least the baseline's mean minus that band.
"""

import argparse
import statistics
from dataclasses import dataclass
from pathlib import Path

from assistant_core.models import Transcript
from benchmark.records import Category, QuestionResult, Score, read_jsonl

RESULTS_DIR = Path("benchmark/results")
SLOW_FIRST_REQUEST_FRESH_TOKENS = 600
FIRST_REQUEST_SHARE_REQUIRED = 0.9
EMPTY_COMPLETION_RATE_LIMIT = 1 / 7
SPOKEN_WORD_RATIO_LIMIT = 0.5
SLOWEST_TENTH = 0.9


@dataclass
class RunFigures:
    """What one run of one candidate measured."""

    total: int | None
    category_totals: dict[Category, int]
    exchanges: int
    malformed_exchanges: int
    empty_completion_exchanges: int
    first_spoken_seconds: list[float]
    first_request_fresh_tokens: list[int]
    decode_rates: list[float]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare two candidates over repeated runs against M1's exit criteria.")
    parser.add_argument("--run", action="append", required=True, help="results folder under benchmark/results; repeat once per run")
    parser.add_argument("--baseline", required=True, help="candidate key of the baseline, e.g. gemma4-e4b")
    parser.add_argument("--candidate", required=True, help="candidate key under test, e.g. gemma4-e4b-llama")
    parser.add_argument("--output", type=Path, help="write the markdown here as well as printing it")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    baseline = [run_figures(RESULTS_DIR / run, args.baseline) for run in args.run]
    candidate = [run_figures(RESULTS_DIR / run, args.candidate) for run in args.run]
    text = render(args.baseline, baseline, args.candidate, candidate, args.run)
    print(text)
    if args.output:
        args.output.write_text(text)


def run_figures(run_dir: Path, key: str) -> RunFigures:
    results = read_jsonl(run_dir / f"{key}.jsonl", QuestionResult)
    scores = read_jsonl(run_dir / f"{key}.scores.jsonl", Score)
    exchanges = [transcript for result in results for transcript in result.exchanges]
    return RunFigures(
        total=sum(score.total for score in scores) if scores else None,
        category_totals={category: sum(score.total for score in scores if score.category == category) for category in Category},
        exchanges=len(exchanges),
        malformed_exchanges=sum(1 for transcript in exchanges if transcript.malformed_tool_calls),
        empty_completion_exchanges=sum(1 for transcript in exchanges if transcript.empty_completion_retries),
        first_spoken_seconds=[transcript.time_to_first_spoken_seconds for transcript in exchanges if transcript.time_to_first_spoken_seconds is not None],
        first_request_fresh_tokens=[fresh for transcript in exchanges if (fresh := first_request_fresh_tokens(transcript)) is not None],
        decode_rates=[rate for transcript in exchanges for rate in decode_rates(transcript)],
    )


def first_request_fresh_tokens(transcript: Transcript) -> int | None:
    return transcript.model_calls[0].fresh_prompt_tokens if transcript.model_calls else None


def decode_rates(transcript: Transcript) -> list[float]:
    return [call.output_tokens / call.generation_seconds for call in transcript.model_calls if call.output_tokens and call.generation_seconds]


def slowest_tenth(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * SLOWEST_TENTH))] if ordered else 0.0


def pooled(runs: list[RunFigures], field: str) -> list[float]:
    return [value for run in runs for value in getattr(run, field)]


def render(baseline_key: str, baseline: list[RunFigures], candidate_key: str, candidate: list[RunFigures], run_names: list[str]) -> str:
    sections = [
        f"# M1 engine bake-off: {candidate_key} against {baseline_key}\n\nRuns: {', '.join(run_names)}.",
        render_scores(baseline_key, baseline, candidate_key, candidate),
        render_reliability(baseline_key, baseline, candidate_key, candidate),
        render_speed(baseline_key, baseline, candidate_key, candidate),
        render_criteria(baseline, candidate),
    ]
    return "\n\n".join(sections) + "\n"


def render_scores(baseline_key: str, baseline: list[RunFigures], candidate_key: str, candidate: list[RunFigures]) -> str:
    lines = [
        "## Scores per run (gated questions count zero)",
        "",
        "| Category | "
        + " | ".join(f"{baseline_key} run {index + 1}" for index in range(len(baseline)))
        + " | Noise band | "
        + " | ".join(f"{candidate_key} run {index + 1}" for index in range(len(candidate)))
        + " |",
    ]
    lines.append("|---|" + "---|" * (len(baseline) + len(candidate) + 1))
    for category in Category:
        base_values = [run.category_totals[category] for run in baseline]
        lines.append(
            f"| {category.value} | "
            + " | ".join(str(value) for value in base_values)
            + f" | {max(base_values) - min(base_values)} | "
            + " | ".join(str(run.category_totals[category]) for run in candidate)
            + " |"
        )
    lines.append("| Total | " + " | ".join(str(run.total) for run in baseline) + f" | {noise_band(baseline)} | " + " | ".join(str(run.total) for run in candidate) + " |")
    return "\n".join(lines)


def noise_band(runs: list[RunFigures]) -> int | None:
    totals = [run.total for run in runs if run.total is not None]
    return max(totals) - min(totals) if totals else None


def render_reliability(baseline_key: str, baseline: list[RunFigures], candidate_key: str, candidate: list[RunFigures]) -> str:
    lines = ["## Tool calls and empty completions, all runs", "", "| Candidate | Exchanges | With a malformed tool call | With an empty completion retried |", "|---|---|---|---|"]
    for key, runs in ((baseline_key, baseline), (candidate_key, candidate)):
        exchanges = sum(run.exchanges for run in runs)
        lines.append(f"| {key} | {exchanges} | {sum(run.malformed_exchanges for run in runs)} | {sum(run.empty_completion_exchanges for run in runs)} |")
    return "\n".join(lines)


def render_speed(baseline_key: str, baseline: list[RunFigures], candidate_key: str, candidate: list[RunFigures]) -> str:
    lines = [
        "## Speed, all runs pooled",
        "",
        f"| Candidate | Median first spoken word | Slowest tenth | First requests over {SLOW_FIRST_REQUEST_FRESH_TOKENS} fresh tokens | Median decode |",
        "|---|---|---|---|---|",
    ]
    for key, runs in ((baseline_key, baseline), (candidate_key, candidate)):
        spoken = pooled(runs, "first_spoken_seconds")
        fresh = pooled(runs, "first_request_fresh_tokens")
        decode = pooled(runs, "decode_rates")
        over = f"{sum(1 for value in fresh if value > SLOW_FIRST_REQUEST_FRESH_TOKENS)} of {len(fresh)}" if fresh else "not reported"
        lines.append(f"| {key} | {statistics.median(spoken) if spoken else 0:.2f} s | {slowest_tenth(spoken):.2f} s | {over} | {statistics.median(decode) if decode else 0:.1f} tok/s |")
    return "\n".join(lines)


def render_criteria(baseline: list[RunFigures], candidate: list[RunFigures]) -> str:
    lines = ["## M1 exit criteria (v2/00 section 9)", "", "| Criterion | Measured | Met |", "|---|---|---|"]
    for name, measured, met in m1_criteria(baseline, candidate):
        lines.append(f"| {name} | {measured} | {'yes' if met else ('not judged yet' if met is None else 'NO')} |")
    return "\n".join(lines)


def m1_criteria(baseline: list[RunFigures], candidate: list[RunFigures]) -> list[tuple[str, str, bool | None]]:
    return [score_criterion(baseline, candidate), malformed_criterion(baseline, candidate), empty_criterion(candidate), spoken_criterion(baseline, candidate), fresh_criterion(candidate)]


def score_criterion(baseline: list[RunFigures], candidate: list[RunFigures]) -> tuple[str, str, bool | None]:
    base_totals = [run.total for run in baseline if run.total is not None]
    cand_totals = [run.total for run in candidate if run.total is not None]
    if not base_totals or not cand_totals:
        return ("Score at least the baseline's minus the noise", "scores missing", None)
    floor = statistics.fmean(base_totals) - (max(base_totals) - min(base_totals))
    mean = statistics.fmean(cand_totals)
    return ("Score at least the baseline's minus the noise", f"mean {mean:.1f} against a floor of {floor:.1f}", mean >= floor)


def malformed_criterion(baseline: list[RunFigures], candidate: list[RunFigures]) -> tuple[str, str, bool]:
    base = sum(run.malformed_exchanges for run in baseline)
    cand = sum(run.malformed_exchanges for run in candidate)
    return ("Malformed tool calls no more often than the baseline", f"{cand} against {base}", cand <= base)


def empty_criterion(candidate: list[RunFigures]) -> tuple[str, str, bool]:
    exchanges = sum(run.exchanges for run in candidate)
    empty = sum(run.empty_completion_exchanges for run in candidate)
    rate = empty / exchanges if exchanges else 0.0
    return ("Empty completions rarer than one in seven", f"{empty} of {exchanges} ({rate:.0%})", rate < EMPTY_COMPLETION_RATE_LIMIT)


def spoken_criterion(baseline: list[RunFigures], candidate: list[RunFigures]) -> tuple[str, str, bool]:
    base = statistics.median(pooled(baseline, "first_spoken_seconds"))
    cand = statistics.median(pooled(candidate, "first_spoken_seconds"))
    return ("Median first spoken word at most half the baseline's", f"{cand:.2f} s against {base:.2f} s", cand <= base * SPOKEN_WORD_RATIO_LIMIT)


def fresh_criterion(candidate: list[RunFigures]) -> tuple[str, str, bool]:
    fresh = pooled(candidate, "first_request_fresh_tokens")
    within = sum(1 for value in fresh if value <= SLOW_FIRST_REQUEST_FRESH_TOKENS)
    share = within / len(fresh) if fresh else 0.0
    return (f"Nine first requests in ten read at most {SLOW_FIRST_REQUEST_FRESH_TOKENS} tokens fresh", f"{within} of {len(fresh)} ({share:.0%})", share >= FIRST_REQUEST_SHARE_REQUIRED)


if __name__ == "__main__":
    main()
