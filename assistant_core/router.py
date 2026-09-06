"""Decide, before the model speaks, whether a question needs the web, the calculator, or neither, and say so in the message the model sees.

Two layers. Rules fire on unmistakable wording (an explicit request to search, or several numbers with an arithmetic cue) at no cost. When no rule fires,
one short structured-output call asks the same model to classify the question. Either way the decision is appended to the user message as a bracketed
note, because Ollama offers no way to force a tool call. The decision is recorded on the transcript so the benchmark can score the router on its own.
"""

import re
import time

from assistant_core.llm_client import LLMClient
from assistant_core.models import AgentPolicy, Message, Role, Route, RouteDecision

ROUTE_SCHEMA = {"type": "object", "properties": {"route": {"type": "string", "enum": [route.value for route in Route]}}, "required": ["route"]}

ROUTER_SYSTEM_PROMPT = """You sort spoken questions for a home voice assistant. Reply with JSON only: {"route": "search" | "calculate" | "answer"}.
search: the correct answer depends on facts that change over time or that the assistant cannot know without checking: current prices, rates, news, weather, schedules, product availability, recent releases, market conditions, what to buy today, whether an offer is competitive right now, or a claim about a recent event. Also anything the user explicitly asks to be searched or looked up.
calculate: the correct answer requires arithmetic on numbers in the question: percentages, totals over time, compounding, unit or temperature conversions, energy costs, loan payments, tips, splits, or date differences.
answer: everything else: explanations of how things work, reasoning, advice from what the user said, comparisons of ideas, opinions, clarifying questions, and settled history even when it sounds topical.
Examples: "What hardware gives the most memory for a thousand dollars today?" -> search. "Is a four percent rent increase competitive in my neighborhood?" -> search. "Since the central bank cut rates last month, should I refinance?" -> search. "What year did the Berlin Wall fall?" -> answer. "Why can a sparse model run on a smaller GPU?" -> answer. "What is fifteen percent of eighty dollars?" -> calculate."""

SEARCH_DIRECTIVE = "[Assistant note: this question needs current information from the web. Call search_and_read before answering; do not answer it from memory.]"
CALCULATE_DIRECTIVE = "[Assistant note: this question needs arithmetic. Call the calculator tools (calculate, percent, convert, growth_schedule, energy_cost, loan_payment, break_even, date_math) for every number; do not do the math yourself.]"
DIRECTIVES = {Route.SEARCH: SEARCH_DIRECTIVE, Route.CALCULATE: CALCULATE_DIRECTIVE}

EXPLICIT_SEARCH = re.compile(
    r"\b(search (the )?(web|internet|online)|search for|look (it |this |that |them )?up|look up|google (it|this|that|for)|web search for|check (the web|online)|find (me )?the (latest|current|newest|best current))\b",
    re.IGNORECASE,
)
NUMBER = re.compile(r"(?<![\w.])\$?\d[\d,]*(?:\.\d+)?%?")
ARITHMETIC_CUE = re.compile(
    r"(\d%|\bpercent\b|\bper (month|year|hour|day|week|kilowatt)\b|\ba (month|year|week)\b|\bkilowatt|\bkwh\b|\bwatts?\b|\binterest\b|\bcompound|\bmortgage\b|\bloan\b|\btip\b|"
    r"\bconvert\b|\bdegrees\b|\bfahrenheit\b|\bcelsius\b|\btimes\b|\bplus\b|\bminus\b|\bdivided\b|\bmultipl|\bsquare(d)?\b|\bhow much (would|will|do|does) (i|it|that) (pay|cost|save|come)|\bin total\b|\btotal cost\b|\bmonthly (cost|payment)\b|\bsplit\b)",
    re.IGNORECASE,
)
MIN_NUMBERS_FOR_ARITHMETIC = 2


def rule_route(text: str) -> RouteDecision | None:
    if EXPLICIT_SEARCH.search(text):
        return RouteDecision(route=Route.SEARCH, source="rule", detail="explicit request to search")
    numbers = NUMBER.findall(text)
    cue = ARITHMETIC_CUE.search(text)
    if len(numbers) >= MIN_NUMBERS_FOR_ARITHMETIC and cue:
        return RouteDecision(route=Route.CALCULATE, source="rule", detail=f"{len(numbers)} numbers and cue '{cue.group(0)}'")
    return None


async def model_route(llm: LLMClient, text: str, earlier_user_turns: list[str], policy: AgentPolicy) -> RouteDecision:
    started = time.perf_counter()
    context = "".join(f"Earlier the user said: {turn}\n" for turn in earlier_user_turns[-2:])
    try:
        raw = await llm.classify(ROUTER_SYSTEM_PROMPT, f"{context}Question: {text}", ROUTE_SCHEMA, policy)
        route = Route(raw["route"])
        detail = "model classified"
    except Exception as error:  # noqa: BLE001 - a broken router must never block the answer
        route, detail = Route.ANSWER, f"router failed, defaulted to answer: {type(error).__name__}: {error}"
    return RouteDecision(route=route, source="model", detail=detail, seconds=time.perf_counter() - started)


async def decide_route(llm: LLMClient, conversation: list[Message], policy: AgentPolicy) -> RouteDecision:
    user_turns = [message.content for message in conversation if message.role == Role.USER]
    if not user_turns:
        return RouteDecision(route=Route.ANSWER, source="none", detail="no user message")
    decision = rule_route(user_turns[-1])
    if decision is not None:
        return decision
    return await model_route(llm, user_turns[-1], user_turns[:-1], policy)


def apply_route(messages: list[Message], decision: RouteDecision) -> list[Message]:
    """Return a copy of the messages with the directive for the route appended to the last user message; unchanged for the answer route."""
    directive = DIRECTIVES.get(decision.route)
    if directive is None:
        return messages
    for index in range(len(messages) - 1, -1, -1):
        if messages[index].role == Role.USER:
            annotated = messages[index].model_copy(update={"content": f"{messages[index].content}\n\n{directive}"})
            return [*messages[:index], annotated, *messages[index + 1 :]]
    return messages
