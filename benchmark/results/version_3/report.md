# LLM benchmark report, version_3

Question set v1.2, 28 questions, 10 points each. Any gate failure zeroes a question. System prompt v1.3; question routing on.

## Scores

Total counts a gated question as zero; ungated total ignores the gates and sums the dimension scores, so the gap between them is what the gates cost.

| Candidate | Total | Ungated total | Category A | Category B | Category C | vs baseline | Gated questions | Quality /5 | Judgment /3 | Spoken /2 | Unjudged |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen 3.5 9B, Q4_K_M | 183/280 | 194/280 | 80/110 | 56/110 | 47/60 | n/a | 3 | 3.0 | 2.1 | 1.9 | 0 |
| Qwen 3.5 4B, Q4_K_M | 145/280 | 184/280 | 62/110 | 36/110 | 47/60 | n/a | 8 | 2.9 | 1.9 | 1.8 | 0 |
| Gemma 4 E4B, QAT int4 | 138/280 | 147/280 | 72/110 | 34/110 | 32/60 | n/a | 8 | 2.2 | 1.6 | 1.5 | 0 |

## Compared with version_2

Totals on the questions both passes share, so new questions do not inflate the second pass.

| Candidate | Shared questions | Previous | This pass | Change | Previous ungated | This pass ungated | Previous gated | This pass gated |
|---|---|---|---|---|---|---|---|---|
| Qwen 3.5 4B, Q4_K_M | 28 | 151/280 | 145/280 | -6 | 179/280 | 184/280 | 7 | 8 |
| Gemma 4 E4B, QAT int4 | 28 | 174/280 | 138/280 | -36 | 188/280 | 147/280 | 5 | 8 |
| Qwen 3.5 9B, Q4_K_M | 28 | 156/280 | 183/280 | +27 | 182/280 | 194/280 | 6 | 3 |

## Gate failures by type

| Candidate | agreed_with_false_premise | did_not_search_on_search_question | fabricated_current_fact | no_final_answer | presented_estimate_as_fact | searched_on_no_search_question | too_many_tool_calls | violated_explicit_constraint |
|---|---|---|---|---|---|---|---|---|
| Qwen 3.5 4B, Q4_K_M | 1 | 1 | 2 | 0 | 1 | 1 | 1 | 2 |
| Gemma 4 E4B, QAT int4 | 2 | 5 | 0 | 4 | 0 | 0 | 0 | 0 |
| Qwen 3.5 9B, Q4_K_M | 0 | 2 | 3 | 0 | 0 | 0 | 0 | 0 |

## Router accuracy (search / calculate / answer decided before the model spoke)

The rule layer is model-independent, so its row is the same for every candidate; the model layer is the candidate classifying its own question.

| Candidate | Rule layer fired | Rule correct | Model layer decided | Model correct | Overall correct | Median router time | Misroutes (got, expected) |
|---|---|---|---|---|---|---|---|
| Qwen 3.5 4B, Q4_K_M | 12 | 12/12 | 16 | 15/16 | 27/28 (96%) | 1.22 s | B14 (answer, search) |
| Gemma 4 E4B, QAT int4 | 12 | 12/12 | 16 | 16/16 | 28/28 (100%) | 1.06 s | none |
| Qwen 3.5 9B, Q4_K_M | 12 | 12/12 | 16 | 15/16 | 27/28 (96%) | 2.18 s | B14 (answer, search) |

## Logged, not scored (prototype machine, for projection only)

| Candidate | Median time to first token | Median total | Mean answer words | Questions searched | Fully on GPU |
|---|---|---|---|---|---|
| Qwen 3.5 4B, Q4_K_M | 4.4 s | 14.3 s | 100 | 11/28 | yes |
| Gemma 4 E4B, QAT int4 | 2.7 s | 5.5 s | 59 | 6/28 | yes |
| Qwen 3.5 9B, Q4_K_M | 3.5 s | 10.7 s | 92 | 9/28 | yes |

## Per-question scores (G = gated to zero, - = not judged)

| Question | qwen3.5-4b | gemma4-e4b | qwen3.5-9b |
|---|---|---|---|
| A1 | 4 | 6 | 8 |
| A2 | 0 | 1 | 4 |
| A3 | 9 | G (2) | 8 |
| A4 | 7 | 8 | 9 |
| A5 | 5 | 8 | 6 |
| A6 | G (5) | 7 | 6 |
| A7 | 4 | 8 | 5 |
| A8 | 7 | 7 | 7 |
| A9 | 9 | 8 | 8 |
| A10 | 7 | 9 | 9 |
| A11 | 10 | 10 | 10 |
| B11 | 7 | 7 | 9 |
| B12 | G (5) | G (2) | 6 |
| B13 | G (5) | G (0) | 5 |
| B14 | 9 | 9 | G (3) |
| B15 | G (7) | 5 | 9 |
| B16 | 7 | G (3) | 7 |
| B17 | 7 | 6 | 8 |
| B18 | 6 | 4 | G (3) |
| B19 | G (6) | G (0) | 5 |
| B20 | G (5) | 3 | 7 |
| B21 | G (4) | G (2) | G (5) |
| C23 | 10 | G (0) | 10 |
| C24 | G (2) | 2 | 5 |
| C25 | 10 | 10 | 10 |
| C26 | 10 | G (0) | 2 |
| C27 | 7 | 10 | 10 |
| C28 | 10 | 10 | 10 |

## Judge agreement

Review sheet not yet filled in.

## Judge

Scores in this pass were produced by: claude-opus-5 (Claude Code subagent). Same rubric and output schema as every other pass; a subagent judge costs nothing but is a different session of the model than an API judge, so compare totals across passes with that in mind.

## Paid API spend for this run

About $0.00 (baseline run plus judging, at Claude Opus 5 list prices).
