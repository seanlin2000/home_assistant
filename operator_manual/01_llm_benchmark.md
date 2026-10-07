# Benchmarking and Model Selection
<!-- complexity: packages=3 parts=3 concepts=2 tier=deep -->

The benchmark is how the project decides which language model answers your questions. It asks each candidate model the same 38 questions through the same agent loop the assistant runs in production, records every tool call and every answer, checks the answers against a written rubric, and prints one score per model. The model at the top of that table is the one the assistant speaks with, and its memory footprint is what sized the Mac.

## Where this fits

```mermaid
flowchart TB
--8<-- "_includes/system_map.mmd"
class ollama,mcp,laptop current
```

A benchmark pass starts on the laptop and its results land there, as files under `benchmark/results/`. Each question goes from the laptop into Ollama as a chat with tool schemas attached, exactly as the conversation agent sends it during a real exchange. When the model asks for a tool, the call goes over MCP to a copy of `web_search_mcp` that the benchmark starts for itself on port 8766, next to the product's server on 8765, so a run can cache search results and the forecast without touching the live service; that copy still reaches SearXNG and the search engines, and Met.no for the forecast. Nothing on the puck, in Home Assistant, or in the speech stages is involved.

## Key definitions

| Term | Meaning |
|---|---|
| Candidate | One model configuration the benchmark scores: an Ollama model tag or a set of hand-written answers, named by a key in `benchmark/config.yaml`. |
| Gate | A pass-or-fail rule in the benchmark rubric whose failure zeroes the question, so a fluent fabrication cannot score well. |
| LLM-as-judge | Using a strong model to grade another model's answer against a written rubric. |
| Reference sketch | Two or three sentences in the benchmark saying what a correct answer must contain, so the judge checks against it instead of working the problem itself. |
| Preview build | A reduced-precision build of a model whose 4-bit production build does not fit the prototype machine, so a high preview score is strong evidence for the production build and a low one only weak evidence against it. |

## Packages and tools

| Tool | What it is | How this part uses it |
|---|---|---|
| Ollama 0.33.3 and the `ollama` Python client 0.6.2 | A server that downloads language models and answers chat requests over HTTP on port 11434, and the client library that talks to it | Every local candidate runs through it. The harness pulls a missing model tag, warms the model up, reads how much of it sits on the GPU, and unloads it after the run |
| `mcp` 2.1.1 | The Model Context Protocol client library | Connects the agent loop to `web_search_mcp` over HTTP and turns the server's tool list into the schemas each model sees |
| `web_search_mcp` and SearXNG | Our tool server (see [MCP Tool Server](03_web_search_mcp.md)) and the metasearch engine in Docker on port 8080 | The harness starts its own tool server as a child process with a per-run cache folder and a fixed home, so every candidate in a pass reads the same pages for the same query and the same forecast |
| `pydantic` 2.13.5 | A library for typed data records validated on load | Every file the benchmark reads or writes is a pydantic model: questions, candidates, transcripts, gate lists, judge verdicts, scores. A verdict file is scored only if it parses as the `JudgeVerdict` model |
| `pyyaml` 6.0.3 and `rich` 15.0.0 | A YAML parser and a terminal formatting library | YAML holds the questions, the configuration, the hand-written answers, and the review sheet. `rich` prints the progress lines and the speed table |
| Claude Code and the `benchmark-judge` subagent | The coding assistant this project is developed with, and an agent definition in `.claude/agents/` | The judge: the subagent reads exported case files and writes one verdict file per question, on your Claude Code subscription, so judging costs nothing |

## How it works

### The benchmark end to end

One pass of the benchmark is four commands and one Claude Code subagent, each reading the files the step before it wrote.

