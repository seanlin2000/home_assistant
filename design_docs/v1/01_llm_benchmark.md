# 01. LLM benchmark

## 1. Purpose

Choose the language model, and therefore the hardware, from evidence instead of leaderboards. The benchmark runs twenty questions shaped like the ones you actually ask an assistant through the exact agent loop the product will use, against every candidate model that fits the 16 GB MacBook, plus a frontier model as the quality ceiling. It scores not only whether an answer is good but whether the model made the right call about searching the web.

## 2. Diagram

```
 benchmark/questions.yaml                 assistant_core (the same loop the product ships)
 ┌──────────────────────┐                 ┌────────────────────────────────────────────────────┐
 │ 20 questions          │   for each     │  system prompt (identical for every model)          │
 │  id, category,        │───question────▶│  ┌─────────┐  tool call?  ┌────────────────────┐   │
 │  expected_search,     │   × each       │  │  model  │─────────────▶│ web_search_mcp     │   │
 │  constraints,         │   candidate    │  │ (Ollama │◀─────────────│  → SearXNG (local) │   │
 │  reference sketch     │                │  │  or API)│  excerpts    └────────────────────┘   │
 └──────────────────────┘                 │  └────┬────┘                                        │
                                          │       │ final answer + full transcript              │
                                          └───────┼────────────────────────────────────────────┘
                                                  ▼
                                    results/<date>/<model>.jsonl
                                    (question, turns, tool calls, retrieved excerpts, answer,
                                     time to first token, total latency, tokens, word count)
                                                  │
                        ┌─────────────────────────┼──────────────────────────────┐
                        ▼                         ▼                              ▼
              harness gate checks        frontier judge (temp 0)         your review sheet
              searched when it should    reads transcript + rubric       fixed 20% sample plus
              not, did not search when   → JSON: gates, 3 scores,        every judge/harness
              it should, word limits,    justifications                  disagreement
              tool loops                          │                              │
                        └─────────────────────────┼──────────────────────────────┘
                                                  ▼
                                    report.md: per model total /200, per category /100,
                                    gate failures by type, latency table, judge agreement rate
                                                  │
                                                  ▼
                                    decision: model tier → Mac tier
```

## 3. How it works, step by step

1. `run.py` loads the questions and, for each candidate model, runs every question through `assistant_core.agent_loop` with the shared system prompt and the two search tools. The two-turn question is run as a real two-turn conversation. Each run writes one JSONL line per question with the full transcript and timing.
2. The harness applies the gates it can detect mechanically: whether a tool was called, how many times, whether the final answer exists, and word counts against explicit limits.
3. `judge.py` sends each transcript to a frontier model at temperature 0 together with the rubric, the question's metadata, and (for reasoning questions) a short reference sketch. The judge returns strict JSON: which gates it believes were hit, three dimension scores, and a one-sentence justification per score.
4. `report.py` merges harness gates and judge output. Any gate failure zeroes that question. It renders a markdown report and a review sheet containing a fixed random 20% of answers plus every case where the judge and the harness disagree on a gate.
5. You score the review sheet by hand. The report prints your agreement rate with the judge. Below 90% on gates, we tighten the rubric wording and re-judge, which costs cents and needs no re-run.
6. The decision gate reads the report: which local models reach your bar, expressed as a fraction of the frontier baseline's score and by gate-failure count.

## 4. Question set, version 1

Stored verbatim in `benchmark/questions.yaml`. Category A should be answered without searching. Category B should trigger a search. Metadata per question: `expected_search` (no / yes / instructed, where "instructed" means the question itself says to search), explicit constraints to check, and a reference sketch for Category A.

### Category A: answer from reasoning or knowledge, do not search

