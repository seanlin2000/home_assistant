# 08. Hardware and deployment

## 1. Purpose

The always-on machine and where each service runs on it. The prototype runs on the 16 GB M1 Pro MacBook; the production machine is a Mac mini whose tier the benchmark decides. This doc explains why a Mac mini over a Linux box with a graphics card, how memory decides the tier, which services run natively versus in a VM versus in Docker and why, and how everything comes back after a reboot.

## 2. Diagram

```
  Mac mini (silent, ~4 W idle, on a shelf)
  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐
  │ macOS                                                                                        │
  │                                                                                              │
  │  native processes (launchd, start at login)          UTM VM (bridged)      Docker Desktop    │
  │  ┌──────────────────────────────────────────┐        ┌────────────────┐    ┌──────────────┐  │
  │  │ Ollama (launchd)           GPU via MLX    │        │ Home Assistant │    │ SearXNG      │  │
  │  │ wyoming-mlx-whisper (.venv) GPU via MLX   │◀──LAN──│ OS + add-ons   │    │ localhost    │  │
  │  │ Kokoro Wyoming server (.venv) CPU         │        │ ESPHome, Piper,│    │ :8080        │  │
  │  │ web_search_mcp (.venv)      CPU ──────────┼────────┼────────────────┼───▶│              │  │
  │  └──────────────────────────────────────────┘        │ Music Assistant│    └──────────────┘  │
  │                                                      └────────────────┘                      │
  │  why here: Metal acceleration only works             why a VM: add-ons   why Docker: SearXNG  │
  │  for native processes                                 and mDNS           ships as an image    │
  └─────────────────────────────────────────────────────────────────────────────────────────────┘
        │ Wi-Fi                                   │ Wi-Fi
   Voice PE puck                             Sonos Era 100 SL
```

## 3. Placement rules and why

| Service | Where | Why |
|---|---|---|
| Ollama | Native | GPU acceleration through Metal is only available to native processes. A container or VM on macOS cannot use the GPU. |
| Whisper (MLX) | Native, from `.venv` | Same reason. |
| Kokoro | Native, from `.venv` | CPU is enough; native keeps it simple and lets it use MLX later. |
| `web_search_mcp` | Native, from `.venv` | Easiest to debug and to run under the project's pinned dependencies. A Dockerfile is provided for portability. |
| SearXNG | Docker Desktop | Distributed as a container image; no GPU needed; bound to localhost. |
| Home Assistant OS | UTM VM, bridged | Add-ons require the OS image; discovery requires a real LAN presence. Docker Desktop on macOS has no host networking. |
| Piper | Home Assistant add-on inside the VM | One click; CPU is enough. |
| Music Assistant, ESPHome | Add-ons inside the VM | Same. |

## 4. Choosing the machine

### Why a Mac mini

- Unified memory: a 32 GB Mac holds a 16 to 20 GB model next to the speech models and the VM. A consumer graphics card tops out at 16 or 24 GB of dedicated memory.
- The M5 and M6 chips' neural accelerators cut time to first token three to four times versus the M4. After a search puts thousands of tokens of page text in the prompt, that is the difference between a 2-second and an 8-second pause.
- Silent and about 4 W idle, 30 to 40 W under inference. In a 500 square foot studio a fan-cooled GPU box at 300 W is heat and noise you live with.
- The prototype MacBook and the production Mac mini run the same software the same way, so the proof of concept transfers without a rewrite.

### Tiers

| Tier | Machine | Total with puck and Sonos | Runs comfortably |
|---|---|---|---|
| Budget | Mac mini M6, 24 GB / 256 GB, $1,100 | ~$1,360 | Gemma 4 E4B, Qwen 3.5-9B at full precision; Gemma 4 26B-A4B only at 3-bit with a small context |
| Mid | Mac mini M6, 32 GB / 256 GB, $1,300 | ~$1,560 | Gemma 4 26B-A4B at 4-bit with 16k context; Qwen 3.6-35B-A3B at 4-bit if the VM is trimmed; Qwen 3.6-27B dense at ~10 tok/s |
| High | Mac mini M5 Pro, 48 GB, ~$2,100 (verify configurator) | ~$2,360 | Qwen 3.6-35B-A3B at 8-bit, Gemma 4 31B dense at ~20 tok/s, roughly double the memory bandwidth |
| Alternative | Linux PC with a used RTX 3090 24 GB | ~$1,600 to $1,900 | 26B MoE at 60+ tok/s; loud, hot, 300 W, do-it-yourself Linux |
| Not recommended | Refurbished M4 Mac mini 16 GB, $849 | ~$1,110 | Same limits as the prototype MacBook, no neural accelerators |

