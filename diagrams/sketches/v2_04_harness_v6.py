"""Sketch: v2 agent harness in two lanes of equal boxes, read left to right. The first lane is one question with its tool loop drawn over the top;
the second is what happens when the conversation ends. Each box that sends a prompt to the model is a "llama.cpp request", named for its purpose and slot, since one model serves them all. Replaces v4 ("call" boxes) and v3, which split the question and its tool loop into separate lanes.
"""

from canvas import Canvas

CONTENT = 18
BOX_WIDTH = CONTENT + 4
GAP = 3
COLUMNS = [1 + BOX_WIDTH // 2 + index * (BOX_WIDTH + GAP) for index in range(6)]
W = 1 + 6 * BOX_WIDTH + 5 * GAP + 1


def chain(top: int, boxes: list[list[str]], stored_last: bool = False) -> list[tuple[int, int, int]]:
    spans = []
    for index, (column, lines) in enumerate(zip(COLUMNS, boxes)):
        stored = stored_last and index == len(boxes) - 1
        spans.append(canvas.box(top, column, [line.center(CONTENT) for line in lines], stored=stored))
    for (_, right, _), (left, _, _) in zip(spans, spans[1:]):
        canvas.hline(top + 2, right + 1, left - 1)
    return spans


canvas = Canvas(W, 20)
MODEL, TOOLS = COLUMNS[3], COLUMNS[5]

canvas.put(0, 1, "ONE QUESTION")
canvas.put(2, MODEL + 3, "result added to slot 0; a new llama.cpp request")
canvas.vline(TOOLS, 3, 4, head="")
canvas.vline(MODEL, 3, 4)
canvas.hline(3, MODEL + 1, TOOLS - 1, head="")
canvas.corner(3, MODEL, "┌")
canvas.corner(3, TOOLS, "┐")
spans = chain(
    5,
    [
        ["your question", "via the puck"],
        ["recall", "2 or 3 past notes"],
        ["llama.cpp request", "plan, slot 1"],
        ["llama.cpp request", "response, slot 0"],
        ["guards", "check each request"],
        ["tool server", "runs the requests"],
    ],
)
canvas.vline(MODEL, spans[3][2] + 1, spans[3][2] + 2)
canvas.put(spans[3][2] + 2, MODEL + 2, "no tool call: the answer streams back to Home Assistant")

canvas.put(12, 1, "WHEN THE CONVERSATION ENDS")
canvas.put(19, 1, "A llama.cpp request sends one prompt to the one Gemma 4 model in llama-server and gets one reply; only the prompt and the slot differ.")
chain(14, [["five minutes", "of quiet"], ["llama.cpp request", "summary, slot 1"], ["code checks it", "length, no URLs"], ["memory vault", "one note"]], stored_last=True)

print("\n".join(line.ljust(W) for line in canvas.render().rstrip("\n").splitlines()))
