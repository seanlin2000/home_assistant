"""Sketch: v2 system overview. The agent leaves the Home Assistant VM: a thin client there, the harness, llama-server, the tools and memory on the Mac."""

from canvas import Canvas

W, H = 126, 62
STT, INTENT, AGENT, TTS = 28, 48, 76, 106
LLM, TOOLS, VAULT = 60, 86, 110


def padded(lines: list[str], width: int) -> list[str]:
    return [line.center(width) for line in lines]


def titled(canvas: Canvas, top: int, left: int, bottom: int, right: int, title: str, title_x: int) -> None:
    """A container whose title starts at title_x, so a line entering through the top border can pass left of the title."""
    canvas.frame(top, left, bottom, right)
    canvas.grid[top][title_x : title_x + len(title) + 2] = list(" " + title + " ")


canvas = Canvas(W, H)
canvas.container(0, 0, 53, W - 1, "YOUR STUDIO: everything inside stays local")
titled(canvas, 8, 14, 51, W - 3, "MAC, ALWAYS ON", STT + 3)
titled(canvas, 10, 17, 24, W - 5, "HOME ASSISTANT OS, a virtual machine", STT + 3)

canvas.box(2, STT, ["Voice puck"])
canvas.vline(STT, 5, 12, head="▲")
canvas.put(6, STT + 2, "audio in,")
canvas.put(7, STT + 2, "spoken reply back")

stage = 11
_, stt_r, stt_b = canvas.box(13, STT, padded(["speech", "to text"], stage))
int_l, int_r, int_b = canvas.box(13, INTENT, padded(["intent", "matcher"], stage))
agt_l, agt_r, agt_b = canvas.box(13, AGENT, padded(["our agent,", "thin client"], stage))
tts_l, _, tts_b = canvas.box(13, TTS, padded(["text to", "speech"], stage))
canvas.hline(14, stt_r + 1, int_l - 1)
canvas.hline(14, int_r + 1, agt_l - 1)
canvas.put(15, int_r + 2, "no match")
canvas.hline(14, agt_r + 1, tts_l - 1)
canvas.put(15, agt_r + 3, "answer")

canvas.vline(INTENT, int_b + 1, 18)
canvas.put(17, INTENT + 2, "play X")
ma_l, _, ma_b = canvas.box(19, INTENT, ["Music Assistant"])
sonos_l, sonos_r, _ = canvas.box(19, 7, ["Sonos"])
canvas.hline(20, sonos_r + 1, ma_l - 1, head="◀")
canvas.put(21, ma_l - 7, "music")

canvas.vline(STT - 2, stt_b + 1, 26)
canvas.vline(STT + 2, stt_b + 1, 26, head="▲")
canvas.put(25, STT - 8, "audio")
canvas.put(25, STT + 4, "text")
canvas.vline(TTS - 2, tts_b + 1, 26)
canvas.vline(TTS + 2, tts_b + 1, 26, head="▲")
canvas.put(25, TTS - 7, "text")
canvas.put(25, TTS + 4, "speech")
voice = 10
canvas.box(27, STT, padded(["Whisper", "on the GPU"], voice))
canvas.box(27, TTS, padded(["Kokoro", "the voice"], voice))

canvas.vline(AGENT - 2, agt_b + 1, 30)
canvas.vline(AGENT + 2, agt_b + 1, 30, head="▲")
canvas.put(26, AGENT - 20, "question, history")
canvas.put(26, AGENT + 4, "answer,")
canvas.put(27, AGENT + 4, "streamed")
_, _, harness_b = canvas.box(31, AGENT, ["agent harness, new:", "loop, guards, memory"])

fork_y = harness_b + 2
canvas.vline(AGENT, harness_b + 1, fork_y, head="")
canvas.hline(fork_y, LLM, VAULT, head="")
canvas.corner(fork_y, LLM, "┌")
canvas.corner(fork_y, AGENT, "┴")
canvas.corner(fork_y, TOOLS, "┬")
canvas.corner(fork_y, VAULT, "┐")
child_y = fork_y + 3
for column in (LLM, TOOLS, VAULT):
    canvas.vline(column, fork_y + 1, child_y - 1)
canvas.put(fork_y + 1, LLM + 2, "prompts")
canvas.put(fork_y + 1, TOOLS + 2, "tool calls")
canvas.put(fork_y + 1, VAULT + 2, "notes")
peer = 16
canvas.box(child_y, LLM, padded(["llama-server", "replaces Ollama"], peer))
_, _, tools_b = canvas.box(child_y, TOOLS, padded(["MCP tool server", "assistant-tools"], peer))
canvas.box(child_y, VAULT, padded(["memory vault", "notes and index"], peer), stored=True)

searx = TOOLS - 4
apis = TOOLS + 7
canvas.container(tools_b + 2, searx - 14, tools_b + 7, searx + 8, "DOCKER")
canvas.vline(searx, tools_b + 1, tools_b + 3)
_, _, sx_b = canvas.box(tools_b + 4, searx, ["SearXNG"])

bottom = 56
canvas.vline(INTENT, ma_b + 1, bottom)
canvas.vline(searx, sx_b + 1, bottom)
turn_y, external = tools_b + 4, VAULT + 2
canvas.vline(apis, tools_b + 1, turn_y, head="")
canvas.hline(turn_y, apis, external, head="")
canvas.corner(turn_y, apis, "└")
canvas.corner(turn_y, external, "┐")
canvas.vline(external, turn_y + 1, bottom)
canvas.put(55, INTENT - 19, "catalogue, stream")
canvas.put(55, searx - 14, "search query")
canvas.put(55, external + 2, "lookups")
outside = 19
canvas.box(57, INTENT, padded(["Spotify", "API"], outside))
canvas.box(57, searx, padded(["public search", "engines"], outside))
canvas.box(57, external, padded(["weather, Wikipedia,", "sports, Reddit"], outside))
canvas.put(59, 2, "LEAVES THE NETWORK")

print("\n".join(line.ljust(W) for line in canvas.render().rstrip("\n").splitlines()))
