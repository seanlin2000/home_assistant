# CLAUDE.md

### General Notes
1. When executing a code command, make sure that we are using the project's virtual environment rather than the local machine's python interpreter.
2. Every change goes through a branch and a pull request; never push to `main`. The pre-commit hook (`.githooks/pre-commit`) must pass on its own; do not use `--no-verify`. PR descriptions follow `.github/pull_request_template.md`, with line references produced by `uv run pr-refs resolve`, never typed by hand, and pass `uv run pr-refs check` and `uv run pr-refs lint`. Use the `/pr` skill (`.claude/skills/pr/SKILL.md`) to take a change from branch to open pull request.

### Coding Standards
1. **Use clear and concise variable and function names**
2. **Define the type of all function parameters** Prompt user when unsure of the type of a function parameter
3. **Do not rewrite the same function in multiple files** Reuse functions when possible and refactor to a new file of type `utils/{util_type}_utils.py` when necessary
4. **Read Reference Materials First**. When pointed to existing file such as README or existing code. read it thoroughly before drafting plan or executing code.
5. **Exhaustive Info on Variables, Functions, and Code Comments** Refer to @claude_docs/CLEAN_CODE.md for coding conventions regarding naming, functions, and code comments

### Code Format Rules
1. **Python line length:** 200 characters max
2. **Python formatting (black):**
    - 4-space indentation
    - Double quotes (prefer over single quotes)
    - Trailing commas on multi-line collections/arguments
    - No trailing whitespace
    - One blank line between methods, two blank lines between top-level definitions
    - Magic trailing comma: a trailing comma forces multi-line formatting even if it fits on one line
3. **Import ordering (isort, black profile):** standard library -> third-party -> local, separated by blank lines. Imports at the top of the file. No in-line imports.

### Resources
Refer to @claude_docs/CLEAN_CODE.md for coding conventions regarding naming, functions, and code comments

For project overview and detailed usage, see @README.md.