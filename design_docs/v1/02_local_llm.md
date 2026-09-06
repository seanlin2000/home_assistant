# 02. Local LLM

## 1. Purpose

Run the language model on the Mac, with no cloud involved, fast enough for conversation. This doc explains how a model occupies memory and compute on Apple Silicon, why mixture-of-experts models are the right shape for this project, what quantization trades away, and how Ollama exposes all of it as one HTTP API that the conversation agent and the benchmark share.

## 2. Diagram

```
                       Apple Silicon Mac: one pool of unified memory shared by CPU and GPU
 ┌─────────────────────────────────────────────────────────────────────────────────────────────┐
 │  macOS ~3 GB │ HA VM 3-4 GB │ Whisper 1.6 GB │ TTS <1 GB │      Ollama                       │
 │              │              │                │           │  ┌──────────────────────────────┐ │
 │              │              │                │           │  │ model weights (quantized)    │ │
 │              │              │                │           │  │  e.g. Gemma 4 26B-A4B Q4     │ │
 │              │              │                │           │  │  ~16 GB, all experts resident│ │
 │              │              │                │           │  ├──────────────────────────────┤ │
 │              │              │                │           │  │ KV cache (grows with context)│ │
 │              │              │                │           │  │  1-2 GB at 16k tokens        │ │
 │              │              │                │           │  └──────────────────────────────┘ │
 └─────────────────────────────────────────────────────────────────────────────────────────────┘

  One request through Ollama:

  agent ──POST /api/chat──▶ Ollama ──▶ 1. prompt processing (compute-bound)
         messages, tools,             │    reads every prompt token; cost grows with prompt length
         temperature, think=false     │    this is "time to first token"
                                      ▼
                                   2. generation (memory-bandwidth-bound)
                                      │  one forward pass per token; only ACTIVE experts computed
                                      │  this is "tokens per second"
                                      ▼
  agent ◀──stream of JSON chunks────  tokens, or a structured tool_call, plus timing stats
```

## 3. How it works, step by step

1. Ollama runs as a native macOS service (installed with Homebrew) and listens on `localhost:11434`. On Apple Silicon since version 0.19 it uses Apple's MLX framework, which runs the model on the GPU through Metal.
2. `ollama pull <tag>` downloads a model in a quantized format. The first request loads the weights into unified memory, where they stay resident until an idle timeout.
3. The agent sends a `POST /api/chat` with the message history, the tool schemas, and options such as temperature. With `stream: true` Ollama returns a chunk per token.
4. Ollama first processes the prompt. Every token in the system prompt, history, and any retrieved search excerpts is read in one pass. This step is compute-bound and its duration is the time to first token.
5. Then it generates. Each new token needs the weights of the active layers streamed from memory through the GPU, so the speed is set by memory bandwidth divided by the bytes touched per token. For a mixture-of-experts model that is only the active experts.
6. If the model decides to call a tool, Ollama parses the model's structured output and returns a `tool_calls` field instead of text. The agent runs the tool, appends the result as a `tool` message, and sends the whole conversation again.
7. The final chunk carries statistics: prompt tokens, generated tokens, prompt processing time, generation time. The benchmark records these.

## 4. Why mixture of experts fits this project

| Model type | Memory to hold | Compute per token | Example |
|---|---|---|---|
| Dense 27B | ~17 GB at 4-bit | all 27B parameters | Qwen 3.6-27B: ~10 tok/s on a 170 GB/s Mac |
| MoE 26B, 4B active | ~16 GB at 4-bit | ~4B parameters | Gemma 4 26B-A4B: 20 to 40 tok/s on the same Mac |
| Dense 9B | ~6.6 GB at 4-bit | 9B | Qwen 3.5-9B: fast, less capable |

A Mac has a lot of memory and modest compute. A mixture-of-experts model spends the memory to hold many experts and the compute on only a few per token, so it runs at small-model speed with large-model quality. That is the sweet spot for a voice assistant, where both time to first token and generation speed are felt directly.

## 5. Memory arithmetic

Weights: parameters × bits per parameter ÷ 8. A 26B model at roughly 4.5 bits per parameter (4-bit weights plus overhead) is about 15 to 17 GB. At 3 bits it is 11 to 13 GB.

KV cache: memory the model keeps for every token in the current context so it does not recompute attention. It grows linearly with context length. For the candidate models, a 16k-token context costs roughly 1 to 2 GB.

Ollama's ceiling on a 16 GB Mac is about 12 GB of GPU memory by default, raisable to about 14 GB with the `iogpu.wired_limit_mb` kernel setting, which is why the 13 GB previews in the benchmark are labeled tight.

Production budget for the 32 GB tier: macOS 3 GB, Home Assistant VM 3 to 4 GB, model 16 GB, KV cache 1 to 2 GB, Whisper 1.6 GB, text to speech under 1 GB, total 25 to 27 GB.

## 6. Speed arithmetic

Generation speed ≈ memory bandwidth ÷ bytes read per token. A Mac mini M6 with 24 or 32 GB has 170 GB/s. Gemma 4 26B-A4B touches roughly 4 to 5 GB per token at 4-bit, which predicts 30 to 40 tok/s in theory and 20 to 30 tok/s in practice. Speech plays at 3 to 4 tok/s, so anything above about 5 tok/s stays ahead of the voice once streaming starts.

