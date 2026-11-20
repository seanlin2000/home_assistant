"""Sketch: Conversation Agent, the question router, v2. The two rules are one box: a free check for wording that cannot be read two ways, and the model is asked only when it finds no match. Row 1 is the order of the checks; row 2 is the three routes. One crossing remains, because the rules and the model both reach search and calculate."""

from canvas import Canvas

CONTENT_WIDTH = 20
ROUTES_TOP = 11
canvas = Canvas(124, 16)


def place(y: int, center: int, lines: list[str]) -> tuple[int, int, int]:
    return canvas.box(y, center, [line.center(CONTENT_WIDTH) for line in lines])


def elbow(depart_x: int, turn_y: int, arrive_x: int) -> None:
    """A line down from the checks row, across at turn_y, and down into a route box."""
    canvas.vline(depart_x, 5, turn_y - 1, head="")
    leftward = arrive_x < depart_x
    canvas.corner(turn_y, depart_x, "╯" if leftward else "╰")
    canvas.hline(turn_y, min(depart_x, arrive_x) + 1, max(depart_x, arrive_x) - 1, head="")
    canvas.corner(turn_y, arrive_x, "╭" if leftward else "╮")
    canvas.vline(arrive_x, turn_y + 1, ROUTES_TOP - 1)


question = place(0, 13, ["your question", "the latest thing", "you said"])
rules = place(0, 45, ["the rules", "a pattern match", "costs nothing"])
model = place(0, 109, ["ask the model", "one quick call", "about a second"])
search = place(ROUTES_TOP, 45, ["search", "a SEARCH note", "in the system prompt"])
calculate = place(ROUTES_TOP, 77, ["calculate", "a CALCULATE note", "in the system prompt"])
answer = place(ROUTES_TOP, 109, ["answer", "nothing added", "or if the call fails"])

canvas.hline(2, question[1] + 1, rules[0] - 1)
canvas.hline(2, rules[1] + 1, model[0] - 1)
canvas.put(1, rules[1] + 3, "no match")

canvas.vline(45, 5, ROUTES_TOP - 1)
canvas.put(6, 45 - 2 - len('"look it up"'), '"look it up"')
elbow(97, 7, 53)
elbow(49, 8, 73)
canvas.put(6, 51, '"15% of $80"')
elbow(103, 9, 81)
canvas.vline(109, 5, ROUTES_TOP - 1)

print("\n".join(line.ljust(len(canvas.grid[0])) for line in canvas.render().splitlines()))
