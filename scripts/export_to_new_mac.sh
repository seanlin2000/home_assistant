#!/usr/bin/env bash
# Pack everything a new Mac needs from this one into one folder, which scripts/bootstrap_mac.sh on the new Mac sets itself up from (design doc
# v2/10 section 3.10). Nothing travels over the network and the new Mac needs no Remote Login.
#
#   scripts/export_to_new_mac.sh DESTINATION [--dry-run]
#
# Run it on the Mac that serves today, from its production checkout (the one whose .env the services use). DESTINATION is a USB drive or any
# folder you can carry to the new Mac; the export goes into DESTINATION/studio-assistant-move. Then, on the new Mac, in Terminal:
#   bash /Volumes/<drive>/studio-assistant-move/bootstrap_mac.sh
#
# This Mac's services and Home Assistant VM are stopped first, because a copy of a running VM's disk is corrupt, and left stopped: both copies of
# the VM share one network address, so it must never run on two Macs. The folder holds .env's passwords, the API keys and the Brave Search key;
# delete it once the new Mac answers.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MOVE_FOLDER_NAME="studio-assistant-move"
VM_NAME="${HAOS_VM_NAME:-Home Assistant}"
VM_BUNDLE="$HOME/Library/Containers/com.utmapp.UTM/Data/Documents/$VM_NAME.utm"
APP_SUPPORT_DIR="$HOME/Library/Application Support/studio-assistant"
LOG_DIR="$HOME/Library/Logs/studio-assistant"
# The dashboard's history (ops/paths.py). Service logs, health state and deploy records describe this Mac and stay behind.
HISTORY_FOLDERS=(exchanges traces pipeline_runs)
# The Brave Search key's Keychain item, as web_search_mcp/brave_client.py reads it.
KEYCHAIN_SERVICE="studio-assistant"
KEYCHAIN_ACCOUNT="brave-search-api"

DESTINATION=""
DRY_RUN=false
while [[ $# -gt 0 ]]; do
    case "$1" in
    --dry-run) DRY_RUN=true && shift ;;
    -*)
        sed -n '2,14p' "$0"
        exit 1
        ;;
    *)
        DESTINATION="$1"
        shift
        ;;
    esac
done
[[ -n "$DESTINATION" ]] || {
    sed -n '2,14p' "$0"
    exit 1
}
MOVE_DIR="$DESTINATION/$MOVE_FOLDER_NAME"

step() { printf '\n==> %s\n' "$*"; }
run() {
    if $DRY_RUN; then echo "    (dry run) $*"; else "$@"; fi
}

refuse_unless_ready() {
    [[ -d "$DESTINATION" ]] || {
        echo "export: $DESTINATION is not a folder; plug in the drive or create the folder first" >&2
        exit 1
    }
    [[ ! -e "$MOVE_DIR" ]] || {
        echo "export: $MOVE_DIR already exists; delete it or choose another destination" >&2
        exit 1
    }
    [[ -f "$PROJECT_DIR/.env" ]] || {
        echo "export: no .env in $PROJECT_DIR; run this from the checkout the services run from" >&2
        exit 1
    }
}

refuse_unless_it_fits() {
    local needed_kb=0 available_kb path
    for path in "$VM_BUNDLE" "$APP_SUPPORT_DIR" "$LOG_DIR"; do
        if [[ -e "$path" ]]; then needed_kb=$((needed_kb + $(du -sk "$path" | cut -f1))); fi
    done
    available_kb="$(df -k "$DESTINATION" | awk 'NR==2{print $4}')"
    echo "    needs about $((needed_kb / 1024 / 1024 + 1)) GB; $((available_kb / 1024 / 1024)) GB free at $DESTINATION"
    ((available_kb > needed_kb)) || {
        echo "export: not enough space at $DESTINATION" >&2
        exit 1
    }
}

