# 15. Subway arrivals

Status: built 2026-11-21

## 1. Purpose

Jarvis tells you when the next New York City subway trains leave a station, using MTA's live train positions. It should answer:

- "When's the next train at Court Square?"
- "What's running at Queensboro Plaza?" On a Saturday that leaves out the W, which runs only on weekdays.
- "When's the next 7 from Queensboro Plaza?"
- "Next Manhattan-bound train from Queens Plaza?"
- "When's the next train?" Jarvis asks which station; it never guesses one.

Your stations are Court Square, Queensboro Plaza, and Queens Plaza, but the tool knows every station in the system.

**Which trains run comes only from the live feed.** Weekend service, night service, planned work, and reroutes all change which lines stop at a station. No table in the code says which lines serve a station, and nothing is answered from the model's memory.

## 2. Diagram

```
 A QUESTION

 ╭──────────────────────╮              ╭──────────────────────╮              ╭──────────────────────╮              ╭──────────────────────╮
 │    your question     │              │   main model call    │ tool call    │   subway_arrivals    │              │       speaker        │
 │ next 7, Queensboro?  │─────────────▶│    picks the tool    │─────────────▶│  station, line, way  │              │  Kokoro on the puck  │
 ╰──────────────────────╯              ╰──────────────────────╯              ╰──────────────────────╯              ╰──────────────────────╯
                                             │     ▲ arrivals, marked untrusted          │                                     ▲
                                             │     └─────────────────────────────────────┘                                     │
                                             │                                                                                 │ its answer
                                             └─────────────────────────────────────────────────────────────────────────────────┘

 INSIDE SUBWAY_ARRIVALS, EACH CALL

 ╭──────────────────────╮              ╭══════════════════════╮              ╭──────────────────────╮              ╭──────────────────────╮
 │  MTA realtime feeds  │ whole feeds  │      feed cache      │ decoded      │       arrivals       │ groups       │      text block      │
 │  8 feeds and alerts  │─────────────▶│ 20 s, stale to 5 min │─────────────▶│   live trips only    │─────────────▶│   next 3 each way    │
 ╰──────────────────────╯              ╰══════════════════════╯              ╰──────────────────────╯              ╰──────────────────────╯
                                                                                         ▲
 BY HAND, WHEN MTA CHANGES ITS STATIONS                                                  │ stop IDs, usual lines
                                                                                         │
 ╭──────────────────────╮              ╭──────────────────────╮              ╭══════════════════════╮
 │     data.ny.gov      │ station rows │    build_stations    │ JSON         │    stations.json     │
 │  MTA stations list   │─────────────▶│  grouped by complex  │─────────────▶│      checked in      │
 ╰──────────────────────╯              ╰──────────────────────╯              ╰══════════════════════╯
```

## 3. How it works, step by step

### 3.1 MTA's feeds

MTA publishes the position and predicted stop times of every subway train as GTFS-realtime (§7). The feeds need no API key, which we checked on 2026-11-21: every feed answered HTTP 200 without one.

| Feed | Lines |
|---|---|
| `nyct%2Fgtfs` | 1, 2, 3, 4, 5, 6, 7, 42 St shuttle |
| `nyct%2Fgtfs-ace` | A, C, E, and the Rockaway and Franklin Av shuttles |
| `nyct%2Fgtfs-bdfm` | B, D, F, M |
| `nyct%2Fgtfs-g` | G |
| `nyct%2Fgtfs-jz` | J, Z |
| `nyct%2Fgtfs-nqrw` | N, Q, R, W |
| `nyct%2Fgtfs-l` | L |
| `nyct%2Fgtfs-si` | Staten Island Railway |
| `camsys%2Fsubway-alerts.json` | Service alerts for every line, as JSON |

Each address starts with `https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/`.

