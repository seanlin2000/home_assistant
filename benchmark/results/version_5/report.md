# LLM benchmark report, version_5

Question set v1.2, 28 questions, 10 points each. Any gate failure zeroes a question. System prompt v1.5; question routing on.

## Scores

Total counts a gated question as zero; ungated total ignores the gates and sums the dimension scores, so the gap between them is what the gates cost.

| Candidate | Total | Ungated total | Category A | Category B | Category C | vs baseline | Gated questions | Quality /5 | Judgment /3 | Spoken /2 | Unjudged |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Gemma 4 26B-A4B, UD-IQ4_XS (preview, tight fit) (preview) | 232/280 | 236/280 | 95/110 | 78/110 | 59/60 | n/a | 1 | 4.0 | 2.7 | 1.8 | 0 |
| Claude Fable 5.1, answered by hand in the coding session (reference ceiling) | 217/280 | 245/280 | 109/110 | 48/110 | 60/60 | n/a | 5 | 4.1 | 2.6 | 2.0 | 0 |
| Qwen 3.6 35B-A3B, UD-IQ3_XXS (3-bit preview) (preview) | 208/280 | 230/280 | 76/110 | 72/110 | 60/60 | n/a | 4 | 3.9 | 2.6 | 1.6 | 0 |
| Gemma 4 26B-A4B, UD-IQ3_XXS (3-bit preview) (preview) | 199/280 | 225/280 | 84/110 | 56/110 | 59/60 | n/a | 5 | 3.6 | 2.6 | 1.8 | 0 |
| Gemma 4 E4B, QAT int4 | 176/280 | 186/280 | 74/110 | 50/110 | 52/60 | n/a | 5 | 2.9 | 2.0 | 1.8 | 0 |
| Qwen 3.5 4B, Q4_K_M | 157/280 | 187/280 | 72/110 | 33/110 | 52/60 | n/a | 7 | 3.0 | 2.1 | 1.6 | 0 |
| Qwen 3.5 9B, Q4_K_M | 154/280 | 185/280 | 80/110 | 28/110 | 46/60 | n/a | 7 | 2.9 | 2.0 | 1.7 | 0 |
| gpt-oss 20B, MXFP4 | 145/280 | 186/280 | 63/110 | 25/110 | 57/60 | n/a | 9 | 3.2 | 2.0 | 1.6 | 1 |

> Preview builds run at 3-bit precision because the 4-bit production build does not fit the prototype machine. A high preview score is strong evidence for the production build; a low one is only weak evidence against it.

## Compared with version_4

Totals on the questions both passes share, so new questions do not inflate the second pass.

| Candidate | Shared questions | Previous | This pass | Change | Previous ungated | This pass ungated | Previous gated | This pass gated |
|---|---|---|---|---|---|---|---|---|
| Qwen 3.5 4B, Q4_K_M | 28 | 162/280 | 157/280 | -5 | 176/280 | 187/280 | 4 | 7 |
| Gemma 4 E4B, QAT int4 | 28 | 162/280 | 176/280 | +14 | 174/280 | 186/280 | 5 | 5 |
| Qwen 3.5 9B, Q4_K_M | 28 | 125/280 | 154/280 | +29 | 171/280 | 185/280 | 9 | 7 |
| Claude Fable 5.1, answered by hand in the coding session (reference ceiling) | 28 | 241/280 | 217/280 | -24 | 259/280 | 245/280 | 3 | 5 |

## Gate failures by type

| Candidate | agreed_with_false_premise | did_not_search_on_search_question | fabricated_current_fact | no_final_answer | presented_estimate_as_fact | run_error | searched_on_no_search_question | too_many_tool_calls | violated_explicit_constraint |
|---|---|---|---|---|---|---|---|---|---|
| Qwen 3.5 4B, Q4_K_M | 0 | 0 | 5 | 0 | 0 | 0 | 1 | 0 | 1 |
| Gemma 4 E4B, QAT int4 | 1 | 2 | 0 | 2 | 0 | 0 | 0 | 0 | 1 |
| Qwen 3.5 9B, Q4_K_M | 0 | 3 | 6 | 0 | 1 | 0 | 0 | 0 | 0 |
| gpt-oss 20B, MXFP4 | 1 | 0 | 6 | 0 | 0 | 1 | 1 | 0 | 2 |
| Gemma 4 26B-A4B, UD-IQ3_XXS (3-bit preview) (preview) | 0 | 0 | 2 | 0 | 1 | 0 | 0 | 0 | 2 |
| Gemma 4 26B-A4B, UD-IQ4_XS (preview, tight fit) (preview) | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Qwen 3.6 35B-A3B, UD-IQ3_XXS (3-bit preview) (preview) | 0 | 0 | 2 | 0 | 0 | 0 | 1 | 3 | 1 |
| Claude Fable 5.1, answered by hand in the coding session (reference ceiling) | 0 | 0 | 5 | 0 | 0 | 0 | 0 | 0 | 1 |

## Router accuracy (search / calculate / answer decided before the model spoke)

The rule layer is model-independent, so its row is the same for every candidate; the model layer is the candidate classifying its own question.

