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
 │              (music)                        ▼                   │
 │                                   ┌───────────────────────┐    │
 │                                   │ HA adapter             │    │
 │                                   │  chat_log ⇄ messages   │    │
 │                                   │  stream deltas to TTS  │    │
 │                                   │  continue_conversation │    │
 │                                   └──────────┬────────────┘    │
 └──────────────────────────────────────────────┼─────────────────┘
                                                │ same package, same code as the benchmark
                                                ▼
        assistant_core.agent_loop.run(conversation, llm, tools, policy)
        ┌───────────────────────────────────────────────────────────────────────────────────┐
        │ 1. messages = [system prompt] + the conversation so far (+ memory.get_context())   │
        │ 2. stream = llm.chat(messages, tools, temperature, think=False)                    │──▶ Ollama
        │ 3. for each delta:                                                                 │
        │      text        → yield to caller (HA speaks it as it arrives)                    │
        │      tool_call   → yield FILLER sentence immediately ("Let me pull some sources.") │
        │                    result = tools.call(name, args)   ────────────────────────────────▶ web_search_mcp
        │                    append tool result; go to 2 (max 4 rounds)                      │
        │ 4. final answer complete → policy: continue_conversation = True                    │
        │ 5. transcript (messages, tool calls, excerpts, timings) returned for logs/benchmark │
        └───────────────────────────────────────────────────────────────────────────────────┘
