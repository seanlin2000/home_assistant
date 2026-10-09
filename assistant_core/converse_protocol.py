"""The harness's HTTP API in one place: the request the component sends, and the newline-delimited JSON events the harness streams back
(design doc v2/04 section 3.2). Pure pydantic, so the component imports it inside Home Assistant's own Python."""

import json

from pydantic import BaseModel

from assistant_core.models import AgentEvent, AnswerDelta, Done, FillerSpoken, Message, ToolCall, ToolFinished, ToolStarted, Transcript

CONVERSE_PATH = "/v1/converse"
HEALTH_PATH = "/health"
NDJSON_MEDIA_TYPE = "application/x-ndjson"


class ConverseRequest(BaseModel):
    """One question: the conversation so far as Home Assistant's chat log holds it, with the new question as its last user message."""

    conversation_id: str
    conversation: list[Message]
    source: str = "home_assistant"  # how the exchange log labels it: "home_assistant", "benchmark", "smoke"


class HarnessHealth(BaseModel):
    status: str  # "ok" when both dependencies answer, otherwise "degraded"
    llama_server: bool
    tool_server: bool


def event_to_line(event: AgentEvent) -> str:
    """One event as one JSON line, without the trailing newline."""
    if isinstance(event, FillerSpoken):
        body = {"event": "filler", "text": event.text}
    elif isinstance(event, AnswerDelta):
        body = {"event": "answer", "text": event.text}
    elif isinstance(event, ToolStarted):
        body = {"event": "tool_started", "call": event.call.model_dump()}
    elif isinstance(event, ToolFinished):
        body = {"event": "tool_finished", "call": event.call.model_dump(), "seconds": event.seconds, "error": event.error}
    else:
        body = {"event": "done", "transcript": event.transcript.model_dump(mode="json")}
    return json.dumps(body)


def line_to_event(line: str) -> AgentEvent:
    body = json.loads(line)
    kind = body["event"]
    if kind == "filler":
        return FillerSpoken(text=body["text"])
    if kind == "answer":
        return AnswerDelta(text=body["text"])
    if kind == "tool_started":
        return ToolStarted(call=ToolCall(**body["call"]))
    if kind == "tool_finished":
        return ToolFinished(call=ToolCall(**body["call"]), seconds=body["seconds"], error=body.get("error"))
    if kind == "done":
        return Done(transcript=Transcript.model_validate(body["transcript"]))
    raise ValueError(f"unknown harness event {kind!r}")
