from assistant_core.models import GenerationStats, Transcript
from benchmark.pass_summary import gate_rows, per_question_rows, summary_row
from benchmark.records import Candidate, Category, Gate, JudgeVerdict, QuestionResult, Score
from benchmark.report import CandidateReport

CANDIDATE = Candidate(key="flash", label="Flash Next", provider="llama-server", model="qwen3.8-flash-next")


def verdict(quality: int, judgment: int = 3, spoken_fit: int = 2, gates: list[Gate] | None = None) -> JudgeVerdict:
    return JudgeVerdict(
        gates_hit=gates or [],
        search_decision_correct=True,
        answer_quality=quality,
        judgment=judgment,
        spoken_fit=spoken_fit,
        answer_quality_reason="",
        judgment_reason="",
        spoken_fit_reason="",
    )


def result(question_id: str, answer: str, stop_reason: str = "stop") -> QuestionResult:
    call = GenerationStats(model="m", total_seconds=2.0, fresh_prompt_tokens=900, cached_prompt_tokens=0, prompt_eval_seconds=1.0, output_tokens=100, generation_seconds=2.0, stop_reason=stop_reason)
    transcript = Transcript(model="m", system_prompt="", conversation=[], model_calls=[call], final_answer=answer, total_seconds=4.0)
    return QuestionResult(question_id=question_id, candidate_key="flash", model="m", exchanges=[transcript])


def one_pass(a_quality: int, b_gates: list[Gate] | None = None, b_stop_reason: str = "stop") -> CandidateReport:
    scores = [
        Score(question_id="A1", candidate_key="flash", category=Category.A, harness_gates=[], judge=verdict(a_quality)),
        Score(question_id="B1", candidate_key="flash", category=Category.B, harness_gates=[], judge=verdict(4, gates=b_gates)),
    ]
    return CandidateReport(CANDIDATE, [result("A1", "one two three"), result("B1", "four five", b_stop_reason)], scores)


def test_the_summary_averages_each_passs_totals_and_keeps_their_range() -> None:
    row = summary_row(CANDIDATE, [one_pass(5), one_pass(3, b_gates=[Gate.FABRICATED_CURRENT_FACT])])
    assert (row["pass1"], row["pass2"], row["mean"], row["low"], row["high"]) == (19, 8, 13.5, 8, 19)
    assert (row["cat_a"], row["cat_b"], row["before_gates"], row["gated_questions"]) == (9.0, 4.5, 18.0, 0.5)


def test_quality_with_gates_counts_a_gated_answers_quality_as_zero() -> None:
    row = summary_row(CANDIDATE, [one_pass(5), one_pass(3, b_gates=[Gate.FABRICATED_CURRENT_FACT])])
    assert (row["quality_pass1"], row["quality_pass2"], row["quality"], row["quality_gated"]) == (9, 7, 8.0, 6.0)
    assert (row["quality_a"], row["quality_b"], row["judgment"], row["spoken_fit"]) == (4.0, 4.0, 6.0, 4.0)


def test_speed_length_and_token_cap_pool_every_passs_answers() -> None:
    row = summary_row(CANDIDATE, [one_pass(5), one_pass(5, b_stop_reason="length")])
    assert (row["prefill_tps"], row["decode_tps"], row["words"], row["median_seconds"]) == (900, 50.0, 2, 4.0)
    assert (row["over_cap_pct"], row["empty_answers"], row["calls_per_question"]) == (25, 0.0, 0.0)


def test_per_question_rows_and_gate_counts_cover_every_pass() -> None:
    passes = [one_pass(5), one_pass(3, b_gates=[Gate.FABRICATED_CURRENT_FACT])]
    b_row = next(row for row in per_question_rows(CANDIDATE, passes) if row["question_id"] == "B1")
    assert (b_row["score"], b_row["before_gates"], b_row["quality"], b_row["quality_gated"]) == (4.5, 9.0, 4.0, 2.0)
    assert gate_rows(CANDIDATE, passes) == [{"key": "flash", "gate": "fabricated_current_fact", "count": 1}]
