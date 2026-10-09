"""The router must never fire a rule wrongly on the benchmark set, must fall back to the model, and must leave the answer route alone."""

from pathlib import Path

import pytest

from assistant_core.models import AgentPolicy, Message, Role, Route, RouteDecision, ToolSpec
from assistant_core.router import SEARCH_DIRECTIVE, decide_route, decision_from_classification, directive_for, route_to_offered_tools, rule_route, tool_round_cap
from benchmark.records import load_questions

QUESTIONS = load_questions(Path("benchmark/questions.yaml"))
# B13 asks for train schedules and the weather; it has been scored as a search question since v1, so its scoring stays and the forecast is allowed here.
MIXED_QUESTIONS = {"B13": [Route.WEATHER]}
POLICY = AgentPolicy()


class FakeClassifier:
    model_name = "fake"

    def __init__(self, route: str | None = "search", fail: bool = False) -> None:
        self.route, self.fail, self.calls = route, fail, []
        self.also: list[str] = []
        self.plan = ""

    async def classify(self, system_prompt: str, user_text: str, schema: dict, policy: AgentPolicy) -> dict:
        self.calls.append(user_text)
        if self.fail:
            raise RuntimeError("model down")
        return {"route": self.route, "also": self.also, "plan": self.plan}


def test_rules_never_fire_wrongly_on_the_question_set() -> None:
    wrong = [
        (question.id, [route.value for route in decision.tool_routes])
        for question in QUESTIONS.questions
        if (decision := rule_route(question.exchanges[-1])) and not set(decision.tool_routes) <= set(question.required_tools or [question.route, *MIXED_QUESTIONS.get(question.id, [])])
    ]
    assert wrong == []


def test_rules_catch_explicit_searches_and_plain_arithmetic() -> None:
    fired = {question.id: decision.route for question in QUESTIONS.questions if (decision := rule_route(question.exchanges[-1]))}
    assert {"B17", "B18", "B19"} <= {qid for qid, route in fired.items() if route == Route.SEARCH}
    assert {"A2", "C23", "C26", "C27", "C28"} <= {qid for qid, route in fired.items() if route == Route.CALCULATE}
    assert rule_route("Can you look up whether the pharmacy on 5th is open on Sundays?").route == Route.SEARCH
    assert rule_route("Why is the sky blue?") is None


def test_weather_rule_fires_for_home_and_named_places_and_not_for_explanations() -> None:
    fired = {question.id for question in QUESTIONS.questions if (decision := rule_route(question.exchanges[-1])) and decision.route == Route.WEATHER}
    assert {"E36", "E37"} <= fired and "B13" not in fired
    for forecast in ("what's the weather", "Is it going to snow on Saturday?", "Will it rain in Paris tomorrow?", "What's the current weather in Tokyo?"):
        assert rule_route(forecast).tool_routes == [Route.WEATHER], forecast
    assert rule_route("Why does rain smell nice?") is None


def test_rules_combine_when_a_question_needs_several_tools() -> None:
    assert rule_route("What are the current train schedules and weather in Lucerne?").tool_routes == [Route.SEARCH, Route.WEATHER]
    assert rule_route("Search for today's mortgage rate and the monthly payment on a 400,000 dollar loan").tool_routes == [Route.SEARCH, Route.CALCULATE]
    assert rule_route("What is 15% of $80 plus $20?").tool_routes == [Route.CALCULATE]


def test_the_model_layer_can_plan_several_tools_but_never_repeats_or_adds_to_an_answer() -> None:
    planned = decision_from_classification({"route": "search", "also": ["calculate", "search"], "plan": "Find the rate, then multiply."})
    assert planned.tool_routes == [Route.SEARCH, Route.CALCULATE] and planned.plan == "Find the rate, then multiply."
    assert decision_from_classification({"route": "answer", "also": ["search"], "plan": "x"}).tool_routes == []
    assert decision_from_classification({"route": "weather", "plan": "ignored without also"}).plan == ""


def test_weather_rule_needs_a_question_about_coming_or_current_conditions_not_just_a_rain_or_snow_word() -> None:
    for forecast in ("Do I need an umbrella tomorrow?", "Will it rain this afternoon?", "Is it going to snow in the morning?", "What's the weather?"):
        assert rule_route(forecast).route == Route.WEATHER, forecast
    for not_forecast_by_rule in ("Who sang Purple Rain?", "Who wrote Snow Crash?", "How much rain does Seattle get a year?"):
        assert rule_route(not_forecast_by_rule) is None, not_forecast_by_rule


