# Current Working Changes

This page lists the pull requests that are open right now, one entry each, in the same shape as a section. An entry is written when its pull request opens and removed when the pull request merges or closes.

## PR #6: The Home Assistant Handbook, its skill, the MkDocs site, and the diagram checker
<!-- manual-entry branch="operator-manual" pr="6" date="2026-09-08" -->

### Where this fits

```mermaid
flowchart TB
--8<-- "_includes/system_map.mmd"
class laptop current
```

### Key definitions

Two terms this change introduces:

| Term | Meaning |
|---|---|
| ELK | The Eclipse Layout Kernel, a layout engine Mermaid can use instead of its default, which keeps sibling groups in the order the source declares them. |
| Headless browser | A browser that runs without a window and is driven by a program, which is how mermaid-cli draws a diagram in Google Chrome. |

### Packages and tools

The four tools this change adds, and what it does with each:

| Tool | What it is | How this change uses it |
|---|---|---|
| Material for MkDocs 9.7.7 | A theme for MkDocs 1.6.1, a static site generator that builds a website from a folder of markdown, with navigation, search, and light and dark schemes | Builds `operator_manual/` into the handbook at https://seanlin2000.github.io/home_assistant/ |
| mermaid-cli 11.17.0 | The command-line renderer `mmdc` for Mermaid, a text language for diagrams; it draws through a headless Google Chrome | Draws every diagram in the handbook to SVG, when the site is built and when `manual-check` runs |
| `manual_checks` (ours) | A Python package in this repository, run as `uv run manual-check`, plus the MkDocs hook that swaps each diagram for its SVG at build time | Checks every page against its profile and reports a diagram that will not draw at its line in the markdown |
| `diagrams` (ours) | A Python package in this repository, run as `uv run draw-diagram` | Drives `mmdc` with ELK and one light theme, lays each drawing out in full-width bands or a grid the source pins, and rounds its corners |

### What changed

The change has four parts:

- **The manual.** `operator_manual/` holds this handbook: an Introduction, one page per part of the system, a glossary, a diagram legend, and the versions of record. [The manual](09_dev_environment.md#the-manual) on the Development page explains how it is built and published.
- **The checker and the site.** `uv run manual-check` checks every page and draws every diagram, and `uv run mkdocs build --strict` fails on a broken link or a diagram that will not draw. On every pull request the `docs` job runs the strict build and the structure checks, and `pages.yml` publishes the site on every merge to `main` (see [The checkers](09_dev_environment.md#the-checkers) and [The path to main](09_dev_environment.md#the-path-to-main)).
- **The drawing standard.** Every figure follows the [twelve rules](https://github.com/seanlin2000/home_assistant/blob/main/.claude/skills/draw-diagram/SKILL.md#6-the-twelve-rules), four shapes, and five colours of the `draw-diagram` skill. Each figure is drawn from an ASCII sketch committed in `diagrams/sketches/`, and the `diagrams` package draws it the same way for the site and for the checker.
- **The skills.** The [`operator-manual` skill](https://github.com/seanlin2000/home_assistant/blob/main/.claude/skills/operator-manual/SKILL.md) writes and checks the handbook and keeps this page's entries. The [`create-pr` skill](https://github.com/seanlin2000/home_assistant/blob/main/.claude/skills/create-pr/SKILL.md) offers an entry here before it pushes a pull request.

### Run it yourself

Both commands run on the laptop from the repository folder.

1. Preview the handbook:

    ```bash
    uv run mkdocs serve
    ```

    It prints `Serving on http://127.0.0.1:8000/home_assistant/`. Open that address to read the handbook; the page rebuilds whenever a file under `operator_manual/` is saved. Ctrl-C stops the server.

2. Check the handbook:

    ```bash
    uv run manual-check
    ```

    It prints nothing and exits 0 when every page is clean. Otherwise it prints one finding per line, such as `operator_manual/current_changes.md:5: missing heading '### What changed'`, and exits 1. The first run draws every diagram, which needs `brew install mermaid-cli` and Google Chrome; later runs take unchanged diagrams from the cache.