```

## 3. How it works, step by step

1. Home Assistant's pipeline has already turned speech into text and tried its built-in intents. Music commands never reach us. Weather questions do, because Home Assistant's weather intent is left with nothing to answer from (doc 06 §12, and §16 below). Everything else arrives as `ConversationInput` with the text, a conversation id, and a `ChatLog` holding the earlier messages of this conversation.
2. The adapter converts the chat log into the core's plain message list and calls `agent_loop.run`.
3. The core builds the message list: the shared system prompt (persona "Jarvis", English, one to three sentences, lead with the answer, no lists or URLs aloud, when to search), then the conversation's messages. `memory.get_context()` is called and, in v1, returns nothing; this is the seam for persistent memory later.
4. The core streams from the model. Text deltas are yielded upward immediately; the adapter writes them into the chat log as streaming content, and Home Assistant's text-to-speech starts on the first complete sentence.
5. If the model emits a tool call instead, the core first yields a filler sentence chosen from a short list ("Let me pull some sources on that.", "One moment, checking the web."). Because it is yielded before the tool runs, the listener hears it within a second of finishing their question. Then the tool is executed through the MCP client, its result appended as a tool message, and the model is called again. At most four tool rounds.
6. When the final answer finishes, the adapter decides whether the puck should reopen the microphone for a few seconds without the wake word, and returns a `ConversationResult` with `continue_conversation` set to that decision. It says yes after an ordinary answer, no after a silent reply or "Okay.", and no once a conversation has had two follow-ups in a row (§15).
7. The full transcript, including tool calls, retrieved excerpts, and timings, is returned. In production it is logged at debug level; in the benchmark it is the record that gets judged.

## 4. Why two layers

| Layer | Depends on | Tested with | Used by |
|---|---|---|---|
| `assistant_core` | `ollama`, `mcp`, `pydantic` | plain pytest, mocked model and tools | benchmark harness, `studio_assistant` |
| `studio_assistant` | Home Assistant | `pytest-homeassistant-custom-component` | Home Assistant at runtime |

The benchmark must exercise exactly the code the product runs, or it measures the wrong thing. Keeping the loop free of Home Assistant imports makes that possible and keeps the fast unit tests fast.

## 5. Behaviors the agent owns

- **Brevity.** The system prompt asks for one to three sentences and the answer first. The agent also enforces a soft cap: if a response runs past a word budget, the remainder is dropped after the current sentence, and the model is told in the system prompt that it can offer more detail if asked.
- **Filler before tools.** Deterministic, in code, not left to the model.
- **Follow-up.** After an ordinary answer the puck listens again without the wake word, at most two times in a row per conversation (§15). A follow-up arrives as a new `async_process` call with the same conversation id and the chat log already holding the prior exchanges, which is how the two-exchange benchmark question works too.
- **Unclear input.** The wake word sometimes fires on a television or on people talking. The system prompt tells the model to reply with a silence marker to speech not meant for it, to ask "Can you repeat that?" after a garbled request, and to say "Okay." to "never mind"; the loop never speaks the marker (§15).
- **Search restraint.** The system prompt tells the model when to search (current facts, prices, schedules, anything after its training cutoff, anything it is unsure about) and when not to (arithmetic, explanations, opinions).
- **Memory seam.** `memory.py` defines `get_context(conversation) -> str` and `remember(conversation) -> None` with a no-op implementation. Persistent memory later means swapping the implementation, not rewriting the loop.

## 6. Packages and what they do for us

| Package | Role in the business logic |
|---|---|
| `ollama` | `OllamaClient` streams chat completions with tool schemas from the local model. |
| `mcp` (client) | Connects to `web_search_mcp`, lists tools, converts their schemas into the shape each provider expects, executes calls. |
| `pydantic` | Typed `Message`, `ToolCall`, `Transcript`, and `AgentPolicy` (temperature, max tool rounds, word budget, filler phrases). |
| Home Assistant `conversation` platform | `ConversationEntity`, `ChatLog`, `ConversationResult`, streaming content deltas, `continue_conversation`. The adapter is written against these. |
| `pytest-homeassistant-custom-component` | Boots a minimal Home Assistant in tests so the adapter can be exercised without the VM. |

## 7. Configuration we control

Set through the component's UI config flow and stored by Home Assistant: Ollama URL and model tag, MCP server URL, persona name, temperature, word budget, filler phrases, follow-up on or off, and how many follow-ups in a row are heard before the wake word is needed again (`max_follow_ups`, default 2). `assistant_core` reads the same fields from a small config object so the benchmark can set them from `benchmark/config.yaml`.

## 8. Failure modes

- **Model returns a tool call in plain text instead of the structured field.** Treated as no tool call. Logged. Small models do this; the benchmark surfaces which ones.
- **Tool server down.** The core yields "I can't reach the web right now" and answers from knowledge with an explicit caveat rather than failing the exchange.
- **Model loops on tools.** Hard cap of four rounds, then the model is asked to answer with what it has.
- **Answer too long for a spoken reply.** Soft cap after the current sentence.
- **Home Assistant API change.** The conversation platform has evolved monthly through 2025 and 2026. The component pins the Home Assistant version it is tested against; bumps go through the test suite first.
- **Streaming and text-to-speech.** If the chosen TTS service does not support streaming, Home Assistant waits for the full answer before speaking and the filler sentence loses most of its value. Verified in the voice pipeline doc's checklist.

## 9. Concepts for newcomers

**Agent loop.** The pattern "call the model, if it asks for a tool run it and call again, else return the answer." Everything called an agent is some version of this loop plus policy around it.

**System prompt.** Instructions placed before the conversation that the model treats as standing orders: who it is, how long to answer, when to use tools. It is the main lever on behavior short of changing the model.

**Streaming.** Receiving the answer token by token as it is generated rather than waiting for the whole thing. For voice it means speech can start after the first sentence.

**Conversation id and chat log.** Home Assistant groups exchanges into a conversation and hands the agent the history each time, so the agent itself stores no history between calls. Statelessness makes the component simple and the benchmark reproducible. The one exception is a small counter per conversation of how many follow-ups in a row it has had, kept in memory by the component (§15).

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

- `assistant_core/models.py` holds the typed vocabulary: `Message`, `ToolCall`, `ToolSpec`, `AgentPolicy`, the model-client events (`TextDelta`, `ToolCallRequest`, `MalformedToolCall`, `Completion`), the agent events (`FillerSpoken`, `ToolStarted`, `ToolFinished`, `AnswerDelta`, `Done`), and `Transcript`.
- `agent_loop.run(conversation, llm, tools, policy, memory)` is an async generator. The filler sentence is yielded the moment the first tool call arrives, before the tool runs. Tool failures are turned into a notice the model sees rather than an exception. At the tool-round cap the pending calls get a "tool limit reached" notice and the model is asked once more to answer; that answer streams to the listener through the same word cap as any other.
- The spoken word cap is applied to the stream: past the budget, speech stops at the end of the current sentence and `Transcript.truncated` is set. `spoken_text` is what the listener heard across the whole exchange; `final_answer` is the model's last message in full.
- `llm_client.OllamaClient` streams through the `ollama` package with `think` passed only when the candidate config sets it, and retries once without it for model families that reject the switch.
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
               │  Ollama: chat(format=<json schema>, think=False)
               ▼
             RouteDecision(route, source="rule"|"model", detail, seconds)  ── recorded on the Transcript
               │
               ├─ search    ─▶ append "Routing for this question: SEARCH. ... Call search_and_read first ..." to the system prompt
               ├─ calculate ─▶ append "Routing for this question: CALCULATE. ... Call the calculator tools ... for every number ..."
               └─ answer    ─▶ messages unchanged          (the user's message is never changed)
                                                    ▼
                                    normal loop: model ─▶ tools ─▶ model ─▶ spoken answer
```