| Id | Tests | Question |
|---|---|---|
| A1 | Technical explanation without misleading simplification | Why can a 16 GB GPU sometimes run an MoE model with 30 billion total parameters, but not necessarily a 30 billion parameter dense model? Explain the difference between active parameters and the memory required to store the model. |
| A2 | Multi-step arithmetic, compounding versus flat increase | I pay $3,500 per month in rent. My landlord offers me a one-year lease at a 5% increase or a two-year lease at a 3% increase each year. Ignoring the time value of money, how much would I pay over each option, and how much would I save with the cheaper option? |
| A3 | Challenging a false premise | Someone says that because an MoE model only activates 4 billion parameters per token, a 4 GB GPU should be enough to run it. Is that correct? Explain exactly why or why not. |
| A4 | Diagnosis under uncertainty, asking for missing information | My plant is growing new leaves quickly near the top, but its older lower leaves are gradually yellowing and dying. The plant is otherwise healthy. What are the most likely explanations, and what information would you want before deciding whether this is normal or a problem? |
| A5 | Planning under constraints, no product names | I live in a 500-square-foot studio and want a voice assistant that can hear me from across the room. I care more about microphone quality and natural conversation than smart-home automation. Give me the main hardware design considerations without recommending specific products. |
| A6 | Two-turn context. Turn 1 then turn 2 | Turn 1: I'm deciding between a computer with 16 GB of VRAM and one with 24 GB. I primarily care about running a local LLM. Turn 2: Suppose the 24 GB machine costs $400 more. Does that change your recommendation? |
| A7 | Estimation with explicit assumptions | I have a computer that consumes 50 watts when idle and 300 watts during active inference. If I interact with it for roughly one hour per day, estimate the monthly electricity cost. State your assumptions instead of pretending you know exactly how much time it spends under load. |
| A8 | Systems thinking, comparing designs | For a personal AI assistant, compare these two designs: one large LLM handles every request, versus a smaller router that sends simple commands to deterministic tools and only uses a larger LLM for complex questions. Which would you recommend and why? |
| A9 | Recognizing ambiguity instead of inventing preferences | I say: "I want to go somewhere warm but not too expensive, preferably with good public transportation." What information is missing before you can make a good recommendation, and what assumptions should you avoid making? |
| A10 | Spoken concision, under 45 seconds (about 110 words) | Explain why VRAM capacity can matter more than raw GPU speed when choosing hardware for a local LLM. Answer in a way that would sound natural if spoken aloud in under 45 seconds. |

### Category B: the model should decide to search

| Id | Tests | Question |
|---|---|---|
| B11 | Freshness detection, source synthesis | What is the current federal funds rate, and how has it changed over the last year? |
| B12 | Current prices under a budget | I'm looking for a computer to run a local LLM with approximately $1,000 total budget. What hardware can I buy today that gives me the most usable VRAM for the money? |
| B13 | Combining current sources | I'm staying in Lucerne and want to take a scenic day trip tomorrow using public transportation. What are my best options, considering current schedules and weather? |
| B14 | Research synthesis, not snippet parroting | Why have NVIDIA GPU prices increased recently? I don't just want the current prices—I want to understand what changed in the supply chain or market. |
| B15 | Shopping research with a hard constraint | Find me the best current option for a 16 GB NVIDIA GPU under $500. Used hardware is acceptable. |
| B16 | Search plus skepticism about the comparison | I'm considering signing a two-year lease. Based on current rental conditions in Long Island City, does accepting a 4% annual increase seem competitive? Compare my offer against the current market, but also explain the risks of using advertised rents as the comparison. |
| B17 | Source selection (instructed search) | Search for the answer to this question: "Is the Home Assistant Voice Preview Edition capable of running a custom wake word?" Give me the answer and explain which source you trusted and why. |
| B18 | Technical research synthesis (instructed search) | Search for the latest information about the Qwen open-source model family. I want to know which currently available models are realistic to run locally on approximately 16 GB of GPU memory. Don't just list models—explain the tradeoffs between model quality, quantization, memory usage, and speed. |
| B19 | Critical reading of results (instructed search) | Search for whether an RTX 4060 Ti 16 GB can run Qwen3.8. Then tell me whether the answer you found is actually enough to predict whether it will provide a good voice-assistant experience. |
| B20 | Research with conflicting constraints, willingness to say no | I want to build a local voice assistant for under $1,000 all-in. It should answer general questions at roughly ChatGPT-like quality, perform web searches when necessary, and work entirely locally except for those searches. Find the best hardware approach available today. If my requirements cannot realistically be met within the budget, tell me explicitly instead of quietly increasing the budget. |

