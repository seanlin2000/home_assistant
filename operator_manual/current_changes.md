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
  skill("operator-manual skill<br/>one subagent per section")
end
subgraph written["What it writes"]
  manual[("operator_manual/<br/>Introduction, sections 1 to 10,<br/>glossary, current changes")]
end
subgraph builder["What turns them into a site"]
  site("Material for MkDocs<br/>site/")
end
subgraph hosting["Where the site is served"]
  pages("GitHub Pages")
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
  check("uv run manual-check<br/>blocks.py finds fences, headings.py checks profiles")
  build("uv run mkdocs build --strict<br/>mkdocs_hook.py hands every fence to the renderer")
end
subgraph renderer["One renderer draws them"]
  render("diagrams/<br/>mmdc, ELK, the light theme,<br/>then bands and rounded corners")
end
subgraph outputs["What comes out"]
  findings("path:line: message<br/>exit 1")
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

#### The drawing standard

```mermaid
flowchart LR
--8<-- "_includes/palette.mmd"
subgraph author["The author"]
  rules(["draw-diagram skill:<br/>ten rules, four shapes,<br/>five colours"])
  text[("Mermaid text<br/>layers as sibling subgraphs")]
end
subgraph engine["mermaid-cli"]
  mmdc("mmdc + ELK<br/>diagrams/mermaid_config.json<br/>light theme, wide spacing")
end
subgraph post["diagrams/polish.py"]
  bands("every layer a full-width band,<br/>title at the left")
  corners("rounded corners,<br/>translucent containers")
end
subgraph look["What people see"]
  svg[("SVG on the page")]
  png[("PNG to look at<br/>diagrams/screenshot.py")]
end
rules --> text --> mmdc --> bands --> corners
corners --> svg
corners --> png
class rules,text,bands,corners,png ours
class mmdc,svg third
```

Every diagram is judged against ten rules that came from reading the first drafts: position carries meaning, layers are in line, text is visible, nothing is dark, no text sits on an arrow, arrows are tidy, corners are soft, colour has a stated meaning, shapes are standard, and containers are translucent with generous spacing. The `draw-diagram` skill holds those rules with a vocabulary of four shapes (a rounded rectangle for anything that runs, a cylinder for a store, a diamond for a decision, a stadium for what a person says or does) and five colour classes whose meaning is ownership. The `diagrams/` package does the part a program can do: it runs `mmdc` with the ELK layout engine and one light theme, then rewrites the SVG so every subgraph becomes a band spanning the drawing with its title at the left edge, or a full-height column in a left-to-right drawing, and rounds every corner. The site's hook and `manual-check --png` both go through it, and `uv run draw-diagram file.mmd --png out.png` renders one loose diagram the same way. The system map was redrawn to this standard first and every other diagram then converted to the four shapes.

#### The skills

`.claude/skills/operator-manual/` holds the procedure, the page profiles, the system map with each section's highlights, the complexity rubric, the brief handed to each section subagent, and the contract for pull request entries. With no mode given, the skill asks whether to rewrite one section completely or to append an entry for the branch here, and it invokes `draw-diagram` for every drawing. The `create-pr` skill gains one step: after drafting the description it asks whether the pull request deserves an entry here, runs the `pr-entry` mode, and after the number exists renames the entry's heading. `pr-entry` first removes any entry whose pull request has merged or closed, so this page only ever lists open work.

### Run it yourself

```bash
uv run mkdocs serve             # read the manual at http://127.0.0.1:8000/home_assistant/
uv run manual-check             # renders every diagram; needs brew install mermaid-cli and Google Chrome
uv run manual-check --no-render # the structure checks only, under a second
uv run manual-check --png out/ operator_manual/index.md   # write the page's diagrams as PNGs, as the site shows them
uv run draw-diagram diagram.mmd --png out/diagram.png    # render one loose diagram the same way
```

`manual-check` prints nothing and exits 0 when the manual is clean. Break a diagram on purpose, for example by deleting a closing bracket in any ```mermaid block, and it prints the file and line with `Parse error on line N`. `mkdocs serve` rebuilds on every save; Ctrl-C stops it.
