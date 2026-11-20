# Development
<!-- complexity: packages=3 parts=3 concepts=2 tier=deep -->

This page covers how code in this repository is built, checked, and merged, so the Mac runs code that was tested the same way on the laptop and on GitHub. One tool builds the Python environment from a lock file. A git hook refuses a commit that fails formatting, the coding conventions, or the tests, and a pull request runs the same checks again on GitHub, verifies its own description, and builds this handbook. `main` accepts only pull requests that passed, and every merge publishes the handbook. [Operations](10_operations.md#deploy-smoke-test-and-rollback) takes over from there and deploys a commit to the Mac.

## Where this fits

```mermaid
flowchart TB
--8<-- "_includes/system_map.mmd"
class laptop current
```

## Key definitions

| Term | Meaning |
|---|---|
| Lock file | A file that records every resolved dependency at one exact version with its hash, regenerated from the declared constraints; `uv.lock` is one. |
| Git hook | A program git runs at a fixed moment, such as just before a commit is recorded, whose non-zero exit cancels the commit. |
| Worktree | A second checkout of the same repository in its own folder, with its own branch and working files but the same history. |
| Line reference | A citation in a pull request description of the form `` `path:start-end` (`symbol`) `` that names the exact lines a reviewer should open. |
| Branch protection | A GitHub setting that makes `main` accept only merges of pull requests whose required checks passed and whose review threads are all resolved. |

## Packages and tools

| Tool | What it is | How this part uses it |
|---|---|---|
| uv 0.12.10 | One binary, installed with Homebrew, that manages Python interpreters, virtual environments, dependency resolution, and the lock file | Installs Python 3.12.14 into its own folder, builds `.venv/` from `uv.lock`, and runs every Python command through `uv run`, so the machine's own Python is never involved |
| black 26.5.1 and isort 9.0.1 | A Python code formatter and an import sorter | `scripts/lint.sh` runs both at line length 200 with the black profile; the hook runs them in check mode |
| shfmt 3.14.0 and shellcheck 0.11.0 | A shell script formatter and a shell script linter | `scripts/lint.sh` formats every `.sh` file and the hooks with four-space indents and lints them; CI installs the same shfmt version |
| pytest 9.1.1 and pytest-asyncio 1.4.0 | The test runner and its asyncio plugin | `uv run pytest -q` runs the 287 tests in `tests/` in about four seconds; `asyncio_mode = "auto"` lets async tests run without a marker |
| git 2.39 and the GitHub CLI `gh` 2.100 | Version control, and GitHub from the terminal | Hooks, worktrees, and branches on the laptop; `gh pr create`, `gh pr edit`, and `gh pr checks --watch` for the pull request |
| GitHub Actions | GitHub's hosted runners, driven by YAML workflows in `.github/workflows/` | `checks.yml` runs three jobs on every pull request; `pages.yml` publishes the handbook on every push to `main`; `actions/cache` keeps drawn diagrams between runs |
| MkDocs 1.6.1 with Material 9.7.7 | A static site generator for markdown, and the theme that gives it navigation, search, and a dark scheme | Turns `operator_manual/` into the site at `https://seanlin2000.github.io/home_assistant/`; `--strict` fails the build on any broken link, missing include, or diagram that will not draw |
| Mermaid, mermaid-cli 11.17.0, and Google Chrome | A text language for diagrams, its command-line renderer `mmdc`, and the browser `mmdc` drives | Every diagram in the handbook is Mermaid text, drawn to SVG through `mmdc` and Chrome when the site is built and when `manual-check` runs |
| `deslop`, `pr_references`, `manual_checks`, `diagrams` (ours) | Four Python packages at the top of the repository | `uv run deslop` checks Python source; `uv run pr-refs` writes and checks line references; `uv run manual-check` checks this handbook; `diagrams` draws every figure for both the site and the checker |
| Claude Code skills | Markdown procedures in `.claude/skills/` that a Claude Code session loads when you type their slash command | `/create-pr` walks a change from worktree to open pull request; `/operator-manual` writes and checks this handbook; `/draw-diagram` holds the rules for every figure |

## How it works

### The environment

```mermaid
flowchart LR
--8<-- "_includes/palette.mmd"
%% grid: pyproject  lock    venv  used
%% grid: pyver      python  .     .
%% peers: pyproject lock venv used pyver python
pyproject[("pyproject.toml<br/>direct dependencies")]
lock[("uv.lock, committed<br/>every exact version")]
venv[("the .venv folder<br/>git-ignored")]
used("pytest, deslop,<br/>every Python command")
pyver[(".python-version<br/>3.12")]
python("Python 3.12.14<br/>in uv's own folder")
pyproject -- "uv lock" --> lock
lock -- "uv sync" --> venv
venv -- "uv run" --> used
pyver -- "uv python install" --> python
python --> venv
class pyproject,lock,pyver,used ours
class venv,python third
```

A virtual environment is a folder holding one Python interpreter and one set of installed packages, kept apart from everything else on the machine. This project has one, `.venv/` in the repository folder, and every Python command runs inside it. The Python that ships with macOS and any Homebrew Python are never used.

Five steps take the project from declared dependencies to a running command:

1. **`.python-version` picks the interpreter.** It says `3.12`, and `requires-python = ">=3.12,<3.13"` in `pyproject.toml` agrees. The first time uv needs that version it downloads a standalone Python 3.12 (3.12.14 today) into its own folder outside the repository; `uv python install 3.12` does the same on demand.
2. **`pyproject.toml` declares what the code needs.** It lists nine direct dependencies with loose constraints such as `httpx>=0.27`, and four dependency groups: `dev` (black, isort, pytest, pytest-asyncio), `docs` (mkdocs-material), `deploy` (websockets), and `voice` (the Whisper and Kokoro servers, whose MLX wheels exist only for Apple Silicon). `[tool.uv] default-groups` installs all four.
3. **`uv lock` writes `uv.lock`.** It resolves those constraints into every package, direct or transitive, at one exact version with its hash. The lock is committed and reviewed in diffs like code, because two machines with the same lock and the same interpreter run the same bytes.
4. **`uv sync` builds `.venv/` from the lock.** It installs exactly the locked versions and removes any package the lock does not name.
5. **`uv run` runs a command inside `.venv/`.** Before running it, uv re-resolves the lock if `pyproject.toml` has changed and syncs `.venv/` if it no longer matches the lock.

`pyproject.toml` also turns ten functions into commands under `[project.scripts]`. `uv run deslop` calls `deslop.cli:main`, `uv run pr-refs` calls `pr_references.cli:main`, `uv run manual-check` calls `manual_checks.cli:main`, and `uv run draw-diagram` calls `diagrams.cli:main`. The other six start the search server, the benchmark's four commands, and the Kokoro server. The long-running services on the Mac skip `uv run`: their launchd plists call the commands in `.venv/bin/`, such as `.venv/bin/web-search-mcp`, by absolute path, so they run inside the environment without uv on the path at login (see [Operations](10_operations.md)).

`scripts/dev_setup.sh` is the one way to create or refresh the environment:

*From `scripts/dev_setup.sh`:*

```bash
if [ "${1:-}" = "--upgrade" ]; then
    uv lock --upgrade
fi
# --locked refuses a uv.lock that no longer matches pyproject.toml, so a forgotten `uv lock` fails here instead of being installed.
uv sync --locked

chflags -R nohidden .venv
git config core.hooksPath .githooks
uv run python -c "import assistant_core, benchmark, web_search_mcp; print('environment ready:', __import__('sys').executable)"
```

What each part does:

- **`uv sync --locked`** installs exactly what `uv.lock` says and never rewrites the lock. It first checks that the lock still matches `pyproject.toml`, and when it does not, it fails and installs nothing, so an edit to `pyproject.toml` without `uv lock` stops here instead of being installed. `--upgrade` relocks first, so its sync passes.
- **`chflags -R nohidden .venv`** matters when the repository lives in an iCloud-synced folder. macOS marks dot-prefixed items there hidden, and Python 3.12.14 refuses to load hidden `.pth` files, which would silently drop the project's own packages from the environment.
- **`git config core.hooksPath .githooks`** points git at the versioned hooks folder (see [The path to main](#the-path-to-main)).
- **The last line** imports three of the project's packages and prints the interpreter path, which proves the environment works.

Dependencies move only when you ask. `scripts/dev_setup.sh --upgrade` runs `uv lock --upgrade`, which moves every package to the newest version its constraint allows, then the same `uv sync --locked`. To move one package, run `uv lock --upgrade-package httpx`, then `scripts/dev_setup.sh`. Either way the `uv.lock` diff shows every package that moved, and it is reviewed and committed like code. [How to refresh this file](versions.md#how-to-refresh-this-file) on Versions of Record lists the steps that go with an upgrade, including the component's `manifest.json` pins, which move with the lock.

Not everything is Python. Ollama, Docker Desktop, UTM, Home Assistant OS and its add-ons, mermaid-cli, and uv itself come from Homebrew or from their own installers. [Versions of Record](versions.md) records each one's version with the command that checks it. Models are pinned there by Ollama tag and build id, because a re-pull of the same tag can fetch a different build.

### The path to main

```mermaid
flowchart TB
--8<-- "_includes/palette.mmd"
%% grid: commit   .github
%% grid: hook     checksjob
%% grid: push     descjob
%% grid: .laptop  docsjob
%% grid: fix      protect
%% grid: .laptop  merge
%% grid: .laptop  pages
%% join: protect
%% peers: commit hook push fix checksjob descjob docsjob protect merge pages
subgraph laptop["the laptop"]
  commit("git commit<br/>on a worktree branch")
  hook("pre-commit hook<br/>lint, deslop, pytest")
  push("git push,<br/>gh pr create")
  fix("fix on the branch,<br/>push the fix")
end
subgraph github["GitHub"]
  checksjob("checks job<br/>the hook's three steps")
  descjob("pr-description job<br/>pr-refs check and lint")
  docsjob("docs job<br/>strict build, diagrams")
  protect("branch protection<br/>jobs pass, threads closed")
  merge("merge<br/>squash, a person clicks")
  pages("pages.yml<br/>publishes the handbook")
end
commit --> hook
hook --> push
push --> checksjob
push --> descjob
push --> docsjob
checksjob --> protect
descjob --> protect
docsjob --> protect
protect -- "fail" --> fix
protect -- "pass" --> merge
merge --> pages
class hook,checksjob,descjob,docsjob,pages ours
class commit,push,fix third
class protect,merge ext
```

Every change starts on a branch in its own worktree, cut from the latest `origin/main`, and reaches `main` only through a pull request. The same three checks run twice on the way: on the laptop before the commit exists, and on GitHub before the merge.

**On the laptop.** `scripts/dev_setup.sh` sets `core.hooksPath` to `.githooks/`, so git runs `.githooks/pre-commit` before recording any commit. The hook checks the whole working tree rather than only the staged files, which keeps it identical to CI, and it takes under ten seconds. A passing commit prints three lines: `== pre-commit: formatting check ... ok`, `== pre-commit: deslop ... ok`, and `== pre-commit: tests ... ok`. A failing step prints its output and a hint that says what to do, and the commit is refused.

*From `.githooks/pre-commit`, `run_step`:*

```bash
run_step() {
    local title=$1 hint=$2
    shift 2
    printf '== pre-commit: %s ... ' "$title"
    if "$@" >"$LOG" 2>&1; then
        printf 'ok\n'
    else
        printf 'FAILED\n\n'
        cat "$LOG"
        printf '\npre-commit: %s failed. %s\n' "$title" "$hint" >&2
        exit 1
    fi
}

run_step "formatting check" "Run scripts/lint.sh, then git add the reformatted files and commit again." scripts/lint.sh -c
run_step "deslop" "Fix the findings above, or add '# deslop: allow-comments' to a function whose comment earns its length, and commit again." uv run deslop
run_step "tests" "Fix the failing tests and commit again." uv run pytest -q
```

`git commit --no-verify` skips the hook. `CLAUDE.md` forbids it, and the `checks` job catches it anyway.

**On GitHub.** `checks.yml` runs when a pull request against `main` is opened, pushed to, reopened, edited, or marked ready for review, and again on every push to `main`. Each job starts on a fresh Ubuntu machine, checks out the code, installs uv, and runs `uv sync --locked --no-group voice`, leaving out the group whose wheels need Apple Silicon; a `uv.lock` that no longer matches `pyproject.toml` fails the job there. Then each job runs its own checks:

| Job | What it runs |
|---|---|
| `checks` | Installs shellcheck from apt and shfmt 3.14.0 from its release binary, then the hook's three steps: `scripts/lint.sh -c`, `uv run deslop`, and `uv run pytest -q` |
| `pr-description` | Checks out the pull request's head commit, writes the description to a file, and runs `uv run pr-refs check` and `uv run pr-refs lint` on it (see [The PR description](#the-pr-description)) |
| `docs` | Installs Node 22 and mermaid-cli 11.17.0. Builds a cache key with `scripts/diagram_cache_key.sh` and restores `.cache/manual_diagrams` with `actions/cache`. Runs `uv run mkdocs build --strict`, which draws every diagram not in the cache and fails at `page.md:LINE` on one that will not draw, then `uv run manual-check --no-render` for the structure checks (see [The manual](#the-manual)) |

**Into `main`.** Branch protection on `main` accepts a merge only when all three jobs pass, every review thread is resolved, and the branch is up to date with `main`. Administrators get no bypass. No approving review is required, because GitHub never lets an author approve their own pull request, and in a one-person repository a required approval would block every merge. On a failure you fix the branch and push again, and the jobs run again. The human step is the Merge click, which squashes the branch into one commit on `main`. That push runs `pages.yml`, which publishes the handbook (see [The manual](#the-manual)).

### The checkers

Seven checkers stand between an edit and `main`. Each one reads something different, refuses something different, and runs in a fixed place:

| Checker | Reads | Checks | Runs in |
|---|---|---|---|
| `scripts/lint.sh -c` | Every Python file, every `.sh` file, and the hooks in `.githooks/` | black at line length 200 and isort with the black profile would change nothing; shfmt with four-space indents would change nothing; shellcheck finds nothing | Pre-commit hook, `checks` job |
| `uv run deslop` | Every `.py` file outside `.venv`, `.git`, `vm`, and `__pycache__` | Every function parameter has a type annotation; in each function, comment lines never outnumber code lines | Pre-commit hook, `checks` job |
| `uv run pytest -q` | The tests in `tests/` | Every test passes, including `test_the_real_manual_structure_is_clean`, which runs the manual's structure check | Pre-commit hook, `checks` job |
| `uv run pr-refs check` | The pull request body, and the code at the pull request's head | Every line reference matches the definition's exact span, or has its quoted text on a cited line | `pr-description` job |
| `uv run pr-refs lint` | The pull request body | `## Summary`, `## How to verify`, and `## Review notes` exist; every change section has bullets of reference, bold phrase, description | `pr-description` job |
| `uv run mkdocs build --strict` | `mkdocs.yml`, `operator_manual/`, and its `_includes/` | No broken link, missing anchor, missing include, or page absent from `nav`; every Mermaid diagram renders | `docs` job |
| `uv run manual-check` | `operator_manual/*.md`, `glossary.md`, and `_includes/palette.mmd` | Each page's headings in order, its complexity comment, its system map highlight, palette classes only, Key definitions terms in the glossary, no page numbers in titles or links | `docs` job, as `--no-render` |

Three small packages in this repository do the checking that no off-the-shelf tool does. Each prints findings as `path:line: message`, prints nothing when clean, and exits 1 when there is any finding, so the hook and CI treat them alike. `deslop` reads Python source and is covered here. `pr-refs` reads a pull request description and the code it cites ([The PR description](#the-pr-description)). `manual-check` reads this handbook and drives a browser ([The manual](#the-manual)).

`deslop` enforces the two rules in `claude_docs/CLEAN_CODE.md` that a script can judge without taste:

- **Every function parameter has a type annotation.** That includes `*args`, `**kwargs`, keyword-only, and positional-only parameters. The only exceptions are `self` and `cls` as the first parameter of a method inside a class.
- **Within one function, comment lines never outnumber code lines.** The docstring counts as comment. Only whole-line comments count, so a line of code with a comment after it is a code line.

It walks every `.py` file under the given paths, skipping `.venv`, `.git`, `vm`, and `__pycache__`. It parses each file into a syntax tree with Python's `ast` module to find the functions and their parameters. Separately, it runs Python's tokenizer to find the comment lines, so a `#` inside a string is never counted as a comment.

*From `deslop/checks.py`, `count_lines`:*

```python
def count_lines(node: FunctionNode, source: ParsedSource) -> tuple[int, int]:
    docstring = docstring_lines(node)
    nested = nested_function_lines(node)
    comment_count = len(docstring)
    code_count = 0
    for line in range(node.lineno + 1, (node.end_lineno or node.lineno) + 1):
        if line in docstring or line in nested:
            continue
        if line in source.comment_lines:
            comment_count += 1
        elif line >= node.body[0].lineno and source.lines[line - 1].strip():
            code_count += 1
    return comment_count, code_count
```

Lines that belong to a nested function are left out of the outer function's count, so each function is judged on its own. When a short function carries a long comment that earns its place, the marker `# deslop: allow-comments` exempts that one function from the ratio rule and leaves the exception visible in review. The marker goes on the `def` line, the line above it, or the line above its first decorator. The two findings read:

- `path:line: name: parameter 'x' has no type annotation`
- `path:line: name: 5 comment lines exceed 3 code lines (add '# deslop: allow-comments' to exempt)`

### The PR description

A pull request description has the shape set by `.github/pull_request_template.md`:

- **`## Summary`**: two to five sentences on what and why.
- **One `## <Change>` section per important change**, made of bullets. Each bullet reads in one order: the line references, a short bold phrase ending in a period, then one or two sentences of business logic. The reference comes first so a reviewer can open the code before reading the claim about it.
- **`## How to verify`**: the commands, in a fenced block.
- **`## Review notes`**: where to focus and what to skip.

A description is written and checked in four steps:

1. **Resolve every reference.** Line references are never typed. `uv run pr-refs resolve deslop/checks.py:count_lines` parses the file and prints `` `deslop/checks.py:115-127` (`count_lines`) ``, the definition's span with any decorators. A dotted name such as `pr_references/references.py:SymbolAnchor.span` reaches a method. Shell, YAML, and markdown files have no symbols, so they take a quoted text anchor: `.githooks/pre-commit:"uv run deslop"` prints the first line containing that text through the end of its indented block. The printed form is pasted unchanged.
2. **Check the references.** `uv run pr-refs check body.md` ignores HTML comments and re-resolves every reference against the checked-out code. A symbol reference must match the definition's exact span; a text reference must have its quoted text on one of the cited lines. It prints one line per wrong reference, a warning for a change section that cites no code, and a summary such as `2 references checked, 0 wrong`.
3. **Check the shape.** `uv run pr-refs lint body.md` confirms that the three required sections exist and that every bullet in a change section reads reference, bold phrase, description. It ends with `description shape: 0 problems`.
4. **Let CI check again.** The `pr-description` job runs both commands on the pull request body at every push and every edit of the description. A reference that goes stale after a later commit blocks the merge until it is resolved again.

The `/create-pr` skill, `.claude/skills/create-pr/SKILL.md`, drives this whole path in six steps. It finds out where the work stands, starts the branch in its own worktree from `origin/main`, and runs `scripts/dev_setup.sh` there so the hook can run. It commits through the hook and writes the description outside the tree with references from `pr-refs resolve`, then runs `check` and `lint`. It offers to add an entry to the handbook's [Current Working Changes](current_changes.md) page, pushes, opens or edits the pull request with `gh`, and waits with `gh pr checks --watch`. It reports the URL and the CI result and leaves the Merge click to you.

### The manual

```mermaid
flowchart TB
--8<-- "_includes/palette.mmd"
%% grid: source  serve     preview
%% grid: main    pagesyml  ghpages
%% peers: source serve preview main pagesyml ghpages
subgraph laptop["the laptop"]
  source[("operator_manual/<br/>your working copy")]
  serve("mkdocs serve<br/>draws each diagram")
  preview("127.0.0.1:8000<br/>preview while editing")
end
subgraph github["GitHub"]
  main[("main branch<br/>the latest pages")]
  pagesyml("pages.yml<br/>strict build, diagrams")
  ghpages("GitHub Pages<br/>the public handbook")
end
source -- "on save" --> serve
serve --> preview
source -- "merged PR" --> main
main -- "on merge" --> pagesyml
pagesyml --> ghpages
class source,main,pagesyml ours
class serve,preview third
class ghpages ext
```

MkDocs is a static site generator: it reads a folder of markdown files and one `mkdocs.yml`, and writes plain HTML that any web server can host. Material is the theme that adds the sidebar, the page outline, search, and the light and dark schemes. Both are Python packages in the `docs` dependency group, pinned in `uv.lock` like everything else. `mkdocs.yml` sets four things this handbook depends on:

- **The source and the order.** `docs_dir: operator_manual` names the folder, and `nav` lists every page.
- **Includes.** `pymdownx.snippets` expands a line such as `--8<-- "_includes/system_map.mmd"` into that file's contents, and `check_paths: true` makes a missing include an error.
- **Diagram blocks.** `pymdownx.superfences` keeps a ```` ```mermaid ```` fence intact as one block, so a diagram lives in the markdown as text and is reviewed and diffed as text.
- **Strictness.** The `validation` block makes every broken link, missing anchor, and page absent from `nav` a warning, and `--strict` turns any warning into a failed build.

The browser never draws a diagram. While the site is built, the hook `manual_checks/mkdocs_hook.py` replaces each Mermaid fence with a finished SVG, drawn by the `diagrams/` package in four steps:

1. **Draw.** `mmdc` starts a headless Google Chrome and draws the diagram with the fixed light theme and the ELK layout in `diagrams/mermaid_config.json`.
2. **Lay out.** A diagram whose source pins a grid in `%% grid:` comment lines goes to `diagrams/grid.py`. It puts every box in the cell the source names, wraps each subgraph around the cells it holds, and redraws every edge with right-angled turns. Any other diagram goes to `diagrams/polish.py`, which stretches every layer into a full-width band or full-height column and moves its title into a gutter where no edge runs.
3. **Polish.** Every corner is rounded, and every edge label is filled with the colour behind it.
4. **Store and inline.** The SVG is saved in the cache and inlined on a white card that reads the same in both colour schemes.

A diagram that will not draw stops the build with `page.md:LINE: Parse error on line N`, at the line in the markdown.

Two caches keep the drawing cheap:

- **On the laptop**, `.cache/manual_diagrams` holds every finished SVG, named by a hash of its source and the drawing code. The build hook, `manual-check`, and its PNG writer share it, so `mkdocs serve` draws only the diagrams that changed, and the system map, which every page includes, is drawn once.
- **In CI**, the `docs` job and `pages.yml` restore that folder with `actions/cache`. A cached file's name does not cover everything that shapes a drawing, so `scripts/diagram_cache_key.sh` names the cache after the rest: the `diagrams/` package (all but its `sketches/` folder) with the cache and the hook, the exact npm packages mermaid-cli resolved to, and the runner image, which supplies Chrome and its fonts. Each run restores the newest cache with that name, draws only what is missing, and saves its own.

On each merge, `pages.yml` builds the site the same way, uploads the `site/` folder, and deploys it to GitHub Pages. Its `concurrency` group cancels an older deploy when a newer one starts.

`manual-check` checks the handbook outside the build. It finds every Mermaid block in every page, expands the includes, and draws each through the same `diagrams/` package and cache, four at a time by default. A failure is reported as `path:line: Parse error on line N` at the line in the markdown, mapped back through the include, so an error inside `system_map.mmd` points at the include line. `--png <dir>` also writes every diagram as a PNG, exactly as the site shows it, screenshotted by Chrome at twice the pixel density. The last check is a person looking at each PNG against the twelve rules of the `draw-diagram` skill. `uv run draw-diagram file.mmd --png out.png` does the same for one loose diagram. Chrome is found through `PUPPETEER_EXECUTABLE_PATH` when it is set, then in `/Applications`, then as a Chrome or Chromium on the path.

The same command checks each page's structure against the profile its file name selects, the checks listed for it in [The checkers](#the-checkers). `--no-render` runs only those. The test `test_the_real_manual_structure_is_clean` runs them on the real handbook, so the pre-commit hook covers structure on every commit.

The `/operator-manual` skill holds the steps for writing a page, the page profiles, the system map with each page's highlights, and the complexity rubric that sets a page's length. It invokes the `/draw-diagram` skill, with its twelve rules, four shapes, and five colours, for every drawing.

## Run it yourself

Everything here runs on the laptop from the repository folder.

1. Install the tools once per machine, then build the environment. The diagrams also need Google Chrome in `/Applications`.

    ```bash
    brew install uv shfmt shellcheck gh mermaid-cli
    uv python install 3.12
    scripts/dev_setup.sh
    ```

    uv installs the locked packages, then the last line prints `environment ready: /Users/<you>/code/home_assistant/.venv/bin/python`.

2. Run the three checks the hook runs:

    ```bash
    uv run pytest -q
    scripts/lint.sh -c
    uv run deslop; echo "exit $?"
    ```

    The tests print rows of dots and end with `287 passed in 3.94s`, give or take a second. The formatting check ends with a black line such as `144 files would be left unchanged.` and isort's `Skipped 1 files`; shfmt and shellcheck print nothing when the shell scripts are clean. `deslop` prints nothing, then `exit 0`. Without `-c`, `scripts/lint.sh` rewrites files in place.

3. Give `deslop` a file with an untyped parameter:

    ```bash
    printf 'def double(x):\n    return 2 * x\n' > /tmp/untyped.py
    uv run deslop /tmp/untyped.py
    ```

    It prints `/tmp/untyped.py:1: double: parameter 'x' has no type annotation` and exits 1.

4. Resolve two references, one to a function and one to a line of shell:

    ```bash
    uv run pr-refs resolve deslop/checks.py:count_lines '.githooks/pre-commit:"uv run deslop"'
    ```

    You see `` `deslop/checks.py:115-127` (`count_lines`) `` and `` `.githooks/pre-commit:27-27` ("uv run deslop") ``.

5. Paste the first reference into a minimal description written outside the tree, and check it:

    ```bash
    cat > /tmp/body.md <<'BODY'
    ## Summary
    Exercise the description checks.
    ## Comment counting
    - `deslop/checks.py:115-127` (`count_lines`) **Nested functions are excluded.** Each function is judged on its own lines.
    ## How to verify
    uv run pytest -q
    ## Review notes
    None.
    BODY
    uv run pr-refs check /tmp/body.md
    uv run pr-refs lint /tmp/body.md
    ```

    `check` prints `1 references checked, 0 wrong`, and `lint` prints `description shape: 0 problems`. Change `115-127` to `115-126` and run `check` again: it prints `` `count_lines` actually spans lines 115-127 `` and exits 1.

6. Check this page, then preview the handbook:

    ```bash
    uv run manual-check operator_manual/09_dev_environment.md
    uv run mkdocs serve
    ```

    `manual-check` prints nothing when the page is clean. The first run draws the page's four diagrams in a few seconds; later runs take them from the cache. `mkdocs serve` prints `Serving on http://127.0.0.1:8000/home_assistant/` and rebuilds whenever a file under `operator_manual/` is saved. Open that address, and press Ctrl-C to stop the server. `uv run mkdocs build --strict` builds once into `site/` and ends with `Documentation built in N seconds`, or with `Aborted with N warnings in strict mode!` and the offending links.

7. Upgrade the dependencies on purpose:

    ```bash
    scripts/dev_setup.sh --upgrade
    git diff --stat uv.lock
    uv run pytest -q
    ```

    The lock diff shows every package that moved. If the tests fail or the move is unwanted, `git checkout uv.lock && scripts/dev_setup.sh` puts the environment back.

8. Start a change the repository's way, which is what `/create-pr` does for you. Replace `my-change` with a short kebab-case name:

    ```bash
    git fetch origin
    git worktree add -b my-change ../home_assistant_my-change origin/main
    cd ../home_assistant_my-change
    scripts/dev_setup.sh
    ```

    Edit, then `git commit`. You see the three `== pre-commit:` lines end in `ok`, or one end in `FAILED` followed by its output and a hint.

9. Push and open the pull request:

    ```bash
    git push -u origin my-change
    gh pr create --base main --head my-change --title "Summary line" --body-file /tmp/body.md
    gh pr checks --watch
    ```

    `gh pr checks --watch` prints one row per job (`checks`, `pr-description`, and `docs`), refreshes every ten seconds, and exits when all three have finished. Ctrl-C stops watching without affecting the jobs. After the Merge click, `git worktree remove ../home_assistant_my-change` deletes the folder.

## Where to look in the code

| Path | What you find there |
|---|---|
| [`pyproject.toml`](https://github.com/seanlin2000/home_assistant/blob/main/pyproject.toml) and [`.python-version`](https://github.com/seanlin2000/home_assistant/blob/main/.python-version) | The direct dependencies, the four dependency groups, the ten console scripts, the packages built into the wheel, and the black, isort, uv, and pytest settings; the interpreter version |
| [`uv.lock`](https://github.com/seanlin2000/home_assistant/blob/main/uv.lock) | Every package at its exact version with hashes; `docs/VERSIONS.md` quotes the notable ones |
| [`scripts/dev_setup.sh`](https://github.com/seanlin2000/home_assistant/blob/main/scripts/dev_setup.sh) | The locked sync, the `--upgrade` path, the hidden-flag fix, the hook installation, and the import check |
| [`scripts/lint.sh`](https://github.com/seanlin2000/home_assistant/blob/main/scripts/lint.sh) | black, isort, shfmt, and shellcheck with their options, and the `-c` check mode the hook uses |
| [`.githooks/pre-commit`](https://github.com/seanlin2000/home_assistant/blob/main/.githooks/pre-commit) | `run_step` and the three steps, each with the hint printed on failure |
| [`deslop/checks.py`](https://github.com/seanlin2000/home_assistant/blob/main/deslop/checks.py) | `check_source`, `unannotated_parameters`, `implicit_receiver`, `count_lines`, `is_exempt`, and the `ALLOW_COMMENTS_MARKER` constant |
| [`deslop/cli.py`](https://github.com/seanlin2000/home_assistant/blob/main/deslop/cli.py) | The file walk with `EXCLUDED_DIRS`, the sorted findings, and `format_finding`, which `manual-check` reuses |
| [`pr_references/references.py`](https://github.com/seanlin2000/home_assistant/blob/main/pr_references/references.py) | `SymbolAnchor`, `TextAnchor`, `Reference`, the two reference patterns, `find_definition`, and `indented_block_end` |
| [`pr_references/lint.py`](https://github.com/seanlin2000/home_assistant/blob/main/pr_references/lint.py) | `WELL_FORMED_BULLET`, `REQUIRED_SECTIONS`, and `change_sections` |
| [`pr_references/cli.py`](https://github.com/seanlin2000/home_assistant/blob/main/pr_references/cli.py) | The `resolve`, `check`, and `lint` subcommands and their summary lines |
| [`manual_checks/cli.py`](https://github.com/seanlin2000/home_assistant/blob/main/manual_checks/cli.py) | `check`, the page loader, and the `--root`, `--no-render`, `--jobs`, and `--png` flags |
| [`manual_checks/headings.py`](https://github.com/seanlin2000/home_assistant/blob/main/manual_checks/headings.py) | The three profiles, `COMPLEXITY` and `TIERS`, the map and palette checks, and the glossary check |
| [`manual_checks/render.py`](https://github.com/seanlin2000/home_assistant/blob/main/manual_checks/render.py) | `render_source`, `drawn_svg`, `render_png`, and `render_findings`, which draws each distinct diagram once and reports a failure at every line that includes it |
| [`manual_checks/blocks.py`](https://github.com/seanlin2000/home_assistant/blob/main/manual_checks/blocks.py) | Fence scanning, `--8<--` snippet expansion, and `file_line`, the mapping behind every finding |
| [`manual_checks/mkdocs_hook.py`](https://github.com/seanlin2000/home_assistant/blob/main/manual_checks/mkdocs_hook.py) and [`manual_checks/diagram_cache.py`](https://github.com/seanlin2000/home_assistant/blob/main/manual_checks/diagram_cache.py) | `on_page_markdown`, which swaps each Mermaid fence for its SVG, and the cache under `.cache/manual_diagrams` with its `cache_key` |
| [`diagrams/`](https://github.com/seanlin2000/home_assistant/tree/main/diagrams) | `mmdc.py` with `find_mmdc`, `find_browser`, and `parse_failure`; `mermaid_config.json`; `layout.py`, which picks `grid.py` or `polish.py`; `screenshot.py` for the PNGs; and `sketches/`, the ASCII sketch each figure was drawn from |
| [`scripts/diagram_cache_key.sh`](https://github.com/seanlin2000/home_assistant/blob/main/scripts/diagram_cache_key.sh) | The CI cache name: the drawing code, the installed mermaid-cli packages, and the runner image |
| [`.github/workflows/checks.yml`](https://github.com/seanlin2000/home_assistant/blob/main/.github/workflows/checks.yml) | The `checks`, `pr-description`, and `docs` jobs |
| [`.github/workflows/pages.yml`](https://github.com/seanlin2000/home_assistant/blob/main/.github/workflows/pages.yml) | The build and deploy jobs that publish the handbook on every push to `main` |
| [`.github/pull_request_template.md`](https://github.com/seanlin2000/home_assistant/blob/main/.github/pull_request_template.md) | The description's shape, with the bullet form and the `pr-refs` commands in its comments |
| [`.claude/skills/create-pr/SKILL.md`](https://github.com/seanlin2000/home_assistant/blob/main/.claude/skills/create-pr/SKILL.md) | The six steps from worktree to open pull request |
| [`.claude/skills/operator-manual/SKILL.md`](https://github.com/seanlin2000/home_assistant/blob/main/.claude/skills/operator-manual/SKILL.md) and [`.claude/skills/draw-diagram/SKILL.md`](https://github.com/seanlin2000/home_assistant/blob/main/.claude/skills/draw-diagram/SKILL.md) | The modes for writing and checking this handbook, with the profiles, diagram style, system map, and rubric under `references/`; the twelve diagram rules |
| [`mkdocs.yml`](https://github.com/seanlin2000/home_assistant/blob/main/mkdocs.yml) | The Material theme, the snippets and superfences extensions, the hook, the strict validation rules, and the `nav` |
| [`CLAUDE.md`](https://github.com/seanlin2000/home_assistant/blob/main/CLAUDE.md) and [`claude_docs/CLEAN_CODE.md`](https://github.com/seanlin2000/home_assistant/blob/main/claude_docs/CLEAN_CODE.md) | The rules the hook and `deslop` enforce: the virtual environment, the branch-and-pull-request path, typed parameters, and comments that explain why |
| [`tests/test_deslop.py`](https://github.com/seanlin2000/home_assistant/blob/main/tests/test_deslop.py), [`tests/test_pr_references.py`](https://github.com/seanlin2000/home_assistant/blob/main/tests/test_pr_references.py), [`tests/test_manual_checks.py`](https://github.com/seanlin2000/home_assistant/blob/main/tests/test_manual_checks.py) | The tests for the three checkers, including the one that checks the real handbook's structure on every commit |

## Further reading

- Design doc: [`design_docs/v1/09_dev_environment.md`](https://github.com/seanlin2000/home_assistant/blob/main/design_docs/v1/09_dev_environment.md), which also covers the code review process and the handbook tooling
- [uv documentation](https://docs.astral.sh/uv/), for the commands behind `dev_setup.sh` and the `uv run` guarantee
- [uv lock and sync semantics](https://docs.astral.sh/uv/concepts/projects/sync/), for what `--frozen` and `--locked` do with a lock that no longer matches `pyproject.toml`
- [git hooks](https://git-scm.com/docs/githooks), for the moments git runs a hook and how the exit code is read
- [GitHub branch protection](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches), for the settings behind the Merge button
- [Python `ast`](https://docs.python.org/3/library/ast.html) and [Python `tokenize`](https://docs.python.org/3/library/tokenize.html), the two standard modules `deslop` reads source with
- [MkDocs](https://www.mkdocs.org/) and [Material for MkDocs diagrams](https://squidfunk.github.io/mkdocs-material/reference/diagrams/), for how the site is built and how Material would otherwise draw Mermaid in the browser
- [Mermaid](https://mermaid.js.org/) and [mermaid-cli](https://github.com/mermaid-js/mermaid-cli), for the diagram syntax and the renderer the hook and `manual-check` drive
- [GitHub Pages with Actions](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site), for what `pages.yml` does on every merge
