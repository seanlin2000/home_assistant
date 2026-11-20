"""Sketch v1: Operations page, bootstrap. Two places as columns, the laptop and the Mac mini; one row per thing the laptop sends, with the mini.sh command that sends it on the arrow."""

from canvas import Canvas

CONTENT_WIDTH = 22
LAPTOP, MINI = 15, 77
ROWS = [
    (["bootstrap_mac.sh", "and the Brewfile"], False, "mini.sh bootstrap", ["detached checkout,", ".venv, agents, SearXNG"], False),
    ([".env", "addresses, secrets"], True, "mini.sh push-env", [".env", "mode 600"], True),
    (["~/.ollama/models", "the tested model"], True, "mini.sh push-models", ["~/.ollama/models", "the same blobs"], True),
    (["Home Assistant.utm", "the configured VM"], True, "mini.sh push-vm", ["the VM in UTM,", "keeps its 4 GB"], False),
]
canvas = Canvas(93, 23)


def place(y: int, center: int, lines: list[str], stored: bool) -> tuple[int, int, int]:
    return canvas.box(y, center, [line.center(CONTENT_WIDTH) for line in lines], stored)


canvas.container(0, 0, 22, 30, "the laptop")
canvas.container(0, 62, 22, 92, "the Mac mini")
for index, (source, source_stored, command, target, target_stored) in enumerate(ROWS):
    y = 2 + index * 5
    _, source_right, _ = place(y, LAPTOP, source, source_stored)
    target_left, _, _ = place(y, MINI, target, target_stored)
    canvas.hline(y + 2, source_right + 1, target_left - 1)
    canvas.put(y + 1, 46 - len(command) // 2, command)

print("\n".join(line.ljust(len(canvas.grid[0])) for line in canvas.render().splitlines()))
