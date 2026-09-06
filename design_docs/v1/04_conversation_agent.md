# 04. Conversation agent

## 1. Purpose

The loop that turns a transcribed question into a spoken answer. It holds the persona and brevity rules, decides how to present tool use to the listener, runs tools, and tells Home Assistant to keep the microphone open for a follow-up. It lives in two layers: `assistant_core`, a plain Python package with no Home Assistant dependency that the benchmark also runs, and `studio_assistant`, a thin Home Assistant custom component that adapts the core to Home Assistant's conversation API. Writing our own agent rather than using Home Assistant's stock Ollama agent is what makes the filler sentence, the brevity, and the follow-up behavior deterministic.

## 2. Diagram

```
                     Home Assistant OS (VM)                                    native macOS
 ┌────────────────────────────────────────────────────────────────┐
 │ Assist pipeline                                                 │
 │   STT text ──▶ intent matcher ──miss──▶ studio_assistant        │
 │                    │ hit                 (custom component)     │
 │                    ▼                        │                   │
 │              built-in handler               │ ConversationEntity.async_process(user_input, chat_log)
 │              (music, weather)               ▼                   │
 │                                   ┌───────────────────────┐    │
 │                                   │ HA adapter             │    │
 │                                   │  chat_log ⇄ core turns │    │
 │                                   │  stream deltas to TTS  │    │
 │                                   │  continue_conversation │    │
 │                                   └──────────┬────────────┘    │
 └──────────────────────────────────────────────┼─────────────────┘
                                                │ same package, same code as the benchmark
                                                ▼
        assistant_core.agent_loop.run(conversation, llm, tools, policy)
        ┌───────────────────────────────────────────────────────────────────────────────────┐
        │ 1. messages = [system prompt] + this conversation's turns (+ memory.get_context()) │
        │ 2. stream = llm.chat(messages, tools, temperature, think=False)                    │──▶ Ollama
        │ 3. for each delta:                                                                 │
        │      text        → yield to caller (HA speaks it as it arrives)                    │
        │      tool_call   → yield FILLER sentence immediately ("Let me pull some sources.") │
        │                    result = tools.call(name, args)   ────────────────────────────────▶ web_search_mcp
        │                    append tool result; go to 2 (max 4 rounds)                      │
        │ 4. final answer complete → policy: continue_conversation = True                    │
        │ 5. transcript (turns, tool calls, excerpts, timings) returned for logging/benchmark │
        └───────────────────────────────────────────────────────────────────────────────────┘
```

## 3. How it works, step by step

1. Home Assistant's pipeline has already turned speech into text and tried its built-in intents. Music and weather never reach us. Everything else arrives as `ConversationInput` with the text, a conversation id, and a `ChatLog` holding the earlier turns of this conversation.
2. The adapter converts the chat log into the core's plain turn list and calls `agent_loop.run`.
3. The core builds the message list: the shared system prompt (persona "Jarvis", English, one to three sentences, lead with the answer, no lists or URLs aloud, when to search), then the turns. `memory.get_context()` is called and, in v1, returns nothing; this is the seam for persistent memory later.
4. The core streams from the model. Text deltas are yielded upward immediately; the adapter writes them into the chat log as streaming content, and Home Assistant's text-to-speech starts on the first complete sentence.
5. If the model emits a tool call instead, the core first yields a filler sentence chosen from a short list ("Let me pull some sources on that.", "One moment, checking the web."). Because it is yielded before the tool runs, the listener hears it within a second of finishing their question. Then the tool is executed through the MCP client, its result appended as a tool message, and the model is called again. At most four tool rounds.
6. When the final answer finishes, the adapter returns a `ConversationResult` with `continue_conversation=True`, which tells the puck to reopen the microphone for a few seconds without the wake word.
7. The full transcript, including tool calls, retrieved excerpts, and timings, is returned. In production it is logged at debug level; in the benchmark it is the record that gets judged.

## 4. Why two layers

| Layer | Depends on | Tested with | Used by |
|---|---|---|---|
| `assistant_core` | `ollama`, `anthropic`, `mcp`, `pydantic` | plain pytest, mocked model and tools | benchmark harness, `studio_assistant` |
| `studio_assistant` | Home Assistant | `pytest-homeassistant-custom-component` | Home Assistant at runtime |

