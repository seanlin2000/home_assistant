# 10. Operations

Status: designed 2026-10-08

## 1. Purpose

How v2's new parts are installed, updated and watched on a Mac that nobody sits at. The rule from v1 still shapes everything: the laptop is where you and Claude work, the Mac is a box on a shelf, and every operation is started from the laptop over SSH.

v1/10 still applies to everything this doc does not change:
- the first boot and the bootstrap;
- the SSH and firewall settings;
- log rotation;
- pulling the logs to the laptop and the weekly report;
- deploy and rollback.

What v2 changes:
- **Services.** llama-server and the harness become launchd services, and Ollama's service goes away (3.1).
- **API keys.** Each key is made once, at install (3.2).
- **Deploys.** The list that decides what a deploy restarts gains the new parts, and every deploy that restarts the model warms it up before the smoke test (3.3).
- **Health check.** It checks the new parts and records how often a request had to read its whole prompt (3.4).
- **Exchange log.** The harness writes it instead of the tool server (3.5).
- **Memory notes.** They are backed up to the laptop, outside any git repository (3.6).
- **Models.** They are GGUF files, copied and checked by their hash (3.7).
- **Versions.** llama.cpp is held at a known version (3.8).
- **Moving to a new Mac.** One command on each Mac, run at its own keyboard, with nothing sent over SSH (3.10).

## 2. Diagram

```
 A DEPLOY, started from the laptop

 ╭────────────────────╮      ╭────────────────────╮      ╭────────────────────╮      ╭────────────────────╮      ╭────────────────────╮
 │   changed files    │      │  select restarts   │      │      restart       │      │      warm up       │      │     smoke test     │
 │ since last deploy  │─────▶│ by folder changed  │─────▶│ llama, harness...  │─────▶│  both slots read   │─────▶│ a question via HA  │
 ╰────────────────────╯      ╰────────────────────╯      ╰────────────────────╯      ╰────────────────────╯      ╰────────────────────╯

 THE HEALTH CHECK, every five minutes

 ╭────────────────────╮      ╭────────────────────╮      ╭────────────────────╮      ╭────────────────────╮      ╭════════════════════╮
 │  check each part   │      │       record       │      │   count failures   │      │  restart the part  │      │    health.json     │
 │ llama, harness...  │─────▶│ RAM, slow requests │─────▶│ since last success │─────▶│  after 2 failures  │─────▶│    the snapshot    │
 ╰────────────────────╯      ╰────────────────────╯      ╰────────────────────╯      ╰────────────────────╯      ╰════════════════════╯
```

A deploy restarts only the parts whose files changed. A restart of llama-server or the harness is followed by a warm-up, so the first real question is not the one that pays for reading the stable prompt. The health check keeps one count per part of the checks it has failed since it last answered, and restarts the part when the count reaches two.

## 3. How it works, step by step

### 3.1 The services launchd runs

`scripts/services.sh install` writes one launchd agent per service, as in v1. These are the agents in v2:

| Agent | Program | Runs | Log |
|---|---|---|---|
| `llama` | `uv run serving launch`, which checks the model's hash and replaces itself with `llama-server` (doc 02 §3.5) | Always (`KeepAlive`) | `llama.log` |
| `harness` | `.venv/bin/python -m assistant_service` | Always | `harness.log` |
| `mcp` | The tool server, as in v1, on `127.0.0.1` from M2 | Always | `mcp.log` |
| `whisper`, `kokoro` | As in v1 | Always | As in v1 |
| `health` | `scripts/health_check.py` | Every 300 seconds (`StartInterval`) | `health.log` |
| `ollama` | Removed: `services.sh install` unloads it and deletes its plist | Never | |

**Start order.** launchd starts agents in no particular order, so each one tolerates the others being missing:
- **The harness waits for llama-server.** When the harness starts, it waits for llama-server's `/health` to report the model loaded, then warms both slots (doc 04 §3.6). Each warm-up request sends a slot its stable prompt once, so the cache holds it.
- **The harness notices when llama-server comes back.** It asks llama-server's `/health` once a minute, on the same timer that ends quiet conversations (doc 04 §3.5). If llama-server was unreachable and is back, the harness warms both slots again. A restart of llama-server alone, by the health check or by hand, therefore never leaves the first question to read the stable prompt.
- **Questions wait for the warm-up.** A question that arrives during a warm-up goes first (doc 04 §3.7).

### 3.2 API keys

