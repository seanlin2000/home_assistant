# Current Working Changes

This page lists the pull requests that are open right now, one entry each, in the same shape as a section. An entry is written when its pull request opens and removed when the pull request merges or closes.

## PR #51: Add broadway_shows: what is playing on Broadway and Off-Broadway, from TodayTix
<!-- manual-entry branch="broadway-shows" pr="51" date="2026-10-25" -->

### Where this fits

```mermaid
flowchart TB
--8<-- "_includes/system_map.mmd"
class agent,mcp,laptop,health,ollama current
```

### Key definitions

| Term | Meaning |
|---|---|
| Listings snapshot | The file the nightly listings refresh writes, such as `broadway.json`, which a listings tool reads on every call instead of asking the source. |
| Rush ticket | A cheap ticket a theater sells on the day of the performance, first come, first served. |
| Ticket lottery | A draw for cheap tickets to one performance, entered online before the day. |

### Packages and tools

| Tool | What it is | How this change uses it |
|---|---|---|
| TodayTix listing | The JSON that TodayTix's own website reads, at `api.todaytix.com/api/v2/shows`, with no key | One request a night returns every New York show with its category, genre tags, theater, dates, cheapest price, audience score, and page views |
| launchd `StartCalendarInterval` | The plist key that makes launchd run a job at a time of day | Runs the listings refresh at 4:30 every morning, or on waking if the Mac slept through it |

### What changed

- **A nightly listings refresh.** A new launchd agent, `listings`, runs `listings-refresh` at 4:30 a.m. and once whenever it is loaded. It reads TodayTix once and writes the snapshot; if TodayTix fails, the last snapshot stays and the failure is one line in `listings.log`. [Operations](10_operations.md) covers the other agents.
- **The `broadway_shows` tool.** A new tool on the [MCP Tool Server](03_web_search_mcp.md) lists the shows running now, or those not started yet, filtered by Broadway or Off-Broadway, musical or play, TodayTix genre tag, price, and rush or lottery tickets, and ordered by page views, review count, or audience score.
- **A shows route.** The [question router](04_conversation_agent.md) sends "Off-Broadway", or "Broadway" with a theater word, to the new tool, and prompt 2.5 tells the model to call it instead of searching.

#### The listings refresh and broadway_shows

```mermaid
flowchart LR
--8<-- "_includes/palette.mmd"
%% peers: todaytix refresh snapshot tool agent
subgraph outside["Outside the apartment"]
  todaytix("TodayTix listing<br/>about 3 MB")
end
subgraph nightly["Nightly, 4:30 a.m."]
  refresh("listings-refresh<br/>keeps the shows")
end
subgraph cache["Cache folder"]
  snapshot[("broadway.json<br/>the snapshot")]
end
subgraph server["Tool server"]
  tool("broadway_shows<br/>filters and sorts")
end
subgraph harness["Conversation agent"]
  agent("the model<br/>says the list")
end
todaytix -- "one request" --> refresh
refresh -- "written whole" --> snapshot
snapshot -- "read per call" --> tool
tool -- "ten shows" --> agent
class todaytix ext
class refresh,snapshot,tool,agent ours
```

The snapshot sits in `~/Library/Caches/studio-assistant/listings/`. Every label in it is TodayTix's own: a show's category, such as Musicals, and its genre tags, such as Comedy or Family / Kid-friendly. The tool only filters and sorts them. A snapshot more than three days old makes the answer say the listings may be out of date.

One line of the tool's reply, for the default question:

```text
1. The Rocky Horror Show | musical | Comedy, Horror, Sci Fi / Fantasy, Revival | Studio 54 | from $62 | audience score 94 | lottery tickets
```

### Run it yourself

1. Refresh the listings into a scratch file, so the real snapshot is left alone:

    ```bash
    BROADWAY_SNAPSHOT_PATH=/tmp/broadway.json uv run listings-refresh
    ```

    It logs one request to `api.todaytix.com`, then a line such as `broadway: 262 shows (52 Broadway, 210 Off-Broadway) written to /tmp/broadway.json`, and exits 0.

2. Install the agents, which also runs the first refresh:

    ```bash
    scripts/services.sh install
    scripts/services.sh status
    ```

    `status` prints `listings: refreshes daily at 4:30; last:` followed by the last line of `listings.log`.
