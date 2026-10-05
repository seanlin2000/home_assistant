# Operations
<!-- complexity: packages=3 parts=2 concepts=3 tier=deep -->

This page covers how the Mac mini is set up, updated, watched, and read, so the assistant keeps answering with nobody at the Mac. Every operation starts on the laptop and reaches the mini over SSH; the mini never reaches out to the laptop. The health check is the one part that acts on its own: it runs every five minutes and restarts what has stopped answering. Until the mini is bought, the laptop plays both roles.

## Where this fits

```mermaid
flowchart TB
--8<-- "_includes/system_map.mmd"
class laptop,health current
```

## Key definitions

| Term | Meaning |
|---|---|
| SSH key | A secret file on the laptop and a matching public file on the Mac mini, which lets the mini check that the laptop holds the secret without the secret crossing the network. |
| Idempotent | Safe to run again, because every step checks whether it is already done, so a script that fails halfway is simply rerun. |
| Detached checkout | A checkout of a specific commit hash rather than a branch, so what is running is unambiguous and rolling back means checking out an older hash. |
| Deploy plan | The ordered list of actions derived from the paths that changed between the running commit and the new one. |
| Smoke test | The smallest end-to-end exercise that proves the system is alive: one question through Home Assistant, the conversation agent, the model, and the tools. |
| Last good commit | The commit hash that most recently passed the smoke test, kept in the file `last_good_ref` on the mini for a rollback to return to. |
| Maintenance flag | A file the deploy creates before it changes anything, and while it exists the health check records but takes no action. |
| Health snapshot | One health check's result (every probe's outcome, the memory figures, and the actions taken), written to `health.json` and appended to `health.jsonl`. |
| Cooldown | The minimum time between two automatic runs of the same action on the same target, 30 minutes for most actions and two hours for restarting the VM, so a broken part is not restarted at every five-minute check. |

## Packages and tools

| Tool | What it is | How this part uses it |
|---|---|---|
| `ops` package (ours) | Python modules under `ops/` | `health` probes, decides, and does the housekeeping; `deploy` plans, applies, and rolls back; `smoke` asks the one test question; `report` summarises a log directory; `pipeline_runs` pulls Home Assistant's debug runs |
| `scripts/mini.sh`, `scripts/bootstrap_mac.sh`, `scripts/services.sh` (ours) | Three shell scripts | `mini.sh` is the laptop side of every operation and the only script that knows the mini's address. `bootstrap_mac.sh` is copied to the mini and run there. `services.sh` writes and controls the five launchd agents |
| launchd and `launchctl` | macOS's service manager and its command line | Runs the four services and the health check. `launchctl kickstart -k` restarts one agent by name, `bootout` unloads one, and `print` tells the health check whether one is loaded |
| OpenSSH: `ssh`, `scp`, `ssh-copy-id` | The remote shell, built into macOS | Every command on the mini travels over `ssh` with `BatchMode=yes`, so a missing key fails instead of prompting for a password |
| rsync 3.x from Homebrew | A copy tool that sends only the differences; macOS ships `openrsync`, which lacks some of its flags | Pulls the mini's log directory into `logs/mini/`, pushes the model's files, and pushes the VM. An interrupted copy resumes |
| git | Version control | The mini holds a detached checkout. A deploy is `git fetch` then `git checkout --detach SHA`; the mini never commits or pushes |
| `utmctl` (UTM 4.7.5) | UTM's command line | The health check reads `utmctl status "Home Assistant"` and runs `utmctl start` or `stop`. [Home Assistant](06_home_assistant_core.md#the-virtual-machine) covers the VM itself |

## How it works

### Bootstrap

```mermaid
flowchart TB
--8<-- "_includes/palette.mmd"
%% grid: script  checkout
%% grid: env     envmini
%% grid: models  store
%% grid: bundle  utm
%% peers: script env models bundle checkout envmini store utm
%% column-gap: 250
subgraph laptop["the laptop"]
  script("bootstrap_mac.sh<br/>and the Brewfile")
  env[(".env<br/>addresses, secrets")]
  models[("~/.ollama/models<br/>the tested model")]
  bundle[("Home Assistant.utm<br/>the configured VM")]
end
subgraph mini["the Mac mini"]
  checkout("detached checkout,<br/>.venv, agents, SearXNG")
  envmini[(".env<br/>mode 600")]
  store[("~/.ollama/models<br/>the same blobs")]
  utm("the VM in UTM,<br/>keeps its 4 GB")
end
script -- "mini.sh bootstrap" --> checkout
env -- "mini.sh push-env" --> envmini
models -- "mini.sh push-models" --> store
bundle -- "mini.sh push-vm" --> utm
class script,env,envmini,checkout ours
class models,bundle,store,utm third
```