Design rules:

- **Rules only fire when they cannot be wrong.** The explicit-search pattern needs an imperative ("search for", "look up", "find me the latest"); a noun like "web search" does not count. The arithmetic pattern needs at least two numbers and a cue such as a percent sign, "per month", "watts", or "mortgage". A test asserts that no rule fires wrongly on any benchmark question; on question set 1.2 rules decide 15 of 28 questions.
- **The model layer is the same model classifying its own question.** It costs one short call (about 10 output tokens, 1.1 s on Gemma 4 E4B) before the first real call. The request must use the same `num_ctx` as the chat calls: Ollama reloads a model whose context length changes, and the first pass-2 attempt paid about 5 s twice per question for exactly that reason before the fix. It is measured separately in the report because it may or may not beat the tool descriptions.
- **A broken router never blocks an answer.** Any exception in the model layer yields the answer route with the error in `detail`.
- **The route is recorded; the directive is not.** `apply_route` appends the directive to the system prompt for that exchange only. The transcript keeps the base system prompt and a conversation without system messages, so neither the transcript nor the judge's case file contains the directive. The judge sees the route as a harness observation, "Router decided 'search' by rule (...)", and the rubric tells it to grade the answer, not the routing. The `route_questions` policy flag turns the whole layer off.

Packages: `re` for the rule layer; `ollama`'s `format` argument (a JSON schema the server constrains decoding to) for the model layer. Code: `assistant_core/router.py`, the `classify` method on the client, and four lines in `agent_loop.run`.

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
- **The filler sentence depends on the tool.** A calculator call used to say "Let me pull some sources on that." `AgentPolicy` now has `calculate_filler_phrases` ("Let me work that out.", "One second, doing the math.") and `agent_loop.filler_for` picks the list by whether the first tool of the exchange is in `SEARCH_TOOL_NAMES`, which moved to `assistant_core.models` so the benchmark and the loop share one definition.

Deployment is `scripts/deploy_component.py`: it stages the component with `assistant_core` vendored under `vendor/`, mounts the VM's `config` share over SMB (the Samba add-on), copies the tree into `custom_components/studio_assistant`, unmounts, and calls the restart service. Home Assistant 2026.9 usually drops that HTTP connection as it shuts down instead of answering, so the script treats a dropped connection as accepted and polls `/api/` until the API is back (about 30 s).

## 14. As built, 2026-09-06: the directive moves into the system prompt (prompt 1.3)

Pass 2 showed the router choosing "calculate" correctly for Qwen 3.5 9B on every arithmetic question while the model made zero calculator calls; a rerun of the eight arithmetic questions reproduced it exactly. The directive was a bracketed "[Assistant note: ...]" appended to the user's message, which models read as part of the request rather than as an operator rule. From prompt version 1.3, `apply_route` appends the directive to the system prompt for that exchange and leaves the user's message untouched:

```
 SYSTEM  base prompt (unchanged)
         + "Routing for this question: CALCULATE.
            This question needs arithmetic. Call the calculator tools (...) for every number; do not do the math yourself. ...
            Example. Question: "What is 15 percent of 80 dollars?"  Tool call: percent(kind="of", a=15, b=80)  Tool result: ...  Answer: ..."
 USER    exactly what the user said
```

The search route gets the matching block with one `search_and_read` example. The wording stays a plain instruction: nothing in the harness enforces it, so it makes no claims about what happens to an answer that ignores it, at the user's request. Latency is unchanged (about ninety more prompt tokens, no extra call). The route record on the transcript and the router accuracy table are unaffected, so passes remain comparable on routing; answer scores are compared pass to pass in `benchmark/results/version_3/report.md`.

