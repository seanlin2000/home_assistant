"""Decide, before the model speaks, which tools a question needs (the web, the calculator, the forecast, several of them, or none) and say so just before the question.

Two layers. Rules fire on unmistakable wording (an explicit request to search, numbers with an arithmetic cue, or a question about coming or current
weather) at no cost, and several can fire for one question. When no rule fires, one short structured-output call asks the same model to classify the
question and, when it needs more than one tool, to plan their order in a sentence. A directive naming the tools to call goes into the block just before the
question (prompt 2.0), because the engines offer no way to force a tool call; answer adds nothing. The system prompt stays the same for every question so
the engine keeps it cached. The decision is recorded on the transcript so the benchmark can score the router on its own.
"""

import re
import time

from assistant_core.llm_client import LLMClient
from assistant_core.models import WEATHER_TOOL_NAMES, AgentPolicy, Message, Role, Route, RouteDecision, ToolSpec

TOOL_ROUTES = [Route.SEARCH, Route.CALCULATE, Route.WEATHER]
MAX_EXTRA_ROUTES = 2
ROUTE_SCHEMA = {
    "type": "object",
    "properties": {
        "route": {"type": "string", "enum": [route.value for route in Route]},
        "also": {"type": "array", "items": {"type": "string", "enum": [route.value for route in TOOL_ROUTES]}, "maxItems": MAX_EXTRA_ROUTES},
        "plan": {"type": "string"},
    },
    "required": ["route"],
}

ROUTER_SYSTEM_PROMPT = """You sort spoken questions for a home voice assistant. Reply with JSON only: {"route": "search" | "calculate" | "weather" | "answer", "also": [...], "plan": "..."}.
search: the correct answer depends on facts that change over time or that the assistant cannot know without checking: current prices, rates, news, schedules, product availability, recent releases, market conditions, what to buy today, whether an offer is competitive right now, or a claim about a recent event. Also anything the user explicitly asks to be searched or looked up.
calculate: the correct answer requires arithmetic on numbers in the question: percentages, totals over time, compounding, unit or temperature conversions, energy costs, loan payments, tips, splits, or date differences.
weather: the coming or current weather or forecast, at home or in any named place: whether it will rain, how warm or cold it will get, whether to take an umbrella or a coat, the weekend forecast.
answer: everything else: explanations of how things work, reasoning, advice from what the user said, comparisons of ideas, opinions, clarifying questions, and settled history even when it sounds topical.
Examples: "What hardware gives the most memory for a thousand dollars today?" -> search. "Is a four percent rent increase competitive in my neighborhood?" -> search. "Since the central bank cut rates last month, should I refinance?" -> search. "What year did the Berlin Wall fall?" -> answer. "Why can a sparse model run on a smaller GPU?" -> answer. "What is fifteen percent of eighty dollars?" -> calculate. "Do I need an umbrella tomorrow?" -> weather. "What's the weather in Lisbon this weekend?" -> weather.
also: only when the question needs a second or third kind of tool after the first, in the order to use them; otherwise leave it out. plan: when also is given, one short sentence on how to use the tools together; otherwise leave it out.
Examples: "Look up today's gold price and tell me what three ounces cost." -> {"route": "search", "also": ["calculate"], "plan": "Find today's gold price per ounce, then multiply it by three."} "Will it rain in Seattle tomorrow, and what time is the last ferry to Bainbridge?" -> {"route": "weather", "also": ["search"], "plan": "Get Seattle's forecast for tomorrow, then search the ferry schedule."} "Will Oslo be colder than here on Saturday?" -> {"route": "weather", "also": ["calculate"], "plan": "Get Saturday's forecast for Oslo and for home, then subtract the temperatures."} "What's tomorrow's high in Chicago in Celsius?" -> {"route": "weather", "also": ["calculate"], "plan": "Get Chicago's forecast for tomorrow, then convert the high to Celsius."}
A comparison between places or a figure in other units needs the calculator as well as the forecast."""

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
# A question that needs several tools gets one directive: the routes in order, the plan, then each route's instruction and example call without its heading.
SEVERAL_TOOLS_INSTRUCTION = "This question needs more than one tool. Call each of them, in this order, and answer from what they return; do no arithmetic yourself."

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
MAX_TOOL_ROUNDS = 6
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
# A weather question that also asks for other current facts ("schedules and weather") needs a search as well as the forecast.
OTHER_CURRENT_FACTS_CUE = re.compile(r"\b(schedules?|timetables?|prices?|tickets?|news)\b", re.IGNORECASE)
# A second request joined to the first ("will it rain, and when is the last ferry?"): the rules may see only one of the two, so the model layer is asked too.
SECOND_REQUEST = re.compile(
    r"\b(and|also|then)\s+(what|when|where|which|who|how|is|are|does|do|can|could|will|should|tell me|work out|figure out|convert|compare)\b",
    re.IGNORECASE,
)
EXPLANATION_CUE = re.compile(r"\b(why|explain|what causes|what makes|how (does|do) (rain|snow|weather|the weather))\b", re.IGNORECASE)


def rule_route(text: str) -> RouteDecision | None:
    """Every rule that fires, searching first, then the forecast, then the arithmetic on what they found; None when no rule fires."""
    fired = [*search_reasons(text), *weather_reasons(text)]
    fired.extend(arithmetic_reasons(text, minimum_numbers=1 if any(route == Route.SEARCH for route, _ in fired) else MIN_NUMBERS_FOR_ARITHMETIC))
    if not fired:
        return None
    routes = [route for route, _ in fired]
    return RouteDecision(route=routes[0], also=routes[1:], source="rule", detail="; ".join(reason for _, reason in fired))


