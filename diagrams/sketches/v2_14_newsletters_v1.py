"""Sketch: v2 personal-data tools, newsletters. One lane per path; the two question lanes differ in who speaks: the model, or the tool's own text."""

from canvas import Canvas

CONTENT = 20
COLUMNS = (13, 51, 89, 127)
W = 141

lanes = [
    (
        "EVERY HOUR: GMAIL TO THE STUDIO",
        [["Gmail label", "Newsletters"], ["pull job", "dmarc=pass only"], ["converter", "no ads, no emoji"], ["day folders", "markdown, 30 days"]],
        ["IMAP, read", "raw email", "sections"],
    ),
    (
        "LIST AND SUMMARIZE",
        [["your question", "what's new today?"], ["main model call", "picks a tool"], ["list or summarize", "reads day folders"], ["speaker", "Kokoro on the puck"]],
        ["", "tool call", None],
    ),
    (
        "READ ALOUD",
        [["your question", "read me Money Stuff"], ["main model call", "picks the tool"], ["newsletter_read", "one 3-minute part"], ["speaker", "no model between"]],
        ["", "tool call", "the part"],
    ),
]


def draw_model_round_trip(canvas: Canvas, spans: list[tuple[int, int, int]]) -> int:
    model_left, _, model_bottom = spans[1]
    return_y = model_bottom + 2
    canvas.vline(COLUMNS[2], model_bottom + 1, return_y, head="")
    canvas.hline(return_y, COLUMNS[1], COLUMNS[2], head="")
    canvas.corner(return_y, COLUMNS[2], "┘")
    canvas.corner(return_y, COLUMNS[1], "└")
    canvas.vline(COLUMNS[1], model_bottom + 1, return_y - 1, head="▲")
    canvas.put(return_y - 1, COLUMNS[1] + 2, "cleaned text, marked untrusted")
    answer_x, answer_y = model_left + 6, return_y + 2
    canvas.vline(answer_x, model_bottom + 1, answer_y, head="")
    canvas.hline(answer_y, answer_x, COLUMNS[3], head="")
    canvas.corner(answer_y, answer_x, "└")
    canvas.corner(answer_y, COLUMNS[3], "┘")
    canvas.vline(COLUMNS[3], model_bottom + 1, answer_y - 1, head="▲")
    canvas.put(answer_y - 1, COLUMNS[3] + 2, "its answer")
    return answer_y


canvas = Canvas(W, 34)
top = 0
for title, boxes, labels in lanes:
    canvas.put(top, 1, title)
    spans = []
    for index, (column, lines) in enumerate(zip(COLUMNS, boxes)):
        stored = title.startswith("EVERY HOUR") and index == len(boxes) - 1
        spans.append(canvas.box(top + 2, column, [line.center(CONTENT) for line in lines], stored=stored))
    for (_, right, _), (left, _, _), label in zip(spans, spans[1:], labels):
        if label is None:
            continue
        canvas.hline(top + 4, right + 1, left - 1)
        if label:
            canvas.put(top + 3, right + 2, label)
    last_row = draw_model_round_trip(canvas, spans) if title == "LIST AND SUMMARIZE" else spans[0][2]
    top = last_row + 2

print("\n".join(line.ljust(W) for line in canvas.render().rstrip("\n").splitlines()))
