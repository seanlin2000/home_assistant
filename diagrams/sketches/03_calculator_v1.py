"""Sketch: section 3, the calculate tool. Every box has the same width and three lines."""

from canvas import Canvas

CONTENT_WIDTH = 20
BOX_WIDTH = CONTENT_WIDTH + 4
GAP = 8
CHANNEL_Y = 6
canvas = Canvas(153, 13)


def center_of(column: int) -> int:
    return 1 + column * (BOX_WIDTH + GAP) + BOX_WIDTH // 2


def place(y: int, column: int, lines: list[str]) -> tuple[int, int, int]:
    return canvas.box(y, center_of(column), [line.center(CONTENT_WIDTH) for line in lines])


expression = place(0, 0, ["an expression", "from the model", "$3,500 * 1.05 * 12"])
normalize = place(0, 1, ["normalize", "drop $ and commas", "15% becomes 15/100"])
parse = place(0, 2, ["parse", "into a Python", "syntax tree"])
evaluate = place(0, 3, ["evaluate the tree", "allowed syntax only", "numbers in limits"])
answer = place(0, 4, ["the answer", "result: 44,100", "plus a spoken line"])
error = place(8, 2, ["Calculator error", "returned as text", "so the model retries"])

for (_, left_right, _), (right_left, _, _) in [(expression, normalize), (normalize, parse), (parse, evaluate), (evaluate, answer)]:
    canvas.hline(2, left_right + 1, right_left - 1)

error_center = center_of(2)
canvas.vline(error_center - 4, 5, 7)
canvas.put(6, error_center - 16, "not valid")

canvas.vline(center_of(3), 5, CHANNEL_Y, head="")
canvas.corner(CHANNEL_Y, center_of(3), "╯")
canvas.hline(CHANNEL_Y, error_center + 5, center_of(3) - 1, head="")
canvas.corner(CHANNEL_Y, error_center + 4, "╭")
canvas.vline(error_center + 4, CHANNEL_Y + 1, 7)
canvas.put(5, center_of(3) + 2, "not allowed")

print("\n".join(line.ljust(len(canvas.grid[0])) for line in canvas.render().splitlines()))
