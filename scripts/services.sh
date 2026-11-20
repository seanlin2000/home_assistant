#!/usr/bin/env bash
# Install, start, stop, and inspect the native macOS services that Home Assistant talks to over the LAN.
#
#   scripts/services.sh install      write launchd agents for speech to text, kokoro, the harness and the exchange dashboard (LAN), llama-server and mcp (127.0.0.1), the health check, the nightly listings refresh, and the hourly newsletters pull, and load them
#   scripts/services.sh start|stop   load/unload the agents
#   scripts/services.sh restart NAME restart one agent (llama|mcp|harness|dashboard|speech|kokoro|health|listings|newsletters)
#   scripts/services.sh engine NAME  serve with llama-server or strata on this Mac whatever config/serving.toml says, or default to follow it again
#   scripts/services.sh status       show what is listening on each port and the last health snapshot; exits 1 if an agent or port is down
#   scripts/services.sh dashboard    start the exchange dashboard if it is not running and open it in the browser
#   scripts/services.sh logs NAME    tail a service log (speech|kokoro|mcp|harness|dashboard|llama|health|listings|newsletters)
#   scripts/services.sh uninstall    unload and remove the agents
#
# Ports: speech to text 10300 (the speech server, config/speech.toml), Kokoro 10210 and the harness 8770 (with an API key) bind 0.0.0.0 so the VM can reach them, and the
# exchange dashboard 8775 does so a laptop on the home network can open it. The engine 127.0.0.1:8090 (with an API key, from config/serving.toml)
# and the tool server 127.0.0.1:8765 answer only this Mac (design_docs/v2/08 section 3.2).
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
AGENTS_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$HOME/Library/Logs/studio-assistant"
PREFIX="com.studio-assistant"
SERVICES=(llama mcp harness dashboard speech kokoro health listings newsletters)
# Agents an older install wrote and install now removes: llama-server replaced Ollama (design_docs/v2/10 section 3.1), and the speech server's
# Qwen3-ASR replaced Whisper.
RETIRED_SERVICES=(ollama whisper)
APP_SUPPORT_DIR="$HOME/Library/Application Support/studio-assistant"
HEALTH_INTERVAL_SECONDS="${HEALTH_INTERVAL_SECONDS:-300}"
LISTINGS_REFRESH_HOUR="${LISTINGS_REFRESH_HOUR:-4}"
LISTINGS_REFRESH_MINUTE="${LISTINGS_REFRESH_MINUTE:-30}"
NEWSLETTERS_INTERVAL_SECONDS="${NEWSLETTERS_INTERVAL_SECONDS:-3600}"
UNLOAD_TIMEOUT_SECONDS="${UNLOAD_TIMEOUT_SECONDS:-30}"
# The llama agent runs whichever engine serving.toml (or this file, written by `engine`) names; Strata's server stops its engine as it exits, and the
# engine takes a few seconds more to unmap the model, so a restart waits for it instead of loading a second engine beside it.
ENGINE_OVERRIDE_FILE="$APP_SUPPORT_DIR/engine"
STRATA_ENGINE_PROCESS=strata
SERVING_CLI="${SERVING_CLI:-$PROJECT_DIR/.venv/bin/serving}"
STRATA_SCRIPT="${STRATA_SCRIPT:-$PROJECT_DIR/scripts/strata.sh}"
ENGINE_EXIT_TIMEOUT_SECONDS="${ENGINE_EXIT_TIMEOUT_SECONDS:-60}"
# How often MLX renews the speech server's wired memory (install_agents explains why); scripts/speech_server.sh uses the same default.
MLX_RESIDENCY_REFRESH_MS="${MLX_RESIDENCY_REFRESH_MS:-1000}"

usage() {
    sed -n '2,15p' "$0"
    exit 1
}

plist_path() { echo "$AGENTS_DIR/$PREFIX.$1.plist"; }

agent_target() { echo "gui/$(id -u)/$PREFIX.$1"; }