### Prompt 1.4, same day

Pass 3 (`benchmark/results/version_3/report.md`) showed the trade: Qwen 3.5 9B started calling the calculator (1 of 6 arithmetic questions in pass 2, 4 of 6 in pass 3) and gained 27 points, but Gemma 4 E4B searched on only 6 of 11 questions it was routed to search on (11 of 11 in pass 2) and lost 36, and both Qwens skipped one search. The search block's example had shown a finished spoken answer, and the small models imitated the answer rather than the call. Prompt 1.4 cuts each block to the instruction plus one example call and nothing after it. Pass 4 measures that.

### Prompt 1.5: the date line, 2026-09-06

The models do not know what day it is. In benchmark pass 4, fourteen of the forty-six search queries the small models wrote were pinned to 2024 or 2025 (the years their training data ends), which pulled stale pages, and Gemma 4 E4B once declined a schedule question because it did not know the date. `assistant_core.prompts.system_prompt(today)` now returns the system prompt with one line inserted after the persona sentence: "Today is Sunday, September 6, 2026. Use this date whenever a question depends on what is current; do not assume an earlier year in your searches or answers." `build_messages` calls it per request, so the Home Assistant component and the benchmark both get the real date and the wording is never frozen in the code. Within a benchmark pass every candidate sees the same line, so the fairness rule holds. The transcript records the exact system prompt used, date included.

### Retry on an empty completion, 2026-09-06

Gemma 4 E4B returned nothing on about one answer in seven across passes 3 to 5: no words, no tool call, twenty to fifty output tokens billed. Replaying the same requests against Ollama returned a valid tool call every time, so in the failing cases the model wrote a call with a small formatting slip and Ollama's Gemma parser dropped it without reporting anything (pass 4's server log shows the same class of failure with an "invalid character" warning). Read aloud, an empty completion is silence. `run_agent` therefore treats a completion with neither text nor tool calls as a miss and asks the model once more with the same messages before accepting the empty answer; the miss is still counted in `model_calls` and in a new `Transcript.empty_completion_retries` field, so the benchmark can see how often it happens. One retry, not more: a model that returns nothing twice is not going to answer, and the caller should not wait on a third attempt.

## 15. As built, 2026-09-30: unclear input, the silence marker, and the follow-up cap (prompt 1.6)

The Voice PE puck's wake word sometimes fires on a television, a radio, or people talking in the room. Until this change the component asked the puck to listen again after every answer, so a false wake could loop: the assistant answered the television, the microphone reopened, the television was still talking, and the assistant answered it again, for as long as twenty minutes. The prompt also gave the model no guidance for speech that was garbled, overheard, or called off. Three pieces fix it: rules in the prompt, a silence path in the loop, and a cap on follow-ups in the component. The wake word itself is unchanged.

```
 transcript text ──▶ model, system prompt 1.6
                       │
                       ├─ speech not meant for it           ─▶ replies "*"                     ─▶ loop speaks nothing; Transcript.stayed_silent
                       ├─ short garbled or cut-off request  ─▶ replies "Can you repeat that?"  ─▶ spoken
                       ├─ "never mind", "stop", "cancel"    ─▶ replies "Okay."                 ─▶ spoken
                       └─ a real question, however phrased  ─▶ answers it                      ─▶ spoken

 then studio_assistant decides: listen again without the wake word?  (rules checked in this order)
   1. the follow-up setting is off                                   ─▶ no
   2. the reply stayed silent                                        ─▶ no, count forgotten
   3. the reply was "Okay."                                          ─▶ no, count forgotten
   4. this conversation already had max_follow_ups (2) in a row      ─▶ no, count forgotten
   5. otherwise                                                      ─▶ yes, count goes up by one

 wake word ─▶ answer (listen) ─▶ follow-up ─▶ answer (listen) ─▶ follow-up ─▶ answer (stop: the wake word is needed again)
```

