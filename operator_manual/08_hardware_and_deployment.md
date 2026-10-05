# Hardware
<!-- complexity: packages=3 parts=2 concepts=2 tier=standard -->

This page covers the one Mac that runs everything: where each service runs on it, what has to fit in its memory, and how it comes back on its own after a power cut. Today that Mac is a 16 GB M1 Pro MacBook; the always-on machine will be a Mac mini whose size [the benchmark](01_llm_benchmark.md) decides.

## Where this fits

```mermaid
flowchart TB
--8<-- "_includes/system_map.mmd"
class stt,intents,agent,tts,ma,piper,whisper,ollama,mcp,searxng,health current
```

## Key definitions

| Term | Meaning |
|---|---|
| Unified memory | One pool of memory shared by the CPU and GPU on Apple Silicon, whose size decides which models fit. |
| launchd | macOS's service manager, which runs the program a plist file describes at login and keeps it alive or reruns it every N seconds. |
| Login item | An application macOS opens when the user logs in, listed under System Settings, General, Login Items. |
| Docker Desktop on macOS | An app that runs Linux containers inside a hidden Linux virtual machine, where they cannot see the GPU or receive the network's discovery packets. |

## Packages and tools

| Tool | What it is | How this part uses it |
|---|---|---|
| The Mac | An Apple Silicon computer with unified memory. The prototype is a 16 GB M1 Pro MacBook; the Mac mini is not yet bought | Runs every service. Its memory decides which model fits, and its GPU is why the model and Whisper run natively |
| macOS 15.7.3 | The operating system, with `pmset` for power, `socketfilterfw` for the application firewall, login items, and automatic login | `scripts/bootstrap_mac.sh` sets it up once: restart after a power failure, never sleep, let the LAN-facing programs through the firewall, SSH by key only |
| Homebrew and the `Brewfile` | macOS's package manager and the list of what `brew bundle` installs | Installs `git`, `uv`, `ollama`, `espeak-ng`, `rsync`, `shellcheck`, `shfmt`, `mermaid-cli`, Docker Desktop, and UTM |
| launchd | macOS's service manager | `scripts/services.sh install` writes and loads five agents: Ollama, the tool server, Whisper, Kokoro, and the health check |
| UTM 4.7.5 | A free app that runs virtual machines on Apple's hypervisor | Runs the Home Assistant OS VM that `scripts/haos_vm.sh` creates with 4,096 MB, 2 cores, and a bridged network interface. [Home Assistant](06_home_assistant_core.md) covers what runs inside |
| Docker Desktop 4.89.0, engine 29.7.2 | Docker for macOS: a hidden Linux VM with a container runtime inside | Runs the SearXNG container from `docker/searxng/docker-compose.yml`. [MCP Tool Server](03_web_search_mcp.md#searxng-in-docker) covers the container |

## How it works

### Three places to run a service

```mermaid
flowchart TB
--8<-- "_includes/palette.mmd"
%% grid: .haos   health   .docker
%% grid: .haos   mcp      searxng
%% grid: core    kokoro   .
%% grid: core    whisper  .
%% grid: addons  ollama   .
%% grid: .       gpu      .
%% peers: core addons health mcp kokoro whisper ollama searxng
subgraph mac["the Mac, 192.168.1.152"]
  subgraph haos["UTM VM, 192.168.1.156"]
    core("Home Assistant<br/>port 80")
    addons("add-ons<br/>Piper, Music Assistant")
  end
  subgraph native["launchd agents, on 0.0.0.0"]
    health("health check<br/>every 300 s")
    mcp("tool server<br/>port 8765")
    kokoro("Kokoro, on the CPU<br/>port 10210")
    whisper("Whisper<br/>port 10300")
    ollama("Ollama<br/>port 11434")
  end
  subgraph docker["Docker Desktop's Linux VM"]
    searxng("SearXNG<br/>127.0.0.1:8080 only")
  end
  gpu("Apple Silicon GPU<br/>one pool of unified memory")
end
core -- "MCP" --> mcp
core -- "Wyoming" --> kokoro
core -- "Wyoming" --> whisper
core -- "HTTP" --> ollama
mcp -- "loopback" --> searxng
whisper -- "MLX" --> gpu
ollama -- "MLX" --> gpu
class core,addons,whisper,ollama,searxng third
class mcp,health,kokoro ours
class gpu hw
```

Each place exists because one service needs something only that place gives:

- **Native processes, started by launchd:** Ollama, Whisper, Kokoro, the tool server, and the health check.
    - Only a native process can reach the GPU. Metal, Apple's GPU programming interface, is not exposed to a virtual machine or a container on macOS, so Ollama and Whisper must run here.
    - Kokoro and the tool server do not need the GPU. They run natively from the project's `.venv`, so they use exactly the versions pinned in `uv.lock`.
    - Each binds `0.0.0.0`, all of the Mac's addresses, because its caller is Home Assistant in the VM, which arrives over the Wi-Fi at 192.168.1.152.
- **The UTM virtual machine:** Home Assistant OS and its add-ons.
    - Home Assistant OS is a whole operating system, and its add-ons, such as Piper and Music Assistant, exist only on that image, so it needs a machine of its own.
    - Its network interface is bridged onto the Wi-Fi, so it has its own address, 192.168.1.156, and its own name, `homeassistant.local`. The puck and the Sonos find it by multicast discovery, which reaches only a real address on the LAN. Docker Desktop on macOS cannot give a container one.
    - You reach it on port 80 of that address.
- **Docker Desktop:** SearXNG.
    - SearXNG ships as a container image, and Docker Desktop is a Linux VM plus a container runtime that Docker maintains for us, so there is no Linux machine of our own to look after.
    - The compose file publishes it on `127.0.0.1:8080` only. Its one caller is the tool server on the same Mac, so nothing on the Wi-Fi needs to reach it.

The first time a program listens on the LAN, macOS asks whether to allow incoming connections, and the VM's calls time out until the answer is "allow". A Mac with no screen cannot answer that dialog, so `scripts/bootstrap_mac.sh` adds Ollama, the `.venv` Python, Docker, and UTM to the firewall's allow-list in advance.

`scripts/services.sh install` writes and loads all five launchd agents:

*From `scripts/services.sh`, `install_agents`:*

```bash
install_agents() {
    mkdir -p "$AGENTS_DIR" "$LOG_DIR"
    prepare_kokoro
    # launchd keeps running the definition it loaded, so every agent is unloaded before its plist is rewritten; start_agents then loads the new ones.
    stop_agents
    ...
    # Ollama: Homebrew's service binds to localhost only; ours binds the LAN and keeps the model loaded.
    brew services stop ollama >/dev/null 2>&1 || true
    ENV_KEYS=(OLLAMA_HOST OLLAMA_KEEP_ALIVE OLLAMA_MAX_LOADED_MODELS) ENV_VALUES=(0.0.0.0:11434 -1 1)
    write_plist ollama "$OLLAMA_BIN" serve
    ...
    ENV_KEYS=(WEB_SEARCH_HOST WEB_SEARCH_PORT WEB_SEARCH_EXCHANGES_DIR WEB_SEARCH_ALLOWED_HOSTS)
    ENV_VALUES=(0.0.0.0 8765 "$LOG_DIR/exchanges" "${WEB_SEARCH_ALLOWED_HOSTS:-${lan_address:+$lan_address:8765,}localhost:8765,127.0.0.1:8765}")
    ...
    write_plist mcp "$PROJECT_DIR/.venv/bin/web-search-mcp"
    ENV_KEYS=() ENV_VALUES=()
    write_plist whisper "$PROJECT_DIR/.venv/bin/wyoming-mlx-whisper" --uri tcp://0.0.0.0:10300 --model mlx-community/whisper-large-v3-turbo --language en
    write_plist kokoro "$PROJECT_DIR/.venv/bin/kokoro-server" --uri tcp://0.0.0.0:10210 --voice af_heart --data-dir "$HOME/.cache/wyoming-kokoro" --streaming --device cpu
    ...
    PLIST_START_INTERVAL="$HEALTH_INTERVAL_SECONDS" write_plist health "$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/scripts/health_check.py" "${health_flags[@]}"
    start_agents
}
```

What that produces:

- **One file per agent.** `write_plist` writes `~/Library/LaunchAgents/com.studio-assistant.<name>.plist` with the program and its arguments, its environment, the repository as working directory, and a log at `~/Library/Logs/studio-assistant/<name>.log`.
- **Kept alive or rerun.** Every agent has `RunAtLoad`, so it starts at login. Ollama, the tool server, Whisper, and Kokoro also get `KeepAlive`, so launchd restarts one that exits, waiting at least ten seconds between starts. The health check gets `StartInterval` instead and runs once every 300 seconds.
- **Unloaded before rewriting.** launchd keeps running the definition it loaded, so a changed argument or environment variable takes effect only if the old agent is unloaded first.
- **Homebrew's Ollama service stopped.** It binds loopback only, where the VM could never reach it. Ours binds `0.0.0.0:11434` and keeps the model loaded until Ollama stops (`OLLAMA_KEEP_ALIVE=-1`).

The ports are fixed:

| Service | Port | Listens on |
|---|---|---|
| Ollama | 11434 | all of the Mac's addresses |
| Whisper | 10300 | all of the Mac's addresses |
| Kokoro | 10210 | all of the Mac's addresses |
| Tool server | 8765 | all of the Mac's addresses |
| SearXNG | 8080 | the Mac's loopback address only |
| Home Assistant | 80 | the VM's address, 192.168.1.156 |

### The memory budget

On Apple Silicon there is no separate graphics memory. The CPU, the GPU, and every virtual machine draw from one pool, so choosing a machine means adding up everything that is resident at the same time. [LLMs on Apple Silicon](02_local_llm.md#memory-cost) explains what the model itself costs.

The table adds it up for the prototype, as measured, and for the mid-tier Mac mini, as an estimate:

| Part | Prototype: MacBook M1 Pro, 16 GB, `gemma4:e4b-it-qat` | Mid tier: Mac mini, 32 GB, Gemma 4 26B-A4B at 4-bit |
|---|---|---|
| macOS | about 3 GB | about 3 GB |
| The Home Assistant VM, with Piper and the other add-ons | given 4,096 MB; its process holds about 7.5 GB | given 3,072 MB; 3 to 4 GB |
| Whisper | 1.6 GB of weights; the process holds about 2.5 GB | about 2.5 GB |
| Kokoro | about 1 GB | about 1 GB |
| SearXNG in Docker Desktop | about 1.7 GB | about 1.7 GB |
| The model's weights | 6.1 GB | about 16 GB |
| The KV cache, at 16k tokens | 1 to 2 GB | 1 to 2 GB |
| **Total** | **about 23 to 24 GB, well over 16** | **about 28 to 30 GB** |

What the totals mean:

- **The prototype cannot hold everything at once.** macOS survives the overflow by compressing memory and swapping. That is tolerable for a spoken answer and fatal for a benchmark, where a model that spills off the GPU writes a fraction of a token per second. So the rule is one heavy workload at a time: the VM with the speech services, or a benchmark pass, never both.
- **The 26B model does not fit the prototype at all.** Its weights alone take about 16 GB.
- **The mid tier fits with a few gigabytes to spare.** The bootstrap's instructions create the Mac mini's VM with 3,072 MB (`HAOS_VM_MEMORY_MB=3072`) to leave the model room. The VM row is the least certain one, because on the prototype the VM's process holds far more than the 4,096 MB it is given.

These are the Mac mini configurations under consideration:

| Tier | Machine | Runs comfortably |
|---|---|---|
| Budget | Mac mini M6, 24 GB, $1,100 | Gemma 4 E4B and Qwen 3.5-9B at full precision; Gemma 4 26B-A4B only at 3-bit with a small context |
| Mid | Mac mini M6, 32 GB, $1,300 | Gemma 4 26B-A4B at 4-bit with a 16k context; Qwen 3.6-35B-A3B at 4-bit if the VM is trimmed |
| High | Mac mini M5 Pro, 48 GB, about $2,100 | Qwen 3.6-35B-A3B at 8-bit, Gemma 4 31B dense at about 20 tokens per second |
| Not recommended | Refurbished M4 Mac mini, 16 GB, $849 | The same limits as the prototype MacBook, without neural accelerators |

Two things matter beyond memory size:

- **Neural accelerators.** The M5 and M6 GPU cores carry them, and they cut the time to first token three to four times against the M4. After a search puts thousands of tokens of page text in the prompt, that is the difference between a two-second and an eight-second pause.
- **Power and noise.** A Mac mini idles at about 4 W and draws 30 to 40 W while generating, silently, which suits an always-on machine in a 500 square foot studio.

### Coming back after a reboot

```mermaid
flowchart LR
--8<-- "_includes/palette.mmd"
%% grid: .      .      docker   searxng  .
%% grid: power  login  launchd  agents   .
%% grid: .      .      .        health   vm
%% grid: .      .      utm      .        .
%% peers: power login docker searxng launchd agents health vm utm
power("power returns<br/>pmset autorestart")
login("user logged in<br/>automatic login")
docker("Docker Desktop<br/>login item")
searxng("SearXNG<br/>unless-stopped")
launchd("launchd<br/>five agents")
agents("Ollama, Whisper,<br/>Kokoro, tool server")
health("health check<br/>every 300 s")
vm("the VM boots<br/>Home Assistant :80")
utm("UTM<br/>login item")
power --> login
login --> docker
login --> launchd
login --> utm
docker --> searxng
launchd --> agents
launchd --> health
health -- "starts" --> vm
utm -- "hosts" --> vm
class docker,searxng,launchd,agents,vm,utm third
class health ours
```

Nobody sits at this Mac, so a power cut must end with the assistant answering again and no hands involved. Each link below is set once, by the [bootstrap script](10_operations.md#bootstrap) or by a person at the screen:

1. **Power.** `pmset -a sleep 0 disksleep 0 displaysleep 5 autorestart 1 womp 1 powernap 0` tells the Mac never to sleep, to start up on its own when power returns, and to wake on a LAN packet.
2. **Automatic login.** Every service runs under the user's account, so the Mac must log that user in without a password prompt. Automatic login is a switch in System Settings, Users & Groups, and it needs FileVault off, because an encrypted disk asks for a password before macOS starts.
3. **launchd agents and login items.** Once the user is logged in, launchd starts the five `com.studio-assistant` agents. Ollama loads the model on the first request and keeps it. At the same time macOS opens the two login items, Docker Desktop and UTM, both hidden. Docker's engine starts and brings the SearXNG container back, because the compose file says `restart: unless-stopped`.
4. **The VM, through the health check.** UTM opens but does not start the VM; the health check does. It runs at login and every 300 seconds after, and applies the defaults in `Policy`:
    - A VM whose `utmctl status` is anything but `started` gets `utmctl start`, at most once every 30 minutes.
    - A VM that is running while Home Assistant has failed five checks in a row is stopped and started, at most once every two hours.
    - Home Assistant then needs a few minutes to boot and answer on port 80.

On the prototype MacBook the health check is installed with `HEALTH_CHECK_FLAGS="--no-remediate"`, so it only records, and the VM stays stopped until you start it. [Operations](10_operations.md#the-health-check) covers the rest of the health check and the maintenance flag that pauses it during a deploy.

The bootstrap sets the login items and the power settings in these steps:

*From `scripts/bootstrap_mac.sh`, the services and power steps:*

```bash
step "launchd agents: ollama, mcp, whisper, kokoro, health"
run "$TARGET_DIR/scripts/services.sh" install

step "Docker and UTM open at login (the VM and SearXNG must come back after a power cut)"
for app in Docker UTM; do
    run osascript -e "tell application \"System Events\" to if not (exists login item \"$app\") then make login item at end with properties {path:\"/Applications/$app.app\", hidden:true}"
done
...
    step "power: never sleep, restart after a power failure, wake on LAN"
    as_root pmset -a sleep 0 disksleep 0 displaysleep 5 autorestart 1 womp 1 powernap 0
```

Automatic macOS updates are switched off as well. Home Assistant, Ollama, the models, and the Python packages are upgraded on purpose, one at a time, and `docs/VERSIONS.md` records what is running now; its refresh procedure is the upgrade procedure.

## Run it yourself

Everything below runs on the Mac from the repository folder, and all of it except the last step only reads.

1. Check the native services and the last health snapshot:

    ```bash
    scripts/services.sh status
    ```

    You see one line per port, then the health check, then its last snapshot:

    ```text
    ollama: listening on 11434
    mcp: listening on 8765
    whisper: NOT listening on 10300
    kokoro: NOT listening on 10210
    health: checks every 300 s
    last health snapshot 2026-09-30T05:44:01+00:00: FAILING home_assistant, searxng, vm
    ```

    That is the prototype between sessions: the speech services, the VM, and SearXNG are stopped on purpose. On a Mac where everything runs, every port says `listening` and the snapshot says `all ok`.

2. List the agents launchd has loaded:

    ```bash
    launchctl list | grep studio-assistant
    ```

    Each row is a process id (or `-` when not running), the last exit status, and the label, for example `138  0  com.studio-assistant.ollama`. The health check shows `-` between runs, and an exit status of 1 when its last run found a failure. An unloaded agent does not appear.

3. Check the VM and the container. `docker` is not on the shell's path, because Docker Desktop keeps its command line tool inside the app, so use the wrapper script or the full path:

    ```bash
    scripts/haos_vm.sh status
    scripts/searxng.sh status
    /Applications/Docker.app/Contents/Resources/bin/docker ps
    ```

    `haos_vm.sh status` prints `stopped` or `started`. `searxng.sh status` prints the compose table, then `SearXNG JSON API: ok` when the container answers or `SearXNG JSON API: not responding` when it does not. `docker ps` lists `studio-searxng` with `127.0.0.1:8080->8080/tcp` when SearXNG is up, and only the header row when nothing runs.

4. Check that the Mac matches the `Brewfile`:

    ```bash
    brew bundle check --no-upgrade --verbose
    ```

    A match prints `The Brewfile's dependencies are satisfied.` Otherwise it names each gap, such as `→ Formula rsync needs to be installed.`, and `brew bundle install` fills it. Without `--no-upgrade` it also flags every outdated formula. Setting up a fresh Mac, and rehearsing that on this one, is in [Operations](10_operations.md#bootstrap).

5. Take the native services down and bring them back:

    ```bash
    scripts/services.sh stop
    scripts/services.sh status
    scripts/services.sh start
    ```

    `stop` unloads all five agents, Ollama included, so the model leaves memory and the next question waits while it reloads. `start` loads them again and prints the status. `scripts/services.sh restart ollama` (or `mcp`, `whisper`, `kokoro`, `health`) restarts one agent. To stop only the speech services, unload their two agents as [Voice Pipeline](05_voice_pipeline.md#run-it-yourself) shows; to start or stop the VM, use `scripts/haos_vm.sh start` and `stop` as [Home Assistant](06_home_assistant_core.md#run-it-yourself) shows.

## Where to look in the code

| Path | What you find there |
|---|---|
| [`scripts/bootstrap_mac.sh`](https://github.com/seanlin2000/home_assistant/blob/main/scripts/bootstrap_mac.sh) | The power settings, firewall allow-list, and login items that bring the Mac back after a power cut; [Operations](10_operations.md#bootstrap) walks through the rest of the script |
| [`Brewfile`](https://github.com/seanlin2000/home_assistant/blob/main/Brewfile) | Everything Homebrew installs, with a comment on most lines saying which part of the system needs it |
| [`scripts/services.sh`](https://github.com/seanlin2000/home_assistant/blob/main/scripts/services.sh) | `write_plist` and `install_agents`: the five launchd agents, their ports, the `0.0.0.0` binding, and the `status`, `logs`, and `restart` subcommands |
| [`scripts/haos_vm.sh`](https://github.com/seanlin2000/home_assistant/blob/main/scripts/haos_vm.sh) | The UTM virtual machine: memory, cores, UEFI, the virtio disk, the bridged interface, and the `utmctl` wrappers |
| [`docker/searxng/docker-compose.yml`](https://github.com/seanlin2000/home_assistant/blob/main/docker/searxng/docker-compose.yml) | The SearXNG container: the loopback-only port, `restart: unless-stopped`, and the dropped capabilities |
| [`scripts/searxng.sh`](https://github.com/seanlin2000/home_assistant/blob/main/scripts/searxng.sh) | `up`, `down`, `restart`, `status`, and `logs` for the container, and the path fix for Docker Desktop's command line tool |
| [`ops/health.py`](https://github.com/seanlin2000/home_assistant/blob/main/ops/health.py) | `Policy` and `decide_actions`: when the health check starts or restarts the VM, brings SearXNG back up, or kickstarts an agent, with the cooldowns |
| [`docs/VERSIONS.md`](https://github.com/seanlin2000/home_assistant/blob/main/docs/VERSIONS.md) | The versions of record for macOS, Homebrew tools, Docker, UTM, Home Assistant OS, the add-ons, and the models, with the refresh procedure |

## Further reading

- Design doc: [`design_docs/v1/08_hardware_and_deployment.md`](https://github.com/seanlin2000/home_assistant/blob/main/design_docs/v1/08_hardware_and_deployment.md), which also carries the bill of materials, the running cost, and the failure modes
- [Home Assistant OS on macOS with UTM](https://www.home-assistant.io/installation/macos), the official steps behind `scripts/haos_vm.sh`, including why the VM must be bridged
- [Apple, exploring LLMs with MLX on the M5](https://machinelearning.apple.com/research/exploring-llms-mlx-m5), for the measurements behind the claim that the neural accelerators cut time to first token
- [MacRumors, Apple announces the 2026 Mac mini](https://www.macrumors.com/2026/08/25/apple-announces-2026-mac-mini/), for the M6 and M5 Pro configurations the tier table compares
- [unsloth/gemma-4-26B-A4B-it-GGUF](https://huggingface.co/unsloth/gemma-4-26B-A4B-it-GGUF), for the file size of each quantization of the model that sets the 32 GB budget
