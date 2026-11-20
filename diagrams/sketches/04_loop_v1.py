"""Sketch: Conversation Agent, inside the loop. Row 1 is the path through one exchange, with the model call and the tool run joined by a pair of opposing arrows instead of an outer loop; row 2 is the two ways the loop ends."""

from canvas import Canvas

CONTENT_WIDTH = 24
canvas = Canvas(124, 15)


def place(y: int, center: int, lines: list[str]) -> tuple[int, int, int]:
    return canvas.box(y, center, [line.center(CONTENT_WIDTH) for line in lines])


setup = place(0, 15, ["set up", "system prompt, history", "tool list, route"])
call = place(0, 55, ["call the model", "speak text as it comes", "stops near 200 words"])
tools = place(0, 107, ["run the tools", "filler before the first", "results join the chat"])
done = place(10, 35, ["done", "the answer was spoken", "while it streamed"])
last = place(10, 83, ["one last answer", "a notice: no more tools", "answer from what it has"])

canvas.hline(2, setup[1] + 1, call[0] - 1)
canvas.hline(2, call[1] + 1, tools[0] - 1)
canvas.put(1, call[1] + 5, "asks for tools")
canvas.hline(3, call[1] + 1, tools[0] - 1, head="◀")
canvas.put(4, call[1] + 5, "the results")

canvas.vline(47, call[2] + 1, 6, head="")
canvas.corner(7, 47, "╯")
canvas.hline(7, 36, 46, head="")
canvas.corner(7, 35, "╭")
canvas.vline(35, 8, 9)
canvas.put(6, 47 - 2 - len("no tool calls"), "no tool calls")

canvas.vline(62, call[2] + 1, 6, head="")
canvas.corner(7, 62, "╰")
canvas.hline(7, 63, 82, head="")
canvas.corner(7, 83, "╮")
canvas.vline(83, 8, 9)
canvas.put(6, 64, "tools again after 4 rounds")

print("\n".join(line.ljust(len(canvas.grid[0])) for line in canvas.render().splitlines()))
