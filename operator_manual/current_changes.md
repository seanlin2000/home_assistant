# Current working changes

Pull requests that are open right now, one entry each, in the same shape as a section: where the change sits on the system map, the terms it introduces, the tools it touches, what changed, and how to try it. An entry is written when the pull request is opened and removed when the pull request merges or closes, so this page is always the difference between the manual and `main`.

## PR #6: The Home Assistant Handbook, its skill, the MkDocs site, and the diagram checker
<!-- manual-entry branch="operator-manual" pr="6" date="2026-09-08" -->

### Where this fits

```mermaid
flowchart TB
--8<-- "_includes/system_map.mmd"
class laptop current
```

Everything in this change lives on the laptop side of the map: the manual you are reading, the skill that writes it, the site that renders it, and the checker that keeps it honest. No running service changes.

### Key definitions

- **Static site generator.** A program that reads a folder of markdown files and writes plain HTML that any web server can host. MkDocs is one; there is no server-side code at all.
- **Mermaid.** A text language for diagrams. A block such as `a["Ollama"] --> b["agent"]` becomes two boxes and an arrow, so the diagram is reviewed and diffed as text. Here every block is drawn once at build time and the page carries the finished picture.
- **ELK.** The Eclipse Layout Kernel, a layout engine Mermaid can use instead of its default. It keeps sibling groups in the order they are declared, which is what lets a diagram be authored as rows or columns that mean something.
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
flowchart TB
--8<-- "_includes/palette.mmd"
subgraph sources["What the skill reads"]
  docs[("design_docs/v1<br/>intent and as-built appendices")]
  code[("the code")]
  walk[("docs/phase2_walkthrough.md")]
end
subgraph writer["What writes the pages"]
  skill["operator-manual skill<br/>one subagent per section"]
end
subgraph written["What it writes"]
  manual[("operator_manual/<br/>Introduction, sections 1 to 10,<br/>glossary, current changes")]
end
subgraph builder["What turns them into a site"]
  site["Material for MkDocs<br/>site/"]
end
subgraph hosting["Where the site is served"]
  pages>"GitHub Pages"]
end
docs --> skill
code --> skill
walk --> skill
skill --> manual
manual --> site
site --> pages
class skill,manual ours
class site,docs,code,walk third
class pages ext
```

Eleven pages: an Introduction with the system map and a tour of one question, one section per design doc with the same seven headings, a glossary of 108 terms that every section's definitions must agree with, a diagram legend, and the versions of record included from `docs/VERSIONS.md`. Every section carries a "Run it yourself" subsection with the real commands for its part and what they print; the content of the phase 2 walkthrough is folded into sections 2, 3, 5, 6, and 10. One drawing of the whole system lives in `operator_manual/_includes/system_map.mmd` and is included into every section with that section's nodes highlighted.

#### The checker and the site

```mermaid
flowchart TB
--8<-- "_includes/palette.mmd"
subgraph pages_in["The pages"]
  page[("operator_manual/*.md<br/>Mermaid fences inline")]
end
subgraph commands["Two commands read them"]
  check["uv run manual-check<br/>blocks.py finds fences, headings.py checks profiles"]
  build["uv run mkdocs build --strict<br/>mkdocs_hook.py hands every fence to the renderer"]
end
subgraph renderer["One renderer draws them"]
  render["render.py<br/>mmdc, headless Chrome, ELK layout,<br/>the light theme in mermaid_config.json"]
end
subgraph outputs["What comes out"]
  findings["path:line: message<br/>exit 1"]
  pngs[("PNGs to look at<br/>manual-check --png")]
  site[("site/<br/>with the SVG of every diagram")]
end
page --> check
page --> build
check -- "every fence" --> render
build -- "every fence" --> render
check -- "heading findings" --> findings
render -- "parse errors" --> findings
render -- "PNG per diagram" --> pngs
render -- "SVG per diagram" --> site
class check,build,render,findings ours
class page,pngs,site third
```

`uv run manual-check` renders every diagram in about twenty seconds and prints one finding per line, the same shape as `deslop`; with `--png <dir>` it also writes each diagram as a PNG so the author can look at it, which the skill requires before a diagram ships. The site does not draw diagrams in the browser: an MkDocs hook renders each fence with the same renderer and a fixed light theme at build time, caches the SVG by content hash under `.cache/`, and inlines it on a white card, so every diagram reads the same in the light and dark schemes. A `docs` CI job runs the checker after `uv run mkdocs build --strict`, whose strict mode fails on a broken link, a page missing from the navigation, or a missing include, and the `pages` workflow installs mermaid-cli for the same reason. The pre-commit hook does not render; it runs the fast structure check through `pytest`.

#### The skills

`.claude/skills/operator-manual/` holds the procedure, the page profiles, the diagram style, the system map with each section's highlights, the complexity rubric, the brief handed to each section subagent, and the contract for pull request entries. The `create-pr` skill gains one step: after drafting the description it asks whether the pull request deserves an entry here, runs the `pr-entry` mode, and after the number exists renames the entry's heading. `pr-entry` first removes any entry whose pull request has merged or closed, so this page only ever lists open work.

### Run it yourself

```bash
uv run mkdocs serve             # read the manual at http://127.0.0.1:8000/home_assistant/
uv run manual-check             # renders every diagram; needs brew install mermaid-cli and Google Chrome
uv run manual-check --no-render # the structure checks only, under a second
uv run manual-check --png out/ operator_manual/index.md   # write the page's diagrams as PNGs
```

`manual-check` prints nothing and exits 0 when the manual is clean. Break a diagram on purpose, for example by deleting a closing bracket in any ```mermaid block, and it prints the file and line with `Parse error on line N`. `mkdocs serve` rebuilds on every save; Ctrl-C stops it.
