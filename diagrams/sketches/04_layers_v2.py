"""Sketch: section 4, the two layers. Callers on top, assistant_core's loop and the modules it calls, the two services they call below; no machine containers. Peer boxes share one size."""

from canvas import Canvas

CONTENT_WIDTH = 16
MODULE_X = [14, 38, 62, 86, 110]
LOOP_X = 62
canvas = Canvas(125, 32)


def place(y: int, center: int, lines: list[str]) -> tuple[int, int, int]:
    return canvas.box(y, center, [line.center(CONTENT_WIDTH) for line in lines])


bench = place(0, 38, ["benchmark", "on the laptop"])
component = place(0, 86, ["studio_assistant", "in the VM"])

canvas.frame(8, 1, 24, 123)
canvas.put(9, 3, "ASSISTANT_CORE: RUNS INSIDE EACH CALLER")
canvas.put(10, 3, "AND NEVER IMPORTS HOME ASSISTANT")
loop = place(11, LOOP_X, ["agent_loop.py", "the loop"])
labels = [["prompts.py", "system prompt"], ["memory.py", "empty for now"], ["router.py", "picks the route"], ["llm_client.py", "calls Ollama"], ["mcp_http.py", "calls the tools"]]
modules = [place(19, x, lines) for x, lines in zip(MODULE_X, labels)]

canvas.vline(38, 4, 5, head="")
canvas.corner(6, 38, "╰")
canvas.hline(6, 39, 57, head="")
canvas.corner(6, 58, "╮")
canvas.vline(58, 7, 10)
canvas.put(5, 40, "a question")
canvas.vline(86, 4, 5, head="")
canvas.corner(6, 86, "╯")
canvas.hline(6, 67, 85, head="")
canvas.corner(6, 66, "╭")
canvas.vline(66, 7, 10)
canvas.put(5, 64, "your text, chat log")

canvas.vline(LOOP_X, 15, 16, head="")
canvas.hline(17, MODULE_X[0] + 1, MODULE_X[-1] - 1, head="")
canvas.corner(17, MODULE_X[0], "╭")
canvas.corner(17, MODULE_X[-1], "╮")
for x in MODULE_X[1:-1]:
    canvas.corner(17, x, "┼" if x == LOOP_X else "┬")
for x in MODULE_X:
    canvas.vline(x, 18, 18)

place(28, 86, ["Ollama", "on the Mac"])
place(28, 110, ["web_search_mcp", "on the Mac"])
canvas.vline(86, 23, 27)
canvas.put(25, 88, "chat, tool list")
canvas.vline(110, 23, 27)
canvas.put(25, 112, "tool calls")

print("\n".join(line.ljust(len(canvas.grid[0])) for line in canvas.render().splitlines()))