Apple announced the M6 and M5 Pro Mac minis on August 25, 2026, shipping September 22, at $100 above the M4 generation. The 16 GB M6 has lower memory bandwidth than the 24 and 32 GB configurations and is not considered.

### Memory budget for the mid tier

| Resident item | Memory |
|---|---|
| macOS and system | ~3 GB |
| Home Assistant VM, given 3,072 MB | 3 to 4 GB |
| Gemma 4 26B-A4B, 4-bit weights | ~16 GB |
| KV cache at 16k context | 1 to 2 GB |
| Whisper large-v3-turbo | ~1.6 GB |
| Kokoro and Piper | <1 GB |
| **Total** | **~25 to 27 GB** |

This is why 24 GB is the budget tier and not the default: the target-class model does not fit next to everything else with headroom.

The VM row is the least certain. `scripts/bootstrap_mac.sh` has the mini's VM created with `HAOS_VM_MEMORY_MB=3072`, but on the 16 GB prototype, where `scripts/haos_vm.sh` gives the VM its default 4,096 MB, the QEMU process holds about 7.5 GB (doc 06 §11).

## 5. Bill of materials

| Item | Cost |
|---|---|
| Mac mini M6, 24 or 32 GB | $1,100 or $1,300 |
| Home Assistant Voice Preview Edition | $69 |
| USB-C power supply for the puck, if no spare | ~$10 |
| Sonos Era 100 SL | $189 |
| Ethernet cable to the router (optional, recommended for the Mac) | ~$10 |
| **Total** | **~$1,380 to $1,580** |

Running cost: Mac mini averaging 8 W, puck 1.5 W, Sonos 2 W idle, about 100 kWh a year, roughly $2.50 a month at $0.30/kWh.

## 6. Coming back after a reboot

- Native services: `scripts/services.sh install` writes one launchd agent per service, `~/Library/LaunchAgents/com.studio-assistant.<name>.plist`, and loads it. Ollama, the MCP server, Whisper, and Kokoro each get `RunAtLoad` and `KeepAlive`; the program is `ollama serve` or the `.venv` command, by absolute path. Logs go to `~/Library/Logs/studio-assistant/<name>.log`.
- Ollama: our launchd agent, not Homebrew's service, which `services.sh install` stops because it binds localhost only. The agent sets `OLLAMA_HOST=0.0.0.0:11434`, `OLLAMA_KEEP_ALIVE=-1` so the model is loaded once and stays, and `OLLAMA_MAX_LOADED_MODELS=1`.
- Docker Desktop: a login item, registered by `scripts/bootstrap_mac.sh`; the SearXNG compose file has `restart: unless-stopped`.
- UTM: a login item, registered by `scripts/bootstrap_mac.sh`; opening UTM does not start the VM. The health check, a fifth launchd agent that runs at login and then every 300 seconds (`StartInterval`), starts the VM with `utmctl start` whenever `utmctl status` is not `started`, and stops and starts it when the Home Assistant API has failed five checks in a row (25 minutes) while the VM runs. Thresholds and cooldowns are in doc 10 §3.5.
- macOS: automatic login enabled, sleep disabled, "start up automatically after a power failure" enabled. Automatic OS updates off; updates are applied deliberately after the monthly Home Assistant update.

## 7. Networking

- The Mac on Ethernet if the router is within reach, otherwise Wi-Fi. Fixed IP reservation on the router for the Mac, the VM, the puck, and the Sonos.
- Everything listens on the LAN only. No port forwarding, no cloud relay.
- Ports (fixed in `scripts/services.sh` and `docker/searxng/docker-compose.yml`): Ollama 11434, Whisper 10300, Kokoro 10210, and the MCP server 8765 on all of the Mac's addresses; SearXNG 8080 on localhost only; Home Assistant 80 on the VM's address.
- Piper has no port on the LAN. It is an add-on inside the VM, and Home Assistant finds it through the Supervisor's add-on discovery, which `scripts/ha_setup.py` only confirms.

