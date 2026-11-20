# LLM benchmark report, v3q_p2

Question set v3.0, 75 questions, 10 points each. Any gate failure zeroes a question. System prompt v3.0; question routing off.

## Scores

Total counts a gated question as zero; ungated total ignores the gates and sums the dimension scores, so the gap between them is what the gates cost.

| Candidate | Total | Ungated total | Category A | Category B | Category C | Category D | Category E | Gated questions | Quality /5 | Judgment /3 | Spoken /2 | Unjudged |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen 3.8 27B, Q8_0, on llama-server, thinking medium (prompt 3.0) | 120/220 | 152/220 | 88/130 | 32/90 | n/a | n/a | n/a | 7 | 3.5 | 2.5 | 1.0 | 0 |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking low (prompt 3.0) | 105/220 | 142/220 | 79/130 | 26/90 | n/a | n/a | n/a | 8 | 3.4 | 2.2 | 0.9 | 0 |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking off (prompt 3.0) | 49/220 | 116/220 | 41/130 | 8/90 | n/a | n/a | n/a | 16 | 2.7 | 2.0 | 0.6 | 0 |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking medium (prompt 3.0) | 43/220 | 111/220 | 34/130 | 9/90 | n/a | n/a | n/a | 17 | 3.2 | 1.5 | 0.4 | 0 |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking low (prompt 3.0) | 39/220 | 124/220 | 30/130 | 9/90 | n/a | n/a | n/a | 17 | 3.4 | 2.0 | 0.2 | 0 |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking off (prompt 3.0) | 0/0 | 0/0 | 0/0 | 0/0 | n/a | n/a | n/a | 0 | 0.0 | 0.0 | 0.0 | 0 |

## Gate failures by type

| Candidate | did_not_search_on_search_question | fabricated_current_fact | malformed_tool_call | missing_required_tool | no_final_answer | searched_on_no_search_question | too_many_tool_calls |
|---|---|---|---|---|---|---|---|
| Qwen 3.8 27B, Q8_0, on llama-server, thinking medium (prompt 3.0) | 0 | 2 | 0 | 1 | 1 | 3 | 3 |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking low (prompt 3.0) | 1 | 1 | 0 | 1 | 1 | 3 | 3 |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking off (prompt 3.0) | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking medium (prompt 3.0) | 0 | 0 | 0 | 0 | 4 | 10 | 13 |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking low (prompt 3.0) | 0 | 1 | 1 | 0 | 2 | 11 | 11 |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking off (prompt 3.0) | 0 | 0 | 0 | 1 | 1 | 8 | 13 |

## Router

No routed results in this run.

## Logged, not scored (prototype machine, for projection only)

| Candidate | Median time to first token | Median total | Mean answer words | Questions searched | Prefill | Decode | Fully on GPU |
|---|---|---|---|---|---|---|---|
| Qwen 3.8 27B, Q8_0, on llama-server, thinking medium (prompt 3.0) | 3.1 s | 43.9 s | 491 | 10/22 | 637 tok/s | 33 tok/s | n/a |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking low (prompt 3.0) | 8.8 s | 48.1 s | 463 | 9/22 | 643 tok/s | 35 tok/s | n/a |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking off (prompt 3.0) | 0.3 s | 18.3 s | 341 | 0/13 | 332 tok/s | 32 tok/s | n/a |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking medium (prompt 3.0) | 2.0 s | 64.6 s | 505 | 17/22 | 885 tok/s | 53 tok/s | n/a |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking low (prompt 3.0) | 3.9 s | 59.3 s | 542 | 18/22 | 873 tok/s | 53 tok/s | n/a |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking off (prompt 3.0) | 0.3 s | 30.6 s | 392 | 15/22 | 871 tok/s | 52 tok/s | n/a |

## Per-question scores (G = gated to zero, - = not judged)

| Question | qwen3.8-27b-medium | qwen3.8-27b-low | qwen3.8-27b-off | qwen3.8-flash-next-medium | qwen3.8-flash-next-low | qwen3.8-flash-next-off |
|---|---|---|---|---|---|---|
| A76 | 7 | 7 | - | G (6) | G (6) | G (4) |
| A77 | 8 | 8 | - | 7 | 7 | 9 |
| A78 | 8 | 9 | - | G (4) | G (7) | 8 |
| A79 | G (7) | G (6) | - | G (4) | G (6) | G (3) |
| A80 | 8 | 5 | - | G (5) | G (4) | 8 |
| A81 | 8 | 7 | - | G (5) | G (6) | G (4) |
| A82 | 7 | 8 | - | G (3) | G (5) | 6 |
| A83 | 8 | 9 | - | 10 | 8 | G (8) |
| A84 | 9 | 8 | - | 8 | G (7) | G (5) |
| A85 | 7 | G (0) | - | G (0) | G (3) | G (3) |
| A86 | G (5) | G (6) | - | G (5) | G (7) | G (3) |
| A87 | 8 | 8 | - | G (4) | 5 | G (3) |
| A11 | 10 | 10 | - | 9 | 10 | 10 |
| B88 | 8 | G (5) | - | G (6) | G (8) | G (4) |
| B89 | G (5) | G (8) | - | G (0) | G (4) | G (4) |
| B90 | 7 | 8 | - | G (7) | G (6) | G (6) |
| B91 | G (6) | 6 | - | G (6) | G (6) | G (5) |
| B92 | G (5) | G (6) | - | G (8) | G (7) | G (1) |
| B93 | G (4) | G (3) | - | G (5) | G (3) | G (5) |
| B94 | G (0) | 6 | - | G (0) | G (0) | G (5) |
| B95 | 8 | G (3) | - | G (0) | G (0) | G (4) |
| B21 | 9 | 6 | - | 9 | 9 | 8 |
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
