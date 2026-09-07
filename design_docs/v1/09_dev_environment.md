# 09. Development environment

## 1. Purpose

Every piece of Python in this repository runs from a virtual environment inside the project folder, never from the machine's Python. Dependencies are pinned exactly so an environment can be rebuilt byte for byte, and upgraded on purpose with one command. This doc defines the tool, the files, the commands, the project layout, and how the pieces that are not Python are pinned.

## 2. Diagram

```
  home_assistant/                                 what pins it
  ├── .python-version        "3.12"               uv installs and uses this interpreter; the Mac's python3 is never touched
  ├── pyproject.toml         direct dependencies   loose constraints, e.g. httpx>=0.27; also black/isort config, scripts
  ├── uv.lock                every dependency      exact versions and hashes, committed
  ├── .venv/                 the environment       created by `uv sync`, ignored by git, rebuilt anywhere from the lock
  │
  ├── assistant_core/        shared agent loop     ┐
  ├── web_search_mcp/        MCP search server     │ Python packages in this repo,
  ├── benchmark/             harness, judge, report│ importable from .venv
  ├── custom_components/     studio_assistant      │ (HA component: developed here, deployed into the VM)
  ├── scripts/               benchmark_llm, deploy │
  ├── tests/                                       ┘
  │
  ├── docker/searxng/        compose + settings    image tag pinned in docker-compose.yml
  ├── deploy/launchd/        plists                point at /abs/path/.venv/bin/python
  ├── design_docs/           v0 frozen, v1 living
  ├── claude_docs/           coding conventions
  └── CLAUDE.md

  freeze:   uv lock                       → rewrites uv.lock from pyproject constraints
  rebuild:  uv sync --frozen              → .venv exactly as locked, fails if lock is stale
  upgrade:  uv lock --upgrade [--upgrade-package X] && uv sync && uv run pytest
  run:      uv run python scripts/benchmark_llm.py      uv run web-search-mcp      uv run pytest
```

## 3. How it works, step by step

1. Install `uv` once with Homebrew. It is a single binary that manages Python interpreters, virtual environments, and dependency resolution.
2. `uv python install 3.12` downloads a standalone interpreter into uv's own directory. `.python-version` in the repo tells uv to use it here. The interpreter that ships with macOS, and any Homebrew Python, are never involved.
3. `uv sync` reads `pyproject.toml` and `uv.lock`, creates `.venv/` in the project folder, and installs exactly the locked versions. On a clean clone this reproduces the environment. `--frozen` makes it fail loudly instead of silently re-resolving if the lock is out of date.
4. Adding a dependency is `uv add httpx`, which edits `pyproject.toml`, re-locks, and syncs in one step.
5. Running anything is `uv run <command>`, which guarantees the command executes inside `.venv`. Scripts declared under `[project.scripts]` become commands, so the search server is `uv run web-search-mcp`.
6. Upgrading is deliberate: `uv lock --upgrade` moves everything to the newest versions allowed by the constraints, or `--upgrade-package` moves one. Then `uv sync`, `uv run pytest`, review the lock diff, commit.
7. Long-running services on the Mac are launchd agents whose plists call `.venv/bin/python` by absolute path, so they also run inside the environment without needing `uv` on the path at login.

## 4. The Home Assistant component exception

`custom_components/studio_assistant` is developed and tested in `.venv` like everything else, using `pytest-homeassistant-custom-component` to boot a minimal Home Assistant in-process. At runtime, though, Home Assistant loads the component inside its own Python in the VM and installs the packages listed in the component's `manifest.json` itself. So that folder has two dependency declarations that must agree: the project lock (for development) and `manifest.json` (for deployment). `scripts/deploy_component.py` copies the folder into the VM's config directory and checks that the versions in `manifest.json` match the lock before doing so.

## 5. What is not Python, and how it is pinned

| Piece | Pinned by |
|---|---|
| Ollama | Homebrew formula version, recorded in `docs/VERSIONS.md`; upgraded deliberately after re-running the benchmark |
| Models | Ollama tag plus digest, recorded in `benchmark/config.yaml` and `docs/VERSIONS.md` |
| SearXNG | Image tag in `docker/searxng/docker-compose.yml` |
| Home Assistant OS | Version recorded in `docs/VERSIONS.md`; updated monthly by hand |
| Music Assistant, ESPHome, Piper add-ons | Versions recorded in `docs/VERSIONS.md` |
| `uv` itself | Homebrew; minimum version noted in `pyproject.toml` |

