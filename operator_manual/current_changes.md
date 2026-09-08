# Current working changes

Pull requests that are open right now, one entry each, in the same shape as a section: where the change sits on the system map, the terms it introduces, the tools it touches, what changed, and how to try it. An entry is written when the pull request is opened and removed when the pull request merges or closes, so this page is always the difference between the manual and `main`.

## PR #6: The Operator's Manual, its skill, the MkDocs site, and the diagram checker
<!-- manual-entry branch="operator-manual" pr="6" date="2026-09-08" -->

### Where this fits

```mermaid
flowchart LR
--8<-- "_includes/system_map.mmd"
class laptop current
```

Everything in this change lives on the laptop side of the map: the manual you are reading, the skill that writes it, the site that renders it, and the checker that keeps it honest. No running service changes.

### Key definitions

- **Static site generator.** A program that reads a folder of markdown files and writes plain HTML that any web server can host. MkDocs is one; there is no server-side code at all.
- **Mermaid.** A text language for diagrams. A block such as `a["Ollama"] --> b["agent"]` becomes two boxes and an arrow when the page opens, so the diagram is reviewed and diffed as text.
- **Headless browser.** A browser run without a window, driven by a program. Mermaid is drawn by a browser, so the checker starts a headless Chrome to find out whether a diagram parses.

### Packages and tools

| Tool | What it is | How this change uses it |
|---|---|---|
| Material for MkDocs 9.7 | A theme for the MkDocs static site generator: sidebar table of contents, page outline, search, light and dark schemes, Mermaid support | Renders `operator_manual/` into the site at https://seanlin2000.github.io/home_assistant/. Pinned in `uv.lock` under the `docs` group |
| mermaid-cli 11.17 | The Mermaid project's command-line renderer, installed with Homebrew, which drives a headless Chrome | `manual-check` renders every diagram through it and reports a parse error at its line in the markdown |
| `manual_checks` | A small checker in this repository, shaped like `deslop` | Finds every Mermaid block, expands the shared includes, renders each one, and checks every page against its profile: required headings in order, a complexity comment whose tier matches its score, a system map that highlights something, palette discipline, and glossary agreement |
| GitHub Actions and Pages | GitHub's CI runners and static hosting | A `docs` job runs the strict build and the checker on every pull request; a `pages` workflow publishes the site on every merge to `main` |
| The `operator-manual` skill | The procedure in `.claude/skills/operator-manual/` | Writes and refreshes sections, scores their length with a rubric, and adds an entry to this page for each pull request through `create-pr` |

### What changed

#### The manual

```mermaid
flowchart LR
--8<-- "_includes/palette.mmd"
docs[("design_docs/v1<br/>intent and as-built appendices")] --> skill["operator-manual skill<br/>one subagent per section"]
code[("the code")] --> skill
walk[("docs/phase2_walkthrough.md")] --> skill
skill --> manual[("operator_manual/<br/>Introduction, sections 1 to 10,<br/>glossary, current changes")]
manual --> site["Material for MkDocs<br/>site/"]
site --> pages>"GitHub Pages"]
class skill,manual ours
class site third
class pages ext
class docs,code,walk third
```

Eleven pages: an Introduction with the system map and a tour of one question, one section per design doc with the same seven headings, a glossary of 108 terms that every section's definitions must agree with, a diagram legend, and the versions of record included from `docs/VERSIONS.md`. Every section carries a "Run it yourself" subsection with the real commands for its part and what they print; the content of the phase 2 walkthrough is folded into sections 2, 3, 5, 6, and 10. One drawing of the whole system lives in `operator_manual/_includes/system_map.mmd` and is included into every section with that section's nodes highlighted.

#### The checker and the site

```mermaid
flowchart LR
--8<-- "_includes/palette.mmd"
page[("operator_manual/*.md")] --> blocks["blocks.py<br/>find fences, expand includes"]
blocks --> render["render.py<br/>mmdc + headless Chrome"]
page --> headings["headings.py<br/>profiles, palette, glossary"]
render --> findings["path:line: message<br/>exit 1"]
headings --> findings
page --> mkdocs["mkdocs build --strict"]
mkdocs --> site[("site/")]
class blocks,render,headings,findings ours
class mkdocs,site third
```

`uv run manual-check` renders all 51 diagrams in about 20 seconds and prints one finding per line, the same shape as `deslop`. A `docs` CI job runs it after `uv run mkdocs build --strict`, whose strict mode fails on a broken link, a page missing from the navigation, or a missing include. The pre-commit hook does not render; it runs the fast structure check through `pytest`.

#### The skills

`.claude/skills/operator-manual/` holds the procedure, the page profiles, the diagram style, the system map with each section's highlights, the complexity rubric, the brief handed to each section subagent, and the contract for pull request entries. The `create-pr` skill gains one step: after drafting the description it asks whether the pull request deserves an entry here, runs the `pr-entry` mode, and after the number exists renames the entry's heading. `pr-entry` first removes any entry whose pull request has merged or closed, so this page only ever lists open work.

### Run it yourself

```bash
uv run mkdocs serve             # read the manual at http://127.0.0.1:8000/home_assistant/
uv run manual-check             # renders every diagram; needs brew install mermaid-cli and Google Chrome
uv run manual-check --no-render # the structure checks only, under a second
```

`manual-check` prints nothing and exits 0 when the manual is clean. Break a diagram on purpose, for example by deleting a closing bracket in any ```mermaid block, and it prints the file and line with `Parse error on line N`. `mkdocs serve` rebuilds on every save; Ctrl-C stops it.
