"""Replay hand-written answers through the real agent loop and tool server, so a human (or a model driven by hand) can be scored on the same footing as the candidates.

The scripted answers live in benchmark/manual/<candidate_key>.yaml. Each turn lists the search queries to issue and the final spoken answer; the queries are executed for real
through web_search_mcp, so the transcript carries genuine tool results, and the gates, word cap, and judge treat the record exactly like a model run.
"""

import argparse
import asyncio
from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from rich.console import Console

from assistant_core import agent_loop
from assistant_core.models import AgentPolicy, Completion, Done, GenerationStats, LLMEvent, Message, Role, TextDelta, ToolCall, ToolCallRequest, ToolSpec, Transcript
from assistant_core.tools import McpToolBox
from benchmark.mcp_process import McpServerProcess
from benchmark.records import Candidate, Question, QuestionResult, load_config, load_questions, write_jsonl

CONFIG_PATH = Path("benchmark/config.yaml")
QUESTIONS_PATH = Path("benchmark/questions.yaml")
MANUAL_DIR = Path("benchmark/manual")
console = Console()


class ScriptedCall(BaseModel):
    name: str
    arguments: dict = Field(default_factory=dict)


class ScriptedTurn(BaseModel):
    queries: list[str] = Field(default_factory=list)  # shorthand for search_and_read calls
    calls: list[ScriptedCall] = Field(default_factory=list)  # any other tool calls, e.g. the calculator
    answer: str

    def tool_calls(self) -> list[ToolCall]:
        searches = [ToolCall(id=f"manual_q{index}", name="search_and_read", arguments={"query": query}) for index, query in enumerate(self.queries)]
        others = [ToolCall(id=f"manual_c{index}", name=call.name, arguments=call.arguments) for index, call in enumerate(self.calls)]
        return [*searches, *others]

    def implied_route(self) -> str:
        if self.queries:
            return "search"
        return "calculate" if self.calls else "answer"


class ScriptedQuestion(BaseModel):
    question_id: str
    turns: list[ScriptedTurn]


class ScriptedAnswers(BaseModel):
    candidate_key: str
    answered_by: str
    questions: list[ScriptedQuestion]

    def by_id(self, question_id: str) -> ScriptedQuestion:
        return next(question for question in self.questions if question.question_id == question_id)


class ScriptedAnswerClient:
    """Plays one scripted turn as if it were a model: first the search calls, then the spoken answer."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._turn: ScriptedTurn | None = None
        self._searched = False

    @property
    def model_name(self) -> str:
        return self._model_name

    def load_turn(self, turn: ScriptedTurn) -> None:
        self._turn = turn
        self._searched = False

    async def chat(self, messages: list[Message], tools: list[ToolSpec], policy: AgentPolicy) -> AsyncIterator[LLMEvent]:
        if self._turn is None:
            raise RuntimeError("load_turn must be called before chat")
        calls = self._turn.tool_calls()
        if calls and not self._searched:
            self._searched = True
            async for event in self._tool_events(calls):
                yield event
            return
        yield TextDelta(text=self._turn.answer)
        yield Completion(message=Message(role=Role.ASSISTANT, content=self._turn.answer), stats=self._stats())

    async def classify(self, system_prompt: str, user_text: str, schema: dict) -> dict:
        """The hand-written script is its own router: the route is whatever tools the scripted turn uses."""
        if self._turn is None:
            raise RuntimeError("load_turn must be called before classify")
        return {"route": self._turn.implied_route()}

    async def _tool_events(self, calls: list[ToolCall]) -> AsyncIterator[LLMEvent]:
        for call in calls:
            yield ToolCallRequest(call=call)
        yield Completion(message=Message(role=Role.ASSISTANT, content="", tool_calls=calls), stats=self._stats())

    def _stats(self) -> GenerationStats:
        return GenerationStats(model=self._model_name, total_seconds=0.0, time_to_first_token_seconds=0.0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay hand-written answers through the agent loop and write a results file.")
    parser.add_argument("candidate", help="candidate key; reads benchmark/manual/<key>.yaml")
    parser.add_argument("--date", default=date.today().isoformat(), help="results folder name, default today")
    return parser.parse_args()


def main() -> None:
    asyncio.run(main_async(parse_args()))


async def main_async(args: argparse.Namespace) -> None:
    config = load_config(CONFIG_PATH)
    question_set = load_questions(QUESTIONS_PATH)
    candidate = config.candidate(args.candidate)
    answers = load_answers(MANUAL_DIR / f"{candidate.key}.yaml")
    run_dir = Path(config.services.results_dir) / args.date
    async with McpServerProcess(config.services, run_dir / "cache") as mcp_url:
        async with McpToolBox(mcp_url) as toolbox:
            results = [await replay_question(question, answers.by_id(question.id), candidate, toolbox, config.policy) for question in question_set.questions]
    write_jsonl(run_dir / f"{candidate.key}.jsonl", results)
    console.print(f"wrote {len(results)} results for {candidate.key} (answered by {answers.answered_by})")


def load_answers(path: Path) -> ScriptedAnswers:
    return ScriptedAnswers(**yaml.safe_load(path.read_text()))


async def replay_question(question: Question, scripted: ScriptedQuestion, candidate: Candidate, toolbox: McpToolBox, policy: AgentPolicy) -> QuestionResult:
    if len(scripted.turns) != len(question.turns):
        raise ValueError(f"{question.id}: scripted {len(scripted.turns)} turns, question has {len(question.turns)}")
    client = ScriptedAnswerClient(candidate.model)
    transcripts: list[Transcript] = []
    conversation: list[Message] = []
    for turn_text, scripted_turn in zip(question.turns, scripted.turns):
        client.load_turn(scripted_turn)
        conversation.append(Message(role=Role.USER, content=turn_text))
        transcript = await replay_turn(conversation, client, toolbox, policy)
        transcripts.append(transcript)
        conversation = list(transcript.conversation)
    print_result_line(question, transcripts[-1])
    return QuestionResult(question_id=question.id, candidate_key=candidate.key, model=candidate.model, turns=transcripts)


async def replay_turn(conversation: list[Message], client: ScriptedAnswerClient, toolbox: McpToolBox, policy: AgentPolicy) -> Transcript:
    async for event in agent_loop.run(conversation, client, toolbox, policy):
        if isinstance(event, Done):
            return event.transcript
    raise RuntimeError("agent loop ended without a Done event")


def print_result_line(question: Question, transcript: Transcript) -> None:
    searched = "search" if any(exchange.call.name == "search_and_read" for exchange in transcript.tool_exchanges) else "no search"
    truncated = " [cut by word cap]" if transcript.truncated else ""
    console.print(f"  {question.id:<4} {searched:<9} calls={transcript.tool_call_count} words={len(transcript.final_answer.split())}{truncated}")


if __name__ == "__main__":
    main()
