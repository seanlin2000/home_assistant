# Diagram Legend

Every diagram in this handbook uses four colours and one highlight. The colour says who is responsible for a box: blue is code written in this repository, grey is third-party software we run, green is a physical device, and red is anything whose traffic leaves the apartment.

Each colour, and the orange ring that marks the part a page is about:

```mermaid
flowchart TB
--8<-- "_includes/palette.mmd"
a("our code:<br/>written in this repository")
b("third-party software<br/>we run and configure")
c("a physical device")
d("traffic that leaves<br/>the apartment")
e("the part this page<br/>is about")
class a ours
class b third
class c hw
class d ext
class e third
class e current
```

Each shape has one meaning:

```mermaid
flowchart TB
--8<-- "_includes/palette.mmd"
%% grid: runs  stored  person
%% peers: runs stored person
runs("anything that runs:<br/>a service, device, API")
stored[("anything stored:<br/>a file, database, log")]
person(["a person:<br/>what you say or do"])
class runs,stored,person third
```

Lines, and boxes drawn around boxes, mean this:

| Looks like | Means | Example |
|---|---|---|
| `──▶` | sends or calls what its label says | our agent sends "tool calls" to the MCP server, on the [system map](index.md#the-system-map) |
| `┄┄▶` | copied later, when someone asks | the logs `mini.sh logs` pulls to the laptop, in [Logs and the report](10_operations.md#the-report) |
| `◀──▶` | both ways | the voice puck and speech to text, on the [system map](index.md#the-system-map) |
| a box drawn around boxes | where the boxes inside run or are kept | the Mac mini, the Home Assistant VM, and the log folder, in [Logs and the report](10_operations.md#the-report) |

The system map under every page's "Where this fits" is one shared drawing, `operator_manual/_includes/system_map.mmd`, and only its orange highlight changes from page to page. The rules behind every diagram are in the repository's [`draw-diagram` skill](https://github.com/seanlin2000/home_assistant/blob/main/.claude/skills/draw-diagram/SKILL.md).
