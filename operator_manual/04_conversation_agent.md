# Conversation Agent
<!-- complexity: packages=2 parts=3 concepts=3 tier=deep -->

This page covers the conversation agent, the code that answers you. Home Assistant hands it the text of what you said and the conversation so far. For each question it:

1. puts the persona and the house rules in front of the model;
2. decides, before the model answers, whether the question needs the web, the calculator, the forecast for home, or none of them;
3. runs the tools the model asks for, saying a short filler sentence while they run;
4. streams the answer to text to speech, stopping at the end of a sentence once the answer is long enough;
5. after an ordinary answer, asks Home Assistant to keep listening for a follow-up, at most twice in a row.

The same code runs in the Home Assistant VM as the `studio_assistant` component and on the laptop as the benchmark, so the code that was measured is the code you talk to.

## Where this fits

```mermaid
flowchart TB
--8<-- "_includes/system_map.mmd"
class agent,ollama,mcp current
```

The agent receives, from the intent matcher, every sentence that matched none of Home Assistant's fixed patterns, together with the chat log of the conversation so far. It sends the chat and the tool schemas to Ollama and gets back a stream of tokens or a tool call; tool calls go over MCP to `web_search_mcp`, and the results go back into the next call to Ollama. What it hands on is the answer, sentence by sentence, to the text to speech stage, plus the flag that keeps the puck listening for a follow-up.

## Key definitions

| Term | Meaning |
|---|---|
| Agent loop | The pattern of calling the model, running any tool it asks for and calling it again, and returning its answer once it asks for none. |
| Tool calling | The model replying with a structured request to run a tool, such as `web_search(query="current federal funds rate")`, instead of with an answer. |
| Tool round | One cycle of the agent loop in which the model asks for tools, the loop runs them, and the model is called again with the results. |
| Exchange | One question you ask and the answer the assistant gives, however many model calls and tool rounds it takes. |
| System prompt | Instructions placed before the conversation that the model treats as standing orders: who it is, how long to answer, and when to use tools. |
| Streaming | Receiving the answer token by token as it is generated rather than waiting for the whole thing. |
| Filler sentence | A short sentence such as "Let me work that out." that the agent speaks as soon as the model asks for its first tool, so you hear something within a second or two. |
| Word budget | The soft cap on spoken words, past which speech stops at the end of the current sentence. |
| Question router | The step before the first model call that decides whether a question needs the web, the calculator, the forecast for home, or none of them. |
| Conversation entity | The kind of Home Assistant entity a conversation agent is, which the Assist pipeline calls with your text and the chat log and expects a reply it can speak. |
| Chat log | Home Assistant's record of one conversation's exchanges, handed to the conversation entity on every call. |
| Transcript | The record the agent loop returns at the end of an exchange: every message, every tool call with its result and timing, token counts, the route decision, whether the reply stayed silent, and the failure flags. |
| Exchange record | A trimmed copy of one exchange's transcript, without the page text, that the component posts to the tool server after each answer. |

## Packages and tools

| Tool | What it is | How this part uses it |
|---|---|---|
| `ollama` 0.6.2 | The typed Python client for the Ollama HTTP API | `OllamaClient` in `assistant_core/llm_client.py` streams every chat request with the tool schemas attached and turns each chunk into a text delta or a tool call. Its `classify` method sends the router's question with a JSON schema in the `format` field. The component's `manifest.json` pins the same version so Home Assistant installs it inside the VM |
| `pydantic` 2.13.5 | Typed data models | The whole vocabulary of the loop is pydantic models in `assistant_core/models.py`: `Message`, `ToolCall`, `ToolSpec`, `AgentPolicy`, the events the model client emits, the events the loop emits, `RouteDecision`, and `Transcript`. `ExchangeRecord` in `exchange_record.py` is one too, which is how it serialises to JSON for posting |
| `httpx` 0.28.1 | An async HTTP client | The only dependency of `HttpMcpToolBox`, the MCP client the component uses to list and call tools, and the client that posts exchange records. Inside Home Assistant the component borrows Home Assistant's shared `httpx` client rather than opening its own |
| Home Assistant core 2026.9.1, `conversation` platform | The part of Home Assistant that defines what a conversation agent is | `StudioAssistantEntity` subclasses `ConversationEntity`, reads the `ChatLog`, streams the reply back with `async_add_delta_content_stream`, and returns a `ConversationResult` with `continue_conversation` set. The config flow and options form are built on Home Assistant's `ConfigFlow`, `OptionsFlow`, and `voluptuous` schemas |

