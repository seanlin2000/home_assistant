"""Decide, before the model speaks, whether a question needs the web, the calculator, the home forecast, or none of them, and say so in the system prompt the model sees.

Two layers. Rules fire on unmistakable wording (an explicit request to search, several numbers with an arithmetic cue, or a question about coming or current
weather) at no cost. When no rule fires, one short structured-output call asks the same model to classify the question. For search, calculate, and weather a
directive naming the tool to call goes into the block just before the question (prompt 2.0), because the engines offer no way to force a tool call; answer adds
nothing. The system prompt stays the same for every question so the engine keeps it cached. The decision is recorded on the transcript so the benchmark can score the router on its own.
"""

import re
import time

from assistant_core.llm_client import LLMClient
from assistant_core.models import WEATHER_TOOL_NAMES, AgentPolicy, Message, Role, Route, RouteDecision, ToolSpec

ROUTE_SCHEMA = {"type": "object", "properties": {"route": {"type": "string", "enum": [route.value for route in Route]}}, "required": ["route"]}

ROUTER_SYSTEM_PROMPT = """You sort spoken questions for a home voice assistant. Reply with JSON only: {"route": "search" | "calculate" | "weather" | "answer"}.
search: the correct answer depends on facts that change over time or that the assistant cannot know without checking: current prices, rates, news, schedules, product availability, recent releases, market conditions, what to buy today, whether an offer is competitive right now, or a claim about a recent event. Also anything the user explicitly asks to be searched or looked up.
calculate: the correct answer requires arithmetic on numbers in the question: percentages, totals over time, compounding, unit or temperature conversions, energy costs, loan payments, tips, splits, or date differences.
weather: the coming or current weather or forecast, at home or in any named place: whether it will rain, how warm or cold it will get, whether to take an umbrella or a coat, the weekend forecast.
answer: everything else: explanations of how things work, reasoning, advice from what the user said, comparisons of ideas, opinions, clarifying questions, and settled history even when it sounds topical.
Examples: "What hardware gives the most memory for a thousand dollars today?" -> search. "Is a four percent rent increase competitive in my neighborhood?" -> search. "Since the central bank cut rates last month, should I refinance?" -> search. "What year did the Berlin Wall fall?" -> answer. "Why can a sparse model run on a smaller GPU?" -> answer. "What is fifteen percent of eighty dollars?" -> calculate. "Do I need an umbrella tomorrow?" -> weather. "What's the weather in Lisbon this weekend?" -> weather."""

# Prompt 1.3 to 1.8 appended the directive to the system prompt, where models weight operator instructions most; prompt 2.0 moves it into the block
# just before the question, because a system prompt that changes per question makes the engine read the tools and history again (design doc v2/02 3.2).
# One worked example shows the exact call shape. The wording stays a plain instruction;
# nothing in the harness enforces it, so it makes no threats about what happens to an answer that ignores it.
# Prompt 1.4 trimmed both blocks after pass 3: the search example had shown a finished spoken answer, and the smaller models imitated the answer
# instead of the tool call. Each block now shows the call and nothing else.
# Prompt 1.8 names wikipedia_lookup in the search block for lists and records; the example stays a search_and_read call, the commoner of the two.
SEARCH_DIRECTIVE = """Routing for this question: SEARCH.
This question needs information you must look up. Call search_and_read first, or wikipedia_lookup when it asks about a settled fact, list, or record such as a team's past players or who held an office; do not answer it from memory. Answer from what the tool returns.
Example call: search_and_read(query="used RTX 3090 price")
"""
CALCULATE_DIRECTIVE = """Routing for this question: CALCULATE.
This question needs arithmetic. Call the calculator tools (calculate, percent, convert, growth_schedule, energy_cost, loan_payment, break_even, date_math) for every number; do not do the math yourself. Then say what the result means.
Example call: percent(kind="of", a=15, b=80)
"""
WEATHER_DIRECTIVE = """Routing for this question: WEATHER.
This question is about the weather. Call weather_forecast first, with place set to the place the user named, or with no place for home; do not search the web and do not answer from memory. Answer from the forecast it returns.
Example call: weather_forecast(day="saturday", part_of_day="all", place="Lisbon")
"""
DIRECTIVES = {Route.SEARCH: SEARCH_DIRECTIVE, Route.CALCULATE: CALCULATE_DIRECTIVE, Route.WEATHER: WEATHER_DIRECTIVE}

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
# The weather rule fires on a question about coming or current conditions, at home or anywhere else, since weather_forecast takes a place (design doc
# v2/03 section 3.2). "Weather", "umbrella", or "the forecast" says so on its own; a precipitation word needs a time cue or a forecast question form as
# well, because "Purple Rain", "Snow Crash", or "how much rain does Seattle get a year" name rain and snow without asking about them.
FORECAST_WORD = re.compile(r"\b(weather|umbrella|(the|today's|tonight's|tomorrow's|weekend's) forecast)\b", re.IGNORECASE)
PRECIPITATION_WORD = re.compile(r"\b(rain(s|ing|y)?|snow(s|ing|y)?|drizzl\w*|thunderstorms?|sleet)\b", re.IGNORECASE)
TIME_CUE = re.compile(
    r"\b(today|tonight|tomorrow|(this|in the) (morning|afternoon|evening)|(this|next) week(end)?|weekend|later|now|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.IGNORECASE,
)
FORECAST_QUESTION_FORM = re.compile(r"\b(will it|is it (going to|gonna)|will there be|is there going to be|should i (bring|take|wear|expect))\b", re.IGNORECASE)
# A question that also asks for other current facts ("current schedules and weather") needs more than the forecast; the model layer decides it until
# M5 lets one question use several tools.
OTHER_CURRENT_FACTS_CUE = re.compile(r"\b(current|schedules?|timetables?|prices?|tickets?|news)\b", re.IGNORECASE)
EXPLANATION_CUE = re.compile(r"\b(why|explain|what causes|what makes|how (does|do) (rain|snow|weather|the weather))\b", re.IGNORECASE)


