# LLM benchmark report, 2026-09-06

Question set v1.2, 28 questions, 10 points each. Any gate failure zeroes a question. System prompt v1.2; question routing on.

## Scores

Total counts a gated question as zero; ungated total ignores the gates and sums the dimension scores, so the gap between them is what the gates cost.

| Candidate | Total | Ungated total | Category A | Category B | Category C | vs baseline | Gated questions | Quality /5 | Judgment /3 | Spoken /2 | Unjudged |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Claude Fable 5.1, answered by hand in the coding session (reference ceiling) | 226/280 | 249/280 | 110/110 | 56/110 | 60/60 | n/a | 4 | 4.2 | 2.6 | 2.0 | 0 |
| Gemma 4 E4B, QAT int4 | 174/280 | 188/280 | 74/110 | 58/110 | 42/60 | n/a | 5 | 3.0 | 2.0 | 1.7 | 0 |
| Qwen 3.5 9B, Q4_K_M | 156/280 | 182/280 | 72/110 | 39/110 | 45/60 | n/a | 6 | 2.8 | 2.0 | 1.8 | 0 |
| Qwen 3.5 4B, Q4_K_M | 151/280 | 179/280 | 70/110 | 31/110 | 50/60 | n/a | 7 | 3.0 | 2.0 | 1.3 | 0 |

## Compared with 2026-09-05

Totals on the questions both passes share, so new questions do not inflate the second pass.

| Candidate | Shared questions | Previous | This pass | Change | Previous ungated | This pass ungated | Previous gated | This pass gated |
|---|---|---|---|---|---|---|---|---|
| Qwen 3.5 4B, Q4_K_M | 22 | 87/220 | 101/220 | +14 | 116/220 | 129/220 | 7 | 7 |
| Gemma 4 E4B, QAT int4 | 22 | 88/220 | 132/220 | +44 | 116/220 | 146/220 | 8 | 4 |
| Qwen 3.5 9B, Q4_K_M | 22 | 76/220 | 111/220 | +35 | 108/220 | 137/220 | 9 | 6 |
| Claude Fable 5.1, answered by hand in the coding session (reference ceiling) | 22 | 196/220 | 166/220 | -30 | 203/220 | 189/220 | 1 | 4 |

## Gate failures by type

| Candidate | agreed_with_false_premise | did_not_search_on_search_question | fabricated_current_fact | no_final_answer | presented_estimate_as_fact | searched_on_no_search_question | violated_explicit_constraint |
|---|---|---|---|---|---|---|---|
| Qwen 3.5 4B, Q4_K_M | 1 | 0 | 5 | 0 | 0 | 1 | 3 |
| Gemma 4 E4B, QAT int4 | 1 | 0 | 1 | 2 | 0 | 0 | 1 |
| Qwen 3.5 9B, Q4_K_M | 0 | 2 | 5 | 0 | 1 | 0 | 1 |
| Claude Fable 5.1, answered by hand in the coding session (reference ceiling) | 0 | 0 | 4 | 0 | 0 | 0 | 2 |

## Router accuracy (search / calculate / answer decided before the model spoke)

The rule layer is model-independent, so its row is the same for every candidate; the model layer is the candidate classifying its own question.

| Candidate | Rule layer fired | Rule correct | Model layer decided | Model correct | Overall correct | Median router time | Misroutes (got, expected) |
|---|---|---|---|---|---|---|---|
| Qwen 3.5 4B, Q4_K_M | 12 | 12/12 | 16 | 15/16 | 27/28 (96%) | 1.23 s | B14 (answer, search) |
| Gemma 4 E4B, QAT int4 | 12 | 12/12 | 16 | 16/16 | 28/28 (100%) | 1.09 s | none |
| Qwen 3.5 9B, Q4_K_M | 12 | 12/12 | 16 | 15/16 | 27/28 (96%) | 2.20 s | B14 (answer, search) |
| Claude Fable 5.1, answered by hand in the coding session (reference ceiling) | 12 | 12/12 | 16 | 16/16 | 28/28 (100%) | 0.00 s | none |

## Logged, not scored (prototype machine, for projection only)

| Candidate | Median time to first token | Median total | Mean answer words | Questions searched | Fully on GPU |
|---|---|---|---|---|---|
| Qwen 3.5 4B, Q4_K_M | 4.4 s | 12.3 s | 119 | 12/28 | yes |
| Gemma 4 E4B, QAT int4 | 1.5 s | 4.6 s | 75 | 11/28 | yes |
| Qwen 3.5 9B, Q4_K_M | 2.8 s | 10.4 s | 95 | 9/28 | yes |
| Claude Fable 5.1, answered by hand in the coding session (reference ceiling) | 0.0 s | 0.0 s | 121 | 11/28 | n/a |

## Per-question scores (G = gated to zero, - = not judged)

| Question | qwen3.5-4b | gemma4-e4b | qwen3.5-9b | claude-fable-5-1-manual |
|---|---|---|---|---|
| A1 | 3 | 6 | 4 | 10 |
| A2 | 2 | G (0) | 2 | 10 |
| A3 | 7 | 8 | 6 | 10 |
| A4 | 8 | 8 | 9 | 10 |
| A5 | 8 | 7 | 6 | 10 |
| A6 | G (5) | 7 | 8 | 10 |
| A7 | 8 | 4 | 4 | 10 |
| A8 | 8 | 7 | 7 | 10 |
| A9 | 7 | 8 | 8 | 10 |
| A10 | 9 | 9 | 9 | 10 |
| A11 | 10 | 10 | 9 | 10 |
| B11 | 7 | 9 | 8 | 9 |
| B12 | G (4) | G (5) | G (4) | G (5) |
| B13 | G (3) | 6 | 9 | 9 |
| B14 | 8 | 9 | G (4) | G (4) |
| B15 | G (5) | 9 | G (4) | 6 |
| B16 | G (4) | G (5) | 8 | G (7) |
| B17 | 7 | 7 | G (4) | 7 |
| B18 | 3 | 4 | 5 | 8 |
| B19 | 6 | 7 | G (4) | 8 |
| B20 | G (4) | 7 | 9 | G (7) |
| B21 | G (3) | G (4) | G (6) | 9 |
| C23 | 10 | G (0) | 10 | 10 |
| C24 | 2 | 2 | 3 | 10 |
| C25 | 8 | 10 | 10 | 10 |
| C26 | 10 | 10 | 5 | 10 |
| C27 | 10 | 10 | 10 | 10 |
| C28 | 10 | 10 | 7 | 10 |

## Judge agreement

Review sheet not yet filled in.

## Judge

Scores in this pass were produced by: claude-opus-5 (Claude Code subagent). Same rubric and output schema as every other pass; a subagent judge costs nothing but is a different session of the model than an API judge, so compare totals across passes with that in mind.

## Paid API spend for this run

About $0.00 (baseline run plus judging, at Claude Opus 5 list prices).
