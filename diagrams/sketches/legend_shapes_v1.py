"""Sketch v1: Diagram Legend, the shapes. The three shapes the handbook's figures use, side by side with no arrows between them: a rounded box for anything that runs, a cylinder for anything stored, a stadium for what a person says or does."""

from canvas import Canvas

CONTENT_WIDTH = 24
RUNS, STORED, PERSON = 15, 47, 79
canvas = Canvas(94, 6)


def place(center: int, lines: list[str], stored: bool = False) -> tuple[int, int, int]:
    return canvas.box(1, center, [line.center(CONTENT_WIDTH) for line in lines], stored)


place(RUNS, ["anything that runs:", "a service, device, API"])
place(STORED, ["anything stored:", "a file, database, log"], stored=True)
left, right, _ = place(PERSON, ["a person:", "what you say or do"])
for y in (2, 3):
    canvas.grid[y][left] = "("
    canvas.grid[y][right] = ")"

print("\n".join(line.ljust(len(canvas.grid[0])) for line in canvas.render().splitlines()))