## 6. Packages and tools, and what they do for us

| Tool | Role |
|---|---|
| `uv` | Interpreter management, virtual environment, resolver, lock file, script runner. Replaces pyenv, venv, pip, and pip-tools with one tool. Chosen over pip-tools because it also manages the interpreter, which is what makes "never the machine's Python" enforceable, and because it is fast enough that re-locking is not a chore. |
| `pyproject.toml` | The single source for project metadata, direct dependencies, console scripts, and tool configuration: black at line length 200, isort with the black profile, pytest options. |
| `uv.lock` | The exact, hashed dependency graph. Committed. Reviewed in diffs like code. |
| `black`, `isort` | Formatting and import ordering per CLAUDE.md, run with `uv run black .` and `uv run isort .`. |
| `pytest`, `pytest-asyncio` | Tests. Async because the agent loop, the MCP client, and the HA component are async. |
| `pytest-homeassistant-custom-component` | Home Assistant test fixtures for the custom component. |
| `mypy` (optional, later) | Type checking; every function is typed per CLAUDE.md, so this is cheap to add. |

## 7. Project layout and conventions

- Packages: `assistant_core`, `web_search_mcp`, `benchmark`, `custom_components/studio_assistant`. Shared helpers only when two packages need the same function, and then in `utils/{util_type}_utils.py` per CLAUDE.md.
- Every function parameter typed. Functions small. No flag arguments. Exceptions, not error codes. Comments explain why, not what. See `claude_docs/CLEAN_CODE.md`.
- Secrets (Spotify client secret, the frontier API key for the benchmark) live in `secrets/` or `.env`, both ignored by git, and are read through one small settings module.
- Benchmark results are committed under `benchmark/results/<date>/` so runs can be compared over time; only the SearXNG response cache inside a run is ignored.

## 8. Failure modes

- **Someone runs `python3 script.py`.** It may work by accident with the system Python and then fail on the next machine. Every documented command uses `uv run`; a pre-commit hook can refuse commits when `.venv` is not active.
- **Lock drifts from pyproject.** `uv sync --frozen` fails and says so; `uv lock` fixes it.
- **A transitive dependency breaks on upgrade.** The upgrade command is followed by the test suite before commit; the lock diff shows exactly what moved.
- **`manifest.json` and the lock disagree.** The deploy script refuses to copy.
- **launchd agent runs the wrong interpreter.** Plists use absolute `.venv/bin/python` paths; a health check logs `sys.executable` at startup.

## 9. Concepts for newcomers

Most of this will be familiar from data work; two things are worth stating plainly.

**Lock file versus requirements file.** `requirements.txt` produced by `pip freeze` lists what happened to be installed. A lock file records the full resolved graph with hashes and the constraints it was solved from, and can be regenerated deterministically. `uv export --format requirements-txt` produces the classic file when another tool needs it.

**Why the interpreter matters as much as the packages.** Two machines with identical package pins but different Python versions can still behave differently, especially for compiled packages like the MLX wheels. Pinning the interpreter closes that gap.

## 10. Sources

