# 10. Operations and maintenance

## 1. Purpose

How the assistant is installed on, updated on, watched, and debugged from a headless Mac mini without anyone sitting at it. The rule that shapes everything here: the laptop is the place where humans and Claude work, the mini is a box on a shelf. Every operation is started from the laptop over SSH, every log ends up on the laptop, and the mini never reaches out to the laptop. Home Assistant stays in its bridged UTM VM on the mini (doc 06 §5 explains why a Docker container cannot host it on macOS: Docker Desktop passes only TCP and UDP, so the multicast traffic that device discovery for the puck and Sonos runs on never arrives). This doc is written before the hardware exists; the tooling is tested on the laptop, which plays both roles, with a second clone of the repository standing in for the mini.

## 2. Diagram

```
 laptop  ~/code/home_assistant                          Mac mini  MINI_PROJECT_DIR
 ┌───────────────────────────────────┐    ssh / rsync   ┌────────────────────────────────────────────────┐
 │ scripts/mini.sh                   │ ───────────────▶ │ scripts/bootstrap_mac.sh   (once, idempotent)  │
 │  bootstrap deploy rollback status │                  │ python -m ops.deploy apply|rollback             │
 │  logs report push-env push-models │                  │   git checkout SHA, uv sync, pytest, restart    │
 │  push-vm ssh                      │                  │   changed agents, deploy_component, last_good   │
 │ python -m ops.smoke  (asks HA one │ ── HA API ──┐    │ launchd: ollama mcp whisper kokoro  + health    │
 │   calculator question)            │             │    │   health_check.py every 300 s → health.json,    │
 │ scripts/ops_report.py             │             │    │   health.jsonl, kickstart / VM restart,         │
 │ logs/mini/   (rsync mirror,       │             │    │   log rotation, 90-day prune                    │
 │   gitignored)                     │             ▼    │ web_search_mcp :8765   POST /turns  GET /healthz │
 └───────────────────────────────────┘   HAOS VM (UTM)  │   → ~/Library/Logs/studio-assistant/turns/*.jsonl│
                              studio_assistant component ── POST /turns (trimmed record) ──▶             │
                                                        └────────────────────────────────────────────────┘
```

Six operations run over this shape. Each has its own diagram in §3.

## 3. How it works, step by step

### 3.1 First boot: the only ten minutes at a screen

A Mac out of the box has no user account, and the wizard that creates one only runs on a physical display. There is no supported way around this for a single home machine. So the mini is plugged into a TV over HDMI with any keyboard and mouse, the account is created, Wi-Fi joined, and two switches flipped in System Settings → General → Sharing: Remote Login (SSH) and, temporarily, Screen Sharing. From then on the TV is unplugged and never needed again, except for the auto-login setting in §3.2's checklist.

### 3.2 Bootstrap: everything else, from the laptop

```
 TV + keyboard (10 min)             laptop                                   Mac mini
 ┌──────────────────────┐          ┌────────────────────┐   ssh -t (key)    ┌─────────────────────────────┐
 │ create user account  │          │ mini.sh bootstrap  │ ────────────────▶ │ bootstrap_mac.sh            │
 │ join Wi-Fi           │          │  scp bootstrap +   │                   │  brew bundle (uv git ollama │
 │ Remote Login: on     │──then──▶ │  Brewfile          │                   │   docker utm ...)           │
 │ Screen Sharing: on   │          └────────────────────┘                   │  git clone repo             │
 └──────────────────────┘                                                   │  dev_setup.sh  (.venv)      │
                                                                            │  services.sh install        │
                                                                            │  searxng.sh up              │
                                                                            │  pmset, firewall, sshd      │
                                                                            │   drop-in (keys only)       │
                                                                            │  prints GUI checklist       │
                                                                            └─────────────────────────────┘
```

`scripts/mini.sh bootstrap` copies `scripts/bootstrap_mac.sh` and the `Brewfile` to the mini and runs the script there in an interactive SSH session, because a few steps ask for the administrator password. Every step checks whether it is already done before doing it, so the script can be re-run after a failure. In order:

