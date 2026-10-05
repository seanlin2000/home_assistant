---
name: draw-diagram
description: Draw, redraw, or review a diagram to this project's readability standard. Diagrams are Mermaid text rendered by the diagrams package (mermaid-cli, the ELK layout engine, one fixed light theme, rounded shapes, and either full-width bands or a fixed grid the source pins). Use whenever a diagram is written or changed anywhere in the repository: a handbook page, a PR entry, a design doc, a README. Holds the ASCII-sketch-first workflow, the twelve rules a diagram is judged by, the shape and colour vocabulary, the authoring patterns, and the render-and-look loop. The operator-manual skill invokes it for every diagram.
argument-hint: <diagram.mmd | page.md> [--png <dir>]
---

# Draw a diagram

A diagram in this repository is judged by a person looking at the rendered picture, against the twelve rules below. The rendering pipeline (`diagrams/`) does part of the work: it lays flowcharts out with ELK so declared layers stay in order, stretches every layer into a full-width band and moves its title into a header column at the left (or a full-height column with the title in a strip along the top), or, when the source pins a grid, puts every box in the cell the source names; then it rounds every corner, tints containers faintly, and spaces boxes generously. What the pipeline cannot do is decide the placement, the shapes, the colours, and the words. That is this skill.

Arguments: `$ARGUMENTS`. A `.mmd` file is rendered on its own; a `.md` page has every ```mermaid fence rendered. With `--png <dir>` the pictures are written there; without it, use a scratch directory.

Read `references/mermaid_patterns.md` before authoring: it holds the exact Mermaid text for each kind of diagram, the grid spec, and the syntax that is forbidden.

## 1. Sketch the layout in ASCII first

**Before any Mermaid is written, draw the diagram as an ASCII sketch.** Place every box by hand: what contains what, which boxes share a row, which share a column, what each axis means, where each arrow runs. Boxes as `┌─┐`, arrows as `──▶`, containers as boxes drawn around boxes, captions where the titles will go.

The sketch is the layout decision. Mermaid is only the renderer that gives that decision rounded boxes, the palette's colours, and real arrowheads. Author the Mermaid to be faithful to the sketch. When the layout engine will not reproduce the sketch's placement, pin it with the fixed grid in section 3; never let the engine's preference override the sketch.

The worked example is the system map: the ASCII diagram in `design_docs/v1/00_system_overview.md` §2 is the sketch, and `operator_manual/_includes/system_map.mmd` is that sketch rendered, with the same containment, the same rows and columns, and the same flow.

### Where sketches are kept

Every sketch is committed in `diagrams/sketches/`, so a later review can compare a figure with the layout it was drawn from.

- **A script and its output.** Anything beyond a simple chain is drawn by a script, `<page>_<name>_vN.py`, that places boxes, lanes, and crossings by coordinate (on `canvas.py`'s character canvas, which refuses overlaps), so every line comes out the same width. Its output is saved beside it as `<page>_<name>_vN.txt`. `<page>` is the handbook page's number (`00` for the introduction and the system map, `legend` for the Diagram Legend).
- **Run from the folder.** The scripts import `from canvas import Canvas`, so run them there: `cd diagrams/sketches && uv run python 04_router_v2.py`. The pre-commit hook checks them like any other Python file (black, isort, deslop).
- **A header on the `.txt`.** Its first lines name the figure and its page, say whether the version is proposed or approved, and say what it supersedes and why. The script prints only the drawing, so a regenerated `.txt` keeps those lines.
- **A new version is a new file.** A revision is `_v2`, never an edit to the approved `_v1`. Once a figure ships, delete the versions it superseded; git history keeps them.

### What makes a layout good

1. **Use both axes.** One axis carries sequence, the other, together with containment, carries place and ownership, so the picture answers two questions at once: what happens in what order, and where does each part run.
2. **Containment draws a real boundary.** A container is a machine, a virtual machine, a network, a trust boundary, never decoration. On the system map the arrows that cross the studio's edge are exactly the traffic that leaves the apartment.
3. **The layout matches the question the diagram answers.** A "where does this fit" diagram is place-based; a diagram of one exchange over time is time-based. Either way it fits on one screen, the text stays short, and a concrete example in a label earns its place ("play X", "weather").

## 2. Choose the kind

| The picture shows | Kind | Layers |
|---|---|---|
| Tiers of a system: who calls whom | Layered flowchart, `flowchart TB` | One row per tier, top row calls the row below |
| The stages of one process in order | Layered flowchart, `flowchart LR` | One column per stage, left to right |
| Where every part runs, and the path through them | Fixed-grid flowchart, `flowchart TB` | Nested containers for the machines, a grid spec for the placement |
| A chain of rules that ends in outcomes | Decision flowchart, `flowchart TB`, no containers | One decision per row, outcomes in the bottom row |
| Three or more parties exchanging messages over time | `sequenceDiagram` | One column per participant, in the order the first request travels |
| A thing that really has states | `stateDiagram-v2` | At most six states |

Split anything with more than about eighteen boxes into two diagrams.

## 3. Pin the placement when the engine will not

ELK places boxes by its own rules. That is enough for a layered diagram, where the only thing that must survive is the order of the layers, and it is not enough for a sketch such as the system map: a row of pipeline stages inside a virtual machine, each with the service it calls hanging directly below it, inside the machine that runs them all. For a sketch like that, declare the grid in the source and `diagrams/grid.py` lays the rendered drawing out on it.

The spec is `%%` comment lines, which Mermaid ignores and a snippet include carries along, one line per row, the ids in column order, `.` for an empty cell:

```
%% grid: puck    stt      intents  agent    tts
%% grid: .       whisper  ma       ollama   kokoro
%% grid: sonos   .        .        mcp      .
```

Columns are as wide as their widest box, rows as tall as their tallest, and every box is centred in its cell, so a box written under another really sits under it. Each `subgraph` becomes a container wrapping the cells of everything inside it, however deeply nested, with its title in a strip at the top of it. Every edge is redrawn as an orthogonal line: straight between neighbouring cells, and through the gutters between the cells otherwise. Several unlabelled edges from one box into the row below, or into the row above, share one bus: one line across the gutter between the box and that row, a leg dropping (or rising) into the centre of each target, every arrowhead on a target. A box that starts everything above it, such as a Supervisor under the containers it runs, is written with its edges pointing at them and gets the upward bus. Where two edges would otherwise run along one line in a gutter (a bus trunk and another box's staircase, or a leg landing on another edge's straight drop), that gutter is crowded: every edge crossing it gets a level of its own, 20 px apart, and its own point on each box, spread across the half of the box facing the other end. The order of levels and points is the one with the fewest crossings, the furthest-reaching run highest among equals. The gap grows to hold the levels, with a band above them for the labels of the edges starting down into it, which sit beside their own lines. Labelled edges from several boxes in one row converging on one box in the row below, such as the steps of a chain each saving a key to one file, keep their labels on their own lines when those fit; when one would land on a neighbour's line, their turns share one level; the gap grows to hold a band above that level, and each label sits right of its own line where it leaves its box.

Authoring a grid diagram:

- **Every node gets exactly one cell**, and every cell names a node of the diagram. Line the ids up in columns in the source; the file then reads like the picture.
- **Declare each node on its own line inside its subgraph.** That is how the renderer learns what each container holds.
- **Nested subgraphs are the point here** (the ban under "Forbidden" is for layered diagrams). Containers nest as machines nest: the studio holds the Mac, the Mac holds the virtual machine.
- **Leave a column free where a line has to pass a row**, or the renderer takes it down the gutter beside the target column, which is tidy but longer.
- **Reserve an empty cell for a container with `.name`.** The cell stays empty, but container `name` (and every container around it) reaches over it. Use it when a sketch's machine encloses the stretch an edge runs through below its boxes, as in `%% grid: .      .mac .        pages`.
- **Centre a box over two columns by writing its id in both cells**, as in `%% grid: .    puck     puck     .`, for a device centred above the row of stages it feeds. It widens neither column; its edges land in the centre of the box at their other end, and a labelled one crosses the gutter half a row gap from the spanning box, with its label right of the leg into (or out of) the other box.
- **Hang a box under one half of the box above with `<id` or `id>`.** Written `<kokoro` the box moves left by half its width, written `piper>` right, so its inner edge sits on its column's centre line. Two engines under one stage, a row apart (Piper inside the virtual machine, Kokoro below it on the Mac), each hang under a half of their own, and the lower one's pair of lines passes beside the upper one instead of through it. A container holding a hung box reaches around the box, not just its column.
- **Centre a box between two rows by writing its id in the same column of both**, as in `%% grid: core    kokoro` above `%% grid: core    whisper`, for the box that feeds a column of services from level with its middle. It heightens neither row.
- **A box feeding boxes both above and below it in the next column fans out.** One line leaves its side for a trunk 24 px past its column (and past any container ending there), and a branch runs from the trunk into the side of each box, each label on its own branch, as a sketch draws a fan-out bus. The gap grows to hold the trunk and the widest label. A box feeding only the box level with it and those below keeps its straight line. The places figure on the Hardware page is the example (Home Assistant into four services), and so is the login fan-out of its reboot figure.
- **Several files in one column read by one box further right fan in.** When unlabelled edges from boxes in one column (stored files in a folder, say) all reach one box in a later column that sits level with the topmost of them or above it, each leaves its right side for one trunk 24 px past the column: outside any container around that column alone (the folder), inside the machine around them, which reaches 18 px past the trunk. The trunk rises to the target's row and enters its side. If a straight line already enters that side from the same row (Assist debug runs into `mini.sh logs`), the trunk joins it and the target gets one arrowhead; otherwise the topmost file's line carries the arrowhead in. Each file's line climbs only to the one above it, so no stretch is drawn twice and no line crosses a container title. The logs figure on the Operations page is the example.
- **Boxes that all gate one box below them join on the right with `%% join: <id>`.** Several boxes in one column whose unlabelled edges all reach one box further down that column, such as three CI jobs that must pass before branch protection lets a merge through, are drawn the way a sketch draws a join bus once the target is named on a `%% join:` line: each leaves its right side for one trunk 24 px past the column, inside the innermost container holding them all, which reaches 18 px past the trunk, and the trunk drops into the right side of the target, the nearest box's line carrying the one arrowhead. Without the line, an edge that skips a box passes beside it and widens the target to land on its top. The path-to-main figure on the Development page is the example.
- **Branches out of one box to rows further down leave at points of their own.** When a box sends elbows (down, then across into a side) toward boxes on one side in different rows, such as a smoke test's pass one row down and its fail two rows down, the nearer row's line leaves a quarter of the box's width from its centre toward the targets and the farthest a quarter away from them, the rest evenly between. Each farther line drops outside the nearer ones and runs under their corners, with no shared stretch and no crossing, and each label sits beside its own drop on the targets' side, a farther one's below the nearer one's turn. The deploy figure on the Operations page is the example.
- **A line down a column passes beside the boxes in its way.** An edge from a box to one further down its column, with a box in between, leaves the source's side (the side fewer other edges reach, the right on a tie), runs 28 px clear of the boxes it passes, and drops into the top of the box below; that box widens about its centre until the line lands 28 px inside its corner, like a base the column stands on. Its label sits past the last border it crosses, level with the label of a straight line into the same box. Boxes hung under one half (`<id`, `id>`) already pass each other and are left alone.
- **A left-to-right figure takes its elbows by the side.** In a `flowchart LR` figure, outside every container, an edge to a later step one row down drops out of the source and turns into the target's side, and an edge to a later column higher up runs along its row, under the empty cells, and rises into the target's bottom with its label on the rise. The reboot figure on the Hardware page is the example. A `flowchart TB` figure keeps its staircases.
- **A device over a box it does not feed enters under itself.** When a box above a machine hangs over a box it has no edge with and feeds the boxes either side (the puck over the intent matcher, feeding speech to text and hearing back from text to speech), its lines cross the container tops straight under the device, a quarter of its width from its centre, turn inside the innermost container, midway between its title and its top row, and meet each box in the centre of its top. The container's title strip grows to hold that turn, the titles stay at the left, and each label sits right of its line between the device and the outermost container. A device over a box it does feed keeps the staircase above the containers.
- **A detour under an unrelated box is entered and left by its side.** A box fed from the row above that also feeds back into it, hanging under a box it has no edge with (our agent under the built-in handler, taking over when no sentence matches), is tucked: the edge into it comes down the source's centre line and into its side, the edge out of it leaves by its side and rises into the target's centre, each label right of its vertical line. A box that only receives from the row above, such as an outcome, keeps its staircases. The Assist pipeline figure on the Home Assistant page is the example of both.
- **Make peer boxes one size with `%% peers: a b c`.** Every listed box, cylinder, or stadium takes the widest one's width and the tallest one's height (a stadium keeping fully round ends), labels stay centred, and the gaps between them are evened. List the boxes of every row or chain whose members are peers (rule 12).
- **Keep edge labels to a word or three.** A label between two neighbouring boxes widens the gap it sits in, so a long one pushes whole columns apart.
- **Give figures meant to be compared one column gap with `%% column-gap: N`.** Every gap between columns is then at least N px (never less than the default 76 px), and it still grows where a label needs more. When two figures with the same grid and peers sit together on a page, such as two rounds of one exchange, give both the same N: the widest label between neighbouring columns in either figure, plus 28 px. Every box then lands in the same place in both.
- **Write each pair in the order the sketch stacks it.** Two neighbours that send each other something get two parallel lines, and the edge written first in the source takes the line above the centre (in a row) or left of it (in a column), whichever way it points. A sketch that draws every side box's request above its reply, on both sides of a column, is written request first, reply second, for every pair.
- **A vertical pair's labels stay clear of borders and rows.** When a pair passes a row on its way down, as Whisper's pair passes the Piper row, its labels sit below the last container border it crosses, beside the box it reaches, rather than halfway down among that row's boxes. A container around a pair at its edge reaches far enough to keep each label as clear of its border as of its own line.
- **Hold a slot open with an invisible link.** In a vertical pair each label sits outside its own line. When a companion figure keeps only the return edge, write `a ~~~ b` in place of the missing forward edge. It draws nothing, no line and no arrowhead, but it keeps the return line in the slot it has in the companion.
- Use the grid only when a layout genuinely needs pinning. The layered flowchart in `references/mermaid_patterns.md` remains the default.

## 4. Author it with the vocabulary

**Layers.** In a layered flowchart every box sits inside exactly one `subgraph`, all subgraphs are siblings declared in reading order, and every edge crosses from one layer to a later one. A box goes in the layer of whatever calls it. The subgraph title names the layer in words a newcomer understands ("Home Assistant, a virtual machine on the Mac").

**Shapes.** Four, each with one meaning. Nothing else.

| Shape | Mermaid | Meaning |
|---|---|---|
| Rounded rectangle | `id("text")` | Anything that runs: a process, a service, a device, an external API. Colour says which |
| Cylinder | `id[("text")]` | A data store: a file, a database, a cache, a log |
| Diamond | `id{"text"}` | A decision, only in a decision flowchart |
| Stadium | `id(["text"])` | Something a person says or does |

**Colours.** Four fills plus one highlight; the meaning is ownership, so a reader can tell at a glance what this repository is responsible for, what it merely runs, what is hardware, and what leaves the apartment. The legend page of the handbook states this and every diagram uses exactly these classes.

| Class | Fill | Meaning |
|---|---|---|
| `ours` | light blue | Code in this repository |
| `third` | light grey | Third-party software the project runs and configures |
| `hw` | light green | A physical device |
| `ext` | light red | Anything whose traffic leaves the apartment |
| `current` | orange outline | The part this page is about; applied last so it wins |

In the handbook the classes come from `operator_manual/_includes/palette.mmd` through a snippet include. Elsewhere, paste the five `classDef` lines from that file verbatim.

**Words.** Labels are two to five words, or two short lines split with `<br/>`, always double-quoted. Edge labels name what travels ("audio", "tool call"). Node ids are lowercase ASCII, stable across the repository, and never start with a digit.

## 5. Render and look

```
uv run draw-diagram path/to/diagram.mmd --png out/diagram.png        # one loose diagram
uv run manual-check --png out/ operator_manual/<page>.md             # every fence of a handbook page, as out/<page>_<line>.png
```

Both need `mmdc` (`brew install mermaid-cli`) and Google Chrome. A running `mkdocs serve` keeps the `diagrams` package it imported at start, so after editing anything in `diagrams/` restart it and clear `.cache/manual_diagrams/`. A parse error is printed with the diagram line. Open every PNG with the Read tool and judge it against the sketch first and the rules second. Fix the source and render again until the picture is the sketch and every rule holds. Iterate one image at a time; a diagram nobody has looked at does not ship.

## 6. The twelve rules

1. **Position carries meaning.** Rows in a top-down diagram, columns in a left-to-right one, each a tier of the system or a stage of a process. A reader learns the architecture from where a box sits.
2. **Layers are in line.** Every row spans the full width and every column the full height, with titles in one header gutter, so the eye never zig-zags between a layer on the far left and the next on the far right. In a grid diagram the cells line up instead, and each container's title sits in its own strip.
3. **Text in every box is visible.** Light fills, dark text, labels that fit their box.
4. **Nothing is dark.** No black or dark grey background, no white text.
5. **No text over arrows.** A title, a label, or an edge label never crosses an edge. Titles live in their own gutter or strip for that reason; an edge label that lands on a box or a title means the label is too long or the diagram is `LR` when it should be `TB`.
6. **Arrows are tidy.** Once the boxes are placed, edges run straight from a box to the box below or beside it, turn only at right angles, flow in one direction, cross rarely, and never loop around the outside of the drawing.
7. **Corners are soft.** Every shape is rounded; the pipeline does this, so never draw a sharp-cornered shape by hand.
8. **Colour has stated meaning.** Only the five classes above, and the meaning is written where the reader can find it.
9. **Shapes are standard and meaningful.** Only the four shapes above, each used for its one meaning; a device is a rounded rectangle in green, not a double-edged box.
10. **Containers are translucent and spacing is generous.** A container's tint is faint enough that the boxes inside it stand out, and boxes never crowd each other or the edges.
11. **The diagram explains itself.** No prose after a figure tells the reader how to read it: not its rows, its colours, its shapes, or its highlight. The key lives once on the legend page. Text near a figure adds only facts the drawing does not show.
12. **Peer boxes share one size.** Boxes in one row or chain have the same width, the same number of text lines, and even gaps; pad short text rather than letting a box shrink to fit it, and move a detail to prose rather than let one box grow taller than its neighbours. Declare them with `%% peers:`.

## Forbidden

- In a layered diagram: nested subgraphs, boxes outside every subgraph, `direction` inside a subgraph, edges within a layer or against the reading direction. A fixed-grid diagram nests containers on purpose and places every box itself.
- Any shape other than the four, including `[["..."]]`, `>"..."]`, and Mermaid 11 `@{ shape: ... }`.
- `%%{init}%%` directives other than `%%{init: {"flowchart": {"wrappingWidth": N}}}%%`, which widens one figure's label wrapping when a single line would otherwise break; colours outside the palette; `style` lines other than the orange highlight of a subgraph.
- Titles longer than about eight words: they wrap in the header gutter, and a long one becomes a paragraph.
