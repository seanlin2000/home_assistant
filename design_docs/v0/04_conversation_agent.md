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
