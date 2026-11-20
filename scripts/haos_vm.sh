#!/usr/bin/env bash
# Create and control the Home Assistant OS virtual machine in UTM from the command line.
#
#   scripts/haos_vm.sh create [image.qcow2.xz]   create the VM from the HAOS disk image (bridged network, UEFI, 4 GB, 2 cores)
#   scripts/haos_vm.sh register BUNDLE            take in a VM copied from another Mac: bridge it to this Mac's network and add it to UTM
#   scripts/haos_vm.sh start | stop | status      control it (utmctl)
#   scripts/haos_vm.sh ip                         resolve homeassistant.local on the LAN
#   scripts/haos_vm.sh delete                     remove the VM and its disk (asks for confirmation)
#
# Requires UTM (brew install --cask utm). The design (design_docs/v1/06) calls for bridged networking so the VM has its own LAN address and mDNS works.
set -euo pipefail

VM_NAME="${HAOS_VM_NAME:-Home Assistant}"
VM_MEMORY_MB="${HAOS_VM_MEMORY_MB:-4096}"
VM_CPUS="${HAOS_VM_CPUS:-2}"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BRIDGE_INTERFACE="${HAOS_BRIDGE_INTERFACE:-$("$PROJECT_DIR/scripts/network_identity.sh" interface 2>/dev/null || true)}"
# Where UTM keeps the VMs it made; a VM copied from another Mac goes here too.
UTM_DOCUMENTS="$HOME/Library/Containers/com.utmapp.UTM/Data/Documents"
DEFAULT_IMAGE_XZ="$PROJECT_DIR/vm/haos_generic-aarch64-18.2.qcow2.xz"

usage() {
    sed -n '2,11p' "$0"
    exit 1
}

ensure_utm() {
    if ! command -v utmctl >/dev/null 2>&1; then
        echo "utmctl not found; install UTM with: brew install --cask utm" >&2
        exit 1
    fi
    open -g -a UTM
    sleep 3
}

vm_exists() {
    utmctl list 2>/dev/null | awk -v name="$VM_NAME" 'NR>1 { $1=""; $2=""; sub(/^  */, ""); if ($0 == name) found=1 } END { exit !found }'
}

create_vm() {
    local image_xz="${1:-$DEFAULT_IMAGE_XZ}"
    local image="${image_xz%.xz}"
    ensure_utm
    if vm_exists; then
        echo "VM '$VM_NAME' already exists"
        exit 0
    fi
    if [[ ! -f "$image" ]]; then
        echo "decompressing $image_xz"
        xz -dk "$image_xz"
    fi
    echo "creating '$VM_NAME': ${VM_MEMORY_MB} MB, ${VM_CPUS} cores, bridged on ${BRIDGE_INTERFACE}, disk $(du -h "$image" | cut -f1)"
    osascript <<EOF
tell application "UTM"
	set diskImage to POSIX file "$image"
	set newVM to make new virtual machine with properties {backend:qemu, configuration:{name:"$VM_NAME", notes:"Home Assistant OS, created by scripts/haos_vm.sh", architecture:"aarch64", memory:$VM_MEMORY_MB, cpu cores:$VM_CPUS, uefi:true, hypervisor:true, drives:{{source:diskImage, interface:virtio}}, network interfaces:{{mode:bridged, host interface:"$BRIDGE_INTERFACE"}}}}
	return id of newVM
end tell
EOF
    echo "created. start it with: $0 start"
}

register_vm() {
    # $1 a .utm bundle copied from another Mac (scripts/export_to_new_mac.sh). It keeps its network card's MAC address, so the router gives it the
    # same LAN address as before, but its bridge still names the old Mac's interface: a MacBook's Wi-Fi is en0, a Mac Studio's en0 is Ethernet.
    local source="${1:?VM bundle to register}" bundle="$UTM_DOCUMENTS/$VM_NAME.utm"
    ensure_utm
    if vm_exists; then
        echo "VM '$VM_NAME' is already in UTM; leaving it as it is"
        return
    fi
    if [[ ! -d "$bundle" ]]; then
        echo "copying the VM into UTM's folder ($(du -sh "$source" | cut -f1)); allow Terminal to access UTM's data if macOS asks"
        mkdir -p "$UTM_DOCUMENTS"
        ditto "$source" "$bundle"
    fi
    bridge_to_this_mac "$bundle/config.plist"
    # UTM 5 lists only the VMs it has opened, not every bundle in its folder; opening the bundle adds it in place.
    open -a UTM "$bundle"
    local seconds=0
    until vm_exists; do
        if ((seconds >= 60)); then
            echo "UTM did not list '$VM_NAME' within 60 s; if macOS asked whether Terminal may control UTM, allow it and run this again" >&2
            exit 1
        fi
        sleep 1
        seconds=$((seconds + 1))
    done
    echo "registered '$VM_NAME', bridged on $BRIDGE_INTERFACE"
}

bridge_to_this_mac() {
    # $1 the VM's config.plist, edited before UTM has opened it, so UTM never holds the old setting.
    local config="$1" current
    current="$(plutil -extract Network.0.BridgeInterface raw "$config" 2>/dev/null || true)"
    if [[ -z "$current" || "$current" == "$BRIDGE_INTERFACE" ]]; then
        return
    fi
    plutil -replace Network.0.BridgeInterface -string "$BRIDGE_INTERFACE" "$config"
    echo "bridged the VM to $BRIDGE_INTERFACE (it was on $current on the old Mac)"
}

resolve_ip() {
    local host="${HAOS_HOSTNAME:-homeassistant.local}"
    local ip
    ip="$(dscacheutil -q host -a name "$host" 2>/dev/null | awk '/ip_address/{print $2; exit}')"
    if [[ -z "$ip" ]]; then
        ip="$(ping -c 1 -t 2 "$host" 2>/dev/null | awk -F'[()]' 'NR==1{print $2}')"
    fi
    if [[ -z "$ip" ]]; then
        echo "could not resolve $host yet (the VM takes a few minutes on first boot)" >&2
        exit 1
    fi
    echo "$ip"
}

case "${1:-}" in
create) create_vm "${2:-}" ;;
register) register_vm "${2:-}" ;;
start)
    ensure_utm
    utmctl start "$VM_NAME"
    ;;
stop) utmctl stop "$VM_NAME" ;;
status) utmctl status "$VM_NAME" ;;
ip) resolve_ip ;;
delete)
    read -r -p "Delete VM '$VM_NAME' and its disk? [y/N] " answer
    [[ "$answer" == "y" ]] && utmctl delete "$VM_NAME"
    ;;
*) usage ;;
esac