llama-server and the harness each require a key:
- **Where.** The keys live in `~/Library/Application Support/studio-assistant/`, as `llama-server.key` and `harness.key`. Only your user can read them (`chmod 600`).
- **When they are made.** `scripts/services.sh install` makes each key once, if its file is missing, with `openssl rand -hex 32`. A later install keeps the existing key.
- **Who reads them.** The launcher passes the llama-server key file's path to `llama-server --api-key-file`, and the harness reads both files. The keys never appear on a command line, in a launchd file, or in the repository.
- **Home Assistant's copy.** The harness key also goes into the component's options in Home Assistant. `scripts/ha_setup.py` copies it there, as it sets the component's other options.
- **Changing a key.** Delete its file, run `services.sh install`, and, for the harness key, run `ha_setup.py` again.

### 3.3 A deploy

A deploy runs as in v1/10 §3.8:
1. raise the maintenance flag;
2. check out the commit;
3. run the tests;
4. restart what changed;
5. run the smoke test from the laptop;
6. roll back if it fails.

What changes is the list that maps each changed folder to what must restart, the warm-up before the smoke test, and the smoke test's reach.

`ops/deploy.py` compares the old and new commits, finds every changed file, and looks each one up in this list. The deploy then does every action at least one changed file asked for, each once:

| A change to | Restarts | Why |
|---|---|---|
| `config/serving.toml`, or the launcher's code | llama-server, then warms both slots | The model, its flags, or its file changed (doc 02 §3.5) |
| `assistant_service/`, `assistant_core/`, `config/tools.toml` | The harness, then warms both slots | The loop, the prompt, or the tools' tiers changed. A new prompt means a new stable prefix, so the slots are warmed with it |
| `web_search_mcp/`, `calculator_mcp/`, `weather_mcp/`, `wikipedia_mcp/`, `utils/` | The tool server | As in v1 |
| The files of `assistant_core/` that the component vendors (the event and transcript models) | Copies the component into the VM and restarts Home Assistant | The component and the harness must agree on the events they exchange |
| `custom_components/` | Copies the component into the VM and restarts Home Assistant | As in v1 |
| `uv.lock`, `pyproject.toml` | Syncs the environment and restarts every Python service, the harness included | As in v1 |
| `voice/` | Kokoro | As in v1 |
| `scripts/services.sh` | Rewrites and reloads every agent | As in v1 |
| `docker/searxng/` | SearXNG | As in v1 |
| `Brewfile` | Nothing | Programs are upgraded by hand (3.8) |
| `ops/`, docs, the benchmark, tests | Nothing | As in v1 |

In v1, every change to `assistant_core/` copied the component into the VM and restarted Home Assistant, because the loop ran there. In v2 the loop runs in the harness, so most changes to it restart only the harness, which takes seconds instead of a minute.

The deploy waits up to two minutes for llama-server's `/health` after restarting it, since loading the model takes time; the larger model planned for the new Mac takes longer than E4B. The deploy then waits for the harness to report its warm-up done.

The smoke test is still v1's calculator question, asked through Home Assistant. In v2 it passes through every new part: Home Assistant, the thin client, the harness, llama-server and the tool server.

### 3.4 The health check

The health check is still one launchd agent that runs every five minutes, checks each part, records the result, and restarts what has failed. It does five things in order.

**1. Check each part.** The cheapest probe that proves the part is really ours:

| Part | Probe | Healthy when |
|---|---|---|
| llama-server | `GET /health` | 200. A 503 means the model is still loading: recorded, but not counted as a failure for the first five minutes after a start |
| llama-server's slots | `GET /slots`, with its key | Recorded, not counted as a failure: the slots working on a request, with the request's id and the tokens written so far. A slot that is still on the same request with no new token at the next check is stuck (step 4) |
| The harness | `GET /health`, with its key | 200. Its answer also says whether it can reach llama-server and the tool server |
| The tool server | `GET /healthz`, as in v1 | It lists the tools the harness depends on |
| Whisper, Kokoro, Home Assistant, the VM | As in v1 | As in v1 |
| SearXNG | `GET /`, as in v1; with `--full`, one real search of the web engines | The status is below 500; with `--full`, at least one web engine answers. The detail names the engines that answered and those that did not, with SearXNG's reason, and says "no fallback" when only one answered |
| Ollama | As in v1 | Until M2, then removed |

**2. Record RAM use and slow requests.** Each snapshot records the Mac's free memory and swap, as in v1. Two figures change:
- **Model memory.** It is llama-server's resident memory, instead of the size Ollama reported for its loaded model.
- **Slow requests (new).** The number of llama.cpp requests in the last five minutes that read more than 600 prompt tokens fresh. The count comes from the exchange log (3.5), which records each request's fresh and cached tokens. M1's target is that nine first requests out of ten read at most 600 (v2/00 §9), so a rising count means the prompt cache is being lost, for example after a llama.cpp upgrade. The check only reports it; restarting would not help.

