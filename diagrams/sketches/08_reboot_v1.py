"""Sketch v1: Hardware page, coming back after a reboot. Time runs left to right. After the login the chain fans out into the three things macOS starts at login, one row each; the health check, which launchd runs, starts the VM that UTM hosts."""

from canvas import Canvas

CONTENT_WIDTH = 19
POWER, LOGIN, STARTER, STARTED, VM = 11, 39, 70, 98, 129
BUS = 54
DOCKER_ROW, LAUNCHD_ROW, HEALTH_ROW, UTM_ROW = 0, 5, 10, 15
canvas = Canvas(141, 19)


def place(y: int, center: int, lines: list[str]) -> tuple[int, int, int]:
    return canvas.box(y, center, [line.center(CONTENT_WIDTH) for line in lines])


place(LAUNCHD_ROW, POWER, ["power returns", "pmset autorestart"])
place(LAUNCHD_ROW, LOGIN, ["user logged in", "automatic login"])
place(DOCKER_ROW, STARTER, ["Docker Desktop", "login item"])
place(LAUNCHD_ROW, STARTER, ["launchd", "five agents"])
place(UTM_ROW, STARTER, ["UTM", "login item"])
place(DOCKER_ROW, STARTED, ["SearXNG", "unless-stopped"])
place(LAUNCHD_ROW, STARTED, ["Ollama, Whisper,", "Kokoro, tool server"])
place(HEALTH_ROW, STARTED, ["health check", "every 300 s"])
place(HEALTH_ROW, VM, ["the VM boots", "Home Assistant :80"])

canvas.hline(LAUNCHD_ROW + 1, POWER + 12, LOGIN - 12)
canvas.hline(LAUNCHD_ROW + 1, LOGIN + 12, BUS - 1, head="")
canvas.vline(BUS, DOCKER_ROW + 1, UTM_ROW + 1, head="")
canvas.corner(DOCKER_ROW + 1, BUS, "╭")
canvas.corner(LAUNCHD_ROW + 1, BUS, "┼")
canvas.corner(UTM_ROW + 1, BUS, "╰")
for row in (DOCKER_ROW, LAUNCHD_ROW, UTM_ROW):
    canvas.hline(row + 1, BUS + 1, STARTER - 12)
for row in (DOCKER_ROW, LAUNCHD_ROW):
    canvas.hline(row + 1, STARTER + 12, STARTED - 12)

canvas.vline(STARTER, LAUNCHD_ROW + 4, HEALTH_ROW, head="")
canvas.corner(HEALTH_ROW + 1, STARTER, "╰")
canvas.hline(HEALTH_ROW + 1, STARTER + 1, STARTED - 12)
canvas.hline(HEALTH_ROW + 1, STARTED + 12, VM - 12)
canvas.put(HEALTH_ROW, STARTED + 13, "starts")

canvas.hline(UTM_ROW + 1, STARTER + 12, VM - 1, head="")
canvas.corner(UTM_ROW + 1, VM, "╯")
canvas.vline(VM, HEALTH_ROW + 4, UTM_ROW, head="▲")
canvas.put(UTM_ROW, VM - 7, "hosts")

print("\n".join(line.ljust(len(canvas.grid[0])) for line in canvas.render().splitlines()))
