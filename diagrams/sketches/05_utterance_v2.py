"""Sketch v2: section 5, one question end to end. Each engine link is two arrows, down with what the stage sends and up with what comes back. Place-based like the system map: the device above the Mac, the VM's pipeline as one row, each speech engine directly below the stage that calls it."""

from canvas import Canvas

CONTENT_WIDTH = 20
STT, MIDDLE, TTS = 18, 64, 110
KOKORO_DOWN, KOKORO_UP, PIPER_DOWN, PIPER_UP = 99, 104, 114, 119
WHISPER_DOWN, WHISPER_UP = 13, 23
KOKORO, PIPER = 100, 120
DEVICE_OUT, DEVICE_IN = 58, 70
canvas = Canvas(140, 34)


def place(y: int, center: int, lines: list[str]) -> tuple[int, int, int]:
    return canvas.box(y, center, [line.center(CONTENT_WIDTH) for line in lines])


place(0, MIDDLE, ["Puck", ""])
canvas.container(6, 0, 33, 139, "the Mac, 192.168.1.152")
canvas.container(8, 3, 25, 136, "Home Assistant OS, a VM at 192.168.1.156")

stages = [
    place(13, STT, ["speech to text", "stt.mlx_whisper"]),
    place(13, MIDDLE, ["intent matcher", "or our agent"]),
    place(13, TTS, ["text to speech", "tts.piper or kokoro"]),
]
place(20, PIPER, ["Piper add-on", "Wyoming, in the VM"])
place(28, STT, ["Whisper, on the GPU", "Wyoming, port 10300"])
place(28, KOKORO, ["Kokoro, on the CPU", "Wyoming, port 10210"])

canvas.vline(DEVICE_OUT, 4, 9, head="")
canvas.corner(10, DEVICE_OUT, "╯")
canvas.hline(10, STT + 1, DEVICE_OUT - 1, head="")
canvas.corner(10, STT, "╭")
canvas.vline(STT, 11, 12)
canvas.put(5, DEVICE_OUT + 2, "audio")

canvas.vline(DEVICE_IN, 4, 9, head="▲")
canvas.corner(10, DEVICE_IN, "╰")
canvas.hline(10, DEVICE_IN + 1, TTS - 1, head="")
canvas.corner(10, TTS, "╮")
canvas.vline(TTS, 11, 12, head="")
canvas.put(5, DEVICE_IN + 2, "speech")

for (_, right, _), (left, _, _), label in zip(stages, stages[1:], ["text", "the answer"]):
    canvas.hline(14, right + 1, left - 1)
    canvas.put(13, right + 2, label)

canvas.vline(WHISPER_DOWN, 17, 27)
canvas.vline(WHISPER_UP, 17, 27, head="▲")
canvas.put(26, WHISPER_DOWN - 6, "audio")
canvas.put(26, WHISPER_UP + 2, "text")

canvas.vline(KOKORO_DOWN, 17, 27)
canvas.vline(KOKORO_UP, 17, 27, head="▲")
canvas.put(26, KOKORO_DOWN - 5, "text")
canvas.put(26, KOKORO_UP + 2, "speech")

canvas.vline(PIPER_DOWN, 17, 19)
canvas.vline(PIPER_UP, 17, 19, head="▲")
canvas.put(18, PIPER_DOWN - 5, "text")
canvas.put(18, PIPER_UP + 2, "speech")

print("\n".join(line.ljust(len(canvas.grid[0])) for line in canvas.render().splitlines()))