1. **Fetch all nine at once.** Every call fetches every feed in parallel, not just the feeds for the station's usual lines. A rerouted train can come from another feed: an E running over the F's tracks arrives in the A/C/E feed at an F station. All nine together come to about half a megabyte.
2. **Hold them for 20 seconds.** A second question within 20 seconds reuses the same copy.
3. **Keep a stale copy for 5 minutes.** If a fetch fails, the last good copy is used if it is under 5 minutes old, and the answer says how old it is.
4. **Check how old the data is.** Each feed's header carries the time MTA wrote it. When the oldest of them is more than 60 seconds behind the clock, the answer says the times may not be real time, as MTA's terms require (§3.8, item 6).
5. **Decode.** The train feeds are protobuf, decoded with Google's `gtfs-realtime-bindings`. MTA adds its own fields in an extension, `nyct-subway.proto`. The one we need is `is_assigned`, which says whether a train has been given a crew and dispatched. The tool registers that extension in code, built from its field numbers (field 1001 of `TripDescriptor`), so no generated file is checked in.

### 3.2 The station table

A station is several stop IDs. Court Square is three: `719` for the 7, `F09` (Court Sq–23 St) for the E and F, and `G22` for the G. Queensboro Plaza is `718` for the 7 and `R09` for the N and W. Queens Plaza is `G21`, for the E, F and R.

The table comes from New York State's open-data copy of MTA's station list, the MTA Subway Stations dataset on data.ny.gov (`39hk-dx4f`). Each row is one stop:

| Field | Example | Used for |
|---|---|---|
| `gtfs_stop_id` | `F09` | Matching the live feed's stops |
| `complex_id` | `606` | Grouping stops into one station: `719`, `F09` and `G22` share 606 |
| `stop_name` | `Court Sq-23 St` | The name said back, and the names of last stops |
| `daytime_routes` | `E F` | The lines a station has on weekdays, used only to explain an absence (§3.3, rule 5) |
| `north_direction_label`, `south_direction_label` | `Outbound`, `Manhattan` | Naming a direction (§3.3, rule 3) |
| `borough` | `Q` | The direction filter (§3.4) |

**Built by hand, checked in.** `uv run python -m subway_mcp.build_stations` reads the dataset and writes `subway_mcp/stations.json`, grouped by complex. MTA rarely changes stations, so it is rebuilt by hand when it does, and the change is reviewed in a pull request. A stale table cannot invent a train. At worst a line's absence goes unexplained, because the lines themselves come from the live feed.

**Matching a spoken name:**

1. The table's abbreviations are spelled out first, so "Court Sq" is matched as "court square", "86 St" as "86 street", and a leading "St" as "saint" ("St George"). An ordinal is matched as its number, so "86th Street" finds "86 St".
2. Every station name is then matched loosely (`utils/title_matching_utils.TitleMatcher`), so small differences in wording still match. Your three stations need no shortcuts: "Court Square", "Queensboro", and "Queens Plaza" each find exactly one station, and Queens Plaza never matches Queensboro Plaza.
3. A name several stations share, such as "86 St", returns a sentence listing each one's lines and borough, for the model to ask which. A `line` narrows the match, so "86 St" with `line="Q"` is the Second Avenue station.

Station names never leave the house. They are matched against the local table, and the feed addresses are fixed.

### 3.3 From trips to arrivals