**The prompt rules.** A new section of the system prompt, "When what you heard is unclear", modelled on a decision hierarchy a Home Assistant forum user had run successfully with a local model. It tells the model that its input is a speech-recognition transcript and that the wake word sometimes fires by mistake, then gives one fixed reply per case: `*` for speech not addressed to it (overheard conversation, a television or radio, rambling narration, stray phrases, and recognizer artifacts such as "Thank you for watching.", which Whisper produces from near silence), "Can you repeat that?" for a botched request of about one to ten words, and "Okay." for "never mind", "stop", or "cancel". A real question stays a question even when oddly phrased or when a word was clearly misheard, and a clarifying question, when one is needed, is two to five words that name only the ambiguity, never a list of options. The three replies are constants in `assistant_core/prompts.py` (`SILENCE_MARKER`, `REPEAT_REQUEST_REPLY`, `ACKNOWLEDGEMENT_REPLY`) so the loop, the component, and the benchmark read the same strings. An asterisk is a safe marker because the prompt already forbids markdown, so no real answer is an asterisk alone.

**Silence in the loop.** A model streams its reply a few characters at a time, and the loop normally passes each piece on to be spoken at once. `SilenceMarkerHold` in `agent_loop.py` holds the text back only while everything received so far, ignoring whitespace, could still be the marker, which for a one-character marker means only until the first character that is not `*` or whitespace. At that point everything held is released together, so an ordinary answer gains no delay, and an answer that happens to begin with an asterisk followed by more text is spoken in full. A reply that is exactly `*` is never released: nothing is spoken, `spoken_text` stays empty, `final_answer` keeps the `*` so the log shows what the model chose, and `Transcript.stayed_silent` is set. The same flag is copied onto the exchange record the component posts to the tool server, so the production log can count silent exchanges.

**The follow-up cap.** `FollowUpListening` in `custom_components/studio_assistant/adapter.py` is plain Python with no Home Assistant import, so it is unit-tested directly. The entity keeps one instance, and it keeps a count per conversation id of the follow-ups in a row. The count is removed whenever a conversation stops listening, and at most 32 conversations are tracked, oldest dropped first, because a follow-up that nobody spoke into ends without another call to the agent and would otherwise leave its count behind. "Can you repeat that?" is an ordinary reply here and counts toward the cap. `max_follow_ups` is a new option in the component's options form, default 2; turning the existing follow-up setting off now means the puck never listens again without the wake word.

**What Home Assistant does with a silent reply.** A silent reply streams no text into Home Assistant's chat log, and Home Assistant's helper that builds the conversation result raises an error when the log does not end with an assistant entry, which the puck would announce as a failure. The entity therefore adds an empty assistant entry when the stream produced none. The result then carries empty speech, and Home Assistant's pipeline skips the text-to-speech stage when the speech is empty or whitespace; the puck's firmware treats a run that ends without a text-to-speech stage as "never mind" and returns to idle. This is the same path Home Assistant's own "never mind" intent takes. It was established by reading the Home Assistant and ESPHome sources and has not yet been heard on the real puck.

**Known edges.**

- If the router sends overheard speech to the search route (a television line about the weather can do that), the filler sentence is spoken before the model replies `*`. The exchange still counts as silent, so the puck does not listen again, but the listener heard "Let me look that up."
- The puck reuses a conversation id for five minutes after its last exchange. If a follow-up window closes with nobody speaking, that conversation's count stays where it was, and a new wake word within five minutes starts from it, so that conversation gets one fewer follow-up than usual.

Code: `assistant_core/prompts.py`, `SilenceMarkerHold` and `finish_transcript` in `assistant_core/agent_loop.py`, `Transcript.stayed_silent` in `assistant_core/models.py`, `ExchangeRecord.stayed_silent`, `FollowUpListening` and `agent_events_to_deltas` in the component's `adapter.py`, and `_async_handle_message` in `conversation.py`. The benchmark measures the prompt rules with category D (doc 01, "Question set 1.3").

## 16. As built, 2026-09-30: weather at home (prompt 1.7)

Weather questions now reach the agent (doc 06 §12), and the tool server offers `weather_forecast`, which reads Met.no's forecast for home (doc 03 §14). The router gains a fourth route so the model calls that tool instead of searching the web or answering from memory.

