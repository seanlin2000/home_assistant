"""Sketch: section 6, the virtual machine. Traffic comes down from the Wi-Fi straight into the VM's own address; control grows up from the Mac: UTM boots the VM, the Supervisor runs every container. No crossings."""

from canvas import Canvas

CONTENT_WIDTH = 19
CENTERS = [18, 44, 70, 96, 122]
PIPER, MUSIC, OTHERS, CORE, SAMBA = CENTERS
canvas = Canvas(141, 33)


def place(y: int, center: int, lines: list[str]) -> tuple[int, int, int]:
    return canvas.box(y, center, [line.center(CONTENT_WIDTH) for line in lines])


place(0, CORE, ["voice puck", "on the Wi-Fi"])
place(0, SAMBA, ["laptop", "on the Wi-Fi"])

canvas.container(7, 1, 32, 139, "the Mac, 192.168.1.152")
canvas.container(9, 4, 24, 136, "Home Assistant OS, a virtual machine with its own address: 192.168.1.156")

containers = [
    (PIPER, ["Piper", "text to speech"]),
    (MUSIC, ["Music Assistant", "plays music"]),
    (OTHERS, ["openWakeWord", "and ESPHome"]),
    (CORE, ["Home Assistant Core", "web UI and API"]),
    (SAMBA, ["Samba", "/config as a share"]),
]
for center, lines in containers:
    place(12, center, lines)
place(19, OTHERS, ["Supervisor", "runs each container"])
place(27, OTHERS, ["UTM", "runs the VM"])

canvas.vline(CORE, 4, 11)
canvas.put(5, CORE - 7, "audio")
canvas.vline(SAMBA, 4, 11)
canvas.put(5, SAMBA + 2, "SMB")
canvas.vline(SAMBA - 6, 4, 4, head="")
canvas.corner(5, SAMBA - 6, "╯")
canvas.hline(5, CORE + 6, SAMBA - 7, head="")
canvas.corner(5, CORE + 5, "╭")
canvas.vline(CORE + 5, 6, 11)
canvas.put(6, CORE + 7, "HTTP :80")

canvas.hline(17, PIPER + 1, SAMBA - 1, head="")
canvas.corner(17, PIPER, "╰")
canvas.corner(17, SAMBA, "╯")
for x in (MUSIC, CORE):
    canvas.corner(17, x, "┴")
canvas.corner(17, OTHERS, "┼")
for x in CENTERS:
    canvas.vline(x, 16, 16, head="▲")
canvas.vline(OTHERS, 18, 18, head="")

canvas.vline(OTHERS, 23, 26, head="▲")
canvas.put(25, OTHERS + 2, "boots")

print("\n".join(line.ljust(len(canvas.grid[0])) for line in canvas.render().splitlines()))
