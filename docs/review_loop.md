# The automated review loop

Claude opens a pull request, Codex reviews it, Claude fixes what the review found, Codex looks again, and the human's only step is one click on
Merge once everything is green. This page is the one-time setup, the round-by-round procedure the fixing agent follows, and how to stop it.

```
  PR opened ──▶ CI: checks + pr-description ──▶ Codex automatic review (bot chatgpt-codex-connector)
                                                        │ submits a GitHub review
                                                        ▼
                                  .github/workflows/claude-review-fixes.yml (one round)
                                    fix or decline each thread ─▶ lint, deslop, tests ─▶ push
                                    ─▶ re-resolve PR references ─▶ reply + resolve fixed threads
                                    ─▶ "Review round N" comment ─▶ "@codex review" if anything changed
                                                        │
                              round cap: 3 (counted from the "Review round" comments)
                                                        ▼
  Codex has no new findings, CI green, threads resolved ──▶ human reads the round summaries, clicks Merge (squash)
```

## One-time setup

1. **Codex automatic reviews.** In the Codex GitHub integration settings, enable automatic reviews for `seanlin2000/home_assistant`. Codex then
   posts a standard review on every new PR as the bot account `chatgpt-codex-connector`, focused on P0 and P1 findings, guided by the
   `## Code Review Rules` section of `AGENTS.md`. Comment `@codex review` on a PR to trigger a review by hand.
2. **Claude GitHub App and token.** From Claude Code in this repository run `/install-github-app`. When asked how to authenticate, choose the
   Claude subscription token, so review rounds are billed to the subscription and not to the prepaid API balance. This stores the repository
   secret `CLAUDE_CODE_OAUTH_TOKEN`, which the workflow reads. If the command also offers to add its own `claude.yml` workflow, that is optional;
   the loop only needs the app installed and the secret present.
3. **Branch protection** on `main` (set up with PR 1): pull request required, `checks` and `pr-description` green, conversations resolved,
   no bypass. No approving review is required, because GitHub does not let a PR's author approve their own PR and every PR here has the same author.

## One round, step by step

The workflow triggers on `pull_request_review: submitted` and runs only when the review author is the Codex bot. Claude Code then:

1. Counts existing "Review round" comments. At 3 it posts a hand-over comment and stops.
2. Lists unresolved review threads.
3. Fixes each valid point; replies with a reason on each declined point and leaves that thread open.
4. Runs `scripts/lint.sh`, `uv run deslop`, `uv run pytest -q`; nothing is pushed until all three pass.
5. Commits and pushes to the PR branch. Never a force-push, never a change under `.github/workflows`.
6. Re-runs `uv run pr-refs resolve` for any cited symbol that moved and updates the PR body, so the `pr-description` check stays green.
7. Replies in each fixed thread and resolves it. Threads it did not act on stay open.
8. Posts a "Review round N" summary comment.
9. Comments `@codex review` if anything changed, which starts the next round.

## What needs a human

- A thread left open: Claude disagreed or the point was out of scope. Read the reply, then either resolve it yourself or reply with instructions
  and `@claude` to have the interactive workflow act on it.
- The round cap comment: three rounds did not converge. Review the PR directly.
- The merge. Nothing merges on its own: when CI is green and every thread is resolved, the human reads the round summaries and clicks Merge.

## Stopping the loop

Close the PR, or delete `.github/workflows/claude-review-fixes.yml` on `main`. Removing the `CLAUDE_CODE_OAUTH_TOKEN` secret also stops it,
with a failed workflow run on the next review.

## Cost

Each round is one Claude Code session on GitHub's runners, capped at 40 turns and 30 minutes, billed to the Claude subscription. GitHub Actions
minutes are free for this public repository.
