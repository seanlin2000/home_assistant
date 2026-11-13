# LLM benchmark report, qwen38_think_levels

Question set v2.4, 75 questions, 10 points each. Any gate failure zeroes a question. System prompt v3.0; question routing off.

## Scores

Total counts a gated question as zero; ungated total ignores the gates and sums the dimension scores, so the gap between them is what the gates cost.

| Candidate | Total | Ungated total | Category A | Category B | Category C | Category D | Category E | Gated questions | Quality /5 | Judgment /3 | Spoken /2 | Unjudged |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen 3.8 27B, Q8_0, on llama-server, thinking low (prompt 3.0) | 531/750 | 608/750 | 80/110 | 54/110 | 58/60 | 56/70 | 28/30 | 13 | 4.1 | 2.6 | 1.4 | 0 |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking off (prompt 3.0) | 429/750 | 483/750 | 73/110 | 62/110 | 48/60 | 57/70 | 9/30 | 25 | 3.2 | 2.0 | 1.2 | 0 |

## Gate failures by type

| Candidate | did_not_check_forecast_on_weather_question | did_not_search_on_search_question | fabricated_current_fact | missing_required_tool | searched_on_no_search_question | spoke_when_it_should_stay_silent | stayed_silent_on_real_request | too_many_tool_calls | violated_explicit_constraint | wrong_entity | wrong_place |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen 3.8 27B, Q8_0, on llama-server, thinking low (prompt 3.0) | 0 | 4 | 5 | 3 | 2 | 1 | 0 | 0 | 1 | 1 | 0 |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking off (prompt 3.0) | 3 | 8 | 8 | 10 | 1 | 0 | 9 | 2 | 1 | 6 | 1 |

## Router

No routed results in this run.

## Logged, not scored (prototype machine, for projection only)

| Candidate | Median time to first token | Median total | Mean answer words | Questions searched | Prefill | Decode | Fully on GPU |
|---|---|---|---|---|---|---|---|
| Qwen 3.8 27B, Q8_0, on llama-server, thinking low (prompt 3.0) | 6.0 s | 33.2 s | 146 | 23/75 | 86 tok/s | 4 tok/s | n/a |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking off (prompt 3.0) | 0.5 s | 9.2 s | 121 | 18/75 | 67 tok/s | 9 tok/s | n/a |

## Per-question scores (G = gated to zero, - = not judged)

| Question | qwen3.8-27b-low | qwen3.8-27b-off |
|---|---|---|
| A1 | 4 | 7 |
| A2 | 9 | 6 |
| A3 | 9 | 10 |
| A4 | 8 | 8 |
| A5 | 7 | G (0) |
| A6 | G (6) | 9 |
| A7 | 7 | 8 |
| A8 | 9 | 9 |
| A9 | 8 | 7 |
| A10 | 9 | G (6) |
| A11 | 10 | 9 |
| B11 | 9 | 8 |
| B12 | G (4) | 6 |
| B13 | G (6) | 6 |
| B14 | 8 | 8 |
| B15 | G (6) | G (1) |
| B16 | 3 | 8 |
| B17 | 8 | 9 |
| B18 | 5 | 8 |
| B19 | 8 | 9 |
| B20 | 4 | G (4) |
| B21 | 9 | G (7) |
| C23 | 10 | 10 |
| C24 | 10 | 9 |
| C25 | 10 | 10 |
| C26 | 10 | 10 |
| C27 | 8 | 9 |
| C28 | 10 | G (0) |
| D29 | G (0) | 10 |
| D30 | 10 | 10 |
| D31 | 10 | 10 |
| D32 | 10 | 9 |
| D33 | 6 | G (2) |
| D34 | 10 | 8 |
| D35 | 10 | 10 |
| E36 | 9 | 9 |
| E37 | 10 | G (0) |
| E38 | 9 | G (0) |
| H39 | G (7) | G (0) |
| H40 | G (4) | 9 |
| H41 | 9 | 9 |
| H42 | 7 | G (0) |
| H43 | G (6) | G (1) |
| H44 | 9 | 9 |
| H45 | 9 | 8 |
| H46 | G (5) | G (5) |
| I47 | 9 | G (0) |
| I48 | 10 | 10 |
| I49 | 9 | 10 |
| I50 | G (8) | 10 |
| I51 | 8 | 8 |
| I52 | 10 | 9 |
| F53 | 10 | 10 |
| F54 | G (9) | G (6) |
| F55 | 9 | 8 |
| F56 | 8 | 5 |
| F57 | G (8) | 10 |
| F58 | 6 | G (4) |
| F59 | 10 | 9 |
| F60 | 7 | G (0) |
| J61 | 9 | G (0) |
| J62 | 10 | 10 |
| J63 | 7 | G (5) |
| J64 | 7 | G (0) |
| J65 | 8 | 8 |
| J66 | 6 | 6 |
| J67 | 10 | G (0) |
| J68 | 10 | G (2) |
| J69 | 8 | 4 |
| J70 | 10 | 8 |
| J71 | 10 | 10 |
| J72 | 10 | G (2) |
| J73 | 10 | G (4) |
| J74 | G (8) | G (5) |
| J75 | 10 | 10 |

## Judge agreement

Review sheet not yet filled in.

## Judge

Scores in this pass were produced by: claude-opus-5-5. Same rubric and output schema as every other pass, but each pass is graded in a separate session of the judge, so compare totals across passes with that in mind.