def rule_route(text: str) -> RouteDecision | None:
    if EXPLICIT_SEARCH.search(text):
        return RouteDecision(route=Route.SEARCH, source="rule", detail="explicit request to search")
    numbers = NUMBER.findall(text)
    cue = ARITHMETIC_CUE.search(text)
    if len(numbers) >= MIN_NUMBERS_FOR_ARITHMETIC and cue:
        return RouteDecision(route=Route.CALCULATE, source="rule", detail=f"{len(numbers)} numbers and cue '{cue.group(0)}'")
    weather_cue = forecast_cue(text)
    if weather_cue and not EXPLANATION_CUE.search(text) and not OTHER_CURRENT_FACTS_CUE.search(text):
        return RouteDecision(route=Route.WEATHER, source="rule", detail=weather_cue)
    return None


def forecast_cue(text: str) -> str | None:
    """What makes the text a question about coming or current weather, or None when nothing does."""
    forecast_word = FORECAST_WORD.search(text)
    if forecast_word:
        return f"forecast word '{forecast_word.group(0)}'"
    precipitation_word = PRECIPITATION_WORD.search(text)
    time_or_form = TIME_CUE.search(text) or FORECAST_QUESTION_FORM.search(text)
    if precipitation_word and time_or_form:
        return f"'{precipitation_word.group(0)}' with '{time_or_form.group(0)}'"
    return None


async def model_route(llm: LLMClient, text: str, earlier_user_messages: list[str], policy: AgentPolicy) -> RouteDecision:
    started = time.perf_counter()
    context = "".join(f"Earlier the user said: {message}\n" for message in earlier_user_messages[-2:])
    try:
        raw = await llm.classify(ROUTER_SYSTEM_PROMPT, f"{context}Question: {text}", ROUTE_SCHEMA, policy)
        route = Route(raw["route"])
        detail = "model classified"
    except Exception as error:  # noqa: BLE001 - a broken router must never block the answer
        route, detail = Route.ANSWER, f"router failed, defaulted to answer: {type(error).__name__}: {error}"
    return RouteDecision(route=route, source="model", detail=detail, seconds=time.perf_counter() - started)


async def decide_route(llm: LLMClient, conversation: list[Message], policy: AgentPolicy) -> RouteDecision:
    user_messages = [message.content for message in conversation if message.role == Role.USER]
    if not user_messages:
        return RouteDecision(route=Route.ANSWER, source="none", detail="no user message")
    decision = rule_route(user_messages[-1])
    if decision is not None:
        return decision
    return await model_route(llm, user_messages[-1], user_messages[:-1], policy)


def route_to_offered_tools(decision: RouteDecision, tool_specs: list[ToolSpec]) -> RouteDecision:
    """The tool server offers weather_forecast only when home has coordinates; without it a weather question is searched like any other place's weather."""
    if decision.route != Route.WEATHER or any(spec.name in WEATHER_TOOL_NAMES for spec in tool_specs):
        return decision
    return decision.model_copy(update={"route": Route.SEARCH, "detail": f"{decision.detail}; weather tool not offered, so searched"})


def directive_for(decision: RouteDecision) -> str | None:
    """The directive naming the tool to call, for the per-question block just before the question; None for the answer route."""
    directive = DIRECTIVES.get(decision.route)
    return directive.rstrip() if directive else None
