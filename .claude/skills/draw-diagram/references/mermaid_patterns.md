# Mermaid patterns

The exact text for each kind of diagram, and what makes the layout engine keep the layers. Flowcharts are laid out by ELK with `NETWORK_SIMPLEX` placement and a fixed light theme from `diagrams/mermaid_config.json`; `diagrams/polish.py` then stretches every subgraph into a band, moves its title into the header gutter, and rounds every corner. A source that declares a grid goes to `diagrams/grid.py` instead, which puts every box in the cell the source names.

## Layered flowchart

```
flowchart TB
--8<-- "_includes/palette.mmd"
subgraph clients["Who starts a request"]
  puck("Voice PE puck")
end
subgraph ha["Home Assistant"]
  stt("1. speech to text stage")
  tts("2. text to speech stage")
end
subgraph services["Services on the Mac"]
  whisper("Whisper")
  kokoro("Kokoro")
end
puck <-- "audio in, reply out" --> stt
stt -- "audio" --> whisper
tts -- "sentences" --> kokoro
class puck hw
class stt,tts,whisper,kokoro third
```

What keeps ELK honest:

- **One subgraph per layer, all siblings, declared in reading order.** Top row first in `TB`, left column first in `LR`. A nested subgraph or a loose node lets the engine scatter boxes, and the band post-processing then leaves the drawing alone.
- **Edges only cross layers, and only in the reading direction.** An edge inside a layer, or one pointing back, makes ELK invent a new layer. Two boxes in one layer that talk to each other get numbered labels ("1. speech to text stage", "2. intent matcher") or their own diagram. A reply is drawn on the forward edge as `a <-- "request, reply" --> b`; Mermaid has no arrow with a head only at the start.
- **A box goes in the layer of what calls it.** The Sonos speaker sits beside the Mac's services because Home Assistant calls it; the puck sits on top because it starts the request.
- **Let ELK order boxes inside a layer.** Crossing minimisation puts each target under its source; declare nodes in a sensible order because ties break on declaration order.
- **Titles are short.** They wrap inside a 180 px header column in a `TB` drawing and inside the column's width in an `LR` one; about eight words is the most that reads well.
- **Left-to-right diagrams keep edge labels to one to three words** and column titles short enough to wrap into two lines at the column's width. ELK widens the gap between rows to fit a label but not the gap between columns, so a long label in `LR` lands on the neighbouring column and its title. Anything that needs long labels is drawn `TB`, or the words move into the boxes.

## Fixed-grid flowchart

For a drawing whose placement is the point: a row of stages inside one machine, the service each stage calls hanging below it, and the machines drawn as containers around them. Sketch it in ASCII first, then write the grid, then the containers, then the edges.

```
flowchart TB
--8<-- "_includes/palette.mmd"
%% grid: puck    stt      intents  agent
%% grid: .       whisper  ma       ollama
%% grid: sonos   .        .        mcp
subgraph studio["Your studio: everything inside it stays local"]
  puck("Voice PE puck")
  sonos("Sonos speaker")
  subgraph mac["Mac, always on"]
    subgraph haos["Home Assistant OS, a virtual machine"]
      stt("speech to text stage")
      intents("intent matcher")
      agent("studio_assistant")
    end
    whisper("Whisper")
    ma("Music Assistant")
    ollama("Ollama")
    mcp("web_search_mcp")
  end
end
puck <-- "audio in,<br/>reply back" --> stt
stt --> intents
intents --> agent
stt --> whisper
intents -- "play X" --> ma
agent -- "LLM calls" --> ollama
ollama -- "tool call" --> mcp
ma -- "music" --> sonos
```

How the spec is read:

