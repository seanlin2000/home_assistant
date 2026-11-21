"""Sketch: v2 subway arrivals. One lane for the question, one for what the tool does on each call, one for the station table built by hand; the table feeds the
arrivals step from below."""

from canvas import Canvas

CONTENT = 20
COLUMNS = (13, 51, 89, 127)
W = 141
QUESTION_LANE = "A QUESTION"
TOOL_LANE = "INSIDE SUBWAY_ARRIVALS, EACH CALL"
TABLE_LANE = "BY HAND, WHEN MTA CHANGES ITS STATIONS"

lanes = [
    (
        QUESTION_LANE,
        [["your question", "next 7, Queensboro?"], ["main model call", "picks the tool"], ["subway_arrivals", "station, line, way"], ["speaker", "Kokoro on the puck"]],
        ["", "tool call", None],
    ),
    (
        TOOL_LANE,
        [["MTA realtime feeds", "8 feeds and alerts"], ["feed cache", "20 s, stale to 5 min"], ["arrivals", "live trips only"], ["text block", "next 3 each way"]],
        ["whole feeds", "decoded", "groups"],
    ),
    (
        TABLE_LANE,
        [["data.ny.gov", "MTA stations list"], ["build_stations", "grouped by complex"], ["stations.json", "checked in"]],
        ["station rows", "JSON"],
    ),
]
STORED = {(TOOL_LANE, 1), (TABLE_LANE, 2)}


def draw_model_round_trip(canvas: Canvas, spans: list[tuple[int, int, int]]) -> int:
    model_left, _, model_bottom = spans[1]
    return_y = model_bottom + 2
    canvas.vline(COLUMNS[2], model_bottom + 1, return_y, head="")
    canvas.hline(return_y, COLUMNS[1], COLUMNS[2], head="")
    canvas.corner(return_y, COLUMNS[2], "┘")
    canvas.corner(return_y, COLUMNS[1], "└")
    canvas.vline(COLUMNS[1], model_bottom + 1, return_y - 1, head="▲")
    canvas.put(return_y - 1, COLUMNS[1] + 2, "arrivals, marked untrusted")
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


canvas = Canvas(W, 32)
top = 0
arrivals_bottom = 0
for title, boxes, labels in lanes:
    spans = draw_lane(canvas, top, title, boxes, labels)
    if title == TOOL_LANE:
        arrivals_bottom = spans[2][2]
    if title == TABLE_LANE:
        canvas.vline(COLUMNS[2], arrivals_bottom + 1, spans[2][2] - 4, head="▲")
        canvas.put(arrivals_bottom + 2, COLUMNS[2] + 2, "stop IDs, usual lines")
    last_row = draw_model_round_trip(canvas, spans) if title == QUESTION_LANE else spans[0][2]
    top = last_row + 2

print("\n".join(line.ljust(W) for line in canvas.render().rstrip("\n").splitlines()))