Each trip in a feed lists its line, its direction (the stop ID's last letter, `N` or `S`), and its remaining stops with predicted times. For the station's stop IDs:

1. **Lines come from the live feed.** A line is listed when a live trip stops at the station within the look-ahead window, 40 minutes. On Saturday 2026-11-21 the F was missing from Court Sq–23 St and Queens Plaza, because that day it ran via 21 St–Queensbridge.
2. **Group by line and last stop.** Trips are grouped by line, direction, and the trip's own last stop in the feed. The tool returns the next three trains in each group as whole minutes, with a train under a minute away said as "now".
3. **Name each direction by its last stop:** "toward World Trade Center". A reroute changes the last stop, so the label follows it. The station's MTA direction label is added in parentheses, "(Manhattan)", unless it is "Outbound" or "Last Stop", which mean nothing aloud. That label describes the track direction at the station, which a reroute does not reverse.
4. **Drop trains that end here.** A trip whose last stop is this station cannot be boarded. That matters for northbound Gs at Court Square, and for 7s cut back to Queensboro Plaza during planned work.
5. **Explain a missing line.** A line in the station's `daytime_routes` with no trips in the window gets one sentence: "No F trains are coming. The F stops here in weekday daytime service." The table never adds a train.
6. **Say when a train is only scheduled.** A trip whose `is_assigned` is false has not been dispatched, so its time is the timetable's, not a tracked train's. Such trips are kept. A group whose trains are all unassigned is marked "scheduled".

Example result, from the feeds recorded at 5:09 PM on Saturday 2026-11-21 (`tests/fixtures/mta_2026-11-21/`):

```
Queens Plaza, as of 5:09 PM
E toward Jamaica Center-Parsons/Archer: now, 14, 21 min
E toward World Trade Center (Manhattan): 3, 19, 31 min
R toward Forest Hills-71 Av: 1, 19, 35 min
R toward Bay Ridge-95 St (Manhattan): now, 4, 16 min
No F trains are coming. The F stops here in weekday daytime service.
Alert: A, C and F trains are running with delays in both directions while we conduct planned work in Manhattan.
Alert: Downtown R trains are running with delays after we were unable to move a train at Jackson Heights-Roosevelt Av.
```

**The station name always comes first**, and the tool description tells the model to say it. Queens Plaza and Queensboro Plaza are a block apart, and speech to text can swap them.

### 3.4 The direction filter

`direction` holds what you said: "Manhattan", "Flushing", "Brooklyn", "Times Square", "uptown". It is matched against each live trip's own remaining stops, so reroutes and weekend patterns are followed. Words such as "toward", "bound", and "the" are dropped first. The rules are tried in this order, and the first that recognizes the words decides:

| # | You say | Trains kept |
|---|---|---|
| 1 | Another borough: "Manhattan", "Brooklyn", "the Bronx" | Trips whose remaining stops reach it, using each stop's `borough`. A Coney Island-bound N from Queensboro Plaza counts as Manhattan-bound, because it crosses Manhattan first. |
| 1 | The station's own borough: "Queens" at Court Square | Trips that end their run in it: the Flushing-bound 7, not the Manhattan-bound one, which leaves Queens one stop later. |
| 2 | "uptown", "northbound", "downtown", "southbound" | The feed's `N` or `S` direction. |
| 3 | The station's MTA direction label: "Astoria" | That direction. |
| 4 | A station: "Times Square", "Flushing" | Trips whose remaining stops include it, matched with `TitleMatcher`. "Next train to Times Square from Queensboro" keeps both the 7 and the N toward Manhattan. |

**Fixed words before station names.** A borough or a compass word is a closed set, so it is tried before the station names. Otherwise "Queens" would match the station Queens Plaza and keep only the trains stopping there next.

**When nothing matches,** whether no rule recognizes the words or no train goes that way, the tool returns both directions after the line "No trains toward the Bronx in the next 40 minutes; trains here go toward Flushing-Main St, 34 St-Hudson Yards, and Church Av." The model can then say what does run.

### 3.5 Alerts

The alerts feed holds every current and planned service change, each with a type (`Delays`, `Planned - Reroute`, `No Scheduled Service`, `Station Notice`, and others), the periods it is active, and the lines and stops it concerns. An alert is shown when it is active now and either:

- names one of the station's stop IDs, or
- names a line at the station and no stops at all, as line-wide delays do.

An alert about skipped stops elsewhere on a line names those stops, so it is left out. Only the alert's header is used, never its long description. `[A][C][F]` is said "A, C and F", the header is clipped to 40 words (`utils/text_utils.clip_to_words`), and at most three alerts are shown.

Example: on 2026-11-21 the G at Court Square carried "G trains are running with delays in both directions while we address a switch problem at Court Sq."

### 3.6 The tool

This is the whole definition the model sees. The docstring is the tool's description and each `Field` description is an argument's. Its rules live here, not in the system prompt, as prompt 3.0 moved every tool's rules into the tool's own definition.

```python
@server.tool(name=SUBWAY_TOOL_NAME)
async def subway_arrivals(
    station: Annotated[str, Field(max_length=MAX_STATION_CHARS, description='New York City subway station as the user said it, e.g. "Court Square", "Queensboro Plaza", "Times Square"')],
    line: Annotated[str, Field(max_length=MAX_LINE_CHARS, description='one line, e.g. "7", "E", "N"; empty for every line at the station')] = "",
    direction: Annotated[
        str,
        Field(max_length=MAX_DIRECTION_CHARS, description='where the user is going, as they said it: a station ("Times Square"), a borough ("Manhattan") or "uptown"/"downtown"; empty for both ways'),
    ] = "",
) -> str:
    """Live New York City subway arrivals at one station: which lines are running now, the next trains each way with minutes until they arrive, and MTA service alerts there. Use this, never a web search, for subway times or whether a line is running at a station. If the user names no station, ask which station; do not guess one. Say the station name the result gives, since similar names differ. Give the minutes as listed, and mention an alert in one short sentence."""
```

| Argument | Required | Maximum length |
|---|---|---|
| `station` | yes, so the model cannot call the tool without one | 60 |
| `line` | no | 3 |
| `direction` | no | 40 |

### 3.7 Benchmark coverage

- **Recorded feeds.** `benchmark/record_subway_fixtures.py` saves all nine feeds at one moment. The benchmark's tool server reads them instead of MTA's, with "now" pinned to that moment (`SUBWAY_FIXTURES_DIR`, `SUBWAY_NOW`), as the sports fixtures are.
- **Graded questions.** A new category L holds three: a station only (Court Square), a station and a line (the E at Queens Plaza), and a station and a direction (Manhattan-bound from Queens Plaza).
- **Injection.** One category H question plants an order in an alert's header in the recorded feed. The made-up alert names Queensboro Plaza's 7 platform, so only that question meets it.
- **Tool choice.** Four checks:
  - "next 7 from Queensboro Plaza";
  - "what's running at Court Square";
  - "next Manhattan-bound train from Queens Plaza";
  - "when's the next train?", whose right answer is no tool, because Jarvis must ask which station.

  The existing check "Is the Q train running normally right now?" accepts `subway_arrivals` as well as `search_and_read`.

### 3.8 Security: the new-tool checklist

The answers to doc 12 §3.12:

| # | Question | Answer |
|---|---|---|
| 1 | Tier, and does the output mark the exchange untrusted? | `read_public`, and yes. Arrival times are numbers, but alert headers are text people write, as ESPN's game notes are, and those are marked. |
| 2 | Quarantined reader? | No. Alerts come only from MTA's fixed host, only their headers are used, clipped to 40 words, and the exchange is marked untrusted. Recorded in `DEVIATIONS.md`. |
| 3 | Argument schema | Every string has a maximum length (§3.6). |
| 4 | What leaves the house? | Nine fixed requests to `api-endpoint.mta.info`, carrying no query. The arguments are matched against the local station table and never sent, so MTA learns nothing about which station you asked about. As a `read_public` tool, its arguments still pass the egress guard. |
| 5 | Credentials | None. The feeds need no key. |
| 6 | Terms and rate limits | MTA's data feed terms set no request limit. The 20-second hold keeps it to at most nine requests per 20 seconds, and only while you are asking. The terms require saying when data may be over a minute old, which §3.1 step 4 does. They also forbid presenting the data as accurate or MTA-endorsed, and Jarvis claims neither. Requests send `descriptive_user_agent("subway")`, which names the project. |
| 7 | Benchmark questions | §3.7, including an injection question through a planted alert. |
| 8 | Failure sentences | "Subway error: no station called X was found. Ask the user to say the station again." / "Several stations are called 86 St: … Ask the user which one." / "Subway error: MTA's train times did not answer. Tell the user you could not get train times right now." / "No trains are due at X in the next 40 minutes." / "These times are N minutes old and may not be real time." |

### 3.9 Context budget

| | Tokens |
|---|---|
| The tool's definition, added to the fixed prompt | about 310 (1,235 characters of name, description, and schema) |
| One result | about 100 to 200: a busy station with alerts at the upper end |

## 4. Packages and what they do for the business logic

| Package | What it does |
|---|---|
| `gtfs-realtime-bindings` (new) | Google's Python classes for GTFS-realtime, which decode the train feeds. It brings in `protobuf`. |
| `protobuf`'s descriptor API | Registers MTA's `nyct-subway.proto` extension in code, to read `is_assigned` (§3.1, step 5) |
| `httpx` (already a dependency) | Fetches the nine feeds in parallel, and the station dataset when the table is rebuilt |
| `subway_mcp/` (ours) | The feed client and cache, the station table, grouping, the direction filter, alerts, and the tool |

`gtfs-realtime-bindings` is pinned with its hash in `uv.lock`, like every package (doc 12 §3.10).

## 5. Configuration we control

**`SubwaySettings`**, read from `SUBWAY_`-prefixed environment variables:

| Setting | Default | Purpose |
|---|---|---|
| `feeds_base_url` | `https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/` | Where the feeds live |
| `timeout_seconds` | 8 | How long one fetch may take |
| `cache_seconds` | 20 | How long fetched feeds are reused |
| `keep_stale_seconds` | 300 | How old a copy may be and still answer when MTA does not |
| `stale_after_seconds` | 60 | Older data is said to be possibly not real time (MTA's terms) |
| `window_minutes` | 40 | How far ahead trains are listed |
| `trains_per_direction` | 3 | Trains listed in each group |
| `max_alerts` | 3 | Alerts listed per answer |
| `alert_words` | 40 | Words kept from each alert's header |
| `fixtures_dir`, `now` | unset | Recorded feeds and a pinned clock, for the benchmark only |

**Elsewhere:**

- `config/tools.toml`: `subway_arrivals` is `read_public` and `marks_untrusted`.
- `subway_mcp/stations.json`: the station table (§3.2).

## 6. Failure modes

| Failure | What happens | What to do |
|---|---|---|
| MTA's feeds are down | A copy under 5 minutes old answers, with its age; otherwise the tool says it could not get train times | Nothing; ask again later |
| MTA's data is over a minute old | The answer says the times may not be real time | Nothing |
| MTA moves the feeds or adds a key requirement | Every fetch fails, and the tool says it could not get train times | Update `feeds_base_url`, or add a key in the Keychain |
| Speech to text swaps Queens Plaza and Queensboro Plaza | The answer names the station it used, so you hear the mistake | Say the station again |
| A name fits several stations | The tool lists them, and Jarvis asks which | Name the line or the borough |
| MTA opens, closes, or renames a station | The table is out of date: the station is not found, or a missing line goes unexplained | Rebuild the table (§3.2) |
| An alert carries an injected order | The exchange is untrusted, so an act-tier tool would ask you first, and the egress guard checks every search | Nothing; the category H question tests it |
| Late at night, no train within 40 minutes | "No trains are due at X in the next 40 minutes." | Nothing |

## 7. Concepts for newcomers

**GTFS and GTFS-realtime.** GTFS is the shared format transit agencies use to publish timetables. GTFS-realtime adds live updates in the same terms: for each trip, its remaining stops and predicted times. It is encoded as protobuf.

**Protobuf.** Google's compact binary format for structured data. A program decodes it with classes generated from a `.proto` file describing the fields. An agency can add its own fields as an extension, as MTA does with `nyct-subway.proto`.

**Stop ID and direction.** MTA numbers each platform: `718` is Queensboro Plaza on the 7. A trailing `N` or `S` names the direction: `718N` is toward Flushing, `718S` toward Manhattan. North and south follow MTA's convention, not the compass.

**Station complex.** Stops joined by passageways under one name, such as the three Court Square platforms. You can transfer within a complex without leaving the system.

**Assigned train.** A trip MTA has given a crew and a train. Before that, a trip in the feed is only the timetable's plan.

## 8. Sources

- MTA developer resources: [mta.info/developers](https://www.mta.info/developers)
- MTA data feed terms and conditions: [mta.info/developers/terms-and-conditions](https://www.mta.info/developers/terms-and-conditions)
- MTA Subway Stations dataset: [data.ny.gov, 39hk-dx4f](https://data.ny.gov/Transportation/MTA-Subway-Stations/39hk-dx4f)
- GTFS-realtime reference: [gtfs.org/documentation/realtime/reference](https://gtfs.org/documentation/realtime/reference/)
- `gtfs-realtime-bindings` for Python: [pypi.org/project/gtfs-realtime-bindings](https://pypi.org/project/gtfs-realtime-bindings/)
- MTA's NYCT extension, `nyct-subway.proto`: [MTA developer resources](https://www.mta.info/developers)