- **One `%% grid:` line per row**, ids in column order, `.` for an empty cell. Mermaid ignores `%%` lines and pymdownx carries them through a snippet include, so the layout travels with the diagram and cannot drift from it.
- **A column is as wide as its widest box and a row as tall as its tallest**, every box centred in its cell, so ids written in the same column really line up. Align the ids in the source too: the file should look like the picture.
- **Containers come from the subgraphs**, nested as deeply as the machines nest, each wrapping the cells of everything inside it with its title in a strip at the top. A node is counted as inside the subgraph whose block declares it, so give every node its own line there.
- **Edges are redrawn orthogonally**: straight between neighbouring cells, otherwise down into the gutter below the source row, across, and down into the target. When the target's column is blocked by a box in between, the line takes the gutter beside that column instead. Two lines leaving the same side of a box are spread across it, with the straight one keeping the centre.
- **Unlabelled edges from one box into the row below, or into the row above, share a bus**: they leave its centre, run along one line across the gutter between the box and that row, and drop (or rise) into the centre of each target, the arrowheads on the targets. A bus rising into the row above is drawn the same way even when a leg on its own would return by the right side. A labelled edge keeps a line of its own. The virtual machine figure on the Home Assistant page is the example of the upward bus: the Supervisor, below the five containers, feeds all of them through one trunk.
- **A crowded gutter gives every run a level of its own.** When two edges would run along one line in a gutter, such as a bus trunk and another box's staircase, or a leg landing on another edge's straight drop into the same box, every edge crossing that gutter gets its own level, 20 px apart, and its own point on each box it touches, the points on one half of a column spread evenly across it. The order is the one with the fewest crossings; among equals, the run reaching furthest sits highest. The gap grows to hold the levels plus a band above them, where the labels of the edges starting down into the gutter sit beside their own lines, outside the pair. The question router in the conversation-agent page is the example: two sources each feeding two shared targets cross once, and never share a line.
- **Labelled edges converging on one box share a turn.** When boxes in one row each send a labelled edge to one box in the row below and one of those labels finds no clear spot on its own line, the staircases among them turn on one level, the gap grows to hold a label band above it, and every label sits right of its own line between its box and that level, the straight drop's label level with the others. The setup-script figure on the Home Assistant page is the example: three steps each save a key to `.env`, the key named beside the line that leaves the step.
- **Edge labels sit on the longest clear segment** of their own line. A label between two neighbouring boxes widens the gap it sits in, so keep labels to a word or three and split a two-part label with `<br/>`.
- **Two neighbours that send each other something get two parallel lines** 40 px apart. The edge written first in the source runs above the centre line in a row, or left of it in a column, and the other one below it or right of it, whichever way each points. In a row each label sits on its own line; in a column each label sits outside its own line, the two labels level. Write the pairs in the order the sketch stacks them: for a column of stages with side boxes on both sides, each stage's request to its side box first and the reply second, so the request runs above on the left as well as on the right:

```
stt -- "audio" --> whisper
whisper -- "the words" --> stt
agent -- "the chat, tool list" --> ollama
ollama -- "tool call, then answer" --> agent
```

- **An id written in two neighbouring cells of one row spans them.** The box is centred over the stretch and widens neither column. Its edges land in the centre of the box at their other end, the way a bus's legs do, and only on the spanning box are they spread to the side facing that box, so an edge rising into it never returns by the right. A labelled one crosses the gutter half a row gap from the spanning box, the gap grows to hold a label band beside the other box, and the label sits right of the leg into (or out of) that box.
- **`<id` and `id>` hang a box under one half of its column.** The box moves half its width left or right, so its inner edge sits on the column's centre line, and a pair between it and the box above runs down the middle of the stretch the two share, a quarter of the way in from the upper box's side. Two boxes under one stage, a row apart, take one half each, and the lower one's lines pass beside the upper one. A container holding a hung box wraps the box itself. The Voice page's figure is the example:

```
%% grid: .        puck     .
%% grid: stt      intents  tts
%% grid: .        .        piper>
%% grid: whisper  .        <kokoro
```