## 8. Failure modes

- **Memory pressure after a model or Home Assistant update grows.** Check with `ollama ps` and Activity Monitor; drop context length or VM memory before dropping the model.
- **Thermal throttling.** Not an issue for the Mac mini at these loads.
- **Wi-Fi congestion.** Audio streaming from the puck is small; music to the Sonos is larger. Ethernet for the Mac removes it from the equation.
- **Power outage.** Everything autostarts; the puck and Sonos come back on their own.
- **macOS update breaks a launchd agent.** The health snapshot names the failing agent; `scripts/services.sh install` rewrites every plist from its template and reloads it.

## 9. Concepts for newcomers

**Unified memory.** One pool shared by CPU and GPU on Apple Silicon. The number that decides which models fit.

**Memory bandwidth.** How fast data moves between memory and the processor, in GB/s. Sets token generation speed for a given model size.

**Neural accelerators.** Matrix-multiply units inside each GPU core on the M5 and M6, used by MLX for prompt processing.

**Metal.** Apple's GPU programming interface. Only reachable from native macOS processes, which dictates the placement rules above.

**launchd.** macOS's service manager. A plist file describes a program to run at login and keep alive; the equivalent of systemd on Linux.

**UTM.** A free virtualization app for macOS built on Apple's hypervisor. Runs the Home Assistant OS disk image as a virtual machine.

**Bridged networking.** The VM gets its own IP on the Wi-Fi like a separate physical machine, which is what makes device discovery work.

**Docker Desktop on macOS.** Runs Linux containers inside a hidden Linux VM. Convenient, but containers cannot see the GPU and, on macOS, cannot share the host network, which is why the GPU services and Home Assistant do not run there.

## 10. Sources

- Mac mini M6 and M5 Pro announcement and configurations: [MacRumors](https://www.macrumors.com/2026/08/25/apple-announces-2026-mac-mini/), [Daring Fireball pricing table](https://daringfireball.net/2026/08/configurations_and_pricing_for_new_mac_minis_and_mac_studios), [MindStudio specs](https://www.mindstudio.ai/blog/apple-mac-studio-mini-pricing-specs)
- Refurbished M4 Mac mini pricing: [9to5Toys](https://9to5toys.com/2026/08/26/rare-deal-m4-mac-mini-apple-refurb/)
- Apple M5 neural accelerators and time to first token: [machinelearning.apple.com](https://machinelearning.apple.com/research/exploring-llms-mlx-m5)
- Home Assistant OS on macOS with UTM: [home-assistant.io/installation/macos](https://www.home-assistant.io/installation/macos)
- Gemma 4 26B-A4B quantization sizes: [unsloth GGUF page](https://huggingface.co/unsloth/gemma-4-26B-A4B-it-GGUF)

## 11. As built, 2026-09-06: deploying into the VM

- The component reaches the VM over SMB: the Samba add-on shares `/config`, and `scripts/deploy_component.py` mounts it with `mount_smbfs` at a temporary path, copies the staged tree, and unmounts. Credentials come from `.env` (`HA_SAMBA_USER`, `HA_SAMBA_PASSWORD`); the share is reachable from private address ranges only.
- **A hung SMB mount blocks everything that touches it.** While the VM was saturated pulling add-on images, one deploy's mount stopped answering. On macOS a stalled SMB mount lives in the kernel: `umount`, `diskutil unmount force`, and even `ls` on the path block forever, a second mount of the same share fails with "File exists" whatever hostname is used, and only `sudo umount -f` (or a reboot) clears it. Restarting the Samba add-on on the VM side did not help. Rule for the future: do not deploy while the Supervisor is installing add-ons, and if a mount hangs, stop and clear it as root before retrying.
- Home Assistant's own Python (3.14 in core 2026.9.1) pins `mcp==1.26.0`, `httpx==0.28.1`, and `pydantic==2.13.4`. Anything vendored into the component must import cleanly against those; the project venv keeps `mcp` 2.x for the benchmark. See doc 04 §13.
- Ollama, the MCP server, Whisper, and Kokoro must listen on the Mac's LAN address (`0.0.0.0`), and macOS asks once, per binary, whether to allow incoming connections; the answer must be "allow" or the VM's calls time out.
