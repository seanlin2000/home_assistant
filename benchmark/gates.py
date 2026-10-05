"""Gates the harness can decide mechanically from a transcript, without a judge."""

from assistant_core.models import Route
from benchmark.records import Gate, Question, QuestionResult


def harness_gates(question: Question, result: QuestionResult, max_tool_rounds: int) -> list[Gate]:
    if result.error:
        return [Gate.RUN_ERROR]
    checks = (
        (Gate.SEARCHED_ON_NO_SEARCH_QUESTION, result.searched and not question.should_search),
        (Gate.DID_NOT_SEARCH_ON_SEARCH_QUESTION, question.should_search and not result.searched),
        (Gate.DID_NOT_CHECK_FORECAST_ON_WEATHER_QUESTION, question.route == Route.WEATHER and not result.checked_forecast),
        (Gate.MALFORMED_TOOL_CALL, any(transcript.malformed_tool_calls for transcript in result.exchanges)),
        (Gate.TOO_MANY_TOOL_CALLS, any(transcript.tool_call_count > max_tool_rounds for transcript in result.exchanges)),
        (Gate.NO_FINAL_ANSWER, not result.final.final_answer.strip()),
        (Gate.SPOKE_WHEN_IT_SHOULD_STAY_SILENT, question.should_stay_silent and not result.final.stayed_silent),
        (Gate.STAYED_SILENT_ON_REAL_REQUEST, not question.should_stay_silent and any(transcript.stayed_silent for transcript in result.exchanges)),
        (Gate.VIOLATED_EXPLICIT_CONSTRAINT, exceeds_word_limit(question, result)),
    )
    return [gate for gate, failed in checks if failed]


def exceeds_word_limit(question: Question, result: QuestionResult) -> bool:
    limit = question.constraints.max_words
    return limit is not None and word_count(result.final.final_answer) > limit


def word_count(text: str) -> int:
    return len(text.split())
