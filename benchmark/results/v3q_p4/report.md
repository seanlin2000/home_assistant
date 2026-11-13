# LLM benchmark report, v3q_p4

Question set v3.0, 75 questions, 10 points each. Any gate failure zeroes a question. System prompt v3.0; question routing off.

## Scores

Total counts a gated question as zero; ungated total ignores the gates and sums the dimension scores, so the gap between them is what the gates cost.

| Candidate | Total | Ungated total | Category A | Category B | Category C | Category D | Category E | Gated questions | Quality /5 | Judgment /3 | Spoken /2 | Unjudged |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen 3.8 27B, Q8_0, on llama-server, thinking medium (prompt 3.0) | 113/220 | 147/220 | 86/130 | 27/90 | n/a | n/a | n/a | 7 | 3.5 | 2.5 | 0.7 | 0 |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking low (prompt 3.0) | 107/220 | 140/220 | 86/130 | 21/90 | n/a | n/a | n/a | 7 | 3.5 | 2.4 | 0.5 | 0 |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking medium (prompt 3.0) | 58/220 | 124/220 | 49/130 | 9/90 | n/a | n/a | n/a | 15 | 3.2 | 1.8 | 0.7 | 0 |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking off (prompt 3.0) | 55/220 | 119/220 | 48/130 | 7/90 | n/a | n/a | n/a | 15 | 2.9 | 2.0 | 0.5 | 0 |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking low (prompt 3.0) | 32/220 | 98/220 | 32/130 | 0/90 | n/a | n/a | n/a | 18 | 2.9 | 1.4 | 0.1 | 0 |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking off (prompt 3.0) | 0/0 | 0/0 | 0/0 | 0/0 | n/a | n/a | n/a | 0 | 0.0 | 0.0 | 0.0 | 0 |

## Gate failures by type

| Candidate | fabricated_current_fact | malformed_tool_call | missing_required_tool | no_final_answer | searched_on_no_search_question | too_many_tool_calls | violated_explicit_constraint |
|---|---|---|---|---|---|---|---|
| Qwen 3.8 27B, Q8_0, on llama-server, thinking medium (prompt 3.0) | 3 | 0 | 1 | 0 | 3 | 3 | 0 |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking low (prompt 3.0) | 4 | 0 | 3 | 0 | 3 | 5 | 0 |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking off (prompt 3.0) | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking medium (prompt 3.0) | 0 | 1 | 0 | 4 | 8 | 11 | 0 |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking low (prompt 3.0) | 3 | 0 | 0 | 4 | 9 | 12 | 0 |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking off (prompt 3.0) | 1 | 0 | 0 | 0 | 8 | 13 | 1 |

## Router

No routed results in this run.

## Logged, not scored (prototype machine, for projection only)

| Candidate | Median time to first token | Median total | Mean answer words | Questions searched | Prefill | Decode | Fully on GPU |
|---|---|---|---|---|---|---|---|
| Qwen 3.8 27B, Q8_0, on llama-server, thinking medium (prompt 3.0) | 5.2 s | 55.8 s | 479 | 10/22 | 639 tok/s | 32 tok/s | n/a |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking low (prompt 3.0) | 8.2 s | 60.4 s | 461 | 10/22 | 633 tok/s | 36 tok/s | n/a |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking off (prompt 3.0) | 0.3 s | 19.7 s | 382 | 1/13 | 517 tok/s | 31 tok/s | n/a |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking medium (prompt 3.0) | 2.0 s | 64.5 s | 477 | 15/22 | 888 tok/s | 53 tok/s | n/a |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking low (prompt 3.0) | 5.9 s | 61.7 s | 450 | 16/22 | 888 tok/s | 53 tok/s | n/a |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking off (prompt 3.0) | 0.3 s | 32.7 s | 411 | 15/22 | 868 tok/s | 52 tok/s | n/a |

## Per-question scores (G = gated to zero, - = not judged)

| Question | qwen3.8-27b-medium | qwen3.8-27b-low | qwen3.8-27b-off | qwen3.8-flash-next-medium | qwen3.8-flash-next-low | qwen3.8-flash-next-off |
|---|---|---|---|---|---|---|
| A76 | 6 | 5 | - | 8 | G (5) | G (3) |
| A77 | 8 | 8 | - | 8 | 7 | 8 |
| A78 | 9 | 9 | - | G (7) | G (3) | 8 |
| A79 | 8 | 7 | - | G (2) | G (5) | G (3) |
| A80 | 7 | 8 | - | G (6) | G (5) | 6 |
| A81 | 7 | 7 | - | G (6) | G (5) | G (4) |
| A82 | G (4) | 7 | - | 8 | 7 | G (3) |
| A83 | 10 | 9 | - | 6 | 8 | 9 |
| A84 | 8 | 8 | - | 9 | G (6) | 7 |
| A85 | 7 | 1 | - | G (0) | G (0) | G (4) |
| A86 | G (6) | G (5) | - | G (6) | G (5) | G (4) |
| A87 | 6 | 7 | - | G (5) | G (3) | G (3) |
| A11 | 10 | 10 | - | 10 | 10 | 10 |
| B88 | 7 | G (7) | - | G (9) | G (6) | G (4) |
| B89 | G (4) | G (4) | - | G (0) | G (0) | G (4) |
| B90 | G (8) | G (5) | - | G (7) | G (5) | G (6) |
| B91 | 8 | 8 | - | G (5) | G (4) | G (6) |
| B92 | G (5) | G (4) | - | G (8) | G (5) | G (8) |
| B93 | G (2) | G (4) | - | G (5) | G (3) | G (4) |
| B94 | 5 | G (4) | - | G (0) | G (0) | G (4) |
| B95 | G (5) | 4 | - | G (0) | G (0) | G (4) |
| B21 | 7 | 9 | - | 9 | G (6) | 7 |
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