### Notes for version 1.1

Not changes to v1. B17 to B19 say "search for", so they test instruction following more than the search decision. The set also has no pure adversarial items. Two candidates to add after the first run: a question that sounds current but is not ("What year did the Berlin Wall fall?", should not search), and one with a false current premise ("Since the Fed cut rates to zero last month, should I refinance?", should search and correct the premise).

## 5. Rubric, version 1

### Why this shape

The first draft had seven dimensions with different maxima, one of which applied only to searched questions. That makes per-question totals uneven and category averages hard to compare, and two of the dimensions (correctness and reasoning) overlap enough that a judge scores them together anyway. Fewer, sharper dimensions with the same maximum on every question score more consistently, especially with a language model as the judge.

### Step 1: gates

Any gate failure sets the question's score to 0 and is listed by name in the report. Gates are the behaviors that would make you stop trusting the assistant.

| Gate | Detected by |
|---|---|
| Fabricated a current fact instead of searching | Judge, given a transcript with no tool call |
| Searched on a Category A question | Harness: tool call present |
| Did not search on a Category B question | Harness: no tool call |
| Violated an explicit constraint (budget, no product names, word limit) | Harness for word limits, judge for the rest |
| Presented an estimate or assumption as a measured fact | Judge |
| Lost prior-turn context on A6, or asked the user to repeat it | Judge |
| Agreed with the false premise in A3 | Judge |
| Malformed tool calls, more than 4 tool calls, or no final answer | Harness |

### Step 2: score, 0 to 10 per question

| Dimension | Points | What it measures |
|---|---|---|
| Answer quality | 0 to 5 | Correct, complete for what was asked, sound reasoning. For searched questions: claims traceable to the retrieved excerpts, synthesis rather than snippet parroting, sensible choice of sources. |
| Judgment | 0 to 3 | Right decision on whether to search. States assumptions and asks for genuinely missing information. Pushes back on shaky premises. Says "no" when constraints cannot be met. |
| Spoken fit | 0 to 2 | Would sound right read aloud: leads with the answer, one to three sentences unless the question demands more, no lists, markdown, or URLs read aloud. |

Maximum 10 per question, 200 per model, 100 per category.

### Logged but not scored

Time to first token, total latency, tokens generated, number of tool calls, answer word count. These decide hardware, not model quality. The prototype machine has no neural accelerators, so searched answers will be slow there; latency is recorded for projection to the production Mac, not judged.

## 6. Fairness rules

Identical for every candidate:

- System prompt: the voice persona, the brevity instruction, the tool descriptions. One file, `assistant_core/prompts.py`.
- Tools: `web_search` and `fetch_page`, backed by the same local SearXNG instance.
- Temperature: one fixed value, recorded in the results. Vendors recommend different values (Gemma 4 says 1.0, Qwen lower), so a single value is a deliberate compromise in favor of comparability.
- Maximum tool calls per question (4) and maximum output tokens.
- Thinking mode off for every model that has a toggle. Gemma 4 thinks only if `<|think|>` appears in the system prompt; we leave it out. Qwen 3.8 open weights cannot turn thinking off and are excluded.
- Run window: all candidates on the same day so search results match as closely as possible. SearXNG responses are cached by query string for the duration of a run, so two models issuing the same query see the same page.
- One pass per model in v1. A second pass only if a result looks like noise.

## 7. Candidates on the 16 GB MacBook

Ollama's default GPU memory ceiling on a 16 GB Mac is about 12 GB and can be raised to about 14 GB with the `iogpu.wired_limit_mb` kernel setting. Everything else is closed during runs, models are loaded one at a time and unloaded between candidates.

