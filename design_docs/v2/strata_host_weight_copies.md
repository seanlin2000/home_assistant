# Strata in resident mode: the host code's unused weight copies

Status: building (Strata trial, draft PR #110; production still runs llama-server)

## Purpose

In resident mode, Strata keeps several gigabytes of GPU buffers that nothing on a Mac reads. These are copies of the weights and state that Strata's shared, CUDA-shaped host code allocates at load time. On a Mac the Metal decode window reads the model file itself and keeps its own buffers, so the copies sit untouched. macOS compresses or swaps them, and compressed they still cost RAM.

This doc records:
- which buffers they are
- why the Mac never reads them
- how the trial gives them back
- what that saved
- what is still unknown.

All source references are to Strata v0.2.16 (commit `64524fb`), paths relative to the Strata repository. Sizes are in binary units (MiB, GiB), as Strata's log, `vmmap` and `top` print them, unless a line says otherwise.

## Where the 4.9 GiB came from

During the trial (phases 3 and 4a), `vmmap --summary` on the Strata process showed its GPU buffers (the `IOAccelerator (graphics)` region) at about 11 GiB, with 4.9 GiB of that compressed or in swap while the engine was idle. An engine buffer only stays compressed while idle if no request touches it, which is what pointed at buffers the Metal path never reads.

```
Strata process, resident mode (STRATA_METAL_STREAM=0)
├── Metal window's own buffers ............ read on every request
│     expert arena, K/V, prompt buffers
├── the model file, memory-mapped ......... read on every request
└── host code's device allocations ........ allocated at load, never read on Mac
      ├── five of 32 MiB or more ........ 3,122.9 MiB  ← released by the trial patch
      ├── ~316 smaller ones ............. ~1,781 MiB   ← not audited, kept
      └── token embedding (a host allocation, not a device one) 260 MiB ← kept
```

Together these come to about 5,164 MiB (5.0 GiB). That's close to the 4.9 GiB that `vmmap` showed compressed. It's an approximate match, not a one-to-one accounting.

## The five buffers

Every device allocation the host code makes goes through Strata's Metal stand-in for the CUDA runtime (`engine/metal/src/gpu/runtime.cpp`). A patched build listed each device allocation of 32 MiB or more at the first request. There were five:

| Size | What it is | Allocated at | Why the Mac never reads it |
|---|---|---|---|
| 1,466.8 MiB | Weight arena: the pack's dense canonical tensors | `engine/src/program/generate.cpp:5688` (`cudaMalloc(&arena, pool_bytes)`) | The Metal window reads the dense weights from the mapped model file |
| 997.1 MiB | Session state: K/V, GatedDeltaNet state and the like, in the CUDA path's layout | `engine/src/program/generate.cpp:7360` (`session_bytes(g, o.max_context, ...)`), laid out by `session_init` at `engine/src/core/session.cpp:72` | The window rebinds the session to its own K/V buffers at load: `bind_session(ss)` at `engine/metal/src/engine/window.cpp:887`, defined at `:2303`. At 34,816 tokens of context with fp16 K/V the layout works out to 988.2 MiB, matching the allocation. |
| 416.8 MiB | Native output head (`output.weight`, Q5_K) | `engine/src/core/native_head.cpp:67` | The window computes the head from the mapped file |
| 142.2 MiB | Expert cache: 84 slots | `engine/src/core/expert_cache.cpp:662` | On Metal the prompt path uses the window's own buffers and never borrows or refills cache slots (`engine/src/program/generate.cpp:12127-12135`) |
| 100.0 MiB | DFlash2 prompt-tap staging (`Prefill::tap_dev_`) | `engine/src/prefill/prefill.cpp:1746` | The window supplies the drafter's taps from its own buffers |
| **3,122.9 MiB** | **in all** (3.05 GiB; the patch's log printed it as "3.27 GB", decimal) | | |

## Why nothing reads them, and what would happen if something did

### Strata already gives these buffers back in streaming mode

In streaming mode (the default on small Macs), stock v0.2.16 already does what the trial does. `Window::stream_arena` calls `strata::gpu::purge_device_allocations(32u << 20)` at `engine/metal/src/engine/window.cpp:1696`. It logs that the host code's device weight copies were "given back (unused by the Metal window)", unless `STRATA_METAL_KEEP_HOST_WEIGHTS=1` is set.

The purge itself is `engine/metal/src/gpu/runtime.cpp:327-340`:
- it skips host allocations, allocations already given back, and anything under the minimum size
- it removes every other buffer from the Metal residency set and marks it `PurgeableStateEmpty`
- it flags each one `purged`.

The host code runs the same paths in streaming and resident mode. Every streaming user's Mac already runs without these five buffers.

### A read through the runtime's copy or fill calls aborts loudly

`check_purged` (`engine/metal/src/gpu/runtime.cpp:187-195`) runs on every copy and every fill (`:201`, `:202`, `:225`). If one touches a given-back allocation, it prints the allocation's size and a backtrace, then calls `std::abort()`. So a copy or fill the audit missed would kill the engine with a backtrace. It couldn't silently produce a wrong answer.

### The one unguarded route never points at these buffers

`host_view()` (`engine/metal/src/gpu/runtime.cpp:317-321`) hands host code a CPU pointer into a device allocation, with no purge check. It's used in three places, and each one points at its own small allocation, never one of the five:

| Use | Its own allocation |
|---|---|
| Logit bias upload | `engine/src/core/verify.cpp:884` |
| Repetition-penalty history | `engine/src/program/generate.cpp:12510` |
| M-RoPE image positions (vision input only) | `engine/src/program/generate.cpp:5822` |

### GPU kernels can't reach them either

- The runtime's `dispatch` (`engine/metal/src/gpu/runtime.cpp:603`) has no callers in the Metal build.
- Shared kernel entry points without a Metal implementation are stubs. They print their name and exit with code 86 (`engine/metal/src/engine/missing.cpp:22`).
- The Metal window's own runtime (`engine/metal/src/mtl_rt.mm`) never refers to `strata::gpu` allocations.

### Paths that would abort, none of them used in our setup

| Path | Where |
|---|---|
| The explicit command to resize GPU memory, which refills the expert cache | `engine/src/program/generate.cpp:15740-15807` |
| `--prefill-head-alias` | |
| `--batch` parking | |

### Past Strata issues that fit this picture

| Issue | What happened | Status |
|---|---|---|
| #3030 | In streaming mode, an expert-cache refill wrote into a buffer the purge had given back | Fixed in v0.2.16. The comment at `engine/src/program/generate.cpp:12127-12135` explains the fix. |
| #5401 | A copy for parking or saving wrote into a given-back buffer | Fixed in v0.2.16 |
| #2338 | Added resident mode for 64 GB Macs | Didn't measure memory headroom |
| #3784 | An out-of-memory failure in resident mode on another model | |

Both #3030 and #5401 ended in the loud abort above, not in wrong answers.

### Confidence

- **High** that no wrong answers can come from this: every guarded route aborts, and the unguarded one never points at these buffers.
- **Medium-high** that no request in our setup crashes. The audit didn't trace every `cudaMemcpy` in the 24,000-line `generate.cpp`. It relied on the abort guard for those, so a missed one would mean a crash and an engine restart, not a wrong answer.

## How the trial gives them back

The patch is `scripts/strata_patches/release_host_weights.patch` on the `strata-trial` branch. It's built into `~/strata/engine/build-metal/strata`, and the stock binary is kept as `strata.v0.2.16-orig`.

What it adds:
- `release_host_weights_once()` to `engine/metal/src/engine/window.cpp`. It runs once, at the first `Window::run`, `Window::run_rows` or `Window::prompt_gemm_init`, and only in resident mode.
- Behaviour set by `STRATA_METAL_RELEASE_HOST_WEIGHTS`:
  - **`release`** calls the same `purge_device_allocations` that streaming mode uses
  - **`poison`** overwrites the same allocations with `0xFF` and keeps them, so a hidden reader would change the answers or crash the engine
  - **unset** keeps stock behaviour.
- `STRATA_METAL_RELEASE_MIN_MIB` sets the size threshold, 32 MiB by default, like streaming mode's.
- Two functions in `engine/metal/src/gpu/runtime.cpp`: `log_device_allocations`, which lists what will be touched, and `poison_device_allocations`.

## What the release experiment measured

`scripts/strata_release_experiment.sh`, results in `benchmark/results/strata_release/`, ran 2026-11-20. Strata lean2 served production's port with the whole production stack running, three times:
- `off`: the switch unset
- `poison`
- `release`.

**Answers and health**

| Check | off | poison | release |
|---|---|---|---|
| Greedy answers, word for word against off's (short, story, ~6K-token and tool-call prompts) | reference; repeats across a restart | identical | identical |
| Median decode | 93.3 tok/s | 93.6 tok/s | 92.9 tok/s |
| Smoke tests through Home Assistant | 3 of 3 | 3 of 3 | 3 of 3 |
| Engine errors, restarts | none | none | none |

**Memory, after the smoke tests**

| Measure | off | release |
|---|---|---|
| Strata's footprint (`top`) | 10 GiB | 7.5 GiB (7,686 MiB) |
| Strata's GPU buffers (`vmmap`): in RAM, compressed or swapped | 9.2 GiB, 4.2 GiB | 6.3 GiB, 2.0 GiB |
| Swap growth over the run's llama-server baseline | +973 MiB | −16 MiB |

The whole-Mac compressor didn't shrink, because macOS used the freed RAM for file cache and model pages. Strata's own footprint is the right measure of the saving.

## What remains

- **About 1.78 GiB in roughly 316 smaller device allocations.** These are most likely the native projection matrices, which the startup log reports as 1,781.11 MiB (`engine/src/program/generate.cpp:5755`). Each is under 32 MiB, so the purge skips them in streaming mode too. Nobody has checked whether the Metal window reads them. Releasing them would need the same audit and the same poison and release runs, with the threshold lowered.
- **The 260 MiB token embedding.** It's a host allocation, so the purge skips it.
- **Even with all five released, Strata needs about 4.3 GiB more RAM than llama-server**: lean2's footprint is 7.5 GiB, against llama-server's 3.2 GiB. The voice-latency comparison (`scripts/strata_voice_latency.sh`) measures whether that difference reaches Kokoro, Qwen3-ASR or the model in a way a user would hear.
- **More checks before production would rely on the release:**
  - a build that aborts with a backtrace on any GPU dispatch argument or `host_view` lookup that falls inside a given-back buffer
  - a full benchmark pass, A and B, through the harness with production settings: medium reasoning effort and real multi-round tool calls.
