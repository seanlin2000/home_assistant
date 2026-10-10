"""TriviaBench: the alias grader reads spoken answers fairly, the question set keeps its shape, and the runner and report handle partial and failed runs."""

import re
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from assistant_core.converse_protocol import ConverseRequest
from assistant_core.models import AgentEvent, Done, Message, Role, ToolCall, ToolCallRecord, Transcript
from benchmark.records import Candidate, append_jsonl
from benchmark.triviabench.grading import Match, grade_answer, normalize_answer
from benchmark.triviabench.records import Difficulty, Era, Topic, TriviaQuestion, TriviaResult, TriviaSize, load_reference_answers, load_trivia_set
from benchmark.triviabench.report import REFERENCE_PATH, grade_candidate, render_report
from benchmark.triviabench.run import TRIVIA_SET_PATH, ask_question, harness_candidate, pending_questions

TRIVIA_SET = load_trivia_set(TRIVIA_SET_PATH)
HARNESS_CANDIDATE = Candidate(key="small-harness", label="Small model through the harness", provider="harness", model="small")


def trivia_question(question_id: str = "TB9999", answers: list[str] | None = None) -> TriviaQuestion:
    return TriviaQuestion(
        id=question_id,
        triviaqa_id="test_1",
        question="In which year did the Beatles release Abbey Road?",
        answers=answers or ["1969"],
        topic=Topic.MUSIC,
        year=1969,
        era=Era.FROM_1950_TO_1979,
        difficulty=Difficulty.MEDIUM,
        in_xs=True,
    )


def answered(question_id: str, answer: str, queries: list[str]) -> TriviaResult:
    records = [ToolCallRecord(round_index=0, call=ToolCall(id=f"call_{index}", name="search_and_read", arguments={"query": query}), result="", seconds=1.0) for index, query in enumerate(queries)]
    transcript = Transcript(model="small", system_prompt="", conversation=[], tool_call_records=records, final_answer=answer, total_seconds=4.0)
    return TriviaResult(question_id=question_id, candidate_key=HARNESS_CANDIDATE.key, model="small", transcript=transcript)


@pytest.mark.parametrize(
    ("spoken", "written"),
    [
        ("nineteen sixty-six", "1966"),
        ("sixty six", "66"),
        ("twenty twelve", "2012"),
        ("eighteen oh five", "1805"),
        ("two thousand and eight", "2008"),
        ("a hundred and one", "101"),
        ("3 million", "3000000"),
        ("The Third Man", "3rd man"),
        ("Côte d’Ivoire", "cote d ivoire"),
        ("Cote d'Ivoire", "cote d ivoire"),
        ("Oh, Brontë!", "oh bronte"),
    ],
)
def test_normalize_answer_reads_spoken_numbers_and_folds_punctuation(spoken: str, written: str) -> None:
    assert normalize_answer(spoken) == written


def test_spoken_year_in_a_sentence_matches_a_digit_alias() -> None:
    assert grade_answer("Abbey Road came out in nineteen sixty-nine.", ["1969"], "In which year did the Beatles release Abbey Road?") == Match.CONTAINED


def test_exact_answer_matches_any_alias() -> None:
    assert grade_answer("The Nutmeg State", ["Connecticut", "Nutmeg State"], "Which state is Yale in?") == Match.EXACT


def test_alias_the_question_repeats_only_counts_when_exact() -> None:
    question = "Which country won the 1966 World Cup?"
    assert grade_answer("The 1966 World Cup went to West Germany.", ["1966", "England"], question) == Match.NONE
    assert grade_answer("England won it at Wembley.", ["1966", "England"], question) == Match.CONTAINED


def test_short_word_alias_is_not_found_inside_a_sentence() -> None:
    assert grade_answer("It was in the US, I believe.", ["us"], "Where was it?") == Match.NONE
    assert grade_answer("US", ["us"], "Where was it?") == Match.EXACT


def test_trivia_set_has_one_thousand_questions_with_xs_inside() -> None:
    sizes = {size: TRIVIA_SET.of_size(size) for size in TriviaSize}
    assert len(sizes[TriviaSize.S]) == 1000
    assert len(sizes[TriviaSize.XS]) == 100
    assert {question.id for question in sizes[TriviaSize.XS]} <= {question.id for question in sizes[TriviaSize.S]}
    assert len({question.id for question in TRIVIA_SET.questions}) == 1000
    assert len({question.triviaqa_id for question in TRIVIA_SET.questions}) == 1000


