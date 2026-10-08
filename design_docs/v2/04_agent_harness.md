# 04. Agent harness

Status: building

## 1. Purpose

The code around the model that turns a question into a spoken answer. In v1 it ran inside Home Assistant as the `studio_assistant` component, and it handled one tool per question at best. In v2 it moves out of Home Assistant into a service of its own on the Mac, so it can keep state between questions, reach llama-server and the tool server without opening them to the network, and do work after a conversation ends. The component in Home Assistant becomes a thin client that forwards the question and speaks what comes back. The harness also learns to use several tools for one question, and to keep every prompt inside a budget that suits the model it is serving. v1/04 still describes the behaviours that carry over unchanged: the filler sentence, the brevity cap, the silence marker, and the follow-up cap.

## 2. Diagram

```
 ONE QUESTION

                                                                                          result added to slot 0; a new llama.cpp request
                                                                                       ┌─────────────────────────────────────────────────┐
                                                                                       ▼                                                 │
 ╭────────────────────╮   ╭────────────────────╮   ╭────────────────────╮   ╭────────────────────╮   ╭────────────────────╮   ╭────────────────────╮
 │   your question    │   │       recall       │   │ llama.cpp request  │   │ llama.cpp request  │   │       guards       │   │    tool server     │
 │    via the puck    │──▶│ 2 or 3 past notes  │──▶│    plan, slot 1    │──▶│  response, slot 0  │──▶│ check each request │──▶│ runs the requests  │
 ╰────────────────────╯   ╰────────────────────╯   ╰────────────────────╯   ╰────────────────────╯   ╰────────────────────╯   ╰────────────────────╯
                                                                                       │
                                                                                       ▼ no tool call: the answer streams back to Home Assistant

 WHEN THE CONVERSATION ENDS

 ╭────────────────────╮   ╭────────────────────╮   ╭────────────────────╮   ╭════════════════════╮
 │    five minutes    │   │ llama.cpp request  │   │   code checks it   │   │    memory vault    │
 │      of quiet      │──▶│  summary, slot 1   │──▶│  length, no URLs   │──▶│      one note      │
 ╰────────────────────╯   ╰────────────────────╯   ╰────────────────────╯   ╰════════════════════╯

 A llama.cpp request sends one prompt to the one Gemma 4 model in llama-server and gets one reply; only the prompt and the slot differ.
```

## 3. How it works, step by step

### 3.1 One question

Home Assistant's pipeline turns speech into text and tries its built-in intents, as in v1. A question it does not handle reaches `studio_assistant`. The component turns the chat log into the list of earlier spoken exchanges, exactly as v1 does (`chat_log_to_conversation`), and posts it with the new question and the conversation id to the harness's `/v1/converse`, with the harness's API key. In the diagram, the first lane is steps 2, 3, and 5 to 7, and the second lane is steps 9 and 10.

1. **Load the conversation's state.** The harness looks up whether this conversation is already marked untrusted and, if it has been compacted, the summary that stands in for its older exchanges (3.5).
2. **Find matching past notes.** The memory index returns the two or three past-conversation summaries that best match the question (doc 11).
3. **Ask the router.** One short llama.cpp request, in slot 1, returns the tools the question needs, in order, with a one-line plan (3.3).
4. **Build the prompt.** The prompt builder lays it out in the cache order of doc 02 §3.3, counts it, and trims it to the model's budget if needed (3.4).
5. **Send the response request.** The conversation's prompt goes to slot 0 as a llama.cpp request. If the model asks for a tool, the harness sends the filler sentence to Home Assistant at once.
6. **Run the allowed tool calls.** Every call is checked against the guards of doc 12; the allowed ones run on the tool server, at the same time when there are several.
7. **Add the results and send a new llama.cpp request.** This repeats until the model answers or the round cap is reached. The answer streams to Home Assistant as it is written, and a final `done` line carries the exchange's transcript. The component writes the text into the chat log, so text-to-speech starts on the first sentence, and decides whether the puck listens again (v1/04 §15).
8. **Log the exchange,** with the trust mark and the token counts of every llama.cpp request.
9. **Summarise the conversation.** When it has been quiet for five minutes, which is when Home Assistant also forgets it, the harness sends the summary prompt to slot 1.
10. **Save the note.** Code checks the summary and saves it as one note (doc 11).

### 3.2 The service and the thin client

The harness is a new package, `assistant_service/`, run by launchd like the other services (doc 10). It is a Starlette app served by uvicorn, both already installed with the `mcp` package. It owns only what a long-running service needs:

