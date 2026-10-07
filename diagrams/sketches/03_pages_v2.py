"""Sketch: section 3, reading the pages. Every box has the same width and three lines."""

from canvas import Canvas

CONTENT_WIDTH = 20
GAP = 16
canvas = Canvas(146, 5)

boxes = [
    ["ranked results", "from SearXNG", "best match first"],
    ["download", "first 12 web pages", "6 s, 2 MB each"],
    ["keep the parts", "that match the query", "350 words a page"],
    ["one ranked list", "passages of 6 pages,", "the rest as snippets"],
]
labels = ["28 URLs", "HTML pages", "passages"]

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