| Candidate | Rule layer fired | Rule correct | Model layer decided | Model correct | Overall correct | Median router time | Misroutes (got, expected) |
|---|---|---|---|---|---|---|---|
| Qwen 3.5 4B, Q4_K_M | 12 | 12/12 | 16 | 15/16 | 27/28 (96%) | 1.30 s | B14 (answer, search) |
| Gemma 4 E4B, QAT int4 | 12 | 12/12 | 16 | 16/16 | 28/28 (100%) | 1.08 s | none |
| Qwen 3.5 9B, Q4_K_M | 12 | 12/12 | 16 | 15/16 | 27/28 (96%) | 2.25 s | B14 (answer, search) |
| gpt-oss 20B, MXFP4 | 12 | 12/12 | 15 | 9/15 | 21/27 (78%) | 7.69 s | B11 (answer, search), B13 (answer, search), B14 (answer, search), B16 (answer, search), B20 (answer, search), B21 (answer, search) |
| Gemma 4 26B-A4B, UD-IQ3_XXS (3-bit preview) (preview) | 12 | 12/12 | 16 | 16/16 | 28/28 (100%) | 15.97 s | none |
| Gemma 4 26B-A4B, UD-IQ4_XS (preview, tight fit) (preview) | 12 | 12/12 | 16 | 16/16 | 28/28 (100%) | 33.68 s | none |
| Qwen 3.6 35B-A3B, UD-IQ3_XXS (3-bit preview) (preview) | 12 | 12/12 | 16 | 16/16 | 28/28 (100%) | 18.01 s | none |
| Claude Fable 5.1, answered by hand in the coding session (reference ceiling) | 12 | 12/12 | 16 | 16/16 | 28/28 (100%) | 0.00 s | none |

## Logged, not scored (prototype machine, for projection only)

| Candidate | Median time to first token | Median total | Mean answer words | Questions searched | Fully on GPU |
|---|---|---|---|---|---|
| Qwen 3.5 4B, Q4_K_M | 2.9 s | 8.9 s | 96 | 12/28 | yes |
| Gemma 4 E4B, QAT int4 | 1.4 s | 4.7 s | 76 | 9/28 | yes |
| Qwen 3.5 9B, Q4_K_M | 2.8 s | 10.5 s | 105 | 8/28 | yes |
| gpt-oss 20B, MXFP4 | 16.6 s | 50.6 s | 126 | 11/28 | NO |
| Gemma 4 26B-A4B, UD-IQ3_XXS (3-bit preview) (preview) | 28.4 s | 84.0 s | 104 | 11/28 | NO |
| Gemma 4 26B-A4B, UD-IQ4_XS (preview, tight fit) (preview) | 61.6 s | 155.1 s | 97 | 10/28 | NO |
| Qwen 3.6 35B-A3B, UD-IQ3_XXS (3-bit preview) (preview) | 50.5 s | 156.4 s | 130 | 12/28 | NO |
| Claude Fable 5.1, answered by hand in the coding session (reference ceiling) | 0.0 s | 0.0 s | 121 | 11/28 | n/a |

## Per-question scores (G = gated to zero, - = not judged)

| Question | qwen3.5-4b | gemma4-e4b | qwen3.5-9b | gpt-oss-20b | gemma4-26b-a4b-iq3 | gemma4-26b-a4b-iq4 | qwen3.6-35b-a3b-iq3 | claude-fable-5-1-manual |
|---|---|---|---|---|---|---|---|---|
| A1 | 4 | 8 | 5 | 5 | 8 | 9 | 7 | 10 |
| A2 | 2 | G (0) | 3 | 4 | G (6) | 8 | G (10) | 10 |
| A3 | 9 | 9 | 8 | G (8) | 9 | 9 | 8 | 10 |
| A4 | 8 | 9 | 9 | 8 | 9 | 9 | 9 | 10 |
| A5 | 8 | 7 | 6 | 5 | 8 | 8 | 8 | 10 |
| A6 | G (4) | 7 | 6 | 7 | 7 | 7 | G (3) | 10 |
| A7 | 8 | G (0) | 9 | 9 | 9 | 9 | 9 | 9 |
| A8 | 7 | 8 | 7 | 7 | 7 | 8 | 7 | 10 |
| A9 | 8 | 7 | 8 | 8 | 8 | 9 | 9 | 10 |
| A10 | 8 | 9 | 9 | G (7) | 9 | 9 | 9 | 10 |
| A11 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 |
| B11 | G (5) | 6 | G (5) | 10 | 8 | 8 | 8 | 9 |
| B12 | 6 | 7 | 7 | - | G (4) | 8 | 8 | G (5) |
| B13 | G (5) | G (2) | G (4) | G (3) | 9 | 8 | 9 | 9 |
| B14 | 9 | 9 | G (3) | G (7) | 8 | 8 | 9 | G (6) |
| B15 | G (4) | G (5) | 9 | G (6) | G (6) | 7 | G (1) | 5 |
| B16 | G (4) | 7 | G (6) | G (4) | 7 | 7 | 8 | G (6) |
| B17 | 5 | 7 | G (3) | 5 | 9 | 10 | 8 | 7 |
| B18 | G (3) | 4 | 5 | 5 | 6 | 6 | 7 | G (5) |
| B19 | 6 | 7 | G (5) | 5 | G (6) | 9 | 7 | 8 |
| B20 | G (5) | 3 | 7 | G (3) | G (4) | 7 | G (8) | G (6) |
| B21 | 7 | G (3) | G (5) | G (3) | 9 | G (4) | 8 | 10 |
| C23 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 |
| C24 | 4 | 2 | 4 | 7 | 9 | 9 | 10 | 10 |
| C25 | 8 | 10 | 9 | 10 | 10 | 10 | 10 | 10 |
| C26 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 |
| C27 | 10 | 10 | 3 | 10 | 10 | 10 | 10 | 10 |
| C28 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 |

## Judge agreement

Review sheet not yet filled in.

## Judge

Scores in this pass were produced by: claude-opus-5 (Claude Code subagent). Same rubric and output schema as every other pass; a subagent judge costs nothing but is a different session of the model than an API judge, so compare totals across passes with that in mind.

## Paid API spend for this run

About $0.00 (baseline run plus judging, at Claude Opus 5 list prices).
