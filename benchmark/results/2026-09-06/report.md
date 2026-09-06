# LLM benchmark report, 2026-09-06

Question set v1.2, 28 questions, 10 points each. Any gate failure zeroes a question. System prompt v1.2; question routing on.

## Scores

Total counts a gated question as zero; ungated total ignores the gates and sums the dimension scores, so the gap between them is what the gates cost.

| Candidate | Total | Ungated total | Category A | Category B | Category C | vs baseline | Gated questions | Quality /5 | Judgment /3 | Spoken /2 | Unjudged |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Claude Fable 5.1, answered by hand in the coding session (reference ceiling) | 254/280 | 261/280 | 109/110 | 89/110 | 56/60 | n/a | 1 | 4.6 | 2.8 | 2.0 | 0 |
| Gemma 4 E4B, QAT int4 | 133/280 | 147/280 | 64/110 | 50/110 | 19/60 | n/a | 4 | 2.1 | 1.6 | 1.5 | 0 |
| Qwen 3.5 9B, Q4_K_M | 128/280 | 158/280 | 73/110 | 23/110 | 32/60 | n/a | 8 | 2.4 | 1.5 | 1.7 | 0 |
| Qwen 3.5 4B, Q4_K_M | 92/280 | 132/280 | 55/110 | 25/110 | 12/60 | n/a | 12 | 2.2 | 1.4 | 1.3 | 1 |

## Compared with 2026-09-05

Totals on the questions both passes share, so new questions do not inflate the second pass.

| Candidate | Shared questions | Previous | This pass | Change | Previous ungated | This pass ungated | Previous gated | This pass gated |
|---|---|---|---|---|---|---|---|---|
| Qwen 3.5 4B, Q4_K_M | 22 | 87/220 | 80/220 | -7 | 116/220 | 111/220 | 7 | 8 |
| Gemma 4 E4B, QAT int4 | 22 | 88/220 | 114/220 | +26 | 116/220 | 128/220 | 8 | 3 |
| Qwen 3.5 9B, Q4_K_M | 22 | 76/220 | 96/220 | +20 | 108/220 | 126/220 | 9 | 8 |
| Claude Fable 5.1, answered by hand in the coding session (reference ceiling) | 22 | 196/220 | 198/220 | +2 | 203/220 | 205/220 | 1 | 1 |

## Gate failures by type

| Candidate | agreed_with_false_premise | did_not_search_on_search_question | fabricated_current_fact | no_final_answer | run_error | searched_on_no_search_question | violated_explicit_constraint |
|---|---|---|---|---|---|---|---|
| Qwen 3.5 4B, Q4_K_M | 1 | 0 | 4 | 0 | 1 | 4 | 2 |
| Gemma 4 E4B, QAT int4 | 1 | 0 | 1 | 1 | 0 | 0 | 2 |
| Qwen 3.5 9B, Q4_K_M | 0 | 4 | 5 | 0 | 0 | 0 | 2 |
| Claude Fable 5.1, answered by hand in the coding session (reference ceiling) | 0 | 0 | 1 | 0 | 0 | 0 | 0 |

## Router accuracy (search / calculate / answer decided before the model spoke)

The rule layer is model-independent, so its row is the same for every candidate; the model layer is the candidate classifying its own question.

| Candidate | Rule layer fired | Rule correct | Model layer decided | Model correct | Overall correct | Median router time | Misroutes (got, expected) |
|---|---|---|---|---|---|---|---|
| Qwen 3.5 4B, Q4_K_M | 11 | 11/11 | 16 | 15/16 | 26/27 (96%) | 1.23 s | B14 (answer, search) |
| Gemma 4 E4B, QAT int4 | 12 | 12/12 | 16 | 16/16 | 28/28 (100%) | 1.13 s | none |
| Qwen 3.5 9B, Q4_K_M | 12 | 12/12 | 16 | 15/16 | 27/28 (96%) | 2.18 s | B14 (answer, search) |
| Claude Fable 5.1, answered by hand in the coding session (reference ceiling) | 12 | 12/12 | 16 | 16/16 | 28/28 (100%) | 0.00 s | none |

## Logged, not scored (prototype machine, for projection only)

| Candidate | Median time to first token | Median total | Mean answer words | Questions searched | Fully on GPU |
|---|---|---|---|---|---|
| Qwen 3.5 4B, Q4_K_M | 4.0 s | 15.5 s | 137 | 15/28 | yes |
| Gemma 4 E4B, QAT int4 | 2.0 s | 6.5 s | 82 | 11/28 | yes |
| Qwen 3.5 9B, Q4_K_M | 2.6 s | 11.0 s | 102 | 7/28 | yes |
| Claude Fable 5.1, answered by hand in the coding session (reference ceiling) | 0.0 s | 0.0 s | 121 | 11/28 | n/a |

## Per-question scores (G = gated to zero, - = not judged)

| Question | qwen3.5-4b | gemma4-e4b | qwen3.5-9b | claude-fable-5-1-manual |
|---|---|---|---|---|
| A1 | 3 | 3 | 4 | 10 |
| A2 | 2 | 2 | 4 | 10 |
| A3 | 8 | 6 | 9 | 10 |
| A4 | 6 | 8 | 7 | 10 |
| A5 | 7 | 5 | 8 | 10 |
| A6 | G (2) | 6 | 6 | 10 |
| A7 | 3 | 3 | 2 | 9 |
| A8 | 7 | 6 | 7 | 10 |
| A9 | 9 | 6 | 7 | 10 |
| A10 | G (6) | 9 | 9 | 10 |
| A11 | 10 | 10 | 10 | 10 |
| B11 | 6 | 6 | 7 | 10 |
| B12 | G (5) | G (5) | G (4) | G (7) |
| B13 | G (4) | 5 | G (5) | 8 |
| B14 | G (3) | 9 | G (3) | 9 |
| B15 | 7 | G (5) | G (4) | 9 |
| B16 | G (4) | 7 | G (3) | 10 |
| B17 | 5 | 7 | 7 | 6 |
| B18 | 5 | 5 | G (4) | 9 |
| B19 | G (4) | 7 | G (3) | 9 |
| B20 | 2 | 4 | G (4) | 9 |
| B21 | G (3) | G (4) | 9 | 10 |
| C23 | 9 | 4 | 9 | 10 |
| C24 | G (2) | 1 | 1 | 9 |
| C25 | G (6) | 9 | 9 | 10 |
| C26 | 3 | G (0) | 5 | 10 |
| C27 | - | 2 | 4 | 8 |
| C28 | G (1) | 3 | 4 | 9 |

## Judge agreement

Review sheet not yet filled in.

## Paid API spend for this run

About $4.87 (baseline run plus judging, at Claude Opus 5 list prices).
