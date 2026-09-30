"""Decide, before the model speaks, whether a question needs the web, the calculator, the home forecast, or none of them, and say so in the system prompt the model sees.

Two layers. Rules fire on unmistakable wording (an explicit request to search, several numbers with an arithmetic cue, or a weather word with no other place
named) at no cost. When no rule fires, one short structured-output call asks the same model to classify the question. For search, calculate, and weather a
directive naming the tool to call is appended to the system prompt, because Ollama offers no way to force a tool call; answer adds nothing, and the user's
message is left exactly as spoken. The decision is recorded on the transcript so the benchmark can score the router on its own.
"""

import re
import time

from assistant_core.llm_client import LLMClient
from assistant_core.models import WEATHER_TOOL_NAMES, AgentPolicy, Message, Role, Route, RouteDecision, ToolSpec

ROUTE_SCHEMA = {"type": "object", "properties": {"route": {"type": "string", "enum": [route.value for route in Route]}}, "required": ["route"]}

ROUTER_SYSTEM_PROMPT = """You sort spoken questions for a home voice assistant. Reply with JSON only: {"route": "search" | "calculate" | "weather" | "answer"}.
search: the correct answer depends on facts that change over time or that the assistant cannot know without checking: current prices, rates, news, weather anywhere other than the user's home, schedules, product availability, recent releases, market conditions, what to buy today, whether an offer is competitive right now, or a claim about a recent event. Also anything the user explicitly asks to be searched or looked up.
calculate: the correct answer requires arithmetic on numbers in the question: percentages, totals over time, compounding, unit or temperature conversions, energy costs, loan payments, tips, splits, or date differences.
weather: the weather or forecast where the user lives, with no other place named: whether it will rain, how warm or cold it will get, whether to take an umbrella or a coat, the weekend forecast.
answer: everything else: explanations of how things work, reasoning, advice from what the user said, comparisons of ideas, opinions, clarifying questions, and settled history even when it sounds topical.
Examples: "What hardware gives the most memory for a thousand dollars today?" -> search. "Is a four percent rent increase competitive in my neighborhood?" -> search. "Since the central bank cut rates last month, should I refinance?" -> search. "What year did the Berlin Wall fall?" -> answer. "Why can a sparse model run on a smaller GPU?" -> answer. "What is fifteen percent of eighty dollars?" -> calculate. "Do I need an umbrella tomorrow?" -> weather. "What's the weather in Lisbon this weekend?" -> search."""

# Since prompt version 1.3 the directive is appended to the system prompt for the exchange, not to the user's message: models weight operator
# instructions above trailing notes in the request, and one worked example shows the exact call shape. The wording stays a plain instruction;
# nothing in the harness enforces it, so it makes no threats about what happens to an answer that ignores it.
# Prompt 1.4 trimmed both blocks after pass 3: the search example had shown a finished spoken answer, and the smaller models imitated the answer
# instead of the tool call. Each block now shows the call and nothing else.
SEARCH_DIRECTIVE = """Routing for this question: SEARCH.
This question needs current information from the web. Call search_and_read first; do not answer it from memory. Answer from the excerpts it returns.
Example call: search_and_read(query="used RTX 3090 price")
"""
CALCULATE_DIRECTIVE = """Routing for this question: CALCULATE.
This question needs arithmetic. Call the calculator tools (calculate, percent, convert, growth_schedule, energy_cost, loan_payment, break_even, date_math) for every number; do not do the math yourself. Then say what the result means.
Example call: percent(kind="of", a=15, b=80)
"""
WEATHER_DIRECTIVE = """Routing for this question: WEATHER.
This question is about the weather at home. Call weather_forecast first; do not search the web and do not answer from memory. Answer from the forecast it returns.
Example call: weather_forecast(day="tomorrow", part_of_day="afternoon")
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
# The weather rule fires only when no other place could be meant. Whatever follows a preposition (skipping "the") must be a word that names a time or
# the user's own surroundings; "in Lucerne", "in the Alps", or anything unrecognised leaves the question to the model layer, which sends other places to search.
WEATHER_WORD = re.compile(r"\b(weather|umbrella|rain(s|ing|y)?|snow(s|ing|y)?|drizzl\w*|thunderstorms?|sleet)\b", re.IGNORECASE)
EXPLANATION_CUE = re.compile(r"\b(why|explain|what causes|what makes|how (does|do) (rain|snow|weather|the weather))\b", re.IGNORECASE)
PREPOSITION_OBJECT = re.compile(r"\b(?:in|at|for|near|around|over|to|from|on)\s+(?:the\s+)?(\w+)", re.IGNORECASE)
WORDS_THAT_NAME_NO_OTHER_PLACE = frozenset(
    {"this", "that", "a", "an", "my", "our", "here", "home", "outside", "work", "commute"}
    | {"today", "tonight", "tomorrow", "morning", "afternoon", "evening", "night", "weekend", "week", "next", "later", "now", "noon", "midnight"}
    | {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
    | {"go", "be", "get", "bring", "wear", "take", "walk", "run", "bike", "rain", "snow", "sleet", "drizzle", "storm"}
)


def rule_route(text: str) -> RouteDecision | None:
    if EXPLICIT_SEARCH.search(text):
        return RouteDecision(route=Route.SEARCH, source="rule", detail="explicit request to search")
    numbers = NUMBER.findall(text)
    cue = ARITHMETIC_CUE.search(text)
    if len(numbers) >= MIN_NUMBERS_FOR_ARITHMETIC and cue:
        return RouteDecision(route=Route.CALCULATE, source="rule", detail=f"{len(numbers)} numbers and cue '{cue.group(0)}'")
    weather_word = WEATHER_WORD.search(text)
    if weather_word and not EXPLANATION_CUE.search(text) and not names_another_place(text):
        return RouteDecision(route=Route.WEATHER, source="rule", detail=f"weather word '{weather_word.group(0)}' and no other place named")
    return None


def names_another_place(text: str) -> bool:
    return any(not word.isdigit() and word.lower() not in WORDS_THAT_NAME_NO_OTHER_PLACE for word in PREPOSITION_OBJECT.findall(text))


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


def apply_route(messages: list[Message], decision: RouteDecision) -> list[Message]:
    """Return a copy of the messages with the directive for the route appended to the system prompt; unchanged for the answer route.

    The user's message is left exactly as spoken. If there is no system message yet (a caller that skipped build_messages), one is prepended."""
    directive = DIRECTIVES.get(decision.route)
    if directive is None:
        return messages
    for index, message in enumerate(messages):
        if message.role == Role.SYSTEM:
            annotated = message.model_copy(update={"content": f"{message.content}\n\n{directive.rstrip()}"})
            return [*messages[:index], annotated, *messages[index + 1 :]]
    return [Message(role=Role.SYSTEM, content=directive.rstrip()), *messages]
