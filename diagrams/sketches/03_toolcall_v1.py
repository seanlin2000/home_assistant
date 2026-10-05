"""Sketch: section 3, one tool call end to end."""

from canvas import Canvas

canvas = Canvas(156, 18)

canvas.frame(0, 0, 17, 110)
canvas.put(1, 2, "THE MAC")
canvas.frame(0, 114, 17, 155)
canvas.put(1, 116, "THE INTERNET")
canvas.frame(3, 82, 12, 107)
canvas.put(4, 84, "DOCKER DESKTOP")

agent_left, agent_right, _ = canvas.box(6, 13, ["conversation agent", "in Home Assistant"])
mcp_left, mcp_right, mcp_bottom = canvas.box(6, 60, ["web_search_mcp", "port 8765"])
searxng_left, searxng_right, _ = canvas.box(6, 95, ["SearXNG", "127.0.0.1:8080"])
engines_left, engines_right, _ = canvas.box(6, 141, ["search engines", "Google, Bing, ..."])
pages_left, _, _ = canvas.box(13, 141, ["the top web pages"])

canvas.hline(7, agent_right + 1, mcp_left - 1)
canvas.put(6, agent_right + 2, "1 search_and_read")
canvas.hline(8, agent_right + 1, mcp_left - 1, head="◀")
canvas.put(9, agent_right + 2, "6 excerpts from the pages")

canvas.hline(7, mcp_right + 1, searxng_left - 1)
canvas.put(6, mcp_right + 2, "2 query")
canvas.hline(8, mcp_right + 1, searxng_left - 1, head="◀")
canvas.put(9, mcp_right + 2, "4 results")

canvas.hline(7, searxng_right + 1, engines_left - 1)
canvas.put(6, 116, "3 same query")

canvas.vline(60, mcp_bottom + 1, 14, head="")
canvas.corner(14, 60, "╰")
canvas.hline(14, 61, pages_left - 1)
canvas.put(15, 70, "5 fetch the top pages")

print(canvas.render())
