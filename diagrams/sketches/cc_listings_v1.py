"""Sketch: Current Working Changes, the Broadway listings from TodayTix to a spoken answer. One column per stage, left to right; every box the same size."""

from canvas import Canvas

CONTENT_WIDTH = 18
BOX_WIDTH = CONTENT_WIDTH + 4
GAP = 14
BOX_TOP = 4
canvas = Canvas(5 * BOX_WIDTH + 4 * GAP + 2, 9)


def center_of(column: int) -> int:
    return 1 + column * (BOX_WIDTH + GAP) + BOX_WIDTH // 2


def place(column: int, title: str, lines: list[str], stored: bool = False) -> tuple[int, int, int]:
    canvas.put(0, center_of(column) - len(title) // 2, title)
    return canvas.box(BOX_TOP, center_of(column), [line.center(CONTENT_WIDTH) for line in lines], stored)


todaytix = place(0, "outside the apartment", ["TodayTix listing", "about 3 MB"])
refresh = place(1, "nightly, 4:30 a.m.", ["listings-refresh", "keeps the shows"])
snapshot = place(2, "cache folder", ["broadway.json", "the snapshot"], stored=True)
tool = place(3, "tool server", ["broadway_shows", "filters and sorts"])
agent = place(4, "conversation agent", ["the model", "says the list"])

labels = ["one request", "written whole", "read per call", "ten shows"]
for (_, left_right, _), (right_left, _, _), label in zip([todaytix, refresh, snapshot, tool], [refresh, snapshot, tool, agent], labels):
    canvas.hline(BOX_TOP + 1, left_right + 1, right_left - 1)
    canvas.put(BOX_TOP - 1, left_right + 1 + (right_left - left_right - 1 - len(label)) // 2, label)

print("\n".join(line.ljust(len(canvas.grid[0])) for line in canvas.render().splitlines()))