def search_reasons(text: str) -> list[tuple[Route, str]]:
    if EXPLICIT_SEARCH.search(text):
        return [(Route.SEARCH, "explicit request to search")]
    other_facts = OTHER_CURRENT_FACTS_CUE.search(text)
    if other_facts and weather_question_cue(text):
        return [(Route.SEARCH, f"weather and '{other_facts.group(0)}'")]
    return []


def weather_reasons(text: str) -> list[tuple[Route, str]]:
    cue = weather_question_cue(text)
    return [(Route.WEATHER, cue)] if cue else []


def arithmetic_reasons(text: str, minimum_numbers: int) -> list[tuple[Route, str]]:
    """Numbers with an arithmetic cue. One number is enough after a search, whose result supplies the other ("the rate times 25,000")."""
    numbers = NUMBER.findall(text)
    cue = ARITHMETIC_CUE.search(text)
    if len(numbers) >= minimum_numbers and cue:
        return [(Route.CALCULATE, f"{len(numbers)} numbers and cue '{cue.group(0)}'")]
    return []


def weather_question_cue(text: str) -> str | None:
    return None if EXPLANATION_CUE.search(text) else forecast_cue(text)


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
        decision = decision_from_classification(await llm.classify(ROUTER_SYSTEM_PROMPT, f"{context}Question: {text}", ROUTE_SCHEMA, policy))
    except Exception as error:  # noqa: BLE001 - a broken router must never block the answer
        decision = RouteDecision(route=Route.ANSWER, source="model", detail=f"router failed, defaulted to answer: {type(error).__name__}: {error}")
    return decision.model_copy(update={"seconds": time.perf_counter() - started})


def decision_from_classification(raw: dict) -> RouteDecision:
    """The model's answer as a decision. A further route that repeats the first, or follows an answer route, is dropped."""
    route = Route(raw["route"])
    also = [] if route == Route.ANSWER else list(dict.fromkeys(Route(extra) for extra in raw.get("also") or [] if Route(extra) != route))
    return RouteDecision(route=route, also=also[:MAX_EXTRA_ROUTES], plan=str(raw.get("plan") or "").strip() if also else "", source="model", detail="model classified")


async def decide_route(llm: LLMClient, conversation: list[Message], policy: AgentPolicy) -> RouteDecision:
    user_messages = [message.content for message in conversation if message.role == Role.USER]
    if not user_messages:
        return RouteDecision(route=Route.ANSWER, source="none", detail="no user message")
    question = user_messages[-1]
    decision = rule_route(question)
    if decision is None:
        return await model_route(llm, question, user_messages[:-1], policy)
    if not SECOND_REQUEST.search(question):
        return decision
    return merged(decision, await model_route(llm, question, user_messages[:-1], policy))


def merged(rule_decision: RouteDecision, model_decision: RouteDecision) -> RouteDecision:
    """The rules' routes first, then any the model adds for the second request, with the model's plan when it added one."""
    routes = list(dict.fromkeys([*rule_decision.tool_routes, *model_decision.tool_routes]))[: 1 + MAX_EXTRA_ROUTES]
    added = len(routes) > len(rule_decision.tool_routes)
    return rule_decision.model_copy(
        update={
            "also": routes[1:],
            "plan": model_decision.plan if added else "",
            "source": "rule+model" if added else "rule",
            "detail": f"{rule_decision.detail}; second request, model added {[route.value for route in routes[len(rule_decision.tool_routes):]]}" if added else rule_decision.detail,
            "seconds": model_decision.seconds,
        }
    )


def route_to_offered_tools(decision: RouteDecision, tool_specs: list[ToolSpec]) -> RouteDecision:
    """The tool server offers weather_forecast only when home has coordinates; without it a weather question is searched like any other place's weather."""
    if Route.WEATHER not in decision.tool_routes or any(spec.name in WEATHER_TOOL_NAMES for spec in tool_specs):
        return decision
    routes = list(dict.fromkeys(Route.SEARCH if route == Route.WEATHER else route for route in decision.tool_routes))
    return decision.model_copy(update={"route": routes[0], "also": routes[1:], "detail": f"{decision.detail}; weather tool not offered, so searched"})


def directive_for(decision: RouteDecision) -> str | None:
    """The directive naming the tools to call, for the per-question block just before the question; None for the answer route."""
    routes = decision.tool_routes
    if not routes:
        return None
    if len(routes) == 1:
        return DIRECTIVES[routes[0]].rstrip()
    return several_tools_directive(routes, decision.plan)


def several_tools_directive(routes: list[Route], plan: str) -> str:
    heading = f"Routing for this question: {', then '.join(route.value.upper() for route in routes)}."
    plan_line = [f"Plan: {plan}"] if plan else []
    instructions = [DIRECTIVES[route].split("\n", 1)[1].rstrip() for route in routes]
    return "\n".join([heading, SEVERAL_TOOLS_INSTRUCTION, *plan_line, *instructions])


def tool_round_cap(decision: RouteDecision | None, configured_rounds: int) -> int:
    """One round per planned tool plus one to answer, never below the configured cap and never above six (design doc v2/04 section 3.3)."""
    planned = len(decision.tool_routes) if decision else 0
    return min(MAX_TOOL_ROUNDS, max(configured_rounds, planned + 1))
