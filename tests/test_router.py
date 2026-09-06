"""The router must never fire a rule wrongly on the benchmark set, must fall back to the model, and must leave the answer route alone."""

from pathlib import Path

import pytest

from assistant_core.models import Message, Role, Route
from assistant_core.router import CALCULATE_DIRECTIVE, SEARCH_DIRECTIVE, apply_route, decide_route, rule_route
from benchmark.records import load_questions

QUESTIONS = load_questions(Path("benchmark/questions.yaml"))


class FakeClassifier:
    model_name = "fake"

    def __init__(self, route: str | None = "search", fail: bool = False) -> None:
        self.route, self.fail, self.calls = route, fail, []

    async def classify(self, system_prompt: str, user_text: str, schema: dict) -> dict:
        self.calls.append(user_text)
        if self.fail:
            raise RuntimeError("model down")
        return {"route": self.route}


def test_rules_never_fire_wrongly_on_the_question_set() -> None:
    wrong = [(question.id, decision.route.value) for question in QUESTIONS.questions if (decision := rule_route(question.turns[-1])) and decision.route != question.route]
    assert wrong == []


def test_rules_catch_explicit_searches_and_plain_arithmetic() -> None:
    fired = {question.id: decision.route for question in QUESTIONS.questions if (decision := rule_route(question.turns[-1]))}
    assert {"B17", "B18", "B19"} <= {qid for qid, route in fired.items() if route == Route.SEARCH}
    assert {"A2", "C23", "C26", "C27", "C28"} <= {qid for qid, route in fired.items() if route == Route.CALCULATE}
    assert rule_route("Can you look up whether the pharmacy on 5th is open on Sundays?").route == Route.SEARCH
    assert rule_route("Why is the sky blue?") is None


@pytest.mark.asyncio
async def test_model_layer_runs_only_when_no_rule_fires_and_defaults_on_failure() -> None:
    classifier = FakeClassifier("search")
    decision = await decide_route(classifier, [Message(role=Role.USER, content="What is the current federal funds rate?")])
    assert decision.route == Route.SEARCH and decision.source == "model" and classifier.calls
    quiet = FakeClassifier()
    ruled = await decide_route(quiet, [Message(role=Role.USER, content="Search for the latest Qwen release")])
    assert ruled.source == "rule" and quiet.calls == []
    broken = await decide_route(FakeClassifier(fail=True), [Message(role=Role.USER, content="Why is the sky blue?")])
    assert broken.route == Route.ANSWER and "router failed" in broken.detail


@pytest.mark.asyncio
async def test_follow_up_turns_pass_earlier_user_turns_as_context() -> None:
    classifier = FakeClassifier("answer")
    conversation = [
        Message(role=Role.USER, content="I am choosing between 16 and 24 GB."),
        Message(role=Role.ASSISTANT, content="Go 24."),
        Message(role=Role.USER, content="Does it change if it costs more?"),
    ]
    await decide_route(classifier, conversation)
    assert "Earlier the user said: I am choosing between 16 and 24 GB." in classifier.calls[0]


def test_apply_route_annotates_only_the_last_user_message() -> None:
    messages = [Message(role=Role.SYSTEM, content="sys"), Message(role=Role.USER, content="first"), Message(role=Role.ASSISTANT, content="a"), Message(role=Role.USER, content="second")]
    search = apply_route(messages, rule_route("search the web for it"))
    assert search[-1].content == f"second\n\n{SEARCH_DIRECTIVE}" and search[1].content == "first" and messages[-1].content == "second"
    calc = apply_route(messages, rule_route("what is 15% of $80 plus $20"))
    assert calc[-1].content.endswith(CALCULATE_DIRECTIVE)
    from assistant_core.models import RouteDecision

    assert apply_route(messages, RouteDecision(route=Route.ANSWER, source="model")) is messages