agent_loaded() { launchctl print "$(agent_target "$1")" >/dev/null 2>&1; }

env_file_value() {
    # $1 key; its value in the project's .env, or nothing when absent
    grep -E "^$1=" "$PROJECT_DIR/.env" 2>/dev/null | tail -n 1 | cut -d= -f2- || true
}

write_plist() {
    # $1 name, $2.. program arguments; environment via ENV_KEYS/ENV_VALUES arrays.
    # PLIST_START_INTERVAL=N makes a periodic job (launchd runs it every N seconds) instead of a kept-alive daemon; PLIST_START_HOUR and
    # PLIST_START_MINUTE make a daily one (launchd runs it at that local time, or on waking when the Mac slept through it).
    local name="$1"
    shift
    local path
    path="$(plist_path "$name")"
    {
        cat <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$PREFIX.$name</string>
  <key>ProgramArguments</key><array>
EOF
        for arg in "$@"; do echo "    <string>$arg</string>"; done
        cat <<EOF
  </array>
  <key>WorkingDirectory</key><string>$PROJECT_DIR</string>
  <key>EnvironmentVariables</key><dict>
    <key>HOME</key><string>$HOME</string>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
EOF
        local i
        for i in "${!ENV_KEYS[@]}"; do echo "    <key>${ENV_KEYS[$i]}</key><string>${ENV_VALUES[$i]}</string>"; done
        cat <<EOF
  </dict>
  <key>RunAtLoad</key><true/>
EOF
        if [[ -n "${PLIST_START_INTERVAL:-}" ]]; then
            echo "  <key>StartInterval</key><integer>$PLIST_START_INTERVAL</integer>"
        elif [[ -n "${PLIST_START_HOUR:-}" ]]; then
            echo "  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>$PLIST_START_HOUR</integer><key>Minute</key><integer>${PLIST_START_MINUTE:-0}</integer></dict>"
        else
            echo "  <key>KeepAlive</key><true/>"
            echo "  <key>ThrottleInterval</key><integer>10</integer>"
        fi
        cat <<EOF
  <key>StandardOutPath</key><string>$LOG_DIR/$name.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/$name.log</string>
</dict></plist>
EOF
    } >"$path"
    echo "wrote $path"
}

prepare_kokoro() {
    # wyoming-kokoro-torch downloads voices itself but expects the model weights and config in its data directory.
    local data_dir="$HOME/.cache/wyoming-kokoro"
    mkdir -p "$data_dir"
    if [[ ! -e "$data_dir/kokoro-v1_0.pth" ]]; then
        local snapshot
        snapshot="$("$PROJECT_DIR/.venv/bin/python" -c "from huggingface_hub import snapshot_download; print(snapshot_download('hexgrad/Kokoro-82M', allow_patterns=['kokoro-v1_0.pth','config.json']))")"
        ln -sf "$snapshot/kokoro-v1_0.pth" "$data_dir/kokoro-v1_0.pth"
        ln -sf "$snapshot/config.json" "$data_dir/config.json"
    fi
}

prepare_speech() {
    # The speech server's own environment, and its model at the pinned revision, so the agent's first start loads it instead of downloading 2.5 GiB.
    "$PROJECT_DIR/scripts/speech_env.sh"
    "$PROJECT_DIR/.venv-speech/bin/speech-server" --download-only
}

ensure_api_key() {
    # $1 the key's name. Made once, readable only by this user, and kept on later installs; delete the file to change the key (design_docs/v2/10 section 3.2).
    local path="$APP_SUPPORT_DIR/$1.key"
    mkdir -p "$APP_SUPPORT_DIR"
    if [[ ! -s "$path" ]]; then
        (umask 077 && openssl rand -hex 32 >"$path")
        echo "made $path"
    fi
}

