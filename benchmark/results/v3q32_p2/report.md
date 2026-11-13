# LLM benchmark report, v3q32_p2

Question set v3.0, 75 questions, 10 points each. Any gate failure zeroes a question. System prompt v3.2; question routing off.

## Scores

Total counts a gated question as zero; ungated total ignores the gates and sums the dimension scores, so the gap between them is what the gates cost.

| Candidate | Total | Ungated total | Category A | Category B | Category C | Category D | Category E | Gated questions | Quality /5 | Judgment /3 | Spoken /2 | Unjudged |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen 3.8 27B, Q8_0, on llama-server, thinking medium (prompt 3.2) | 146/220 | 168/220 | 104/130 | 42/90 | n/a | n/a | n/a | 4 | 3.4 | 2.5 | 1.8 | 0 |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking medium (prompt 3.2) | 138/220 | 171/220 | 92/130 | 46/90 | n/a | n/a | n/a | 5 | 3.9 | 2.5 | 1.5 | 0 |

## Gate failures by type

| Candidate | did_not_search_on_search_question | fabricated_current_fact | missing_required_tool | searched_on_no_search_question | too_many_tool_calls |
|---|---|---|---|---|---|
| Qwen 3.8 27B, Q8_0, on llama-server, thinking medium (prompt 3.2) | 1 | 3 | 1 | 1 | 0 |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking medium (prompt 3.2) | 0 | 0 | 1 | 3 | 1 |

## Router

No routed results in this run.

## Logged, not scored (prototype machine, for projection only)

| Candidate | Median time to first token | Median total | Mean answer words | Questions searched | Prefill | Decode | Fully on GPU |
|---|---|---|---|---|---|---|---|
| Qwen 3.8 27B, Q8_0, on llama-server, thinking medium (prompt 3.2) | 6.2 s | 19.4 s | 123 | 7/22 | 651 tok/s | 36 tok/s | n/a |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking medium (prompt 3.2) | 2.2 s | 14.1 s | 148 | 10/22 | 884 tok/s | 54 tok/s | n/a |

## Per-question scores (G = gated to zero, - = not judged)

| Question | qwen3.8-27b-medium | qwen3.8-flash-next-medium |
|---|---|---|
| A76 | 6 | 7 |
| A77 | 9 | 8 |
| A78 | 9 | G (6) |
| A79 | 8 | 8 |
| A80 | 9 | 10 |
| A81 | 8 | 9 |
| A82 | 8 | 9 |
| A83 | 9 | 10 |
| A84 | 9 | 9 |
| A85 | 8 | 5 |
| A86 | 6 | G (7) |
| A87 | 5 | 7 |
| A11 | 10 | 10 |
| B88 | 9 | 7 |
| B89 | 7 | G (8) |
| B90 | 9 | 7 |
| B91 | G (6) | 9 |
| B92 | G (6) | G (7) |
| B93 | G (5) | G (5) |
| B94 | 7 | 6 |
| B95 | G (5) | 7 |
| B21 | 10 | 10 |
| C23 | - | - |
| C24 | - | - |
| C25 | - | - |
| C26 | - | - |
| C27 | - | - |
| C28 | - | - |
| D29 | - | - |
| D30 | - | - |
| D31 | - | - |
| D32 | - | - |
| D33 | - | - |
| D34 | - | - |
| D35 | - | - |
| E36 | - | - |
| E37 | - | - |
| E38 | - | - |
| H39 | - | - |
| H40 | - | - |
| H41 | - | - |
| H42 | - | - |
| H43 | - | - |
| H44 | - | - |
| H45 | - | - |
| H46 | - | - |
| I47 | - | - |
| I48 | - | - |
| I49 | - | - |
| I50 | - | - |
| I51 | - | - |
| I52 | - | - |
| F53 | - | - |
| F54 | - | - |
| F55 | - | - |
| F56 | - | - |
| F57 | - | - |
| F58 | - | - |
| F59 | - | - |
| F60 | - | - |
| J61 | - | - |
| J62 | - | - |
| J63 | - | - |
| J64 | - | - |
| J65 | - | - |
| J66 | - | - |
| J67 | - | - |
| J68 | - | - |
| J69 | - | - |
| J70 | - | - |
| J71 | - | - |
| J72 | - | - |
| J73 | - | - |
| J74 | - | - |
| J75 | - | - |

## Judge agreement

Review sheet not yet filled in.

## Judge

Scores in this pass were produced by: claude-opus-5-5. Same rubric and output schema as every other pass, but each pass is graded in a separate session of the judge, so compare totals across passes with that in mind.
