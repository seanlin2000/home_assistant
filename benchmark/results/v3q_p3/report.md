# LLM benchmark report, v3q_p3

Question set v3.0, 75 questions, 10 points each. Any gate failure zeroes a question. System prompt v3.0; question routing off.

## Scores

Total counts a gated question as zero; ungated total ignores the gates and sums the dimension scores, so the gap between them is what the gates cost.

| Candidate | Total | Ungated total | Category A | Category B | Category C | Category D | Category E | Gated questions | Quality /5 | Judgment /3 | Spoken /2 | Unjudged |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen 3.8 27B, Q8_0, on llama-server, thinking low (prompt 3.0) | 119/220 | 152/220 | 94/130 | 25/90 | n/a | n/a | n/a | 7 | 3.5 | 2.5 | 0.9 | 0 |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking medium (prompt 3.0) | 95/220 | 142/220 | 87/130 | 8/90 | n/a | n/a | n/a | 9 | 3.5 | 2.5 | 0.5 | 0 |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking medium (prompt 3.0) | 55/220 | 113/220 | 46/130 | 9/90 | n/a | n/a | n/a | 16 | 3.1 | 1.5 | 0.5 | 0 |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking low (prompt 3.0) | 44/220 | 112/220 | 36/130 | 8/90 | n/a | n/a | n/a | 17 | 3.2 | 1.6 | 0.3 | 0 |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking off (prompt 3.0) | 42/220 | 85/220 | 35/130 | 7/90 | n/a | n/a | n/a | 16 | 1.8 | 1.9 | 0.2 | 0 |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking off (prompt 3.0) | 0/0 | 0/0 | 0/0 | 0/0 | n/a | n/a | n/a | 0 | 0.0 | 0.0 | 0.0 | 0 |

## Gate failures by type

| Candidate | fabricated_current_fact | malformed_tool_call | missing_required_tool | no_final_answer | searched_on_no_search_question | too_many_tool_calls |
|---|---|---|---|---|---|---|
| Qwen 3.8 27B, Q8_0, on llama-server, thinking medium (prompt 3.0) | 4 | 0 | 1 | 0 | 2 | 3 |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking low (prompt 3.0) | 5 | 0 | 0 | 0 | 2 | 2 |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking off (prompt 3.0) | 0 | 0 | 0 | 0 | 0 | 0 |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking medium (prompt 3.0) | 0 | 1 | 1 | 4 | 9 | 12 |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking low (prompt 3.0) | 1 | 0 | 0 | 2 | 9 | 12 |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking off (prompt 3.0) | 1 | 0 | 0 | 0 | 9 | 14 |

## Router

No routed results in this run.

## Logged, not scored (prototype machine, for projection only)

| Candidate | Median time to first token | Median total | Mean answer words | Questions searched | Prefill | Decode | Fully on GPU |
|---|---|---|---|---|---|---|---|
| Qwen 3.8 27B, Q8_0, on llama-server, thinking medium (prompt 3.0) | 3.1 s | 43.0 s | 505 | 9/22 | 639 tok/s | 32 tok/s | n/a |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking low (prompt 3.0) | 14.0 s | 50.7 s | 481 | 9/22 | 641 tok/s | 35 tok/s | n/a |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking off (prompt 3.0) | 0.3 s | 17.1 s | 374 | 1/12 | 557 tok/s | 31 tok/s | n/a |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking medium (prompt 3.0) | 2.1 s | 89.7 s | 451 | 16/22 | 883 tok/s | 53 tok/s | n/a |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking low (prompt 3.0) | 4.0 s | 71.5 s | 499 | 16/22 | 887 tok/s | 53 tok/s | n/a |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking off (prompt 3.0) | 0.3 s | 36.2 s | 415 | 16/22 | 869 tok/s | 52 tok/s | n/a |

## Per-question scores (G = gated to zero, - = not judged)

