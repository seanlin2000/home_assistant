#!/usr/bin/env bash
# First-time setup of the Mac that runs the assistant (design doc 10 §3.2). Idempotent: safe to run again after a partial failure.
#
#   bash bootstrap_mac.sh --repo URL --dir code/home_assistant [--dry-run] [--skip-system] [--ref REF]
#
# Normally launched from the laptop by `scripts/mini.sh bootstrap`, after the ten minutes on a TV (user account, Wi-Fi, Remote Login on).
# Runs as the ordinary user; the system steps (power, firewall, SSH hardening) ask for that user's password through sudo once.
#   --dry-run       print every step, change nothing
#   --skip-system   everything except the sudo steps (used for the rehearsal on the laptop)
#   --ref REF       commit or branch to check out (default: origin/main)
set -euo pipefail

REPO=""
TARGET_DIR="code/home_assistant"
REF="origin/main"
DRY_RUN=false
SKIP_SYSTEM=false
while [[ $# -gt 0 ]]; do
    case "$1" in
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
        sed -n '2,11p' "$0"
        exit 1
        ;;
    esac
done
[[ -n "$REPO" ]] || {
    echo "--repo is required" >&2
    exit 1
}
case "$TARGET_DIR" in /*) ;; *) TARGET_DIR="$HOME/$TARGET_DIR" ;; esac
HERE="$(cd "$(dirname "$0")" && pwd)"
BREWFILE="$HERE/Brewfile"
[[ -f "$BREWFILE" ]] || BREWFILE="$TARGET_DIR/Brewfile"
export PATH="/opt/homebrew/bin:$PATH"

step() { printf '\n==> %s\n' "$*"; }
run() {
    if $DRY_RUN; then echo "    (dry run) $*"; else "$@"; fi
}
as_root() {
    if $DRY_RUN; then echo "    (dry run) sudo $*"; else sudo "$@"; fi
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
# A detached checkout of an exact commit: the mini never has a branch to drift on; ops.deploy moves it from one commit to the next.
run git -C "$TARGET_DIR" checkout --detach --quiet "$REF"

step "virtual environment (uv sync --frozen)"
run "$TARGET_DIR/scripts/dev_setup.sh"

step "log directory"
run mkdir -p "$HOME/Library/Logs/studio-assistant/turns"

# ---------------------------------------------------------------- 3. services
step "Docker Desktop and SearXNG"
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

step "launchd agents: ollama, mcp, whisper, kokoro, health"
run "$TARGET_DIR/scripts/services.sh" install

step "Docker and UTM open at login (the VM and SearXNG must come back after a power cut)"
for app in Docker UTM; do
    run osascript -e "tell application \"System Events\" to if not (exists login item \"$app\") then make login item at end with properties {path:\"/Applications/$app.app\", hidden:true}"
done

step "Home Assistant OS VM (3 GB on the mini; the model gets the rest of the memory)"
if command -v utmctl >/dev/null && utmctl list 2>/dev/null | grep -q "Home Assistant"; then
    echo "    VM already registered"
else
    echo "    no VM yet: either copy the laptop's bundle with 'scripts/mini.sh push-vm' (keeps the HA configuration and its MAC address)"
    echo "    or create a fresh one: HAOS_VM_MEMORY_MB=3072 $TARGET_DIR/scripts/haos_vm.sh create  (then scripts/ha_setup.py from the laptop)"
fi

# ---------------------------------------------------------------- 4. system settings (sudo)
if $SKIP_SYSTEM; then
    step "system settings skipped (--skip-system)"
else
    step "power: never sleep, restart after a power failure, wake on LAN"
    as_root pmset -a sleep 0 disksleep 0 displaysleep 5 autorestart 1 womp 1 powernap 0

    step "application firewall on, with the LAN-facing programs allowed (a headless machine cannot answer the per-app dialog)"
    FW=/usr/libexec/ApplicationFirewall/socketfilterfw
    as_root "$FW" --setglobalstate on
    as_root "$FW" --setstealthmode off
    for program in "$(command -v ollama)" "$TARGET_DIR/.venv/bin/python" "$(readlink -f "$TARGET_DIR/.venv/bin/python")" /Applications/Docker.app /Applications/UTM.app; do
        [[ -e "$program" ]] || continue
        as_root "$FW" --add "$program"
        as_root "$FW" --unblockapp "$program"
    done

    step "SSH: only this user, keys only"
    as_root dseditgroup -o edit -a "$USER" -t user com.apple.access_ssh
    DROPIN=/etc/ssh/sshd_config.d/010-studio-assistant.conf
    if [[ -s "$HOME/.ssh/authorized_keys" ]] && [[ -n "${SSH_CONNECTION:-}" || -n "${SSH_TTY:-}" ]]; then
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
        echo "    skipped: no ~/.ssh/authorized_keys yet or not connected over SSH. Run 'ssh-copy-id $USER@<this mac>' from the laptop, then rerun."
    fi
fi

# ---------------------------------------------------------------- 5. what a person still has to do
step "done. Left for the screen and the laptop:"
cat <<EOF
    System Settings on this Mac (once, with a screen attached):
      - Users & Groups -> Automatic login: $USER   (requires FileVault OFF: $(fdesetup status 2>/dev/null || echo 'unknown'))
      - General -> Sharing: Remote Login "only these users" should now list $USER; turn Screen Sharing OFF once bootstrap works
      - General -> Software Update -> Automatic updates OFF (updates are applied on purpose, doc 08 §6)
      - Open Docker once and accept its terms; open UTM once and allow it to run
      - Privacy & Security: approve any "background items" prompt for the launchd agents
    On the router: DHCP reservation for this Mac and for the VM's MAC address.
    Plug in the HDMI dummy plug before unplugging the screen.
    From the laptop:  scripts/mini.sh push-env ; push-models ; push-vm ; then scripts/haos_vm.sh start here ; then mini.sh status
EOF