Time to first token ≈ prompt tokens ÷ prompt processing rate. Prompt processing is compute-bound. The M5 and M6 chips added neural accelerators to every GPU core, which Apple measured at 3.3 to 4x faster time to first token than the M4 across models from 1.7B to gpt-oss-20b. This is the single most important hardware fact for this project: after a web search, the prompt carries 3,000 to 6,000 tokens of page text, and this step decides whether the answer starts in 2 seconds or 8. The M1 Pro prototype machine lacks these accelerators, so its searched-answer latency is recorded for projection, not judged.

## 7. Thinking modes

Several 2026 models can "think" before answering: they generate a hidden chain of reasoning first. It improves hard reasoning and multiplies latency by 2 to 5x. For voice we turn it off.

| Model | How to disable |
|---|---|
| Gemma 4 | Omit the `<|think|>` token from the system prompt. Default is off. |
| Qwen 3.5 / 3.6 | `think: false` in the Ollama request. |
| gpt-oss | Reasoning effort set to low via the system prompt. |
| Qwen 3.8 open weights | Cannot be disabled. Excluded. |

## 8. Packages and what they do for us

| Package or tool | Role in the business logic |
|---|---|
| Ollama (Homebrew, native) | Hosts the model, manages memory, exposes one HTTP API for every candidate. Chosen over LM Studio and raw llama.cpp because Home Assistant, the benchmark, and our agent all speak its API and it handles tool-call parsing per model family. |
| MLX (inside Ollama) | Apple's array framework. The reason generation runs on the GPU rather than the CPU. |
| `ollama` (Python client) | Thin typed wrapper over the HTTP API used by `assistant_core.llm_client.OllamaClient`. Streams chunks, returns timing statistics. |
| `httpx` | Used directly for health checks and the `/api/ps` endpoint that reports whether a model is fully loaded on the GPU. |

## 9. Configuration we control

- Which model tag is loaded: decided by the benchmark, set in `assistant_core` config.
- `OLLAMA_KEEP_ALIVE`: how long the model stays resident after a request. Set to `-1` (forever) on the production Mac so the first question of the day is not slow.
- `OLLAMA_NUM_PARALLEL`: 1. One user, one conversation at a time.
- Context length (`num_ctx`): 16k in production, enough for a system prompt, a few turns, and two fetched pages.
- Temperature and `think` per request, fixed in `assistant_core.prompts`.
- `iogpu.wired_limit_mb` on the prototype machine only.

## 10. Failure modes

- **Model does not fit and spills to CPU or swap.** Generation drops to a crawl. Detect with `/api/ps` (the `size_vram` field) at startup; the harness flags it.
- **Prompt too long for `num_ctx`.** Ollama silently truncates the oldest messages. The agent caps fetched-page excerpts and trims history so the system prompt is never lost.
- **Model ignores the tool schema and writes a tool call as plain text.** Common in small models. The agent treats it as a gate failure in the benchmark and as "no tool call" in production.
- **Ollama update changes a model's default template.** Pin the Ollama version with Homebrew and re-run the benchmark before upgrading.
- **Thermal throttling in a small enclosure.** The Mac mini is fine; a laptop under sustained load may slow. Another reason the production box is a desktop.

## 11. Concepts for newcomers

**Parameters.** The learned numbers inside the model. "26B" means 26 billion of them. More parameters, more capability, more memory.

**Active parameters.** In a mixture-of-experts model, the subset actually used for a given token. Memory is set by total parameters; speed is set by active parameters.

**Context window.** The maximum number of tokens the model can see at once: system prompt, conversation so far, tool results. Exceed it and the oldest content is dropped.

**KV cache.** The model's working memory for the current context. Costs memory proportional to context length, saves recomputation.

**Quantization.** Compressing weights from 16-bit floating point to 4 or 3 bits. 4-bit is the standard tradeoff for local use: about a quarter the memory, a few percent quality loss. 3-bit is a further quarter off with a noticeable loss on reasoning. The benchmark uses 3-bit only where 4-bit does not fit the prototype machine.

**Memory-bandwidth-bound.** Generation is limited by how fast weights can be read from memory, not by arithmetic. This is why an Apple chip with fast unified memory competes with a discrete GPU for token generation, and why a chip's bandwidth number matters more than its core count for this step.

**Compute-bound.** Prompt processing is limited by arithmetic throughput. This is where a discrete GPU or the new neural accelerators pull ahead, and why the M5/M6 generation is a real step for this use case.

**Metal and MLX.** Metal is Apple's GPU programming interface. MLX is Apple's machine learning framework on top of it. Ollama uses MLX on Macs so the model runs on the GPU.

## 12. Sources

- Ollama switched its Apple Silicon backend to MLX in v0.19: [apxml.com](https://apxml.com/posts/best-local-llms-apple-silicon-mac)
- Apple M5 neural accelerator results: [machinelearning.apple.com](https://machinelearning.apple.com/research/exploring-llms-mlx-m5), [9to5Mac summary](https://9to5mac.com/2025/11/20/apple-shows-how-much-faster-the-m5-runs-local-llms-compared-to-the-m4/)
- Mac mini M6 memory bandwidth 170 GB/s at 24/32 GB: [MindStudio](https://www.mindstudio.ai/blog/apple-mac-studio-mini-pricing-specs)
- Gemma 4 26B-A4B speed on Apple Silicon: [SudoAll](https://sudoall.com/gemma-4-31b-apple-silicon-local-guide/), [gemmai4.com](https://gemmai4.com/mac/)
- Gemma 4 quantization sizes: [unsloth/gemma-4-26B-A4B-it-GGUF](https://huggingface.co/unsloth/gemma-4-26B-A4B-it-GGUF)
- Thinking mode latency cost: [gemma4.dev](https://gemma4.dev/docs/concepts/thinking-mode)
