"""Sketch v1: Development page, the path to main. Two places as columns, the laptop and GitHub; time runs down. The push fans out to the three CI jobs, which join at branch protection; a failure there sends the work back to the laptop."""

from canvas import Canvas

CONTENT_WIDTH = 26
LAPTOP, GITHUB = 18, 67
LAPTOP_RIGHT, GITHUB_LEFT, GITHUB_RIGHT = 32, 52, 81
FAN, JOIN = 42, 85
canvas = Canvas(90, 38)


def row(index: int) -> int:
    return 2 + index * 5


def place(index: int, center: int, lines: list[str]) -> None:
    canvas.box(row(index), center, [line.center(CONTENT_WIDTH) for line in lines])


canvas.container(0, 0, 37, 35, "the laptop")
canvas.container(0, 49, 37, 89, "GitHub")

place(0, LAPTOP, ["git commit", "on a worktree branch"])
place(1, LAPTOP, ["pre-commit hook", "lint, deslop, pytest"])
place(2, LAPTOP, ["git push,", "gh pr create"])
place(4, LAPTOP, ["fix on the branch,", "push the fix"])
place(1, GITHUB, ["checks job", "the hook's three steps"])
place(2, GITHUB, ["pr-description job", "pr-refs check and lint"])
place(3, GITHUB, ["docs job", "strict build, diagrams"])
place(4, GITHUB, ["branch protection", "jobs pass, threads closed"])
place(5, GITHUB, ["merge", "squash, a person clicks"])
place(6, GITHUB, ["pages.yml", "publishes the handbook"])

canvas.vline(LAPTOP, row(0) + 4, row(1) - 1)
canvas.vline(LAPTOP, row(1) + 4, row(2) - 1)

canvas.hline(row(2) + 2, LAPTOP_RIGHT + 1, FAN - 1, head="")
canvas.vline(FAN, row(1) + 2, row(3) + 2, head="")
canvas.corner(row(1) + 2, FAN, "╭")
canvas.corner(row(2) + 2, FAN, "┼")
canvas.corner(row(3) + 2, FAN, "╰")
for index in (1, 2, 3):
    canvas.hline(row(index) + 2, FAN + 1, GITHUB_LEFT - 1)

canvas.vline(JOIN, row(1) + 2, row(4) + 2, head="")
canvas.corner(row(1) + 2, JOIN, "╮")
canvas.corner(row(2) + 2, JOIN, "┤")
canvas.corner(row(3) + 2, JOIN, "┤")
canvas.corner(row(4) + 2, JOIN, "╯")
for index in (1, 2, 3):
    canvas.hline(row(index) + 2, GITHUB_RIGHT + 1, JOIN - 1, head="")
canvas.hline(row(4) + 2, GITHUB_RIGHT + 1, JOIN - 1, head="◀")

canvas.hline(row(4) + 2, LAPTOP_RIGHT + 1, GITHUB_LEFT - 1, head="◀")
canvas.put(row(4) + 1, 40, "fail")
canvas.vline(GITHUB, row(4) + 4, row(5) - 1)
canvas.put(row(4) + 4, GITHUB + 2, "pass")
canvas.vline(GITHUB, row(5) + 4, row(6) - 1)

print("\n".join(line.ljust(len(canvas.grid[0])) for line in canvas.render().splitlines()))
