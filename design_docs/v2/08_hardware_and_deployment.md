# 08. Hardware and deployment

Status: designed 2026-10-08

## 1. Purpose

Where each part of v2 runs on the Mac, who can reach it, and how much memory it takes. v2 adds two services, llama-server and the harness, and removes Ollama. It also closes every port that only the Mac itself needs, so that the home network can reach only what the Home Assistant VM and your laptop actually use.

v1/08 still applies to everything this doc does not change:
- why a Mac, rather than a Linux box with a graphics card;
- why Home Assistant runs in a UTM VM and SearXNG in Docker;
- how each part comes back after a reboot;
- what happens when the Wi-Fi or the power fails.

The new Mac is chosen separately and is not discussed here. When it arrives, its column in the memory budget (3.3) is filled in from measurements, in M8.

## 2. Diagram

```
 HOME NETWORK                 ┌─ MAC: ON ITS NETWORK ADDRESS ───────────┐
                              │                                         │
 ╭────────────────────╮       │speech   ╭────────────────────╮          │
 │ Home Assistant VM  │───────┼────────▶│      Whisper       │          │
 │  its own address   │       │         │       :10300       │          │
 │                    │       │         ╰────────────────────╯          │       ┌─ MAC: ON 127.0.0.1 ONLY ──────────────────────────────────────┐
 │                    │       │                                         │       │                                                               │
 │                    │       │question ╭────────────────────╮ prompts  │       │        ╭────────────────────╮                                 │
 │                    │───────┼────────▶│      harness       │──────────┼───────┼───────▶│    llama-server    │                                 │
 │                    │       │         │   :8770, API key   │──────────┼───┐   │        │   :8090, API key   │                                 │
 │                    │       │         ╰────────────────────╯          │   │   │        ╰────────────────────╯                                 │
 │                    │       │                                         │   │   │                                                               │
 │                    │       │text     ╭────────────────────╮          │   │   │tools   ╭────────────────────╮ queries╭────────────────────╮   │
 │                    │───────┼────────▶│       Kokoro       │          │   └───┼───────▶│    tool server     │───────▶│      SearXNG       │   │
 │                    │       │         │       :10210       │          │       │        │       :8765        │        │   :8080, Docker    │   │
 ╰────────────────────╯       │         ╰────────────────────╯          │       │        ╰────────────────────╯        ╰────────────────────╯   │
                              │                                         │       │                                                               │
 ╭────────────────────╮       │deploys  ╭────────────────────╮          │       └───────────────────────────────────────────────────────────────┘
 │    your laptop     │───────┼────────▶│        SSH         │          │
 │                    │       │         │   :22, keys only   │          │
 ╰────────────────────╯       │         ╰────────────────────╯          │
                              └─────────────────────────────────────────┘
```

The middle column follows a spoken question in order:
1. Home Assistant sends your speech to Whisper and gets back text.
2. It sends the question to the harness, which uses llama-server and the tool server on the right.
3. It sends the response text to Kokoro to be spoken.

Nothing on the right can be reached from another device.

## 3. How it works, step by step

### 3.1 What runs where

Every part still runs where v1/08 §3 put it, for the same reasons. What changes:

| Part | Where | Change from v1 |
|---|---|---|
| llama-server | Native, a launchd agent | New. Replaces Ollama, which is removed at M2 (3.4). It needs the GPU, so it must be native |
| The harness (`assistant_service/`) | Native, a launchd agent, from `.venv` | New. The agent loop moves here from the Home Assistant component (doc 04) |
| The tool server | Native, from `.venv` | Listens on `127.0.0.1` instead of every address |
| Whisper, Kokoro | Native, from `.venv` | Unchanged |
| SearXNG | Docker Desktop | Unchanged, already on `127.0.0.1` |
| Home Assistant OS | UTM VM, bridged | Unchanged; its component becomes a thin client of the harness |
| Memory notes | A folder in `~/Library/Application Support/studio-assistant/` | New (doc 11). Outside the repository and never under git |

### 3.2 Who can reach which port

Each port is bound to the narrowest address that still works. A service bound to `127.0.0.1` cannot be reached from any other device, whatever the firewall says, so only the parts the VM or the laptop must call listen on the Mac's network address.

