"""The exchange dashboard: sources are split and scored against the answer, steps land on one time axis, pipeline runs find their exchange, and the
API serves a day's exchanges only to names of this Mac (design doc v2/13)."""

import json
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest

from assistant_core.converse_protocol import ConverseRequest
from assistant_core.exchange_record import ExchangeRecord, exchange_record_from_transcript
from assistant_core.models import AgentEvent, AnswerDelta, Done, FillerSpoken, GenerationStats, Message, Role, RouteDecision, ToolCall, ToolCallRecord, Transcript
from assistant_service.exchange_log import ExchangeArchive, ExchangeLog, TraceLog
from dashboard.app import Converse, build_app
from dashboard.evidence import distinctive_terms, tool_evidence
from dashboard.exchange_views import ExchangeStore
from dashboard.pipeline_collector import PipelineRunCollector
from dashboard.pipeline_match import matching_run
from dashboard.timeline import Lane, build_timeline
from ops.pipeline_runs import PipelineRun, PipelineRunLog, summarize
from utils.jsonl_utils import append_jsonl

QUESTION = "Who won the World Series in 1995?"
ANSWER = "The Atlanta Braves won it, beating the Cleveland Indians."
SEARCH_RESULT = """<untrusted source="search_and_read">
Read 1 of 2 results for "1995 World Series".

[1] 1995 World Series - Wikipedia
URL: https://en.wikipedia.org/wiki/1995_World_Series
The Atlanta Braves defeated the Cleveland Indians four games to two.

[2] 1995 MLB season (not read)
The season was shortened by the strike.

If these sources do not answer the question, say plainly that you could not find it.
</untrusted>"""
ALLOWED_HOSTS = ["mac.lan:8775"]


def search_transcript() -> Transcript:
    call = ToolCall(id="call_1", name="search_and_read", arguments={"query": "1995 World Series"})
    return Transcript(
        model="small",
        system_prompt="You are a voice assistant.",
        conversation=[
            Message(role=Role.USER, content="Hello"),
            Message(role=Role.ASSISTANT, content="Hi."),
            Message(role=Role.USER, content=QUESTION),
            Message(role=Role.ASSISTANT, thinking="A past result; search.", tool_calls=[call]),
            Message(role=Role.TOOL, content=SEARCH_RESULT, tool_call_id="call_1", tool_name="search_and_read"),
            Message(role=Role.ASSISTANT, content=ANSWER),
        ],
        tool_call_records=[ToolCallRecord(round_index=0, call=call, result=SEARCH_RESULT, seconds=2.0, started_seconds=1.5)],
        model_calls=[
            GenerationStats(model="small", prompt_tokens=900, output_tokens=20, total_seconds=1.0, prompt_eval_seconds=0.4, generation_seconds=0.5, started_seconds=0.5),
            GenerationStats(model="small", prompt_tokens=1400, cached_prompt_tokens=900, output_tokens=15, total_seconds=1.5, started_seconds=3.5),
        ],
        route=RouteDecision(route="search", source="rule", seconds=0.1, started_seconds=0.0),
        filler_text="Let me look that up.",
        final_answer=ANSWER,
        total_seconds=5.0,
        time_to_first_spoken_seconds=1.4,
    )


def pipeline_run(intent_started: datetime, intent_input: str = QUESTION, conversation_id: str = "conv-1", run_id: str = "run-1") -> PipelineRun:

    def stamp(offset: float) -> str:
        return (intent_started + timedelta(seconds=offset)).isoformat()

    events = [
        {"type": "run-start", "timestamp": stamp(-3), "data": {}},
        {"type": "stt-vad-end", "timestamp": stamp(-1), "data": {}},
        {"type": "stt-end", "timestamp": stamp(-0.2), "data": {"stt_output": {"text": intent_input}}},
        {"type": "intent-start", "timestamp": stamp(0), "data": {"intent_input": intent_input, "conversation_id": conversation_id}},
        {"type": "intent-end", "timestamp": stamp(5), "data": {}},
        {"type": "tts-start", "timestamp": stamp(1.5), "data": {}},
        {"type": "tts-end", "timestamp": stamp(6), "data": {}},
    ]
    return summarize("Jarvis", run_id, events)


def test_search_results_split_into_sources_starred_by_the_answer_words_they_hold() -> None:
    evidence = tool_evidence(SEARCH_RESULT, ANSWER, QUESTION)
    assert evidence.header == 'Read 1 of 2 results for "1995 World Series".'
    assert evidence.footer.startswith("If these sources do not answer")
    first, second = evidence.sources
    assert (first.rank, first.site, first.url, first.read, first.starred) == (1, "en.wikipedia.org", "https://en.wikipedia.org/wiki/1995_World_Series", True, True)
    assert first.text == "The Atlanta Braves defeated the Cleveland Indians four games to two."
    assert (second.title, second.read, second.starred) == ("1995 MLB season", False, False)


