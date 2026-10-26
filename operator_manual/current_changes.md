# Current Working Changes

This page lists the pull requests that are open right now, one entry each, in the same shape as a section. An entry is written when its pull request opens and removed when the pull request merges or closes.

## Branch movies-showing: Add movies_showing and movie_details: what is on at Manhattan theaters, this week and coming up, from Fandango
<!-- manual-entry branch="movies-showing" pr="pending" date="2026-10-25" -->

### Where this fits

```mermaid
flowchart TB
--8<-- "_includes/system_map.mmd"
class agent,mcp,laptop,health,ollama current
```

### Key definitions

| Term | Meaning |
|---|---|
| Listings snapshot | The file the nightly listings refresh writes, such as `movies.json`, which a listings tool reads on every call instead of asking the source. |
| Tomatometer | Rotten Tomatoes' critics score: the percentage of critics' reviews of a movie that are positive. |
| Popcornmeter | Rotten Tomatoes' audience score: the percentage of audience ratings of a movie that are positive. |

### Packages and tools

| Tool | What it is | How this change uses it |
|---|---|---|
| Fandango theater listing | The JSON that Fandango's zip-code page reads, at `fandango.com/napi/theaterswithshowtimes`, with no key | Two requests a day for 60 days return every theater near Times Square with the movies it shows that day |
| Fandango ratings | The JSON a Fandango movie page reads for its Rotten Tomatoes scores, at `fandango.com/napi/fanAndCriticRatings/{id}` | One request per movie each night returns its Tomatometer, Popcornmeter, and Certified Fresh badge |
| Fandango movie page | A movie's page on `fandango.com`, which carries a schema.org Movie description | Read once per movie, for its synopsis, directors, and lead actors |

### What changed

- **Movies in the nightly listings refresh.** The `listings-refresh` command now also reads Fandango's listings for the 23 Manhattan theaters, 60 days ahead, then each movie's scores and, the first night it is listed, its page. [Operations](10_operations.md) covers the launchd agents that run it.
- **The `movies_showing` tool.** A new tool on the [MCP Tool Server](03_web_search_mcp.md) lists the movies showing this week, or with `when="coming_up"` those whose first Manhattan showing is later. It filters by Fandango genre, title, or theater and orders by theaters, release date, critics score, or audience score. Horror is left out unless asked for.
- **The `movie_details` tool.** It answers what one movie is about: its synopsis, directors, lead actors, scores, opening date, and every theater showing it, grouped by the day each starts.
- **A movies route.** The [question router](04_conversation_agent.md) sends a movie word with an ask ("playing", "coming soon"), or a theater chain with "playing" or "showing", to the new tools, and prompt 2.6 tells the model to call them instead of searching.

#### The listings refresh and the movies tools

```mermaid
flowchart LR
--8<-- "_includes/palette.mmd"
%% peers: fandango refresh snapshot tools agent
subgraph outside["Outside the apartment"]
  fandango("Fandango<br/>listings, scores, pages")
end
subgraph nightly["Nightly, 4:30 a.m."]
  refresh("listings-refresh<br/>keeps Manhattan")
end
subgraph cache["Cache folder"]
  snapshot[("movies.json<br/>the snapshot")]
end
subgraph server["Tool server"]
  tools("movies_showing<br/>movie_details")
end
subgraph harness["Conversation agent"]
  agent("the model<br/>says the answer")
end
fandango -- "one a second" --> refresh
refresh -- "written whole" --> snapshot
snapshot -- "read per call" --> tools
tools -- "the reply" --> agent
class fandango ext
class refresh,snapshot,tools,agent ours
```

Fandango's listing JSON and its scores answer only a session that has opened its zip-code page first, so the refresh opens that page once and then makes one request a second. The first run on 2026-10-25 kept 294 movies through December 23 in about 16 minutes. Later nights skip the movie pages they already have.

Every label in the snapshot is Fandango's own: a movie's genres, such as Drama or Kids & Family, and its MPAA rating. The tools only filter and sort them. A snapshot more than three days old makes the answer say the listings may be out of date.

One line of `movies_showing`'s reply, for the default question:

```text
1. You Can See Everything | Documentary | rated R | 2 hours 54 minutes | Rotten Tomatoes: critics 98%, Certified Fresh, audience 96% | playing at 17 theaters
```

### Run it yourself

1. Refresh the movie listings into a scratch file, so the real snapshot is left alone:

    ```bash
    MOVIES_SNAPSHOT_PATH=/tmp/movies.json BROADWAY_SNAPSHOT_PATH=/tmp/broadway.json uv run listings-refresh
    ```

    After about a quarter of an hour it logs a line such as `movies: 294 movies at 23 Manhattan theaters, 2026-10-25 to 2026-12-23, written to /tmp/movies.json`, and exits 0.

2. Call the tools against the benchmark's snapshot, with no model involved:

    ```bash
    uv run pytest -q tests/test_movies_showing.py
    ```

    Every test passes; the details tests ask for Clayface, Avengers: Doomsday, and "rocky".
