# LLMs on Apple Silicon
<!-- complexity: packages=2 parts=2 concepts=3 tier=standard -->

This part is the model itself: the program that turns a question, a persona, and a page of search excerpts into an answer, one token at a time, on the Mac in the room. Ollama downloads the model, keeps it in the Mac's memory, runs it on the GPU, and answers HTTP requests from the conversation agent and from the benchmark. Nothing about the question or the answer leaves the machine.

## Where this fits

```mermaid
flowchart TB
--8<-- "_includes/system_map.mmd"
class ollama current
```

Ollama receives, from the conversation agent or from the laptop's benchmark, the chat so far plus the schemas of the tools the model may call, and returns a stream of tokens or a structured tool call. It talks to nothing else: it reads the model's weights from disk once, keeps them in memory, and runs on the Mac's GPU.

## Key definitions

| Term | Meaning |
|---|---|
| Parameters | The learned numbers inside a model, counted in billions ("26B"), where more of them means more capability and more memory. |
| Mixture of experts (MoE) | A model whose layers are split into many "experts" with a small router picking a few per token, so it holds every expert in memory but runs nearly as fast as a much smaller model. |
| Quantization | Storing model weights at 4 or 3 bits instead of 16, where 4-bit cuts memory about four times with a small quality loss and 3-bit cuts further with a noticeable one. |
| Unified memory | One pool of memory shared by the CPU and GPU on Apple Silicon, whose size decides which models fit. |
| Memory bandwidth | How many bytes per second move between unified memory and the chip, in GB/s. |
| Compute | Arithmetic operations per second, which on a Mac scales with the number of GPU cores. |
| KV cache | The model's working memory for the current context, which costs memory in proportion to context length and saves recomputation. |
| Context window | The maximum number of tokens the model can see at once: the system prompt, the conversation, and tool results together. |
| Prefill | Reading the whole prompt in one batch before the first token, which is limited by compute. |
| Decode | Writing the answer one token at a time, which is limited by memory bandwidth. |
| Time to first token | How long the model takes to read the prompt before it starts writing, which prefill sets and which grows with prompt length. |
| Tokens per second | How fast the model writes once it has started, which decode sets and which keeps up with speech above about three to four. |
| Model tag | The name Ollama uses for one downloadable build of a model, such as `gemma4:e4b-it-qat`, whose part after the colon names the size and quantization. |
| Keep-alive | How long Ollama keeps a model's weights in memory after the last request: zero unloads at once, a duration such as `10m` unloads after that idle time, and `-1` keeps the model resident until Ollama stops. |
| Thinking mode | A setting on recent models that makes them write a hidden chain of reasoning before the answer, which helps hard problems and multiplies latency. |

## Packages and tools

| Tool | What it is | How this part uses it |
|---|---|---|
| Ollama 0.33.3 | A program, installed with Homebrew, that downloads open-weight models and serves them over HTTP on port 11434 | Hosts the model, loads it into unified memory, parses each model family's tool-call format, and reports timing statistics with every answer. The agent, Home Assistant, and the benchmark all speak its API |
| MLX and Metal | Apple's machine learning framework and the GPU interface beneath it, built into Ollama on Apple Silicon | The reason generation runs on the GPU instead of the CPU. Nothing in this repository calls them directly |
| `ollama` Python package 0.6.2 | A thin typed client for the Ollama HTTP API | `OllamaClient` in `assistant_core/llm_client.py` streams chat responses through it; `benchmark/ollama_utils.py` uses it to list, load, inspect, and unload models |
| launchd | macOS's service manager | `scripts/services.sh install` writes a launchd agent that starts `ollama serve` at login, keeps it alive, binds it to the LAN, and keeps the model resident |

## How it works

### Memory cost

```mermaid
flowchart TB
--8<-- "_includes/palette.mmd"
%% grid: macos  haos     ollama  whisper
%% grid: .      .        weights+kv  .
%% peers: macos haos ollama whisper
%% peers: weights kv
subgraph pool["The prototype Mac's 16 GB of unified memory"]
  macos("macOS<br/>about 3 GB")
  haos("Home Assistant VM + Piper<br/>3 to 4 GB")
  ollama("Ollama<br/>about 7.5 GB")
  whisper("Whisper<br/>1.6 GB")
  weights[("weights, 4-bit<br/>gemma4:e4b-it-qat<br/>6.1 GB")]
  kv[("KV cache<br/>1 to 2 GB<br/>at 16k tokens")]
end
ollama -- "loaded once" --> weights
ollama -- "grows with context" --> kv
class macos,haos,ollama,whisper,weights,kv third
class ollama current
```