The benchmark must exercise exactly the code the product runs, or it measures the wrong thing. Keeping the loop free of Home Assistant imports makes that possible and keeps the fast unit tests fast.

## 5. Behaviors the agent owns

- **Brevity.** The system prompt asks for one to three sentences and the answer first. The agent also enforces a soft cap: if a response runs past a word budget, the remainder is dropped after the current sentence, and the model is told in the system prompt that it can offer more detail if asked.
- **Filler before tools.** Deterministic, in code, not left to the model.
- **Follow-up.** `continue_conversation=True` after every answer. A follow-up arrives as a new `async_process` call with the same conversation id and the chat log already holding the prior turns, which is how the two-turn benchmark question works too.
- **Search restraint.** The system prompt tells the model when to search (current facts, prices, schedules, anything after its training cutoff, anything it is unsure about) and when not to (arithmetic, explanations, opinions).
- **Memory seam.** `memory.py` defines `get_context(conversation) -> str` and `remember(conversation) -> None` with a no-op implementation. Persistent memory later means swapping the implementation, not rewriting the loop.

## 6. Packages and what they do for us

| Package | Role in the business logic |
|---|---|
| `ollama` | `OllamaClient` streams chat completions with tool schemas from the local model. |
| `anthropic` | `AnthropicClient` runs the same loop against a frontier model for the benchmark baseline. Not used in production. |
| `mcp` (client) | Connects to `web_search_mcp`, lists tools, converts their schemas into the shape each provider expects, executes calls. |
| `pydantic` | Typed `Turn`, `ToolCall`, `Transcript`, and `AgentPolicy` (temperature, max tool rounds, word budget, filler phrases). |
| Home Assistant `conversation` platform | `ConversationEntity`, `ChatLog`, `ConversationResult`, streaming content deltas, `continue_conversation`. The adapter is written against these. |
| `pytest-homeassistant-custom-component` | Boots a minimal Home Assistant in tests so the adapter can be exercised without the VM. |

## 7. Configuration we control

Set through the component's UI config flow and stored by Home Assistant: Ollama URL and model tag, MCP server URL, persona name, temperature, word budget, filler phrases, follow-up on or off. `assistant_core` reads the same fields from a small config object so the benchmark can set them from `benchmark/config.yaml`.

## 8. Failure modes

- **Model returns a tool call in plain text instead of the structured field.** Treated as no tool call. Logged. Small models do this; the benchmark surfaces which ones.
- **Tool server down.** The core yields "I can't reach the web right now" and answers from knowledge with an explicit caveat rather than failing the turn.
- **Model loops on tools.** Hard cap of four rounds, then the model is asked to answer with what it has.
- **Answer too long for a spoken reply.** Soft cap after the current sentence.
- **Home Assistant API change.** The conversation platform has evolved monthly through 2025 and 2026. The component pins the Home Assistant version it is tested against; bumps go through the test suite first.
- **Streaming and text-to-speech.** If the chosen TTS service does not support streaming, Home Assistant waits for the full answer before speaking and the filler sentence loses most of its value. Verified in the voice pipeline doc's checklist.

## 9. Concepts for newcomers

**Agent loop.** The pattern "call the model, if it asks for a tool run it and call again, else return the answer." Everything called an agent is some version of this loop plus policy around it.

**System prompt.** Instructions placed before the conversation that the model treats as standing orders: who it is, how long to answer, when to use tools. It is the main lever on behavior short of changing the model.

**Streaming.** Receiving the answer token by token as it is generated rather than waiting for the whole thing. For voice it means speech can start after the first sentence.

**Conversation id and chat log.** Home Assistant groups turns into a conversation and hands the agent the history each time, so the agent itself stores nothing between calls. Statelessness makes the component simple and the benchmark reproducible.

**Custom component.** A Python package dropped into Home Assistant's `custom_components/` folder that Home Assistant loads at startup. It declares its Python dependencies in `manifest.json`, and Home Assistant installs them into its own environment inside the VM.

**Deterministic versus model-driven behavior.** Anything the product must do every time, like the filler sentence or reopening the microphone, belongs in code. Anything that needs judgment, like whether to search, belongs to the model with guidance in the prompt.

