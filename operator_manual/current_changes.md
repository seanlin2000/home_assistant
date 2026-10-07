# Current Working Changes

This page lists the pull requests that are open right now, one entry each, in the same shape as a section. An entry is written when its pull request opens and removed when the pull request merges or closes.

## PR #15: Read Wikipedia articles with their tables: a wikipedia_lookup tool and Wikipedia results in search_and_read
<!-- manual-entry branch="wikipedia-tool" pr="15" date="2026-10-07" -->

### Where this fits

```mermaid
flowchart TB
--8<-- "_includes/system_map.mmd"
class agent,mcp,laptop current
```

### Key definitions

Two terms this change introduces:

| Term | Meaning |
|---|---|
| Focus | The words or year a caller names to pick the part of a long Wikipedia article it needs, so the lines that match are kept and the rest is dropped. |
| Parsoid HTML | The HTML that Wikipedia's REST API returns for an article, in which every section is a `<section>` element holding its heading and data tables carry the class `wikitable`. |

### Packages and tools

| Tool | What it is | How this change uses it |
|---|---|---|
| Wikipedia REST API | Wikimedia's free, keyless HTTP interface to Wikipedia: a title search and each article's HTML | `wikipedia_lookup` and `search_and_read` fetch article HTML from it, with a User-Agent naming the project |
| lxml 6.1.3 | A Python library that parses HTML into a tree that can be searched with XPath | Turns an article's HTML into headings, prose, and one line per table row |

### What changed

The change has three parts:

- **The `wikipedia_lookup` tool.** The tool server offers a thirteenth tool, twelve without the forecast, that reads one Wikipedia article and keeps the parts a focus names, with every table row on its own line. [Wikipedia articles](03_web_search_mcp.md#wikipedia-articles) on the MCP Tool Server page explains it.
- **Wikipedia results in `search_and_read`.** A search result on `en.wikipedia.org/wiki/` is read through the same code, with the search query as the focus, so its tables reach the model even when the model never calls the new tool.
- **Prompt 1.8.** The system prompt and the search directive send settled facts, lists, and records to `wikipedia_lookup`, and the tool counts as a search for the filler line and the benchmark's gates (see [The question router](04_conversation_agent.md#the-question-router)).

### Run it yourself

1. Run the tests that serve a recorded Wikipedia article:

    ```bash
    uv run pytest tests/test_wikipedia_lookup.py -q
    ```

    It prints `18 passed`.

2. After the change is deployed, confirm the tool server offers the tool:

    ```bash
    curl -s http://127.0.0.1:8765/healthz
    ```

    The reply lists `wikipedia_lookup` among the tools and shows `"missing":[]`.