host_names_with_port() {
    # $1 port. Every Host header a caller on the home network or this Mac sends: the LAN address, the Bonjour name as macOS spells it and in the
    # lowercase a browser sends, and the loopback names. The match is exact, so each spelling is listed.
    local port="$1" address name hosts=() host listed=""
    address="$("$PROJECT_DIR/scripts/network_identity.sh" address 2>/dev/null || true)"
    name="$("$PROJECT_DIR/scripts/network_identity.sh" name 2>/dev/null || true)"
    [[ -n "$address" ]] && hosts+=("$address")
    [[ -n "$name" ]] && hosts+=("$name" "$(echo "$name" | tr '[:upper:]' '[:lower:]')")
    hosts+=(localhost 127.0.0.1)
    for host in "${hosts[@]}"; do
        [[ ",$listed," == *",$host:$port,"* ]] || listed="${listed:+$listed,}$host:$port"
    done
    echo "$listed"
}

install_agents() {
    mkdir -p "$AGENTS_DIR" "$LOG_DIR"
    prepare_kokoro
    prepare_speech
    # launchd keeps running the definition it loaded, so every agent is unloaded before its plist is rewritten; start_agents then loads the new ones.
    stop_agents
    remove_retired_agents
    # With the harness stopped, nothing appends to the old turns/ folder while the exchange logs move out of it (a no-op once moved).
    # A failed move leaves the files where they were, so it must not stop the agents from coming back.
    "$PROJECT_DIR/.venv/bin/python" -m ops.legacy_exchange_logs "$LOG_DIR" || echo "warning: exchange logs not moved out of $LOG_DIR/turns; rerun: .venv/bin/python -m ops.legacy_exchange_logs" >&2
    # The engine: the launcher checks the model's hash (and Strata's install) and replaces itself with llama-server or Strata's server, so launchd
    # supervises the server directly.
    ensure_api_key llama-server
    ENV_KEYS=() ENV_VALUES=()
    write_plist llama "$PROJECT_DIR/.venv/bin/serving" launch
    # Only the harness calls the tool server, so it listens on 127.0.0.1 alone.
    ENV_KEYS=(ASSISTANT_MCP_HOST ASSISTANT_MCP_PORT)
    ENV_VALUES=(127.0.0.1 8765)
    # Home for weather_forecast, written to .env by scripts/ha_setup.py --only weather (the shell environment wins). Without coordinates the server
    # starts without the weather tool and says why in mcp.log.
    local key value
    for key in WEATHER_LATITUDE WEATHER_LONGITUDE WEATHER_TIMEZONE WEATHER_UNITS; do
        value="${!key:-$(env_file_value "$key")}"
        if [[ -n "$value" ]]; then
            ENV_KEYS+=("$key")
            ENV_VALUES+=("$value")
        fi
    done
    write_plist mcp "$PROJECT_DIR/.venv/bin/assistant-mcp"
    # The harness listens on the LAN for the Home Assistant VM, so it requires its API key and answers only requests that name this machine (Host
    # header); a web page cannot reach it by DNS rebinding. HARNESS_ALLOWED_HOSTS in the environment overrides the derived list. Rerun install after
    # an address change. Its other settings are in config/harness.toml.
    ensure_api_key harness
    ENV_KEYS=(HARNESS_ALLOWED_HOSTS)
    ENV_VALUES=("${HARNESS_ALLOWED_HOSTS:-$(host_names_with_port 8770)}")
    write_plist harness "$PROJECT_DIR/.venv/bin/assistant-service"
    # The exchange dashboard has no key of its own (its chat box uses the harness's, server side), so it too answers only requests that name this
    # machine and refuses other sites' pages (design_docs/v2/13).
    ENV_KEYS=(DASHBOARD_ALLOWED_HOSTS)
    ENV_VALUES=("${DASHBOARD_ALLOWED_HOSTS:-$(host_names_with_port 8775)}")
    write_plist dashboard "$PROJECT_DIR/.venv/bin/exchange-dashboard"
    # Qwen3-ASR on MLX, on the port and model in config/speech.toml. It loads and warms the model before it listens (a few seconds).
    # macOS 26 and later unwire GPU memory about 2 s after a process's last GPU work, so the wired limit in config/speech.toml holds only if MLX
    # renews it; MLX does that only with this variable set, and every 3 s is too slow (ml-explore/mlx#4609).
    ENV_KEYS=(MLX_METAL_RESIDENCY_REFRESH_INTERVAL_MS)
    ENV_VALUES=("$MLX_RESIDENCY_REFRESH_MS")
    write_plist speech "$PROJECT_DIR/.venv-speech/bin/speech-server"
    ENV_KEYS=() ENV_VALUES=()
    # --volume 2 (+6 dB) brings answers level with the speaker's wake sound, which was about 8 dB louder. Kokoro lowers a sentence that would clip.
    write_plist kokoro "$PROJECT_DIR/.venv/bin/kokoro-server" --uri tcp://0.0.0.0:10210 --voice bm_fable --data-dir "$HOME/.cache/wyoming-kokoro" --streaming --volume 2 --device cpu
    # HEALTH_CHECK_FLAGS="--leave-vm" restarts services but never the VM (used on the laptop, where the VM is stopped on purpose most of the time);
    # "--no-remediate" installs an observe-only check.
    read -ra health_flags <<<"${HEALTH_CHECK_FLAGS:-}"
    # Bash 3.2, the one macOS ships, treats "${array[@]}" of an empty array as unbound under set -u; this form expands to nothing instead.
    PLIST_START_INTERVAL="$HEALTH_INTERVAL_SECONDS" write_plist health "$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/scripts/health_check.py" ${health_flags[@]+"${health_flags[@]}"}
    # The show listings the tool server reads all day (ops/listings_refresh.py). RunAtLoad also refreshes them on every install, so a new Mac has
    # listings before its first night.
    PLIST_START_HOUR="$LISTINGS_REFRESH_HOUR" PLIST_START_MINUTE="$LISTINGS_REFRESH_MINUTE" write_plist listings "$PROJECT_DIR/.venv/bin/listings-refresh"
    # Copies the Gmail newsletters label to dated markdown files the tool server reads (newsletters_mcp/pull.py, design doc v2/14). It runs in the
    # login session, where the Keychain holding its app password is unlocked.
    PLIST_START_INTERVAL="$NEWSLETTERS_INTERVAL_SECONDS" write_plist newsletters "$PROJECT_DIR/.venv/bin/newsletters-pull"
    start_agents
}

