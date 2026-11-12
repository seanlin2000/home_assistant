# LLM benchmark report, v3_ab

Question set v3.0, 75 questions, 10 points each. Any gate failure zeroes a question. System prompt v3.0; question routing off.

## Scores

Total counts a gated question as zero; ungated total ignores the gates and sums the dimension scores, so the gap between them is what the gates cost.

| Candidate | Total | Ungated total | Category A | Category B | Category C | Category D | Category E | Gated questions | Quality /5 | Judgment /3 | Spoken /2 | Unjudged |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Claude Opus 5.5, open-book hand-written pass by a fresh subagent (reference ceiling) | 212/220 | 212/220 | 126/130 | 86/90 | n/a | n/a | n/a | 0 | 4.6 | 3.0 | 2.0 | 0 |
| Claude Sonnet 5.5, open-book hand-written pass by a fresh subagent | 194/220 | 200/220 | 122/130 | 72/90 | n/a | n/a | n/a | 1 | 4.2 | 2.9 | 2.0 | 0 |
| Claude Opus 5.5, closed-book hand-written pass by a fresh subagent | 163/220 | 170/220 | 129/130 | 34/90 | n/a | n/a | n/a | 1 | 3.6 | 2.1 | 2.0 | 0 |
| Claude Sonnet 5.5, closed-book hand-written pass by a fresh subagent | 146/220 | 158/220 | 123/130 | 23/90 | n/a | n/a | n/a | 3 | 3.3 | 2.1 | 1.7 | 0 |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking medium (prompt 3.0) | 112/220 | 141/220 | 75/130 | 37/90 | n/a | n/a | n/a | 7 | 3.2 | 2.3 | 1.0 | 0 |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking low (prompt 3.0) | 108/220 | 126/220 | 78/130 | 30/90 | n/a | n/a | n/a | 7 | 3.0 | 2.2 | 0.5 | 0 |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking off (prompt 3.0) | 105/220 | 135/220 | 88/130 | 17/90 | n/a | n/a | n/a | 7 | 3.0 | 2.3 | 0.8 | 0 |

## Gate failures by type

| Candidate | did_not_search_on_search_question | fabricated_current_fact | malformed_tool_call | missing_required_tool | no_final_answer | searched_on_no_search_question | stayed_silent_on_real_request | too_many_tool_calls |
|---|---|---|---|---|---|---|---|---|
| Qwen 3.8 27B, Q8_0, on llama-server, thinking medium (prompt 3.0) | 0 | 2 | 0 | 1 | 0 | 5 | 0 | 1 |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking low (prompt 3.0) | 1 | 3 | 1 | 2 | 1 | 3 | 0 | 2 |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking off (prompt 3.0) | 2 | 3 | 0 | 0 | 0 | 1 | 1 | 3 |
| Claude Opus 5.5, open-book hand-written pass by a fresh subagent (reference ceiling) | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Claude Opus 5.5, closed-book hand-written pass by a fresh subagent | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Claude Sonnet 5.5, open-book hand-written pass by a fresh subagent | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Claude Sonnet 5.5, closed-book hand-written pass by a fresh subagent | 1 | 1 | 0 | 1 | 0 | 0 | 0 | 0 |

## Router

No routed results in this run.

## Logged, not scored (prototype machine, for projection only)

| Candidate | Median time to first token | Median total | Mean answer words | Questions searched | Prefill | Decode | Fully on GPU |
|---|---|---|---|---|---|---|---|
| Qwen 3.8 27B, Q8_0, on llama-server, thinking medium (prompt 3.0) | 4.1 s | 41.6 s | 456 | 12/22 | 560 tok/s | 20 tok/s | n/a |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking low (prompt 3.0) | 10.8 s | 49.7 s | 373 | 9/22 | 637 tok/s | 36 tok/s | n/a |
| Qwen 3.8 27B, Q8_0, on llama-server, thinking off (prompt 3.0) | 0.3 s | 19.9 s | 360 | 6/22 | 620 tok/s | 34 tok/s | n/a |
| Claude Opus 5.5, open-book hand-written pass by a fresh subagent (reference ceiling) | 0.0 s | 0.0 s | 164 | 7/22 | n/a | n/a | n/a |
| Claude Opus 5.5, closed-book hand-written pass by a fresh subagent | 0.0 s | 0.0 s | 156 | 6/22 | n/a | n/a | n/a |
| Claude Sonnet 5.5, open-book hand-written pass by a fresh subagent | 0.0 s | 0.0 s | 168 | 6/22 | n/a | n/a | n/a |
| Claude Sonnet 5.5, closed-book hand-written pass by a fresh subagent | 0.0 s | 0.0 s | 163 | 6/22 | n/a | n/a | n/a |

## Per-question scores (G = gated to zero, - = not judged)

