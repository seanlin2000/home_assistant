"""Gates the harness can decide mechanically from a transcript, without a judge."""

from benchmark.records import Gate, Question, QuestionResult


def harness_gates(question: Question, result: QuestionResult, max_tool_rounds: int) -> list[Gate]:
    if result.error:
        return [Gate.RUN_ERROR]
    checks = (
        (Gate.SEARCHED_ON_NO_SEARCH_QUESTION, result.searched and not question.should_search),
        (Gate.DID_NOT_SEARCH_ON_SEARCH_QUESTION, question.should_search and not result.searched),
        (Gate.MALFORMED_TOOL_CALL, any(transcript.malformed_tool_calls for transcript in result.turns)),
        (Gate.TOO_MANY_TOOL_CALLS, any(transcript.tool_call_count > max_tool_rounds for transcript in result.turns)),
        (Gate.NO_FINAL_ANSWER, not result.final.final_answer.strip()),
        (Gate.VIOLATED_EXPLICIT_CONSTRAINT, exceeds_word_limit(question, result)),
    )
    return [gate for gate, failed in checks if failed]


def exceeds_word_limit(question: Question, result: QuestionResult) -> bool:
    limit = question.constraints.max_words
    return limit is not None and word_count(result.final.final_answer) > limit


def word_count(text: str) -> int:
    return len(text.split())
