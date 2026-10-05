"""Sketch v1: Hardware page, three places to run a service. The Mac is one container holding three columns, left to right in the direction calls travel: the UTM VM that calls, the native launchd agents it calls, and Docker's Linux VM that the tool server calls. The GPU sits under the native column because only native processes reach it."""

from canvas import Canvas

CONTENT_WIDTH = 22
HOME_ASSISTANT, NATIVE, DOCKER = 17, 66, 111
BUS, GPU_GUTTER = 38, 81
canvas = Canvas(130, 38)


def place(y: int, center: int, lines: list[str]) -> tuple[int, int, int]:
    return canvas.box(y, center, [line.center(CONTENT_WIDTH) for line in lines])


canvas.container(0, 0, 37, 129, "the Mac, 192.168.1.152")
canvas.container(2, 2, 29, 33, "UTM VM, 192.168.1.156")
canvas.container(2, 50, 29, 84, "launchd agents, on 0.0.0.0")
canvas.container(2, 96, 14, 126, "Docker Desktop's Linux VM")

place(16, HOME_ASSISTANT, ["Home Assistant", "port 80"])
place(22, HOME_ASSISTANT, ["add-ons", "Piper, Music Assistant"])
place(4, NATIVE, ["health check", "every 300 s"])
place(9, NATIVE, ["tool server", "port 8765"])
place(14, NATIVE, ["Kokoro, on the CPU", "port 10210"])
place(19, NATIVE, ["Whisper", "port 10300"])
place(24, NATIVE, ["Ollama", "port 11434"])
place(9, DOCKER, ["SearXNG", "127.0.0.1:8080 only"])
canvas.box(32, NATIVE, ["Apple Silicon GPU".center(30), "one pool of unified memory".center(30)])

canvas.hline(17, 30, BUS - 1, head="")
canvas.vline(BUS, 10, 25, head="")
canvas.corner(10, BUS, "╭")
canvas.corner(25, BUS, "╰")
canvas.corner(17, BUS, "┤")
for row, label in [(10, "MCP"), (15, "Wyoming"), (20, "Wyoming"), (25, "HTTP")]:
    if row not in (10, 25):
        canvas.corner(row, BUS, "├")
    canvas.hline(row, BUS + 1, NATIVE - 14)
    canvas.put(row - 1, BUS + 2, label)

canvas.hline(10, NATIVE + 13, DOCKER - 14)
canvas.put(9, NATIVE + 21, "loopback")

canvas.vline(NATIVE, 28, 31)
canvas.put(30, NATIVE + 2, "MLX")
canvas.hline(20, NATIVE + 13, GPU_GUTTER - 1, head="")
canvas.corner(20, GPU_GUTTER, "╮")
canvas.vline(GPU_GUTTER, 21, 31)
canvas.put(30, GPU_GUTTER + 2, "MLX")

print("\n".join(line.ljust(len(canvas.grid[0])) for line in canvas.render().splitlines()))
