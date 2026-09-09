# Diagram style

Every diagram is Mermaid text inside a ```mermaid fence. At build time an MkDocs hook (`manual_checks/mkdocs_hook.py`) renders each fence with mermaid-cli and the fixed light theme in `manual_checks/mermaid_config.json`, and the page shows that SVG on a white card in both colour schemes. Flowcharts are laid out by ELK, not dagre. `manual-check` renders every block the same way and rejects any `classDef` that is not in the palette and any class name outside it.

## The four rules

Every diagram is judged against these before it ships:

1. **Position carries meaning.** A top-down diagram is a stack of rows, a left-to-right diagram is a series of columns, and each row or column is one layer of the system (the devices, Home Assistant, the Mac's services, the internet) or one stage of a process. A reader learns the architecture from where a box sits.
2. **Text inside every box is visible.** Light fills, dark text, labels that fit. A label that wraps into the border or hides behind an edge fails.
3. **No dark backgrounds.** Nothing is drawn white on black or dark grey; every colour comes from the palette and reads against the white card.
4. **Edges are tidy.** Once the boxes are in layers, the edges run straight from a box to the box below or beside it, in one direction, with few crossings and no loop around the outside of the drawing.

## Layered flowcharts

This is the shape of every architecture and data-flow diagram, including the system map.

```
flowchart TB
--8<-- "_includes/palette.mmd"
subgraph clients["Who starts a request"]
  puck[["Voice PE puck"]]
end
subgraph ha["Home Assistant"]
  stt["1. speech to text stage"]
  tts["2. text to speech stage"]
end
subgraph services["Services on the Mac"]
  whisper["Whisper"]
  kokoro["Kokoro"]
end
puck <-- "audio in, reply out" --> stt
stt -- "audio" --> whisper
tts -- "sentences" --> kokoro
class puck hw
class stt,tts,whisper,kokoro third
```

Rules that make ELK keep the layers:

- **Direction.** `flowchart TB` when the layers are tiers of the system, read as "who calls whom" from top to bottom. `flowchart LR` when the layers are the stages of one process in the order they happen.
- **One subgraph per layer, all siblings.** Never nest a subgraph inside another and never leave a node outside every subgraph: nested containers and loose nodes are what let the layout engine scatter boxes. The subgraph title names the layer ("Native macOS services on the Mac, kept alive by launchd"); a box that would have been an outer container becomes words in the titles.
- **Declare layers in reading order.** Top row first in `TB`, left column first in `LR`.
- **Edges only cross layers, and only in the reading direction.** Down in `TB`, right in `LR`. An edge between two boxes in the same layer, or one that points back up, makes ELK move boxes into new layers and the rows fall apart. Two boxes in one layer that talk to each other get numbered labels instead ("1. speech to text stage", "2. intent matcher") or their own diagram where the stages become the layers. A reply that flows back is drawn on the forward edge as `a <-- "request, reply" --> b`; Mermaid has no arrow with a head only at the start.
- **A box goes in the layer of what calls it.** Something that only receives from a layer sits in the layer below, even when it is the same kind of thing as a box higher up: the Sonos speaker sits beside the Mac's services because Home Assistant calls it, while the puck sits at the top because it starts the request.
- **Let ELK order boxes inside a layer.** Do not try to pin the left-to-right order; crossing minimisation puts each target under its source, which is what keeps edges straight. Declare nodes in a sensible order anyway, since ties break on declaration order.
- **Keep it small.** At most about sixteen nodes and six layers; split anything bigger into two diagrams. Edge labels are two to four words naming what travels.

## Decision flowcharts

Rule chains (the router, the URL guard, the health policy) are `flowchart TB` with `{ }` decision nodes and no subgraphs. Each decision is its own row, every outcome edge points down and is labelled (`-- "yes" -->`, `-- "no" -->`), and the terminal boxes sit in the bottom row. Keep every path flowing down; a "try again" loop that points back up is drawn as a terminal box saying what happens next ("next candidate") rather than as an edge.

## Sequence diagrams

Use `sequenceDiagram` for three or more parties exchanging messages over time. The columns are the participants, so alignment already carries meaning: order participants left to right in the direction the first request travels (the puck, then Home Assistant, then the agent, then Ollama). Group them with `box rgb(219,234,254) Our code` … `end` and `box rgb(241,245,249) Third-party` using the palette fills. At most six participants and about fourteen messages; longer conversations split by phase. Notes are one short line with no `;` in them, and no participant is named `loop`, `end`, `opt`, `alt`, or `par`.

## State diagrams

`stateDiagram-v2` only when a thing really has states (a service under the health check, a conversation's continue flag), with at most six states.

## Palette (`operator_manual/_includes/palette.mmd`)

Include it in every flowchart with `--8<-- "_includes/palette.mmd"` as the first line after the diagram type. Fills are light and text is dark so every label reads on the white card.

| Class | Meaning | Look |
|---|---|---|
| `ours` | Code in this repository | light blue fill, blue stroke |
| `third` | Third-party software we run (Ollama, SearXNG, Home Assistant, Whisper, Kokoro, Piper, Music Assistant) | light grey fill |
| `hw` | A physical device (puck, Sonos, Mac, laptop) | light green fill |
| `ext` | Anything whose traffic leaves the apartment (search engines, Spotify, Met.no, the Anthropic API) | light red fill, dashed stroke |
| `current` | The part this page is about | thick orange stroke, applied last so it wins |

Apply classes with `class id1,id2 ours` lines at the end of the diagram. Subgraphs cannot take classes; highlight one with `style haos stroke:#f59e0b,stroke-width:4px`.

## Shapes

| Syntax | Use for |
|---|---|
| `id["text"]` | a process or service |
| `id[["text"]]` | a physical device |
| `id[("text")]` | a data store: files, SQLite, cache, logs |
| `id{"text"}` | a decision |
| `id(["text"])` | something a person says or does |
| `id>"text"]` | an external API |

Always double-quote labels so colons, parentheses, and `+` never break the parser. Use `<br/>` for line breaks and keep a label to three short lines. Node ids are lowercase ASCII and stable across the manual; reuse the ids in `system_map.md` when a diagram shows the same thing.

## Forbidden

- Nested subgraphs, nodes outside every subgraph in a layered diagram, and `direction` inside a subgraph: all three let the layout engine break the layers.
- Edges inside a layer or against the reading direction (see above for what to draw instead).
- `%%{init}%%` directives: the theme is fixed in `mermaid_config.json`.
- Mermaid 11 `@{ shape: ... }` syntax.
- Colours outside the palette, including in `style` lines other than the orange highlight, and any `fill` darker than the palette's.
- More than about sixteen nodes in one diagram.

## Checking your own output

`uv run manual-check path/to/page.md` renders every block with the site's configuration; a failure prints `path:line: Parse error on line N` at the markdown line. To look at the diagrams, add `--png <dir>`: every block of the page is written to `<dir>/<page stem>_<line>.png`. Open each PNG with the Read tool and check the four rules: layers in declared order, every label readable, nothing dark, edges straight with no loop around the outside. Fix the source and render again until all four hold. A diagram nobody has looked at does not ship.
