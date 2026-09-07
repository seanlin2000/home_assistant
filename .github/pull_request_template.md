## Summary

<!-- What this PR is and why, in 2-5 sentences. -->

## <Change 1>

<!--
One "## " section per important change. Each bullet states one piece of core business logic and ends with the
lines a reviewer should read for it. References are produced by the tool, never typed by hand:

    uv run pr-refs resolve deslop/checks.py:count_lines .githooks/pre-commit:"uv run deslop"

which prints, for example, `deslop/checks.py:115-127` (`count_lines`) and `.githooks/pre-commit:20-20` ("uv run deslop").
Before opening or editing the PR: uv run pr-refs check body.md. CI runs the same check on every push.
-->

- ...

## How to verify

```
uv run pytest -q
```

## Review notes

<!-- Where to focus, what to skip. -->
