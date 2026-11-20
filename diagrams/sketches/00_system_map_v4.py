W, H = 114, 56
grid = [[" "] * W for _ in range(H)]


def put(y: int, x: int, text: str) -> None:
    for i, ch in enumerate(text):
        assert grid[y][x + i] == " ", f"label {text!r} collides at ({y},{x + i}) with {grid[y][x + i]!r}"
        grid[y][x + i] = ch


def container(y1: int, x1: int, y2: int, x2: int, title: str, title_x: int) -> None:
    for x in range(x1, x2 + 1):
        grid[y1][x] = grid[y2][x] = "─"
    for y in range(y1, y2 + 1):
        grid[y][x1] = grid[y][x2] = "│"
    grid[y1][x1], grid[y1][x2], grid[y2][x1], grid[y2][x2] = "┌", "┐", "└", "┘"
    for i, ch in enumerate(f" {title} "):
        grid[y1][title_x + i] = ch


def box(y: int, center: int, lines: list[str]) -> tuple[int, int, int]:
    width = max(len(l) for l in lines) + 4
    x = center - width // 2
    rows = ["╭" + "─" * (width - 2) + "╮"] + ["│ " + l.center(width - 4) + " │" for l in lines] + ["╰" + "─" * (width - 2) + "╯"]
    for i, row in enumerate(rows):
        put(y + i, x, row)
    return x, x + width - 1, y + len(rows) - 1


def cross(y: int, x: int, along: str) -> str:
    here = grid[y][x]
    if here in "─│" and here != along:
        return "┼"
    assert here in " ─│", f"line {along} hits {here!r} at ({y},{x})"
    return along


def vline(x: int, y1: int, y2: int, up: bool = False) -> None:
    for y in range(y1, y2 + 1):
        grid[y][x] = cross(y, x, "│")
    grid[y2][x] = "▼"
    if up:
        grid[y1][x] = "▲"


def vline_up(x: int, y1: int, y2: int) -> None:
    for y in range(y1, y2 + 1):
        grid[y][x] = cross(y, x, "│")
    grid[y1][x] = "▲"


def hline(y: int, x1: int, x2: int, left: bool = False) -> None:
    for x in range(x1, x2 + 1):
        grid[y][x] = cross(y, x, "─")
    if left:
        grid[y][x1] = "◀"
    else:
        grid[y][x2] = "▶"


def fork(center: int, bottom: int, left: int, right: int) -> None:
    grid[bottom + 1][center] = "│"
    for x in range(left, right + 1):
        grid[bottom + 2][x] = "─"
    grid[bottom + 2][left], grid[bottom + 2][right], grid[bottom + 2][center] = "┌", "┐", "┴"


L1, L2, L3, L4, L5, L6 = 31, 44, 57, 66, 82, 97
TITLE_X = L1 + 3

container(0, 0, 47, W - 1, "YOUR STUDIO: everything inside stays local", 2)
container(8, 20, 45, W - 3, "MAC, ALWAYS ON", TITLE_X)
container(10, 23, 28, W - 5, "HOME ASSISTANT OS, a virtual machine", TITLE_X)
container(37, L5 - 13, 43, L5 + 9, "DOCKER", L5 - 11)

box(2, L1, ["Voice puck"])
box(2, 74, ["Laptop: deploys,", "reads logs over SSH"])
vline(L1, 5, 12, up=True)
put(6, L1 + 2, "audio in,")
put(7, L1 + 2, "spoken reply back")

_, stt_r, stt_b = box(13, L1, ["speech", "to text"])
int_l, int_r, int_b = box(13, (L2 + L3) // 2, ["intent", "matcher"])
agt_l, agt_r, agt_b = box(13, (L4 + L5) // 2, ["our", "agent"])
tts_l, tts_r, tts_b = box(13, L6, ["text to", "speech"])
hline(14, stt_r + 1, int_l - 1)
hline(14, int_r + 1, agt_l - 1)
put(15, int_r + 2, "no match")
hline(14, agt_r + 1, tts_l - 1)
put(15, agt_r + 4, "answer")
fork((L2 + L3) // 2, int_b, L2, L3)
fork((L4 + L5) // 2, agt_b, L4, L5)

vline(L1 - 2, stt_b + 1, 30)
vline_up(L1 + 2, stt_b + 1, 30)
vline(L2, int_b + 3, 22)
vline(L3, int_b + 3, 50)
vline(L4, agt_b + 3, 30)
vline(L5, agt_b + 3, 30)
vline(L6 - 2, tts_b + 1, 22)
vline_up(L6 + 2, tts_b + 1, 22)
put(29, L1 - 8, "audio")
put(29, L1 + 4, "text")
put(19, L2 + 2, "play X")
put(20, L3 - 8, "weather")
put(19, L4 + 2, "conversation,")
put(20, L4 + 2, "tool list")
put(19, L5 + 2, "tool calls")
put(20, L6 - 7, "text")
put(20, L6 + 4, "speech")

ma_l, _, ma_b = box(23, L2, ["Music Assistant"])
box(23, L6, ["Piper", "the voice"])
sonos_l, sonos_r, _ = box(23, 9, ["Sonos"])
hline(24, sonos_r + 1, ma_l - 1, left=True)
put(25, sonos_r + 2, "music")

box(31, L1, ["Whisper", "on the GPU"])
box(31, L4, ["Ollama"])
_, _, mcp_b = box(31, L5, ["MCP server:", "search and", "calculator"])
box(31, L6, ["health", "check"])
vline(L5, mcp_b + 1, 39)
put(38, L5 + 2, "search")
_, _, sx_b = box(40, L5, ["SearXNG"])

vline(L2, ma_b + 1, 50)
vline(L5, sx_b + 1, 50)
put(49, L2 - 19, "catalogue, stream")
put(49, L5 + 2, "search query")
put(53, 2, "LEAVES THE NETWORK")
box(51, L2, ["Spotify API"])
box(51, L3 + 2, ["Met.no"])
box(51, L5, ["public search engines"])

lines = ["".join(row) for row in grid]
print("\n".join(line.ljust(W) for line in lines if line.strip()))