| Candidate | Size on disk | Fit | Role |
|---|---|---|---|
| Gemma 4 E4B, Q4 | ~4.5 GB | comfortable | small, fast reference |
| Qwen 3.5-4B, Q4 | 3.4 GB | comfortable | small, fast reference |
| Qwen 3.5-9B, Q4 | 6.6 GB | comfortable | best mid-size that fits at full precision |
| gpt-oss-20b, MXFP4 | ~13 GB | tight | 2025 MoE reference, known to run on 16 GB Macs |
| Gemma 4 26B-A4B, UD-IQ3_XXS | 11.4 GB | fits | reduced-precision preview of a production candidate |
| Gemma 4 26B-A4B, UD-IQ4_XS | 13.6 GB | tight, after raising the ceiling | closer to production precision |
| Qwen 3.6-35B-A3B, UD-IQ3_XXS | 13.2 GB | tight | reduced-precision preview of the other production candidate |
| Frontier model via API | n/a | n/a | quality ceiling on the same harness |

Not testable on this machine: Qwen 3.5/3.6-27B dense (17 GB), Qwen 3.6-35B-A3B at Q4 (~20 GB), Gemma 4 31B dense, gpt-oss-120b.

How to read a 3-bit preview: if it scores near the frontier baseline, that is strong evidence its 4-bit production version will too. If it scores poorly, that is only weak evidence against the production version, because 3-bit quantization measurably hurts reasoning. The report labels previews and states this caveat next to their scores.

## 8. Packages and what they do for us

| Package | Role in the business logic |
|---|---|
| `ollama` (Python client) | Talks to the local Ollama server: sends the conversation and tool schemas, streams tokens back, reports timing. Every local candidate goes through it, so timing is measured the same way. |
| `anthropic` | Two jobs: runs the frontier baseline through the same loop, and acts as the judge. Usage follows the `claude-api` reference loaded at implementation time. |
| `mcp` (client side) | Connects the agent loop to `web_search_mcp` over streamable HTTP and converts the server's tool schemas into the format each model provider expects. |
| `pydantic` | Typed records for questions, transcripts, gate results, and judge output. The judge is forced to return JSON that validates against the score model, which turns a free-text opinion into data. |
| `pyyaml` | Reads `questions.yaml`. |
| `httpx` | HTTP client under the MCP client and the SearXNG cache. |
| `rich` | Progress display while a run walks 20 questions times 8 models. |
| `pytest` | Tests: gate detection on synthetic transcripts, the loop against a mocked model and mocked search, report rendering. |

## 9. Configuration we control

- `benchmark/questions.yaml`: the set, its metadata, reference sketches.
- `benchmark/rubric.md`: the exact text the judge receives.
- `benchmark/config.yaml`: candidate list with Ollama tags, temperature, token limits, tool-call cap, judge model, sample fraction for review.
- `assistant_core/prompts.py`: the shared system prompt.
- `docker/searxng/settings.yml`: which engines feed search results.

## 10. Failure modes

- **Judge and human disagree.** Caught by the 20% review and the agreement rate. Fix the rubric text, re-judge.
- **Model produces malformed tool calls.** Counted as a gate failure, logged with the raw output so the tool-schema conversion can be checked; smaller models are the usual offenders.
- **Search results change between candidates.** Same-day runs and per-query caching. Results directories are dated and committed so later runs can be compared to earlier ones with that caveat in mind.
- **Memory pressure on the 16 GB machine.** A candidate that swaps produces misleading latency. The harness records memory pressure at start and flags runs where the model did not fully load on the GPU.
- **A candidate that cannot follow the system prompt's brevity rule.** Shows up as low spoken-fit scores, which is the point: for a voice product that is a real deficiency, not a scoring artifact.

## 11. Concepts for newcomers

**LLM-as-judge.** Using a strong model to grade another model's answer against a rubric. It is consistent and cheap but has biases (it tends to reward verbosity and its own style). The mitigations here are a fixed low temperature, forced JSON output, a written rubric, reference sketches, and a human review of a sample with the agreement rate printed in the report.

