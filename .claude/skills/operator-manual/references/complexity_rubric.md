# Complexity rubric

Score a section before writing it, from its design doc and the code it covers. Three factors, each 1 to 3:

| Factor | 1 | 2 | 3 |
|---|---|---|---|
| Packages and tools the reader must understand | ≤ 2 | 3 to 4 | ≥ 5 |
| Modular parts under "How it works" | ≤ 2 | 3 to 4 | ≥ 5 |
| Newcomer concepts the reader must learn (terms in "Key definitions") | ≤ 2 | 3 to 5 | ≥ 6 |

The sum picks the tier:

| Sum | Tier | Reading time | Diagrams | Code samples |
|---|---|---|---|---|
| 3 to 4 | light | 3 to 5 minutes | 1 to 2 (the map counts) | 0 to 1 |
| 5 to 7 | standard | 5 to 8 minutes | 2 to 4 | 0 to 2 |
| 8 to 9 | deep | 10 to 15 minutes | 4 to 6 | 1 to 3 |

Record the score on the line under the title, exactly:

```
<!-- complexity: packages=2 parts=3 concepts=4 tier=standard -->
```

`manual-check` rejects a missing comment and a tier that does not match the sum. The tier is a budget, not a target: a light section that says everything in three minutes is finished. A deep section that needs a seventh diagram to be honest gets it.
