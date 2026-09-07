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

Stored verbatim in `benchmark/questions.yaml`. Category A should be answered without searching. Category B should trigger a search. Category C, added in question set 1.2, should go through the calculator tools. Metadata per question: `expected_search` (no / yes / instructed, where "instructed" means the question itself says to search), explicit constraints to check, and a reference sketch for Category A.

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

### Category C: arithmetic through the calculator tools (added in question set 1.2)

The router should mark every one of these `calculate`, the model should call the calculator tools rather than do the digits itself, and no search is expected. Each carries a reference sketch with the exact figures and the tolerances the judge accepts.

| Id | Tests | Question | Reference figures |
|---|---|---|---|
| C23 | Percent of an amount, then a total | We just got a $64.50 dinner bill. What's an 18 percent tip, and what's the total with the tip? | Tip 11.61, total 76.11; rounding to 11.60 or 76 is fine if said as rounding. |
| C24 | Compound growth with regular contributions | If I put $500 a month into a savings account that pays 4 percent a year, compounded monthly, how much will I have after three years? | About 19,091 (end-of-month deposits) or 19,154 (start of month); 18,000 of it is deposits, so interest is about 1,091. A flat 4 percent on 18,000, or compounding the whole 18,000 for three years (about 20,300), is wrong. |
| C25 | Two unit conversions in one question | It's 72 degrees Fahrenheit outside. What is that in Celsius, and how far is a 5 kilometer run in miles? | 22.2 C (22 is fine); 3.11 miles (3.1 is fine). |
| C26 | What percent one number is of another, then a percent increase | My rent is $2,850 a month and my take-home pay is $7,400 a month. What percent of my income goes to rent, and what would the rent be after a 4 percent increase? | 38.5 percent (38 or 39 if said as about); 2,964 after the increase. |
| C27 | Energy cost from watts, hours, and a stated price | My TV draws 120 watts. If I watch about 4 hours a day and electricity costs 30 cents per kilowatt hour, what does it cost me per month? | 0.48 kWh a day, about 14.4 kWh a month, about 4.32 dollars for 30 days (4.38 to 4.46 for 30.4 to 31 days is fine). The rate is given, so no assumption is needed. |
| C28 | Loan amortization | What's the monthly payment on a $400,000 mortgage at 6 percent for 30 years, and roughly how much interest do I pay in total? | Payment 2,398.20 (about 2,400 is fine); total paid about 863,353, so interest about 463,353. Noting that taxes and insurance are excluded is a plus. |

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
| Qwen 3.6-27B dense, Q3_K_S (added 2026-09-06) | 12.4 GB | spills to CPU under the default 12 GB ceiling; latency flagged, quality still scored | reduced-precision preview of the dense production candidate |
| Frontier model via API | n/a | n/a | quality ceiling on the same harness |
| Hand-written answers by Claude Fable 5.1 (`benchmark-manual`) | n/a | n/a | reference ceiling for the question set itself, not a purchasable candidate. Since pass 5 it is authored closed book by a fresh subagent that runs the real search and calculator tools and sees nothing but the questions and the system prompt (`claude-fable-5-1-manual-2`); the first pass, written inside the coding session, is kept as `claude-fable-5-1-manual` |

Not testable on this machine at production precision: Qwen 3.5/3.6-27B dense at Q4 (17 GB), Qwen 3.6-35B-A3B at Q4 (~20 GB), Gemma 4 31B dense, gpt-oss-120b. The user chose to add only the Qwen 3.6-27B 3-bit preview from the larger-model candidates researched on 2026-09-05, judging Gemma 4 31B unlikely to differ enough from the 26B MoE to change the decision and declining NVIDIA Nemotron.

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
- Commands: `uv run benchmark-run [--candidate KEY]... [--question ID]... [--date D] [--force] [--delete-models]`, `uv run benchmark-judge D`, `uv run benchmark-report D`, `uv run benchmark-manual KEY [--date D]` (replays hand-written answers from `benchmark/manual/KEY.yaml` through the same loop and tool server), `uv run python scripts/benchmark_llm.py`. Runs resume: questions already in `results/D/<key>.jsonl` are skipped unless `--force`.
- Harness gates (`benchmark/gates.py`): searched on a no-search question, did not search on a search question, malformed tool call, more than the tool-round cap, no final answer, word limit exceeded, and `run_error` when the model call itself failed.
- Judge (`benchmark/judge.py`): `messages.parse` with the `JudgeVerdict` pydantic model as the required output shape; `benchmark/rubric.md` is the system prompt verbatim. Each score records the judge's model id and token usage. Sampling temperature cannot be set on Claude Opus 5, so determinism comes from the structured schema and the fixed rubric rather than temperature 0.
- Report (`benchmark/report.py`): scores table with the fraction of the baseline, gate counts by type, latency and word counts (logged, not scored), per-question matrix, judge agreement once `review_sheet.yaml` is filled in, and the paid API spend for the run.
- Review sheet: a seeded 20% sample per candidate plus every case where the judge's view of the search decision disagrees with the harness. Human fields are preserved across re-renders.
- The harness starts `web_search_mcp` as a subprocess with `WEB_SEARCH_CACHE_DIR=results/D/cache`, so every candidate in a run sees identical search results.
- Memory fit is read from Ollama's `/api/ps` after a warm-up call that uses the run's context length, so the first question does not pay a model reload.

