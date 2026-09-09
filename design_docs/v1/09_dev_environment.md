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
                  │               job "pr-description": uv run pr-refs check + lint on the PR body
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

**PR references (`pr-refs`).** A pull request description has one section per important change, and every bullet opens with the lines a reviewer should read, then a short bold phrase naming the change, then the business logic (the reference first, so a reviewer can open the code before reading the claim about it). Typing line numbers from memory produces wrong ones, so `uv run pr-refs resolve deslop/checks.py:count_lines` prints the real span of that definition as `` `deslop/checks.py:41-58` (`count_lines`) ``, and for files without symbols `uv run pr-refs resolve .githooks/pre-commit:"uv run deslop"` prints a range that contains that text. `uv run pr-refs check body.md` re-verifies every reference against the checked-out code, and the `pr-description` CI job does the same on every push, so a reference that goes stale after a later commit blocks the merge until it is re-resolved. `uv run pr-refs lint body.md` (added 2026-09-07) checks the shape rather than the ranges: the Summary, How to verify, and Review notes sections exist, and every bullet in a change section reads reference, bold phrase ending in a period, description. Before it, the order was enforced only by whoever wrote the description reading the template; CI runs it next to `check`.

**The `/create-pr` skill.** A Claude Code skill is a markdown file of instructions that a session loads when the user types its slash command; `.claude/skills/create-pr/SKILL.md` is checked in, so every session and every contributor gets the same procedure. It walks the path a change takes to `main` in order: the worktree and branch from `origin/main` (never from the current tree, where other edits may be in progress), `scripts/dev_setup.sh` so the hook can run, commits with the hook on, the description written outside the tree with references from `pr-refs resolve`, `pr-refs check` and `pr-refs lint` before the body is used, `gh pr create` or `gh pr edit`, then `gh pr checks --watch`. Steps 1 and 4 of that path (branching and the description's shape) were the two the tooling could not enforce on its own; the skill closes the first and `lint` the second.

**GitHub Actions and branch protection.** GitHub Actions runs the workflow in `.github/workflows/checks.yml` on a fresh Ubuntu machine for every pull request; it installs the locked environment with `uv sync --frozen` (without the `voice` group, whose MLX wheels exist only for Apple Silicon) and runs the same commands as the hook. Branch protection is a repository setting that makes `main` accept only merges of pull requests whose required jobs passed and whose review threads are all resolved. No approving review is required: GitHub never lets a pull request's author approve their own PR, and on a one-person repository the author is always the same person, so a required approval would block every merge. The human step is the Merge click itself, after reading the review rounds.

Sources: [git hooks](https://git-scm.com/docs/githooks), [GitHub branch protection](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches), [Python `tokenize`](https://docs.python.org/3/library/tokenize.html), [Python `ast`](https://docs.python.org/3/library/ast.html).

## 13. Handbook tooling, added 2026-09-07

The design docs record intent and how the build departed from it, which is the wrong shape for someone who needs to learn the system as it stands. This section adds a second kind of document, the Home Assistant Handbook in `operator_manual/`, and the tools that keep it honest.

```
  operator_manual/*.md                 one page per design doc, plus Introduction, Current changes, Glossary
     │  Mermaid diagrams inline, every "Where this fits" map pulled from _includes/system_map.mmd
     │
     ├──▶ uv run manual-check          renders every diagram through diagrams/ (mermaid-cli, ELK, then the
     │                                 band and corner post-processing) and checks the required headings,
     │                                 the complexity comment, the palette; --png writes each as a picture
     │
     ├──▶ uv run mkdocs build --strict Material for MkDocs turns the markdown into a site; a hook renders
     │                                 every diagram to SVG through the same diagrams/ package, so the page
     │                                 carries the finished picture; any broken link, missing nav entry, or
     │                                 missing include fails the build
     │
     └──▶ .github/workflows/checks.yml job "docs": the same two commands on every pull request
          .github/workflows/pages.yml  on merge to main: build again and publish to GitHub Pages
                                       https://seanlin2000.github.io/home_assistant/
```

**Material for MkDocs.** MkDocs is a static site generator: it reads a folder of markdown files and a `mkdocs.yml` and writes plain HTML that any web server, including GitHub Pages, can host. Material is the theme that gives it a sidebar table of contents, a page outline, search, and a light and dark scheme. It is a Python package, so it is pinned in `uv.lock` in the `docs` dependency group like everything else here; `uv run mkdocs serve` shows the book at `http://127.0.0.1:8000` and rebuilds on every save.

**Mermaid.** A text language for diagrams: `a["Ollama"] --> b["agent"]` becomes two boxes and an arrow. The diagram lives in the markdown as a ```mermaid block, so it is reviewed and diffed as text. Material can draw those blocks in the browser, but it re-themes them at page load (dark group fills, its own label colours), which made the first version of the manual unreadable in the dark scheme. So the site does not draw them in the browser: an MkDocs hook (`manual_checks/mkdocs_hook.py`) renders each block once at build time through the `diagrams/` package, caches the SVG by content hash under `.cache/`, and inlines it on a white card that looks the same in both schemes. Flowcharts are laid out by ELK, the Eclipse Layout Kernel, because it keeps sibling groups in declaration order; that is what lets every architecture diagram be authored as rows or columns with meaning. One drawing of the whole system lives in `operator_manual/_includes/system_map.mmd` and is included into every section with that section's parts highlighted.

**The diagrams package and the draw-diagram skill.** Mermaid and ELK can be configured for a theme and a layout strategy but not for the things that made the first drafts hard to read: containers of different widths that zig-zag across the page, titles sitting on arrows, sharp corners, opaque group fills, and cramped spacing. `diagrams/` fixes that in two steps. `diagrams/mmdc.py` runs `mmdc` with `diagrams/mermaid_config.json` (ELK with network-simplex placement, one light theme, wide node and rank spacing, faintly tinted containers). `diagrams/polish.py` then rewrites the SVG text: when the subgraphs are stacked it stretches each into a band spanning the whole drawing with its title at the left edge, when they are side by side it stretches each into a full-height column with its title at the top, and it rounds every node and container corner. `diagrams/screenshot.py` turns the finished SVG into a PNG with a headless Chrome at twice the pixel density, which is what `manual-check --png` and `uv run draw-diagram` write for a person to look at. The rules themselves, ten of them, with a vocabulary of four shapes and five colours, live in `.claude/skills/draw-diagram/`, and the `operator-manual` skill invokes that skill for every drawing.

**mermaid-cli and the checker.** A browser draws Mermaid, so nothing in Python can tell whether a diagram parses. `mermaid-cli` (`mmdc`, installed with Homebrew; on the CI runners with npm) runs a headless Chrome to draw one diagram to a file. `manual_checks/` (`uv run manual-check`) finds every Mermaid block in the manual, expands the includes, renders each block in parallel with the site's configuration, and reports a failure as `path:line: Parse error on line N` at the markdown line; it also checks each page's required headings, the complexity comment, the palette, the system-map highlight, and glossary agreement. With `--png <dir>` it writes every diagram as a PNG, post-processed as the site shows it, because the last check is a person looking at the drawing against the `draw-diagram` rules, none of which a program can test.

**The skill.** `.claude/skills/operator-manual/` holds the procedure Claude follows to write or refresh a page (with no mode given it asks whether to rewrite a section or append an entry), the page profiles, the system map with each page's highlights, a complexity rubric that sets each page's length, and the contract `create-pr` uses to add an entry to "Current working changes" for every pull request and to remove entries whose pull request has merged.

Sources: [MkDocs](https://www.mkdocs.org/), [Material for MkDocs diagrams](https://squidfunk.github.io/mkdocs-material/reference/diagrams/), [Mermaid](https://mermaid.js.org/), [mermaid-cli](https://github.com/mermaid-js/mermaid-cli), [GitHub Pages with Actions](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).