start_agents() {
    # A loaded agent is restarted; an unloaded one is loaded from its plist. Any agent that fails either way is named and the command fails,
    # because a silent failure here once left the puck with no voice and only "NOT listening" in the status to show for it.
    local name error failed=()
    for name in "${SERVICES[@]}"; do
        [[ -f "$(plist_path "$name")" ]] || continue
        if [[ "$name" == llama ]]; then
            error="$(restart_engine 2>&1)" || failed+=("$name (${error##*$'\n'})")
        elif agent_loaded "$name"; then
            error="$(launchctl kickstart -k "$(agent_target "$name")" 2>&1)" || failed+=("$name (${error%%$'\n'*})")
        else
            error="$(launchctl bootstrap "gui/$(id -u)" "$(plist_path "$name")" 2>&1)" || failed+=("$name (${error%%$'\n'*})")
        fi
    done
    sleep 2
    # What is still starting is shown, not judged: a service that loads a model cannot be listening 2 s after it starts. Whether the commit works
    # is the deploy's smoke test to say; this command fails only when launchd would not load an agent.
    status || true
    if ((${#failed[@]} > 0)); then
        printf 'failed to load: %s\n' "${failed[@]}" >&2
        return 1
    fi
}

stop_agents() {
    local name
    for name in "${SERVICES[@]}"; do
        launchctl bootout "$(agent_target "$name")" 2>/dev/null || true
    done
    for name in "${SERVICES[@]}"; do
        wait_until_unloaded "$name"
    done
    wait_for_engine_exit
}

remove_retired_agents() {
    local name
    for name in "${RETIRED_SERVICES[@]}"; do
        agent_loaded "$name" || [[ -f "$(plist_path "$name")" ]] || continue
        launchctl bootout "$(agent_target "$name")" 2>/dev/null || true
        wait_until_unloaded "$name"
        rm -f "$(plist_path "$name")"
        echo "removed the retired $name agent"
    done
}

wait_until_unloaded() {
    # bootout returns while launchd still holds the job: Kokoro takes about 5 s to exit, and loading its plist again in that window fails with
    # "Bootstrap failed: 5: Input/output error". Rewriting or reloading a plist waits until the old job is gone.
    local name="$1" half_seconds=0
    while agent_loaded "$name"; do
        if ((half_seconds >= UNLOAD_TIMEOUT_SECONDS * 2)); then
            echo "$name still unloading after $UNLOAD_TIMEOUT_SECONDS s" >&2
            return 1
        fi
        sleep 0.5
        half_seconds=$((half_seconds + 1))
    done
}

restart_agent() {
    local name="${1:?service name}"
    if [[ "$name" == llama ]]; then
        restart_engine
    else
        launchctl kickstart -k "$(agent_target "$name")" 2>/dev/null || launchctl bootstrap "gui/$(id -u)" "$(plist_path "$name")"
    fi
    echo "restarted $name"
}

prepare_engine() {
    # Under Strata, bring it to this checkout's pinned commit and folder before the running engine stops: only a check when it already is, an
    # install or update otherwise, so the old engine keeps answering meanwhile and a failed install leaves it running. Every engine start
    # comes through here (a deploy, start, install, the health check, engine), including a deploy run by code from before Strata.
    [[ "$("$SERVING_CLI" engine)" == strata ]] || return 0
    "$STRATA_SCRIPT" ensure
}

restart_engine() {
    prepare_engine || {
        echo "Strata is not at this checkout's pin; the running engine was left alone" >&2
        return 1
    }
    # A slow unload must not stop the script before it loads the agent again: under the health check, that would leave the engine down.
    launchctl bootout "$(agent_target llama)" 2>/dev/null || true
    wait_until_unloaded llama || true
    wait_for_engine_exit
    launchctl bootstrap "gui/$(id -u)" "$(plist_path llama)"
}

wait_for_engine_exit() {
    # Past the timeout the engine is stopped outright: two engines would each hold several GB of their own buffers.
    local half_seconds=0
    while pgrep -x "$STRATA_ENGINE_PROCESS" >/dev/null; do
        if ((half_seconds >= ENGINE_EXIT_TIMEOUT_SECONDS * 2)); then
            echo "Strata's engine still runs $ENGINE_EXIT_TIMEOUT_SECONDS s after its server stopped; killing it" >&2
            pkill -9 -x "$STRATA_ENGINE_PROCESS" || true
            return
        fi
        sleep 0.5
        half_seconds=$((half_seconds + 1))
    done
}

set_engine() {
    # The quick rollback at the keyboard: no commit, no deploy. The choice is checked before the engine restarts, and a refused one is undone.
    local choice="${1:-}" previous
    previous="$(cat "$ENGINE_OVERRIDE_FILE" 2>/dev/null || true)"
    case "$choice" in
    llama-server | strata) mkdir -p "$APP_SUPPORT_DIR" && echo "$choice" >"$ENGINE_OVERRIDE_FILE" ;;
    default) rm -f "$ENGINE_OVERRIDE_FILE" ;;
    *)
        echo "usage: scripts/services.sh engine llama-server|strata|default" >&2
        return 1
        ;;
    esac
    if ! { prepare_engine && "$SERVING_CLI" check; }; then
        if [[ -n "$previous" ]]; then echo "$previous" >"$ENGINE_OVERRIDE_FILE"; else rm -f "$ENGINE_OVERRIDE_FILE"; fi
        echo "the engine was not switched; the running one is untouched" >&2
        return 1
    fi
    restart_agent llama
    restart_agent harness
}

