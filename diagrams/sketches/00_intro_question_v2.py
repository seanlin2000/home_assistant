"""Sketch: Introduction, one spoken question end to end. Rows run in time order down the middle column, the stages the question passes through; the side columns hold what each stage calls, joined by pairs of opposing arrows instead of loops. Place is left to the system map above it."""

from canvas import Canvas

CONTENT_WIDTH = 26
BOX_WIDTH = CONTENT_WIDTH + 4
GAP = 27
LEFT = 1 + BOX_WIDTH // 2
MAIN = LEFT + BOX_WIDTH + GAP
RIGHT = MAIN + BOX_WIDTH + GAP
ROW_STEP = 7
canvas = Canvas(RIGHT + BOX_WIDTH // 2 + 2, ROW_STEP * 8)


def place(row: int, center: int, lines: list[str]) -> tuple[int, int, int]:
    return canvas.box(row * ROW_STEP, center, [line.center(CONTENT_WIDTH) for line in lines])


def pill(row: int, lines: list[str]) -> tuple[int, int, int]:
    x_left, x_right, y_bottom = place(row, MAIN, lines)
    for y in (row * ROW_STEP + 1, row * ROW_STEP + 2):
        canvas.grid[y][x_left] = "("
        canvas.grid[y][x_right] = ")"
    return x_left, x_right, y_bottom


def down(upper: tuple[int, int, int], label: str = "") -> None:
    canvas.vline(MAIN, upper[2] + 1, upper[2] + ROW_STEP - 4)
    if label:
        canvas.put(upper[2] + 2, MAIN + 2, label)


def pair(main_box: tuple[int, int, int], side_box: tuple[int, int, int], outward: str, inward: str) -> None:
    top = main_box[2] - 3
    if side_box[0] > main_box[1]:
        canvas.hline(top + 1, main_box[1] + 1, side_box[0] - 1, head="▶")
        canvas.hline(top + 2, main_box[1] + 1, side_box[0] - 1, head="◀")
        canvas.put(top, main_box[1] + 3, outward)
        canvas.put(top + 3, main_box[1] + 3, inward)
    else:
        canvas.hline(top + 1, side_box[1] + 1, main_box[0] - 1, head="◀")
        canvas.hline(top + 2, side_box[1] + 1, main_box[0] - 1, head="▶")
        canvas.put(top, main_box[0] - 2 - len(outward), outward)
        canvas.put(top + 3, main_box[0] - 2 - len(inward), inward)


you = pill(0, ["You: “Hey Jarvis, who won", "the Ballon d’Or?”"])
puck = place(1, MAIN, ["voice puck", "wakes on “Hey Jarvis”"])
stt = place(2, MAIN, ["speech to text", "in Home Assistant"])
whisper = place(2, LEFT, ["Whisper", "on the Mac’s GPU"])
intents = place(3, MAIN, ["intent matcher", "fixed sentence patterns"])
fixed = place(3, RIGHT, ["music or weather", "handled with no model"])
agent = place(4, MAIN, ["our agent", "studio_assistant"])
ollama = place(4, RIGHT, ["Ollama", "the language model"])
mcp = place(4, LEFT, ["our MCP server", "searches, reads pages"])
tts = place(5, MAIN, ["text to speech", "in Home Assistant"])
piper = place(5, LEFT, ["Piper", "the voice"])
heard = pill(6, ["You hear the answer;", "the puck keeps listening"])

down(you)
down(puck, "audio, over Wi-Fi")
down(stt, "“who won the Ballon d’Or?”")
down(intents, "no match")
down(agent, "the answer, streamed")
down(tts, "spoken, on the puck")

pair(stt, whisper, "audio", "text")
pair(agent, ollama, "the chat, tool list", "tool call, then answer")
pair(agent, mcp, "“Ballon d’Or winner”", "excerpts of the pages")
pair(tts, piper, "text", "audio")
canvas.hline(intents[2] - 2, intents[1] + 1, fixed[0] - 1)
canvas.put(intents[2] - 3, intents[1] + 3, "matches “play X”")

canvas.grid = canvas.grid[: heard[2] + 1]
print("\n".join(line.ljust(len(canvas.grid[0])) for line in canvas.render().splitlines()))