- **A device over a box it does not feed enters its machine under itself.** The puck above hangs over the intent matcher and feeds the stages either side of it. Its edges cross the container tops straight under the puck, a quarter of its width from its centre, turn on a level inside the innermost container, midway between that container's title and its top row, and meet each stage in the centre of its top; the edge back to the puck runs the same way upward. That container's title strip grows by 32 px to hold the turn, the titles stay at the left because no line crosses them, and each label sits right of its own line between the device and the outermost container. A device that does feed the box beneath it keeps the staircase above the containers.
- **An id written in the same column of two neighbouring rows is centred between them**, heightening neither row. Use it for a box that feeds a column of services from level with its middle.
- **A fan-out into the next column.** A box whose edges reach boxes both above and below it in the neighbouring column leaves its side on one line, turns on a trunk 24 px past its column and any container ending there, and branches into the side of each target, arrowheads 4 px short. Each label sits on its own branch between the trunk and the target column's first border, and the gap grows to 24 px plus the widest label plus its clearance. The Hardware page's places figure is the example:

```
%% grid: .haos   health   .docker
%% grid: .haos   mcp      searxng
%% grid: core    kokoro   .
%% grid: core    whisper  .
%% grid: addons  ollama   .
%% grid: .       gpu      .
```

- **A fan-in into a later column's side.** Unlabelled edges from several boxes in one column to one box in a later column, level with the topmost source or above it, leave each source's right side for one trunk 24 px past the column, outside any container around that column alone and inside the machine around them (which grows 24 px to hold it), rise to the target's row, and enter the target's side. Each line climbs only to the one above it. A straight line already entering that side from the same row takes the trunk in, and only it keeps an arrowhead; with no such line the topmost source's line carries the arrowhead in. The Operations page's logs figure is the example, three log folders' files joining the Assist debug runs line into `mini.sh logs`:

```
%% grid: debug  .         .          minilogs
%% grid: agent  mcp       exchanges  mirror
%% grid: .      launchd   svclogs    reportp
%% grid: .      healthchk hfiles     .
```

- **A join down a column, `%% join: <id>`.** Unlabelled edges from several boxes in one column to one box further down the same column, with that box named on a `%% join:` line, leave each source's right side for one trunk 24 px past the column, inside the innermost container holding the sources and the target (which grows to reach 18 px past the trunk), drop to the target's row, and enter its right side. Each line descends only to the one below it; the nearest source's line carries the one arrowhead. The legs never count as lines passing beside the boxes in between, so the target keeps its size. The Development page's path-to-main figure is the example, three CI jobs joining into branch protection:

```
%% grid: hook     checksjob
%% grid: push     descjob
%% grid: .laptop  docsjob
%% grid: fix      protect
%% join: protect
```

