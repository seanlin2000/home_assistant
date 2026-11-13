# LLM benchmark report, v3_ab_p5

Question set v3.0, 75 questions, 10 points each. Any gate failure zeroes a question.

## Scores

Total counts a gated question as zero; ungated total ignores the gates and sums the dimension scores, so the gap between them is what the gates cost.

| Candidate | Total | Ungated total | Category A | Category B | Category C | Category D | Category E | Gated questions | Quality /5 | Judgment /3 | Spoken /2 | Unjudged |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Claude Opus 5.5, open-book hand-written pass by a fresh subagent (reference ceiling) | 213/220 | 213/220 | 126/130 | 87/90 | n/a | n/a | n/a | 0 | 4.7 | 3.0 | 2.0 | 0 |
| Claude Sonnet 5.5, open-book hand-written pass by a fresh subagent | 195/220 | 202/220 | 123/130 | 72/90 | n/a | n/a | n/a | 1 | 4.3 | 2.9 | 2.0 | 0 |
| Claude Opus 5.5, closed-book hand-written pass by a fresh subagent | 158/220 | 158/220 | 120/130 | 38/90 | n/a | n/a | n/a | 0 | 3.4 | 2.1 | 1.7 | 0 |
| Claude Sonnet 5.5, closed-book hand-written pass by a fresh subagent | 144/220 | 150/220 | 120/130 | 24/90 | n/a | n/a | n/a | 1 | 3.2 | 2.0 | 1.6 | 0 |

## Gate failures by type

| Candidate | did_not_search_on_search_question |
|---|---|
| Claude Opus 5.5, open-book hand-written pass by a fresh subagent (reference ceiling) | 0 |
| Claude Opus 5.5, closed-book hand-written pass by a fresh subagent | 0 |
| Claude Sonnet 5.5, open-book hand-written pass by a fresh subagent | 1 |
| Claude Sonnet 5.5, closed-book hand-written pass by a fresh subagent | 1 |

## Router

No routed results in this run.

## Logged, not scored (prototype machine, for projection only)

| Candidate | Median time to first token | Median total | Mean answer words | Questions searched | Prefill | Decode | Fully on GPU |
|---|---|---|---|---|---|---|---|
| Claude Opus 5.5, open-book hand-written pass by a fresh subagent (reference ceiling) | 0.0 s | 0.0 s | 164 | 7/22 | n/a | n/a | n/a |
| Claude Opus 5.5, closed-book hand-written pass by a fresh subagent | 0.0 s | 0.0 s | 157 | 7/22 | n/a | n/a | n/a |
| Claude Sonnet 5.5, open-book hand-written pass by a fresh subagent | 0.0 s | 0.0 s | 155 | 6/22 | n/a | n/a | n/a |
| Claude Sonnet 5.5, closed-book hand-written pass by a fresh subagent | 0.0 s | 0.0 s | 170 | 6/22 | n/a | n/a | n/a |

## Per-question scores (G = gated to zero, - = not judged)

| Question | claude-opus-5-5-open | claude-opus-5-5-closed | claude-sonnet-5-5-open | claude-sonnet-5-5-closed |
|---|---|---|---|---|
| A76 | 9 | 9 | 9 | 9 |
| A77 | 10 | 10 | 9 | 10 |
| A78 | 10 | 10 | 9 | 9 |
| A79 | 10 | 10 | 10 | 10 |
| A80 | 10 | 10 | 10 | 10 |
| A81 | 10 | 10 | 9 | 9 |
| A82 | 9 | 9 | 9 | 9 |
| A83 | 10 | 3 | 10 | 8 |
| A84 | 10 | 10 | 10 | 10 |
| A85 | 10 | 10 | 9 | 7 |
| A86 | 9 | 9 | 10 | 10 |
| A87 | 9 | 10 | 9 | 9 |
| A11 | 10 | 10 | 10 | 10 |
| B88 | 9 | 3 | 7 | 2 |
| B89 | 10 | 3 | 9 | 2 |
| B90 | 10 | 2 | 9 | 2 |
| B91 | 10 | 4 | 9 | 3 |
| B92 | 10 | 4 | 9 | 2 |
| B93 | 10 | 2 | 10 | 1 |
| B94 | 9 | 5 | 9 | 5 |
| B95 | 9 | 8 | G (7) | G (6) |
| B21 | 10 | 7 | 10 | 7 |
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
