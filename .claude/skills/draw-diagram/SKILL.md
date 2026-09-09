---
name: draw-diagram
description: Draw, redraw, or review a diagram to this project's readability standard. Diagrams are Mermaid text rendered by the diagrams package (mermaid-cli, the ELK layout engine, one fixed light theme, every layer turned into a full-width band, rounded shapes). Use whenever a diagram is written or changed anywhere in the repository: a handbook page, a PR entry, a design doc, a README. Holds the ten rules a diagram is judged by, the shape and colour vocabulary, the authoring patterns, and the render-and-look loop. The operator-manual skill invokes it for every diagram.
argument-hint: <diagram.mmd | page.md> [--png <dir>]
---

# Draw a diagram

A diagram in this repository is judged by a person looking at the rendered picture, against the ten rules below. The rendering pipeline (`diagrams/`) does part of the work: it lays flowcharts out with ELK so declared layers stay in order, stretches every layer into a full-width band with its title at the left (or a full-height column with the title at the top), rounds every corner, tints containers faintly, and spaces boxes generously. What the pipeline cannot do is choose the layers, the shapes, the colours, and the words. That is this skill.

Arguments: `$ARGUMENTS`. A `.mmd` file is rendered on its own; a `.md` page has every ```mermaid fence rendered. With `--png <dir>` the pictures are written there; without it, use a scratch directory.

Read `references/mermaid_patterns.md` before authoring: it holds the exact Mermaid text for each kind of diagram and the syntax that is forbidden.

## 1. Choose the kind

| The picture shows | Kind | Layers |
|---|---|---|
| Tiers of a system: who calls whom | Layered flowchart, `flowchart TB` | One row per tier, top row calls the row below |
| The stages of one process in order | Layered flowchart, `flowchart LR` | One column per stage, left to right |
| A chain of rules that ends in outcomes | Decision flowchart, `flowchart TB`, no containers | One decision per row, outcomes in the bottom row |
| Three or more parties exchanging messages over time | `sequenceDiagram` | One column per participant, in the order the first request travels |
| A thing that really has states | `stateDiagram-v2` | At most six states |

Split anything with more than about sixteen boxes or six layers into two diagrams.

## 2. Author it with the vocabulary

**Layers.** Every box in a layered flowchart sits inside exactly one `subgraph`, all subgraphs are siblings declared in reading order, and every edge crosses from one layer to a later one. A box goes in the layer of whatever calls it. The subgraph title names the layer in words a newcomer understands ("Home Assistant, a virtual machine on the Mac").

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

**Words.** Labels are two to five words, or two short lines split with `<br/>`, always double-quoted. Edge labels name what travels ("audio", "tool calls over MCP"). Node ids are lowercase ASCII, stable across the repository, and never start with a digit.

## 3. Render and look

```
uv run draw-diagram path/to/diagram.mmd --png out/diagram.png        # one loose diagram
uv run manual-check --png out/ operator_manual/<page>.md             # every fence of a handbook page, as out/<page>_<line>.png
```

Both need `mmdc` (`brew install mermaid-cli`) and Google Chrome. A parse error is printed with the diagram line. Open every PNG with the Read tool and judge it against the rules. Fix the source and render again until every rule holds. Iterate one image at a time; a diagram nobody has looked at does not ship.

## 4. The ten rules

1. **Position carries meaning.** Rows in a top-down diagram, columns in a left-to-right one, each a tier of the system or a stage of a process. A reader learns the architecture from where a box sits.
2. **Layers are in line.** Every row spans the full width and every column the full height, with titles at the same edge, so the eye never zig-zags between a layer on the far left and the next on the far right.
3. **Text in every box is visible.** Light fills, dark text, labels that fit their box.
4. **Nothing is dark.** No black or dark grey background, no white text.
5. **No text over arrows.** A title, a label, or an edge label never crosses an edge. Shorten the title or move the box.
6. **Arrows are tidy.** Once the boxes are placed, edges run straight from a box to the box below or beside it, flow in one direction, cross rarely, and never loop around the outside of the drawing.
7. **Corners are soft.** Every shape is rounded; the pipeline does this, so never draw a sharp-cornered shape by hand.
8. **Colour has stated meaning.** Only the five classes above, and the meaning is written where the reader can find it.
9. **Shapes are standard and meaningful.** Only the four shapes above, each used for its one meaning; a device is a rounded rectangle in green, not a double-edged box.
10. **Containers are translucent and spacing is generous.** A layer's tint is faint enough that the boxes inside it stand out, and boxes never crowd each other or the edges.

## Forbidden

- Nested subgraphs, boxes outside every subgraph in a layered diagram, `direction` inside a subgraph, edges within a layer or against the reading direction.
- Any shape other than the four, including `[["..."]]`, `>"..."]`, and Mermaid 11 `@{ shape: ... }`.
- `%%{init}%%` directives, colours outside the palette, `style` lines other than the orange highlight of a subgraph.
- Titles longer than one line at the drawing's width.
