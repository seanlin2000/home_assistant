"""Sketch: section 3, SearXNG in Docker."""

from canvas import Canvas

CLIENT_X = 19
SEARXNG_X = 74
canvas = Canvas(152, 22)

canvas.frame(0, 0, 21, 97)
canvas.put(1, 2, "THE MAC")
canvas.frame(3, 3, 19, 37)
canvas.put(4, 5, "WEB_SEARCH_MCP")
canvas.frame(3, 54, 19, 94)
canvas.put(4, 56, "DOCKER DESKTOP")
canvas.frame(0, 101, 21, 151)
canvas.put(1, 103, "THE INTERNET")

client_left, client_right, client_bottom = canvas.box(6, CLIENT_X, ["SearxngClient", "3 s between live searches"])
searxng_left, searxng_right, searxng_bottom = canvas.box(6, SEARXNG_X, ["SearXNG", "studio-searxng", "127.0.0.1:8080, Mac only"])
engines_left, _, _ = canvas.box(6, 138, ["seven search", "engines"])
_, _, _ = canvas.box(13, CLIENT_X, ["query cache", "results by query", "benchmark runs only"], stored=True)
_, _, _ = canvas.box(13, SEARXNG_X, ["settings.yml", "seven engines", "JSON output on"], stored=True)

canvas.hline(7, client_right + 1, searxng_left - 1)
canvas.put(6, 39, "query, as JSON")
canvas.hline(7, searxng_right + 1, engines_left - 1)
canvas.put(6, 103, "same query, in parallel")

canvas.vline(CLIENT_X, client_bottom + 1, 12, head="▲")
canvas.put(10, CLIENT_X + 2, "results of a")
canvas.put(11, CLIENT_X + 2, "repeated query")
canvas.vline(SEARXNG_X, searxng_bottom + 1, 12, head="▲")
canvas.put(11, SEARXNG_X + 2, "mounted read-only")

print(canvas.render())
