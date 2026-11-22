"""Sketch: v2 stock quotes. One lane for the question, one for what the tool does on each call; the market view reads three funds through the same steps."""

from canvas import Canvas

CONTENT = 20
COLUMNS = (13, 51, 89, 127)
W = 141
QUESTION_LANE = "A QUESTION"
TOOL_LANE = "INSIDE STOCK_QUOTE, EACH CALL"

lanes = [
    (
        QUESTION_LANE,
        [["your question", "how's Apple doing?"], ["main model call", "picks the tool"], ["stock_quote", "one company"], ["speaker", "voice on the puck"]],
        ["", "tool call", None],
    ),
    (
        TOOL_LANE,
        [["name to ticker", "table, else search"], ["quote cache", "60 s, or to the open"], ["Finnhub", "quote and metrics"], ["text block", "rounded, as-of time"]],
        ["ticker", "on a miss", "numbers"],
    ),
]
STORED = {(TOOL_LANE, 1)}


def draw_model_round_trip(canvas: Canvas, spans: list[tuple[int, int, int]]) -> int:
    model_left, _, model_bottom = spans[1]
    return_y = model_bottom + 2
    canvas.vline(COLUMNS[2], model_bottom + 1, return_y, head="")
    canvas.hline(return_y, COLUMNS[1], COLUMNS[2], head="")
    canvas.corner(return_y, COLUMNS[2], "┘")
    canvas.corner(return_y, COLUMNS[1], "└")
    canvas.vline(COLUMNS[1], model_bottom + 1, return_y - 1, head="▲")
    canvas.put(return_y - 1, COLUMNS[1] + 2, "quote, marked untrusted")
    answer_x, answer_y = model_left + 6, return_y + 2
    canvas.vline(answer_x, model_bottom + 1, answer_y, head="")
    canvas.hline(answer_y, answer_x, COLUMNS[3], head="")
    canvas.corner(answer_y, answer_x, "└")
    canvas.corner(answer_y, COLUMNS[3], "┘")
    canvas.vline(COLUMNS[3], model_bottom + 1, answer_y - 1, head="▲")
    canvas.put(answer_y - 1, COLUMNS[3] + 2, "its answer")
    return answer_y


def draw_lane(canvas: Canvas, top: int, title: str, boxes: list[list[str]], labels: list[str | None]) -> list[tuple[int, int, int]]:
    canvas.put(top, 1, title)
    spans = [canvas.box(top + 2, column, [line.center(CONTENT) for line in lines], stored=(title, index) in STORED) for index, (column, lines) in enumerate(zip(COLUMNS, boxes))]
    for (_, right, _), (left, _, _), label in zip(spans, spans[1:], labels):
        if label is None:
            continue
        canvas.hline(top + 4, right + 1, left - 1)
        if label:
            canvas.put(top + 3, right + 2, label)
    return spans


canvas = Canvas(W, 20)
top = 0
for title, boxes, labels in lanes:
    spans = draw_lane(canvas, top, title, boxes, labels)
    last_row = draw_model_round_trip(canvas, spans) if title == QUESTION_LANE else spans[0][2]
    top = last_row + 2

print("\n".join(line.ljust(W) for line in canvas.render().rstrip("\n").splitlines()))
