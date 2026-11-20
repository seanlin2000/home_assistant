"""Sketch: section 6, the setup script. The four steps as one chain; the file they write sits below, and each arrow into it carries the key it saves. Step 4 saves nothing."""

from canvas import Canvas

CONTENT_WIDTH = 24
ONBOARDING, ADDONS, INTEGRATIONS, PIPELINE = 16, 48, 80, 112
canvas = Canvas(129, 14)


def place(y: int, center: int, lines: list[str], stored: bool = False) -> tuple[int, int, int]:
    return canvas.box(y, center, [line.center(CONTENT_WIDTH) for line in lines], stored)


steps = [
    place(0, ONBOARDING, ["1. onboarding", "owner account, location", "a ten-year token"]),
    place(0, ADDONS, ["2. add-ons", "install and start five", "restarted if they die"]),
    place(0, INTEGRATIONS, ["3. integrations", "Whisper, Kokoro, add-ons", "and our agent"]),
    place(0, PIPELINE, ["4. pipeline", "Jarvis, built from", "Whisper, agent, Piper"]),
]
for (_, right, _), (left, _, _) in zip(steps, steps[1:]):
    canvas.hline(2, right + 1, left - 1)

env_file = place(10, ADDONS, [".env", "on the laptop"], stored=True)

canvas.vline(ONBOARDING, 5, 6, head="")
canvas.corner(7, ONBOARDING, "╰")
canvas.hline(7, ONBOARDING + 1, ADDONS - 7, head="")
canvas.corner(7, ADDONS - 6, "╮")
canvas.vline(ADDONS - 6, 8, 9)
canvas.put(5, ONBOARDING + 2, "HA_TOKEN")

canvas.vline(ADDONS, 5, 9)
canvas.put(5, ADDONS + 2, "HA_SAMBA_PASSWORD")

canvas.vline(INTEGRATIONS, 5, 6, head="")
canvas.corner(7, INTEGRATIONS, "╯")
canvas.hline(7, ADDONS + 7, INTEGRATIONS - 1, head="")
canvas.corner(7, ADDONS + 6, "╭")
canvas.vline(ADDONS + 6, 8, 9)
canvas.put(5, INTEGRATIONS + 2, "two Wyoming entry ids")

print("\n".join(line.ljust(len(canvas.grid[0])) for line in canvas.render().splitlines()))
