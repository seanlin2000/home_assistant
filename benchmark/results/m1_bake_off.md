# M1 engine bake-off: gemma4-e4b-llama against gemma4-e4b

Runs: m1_run1, m1_run2, m1_run3.

## Scores per run (gated questions count zero)

| Category | gemma4-e4b run 1 | gemma4-e4b run 2 | gemma4-e4b run 3 | Noise band | gemma4-e4b-llama run 1 | gemma4-e4b-llama run 2 | gemma4-e4b-llama run 3 |
|---|---|---|---|---|---|---|---|
| A | 67 | 67 | 71 | 4 | 60 | 66 | 61 |
| B | 34 | 46 | 31 | 15 | 44 | 58 | 61 |
| C | 38 | 47 | 52 | 14 | 34 | 41 | 33 |
| D | 47 | 46 | 50 | 4 | 50 | 50 | 45 |
| E | 28 | 19 | 20 | 9 | 27 | 27 | 27 |
| Total | 214 | 225 | 224 | 11 | 215 | 242 | 227 |

## Tool calls and empty completions, all runs

| Candidate | Exchanges | With a malformed tool call | With an empty completion retried |
|---|---|---|---|
| gemma4-e4b | 117 | 0 | 2 |
| gemma4-e4b-llama | 117 | 1 | 0 |

## Speed, all runs pooled

| Candidate | Median first spoken word | Slowest tenth | First requests over 600 fresh tokens | Median decode |
|---|---|---|---|---|
| gemma4-e4b | 3.66 s | 7.07 s | not reported | 41.6 tok/s |
| gemma4-e4b-llama | 1.04 s | 1.77 s | 0 of 117 | 41.1 tok/s |

## M1 exit criteria (v2/00 section 9)

| Criterion | Measured | Met |
|---|---|---|
| Score at least the baseline's minus the noise | mean 228.0 against a floor of 210.0 | yes |
| Malformed tool calls no more often than the baseline | 1 against 0 | NO |
| Empty completions rarer than one in seven | 0 of 117 (0%) | yes |
| Median first spoken word at most half the baseline's | 1.04 s against 3.66 s | yes |
| Nine first requests in ten read at most 600 tokens fresh | 117 of 117 (100%) | yes |
