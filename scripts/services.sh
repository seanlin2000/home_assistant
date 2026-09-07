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
OLLAMA_BIN="$(command -v ollama || echo /opt/homebrew/bin/ollama)"

usage() {
    sed -n '2,11p' "$0"
    exit 1
}

plist_path() { echo "$AGENTS_DIR/$PREFIX.$1.plist"; }

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
    # Ollama: Homebrew's service binds to localhost only; ours binds the LAN and keeps the model loaded.
    brew services stop ollama >/dev/null 2>&1 || true
    ENV_KEYS=(OLLAMA_HOST OLLAMA_KEEP_ALIVE OLLAMA_MAX_LOADED_MODELS) ENV_VALUES=(0.0.0.0:11434 -1 1)
    write_plist ollama "$OLLAMA_BIN" serve
    # Bound to the LAN, the tool server answers only requests that name this machine (Host header); a web page cannot reach it by DNS rebinding.
    # WEB_SEARCH_ALLOWED_HOSTS in the environment overrides the derived list (the mini's interface may not be en0). Rerun install after an address change.
    local lan_address
    lan_address="$(ipconfig getifaddr en0 2>/dev/null || true)"
    ENV_KEYS=(WEB_SEARCH_HOST WEB_SEARCH_PORT WEB_SEARCH_TURNS_DIR WEB_SEARCH_ALLOWED_HOSTS)
    ENV_VALUES=(0.0.0.0 8765 "$LOG_DIR/turns" "${WEB_SEARCH_ALLOWED_HOSTS:-${lan_address:+$lan_address:8765,}localhost:8765,127.0.0.1:8765}")
    write_plist mcp "$PROJECT_DIR/.venv/bin/web-search-mcp"
    ENV_KEYS=() ENV_VALUES=()
    write_plist whisper "$PROJECT_DIR/.venv/bin/wyoming-mlx-whisper" --uri tcp://0.0.0.0:10300 --model mlx-community/whisper-large-v3-turbo --language en
    write_plist kokoro "$PROJECT_DIR/.venv/bin/kokoro-server" --uri tcp://0.0.0.0:10210 --voice af_heart --data-dir "$HOME/.cache/wyoming-kokoro" --streaming --device cpu
    # HEALTH_CHECK_FLAGS="--no-remediate" installs an observe-only check (used on the laptop, where the VM is stopped on purpose most of the time).
    read -ra health_flags <<<"${HEALTH_CHECK_FLAGS:-}"
    PLIST_START_INTERVAL="$HEALTH_INTERVAL_SECONDS" write_plist health "$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/scripts/health_check.py" "${health_flags[@]}"
    start_agents
}

start_agents() {
    for name in "${SERVICES[@]}"; do
        [[ -f "$(plist_path "$name")" ]] && launchctl bootstrap "gui/$(id -u)" "$(plist_path "$name")" 2>/dev/null || launchctl kickstart -k "gui/$(id -u)/$PREFIX.$name" 2>/dev/null || true
    done
    sleep 2
    status
}

stop_agents() {
    for name in "${SERVICES[@]}"; do
        launchctl bootout "gui/$(id -u)/$PREFIX.$name" 2>/dev/null || true
    done
}

restart_agent() {
    local name="${1:?service name}"
    launchctl kickstart -k "gui/$(id -u)/$PREFIX.$name" 2>/dev/null || launchctl bootstrap "gui/$(id -u)" "$(plist_path "$name")"
    echo "restarted $name"
}

status() {
    local ports=("ollama:11434" "mcp:8765" "whisper:10300" "kokoro:10210")
    for entry in "${ports[@]}"; do
        local name="${entry%%:*}" port="${entry##*:}"
        if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
            echo "$name: listening on $port"
        else
            echo "$name: NOT listening on $port"
        fi
    done
    if launchctl print "gui/$(id -u)/$PREFIX.health" >/dev/null 2>&1; then
        echo "health: checks every $HEALTH_INTERVAL_SECONDS s"
    else
        echo "health: agent NOT loaded"
    fi
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