- **The HTTP API.** `POST /v1/converse` answers one question; `GET /health` reports whether llama-server and the tool server answer.
- **Who may call it.** It listens on the network because the Home Assistant VM must reach it, so it requires the API key, accepts only requests addressed to this Mac by name, and refuses requests with a browser `Origin` header (doc 12 §3.9).
- **State per conversation** (3.5).
- **Background work**: summaries and compaction, scheduled so they never delay a question (3.7).

Everything that shapes an answer stays in `assistant_core`: the router, the prompt builder, the context budget, the guards, the memory lookup, and the loop. The benchmark imports `agent_loop.run` and runs exactly that code in-process, as in v1, and one benchmark pass per milestone also goes through the HTTP API, so the service itself is measured too.

The response streams as newline-delimited JSON: one JSON object per line, each one of the loop's existing events. A question that needs the forecast looks like this:

```
{"event": "filler", "text": "Checking the forecast."}
{"event": "tool_started", "name": "weather_forecast"}
{"event": "tool_finished", "name": "weather_forecast", "seconds": 0.4}
{"event": "answer", "text": "Tomorrow afternoon looks dry, "}
{"event": "answer", "text": "with a high of 18 degrees."}
{"event": "done", "transcript": {…}}
```

Newline-delimited JSON needs nothing beyond `httpx`'s line streaming on the Home Assistant side and adds no package to either end. Server-sent events would add framing the component does not need, and a websocket would add a connection to keep alive.

What the component keeps and what it loses:

| Kept in the component | Moves to the harness |
|---|---|
| Converting the chat log to a list of exchanges | The router, the loop, the model client, the tool client |
| Streaming the text into the chat log for text-to-speech | Temperature, word budget, tool rounds, context size, filler phrases |
| The follow-up decision and its cap (`FollowUpListening`) | Writing the exchange log (doc 12 §3.9) |
| The empty assistant entry after a silent reply | The model's address and the tool server's address |

The component's options form shrinks to the harness's address and key, the follow-up switch, and `max_follow_ups`. It still vendors `assistant_core` for the shared event and transcript models, but no longer runs any of the loop, so Home Assistant's Python never imports a model client. If the harness cannot be reached, the component speaks "I can't reach the assistant right now." rather than failing silently.

**Result, 2026-10-08** (run `m2_harness_run1`, question set 1.4 through the HTTP API): M2's exit criteria are met.

| Criterion | Measured |
|---|---|
| The same gates over HTTP | The code gates fired as often as in M1's three in-process runs: twice `spoke_when_it_should_stay_silent` (D29, D31), once each way on the search decision (A11, B21), and nothing else |
| `ops.smoke --full` passes | Both questions passed through Home Assistant: the calculator in 1.3 s and the web search in 13.9 s |
| First spoken word no more than 150 ms above in-process | Median 1.160 s through the API, timed at the client, against 1.044 to 1.073 s in process in M1's three runs: 87 to 116 ms more |

The pass needs a tool server that offers `weather_forecast`. The first attempt used the installed one, which had no home coordinates in `.env` and so started without the weather tool; the three weather questions then searched instead. The recorded pass used the branch's tool server with the benchmark's home.

### 3.3 Several tools for one question

v1's loop allows several tool rounds but the router picks only one route, and in the trial, without the router, Gemma 4 E4B searched for an interest rate and then did the arithmetic in its head, wrongly, instead of calling the calculator. v2 changes the loop in five ways, built in M5:

1. **The router returns a plan.** Its JSON answer becomes `{"tools": ["weather_forecast", "weather_forecast", "calculator"], "plan": "Get tomorrow's forecast for Lisbon and for home, then subtract the highs."}`. The rule layer stays in front of it and still decides the easy cases in no time. The plan goes into the per-question block of the prompt, never into the system text, so the cache is untouched (doc 02 §3.3). The tool definitions offered to the model never change between questions for the same reason; the plan tells the model what to use, it does not hide the other tools.
2. **Calls in one turn run together.** When the model asks for several tools at once, the harness checks each against the guards and runs the allowed ones at the same time.
3. **Repeated calls are answered from the first.** The same tool with the same arguments in one question gets the earlier result back, with a note that it is a repeat, instead of a second network call.
4. **The round cap follows the plan.** The cap is the number of planned tools plus one, at least two and at most six, so a one-tool question cannot wander and a three-step question is not cut off.
5. **Broken turns stay out of the history.** A model turn whose tool call cannot be parsed is not added to the messages; the model is asked again once with the same messages, as v1 already does for empty answers. A broken example in the history would teach the model the broken format for the rest of the question.

