"""The two plain HTTP routes the tool server exposes beside /mcp: POST /turns appends a TurnRecord, GET /healthz names the tools."""

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from assistant_core.models import GenerationStats, Message, Role, Transcript
from assistant_core.turn_record import TURNS_ROUTE, turn_record_from_transcript
from web_search_mcp.server import build_server
from web_search_mcp.settings import SearchSettings
from web_search_mcp.turn_log import TurnLog


def sample_record():
    transcript = Transcript(
        model="gemma4:26b",
        system_prompt="You are Jarvis.",
        conversation=[Message(role=Role.USER, content="What is 12 percent of 250?"), Message(role=Role.ASSISTANT, content="It is 30.")],
        model_calls=[GenerationStats(model="gemma4:26b", prompt_tokens=100, output_tokens=10, total_seconds=1.2)],
        final_answer="It is 30.",
        total_seconds=1.5,
    )
    return turn_record_from_transcript(transcript)


def client_for(tmp_path: Path | None) -> httpx.AsyncClient:
    settings = SearchSettings(searxng_url="http://127.0.0.1:1", turns_dir=str(tmp_path) if tmp_path else None)
    server = build_server(settings)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=server.streamable_http_app()), base_url="http://testserver")


@pytest.mark.asyncio
async def test_post_turn_appends_one_line_per_record(tmp_path):
    async with client_for(tmp_path) as client:
        for _ in range(2):
            response = await client.post(TURNS_ROUTE, content=sample_record().model_dump_json(), headers={"content-type": "application/json"})
            assert response.status_code == 204
    today = TurnLog(tmp_path).path_for(datetime.now(UTC).date())
    lines = today.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["user_text"] == "What is 12 percent of 250?"


@pytest.mark.asyncio
async def test_post_turn_rejects_bad_json_and_wrong_shape(tmp_path):
    async with client_for(tmp_path) as client:
        assert (await client.post(TURNS_ROUTE, content=b"not json")).status_code == 400
        response = await client.post(TURNS_ROUTE, json={"hello": "world"})
    assert response.status_code == 400
    assert "TurnRecord" in response.json()["error"]
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_post_turn_without_a_directory_is_503():
    async with client_for(None) as client:
        response = await client.post(TURNS_ROUTE, content=sample_record().model_dump_json())
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_healthz_lists_every_required_tool(tmp_path):
    async with client_for(tmp_path) as client:
        response = await client.get("/healthz")
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["missing"] == []
    assert {"search_and_read", "calculate", "percent"} <= set(body["tools"])
    assert body["turns_dir"] == str(tmp_path)


def test_turn_log_prunes_only_old_day_files(tmp_path):
    log = TurnLog(tmp_path)
    today = date(2026, 9, 7)
    for days_ago in (0, 89, 90, 91, 400):
        log.path_for(today - timedelta(days=days_ago)).write_text("{}\n")
    (tmp_path / "notes.txt").write_text("keep me")
    deleted = log.prune(retention_days=90, today=today)
    assert sorted(path.name for path in deleted) == ["2025-08-03.jsonl", "2026-06-08.jsonl"]
    remaining = sorted(path.name for path in tmp_path.iterdir())
    assert remaining == ["2026-06-09.jsonl", "2026-06-10.jsonl", "2026-09-07.jsonl", "notes.txt"]


def test_turn_log_read_since_returns_records_in_day_order(tmp_path):
    log = TurnLog(tmp_path)
    record = sample_record()
    for day in (date(2026, 9, 1), date(2026, 9, 5)):
        log.path_for(day).write_text(record.model_dump_json() + "\n")
    assert len(log.read_since(date(2026, 9, 1))) == 2
    assert len(log.read_since(date(2026, 9, 2))) == 1
