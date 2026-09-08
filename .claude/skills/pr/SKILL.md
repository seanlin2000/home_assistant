---
name: pr
description: Ship a change to main the repository's way. Branch from origin/main in its own worktree, commit through the pre-commit hook, write the PR description in the template's shape with tool-resolved line references, verify it with pr-refs, push, open or update the pull request, and wait for CI. Use for every change destined for main, whether starting from scratch or from a branch that already has commits.
argument-hint: [branch-name] [one line on what the change is]
---

# Open a pull request

The rules this skill carries out are in `CLAUDE.md`, the README ("Changing the code"), and design doc 09 §12. Nothing here replaces them; this is the order to do them in.

Arguments: `$ARGUMENTS`. The first word is the branch name if one is given; the rest describes the change. If no branch name is given and the work is not yet on a branch, choose a short kebab-case name for it.

## 1. Find out where the work stands

```
git -C "$(git rev-parse --show-toplevel)" status --short --branch
git worktree list
gh pr list --head "$(git branch --show-current)" --json number,url
```

- On `main`, or in the main checkout with uncommitted edits that belong to this change: go to step 2 and move the edits there (`git stash` in the main checkout, `git stash pop` in the new worktree).
- Already in a worktree on a feature branch: skip to step 3.
- A PR already exists for the branch: skip to step 5 and update it instead of opening a second one.

## 2. Start the branch in its own worktree

Always from the latest `origin/main`, never from the current working tree, because other edits may be in progress there.

```
git fetch origin
git worktree add -b <branch> ../home_assistant_<branch> origin/main
cd ../home_assistant_<branch>
scripts/dev_setup.sh
```

`dev_setup.sh` builds the worktree's `.venv` from `uv.lock` and installs the pre-commit hook; without it the hook cannot run and the commit is refused. Everything Python runs from that `.venv` or through `uv run`, never the machine's interpreter.

## 3. Commit through the hook

- Run `scripts/lint.sh` first so formatting never fails the hook.
- `git commit` with the hook on. Never `--no-verify`. If a step fails, fix the cause and commit again; do not weaken the check.
- One commit per coherent step is fine; the PR is squash-merged.
- The message: an imperative summary line, then the why in a short body, then the attribution trailers the environment asks for.

## 4. Write the description

Write it to a file outside the repository (the session scratchpad), never into the tree. Follow `.github/pull_request_template.md`:

1. `## Summary`: what and why, two to five sentences.
2. One `## <Change>` section per important change. Every line in it is a bullet with three parts in this order:
   - the reference or references, pasted verbatim from `uv run pr-refs resolve`;
   - a short bold phrase naming the change, ending in a period;
   - one or two sentences of the business logic.
3. `## How to verify`: the commands, in a fenced block, and anything checked by hand.
4. `## Review notes`: where to focus, what to skip, what stays out of scope.
5. The attribution footer the environment asks for.

Resolving references:

```
uv run pr-refs resolve web_search_mcp/url_guard.py:pin_url_to_address        # a function, class, method (dotted), or constant
uv run pr-refs resolve 'scripts/services.sh:"ipconfig getifaddr en0"'         # quoted text, for shell, YAML, markdown
```

Paste the printed form unchanged. Never type a `path:start-end` from memory or estimation. Reference the code at the branch head; after any later commit that moves lines, resolve again.

Then both checks must pass before the body is used:

```
uv run pr-refs check body.md   # every cited range still matches the code
uv run pr-refs lint body.md    # required sections present; every change bullet has the three parts in order
```

## 5. Push and open, or update

```
git push -u origin <branch>
gh pr create --base main --head <branch> --title "<summary line>" --body-file body.md
```

If a PR already exists: `gh pr edit <number> --body-file body.md`. Never push to `main`, never merge, never force-push over someone else's commits.

## 6. Wait for CI and report

```
gh pr checks <number> --watch
```

Both jobs must be green: `checks` (lint, deslop, tests) and `pr-description` (`pr-refs check` and `pr-refs lint` on the PR body). If a job fails, fix it on the branch, commit through the hook, push, re-resolve any moved references, and edit the PR body.

Report to the user: the PR URL, the CI result, and what was verified by hand. The Merge click is theirs. Mention that the worktree can be removed after the merge (`git worktree remove ../home_assistant_<branch>`).
