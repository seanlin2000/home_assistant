"""Sketch: section 6, the Assist pipeline. The four stages the setup script picks sit in one row; the puck above them sends audio into the first and hears the last. A matched sentence stays in the row; an unmatched one drops to our agent and rejoins at text to speech."""

from canvas import Canvas

CONTENT_WIDTH = 18
STT, MATCHER, BUILTIN, TTS = 14, 48, 82, 116
PUCK = 65
canvas = Canvas(140, 20)


def place(y: int, center: int, lines: list[str]) -> tuple[int, int, int]:
    return canvas.box(y, center, [line.center(CONTENT_WIDTH) for line in lines])


place(0, PUCK, ["voice puck", "or the Assist app"])
stages = [
    place(10, STT, ["speech to text", "stt.mlx_whisper"]),
    place(10, MATCHER, ["intent matcher", "fixed sentences"]),
    place(10, BUILTIN, ["built-in handler", "music, weather"]),
    place(10, TTS, ["text to speech", "tts.piper"]),
]
place(16, BUILTIN, ["our agent", "studio_assistant"])

canvas.vline(PUCK - 6, 4, 5, head="")
canvas.corner(6, PUCK - 6, "╯")
canvas.hline(6, STT + 1, PUCK - 7, head="")
canvas.corner(6, STT, "╭")
canvas.vline(STT, 7, 9)
canvas.put(7, STT + 2, "audio")

canvas.vline(PUCK + 5, 4, 5, head="▲")
canvas.corner(6, PUCK + 5, "╰")
canvas.hline(6, PUCK + 6, TTS - 1, head="")
canvas.corner(6, TTS, "╮")
canvas.vline(TTS, 7, 9, head="")
canvas.put(7, TTS + 2, "speech")

for (_, right, _), (left, _, _), label in zip(stages, stages[1:], ["text", "match", "reply"]):
    canvas.hline(12, right + 1, left - 1)
    canvas.put(11, right + 2, label)

canvas.vline(MATCHER, 14, 17, head="")
canvas.corner(18, MATCHER, "╰")
canvas.hline(18, MATCHER + 1, BUILTIN - 12)
canvas.put(15, MATCHER + 2, "no match")

canvas.hline(18, BUILTIN + 11, TTS - 1, head="")
canvas.corner(18, TTS, "╯")
canvas.vline(TTS, 14, 17, head="▲")
canvas.put(15, TTS + 2, "the answer, streamed")

print("\n".join(line.ljust(len(canvas.grid[0])) for line in canvas.render().splitlines()))
