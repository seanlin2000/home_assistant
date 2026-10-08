"""Sketch: v2 inference. Top lane: one request in the order the model reads it, and which part the cache already holds. Bottom lane: two pinned slots in one shared KV pool, so the router and summaries never evict the conversation."""

from canvas import Canvas

CONTENT = 20
GAP = 12
W = 4 * (CONTENT + 4) + 3 * GAP + 2

request_parts = [
    ["system rules", "never change", "~900 tokens"],
    ["tool definitions", "change with the tools", "~1,400 tokens"],
    ["earlier exchanges", "questions, answers", "grow by ~100 each"],
    ["this question", "date, plan, notes", "~50 to 450 tokens"],
]

canvas = Canvas(W, 24)
canvas.put(0, 1, "ONE REQUEST TO LLAMA-SERVER, in the order the model reads it")
spans = []
left = 1
for lines in request_parts:
    width = CONTENT + 4
    spans.append(canvas.box(2, left + width // 2, [line.center(CONTENT) for line in lines]))
    left += width + GAP
for (_, right, _), (next_left, _, _) in zip(spans, spans[1:]):
    canvas.hline(4, right + 1, next_left - 1, head="")

cached_left, cached_right = spans[0][0], spans[2][1]
fresh_left, fresh_right = spans[3][0], spans[3][1]
bracket_y = spans[0][2] + 1
canvas.put(bracket_y, cached_left, "└" + "─" * (cached_right - cached_left - 1) + "┘")
canvas.put(bracket_y, fresh_left, "└" + "─" * (fresh_right - fresh_left - 1) + "┘")
cached_label = "already in the cache from the last request: about 0.1 s"
fresh_label = "read fresh: 0.2 to 1.3 s"
canvas.put(bracket_y + 1, cached_left + (cached_right - cached_left - len(cached_label)) // 2, cached_label)
canvas.put(bracket_y + 1, fresh_left + (fresh_right - fresh_left - len(fresh_label)) // 2, fresh_label)

canvas.put(11, 1, "TWO SLOTS SHARING ONE KV POOL: the router and the summaries never push the conversation out")
first_center = (spans[0][0] + spans[0][1]) // 2 + 1
slot_center = (spans[2][0] + spans[2][1]) // 2
_, harness_right, _ = canvas.box(16, first_center, [line.center(CONTENT) for line in ["the harness", "pins every request", "to its slot"]])
router_left, _, _ = canvas.box(13, slot_center, [line.center(CONTENT) for line in ["slot 1", "router, summaries", "~400 tokens each"]])
chat_left, _, _ = canvas.box(19, slot_center, [line.center(CONTENT) for line in ["slot 0", "the conversation", "~2,400 tokens and up"]])
branch_x = spans[1][0] + 4
canvas.hline(18, harness_right + 1, branch_x - 1, head="")
canvas.vline(branch_x, 15, 21, head="")
canvas.corner(15, branch_x, "┌")
canvas.corner(18, branch_x, "┤")
canvas.corner(21, branch_x, "└")
canvas.hline(15, branch_x + 1, router_left - 1)
canvas.hline(21, branch_x + 1, chat_left - 1)
canvas.put(14, branch_x + 3, "quiet requests")
canvas.put(22, branch_x + 3, "response requests")

print("\n".join(line.ljust(W) for line in canvas.render().rstrip("\n").splitlines()))