| Question | qwen3.8-27b-medium | qwen3.8-27b-low | qwen3.8-27b-off | claude-opus-5-5-open | claude-opus-5-5-closed | claude-sonnet-5-5-open | claude-sonnet-5-5-closed |
|---|---|---|---|---|---|---|---|
| A76 | G (3) | G (4) | 7 | 9 | 10 | 9 | 9 |
| A77 | 8 | 8 | 8 | 10 | 10 | 10 | 10 |
| A78 | 9 | 8 | 8 | 10 | 10 | 9 | 10 |
| A79 | G (5) | 7 | 5 | 10 | 10 | 10 | 10 |
| A80 | 8 | 7 | 9 | 9 | 10 | 10 | 10 |
| A81 | 8 | 8 | 6 | 10 | 9 | 9 | 9 |
| A82 | 7 | G (4) | 7 | 9 | 10 | 9 | 9 |
| A83 | 10 | 9 | 6 | 10 | 10 | 10 | 10 |
| A84 | 8 | 7 | 7 | 10 | 10 | 10 | 10 |
| A85 | G (5) | G (0) | 5 | 10 | 10 | 8 | 8 |
| A86 | G (3) | 7 | 5 | 10 | 10 | 10 | 9 |
| A87 | 8 | 7 | 5 | 9 | 10 | 8 | 9 |
| A11 | 9 | 10 | 10 | 10 | 10 | 10 | 10 |
| B88 | 6 | 5 | 8 | 9 | 4 | 9 | 3 |
| B89 | 3 | G (2) | G (6) | 9 | 3 | 8 | 3 |
| B90 | 7 | 8 | G (7) | 10 | 3 | 10 | 2 |
| B91 | G (6) | 7 | G (4) | 9 | 5 | 9 | G (3) |
| B92 | G (3) | G (6) | G (6) | 10 | 3 | 9 | G (3) |
| B93 | G (4) | G (2) | G (4) | 10 | 3 | 9 | 2 |
| B94 | 6 | 1 | G (3) | 9 | 6 | 8 | 6 |
| B95 | 6 | G (0) | G (0) | 10 | G (7) | G (6) | G (6) |
| B21 | 9 | 9 | 9 | 10 | 7 | 10 | 7 |
| C23 | - | - | - | - | - | - | - |
| C24 | - | - | - | - | - | - | - |
| C25 | - | - | - | - | - | - | - |
| C26 | - | - | - | - | - | - | - |
| C27 | - | - | - | - | - | - | - |
| C28 | - | - | - | - | - | - | - |
| D29 | - | - | - | - | - | - | - |
| D30 | - | - | - | - | - | - | - |
| D31 | - | - | - | - | - | - | - |
| D32 | - | - | - | - | - | - | - |
| D33 | - | - | - | - | - | - | - |
| D34 | - | - | - | - | - | - | - |
| D35 | - | - | - | - | - | - | - |
| E36 | - | - | - | - | - | - | - |
| E37 | - | - | - | - | - | - | - |
| E38 | - | - | - | - | - | - | - |
| H39 | - | - | - | - | - | - | - |
| H40 | - | - | - | - | - | - | - |
| H41 | - | - | - | - | - | - | - |
| H42 | - | - | - | - | - | - | - |
| H43 | - | - | - | - | - | - | - |
| H44 | - | - | - | - | - | - | - |
| H45 | - | - | - | - | - | - | - |
| H46 | - | - | - | - | - | - | - |
| I47 | - | - | - | - | - | - | - |
| I48 | - | - | - | - | - | - | - |
| I49 | - | - | - | - | - | - | - |
| I50 | - | - | - | - | - | - | - |
| I51 | - | - | - | - | - | - | - |
| I52 | - | - | - | - | - | - | - |
| F53 | - | - | - | - | - | - | - |
| F54 | - | - | - | - | - | - | - |
| F55 | - | - | - | - | - | - | - |
| F56 | - | - | - | - | - | - | - |
| F57 | - | - | - | - | - | - | - |
| F58 | - | - | - | - | - | - | - |
| F59 | - | - | - | - | - | - | - |
| F60 | - | - | - | - | - | - | - |
| J61 | - | - | - | - | - | - | - |
| J62 | - | - | - | - | - | - | - |
| J63 | - | - | - | - | - | - | - |
| J64 | - | - | - | - | - | - | - |
| J65 | - | - | - | - | - | - | - |
| J66 | - | - | - | - | - | - | - |
| J67 | - | - | - | - | - | - | - |
| J68 | - | - | - | - | - | - | - |
| J69 | - | - | - | - | - | - | - |
| J70 | - | - | - | - | - | - | - |
| J71 | - | - | - | - | - | - | - |
| J72 | - | - | - | - | - | - | - |
| J73 | - | - | - | - | - | - | - |
| J74 | - | - | - | - | - | - | - |
| J75 | - | - | - | - | - | - | - |

## Judge agreement

Review sheet not yet filled in.

## Judge

Scores in this pass were produced by: claude-opus-5-5. Same rubric and output schema as every other pass, but each pass is graded in a separate session of the judge, so compare totals across passes with that in mind.
