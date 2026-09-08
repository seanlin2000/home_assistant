# Page profiles

`manual-check` enforces the `##` headings of each profile in this order. Extra `##` headings are allowed between them. Sections also need the complexity comment on the line under the title.

## Section profile (`operator_manual/NN_stem.md`, NN ≥ 01)

````markdown
# N. Title
<!-- complexity: packages=N parts=N concepts=N tier=light|standard|deep -->

One paragraph: what this part does for the person talking to the assistant, in plain words.

## Where this fits

```mermaid
flowchart LR
--8<-- "_includes/system_map.mmd"
class agent,mcp current
```

One paragraph that reads the highlighted nodes left to right and names what enters and leaves them.

## Key definitions

- **Term.** One or two sentences. Every term here must also exist in `glossary.md`.

## Packages and tools

| Tool | What it is | How this part uses it |
|---|---|---|

## How it works

### Part 1

Diagram first (flowchart, sequence, or state), then prose, then an optional code sample with a caption line such as `*From `assistant_core/router.py`, `decide_route`:*`.

### Part 2

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

`# Introduction`, then in order: `## Purpose`, `## How to read this manual`, `## Key definitions`, `## Software and hardware` (table: name, what it is, how the project uses it, section), `## The system map` (the full map with no highlight, then a two-paragraph tour of a question from wake word to spoken answer), `## Where the code lives` (table of top-level folders), `## Before you run anything` (one heavy workload at a time, loading `.env`, which services are always on).

## Current working changes profile (`operator_manual/current_changes.md`)

`# Current working changes`, an intro paragraph, then one entry per in-flight pull request:

````markdown
## PR #12: Title of the pull request
<!-- manual-entry branch="operator-manual" pr="12" date="2026-09-07" -->

### Where this fits

(system map with the nodes from the path-prefix table highlighted)

### Key definitions

New terms only, or "None new."

### Packages and tools

### What changed

#### Part 1

Diagram, then prose. One `####` per modular part of the change.

### Run it yourself

Commands, or one sentence saying nothing is human-run.
````

Before the PR number exists the heading is `## Branch <name>: Title` and the marker says `pr="pending"`.

## Pages without a profile

`glossary.md`, `diagram_legend.md`, and `versions.md` have no required headings. The glossary is a single alphabetical list of `- **Term.** definition` bullets; the checker reads it to validate every section's "Key definitions".
