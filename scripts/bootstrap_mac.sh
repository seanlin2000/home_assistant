#!/usr/bin/env bash
# Set up the Mac that runs the assistant (design doc 10 section 3.2, v2/10 section 3.10). Idempotent: safe to run again after a partial failure.
#
#   bash bootstrap_mac.sh [--from FOLDER] [--repo URL] [--dir code/home_assistant_live] [--dry-run] [--skip-system] [--ref REF]
#
# Moving from another Mac: run scripts/export_to_new_mac.sh there, then run the copy of this script inside the export folder on this Mac, at its
# own keyboard:  bash /Volumes/<drive>/studio-assistant-move/bootstrap_mac.sh
# It restores the other Mac's settings, keys, history, Brave Search key and Home Assistant VM, points Home Assistant at this Mac, and asks the test
# question. Without an export folder it sets up the services alone, and --repo is required. Runs as the ordinary user; the system steps (power,
# firewall, SSH hardening) ask for that user's password through sudo once.
#   --from FOLDER   an export folder (default: the folder this script is in, when it holds manifest.txt)
#   --dir DIR       where the production checkout goes, relative to your home folder (default: code/home_assistant_live)
#   --dry-run       print every step, change nothing
#   --skip-system   everything except the sudo steps (used for the rehearsal on the laptop)
#   --ref REF       commit or branch to check out (default: origin/main)
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
FROM=""
REPO=""
TARGET_DIR="code/home_assistant_live"
REF="origin/main"
DRY_RUN=false
SKIP_SYSTEM=false
while [[ $# -gt 0 ]]; do
    case "$1" in
    --from)
        FROM="$2"
        shift 2
        ;;
    --repo)
        REPO="$2"
        shift 2
        ;;
    --dir)
        TARGET_DIR="$2"
        shift 2
        ;;
    --ref)
        REF="$2"
        shift 2
        ;;
    --dry-run) DRY_RUN=true && shift ;;
    --skip-system) SKIP_SYSTEM=true && shift ;;
    *)
        sed -n '2,16p' "$0"
        exit 1
        ;;
    esac
done
if [[ -z "$FROM" && -f "$HERE/manifest.txt" ]]; then FROM="$HERE"; fi
if [[ -n "$FROM" ]]; then
    FROM="$(cd "$FROM" && pwd)"
    [[ -f "$FROM/manifest.txt" ]] || {
        echo "$FROM is not an export folder (no manifest.txt); make one with scripts/export_to_new_mac.sh on the old Mac" >&2
        exit 1
    }
    [[ -n "$REPO" ]] || REPO="$(sed -n 's/^repo=//p' "$FROM/manifest.txt")"