```mermaid
flowchart TB
--8<-- "_includes/palette.mmd"
%% grid: .  config+questions  .
%% grid: .  run               .
%% grid: .  judgeexport       .
%% grid: .  judge             rubric
%% grid: .  judgeimport       .
%% grid: .  report            sheet
%% grid: .  standings         .
%% peers: run judgeexport judge judgeimport report
%% peers: config questions rubric sheet standings
config[("config.yaml<br/>the candidates")]
questions[("questions.yaml<br/>28 questions")]
run("benchmark-run<br/>asks each question")
judgeexport("judge --export<br/>harness gates")
judge("judge subagent<br/>in Claude Code")
judgeimport("judge --import<br/>checks each verdict")
report("benchmark-report<br/>scores candidates")
rubric[("rubric.md<br/>5 gates, 3 scores")]
sheet[("review_sheet.yaml<br/>20% to check by hand")]
standings[("report.md<br/>the standings")]
config --> run
questions --> run
run -- "key.jsonl:#nbsp;a#nbsp;transcript#nbsp;per#nbsp;question" --> judgeexport
judgeexport -- "judge_cases/key/:#nbsp;a#nbsp;case#nbsp;per#nbsp;question" --> judge
rubric --> judge
judge -- "qid.verdict.json:#nbsp;a#nbsp;verdict#nbsp;per#nbsp;case" --> judgeimport
judgeimport -- "key.scores.jsonl:#nbsp;gates#nbsp;and#nbsp;scores" --> report
report -- "writes a sample" --> sheet
sheet -- "your checks" --> report
report --> standings
class config,questions,run,judgeexport,judgeimport,report,rubric,sheet,standings ours
class judge ext
```

Every file a step writes lands in `benchmark/results/version_N/`, one folder per pass, and `key` is a candidate's key from `config.yaml`, so every candidate has its own transcript file and its own score file. The two judge steps are one command run twice, `benchmark-judge --export` before the subagent and `benchmark-judge --import` after it. `benchmark-manual` writes a hand-written candidate's transcripts into the same folder, so it joins the flow at the transcript file. The subagent runs on your Claude Code subscription, so judging a pass costs nothing. `benchmark-run`, `benchmark-judge --export`, and `benchmark-judge --import` skip the questions they have already handled, so any of them can be stopped and run again.

### Questions, rubric, and configuration

Three files define the benchmark, and everything else is machinery that reads them.

| File | What it holds | What reads it |
|---|---|---|
| `benchmark/config.yaml` | The candidates, the policy they all run under, the service addresses, the fixed home the forecast tool reports on, and the review sample | Every command: `benchmark-run`, `benchmark-manual`, `benchmark-judge`, `benchmark-report`, and `scripts/benchmark_llm.py` |
| `benchmark/questions.yaml` | 38 questions, set 1.4, each with its search expectation, constraints, and reference sketch | `benchmark-run`, `benchmark-manual`, `benchmark-judge`, and `benchmark-report` |
| `benchmark/rubric.md` | The judge's instructions: five gates and three dimension scores | `benchmark-judge --export` copies it beside the cases, and the `benchmark-judge` subagent reads it first |

`benchmark/questions.yaml` holds 38 questions in five categories:

| Category | Questions | What it tests | Examples |
|---|---|---|---|
| A | A1 to A11 | Answering from knowledge or reasoning, without searching | Explaining why a mixture-of-experts model fits in less memory than its parameter count suggests; diagnosing a yellowing plant; a follow-up conversation about a 16 GB versus a 24 GB machine |
| B | B11 to B21 | Deciding to search | The current federal funds rate; a day trip from Lucerne tomorrow; why GPU prices rose |
| C | C23 to C28 | Explicit arithmetic that should go through the calculator tools | A tip; compound savings; a mortgage payment |
| D | D29 to D35 | Unclear input: staying silent for speech not meant for the assistant, asking to repeat a garbled request, a plain "Okay." for "never mind", and two clear questions as controls | A television host announcing the forecast; "What's the the uh capital"; "Never mind."; "Who rote Pride and Prejudice?" |
| E | E36 to E38 | The weather at home, answered from the forecast tool without searching | An umbrella tomorrow afternoon; the weekend's weather; how cold it gets tonight |

