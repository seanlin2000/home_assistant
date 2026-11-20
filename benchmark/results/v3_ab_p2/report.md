# LLM benchmark report, v3_ab_p2

Question set v3.0, 75 questions, 10 points each. Any gate failure zeroes a question.

## Scores

Total counts a gated question as zero; ungated total ignores the gates and sums the dimension scores, so the gap between them is what the gates cost.

| Candidate | Total | Ungated total | Category A | Category B | Category C | Category D | Category E | Gated questions | Quality /5 | Judgment /3 | Spoken /2 | Unjudged |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Claude Opus 5.5, open-book hand-written pass by a fresh subagent (reference ceiling) | 211/220 | 211/220 | 124/130 | 87/90 | n/a | n/a | n/a | 0 | 4.6 | 3.0 | 2.0 | 0 |
| Claude Sonnet 5.5, open-book hand-written pass by a fresh subagent | 195/220 | 201/220 | 121/130 | 74/90 | n/a | n/a | n/a | 1 | 4.2 | 2.9 | 2.0 | 0 |
| Claude Opus 5.5, closed-book hand-written pass by a fresh subagent | 160/220 | 164/220 | 126/130 | 34/90 | n/a | n/a | n/a | 2 | 3.5 | 2.2 | 1.7 | 0 |
| Claude Sonnet 5.5, closed-book hand-written pass by a fresh subagent | 157/220 | 157/220 | 124/130 | 33/90 | n/a | n/a | n/a | 0 | 3.3 | 2.2 | 1.7 | 0 |

## Gate failures by type

| Candidate | did_not_search_on_search_question | fabricated_current_fact | searched_on_no_search_question |
|---|---|---|---|
| Claude Opus 5.5, open-book hand-written pass by a fresh subagent (reference ceiling) | 0 | 0 | 0 |
| Claude Opus 5.5, closed-book hand-written pass by a fresh subagent | 0 | 2 | 1 |
| Claude Sonnet 5.5, open-book hand-written pass by a fresh subagent | 1 | 0 | 0 |
| Claude Sonnet 5.5, closed-book hand-written pass by a fresh subagent | 0 | 0 | 0 |

## Router

No routed results in this run.

## Logged, not scored (prototype machine, for projection only)

| Candidate | Median time to first token | Median total | Mean answer words | Questions searched | Prefill | Decode | Fully on GPU |
|---|---|---|---|---|---|---|---|
| Claude Opus 5.5, open-book hand-written pass by a fresh subagent (reference ceiling) | 0.0 s | 0.0 s | 157 | 7/22 | n/a | n/a | n/a |
| Claude Opus 5.5, closed-book hand-written pass by a fresh subagent | 0.0 s | 0.0 s | 172 | 8/22 | n/a | n/a | n/a |
| Claude Sonnet 5.5, open-book hand-written pass by a fresh subagent | 0.0 s | 0.0 s | 166 | 6/22 | n/a | n/a | n/a |
| Claude Sonnet 5.5, closed-book hand-written pass by a fresh subagent | 0.0 s | 0.0 s | 165 | 7/22 | n/a | n/a | n/a |

## Per-question scores (G = gated to zero, - = not judged)

| Question | claude-opus-5-5-open | claude-opus-5-5-closed | claude-sonnet-5-5-open | claude-sonnet-5-5-closed |
|---|---|---|---|---|
| A76 | 10 | 9 | 9 | 9 |
| A77 | 9 | 10 | 9 | 10 |
| A78 | 10 | 10 | 10 | 10 |
| A79 | 9 | 10 | 9 | 10 |
| A80 | 9 | 9 | 10 | 9 |
| A81 | 10 | 10 | 10 | 9 |
| A82 | 9 | 9 | 9 | 9 |
| A83 | 10 | 10 | 9 | 10 |
| A84 | 10 | 10 | 10 | 10 |
| A85 | 10 | 10 | 8 | 9 |
| A86 | 9 | 10 | 9 | 10 |
| A87 | 9 | 9 | 9 | 9 |
| A11 | 10 | 10 | 10 | 10 |
| B88 | 10 | 3 | 9 | 3 |
| B89 | 9 | 3 | 9 | 3 |
| B90 | 10 | G (2) | 10 | 2 |
| B91 | 9 | 3 | 9 | 3 |
| B92 | 10 | 3 | 10 | 3 |
| B93 | 10 | G (2) | 9 | 1 |
| B94 | 9 | 7 | 8 | 5 |
| B95 | 10 | 8 | G (6) | 7 |
| B21 | 10 | 7 | 10 | 6 |
| C23 | - | - | - | - |
| C24 | - | - | - | - |
| C25 | - | - | - | - |
| C26 | - | - | - | - |
| C27 | - | - | - | - |
| C28 | - | - | - | - |
| D29 | - | - | - | - |
| D30 | - | - | - | - |
| D31 | - | - | - | - |
| D32 | - | - | - | - |
| D33 | - | - | - | - |
| D34 | - | - | - | - |
| D35 | - | - | - | - |
| E36 | - | - | - | - |
| E37 | - | - | - | - |
| E38 | - | - | - | - |
| H39 | - | - | - | - |
| H40 | - | - | - | - |
| H41 | - | - | - | - |
| H42 | - | - | - | - |
| H43 | - | - | - | - |
| H44 | - | - | - | - |
| H45 | - | - | - | - |
| H46 | - | - | - | - |
| I47 | - | - | - | - |
| I48 | - | - | - | - |
| I49 | - | - | - | - |
| I50 | - | - | - | - |
| I51 | - | - | - | - |
| I52 | - | - | - | - |
| F53 | - | - | - | - |
| F54 | - | - | - | - |
| F55 | - | - | - | - |
| F56 | - | - | - | - |
| F57 | - | - | - | - |
| F58 | - | - | - | - |
| F59 | - | - | - | - |
| F60 | - | - | - | - |
| J61 | - | - | - | - |
| J62 | - | - | - | - |
| J63 | - | - | - | - |
| J64 | - | - | - | - |
| J65 | - | - | - | - |
| J66 | - | - | - | - |
| J67 | - | - | - | - |
| J68 | - | - | - | - |
| J69 | - | - | - | - |
| J70 | - | - | - | - |
| J71 | - | - | - | - |
| J72 | - | - | - | - |
| J73 | - | - | - | - |
| J74 | - | - | - | - |
| J75 | - | - | - | - |

## Judge agreement

Review sheet not yet filled in.

## Judge

Scores in this pass were produced by: claude-opus-5-5. Same rubric and output schema as every other pass, but each pass is graded in a separate session of the judge, so compare totals across passes with that in mind.
