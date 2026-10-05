# Page profiles

`manual-check` enforces the `##` headings of each profile in this order. Extra `##` headings are allowed between them. Sections also need the complexity comment on the line under the title. No page title carries a number; the file name keeps its design doc's number (`04_conversation_agent.md`), the title does not (`# Conversation Agent`). Page titles, nav labels, and nav group names are in title case: capitalise every word except the small words a, an, the, of, on, to, and, or, for, and in, which stay lowercase unless they come first (`# Conversation Agent`, `# MCP Tool Server`, `# Benchmarking and Model Selection`, `# LLMs on Apple Silicon`, `Versions of Record`). Code names such as `web_search_mcp` keep their own spelling. Link text that quotes a page or group title uses the same casing (`see [Operations](10_operations.md)`, `[Conversation Agent](04_conversation_agent.md)`). Where a sentence reads naturally with the name in lowercase, write it in sentence case and still link it (`the [conversation agent](04_conversation_agent.md)`). `###` titles and everything below them stay in sentence case (`The judge`, `Coming back after a reboot`).

## Section profile (`operator_manual/NN_stem.md`, NN ≥ 01)

````markdown
# Title
<!-- complexity: packages=N parts=N concepts=N tier=light|standard|deep -->

One paragraph: what this part does for the person talking to the assistant, in plain words. Its first sentence says what the page covers, because a short title such as `# Music` does not.

## Where this fits

```mermaid
flowchart TB
--8<-- "_includes/system_map.mmd"
class agent,mcp current
```

One paragraph on what this part receives and what it hands on. Never a sentence that explains how to read the diagram (its rows, colours, shapes, or highlight): the diagram is self-explanatory and the key lives once on the legend page.

## Key definitions

| Term | Meaning |
|---|---|
| Term | One sentence. |

A two-column table, one row per term, each definition one sentence; how this project uses the term belongs in the page's prose. A bullet list here is a `manual-check` finding. Every term here must also exist in `glossary.md`.

## Packages and tools

| Tool | What it is | How this part uses it |
|---|---|---|

## How it works

### A short title

A few words naming the part (`The judge`, `Logs`, `Bootstrap`), never `Part N:`. Diagram first (flowchart, sequence, or state), then prose, then an optional code sample with a caption line such as `*From `assistant_core/router.py`, `decide_route`:*`.

### Another short title

...

## Run it yourself

Commands in fenced blocks, what the reader should see, and how to stop. If nothing here is human-run, one sentence saying so and why.

## Where to look in the code

| Path | What you find there |
|---|---|

## Further reading

- Design doc: absolute GitHub URL to `design_docs/vN/NN_stem.md`
- Curated sources from the design doc, each with one clause on why it is worth opening
````

## Introduction profile (`operator_manual/index.md`)

`# Introduction`, then in order: `## Purpose`, `## How to read this manual` (the nav groups in nav order, with a named link to each page and never a page number), `## Key definitions`, `## Software and hardware` (table: name, what it is, how the project uses it, page as a named link; rows in nav order), `## The system map` (the full map with no highlight, then a two-paragraph tour of a question from wake word to spoken answer), `## Where the code lives` (table of top-level folders with the page that explains each; rows in nav order), `## Before you run anything` (one heavy workload at a time, loading `.env`, which services are always on).

## Current Working Changes profile (`operator_manual/current_changes.md`)

`# Current Working Changes`, an intro paragraph, then one entry per in-flight pull request:

````markdown
## PR #12: Title of the pull request
<!-- manual-entry branch="operator-manual" pr="12" date="2026-09-07" -->

### Where this fits

(system map with the nodes from the path-prefix table highlighted)

### Key definitions

| Term | Meaning |
|---|---|
| Term | One sentence. |

New terms only, in the same two-column table, each also added to `glossary.md`; or the single line "None new."

### Packages and tools

### What changed

- **A short name for the part.** One or two sentences, linking to the section page that explains it.

One bullet per modular part of the change. A part that no section explains yet gets a `####` heading of its own, a diagram, then prose; a part a section already explains is never redrawn here.

### Run it yourself

Commands, or one sentence saying nothing is human-run.
````

Before the PR number exists the heading is `## Branch <name>: Title` and the marker says `pr="pending"`.

## Pages without a profile

`glossary.md`, `diagram_legend.md`, and `versions.md` have no required headings. The glossary is one alphabetical `| Term | Meaning | Explained in |` table: one sentence per term, and a link to the page that teaches it; the checker reads it to validate the term in every row of each page's "Key definitions" table.
