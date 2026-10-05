---
name: operator-manual
description: Write and maintain the Home Assistant Handbook in operator_manual/ (MkDocs Material, Mermaid diagrams): the book that teaches a CS graduate who is new to LLMs, MCP, Home Assistant, Wyoming, and Apple Silicon inference how this system works and how to run each part. Use when asked to write, build, update, regenerate, or check the manual, a section, the introduction, the glossary, or a "where this fits" diagram, or to add a PR entry to "Current Working Changes" (the create-pr skill invokes pr-entry). Modes: build, introduction, section <NN> (NN is the page's file-stem prefix), pr-entry, check.
argument-hint: build | introduction | section <NN> | pr-entry [--pr N] [--body path] | check
---

# The Home Assistant Handbook

The manual lives in `operator_manual/` and is rendered by Material for MkDocs (`uv run mkdocs serve`, published to GitHub Pages on merge). It describes the system as it is built today, for a reader with a computer science degree who has never used an LLM API, MCP, Home Assistant, the Wyoming protocol, Docker on macOS, or a UTM virtual machine. It never narrates history or departures from the design; `design_docs/` does that.

Arguments: `$ARGUMENTS`. The first word is the mode. With no mode and no `operator_manual/index.md`, run `build`. With no mode otherwise, never guess: ask the user one question with AskUserQuestion, "Rewrite a section completely" or "Append an entry for this branch to Current Working Changes". For a rewrite, ask a second question naming the page: offer, by title, the pages whose code the branch touches (the path-prefix table in `references/system_map.md` maps paths to highlights, and the highlight table maps those back to pages), and let "Other" take any page. Then run `section <NN>`, where `NN` is that page's file-stem prefix (`04` for `04_conversation_agent.md`), or `pr-entry`.

Every diagram goes through the `draw-diagram` skill: invoke it (`.claude/skills/draw-diagram/SKILL.md`) before drawing or fixing one, and hand its rules to every subagent that draws.

Read before any mode: `references/section_template.md`, `references/diagram_style.md`, `references/system_map.md`, `references/complexity_rubric.md`. Read for the mode: `references/section_brief.md` (build, section), `references/pr_entry_contract.md` (pr-entry).

## 0. Locate the sources (every mode)

1. The latest design version is the highest `design_docs/v*` folder: `ls -d design_docs/v*/ | sort -V | tail -1`. Pages come from its `NN_*.md` files with NN ≥ 01; `00_system_overview.md` feeds the Introduction. Design doc `NN_stem.md` becomes handbook page `operator_manual/NN_stem.md`: the file name keeps the number so the page maps to its doc and its URL never changes, but the number never appears in a title, the nav, or the prose. The table in `design_docs/README.md` is the one copy of the mapping (design doc, page file, nav group, page title); read it rather than keeping another list. Read each doc's "As built" appendices; where the doc body and an appendix or the code disagree, the appendix and the code win.
2. Code to read for a section is the table in `references/system_map.md`.
3. Runnable steps come from `README.md`, `scripts/`, `docs/phase2_walkthrough.md`, and the code; never invent a command.
4. Toolchain: `command -v mmdc` (if missing, tell the user to run `brew install mermaid-cli`; rendering also needs Google Chrome or `PUPPETEER_EXECUTABLE_PATH`), `uv run mkdocs --version`.

## Mode `build`

1. Read `00_system_overview.md`, `README.md`, `docs/phase2_walkthrough.md`, `docs/VERSIONS.md`.
2. Seed `operator_manual/glossary.md`: one `| Term | Meaning | Explained in |` row per concept from every "Concepts for newcomers" section, alphabetical, one row per term, the meaning one sentence and the last column a link to the page that teaches it.
3. Confirm `operator_manual/_includes/palette.mmd` matches the palette in the `draw-diagram` skill and `_includes/system_map.mmd` matches `references/system_map.md`; if the system changed shape, update the map and the highlight table together.
4. Write `operator_manual/index.md` on the Introduction profile in `references/section_template.md`.
5. Score each section with `references/complexity_rubric.md`. Launch one subagent per section with `references/section_brief.md` filled in; at most three at a time; each returns its file plus proposed glossary terms.
6. Merge proposed terms into the glossary: one entry per term, keep the shorter definition, alphabetical.
7. Write the header of `operator_manual/current_changes.md` if the file does not exist, then run `pr-entry` for the current branch.
8. Add every new file to `nav` in `mkdocs.yml` where a newcomer needs it (see the nav rule below), and add or update its row in the table in `design_docs/README.md`.
9. Consistency pass: read only "Where this fits" and "Key definitions" of every section; make terms agree with the glossary and highlights agree with the table.
10. `uv run manual-check --png <scratch dir>` and look at every PNG against the twelve rules of the `draw-diagram` skill; redraw what fails. Then `uv run manual-check` and `uv run mkdocs build --strict`; fix every finding; repeat until both are clean.

## Mode `introduction`

Steps 1, 2, 4, 9, 10 of `build`. Refresh glossary entries; never delete a term another page still defines.

## Mode `section <NN>`

`NN` is the page's file-stem prefix, the same number as its design doc (`04` for `04_conversation_agent.md`); it names a file, never a position in the manual. Steps 0, 5 (for one section, in-session or as one subagent), 6, 8, 9, 10. Rewriting a section is allowed and expected when the code changed; it is not a PR entry.

## Mode `pr-entry`

Follow `references/pr_entry_contract.md` exactly: prune entries whose PR is merged or closed, append the entry for this branch, rename the pending heading when `--pr` is given, then `uv run manual-check --png <scratch dir> operator_manual/current_changes.md`, look at the entry's diagrams, and `uv run mkdocs build --strict`.

## Mode `check`

`uv run manual-check` and `uv run mkdocs build --strict`. Report the findings. Fix only when asked.

## Rules

- Define a term the first time it appears in a section and in the glossary. Never assume the reader has read the design docs or knows the stack.
- Prose in the style of huyenchip.com/ml-interviews-book: short declarative sentences, second person allowed, no marketing words, no emoji. Aim for fewer dense paragraphs, not for bulleting everything: a short bullet list is fine anywhere a paragraph would otherwise be dense (a set of reasons, the parts of a thing, parallel facts), a sequence is numbered steps, and a comparison is a table. A plain short paragraph is still right when its three or four facts already read well. "Key definitions" is a `| Term | Meaning |` table with one sentence per definition, never a list.
- Length follows the complexity tier, never a fixed count. No filler for simple topics, no truncation for hard ones.
- Every section has "Run it yourself" with real commands and what the reader should see. If nothing is human-run, say so in one sentence and why.
- No prose after a figure explains how to read it (its rows, colours, shapes, or highlight); the legend page holds the key once. A paragraph after a diagram adds only facts the drawing does not show.
- Every diagram is looked at before it ships: render it with `uv run manual-check --png <dir> <page>` and judge it against the twelve rules of the `draw-diagram` skill, one image at a time.
- Diagrams are Mermaid only, drawn with the `draw-diagram` skill; `references/diagram_style.md` holds what is specific to the handbook. The "Where this fits" block is `flowchart TB`, the system-map include, and `class`/`style` highlight lines; nothing else. Every other diagram includes the palette and uses only its five class names. Every `###` part under "How it works" opens with a diagram when a picture helps; a part without one simply starts with its prose. Never write a sentence about the absence of a diagram, or any other note addressed to the writing process: every line on the page is for a human reader.
- Code samples are copied from the branch head, never invented, at most 25 lines, trimmed with `...`, with a caption line above the fence naming the file and symbol.
- Facts (ports, versions, model tags, numbers) come from the code, `docs/VERSIONS.md`, and the as-built appendices. Describe what exists now, never what it used to be or why it changed.
- Page titles carry no number: the H1 is the page's name (`# Conversation Agent`), and `manual-check` rejects a numbered one. The nav label is the same name as the H1.
- Page titles, nav labels, and nav group names are in title case: capitalise every word except the small words a, an, the, of, on, to, and, or, for, and in, which stay lowercase unless they come first (`# Conversation Agent`, `# MCP Tool Server`, `# Benchmarking and Model Selection`, `# LLMs on Apple Silicon`, `Versions of Record`). Code names such as `web_search_mcp` keep their own spelling. Link text that quotes a page or group title uses the same casing (`see [Operations](10_operations.md)`, `[Conversation Agent](04_conversation_agent.md)`). Where a sentence reads naturally with the name in lowercase, write it in sentence case and still link it (`the [conversation agent](04_conversation_agent.md)`). `###` titles and everything below them stay in sentence case (`The judge`, `Coming back after a reboot`).
- The nav groups pages by what a newcomer needs, in this order: Introduction; The Assistant (the parts a question passes through); The Model; The Machine; Development; Current Working Changes; Appendix. A new page goes where a newcomer needs it inside those groups, not at the end, and a new group is added only when no existing one fits. Whenever a page is added, renamed, or moved in the nav, update the table in `design_docs/README.md` in the same change. A rename also changes the H1, the nav label, the page's row in the highlight table of `references/system_map.md`, and every link whose text quotes the old title (the Introduction's group list and its two tables, and cross-references in every page and in `current_changes.md`).
- `###` titles under "How it works" are a few words each (`The judge`, `Logs`, `Bootstrap`), with no `Part N:` prefix. Prose refers to one by a named anchor link, never by its position.
- Cross-references are named links, never "section N": the link text is the page's title or the thing being pointed at (`see [Conversation Agent](04_conversation_agent.md)`, `the [health check](10_operations.md#the-health-check)`). `manual-check` rejects a reference by section number. Links to other pages are relative files (`04_conversation_agent.md#how-it-works`). Links to design docs and source files are absolute GitHub URLs (`https://github.com/seanlin2000/home_assistant/blob/main/...`); relative links outside `operator_manual/` fail the strict build.
- Never rewrite an existing `##` entry of `current_changes.md`. The only permitted edits are the two in the contract: removing an entry whose PR is merged or closed, and renaming the pending heading of the current branch.
- Finish with `manual-check` and `mkdocs build --strict` clean, then `scripts/lint.sh -c`, `uv run deslop`, `uv run pytest -q`.
- Never touch `design_docs/v0/`. Do not edit design docs from this skill; the one exception is the page-mapping table in `design_docs/README.md`.