| Port | Service | Listens on | Who calls it | What else guards it |
|---|---|---|---|---|
| 10300 | Whisper | The network | Home Assistant | Nothing; the Wyoming protocol has no authentication. Unchanged from v1 |
| 8770 | The harness | The network | Home Assistant | An API key, a list of allowed host names, and refusal of browser requests (doc 12 §3.9) |
| 10210 | Kokoro | The network | Home Assistant | Nothing, as for Whisper |
| 22 | SSH | The network | Your laptop | Keys only, one user (v1/10 §3.9) |
| 8090 | llama-server | `127.0.0.1` | The harness, the benchmark | An API key |
| 8765 | The tool server | `127.0.0.1` | The harness, the benchmark | Its existing host-name check |
| 8080 | SearXNG | `127.0.0.1` | The tool server | Nothing more |
| 11434 | Ollama | The network until M2, then removed | Home Assistant, until the harness takes over | Nothing; this is the open port v2 closes |

Whisper and Kokoro stay open to the network because Home Assistant runs in its own VM with its own address, so it cannot reach the Mac's `127.0.0.1`. Anyone on the home network could send them audio or text. That was already true in v1, and they hold no data.

The harness's port, 8770, is new. Nothing else in the project uses it.

### 3.3 The memory budget

Every part on the Mac shares one pool of memory. On Apple silicon, macOS also limits how much of that pool the GPU may use: about two thirds of the memory on smaller Macs and about three quarters on larger ones. On the 16 GB laptop the limit is about 10.7 GB. Everything llama-server puts on the GPU must fit under it:
- the model's weights;
- the KV pool;
- the compute buffers.

llama-server prints the limit when it starts, as `recommendedMaxWorkingSetSize`. It can be raised with `sudo sysctl iogpu.wired_limit_mb=…`, but Apple does not support that, and the change is lost at restart unless it is made permanent. v2 plans to stay under the default.

This is what each part takes, as measured on the laptop and as expected with the larger model planned for the new Mac:

| Part | Laptop today, Gemma 4 E4B | With Gemma 4 26B-A4B | Notes |
|---|---|---|---|
| macOS and system | ~3 GB | ~3 GB | v1/08 §4 |
| Home Assistant VM | ~7.5 GB held by the VM process, given 4,096 MB | 3 to 4 GB, given 3,072 MB | v1/08 §4; the least certain row |
| llama-server | 5.8 GB, measured during the slot tests | ~16 GB of weights, 1 to 2 GB of KV pool, up to 1 GiB of RAM prompt cache | E4B's file is 5.2 GB. The pool is set by `context_tokens` in `config/serving.toml` (doc 02 §3.5) |
| Whisper large-v3-turbo | ~1.6 GB | ~1.6 GB | v1/08 §4 |
| Kokoro | under 1 GB | under 1 GB | v1/08 §4 |
| Docker's VM, with SearXNG | 0.4 GB, measured 2026-10-08 | 0.4 GB | |
| The harness and the tool server | not yet measured | not yet measured | Two Python processes with no model in them; measured in M2 |
| An embedding model | none | under 1 GB | From M10 (doc 11) |

**The laptop cannot run everything at once.** The rows add up to more than its 16 GB. It already could not in v1: Whisper and Kokoro are stopped between voice sessions, and the VM runs only when Home Assistant is being worked on. The benchmark needs only llama-server and the tool server.

During M1, Ollama and llama-server both exist. Only one of them may hold a model at a time: Ollama's model is unloaded with `ollama stop` before llama-server is started, and the reverse.

**The 26B-A4B column is an estimate.** Benchmark pass 5 scored an unsloth file of this model. v2 accepts weights only from `ggml-org` or `google` (doc 12 §3.10), so M9 benchmarks an allowed file before the model is used. M8 replaces the estimate with measurements.

### 3.4 From the laptop to the new Mac

The work before the new Mac happens on the laptop. Where Home Assistant sends questions changes at M2.

| Milestone | Home Assistant sends questions to | llama-server serves |
|---|---|---|
| Today | Ollama and the tool server on the network, through the v1 component | nothing yet |
| M1 | Unchanged | The benchmark only |
| M2 | The harness, through the thin client | The harness and the benchmark. Ollama is uninstalled and the tool server moves to `127.0.0.1` |

