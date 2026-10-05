"""Sketch v1: Development page, the environment. Left to right is the order things are derived: what we declare, what uv resolves it into, the environment uv builds, and the commands that run inside it. Every edge is the uv command that performs that step."""

from canvas import Canvas

CONTENT_WIDTH = 20
DECLARED, RESOLVED, BUILT, USED = 12, 57, 92, 127
DEPENDENCIES_ROW, PYTHON_ROW = 0, 5
canvas = Canvas(140, 9)


def place(y: int, center: int, lines: list[str], stored: bool = False) -> tuple[int, int, int]:
    return canvas.box(y, center, [line.center(CONTENT_WIDTH) for line in lines], stored)


def arrow(y: int, left_box_right: int, right_box_left: int, label: str) -> None:
    canvas.hline(y + 2, left_box_right + 1, right_box_left - 1)
    canvas.put(y + 1, (left_box_right + right_box_left) // 2 - len(label) // 2, label)


_, pyproject_right, _ = place(DEPENDENCIES_ROW, DECLARED, ["pyproject.toml", "direct dependencies"], stored=True)
lock_left, lock_right, _ = place(DEPENDENCIES_ROW, RESOLVED, ["uv.lock, committed", "every exact version"], stored=True)
venv_left, venv_right, venv_bottom = place(DEPENDENCIES_ROW, BUILT, ["the .venv folder", "git-ignored"], stored=True)
used_left, _, _ = place(DEPENDENCIES_ROW, USED, ["pytest, deslop,", "every Python command"])
_, version_right, _ = place(PYTHON_ROW, DECLARED, [".python-version", "3.12"], stored=True)
python_left, python_right, _ = place(PYTHON_ROW, RESOLVED, ["Python 3.12.14", "in uv's own folder"])

arrow(DEPENDENCIES_ROW, pyproject_right, lock_left, "uv lock")
arrow(DEPENDENCIES_ROW, lock_right, venv_left, "uv sync")
arrow(DEPENDENCIES_ROW, venv_right, used_left, "uv run")
arrow(PYTHON_ROW, version_right, python_left, "uv python install")
canvas.hline(PYTHON_ROW + 2, python_right + 1, BUILT - 1, head="")
canvas.corner(PYTHON_ROW + 2, BUILT, "╯")
canvas.vline(BUILT, venv_bottom + 1, PYTHON_ROW + 1, head="▲")

print("\n".join(line.ljust(len(canvas.grid[0])) for line in canvas.render().splitlines()))
