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
      ├── five of 32 MiB or more ........ 3,122.9 MiB  ← released by the first trial patch
      ├── 300 native projection matrices  1,781.1 MiB  ← released by the second patch (being tested)
      ├── ~16 other small ones .......... a few MiB    ← not audited, kept
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

## The 300 native projection matrices

A second audit (2026-11-20) covered the roughly 316 device allocations under 32 MiB that the first patch leaves alone. Nearly all of them, and nearly all of their 1.78 GiB, are one set: the host code's native copies of the projection matrices.

### What they are

- **Who makes them:** `NativeDense::load` (`engine/src/core/native_dense.cpp:329-634`), called at `engine/src/program/generate.cpp:5751`.
  - Each matrix gets its own `cudaMalloc`, then a `cudaMemcpy` from the memory-mapped GGUF (`native_dense.cpp:454-457`).
  - The startup log reports the set at `generate.cpp:5755`: "300 native projection matrices, 1781.11 MiB of weights".
- **Which tensors:** the name filter `eligible()` (`native_dense.cpp:165`) picks them. The Studio's pack index (`~/Strata-data/packs/iq3_xxs/index.txt`) gives exactly 300:

  | Layers | Matrices | Count |
  |---|---|---|
  | 36 GatedDeltaNet layers | `attn_qkv`, `attn_gate`, `ssm_out` | 108 |
  | 12 attention layers | `attn_q`, `attn_k`, `attn_v`, `attn_output` | 48 |
  | all 48 layers, shared expert | `ffn_gate_shexp`, `ffn_up_shexp`, `ffn_down_shexp` | 144 |

- **Their size:** about 5.9 MiB on average. The largest possible, `attn_q` (2,560 × 12,288) at Q8_0, is 31.9 MiB, so none reaches the 32 MiB threshold, and streaming mode's purge skips them too.
- **Where the pointers live:** `NativeDense::weights_` (`engine/include/strata/core/native_dense.hpp:73`). Each is also published into its tensor's `WeightRef::native_data`, with `native_q8_1` pointing at one shared scratch of about 7 KB (`native_dense.cpp:603-606`; the fields are at `engine/include/strata/core/weights.hpp:90-95`).
- **What else is in the small allocations:** that scratch, plus about 15 allocations not listed. On Metal there's no packed Q8_0 copy (`engine/metal/src/engine/mmvq_host.cpp:62-64`), and no hyper-connection Q8 copy unless `STRATA_HC_Q8=1` is set.

### Why nothing on a Mac reads them

The Metal window reads the same weights from the mapped model file. Its header says so (`engine/metal/src/engine/window.cpp:1-9`), and the shared host code hands decoding and prompt reading to it before any code that would use the copies:

| Path | Where it hands off to the Metal window |
|---|---|
| Decode window: init, run, commit | `engine/src/core/verify.cpp:922` (`window_init`), `:3355` (`window_run`), `:3986` (`window_commit`) |
| Prompt reading | `engine/src/prefill/prefill.cpp:2376` (`window_ensure`), `:9002` (`prompt_run`) |
| DFlash2 drafter | `Dflash2Drafter::bind` ignores the weight table and binds to the window (`engine/metal/src/engine/dflash2.inc:1059`) |

Every reader of `native_data` is CUDA-path code. On a Mac, each one is either unreachable or ends in a stub:

| Reader | Reached on a Mac? | If it ran with the memory gone |
|---|---|---|
| Single-token projections and the shared expert (`engine/src/core/layer.cpp:170`, `:497-499`, `:1166`) | No: the decode window replaces the layer path | The kernels are Metal stubs (`native_mmvq`, `engine/metal/src/engine/stubs.cpp:261`; `shared_expert`), which stop the engine with exit code 86 (`engine/metal/src/engine/missing.cpp:22`) |
| The verifier's own window build (`verify.cpp`, after `capture`) | No: init, run and commit hand off first | Stub, exit 86 |
| Prompt-path GEMMs (`Gemm::native`) | No: the prompt goes to `prompt_run` | Stub (`stubs.cpp:334`), exit 86 |
| The PLE key copy (`generate.cpp:5923`) | No: needs `native_ple_key`; the PLE key isn't one of the 300 | Only stub PLE kernels read it |
| `host_view` | Never on these pointers. Its only callers are the arena poison (`engine/src/core/device.cu:336`) and the window's logit bias, history and M-RoPE buffers | n/a |
| Copies (`cudaMemcpy`) after load | None found. The only other `release()` is a multi-GPU stage reload (`generate.cpp:7236`) | The purge guard aborts with a backtrace (`check_purged`) |

