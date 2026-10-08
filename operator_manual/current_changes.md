# Current Working Changes

This page lists the pull requests that are open right now, one entry each, in the same shape as a section. An entry is written when its pull request opens and removed when the pull request merges or closes.

## PR #17: Kokoro's Fable voice by default, and a services.sh that reports agents that fail to load
<!-- manual-entry branch="kokoro-fable-default" pr="17" date="2026-10-07" -->

### Where this fits

```mermaid
flowchart TB
--8<-- "_includes/system_map.mmd"
class tts,whisper,laptop,health current
```

### Key definitions

None new.

### Packages and tools

No new packages. The change uses `launchctl print`, already used by the health check, to tell whether an agent is still loaded.

### What changed

The change has two parts:

- **Kokoro's Fable voice by default.** The Jarvis pipeline speaks with `tts.kokoro`, language `en_GB`, voice `bm_fable`, and Kokoro itself starts with `--voice bm_fable`. `scripts/ha_setup.py --tts piper` switches back to Piper, and `--tts-voice` with `--tts-language` picks another Kokoro voice. [Text to speech](05_voice_pipeline.md#text-to-speech) on the Voice Pipeline page compares the two engines.
- **Agents that fail to load are reported.** `scripts/services.sh` waits for every agent to finish unloading before it loads it again, since Kokoro takes about 5 s to exit and a reload inside that window failed silently. `install` and `start` now name any agent that does not load and exit 1, and `status` lists every agent that is not loaded. [Operations](10_operations.md) shows how a failed load stops a deploy.

### Run it yourself

1. Reinstall the agents on the laptop:

    ```bash
    HEALTH_CHECK_FLAGS="--no-remediate" scripts/services.sh install
    ```

    Every service prints `listening on` its port, and the command exits 0. An agent that does not load prints `failed to load: NAME (...)` and the command exits 1.

2. With the VM running, rebuild the pipeline:

    ```bash
    uv run python scripts/ha_setup.py --only pipeline
    ```

    It prints `pipeline: 'Jarvis' uses stt.mlx_whisper -> conversation.studio_assistant -> tts.kokoro (en_GB, voice bm_fable) (preferred)`.