The benchmark on the laptop adds one package the component never loads: the official `mcp` 2.1.1 client behind `McpToolBox`.

## How it works

Anything the agent must do every time, such as the filler sentence, lives in code; anything that needs judgement, such as whether to search, is left to the model with guidance in the prompt.

### Two layers, one loop

```mermaid
flowchart TB
--8<-- "_includes/palette.mmd"
%% grid: .        laptop   .        entity   .
%% grid: .        .        loop     .        .
%% grid: prompts  memory   router   llm      http
%% grid: .        .        .        ollama   mcp
%% peers: laptop entity loop prompts memory router llm http ollama mcp
laptop("benchmark<br/>on the laptop")
entity("studio_assistant<br/>in the VM")
subgraph core["assistant_core: runs inside each caller<br/>and never imports Home Assistant"]
  loop("agent_loop.py<br/>the loop")
  prompts("prompts.py<br/>system prompt")
  memory("memory.py<br/>empty for now")
  router("router.py<br/>picks the route")
  llm("llm_client.py<br/>calls Ollama")
  http("mcp_http.py<br/>calls the tools")
end
ollama("Ollama<br/>on the Mac")
mcp("web_search_mcp<br/>on the Mac")
laptop -- "a question" --> loop
entity -- "your text, chat log" --> loop
loop --> prompts
loop --> memory
loop --> router
loop --> llm
loop --> http
llm -- "chat, tool list" --> ollama
http -- "tool calls" --> mcp
class laptop,entity,loop,prompts,memory,router,llm,http,mcp ours
class ollama third
```

The agent is two Python packages. `assistant_core` holds the loop, the router, the system prompt, the model client, the MCP client, the memory seam, and the exchange record. The `studio_assistant` component adds only what Home Assistant needs to see an agent: an entity, a translation between Home Assistant's chat log and the loop's messages, and a settings form.

- **The rule.** Nothing in `assistant_core` imports Home Assistant, and nothing outside `custom_components/studio_assistant` imports the component.
- **Where the core runs.** Inside each caller: the benchmark's Python on the laptop, and Home Assistant's Python in the virtual machine. `assistant_core` is not a published package, so the deploy copies it into `custom_components/studio_assistant/vendor/`, and the component's `__init__.py` adds that folder to the import path when it exists. [Home Assistant](06_home_assistant_core.md#the-custom-component) covers the deploy.
- **Two consequences.**
    - `tools.py` imports the official `mcp` package lazily, inside `McpToolBox`, because Home Assistant ships an older `mcp` with a different client class. The component talks to the tool server through `HttpMcpToolBox` instead.
    - `manifest.json` lists `ollama==0.6.2` and `pydantic>=2.0`, which Home Assistant installs into its own environment at startup.

The component registers one entity per config entry, `conversation.studio_assistant`, declares `en` as its language, and declares that it supports streaming. Everything it does happens in two methods: `_stream_answer_into` runs the loop, and `_async_handle_message` calls it and decides what goes back to Home Assistant.

*From `custom_components/studio_assistant/conversation.py`, `StudioAssistantEntity._stream_answer_into` and `_async_handle_message`:*

```python
    async def _stream_answer_into(self, chat_log: conversation.ChatLog) -> Transcript:
        settings = {**self.entry.data, **self.entry.options}
        history = adapter.chat_log_to_conversation(chat_log.content)
        llm = await self.hass.async_add_executor_job(OllamaClient, settings[CONF_MODEL], settings[CONF_OLLAMA_URL], "30m")
        policy = adapter.policy_from_settings(settings)
        try:
            async with HttpMcpToolBox(settings[CONF_MCP_URL], client=get_async_client(self.hass), timeout_seconds=policy.tool_timeout_seconds) as tools:
                return await self._stream_events(chat_log, agent_loop.run(history, llm, tools, policy))
        except Exception as error:  # the tool server being down must not silence the assistant
            _LOGGER.warning("studio_assistant: search tool unavailable (%s); answering without it", error)
            return await self._stream_events(chat_log, agent_loop.run(history, llm, UnavailableToolBox(), policy))

    async def _async_handle_message(self, user_input: conversation.ConversationInput, chat_log: conversation.ChatLog) -> conversation.ConversationResult:
        transcript = await self._stream_answer_into(chat_log)
        if chat_log.content[-1].role != "assistant":
            chat_log.async_add_assistant_content_without_tools(conversation.AssistantContent(agent_id=self.entity_id, content=None))
        result = conversation.async_get_result_from_chat_log(user_input, chat_log)
        keep_listening = self._follow_up_listening.record_reply_and_decide(result.conversation_id, transcript)
        return conversation.ConversationResult(response=result.response, conversation_id=result.conversation_id, continue_conversation=keep_listening)
```

