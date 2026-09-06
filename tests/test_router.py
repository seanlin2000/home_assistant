"""The router must never fire a rule wrongly on the benchmark set, must fall back to the model, and must leave the answer route alone."""

from pathlib import Path

import pytest

from assistant_core.models import AgentPolicy, Message, Role, Route
from assistant_core.router import CALCULATE_DIRECTIVE, SEARCH_DIRECTIVE, apply_route, decide_route, rule_route
from benchmark.records import load_questions

QUESTIONS = load_questions(Path("benchmark/questions.yaml"))
POLICY = AgentPolicy()


class FakeClassifier:
    model_name = "fake"

    def __init__(self, route: str | None = "search", fail: bool = False) -> None:
        self.route, self.fail, self.calls = route, fail, []

    async def classify(self, system_prompt: str, user_text: str, schema: dict, policy) -> dict:
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
    decision = await decide_route(classifier, [Message(role=Role.USER, content="What is the current federal funds rate?")], POLICY)
    assert decision.route == Route.SEARCH and decision.source == "model" and classifier.calls
    quiet = FakeClassifier()
    ruled = await decide_route(quiet, [Message(role=Role.USER, content="Search for the latest Qwen release")], POLICY)
    assert ruled.source == "rule" and quiet.calls == []
    broken = await decide_route(FakeClassifier(fail=True), [Message(role=Role.USER, content="Why is the sky blue?")], POLICY)
    assert broken.route == Route.ANSWER and "router failed" in broken.detail


@pytest.mark.asyncio
async def test_follow_up_turns_pass_earlier_user_turns_as_context() -> None:
    classifier = FakeClassifier("answer")
    conversation = [
        Message(role=Role.USER, content="I am choosing between 16 and 24 GB."),
        Message(role=Role.ASSISTANT, content="Go 24."),
        Message(role=Role.USER, content="Does it change if it costs more?"),
    ]
    await decide_route(classifier, conversation, POLICY)
    assert "Earlier the user said: I am choosing between 16 and 24 GB." in classifier.calls[0]


def test_apply_route_appends_the_directive_to_the_system_prompt_and_leaves_the_user_message_alone() -> None:
    messages = [Message(role=Role.SYSTEM, content="sys"), Message(role=Role.USER, content="first"), Message(role=Role.ASSISTANT, content="a"), Message(role=Role.USER, content="second")]
    search = apply_route(messages, rule_route("search the web for it"))
    assert search[0].content == f"sys\n\n{SEARCH_DIRECTIVE.rstrip()}" and search[-1].content == "second" and messages[0].content == "sys"
    calc = apply_route(messages, rule_route("what is 15% of $80 plus $20"))
    assert calc[0].content.endswith(CALCULATE_DIRECTIVE.rstrip()) and "do not do the math yourself" in calc[0].content
    from assistant_core.models import RouteDecision

    assert apply_route(messages, RouteDecision(route=Route.ANSWER, source="model")) is messages


def test_apply_route_prepends_a_system_message_when_there_is_none() -> None:
    messages = [Message(role=Role.USER, content="what is 15% of $80 plus $20")]
    calc = apply_route(messages, rule_route(messages[0].content))
    assert calc[0].role == Role.SYSTEM and calc[0].content == CALCULATE_DIRECTIVE.rstrip() and calc[1] is messages[0]
