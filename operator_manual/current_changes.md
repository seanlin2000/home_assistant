# Current Working Changes

This page lists the pull requests that are open right now, one entry each, in the same shape as a section. An entry is written when its pull request opens and removed when the pull request merges or closes.

## PR #16: Read every search result for the passages that match the query
<!-- manual-entry branch="search-passages" pr="16" date="2026-10-07" -->

### Where this fits

```mermaid
flowchart TB
--8<-- "_includes/system_map.mmd"
class mcp,laptop current
```

### Key definitions

One term this change introduces:

| Term | Meaning |
|---|---|
| BM25 | A ranking formula from text search that scores a line by the focus words it contains, weighting each word by how few lines of the page hold it and discounting long lines. |

### Packages and tools

No package is added; one is used differently:

| Tool | What it is | How this change uses it |
|---|---|---|
| `trafilatura` 2.2.0 | A main-content extraction library | Asked for Markdown, which keeps a page's headings, table rows, and lists for passage selection to choose between |

### What changed

The change has four parts:

- **Passages for every page.** `search_and_read` keeps the 350 words of each page that best match the query, chosen by one BM25 ranker that `wikipedia_lookup` shares, instead of the first 600 words; [Passages that match](03_web_search_mcp.md#passages-that-match) explains the rules.
- **Pages keep their structure.** An ordinary page now reaches the ranker with its headings, table rows, and list items on their own lines, as a Wikipedia article does, and six pages fit the same 2,000 words as four did (see [Reading the pages](03_web_search_mcp.md#reading-the-pages)).
- **One ranked list.** Results that could not be read keep their rank, title, and snippet beside the pages that were, and the block ends with a line telling the model to say plainly when the sources do not answer, as in [One tool call, end to end](03_web_search_mcp.md#one-tool-call-end-to-end).
- **`time_range`.** `search_and_read` and `web_search` take an optional `day`, `week`, `month`, or `year` for questions about the latest news, passed on to SearXNG (see [SearXNG in Docker](03_web_search_mcp.md#searxng-in-docker)).

### Run it yourself

1. Run the tests for the ranker, the search tools, and the Wikipedia tool:

    ```bash
    uv run pytest tests/test_passage_utils.py tests/test_web_search_mcp.py tests/test_wikipedia_lookup.py -q
    ```

    It prints `34 passed`. One of them reads a recorded SmashWiki page whose answer sits 3,000 words down.

2. After the change is deployed, run the tool-call script in [Run it yourself](03_web_search_mcp.md#run-it-yourself) with the query `Super Smash Bros character jab back air kill confirm`. The SmashWiki source shows the `Roy |` and `Chrom |` rows, the unread videos and forum threads appear as `(not read)` with their snippets, and the block ends with the not-found line.
