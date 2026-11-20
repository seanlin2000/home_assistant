"""Sketch: section 2, what the model costs in memory."""

from canvas import Canvas

WIDTH = 93
WEIGHTS_STEM, CACHE_STEM = 60, 69
canvas = Canvas(WIDTH, 17)

canvas.container(0, 0, 16, WIDTH - 1, "THE PROTOTYPE MAC'S 16 GB OF UNIFIED MEMORY")
canvas.box(2, 11, ["macOS", "about 3 GB"])
canvas.box(2, 37, ["Home Assistant VM + Piper", "3 to 4 GB"])
_, _, ollama_bottom = canvas.box(2, 65, ["Ollama", "about 7.5 GB"])
canvas.box(2, 83, ["Whisper", "1.6 GB"])

canvas.vline(WEIGHTS_STEM, ollama_bottom + 1, ollama_bottom + 4)
canvas.vline(CACHE_STEM, ollama_bottom + 1, ollama_bottom + 4)
canvas.put(ollama_bottom + 2, WEIGHTS_STEM - 13, "loaded once")
canvas.put(ollama_bottom + 2, CACHE_STEM + 2, "grows with context")
canvas.box(ollama_bottom + 5, 52, ["weights, 4-bit", "gemma4:e4b-it-qat", "6.1 GB"], stored=True)
canvas.box(ollama_bottom + 5, 74, ["KV cache", "1 to 2 GB", "at 16k tokens"], stored=True)

print(canvas.render())