**Gates versus scores.** A score says how good an answer is. A gate says whether the answer is acceptable at all. Zeroing a question on a gate failure prevents a fluent, well-structured hallucination from scoring 7 out of 10.

**Why the search decision is scored separately.** A voice assistant that searches for everything is slow and one that never searches is confidently wrong about current facts. The model's judgment about when to search is a product feature in its own right.

**Reference sketch.** Two or three sentences describing what a correct answer must contain, for example the two lease totals in A2. The judge checks the answer against it rather than working the problem itself.

**Temperature.** A sampling setting. Zero makes the model pick its most likely token every time, which makes the judge nearly deterministic. Candidates run at a moderate fixed value because that is how the product will run.

**Quantization labels (Q4_K_M, IQ3_XXS, MXFP4).** Names of weight-compression schemes and their bit widths. Lower numbers mean smaller files and lower quality. "UD" prefixes denote Unsloth's dynamic quantizations, which keep sensitive layers at higher precision.

## 12. Sources

- Gemma 4 GGUF sizes and recommended settings: [unsloth/gemma-4-26B-A4B-it-GGUF](https://huggingface.co/unsloth/gemma-4-26B-A4B-it-GGUF)
- Qwen 3.6-35B-A3B GGUF sizes: [unsloth/Qwen3.6-35B-A3B-GGUF](https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF/tree/main)
- Qwen 3.5 Ollama tags and sizes: [ollama.com/library/qwen3.5](https://ollama.com/library/qwen3.5)
- Qwen 3.8 open weights require thinking on: [Latent Space](https://www.latent.space/p/ainews-qwen-38-max24t-and-27b-new)
- gpt-oss-20b memory on 16 GB Macs: [willitrunai.com](https://willitrunai.com/blog/gpt-oss-20b-vram-requirements)
- Gemma 4 thinking toggle: [gemma4.dev thinking mode](https://gemma4.dev/docs/concepts/thinking-mode)

## 13. As built, 2026-09-05

- Question set v1.1: 22 questions (A1 to A11, B11 to B21). Maximum 220 per model, 110 per category. See `benchmark/questions.yaml`; every question carries `expected_search`, optional `constraints` (`max_words`, `budget_usd`, `no_product_names`), the gates the judge should watch for, and a reference sketch for reasoning questions.
- Commands: `uv run benchmark-run [--candidate KEY]... [--question ID]... [--date D] [--force] [--delete-models]`, `uv run benchmark-judge D`, `uv run benchmark-report D`, `uv run python scripts/benchmark_llm.py`. Runs resume: questions already in `results/D/<key>.jsonl` are skipped unless `--force`.
- Harness gates (`benchmark/gates.py`): searched on a no-search question, did not search on a search question, malformed tool call, more than the tool-round cap, no final answer, word limit exceeded, and `run_error` when the model call itself failed.
- Judge (`benchmark/judge.py`): `messages.parse` with the `JudgeVerdict` pydantic model as the required output shape; `benchmark/rubric.md` is the system prompt verbatim. Each score records the judge's model id and token usage. Sampling temperature cannot be set on Claude Opus 5, so determinism comes from the structured schema and the fixed rubric rather than temperature 0.
- Report (`benchmark/report.py`): scores table with the fraction of the baseline, gate counts by type, latency and word counts (logged, not scored), per-question matrix, judge agreement once `review_sheet.yaml` is filled in, and the paid API spend for the run.
- Review sheet: a seeded 20% sample per candidate plus every case where the judge's view of the search decision disagrees with the harness. Human fields are preserved across re-renders.
- The harness starts `web_search_mcp` as a subprocess with `WEB_SEARCH_CACHE_DIR=results/D/cache`, so every candidate in a run sees identical search results.
- Memory fit is read from Ollama's `/api/ps` after a warm-up call that uses the run's context length, so the first question does not pay a model reload.