The two methods run in seven steps:

1. **Merge the settings.** The config entry's data is merged with its options, and the options win where both set a field.
2. **Rebuild the history.** `chat_log_to_conversation` keeps only the user and assistant messages that have text, so Home Assistant's own system prompt and the tool results of earlier exchanges are not replayed.
3. **Build the Ollama client on a worker thread.** Creating it opens an `httpx` client, which reads the certificate bundle from disk, and Home Assistant flags blocking reads on its event loop. The `"30m"` asks Ollama to keep the model loaded for thirty minutes after each request.
4. **Build the policy.** `policy_from_settings` copies the loop's defaults and overrides whichever fields the options form set.
5. **Run the loop.** The tool box connects to the MCP server for this one exchange and the loop runs. `agent_events_to_deltas` turns its events into one streamed assistant message, which Home Assistant writes into the chat log and, in a voice pipeline, hands to text to speech as it arrives.
6. **Fall back to no tools.** If the tool server cannot be reached, the entity logs a warning and runs the loop again with a tool box that lists no tools, so the model answers from what it knows.
7. **Return.** A reply that stayed silent streamed nothing, so an empty assistant entry is added to the chat log, which gives empty speech, and the pipeline skips text to speech. The result is read back out of the chat log and returned with `continue_conversation`, the flag that tells Home Assistant to keep the microphone open for a follow-up without waiting for the wake word. `FollowUpListening` sets it only after an ordinary answer, not after a silent reply or the "Okay." that acknowledges "never mind", at most `max_follow_ups` times in a row per conversation (2 by default), and only while the continue-conversation option is on, which it is by default.

The settings come from two forms:

| Form | When you see it | What it holds |
|---|---|---|
| Setup | When you add the integration | The Ollama address, the model tag, and the tool server address, with defaults of `http://192.168.1.152:11434`, `gemma4:e4b-it-qat`, and `http://192.168.1.152:8765/mcp` from `const.py`. The form calls Ollama's `/api/tags` and refuses an address that does not answer or a model tag that is not listed |
| Options | Later, from the integration's card | The model tag again, plus the loop policy: temperature, word budget, tool rounds, context tokens, output tokens, the thinking switch, the tool timeout, whether to continue the conversation, and how many follow-ups in a row are heard before the wake word is needed again |

Saving the options reloads the entry, so a change takes effect on the next question. The model the running system has picked is on the [Versions of Record](versions.md) page.

### One exchange

This follows one exchange for a question that needs a search, from your question to the spoken answer.

The first round, from your question to the filler sentence:

```mermaid
flowchart TB
--8<-- "_includes/palette.mmd"
%% grid: pipeline  agent  ollama
%% grid: .         mcp    .
%% peers: pipeline agent ollama mcp
%% column-gap: 210
subgraph mac["The Mac"]
  subgraph haos["Home Assistant VM"]
    pipeline("Assist pipeline<br/>speech in and out")
    agent("conversation agent<br/>studio_assistant")
  end
  ollama("Ollama<br/>the model")
  mcp("web_search_mcp<br/>the tools")
end
pipeline -- "1 your text, chat log" --> agent
agent -- "2 list tools" --> mcp
mcp -- "3 eleven tools" --> agent
agent -- "4 chat, tool list" --> ollama
ollama -- "5 call search_and_read" --> agent
agent -- "6 filler sentence" --> pipeline
class pipeline,ollama third
class agent,mcp ours
```

The second round, from the search to the spoken answer:

```mermaid
flowchart TB
--8<-- "_includes/palette.mmd"
%% grid: pipeline  agent  ollama
%% grid: .         mcp    .
%% peers: pipeline agent ollama mcp
%% column-gap: 210
subgraph mac["The Mac"]
  subgraph haos["Home Assistant VM"]
    pipeline("Assist pipeline<br/>speech in and out")
    agent("conversation agent<br/>studio_assistant")
  end
  ollama("Ollama<br/>the model")
  mcp("web_search_mcp<br/>the tools")
end
pipeline ~~~ agent
agent -- "7 search_and_read" --> mcp
mcp -- "8 excerpts" --> agent
agent -- "9 chat + excerpts" --> ollama
ollama -- "10 the answer, streamed" --> agent
agent -- "11 the answer, keep listening" --> pipeline
class pipeline,ollama third
class agent,mcp ours
```

