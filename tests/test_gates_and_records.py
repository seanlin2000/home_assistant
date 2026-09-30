from pathlib import Path

import pytest
from pydantic import ValidationError

from assistant_core.models import ToolCall, ToolCallRecord, Transcript
from benchmark.gates import harness_gates
from benchmark.records import Candidate, Gate, JudgeVerdict, QuestionResult, Score, load_config, load_questions


def transcript(answer: str, tool_calls: int = 0, malformed: int = 0) -> Transcript:
    return Transcript(model="m", system_prompt="", conversation=[], final_answer=answer, tool_call_count=tool_calls, malformed_tool_calls=["x"] * malformed)


def result(question_id: str, answer: str, searched: bool, tool_calls: int = 0, malformed: int = 0, checked_forecast: bool = False) -> QuestionResult:
    record = transcript(answer, tool_calls, malformed)
    if searched:
        record.tool_call_records.append(ToolCallRecord(round_index=0, call=ToolCall(id="1", name="search_and_read"), result="r", seconds=0.1))
    if checked_forecast:
        record.tool_call_records.append(ToolCallRecord(round_index=0, call=ToolCall(id="2", name="weather_forecast"), result="forecast", seconds=0.1))
    return QuestionResult(question_id=question_id, candidate_key="c", model="m", exchanges=[record])


QUESTIONS = load_questions(Path("benchmark/questions.yaml"))


def test_question_set_shape() -> None:
    assert len(QUESTIONS.questions) == 31
    assert {question.id for question in QUESTIONS.questions if question.route.value == "weather"} == {"D29", "D30", "D31"}
    assert QUESTIONS.by_id("B13").route.value == "search"
    assert QUESTIONS.by_id("C23").route.value == "calculate" and QUESTIONS.by_id("B11").route.value == "search" and QUESTIONS.by_id("A1").route.value == "answer"
    assert QUESTIONS.by_id("A6").exchanges[1].startswith("Suppose")
    assert QUESTIONS.by_id("A10").constraints.max_words == 120
    assert QUESTIONS.by_id("B21").should_search is True


def test_config_candidates_run_locally_or_by_hand_so_no_run_spends_paid_api_credit() -> None:
    config = load_config(Path("benchmark/config.yaml"))
    assert {candidate.provider for candidate in config.candidates} <= {"ollama", "manual"}
    assert config.policy.max_tool_rounds == 4
    with pytest.raises(ValidationError):
        Candidate(key="api", label="API model", provider="anthropic", model="any")


def test_harness_gates_for_search_decisions() -> None:
    assert harness_gates(QUESTIONS.by_id("A1"), result("A1", "answer", searched=True, tool_calls=1), 4) == [Gate.SEARCHED_ON_NO_SEARCH_QUESTION]
    assert harness_gates(QUESTIONS.by_id("B11"), result("B11", "answer", searched=False), 4) == [Gate.DID_NOT_SEARCH_ON_SEARCH_QUESTION]
    assert harness_gates(QUESTIONS.by_id("B11"), result("B11", "answer", searched=True, tool_calls=1), 4) == []


def test_harness_gates_for_weather_questions() -> None:
    assert harness_gates(QUESTIONS.by_id("D29"), result("D29", "Take one.", searched=False), 4) == [Gate.DID_NOT_CHECK_FORECAST_ON_WEATHER_QUESTION]
    assert harness_gates(QUESTIONS.by_id("D29"), result("D29", "Take one.", searched=True, tool_calls=1), 4) == [
        Gate.SEARCHED_ON_NO_SEARCH_QUESTION,
        Gate.DID_NOT_CHECK_FORECAST_ON_WEATHER_QUESTION,
    ]
    checked = result("D29", "Take one.", searched=False, tool_calls=1, checked_forecast=True)
    assert harness_gates(QUESTIONS.by_id("D29"), checked, 4) == []
    assert checked.forecast_call_count == 1 and checked.calculator_call_count == 0


def test_harness_gates_for_loops_empty_answers_and_word_limits() -> None:
    assert harness_gates(QUESTIONS.by_id("B11"), result("B11", "", searched=True, tool_calls=5), 4) == [Gate.TOO_MANY_TOOL_CALLS, Gate.NO_FINAL_ANSWER]
    assert harness_gates(QUESTIONS.by_id("B11"), result("B11", "ok", searched=True, tool_calls=1, malformed=1), 4) == [Gate.MALFORMED_TOOL_CALL]
    assert harness_gates(QUESTIONS.by_id("A10"), result("A10", "word " * 121, searched=False), 4) == [Gate.VIOLATED_EXPLICIT_CONSTRAINT]
    assert harness_gates(QUESTIONS.by_id("A10"), result("A10", "word " * 100, searched=False), 4) == []


def test_score_is_zeroed_by_any_gate_and_flags_disagreement() -> None:
    verdict = JudgeVerdict(gates_hit=[], search_decision_correct=True, answer_quality=5, judgment=3, spoken_fit=2, answer_quality_reason="", judgment_reason="", spoken_fit_reason="")
    clean = Score(question_id="A1", candidate_key="c", category="A", harness_gates=[], judge=verdict)
    gated = Score(question_id="A1", candidate_key="c", category="A", harness_gates=[Gate.SEARCHED_ON_NO_SEARCH_QUESTION], judge=verdict)
    assert clean.total == 10 and clean.harness_and_judge_disagree is False
    assert gated.total == 0 and gated.dimension_total == 10 and gated.harness_and_judge_disagree is True
