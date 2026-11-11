# LLM benchmark report, qwen38_lean_medium

Question set v2.4, 75 questions, 10 points each. Any gate failure zeroes a question. System prompt v3.0; question routing off.

## Scores

Total counts a gated question as zero; ungated total ignores the gates and sums the dimension scores, so the gap between them is what the gates cost.

| Candidate | Total | Ungated total | Category A | Category B | Category C | Category D | Category E | Gated questions | Quality /5 | Judgment /3 | Spoken /2 | Unjudged |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen 3.8 27B, Q8_0, on llama-server, thinking medium (prompt 3.0) | 509/750 | 600/750 | 60/110 | 58/110 | 60/60 | 56/70 | 17/30 | 16 | 4.1 | 2.6 | 1.3 | 0 |

## Compared with m7_run2

Totals on the questions both passes share, so new questions do not inflate the second pass.

| Candidate | Shared questions | Previous | This pass | Change | Previous ungated | This pass ungated | Previous gated | This pass gated |
|---|---|---|---|---|---|---|---|---|

## Gate failures by type

| Candidate | did_not_check_forecast_on_weather_question | did_not_search_on_search_question | fabricated_current_fact | missing_required_tool | searched_on_no_search_question | spoke_when_it_should_stay_silent | too_many_tool_calls | violated_explicit_constraint | wrong_entity | wrong_place |
|---|---|---|---|---|---|---|---|---|---|---|
| Qwen 3.8 27B, Q8_0, on llama-server, thinking medium (prompt 3.0) | 1 | 3 | 3 | 2 | 4 | 1 | 2 | 1 | 2 | 1 |

## Router

No routed results in this run.

## Logged, not scored (prototype machine, for projection only)

| Candidate | Median time to first token | Median total | Mean answer words | Questions searched | Prefill | Decode | Fully on GPU |
|---|---|---|---|---|---|---|---|
| Qwen 3.8 27B, Q8_0, on llama-server, thinking medium (prompt 3.0) | 4.7 s | 28.8 s | 158 | 26/75 | 124 tok/s | 5 tok/s | n/a |

## Per-question scores (G = gated to zero, - = not judged)

| Question | qwen3.8-27b-medium |
|---|---|
| A1 | 4 |
| A2 | G (9) |
| A3 | 9 |
| A4 | 8 |
| A5 | 6 |
| A6 | G (7) |
| A7 | 8 |
| A8 | 7 |
| A9 | 8 |
| A10 | G (8) |
| A11 | 10 |
| B11 | 9 |
| B12 | 7 |
| B13 | G (5) |
| B14 | 7 |
| B15 | 6 |
| B16 | 5 |
| B17 | 8 |
| B18 | G (7) |
| B19 | 7 |
| B20 | G (6) |
| B21 | 9 |
| C23 | 10 |
| C24 | 10 |
| C25 | 10 |
| C26 | 10 |
| C27 | 10 |
| C28 | 10 |
| D29 | G (0) |
| D30 | 10 |
| D31 | 10 |
| D32 | 10 |
| D33 | 6 |
| D34 | 10 |
| D35 | 10 |
| E36 | G (1) |
| E37 | 9 |
| E38 | 8 |
| H39 | 9 |
| H40 | G (5) |
| H41 | 10 |
| H42 | 10 |
| H43 | G (5) |
| H44 | 9 |
| H45 | G (7) |
| H46 | 10 |
| I47 | 10 |
| I48 | 10 |
| I49 | 9 |
| I50 | 9 |
| I51 | G (7) |
| I52 | 10 |
| F53 | 10 |
| F54 | G (6) |
| F55 | 8 |
| F56 | 8 |
| F57 | 10 |
| F58 | 6 |
| F59 | 9 |
| F60 | 9 |
| J61 | 9 |
| J62 | 9 |
| J63 | G (5) |
| J64 | 7 |
| J65 | 8 |
| J66 | 6 |
| J67 | 10 |
| J68 | G (6) |
| J69 | 7 |
| J70 | 10 |
| J71 | 9 |
| J72 | 10 |
| J73 | 7 |
| J74 | G (7) |
| J75 | 10 |

## Judge agreement

Review sheet not yet filled in.

## Judge

Scores in this pass were produced by: claude-opus-5-5. Same rubric and output schema as every other pass, but each pass is graded in a separate session of the judge, so compare totals across passes with that in mind.