def test_a_result_without_numbered_sources_is_one_source() -> None:
    evidence = tool_evidence("30", "Twelve percent of 250 is 30.", "What is 12 percent of 250?")
    assert [(source.rank, source.text, source.starred) for source in evidence.sources] == [(None, "30", True)]


def test_answer_words_the_question_already_used_do_not_count() -> None:
    assert distinctive_terms(ANSWER, QUESTION) == ["atlanta", "braves", "beating", "cleveland", "indians"]


def test_stamped_steps_sit_where_they_ran_with_speech_on_either_side() -> None:
    record = exchange_record_from_transcript(search_transcript())
    timeline = build_timeline(record, pipeline_run(datetime.fromisoformat("2026-10-11T12:00:00+00:00")))
    placed = [(bar.lane, bar.start, bar.seconds) for bar in timeline.bars]
    assert placed == [
        (Lane.SPEECH, -1.0, 0.8),
        (Lane.ROUTER, 0.0, 0.1),
        (Lane.MODEL, 0.5, 1.0),
        (Lane.TOOL, 1.5, 2.0),
        (Lane.MODEL, 3.5, 1.5),
        (Lane.SPEECH, 1.5, 4.5),
    ]
    assert not timeline.approximate
    assert (timeline.bars[2].read_seconds, timeline.bars[2].write_seconds) == (0.4, 0.5)


def test_unstamped_records_are_laid_end_to_end_and_marked_approximate() -> None:
    record = exchange_record_from_transcript(search_transcript())
    for step in [record.route, *record.model_calls, *record.tool_calls]:
        step.started_seconds = None
    timeline = build_timeline(record, None)
    assert [(bar.lane, bar.start) for bar in timeline.bars] == [(Lane.ROUTER, 0.0), (Lane.MODEL, 0.1), (Lane.TOOL, 1.1), (Lane.MODEL, 3.1)]
    assert timeline.approximate


def recorded(conversation_id: str, recorded_at: str) -> ExchangeRecord:
    return exchange_record_from_transcript(search_transcript(), recorded_at=datetime.fromisoformat(recorded_at)).model_copy(update={"conversation_id": conversation_id})


def test_a_pipeline_run_matches_by_question_within_two_minutes() -> None:
    record = recorded("", "2026-10-11T12:00:05+00:00")
    started = datetime.fromisoformat("2026-10-11T12:00:00+00:00")
    assert matching_run(record, [pipeline_run(started)]).run_id == "run-1"
    assert matching_run(record, [pipeline_run(started - timedelta(minutes=5))]) is None
    assert matching_run(record, [pipeline_run(started, intent_input="What time is it?")]) is None


def test_a_run_matching_conversation_and_question_beats_a_closer_one_matching_only_the_question() -> None:
    record = recorded("conv-1", "2026-10-11T12:00:05+00:00")
    started = datetime.fromisoformat("2026-10-11T12:00:00+00:00")
    runs = [pipeline_run(started, conversation_id="conv-other", run_id="closer"), pipeline_run(started - timedelta(seconds=30), run_id="same-conversation")]
    assert matching_run(record, runs).run_id == "same-conversation"


def seeded_store(tmp_path: Path) -> tuple[ExchangeStore, ExchangeRecord]:
    records, traces, runs = ExchangeLog(tmp_path / "exchanges"), TraceLog(tmp_path / "traces"), PipelineRunLog(tmp_path / "pipeline_runs")
    transcript = search_transcript()
    record = ExchangeArchive(records, traces).keep(ConverseRequest(conversation_id="conv-1", conversation=transcript.conversation[:3]), transcript)
    runs.append(pipeline_run(datetime.fromisoformat(record.recorded_at) - timedelta(seconds=record.total_seconds)))
    append_jsonl(records.path_for(datetime.fromisoformat(record.recorded_at).date()), recorded("", record.recorded_at).model_copy(update={"user_text": "older"}))
    return ExchangeStore(records, traces, runs), record


def client_for(store: ExchangeStore, converse: Converse | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=build_app(store, ALLOWED_HOSTS, converse=converse)), base_url="http://mac.lan:8775")


async def test_the_api_lists_a_day_and_opens_an_exchange_with_its_trace_and_speech(tmp_path: Path) -> None:
    store, record = seeded_store(tmp_path)
    day = record.recorded_at[:10]
    async with client_for(store) as client:
        assert (await client.get("/api/days")).json() == [{"day": day, "exchanges": 2}]
        assert (await client.get("/api/latest")).json()["user_text"] == "older"
        assert [summary["user_text"] for summary in (await client.get(f"/api/days/{day}/exchanges")).json()] == [QUESTION, "older"]
        detail = (await client.get(f"/api/days/{day}/exchanges/0")).json()
    assert detail["has_trace"] and detail["filler_text"] == "Let me look that up."
    assert [message["content"] for message in detail["earlier_messages"]] == ["Hello", "Hi."]
    assert detail["turns"][0]["thinking"] == "A past result; search."
    assert detail["turns"][0]["tools"][0]["evidence"]["sources"][0]["starred"]
    assert detail["speech"]["heard"] == QUESTION
    assert detail["summary"]["model"] == "small"


