"""Sketch: v2 hardware and deployment, who can reach which port. Left: devices on the home network. Middle: what the Mac serves on its
network address, in conversation order (speech to text, the conversation agent, text to speech). Right: what it serves to itself only. Replaces v1, which put the harness first and labelled Whisper's arrow "audio".
"""

from canvas import Canvas

CONTENT = 18
W = 146
HOME, LAN, LOCAL, FAR = 12, 51, 100, 130

canvas = Canvas(W, 23)
canvas.put(0, 1, "HOME NETWORK")
canvas.container(0, 30, 21, 72, "MAC: ON ITS NETWORK ADDRESS")
canvas.container(5, 80, 17, 144, "MAC: ON 127.0.0.1 ONLY")


def box(top: int, center: int, lines: list[str]) -> tuple[int, int, int]:
    return canvas.box(top, center, [line.center(CONTENT) for line in lines])


home_lines = ["Home Assistant VM", "its own address"] + [""] * 10
_, vm_right, _ = box(2, HOME, home_lines)
whisper_left, _, _ = box(2, LAN, ["Whisper", ":10300"])
harness_left, harness_right, _ = box(7, LAN, ["harness", ":8770, API key"])
kokoro_left, _, _ = box(12, LAN, ["Kokoro", ":10210"])
_, laptop_right, _ = box(17, HOME, ["your laptop", ""])
ssh_left, _, _ = box(17, LAN, ["SSH", ":22, keys only"])
llama_left, _, _ = box(7, LOCAL, ["llama-server", ":8090, API key"])
tools_left, tools_right, _ = box(12, LOCAL, ["tool server", ":8765"])
searxng_left, _, _ = box(12, FAR, ["SearXNG", ":8080, Docker"])

for row, target_left, label in [(3, whisper_left, "speech"), (8, harness_left, "question"), (13, kokoro_left, "text")]:
    canvas.hline(row, vm_right + 1, target_left - 1)
    canvas.put(row - 1, 31, label)
canvas.hline(18, laptop_right + 1, ssh_left - 1)
canvas.put(17, 31, "deploys")

canvas.hline(8, harness_right + 1, llama_left - 1)
canvas.put(7, harness_right + 2, "prompts")
branch_x = 76
canvas.hline(9, harness_right + 1, branch_x - 1, head="")
canvas.vline(branch_x, 9, 13, head="")
canvas.corner(9, branch_x, "┐")
canvas.corner(13, branch_x, "└")
canvas.hline(13, branch_x + 1, tools_left - 1)
canvas.put(12, 81, "tools")
canvas.hline(13, tools_right + 1, searxng_left - 1)
canvas.put(12, tools_right + 2, "queries")

print("\n".join(line.ljust(W) for line in canvas.render().rstrip("\n").splitlines()))