The harness also records whether every planned tool was called, which is what the benchmark's `missing_required_tool` gate checks (doc 01).

### 3.4 The context budget

Every model gets a budget: how many tokens the whole prompt may take and how they are shared between its parts. Its numbers live with the model's serving settings in `config/serving.toml` (doc 02 §3.5), so the window the harness plans for is always the one llama-server was started with:

```toml
[models.gemma-4-e4b.budget]
compact_history_at = 0.75     # share of the history allowance that triggers compaction
per_question_block = 600      # date, plan, and memory summaries
memory_summaries = 400        # within the per-question block
tool_result = 2700            # each tool result, after the tool server's own limit
output_reserve = 600          # left free for the answer
```

The rest of the window, after the system rules, the tool definitions, the per-question block, and the output reserve, is the history allowance. For Gemma 4 E4B at 16,384 tokens, that is about 12,800 tokens, shared by the earlier exchanges and this question's tool results.

The window itself is not the model's limit. Gemma 4 E4B accepts 128K tokens, but 16,384 is v1's own setting, chosen to hold a system prompt, a few exchanges, and two fetched pages. In v2 it is llama-server's `-c` flag. M1 sets it per machine from two measurements: the memory left free (the KV cache grows with the window) and where the benchmark's answers stay good, since small models answer worse long before their advertised limit.

Tokens are counted exactly with llama-server's `/tokenize`. The system rules and the tool definitions are counted once at startup and again only when they change; each exchange is counted once and its count kept with it.

When the next llama.cpp request would not fit, the harness gives up space in this order, stopping as soon as it fits:

1. **Condense earlier tool rounds of this question.** Earlier search results are cut again by `select_passages` (`utils/passage_utils.py`) against the question, at a smaller word budget. No llama.cpp request is needed, and the forecast and calculator results are never condensed because they are tiny. This rewrites text the cache already holds, so that one request reads from the change onwards.
2. **Compact older exchanges.** Every exchange but the last two is replaced by one "Earlier in this conversation: …" passage (3.5).
3. **Use fewer memory summaries,** down to none.
4. **Clip tool results** to their allowance.

Every llama.cpp request records the tokens of each part of its prompt and how many came from the cache, so a slow answer can be traced to the part that grew.

### 3.5 Who keeps the conversation

Home Assistant's chat log stays the record of what was said. The component sends the earlier exchanges with every question, as in v1. The harness keeps only what Home Assistant cannot hold for it, keyed by the conversation id:

| Kept by the harness | Why |
|---|---|
| The trust mark | An exchange that read the web marks the whole conversation (doc 12 §3.2). If it were lost on a restart, the conversation's summary could be saved as trusted, so it is stored in a small SQLite file, not only in memory. |
| The compaction summary, and how many exchanges it covers | So the prompt can replace the older exchanges with it, and the same text is reused on every later question of the conversation, keeping the cache warm |
| The time of the last exchange | To know when the conversation has ended |

The alternative, the harness holding the whole history itself, was weighed and set aside: two copies of a conversation can disagree, Home Assistant would still show its own, and the benchmark's two-exchange questions already pass the history in, the way the component does. The exchange log the harness writes holds everything needed to summarise a conversation after Home Assistant has forgotten it.

**Compaction.** When the history passes 75% of its allowance, the harness writes the compaction summary after the answer has been spoken, so the next question never waits for it. It is one quiet llama.cpp request: no tools, an answer forced into a JSON schema, at most 150 words, made from your words and the answers only (v1 already leaves earlier tool results out of the history). A compaction summary of an untrusted conversation is untrusted too.

**The end of a conversation.** Home Assistant forgets a conversation five minutes after its last exchange, and the puck then starts a new conversation id. The harness checks every minute for conversations quiet for five minutes, writes their summaries (doc 11), and drops their state, except the trust mark, which is kept until the summary is saved.

### 3.6 The model client

`LlamaServerClient` in `assistant_core` replaces `OllamaClient`, written over `httpx` with no `openai` or `litellm` package (doc 12 §3.10). It offers the same three things the loop needs:

- **`chat`**: streams a completion with tools from `/v1/chat/completions` and turns the chunks into the loop's existing events (`TextDelta`, `ToolCallRequest`, `MalformedToolCall`, `Completion`). The `Completion` carries llama-server's `timings`, including the tokens served from the cache.
- **`classify`**: one llama.cpp request with the reply forced into a JSON schema, for the router, the summariser, compaction, and the quarantined reader (doc 12 §3.6).
- **Slot pinning**: every response request is sent with `id_slot: 0` and every quiet request with `id_slot: 1`, so the router and the summaries never push the conversation out of the cache (doc 02 §3.4). At startup the client sends one warm-up request to each slot.
- **`count_tokens`**: `/tokenize`, for the budget.

