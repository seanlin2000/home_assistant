# Diagram style

Every diagram is Mermaid text inside a ```mermaid fence. `manual-check` renders each one with mermaid-cli and rejects any `classDef` that is not in the palette and any class name outside it.

## Palette (`operator_manual/_includes/palette.mmd`)

Include it in every flowchart with `--8<-- "_includes/palette.mmd"` as the first line after the diagram type. Fills and text colours are fixed so both Material colour schemes read the same.

| Class | Meaning | Look |
|---|---|---|
| `ours` | Code in this repository | blue fill, blue stroke |
| `third` | Third-party software we run (Ollama, SearXNG, Home Assistant, Whisper, Kokoro, Piper, Music Assistant) | grey fill |
| `hw` | A physical device (puck, Sonos, Mac, laptop) | green fill |
| `ext` | Anything whose traffic leaves the apartment (search engines, Spotify, Met.no, the Anthropic API) | red fill, dashed stroke |
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

Always double-quote labels so colons, parentheses, and `+` never break the parser. Use `<br/>` for line breaks. Node ids are lowercase ASCII and stable across the manual; reuse the ids in `system_map.md` when a diagram shows the same thing.

## Which diagram for what

| Purpose | Diagram | Notes |
|---|---|---|
| Data flow | `flowchart LR` | Subgraphs named `studio`, `mac`, `haos`, `native`, `docker`, `internet`, `laptop`; edge labels say what travels (`-- "audio chunks over Wyoming" -->`) |
| Business logic with three or more parties over time | `sequenceDiagram` | Group participants with `box rgb(219,234,254) Our code` … `end` and `box rgb(229,231,235) Third-party` using the palette fills; no classes in sequence diagrams |
| Rule chains and decisions | `flowchart TB` | `{ }` decision nodes, one edge per outcome, labelled |
| Infrastructure | `flowchart TB` | Nested subgraphs per machine, then per process; memory and ports as node text |
| Lifecycles | `stateDiagram-v2` | Only when a thing really has states (a service under the health check, a conversation's continue flag) |

## Forbidden

- `%%{init}%%` directives: Material injects its own theme and ignores them.
- Mermaid 11 `@{ shape: ... }` syntax: keeps mermaid-cli and Material's bundled Mermaid parsing the same text.
- More than about 16 nodes in one diagram: split into two parts.
- Colours outside the palette, including in `style` lines other than the orange highlight.
- `direction` inside a subgraph whose nodes have edges to the outside: Mermaid ignores it silently.

## Checking your own output

`uv run manual-check path/to/page.md` renders every block; a failure prints `path:line: Parse error on line N` at the markdown line. To look at a diagram, render it to PNG: write the expanded source to a `.mmd` file and run `mmdc -i d.mmd -o d.png -w 1600 -b white -p <puppeteer.json>` where the config names a Chrome binary (`{"executablePath": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"}`), then open the PNG with the Read tool.
