# AGENTS.md

Guidance for automated agents that read this repository. The coding conventions are in `CLAUDE.md` and `claude_docs/CLEAN_CODE.md`; this file
adds what a reviewer or a review-fixing agent needs.

## Code Review Rules

- Formatting and imports are enforced by tooling (black and isort at 200 columns, shfmt, shellcheck), as are typed parameters and the comment-to-code
  ratio (`uv run deslop`). Do not comment on those; CI already fails on them.
- All Python runs from the project virtual environment through `uv run`. Flag any new command, script, or documentation that calls a bare `python3`.
- Flag functions that do more than one thing, boolean flag parameters, error codes returned instead of exceptions, and duplicated logic that belongs in
  `utils/{util_type}_utils.py`. See `claude_docs/CLEAN_CODE.md` sections 2.2, 2.6, 2.9, and 2.10.
- Flag any change to `web_search_mcp/url_guard.py` or `web_search_mcp/page_extractor.py` that could let a fetch reach a private address; the guard must
  hold at every redirect hop.
- Flag any code path that would call a paid API (Anthropic) in a test or by default in the benchmark; paid calls are opt-in and reported.
- The PR description must have one section per important change with line references in the form `` `path:start-end` (`symbol`) ``; if a section
  describes logic the references do not cover, say so.
- Keep findings to what would be wrong in production or would mislead the next reader. Style preferences the tooling does not enforce are not findings.

## Fixing a review

The workflow in `.github/workflows/claude-review-fixes.yml` runs Claude Code on every review submitted by the Codex bot. The procedure and its
guardrails are in `docs/review_loop.md`.