**3. Count failures.** Each part has its own count of the checks it has failed since it last answered. A failed check adds one; one successful check sets it back to zero. The counts are kept between runs in `health_state.json`, as in v1.

**4. Restart the part.** What the health check may do on its own:

| When | It does | And then waits at least |
|---|---|---|
| A service has failed 2 checks since it last answered: llama-server, the harness, the tool server, Whisper or Kokoro | Restarts that service with `launchctl kickstart -k` | 30 minutes before restarting the same service again |
| A llama-server slot is stuck: on the same request, with no new token, at two checks in a row | Restarts llama-server with `launchctl kickstart -k` | The same 30 minutes as any llama-server restart |
| It is between 4 and 6 a.m. local time, nobody has talked to the assistant for 10 minutes, and llama-server has not been restarted today | Restarts llama-server | Until the next day; any restart that day counts, and a night busy through the whole window goes without |
| SearXNG has failed 2 checks | `scripts/searxng.sh up` | 30 minutes |
| The VM is stopped | Starts it | 30 minutes |
| Home Assistant has failed 5 checks while the VM runs | Stops and starts the VM | 2 hours |
| A deploy is running (the maintenance flag is set) | Nothing | |
| The check was installed with `--leave-vm`, as on the laptop | Everything above except starting or restarting the VM, which is stopped there on purpose | |

These are v1's rules with the two new services added, plus two for llama-server that its `/health` cannot see. A slot can stay busy and silent while `/health` answers 200, so the failure count never rises: on 2026-10-20 two requests pinned to one slot hung it until the client gave up, and answers stayed worse until a restart. The daily restart clears damage of that kind that builds up too slowly for a check to notice. The waits stop a part that is truly broken from being restarted every five minutes; the report shows the pattern, and a person decides. When llama-server is restarted, the harness warms it again by itself (3.1).

**5. Write the snapshot.** The results, the counts, and every restart go into `health.json` (the latest) and `health.jsonl` (the history), as in v1.

### 3.5 The exchange log moves to the harness

In v1 the component built a record of each exchange and posted it to the tool server, which appended it to the day's file. In v2 the harness builds the record itself, because it runs the loop, and appends it to the same file:
- **Where.** `~/Library/Logs/studio-assistant/exchanges/YYYY-MM-DD.jsonl`. No HTTP is involved, and Home Assistant sends nothing.
- **What it gains.** For each llama.cpp request, the record adds:
  - its slot;
  - its prompt tokens for each part of the prompt;
  - the tokens read fresh and from the cache, from llama-server's `timings`;
  - the exchange's trust mark (doc 12 §3.2).
- **What it keeps out.** As in v1, the record leaves out the text of fetched pages.
- **Old route.** The tool server's `POST /exchanges` route is removed at M2.
- **Retention.** The log stays 90 days and is rotated, pulled to the laptop and reported on as in v1.

### 3.6 Backing up the memory notes

The memory notes (doc 11) are the only data on the Mac that cannot be rebuilt: the index can be rebuilt from them, and everything else comes from git or the laptop.

They are never put under git, because the repository is public. They are copied to the laptop instead:
- **The command.** `scripts/mini.sh notes` pulls the notes folder over SSH with rsync into `~/Library/Application Support/studio-assistant/notes-backup/` on the laptop. That folder is outside every repository. `mini.sh logs` runs it too, so the notes are copied whenever the logs are.
- **Deletions.** Deleting a note in Obsidian is how you curate, so the copy follows deletions: rsync runs with `--delete`. It also moves each deleted or changed file into a dated folder beside the copy (`--backup-dir`), so a note deleted by mistake can be recovered.
- **Retention.** Those dated folders are removed after 30 days, so a note you deleted is gone from the laptop a month later too.
- **Not included.** The harness's SQLite file holds only trust marks for conversations still in progress and is not backed up.

How you open the notes in Obsidian when the Mac has no screen is decided in doc 11.

### 3.7 Models are GGUF files

In v1, `mini.sh push-models` copied Ollama's blobs by digest. In v2 a model is one GGUF file, named with its source, revision and SHA-256 in `config/serving.toml` (doc 02 §3.5). The model commands:
- **Download.** `uv run serving fetch <model>` downloads the file from Hugging Face at the pinned revision, into `~/models/gguf/`, and checks its hash.
- **Copy to the Mac.** `mini.sh push-models` copies every file that `config/serving.toml` names to the same path on the Mac with rsync, then checks each hash there.
- **Check at start.** The launcher checks the hash again every time llama-server starts. A file that changed on disk is never served.