Four things happen that the figures leave out:

- **The router's own call.** When no fixed rule matches the question, the [question router](#the-question-router) makes one quick classification call to Ollama between steps 3 and 4. A search decision adds a directive to the system prompt that step 4 sends.
- **The record of the exchange.** After the answer, the component posts a record of the exchange to the tool server's `/exchanges` route in a background task. A post that fails is dropped, and the answer is unaffected. [Operations](10_operations.md) covers what is done with the records.
- **Other questions.** A question that needs nothing has no second round: at step 5 Ollama answers at once, so no tool runs and no filler sentence is spoken. An arithmetic question calls a calculator tool instead of the search tool, and its filler sentence is about doing the math rather than checking the web; a question about the weather at home calls `weather_forecast`, with a filler sentence about the forecast.
- **Speaking while it runs.** The loop is an async generator. The component receives each piece of the answer as Ollama writes it, so the answer is being spoken while the loop is still running.

### Inside the loop

```mermaid
flowchart TB
--8<-- "_includes/palette.mmd"
%% grid: setup  model      tools
%% grid: .      done+last  .
%% peers: setup model tools done last
%% column-gap: 150
setup("set up<br/>system prompt, history<br/>tool list, route")
model("call the model<br/>speak text as it comes<br/>stops near 200 words")
tools("run the tools<br/>filler before the first<br/>results join the chat")
done("done<br/>the answer was spoken<br/>while it streamed")
last("one last answer<br/>a notice: no more tools<br/>answer from what it has")
setup --> model
model -- "asks for tools" --> tools
tools -- "the results" --> model
model -- "no tool calls" --> done
model -- "tools again after 4 rounds" --> last
class setup,model,tools,done,last ours
```

*From `assistant_core/agent_loop.py`, `run`:*

```python
async def run(conversation: list[Message], llm: LLMClient, tools: ToolBox, policy: AgentPolicy, memory: ConversationMemory | None = None) -> AsyncIterator[AgentEvent]:
    started = time.perf_counter()
    memory = memory or NoMemory()
    messages = build_messages(conversation, memory)
    transcript = Transcript(model=llm.model_name, system_prompt=system_prompt(), conversation=list(conversation))
    cap = SpokenAnswerCap(policy.word_budget)
    tool_specs = await load_tool_specs(tools, transcript)
    if policy.route_questions and tool_specs:
        transcript.route = await decide_route(llm, conversation, policy)
        messages = apply_route(messages, transcript.route)
    for round_index in range(policy.max_tool_rounds + 1):
        reply = ModelReply()
        async for event in stream_model_reply(llm, messages, tool_specs, policy, reply, cap, transcript, started):
            yield event
        ...
        record_model_reply(transcript, reply, messages)
        if not reply.tool_calls:
            break
        ...
        async for event in execute_tool_calls(tools, reply.tool_calls, round_index, policy, messages, transcript):
            yield event
    finish_transcript(transcript, reply, cap, messages, started)
    memory.remember(transcript.conversation)
    yield Done(transcript=transcript)
```

The setup happens once per exchange:

- **The system prompt.** `build_messages` puts it first and the conversation after it. It is version 1.7 in `assistant_core/prompts.py`:
    - the persona, Jarvis, a voice assistant in a small studio apartment;
    - today's date, filled in on every request, so a search query does not assume the year the model's training ended;
    - the rules for answering: lead with the answer, one to three sentences, plain spoken prose, no lists or URLs, say when you are estimating, draw on earlier exchanges in the conversation;
    - what to do when the text is unclear: reply exactly "Can you repeat that?" to a garbled request, "Okay." to "never mind", and the silence marker `*`, which is never spoken, to speech not meant for the assistant, such as a television;
    - when to search and when not to, and the rule to call the calculator for anything with more than one arithmetic step;
    - the rule to call `weather_forecast` for the weather at home and to search for the weather anywhere else.
