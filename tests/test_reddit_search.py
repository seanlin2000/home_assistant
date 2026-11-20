"""reddit_search and the agent loop around it: subreddit names as spoken, threads in the web search's order with their top comments, subreddits taking
turns, the past year's threads taking turns with the most relevant, a time range asked of the engine and checked against the threads' dates, Arctic
Shift's refusals retried within the attempts and the time budget, the replies when nothing matches or Reddit never answered, and the router, fillers,
still-trying line, and could-not-reach line around them. Arctic Shift and the shared web search are scripted; no request leaves the machine."""

import asyncio
import time
from typing import Any

import httpx
import pytest
from mcp.server.mcpserver import MCPServer

from assistant_core import agent_loop
from assistant_core.agent_loop import filler_for, without_leading_filler
from assistant_core.models import (
    DEFAULT_REDDIT_FILLER_PHRASES,
    REDDIT_TOOL_NAMES,
    AgentEvent,
    AgentPolicy,
    FillerSpoken,
    Message,
    Role,
    Route,
    RouteDecision,
    ToolCall,
    ToolSpec,
)
from assistant_core.router import directive_for, rule_route
from assistant_core.tool_guards import load_tool_table
from assistant_core.tools import McpToolBox
from reddit_mcp.arctic_shift import ArcticShiftSession, RedditUnavailable
from reddit_mcp.register import REDDIT_TOOL_NAME, UNAVAILABLE_MESSAGE, register_reddit_tools
from reddit_mcp.render import OLD_THREADS_NOTE, threads_text
from reddit_mcp.settings import RedditSettings
from reddit_mcp.threads import DEFAULT_TIME_RANGE, RedditQuery, RedditThread, subreddit_names, threads_answering
from tests.fakes import ScriptedLLM, text_reply, tool_reply
from web_search_mcp.searxng_client import SearchResult

NOW = time.time()
DAY = 86_400
NO_WAITS = RedditSettings(retry_waits_seconds=(0.0, 0.0))
REDDIT_TOOL = ToolSpec(
    name=REDDIT_TOOL_NAME,
    description="reddit",
    input_schema={"type": "object", "properties": {"query": {"type": "string"}, "subreddits": {"type": "array", "items": {"type": "string"}}}, "required": ["query"]},
)


def post(post_id: str, subreddit: str = "FoodNYC", age_days: float = 400, num_comments: int = 5, title: str = "", selftext: str = "") -> dict[str, Any]:
    return {"id": post_id, "subreddit": subreddit, "title": title or f"Thread {post_id}", "selftext": selftext, "score": 10, "num_comments": num_comments, "created_utc": NOW - age_days * DAY}


def thread_url(subreddit: str, post_id: str) -> str:
    return f"https://www.reddit.com/r/{subreddit}/comments/{post_id}/some_title/"


