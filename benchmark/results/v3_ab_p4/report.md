# LLM benchmark report, v3_ab_p4

Question set v3.0, 75 questions, 10 points each. Any gate failure zeroes a question.

## Scores

Total counts a gated question as zero; ungated total ignores the gates and sums the dimension scores, so the gap between them is what the gates cost.

| Candidate | Total | Ungated total | Category A | Category B | Category C | Category D | Category E | Gated questions | Quality /5 | Judgment /3 | Spoken /2 | Unjudged |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Claude Opus 5.5, open-book hand-written pass by a fresh subagent (reference ceiling) | 214/220 | 214/220 | 129/130 | 85/90 | n/a | n/a | n/a | 0 | 4.7 | 3.0 | 2.0 | 0 |
| Claude Sonnet 5.5, open-book hand-written pass by a fresh subagent | 197/220 | 203/220 | 125/130 | 72/90 | n/a | n/a | n/a | 1 | 4.4 | 2.9 | 2.0 | 0 |
| Claude Sonnet 5.5, closed-book hand-written pass by a fresh subagent | 153/220 | 162/220 | 124/130 | 29/90 | n/a | n/a | n/a | 2 | 3.4 | 2.2 | 1.7 | 0 |
| Claude Opus 5.5, closed-book hand-written pass by a fresh subagent | 150/220 | 161/220 | 121/130 | 29/90 | n/a | n/a | n/a | 2 | 3.4 | 2.2 | 1.7 | 0 |

## Gate failures by type

| Candidate | did_not_search_on_search_question | fabricated_current_fact | missing_required_tool |
|---|---|---|---|
| Claude Opus 5.5, open-book hand-written pass by a fresh subagent (reference ceiling) | 0 | 0 | 0 |
| Claude Opus 5.5, closed-book hand-written pass by a fresh subagent | 1 | 1 | 0 |
| Claude Sonnet 5.5, open-book hand-written pass by a fresh subagent | 1 | 0 | 0 |
| Claude Sonnet 5.5, closed-book hand-written pass by a fresh subagent | 1 | 0 | 1 |

## Router

No routed results in this run.

## Logged, not scored (prototype machine, for projection only)

| Candidate | Median time to first token | Median total | Mean answer words | Questions searched | Prefill | Decode | Fully on GPU |
|---|---|---|---|---|---|---|---|
| Claude Opus 5.5, open-book hand-written pass by a fresh subagent (reference ceiling) | 0.0 s | 0.0 s | 161 | 7/22 | n/a | n/a | n/a |
| Claude Opus 5.5, closed-book hand-written pass by a fresh subagent | 0.0 s | 0.0 s | 158 | 6/22 | n/a | n/a | n/a |
| Claude Sonnet 5.5, open-book hand-written pass by a fresh subagent | 0.0 s | 0.0 s | 172 | 6/22 | n/a | n/a | n/a |
| Claude Sonnet 5.5, closed-book hand-written pass by a fresh subagent | 0.0 s | 0.0 s | 153 | 6/22 | n/a | n/a | n/a |

## Per-question scores (G = gated to zero, - = not judged)

| Question | claude-opus-5-5-open | claude-opus-5-5-closed | claude-sonnet-5-5-open | claude-sonnet-5-5-closed |
|---|---|---|---|---|
| A76 | 10 | 9 | 9 | 9 |
| A77 | 10 | 10 | 10 | 10 |
| A78 | 10 | 10 | 10 | 10 |
| A79 | 10 | 10 | 10 | 9 |
| A80 | 10 | 10 | 10 | 10 |
| A81 | 10 | 10 | 9 | 10 |
| A82 | 9 | 9 | 9 | 10 |
| A83 | 10 | 4 | 10 | 9 |
| A84 | 10 | 10 | 10 | 10 |
| A85 | 10 | 10 | 10 | 8 |
| A86 | 10 | 10 | 9 | 10 |
| A87 | 10 | 9 | 9 | 9 |
| A11 | 10 | 10 | 10 | 10 |
| B88 | 9 | 3 | 9 | 3 |
| B89 | 9 | 3 | 8 | 3 |
| B90 | 10 | 2 | 9 | 3 |
| B91 | 9 | G (4) | 9 | 4 |
| B92 | 10 | 5 | 9 | G (3) |
| B93 | 10 | 2 | 10 | 2 |
| B94 | 9 | 7 | 8 | 7 |
| B95 | 9 | G (7) | G (6) | G (6) |
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
