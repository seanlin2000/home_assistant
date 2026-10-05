"""Sketch: section 2, keeping a model resident: where the weights live."""

from canvas import Canvas

canvas = Canvas(112, 6)

_, registry_right, _ = canvas.box(0, 12, ["model registry", "Ollama library", "or Hugging Face"])
disk_left, disk_right, _ = canvas.box(0, 51, ["on disk", "Ollama's model store"], stored=True)
memory_left, _, _ = canvas.box(0, 98, ["in unified memory", "ready to answer"], stored=True)

canvas.hline(1, registry_right + 1, disk_left - 1)
canvas.put(0, registry_right + 3, "ollama pull")
canvas.hline(1, disk_right + 1, memory_left - 1)
canvas.hline(2, disk_right + 1, memory_left - 1, head="◀")
canvas.put(0, disk_right + 3, "first request")
canvas.put(3, disk_right + 2, "keep-alive runs out,")
canvas.put(4, disk_right + 2, "or ollama stop")

print(canvas.render())