At M8, the whole system moves to the new Mac with v1/10's tools. The laptop then goes back to being a laptop. The move, in order:
1. **Set up the Mac.** Run the bootstrap (v1/10 §3.1 and §3.2), with the Brewfile changes in doc 10.
2. **Copy what git cannot carry.** `mini.sh push-env`, `push-models` (now the GGUF files named in `config/serving.toml`, checked against their hashes, doc 10 §3.7), and `push-vm`.
3. **Copy the memory notes once.** Use rsync, from the laptop's notes folder to the same path on the new Mac (doc 10 §3.6).
4. **Deploy.** `mini.sh deploy`, which ends with the smoke test.
5. **Measure.** Fill in the new Mac's column of `docs/VERSIONS.md` and the measured memory of each part (3.3). M9's model comparison runs next.
6. **Stop the laptop serving.** Stop every service and leave the laptop's VM stopped (v1/10 §6).

## 4. Packages and tools, and what each does for the business logic

| Package or tool | Role in this subsystem |
|---|---|
| llama.cpp (homebrew-core, pinned) | `llama-server`, which runs the model on the GPU through Metal |
| launchd | Starts llama-server and the harness at login and restarts them if they exit, as it does the v1 services |
| macOS's application firewall | Allows the processes that listen on the network. llama-server is not in the list, because it listens only on `127.0.0.1` |

## 5. Configuration we control

| Setting | Where | Value |
|---|---|---|
| llama-server's address and port | `config/serving.toml` | `127.0.0.1:8090` |
| The harness's address and port | The harness's config file (doc 10) | Every address, port 8770 |
| The tool server's address | The tool server's launchd agent, written by `scripts/services.sh` | `127.0.0.1:8765` from M2 |
| The KV pool and the RAM prompt cache | `config/serving.toml`, `context_tokens` and `prompt_cache_mib` | 18,432 tokens and 1,024 MiB on the laptop; set per machine in M1 and M8 |
| VM memory | `HAOS_VM_MEMORY_MB` | 3,072 MB on the new Mac, as in v1 |

## 6. Failure modes

| Failure | What happens | What to do |
|---|---|---|
| The model and its pool exceed the GPU's limit | llama-server fails to load, or loads slowly and swaps | Lower `context_tokens` or `prompt_cache_mib`; raising the limit with `sysctl` is the last resort |
| Ollama and llama-server both hold a model on the laptop | The laptop swaps and every answer slows | `ollama stop` the model; only one engine serves at a time until M2 |
| The VM takes more than its share | Free memory falls in the health snapshot | Lower `HAOS_VM_MEMORY_MB`, as in v1 |
| A service bound to `127.0.0.1` is needed from the VM | The VM's calls are refused | By design. Only the harness, Whisper and Kokoro serve the VM; anything new goes through the harness |
| The Mac's network address changes | The VM cannot reach the harness, Whisper or Kokoro | The router's DHCP reservation prevents it (v1/08 §7) |

## 7. Concepts for newcomers

**Binding to `127.0.0.1`.** A server listens on one of the machine's addresses. `127.0.0.1` is the address a machine uses to talk to itself, and no other device can send to it. A server bound there is unreachable from the network, however the firewall is set.

**The GPU's memory limit.** Apple silicon has one pool of memory, but macOS lets the GPU use only part of it, so the rest of the system keeps room. A model must fit under that limit, not under the machine's total.

**KV pool.** The memory llama-server sets aside for the keys and values of the tokens it has read, shared by both slots (doc 02 §7). It grows with the context window.

## 8. Sources

- The GPU's default memory limit, and raising it with `iogpu.wired_limit_mb`: [ivanopcode/devnote-override-macos-metal-vram-cap](https://github.com/ivanopcode/devnote-override-macos-metal-vram-cap)
- The laptop's figures: llama-server 0.6.0 (build 11429) with `google/gemma-4-E4B-it-qat-q4_0-gguf`, resident memory measured during the slot tests on 2026-10-08; Docker's VM from `ps` the same day.
- Home Assistant VM memory on the laptop: v1/06 §11.