status() {
    # The exit code is the live state: 1 when an agent is not loaded or a port is not listening, which includes llama-server still loading its
    # model, since it is not serving yet. The last health snapshot is printed for reading but does not decide it: it can be minutes old.
    local name problems=0
    for name in "${SERVICES[@]}"; do
        if ! agent_loaded "$name"; then
            echo "$name: agent NOT loaded"
            problems=$((problems + 1))
        fi
    done
    local ports=("llama:8090" "mcp:8765" "harness:8770" "dashboard:8775" "speech:10300" "kokoro:10210")
    for entry in "${ports[@]}"; do
        local name="${entry%%:*}" port="${entry##*:}"
        if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
            echo "$name: listening on $port"
        else
            echo "$name: NOT listening on $port"
            problems=$((problems + 1))
        fi
    done
    agent_loaded health && echo "health: checks every $HEALTH_INTERVAL_SECONDS s"
    agent_loaded listings && printf 'listings: refreshes daily at %d:%02d; last: %s\n' "$LISTINGS_REFRESH_HOUR" "$LISTINGS_REFRESH_MINUTE" "$(tail -n 1 "$LOG_DIR/listings.log" 2>/dev/null || echo "not run yet")"
    agent_loaded newsletters && printf 'newsletters: pulls every %d s; last: %s\n' "$NEWSLETTERS_INTERVAL_SECONDS" "$(tail -n 1 "$LOG_DIR/newsletters.log" 2>/dev/null || echo "not run yet")"
    [[ -f "$LOG_DIR/maintenance" ]] && echo "MAINTENANCE FLAG SET: self-healing is off ($LOG_DIR/maintenance)"
    # --last exits 1 when the snapshot lists a failing part; that is past information, so it is shown and not counted.
    if [[ -f "$LOG_DIR/health.json" ]]; then
        "$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/scripts/health_check.py" --last || true
    fi
    ((problems == 0))
}

