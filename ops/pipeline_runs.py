"""Pull Home Assistant's recent Assist pipeline runs into a durable file on the laptop (design doc 10 §3.7).

Home Assistant keeps per-stage timings (speech to text, our agent, text to speech) and the transcribed text only in memory and only for the
last handful of runs. `scripts/mini.sh logs` calls this after the rsync so those runs survive:

    uv run python -m ops.pipeline_runs logs/mini/pipeline_runs.jsonl

Runs already in the file are skipped, so the file only grows.
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from ops.ha_client import HomeAssistant
from utils.jsonl_utils import append_jsonl, read_jsonl

PROJECT_DIR = Path(__file__).resolve().parent.parent


class PipelineRun(BaseModel):
    pipeline: str
    run_id: str
    started_at: str
    stages: list[str]
    stt_text: str | None = None
    stt_seconds: float | None = None  # from the end of speech to the transcript
    agent_seconds: float | None = None
    tts_seconds: float | None = None
    total_seconds: float | None = None
    agent_said: str | None = None
    error: str | None = None
    raw_events: list[dict[str, Any]] = Field(default_factory=list)


def seconds_between(start: str, end: str) -> float:
    return round((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds(), 2)


def summarize(pipeline: str, run_id: str, events: list[dict[str, Any]]) -> PipelineRun:
    """Turn Home Assistant's event list for one run into one flat record; the raw events ride along for anything this summary misses."""
    by_type: dict[str, dict[str, Any]] = {event["type"]: event for event in events}
    start = events[0]["timestamp"]
    run = PipelineRun(pipeline=pipeline, run_id=run_id, started_at=start, stages=[event["type"] for event in events], raw_events=events)

    def when(kind: str) -> str | None:
        return by_type[kind]["timestamp"] if kind in by_type else None

    if "stt-end" in by_type:
        run.stt_text = (by_type["stt-end"].get("data") or {}).get("stt_output", {}).get("text")
        speech_end = when("stt-vad-end") or when("stt-start")
        run.stt_seconds = seconds_between(speech_end, when("stt-end")) if speech_end else None
    if "intent-start" in by_type and "intent-end" in by_type:
        run.agent_seconds = seconds_between(when("intent-start"), when("intent-end"))
        output = (by_type["intent-end"].get("data") or {}).get("intent_output") or {}
        run.agent_said = output.get("response", {}).get("speech", {}).get("plain", {}).get("speech")
    if "tts-start" in by_type and "tts-end" in by_type:
        run.tts_seconds = seconds_between(when("tts-start"), when("tts-end"))
    if "run-end" in by_type:
        run.total_seconds = seconds_between(start, when("run-end"))
    if "error" in by_type:
        data = by_type["error"].get("data") or {}
        run.error = f"{data.get('code')}: {data.get('message')}"
    return run


async def pull(ha: HomeAssistant, pipeline_name: str | None, known: set[str]) -> list[PipelineRun]:
    pipelines = (await ha.ws({"type": "assist_pipeline/pipeline/list"}))["pipelines"]
    if pipeline_name:
        pipelines = [pipeline for pipeline in pipelines if pipeline["name"] == pipeline_name]
    new_runs: list[PipelineRun] = []
    for pipeline in pipelines:
        listing = await ha.ws({"type": "assist_pipeline/pipeline_debug/list", "pipeline_id": pipeline["id"]})
        for entry in listing.get("pipeline_runs", []):
            run_id = entry["pipeline_run_id"]
            if run_id in known:
                continue
            detail = await ha.ws({"type": "assist_pipeline/pipeline_debug/get", "pipeline_id": pipeline["id"], "pipeline_run_id": run_id})
            if detail.get("events"):
                new_runs.append(summarize(pipeline["name"], run_id, detail["events"]))
    return new_runs


def main(argv: list[str] | None = None) -> int:
    load_dotenv(PROJECT_DIR / ".env")
    parser = argparse.ArgumentParser(description="Append Home Assistant's recent Assist pipeline runs to a JSON Lines file.")
    parser.add_argument("output", type=Path)
    parser.add_argument("--pipeline", default=None, help="only this pipeline by name (default: all)")
    args = parser.parse_args(argv)
    host = os.environ.get("HA_HOST")
    if not host:
        print("HA_HOST is not set", file=sys.stderr)
        return 2
    known = {run.run_id for run in read_jsonl(args.output, PipelineRun)} if args.output.exists() else set()
    ha = HomeAssistant(host, os.environ.get("HA_TOKEN", ""), os.environ.get("HA_BASE"))
    try:
        new_runs = asyncio.run(pull_and_close(ha, args.pipeline, known))
    except Exception as error:  # noqa: BLE001 - a stopped Home Assistant must not fail the whole log pull
        print(f"pipeline runs: skipped ({type(error).__name__}: {error})")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for run in new_runs:
        append_jsonl(args.output, run)
    print(f"pipeline runs: {len(new_runs)} new, {len(known) + len(new_runs)} total in {args.output}")
    return 0


async def pull_and_close(ha: HomeAssistant, pipeline_name: str | None, known: set[str]) -> list[PipelineRun]:
    try:
        return await pull(ha, pipeline_name, known)
    finally:
        await ha.close()


if __name__ == "__main__":
    sys.exit(main())
