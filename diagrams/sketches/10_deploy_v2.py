"""Sketch v2: Operations page, deploy. Two places as columns, the laptop and the Mac mini; time runs down. The success path is the mini's left lane, the two failure branches its right lane. What happens after the rollback, and the exit codes, live in a table under the figure."""

from canvas import Canvas

CONTENT_WIDTH = 24
LAPTOP, MAIN, FAILURE = 17, 65, 104
LAPTOP_RIGHT, MAIN_LEFT, FAILURE_LEFT = 30, 51, 90
canvas = Canvas(121, 28)


def row(index: int) -> int:
    return 2 + index * 5


def place(index: int, center: int, lines: list[str]) -> None:
    canvas.box(row(index), center, [line.center(CONTENT_WIDTH) for line in lines])


def branch(start: int, index: int, exit_x: int, target_left: int, label: str) -> None:
    canvas.vline(exit_x, row(start) + 4, row(index) + 1, head="")
    canvas.corner(row(index) + 2, exit_x, "╰")
    canvas.hline(row(index) + 2, exit_x + 1, target_left - 1)
    canvas.put(row(index) + 1, exit_x + 2, label)


canvas.container(0, 0, 27, 33, "the laptop")
canvas.container(0, 48, 27, 120, "the Mac mini")

place(0, LAPTOP, ["mini.sh deploy", "clean tree, pushed"])
place(0, MAIN, ["check out the commit,", "maintenance flag on"])
place(1, MAIN, ["uv sync, preflight,", "pytest -q -x"])
place(1, FAILURE, ["old commit back,", "flag stays on"])
place(2, MAIN, ["restart only what", "the change touched"])
place(2, LAPTOP, ["smoke test: 12 percent", "of 250, expects 30"])
place(3, MAIN, ["record as last good,", "flag off: live"])
place(4, FAILURE, ["roll back to the", "last good commit"])

canvas.hline(row(0) + 2, LAPTOP_RIGHT + 1, MAIN_LEFT - 1)
canvas.put(row(0) + 1, 39, "ssh")
canvas.vline(MAIN, row(0) + 4, row(1) - 1)
canvas.hline(row(1) + 2, MAIN + 14, FAILURE_LEFT - 1)
canvas.put(row(1) + 1, MAIN + 16, "fail")
canvas.vline(MAIN, row(1) + 4, row(2) - 1)
canvas.put(row(1) + 4, MAIN + 2, "pass")
canvas.hline(row(2) + 2, LAPTOP_RIGHT + 1, MAIN_LEFT - 1, head="◀")

branch(2, 3, LAPTOP + 3, MAIN_LEFT, "pass")
branch(2, 4, LAPTOP - 3, FAILURE_LEFT, "fail")

print("\n".join(line.ljust(len(canvas.grid[0])) for line in canvas.render().splitlines()))
