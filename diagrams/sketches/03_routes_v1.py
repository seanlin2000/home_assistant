"""Sketch: section 3, who calls what on port 8765. Every box has the same width and three lines."""

from canvas import Canvas

CONTENT_WIDTH = 20
CALLER_X = 13
ROUTE_X = 66
canvas = Canvas(83, 28)


def place(y: int, center: int, lines: list[str]) -> tuple[int, int, int]:
    return canvas.box(y, center, [line.center(CONTENT_WIDTH) for line in lines])


canvas.frame(0, 51, 27, 81)
canvas.put(1, 53, "WEB_SEARCH_MCP, PORT 8765")

agent = place(3, CALLER_X, ["conversation agent", "in the Home", "Assistant VM"])
health = place(15, CALLER_X, ["health check", "launchd, every", "5 minutes"])
browser = place(21, CALLER_X, ["a web page", "in a browser", "on the Wi-Fi"])
mcp = place(3, ROUTE_X, ["/mcp", "the eleven tools", "over MCP"])
exchanges = place(9, ROUTE_X, ["/exchanges", "one JSON Lines", "file per day"])
healthz = place(15, ROUTE_X, ["/healthz", "tool names, and", "ok or degraded"])
refused = place(21, ROUTE_X, ["421 Misdirected", "Host not this Mac,", "or a browser Origin"])

canvas.hline(5, agent[1] + 1, mcp[0] - 1)
canvas.put(4, agent[1] + 3, "tool calls")
canvas.vline(CALLER_X, agent[2] + 1, 10, head="")
canvas.corner(11, CALLER_X, "╰")
canvas.hline(11, CALLER_X + 1, exchanges[0] - 1)
canvas.put(10, agent[1] + 3, "one record per exchange")
canvas.hline(17, health[1] + 1, healthz[0] - 1)
canvas.put(16, health[1] + 3, "is it ours?")
canvas.hline(23, browser[1] + 1, refused[0] - 1)
canvas.put(22, browser[1] + 3, "any request")

print("\n".join(line.ljust(len(canvas.grid[0])) for line in canvas.render().splitlines()))
