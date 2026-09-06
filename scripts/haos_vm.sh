#!/usr/bin/env bash
# Create and control the Home Assistant OS virtual machine in UTM from the command line.
#
#   scripts/haos_vm.sh create [image.qcow2.xz]   create the VM from the HAOS disk image (bridged network, UEFI, 4 GB, 2 cores)
#   scripts/haos_vm.sh start | stop | status      control it (utmctl)
#   scripts/haos_vm.sh ip                         resolve homeassistant.local on the LAN
#   scripts/haos_vm.sh delete                     remove the VM and its disk (asks for confirmation)
#
# Requires UTM (brew install --cask utm). The design (design_docs/v1/06) calls for bridged networking so the VM has its own LAN address and mDNS works.
set -euo pipefail

VM_NAME="${HAOS_VM_NAME:-Home Assistant}"
VM_MEMORY_MB="${HAOS_VM_MEMORY_MB:-4096}"
VM_CPUS="${HAOS_VM_CPUS:-2}"
BRIDGE_INTERFACE="${HAOS_BRIDGE_INTERFACE:-$(route -n get default 2>/dev/null | awk '/interface:/{print $2}')}"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEFAULT_IMAGE_XZ="$PROJECT_DIR/vm/haos_generic-aarch64-18.2.qcow2.xz"

usage() {
    sed -n '2,10p' "$0"
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
