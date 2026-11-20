# Deploying an update

Run this at the Mac that serves (the Studio), after the change is merged on GitHub.

## Deploy

1. Open Terminal on the Studio.
2. Run:
    ```bash
    cd ~/Code/home_assistant_live
    scripts/deploy.sh
    ```
3. Wait for the last line. A model restart can take up to 15 minutes.

## What the last line means

| Exit | Last line starts with | Meaning | Do |
|---|---|---|---|
| 0 | `deploy: done` | The new commit is live | Nothing |
| 0 | `deploy: already at this commit` | Nothing new on main | Nothing |
| 1 | `deploy: NOT deployed` | Tests failed; nothing restarted | Fix it on a branch |
| 1 | `deploy: rolled back` | The test question failed; the old commit answers again | Fix it on a branch |
| 2 | `deploy: the last good commit does not answer either` | Nothing answers | `scripts/services.sh status`, then ask for help |

## Options

1. See what would restart, changing nothing: `scripts/deploy.sh --dry-run`
2. Deploy one commit: `scripts/deploy.sh --ref <sha>`
3. Also ask a searched question: `scripts/deploy.sh --full-smoke`
