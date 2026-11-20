"""Sketch: v2 security, the three guards. Every lane is one chain of equal boxes; a lane's title sits on its own line above it."""

from canvas import Canvas

CONTENT = 20
COLUMNS = (13, 51, 89, 127)
W = 141

lanes = [
    (
        "A QUESTION THAT USES A TOOL",
        [["your question", "spoken, trusted"], ["main model call", "sees past summaries"], ["egress guard", "no private terms out"], ["tool server", "web, weather, sports"]],
        ["", "tool call", "allowed call"],
    ),
    (
        "EMAIL, REDDIT AND X",
        [["email, post, thread", "raw text"], ["quarantined call", "no tools, no memory"], ["schema check", "fixed fields only"], ["main model call", "reads the fields"]],
        ["", "JSON", "fields"],
    ),
    (
        "MEMORY WRITES",
        [["conversation ends", "transcript"], ["summary call", "no tools, JSON only"], ["note validation", "no URLs, no commands"], ["memory vault", "keeps trust mark"]],
        ["", "summary", "valid note"],
    ),
]

canvas = Canvas(W, 30)
top = 0
for title, boxes, labels in lanes:
    canvas.put(top, 1, title)
    spans = []
    for index, (column, lines) in enumerate(zip(COLUMNS, boxes)):
        stored = title == "MEMORY WRITES" and index == len(boxes) - 1
        spans.append(canvas.box(top + 2, column, [line.center(CONTENT) for line in lines], stored=stored))
    for (_, right, _), (left, _, _), label in zip(spans, spans[1:], labels):
        canvas.hline(top + 4, right + 1, left - 1)
        if label:
            canvas.put(top + 3, right + 2, label)
    if title == "A QUESTION THAT USES A TOOL":
        model_bottom, tool_bottom = spans[1][2], spans[3][2]
        return_y = model_bottom + 2
        canvas.vline(COLUMNS[3], tool_bottom + 1, return_y, head="")
        canvas.hline(return_y, COLUMNS[1], COLUMNS[3], head="")
        canvas.corner(return_y, COLUMNS[3], "┘")
        canvas.corner(return_y, COLUMNS[1], "└")
        canvas.vline(COLUMNS[1], model_bottom + 1, return_y - 1, head="▲")
        canvas.put(return_y - 1, COLUMNS[1] + 2, "result, and the exchange is marked untrusted")
        top = return_y + 2
    else:
        top = spans[0][2] + 2

print("\n".join(line.ljust(W) for line in canvas.render().rstrip("\n").splitlines()))