## 10. Sources

- Home Assistant conversation entity developer docs: [developers.home-assistant.io/docs/core/entity/conversation](https://developers.home-assistant.io/docs/core/entity/conversation)
- Home Assistant chat log and LLM API for conversation agents: [developers.home-assistant.io/docs/core/llm](https://developers.home-assistant.io/docs/core/llm/)
- Home Assistant streaming TTS: [home-assistant.io/integrations/tts](https://www.home-assistant.io/integrations/tts/)
- Home Assistant "Voice chapter 10" (continue conversation, ask question): [home-assistant.io blog](https://www.home-assistant.io/blog/2025/06/25/voice-chapter-10/)
- Ollama chat API with tools: [github.com/ollama/ollama/blob/main/docs/api.md](https://github.com/ollama/ollama/blob/main/docs/api.md)
- pytest-homeassistant-custom-component: [github.com/MatthewFlamm/pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component)

## 11. As built, 2026-09-05

- `assistant_core/models.py` holds the typed vocabulary: `Message` (with `provider_payload` so Anthropic thinking and tool-use blocks can be echoed back unchanged), `ToolCall`, `ToolSpec`, `AgentPolicy`, the model-client events (`TextDelta`, `ToolCallRequest`, `MalformedToolCall`, `Completion`), the agent events (`FillerSpoken`, `ToolStarted`, `ToolFinished`, `AnswerDelta`, `Done`), and `Transcript`.
- `agent_loop.run(conversation, llm, tools, policy, memory)` is an async generator. The filler sentence is yielded the moment the first tool call arrives, before the tool runs. Tool failures are turned into a notice the model sees rather than an exception. At the tool-round cap the pending calls get a "tool limit reached" notice and the model is asked once more to answer.
- The spoken word cap is applied to the stream: past the budget, speech stops at the end of the current sentence and `Transcript.truncated` is set. `spoken_text` is what the listener heard across the whole turn; `final_answer` is the model's last message in full.
- `llm_client.OllamaClient` streams through the `ollama` package with `think` passed only when the candidate config sets it, and retries once without it for model families that reject the switch. `llm_client.AnthropicClient` uses `beta.messages.stream` with adaptive thinking and the server-side refusal fallback, and records the model that actually answered.
- `tools.McpToolBox` wraps the MCP client; `memory.NoMemory` is the v1 memory implementation.
- The Home Assistant adapter (`custom_components/studio_assistant`) is not built yet; it belongs to Phase 2.

## 12. As built, 2026-09-06: the question router

Pass 1 of the benchmark showed two failure patterns the model alone did not fix: local models answered implicit "current fact" questions from memory instead of searching, and they set up arithmetic correctly and then miscomputed it. The tool descriptions and the system prompt are the only levers a model reads, and Ollama has no way to force a tool call, so the loop now decides for the model before it speaks.

```
 user text ──▶ rule layer (regex, 0 ms)
               │  "search the web", "look up", "find me the latest" ─▶ search
               │  two or more numbers + an arithmetic cue           ─▶ calculate
               │  nothing matched
               ▼
             model layer (one structured-output call, temperature 0, JSON {"route": ...})
               │  Ollama: chat(format=<json schema>, think=False)   Anthropic: forced tool_choice
               ▼
             RouteDecision(route, source="rule"|"model", detail, seconds)  ── recorded on the Transcript
               │
               ├─ search    ─▶ append "[Assistant note: ... call search_and_read before answering ...]" to the user message
               ├─ calculate ─▶ append "[Assistant note: ... call the calculator tools for every number ...]"
               └─ answer    ─▶ message unchanged
                                                    ▼
                                    normal loop: model ─▶ tools ─▶ model ─▶ spoken answer
```

Design rules:

- **Rules only fire when they cannot be wrong.** The explicit-search pattern needs an imperative ("search for", "look up", "find me the latest"); a noun like "web search" does not count. The arithmetic pattern needs at least two numbers and a cue such as a percent sign, "per month", "watts", or "mortgage". A test asserts that no rule fires wrongly on any benchmark question; on question set 1.2 rules decide 15 of 28 questions.
- **The model layer is the same model classifying its own question.** It costs one short call (about 10 output tokens, 1.1 s on Gemma 4 E4B) before the first real call. The request must use the same `num_ctx` as the chat calls: Ollama reloads a model whose context length changes, and the first pass-2 attempt paid about 5 s twice per question for exactly that reason before the fix. It is measured separately in the report because it may or may not beat the tool descriptions.
- **A broken router never blocks an answer.** Any exception in the model layer yields the answer route with the error in `detail`.
- **The directive is visible in the transcript.** It is appended to the user message, so the judge sees it; the rubric tells the judge it came from the harness. The `route_questions` policy flag turns the whole layer off.

Packages: `re` for the rule layer; `ollama`'s `format` argument (a JSON schema the server constrains decoding to) for the local model layer; the Anthropic SDK's `tool_choice={"type": "tool"}` for the baseline. Code: `assistant_core/router.py`, the `classify` method on each client, and four lines in `agent_loop.run`.

## 13. As built, 2026-09-06: the component running inside Home Assistant

The `studio_assistant` component is deployed and answering in the Home Assistant OS VM (core 2026.9.1). Verified through `POST /api/conversation/process` against `conversation.studio_assistant`: a plain question (answered from the model, 35 s on the first call while Ollama loaded the model), a percentage question (calculator tool, 6 s), an explicit web search (search tool through the MCP server on the Mac, 19 s), a compounding question (`growth_schedule`, 17 s), and a follow-up that correctly recalled the first question of the conversation. `continue_conversation` is true on every reply, so the microphone stays open.

```
 Home Assistant VM (192.168.1.156)                         Mac (192.168.1.152)
 ┌──────────────────────────────────────────────┐          ┌────────────────────────────────┐
 │ conversation.studio_assistant                │ HTTP     │ Ollama :11434  gemma4:e4b-it-qat│
 │   conversation.py  ─▶ agent_loop.run(...)    │─────────▶│                                │
 │   vendor/assistant_core/                     │          ├────────────────────────────────┤
 │     router ─▶ llm_client (ollama) ─▶ loop    │ MCP/HTTP │ web_search_mcp :8765/mcp       │
 │     mcp_http.HttpMcpToolBox (httpx only)     │─────────▶│   search tools + calculator    │
 └──────────────────────────────────────────────┘          └────────────────────────────────┘
```

Three things had to change once the code ran inside Home Assistant's own Python rather than our venv:

- **`tools.py` imports `mcp` lazily.** Home Assistant ships `mcp==1.26.0` for its built-in MCP integration; our venv has `mcp` 2.1.1, whose `mcp.client.client.Client` does not exist in 1.x. The component never uses `McpToolBox` (it uses the httpx-only `HttpMcpToolBox`), but `agent_loop` imports `tools` for the `ToolBox` protocol, so the module-level import made the whole component fail to load with `ModuleNotFoundError: No module named 'mcp.client.client'`. The import now happens inside `McpToolBox.__aenter__`, and `render_tool_result` duck-types the result instead of importing the `mcp` types.
- **The Ollama client is built off the event loop.** Creating `ollama.AsyncClient` creates an `httpx.AsyncClient`, which loads the CA bundle from disk; Home Assistant flags that as a blocking call in the event loop. `conversation.py` constructs it with `hass.async_add_executor_job`.
- **The filler sentence depends on the tool.** A calculator call used to say "Let me pull some sources on that." `AgentPolicy` now has `calculate_filler_phrases` ("Let me work that out.", "One second, doing the math.") and `agent_loop.filler_for` picks the list by whether the first tool of the turn is in `SEARCH_TOOL_NAMES`, which moved to `assistant_core.models` so the benchmark and the loop share one definition.

Deployment is `scripts/deploy_component.py`: it stages the component with `assistant_core` vendored under `vendor/` (minus `anthropic_client.py`), mounts the VM's `config` share over SMB (the Samba add-on), copies the tree into `custom_components/studio_assistant`, unmounts, and calls the restart service. Home Assistant 2026.9 usually drops that HTTP connection as it shuts down instead of answering, so the script treats a dropped connection as accepted and polls `/api/` until the API is back (about 30 s).
