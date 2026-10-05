"""Sketch: section 3, reading the pages. Every box has the same width and three lines."""

from canvas import Canvas

CONTENT_WIDTH = 20
GAP = 16
canvas = Canvas(146, 5)

boxes = [
    ["ranked results", "from SearXNG", "best match first"],
    ["download", "first 8 web pages", "6 s, 2 MB each"],
    ["trafilatura", "keeps the main text", "and the tables"],
    ["numbered sources", "4 pages with text", "under 2,000 words"],
]
labels = ["28 URLs", "HTML pages", "page text"]

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