### 3.8 Versions

llama.cpp comes from homebrew-core and is held at the version the benchmark measured:
- **Holding it.** `brew pin llama.cpp` stops `brew upgrade` from moving it.
- **Recording it.** `docs/VERSIONS.md` gains rows for the llama.cpp version and build, and for each served model's source, revision and SHA-256. The Ollama rows are kept until M2 and then removed.
- **Upgrading it.**
  1. `brew unpin`, upgrade, and pin again.
  2. Run the benchmark.
  3. Run the slot timing test from doc 02 §3.4.

  A release that fixes llama.cpp issue 28139 changes how idle slots are cached. When one arrives, M1's measurements decide whether `--no-cache-idle-slots` stays.

### 3.9 Security posture

v1/10 §3.9 still applies, with three changes:
- **The firewall allow-list.** The bootstrap no longer allows Ollama. It does not list llama-server either, because a process that listens only on `127.0.0.1` never meets the firewall. The project's Python stays on the list, for the harness, Whisper and Kokoro.
- **The Keychain after a restart (to confirm in M8).** The tools that need a secret read it from the macOS Keychain (doc 12 §3.9). With automatic login, macOS should unlock the login keychain itself, so these tools should work after a power cut. M8 checks this. If it does not hold, those tools report themselves unavailable until you log in once through Screen Sharing.
- **No Obsidian plugins on the Mac.** If Obsidian runs on the Mac, it runs with no community plugins (doc 12 §3.8).

### 3.10 Moving to a new Mac

Added 2026-11-11, after the move from the laptop to the Mac Studio. That move used v1's laptop-driven commands (`mini.sh push-env`, `push-vm`) and needed fix after fix by hand: the harness refused Home Assistant because the address check read `en0`, which is the Studio's unplugged Ethernet port; the VM came up bridged to that same port; UTM 5 did not list the copied VM; Home Assistant's speech entries still pointed at the laptop, two of each; the Brave key stayed in the laptop's Keychain, which a session over SSH cannot write; and the dashboard's history stayed behind. Remote control of the new Mac was also the wrong default: nothing on it needs Remote Login once it is set up.

A move is now two commands, each run at the Mac it changes:

1. **On the old Mac, `scripts/export_to_new_mac.sh DESTINATION`.** It stops the services and the VM, then packs one folder, `studio-assistant-move`, onto a drive or any folder you can carry:

    | In the folder | From | Why |
    |---|---|---|
    | `bootstrap_mac.sh`, `Brewfile` | the checkout | The new Mac needs nothing else to start, not even git |
    | `env` | `.env` | Addresses, Home Assistant's token, the Samba password |
    | `app-support/` | `~/Library/Application Support/studio-assistant/` | The API keys Home Assistant already holds, the harness database, the Brave spend log |
    | `logs/` | `exchanges/`, `traces/`, `pipeline_runs/` | The dashboard's history; service logs and health state describe the old Mac and stay |
    | `brave-search-api.key` | the login Keychain | The one secret outside `.env` |
    | `vm/Home Assistant.utm` | UTM's folder | The configured Home Assistant, with its network card's MAC address, so the router gives it the same address |
    | `manifest.txt` | | When, from which Mac, the repository and commit |

    The old Mac's services and VM stay stopped. Both copies of the VM share one MAC address, so it must never run on two Macs.

2. **On the new Mac, `bash <folder>/bootstrap_mac.sh`.** The bootstrap finds the export folder beside itself and reads the repository from the manifest. After v1's install steps it:
    - restores `.env` and the key folder before any service starts, keeping whatever was already there under a dated name;
    - merges the history without overwriting a day the new Mac has already logged;
    - puts the Brave key in the Keychain;
    - downloads the served model, or keeps a file that already matches its hash (`serving fetch`);
    - registers the VM with UTM (`haos_vm.sh register`), bridged to the new Mac's own interface, and starts it;
    - runs `ha_setup.py --only integrations --only pipeline`, which replaces Wyoming entries made for another address, duplicates included;
    - asks the smoke test's question through Home Assistant;
    - removes `env`, `app-support/` and the Brave key from the folder, last, so a run that stops partway can be repeated;
    - prints the router reservation to make, with the interface's hardware address.

    Everything that needs a person comes first: the Xcode tools, the installers' and system settings' password, Docker's terms, and the permission
    prompts for System Events and UTM. The script then prints "nothing below needs you" before the model download, which can take an hour.