Each command copies one thing from the laptop to the mini:

| Command | What it copies | How |
|---|---|---|
| `mini.sh bootstrap` | `scripts/bootstrap_mac.sh` and the `Brewfile` | `scp` both, then run the script over `ssh -t` so its `sudo` steps can ask for the password |
| `mini.sh push-env` | `.env`, the addresses and secrets | `scp`, then `chmod 600` |
| `mini.sh push-models` | The tested model under `~/.ollama/models` | `rsync` exactly the blobs the model's manifest names |
| `mini.sh push-vm` | `Home Assistant.utm`, the configured VM | `rsync` the UTM bundle; refused while the laptop's VM runs |

Setting up a new mini takes three steps:

1. **Ten minutes at a screen.** A Mac out of the box has no user account, and the wizard that creates one needs a physical display. Plug the mini into a TV, create the account, join the Wi-Fi, and turn on Remote Login and Screen Sharing under System Settings, General, Sharing. Run `ssh-copy-id` from the laptop to install its public key, then unplug the TV.
2. **`scripts/mini.sh bootstrap`.** It runs `scripts/bootstrap_mac.sh` on the mini, which turns a Mac out of the box into the machine [Hardware](08_hardware_and_deployment.md) describes. The script is idempotent, and `--dry-run` prints every step without changing anything. In order, it:
    1. Installs the Xcode command line tools (it stops and asks you to approve their dialog, then rerun), Homebrew, everything in the `Brewfile` with `brew bundle --no-upgrade`, and Python 3.12 with `uv python install`.
    2. Clones the repository to `~/code/home_assistant` (`MINI_PROJECT_DIR`), checked out detached at `origin/main`, then builds `.venv` from the lock file with `scripts/dev_setup.sh`, as [Development](09_dev_environment.md#the-environment) describes, and creates the log directory.
    3. Starts Docker Desktop, waits for its engine, and runs `scripts/searxng.sh up`.
    4. Installs the five launchd agents with `scripts/services.sh install`, and adds Docker and UTM as login items so they return after a power cut.
    5. Reports whether a VM named "Home Assistant" is registered with UTM. It never creates one.
    6. Runs the `sudo` steps, which `--skip-system` leaves out for a rehearsal on the laptop: `pmset` for never sleep, restart after a power failure, and wake on network; the application firewall with `ollama`, the `.venv` Python, Docker, and UTM allowed through; `dseditgroup` to limit Remote Login to the one account; and the SSH drop-in `/etc/ssh/sshd_config.d/010-studio-assistant.conf`, which turns off password login and forbids root. The drop-in is written only when a public key is installed and the session came in over SSH, and removed again if `sshd -t` rejects it, so the script cannot lock out its own operator.
    7. Prints what only a person can finish: automatic login (which needs FileVault off), the first launch of Docker and UTM, DHCP reservations for the mini and the VM, the HDMI dummy plug, and automatic updates off.
3. **Push what is not in git.** Three things are kept out of the repository, and each has a push command:
    - `push-env` copies `.env` and sets its mode to 600.
    - `push-models` reads the manifest of `MINI_MODEL` (by default `gemma4:e4b-it-qat`) under `~/.ollama/models/manifests/` and copies exactly the blobs it names, so the mini runs the same bytes the benchmark scored. `push-models --pull` has the mini download the tag instead.
    - `push-vm` copies the UTM folder `~/Library/Containers/com.utmapp.UTM/Data/Documents/Home Assistant.utm`, the whole configured Home Assistant with its add-ons and its network card's MAC address. It refuses while the laptop's VM is running, because a copy of a running disk is corrupt. The terminal needs Full Disk Access, because the folder is inside an app sandbox. On the mini, open UTM once so it registers the bundle, then run `scripts/haos_vm.sh start`.

A pushed VM keeps the 4,096 MB it was given on the laptop. The alternative is a fresh VM on the mini with 3,072 MB, `HAOS_VM_MEMORY_MB=3072 scripts/haos_vm.sh create`, set up again with `scripts/ha_setup.py`.

### Deploy, smoke test, and rollback

```mermaid
flowchart TB
--8<-- "_includes/palette.mmd"
%% grid: deploy   check     .
%% grid: .laptop  tests     oldback
%% grid: smoke    restart   .
%% grid: .laptop  live      .
%% grid: .laptop  .mini     rollback
%% peers: deploy smoke check tests restart live oldback rollback
subgraph laptop["the laptop"]
  deploy("mini.sh deploy<br/>clean tree, pushed")
  smoke("smoke test: 12 percent<br/>of 250, expects 30")
end
subgraph mini["the Mac mini"]
  check("check out the commit,<br/>maintenance flag on")
  tests("uv sync, preflight,<br/>pytest -q -x")
  restart("restart only what<br/>the change touched")
  live("record as last good,<br/>flag off: live")
  oldback("old commit back,<br/>flag stays on")
  rollback("roll back to the<br/>last good commit")
end
deploy -- "ssh" --> check
check --> tests
tests -- "fail" --> oldback
tests -- "pass" --> restart
restart --> smoke
smoke -- "pass" --> live
smoke -- "fail" --> rollback
class deploy,smoke,check,tests,restart,live,oldback,rollback ours
```

A deploy ends in one of five ways:

| Ending | Maintenance flag | `mini.sh deploy` exits |
|---|---|---|
| Smoke test passes: the new commit is live | off | 0 |
| The mini is already at this commit: nothing to do | off | 0 |
| Tests fail on the mini: the old commit is checked out again | stays on | 1 |
| Smoke test fails, the rollback passes its own smoke test | off | 1 |
| The rollback fails its smoke test too: a person has to look | stays on | 2 |

Pushing to GitHub changes nothing on the mini. Going live is `scripts/mini.sh deploy`, in these steps:

1. **The laptop checks the commit.** It refuses when the working tree has uncommitted changes (pass `--ref` to deploy a specific commit anyway), and when the commit is on no `origin` branch, because the mini can only fetch what the remote has.
2. **The mini takes the deploy lock.** `python -m ops.deploy apply --ref SHA` holds an exclusive lock on `deploy.lock`, so two deploys cannot overlap. It refuses if the mini's own checkout has local changes.
3. **The mini checks out the commit.** It fetches, computes the deploy plan from `git diff --name-only` between the running commit and the new one, creates the maintenance flag so the health check stands down, and checks out the new commit detached.
4. **The mini tests before it restarts anything.** It rebuilds `.venv` with `scripts/dev_setup.sh` if the plan says so, runs the preflight, and runs `pytest -q -x` with a fifteen-minute limit. The preflight parses the component's `manifest.json` and `uv.lock` and fails if the component would ask Home Assistant for a package version the lock does not hold. If any check fails, the old commit is checked out, `.venv` is rebuilt if it had changed, nothing restarts, and the flag stays on.
5. **The mini runs the plan.** Each action runs as a subprocess, in the order the plan gives.
6. **The laptop runs the smoke test.** `python -m ops.smoke` waits up to 300 seconds for Home Assistant's `/api/` to answer 200 with the token, then sends "What is 12 percent of 250?" to `conversation.studio_assistant` through `POST /api/conversation/process`, which hands text to the conversation agent as the Assist pipeline does after speech to text. The answer must contain `30` or `thirty` within 60 seconds. That exercises Home Assistant, the component, Ollama, and the tool server without touching the web; `mini.sh deploy --full-smoke` adds one searched question.
7. **The laptop keeps the commit or rolls back.** On a pass it tells the mini `mark-good SHA` and `clear-maintenance`. On a failure it tells the mini `rollback`, which checks out `last_good_ref` and runs the plan for that change with the tests skipped, then smoke-tests again.

The deploy plan comes from a table of rules. Each changed path is matched by prefix against every rule, and the actions of every matching rule go into the plan.

*From `ops/deploy.py`, `RULES` and `ACTION_ORDER`:*

```python
RULES: tuple[Rule, ...] = (
    Rule(
        prefixes=("uv.lock", "pyproject.toml"),
        actions=("sync_env", "restart:mcp", "restart:whisper", "restart:kokoro"),
        why="dependencies changed: sync the venv and restart every long-running Python service",
    ),
    Rule(prefixes=("web_search_mcp/", "calculator_mcp/", "weather_mcp/", "assistant_core/", "utils/"), actions=("restart:mcp",), why="tool server code changed"),
    Rule(prefixes=("custom_components/", "assistant_core/"), actions=("deploy_component",), why="the component or its vendored core changed"),
    Rule(prefixes=("voice/",), actions=("restart:kokoro",), why="Kokoro server wrapper changed"),
    Rule(prefixes=("scripts/services.sh",), actions=("reinstall_agents",), why="launchd definitions changed"),
    Rule(prefixes=("docker/searxng/",), actions=("restart_searxng",), why="SearXNG configuration changed"),
)
ACTION_ORDER = ("sync_env", "reinstall_agents", "restart:mcp", "restart:kokoro", "restart:whisper", "restart_searxng", "deploy_component")
```

What the rules produce:

- **A path that matches no rule restarts nothing.** A change under `ops/`, `tests/`, `benchmark/`, or the docs gives an empty plan. The health check is a fresh process every five minutes, so it picks up new `ops/` code by itself.
- **A path can match two rules.** A change under `assistant_core/` restarts the tool server and also redeploys the component, because the component carries its own copy of that package.
- **A change to `scripts/services.sh` reinstalls every agent.** `reinstall_agents` replaces the separate restarts of the tool server, Whisper, and Kokoro.
- **Every action records its reason.** The plan names the changed path and rule behind each action, and `apply --dry-run` prints it without changing anything.

Each action runs one command:

| Action | Command |
|---|---|
| `sync_env` | `scripts/dev_setup.sh` |
| `reinstall_agents` | `scripts/services.sh install` |
| `restart:NAME` | `scripts/services.sh restart NAME` |
| `restart_searxng` | `scripts/searxng.sh restart` |
| `deploy_component` | `scripts/deploy_component.py`, which copies the component into the VM over the Samba share and restarts Home Assistant, as [Home Assistant](06_home_assistant_core.md#the-custom-component) describes |

### The health check

The fifth launchd agent runs `scripts/health_check.py` every 300 seconds. Each run probes every part of the stack in the cheapest way that proves the part is ours:

| Part | Probe | Passes when |
|---|---|---|
| Ollama | `GET /api/version` on port 11434 | it answers 200 |
| Tool server | `GET /healthz` on port 8765 | the reply lists every tool name in `REQUIRED_TOOL_NAMES` |
| Whisper and Kokoro | a TCP connect to port 10300 or 10210 | the port accepts |
| SearXNG | `GET /` on port 8080; with `--full`, a real search | the status is below 500; with `--full`, the search returns results |
| Home Assistant | `GET /api/` on the VM | it answers 200, or 401 when there is no token |
| The VM | `utmctl status` | the status is `started` |

The run also records free memory from `memory_pressure`, swap from `sysctl vm.swapusage`, and the model Ollama holds from `/api/ps`, because memory creep is this machine's most likely failure. The real SearXNG search runs only with `--full`, so the loop does not send 288 searches a day to upstream engines.

Three cases decide who acts on a service:

- **A crashed service: launchd restarts it.** Every service agent has `KeepAlive`, so launchd starts an exited process again, at least ten seconds after its last start. The health check never sees a failure.
- **A service that is alive but not answering: the health check restarts it.** One failed probe sets the failure count to 1 and does nothing. A second failure five minutes later triggers `launchctl kickstart -k gui/UID/com.studio-assistant.NAME`, and the time is saved in `health_state.json` under `kickstart:NAME`. For the next 30 minutes that service can fail every probe without another restart. A passing probe resets the count to zero.
- **An unloaded agent: skipped.** A person stops a service with `launchctl bootout`. Its probe then fails, but `launchctl print` says the agent is not loaded, so the snapshot marks it `skip` and the count stays at zero. `services.sh start` loads it again. A missing `utmctl` or an unset `HA_HOST` is also `skip`.

Each run checks these conditions in order, and when the maintenance flag is present it stops at the first:

| Condition | Action | At most once every |
|---|---|---|
| The maintenance flag is present | None: the snapshot is recorded and nothing is changed | Not applicable |
| A launchd agent (Ollama, the tool server, Whisper, Kokoro) failed 2 checks in a row | `launchctl kickstart -k` that agent | 30 minutes, per agent |
| SearXNG failed 2 checks in a row | `scripts/searxng.sh up` | 30 minutes |
| `utmctl status` says the VM is not started | `utmctl start` | 30 minutes |
| The VM is started and Home Assistant failed 5 checks in a row | `utmctl stop`, wait 10 seconds, `utmctl start` | 2 hours |

Why the thresholds are staged:

- **Two failures before a restart.** One slow probe must not restart Ollama, because a restart unloads the model.
- **Five failures before the VM restarts.** Home Assistant disappears for minutes during its own updates and add-on installs, so it gets 25 minutes.
- **A two-hour cooldown on the VM.** If Home Assistant is truly broken, the VM restarts at most twelve times a day, the report shows the pattern, and a person fixes it.

Every action goes into the snapshot as one line, such as `kickstart:mcp (mcp failed 2 checks in a row): ok`, so the report can show what the machine did to itself. `tests/test_health.py` pins every threshold and cooldown without touching launchd or UTM.

On the laptop the agent is installed with `HEALTH_CHECK_FLAGS=--no-remediate scripts/services.sh install`, so it records and never acts, because the laptop's VM is stopped on purpose most of the time. The mini uses the default and acts.

### Logs and the report {#the-report}

```mermaid
flowchart TB
--8<-- "_includes/palette.mmd"
%% grid: debug  .         .          minilogs
%% grid: agent  mcp       exchanges  mirror
%% grid: .      launchd   svclogs    reportp
%% grid: .      healthchk hfiles     .
%% peers: debug agent mcp launchd healthchk exchanges svclogs hfiles minilogs mirror reportp
subgraph mini["the Mac mini"]
  subgraph haos["Home Assistant VM"]
    debug("Assist debug runs<br/>kept in memory")
    agent("conversation agent<br/>after each answer")
  end
  mcp("tool server<br/>POST /exchanges")
  launchd("launchd<br/>each agent's output")
  healthchk("health check<br/>every 300 s")
  subgraph logdir["~/Library/Logs/studio-assistant"]
    exchanges[("exchanges/<br/>one file per day")]
    svclogs[("ollama.log, mcp.log,<br/>whisper.log, ...")]
    hfiles[("health.json<br/>health.jsonl")]
  end
end
subgraph laptop["the laptop"]
  minilogs("mini.sh logs<br/>rsync, websocket")
  mirror[("logs/mini/<br/>the mirror")]
  reportp("ops_report.py<br/>the report")
end
agent -- "a record" --> mcp
mcp --> exchanges
launchd --> svclogs
healthchk --> hfiles
debug -.-> minilogs
exchanges -.-> minilogs
svclogs -.-> minilogs
hfiles -.-> minilogs
minilogs --> mirror
mirror --> reportp
class debug,launchd third
class agent,mcp,healthchk,exchanges,svclogs,hfiles,minilogs,mirror,reportp ours
```

Every file lives under `~/Library/Logs/studio-assistant`, listed in `ops/paths.py`, so one copy retrieves all of it. `STUDIO_LOG_DIR` moves the root for tests. Three writers fill it:

- **launchd** opens `NAME.log` for each agent's output in append mode and never closes it.
- **The health check** writes the latest snapshot to `health.json`, appends it to `health.jsonl`, and keeps its failure counts and cooldowns in `health_state.json`.
- **The tool server** writes one line per exchange to `exchanges/YYYY-MM-DD.jsonl`. After every answer the component posts an exchange record to the server's `/exchanges` route in a background task, with a three-second timeout; a failed post is logged and dropped, so logging never slows or silences the assistant. The record keeps the question, the answer, the route, every tool call with its arguments and duration, every model call's token counts, the failure flags, and whether the reply stayed silent. It drops the page text, which runs to thousands of words per search.

Once per calendar day the health check does the housekeeping:

- **Service logs rotate.** Each agent's log (`ollama`, `mcp`, `whisper`, `kokoro`, and `health`) over 20 MB is copied to `.1`, older copies shift to `.2` and `.3`, and the live file is truncated in place. Three generations are kept.
- **Exchange files expire.** Day files older than 90 days are deleted. Exchange records hold what was said in the apartment, and a quarter's worth is the amount kept.
- **Health history is trimmed.** `health.jsonl` keeps the last 90 days.

The rotation copies and then truncates:

*From `ops/health.py`, `rotate_log`:*

```python
def rotate_log(path: Path, over_bytes: int = ROTATE_OVER_BYTES, generations: int = ROTATE_GENERATIONS) -> bool:
    if not path.exists() or path.stat().st_size <= over_bytes:
        return False
    for index in range(generations, 1, -1):
        older = path.with_name(f"{path.name}.{index}")
        newer = path.with_name(f"{path.name}.{index - 1}")
        if newer.exists():
            newer.replace(older)
    shutil.copyfile(path, path.with_name(f"{path.name}.1"))
    with path.open("r+b") as live:
        live.truncate(0)
    return True
```

Append mode is what makes this safe. The running Ollama keeps writing at the new end of the same open file, so rotation never restarts a service and never unloads the model.

`scripts/mini.sh logs` brings the directory to the laptop in two steps:

1. `rsync -az` over SSH mirrors it into `logs/mini/`, excluding `deploy.lock`. Only changed bytes travel.
2. `python -m ops.pipeline_runs logs/mini/pipeline_runs.jsonl` asks Home Assistant over its websocket for the Assist pipeline's recent debug runs, the per-stage timings and transcripts that Home Assistant keeps only in memory and only for a handful of runs, and appends the ones it has not seen. A stopped Home Assistant makes this step print `skipped` rather than fail the pull.

The copy never passes `--delete`, so exchange files the mini has deleted after 90 days stay in `logs/mini/exchanges/` on the laptop until someone removes them. Files the mini trims or rotates, such as `health.jsonl` and the service logs, are overwritten with the mini's copy. `mini.sh logs NAME` is different: it tails `NAME.log` live on the mini, for watching a service while you ask it something.

`scripts/mini.sh report --days N` (7 by default) pulls the logs, then runs `scripts/ops_report.py --days N logs/mini`, which reads only the local mirror and never talks to the mini. The report has four blocks:

| Block | What it shows |
|---|---|
| Exchanges | Exchanges per day; median and 90th percentile of the time to the first spoken word and of the whole exchange; the mix of routes; tool calls with failures per tool; the failure flags; prompt tokens per model call; the three slowest questions; which model answered |
| Health checks | Incidents such as `mcp down 09-07T10:05 -> 09-07T10:15`; the last eight actions the machine took; how many checks ran under the maintenance flag; free memory and swap; which model was resident |
| Home Assistant pipeline runs | Median speech-to-text, agent, and text-to-speech times from Home Assistant's own clock, and any pipeline errors |
| Ollama speeds | Median prompt-reading and generation rates in tokens per second, parsed from the `print_timing` lines in `ollama.log`, which cover every request, not only the assistant's |

When a number points at something, the raw lines are in `logs/mini/` for a person or a Claude session to read.

## Run it yourself

Steps 1 to 7 run on the Mac you are sitting at and need no mini. Run everything from the repository folder.

1. Load the settings:

    ```bash
    set -a; source .env; set +a
    ```

2. Check the installed health check, then run one check by hand:

    ```bash
    scripts/services.sh status
    uv run python scripts/health_check.py --dry-run
    ```

    `status` ends with the last snapshot in one line, such as `last health snapshot 2026-09-30T06:04:27+00:00: FAILING home_assistant, searxng, vm`. The dry run probes everything now and writes nothing. On the laptop between sessions it prints lines like these (trimmed):

    ```text
    health at 2026-09-30T06:04:40+00:00
      ok   ollama          ollama 0.33.3  (0.03s)
      ok   mcp             11 tools  (0.01s)
      skip whisper         launchd agent not loaded (stopped on purpose)  (0.00s)
      ...
      FAIL vm              stopped  (0.18s)
      memory: free 62%  swap used 9349.81 MB  resident model: none (0.0 MB)
      action: would run vm_start:vm (vm is stopped)
    ```

    The `action` lines show what the policy would do on the mini. The exit code is 1 whenever any check fails.

3. Watch the installed agent's output arrive every five minutes, and press Ctrl-C to stop:

    ```bash
    scripts/services.sh logs health
    ```

4. Build the report over this machine's own log directory:

    ```bash
    uv run python scripts/ops_report.py --days 1 ~/Library/Logs/studio-assistant
    ```

    You see the four blocks from [Logs and the report](#the-report). On a laptop that has not been asked anything today the first block says `Exchanges: 0`, and the health block lists which checks have been down since when.

5. Run the deploy protocol against this checkout, with no SSH involved:

    ```bash
    uv run python -m ops.deploy status
    uv run python -m ops.deploy apply --ref HEAD~3 --dry-run
    ```

    `status` prints JSON: the commit at `head` and its subject, `last_good_ref` (null until a deploy has passed a smoke test), `maintenance`, `dirty`, and `manifest_lock_mismatches`, which is empty when the component's pins match the lock. The dry run fetches from `origin` and prints the plan for moving from `HEAD` to the older commit, such as `"plan": ["reinstall_agents", "deploy_component"]`, or an empty list when only docs and tests differ, with `"note": "dry run"`. Nothing is checked out.

6. Run the smoke test. It needs the VM up; [Home Assistant](06_home_assistant_core.md#run-it-yourself) shows how to start it and wait for the API.

    ```bash
    uv run python -m ops.smoke
    ```

    You see `smoke: pass   4.2s  'What is 12 percent of 250?' -> 'It is 30.'` and exit code 0, or `FAIL` with whatever came back and exit code 1. With a cold model the first answer can take most of the 60-second limit. `--full` adds a searched question and needs SearXNG running.

7. Rehearse the bootstrap without changing this Mac:

    ```bash
    bash scripts/bootstrap_mac.sh --repo https://github.com/seanlin2000/home_assistant.git --dry-run --skip-system
    ```

    Each step prints as `==> ...`, followed by `(dry run)` and the command it would run. The output ends with the list of what a person still does at the screen.

8. Drive the mini. Put `MINI_HOST` in `.env` and run `ssh-copy-id "$MINI_USER@$MINI_HOST"` first; `scripts/mini.sh` with no arguments prints the usage. Until the mini exists, `MINI_HOST=localhost` with a second clone of the repository at `MINI_PROJECT_DIR` stands in for it, once Remote Login is turned on for the laptop.

    ```bash
    scripts/mini.sh bootstrap --dry-run      # every step printed, nothing changed; drop the flag to run it
    scripts/mini.sh push-env
    scripts/mini.sh push-models
    scripts/mini.sh push-vm                  # then, on the mini: scripts/haos_vm.sh start
    scripts/mini.sh status
    scripts/mini.sh deploy
    scripts/mini.sh logs
    scripts/mini.sh report --days 7
    ```

    `status` prints the deploy JSON, the port list, and the last health snapshot from the mini. `deploy` prints the hash and subject it is deploying, the mini's JSON with the plan and `"tests": "passed"`, the smoke line, and `deploy: done, SHA is the mini's last good commit`.

9. When you are done on the laptop, stop the memory-heavy parts so the next benchmark pass can run:

    ```bash
    scripts/haos_vm.sh stop
    launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.studio-assistant.whisper.plist
    launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.studio-assistant.kokoro.plist
    scripts/services.sh status
    ```

    Ollama, the tool server, and the health check stay up. The next snapshot shows Whisper and Kokoro as `skip` and the VM as `FAIL`, which the laptop only records. On the mini the health check would start the VM again within five minutes.

When something goes wrong, find the symptom here:

| Symptom | Likely cause | Check |
|---|---|---|
| `scripts/services.sh status` shows a port not listening | the service stopped or crashed | `scripts/services.sh start`, then `scripts/services.sh logs NAME` |
| `MAINTENANCE FLAG SET` in `status` | a deploy died halfway, or a rollback did not answer | `scripts/mini.sh logs`, then `scripts/mini.sh rollback` or `ssh` in and `python -m ops.deploy clear-maintenance` |
| `deploy` refuses before contacting the mini | uncommitted changes, or the commit is not pushed | `git status`, `git push`, or pass `--ref` |
| `deploy` reports `applied false` | the preflight or the tests failed on the mini | the `tests` field in the printed JSON; the checkout is back on the old commit |
| The same `vm_restart:vm` action every two hours in the report | Home Assistant is broken and the cooldown is bounding the restarts | Settings, System, Logs in Home Assistant; `scripts/mini.sh logs` |
| `push-vm` fails with `Operation not permitted` | the terminal lacks Full Disk Access to UTM's sandboxed folder | System Settings, Privacy & Security, Full Disk Access |
| The Mac gets sluggish and apps get killed | the VM, the speech services, and something else heavy at once | the shutdown commands in step 9, then Activity Monitor, Memory |

## Where to look in the code

| Path | What you find there |
|---|---|
| [`scripts/mini.sh`](https://github.com/seanlin2000/home_assistant/blob/main/scripts/mini.sh) | The laptop side of every operation: `cmd_bootstrap`, `cmd_deploy` with its two refusals and the smoke-then-mark-good-or-rollback logic, `cmd_logs`, `cmd_report`, and the three push commands |
| [`ops/deploy.py`](https://github.com/seanlin2000/home_assistant/blob/main/ops/deploy.py) | `RULES` and `plan_actions`, `manifest_lock_mismatches`, `switch_to` (the checkout, preflight, tests, and actions), `with_lock`, and the five subcommands |
| [`ops/smoke.py`](https://github.com/seanlin2000/home_assistant/blob/main/ops/smoke.py) | `CALCULATOR_QUESTION`, the expected pattern, and `smoke`, which waits for the API and asks through `converse` |
| [`ops/health.py`](https://github.com/seanlin2000/home_assistant/blob/main/ops/health.py) | The probes `check_ollama` through `check_vm`, `Policy` with every threshold and cooldown, `decide_actions`, `execute`, `rotate_log`, `prune_history`, `housekeeping`, and `run_once` |
| [`scripts/health_check.py`](https://github.com/seanlin2000/home_assistant/blob/main/scripts/health_check.py) | The command launchd runs: `--dry-run`, `--no-remediate`, `--full`, `--json`, and `--last` |
| [`ops/paths.py`](https://github.com/seanlin2000/home_assistant/blob/main/ops/paths.py) | Every file under `~/Library/Logs/studio-assistant` by name, and the `STUDIO_LOG_DIR` override |
| [`ops/report.py`](https://github.com/seanlin2000/home_assistant/blob/main/ops/report.py) | `exchanges_section`, `health_section`, `pipeline_section`, `ollama_section`, and `render` |
| [`ops/pipeline_runs.py`](https://github.com/seanlin2000/home_assistant/blob/main/ops/pipeline_runs.py) | `PipelineRun`, `summarize`, which flattens Home Assistant's event list, and `pull` over the websocket |
| [`ops/ha_client.py`](https://github.com/seanlin2000/home_assistant/blob/main/ops/ha_client.py) | `HomeAssistant`, `wait_for_api`, `conversation_entity_id`, and `converse`, shared by the smoke test, the health check, the deploy, and the setup script |
| [`web_search_mcp/server.py`](https://github.com/seanlin2000/home_assistant/blob/main/web_search_mcp/server.py) and [`web_search_mcp/exchange_log.py`](https://github.com/seanlin2000/home_assistant/blob/main/web_search_mcp/exchange_log.py) | `register_operations_routes` with `/healthz` and `/exchanges`; `ExchangeLog`, the day files and their pruning |
| [`custom_components/studio_assistant/adapter.py`](https://github.com/seanlin2000/home_assistant/blob/main/custom_components/studio_assistant/adapter.py) | `post_exchange_record`, the best-effort post with its three-second timeout |
| [`scripts/services.sh`](https://github.com/seanlin2000/home_assistant/blob/main/scripts/services.sh) | `write_plist`, the `KeepAlive` and `StartInterval` branches, `install_agents`, which unloads every agent before rewriting its plist, `restart_agent`, `status`, and `logs` |
| [`scripts/bootstrap_mac.sh`](https://github.com/seanlin2000/home_assistant/blob/main/scripts/bootstrap_mac.sh) | The phases of setting up a fresh Mac: tools, the detached checkout, services and login items, the `sudo` block with `pmset`, the firewall, and the SSH drop-in, and the printed checklist of what a person still does |
| [`Brewfile`](https://github.com/seanlin2000/home_assistant/blob/main/Brewfile) | The non-Python software the bootstrap installs |
| [`tests/test_health.py`](https://github.com/seanlin2000/home_assistant/blob/main/tests/test_health.py), [`tests/test_deploy_plan.py`](https://github.com/seanlin2000/home_assistant/blob/main/tests/test_deploy_plan.py), [`tests/test_ops_report.py`](https://github.com/seanlin2000/home_assistant/blob/main/tests/test_ops_report.py) | The policy thresholds and cooldowns, rotation and pruning; the deploy rules and the manifest preflight; the report over a fixture shaped like the mini's files |
| [`docs/VERSIONS.md`](https://github.com/seanlin2000/home_assistant/blob/main/docs/VERSIONS.md) | The versions on the running machine, with a column for the mini, and the rule for refreshing them |

## Further reading

- Design doc: [`design_docs/v1/10_operations.md`](https://github.com/seanlin2000/home_assistant/blob/main/design_docs/v1/10_operations.md), which also lists the security posture and the failure modes with what each one needs from a person
- `man launchd.plist` on any Mac, for `KeepAlive`, `StartInterval`, and `ThrottleInterval`, the three keys `services.sh` writes
- [OpenSSH `sshd_config(5)`](https://man.openbsd.org/sshd_config), for `Include` and the first-match rule that lets the bootstrap's drop-in override Apple's defaults
- [Docker, host network driver](https://docs.docker.com/engine/network/drivers/host/), for the Docker Desktop note that only TCP and UDP reach a container, which is why Home Assistant lives in a UTM VM rather than Docker
- [Home Assistant REST API](https://developers.home-assistant.io/docs/api/rest/), for `POST /api/conversation/process`, the call the smoke test and `converse` make
- [Home Assistant, deprecating Core and Supervised installs](https://www.home-assistant.io/blog/2025/05/22/deprecating-core-and-supervised-installation-methods-and-32-bit-systems/), for why the OS image in a VM is the install method that keeps add-ons
