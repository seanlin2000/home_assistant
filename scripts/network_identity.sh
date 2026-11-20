#!/usr/bin/env bash
# How this Mac appears on the home network, read from whichever interface carries the default route (Wi-Fi or Ethernet, whatever its en number).
#
#   scripts/network_identity.sh interface   the interface name, such as en1
#   scripts/network_identity.sh address     its IPv4 address, such as 192.168.1.162
#   scripts/network_identity.sh name        the Bonjour name other devices can use, such as Seans-Mac-Studio.local
#   scripts/network_identity.sh hardware    the interface's hardware (MAC) address, which a router reservation is keyed on
#
# The one place the scripts and scripts/ha_setup.py learn the Mac's address: a Mac Studio's Wi-Fi is en1, a MacBook's is en0.
set -euo pipefail

default_interface() {
    route -n get default 2>/dev/null | awk '/interface:/{print $2}'
}

require_interface() {
    local interface
    interface="$(default_interface)"
    if [[ -z "$interface" ]]; then
        echo "network_identity: no default route; is this Mac on the network?" >&2
        exit 1
    fi
    echo "$interface"
}

case "${1:-}" in
interface) require_interface ;;
address) ipconfig getifaddr "$(require_interface)" ;;
name) echo "$(scutil --get LocalHostName).local" ;;
hardware) ifconfig "$(require_interface)" | awk '/ether /{print $2; exit}' ;;
*)
    sed -n '2,9p' "$0"
    exit 1
    ;;
esac
