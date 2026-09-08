## Summary

<!-- What this PR is and why, in 2-5 sentences. -->

## <Change 1>

<!--
One "## " section per important change. Each bullet has three parts in this order: the lines a reviewer should read,
a short bold phrase naming the change, then one or two sentences of the business logic behind it:

    - `deslop/checks.py:115-127` (`count_lines`) **Comments counted by the tokenizer.** A "#" inside a string never counts ...

References are produced by the tool, never typed by hand:

    uv run pr-refs resolve deslop/checks.py:count_lines .githooks/pre-commit:"uv run deslop"

which prints, for example, `deslop/checks.py:115-127` (`count_lines`) and `.githooks/pre-commit:20-20` ("uv run deslop").
Before opening or editing the PR: uv run pr-refs check body.md && uv run pr-refs lint body.md (references, then shape).
CI runs both on every push. The /pr skill (.claude/skills/pr/SKILL.md) walks the whole path from branch to open PR.
-->

- `path:start-end` (`symbol`) **Short phrase.** Description.

## How to verify

```
uv run pytest -q
```

## Review notes

<!-- Where to focus, what to skip. -->
