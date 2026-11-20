# LLM benchmark report, version_4

Question set v1.2, 28 questions, 10 points each. Any gate failure zeroes a question. System prompt v1.4; question routing on.

## Scores

Total counts a gated question as zero; ungated total ignores the gates and sums the dimension scores, so the gap between them is what the gates cost.

| Candidate | Total | Ungated total | Category A | Category B | Category C | vs baseline | Gated questions | Quality /5 | Judgment /3 | Spoken /2 | Unjudged |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Claude Fable 5.1, answered by hand in the coding session (reference ceiling) | 241/280 | 259/280 | 110/110 | 71/110 | 60/60 | n/a | 3 | 4.4 | 2.8 | 2.0 | 0 |
| Qwen 3.5 4B, Q4_K_M | 162/280 | 176/280 | 75/110 | 37/110 | 50/60 | n/a | 4 | 2.9 | 2.0 | 1.4 | 0 |
| Gemma 4 E4B, QAT int4 | 162/280 | 174/280 | 65/110 | 45/110 | 52/60 | n/a | 5 | 2.8 | 1.7 | 1.8 | 0 |
| Qwen 3.5 9B, Q4_K_M | 125/280 | 171/280 | 60/110 | 18/110 | 47/60 | n/a | 9 | 2.6 | 1.8 | 1.8 | 0 |

## Compared with version_3

Totals on the questions both passes share, so new questions do not inflate the second pass.

| Candidate | Shared questions | Previous | This pass | Change | Previous ungated | This pass ungated | Previous gated | This pass gated |
|---|---|---|---|---|---|---|---|---|
| Qwen 3.5 4B, Q4_K_M | 28 | 145/280 | 162/280 | +17 | 184/280 | 176/280 | 8 | 4 |
| Gemma 4 E4B, QAT int4 | 28 | 138/280 | 162/280 | +24 | 147/280 | 174/280 | 8 | 5 |
| Qwen 3.5 9B, Q4_K_M | 28 | 183/280 | 125/280 | -58 | 194/280 | 171/280 | 3 | 9 |

## Gate failures by type

| Candidate | agreed_with_false_premise | did_not_search_on_search_question | fabricated_current_fact | no_final_answer | too_many_tool_calls | violated_explicit_constraint |
|---|---|---|---|---|---|---|
| Qwen 3.5 4B, Q4_K_M | 1 | 1 | 3 | 0 | 1 | 0 |
| Gemma 4 E4B, QAT int4 | 2 | 3 | 0 | 1 | 0 | 1 |
| Qwen 3.5 9B, Q4_K_M | 0 | 3 | 6 | 0 | 0 | 3 |
| Claude Fable 5.1, answered by hand in the coding session (reference ceiling) | 0 | 0 | 3 | 0 | 0 | 0 |

## Router accuracy (search / calculate / answer decided before the model spoke)

The rule layer is model-independent, so its row is the same for every candidate; the model layer is the candidate classifying its own question.

| Candidate | Rule layer fired | Rule correct | Model layer decided | Model correct | Overall correct | Median router time | Misroutes (got, expected) |
|---|---|---|---|---|---|---|---|
| Qwen 3.5 4B, Q4_K_M | 12 | 12/12 | 16 | 15/16 | 27/28 (96%) | 1.22 s | B14 (answer, search) |
| Gemma 4 E4B, QAT int4 | 12 | 12/12 | 16 | 16/16 | 28/28 (100%) | 1.06 s | none |
| Qwen 3.5 9B, Q4_K_M | 12 | 12/12 | 16 | 15/16 | 27/28 (96%) | 2.14 s | B14 (answer, search) |
| Claude Fable 5.1, answered by hand in the coding session (reference ceiling) | 12 | 12/12 | 16 | 16/16 | 28/28 (100%) | 0.00 s | none |

## Logged, not scored (prototype machine, for projection only)

| Candidate | Median time to first token | Median total | Mean answer words | Questions searched | Fully on GPU |
|---|---|---|---|---|---|
| Qwen 3.5 4B, Q4_K_M | 4.6 s | 12.9 s | 124 | 10/28 | yes |
| Gemma 4 E4B, QAT int4 | 2.7 s | 6.0 s | 70 | 8/28 | yes |
| Qwen 3.5 9B, Q4_K_M | 2.9 s | 11.4 s | 104 | 8/28 | yes |
| Claude Fable 5.1, answered by hand in the coding session (reference ceiling) | 0.0 s | 0.0 s | 121 | 11/28 | n/a |

## Per-question scores (G = gated to zero, - = not judged)

| Question | qwen3.5-4b | gemma4-e4b | qwen3.5-9b | claude-fable-5-1-manual |
|---|---|---|---|---|
| A1 | 3 | 6 | 5 | 10 |
| A2 | 2 | 3 | 2 | 10 |
| A3 | 9 | G (3) | 6 | 10 |
| A4 | 8 | 7 | 8 | 10 |
| A5 | 8 | 6 | 6 | 10 |
| A6 | 5 | 7 | 5 | 10 |
| A7 | 7 | 1 | 3 | 10 |
| A8 | 6 | 7 | 7 | 10 |
| A9 | 8 | 9 | 8 | 10 |
| A10 | 9 | 9 | G (6) | 10 |
| A11 | 10 | 10 | 10 | 10 |
| B11 | G (5) | 6 | G (3) | 9 |
| B12 | 3 | G (5) | G (6) | 9 |
| B13 | G (4) | G (1) | G (5) | G (5) |
| B14 | 8 | 7 | 8 | G (7) |
| B15 | G (2) | 9 | G (3) | 10 |
| B16 | 4 | 8 | G (5) | G (6) |
| B17 | 7 | 6 | G (5) | 9 |
| B18 | 6 | 6 | 3 | 7 |
| B19 | 3 | G (0) | 7 | 8 |
| B20 | 6 | 3 | G (6) | 9 |
| B21 | G (3) | G (3) | G (7) | 10 |
| C23 | 10 | 10 | 10 | 10 |
| C24 | 1 | 2 | 5 | 10 |
| C25 | 10 | 10 | 10 | 10 |
| C26 | 10 | 10 | 7 | 10 |
| C27 | 10 | 10 | 5 | 10 |
| C28 | 9 | 10 | 10 | 10 |

## Judge agreement

Review sheet not yet filled in.

## Judge

Scores in this pass were produced by: claude-opus-5 (Claude Code subagent). Same rubric and output schema as every other pass; a subagent judge costs nothing but is a different session of the model than an API judge, so compare totals across passes with that in mind.

## Paid API spend for this run

About $0.00 (baseline run plus judging, at Claude Opus 5 list prices).