```
 user text ──▶ rule layer (regex, 0 ms)
               │  "search the web", "look up"                          ─▶ search
               │  two or more numbers + an arithmetic cue              ─▶ calculate
               │  coming weather at home, no other place named         ─▶ weather     "Do I need an umbrella tomorrow afternoon?"
               │  nothing matched
               ▼
             model layer (one structured-output call, four routes)     ─▶ weather     "How cold is it going to get tonight?"
               │                                                       ─▶ search      "What's the weather in Lisbon this weekend?"
               ▼
             route_to_offered_tools: weather tool not offered?         ─▶ search
               │
               ├─ search, calculate, answer ─▶ directives as in §12 and §14
               └─ weather ─▶ system prompt + "Routing for this question: WEATHER. ... Call weather_forecast first ..."
                             Example call: weather_forecast(day="tomorrow", part_of_day="afternoon")
                               │
                               ▼
                             model calls weather_forecast ─▶ filler "Checking the forecast." ─▶ tool result ─▶ spoken answer
```

**The weather rule.** The rule layer checks explicit search first, then arithmetic, then weather, and the weather rule is deliberately conservative, like the others:

- It needs a question about coming or current weather. "Weather", "umbrella", or "the forecast" is enough on its own. A precipitation word (rain, snow, drizzle, thunderstorm, sleet) also needs a time cue ("today", "tonight", "tomorrow", "this afternoon", "the weekend", a weekday, "later", "now") or a forecast question form ("will it", "is it going to", "should I bring"), because "Who sang Purple Rain?", "Who wrote Snow Crash?", and "How much rain does Seattle get a year?" mention rain and snow without asking about them.
- It stands aside for explanations ("why does it rain more in the afternoon"), which the model answers from knowledge.
- It stands aside when another place may be named. After each preposition (in, at, for, near, on, and a few more, skipping "the"), the next word must be one that cannot be a place: a time ("tomorrow", "saturday", "tonight"), the user's own surroundings ("home", "outside", "work"), or a verb ("to bring", "to snow"). "In Lucerne", "in the Alps", or any word the rule does not know leaves the question to the model layer, which sends other places to search.

Questions without a weather word, such as "how cold is it going to get tonight", reach the model layer. Its prompt now lists four routes, defines weather as "the weather or forecast where the user lives, with no other place named", and moves "weather anywhere other than the user's home" into the search definition. On question set 1.4 the rule decides two of the three weather questions; the model layer has to catch the third.

**Fallback when the tool is missing.** The server offers `weather_forecast` only when it knows where home is. `route_to_offered_tools` turns a weather route into a search route when the tool list lacks it, and appends "weather tool not offered, so searched" to the route's detail, so a server started without coordinates degrades to the old behaviour instead of telling the model to call a tool that does not exist.

**Prompt 1.7.** Two changes to the base prompt, plus the weather directive:

- The search list says "weather anywhere other than home" where it said "weather".
- A new "Weather at home" section tells the model to call `weather_forecast` for the weather where the user lives, to search for anywhere else, and to answer from what the tool returns: conditions, temperature range, and whether rain or snow is likely, with the numbers rounded.
- The weather directive has the same shape as the others since prompt 1.4: the instruction and one example call, nothing after it.

Version 1.6 was taken by a separate change to the prompt developed at the same time, so this one is 1.7. Category E (home weather) is new, so a pass under 1.7 compares with earlier passes on categories A to D only.

**The filler.** `filler_for` now has three lists: search tools get the web phrases, `weather_forecast` gets `weather_filler_phrases` ("Checking the forecast.", "One moment, getting the forecast."), and everything else gets the calculator phrases. "Checking the web" would be wrong for a forecast read from one fixed service, for the same reason it was wrong for arithmetic. The phrases live in `AgentPolicy`; the Home Assistant component does not expose any filler phrases in its options, so it uses the defaults.

**How the benchmark measures it.** Question set 1.4 adds category E (home weather), three weather questions with the weather route expected: E36 "Do I need an umbrella tomorrow afternoon?", E37 "What's the weather looking like this weekend?", and E38 "How cold is it going to get tonight?". A new gate, `did_not_check_forecast_on_weather_question`, fails a weather-route question on which the candidate never called the forecast tool. The judge sees the tool result, as it does for search, and the rubric makes that forecast the ground truth: any figure or condition not in it counts as a fabricated current fact. B13 (a day trip from Lucerne that depends on the weather there) still expects search, which checks that another town's weather does not go to the home forecast.

Code: `assistant_core/router.py` (rule, classifier prompt, directive, `route_to_offered_tools`), `assistant_core/prompts.py`, `assistant_core/models.py` (`Route.WEATHER`, `WEATHER_TOOL_NAMES`, the filler phrases), and two lines in `agent_loop.py`.
