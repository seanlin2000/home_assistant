# The `pr-entry` contract

What `create-pr` relies on when it runs `/operator-manual pr-entry [--pr N] [--body path]`, and what `pr-entry` promises in return.

## Inputs

- The current branch and its diff against `origin/main`: `git diff origin/main...HEAD --stat` and `git diff origin/main...HEAD`.
- `--pr N`: the pull request number once it exists. Title from `gh pr view N --json title -q .title`.
- `--body path`: the drafted PR description. Its `## <Change>` sections name the modular parts; reuse them as the `####` parts under "What changed".

## Procedure

1. **Prune.** For every existing `## PR #N:` entry in `operator_manual/current_changes.md`, run `gh pr view N --json state -q .state`. If it prints `MERGED` or `CLOSED`, delete the whole entry: its heading, marker, and everything up to the next `##` or the end of the file. Entries with `pr="pending"` for other branches stay. Tell the user which entries were removed and which sections they had highlighted, so they can run `section <NN>` if a section should absorb the merged change. That refresh is not automatic.
2. **Append.** If no entry exists for this branch, append one at the end of the file on the "Current working changes" profile in `section_template.md`: heading `## Branch <branch>: <title>` (or `## PR #N: <title>` when `--pr` is given), the marker line with today's date, then `### Where this fits` (system map with the highlights from the path-prefix table in `system_map.md`), `### Key definitions` (new terms, also added to `glossary.md`, or "None new."), `### Packages and tools`, `### What changed` with one `####` per part, each opening with a diagram, and `### Run it yourself`. Length 300 to 800 words unless the change is trivial; at least one diagram.
3. **Rename.** If an entry for this branch exists with `pr="pending"` and `--pr N` is given, change its heading to `## PR #N: <title>` and its marker to `pr="N"`. Change nothing else in it.
4. **Idempotence.** If an entry for this branch exists, nothing was pruned, and there is no new commit since the entry's date, report "nothing changed" and stop.
5. **Check.** `uv run manual-check operator_manual/current_changes.md` and `uv run mkdocs build --strict`.

## Promises

- No edit to an existing entry other than the two above, ever.
- `manual-check` needs no network; only the prune step talks to GitHub, through `gh`.
- The entry names the branch in its marker, so `manual-check` rejects a second entry for the same branch.

## What `create-pr` does around it

After drafting the description and before pushing: ask the user once whether this pull request deserves a manual entry. If yes, run `/operator-manual pr-entry --body <body.md>`, commit through the hook, and re-run `uv run pr-refs check` and `uv run pr-refs lint`, because the commit moved lines. After `gh pr create`, run `/operator-manual pr-entry --pr <N>` so the heading carries the number, commit, and push.