- **Memory.** `memory.get_context` is asked what the assistant remembers about this user. `NoMemory` returns nothing, so no "What you remember about this user" paragraph is added. A real memory replaces that class and nothing else.
- **The tools and the route.** The tool schemas are listed from the tool server, and the [question router](#the-question-router) adds its directive to the system prompt.

Each pass through the `for` loop is one call to the model:

- **Text.** `stream_model_reply` passes each text delta through `SilenceMarkerHold`, which holds it back while the reply could still be the silence marker `*`, and then through `SpokenAnswerCap`. Whatever the cap admits is yielded as an `AnswerDelta`.
- **The filler.** The first tool request yields a `FillerSpoken` event before the call is collected, unless something has already been spoken in this exchange, so a second round of tools gets no second filler. The line is picked at random from three lists in `AgentPolicy`:
    - three web lines when the tool is `search_and_read`, `web_search`, or `fetch_page`;
    - two forecast lines when the tool is `weather_forecast`;
    - two arithmetic lines otherwise, because "checking the web" is wrong when the assistant is only doing sums on the Mac.
- **The tools.** `execute_tool_calls` runs the calls in order and appends each result to the messages as a tool message with the call's id and name.

Ollama reports a tool call within a second of the model starting to write, so the filler plays long before the search finishes.

When the loop ends, `finish_transcript` records the model's last message as `final_answer`, what the listener heard as `spoken_text`, whether the reply was the silence marker as `stayed_silent`, and the total time. The `Done` event carries the transcript to the caller: the benchmark hands it to the judge, and the component logs a one-line summary at debug level and posts the exchange record to the tool server's [`/exchanges` route](03_web_search_mcp.md#plain-routes-and-the-host-check).

The loop keeps a few promises whatever the model does, each a line of code rather than a sentence in the prompt:

| What happens | What the loop does | Where it shows in the transcript |
|---|---|---|
| The model replies with only the silence marker `*` | `SilenceMarkerHold` holds back the start of each reply while it could still be the marker, so the marker is never spoken; an ordinary answer is released from its first chunk | `stayed_silent` is true and `spoken_text` is empty |
| The answer runs past the word budget | `SpokenAnswerCap.admit` counts the words in each delta and closes at the first sentence end past 200. Later text is still collected as `final_answer` but not spoken | `truncated` is true, `spoken_text` is shorter than `final_answer` |
| The model asks for tools again after four rounds | Every pending call gets `TOOL_LIMIT_NOTICE`, "Tool call limit reached. Answer the user now with what you already know; do not call any more tools.", as its result. That last answer streams and is spoken like any other | `hit_tool_round_cap` is true |
| A tool call fails or runs past `tool_timeout_seconds` | The result the model sees is "The web search tool is unavailable right now. Tell the user you could not check the web, then answer from your own knowledge with that caveat." The timeout is 60 s in the benchmark's config and the options form, and 30 s when neither sets it | `tool_call_records[n].error` names the exception |
| The tool server cannot be reached | The loop runs with no tools and no route, because a directive to call a tool the model cannot see would only confuse it | `error` starts with "tool server unavailable" when listing the tools fails. When the component cannot connect at all, it swaps in a tool box with no tools (step 6 above) and no error is recorded |
| The model returns neither words nor a tool call | The same messages are sent once more, once per exchange (`EMPTY_COMPLETION_RETRIES`), before the empty answer is accepted | `empty_completion_retries` is 1 and `model_calls` has one entry more than expected |
| Nothing at all was spoken, and the reply was not the silence marker | The adapter yields "Sorry, I could not come up with an answer to that." so the pipeline has something to say | `final_answer` is empty and `stayed_silent` is false |

The empty-reply retry exists because Gemma 4 on Ollama sometimes writes a tool call with a small formatting slip that Ollama's parser drops silently, and the reply arrives with no content. Read aloud, that is silence. A model that returns nothing twice is not going to answer.

The component keeps nothing between exchanges. A follow-up arrives as a new `_async_handle_message` with the same conversation id, the identifier Home Assistant uses to group exchanges into one conversation, and a chat log that already holds the earlier exchanges, and `chat_log_to_conversation` rebuilds the history from it. The benchmark's follow-up questions take the same shape, and `tests/test_agent_loop.py` checks that the second call sees system, user, assistant, user in that order.

### The question router

```mermaid
flowchart TB
--8<-- "_includes/palette.mmd"
%% grid: question  rules   .          model
%% grid: .         search  calculate  answer
%% peers: question rules model search calculate answer
question("your question<br/>the latest thing<br/>you said")
rules("the rules<br/>a pattern match<br/>costs nothing")
model("ask the model<br/>one quick call<br/>about a second")
search("search<br/>a SEARCH note<br/>in the system prompt")
calculate("calculate<br/>a CALCULATE note<br/>in the system prompt")
answer("answer<br/>nothing added<br/>or if the call fails")
question --> rules
rules -- "no match" --> model
rules -- "#quot;look it up#quot;" --> search
rules -- "#quot;15% of $80#quot;" --> calculate
model --> search
model --> calculate
model --> answer
class question third
class rules,model,search,calculate,answer ours
```

A model decides whether to call a tool from the tool descriptions and the system prompt alone, and Ollama has no switch that forces a call. Small models answer "what is the current rate" from memory, and set up arithmetic correctly and then miscompute it. So before the first real call, the loop decides which tool family the question needs and says so in the system prompt. The decision is a `RouteDecision` in `assistant_core/models.py`, holding the route, the layer that decided it (`rule`, `model`, or `none` when there is no user message), a detail string, and the time it took. It is stored on the transcript so the benchmark can score the router apart from the answer.

The rules read only the latest user message. They hold three patterns, checked in order, so an explicit request to search wins over arithmetic, and arithmetic wins over weather:

*From `assistant_core/router.py`, `rule_route`:*

```python
def rule_route(text: str) -> RouteDecision | None:
    if EXPLICIT_SEARCH.search(text):
        return RouteDecision(route=Route.SEARCH, source="rule", detail="explicit request to search")
    numbers = NUMBER.findall(text)
    cue = ARITHMETIC_CUE.search(text)
    if len(numbers) >= MIN_NUMBERS_FOR_ARITHMETIC and cue:
        return RouteDecision(route=Route.CALCULATE, source="rule", detail=f"{len(numbers)} numbers and cue '{cue.group(0)}'")
    weather_cue = forecast_cue(text)
    if weather_cue and not EXPLANATION_CUE.search(text) and not names_another_place(text):
        return RouteDecision(route=Route.WEATHER, source="rule", detail=f"{weather_cue} and no other place named")
    return None
```

- **`EXPLICIT_SEARCH`** needs an imperative such as "search for", "look up", "google it", or "find me the latest". The noun "web search" on its own does not match.
- **Arithmetic** needs at least two numbers and one cue. A number may carry a dollar sign, commas, a decimal part, or a percent sign. The cues include a percent sign after a digit, "per month", "kilowatt", "interest", "mortgage", "tip", "convert", "degrees", "times", "plus", "divided", and "in total".
- **Weather** needs "weather", "umbrella", or "the forecast", or a rain or snow word together with a time such as "tomorrow" or a question form such as "will it". It does not fire on a question asking why, or on one that names another place, such as "in Lisbon".
- **The test.** `tests/test_router.py` runs every benchmark question through the rules and asserts that none fires on a question whose expected route is different.

When no rule matches, `model_route` asks the same model, and `OllamaClient.classify` sends:

- `ROUTER_SYSTEM_PROMPT`, which defines the four routes with examples, then up to two earlier user messages for context, then the question;
- the JSON schema `{"route": "search" | "calculate" | "weather" | "answer"}` in Ollama's `format` field, which asks for structured output: Ollama constrains generation so the reply is always valid JSON holding one of the four;
- temperature 0, the sampling setting at which the model picks its most likely token every time, then at most 40 output tokens, no streaming, and thinking off;
- the chat calls' context length of 16,384 tokens, because Ollama reloads a model whose context length changes, and the reload would cost about five seconds twice per question.

A failure anywhere in this call, from a refused connection to unparseable JSON, is recorded in `detail`.

`apply_route` returns a copy of the messages with one paragraph added to the end of the system prompt. For `answer` it returns the messages unchanged. The user's message is always left exactly as spoken.

- **Search:** "Routing for this question: SEARCH. This question needs current information from the web. Call search_and_read first; do not answer it from memory. Answer from the excerpts it returns." It ends with one example call, `search_and_read(query="used RTX 3090 price")`.
- **Calculate:** it names the eight calculator tools, says "do not do the math yourself", and ends with `percent(kind="of", a=15, b=80)`.
- **Weather:** it says to call `weather_forecast` first, not to search or answer from memory, and ends with `weather_forecast(day="tomorrow", part_of_day="afternoon")`. When the tool server does not offer `weather_forecast`, `route_to_offered_tools` turns a weather decision into search before the directive is added.

Each ends with the example call and nothing after it, because the smaller models imitated a finished answer in the example instead of making the call.

The whole router turns off with the `route_questions` field of `AgentPolicy`. The benchmark can set it in the `policy` section of `benchmark/config.yaml` to measure the router's effect, and its report says whether routing was on.

## Run it yourself

Everything in the first block runs on the laptop with no services at all. The loop's tests replace the model with a scripted client and the tool server with a fake that answers every call with one numbered source, and they exercise the promises from the table above: the filler before the tool, the round cap, the failed tool, the dead tool server, the word budget, the follow-up history, the arithmetic filler, and the empty-completion retry. The router's tests run the rule layer over the whole benchmark question set and check the directive lands in the system prompt.

```bash
uv run pytest -q tests/test_agent_loop.py tests/test_router.py
```

You should see `28 passed` in well under a second. The tests exit on their own. Add `tests/test_prompts.py` and `tests/test_component_adapter.py` to the command to cover the date line and the chat log translation as well. To read the exact system prompt the model sees today, date line included, print it:

```bash
uv run python -c "from assistant_core.prompts import system_prompt; print(system_prompt())"
```

The rest needs the Home Assistant virtual machine and the Mac-side services. Start the VM as [Home Assistant](06_home_assistant_core.md#run-it-yourself) describes, load `.env` into the terminal, and check that no benchmark is running. Then open the Overview dashboard at http://192.168.1.156, choose **Assist** from the three-dot menu at the top right, and type these four questions in turn:

1. "Why does bread rise?" answers from the model in 2 to 5 seconds once the model is warm. The first question after a long idle can take 30 seconds or more while Ollama loads the model.
2. "What is 18 percent of 245 dollars?" shows "Let me work that out." first, then the answer. That first sentence is the filler, written while the calculator runs.
3. "Search the web for the current price of the Home Assistant Voice Preview Edition." shows the web filler, then an answer built from the search excerpts, in 10 to 25 seconds.
4. "And what did I ask you first?" is a follow-up. The chat log carries the earlier exchanges, so the answer names the bread question.

The microphone button in the browser only works over HTTPS, which the VM does not have, so typing is the way here; voice is covered in [Voice Pipeline](05_voice_pipeline.md). The same call from a terminal is the request the pipeline makes internally, and it lets you time it:

```bash
ask() { curl -s -m 240 -X POST http://192.168.1.156/api/conversation/process \
  -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
  -d "{\"text\": \"$1\", \"language\": \"en\", \"agent_id\": \"conversation.studio_assistant\"${2:+, \"conversation_id\": \"$2\"}}" \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["response"]["speech"]["plain"]["speech"]); print("conversation_id:", d["conversation_id"])'; }

time ask "If I put 300 dollars a month into an account paying 5 percent a year, how much do I have after 3 years?"
```

You see the spoken text, filler included, then a line `conversation_id: ...`, then the `time` output. Pass that id as a second argument to continue the same conversation, and the answer will use the figures from the first question:

```bash
ask "And after 5 years?" 01M1VPD9JAPX816PT6V0PHNNVZ
```

While a question runs, a second terminal shows the pieces working: `ollama ps` lists the model resident on the GPU, and `scripts/services.sh logs mcp` tails the tool server's log, where each `tools/call` appears with its query; press Ctrl-C to stop tailing. The most useful view is Home Assistant's own. Under Settings, Voice assistants, open Jarvis, then the three-dot menu, then Debug. The last run lists every stage with its timing and the exact text that passed between them, including the agent's reply with the filler at the front. Nothing about the agent needs stopping: it runs only while a question is in flight. When you are done, stop the VM with `scripts/haos_vm.sh stop` as [Home Assistant](06_home_assistant_core.md#run-it-yourself) describes.

## Where to look in the code

| Path | What you find there |
|---|---|
| [`assistant_core/agent_loop.py`](https://github.com/seanlin2000/home_assistant/blob/main/assistant_core/agent_loop.py) | `run`, the loop itself; `stream_model_reply`, where the filler is yielded; `SilenceMarkerHold`, which keeps the silence marker from being spoken; `SpokenAnswerCap`, the word budget; `execute_tool_calls`; the tool-limit and tool-unreachable notices; the empty-completion retry |
| [`assistant_core/router.py`](https://github.com/seanlin2000/home_assistant/blob/main/assistant_core/router.py) | The patterns of the rule layer, `ROUTER_SYSTEM_PROMPT`, the three directives, `decide_route`, `route_to_offered_tools`, and `apply_route` |
| [`assistant_core/prompts.py`](https://github.com/seanlin2000/home_assistant/blob/main/assistant_core/prompts.py) | The system prompt, its version number, the persona name, the silence marker and the two fixed replies, and `system_prompt`, which inserts the date line |
| [`assistant_core/models.py`](https://github.com/seanlin2000/home_assistant/blob/main/assistant_core/models.py) | Every type the loop speaks: `Message`, `ToolCall`, `AgentPolicy` with its defaults, the filler phrase lists, the model-client and agent events, `RouteDecision`, and `Transcript` |
| [`assistant_core/llm_client.py`](https://github.com/seanlin2000/home_assistant/blob/main/assistant_core/llm_client.py) | The `LLMClient` protocol and `OllamaClient`: the streaming chat request, the `classify` call with a JSON schema, and the conversions to and from Ollama's message shapes |
| [`assistant_core/mcp_http.py`](https://github.com/seanlin2000/home_assistant/blob/main/assistant_core/mcp_http.py) | `HttpMcpToolBox`, the MCP client the component uses: initialize, `tools/list`, `tools/call`, and the parser for JSON or server-sent-events replies |
| [`assistant_core/tools.py`](https://github.com/seanlin2000/home_assistant/blob/main/assistant_core/tools.py) | The `ToolBox` protocol the loop depends on, and `McpToolBox`, the benchmark's client on the official `mcp` package |
| [`assistant_core/memory.py`](https://github.com/seanlin2000/home_assistant/blob/main/assistant_core/memory.py) | The `ConversationMemory` protocol and `NoMemory` |
| [`assistant_core/exchange_record.py`](https://github.com/seanlin2000/home_assistant/blob/main/assistant_core/exchange_record.py) | `ExchangeRecord`, `exchange_record_from_transcript`, and `exchanges_url_from_mcp_url`, the rule that maps the MCP address to the `/exchanges` address |
| [`custom_components/studio_assistant/conversation.py`](https://github.com/seanlin2000/home_assistant/blob/main/custom_components/studio_assistant/conversation.py) | `StudioAssistantEntity`, `_async_handle_message`, `_stream_answer_into`, `_record_exchange` with its exchange-record background task, and `UnavailableToolBox` |
| [`custom_components/studio_assistant/adapter.py`](https://github.com/seanlin2000/home_assistant/blob/main/custom_components/studio_assistant/adapter.py) | `chat_log_to_conversation`, `agent_events_to_deltas`, `policy_from_settings`, `post_exchange_record`, and `FollowUpListening`, the follow-up cap, all free of Home Assistant imports so the laptop can test them |
| [`custom_components/studio_assistant/config_flow.py`](https://github.com/seanlin2000/home_assistant/blob/main/custom_components/studio_assistant/config_flow.py) and [`const.py`](https://github.com/seanlin2000/home_assistant/blob/main/custom_components/studio_assistant/const.py) | The setup form with its Ollama check, the options form, and every default address and policy value |
| [`custom_components/studio_assistant/manifest.json`](https://github.com/seanlin2000/home_assistant/blob/main/custom_components/studio_assistant/manifest.json) | The component's domain, version, and the two packages Home Assistant installs for it |
| [`tests/test_agent_loop.py`](https://github.com/seanlin2000/home_assistant/blob/main/tests/test_agent_loop.py), [`tests/test_router.py`](https://github.com/seanlin2000/home_assistant/blob/main/tests/test_router.py), [`tests/test_component_adapter.py`](https://github.com/seanlin2000/home_assistant/blob/main/tests/test_component_adapter.py), [`tests/test_prompts.py`](https://github.com/seanlin2000/home_assistant/blob/main/tests/test_prompts.py) | The offline tests, with `tests/fakes.py` supplying the scripted model and the fake tool server |

## Further reading

- Design doc: [`design_docs/v1/04_conversation_agent.md`](https://github.com/seanlin2000/home_assistant/blob/main/design_docs/v1/04_conversation_agent.md), which also lists the failure modes and the benchmark evidence behind the router and each prompt version
- [Home Assistant conversation entity](https://developers.home-assistant.io/docs/core/entity/conversation), for the methods `StudioAssistantEntity` implements and what the pipeline expects back
- [Home Assistant chat log and LLM API](https://developers.home-assistant.io/docs/core/llm/), for the content types in a `ChatLog` and how streamed deltas become an assistant message
- [Home Assistant Voice chapter 10](https://www.home-assistant.io/blog/2025/06/25/voice-chapter-10/), for what `continue_conversation` does on a voice device
- [Home Assistant text to speech](https://www.home-assistant.io/integrations/tts/), for which engines can start speaking on a stream, which is what makes the filler sentence worth having
- [Ollama API](https://github.com/ollama/ollama/blob/main/docs/api.md), for the chat request with `tools`, the `tool_calls` field in the reply, and the `format` argument the router relies on
