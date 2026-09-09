---
name: operator-manual
description: Write and maintain the Home Assistant Handbook in operator_manual/ (MkDocs Material, Mermaid diagrams): the book that teaches a CS graduate who is new to LLMs, MCP, Home Assistant, Wyoming, and Apple Silicon inference how this system works and how to run each part. Use when asked to write, build, update, regenerate, or check the manual, a section, the introduction, the glossary, or a "where this fits" diagram, or to add a PR entry to "Current working changes" (the create-pr skill invokes pr-entry). Modes: build, introduction, section <NN>, pr-entry, check.
argument-hint: build | introduction | section <NN> | pr-entry [--pr N] [--body path] | check
---

# The Home Assistant Handbook

The manual lives in `operator_manual/` and is rendered by Material for MkDocs (`uv run mkdocs serve`, published to GitHub Pages on merge). It describes the system as it is built today, for a reader with a computer science degree who has never used an LLM API, MCP, Home Assistant, the Wyoming protocol, Docker on macOS, or a UTM virtual machine. It never narrates history or departures from the design; `design_docs/` does that.

Arguments: `$ARGUMENTS`. The first word is the mode. With no mode and no `operator_manual/index.md`, run `build`. With no mode otherwise, never guess: ask the user one question with AskUserQuestion, "Rewrite a section completely" or "Append an entry for this branch to Current working changes". For a rewrite, ask a second question naming the section: offer the sections whose code the branch touches (the path-prefix table in `references/system_map.md` maps paths to highlights, and the highlight table maps those back to sections), and let "Other" take any number. Then run `section <NN>` or `pr-entry`.

Every diagram goes through the `draw-diagram` skill: invoke it (`.claude/skills/draw-diagram/SKILL.md`) before drawing or fixing one, and hand its rules to every subagent that draws.

Read before any mode: `references/section_template.md`, `references/diagram_style.md`, `references/system_map.md`, `references/complexity_rubric.md`. Read for the mode: `references/section_brief.md` (build, section), `references/pr_entry_contract.md` (pr-entry).

## 0. Locate the sources (every mode)

1. The latest design version is the highest `design_docs/v*` folder: `ls -d design_docs/v*/ | sort -V | tail -1`. Sections come from its `NN_*.md` files with NN ≥ 01; `00_system_overview.md` feeds the Introduction. Read each doc's "As built" appendices; where the doc body and an appendix or the code disagree, the appendix and the code win.
2. Code to read for a section is the table in `references/system_map.md`.
3. Runnable steps come from `README.md`, `scripts/`, `docs/phase2_walkthrough.md`, and the code; never invent a command.
4. Toolchain: `command -v mmdc` (if missing, tell the user to run `brew install mermaid-cli`; rendering also needs Google Chrome or `PUPPETEER_EXECUTABLE_PATH`), `uv run mkdocs --version`.

## Mode `build`

1. Read `00_system_overview.md`, `README.md`, `docs/phase2_walkthrough.md`, `docs/VERSIONS.md`.
2. Seed `operator_manual/glossary.md`: one `- **Term.** sentence` bullet per concept from every "Concepts for newcomers" section, alphabetical, one entry per term.
3. Confirm `operator_manual/_includes/palette.mmd` matches the palette in the `draw-diagram` skill and `_includes/system_map.mmd` matches `references/system_map.md`; if the system changed shape, update the map and the highlight table together.
4. Write `operator_manual/index.md` on the Introduction profile in `references/section_template.md`.
5. Score each section with `references/complexity_rubric.md`. Launch one subagent per section with `references/section_brief.md` filled in; at most three at a time; each returns its file plus proposed glossary terms.
6. Merge proposed terms into the glossary: one entry per term, keep the shorter definition, alphabetical.
7. Write the header of `operator_manual/current_changes.md` if the file does not exist, then run `pr-entry` for the current branch.
8. Add every new file to `nav` in `mkdocs.yml`.
9. Consistency pass: read only "Where this fits" and "Key definitions" of every section; make terms agree with the glossary and highlights agree with the table.
10. `uv run manual-check --png <scratch dir>` and look at every PNG against the ten rules of the `draw-diagram` skill; redraw what fails. Then `uv run manual-check` and `uv run mkdocs build --strict`; fix every finding; repeat until both are clean.

## Mode `introduction`

Steps 1, 2, 4, 9, 10 of `build`. Refresh glossary entries; never delete a term another page still defines.

## Mode `section <NN>`

Steps 0, 5 (for one section, in-session or as one subagent), 6, 8, 9, 10. Rewriting a section is allowed and expected when the code changed; it is not a PR entry.

## Mode `pr-entry`

Follow `references/pr_entry_contract.md` exactly: prune entries whose PR is merged or closed, append the entry for this branch, rename the pending heading when `--pr` is given, then `uv run manual-check --png <scratch dir> operator_manual/current_changes.md`, look at the entry's diagrams, and `uv run mkdocs build --strict`.

## Mode `check`

`uv run manual-check` and `uv run mkdocs build --strict`. Report the findings. Fix only when asked.

## Rules

- Define a term the first time it appears in a section and in the glossary. Never assume the reader has read the design docs or knows the stack.
- Prose in the style of huyenchip.com/ml-interviews-book: short declarative sentences, second person allowed, no marketing words, no emoji, no bullet walls. Bullets only in "Key definitions", tables, and numbered steps.
- Length follows the complexity tier, never a fixed count. No filler for simple topics, no truncation for hard ones.
- Every section has "Run it yourself" with real commands and what the reader should see. If nothing is human-run, say so in one sentence and why.
- Every diagram is looked at before it ships: render it with `uv run manual-check --png <dir> <page>` and judge it against the ten rules of the `draw-diagram` skill, one image at a time.
- Diagrams are Mermaid only, drawn with the `draw-diagram` skill; `references/diagram_style.md` holds what is specific to the handbook. The "Where this fits" block is `flowchart TB`, the system-map include, and `class`/`style` highlight lines; nothing else. Every other diagram includes the palette and uses only its five class names. Every `###` part under "How it works" opens with a diagram or says in one sentence why none is needed.
- Code samples are copied from the branch head, never invented, at most 25 lines, trimmed with `...`, with a caption line above the fence naming the file and symbol.
- Facts (ports, versions, model tags, numbers) come from the code, `docs/VERSIONS.md`, and the as-built appendices. Describe what exists now, never what it used to be or why it changed.
- Links to other sections are relative files (`04_conversation_agent.md#how-it-works`). Links to design docs and source files are absolute GitHub URLs (`https://github.com/seanlin2000/home_assistant/blob/main/...`); relative links outside `operator_manual/` fail the strict build.
- Never rewrite an existing `##` entry of `current_changes.md`. The only permitted edits are the two in the contract: removing an entry whose PR is merged or closed, and renaming the pending heading of the current branch.
- Finish with `manual-check` and `mkdocs build --strict` clean, then `scripts/lint.sh -c`, `uv run deslop`, `uv run pytest -q`.
- Never touch `design_docs/v0/`. Do not edit design docs from this skill.