- **Staggered branches.** Elbows from one box toward one side, into different rows, each leave at a point of their own: the nearest row's a quarter of the box's width from its centre toward the targets, the farthest a quarter away, the rest evenly between. The farther lines drop outside the nearer ones and run under their corners without sharing a stretch or crossing, and each label sits beside its own drop on the targets' side, a farther one's below the nearer one's turn. The Operations page's deploy figure is the example (the smoke test's pass and fail).
- **A line passes beside the boxes in its way.** An edge down (or up) its own column with a box in between leaves the source's side, the one fewer other edges reach (the right on a tie), runs 28 px clear of the boxes it passes, and lands on the top of the box below, which widens about its centre until the line lands 28 px inside its corner. The label sits past the last container border the line crosses, and a straight line into the same box puts its label there too, so the two sit level (Whisper and Ollama into the GPU above).
- **Left-to-right elbows.** In a `flowchart LR` figure, outside every container, an edge to a later step one row down drops out of the source and turns into the target's side, and an edge to a later column higher up runs along its row under the empty cells and rises into the target's bottom, its label on the rise. The reboot figure on the Hardware page is the example; top-to-bottom figures keep their staircases.
- **A vertical pair keeps its labels clear.** Each label sits outside its own line; when the pair passes a row on its way (Whisper's pair passes the Piper row), the labels sit halfway between the last container border it crosses and the box it reaches. A container around a pair at its edge reaches past its column far enough that each label is as far from the border as from its line.
- **A tucked detour is reached by its side.** A box fed from the row above that also feeds back into it, hanging under a box it has no edge with, would otherwise take a line into its top that reads as coming from the box above. Instead the edge into it drops down the source's centre line into its side, and the edge out of it leaves by its side and rises into the target's centre, each label right of the vertical line. It needs the corner cell the line turns in to be empty. The Assist pipeline figure on the Home Assistant page is the example:

```
%% grid: .    puck     puck     .
%% grid: stt  intents  builtin  tts
%% grid: .    .        agent    .
```

- **An invisible link, `a ~~~ b`, holds a slot open.** It draws nothing, no line and no arrowhead, but it counts as the forward edge of a pair, so a lone return edge keeps the lower (or right-hand) slot it has in a companion figure that draws both.
- **`%% peers: a b c`** gives every listed box, cylinder, or stadium the widest one's width and the tallest one's height about its own centre, and evens the gaps between them; a stadium keeps fully round ends, each a half circle of half the new height. A diamond cannot be a peer.
- **`%% column-gap: N`** sets the least gap between columns to N px (the default, and the floor, is 76 px). A label wider than the gap still widens it. Two figures that are meant to be compared declare the same N, taken from the widest label between neighbouring columns in either figure plus 28 px, so their boxes sit in the same places:

```
%% grid: pipeline  agent  ollama
%% grid: .         mcp    .
%% peers: pipeline agent ollama mcp
%% column-gap: 210
```

- Every id in the grid must exist in the diagram, and every node must appear in the grid.

## Decision flowchart

```
flowchart TB
--8<-- "_includes/palette.mmd"
question(["the user's latest message"]) --> explicit{"an explicit request to search?"}
explicit -- "yes" --> search("search")
explicit -- "no" --> stale{"could the answer have changed recently?"}
stale -- "yes" --> search
stale -- "no" --> answer("answer from the model")
class search,answer ours
```

No subgraphs. Each decision is its own row, every outcome edge points down and is labelled, and the terminal boxes sit in the bottom row. A "try again" loop that would point back up is drawn as a terminal box saying what happens next ("next candidate").

## Sequence diagram

```
sequenceDiagram
  box rgb(220,252,231) Devices
    participant puck as Voice PE puck
  end
  box rgb(241,245,249) Third-party
    participant ha as Home Assistant
  end
  box rgb(219,234,254) Our code
    participant agent as conversation agent
  end
  puck->>ha: audio
  ha->>agent: text
  agent-->>ha: sentences
  ha-->>puck: audio
```

Order participants left to right in the direction the first request travels. Group them with `box rgb(...)` using the palette fills: `rgb(219,234,254)` ours, `rgb(241,245,249)` third-party, `rgb(220,252,231)` devices, `rgb(254,226,226)` leaves the apartment. At most six participants and about fourteen messages; a longer exchange splits by phase. Notes are one short line with no `;`, and no participant is named `loop`, `end`, `opt`, `alt`, or `par`.

## State diagram

```
stateDiagram-v2
  [*] --> healthy
  healthy --> failing: probe fails
  failing --> healthy: probe passes
  failing --> restarted: three failures
  restarted --> healthy
```

Only when a thing really has states, and at most six of them.

## Syntax rules

- Always double-quote labels so colons, parentheses, and `+` never break the parser; `<br/>` for a line break; at most three short lines.
- Subgraph titles use square brackets, `subgraph id["Title"]`; that is the one place square brackets remain.
- Node ids never start with a digit and are reused when two diagrams show the same thing (`puck`, `stt`, `agent`, `ollama`, `mcp`, `searxng`, `sonos`, `laptop`, `health`).
- No `%%{init}%%` except a per-figure `flowchart.wrappingWidth` (diagrams render at build time, so mermaid-cli honours it), no `@{ shape: ... }`, no `direction` inside a subgraph, no colours outside the palette.