The benchmark keeps `OllamaClient` until M1 ends, so the bake-off can compare both engines through the same loop.

### 3.7 Questions come first

The conversation and the quiet requests have separate slots (doc 02 §3.4), so a summary never evicts the conversation's cache. But the two slots share one GPU, and a summary being written while you ask a question would slow your answer. The harness therefore runs background requests (conversation summaries and compaction) only when no question is in progress, one at a time. When a question arrives while one is running, the harness closes the background request, which makes llama-server stop it (checked in M2), and retries it once the question has been answered. A summary that cannot be written within an hour is dropped and logged.

## 4. Packages and what they do for the business logic

| Package | Role |
|---|---|
| `httpx` | `LlamaServerClient`, the component's call to the harness, and the tool calls over HTTP |
| Starlette, uvicorn | The harness's HTTP API and its newline-delimited JSON stream. Already installed with `mcp`; listed as direct dependencies when the service is built |
| `sqlite3` (standard library) | The per-conversation state, so a trust mark survives a restart |
| `pydantic` | The events and the transcript, shared by the harness, the component, and the benchmark, as in v1 |
| `mcp` (client) | The tool server, unchanged from v1 |

The `ollama` package leaves the dependencies when M1 ends.

## 5. Configuration we control

- `config/serving.toml`: each model's window and budget (3.4), next to its serving settings (doc 02 §3.5).
- The harness's own settings, in its launchd agent and a small config file (doc 10): its port and allowed host names, its API key file, the tool server's address, and the answer settings that used to live in the component's options form (temperature, word budget, filler phrases).
- `config/tools.toml`: every tool's tier and trust (doc 12 §5).
- The component's options form: the harness's address and key, the follow-up switch, and `max_follow_ups`.

## 6. Failure modes

| Failure | What happens | What to do |
|---|---|---|
| The harness is down | The component says "I can't reach the assistant right now." | `scripts/services.sh restart harness`; the health check reports it (doc 10) |
| llama-server is down | The harness answers "I can't reach the model right now." and reports it in `/health` | Restart llama-server (doc 02 §6) |
| The tool server is down | The model answers from knowledge with v1's caveat | As in v1 |
| The model loops on tools | The round cap ends it, and the model is asked to answer with what it has | Nothing; the benchmark counts how often |
| The model skips a planned tool | The answer may be a guess; the exchange log records the missing tool | M5's gate measures it; a bigger model may be the fix |
| The prompt would overflow | The budget's degrade order applies (3.4) | Lower a part's allowance if one keeps crowding the rest |
| The harness restarts mid-conversation | The conversation continues; its trust mark and compaction summary are read back from SQLite | Nothing |
| A background summary keeps being interrupted | It is retried when the house is quiet, and dropped after an hour | Nothing |

## 7. Concepts for newcomers

**Thin client.** A component that only forwards requests and displays answers, with no logic of its own. Here it keeps Home Assistant's side simple and lets the harness change without redeploying into the VM.

**Newline-delimited JSON.** A stream where each line is a complete JSON object, so the receiver can act on each line as it arrives.

**Tool round.** One llama.cpp request whose reply asks for tools, followed by running them. A question that needs a forecast and then a subtraction takes two rounds and a final request.

**Context budget.** A plan for how the model's limited window is shared between the rules, the tools, the conversation, and the new material for this question, with a fixed order of what gives way first.

**Compaction.** Replacing older parts of a conversation with a short summary so the conversation can continue without overflowing the window.

**Conversation id.** Home Assistant's name for one conversation. It stays the same across follow-ups and is forgotten after five quiet minutes.

## 8. Sources

- Home Assistant conversation entity and chat log: [developers.home-assistant.io](https://developers.home-assistant.io/docs/core/entity/conversation)
- llama.cpp server API, including streaming and `/tokenize`: [llama.cpp server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- Newline-delimited JSON: [github.com/ndjson/ndjson-spec](https://github.com/ndjson/ndjson-spec)
- Starlette streaming responses: [starlette.io](https://www.starlette.io/responses/#streamingresponse)
- Small models degrading well before their advertised context length: [RULER, Hsieh et al., 2024](https://arxiv.org/abs/2404.06654)
