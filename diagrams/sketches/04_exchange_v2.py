"""Sketch: Conversation Agent, one exchange of a search question, split into two figures with the same layout, one per round of the loop. Each arrow carries one numbered step."""

from canvas import Canvas

CONTENT_WIDTH = 18


def draw_round(steps: dict[str, str]) -> str:
    canvas = Canvas(140, 24)

    def place(y: int, center: int, lines: list[str]) -> tuple[int, int, int]:
        return canvas.box(y, center, [line.center(CONTENT_WIDTH) for line in lines])

    canvas.frame(0, 0, 23, 138)
    canvas.put(1, 2, "THE MAC")
    canvas.frame(3, 2, 13, 83)
    canvas.put(4, 4, "HOME ASSISTANT VM")

    pipeline = place(8, 16, ["Assist pipeline", "speech in and out"])
    agent = place(8, 70, ["conversation agent", "studio_assistant"])
    ollama = place(8, 124, ["Ollama", "the model"])
    mcp = place(18, 70, ["web_search_mcp", "the tools"])

    if "pipeline_to_agent" in steps:
        canvas.hline(9, pipeline[1] + 1, agent[0] - 1)
        canvas.put(7, pipeline[1] + 3, steps["pipeline_to_agent"])
    canvas.hline(10, pipeline[1] + 1, agent[0] - 1, head="◀")
    canvas.put(11, pipeline[1] + 3, steps["agent_to_pipeline"])

    canvas.hline(9, agent[1] + 1, ollama[0] - 1)
    canvas.put(7, agent[1] + 6, steps["agent_to_ollama"])
    canvas.hline(10, agent[1] + 1, ollama[0] - 1, head="◀")
    canvas.put(11, agent[1] + 6, steps["ollama_to_agent"])

    canvas.vline(67, agent[2] + 1, mcp[2] - 4)
    canvas.put(15, 66 - len(steps["agent_to_mcp"]), steps["agent_to_mcp"])
    canvas.vline(73, agent[2] + 1, mcp[2] - 4, head="▲")
    canvas.put(15, 75, steps["mcp_to_agent"])

    return "\n".join(line.ljust(len(canvas.grid[0])) for line in canvas.render().splitlines())


FIRST_ROUND = {
    "pipeline_to_agent": "1 your text, chat log",
    "agent_to_mcp": "2 list tools",
    "mcp_to_agent": "3 eleven tools",
    "agent_to_ollama": "4 chat, tool list",
    "ollama_to_agent": "5 call search_and_read",
    "agent_to_pipeline": "6 filler sentence",
}
SECOND_ROUND = {
    "agent_to_mcp": "7 search_and_read",
    "mcp_to_agent": "8 excerpts",
    "agent_to_ollama": "9 chat + excerpts",
    "ollama_to_agent": "10 the answer, streamed",
    "agent_to_pipeline": "11 the answer, keep listening",
}

print("ROUND 1\n" + draw_round(FIRST_ROUND) + "\n\nROUND 2\n" + draw_round(SECOND_ROUND))
