# LLM benchmark report, version_5

Question set v1.2, 28 questions, 10 points each. Any gate failure zeroes a question. System prompt v1.5; question routing on.

## Scores

Total counts a gated question as zero; ungated total ignores the gates and sums the dimension scores, so the gap between them is what the gates cost.

| Candidate | Total | Ungated total | Category A | Category B | Category C | vs baseline | Gated questions | Quality /5 | Judgment /3 | Spoken /2 | Unjudged |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen 3.5 4B, Q4_K_M | 157/280 | 187/280 | 72/110 | 33/110 | 52/60 | n/a | 7 | 3.0 | 2.1 | 1.6 | 0 |
| Gemma 4 E4B, QAT int4 | 154/280 | 165/280 | 74/110 | 35/110 | 45/60 | n/a | 9 | 2.6 | 1.8 | 1.5 | 0 |
| Qwen 3.5 9B, Q4_K_M | 154/280 | 185/280 | 80/110 | 28/110 | 46/60 | n/a | 7 | 2.9 | 2.0 | 1.7 | 0 |
| gpt-oss 20B, MXFP4 | 0/0 | 0/0 | 0/0 | 0/0 | n/a | n/a | 0 | 0.0 | 0.0 | 0.0 | 0 |

## Compared with version_4

Totals on the questions both passes share, so new questions do not inflate the second pass.

| Candidate | Shared questions | Previous | This pass | Change | Previous ungated | This pass ungated | Previous gated | This pass gated |
|---|---|---|---|---|---|---|---|---|
| Qwen 3.5 4B, Q4_K_M | 28 | 162/280 | 157/280 | -5 | 176/280 | 187/280 | 4 | 7 |
| Gemma 4 E4B, QAT int4 | 28 | 162/280 | 154/280 | -8 | 174/280 | 165/280 | 5 | 9 |
| Qwen 3.5 9B, Q4_K_M | 28 | 125/280 | 154/280 | +29 | 171/280 | 185/280 | 9 | 7 |

## Gate failures by type

| Candidate | agreed_with_false_premise | did_not_search_on_search_question | fabricated_current_fact | no_final_answer | presented_estimate_as_fact | searched_on_no_search_question | violated_explicit_constraint |
|---|---|---|---|---|---|---|---|
| Qwen 3.5 4B, Q4_K_M | 0 | 0 | 5 | 0 | 0 | 1 | 1 |
| Gemma 4 E4B, QAT int4 | 2 | 5 | 0 | 4 | 0 | 0 | 1 |
| Qwen 3.5 9B, Q4_K_M | 0 | 3 | 6 | 0 | 1 | 0 | 0 |
| gpt-oss 20B, MXFP4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

## Router accuracy (search / calculate / answer decided before the model spoke)

The rule layer is model-independent, so its row is the same for every candidate; the model layer is the candidate classifying its own question.

| Candidate | Rule layer fired | Rule correct | Model layer decided | Model correct | Overall correct | Median router time | Misroutes (got, expected) |
|---|---|---|---|---|---|---|---|
| Qwen 3.5 4B, Q4_K_M | 12 | 12/12 | 16 | 15/16 | 27/28 (96%) | 1.30 s | B14 (answer, search) |
| Gemma 4 E4B, QAT int4 | 12 | 12/12 | 16 | 16/16 | 28/28 (100%) | 1.08 s | none |
| Qwen 3.5 9B, Q4_K_M | 12 | 12/12 | 16 | 15/16 | 27/28 (96%) | 2.25 s | B14 (answer, search) |
| gpt-oss 20B, MXFP4 | 2 | 2/2 | 12 | 9/12 | 11/14 (79%) | 7.61 s | B11 (answer, search), B13 (answer, search), B14 (answer, search) |

## Logged, not scored (prototype machine, for projection only)

| Candidate | Median time to first token | Median total | Mean answer words | Questions searched | Fully on GPU |
|---|---|---|---|---|---|
| Qwen 3.5 4B, Q4_K_M | 2.9 s | 8.9 s | 96 | 12/28 | yes |
| Gemma 4 E4B, QAT int4 | 1.4 s | 4.8 s | 64 | 6/28 | yes |
| Qwen 3.5 9B, Q4_K_M | 2.8 s | 10.5 s | 105 | 8/28 | yes |
| gpt-oss 20B, MXFP4 | 16.2 s | 40.7 s | 142 | 4/15 | NO |

## Per-question scores (G = gated to zero, - = not judged)

| Question | qwen3.5-4b | gemma4-e4b | qwen3.5-9b | gpt-oss-20b |
|---|---|---|---|---|
| A1 | 4 | 5 | 5 | - |
| A2 | 2 | G (0) | 3 | - |
| A3 | 9 | G (2) | 8 | - |
| A4 | 8 | 9 | 9 | - |
| A5 | 8 | 8 | 6 | - |
| A6 | G (4) | 9 | 6 | - |
| A7 | 8 | 8 | 9 | - |
| A8 | 7 | 8 | 7 | - |
| A9 | 8 | 8 | 8 | - |
| A10 | 8 | 9 | 9 | - |
| A11 | 10 | 10 | 10 | - |
| B11 | G (5) | 7 | G (5) | - |
| B12 | 6 | 7 | 7 | - |
| B13 | G (5) | G (2) | G (4) | - |
| B14 | 9 | 9 | G (3) | - |
| B15 | G (4) | G (4) | 9 | - |
| B16 | G (4) | G (1) | G (6) | - |
| B17 | 5 | G (0) | G (3) | - |
| B18 | G (3) | 5 | 5 | - |
| B19 | 6 | G (0) | G (5) | - |
| B20 | G (5) | 7 | 7 | - |
| B21 | 7 | G (2) | G (5) | - |
| C23 | 10 | 10 | 10 | - |
| C24 | 4 | 5 | 4 | - |
| C25 | 8 | 10 | 9 | - |
| C26 | 10 | G (0) | 10 | - |
| C27 | 10 | 10 | 3 | - |
| C28 | 10 | 10 | 10 | - |

## Judge agreement

Review sheet not yet filled in.

## Judge

Scores in this pass were produced by: claude-opus-5 (Claude Code subagent). Same rubric and output schema as every other pass; a subagent judge costs nothing but is a different session of the model than an API judge, so compare totals across passes with that in mind.

## Paid API spend for this run

About $0.00 (baseline run plus judging, at Claude Opus 5 list prices).
