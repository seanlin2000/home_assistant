# LLM benchmark report, v3_ab_p3

Question set v3.0, 75 questions, 10 points each. Any gate failure zeroes a question.

## Scores

Total counts a gated question as zero; ungated total ignores the gates and sums the dimension scores, so the gap between them is what the gates cost.

| Candidate | Total | Ungated total | Category A | Category B | Category C | Category D | Category E | Gated questions | Quality /5 | Judgment /3 | Spoken /2 | Unjudged |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Claude Opus 5.5, open-book hand-written pass by a fresh subagent (reference ceiling) | 191/220 | 205/220 | 124/130 | 67/90 | n/a | n/a | n/a | 2 | 4.5 | 2.9 | 2.0 | 0 |
| Claude Sonnet 5.5, open-book hand-written pass by a fresh subagent | 185/220 | 191/220 | 118/130 | 67/90 | n/a | n/a | n/a | 1 | 4.0 | 2.8 | 1.9 | 0 |
| Claude Opus 5.5, closed-book hand-written pass by a fresh subagent | 164/220 | 164/220 | 123/130 | 41/90 | n/a | n/a | n/a | 0 | 3.5 | 2.2 | 1.8 | 0 |
| Claude Sonnet 5.5, closed-book hand-written pass by a fresh subagent | 158/220 | 164/220 | 126/130 | 32/90 | n/a | n/a | n/a | 1 | 3.5 | 2.3 | 1.7 | 0 |

## Gate failures by type

| Candidate | did_not_search_on_search_question | fabricated_current_fact |
|---|---|---|
| Claude Opus 5.5, open-book hand-written pass by a fresh subagent (reference ceiling) | 1 | 1 |
| Claude Opus 5.5, closed-book hand-written pass by a fresh subagent | 0 | 0 |
| Claude Sonnet 5.5, open-book hand-written pass by a fresh subagent | 1 | 1 |
| Claude Sonnet 5.5, closed-book hand-written pass by a fresh subagent | 1 | 0 |

## Router

No routed results in this run.

## Logged, not scored (prototype machine, for projection only)

| Candidate | Median time to first token | Median total | Mean answer words | Questions searched | Prefill | Decode | Fully on GPU |
|---|---|---|---|---|---|---|---|
| Claude Opus 5.5, open-book hand-written pass by a fresh subagent (reference ceiling) | 0.0 s | 0.0 s | 166 | 6/22 | n/a | n/a | n/a |
| Claude Opus 5.5, closed-book hand-written pass by a fresh subagent | 0.0 s | 0.0 s | 164 | 7/22 | n/a | n/a | n/a |
| Claude Sonnet 5.5, open-book hand-written pass by a fresh subagent | 0.0 s | 0.0 s | 156 | 6/22 | n/a | n/a | n/a |
| Claude Sonnet 5.5, closed-book hand-written pass by a fresh subagent | 0.0 s | 0.0 s | 174 | 6/22 | n/a | n/a | n/a |

## Per-question scores (G = gated to zero, - = not judged)

| Question | claude-opus-5-5-open | claude-opus-5-5-closed | claude-sonnet-5-5-open | claude-sonnet-5-5-closed |
|---|---|---|---|---|
| A76 | 9 | 9 | 9 | 9 |
| A77 | 10 | 10 | 9 | 10 |
| A78 | 10 | 10 | 10 | 9 |
| A79 | 10 | 10 | 10 | 10 |
| A80 | 9 | 10 | 10 | 10 |
| A81 | 10 | 10 | 7 | 10 |
| A82 | 9 | 10 | 9 | 10 |
| A83 | 10 | 4 | 8 | 10 |
| A84 | 10 | 10 | 10 | 10 |
| A85 | 10 | 10 | 8 | 9 |
| A86 | 10 | 10 | 9 | 10 |
| A87 | 7 | 10 | 9 | 9 |
| A11 | 10 | 10 | 10 | 10 |
| B88 | 9 | 3 | 8 | 3 |
| B89 | 10 | 3 | 9 | 3 |
| B90 | 10 | 2 | 9 | 3 |
| B91 | G (7) | 5 | 9 | 3 |
| B92 | 9 | 4 | 6 | 4 |
| B93 | 10 | 3 | 10 | 2 |
| B94 | 9 | 7 | 7 | 7 |
| B95 | G (7) | 7 | G (6) | G (6) |
| B21 | 10 | 7 | 9 | 7 |
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