class FakeArcticShift:
    """Answers posts/ids (in its own order, not the order asked) and comments/tree, turning away the first few requests to a path."""

    def __init__(self, archive: list[dict[str, Any]], comments: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self.archive = archive
        self.comments = comments or {}
        self.refusals: dict[str, int] = {}
        self.requests: list[httpx.Request] = []

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path.removeprefix("/api")
        if self.refusals.get(path, 0) > 0:
            self.refusals[path] -= 1
            return httpx.Response(422, json={"data": None, "error": "Timeout. Maybe slow down a bit"})
        if path == "/posts/ids":
            wanted = request.url.params["ids"].split(",")
            return httpx.Response(200, json={"data": [archived for archived in reversed(self.archive) if archived["id"] in wanted]})
        post_id = request.url.params["link_id"].removeprefix("t3_")
        return httpx.Response(200, json={"data": [{"kind": "t1", "data": comment} for comment in self.comments.get(post_id, [])] + [{"kind": "more", "data": {}}]})

    def paths(self) -> list[str]:
        return [request.url.path.removeprefix("/api") for request in self.requests]


class FakeWebSearch:
    """The shared web search as the Reddit tool sees it: results per subreddit named in the query, any age or, under "year", the past year's."""

    def __init__(self, urls_by_subreddit: dict[str, list[str]] | None = None, past_year_urls_by_subreddit: dict[str, list[str]] | None = None, fail: bool = False) -> None:
        self.urls_by_subreddit = urls_by_subreddit or {}
        self.past_year_urls_by_subreddit = past_year_urls_by_subreddit or {}
        self.fail = fail
        self.searches: list[tuple[str, str | None]] = []

    async def search(self, query: str, time_range: str | None = None) -> list[SearchResult]:
        self.searches.append((query, time_range))
        if self.fail:
            raise httpx.ConnectError("SearXNG is down")
        subreddit = query.split()[1].removeprefix("r/")
        urls = (self.past_year_urls_by_subreddit if time_range == "year" else self.urls_by_subreddit).get(subreddit, [])
        return [SearchResult(title="", url=url, snippet="", engines=["brave"], score=1.0) for url in urls]


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.waits: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.waits.append(seconds)
        self.now += seconds


async def find(archive: FakeArcticShift, web: FakeWebSearch, subreddits: list[str] | None = None, time_range: str = DEFAULT_TIME_RANGE, settings: RedditSettings = NO_WAITS) -> list[RedditThread]:
    query = RedditQuery(subreddits=subreddits if subreddits is not None else ["FoodNYC"], query="soup dumplings", time_range=time_range)
    async with ArcticShiftSession(settings, archive.transport()) as session:
        return await threads_answering(query, web, session, settings, NOW)


async def ask_tool(archive: FakeArcticShift, web: FakeWebSearch, **arguments: Any) -> str:
    server = MCPServer("test")
    register_reddit_tools(server, NO_WAITS, web, archive.transport())
    async with McpToolBox(server) as toolbox:
        return await toolbox.call(ToolCall(id="1", name=REDDIT_TOOL_NAME, arguments=arguments))


def ids(threads: list[RedditThread]) -> list[str]:
    return [thread.post.id for thread in threads]


def test_spoken_subreddit_names_become_the_names_reddit_uses() -> None:
    assert subreddit_names(["r/FoodNYC", "r slash nba", "Food NYC", "", "not a sub!", "/r/Broadway"], 5) == ["FoodNYC", "nba", "Broadway"]
    assert subreddit_names(["FoodNYC", "AskNYC", "nyc", "Broadway"], 3) == ["FoodNYC", "AskNYC", "nyc"]


async def test_threads_come_in_the_web_search_order_with_their_best_comments() -> None:
    comments = {"aaaaa": [{"body": "Okay", "score": 5}, {"body": "Nan Xiang", "score": 50}, {"body": "[removed]", "score": 100}, {"body": "Kung Fu", "score": 20}]}
    archive = FakeArcticShift([post("aaaaa"), post("bbbbb"), post("xxxxx", subreddit="AskNYC")], comments)
    web = FakeWebSearch({"FoodNYC": [thread_url("FoodNYC", "aaaaa"), thread_url("AskNYC", "xxxxx"), "https://www.reddit.com/r/FoodNYC/", thread_url("FoodNYC", "bbbbb")]})
    threads = await find(archive, web, time_range="all")
    assert ids(threads) == ["aaaaa", "bbbbb"]
    assert [comment.body for comment in threads[0].comments] == ["Nan Xiang", "Kung Fu", "Okay"]


async def test_the_query_names_the_subreddit_in_words_and_asks_for_the_past_year_and_any_age() -> None:
    web = FakeWebSearch()
    await find(FakeArcticShift([]), web)
    assert web.searches == [("site:reddit.com r/FoodNYC soup dumplings", "year"), ("site:reddit.com r/FoodNYC soup dumplings", None)]


async def test_a_recent_range_asks_the_engine_once_for_that_range() -> None:
    web = FakeWebSearch()
    await find(FakeArcticShift([]), web, time_range="week")
    assert web.searches == [("site:reddit.com r/FoodNYC soup dumplings", "week")]


async def test_recent_threads_and_the_most_relevant_take_turns() -> None:
    archive = FakeArcticShift([post("recn1", age_days=20), post("recn2", age_days=40), post("best1", age_days=500), post("best2", age_days=600)])
    web = FakeWebSearch(
        {"FoodNYC": [thread_url("FoodNYC", "best1"), thread_url("FoodNYC", "recn1"), thread_url("FoodNYC", "best2")]},
        {"FoodNYC": [thread_url("FoodNYC", "recn1"), thread_url("FoodNYC", "recn2")]},
    )
    assert ids(await find(archive, web)) == ["recn1", "best1", "recn2", "best2"]


async def test_threads_older_than_the_range_are_left_out_even_when_the_engine_ignores_it() -> None:
    archive = FakeArcticShift([post("fresh", age_days=100), post("stale", age_days=900), post("weeks", age_days=10)])
    web = FakeWebSearch(
        {"FoodNYC": [thread_url("FoodNYC", "stale"), thread_url("FoodNYC", "fresh"), thread_url("FoodNYC", "weeks")]}, {"FoodNYC": [thread_url("FoodNYC", "stale"), thread_url("FoodNYC", "weeks")]}
    )
    assert ids(await find(archive, web)) == ["weeks", "fresh"]
    assert ids(await find(archive, web, time_range="month")) == ["weeks"]
    assert ids(await find(archive, web, time_range="all")) == ["stale", "weeks", "fresh"]


async def test_subreddits_take_turns_so_one_does_not_crowd_out_another() -> None:
    archive = FakeArcticShift([post("aaaa1"), post("aaaa2"), post("bbbb1", subreddit="AskNYC")])
    web = FakeWebSearch({"FoodNYC": [thread_url("FoodNYC", "aaaa1"), thread_url("FoodNYC", "aaaa2")], "AskNYC": [thread_url("AskNYC", "bbbb1")]})
    assert ids(await find(archive, web, subreddits=["FoodNYC", "AskNYC"])) == ["aaaa1", "bbbb1", "aaaa2"]


async def test_with_no_subreddit_named_the_search_covers_all_of_reddit() -> None:
    web = FakeWebSearch()
    await find(FakeArcticShift([]), web, subreddits=[], time_range="year")
    assert web.searches == [("site:reddit.com soup dumplings", "year")]


async def test_a_failed_web_search_leaves_the_other_searches_threads() -> None:
    class FlakyWebSearch(FakeWebSearch):
        async def search(self, query: str, time_range: str | None = None) -> list[SearchResult]:
            if time_range == "year":
                raise httpx.ConnectError("Brave quota spent")
            return await super().search(query, time_range)

    archive = FakeArcticShift([post("aaaaa")])
    assert ids(await find(archive, FlakyWebSearch({"FoodNYC": [thread_url("FoodNYC", "aaaaa")]}))) == ["aaaaa"]
    assert await find(archive, FakeWebSearch(fail=True)) == []


async def test_a_refused_request_is_retried_after_a_wait() -> None:
    archive = FakeArcticShift([post("aaaaa")])
    archive.refusals["/posts/ids"] = 1
    clock = FakeClock()
    async with ArcticShiftSession(RedditSettings(), archive.transport(), clock.sleep, clock) as session:
        found = await session.posts_by_id(["aaaaa"])
    assert [found_post.id for found_post in found] == ["aaaaa"]
    assert clock.waits == [2.0]
    assert session.retries == 1


async def test_retries_stop_when_the_next_wait_would_pass_the_budget() -> None:
    archive = FakeArcticShift([post("aaaaa")])
    archive.refusals["/posts/ids"] = 99
    clock = FakeClock()
    async with ArcticShiftSession(RedditSettings(total_budget_seconds=6.0), archive.transport(), clock.sleep, clock) as session:
        with pytest.raises(RedditUnavailable, match="after 2 attempts"):
            await session.posts_by_id(["aaaaa"])
    assert clock.waits == [2.0]
    assert archive.paths() == ["/posts/ids", "/posts/ids"]


async def test_a_thread_whose_comments_cannot_be_read_keeps_its_post() -> None:
    archive = FakeArcticShift([post("aaaaa")], {"aaaaa": [{"body": "Nan Xiang", "score": 50}]})
    archive.refusals["/comments/tree"] = 99
    threads = await find(archive, FakeWebSearch({"FoodNYC": [thread_url("FoodNYC", "aaaaa")]}))
    assert ids(threads) == ["aaaaa"] and threads[0].comments == []
    assert "No comments could be read." in threads_text(threads, RedditQuery(subreddits=["FoodNYC"], query="q", time_range="all"), NO_WAITS, NOW)


async def test_the_answer_gives_each_threads_month_votes_post_and_best_comments() -> None:
    old = post("aaaaa", age_days=400, title="Best [dumplings](https://x.com) in Flushing?", selftext="Looking for xiao long bao https://maps.app.goo.gl/abc near Main St")
    archive = FakeArcticShift([old, post("bbbbb", age_days=0.5, title="New dumpling spot")], {"aaaaa": [{"body": "Nan Xiang, get the crab ones", "score": 50}]})
    web = FakeWebSearch({"FoodNYC": [thread_url("FoodNYC", "aaaaa"), thread_url("FoodNYC", "bbbbb")]})
    reply = await ask_tool(archive, web, query="soup dumplings Flushing", subreddits=["r/FoodNYC"])
    posted = time.gmtime(NOW - 400 * DAY)
    assert reply.split("\n") == [
        'Reddit threads for "soup dumplings Flushing" in r/FoodNYC, most relevant first.',
        f"[1] r/FoodNYC, {time.strftime('%B', posted)} {posted.tm_year}, 10 upvotes, 5 comments: Best dumplings in Flushing?",
        "    Post: Looking for xiao long bao near Main St",
        "    Comment (50 upvotes): Nan Xiang, get the crab ones",
        f"[2] r/FoodNYC, {time.strftime('%B', time.gmtime(NOW - DAY / 2))} {time.gmtime(NOW - DAY / 2).tm_year}, votes not counted yet: New dumpling spot",
        "    No comments could be read.",
        OLD_THREADS_NOTE,
    ]


async def test_a_long_answer_is_cut_between_lines_and_keeps_the_note() -> None:
    archive = FakeArcticShift([post(f"aaaa{index}") for index in range(4)], {f"aaaa{index}": [{"body": "word " * 60, "score": 1}] * 4 for index in range(4)})
    threads = await find(archive, FakeWebSearch({"FoodNYC": [thread_url("FoodNYC", f"aaaa{index}") for index in range(4)]}))
    reply = threads_text(threads, RedditQuery(subreddits=["FoodNYC"], query="q", time_range="all"), RedditSettings(max_words=300), NOW)
    assert len(reply.split()) <= 300
    assert reply.endswith(OLD_THREADS_NOTE)
    assert all(line.endswith("word") or not line.startswith("    Comment") for line in reply.split("\n"))


async def test_no_matching_threads_says_so_and_points_to_the_web() -> None:
    reply = await ask_tool(FakeArcticShift([]), FakeWebSearch(), query="ramen", subreddits=["FoodNYC"])
    assert reply == 'No Reddit threads in r/FoodNYC from the past two years matched "ramen". Search the web with search_and_read instead.'


async def test_arctic_shift_never_answering_gives_the_unavailable_answer() -> None:
    archive = FakeArcticShift([post("aaaaa")])
    archive.refusals["/posts/ids"] = 99
    reply = await ask_tool(archive, FakeWebSearch({"FoodNYC": [thread_url("FoodNYC", "aaaaa")]}), query="ramen", subreddits=["FoodNYC"])
    assert reply == UNAVAILABLE_MESSAGE
    assert archive.paths() == ["/posts/ids"] * NO_WAITS.attempts


class RedditToolBox:
    def __init__(self, result: str, delay_seconds: float = 0.0) -> None:
        self._result = result
        self._delay_seconds = delay_seconds

    async def list_tools(self) -> list[ToolSpec]:
        return [REDDIT_TOOL]

    async def call(self, call: ToolCall) -> str:
        await asyncio.sleep(self._delay_seconds)
        return self._result


async def reddit_exchange(tools: RedditToolBox, policy: AgentPolicy | None = None) -> list[AgentEvent]:
    llm = ScriptedLLM([tool_reply("ramen", tool_name=REDDIT_TOOL_NAME), text_reply("People like Ichiran.")])
    conversation = [Message(role=Role.USER, content="What does r/FoodNYC say about ramen?")]
    return [event async for event in agent_loop.run(conversation, llm, tools, policy or AgentPolicy(still_trying_after_seconds=0.05))]


def spoken_fillers(events: list[AgentEvent]) -> list[str]:
    return [event.text for event in events if isinstance(event, FillerSpoken)]


async def test_a_slow_reddit_call_gets_the_still_trying_line_while_it_runs() -> None:
    policy = AgentPolicy(reddit_filler_phrases=["Checking Reddit."], reddit_still_trying_phrases=["Still trying."], still_trying_after_seconds=0.05)
    events = await reddit_exchange(RedditToolBox("Reddit threads for ramen.", delay_seconds=0.3), policy)
    assert [type(event).__name__ for event in events] == ["FillerSpoken", "ToolStarted", "FillerSpoken", "ToolFinished", "AnswerDelta", "Done"]
    assert spoken_fillers(events) == ["Checking Reddit.", "Still trying."]
    assert events[-1].transcript.tool_notices == ["Still trying."]


async def test_a_quick_reddit_call_gets_only_the_reddit_filler() -> None:
    events = await reddit_exchange(RedditToolBox("Reddit threads for ramen."), AgentPolicy(still_trying_after_seconds=5.0))
    assert len(spoken_fillers(events)) == 1 and spoken_fillers(events)[0] in DEFAULT_REDDIT_FILLER_PHRASES


async def test_reddit_never_answering_gets_the_could_not_reach_line_before_the_answer() -> None:
    policy = AgentPolicy(reddit_unavailable_phrases=["I couldn't reach Reddit."], still_trying_after_seconds=5.0)
    events = await reddit_exchange(RedditToolBox(UNAVAILABLE_MESSAGE), policy)
    assert [type(event).__name__ for event in events] == ["FillerSpoken", "ToolStarted", "ToolFinished", "FillerSpoken", "AnswerDelta", "Done"]
    assert spoken_fillers(events)[1] == "I couldn't reach Reddit."


async def test_a_comment_quoting_the_error_does_not_trigger_the_could_not_reach_line() -> None:
    events = await reddit_exchange(RedditToolBox(f"Reddit threads for ramen.\n    Comment (3 upvotes): {UNAVAILABLE_MESSAGE}"), AgentPolicy(still_trying_after_seconds=5.0))
    assert len(spoken_fillers(events)) == 1


def test_every_reddit_line_is_dropped_from_a_replayed_answer() -> None:
    policy = AgentPolicy()
    spoken = f"{policy.reddit_filler_phrases[0]}\n\n{policy.reddit_still_trying_phrases[0]}\n\n{policy.reddit_unavailable_phrases[0]}\n\nPeople like Ichiran."
    assert without_leading_filler(Message(role=Role.ASSISTANT, content=spoken), policy.every_filler_phrase).content == "People like Ichiran."


def test_reddit_calls_get_the_reddit_filler() -> None:
    assert REDDIT_TOOL_NAMES == {REDDIT_TOOL_NAME}
    assert filler_for(REDDIT_TOOL_NAME, AgentPolicy()) in DEFAULT_REDDIT_FILLER_PHRASES


@pytest.mark.parametrize(
    "question",
    [
        "What does Reddit say about Via Carota?",
        "What does r/nba say about the Knicks' record?",
        "Check r slash FoodNYC for ramen",
        "What are redditors saying about the new subway fares?",
        "Look up what the Broadway subreddit thinks of Hadestown tickets",
    ],
)
def test_naming_reddit_routes_to_reddit_alone(question: str) -> None:
    decision = rule_route(question)
    assert decision is not None and decision.tool_routes == [Route.REDDIT], question


@pytest.mark.parametrize("question", ["Best soup dumplings in Flushing?", "Is Hadestown worth seeing?", "Do you want coffee and/or tea?"])
def test_questions_that_do_not_name_reddit_stay_off_the_reddit_route(question: str) -> None:
    decision = rule_route(question)
    assert decision is None or Route.REDDIT not in decision.tool_routes, question


def test_the_reddit_directive_names_the_tool_and_the_tool_table_marks_it_untrusted() -> None:
    assert "reddit_search(" in directive_for(RouteDecision(route=Route.REDDIT, source="rule"))
    rule = load_tool_table().tools[REDDIT_TOOL_NAME]
    assert (rule.tier.value, rule.marks_untrusted) == ("read_public", True)
    assert set(AgentPolicy().reddit_still_trying_phrases + AgentPolicy().reddit_unavailable_phrases) <= set(AgentPolicy().every_filler_phrase)
