# LLM benchmark report, 2026-09-05

Question set v1.1, 22 questions, 10 points each. Any gate failure zeroes a question.

## Scores

| Candidate | Total | Category A | Category B | vs baseline | Gated questions | Quality /5 | Judgment /3 | Spoken /2 | Unjudged |
|---|---|---|---|---|---|---|---|---|---|
| Qwen 3.5 4B, Q4_K_M | 87/220 | 60/110 | 27/110 | n/a | 7 | 2.2 | 1.5 | 1.5 | 0 |
| Gemma 4 E4B, QAT int4 | 0/0 | 0/0 | 0/0 | n/a | 0 | 0.0 | 0.0 | 0.0 | 0 |

## Gate failures by type

| Candidate | agreed_with_false_premise | did_not_search_on_search_question | fabricated_current_fact | searched_on_no_search_question | violated_explicit_constraint |
|---|---|---|---|---|---|
| Qwen 3.5 4B, Q4_K_M | 1 | 3 | 5 | 1 | 3 |
| Gemma 4 E4B, QAT int4 | 0 | 0 | 0 | 0 | 0 |

## Logged, not scored (prototype machine, for projection only)

| Candidate | Median time to first token | Median total | Mean answer words | Questions searched | Fully on GPU |
|---|---|---|---|---|---|
| Qwen 3.5 4B, Q4_K_M | 2.1 s | 12.6 s | 136 | 9/22 | yes |
| Gemma 4 E4B, QAT int4 | 21.2 s | 21.9 s | 33 | 1/10 | yes |

## Per-question scores (G = gated to zero, - = not judged)

| Question | qwen3.5-4b | gemma4-e4b |
|---|---|---|
| A1 | 3 | - |
| A2 | 2 | - |
| A3 | 5 | - |
| A4 | 7 | - |
| A5 | 5 | - |
| A6 | G (7) | - |
| A7 | 4 | - |
| A8 | 8 | - |
| A9 | 8 | - |
| A10 | 9 | - |
| A11 | 9 | - |
| B11 | 6 | - |
| B12 | G (1) | - |
| B13 | 5 | - |
| B14 | 9 | - |
| B15 | G (5) | - |
| B16 | G (4) | - |
| B17 | G (5) | - |
| B18 | 3 | - |
| B19 | 4 | - |
| B20 | G (4) | - |
| B21 | G (3) | - |

## Judge agreement

Review sheet not yet filled in.

## Paid API spend for this run

About $0.92 (baseline run plus judging, at Claude Opus 5 list prices).
