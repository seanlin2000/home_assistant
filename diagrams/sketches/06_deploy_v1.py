"""Sketch: section 6, deploying the custom component. The deploy as one chain of five steps; a copy that fails halfway drops out of the swap step and puts the old folder back."""

from canvas import Canvas

CONTENT_WIDTH = 18
CENTERS = [13, 41, 69, 97, 125]
SWAP = CENTERS[2]
canvas = Canvas(138, 14)


def place(y: int, center: int, lines: list[str]) -> tuple[int, int, int]:
    return canvas.box(y, center, [line.center(CONTENT_WIDTH) for line in lines])


labels = [
    ["1. stage", "our component with", "assistant_core"],
    ["2. mount", "the VM's /config", "share over SMB"],
    ["3. swap folders", "old one kept aside", "until copied"],
    ["4. restart", "Home Assistant", "through its API"],
    ["5. wait", "poll /api/ until", "it answers"],
]
steps = [place(0, center, lines) for center, lines in zip(CENTERS, labels)]
for (_, right, _), (left, _, _) in zip(steps, steps[1:]):
    canvas.hline(2, right + 1, left - 1)

place(9, SWAP, ["restore", "the old folder", "and stop"])
canvas.vline(SWAP, 5, 8)
canvas.put(6, SWAP + 2, "copy fails")

print("\n".join(line.ljust(len(canvas.grid[0])) for line in canvas.render().splitlines()))