open_dashboard() {
    # Before install has written its agent, the dashboard runs in this terminal instead, so the command works on a fresh checkout too.
    local url="http://localhost:8775" name
    if [[ ! -f "$(plist_path dashboard)" ]]; then
        echo "no dashboard agent yet (scripts/services.sh install adds one); running it here until Ctrl-C"
        (sleep 2 && open "$url") &
        exec "$PROJECT_DIR/.venv/bin/exchange-dashboard"
    fi
    agent_loaded dashboard || launchctl bootstrap "gui/$(id -u)" "$(plist_path dashboard)"
    local half_seconds=0
    until lsof -nP -iTCP:8775 -sTCP:LISTEN >/dev/null 2>&1; do
        if ((half_seconds >= 20)); then
            echo "the dashboard is not listening on 8775 after 10 s; see scripts/services.sh logs dashboard" >&2
            return 1
        fi
        sleep 0.5
        half_seconds=$((half_seconds + 1))
    done
    name="$("$PROJECT_DIR/scripts/network_identity.sh" name 2>/dev/null || true)"
    echo "dashboard: $url${name:+ (from another computer at home: http://$name:8775)}"
    open "$url"
}

case "${1:-}" in
install) install_agents ;;
start) start_agents ;;
stop) stop_agents ;;
restart) restart_agent "${2:-}" ;;
engine) set_engine "${2:-}" ;;
status) status ;;
dashboard) open_dashboard ;;
logs) tail -n 50 -f "$LOG_DIR/${2:?service name}.log" ;;
uninstall)
    stop_agents
    for name in "${SERVICES[@]}"; do rm -f "$(plist_path "$name")"; done
    ;;
*) usage ;;
esac