fi
[[ -n "$REPO" ]] || {
    echo "--repo is required without an export folder" >&2
    exit 1
}
case "$TARGET_DIR" in /*) ;; *) TARGET_DIR="$HOME/$TARGET_DIR" ;; esac
BREWFILE="$HERE/Brewfile"
[[ -f "$BREWFILE" ]] || BREWFILE="$TARGET_DIR/Brewfile"
APP_SUPPORT_DIR="$HOME/Library/Application Support/studio-assistant"
LOG_DIR="$HOME/Library/Logs/studio-assistant"
VM_NAME="${HAOS_VM_NAME:-Home Assistant}"
# The Brave Search key's Keychain item, as web_search_mcp/brave_client.py reads it.
KEYCHAIN_SERVICE="studio-assistant"
KEYCHAIN_ACCOUNT="brave-search-api"
export PATH="/opt/homebrew/bin:$PATH"

step() { printf '\n==> %s\n' "$*"; }
run() {
    if $DRY_RUN; then echo "    (dry run) $*"; else "$@"; fi
}
as_root() {
    if $DRY_RUN; then echo "    (dry run) sudo $*"; else sudo "$@"; fi
}

restore_keeping_backup() {
    # $1 a file or folder from the export, $2 where it goes. Something different already there is kept beside it, so nothing on this Mac is lost.
    local source="$1" target="$2"
    if [[ -e "$target" ]] && diff -rq "$source" "$target" >/dev/null 2>&1; then
        echo "    $target already restored"
        return
    fi
    if [[ -e "$target" ]]; then
        local backup
        backup="$target.before-move-$(date +%Y%m%d-%H%M%S)"
        echo "    keeping this Mac's own copy as $backup"
        run mv "$target" "$backup"
    fi
    run mkdir -p "$(dirname "$target")"
    run ditto "$source" "$target"
}

store_brave_key() {
    # $1 the key file from the export. -U replaces an older key, so a rerun leaves one item.
    local key_file="$1"
    if $DRY_RUN; then
        echo "    (dry run) security add-generic-password -U -s $KEYCHAIN_SERVICE -a $KEYCHAIN_ACCOUNT -w <the key from $key_file>"
        return
    fi
    if security add-generic-password -U -s "$KEYCHAIN_SERVICE" -a "$KEYCHAIN_ACCOUNT" -w "$(cat "$key_file")"; then
        echo "    stored in the login Keychain"
    else
        echo "    the Keychain refused (it is locked over SSH); at this Mac's keyboard run:" >&2
        echo "      security add-generic-password -U -s $KEYCHAIN_SERVICE -a $KEYCHAIN_ACCOUNT -w" >&2
    fi
}

# ---------------------------------------------------------------- 1. tools
step "Xcode command line tools (git needs them)"
if ! xcode-select -p >/dev/null 2>&1; then
    run xcode-select --install
    echo "    approve the dialog on the screen, then run this script again"
    $DRY_RUN || exit 1
fi

step "Homebrew"
if ! command -v brew >/dev/null 2>&1; then
    run /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    eval "$(/opt/homebrew/bin/brew shellenv)"
fi

step "brew bundle from $BREWFILE"
run brew bundle --file="$BREWFILE" --no-upgrade

step "Python 3.12 for uv (the version uv.lock was resolved for)"
run uv python install 3.12

# ---------------------------------------------------------------- 2. the checkout
step "repository at $TARGET_DIR"
if [[ -d "$TARGET_DIR/.git" ]]; then
    run git -C "$TARGET_DIR" fetch --quiet origin
else
    run mkdir -p "$(dirname "$TARGET_DIR")"
    run git clone --quiet "$REPO" "$TARGET_DIR"
fi
# A detached checkout of an exact commit: the serving Mac never has a branch to drift on; a deploy moves it from one commit to the next.
run git -C "$TARGET_DIR" checkout --detach --quiet "$REF"

step "virtual environment (uv sync --locked)"
run "$TARGET_DIR/scripts/dev_setup.sh"

step "log directory"
run mkdir -p "$LOG_DIR/exchanges"

# ---------------------------------------------------------------- 3. what the old Mac had (before the services start, so they start with it)
if [[ -n "$FROM" ]]; then
    step "restoring from $FROM ($(sed -n 's/^from_mac=//p' "$FROM/manifest.txt"), exported $(sed -n 's/^exported_at=//p' "$FROM/manifest.txt"))"
    echo "    .env"
    restore_keeping_backup "$FROM/env" "$TARGET_DIR/.env"
    run chmod 600 "$TARGET_DIR/.env"
    if [[ -d "$FROM/app-support" ]]; then
        echo "    API keys, the harness database and the Brave spend log"
        restore_keeping_backup "$FROM/app-support" "$APP_SUPPORT_DIR"
    fi
    if [[ -d "$FROM/logs" ]]; then
        # Merged, never overwritten: a day this Mac already logged keeps its own file.
        echo "    the dashboard's history"
        run rsync -a --ignore-existing "$FROM/logs/" "$LOG_DIR/"
    fi
    if [[ -s "$FROM/brave-search-api.key" ]]; then
        echo "    the Brave Search key"
        store_brave_key "$FROM/brave-search-api.key"
    fi
fi

step "the model config/serving.toml serves (the first time this downloads tens of GB; a file already matching its hash is kept)"
run "$TARGET_DIR/.venv/bin/serving" fetch

# ---------------------------------------------------------------- 4. services
step "Docker Desktop and SearXNG (accept Docker's terms if it asks)"
if ! pgrep -xq Docker; then
    run open -g -a Docker
    $DRY_RUN || {
        printf '    waiting for the Docker engine'
        for _ in $(seq 1 60); do
            if "$TARGET_DIR/scripts/searxng.sh" status >/dev/null 2>&1 || /Applications/Docker.app/Contents/Resources/bin/docker info >/dev/null 2>&1; then break; fi
            printf '.'
            sleep 5
        done
        echo
    }
fi
run "$TARGET_DIR/scripts/searxng.sh" up

step "launchd agents: llama, mcp, harness, dashboard, whisper, kokoro, health, listings"
run "$TARGET_DIR/scripts/services.sh" install

step "Docker and UTM open at login (the VM and SearXNG must come back after a power cut)"
for app in Docker UTM; do
    run osascript -e "tell application \"System Events\" to if not (exists login item \"$app\") then make login item at end with properties {path:\"/Applications/$app.app\", hidden:true}"
done

# ---------------------------------------------------------------- 5. system settings (sudo)
if $SKIP_SYSTEM; then
    step "system settings skipped (--skip-system)"
else
    step "power: never sleep, restart after a power failure, wake on LAN"
    as_root pmset -a sleep 0 disksleep 0 displaysleep 5 autorestart 1 womp 1 powernap 0

    step "application firewall on, with the LAN-facing programs allowed (a headless machine cannot answer the per-app dialog)"
    FW=/usr/libexec/ApplicationFirewall/socketfilterfw
    as_root "$FW" --setglobalstate on
    as_root "$FW" --setstealthmode off
    for program in "$TARGET_DIR/.venv/bin/python" "$(readlink -f "$TARGET_DIR/.venv/bin/python")" /Applications/Docker.app /Applications/UTM.app; do
        [[ -e "$program" ]] || continue
        as_root "$FW" --add "$program"
        as_root "$FW" --unblockapp "$program"
    done

    step "SSH: only this user, keys only (only when this session came in over SSH)"
    DROPIN=/etc/ssh/sshd_config.d/010-studio-assistant.conf
    if [[ -s "$HOME/.ssh/authorized_keys" ]] && [[ -n "${SSH_CONNECTION:-}" || -n "${SSH_TTY:-}" ]]; then
        as_root dseditgroup -o edit -a "$USER" -t user com.apple.access_ssh
        # Written only when a key is installed and this session came in over SSH, so a typo cannot lock the laptop out.
        TMP="$(mktemp)"
        cat >"$TMP" <<EOF
# studio-assistant: LAN-only box, keys only. sshd keeps the first value it reads for each option and reads drop-ins in name order
# before the main file, so 010- wins over Apple's 100-macos.conf and over /etc/ssh/sshd_config.
PasswordAuthentication no
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
AllowUsers $USER
EOF
        as_root install -m 644 -o root -g wheel "$TMP" "$DROPIN"
        rm -f "$TMP"
        if $DRY_RUN || sudo sshd -t; then
            # Remote Login restarts sshd for us; launchd's ssh listener re-reads the config per connection, so no restart is needed.
            echo "    $DROPIN installed and validated"
        else
            echo "    sshd -t rejected the config; removing $DROPIN" >&2
            as_root rm -f "$DROPIN"
        fi
    else
        echo "    skipped: this Mac is set up at its own keyboard, and nothing here needs Remote Login"
    fi
fi

# ---------------------------------------------------------------- 6. Home Assistant
step "Home Assistant OS VM"
if [[ -d "$FROM/vm/$VM_NAME.utm" ]]; then
    echo "    allow Terminal to control UTM and to access its data if macOS asks"
    run "$TARGET_DIR/scripts/haos_vm.sh" register "$FROM/vm/$VM_NAME.utm"
    if $DRY_RUN || [[ "$(utmctl status "$VM_NAME" 2>/dev/null)" != "started" ]]; then
        run "$TARGET_DIR/scripts/haos_vm.sh" start
    fi
elif command -v utmctl >/dev/null && utmctl list 2>/dev/null | grep -q "$VM_NAME"; then
    echo "    VM already registered"
else
    echo "    no VM: move one with scripts/export_to_new_mac.sh on the old Mac, or create a fresh one:"
    echo "      HAOS_VM_MEMORY_MB=3072 $TARGET_DIR/scripts/haos_vm.sh create   (then uv run python scripts/ha_setup.py --host <its address>)"
fi

if [[ -n "$FROM" ]]; then
    step "pointing Home Assistant at this Mac (waits for it to boot; the first boot after a move takes a few minutes)"
    run bash -c "cd '$TARGET_DIR' && uv run python scripts/ha_setup.py --only integrations --only pipeline"

    step "the test question, through Home Assistant"
    run bash -c "cd '$TARGET_DIR' && uv run python -m ops.smoke"
fi

# ---------------------------------------------------------------- 7. what a person still has to do
ADDRESS="$("$TARGET_DIR/scripts/network_identity.sh" address 2>/dev/null || echo "this Mac's address")"
HARDWARE="$("$TARGET_DIR/scripts/network_identity.sh" hardware 2>/dev/null || echo "its hardware address")"
NAME="$("$TARGET_DIR/scripts/network_identity.sh" name 2>/dev/null || echo "this-mac.local")"
step "done. Left for you:"
cat <<EOF
    On the router: reserve $ADDRESS for this Mac ($HARDWARE), so Home Assistant keeps finding it.
      If Wi-Fi's "Private Wi-Fi address" is set to Rotating for your network, set it to Fixed or Off first.
    System Settings on this Mac (once):
      - Users & Groups -> Automatic login: $USER   (requires FileVault OFF: $(fdesetup status 2>/dev/null || echo 'unknown'))
      - General -> Software Update -> Automatic updates OFF (updates are applied on purpose, doc 08 section 6)
      - Privacy & Security: approve any "background items" prompt for the launchd agents
    The dashboard, from any computer at home: http://$NAME:8775
EOF
if [[ -n "$FROM" ]]; then
    cat <<EOF
    Delete $FROM once you are happy: it holds passwords and keys.
    Leave the old Mac's VM off: both copies have the same network address.
EOF
fi