- **Nothing under `engine/metal/src` refers to `native_data`, `native_q8_1`, `hc_q8`, `NativeDense` or the PLE key fields.** The window builds its own Q8 copies of the hyper-connection projections (`window.cpp:892` on).
- **`mmvq_host.cpp:1-3` states outright** that the native kernels aren't ported to Metal.
- **The checks for a non-null pointer still pass after a release,** because purging keeps the pointer value. So a path that checks for the copy sees it present, and the kernel it then calls is a stub.

### If the audit is wrong

Every route fails loudly. A stub kernel exits with code 86, and a copy aborts with a backtrace. The one unguarded route, `host_view`, is never used on these pointers. So a miss means an engine restart, not wrong answers.

### Confidence and what wasn't checked

**High, about 90%,** that nothing in our setup reads them. This comes from reading the code, not from a run; the poison test checks it at runtime. Not checked:
- a full read of `generate.cpp`, `prompt_chain.inc` and `dflash2.inc` (pointers were traced by field name)
- `terminal/serve/server.py`
- the `STRATA_HC_Q8=1` and multi-GPU variants
- the ~15 other small allocations
- the per-tensor GGUF types and exact sizes
- shutdown with given-back buffers: `free_alloc` (`engine/metal/src/gpu/runtime.cpp:296-312`) doesn't check `purged`. Stock streaming mode takes the same path with its purged buffers, so this is probably harmless.

Strata has never freed these copies in any mode, and a search of its GitHub issues found nothing about them.

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

### The second patch: the projection matrices

`scripts/strata_patches/release_projections.patch` applies on top of the first. The size threshold can't be used here: lowering it would also catch the small buffers that are read through `host_view` (logit bias, penalty history, M-RoPE positions). So the patch hands over the matrices' exact addresses instead:

1. **`NativeDense::device_weights()`** (`native_dense.hpp`) exposes the 300 pointers in `weights_`.
2. **`generate.cpp`, right after the load log line, Metal build only,** passes them to `strata::gpu::mark_unread_allocations`. That function flags each allocation that starts exactly at one of the pointers and logs "marked 300 of 300 native projection matrices".
3. **At the first request, with `STRATA_METAL_RELEASE_PROJECTIONS=1`,** `release_host_weights_once` poisons or releases the flagged set, the same way as the first set. The log line reads "release projections: X GB of the host code's native projection matrices".
4. **The runtime gives them back with the stock purge,** now behind a selection: size threshold, or the flag. The memory is purged, not freed. A freed address could go to a later allocation, and a stale `native_data` would then point into it.

In the trial scripts, `STRATA_RELEASE_PROJECTIONS=1` turns it on for `strata_trial.sh`, the release experiment and the voice run.

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

### The projection release: being tested

`RELEASE_RUN=strata_release_projections STRATA_RELEASE_PROJECTIONS=1 scripts/strata_release_experiment.sh` runs the same off, poison and release checks, with the 300 matrices included, and records results in `benchmark/results/strata_release_projections/`. It adds one check: at least 1.8 GB of projection matrices handled.

Then the voice run measures release, projections and a 24-hour GPU keep-alive (`STRATA_KEEPALIVE_WINDOW_S=86400`) together. The results go here when they're in.

## What remains

- **The projection release's results:** the poison and release checks, then the voice rounds (see above).
- **About 15 small allocations** besides the projection matrices and their scratch, not audited.
- **The 260 MiB token embedding.** It's a host allocation, so the purge skips it.
- **With the five released, Strata needs about 4.3 GiB more RAM than llama-server:** lean2's footprint is 7.5 GiB, against llama-server's 3.2 GiB.
  - Releasing the projection matrices should bring that down to about 2.5 GiB. That's an estimate, not yet measured.
  - The voice-latency comparison (`scripts/strata_voice_latency.sh`) measures whether the difference reaches Kokoro, Qwen3-ASR or the model in a way a user would hear.
- **More checks before production would rely on the release:**
  - a build that aborts with a backtrace on any GPU dispatch argument or `host_view` lookup that falls inside a given-back buffer
  - a full benchmark pass, A and B, through the harness with production settings: medium reasoning effort and real multi-round tool calls.
