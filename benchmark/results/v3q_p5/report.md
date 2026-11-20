# LLM benchmark report, v3q_p5

Question set v3.0, 75 questions, 10 points each. Any gate failure zeroes a question. System prompt v3.0; question routing off.

## Scores

Total counts a gated question as zero; ungated total ignores the gates and sums the dimension scores, so the gap between them is what the gates cost.

| Candidate | Total | Ungated total | Category A | Category B | Category C | Category D | Category E | Gated questions | Quality /5 | Judgment /3 | Spoken /2 | Unjudged |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen 3.8 27B, Q8_0, on llama-server, thinking low (prompt 3.0) | 101/220 | 132/220 | 81/130 | 20/90 | n/a | n/a | n/a | 8 | 3.3 | 2.2 | 0.5 | 0 |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking medium (prompt 3.0) | 86/220 | 151/220 | 71/130 | 15/90 | n/a | n/a | n/a | 11 | 3.7 | 2.5 | 0.7 | 0 |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking off (prompt 3.0) | 46/220 | 120/220 | 37/130 | 9/90 | n/a | n/a | n/a | 16 | 3.2 | 2.0 | 0.3 | 0 |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking medium (prompt 3.0) | 43/220 | 112/220 | 34/130 | 9/90 | n/a | n/a | n/a | 17 | 3.4 | 1.5 | 0.2 | 0 |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking low (prompt 3.0) | 40/220 | 114/220 | 32/130 | 8/90 | n/a | n/a | n/a | 17 | 2.9 | 1.9 | 0.4 | 0 |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking off (prompt 3.0) | 0/0 | 0/0 | 0/0 | 0/0 | n/a | n/a | n/a | 0 | 0.0 | 0.0 | 0.0 | 0 |

## Gate failures by type

| Candidate | did_not_search_on_search_question | fabricated_current_fact | malformed_tool_call | missing_required_tool | no_final_answer | searched_on_no_search_question | too_many_tool_calls |
|---|---|---|---|---|---|---|---|
| Qwen 3.8 27B, Q8_0, on llama-server, thinking medium (prompt 3.0) | 1 | 1 | 1 | 0 | 1 | 3 | 6 |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking low (prompt 3.0) | 1 | 1 | 0 | 1 | 1 | 3 | 3 |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking off (prompt 3.0) | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking medium (prompt 3.0) | 0 | 2 | 0 | 0 | 4 | 11 | 11 |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking low (prompt 3.0) | 0 | 3 | 0 | 0 | 2 | 8 | 12 |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking off (prompt 3.0) | 0 | 0 | 0 | 0 | 0 | 8 | 15 |

## Router

No routed results in this run.

## Logged, not scored (prototype machine, for projection only)

| Candidate | Median time to first token | Median total | Mean answer words | Questions searched | Prefill | Decode | Fully on GPU |
|---|---|---|---|---|---|---|---|
| Qwen 3.8 27B, Q8_0, on llama-server, thinking medium (prompt 3.0) | 4.0 s | 49.4 s | 482 | 9/22 | 640 tok/s | 33 tok/s | n/a |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking low (prompt 3.0) | 9.4 s | 53.5 s | 406 | 9/22 | 641 tok/s | 36 tok/s | n/a |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking off (prompt 3.0) | 0.3 s | 17.1 s | 348 | 2/10 | 613 tok/s | 31 tok/s | n/a |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking medium (prompt 3.0) | 3.8 s | 63.1 s | 518 | 18/22 | 886 tok/s | 53 tok/s | n/a |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking low (prompt 3.0) | 3.4 s | 78.4 s | 504 | 15/22 | 891 tok/s | 53 tok/s | n/a |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking off (prompt 3.0) | 0.3 s | 31.6 s | 408 | 15/22 | 857 tok/s | 52 tok/s | n/a |

## Per-question scores (G = gated to zero, - = not judged)

| Question | qwen3.8-27b-medium | qwen3.8-27b-low | qwen3.8-27b-off | qwen3.8-flash-next-medium | qwen3.8-flash-next-low | qwen3.8-flash-next-off |
|---|---|---|---|---|---|---|
| A76 | 6 | 6 | - | G (6) | G (3) | G (4) |
| A77 | 9 | 9 | - | 8 | 9 | 8 |
| A78 | 8 | 8 | - | G (5) | G (5) | 7 |
| A79 | G (6) | G (6) | - | G (5) | G (4) | G (3) |
| A80 | 5 | 5 | - | G (6) | G (6) | 7 |
| A81 | G (6) | 7 | - | G (5) | G (5) | G (4) |
| A82 | 7 | 5 | - | G (6) | G (4) | G (4) |
| A83 | 10 | 8 | - | 9 | 7 | G (8) |
| A84 | 9 | 9 | - | 7 | G (8) | G (4) |
| A85 | G (8) | 8 | - | G (0) | G (0) | G (4) |
| A86 | G (5) | G (6) | - | G (6) | G (5) | G (5) |
| A87 | 7 | 6 | - | G (4) | 6 | 5 |
| A11 | 10 | 10 | - | 10 | 10 | 10 |
| B88 | G (6) | 4 | - | G (5) | G (6) | G (4) |
| B89 | G (7) | G (4) | - | G (0) | G (3) | G (4) |
| B90 | G (9) | G (7) | - | G (3) | G (7) | G (6) |
| B91 | 7 | 8 | - | G (5) | G (6) | G (5) |
| B92 | G (6) | G (5) | - | G (8) | G (6) | G (8) |
| B93 | G (8) | G (3) | - | G (5) | G (2) | G (4) |
| B94 | G (0) | G (0) | - | G (0) | G (0) | G (3) |
| B95 | G (4) | G (0) | - | G (0) | G (4) | G (4) |
| B21 | 8 | 8 | - | 9 | 8 | 9 |
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
