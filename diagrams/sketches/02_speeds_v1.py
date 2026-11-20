"""Sketch: section 2, prefill and decode."""

from canvas import Canvas

WIDTH = 86
CLIENT_X = 20
CHANNEL_X = 83
canvas = Canvas(WIDTH, 18)

client_left, client_right, client_bottom = canvas.box(0, CLIENT_X, ["OllamaClient", "our agent"])
canvas.frame(6, 1, 17, 80)
canvas.put(7, 24, "OLLAMA, ON THE MAC'S GPU")
read_left, read_right, _ = canvas.box(10, CLIENT_X, ["prefill", "read the whole prompt at once", "limited by compute", "sets time to first token"])
write_left, write_right, _ = canvas.box(10, 60, ["decode", "write the answer, token by token", "limited by memory bandwidth", "sets tokens per second"])

canvas.vline(CLIENT_X, client_bottom + 1, 9)
canvas.put(4, CLIENT_X + 2, "conversation + tool list")
canvas.hline(11, read_right + 1, write_left - 1)
canvas.hline(11, write_right + 1, CHANNEL_X, head="")
canvas.corner(11, CHANNEL_X, "╯")
canvas.vline(CHANNEL_X, 2, 10, head="")
canvas.corner(1, CHANNEL_X, "╮")
canvas.hline(1, client_right + 1, CHANNEL_X - 1, head="◀")
canvas.put(0, 40, "each token, or a tool call")

print(canvas.render())