Three changes make the scripts work on any Mac, not only the laptop:
- **One place knows the network.** `scripts/network_identity.sh` reads the interface that carries the default route, its address, its hardware address and the Bonjour name. `services.sh`, `haos_vm.sh` and `ha_setup.py` ask it instead of assuming `en0` or `192.168.1.152`.
- **The allowed hosts include the name.** The harness and the dashboard answer to the address and to `<name>.local`, in macOS's spelling and in the lowercase a browser sends, so the dashboard opens by name from the laptop.
- **The Brewfile installs llama.cpp**, not Ollama.

What still needs a person after the script: the router reservation, and erasing the drive, whose copy of the VM holds Home Assistant's accounts. `docs/MOVING_TO_A_NEW_MAC.md` is the human version of this section, as numbered steps; the export copies it into the folder as `README.md`, and CLAUDE.md tells Claude Code on either Mac to give those steps rather than its own.

## 4. Packages and tools, and what each does for the business logic

| Package or tool | Role in this subsystem |
|---|---|
| `ops` (ours) | As in v1, plus the new probes, the slow-request count, and the new restart list |
| `serving` launcher (ours, doc 02) | `launch`, `show` and `fetch`: starts llama-server from `config/serving.toml`, prints its command, and downloads a model at its pinned revision, checking the hash each time |
| launchd | Runs llama-server and the harness, and restarts them if they exit |
| `brew pin` | Holds llama.cpp at the measured version |
| `openssl rand` | Makes the API keys at install |
| rsync over SSH | Copies the models to the Mac and the memory notes to the laptop |

## 5. Configuration we control

| Setting | Where | Value |
|---|---|---|
| The agents | `scripts/services.sh` | `llama`, `harness`, `mcp`, `whisper`, `kokoro`, `health` (`ollama` removed) |
| API key files | `~/Library/Application Support/studio-assistant/` | `llama-server.key`, `harness.key`, mode 600 |
| The harness's address, port and allowed host names | The harness's config file | Every address, port 8770, the Mac's name and address |
| The restart list | `ops/deploy.py` | The table in 3.3 |
| Waiting for llama-server after a restart | `ops/deploy.py` | Two minutes |
| Health thresholds and waits | `ops/health.py` | The table in 3.4 |
| The slow-request threshold | `ops/health.py` | More than 600 tokens read fresh |
| The grace while the model loads | `ops/health.py` | Five minutes after llama-server starts |
| The notes backup on the laptop | `scripts/mini.sh` | `~/Library/Application Support/studio-assistant/notes-backup/`; deleted notes kept 30 days |
| llama.cpp's version | `brew pin`, recorded in `docs/VERSIONS.md` | 0.6.0 (build 11429) on the laptop |

## 6. Failure modes

| Failure | What happens | What to do |
|---|---|---|
| llama-server restarts | The harness answers "I can't reach the model right now" until it is back, then warms both slots | Nothing; if it keeps happening, read `llama.log` |
| The model's file does not match its hash | The launcher refuses to start, and the health check counts llama-server as failed | `serving fetch` the model again, then `push-models` |
| The slow-request count rises | Answers start late; nothing restarts | Compare `cache_n` in the exchange log before and after the last change; an upgrade of llama.cpp or a change to the prompt is the usual cause |
| The harness key in Home Assistant is stale | Every question gets "I can't reach the assistant right now" | Run `ha_setup.py` again |
| A deploy changes the prompt but the warm-up fails | The smoke test still runs; only the first question is slow | Nothing; the next question warms the slot |
| The notes backup is never pulled | The only copy is on the Mac | `mini.sh logs` runs it; the weekly report says when it last ran |
| An upgrade of llama.cpp breaks tool calls | The benchmark shows malformed calls before any deploy | Stay pinned; report it upstream |

## 7. Concepts for newcomers

**Warm-up.** One short request per slot, made before any question, so the cache already holds the part of the prompt that never changes. Without it, the first question after a restart reads the whole prompt.

**Pinning a Homebrew package.** `brew pin` marks a package so that `brew upgrade` leaves it alone. Upgrading it becomes a deliberate act.

**A hash check.** A SHA-256 hash is a fingerprint of a file's bytes. Comparing it with the recorded one proves the file is exactly the one that was tested.

## 8. Sources

- Apple, `launchd.plist(5)`: `KeepAlive`, `StartInterval`.
- Homebrew, `brew pin`: [docs.brew.sh/Manpage](https://docs.brew.sh/Manpage)
- rsync, `--delete` and `--backup-dir`: `man rsync`.
- llama.cpp server's `/health` and `timings`: [llama.cpp server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- The idle-slot bug: [llama.cpp issue 28139](https://github.com/ggml-org/llama.cpp/issues/28139)