Each question carries these fields:

- `expected_search`: `no`, `yes`, or `instructed` when the question itself says "search for".
- `constraints`, optional: `max_words`, `budget_usd`, and `no_product_names`.
- The gates the judge should watch for.
- A reference sketch with the figures a correct answer must contain.
- `expected_route`: `calculate` on A2, A7, and every question in category C, `answer` on every question in category D, and `weather` on every question in category E. It lets the report score the [question router](04_conversation_agent.md#the-question-router) on its own.
- `expected_reply`, carried only by D29 to D33: `silent` for speech not meant for the assistant, `clarify` for a garbled request, or `acknowledge` for "never mind". A question without one expects an ordinary answer.

`benchmark/rubric.md` is the judge's instructions, which the subagent reads first and follows verbatim. It defines the five gates only a reader of the transcript can detect:

- A fabricated current fact.
- A violated constraint.
- An estimate presented as fact.
- Lost the context of an earlier exchange.
- Agreeing with a false premise.

It also defines three dimension scores: answer quality 0 to 5, judgment 0 to 3, and spoken fit 0 to 2. That makes ten points per question and 380 per candidate: 110 for A, 110 for B, 60 for C, 70 for D, and 30 for E.

Every candidate runs under the same settings, set once at the top of `benchmark/config.yaml`:

```yaml
policy:
  temperature: 0.7
  max_tool_rounds: 4
  max_output_tokens: 600
  word_budget: 200
  context_tokens: 16384
  tool_timeout_seconds: 60
```

`word_budget` caps the spoken answer at 200 words, cut at the end of the sentence that crosses the limit, and `tool_timeout_seconds` is how long one tool call may take before the model is told the tool is unreachable.

Below the policy, each candidate has an entry like the top scorer's, where `key` is the name you pass on the command line and `preview: true` marks a reduced-precision build:

```yaml
  - key: gemma4-26b-a4b-iq4
    label: Gemma 4 26B-A4B, UD-IQ4_XS (preview, tight fit)
    provider: ollama
    model: hf.co/unsloth/gemma-4-26B-A4B-it-GGUF:UD-IQ4_XS
    think: false
    preview: true
```

`provider` is `ollama` for a model Ollama runs, or `manual` for hand-written answers. The same file sets the review sample: 20 percent of each candidate's judged questions, drawn with the seed 20260905.

### A pass

A pass is one `benchmark-run --run version_N` invocation, and `version_N` is a folder under `benchmark/results/`. The harness works through it in this order.

**Before the first candidate**

1. Checks that SearXNG answers.
2. Refuses to continue if port 8766 is already taken.
3. Starts `web_search_mcp` as a child process with `WEB_SEARCH_CACHE_DIR` pointing at `version_N/cache` and the forecast's home taken from `weather_home` in `config.yaml`. The cache keeps the first forecast fetched, so every candidate in the pass reads the same one.
4. Lists the server's tools and refuses to continue unless all eight expected tools are present: `search_and_read`, `web_search`, `fetch_page`, `wikipedia_lookup`, `calculate`, `percent`, `convert`, and `weather_forecast`. A stale server from an earlier run can therefore never answer this run's tool calls.
5. Writes `run_meta.json` with the question set version, the system prompt version, the policy, the candidate list, the machine, the chip, the memory size, the Ollama version, and the git commit.

**For each candidate**

1. Skips the questions already in `version_N/<key>.jsonl`, unless you pass `--force`.
2. Skips manual candidates, which `benchmark-manual` produces instead.
3. Pulls the model tag if Ollama does not have it.
4. Sends a one-token warm-up request with the run's context length.
5. Reads Ollama's `/api/ps` to compare the model's size with the bytes resident on the GPU. A model that does not fit prints a yellow warning and is still run, with `fully_on_gpu: false` recorded in every result so the report can flag its latency as unreliable.

**For each question**

1. Runs the question through `assistant_core.agent_loop.run`, the same function the Home Assistant component calls. A question with a follow-up is run as two exchanges, and the second sees the conversation of the first.
2. Records a `QuestionResult`: the transcript of every exchange, with each model call's timing and token counts, each tool call and its result, the router's decision, the memory fit, and an error string if the model call itself failed.
3. Appends it to `version_N/<key>.jsonl` as soon as it finishes, which is why a pass can be interrupted and resumed.

**After the last question**

1. Unloads the model.
2. Deletes it from disk if you passed `--delete-models`, which matters for the 11 to 14 GB preview builds.

### Gates

Some gates need no judgment, only a look at the transcript. `benchmark/gates.py` evaluates nine of them together and returns every one that failed. `benchmark-judge` applies them twice for every question: `--export` writes them into the case file the judge reads, and `--import` records them in the question's score. "Searched" means any call to `search_and_read`, `web_search`, `fetch_page`, or `wikipedia_lookup`; calculator and forecast calls do not count, so a category C question that calls `calculate` and never searches passes both search gates. The word-limit gate applies only to questions that declare `max_words` (A10, the 45-second spoken explanation, with a limit of 120). A question whose model call raised an exception gets the single gate `run_error` and is never sent to the judge.

The nine checks sit side by side in `harness_gates`, from `benchmark/gates.py`:

```python
def harness_gates(question: Question, result: QuestionResult, max_tool_rounds: int) -> list[Gate]:
    if result.error:
        return [Gate.RUN_ERROR]
    checks = (
        (Gate.SEARCHED_ON_NO_SEARCH_QUESTION, result.searched and not question.should_search),
        (Gate.DID_NOT_SEARCH_ON_SEARCH_QUESTION, question.should_search and not result.searched),
        (Gate.DID_NOT_CHECK_FORECAST_ON_WEATHER_QUESTION, question.route == Route.WEATHER and not result.checked_forecast),
        (Gate.MALFORMED_TOOL_CALL, any(transcript.malformed_tool_calls for transcript in result.exchanges)),
        (Gate.TOO_MANY_TOOL_CALLS, any(transcript.tool_call_count > max_tool_rounds for transcript in result.exchanges)),
        (Gate.NO_FINAL_ANSWER, not result.final.final_answer.strip()),
        (Gate.SPOKE_WHEN_IT_SHOULD_STAY_SILENT, question.should_stay_silent and not result.final.stayed_silent),
        (Gate.STAYED_SILENT_ON_REAL_REQUEST, not question.should_stay_silent and any(transcript.stayed_silent for transcript in result.exchanges)),
        (Gate.VIOLATED_EXPLICIT_CONSTRAINT, exceeds_word_limit(question, result)),
    )
    return [gate for gate, failed in checks if failed]
```

The harness gates and the judge's gates meet in the `Score` record. Its `gates` property is the union of both lists, `dimension_total` is the sum of the three judge scores, and `total` is zero the moment any gate is present. The report prints both totals side by side, so the gap between them is what the gates cost a candidate. The same record notices when the harness and the judge disagree about the search decision, which is what puts a question on the review sheet.

The four properties that combine the two lists, from the `Score` record in `benchmark/records.py`:

```python
    @property
    def gates(self) -> list[Gate]:
        judge_gates = self.judge.gates_hit if self.judge else []
        return sorted(set(self.harness_gates) | set(judge_gates))

    @property
    def dimension_total(self) -> int:
        if self.judge is None:
            return 0
        return self.judge.answer_quality + self.judge.judgment + self.judge.spoken_fit

    @property
    def total(self) -> int:
        return 0 if self.gates else self.dimension_total

    @property
    def harness_and_judge_disagree(self) -> bool:
        if self.judge is None:
            return False
        harness_says_search_wrong = any(gate in (Gate.SEARCHED_ON_NO_SEARCH_QUESTION, Gate.DID_NOT_SEARCH_ON_SEARCH_QUESTION) for gate in self.harness_gates)
        return harness_says_search_wrong == self.judge.search_decision_correct
```

### The judge

Every transcript is graded by Claude Opus 5, running as the `benchmark-judge` subagent in Claude Code and reading the rubric. Each case file it grades holds the question with its metadata and reference sketch, every message rendered as `USER`, `ASSISTANT`, `TOOL CALL`, and `TOOL RESULT` lines, a note when the word cap cut the spoken answer, and the harness observations (whether the assistant searched, how many tool, calculator, and forecast calls it made, whether it stayed silent, what the router decided, and which harness gates already apply). The judge is told to grade the final assistant message of the last exchange and to score the three dimensions even when a gate applies.

`benchmark-judge version_N --export` writes one markdown case per unjudged question under `version_N/judge_cases/<key>/`, a `manifest.json` listing each case and the path of the verdict it expects, and a copy of the rubric one folder up. You then hand one candidate's folder to the `benchmark-judge` subagent defined in `.claude/agents/benchmark-judge.md`, which reads the rubric, grades every case in the manifest without reading other candidates' folders, and writes `<qid>.verdict.json` next to each case. `benchmark-judge version_N --import` parses each verdict with the `JudgeVerdict` model, rejects any file with an unknown gate name or a score outside its range, and writes `<key>.scores.jsonl` with the judge recorded as `claude-opus-5 (Claude Code subagent)`. A rejected verdict is reported and left unscored, so you re-run the subagent for that case and import again.

### Report and review sheet

`benchmark-report version_N` reads every candidate's results and scores and writes `report.md` next to them. The scores table is sorted by total and shows, per candidate, the total, the ungated total, the five category totals, the number of gated questions, and the mean of each dimension. Below it come the gate counts by type, the router's accuracy (how many questions the rule layer decided, how many the model layer decided, and each candidate's misroutes), a table of medians that are logged but never scored (time to first token, total time, answer words, questions searched, and whether the model was fully on the GPU), a per-question matrix where `G (7)` means a question gated to zero that earned 7 dimension points, and the judge that produced the scores. When any candidate is a preview build the report carries the caveat that a high preview score is strong evidence for the production build and a low one weak evidence against it. `--compare version_M` adds a table of totals restricted to the questions both passes share, so a pass with new questions is not inflated.

The same command writes the review sheet. For each candidate it draws 20 percent of the judged questions with a seed fixed per candidate, adds every question where the harness and the judge disagree about the search decision, and writes them to `review_sheet.yaml` with the judge's gates, scores, and one-sentence reasons alongside an empty `human` block, plus a readable `review_sheet.md`. You fill in the human block by hand and re-run the report; the values you entered survive re-renders, and once any are present the report prints the gate agreement rate against a 90 percent target and the mean absolute difference in dimension totals.

### Reference and speed table

`benchmark-manual <key> --run version_N` replays scripted answers from `benchmark/manual/<key>.yaml` through the real agent loop and a real tool server. Each scripted exchange lists the search queries to issue, any other tool calls such as `calculate` expressions, and the final spoken answer. A `ScriptedAnswerClient` plays the tool calls first and the answer second, so the transcript carries genuine excerpts and genuine calculator results, and the gates, the word cap, and the judge treat the file exactly like a model run. The configured reference, `claude-fable-5-1-manual-2`, was written closed book by a fresh Claude Fable 5.1 subagent that saw only the questions and the system prompt and ran the tools itself. It answers the 28 questions in categories A to C and is the ceiling for them, not a model you could buy, and its losses show which questions punish even a careful answer.

`scripts/benchmark_llm.py --run version_N` measures raw speed rather than quality. For every Ollama candidate it sends a 400-word and a 3,000-word prompt at temperature 0, asks for 128 tokens, and reports prompt tokens per second, time to first token, and generation tokens per second, with a column saying whether the model was fully on the GPU. The table is printed and written to `version_N/speed.md`. These numbers project how a model will feel on the production Mac (see [LLMs on Apple Silicon](02_local_llm.md#prefill-and-decode)); they play no part in the score.

### Reading the standings

Pass 5 ran every runnable candidate under system prompt 1.5 with routing on, judged by the subagent:

| Candidate | Build | Score /280 | Gated questions |
|---|---|---|---|
| Gemma 4 26B-A4B | UD-IQ4_XS, preview | 232 | 1 |
| Claude Fable 5.1 (the hand-written reference) | Closed book, by a fresh subagent | 226 | 5 |
| Qwen 3.6 35B-A3B | UD-IQ3_XXS, 3-bit preview | 208 | 4 |
| Gemma 4 26B-A4B | UD-IQ3_XXS, 3-bit preview | 199 | 5 |
| Gemma 4 12B, dense | Q4_K_M | 186 | 4 |
| Gemma 4 E4B | QAT int4 | 176 | 5 |
| Qwen 3.5 4B | Q4_K_M | 157 | 7 |
| Qwen 3.5 9B | Q4_K_M | 154 | 7 |
| gpt-oss 20B | MXFP4 | 145 | 9 |

Both large mixture-of-experts previews called the calculator on all six arithmetic questions. The top scorer's one gated question is B21, where it skipped the search and accepted a false premise. Qwen 3.6's four are too many tool calls on A2, A6, and B20, two of them with a fabricated current fact, and a broken constraint on B15. That is the reading behind the decision in [Hardware](08_hardware_and_deployment.md#the-memory-budget), a 26B or 35B mixture-of-experts model at full 4-bit precision on a 32 GB machine; their latency on the 16 GB laptop, one to three minutes per answer, is not part of the score, because neither fits on the GPU there (7.5 of 15.2 GB resident for the top scorer).

## Run it yourself

Every command runs from the repository folder. A pass takes most of a 16 GB machine, so first make sure the Home Assistant VM and the speech services are down, then check that Ollama is listening and start SearXNG:

```bash
pgrep -fl benchmark-run || echo "no benchmark running"
scripts/haos_vm.sh stop
scripts/services.sh status        # ollama on 11434 should be listening; whisper and kokoro should not
scripts/searxng.sh up
```

Pick a fresh folder name for your pass. `benchmark/results/` is committed, and one folder is one pass, so do not write into `version_5`. Run two questions through one of the small models:

```bash
uv run benchmark-run --run version_6 --candidate gemma4-e4b --question A1 --question C23
```

You will see a rule line naming the candidate and the number of pending questions, a pull progress bar the first time the tag is missing, and then one line per question:

```
  A1   no search route=answer/model    calls=0 ttft=1.4s total=4.7s words=76
  C23  no search route=calculate/rule  calls=1 ttft=1.2s total=6.1s words=31
```

The results are in `benchmark/results/version_6/gemma4-e4b.jsonl`, with `run_meta.json` and a `cache/` folder beside it. Stop a run with Ctrl-C. The tool server child stops with the harness, and the finished questions stay in the file, so running the same command again continues where it stopped. Add `--force` to redo questions that already have a result.

Judge those two answers through the subagent, which costs nothing:

```bash
uv run benchmark-judge version_6 --export
```

You will see `gemma4-e4b: exported 2 cases to benchmark/results/version_6/judge_cases/gemma4-e4b`. In Claude Code, ask for the `benchmark-judge` subagent and give it that folder; it replies with the number of verdicts it wrote. Then import them and render the report:

```bash
uv run benchmark-judge version_6 --import
uv run benchmark-report version_6
```

The import prints `gemma4-e4b: imported 2 verdicts`, and the report prints `wrote benchmark/results/version_6/report.md and benchmark/results/version_6/review_sheet.yaml`. Open `report.md` to see the tables from the previous section for your two questions.

For a full pass over every candidate, omit `--candidate`. The large preview builds are 11 to 14 GB each, so add `--delete-models` to remove each one after its run, and expect the pass to take hours on a 16 GB machine because those models spill to the CPU:

```bash
uv run benchmark-run --run version_6 --delete-models
uv run benchmark-manual claude-fable-5-1-manual-2 --run version_6
uv run benchmark-report version_6 --compare version_5
```

For raw speed alone, which takes a minute per model:

```bash
uv run python scripts/benchmark_llm.py --run version_6 --candidate gemma4-e4b
```

You will see a table headed "Raw speed on this machine" with a short and a long prompt row, and `benchmark/results/version_6/speed.md` beside it. When you are done, stop SearXNG with `scripts/searxng.sh down` if you started it only for this; Ollama stays up.

## Where to look in the code

| Path | What you find there |
|---|---|
| `benchmark/run.py` | `benchmark-run`: loads the config and questions, starts the tool server child, prepares and releases each model, runs each question through `agent_loop.run`, appends results, prints the per-question line |
| `benchmark/gates.py` | The nine mechanical gates and the `run_error` gate |
| `benchmark/records.py` | Every typed record: `Question`, `Candidate`, `Services`, `JudgeConfig`, `QuestionResult`, `JudgeVerdict`, `Score`, and the loaders for the YAML files |
| `benchmark/judge.py` | `benchmark-judge`: case rendering, `--export`, `--import`, and range validation of verdicts |
| `benchmark/report.py` | `benchmark-report`: every table in `report.md`, the comparison, and the review sheet with its seeded sample |
| `benchmark/mcp_process.py` | Starting `web_search_mcp` as a child with a per-run cache and the fixed home for the forecast, the port check, and the tool-list check |
| `benchmark/ollama_utils.py` | Pull, warm-up, memory fit from `/api/ps`, unload, delete |
| `benchmark/manual_run.py` | `benchmark-manual` and the `ScriptedAnswerClient` that plays hand-written answers |
| `benchmark/questions.yaml`, `benchmark/rubric.md`, `benchmark/config.yaml` | The question set, the judge's instructions, and the candidate list with the shared policy and the forecast's home |
| `benchmark/manual/` | The hand-written reference answers, one YAML file per manual candidate |
| `benchmark/results/version_N/` | One folder per pass: `run_meta.json`, `<key>.jsonl`, `<key>.scores.jsonl`, `judge_cases/`, `cache/`, `report.md`, `review_sheet.yaml`, `speed.md` |
| `scripts/benchmark_llm.py` | The raw speed table |
| `.claude/agents/benchmark-judge.md` | The subagent's grading procedure and the verdict file format |
| `tests/test_gates_and_records.py`, `tests/test_manual_run.py`, `tests/test_mcp_process.py` | Gate detection on synthetic results, score zeroing and disagreement, scripted exchanges, and the port check |

## Further reading

- Design doc: [design_docs/v1/01_llm_benchmark.md](https://github.com/seanlin2000/home_assistant/blob/main/design_docs/v1/01_llm_benchmark.md), including the pass-by-pass results and what each pass showed
- [unsloth/gemma-4-26B-A4B-it-GGUF](https://huggingface.co/unsloth/gemma-4-26B-A4B-it-GGUF), the source of the Gemma preview builds and their sizes on disk
- [unsloth/Qwen3.6-35B-A3B-GGUF](https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF/tree/main), the same for the Qwen preview
- [ollama.com/library/qwen3.5](https://ollama.com/library/qwen3.5), the tags and sizes behind the two small Qwen candidates
- [gemma4.dev, thinking mode](https://gemma4.dev/docs/concepts/thinking-mode), why the Gemma candidates run with thinking off
- [willitrunai.com on gpt-oss-20b](https://willitrunai.com/blog/gpt-oss-20b-vram-requirements), what a 13 GB model does on a 16 GB Mac
