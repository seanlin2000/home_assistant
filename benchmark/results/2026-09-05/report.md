# LLM benchmark report, 2026-09-05

Question set v1.1, 22 questions, 10 points each. Any gate failure zeroes a question.

## Scores

| Candidate | Total | Category A | Category B | vs baseline | Gated questions | Quality /5 | Judgment /3 | Spoken /2 | Unjudged |
|---|---|---|---|---|---|---|---|---|---|
| Claude Fable 5.1, answered by hand in the coding session (reference ceiling) | 196/220 | 110/110 | 86/110 | n/a | 1 | 4.4 | 2.8 | 2.0 | 0 |
| Gemma 4 E4B, QAT int4 | 88/220 | 70/110 | 18/110 | n/a | 8 | 2.0 | 1.4 | 1.8 | 0 |
| Qwen 3.5 4B, Q4_K_M | 87/220 | 60/110 | 27/110 | n/a | 7 | 2.2 | 1.5 | 1.5 | 0 |
| Qwen 3.5 9B, Q4_K_M | 76/220 | 66/110 | 10/110 | n/a | 9 | 2.0 | 1.2 | 1.6 | 0 |
| gpt-oss 20B, MXFP4 | 65/220 | 34/110 | 31/110 | n/a | 11 | 2.4 | 1.5 | 1.5 | 0 |

## Gate failures by type

| Candidate | agreed_with_false_premise | did_not_search_on_search_question | fabricated_current_fact | presented_estimate_as_fact | searched_on_no_search_question | violated_explicit_constraint |
|---|---|---|---|---|---|---|
| Qwen 3.5 4B, Q4_K_M | 1 | 3 | 5 | 0 | 1 | 3 |
| Gemma 4 E4B, QAT int4 | 1 | 7 | 0 | 1 | 0 | 0 |
| Qwen 3.5 9B, Q4_K_M | 0 | 8 | 6 | 1 | 0 | 0 |
| gpt-oss 20B, MXFP4 | 1 | 0 | 5 | 2 | 4 | 2 |
| Claude Fable 5.1, answered by hand in the coding session (reference ceiling) | 0 | 0 | 1 | 0 | 0 | 0 |

## Logged, not scored (prototype machine, for projection only)

| Candidate | Median time to first token | Median total | Mean answer words | Questions searched | Fully on GPU |
|---|---|---|---|---|---|
| Qwen 3.5 4B, Q4_K_M | 2.1 s | 12.6 s | 136 | 9/22 | yes |
| Gemma 4 E4B, QAT int4 | 0.3 s | 2.8 s | 66 | 4/22 | yes |
| Qwen 3.5 9B, Q4_K_M | 2.9 s | 9.4 s | 106 | 3/22 | yes |
| gpt-oss 20B, MXFP4 | 12.9 s | 64.9 s | 143 | 15/22 | NO |
| Claude Fable 5.1, answered by hand in the coding session (reference ceiling) | 0.0 s | 0.0 s | 143 | 11/22 | n/a |

## Per-question scores (G = gated to zero, - = not judged)

| Question | qwen3.5-4b | gemma4-e4b | qwen3.5-9b | gpt-oss-20b | claude-fable-5-1-manual |
|---|---|---|---|---|---|
| A1 | 3 | 7 | 4 | 3 | 10 |
| A2 | 2 | 1 | 2 | 4 | 10 |
| A3 | 5 | 7 | 6 | 6 | 10 |
| A4 | 7 | 6 | 8 | G (5) | 10 |
| A5 | 5 | 6 | 6 | G (4) | 10 |
| A6 | G (7) | 7 | 4 | G (7) | 10 |
| A7 | 4 | 5 | 3 | 7 | 10 |
| A8 | 8 | 6 | 7 | 7 | 10 |
| A9 | 8 | 6 | 7 | 7 | 10 |
| A10 | 9 | 9 | 9 | G (6) | 10 |
| A11 | 9 | 10 | 10 | G (8) | 10 |
| B11 | 6 | 6 | G (4) | 6 | 9 |
| B12 | G (1) | G (2) | G (4) | G (5) | G (7) |
| B13 | 5 | G (3) | G (3) | G (1) | 8 |
| B14 | 9 | G (3) | G (4) | 7 | 9 |
| B15 | G (5) | G (3) | G (3) | 7 | 8 |
| B16 | G (4) | G (5) | G (2) | 6 | 9 |
| B17 | G (5) | 6 | G (2) | 5 | 7 |
| B18 | 3 | 6 | 5 | G (3) | 8 |
| B19 | 4 | G (5) | 5 | G (5) | 9 |
| B20 | G (4) | G (4) | G (4) | G (5) | 9 |
| B21 | G (3) | G (3) | G (6) | G (3) | 10 |

## Judge agreement

Review sheet not yet filled in.

## Paid API spend for this run

About $4.56 (baseline run plus judging, at Claude Opus 5 list prices).