1. Xcode command line tools (`git` needs them; if missing, the script says so and stops, because the installer is a GUI dialog).
2. Homebrew, then `brew bundle` from the `Brewfile`: uv, git, ollama, shfmt, shellcheck, espeak-ng, and the Docker Desktop and UTM apps.
3. `uv python install 3.12`, clone the repository (or fetch it if present) and check out the default branch as a detached commit. The mini never commits or pushes; it only ever pulls.
4. `scripts/dev_setup.sh` builds the virtual environment from the lock file.
5. `scripts/services.sh install` writes the five launchd agents (the four services plus the health check) and starts them.
6. Docker Desktop is opened and, once it answers, `scripts/searxng.sh up` starts the search aggregator. Docker and UTM are registered as login items so they come back after a reboot.
7. System settings that need `sudo`: power management (never sleep, restart after a power failure, wake on network), the application firewall on with the four things that listen on the LAN allowed through it (Ollama, the virtual environment's Python, Docker, UTM), Remote Login restricted to the one user, and the SSH hardening drop-in described in §3.9. The hardening step is skipped, with a loud message, unless a public key is already installed and the current session logged in with it, so the script can never lock its own operator out.
8. A printed checklist of the steps only a human at the GUI can finish: automatic login (which requires FileVault off), the first-launch approval dialogs of Docker and UTM over Screen Sharing, DHCP reservations for the mini and the VM on the router, the HDMI dummy plug, macOS automatic updates off, and then the three push commands below.

### 3.3 Push what cannot come from git

```
 laptop                                                  Mac mini
 .env ────────────── mini.sh push-env  (scp) ──────────▶ MINI_PROJECT_DIR/.env  (chmod 600)
 ~/.ollama/models ── mini.sh push-models (rsync) ──────▶ ~/.ollama/models   same digest as benchmarked
 ~/Library/.../Home Assistant.utm
   (local VM stopped) ── mini.sh push-vm (rsync) ──────▶ UTM documents dir ── haos_vm.sh start ──▶ VM up,
                                                                                            3 GB, bridged
```

Three things are deliberately not in the repository. Secrets live in `.env` and are copied once. Models are several gigabytes and content-addressed, so copying the laptop's blobs guarantees the mini runs the exact digest the benchmark scored, where a fresh `ollama pull` might fetch a newer build under the same tag. The Home Assistant VM is a single folder in UTM's documents directory that carries the whole configured Home Assistant, add-ons and all; copying it avoids re-running the setup script, and `push-vm` refuses to run while the laptop's copy of the VM is running, because two VMs with the same network address cannot coexist. The VM is given 3 GB on the mini rather than the laptop's 4 GB, which the memory budget in doc 08 §4 relies on.

### 3.4 Every assistant turn writes one record

```
 puck / app ──▶ HA VM (192.168.1.x)                       Mac mini (same box, LAN address)
              ┌──────────────────────────────┐            ┌──────────────────────────────────────────┐
              │ Assist pipeline              │  Ollama    │ Ollama :11434                            │
              │  ▶ studio_assistant component│◀──────────▶│ tool server :8765  /mcp  (search, calc)  │
              │     answer streams to TTS    │  MCP       │                    /turns  POST ─┐       │
              │     on Done: build TurnRecord│───────────▶│                                   ▼       │
              │     (user text, answer, route│  POST      │ ~/Library/Logs/studio-assistant/turns/    │
              │      tool names+args+seconds,│  fire-and- │   2026-09-07.jsonl   (append one line)    │
              │      token stats, timings;   │  forget    │   pruned after 90 days                    │
              │      no page text)           │            └──────────────────────────────────────────┘
              └──────────────────────────────┘
                A failed post is logged and ignored; the spoken answer is never delayed.
```

The agent loop already produces a `Transcript` for every turn (doc 04); the benchmark scores those objects. In production the component turns the transcript into a `TurnRecord`, a trimmed copy that keeps what a debugging session needs and drops what it does not: the user's words, the final answer, the route decision, every tool call's name, arguments, duration, error, and the size of its result, every model call's token counts and timings, and the flags the benchmark gates on (truncated, round cap hit, empty retries, malformed calls, error). The full text of fetched web pages is dropped; it is thousands of words per search and can be re-fetched. The record is posted to a plain HTTP route on the tool server, which the component already talks to for every search, and the server appends it as one line to a file named by the day. The post runs as a background task after the answer has been spoken, with a short timeout, and any failure is logged and swallowed: logging must never make the assistant slower or quieter.

Why the tool server rather than a file inside the VM: it puts every log on the Mac's disk under one directory, so a single copy operation retrieves them all, and it avoids reaching into the VM over the SMB share that once hung (doc 08 §11).

### 3.5 Health check and self-healing

```
 launchd  StartInterval 300
    │
    ▼
 health_check.py ── probes ──▶ ollama /api/version      ┐
                               tool server /healthz     │  results + memory (free %, swap,
                               whisper, kokoro (TCP)    ├─ resident model) ──▶ health.json (latest)
                               searxng :8080            │                      health.jsonl (history)
                               HA /api/ (200 or 401)    │
                               utmctl status            ┘
    │
    ├─ agent down 2 checks in a row ──▶ launchctl kickstart -k  (30 min cooldown)
    ├─ searxng down 2 checks ─────────▶ searxng.sh up
    ├─ VM stopped ────────────────────▶ utmctl start
    ├─ HA down 5 checks (25 min) ─────▶ VM stop + start        (2 h cooldown)
    ├─ maintenance flag present ──────▶ do nothing (a deploy is running)
    └─ once a day ────────────────────▶ rotate logs > 20 MB, prune turns and history > 90 days
```

A fifth launchd agent runs `scripts/health_check.py` every five minutes. It probes each part of the stack the cheapest way that proves the part is really ours: Ollama's version endpoint, the tool server's `/healthz` route (which must list the tool names the agent depends on, the same identity check the benchmark makes before a run), a TCP connect to Whisper and Kokoro, SearXNG's HTTP port (the query probe that hits upstream engines is reserved for `--full`, so the loop does not fire 288 searches a day), Home Assistant's `/api/` (a 401 without a token is a healthy answer), and the VM's state from `utmctl`. Each snapshot also records the machine's free memory percentage, swap in use, and the size of the model Ollama has resident, because memory creep is the failure this machine is most likely to have.

What it may do on its own is a policy table, not code scattered through the script, and it is deliberately staged:

| Condition | Action | Threshold | Cooldown |
|---|---|---|---|
| A launchd service does not answer | `launchctl kickstart -k` that agent | 2 consecutive checks | 30 min per service |
| SearXNG does not answer | `scripts/searxng.sh up` | 2 consecutive checks | 30 min |
| VM reported stopped | `utmctl start` | 1 check | 30 min |
| HA API down while VM runs | `utmctl stop` then `start` | 5 consecutive checks (25 min) | 2 h |
| Maintenance flag present | nothing | | |

Home Assistant legitimately disappears for minutes during its own updates and add-on installs, which is why the VM threshold is long. The maintenance flag is a file the deploy creates before it starts changing things and removes when the smoke test passes, so the health check never fights a deploy. Every action is recorded in the snapshot, so the report can show what the machine did to itself.

### 3.6 Log rotation and retention

launchd opens each service's log file in append mode and never closes it. The health check, once per calendar day, copies any log over 20 MB to a numbered generation, keeps three generations, and truncates the live file in place. Because the file is open in append mode, the service keeps writing at the new end without noticing; this is why in-place truncation was chosen over macOS's own `newsyslog`, whose rename-based rotation would leave a running Ollama writing to the renamed file until it restarted, and restarting Ollama means reloading the model. The same daily pass deletes turn files older than 90 days and trims the health history to 90 days. The retention period is a decision, not a default: turn records contain what was said in the apartment, and the user chose to keep a quarter's worth for debugging.

### 3.7 Retrieving the logs and reading them on the laptop

```
 laptop                                                     Mac mini
 ┌───────────────────────────────┐    ssh + rsync -az       ┌──────────────────────────────────────┐
 │ mini.sh logs                  │ ───── pull ────────────▶ │ ~/Library/Logs/studio-assistant/     │
 │   logs/mini/   (gitignored)   │ ◀──── only changed ───── │   ollama.log mcp.log whisper.log     │
 │     ollama.log ... turns/ ... │       bytes come back    │   kokoro.log  turns/*.jsonl          │
 │     health.json health.jsonl  │                          │   health.json health.jsonl           │
 │                               │    HA API (token)        │   last_good_ref                      │
 │   + pipeline_runs.jsonl       │ ◀──── recent runs ────── │ HA VM: assist pipeline debug store   │
 │                               │                          └──────────────────────────────────────┘
 │ mini.sh report --days 7       │
 │   ops_report.py reads         │   turns/day, median time to first word, p90 total, route mix,
 │   logs/mini/ and prints ───▶  │   tool errors, health incidents, memory trend, Ollama tok/s
 └───────────────────────────────┘
   Nothing is deleted on the laptop; debugging happens from these files, not on the mini.
```

`scripts/mini.sh logs` mirrors the mini's log directory into `logs/mini/` on the laptop with rsync over SSH, which transfers only the bytes that changed since the last pull, so after the first run it takes a second. It also asks Home Assistant's API for its recent pipeline runs (the per-stage timings and transcripts that Home Assistant keeps only in memory and only for a handful of runs) and appends them to a file, which is what makes that view durable. The laptop copy is never pruned automatically, so the laptop can hold more history than the mini. The folder is git-ignored.

`scripts/mini.sh report --days N` pulls and then renders a summary from the local copy: turns per day, median time to first spoken word, the slowest answers, the mix of routes, tool calls and failures by tool, the benchmark-style failure flags, health incidents with their durations and the actions taken, the memory trend, and Ollama's prompt-reading and generation speeds parsed both from the turn records (assistant traffic only) and from Ollama's own log (all traffic). When the summary points at something, the raw lines are in `logs/mini/` for a person or a Claude session to read. No session on the mini is needed for any of this.

### 3.8 Deploy and rollback

```
 laptop                                   Mac mini
 git push origin main                     (nothing happens yet)
        │
 mini.sh deploy ── ssh ──▶ ops.deploy apply --ref <sha>
   refuses if tree dirty        │ touch maintenance flag        (health check stands down)
   or HEAD not pushed           │ git fetch; checkout <sha>
                                │ uv sync --frozen  (if lock changed)
                                │ pytest -q         (fail ──▶ abort, nothing restarted)
                                │ git diff old..new ──▶ plan:
                                │    web_search_mcp/ assistant_core/ ──▶ restart mcp
                                │    custom_components/ ──▶ deploy_component.py (SMB) + HA restart
                                │    scripts/services.sh ──▶ reinstall agents
                                │    docker/searxng/ ──▶ searxng restart
        ◀───────────────────────┘
 ops.smoke: ask HA "What is 12 percent of 250?" ── expect "30" within 60 s
        │
   pass ──▶ ssh: mark-good <sha>; clear maintenance flag         done
   fail ──▶ ssh: ops.deploy rollback  (checkout last_good_ref, same plan in reverse)
                 ──▶ smoke again ──▶ pass: clear flag, exit 1 with the failure printed
                                 ──▶ fail: flag left set, exit 2, "restore by hand"
```

Pushing to the repository changes nothing on the mini. Going live is a separate, deliberate act: `scripts/mini.sh deploy` from the laptop. It refuses to start if the laptop's working tree has uncommitted changes or its commit has not been pushed, because the mini can only pull what the remote has. On the mini, `ops.deploy apply` raises the maintenance flag, fetches, checks out the exact commit, syncs the environment if the lock file changed, and runs the test suite; a failing suite aborts before anything is restarted. It then diffs the old and new commits and derives the smallest set of actions from a rules table:

| Changed path | Action |
|---|---|
| `uv.lock`, `pyproject.toml` | sync the environment, restart every Python service |
| `web_search_mcp/`, `calculator_mcp/`, `assistant_core/` | restart the tool server |
| `custom_components/`, `assistant_core/` | copy the component into the VM and restart Home Assistant |
| `voice/` | restart Kokoro |
| `scripts/services.sh` | rewrite and reload all agents |
| `docker/searxng/` | restart SearXNG |
| `ops/`, docs, benchmark, tests | nothing |

Back on the laptop, `ops.smoke` asks Home Assistant one calculator question through the same conversation API the voice pipeline uses and expects the right number within a minute; this exercises Home Assistant, the component, Ollama, and the tool server in one call without touching the web. On success the commit is recorded as the last known good and the flag is cleared. On failure the mini is told to roll back: it checks out the last good commit and applies the reverse plan, the smoke test runs again, and the command exits non-zero with the failure printed. If even the rollback does not restore service the flag is left in place, self-healing stays off, and the command says so, because at that point a person should look before the machine restarts anything.

The component copy still travels over the Samba share into the VM (doc 08 §11), now with the previous tree renamed aside first and restored if the copy fails halfway. The manifest-versus-lock check that doc 09 §4 promised lives in the deploy's preflight.

### 3.9 Security posture

The mini is reachable only on the home network. No router port is forwarded, and no relay or tunnel is installed; if remote access is ever wanted, an authenticated tunnel such as Tailscale is the path, never an open port. On the machine:

- SSH accepts keys only. The bootstrap writes a drop-in file into `/etc/ssh/sshd_config.d/` that turns off password and keyboard-interactive login, forbids root, and allows only the one user. sshd applies the first matching setting it reads and reads drop-ins before its main file, so the drop-in wins over Apple's defaults. The file is validated with `sshd -t` before sshd is reloaded.
- Remote Login is restricted to the one account through the `com.apple.access_ssh` group, which is what the Sharing pane's "only these users" setting edits.
- The application firewall is on. The processes that must accept LAN connections (Ollama, the virtual environment's interpreter for the Wyoming and tool servers, Docker, UTM) are allowed explicitly, because a headless machine cannot answer the per-application dialog macOS would otherwise show.
- Screen Sharing is turned off after bootstrap and reached, when needed, through an SSH tunnel rather than left open.
- FileVault stays off. This is a trade: a headless machine must log in by itself after a power cut for the user agents to start, and FileVault would wait at a password prompt with no one to type it. The data at stake is the assistant's configuration and its turn logs, in an apartment.
- macOS automatic updates are off; updates are applied deliberately, as doc 08 §6 says, after the monthly Home Assistant update.

## 4. Packages and tools, and what each does for the business logic

| Package or tool | Role in this subsystem |
|---|---|
| `ops` (ours) | The Python behind every operation: `ha_client` (the Home Assistant REST and websocket helper, moved out of the setup script so the health check, smoke test, and deploy share it), `health` (probes, policy, housekeeping), `deploy` (plan from a diff, apply, rollback, last-good bookkeeping), `smoke` (one question through the conversation API), `report` (renders `logs/mini/` into a summary), `paths` (the one place that knows where files live). |
| `assistant_core.turn_record` (ours) | The trimmed per-turn record and the function that builds it from a `Transcript`. Pure pydantic so it imports inside Home Assistant's own Python, where the component runs. |
| `web_search_mcp` routes | Two plain HTTP routes added to the MCP server: `POST /turns` appends a record, `GET /healthz` proves the server is ours by listing its tools. The MCP library exposes custom routes for exactly this kind of health and admin endpoint. |
| `httpx`, `pydantic` | Already project dependencies: HTTP probes and posts, typed records that serialise to JSON lines. |
| launchd | macOS's service manager. The four services use `KeepAlive` so a crash restarts them; the health check uses `StartInterval` so it runs on a schedule and exits. `launchctl kickstart -k` is how one agent is restarted by name. |
| `utmctl` | UTM's command line: start, stop, and query the VM. The only thing that touches the VM besides the SMB copy. |
| `rsync` over `ssh` | Log retrieval and the model and VM copies. Transfers only changed bytes; authentication is the same key as every other operation. |
| `pmset`, `socketfilterfw`, `dseditgroup`, `sshd_config.d` | Apple's tools for power, firewall, the SSH users group, and SSH settings. Used once, by the bootstrap, and documented in §3.9 because they are the security posture. |
| `brew bundle` | Installs the non-Python software from one `Brewfile`, so the list of what the mini needs is a file in the repository. |
| `git` | Deploys are a fetch and a detached checkout of a commit hash; rollback is the same to the previous hash. The mini has no working branch and never pushes. |

## 5. Configuration we control

| Setting | Where | Value |
|---|---|---|
| `MINI_HOST`, `MINI_USER`, `MINI_PROJECT_DIR` | `.env` on the laptop | The mini's address (a DHCP reservation), the login user, the clone path on the mini. During laptop testing: `localhost`, the laptop user, a second clone. |
| `WEB_SEARCH_TURNS_DIR` | mcp launchd plist, written by `services.sh` | `~/Library/Logs/studio-assistant/turns` |
| `STUDIO_LOG_DIR` | environment, optional | Overrides the log directory, for tests |
| Health interval | `services.sh` | 300 s |
| Health thresholds and cooldowns | `ops/health.py` policy | The table in §3.5 |
| Log rotation | `ops/health.py` | 20 MB, 3 generations |
| Retention | `ops/health.py` | 90 days for turns and health history |
| Smoke question | `ops/smoke.py` | "What is 12 percent of 250?" expecting "30", 60 s |
| VM memory on the mini | `HAOS_VM_MEMORY_MB` / UTM config | 3072 MB |
| Log directory layout on the mini | | `ollama.log mcp.log whisper.log kokoro.log health.log`, `turns/YYYY-MM-DD.jsonl`, `health.json`, `health.jsonl`, `last_good_ref`, `maintenance` (flag), `deploy.lock` |
| Mirror on the laptop | | `logs/mini/` with the same layout plus `pipeline_runs.jsonl`; git-ignored |

## 6. Failure modes

- **A deploy dies halfway.** The maintenance flag stays, self-healing is off, and nothing tells you unless you look. `mini.sh status` prints the flag's age in red; `mini.sh rollback` or `ops.deploy clear-maintenance` resolves it.
- **Deploy during a Home Assistant add-on install.** The SMB copy can hang (doc 08 §11). The deploy refuses to start while Home Assistant reports the Supervisor busy, and the copy has a timeout after which the deploy fails cleanly instead of hanging.
- **Environment sync under a running interpreter.** `uv sync` replaces packages while `ops.deploy` itself is running from that environment. All of the deploy's imports happen at start and every action is a subprocess, so the running process is unaffected; the restarted services pick up the new packages.
- **Health check and deploy fighting.** Prevented by the maintenance flag. The residual risk is a health run that started just before the flag was raised; its actions are limited to restarts, which the deploy's restarts supersede.
- **VM restart loop.** If Home Assistant is genuinely broken, the health check would restart the VM every two hours forever. The cooldown bounds the damage, the report shows the pattern, and the fix is a person.
- **Firewall prompt on a headless machine.** A new binary that listens on the LAN triggers a dialog nobody can click. The bootstrap allow-lists the known binaries; a new one (for example a new Python after an interpreter upgrade) needs the same `socketfilterfw --add`, which the deploy's environment-sync action re-applies.
- **Disk fills with logs.** Rotation and pruning run daily; the health snapshot records free disk and the report flags under 10 GB.
- **Both machines run the VM.** Same network identity twice. `push-vm` refuses while the laptop's VM runs, and after the move the laptop's VM is deleted or left stopped.
- **The laptop is asleep or away.** Nothing on the mini depends on the laptop. Logs accumulate on the mini for 90 days and are pulled whenever the laptop next asks.
- **Lost SSH key.** With passwords off, a lost laptop key means Screen Sharing over the LAN with the account password, or the TV again. Keep a second key on a USB stick or a second machine.

## 7. Concepts for newcomers

- **SSH keys versus passwords.** A key pair is a secret file on the laptop and a matching public file on the mini. The mini can check that the laptop holds the secret without the secret ever crossing the network, and nothing can be guessed. Turning passwords off means the only way in is holding that file.
- **launchd `KeepAlive` versus `StartInterval`.** `KeepAlive` means "this program should always be running; restart it if it exits", right for servers. `StartInterval` means "run this program every N seconds and let it exit", right for a check.
- **Append mode and truncation.** When a process opens a file for appending, every write goes to the current end of the file, wherever that is. Cutting the file to zero length underneath it is therefore safe: the next write lands at the new end. Renaming the file is not safe in the same way, because the process keeps writing to the renamed file.
- **sshd first match.** OpenSSH reads its configuration top to bottom and the first setting for a keyword wins. Apple's configuration includes the drop-in directory near the top, so a drop-in named to sort first overrides everything below it.
- **FileVault and auto-login.** FileVault encrypts the disk and asks for a password before the operating system even starts. A headless machine has nobody to type it, so it would sit at that prompt after every power cut. Auto-login requires FileVault off.
- **HDMI dummy plug.** A small connector that pretends to be a monitor. Without a display macOS drives the desktop at a low resolution with graphics acceleration off, which makes Screen Sharing sluggish; with the plug it behaves as if a monitor were attached.
- **Multicast and why Docker cannot host Home Assistant on a Mac.** Device discovery on a home network works by sending a packet to a group address that every interested device listens to (mDNS for `.local` names and the puck, SSDP for Sonos). Docker on macOS runs containers inside a hidden Linux VM and forwards only ordinary point-to-point TCP and UDP into it, so those group packets never arrive. A bridged UTM VM, by contrast, is a real device on the network with its own address, and receives them.
- **rsync.** A copy tool that compares source and destination and sends only the differences. Over SSH it is the standard way to mirror a directory between two machines.
- **Detached checkout and the last good commit.** The mini checks out a specific commit hash rather than a branch, so what is running is unambiguous, and the hash that last passed the smoke test is written to a file. Rolling back is checking that hash out again.
- **Smoke test.** The smallest end-to-end exercise that proves the system is alive: here, one question through the same path a spoken question takes.

## 8. Sources

- Apple, `launchd.plist(5)`: `KeepAlive`, `StartInterval`, `ThrottleInterval`.
- Apple, `socketfilterfw` (Application Firewall command line), `pmset(1)`, `dseditgroup(8)`, `fdesetup(8)`.
- OpenSSH, `sshd_config(5)`: `Include`, first-match semantics, `PasswordAuthentication`, `KbdInteractiveAuthentication`, `AllowUsers`.
- Docker, "Host network driver", Docker Desktop section: layer 4 only, TCP and UDP. https://docs.docker.com/engine/network/drivers/host/
- Music Assistant installation notes on host networking and player discovery. https://www.music-assistant.io/installation/
- Home Assistant, "Deprecating Core and Supervised installation methods" (2025-05-22). https://www.home-assistant.io/blog/2025/05/22/deprecating-core-and-supervised-installation-methods-and-32-bit-systems/
- UTM, `utmctl` command line reference.
- Home Assistant REST API, `POST /api/conversation/process`; websocket `assist_pipeline/pipeline_debug/list` and `get`.
- Headless Mac mini setup guides consulted for the FileVault, auto-login, and dummy-plug points (Astropad, HomeTechOps, agileguy, 2026).