A model is a large array of numbers, its parameters, and running it means reading all of them for every token it writes. On Apple Silicon there is one pool of memory for the CPU and the GPU, so the question "does this model fit" is the question "do the weights plus the working memory fit next to everything else the Mac is running."

A model costs memory in two places:

- **Weights:** \(\text{bytes} = \text{parameters} \times \text{bits} \div 8\), so a 4-bit model is about a quarter of its 16-bit size. Models are published at 16 bits per parameter and stored for local use at 4 bits plus a little overhead, which is why the sizes below are small for their parameter counts.
- **KV cache:** for every token in the context window the model keeps a few vectors so it never recomputes attention over earlier tokens, so the cache grows linearly with context length. The agent's context window of 16,384 tokens (`DEFAULT_CONTEXT_TOKENS` in `custom_components/studio_assistant/const.py`) costs 1 to 2 GB for the models in play.

| Model tag | Parameters | Weights in memory | With a 16k KV cache | Runs on the 16 GB prototype |
|---|---|---|---|---|
| `qwen3.5:4b` | 4B dense, 4-bit | 3.4 GB | about 5 GB | yes, fully on the GPU |
| `gemma4:e4b-it-qat` | 4B effective, 4-bit | 6.1 GB | about 7.5 GB | yes, fully on the GPU |
| `qwen3.5:9b` | 9B dense, 4-bit | 6.6 GB | about 8 GB | yes, fully on the GPU |
| `gemma4:12b` | 12B dense, 4-bit | 7.6 GB | about 9 GB | yes, fully on the GPU |
| Gemma 4 26B-A4B | 26B total, 4B active, 4-bit | 15 to 17 GB | 17 to 19 GB | no; the benchmark's 3-bit and 4-bit previews both spilled to the CPU |

The first four sizes are what `ollama list` reports on the prototype. The same tag can point at a different build after a re-pull, so `docs/VERSIONS.md` records each tag's build id. The last row is the model the benchmark points at for a 32 GB machine (see [Benchmarking and Model Selection](01_llm_benchmark.md)), and it shows why a mixture-of-experts model suits one: the Mac must hold all 26 billion parameters, but each token computes with only the 4 billion active ones, so it writes at a small model's speed with a large model's quality.

