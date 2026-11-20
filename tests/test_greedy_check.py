from assistant_core.models import ToolCall
from benchmark.greedy_check import GreedyAnswer, differing_prompts


def answer(prompt_name: str, text: str, call_id: str = "call-1", city: str = "Paris") -> GreedyAnswer:
    call = ToolCall(id=call_id, name="weather_forecast", arguments={"place": city})
    return GreedyAnswer(label="x", prompt_name=prompt_name, text=text, tool_calls=[call], prompt_tokens=10, time_to_first_token_seconds=0.1, total_seconds=1.0, decode_rate=90.0)


def test_answers_differ_only_in_their_words_or_their_calls_not_in_the_call_ids() -> None:
    reference = [answer("short", "30"), answer("weather", "")]
    assert differing_prompts([answer("short", "30", call_id="call-9"), answer("weather", "")], reference) == []
    assert differing_prompts([answer("short", "30.0"), answer("weather", "", city="Lyon")], reference) == ["short", "weather"]


def test_a_prompt_the_reference_never_answered_differs() -> None:
    assert differing_prompts([answer("story", "Once")], [answer("short", "30")]) == ["story"]
