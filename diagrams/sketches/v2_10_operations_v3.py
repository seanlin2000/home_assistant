"""Sketch: v2 operations in the lane style of the approved figures: a deploy, and the five-minute health check. Every lane is one chain
of equal boxes read left to right. Replaces v1 and v2, whose "rules table", "policy table", "act", and "in a row, per part" needed explaining.
"""

from canvas import Canvas

CONTENT = 18
BOX_WIDTH = CONTENT + 4
GAP = 6
COLUMNS = [1 + BOX_WIDTH // 2 + index * (BOX_WIDTH + GAP) for index in range(5)]
W = 1 + 5 * BOX_WIDTH + 4 * GAP + 1

lanes = [
    (
        "A DEPLOY, started from the laptop",
        [["changed files", "since last deploy"], ["select restarts", "by folder changed"], ["restart", "llama, harness..."], ["warm up", "both slots read"], ["smoke test", "a question via HA"]],
    ),
    (
        "THE HEALTH CHECK, every five minutes",
        [
            ["check each part", "llama, harness..."],
            ["record", "RAM, slow requests"],
            ["count failures", "since last success"],
            ["restart the part", "after 2 failures"],
            ["health.json", "the snapshot"],
        ],
    ),
]

canvas = Canvas(W, 14)
top = 0
for title, boxes in lanes:
    canvas.put(top, 1, title)
    spans = [
        canvas.box(top + 2, column, [line.center(CONTENT) for line in lines], stored=title.startswith("THE HEALTH") and index == len(boxes) - 1)
        for index, (column, lines) in enumerate(zip(COLUMNS, boxes))
    ]
    for (_, right, _), (left, _, _) in zip(spans, spans[1:]):
        canvas.hline(top + 4, right + 1, left - 1)
    top = spans[0][2] + 2

print("\n".join(line.ljust(W) for line in canvas.render().rstrip("\n").splitlines()))
