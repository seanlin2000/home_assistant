# Diagrams in the handbook

Every rule about how a diagram looks lives in the `draw-diagram` skill (`.claude/skills/draw-diagram/SKILL.md` and its `references/mermaid_patterns.md`). Invoke that skill before drawing or fixing any diagram. This file holds only what is specific to the handbook.

- **Where the palette lives.** `operator_manual/_includes/palette.mmd` holds the five `classDef` lines. Every flowchart includes it with `--8<-- "_includes/palette.mmd"` as the first line after the diagram type; the "Where this fits" block gets it through the system map include. `manual-check` rejects any `classDef` outside that file and any class name outside the five.
- **The map block.** Exactly `flowchart TB`, `--8<-- "_includes/system_map.mmd"`, then `class <ids> current` and optionally `style <row> stroke:#f59e0b,stroke-width:3px`; see `system_map.md` for the ids and each section's highlights.
- **Rendering.** An MkDocs hook (`manual_checks/mkdocs_hook.py`) renders each fence through the `diagrams` package at build time and inlines the SVG on a white card, so the page shows the same picture in both colour schemes. `uv run manual-check --png <dir> <page>` writes the same pictures as `<dir>/<page stem>_<line>.png`; look at every one before the page ships.
- **The legend.** `operator_manual/diagram_legend.md` states what the colours, shapes, and positions mean. When the vocabulary in the `draw-diagram` skill changes, the legend changes with it.