def test_trivia_set_spreads_over_every_topic_era_and_difficulty() -> None:
    for size in TriviaSize:
        questions = TRIVIA_SET.of_size(size)
        assert {question.topic for question in questions} == set(Topic)
        assert {question.era for question in questions} == set(Era)
        assert {question.difficulty for question in questions} == set(Difficulty)


def test_no_question_points_at_options_triviaqa_dropped() -> None:
    """TriviaQA kept some multiple-choice stems without their choices ("Which is the longest length below?"); version 1.1 removed them."""
    stems_without_choices = [question.id for question in TRIVIA_SET.questions if re.search(r"\b(of these|below)\b", question.question, re.IGNORECASE)]
    assert stems_without_choices == []


def test_every_question_has_a_reference_answer() -> None:
    reference_ids = {answer.question_id for answer in load_reference_answers(REFERENCE_PATH).answers}
    assert reference_ids == {question.id for question in TRIVIA_SET.questions}


def test_spoken_question_carries_the_search_instruction() -> None:
    assert TRIVIA_SET.spoken_question(trivia_question()).endswith(TRIVIA_SET.search_instruction)


def test_only_harness_candidates_can_run() -> None:
    with pytest.raises(SystemExit):
        harness_candidate(HARNESS_CANDIDATE.model_copy(update={"provider": "ollama"}))
    assert harness_candidate(HARNESS_CANDIDATE) == HARNESS_CANDIDATE


def test_resumed_run_asks_again_only_unanswered_and_failed_questions(tmp_path: Path) -> None:
    output_path = tmp_path / "small-harness.jsonl"
    questions = [trivia_question("TB0001"), trivia_question("TB0002"), trivia_question("TB0003")]
    append_jsonl(output_path, answered("TB0001", "1969", []))
    append_jsonl(output_path, TriviaResult(question_id="TB0002", candidate_key=HARNESS_CANDIDATE.key, model="small", error="ReadTimeout: "))
    assert [question.id for question in pending_questions(questions, output_path, force=False)] == ["TB0002", "TB0003"]
    assert len(pending_questions(questions, output_path, force=True)) == 3
    assert not output_path.exists()


class ScriptedHarness:
    """Stands in for HarnessClient: replies with one transcript, or refuses the connection."""

    def __init__(self, transcript: Transcript | None) -> None:
        self.transcript = transcript
        self.requests: list[ConverseRequest] = []

    async def converse(self, request: ConverseRequest) -> AsyncIterator[AgentEvent]:
        self.requests.append(request)
        if self.transcript is None:
            raise httpx.ConnectError("connection refused")
        yield Done(transcript=self.transcript)


async def test_ask_question_sends_the_question_with_the_search_instruction() -> None:
    harness = ScriptedHarness(answered("TB9999", "Nineteen sixty-nine.", ["abbey road release year"]).transcript)
    result = await ask_question(harness, HARNESS_CANDIDATE, TRIVIA_SET, trivia_question())
    assert harness.requests[0].conversation == [Message(role=Role.USER, content=TRIVIA_SET.spoken_question(trivia_question()))]
    assert result.error is None
    assert result.search_queries == ["abbey road release year"]


async def test_ask_question_records_an_unreachable_harness_as_an_error() -> None:
    result = await ask_question(ScriptedHarness(None), HARNESS_CANDIDATE, TRIVIA_SET, trivia_question())
    assert result.error is not None and "ConnectError" in result.error
    assert result.answer == ""


def test_report_grades_answers_and_splits_by_search() -> None:
    questions = [trivia_question("TB0001"), trivia_question("TB0002"), trivia_question("TB0003")]
    results = [answered("TB0001", "It was nineteen sixty-nine.", ["abbey road"]), answered("TB0002", "Nineteen seventy.", []), answered("TB0002", "1969", [])]
    grades = grade_candidate("small-harness", results, questions)
    assert [graded.question.id for graded in grades.graded] == ["TB0001", "TB0002"]
    assert grades.correct_count() == 2
    assert grades.accuracy(lambda graded: graded.result.searched) == "100.0%"
    assert grades.misses() == []


def test_report_renders_every_section_for_a_partial_run() -> None:
    questions = TRIVIA_SET.of_size(TriviaSize.XS)
    grades = grade_candidate("small-harness", [answered(questions[0].id, questions[0].answers[0], ["query"])], questions)
    report = render_report("test_run", TriviaSize.XS, TRIVIA_SET, questions, [grades])
    for heading in ("## Summary", "## By topic", "## By era", "## By difficulty"):
        assert heading in report
    assert "| small-harness | 1 | 1 | 100.0% |" in report
