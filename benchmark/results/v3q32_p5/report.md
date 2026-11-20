# LLM benchmark report, v3q32_p5

Question set v3.0, 75 questions, 10 points each. Any gate failure zeroes a question. System prompt v3.2; question routing off.

## Scores

Total counts a gated question as zero; ungated total ignores the gates and sums the dimension scores, so the gap between them is what the gates cost.

| Candidate | Total | Ungated total | Category A | Category B | Category C | Category D | Category E | Gated questions | Quality /5 | Judgment /3 | Spoken /2 | Unjudged |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen 3.8 27B, Q8_0, on llama-server, thinking medium (prompt 3.2) | 155/220 | 172/220 | 107/130 | 48/90 | n/a | n/a | n/a | 3 | 3.6 | 2.5 | 1.7 | 0 |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking medium (prompt 3.2) | 138/220 | 173/220 | 94/130 | 44/90 | n/a | n/a | n/a | 6 | 3.9 | 2.6 | 1.4 | 0 |

## Gate failures by type

| Candidate | did_not_search_on_search_question | fabricated_current_fact | missing_required_tool | searched_on_no_search_question | too_many_tool_calls |
|---|---|---|---|---|---|
| Qwen 3.8 27B, Q8_0, on llama-server, thinking medium (prompt 3.2) | 1 | 1 | 1 | 1 | 1 |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking medium (prompt 3.2) | 1 | 2 | 0 | 3 | 1 |

## Router

No routed results in this run.

## Logged, not scored (prototype machine, for projection only)

| Candidate | Median time to first token | Median total | Mean answer words | Questions searched | Prefill | Decode | Fully on GPU |
|---|---|---|---|---|---|---|---|
| Qwen 3.8 27B, Q8_0, on llama-server, thinking medium (prompt 3.2) | 4.5 s | 14.8 s | 120 | 7/22 | 648 tok/s | 37 tok/s | n/a |
| Qwen 3.8 Flash Next, GSQ-RCO IQ3_XXS (n-gram table on disk), on llama-server, thinking medium (prompt 3.2) | 2.0 s | 11.4 s | 145 | 9/22 | 876 tok/s | 54 tok/s | n/a |

## Per-question scores (G = gated to zero, - = not judged)

| Question | qwen3.8-27b-medium | qwen3.8-flash-next-medium |
|---|---|---|
| A76 | 8 | 8 |
| A77 | 9 | 9 |
| A78 | 9 | G (6) |
| A79 | 7 | 8 |
| A80 | 9 | 8 |
| A81 | 9 | 8 |
| A82 | 8 | 8 |
| A83 | 7 | 9 |
| A84 | 10 | 10 |
| A85 | 4 | 8 |
| A86 | 9 | G (6) |
| A87 | 8 | 8 |
| A11 | 10 | 10 |
| B88 | 7 | 8 |
| B89 | 8 | 8 |
| B90 | 10 | 9 |
| B91 | 9 | 9 |
| B92 | G (6) | G (9) |
| B93 | G (5) | G (5) |
| B94 | 6 | G (5) |
| B95 | G (6) | G (4) |
| B21 | 8 | 10 |
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
