# LLM benchmark report, v3q_p1

Question set v3.0, 75 questions, 10 points each. Any gate failure zeroes a question. System prompt v3.0; question routing off.

## Scores

Total counts a gated question as zero; ungated total ignores the gates and sums the dimension scores, so the gap between them is what the gates cost.

| Candidate | Total | Ungated total | Category A | Category B | Category C | Category D | Category E | Gated questions | Quality /5 | Judgment /3 | Spoken /2 | Unjudged |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen 3.8 27B, Q8_0, on llama-server, thinking low (prompt 3.0) | 115/220 | 141/220 | 90/130 | 25/90 | n/a | n/a | n/a | 7 | 3.3 | 2.5 | 0.7 | 0 |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking medium (prompt 3.0) | 102/220 | 152/220 | 85/130 | 17/90 | n/a | n/a | n/a | 8 | 3.4 | 2.5 | 1.0 | 0 |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking off (prompt 3.0) | 47/220 | 109/220 | 39/130 | 8/90 | n/a | n/a | n/a | 16 | 2.8 | 1.8 | 0.4 | 0 |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking medium (prompt 3.0) | 44/220 | 129/220 | 35/130 | 9/90 | n/a | n/a | n/a | 17 | 3.7 | 1.9 | 0.3 | 0 |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking low (prompt 3.0) | 41/220 | 114/220 | 32/130 | 9/90 | n/a | n/a | n/a | 17 | 3.3 | 1.6 | 0.2 | 0 |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking off (prompt 3.0) | 0/0 | 0/0 | 0/0 | 0/0 | n/a | n/a | n/a | 0 | 0.0 | 0.0 | 0.0 | 0 |

## Gate failures by type

| Candidate | fabricated_current_fact | missing_required_tool | no_final_answer | searched_on_no_search_question | too_many_tool_calls |
|---|---|---|---|---|---|
| Qwen 3.8 27B, Q8_0, on llama-server, thinking medium (prompt 3.0) | 4 | 2 | 0 | 3 | 5 |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking low (prompt 3.0) | 3 | 0 | 1 | 2 | 3 |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking off (prompt 3.0) | 0 | 0 | 0 | 0 | 0 |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking medium (prompt 3.0) | 1 | 0 | 3 | 8 | 13 |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking low (prompt 3.0) | 1 | 0 | 3 | 9 | 11 |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking off (prompt 3.0) | 0 | 0 | 0 | 9 | 14 |

## Router

No routed results in this run.

## Logged, not scored (prototype machine, for projection only)

| Candidate | Median time to first token | Median total | Mean answer words | Questions searched | Prefill | Decode | Fully on GPU |
|---|---|---|---|---|---|---|---|
| Qwen 3.8 27B, Q8_0, on llama-server, thinking medium (prompt 3.0) | 4.1 s | 54.9 s | 446 | 10/22 | 641 tok/s | 33 tok/s | n/a |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking low (prompt 3.0) | 8.9 s | 61.6 s | 453 | 9/22 | 639 tok/s | 35 tok/s | n/a |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking off (prompt 3.0) | 0.3 s | 21.0 s | 360 | 8/22 | 622 tok/s | 34 tok/s | n/a |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking medium (prompt 3.0) | 2.5 s | 78.3 s | 531 | 15/22 | 874 tok/s | 53 tok/s | n/a |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking low (prompt 3.0) | 3.6 s | 65.4 s | 470 | 16/22 | 882 tok/s | 53 tok/s | n/a |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking off (prompt 3.0) | 0.3 s | 37.9 s | 405 | 16/22 | 872 tok/s | 52 tok/s | n/a |

## Per-question scores (G = gated to zero, - = not judged)

| Question | qwen3.8-27b-medium | qwen3.8-27b-low | qwen3.8-27b-off | qwen3.8-flash-next-medium | qwen3.8-flash-next-low | qwen3.8-flash-next-off |
|---|---|---|---|---|---|---|
| A76 | 7 | 6 | - | G (6) | G (6) | G (3) |
| A77 | 7 | 8 | - | 9 | 7 | 9 |
| A78 | 8 | 9 | - | G (6) | G (6) | 5 |
| A79 | 9 | 7 | - | G (5) | G (6) | G (3) |
| A80 | 7 | 7 | - | G (5) | G (5) | 5 |
| A81 | 8 | 6 | - | G (5) | G (6) | G (3) |
| A82 | 7 | 6 | - | G (6) | 6 | G (3) |
| A83 | 6 | 10 | - | 10 | 9 | 10 |
| A84 | G (6) | 9 | - | G (8) | G (4) | G (5) |
| A85 | 8 | 5 | - | G (0) | G (0) | G (3) |
| A86 | G (7) | G (3) | - | G (5) | G (5) | G (3) |
| A87 | 8 | 7 | - | 6 | G (3) | G (3) |
| A11 | 10 | 10 | - | 10 | 10 | 10 |
| B88 | G (6) | 7 | - | G (7) | G (7) | G (4) |
| B89 | G (8) | G (4) | - | G (0) | G (0) | G (4) |
| B90 | G (8) | 8 | - | G (8) | G (5) | G (5) |
| B91 | G (5) | G (0) | - | G (7) | G (7) | G (5) |
| B92 | G (5) | G (7) | - | G (7) | G (7) | G (7) |
| B93 | G (5) | G (4) | - | G (6) | G (5) | G (3) |
| B94 | 2 | G (5) | - | G (0) | G (0) | G (4) |
| B95 | 7 | G (3) | - | G (4) | G (1) | G (4) |
| B21 | 8 | 10 | - | 9 | 9 | 8 |
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
