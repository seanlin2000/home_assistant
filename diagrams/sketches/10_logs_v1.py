"""Sketch v1: Operations page, logs. Places as columns: the Home Assistant VM, the Mac's own processes, the log folder, and the laptop. One row per writer, each writing its file in the folder; dashed lines are the laptop's pull, which gathers the folder and Home Assistant's in-memory debug runs into one mirror."""

from canvas import Canvas

CONTENT_WIDTH = 20
VM, NATIVE, FOLDER, LAPTOP = 16, 54, 90, 133
BUS = 111
canvas = Canvas(148, 30)


def row(index: int) -> int:
    return 4 + (index - 1) * 6


def place(index: int, center: int, lines: list[str], stored: bool = False) -> tuple[int, int, int]:
    return canvas.box(row(index), center, [line.center(CONTENT_WIDTH) for line in lines], stored)


canvas.container(0, 0, 29, 114, "the Mac mini")
canvas.container(2, 2, 15, 31, "Home Assistant VM")
canvas.container(8, 73, 27, 108, "~/Library/Logs/studio-assistant")
canvas.container(2, 118, 21, 147, "the laptop")

_, debug_right, _ = place(1, VM, ["Assist debug runs", "kept in memory"])
_, component_right, _ = place(2, VM, ["conversation agent", "after each answer"])
tool_left, tool_right, _ = place(2, NATIVE, ["tool server", "POST /exchanges"])
_, launchd_right, _ = place(3, NATIVE, ["launchd", "each agent's output"])
_, health_right, _ = place(4, NATIVE, ["health check", "every 300 s"])
files = [
    place(2, FOLDER, ["exchanges/", "one file per day"], stored=True),
    place(3, FOLDER, ["ollama.log, mcp.log,", "whisper.log, ..."], stored=True),
    place(4, FOLDER, ["health.json", "health.jsonl"], stored=True),
]
pull_left, _, pull_bottom = place(1, LAPTOP, ["mini.sh logs", "rsync, websocket"])
_, _, mirror_bottom = place(2, LAPTOP, ["logs/mini/", "the mirror"], stored=True)
place(3, LAPTOP, ["ops_report.py", "the report"])

canvas.hline(row(2) + 2, component_right + 1, tool_left - 1)
canvas.put(row(2) + 1, 33, "a record")
for index, writer_right in [(2, tool_right), (3, launchd_right), (4, health_right)]:
    file_left = FOLDER - 12
    canvas.hline(row(index) + 2, writer_right + 1, file_left - 1)

canvas.hline(row(1) + 2, debug_right + 1, pull_left - 1, dashed=True)
canvas.vline(BUS, row(1) + 3, row(4) + 1, head="", dashed=True)
canvas.corner(row(1) + 2, BUS, "┬")
canvas.corner(row(4) + 2, BUS, "╯")
for index, (_, file_right, _) in enumerate(files, start=2):
    canvas.hline(row(index) + 2, file_right + 1, BUS - 1, head="", dashed=True)
canvas.corner(row(2) + 2, BUS, "┤")
canvas.corner(row(3) + 2, BUS, "┤")
canvas.vline(LAPTOP, pull_bottom + 1, row(2) - 1)
canvas.vline(LAPTOP, mirror_bottom + 1, row(3) - 1)

print("\n".join(line.ljust(len(canvas.grid[0])) for line in canvas.render().splitlines()))