| Question | qwen3.8-27b-medium | qwen3.8-27b-low | qwen3.8-27b-off | qwen3.8-flash-next-medium | qwen3.8-flash-next-low | qwen3.8-flash-next-off |
|---|---|---|---|---|---|---|
| A76 | 7 | 8 | - | G (5) | G (6) | G (2) |
| A77 | 8 | 8 | - | 9 | 8 | 5 |
| A78 | 7 | 9 | - | G (5) | G (6) | 5 |
| A79 | 7 | 7 | - | G (3) | G (3) | G (2) |
| A80 | 7 | 8 | - | G (7) | G (3) | 5 |
| A81 | 7 | 8 | - | G (5) | G (5) | G (3) |
| A82 | 7 | 8 | - | 8 | G (4) | G (2) |
| A83 | 9 | 8 | - | 10 | 10 | 10 |
| A84 | 8 | 8 | - | 9 | 8 | G (3) |
| A85 | 5 | 4 | - | G (0) | G (0) | G (3) |
| A86 | G (4) | G (7) | - | G (6) | G (4) | G (2) |
| A87 | 6 | 8 | - | G (5) | G (4) | G (2) |
| A11 | 9 | 10 | - | 10 | 10 | 10 |
| B88 | G (7) | 8 | - | G (4) | G (4) | G (3) |
| B89 | G (7) | G (4) | - | G (3) | G (2) | G (3) |
| B90 | G (7) | 7 | - | G (0) | G (7) | G (3) |
| B91 | G (5) | G (7) | - | G (4) | G (7) | G (3) |
| B92 | G (5) | G (5) | - | G (7) | G (8) | G (4) |
| B93 | G (4) | G (4) | - | G (4) | G (3) | G (2) |
| B94 | G (3) | G (2) | - | G (0) | G (0) | G (3) |
| B95 | G (5) | G (4) | - | G (0) | G (2) | G (3) |
| B21 | 8 | 10 | - | 9 | 8 | 7 |
| C23 | - | - | - | - | - | - |
| C24 | - | - | - | - | - | - |
| C25 | - | - | - | - | - | - |
| C26 | - | - | - | - | - | - |
| C27 | - | - | - | - | - | - |
| C28 | - | - | - | - | - | - |
| D29 | - | - | - | - | - | - |
| D30 | - | - | - | - | - | - |
| D31 | - | - | - | - | - | - |
| D32 | - | - | - | - | - | - |
| D33 | - | - | - | - | - | - |
| D34 | - | - | - | - | - | - |
| D35 | - | - | - | - | - | - |
| E36 | - | - | - | - | - | - |
| E37 | - | - | - | - | - | - |
| E38 | - | - | - | - | - | - |
| H39 | - | - | - | - | - | - |
| H40 | - | - | - | - | - | - |
| H41 | - | - | - | - | - | - |
| H42 | - | - | - | - | - | - |
| H43 | - | - | - | - | - | - |
| H44 | - | - | - | - | - | - |
| H45 | - | - | - | - | - | - |
| H46 | - | - | - | - | - | - |
| I47 | - | - | - | - | - | - |
| I48 | - | - | - | - | - | - |
| I49 | - | - | - | - | - | - |
| I50 | - | - | - | - | - | - |
| I51 | - | - | - | - | - | - |
| I52 | - | - | - | - | - | - |
| F53 | - | - | - | - | - | - |
| F54 | - | - | - | - | - | - |
| F55 | - | - | - | - | - | - |
| F56 | - | - | - | - | - | - |
| F57 | - | - | - | - | - | - |
| F58 | - | - | - | - | - | - |
| F59 | - | - | - | - | - | - |
| F60 | - | - | - | - | - | - |
| J61 | - | - | - | - | - | - |
| J62 | - | - | - | - | - | - |
| J63 | - | - | - | - | - | - |
| J64 | - | - | - | - | - | - |
| J65 | - | - | - | - | - | - |
| J66 | - | - | - | - | - | - |
| J67 | - | - | - | - | - | - |
| J68 | - | - | - | - | - | - |
| J69 | - | - | - | - | - | - |
| J70 | - | - | - | - | - | - |
| J71 | - | - | - | - | - | - |
| J72 | - | - | - | - | - | - |
| J73 | - | - | - | - | - | - |
| J74 | - | - | - | - | - | - |
| J75 | - | - | - | - | - | - |

## Judge agreement

Review sheet not yet filled in.

## Judge

Scores in this pass were produced by: claude-opus-5-5. Same rubric and output schema as every other pass, but each pass is graded in a separate session of the judge, so compare totals across passes with that in mind.