### Prompt version 1.2 and the calculator tools, 2026-09-06

All 2026-09-05 results were produced with prompt version 1.1 and only the three search tools. On 2026-09-06 the MCP server gained eight calculator tools (doc 03, section 11) and the system prompt gained a rule that multi-step arithmetic must go through them. The fairness rule still holds within a run date: every candidate on a given date sees the same prompt and the same tool list, and `run_meta.json` records the prompt version. Calculator calls do not count as searches for the gates. The first use is a rerun of A2 and A7 for the candidates that fit the laptop, to measure the change on the questions it targets before rerunning the whole set.

### Question set 1.2 and the second pass, 2026-09-06

Pass 2 changes three things at once, deliberately, because they ship together: the calculator tools, the question router (doc 04, section 12), and six explicit arithmetic questions in a new category C (C23 to C28: a tip, monthly savings with compounding, two unit conversions, rent as a share of income, a television's energy cost, and a mortgage payment). Every question now carries an expected route (search, calculate, or answer), derived from `expected_search` unless declared, so the report can score the router on its own: how many questions the rule layer decided and got right, how many the model layer decided and got right, the median router time, and the misroutes by question.

Pass 2 runs the full set on every candidate, including the frontier baseline and the hand-written reference, into `results/2026-09-06/`. Pass 1 stays untouched in `results/2026-09-05/`; the new report includes a comparison table restricted to the questions both passes share, so the new category does not inflate the second pass. Command: `benchmark-report 2026-09-06 --compare 2026-09-05`.

### Qwen 3.6-27B dense: not runnable here, 2026-09-07

The Q3_K_S preview (12.4 GB on disk, 13.7 GB loaded with context) kept only 8.3 GB on the GPU. The rest lived in swap, and the first answer took 53 minutes at 0.09 tokens per second. The run was stopped and the candidate removed from both passes; it remains in `config.yaml` for a 32 GB machine. This is the clearest evidence so far that dense models above about 12 GB are out of reach on 16 GB, whatever their quality.

### Judging through a Claude Code subagent, 2026-09-06

```
  benchmark-judge <date> --export        results/<date>/judge_cases/rubric.md
                                         results/<date>/judge_cases/<candidate>/<qid>.md      (question, transcript, harness notes)
                                         results/<date>/judge_cases/<candidate>/manifest.json
          │
          ▼  Agent tool, subagent "benchmark-judge" (Opus, tools Read/Write/Glob), one run per candidate folder
                                         results/<date>/judge_cases/<candidate>/<qid>.verdict.json
          │
          ▼
  benchmark-judge <date> --import        validates each verdict (gate names, score ranges) and writes <candidate>.scores.jsonl
                                         with judge_model "claude-opus-5 (Claude Code subagent)" and zero API tokens
```

The rubric the subagent reads is the same file the API judge received as its system prompt, and the case text is rendered by the same function. What differs: the API path enforced the verdict schema at decode time and ran at the API's default settings, while the subagent writes the JSON itself (malformed files are rejected on import and re-run) and grades with its own thinking budget. The comparison with pass 1 is therefore Opus against Opus, under close but not identical conditions.


### Passes 3 and 4: where the router's directive lives, 2026-09-06

Pass 2 showed Qwen 3.5 9B ignoring the calculator on every arithmetic question even though the router had appended the instruction to the user's message. Pass 3 (prompt 1.3) moved that directive into the system prompt for the turn and added a worked example, including a finished spoken answer. Pass 4 (prompt 1.4) kept the placement but trimmed each directive to the instruction and one example call, because in pass 3 the smaller models had started imitating the example's answer instead of making the call. Only the three small models ran under 1.3 and 1.4; the large models still wait for a prompt decision. Results folders were renamed from dates to `version_N` at the same time, and from pass 4 on the search backend is Startpage and Yahoo rather than Google, Bing, Brave, and DuckDuckGo (doc 03, section 13).

| Candidate | Pass 2 (1.2, user-message note) | Pass 3 (1.3, system prompt with worked example) | Pass 4 (1.4, system prompt with example call) |
|---|---|---|---|
| Qwen 3.5 9B | 156 (A 72, B 39, C 45), calculator on 1 of 6 | 183 (A 80, B 56, C 47), calculator on 4 of 6 | 125 (A 60, B 18, C 47), calculator on 1 of 6 |
| Qwen 3.5 4B | 151 (A 70, B 31, C 50) | 145 (A 62, B 36, C 47) | 162 (A 75, B 37, C 50) |
| Gemma 4 E4B | 174 (A 74, B 58, C 42), searched 11 of 11 | 138 (A 72, B 34, C 32), searched 6 of 11, 4 empty answers | 162 (A 65, B 45, C 52), searched 8 of 11, 1 empty answer |
| Hand-written reference | 226 | not judged (ran during the engine outage) | 241 |

What the three passes say:

- **Category B is noisy at one pass per model.** Qwen 3.5 9B's B score went 39, 56, 18 across three passes with the same questions, and in pass 4 six of its eleven B answers were gated for stating a current figure no excerpt supported. Search results differ from day to day, sampling runs at temperature 0.7, and the judge is a fresh Opus session each time. Swings of this size are larger than any effect a directive wording could plausibly have, so single passes cannot rank prompt variants on B. Categories A and C move far less and are where prompt effects can be read.
- **The worked example is what made Qwen 3.5 9B call the calculator.** With it (pass 3) the model called the tools on four arithmetic questions; without it (passes 2 and 4) on one, and it did the digits itself, which is where its C losses come from (C24, C26, C27 wrong in pass 4). The one question where it did call a tool, the mortgage, was fully correct in both passes.
- **Gemma 4 E4B reacts badly to the same block.** It searched every B question in pass 2 and skipped some in both system-prompt variants. Its empty answers have a cause in Ollama's server log: Gemma sometimes emits a tool call that Ollama's Gemma parser cannot read (for example an arithmetic expression left unquoted), the call and the reply are both dropped, and the harness records an empty answer. That is a Gemma-on-Ollama failure independent of the directive's wording.
- **The reference ceiling is stable** (226, 241) and its losses are all in category B, where even a hand-written answer over the same excerpts drew three fabrication gates. The judge holds a firm line on stating anything the excerpts do not contain.

Open decision before the large models run: keep prompt 1.4, or a 1.5 that restores the worked example for the calculate directive only (it helped the model that needed it and arithmetic questions are not where Gemma's problem was) while the search directive stays as the call alone.

### Pass 5: every runnable model under prompt 1.5, 2026-09-06

Prompt 1.5 is prompt 1.4 plus one line stating today's date (doc 04). All seven local candidates ran in one pass, small models first, then the four large ones with each deleted after its run, then the hand-written reference. Searches went through Startpage and Yahoo, later joined again by Brave and DuckDuckGo as their blocks expired. No search failures, no run errors.

| Candidate | Total /280 | A /110 | B /110 | C /60 | Gated | Median answer | On GPU |
|---|---|---|---|---|---|---|---|
| Gemma 4 26B-A4B, UD-IQ4_XS | 232 | 95 | 78 | 59 | 1 | 155 s | 7.5 of 15.2 GB |
| Hand-written reference, closed book (2026-09-07) | 226 | 100 | 66 | 60 | 5 | n/a | n/a |
| Hand-written reference, first pass (superseded) | 217 | 109 | 48 | 60 | 5 | n/a | n/a |
| Qwen 3.6 35B-A3B, UD-IQ3_XXS | 208 | 76 | 72 | 60 | 4 | 156 s | 8.5 of 14.1 GB |
| Gemma 4 26B-A4B, UD-IQ3_XXS | 199 | 84 | 56 | 59 | 5 | 84 s | 7.5 of 12.8 GB |
| Gemma 4 12B, Q4_K_M (added after the pass) | 186 | 81 | 53 | 52 | 4 | 24 s | all, 8.1 GB |
| Gemma 4 E4B (rerun with retry) | 176 | 74 | 50 | 52 | 5 | 5 s | all |
| Qwen 3.5 4B | 157 | 72 | 33 | 52 | 7 | 9 s | all |
| Qwen 3.5 9B | 154 | 80 | 28 | 46 | 7 | 11 s | all |
| gpt-oss 20B, MXFP4 | 145 | 63 | 25 | 57 | 9 | 51 s | 9.9 of 14.0 GB |

What the pass says:

- **The date line worked as intended.** Across the small models, pass 4 had thirteen search queries pinned to 2024 or 2025; pass 5 had none. It did not by itself raise category B scores, whose losses remain unsupported claims and skipped searches.
- **The large mixture-of-experts previews are a different class.** Gemma 4 26B-A4B at IQ4_XS scored 232, the top score of any local model in any pass, with a single gate; Qwen 3.6 35B-A3B at IQ3_XXS scored 208; the 3-bit Gemma preview 199. Every one of them called the calculator on all six arithmetic questions and searched every question that needed it. Their remaining losses are answers that overrun the spoken word cap and, for Qwen 3.6, literal markdown read aloud. Since these are reduced-quantization previews, the production 4-bit versions should score at least this well (doc 01, section 5's reading rule).
- **Gemma 4 12B sits between the classes.** Added to the candidate list after the pass at the user's request and run under the same prompt and search cache, the dense 12B (Google's June 2026 addition to the family) scored 186: above every small model, 13 points under the 3-bit 26B preview and 46 under the 4-bit one. It searched 10 of 11 search questions, called the calculator on every arithmetic question, and produced no empty answers. Its four gates were a misread tool result on the lease comparison, two unsupported current facts, and one budget overrun. At 8.1 GB fully resident it is the strongest model that fits a 24 GB machine with the rest of the stack, and 14 tokens per second on this laptop, since a dense model streams all of its weights per token where the 26B-A4B streams about four billion.
- **The small models plateau between 155 and 175.** Three passes of prompt variants moved them within noise of each other; Gemma 4 E4B's 176 is the rerun with the retry step, which removed the empty answers that had been costing it about twenty points a pass. Qwen 3.5 9B still calls the calculator on one arithmetic question in six and does the rest in its head, which costs it a third of category C.
- **gpt-oss 20B is not a candidate.** Lowest total, six fabrication gates, and 51 s median answers with the model split across GPU and CPU.
- **The reference was re-authored closed book and is now the 226 row.** The first hand-written reference (217) was composed against the excerpts of an earlier pass, so five of its figures counted as fabrications against pages it was never written from (B12, B14, B16, B18, B20). At the user's request it was redone on 2026-09-07 by a fresh Claude Fable 5.1 subagent that could read only the questions, the system prompt, and the YAML schema, and was barred from the results folders, the earlier answers, the design docs, and its memory files; it ran the live search and calculator tools itself and recorded the exact queries and calls, which `benchmark-manual` replayed against this pass's cache. It scored 226 with the same Opus judge: category B rose from 48 to 66 as three of the stale-excerpt gates cleared, category A fell from 109 to 100 because the lease comparison (A2) tripped the harness's four-call cap with five calculator calls, and two search answers (B11, B15) misread excerpts they had in hand. The two hardware-shopping questions (B12, B20) drew fabrication gates in both passes. Two hand-written passes from the same model landing at 217 and 226 put the reference in a band around 220 rather than at a point, and the 4-bit Gemma 26B preview's 232 sits inside that band. Both files stay in `results/version_5/` (`claude-fable-5-1-manual`, `claude-fable-5-1-manual-2`); the closed-book one is the reference from here on.
- **Gemma 4 E4B rerun with the retry-on-empty step (doc 04).** After the pass, `run_agent` gained a single retry when a completion carries neither text nor a tool call, and Gemma 4 E4B was rerun for this pass with `--force` against the same search cache. The retry fired on four questions and recovered two (B14, C26); the lease comparison (A2) and the electricity cost (A7) came back empty a second time, both arithmetic questions where the model writes a calculator call Ollama cannot parse and writes it the same way again. Gemma's row in the table below is the rerun: 176 with 5 gates, against 154 with 9 gates before it (the original file is in the git history of this commit's parent). No other candidate was rerun; gpt-oss 20B's one empty answer would likely have recovered too, so its 145 is a slight understatement.
- **Gemma 4 E4B's empty answers have a mechanism.** Replaying its four empty pass-5 questions against Ollama returned a valid tool call every time, at the same output length the run recorded, so in the run Gemma emitted a call that Ollama's Gemma parser dropped without surfacing it, presumably a small formatting slip of the kind that produced logged "invalid character" warnings in pass 4. About one answer in seven is lost this way for this model alone. A retry-on-empty step in the agent loop would recover most of them and also matters in production, where an empty answer is silence.
- **Latency is for projection only.** On the 16 GB laptop the large models spill to the CPU and answer in one to three minutes. Fully resident on a 32 GB machine, the same models generate ten to twenty times faster (doc 02); the M5 and M6 neural accelerators cut prompt reading, which dominates a searched answer, by a further factor of three to four.

Decision-gate reading: a 26B or 35B mixture-of-experts model at full 4-bit quantization is the model to deploy, which points at the 32 GB tier (doc 08). The model remains swappable; the harness and prompt are what the project keeps.