On a 32 GB Mac running that model, the memory budget is the mid tier of [the Hardware page's budget](08_hardware_and_deployment.md#the-memory-budget):

| What is resident | Memory |
|---|---|
| macOS | about 3 GB |
| The Home Assistant VM, with Piper and the other add-ons | 3 to 4 GB |
| Whisper | about 2.5 GB |
| Kokoro | about 1 GB |
| SearXNG in Docker Desktop | about 1.7 GB |
| The model's weights, Gemma 4 26B-A4B at 4-bit | about 16 GB |
| Its KV cache at 16k tokens | 1 to 2 GB |
| **Total** | **about 28 to 30 GB** |

When a model does not fit, Ollama does not refuse. It puts what it can on the GPU, runs the rest on the CPU, and generation slows to a crawl. [Keeping a model resident](#keeping-a-model-resident) shows how the benchmark detects this.

### Prefill and decode

```mermaid
%%{init: {"flowchart": {"wrappingWidth": 260}}}%%
flowchart TB
--8<-- "_includes/palette.mmd"
%% grid: client   .
%% grid: prefill  decode
%% peers: prefill decode
client("OllamaClient<br/>our agent")
subgraph gpu["Ollama, on the Mac's GPU"]
  prefill("prefill<br/>read the whole prompt at once<br/>limited by compute<br/>sets time to first token")
  decode("decode<br/>write the answer, token by token<br/>limited by memory bandwidth<br/>sets tokens per second")
end
client -- "conversation + tool list" --> prefill
prefill --> decode
decode -- "each token, or a tool call" --> client
class client ours
class prefill,decode third
```

Every question is one or more of these requests: the agent posts the message history, the tool schemas, and a few options, asks for a stream, and Ollama answers in two phases limited by different parts of the chip.

1. **Prefill.** Every token of the system prompt, the conversation so far, and any search excerpts passes through the model in one batch. The GPU multiplies large matrices and memory is not the bottleneck, so prefill is compute-bound: arithmetic throughput limits it. It sets the time to first token, which grows with prompt length. After a web search the prompt carries 3,000 to 6,000 tokens of page text, so this wait decides whether the answer starts in two seconds or eight.
2. **Decode.** Each new token is one forward pass, which reads the weights of every active layer out of memory. Little arithmetic is reused between tokens, so decode is memory-bandwidth-bound: its speed is memory bandwidth divided by the bytes of weights read per token, and it sets the tokens per second. That is why Apple's fast unified memory competes with discrete GPUs here, and why a mixture-of-experts model, which reads only its active experts, decodes much faster than a dense model of the same total size. Speech plays at three to four tokens per second, so anything faster than about five stays ahead of the voice once streaming starts.

If the model decides to use a tool, Ollama parses its structured output and returns a `tool_calls` field instead of text; the agent runs the tool and posts the whole conversation again (see [Conversation Agent](04_conversation_agent.md#one-exchange)). The final chunk carries the token counts and the durations of both phases in nanoseconds, which `ollama_stats` in `assistant_core/llm_client.py` turns into the statistics the benchmark records.

`OllamaClient._stream`, from `assistant_core/llm_client.py`, builds the request:

```python
    async def _stream(self, messages: list[Message], tools: list[ToolSpec], policy: AgentPolicy) -> AsyncIterator[ollama.ChatResponse]:
        request: dict[str, Any] = {
            "model": self._model,
            "messages": [to_ollama_message(message) for message in messages],
            "tools": [to_ollama_tool(tool) for tool in tools] or None,
            "stream": True,
            "keep_alive": self._keep_alive,
            "options": {"temperature": policy.temperature, "num_ctx": policy.context_tokens, "num_predict": policy.max_output_tokens},
        }
        if policy.think is not None:
            request["think"] = policy.think
        try:
            return await self._client.chat(**request)
        except ollama.ResponseError as error:
            if "think" not in str(error).lower() or "think" not in request:
                raise
            # Some model families reject the thinking switch outright; they have no thinking mode to turn off.
            del request["think"]
            return await self._client.chat(**request)
```

Three options matter here:

- `num_ctx` is the context window, 16,384 tokens. Every request sends the same value, because Ollama reloads the model when the context length changes, about five seconds for a 6 GB model.
- `num_predict` caps the answer at 600 tokens.
- `think` switches thinking mode. A model left to think can spend its whole output budget reasoning in private and return nothing to say aloud. The chat calls send `false` once the integration's options form has been saved. Before that they send no `think`, so the model's own default applies. The question router always sends `false`. The benchmark sets it per candidate: `false` for Gemma 4 and Qwen, `low` for gpt-oss.

### Reading a Mac spec sheet

Four lines on an Apple spec sheet decide how a model runs on the machine:

| Spec sheet line | What it limits | Grows with | What you feel |
|---|---|---|---|
| Unified memory (GB) | which models fit, with their KV cache, next to everything else | the model's total parameters, its bits per parameter, and the context length | whether the model runs at all, or spills to the CPU and crawls |
| Memory bandwidth (GB/s) | decode speed, the tokens per second | the model's active parameters, the bytes read per token | whether the voice ever has to pause mid-sentence |
| GPU cores | prefill speed, the time to first token | prompt length: system prompt, history, search excerpts | the silence before the answer starts |
| Neural Engine (TOPS) | nothing here, because Ollama runs the model on the GPU through Metal | | |

Decode reads the active weights once per token, so memory bandwidth sets a ceiling on its speed:

$$\text{tokens per second} \approx \frac{\text{memory bandwidth}}{\text{bytes of active weights read per token}}$$

Prefill does about two arithmetic operations, a multiply and an add, for every active parameter and every prompt token:

$$\text{prefill operations} \approx 2 \times \text{active parameters} \times \text{prompt tokens}$$

`gemma4:e4b-it-qat` reads about 2 GB of weights per token, its 4 billion effective parameters at 4 bits. Gemma 4 26B-A4B reads about 2.5 GB: its 4 billion active parameters at about 0.6 bytes each, since its 26 billion take 15 to 17 GB. The first rule then gives each machine's decode ceiling:

- **The prototype, an Apple M1 Pro with 16 GB, a 14-core GPU, and 200 GB/s:** at most about 100 tokens per second for `gemma4:e4b-it-qat`. Gemma 4 26B-A4B's ceiling would be 80, but the model does not fit in 16 GB.
- **Mac mini M6 with 24 or 32 GB, a 12-core GPU, and 170 GB/s:** at most about 85 for `gemma4:e4b-it-qat` and 68 for Gemma 4 26B-A4B. A dense 26B model of the same 15 GB would be capped near 11.
- **Mac mini M5 Pro with 48 GB, a 16- or 20-core GPU, and 307 GB/s:** at most about 150 for `gemma4:e4b-it-qat` and 120 for Gemma 4 26B-A4B.

These are upper bounds: no chip reaches its full bandwidth, and the benchmark measured `gemma4:e4b-it-qat` at about 41 tokens per second on the prototype. By the second rule, a 5,000-token searched prompt costs Gemma 4 26B-A4B about 40 trillion operations, and the GPU's arithmetic rate, which grows with its cores, decides how long that takes. The M5 and M6 add neural accelerators to every GPU core, which [Apple measured](https://machinelearning.apple.com/research/exploring-llms-mlx-m5) cutting time to first token 3.3 to 4 times against the M4.

### Keeping a model resident

```mermaid
flowchart LR
--8<-- "_includes/palette.mmd"
%% grid: registry  disk  memory
%% peers: disk memory
registry("model registry<br/>Ollama library<br/>or Hugging Face")
disk[("on disk<br/>Ollama's model store")]
memory[("in unified memory<br/>ready to answer")]
registry -- "ollama pull" --> disk
disk -- "first request" --> memory
memory -- "keep-alive runs out,<br/>or ollama stop" --> disk
class registry ext
class disk,memory third
```

Loading a model means reading gigabytes from disk, so Ollama loads on the first request and keeps the model resident for the keep-alive period. Each request resets the keep-alive. `ollama rm`, or `delete_model` in the benchmark, deletes a model from disk.

`scripts/services.sh install` writes a launchd agent that runs `ollama serve` with three settings:

- `OLLAMA_HOST=0.0.0.0:11434`, so the Home Assistant VM can reach it across the LAN.
- `OLLAMA_KEEP_ALIVE=-1`, so the model never unloads on its own and the first question of the day is not slow.
- `OLLAMA_MAX_LOADED_MODELS=1`, so a second model is never loaded beside the first.

The Home Assistant component points at `http://192.168.1.152:11434` and defaults to `gemma4:e4b-it-qat` (`custom_components/studio_assistant/const.py`); the model the running system has picked is on the [Versions of Record](versions.md) page.

The benchmark uses the same server with a different rhythm, because it walks through every candidate on a machine that holds one at a time. For each candidate, `benchmark/ollama_utils.py`:

1. Pulls the tag if it is missing.
2. Warms the model up with a one-token request.
3. Checks through Ollama's `/api/ps` endpoint that the model sits entirely on the GPU.
4. Unloads it afterwards with a keep-alive of zero.

`memory_fit`, from `benchmark/ollama_utils.py`, reads `/api/ps`:

```python
async def memory_fit(client: ollama.AsyncClient, model: str) -> MemoryFit:
    running = await client.ps()
    for entry in running.models:
        if entry.model == model:
            return MemoryFit(model_size_bytes=entry.size, gpu_resident_bytes=entry.size_vram, fully_on_gpu=bool(entry.size and entry.size_vram and entry.size_vram >= entry.size))
    return MemoryFit()
```

A model whose `size_vram` is smaller than its `size` has spilled to the CPU. The benchmark report prints this as the "Fully on GPU" column, so a slow candidate is never mistaken for a slow model when the machine was the limit.

## Run it yourself

Ollama is always running on the Mac, so nothing needs starting. Check that it is listening and see which model, if any, is in memory:

```bash
scripts/services.sh status
ollama ps
```

You should see `ollama: listening on 11434` in the first output. The second prints a table with the columns `NAME`, `ID`, `SIZE`, `PROCESSOR`, `CONTEXT`, and `UNTIL`; it is empty when no model is loaded. Now talk to the raw model, with no persona, no tools, and no word cap:

```bash
ollama run gemma4:e4b-it-qat "In one sentence, why does bread rise?"
```

The first call after a while takes 5 to 30 seconds while the weights load; later calls answer in a second or two. Run `ollama ps` again and the model is listed with `100% GPU` under `PROCESSOR` and, under `UNTIL`, how long it stays loaded: `Forever` on a Mac where the launchd agent is installed, because the agent sets `OLLAMA_KEEP_ALIVE=-1`. To unload it by hand:

```bash
ollama stop gemma4:e4b-it-qat
```

To measure the two speeds on this machine, run the speed script for one candidate. It loads the model, times a 400-word prompt and a 3,000-word prompt, generates 128 tokens after each, unloads the model, and takes about a minute:

```bash
uv run python scripts/benchmark_llm.py --help
uv run python scripts/benchmark_llm.py --run version_5 --candidate gemma4-e4b
```

You should see a table titled "Raw speed on this machine": one row per prompt length with the prompt token count, the prompt processing rate, the time to first token, the generation rate, and whether the model was fully on the GPU. The same table is written to `benchmark/results/version_5/speed.md`. Candidate keys come from `benchmark/config.yaml`; leaving out `--candidate` measures every Ollama candidate, pulls any that are missing, and must not run while the Home Assistant VM is up. Press Ctrl-C to stop early; the model unloads when its ten-minute keep-alive expires, or at once with `ollama stop`.

## Where to look in the code

| Path | What you find there |
|---|---|
| [`assistant_core/llm_client.py`](https://github.com/seanlin2000/home_assistant/blob/main/assistant_core/llm_client.py) | `OllamaClient`: the streaming chat request, the tool-call and message conversions, the non-streaming `classify` call the router uses, and `ollama_stats`, which turns Ollama's nanosecond counters into seconds |
| [`benchmark/ollama_utils.py`](https://github.com/seanlin2000/home_assistant/blob/main/benchmark/ollama_utils.py) | The model lifecycle around a benchmark run: `ensure_model_present`, `warm_up`, `memory_fit`, `unload`, `delete_model` |
| [`scripts/benchmark_llm.py`](https://github.com/seanlin2000/home_assistant/blob/main/scripts/benchmark_llm.py) | The raw speed measurement: prompt processing and generation rates at a short and a long prompt, written to `speed.md` |
| [`scripts/services.sh`](https://github.com/seanlin2000/home_assistant/blob/main/scripts/services.sh) | `install_agents`, which writes the Ollama launchd agent with its LAN binding, keep-alive, and single-model limit |
| [`custom_components/studio_assistant/const.py`](https://github.com/seanlin2000/home_assistant/blob/main/custom_components/studio_assistant/const.py) | The component's defaults: the Ollama address, the model tag, the context window, the output cap, and the thinking switch |
| [`benchmark/config.yaml`](https://github.com/seanlin2000/home_assistant/blob/main/benchmark/config.yaml) | Every candidate's model tag and thinking setting, and the Ollama address the benchmark uses |
| [`docs/VERSIONS.md`](https://github.com/seanlin2000/home_assistant/blob/main/docs/VERSIONS.md) | The Ollama version and the model tags and build ids on the running machine, with the rule for re-pulling a tag |

## Further reading

- Design doc: [`design_docs/v1/02_local_llm.md`](https://github.com/seanlin2000/home_assistant/blob/main/design_docs/v1/02_local_llm.md), which also lists the failure modes and the thinking switch for each model family
- [Apple, exploring LLMs with MLX on the M5](https://machinelearning.apple.com/research/exploring-llms-mlx-m5), for measurements of how the neural accelerators cut time to first token, the number that matters most after a search
- [Apple, Mac mini (M6 or M5 Pro) tech specs](https://support.apple.com/en-us/128108), for the M6's 12-core GPU and 170 GB/s with 24 or 32 GB, and the M5 Pro's 16- or 20-core GPU and 307 GB/s
- [Apple, MacBook Pro (14-inch, 2021) tech specs](https://support.apple.com/en-us/111902), for the prototype's M1 Pro with its 14-core GPU and 200 GB/s
- [unsloth/gemma-4-26B-A4B-it-GGUF](https://huggingface.co/unsloth/gemma-4-26B-A4B-it-GGUF), for the file size of each quantization of the model the benchmark points at
- [Gemma 4 thinking mode](https://gemma4.dev/docs/concepts/thinking-mode), for what the hidden reasoning costs in latency and why it is off here
- [Best local LLMs on Apple Silicon](https://apxml.com/posts/best-local-llms-apple-silicon-mac), for the background on Ollama's MLX backend on Macs
