"""Sketch v1: Development page, the handbook. Two places as full-width rows, the laptop and GitHub; the same three columns in each row: what the handbook is built from, the build, and where it is read. A merged PR carries the pages from the laptop's row to GitHub's."""

from canvas import Canvas

CONTENT_WIDTH = 24
SOURCE, BUILD, READ = 18, 58, 98
canvas = Canvas(116, 19)


def place(y: int, center: int, lines: list[str], stored: bool = False) -> tuple[int, int, int]:
    return canvas.box(y, center, [line.center(CONTENT_WIDTH) for line in lines], stored)


def chain(y: int, boxes: list[tuple[list[str], bool]], first_label: str) -> None:
    edges = [place(y, center, lines, stored) for center, (lines, stored) in zip((SOURCE, BUILD, READ), boxes)]
    for (_, left_right, _), (right_left, _, _) in zip(edges, edges[1:]):
        canvas.hline(y + 2, left_right + 1, right_left - 1)
    gap_center = (edges[0][1] + edges[1][0]) // 2
    canvas.put(y + 1, gap_center - len(first_label) // 2 + 1, first_label)


canvas.container(0, 0, 7, 115, "the laptop")
canvas.container(11, 0, 18, 115, "GitHub")
chain(2, [(["operator_manual/", "your working copy"], True), (["mkdocs serve", "draws each diagram"], False), (["127.0.0.1:8000", "preview while editing"], False)], "on save")
chain(13, [(["main branch", "the latest pages"], True), (["pages.yml", "strict build, diagrams"], False), (["GitHub Pages", "the public handbook"], False)], "on merge")
canvas.vline(SOURCE, 6, 12)
canvas.put(9, SOURCE + 2, "merged PR")

print("\n".join(line.ljust(len(canvas.grid[0])) for line in canvas.render().splitlines()))