async def test_an_exchange_without_a_trace_still_shows_its_tool_calls(tmp_path: Path) -> None:
    store, record = seeded_store(tmp_path)
    async with client_for(store) as client:
        detail = (await client.get(f"/api/days/{record.recorded_at[:10]}/exchanges/1")).json()
        missing = await client.get(f"/api/days/{record.recorded_at[:10]}/exchanges/9")
    assert not detail["has_trace"]
    assert [(card["name"], card["result"], card["result_chars"]) for card in detail["turns"][0]["tools"]] == [("search_and_read", None, len(SEARCH_RESULT))]
    assert missing.status_code == 404


async def test_other_host_names_and_other_sites_pages_are_turned_away(tmp_path: Path) -> None:
    store, _record = seeded_store(tmp_path)
    async with client_for(store) as client:
        assert (await client.get("/api/days", headers={"host": "evil.example:8775"})).status_code == 421
        assert (await client.get("/api/days", headers={"origin": "http://evil.example"})).status_code == 421
        assert (await client.get("/api/days", headers={"origin": "http://mac.lan:8775"})).status_code == 200
        assert (await client.get("/")).status_code == 200


async def test_the_collector_keeps_each_new_run_once(tmp_path: Path) -> None:
    log = PipelineRunLog(tmp_path / "pipeline_runs")
    started = datetime.fromisoformat("2026-10-11T12:00:00+00:00")
    offered = [pipeline_run(started, run_id="run-1"), pipeline_run(started, run_id="run-2")]

    async def pull_new_runs(known: set[str]) -> list[PipelineRun]:
        return [run for run in offered if run.run_id not in known]

    collector = PipelineRunCollector(log, pull_new_runs)
    assert await collector.collect() == 2
    assert await collector.collect() == 0
    assert [json.loads(line)["run_id"] for path in log.directory.iterdir() for line in path.read_text().splitlines()] == ["run-1", "run-2"]


async def test_a_collector_failure_is_logged_once_until_it_recovers(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    async def unreachable(_known: set[str]) -> list[PipelineRun]:
        raise OSError("no route to host")

    collector = PipelineRunCollector(PipelineRunLog(tmp_path / "pipeline_runs"), unreachable)
    for _ in range(3):
        await collector.collect_logging_failures()
    assert [record.getMessage() for record in caplog.records] == ["pipeline runs not collected: OSError: no route to host"]


class RecordingHarness:
    """Stands in for HarnessClient.converse: answers with a filler and one word, or fails as an unreachable harness does."""

    def __init__(self, reachable: bool) -> None:
        self.reachable = reachable
        self.requests: list[ConverseRequest] = []

    async def converse(self, request: ConverseRequest) -> AsyncIterator[AgentEvent]:
        self.requests.append(request)
        if not self.reachable:
            raise httpx.ConnectError("connection refused")
        yield FillerSpoken(text="One moment.")
        yield AnswerDelta(text="Canberra.")
        yield Done(transcript=Transcript(model="small", system_prompt="", conversation=request.conversation, final_answer="Canberra."))


ASKED = {"conversation_id": "dashboard-1", "conversation": [{"role": "user", "content": "Capital of Australia?"}], "source": "home_assistant"}


async def test_the_chat_box_streams_the_harness_events_and_labels_the_exchange(tmp_path: Path) -> None:
    harness = RecordingHarness(reachable=True)
    async with client_for(seeded_store(tmp_path)[0], harness.converse) as client:
        response = await client.post("/api/ask", json=ASKED, headers={"origin": "http://mac.lan:8775"})
    assert [json.loads(line)["event"] for line in response.text.splitlines()] == ["filler", "answer", "done"]
    assert harness.requests[0].source == "dashboard"


async def test_an_unreachable_harness_ends_the_stream_with_its_reason(tmp_path: Path) -> None:
    async with client_for(seeded_store(tmp_path)[0], RecordingHarness(reachable=False).converse) as client:
        response = await client.post("/api/ask", json=ASKED)
    assert json.loads(response.text.splitlines()[-1]) == {"event": "error", "message": "ConnectError: connection refused"}


async def test_the_chat_box_is_off_without_the_harness_key_and_refuses_other_sites(tmp_path: Path) -> None:
    store = seeded_store(tmp_path)[0]
    async with client_for(store) as client:
        assert (await client.post("/api/ask", json=ASKED)).status_code == 503
    async with client_for(store, RecordingHarness(reachable=True).converse) as client:
        assert (await client.post("/api/ask", json=ASKED, headers={"origin": "http://evil.example"})).status_code == 421
