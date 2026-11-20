"""Sketch: section 3, the URL guard. Every box has the same width and three lines."""

from canvas import Canvas

CONTENT_WIDTH = 20
BOX_WIDTH = CONTENT_WIDTH + 4
GAP = 8
CHANNEL_Y = 6
canvas = Canvas(156, 13)


def center_of(column: int) -> int:
    return 1 + column * (BOX_WIDTH + GAP) + BOX_WIDTH // 2


def place(y: int, column: int, lines: list[str]) -> tuple[int, int, int]:
    return canvas.box(y, center_of(column), [line.center(CONTENT_WIDTH) for line in lines])


url = place(0, 0, ["a URL", "from the model or", "a search result"])
name = place(0, 1, ["check the URL", "http(s), not local", "every address public"])
connect = place(0, 2, ["connect", "to a checked address", "real name in TLS"])
peer = place(0, 3, ["check the peer", "the socket's address", "is public"])
read = place(0, 4, ["read the answer", "HTML only", "stop past 2 MB"])
refused = place(8, 2, ["refused", "UnsafeUrl", "nothing is read"])
redirect = place(8, 4, ["a redirect", "new URL goes back", "to check the URL"])

for (_, left_right, _), (right_left, _, _) in [(url, name), (name, connect), (connect, peer), (peer, read)]:
    canvas.hline(2, left_right + 1, right_left - 1)

refused_center = center_of(2)
canvas.vline(center_of(1), 5, CHANNEL_Y, head="")
canvas.corner(CHANNEL_Y, center_of(1), "╰")
canvas.hline(CHANNEL_Y, center_of(1) + 1, refused_center - 5, head="")
canvas.corner(CHANNEL_Y, refused_center - 4, "╮")
canvas.vline(refused_center - 4, CHANNEL_Y + 1, 7)
canvas.put(5, center_of(1) + 2, "no")

canvas.vline(center_of(3), 5, CHANNEL_Y, head="")
canvas.corner(CHANNEL_Y, center_of(3), "╯")
canvas.hline(CHANNEL_Y, refused_center + 5, center_of(3) - 1, head="")
canvas.corner(CHANNEL_Y, refused_center + 4, "╭")
canvas.vline(refused_center + 4, CHANNEL_Y + 1, 7)
canvas.put(5, center_of(3) + 2, "no")

canvas.vline(center_of(4), 5, 7)
canvas.put(6, center_of(4) + 2, "a 3xx answer")

print("\n".join(line.ljust(len(canvas.grid[0])) for line in canvas.render().splitlines()))
