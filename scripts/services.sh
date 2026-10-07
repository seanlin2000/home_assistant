#!/usr/bin/env bash
# Install, start, stop, and inspect the native macOS services that Home Assistant talks to over the LAN.
#
#   scripts/services.sh install      write launchd agents for whisper, kokoro, mcp, ollama (LAN binding) and the 5-minute health check, and load them
#   scripts/services.sh start|stop   load/unload the agents
#   scripts/services.sh restart NAME restart one agent (ollama|mcp|whisper|kokoro|health)
#   scripts/services.sh status       show what is listening on each port and the last health snapshot
#   scripts/services.sh logs NAME    tail a service log (whisper|kokoro|mcp|ollama|health)
#   scripts/services.sh uninstall    unload and remove the agents
#
# Ports: Ollama 11434, Whisper 10300, Kokoro 10210, MCP 8765 (design_docs/v1/08 section 7). Everything binds 0.0.0.0 so the VM can reach it.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
AGENTS_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$HOME/Library/Logs/studio-assistant"
PREFIX="com.studio-assistant"
SERVICES=(ollama mcp whisper kokoro health)
HEALTH_INTERVAL_SECONDS="${HEALTH_INTERVAL_SECONDS:-300}"
UNLOAD_TIMEOUT_SECONDS="${UNLOAD_TIMEOUT_SECONDS:-30}"
OLLAMA_BIN="$(command -v ollama || echo /opt/homebrew/bin/ollama)"

usage() {
    sed -n '2,11p' "$0"
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
    # PLIST_START_INTERVAL=N makes a periodic job (launchd runs it every N seconds) instead of a kept-alive daemon.
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

install_agents() {
    mkdir -p "$AGENTS_DIR" "$LOG_DIR"
    prepare_kokoro
    # launchd keeps running the definition it loaded, so every agent is unloaded before its plist is rewritten; start_agents then loads the new ones.
    stop_agents
    # With the tool server stopped, nothing appends to the old turns/ folder while the exchange logs move out of it (a no-op once moved).
    # A failed move leaves the files where they were, so it must not stop the agents from coming back.
    "$PROJECT_DIR/.venv/bin/python" -m ops.legacy_exchange_logs "$LOG_DIR" || echo "warning: exchange logs not moved out of $LOG_DIR/turns; rerun: .venv/bin/python -m ops.legacy_exchange_logs" >&2
    # Ollama: Homebrew's service binds to localhost only; ours binds the LAN and keeps the model loaded.
    brew services stop ollama >/dev/null 2>&1 || true
    ENV_KEYS=(OLLAMA_HOST OLLAMA_KEEP_ALIVE OLLAMA_MAX_LOADED_MODELS) ENV_VALUES=(0.0.0.0:11434 -1 1)
    write_plist ollama "$OLLAMA_BIN" serve
    # Bound to the LAN, the tool server answers only requests that name this machine (Host header); a web page cannot reach it by DNS rebinding.
    # WEB_SEARCH_ALLOWED_HOSTS in the environment overrides the derived list (the mini's interface may not be en0). Rerun install after an address change.
    local lan_address
    lan_address="$(ipconfig getifaddr en0 2>/dev/null || true)"
    ENV_KEYS=(WEB_SEARCH_HOST WEB_SEARCH_PORT WEB_SEARCH_EXCHANGES_DIR WEB_SEARCH_ALLOWED_HOSTS)
    ENV_VALUES=(0.0.0.0 8765 "$LOG_DIR/exchanges" "${WEB_SEARCH_ALLOWED_HOSTS:-${lan_address:+$lan_address:8765,}localhost:8765,127.0.0.1:8765}")
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
    write_plist mcp "$PROJECT_DIR/.venv/bin/web-search-mcp"
    ENV_KEYS=() ENV_VALUES=()
    write_plist whisper "$PROJECT_DIR/.venv/bin/wyoming-mlx-whisper" --uri tcp://0.0.0.0:10300 --model mlx-community/whisper-large-v3-turbo --language en
    write_plist kokoro "$PROJECT_DIR/.venv/bin/kokoro-server" --uri tcp://0.0.0.0:10210 --voice bm_fable --data-dir "$HOME/.cache/wyoming-kokoro" --streaming --device cpu
    # HEALTH_CHECK_FLAGS="--no-remediate" installs an observe-only check (used on the laptop, where the VM is stopped on purpose most of the time).
    read -ra health_flags <<<"${HEALTH_CHECK_FLAGS:-}"
    # Bash 3.2, the one macOS ships, treats "${array[@]}" of an empty array as unbound under set -u; this form expands to nothing instead.
    PLIST_START_INTERVAL="$HEALTH_INTERVAL_SECONDS" write_plist health "$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/scripts/health_check.py" ${health_flags[@]+"${health_flags[@]}"}
    start_agents
}

start_agents() {
    # A loaded agent is restarted; an unloaded one is loaded from its plist. Any agent that fails either way is named and the command fails,
    # because a silent failure here once left the puck with no voice and only "NOT listening" in the status to show for it.
    local name error failed=()
    for name in "${SERVICES[@]}"; do
        [[ -f "$(plist_path "$name")" ]] || continue
        if agent_loaded "$name"; then
            error="$(launchctl kickstart -k "$(agent_target "$name")" 2>&1)" || failed+=("$name (${error%%$'\n'*})")
        else
            error="$(launchctl bootstrap "gui/$(id -u)" "$(plist_path "$name")" 2>&1)" || failed+=("$name (${error%%$'\n'*})")
        fi
    done
    sleep 2
    status
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
    launchctl kickstart -k "$(agent_target "$name")" 2>/dev/null || launchctl bootstrap "gui/$(id -u)" "$(plist_path "$name")"
    echo "restarted $name"
}

status() {
    local name
    for name in "${SERVICES[@]}"; do
        agent_loaded "$name" || echo "$name: agent NOT loaded"
    done
    local ports=("ollama:11434" "mcp:8765" "whisper:10300" "kokoro:10210")
    for entry in "${ports[@]}"; do
        local name="${entry%%:*}" port="${entry##*:}"
        if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
            echo "$name: listening on $port"
        else
            echo "$name: NOT listening on $port"
        fi
    done
    agent_loaded health && echo "health: checks every $HEALTH_INTERVAL_SECONDS s"
    [[ -f "$LOG_DIR/maintenance" ]] && echo "MAINTENANCE FLAG SET: self-healing is off ($LOG_DIR/maintenance)"
    if [[ -f "$LOG_DIR/health.json" ]]; then
        "$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/scripts/health_check.py" --last
    fi
}

case "${1:-}" in
install) install_agents ;;
start) start_agents ;;
stop) stop_agents ;;
restart) restart_agent "${2:-}" ;;
status) status ;;
logs) tail -n 50 -f "$LOG_DIR/${2:?service name}.log" ;;
uninstall)
    stop_agents
    for name in "${SERVICES[@]}"; do rm -f "$(plist_path "$name")"; done
    ;;
*) usage ;;
esac
