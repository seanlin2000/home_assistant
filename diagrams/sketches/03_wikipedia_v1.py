"""Sketch: section 3, Wikipedia articles. One row from the model's topic to the lines it reads back; every box has the same width and three lines."""

from canvas import Canvas

CONTENT_WIDTH = 20
GAP = 16
canvas = Canvas(186, 5)

boxes = [
    ["topic and focus", "from the model", "49ers QBs, 2000"],
    ["Wikipedia search", "en.wikipedia.org", "five titles"],
    ["the article", "Parsoid HTML", "for the best title"],
    ["render_article", "one line for each", "table row"],
    ["select_passages", "the lines that match", "up to 900 words"],
]
labels = ["topic", "best title", "HTML", "text"]

left_edge = 1
spans = []
for lines in boxes:
    padded = [line.center(CONTENT_WIDTH) for line in lines]
    width = CONTENT_WIDTH + 4
    spans.append(canvas.box(0, left_edge + width // 2, padded))
    left_edge += width + GAP
for (_, previous_right, _), (next_left, _, _), label in zip(spans, spans[1:], labels):
    canvas.hline(2, previous_right + 1, next_left - 1)
    canvas.put(1, previous_right + 3, label)

print(canvas.render())