stop_vm() {
    command -v utmctl >/dev/null || return 0
    [[ "$(utmctl status "$VM_NAME" 2>/dev/null)" == "started" ]] || return 0
    run "$PROJECT_DIR/scripts/haos_vm.sh" stop
    $DRY_RUN && return 0
    local seconds=0
    until [[ "$(utmctl status "$VM_NAME" 2>/dev/null)" == "stopped" ]]; do
        if ((seconds >= 120)); then
            echo "export: the VM has not stopped after 120 s; stop it in UTM and run this again" >&2
            exit 1
        fi
        sleep 2
        seconds=$((seconds + 2))
    done
}

export_brave_key() {
    local key
    key="$(security find-generic-password -s "$KEYCHAIN_SERVICE" -a "$KEYCHAIN_ACCOUNT" -w 2>/dev/null || true)"
    if [[ -z "$key" ]]; then
        echo "    no Brave Search key in this Mac's Keychain; the new Mac searches with SearXNG until one is added"
        return
    fi
    if $DRY_RUN; then
        echo "    (dry run) write the Brave Search key to $MOVE_DIR/brave-search-api.key"
        return
    fi
    (umask 077 && printf '%s\n' "$key" >"$MOVE_DIR/brave-search-api.key")
}

write_manifest() {
    # bootstrap_mac.sh reads repo= from here, so the new Mac clones the same repository without being told.
    local manifest="$MOVE_DIR/manifest.txt"
    if $DRY_RUN; then
        echo "    (dry run) write $manifest"
        return
    fi
    cat >"$manifest" <<EOF
exported_at=$(date '+%Y-%m-%d %H:%M:%S %Z')
from_mac=$("$PROJECT_DIR/scripts/network_identity.sh" name 2>/dev/null || hostname)
repo=$(git -C "$PROJECT_DIR" remote get-url origin)
commit=$(git -C "$PROJECT_DIR" rev-parse HEAD)
vm=$([[ -d "$MOVE_DIR/vm/$VM_NAME.utm" ]] && echo yes || echo no)
brave_key=$([[ -s "$MOVE_DIR/brave-search-api.key" ]] && echo yes || echo no)
EOF
}

step "checking $DESTINATION"
refuse_unless_ready
refuse_unless_it_fits

step "stopping this Mac's services and its Home Assistant VM (they stay stopped: the VM must run on one Mac only)"
run "$PROJECT_DIR/scripts/services.sh" stop
stop_vm

step "the setup script, the Brewfile and the steps to follow, so the new Mac needs nothing else to start"
run mkdir -p "$MOVE_DIR"
run cp "$PROJECT_DIR/scripts/bootstrap_mac.sh" "$PROJECT_DIR/Brewfile" "$MOVE_DIR/"
run cp "$PROJECT_DIR/docs/MOVING_TO_A_NEW_MAC.md" "$MOVE_DIR/README.md"

step ".env: addresses, passwords and the Home Assistant token"
run cp "$PROJECT_DIR/.env" "$MOVE_DIR/env"
run chmod 600 "$MOVE_DIR/env"

step "API keys, the harness database and the Brave spend log ($APP_SUPPORT_DIR)"
if [[ -d "$APP_SUPPORT_DIR" ]]; then run ditto "$APP_SUPPORT_DIR" "$MOVE_DIR/app-support"; fi

step "the dashboard's history"
for folder in "${HISTORY_FOLDERS[@]}"; do
    if [[ -d "$LOG_DIR/$folder" ]]; then run ditto "$LOG_DIR/$folder" "$MOVE_DIR/logs/$folder"; fi
done

step "the Brave Search key from the Keychain"
export_brave_key

step "the Home Assistant VM"
if [[ -d "$VM_BUNDLE" ]]; then
    echo "    copying $(du -sh "$VM_BUNDLE" | cut -f1); this takes a few minutes"
    run ditto "$VM_BUNDLE" "$MOVE_DIR/vm/$VM_NAME.utm"
else
    echo "    no VM at $VM_BUNDLE; the new Mac will need one made with scripts/haos_vm.sh create"
fi

write_manifest

step "done"
cat <<EOF
    Exported to $MOVE_DIR
    On the new Mac, open Terminal and run:
      bash "$MOVE_DIR/bootstrap_mac.sh"
    This Mac's services and VM are stopped. Leave the VM off from now on.
    The folder holds passwords and keys: delete it once the new Mac answers.
EOF