def test_weather_route_falls_back_to_search_when_the_server_offers_no_forecast_tool() -> None:
    weather = RouteDecision(route=Route.WEATHER, source="rule", detail="weather word")
    forecast_tool = ToolSpec(name="weather_forecast", description="", input_schema={})
    assert route_to_offered_tools(weather, [forecast_tool]) is weather
    fallback = route_to_offered_tools(weather, [ToolSpec(name="search_and_read", description="", input_schema={})])
    assert fallback.route == Route.SEARCH and fallback.detail.endswith("weather tool not offered, so searched")
    answer = RouteDecision(route=Route.ANSWER, source="model")
    assert route_to_offered_tools(answer, []) is answer


@pytest.mark.asyncio
async def test_model_layer_runs_only_when_no_rule_fires_and_defaults_on_failure() -> None:
    classifier = FakeClassifier("search")
    decision = await decide_route(classifier, [Message(role=Role.USER, content="What is the current federal funds rate?")], POLICY)
    assert decision.route == Route.SEARCH and decision.source == "model" and classifier.calls
    quiet = FakeClassifier()
    ruled = await decide_route(quiet, [Message(role=Role.USER, content="Search for the latest Qwen release")], POLICY)
    assert ruled.source == "rule" and quiet.calls == []
    broken = await decide_route(FakeClassifier(fail=True), [Message(role=Role.USER, content="Why is the sky blue?")], POLICY)
    assert broken.route == Route.ANSWER and "router failed" in broken.detail


@pytest.mark.asyncio
async def test_follow_up_exchanges_pass_earlier_user_messages_as_context() -> None:
    classifier = FakeClassifier("answer")
    conversation = [
        Message(role=Role.USER, content="I am choosing between 16 and 24 GB."),
        Message(role=Role.ASSISTANT, content="Go 24."),
        Message(role=Role.USER, content="Does it change if it costs more?"),
    ]
    await decide_route(classifier, conversation, POLICY)
    assert "Earlier the user said: I am choosing between 16 and 24 GB." in classifier.calls[0]


def test_directive_for_names_the_tool_for_each_routed_question_and_nothing_for_answers() -> None:
    assert directive_for(rule_route("search the web for it")) == SEARCH_DIRECTIVE.rstrip()
    assert "do not do the math yourself" in directive_for(rule_route("what is 15% of $80 plus $20"))
    assert 'place="Lisbon"' in directive_for(rule_route("do I need an umbrella tomorrow"))
    assert directive_for(RouteDecision(route=Route.ANSWER, source="model")) is None


def test_a_several_tool_directive_names_the_order_and_the_plan_and_keeps_each_example_call() -> None:
    decision = RouteDecision(route=Route.WEATHER, also=[Route.CALCULATE], plan="Get both highs, then subtract.", source="model")
    directive = directive_for(decision)
    assert directive.startswith("Routing for this question: WEATHER, then CALCULATE.")
    assert "Plan: Get both highs, then subtract." in directive and "weather_forecast(" in directive and "percent(" in directive
    assert "Routing for this question: WEATHER.\n" not in directive


def test_the_round_cap_grows_with_the_plan_but_never_below_the_configured_cap_or_above_six() -> None:
    one_tool = RouteDecision(route=Route.SEARCH, source="rule")
    three_tools = RouteDecision(route=Route.SEARCH, also=[Route.WEATHER, Route.CALCULATE], source="rule")
    assert tool_round_cap(one_tool, 4) == 4 and tool_round_cap(three_tools, 2) == 4 and tool_round_cap(three_tools, 9) == 6 and tool_round_cap(None, 4) == 4


def test_a_missing_forecast_tool_turns_weather_into_search_without_repeating_search() -> None:
    mixed = RouteDecision(route=Route.SEARCH, also=[Route.WEATHER, Route.CALCULATE], source="rule")
    assert route_to_offered_tools(mixed, []).tool_routes == [Route.SEARCH, Route.CALCULATE]


@pytest.mark.asyncio
async def test_a_second_request_after_a_ruled_one_asks_the_model_and_keeps_the_rule_first() -> None:
    classifier = FakeClassifier("weather")
    classifier.also, classifier.plan = ["search"], "Get the forecast, then search the ferry times."
    question = [Message(role=Role.USER, content="Will it rain in Seattle tomorrow, and when does the last ferry leave for Bainbridge?")]
    decision = await decide_route(classifier, question, POLICY)
    assert decision.tool_routes == [Route.WEATHER, Route.SEARCH] and decision.source == "rule+model" and decision.plan.startswith("Get the forecast")
    agreeing = FakeClassifier("weather")
    unchanged = await decide_route(agreeing, question, POLICY)
    assert unchanged.tool_routes == [Route.WEATHER] and unchanged.source == "rule" and agreeing.calls