- uv documentation: [docs.astral.sh/uv](https://docs.astral.sh/uv/)
- uv lock and sync semantics: [docs.astral.sh/uv/concepts/projects/sync](https://docs.astral.sh/uv/concepts/projects/sync/)
- Home Assistant custom component manifest: [developers.home-assistant.io/docs/creating_integration_manifest](https://developers.home-assistant.io/docs/creating_integration_manifest/)
- pytest-homeassistant-custom-component: [github.com/MatthewFlamm/pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component)

## 11. As built, 2026-09-05

- `uv 0.12`, Python 3.12.14 installed by uv, `pyproject.toml` with hatchling and the three packages listed explicitly, `uv.lock` committed. Console scripts: `web-search-mcp`, `benchmark-run`, `benchmark-judge`, `benchmark-report`.
- `scripts/dev_setup.sh` is the documented way to create or refresh the environment. It runs `uv sync --frozen` (or `uv lock --upgrade && uv sync` with `--upgrade`) and then `chflags -R nohidden .venv`. The flag matters because this repository lives in an iCloud-synced Desktop folder, macOS marks dot-prefixed trees there as hidden, and Python 3.12.14 skips hidden `.pth` files, which removes the project's own packages from the environment. Moving the repository out of an iCloud-synced folder would remove the need for this step.
- `scripts/lint.sh` runs black and isort through `uv run`, then shfmt and shellcheck on the shell scripts, skipping `.venv`.
- Docker Desktop 29.7 provides the daemon; its CLI is used from the application bundle because the `/usr/local/bin` link was not created. `scripts/searxng.sh` adds that path itself.
- Ollama 0.33.3 from Homebrew, started with `brew services start ollama`.
- Pinned versions of the third-party packages are in `uv.lock`; the notable ones on the first day were `anthropic 1.4.0`, `mcp 2.1.1`, `ollama 0.6.2`, `trafilatura 2.2.0`, `pydantic 2.13.5`.

## 12. Code review process, added 2026-09-07

Once the repository had five packages and forty commits pushed straight to `main`, nothing was checking that new code followed `CLAUDE.md`. This section adds the checks and the path a change takes to reach `main`.

```
  laptop                                      GitHub
  ──────                                      ──────
  edit code
     │
  git commit ──▶ .githooks/pre-commit         (installed by scripts/dev_setup.sh)
     │            1. scripts/lint.sh -c       black, isort, shfmt, shellcheck, check only
     │            2. uv run deslop            typed parameters, comment-to-code ratio
     │            3. uv run pytest -q         the whole suite (hermetic, ~20 s)
     │          any failure refuses the commit and prints how to fix it
     ▼
  git push ──▶ pull request ──▶ .github/workflows/checks.yml
                  │               job "checks":         the same three steps on ubuntu
                  │               job "pr-description": uv run pr-refs check on the PR body
                  │
                  ├──▶ Codex review (bot) ──▶ Claude fixes, replies, resolves ──▶ @codex review   (loop, PR 2)
                  │
                  ▼
               branch protection on main: PR required, both jobs green, all threads resolved, no bypass
                  │
               one human click on Merge (squash)
```

**Git hooks.** Git runs executable files from a hooks directory at fixed moments; `pre-commit` runs before a commit is recorded and a non-zero exit cancels it. Hooks are not versioned by default (they live in `.git/hooks`), so the repository keeps them in `.githooks/` and `scripts/dev_setup.sh` points git there with `git config core.hooksPath .githooks`. The hook checks the working tree as a whole rather than only the staged files: the repository is small, the three steps take about twenty seconds, and this keeps the hook and CI identical. `git commit --no-verify` skips the hook; CI catches that.

**deslop.** A small AST-based checker (`deslop/`) for the two rules in `claude_docs/CLEAN_CODE.md` that a script can judge without taste: every function parameter has a type annotation (`self` and `cls` excepted), and a function's comment lines, docstring included, never outnumber its code lines. Comments are found with Python's tokenizer rather than by scanning for `#`, so a `#` inside a string is never counted. When a short function carries a long comment that earns its place, `# deslop: allow-comments` on or above the `def` line exempts that one function from the ratio rule and leaves the exception visible in review. Findings print as `path:line: message`, and the exit code is 1 when there are any.

**PR references (`pr-refs`).** A pull request description has one section per important change, and every bullet ends with the lines a reviewer should read. Typing line numbers from memory produces wrong ones, so `uv run pr-refs resolve deslop/checks.py:count_lines` prints the real span of that definition as `` `deslop/checks.py:41-58` (`count_lines`) ``, and for files without symbols `uv run pr-refs resolve .githooks/pre-commit:"uv run deslop"` prints a range that contains that text. `uv run pr-refs check body.md` re-verifies every reference against the checked-out code, and the `pr-description` CI job does the same on every push, so a reference that goes stale after a later commit blocks the merge until it is re-resolved.

**GitHub Actions and branch protection.** GitHub Actions runs the workflow in `.github/workflows/checks.yml` on a fresh Ubuntu machine for every pull request; it installs the locked environment with `uv sync --frozen` (without the `voice` group, whose MLX wheels exist only for Apple Silicon) and runs the same commands as the hook. Branch protection is a repository setting that makes `main` accept only merges of pull requests whose required jobs passed and whose review threads are all resolved. No approving review is required: GitHub never lets a pull request's author approve their own PR, and on a one-person repository the author is always the same person, so a required approval would block every merge. The human step is the Merge click itself, after reading the review rounds.

Sources: [git hooks](https://git-scm.com/docs/githooks), [GitHub branch protection](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches), [Python `tokenize`](https://docs.python.org/3/library/tokenize.html), [Python `ast`](https://docs.python.org/3/library/ast.html).
