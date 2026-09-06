# 06. Home Assistant core

## 1. Purpose

Home Assistant is the orchestrator. It already knows how to adopt the puck, run a speech pipeline, match spoken commands to actions, control Spotify and Sonos, fetch weather, and host third-party Python components. We use it as plumbing so that the only code we write is the part that does not exist yet: the conversation agent and the search tool. It runs as Home Assistant OS inside a virtual machine on the Mac.

## 2. Diagram

```
  Mac
  ┌───────────────────────────────────────────────────────────────────────────────────────┐
  │  UTM virtual machine, bridged networking (own IP on the LAN, mDNS works)               │
  │  ┌─────────────────────────────────────────────────────────────────────────────────┐  │
  │  │ Home Assistant OS                                                                │  │
  │  │  ┌───────────────────────────────┐   ┌────────────────────────────────────────┐ │  │
  │  │  │ Home Assistant Core           │   │ Add-ons (managed containers)            │ │  │
  │  │  │  Assist pipeline              │   │  ESPHome      adopts / flashes the puck │ │  │
  │  │  │   ├ STT ─▶ Wyoming ───────────┼───┼──────────────────────────────▶ Mac: Whisper
  │  │  │   ├ intent matcher            │   │  Piper        text to speech            │ │  │
  │  │  │   ├ conversation agent        │   │  Music Assistant  Spotify → Sonos       │ │  │
  │  │  │   │   └ studio_assistant ─────┼───┼──────────────────────────────▶ Mac: Ollama, MCP
  │  │  │   └ TTS ─▶ Wyoming ───────────┼───┼──────────────────────────────▶ Mac: Kokoro / Piper
  │  │  │  Integrations                 │   └────────────────────────────────────────┘ │  │
  │  │  │   Spotify, Sonos, Met.no,     │                                               │  │
  │  │  │   Wyoming, ESPHome, MA        │   Supervisor: updates, backups, add-on lifecycle│  │
  │  │  │  Recorder (SQLite): history   │                                               │  │
  │  │  └───────────────────────────────┘                                               │  │
  │  └─────────────────────────────────────────────────────────────────────────────────┘  │
  └───────────────────────────────────────────────────────────────────────────────────────┘
        ▲                          ▲
        │ Wi-Fi                    │ Wi-Fi
   Voice PE puck              Sonos Era 100 SL
```

## 3. How it works, step by step

1. **Install.** Home Assistant OS is a purpose-built Linux image. On a Mac it runs in UTM, a free virtualization app, from the official aarch64 image. Networking is set to bridged so the VM gets its own address on the studio Wi-Fi and devices can discover it by mDNS.
2. **Adopt the puck.** The ESPHome add-on discovers the Voice Preview Edition on the network and adds it as a device with a voice assistant entity, a wake word selector, LEDs, and a media player.
3. **Add speech services.** The Wyoming integration is pointed at the Mac's LAN address and the ports where Whisper, Kokoro, and (if not the add-on) Piper listen. Each becomes an STT or TTS entity.
4. **Add the agent.** `studio_assistant` is copied into `/config/custom_components/`, Home Assistant is restarted, and the component is added from the Integrations page, which runs its config flow (Ollama URL, model, MCP URL, persona).
5. **Build the pipeline.** Under Voice assistants, a pipeline is created that chains the STT entity, the `studio_assistant` conversation agent, and the TTS entity, with language English and "prefer handling commands locally" turned on. The puck is set to use that pipeline.
6. **Add music and weather.** The Spotify integration (OAuth against a free Spotify developer app), the Music Assistant add-on with its Spotify provider and the Sonos player, and Met.no (usually present by default) are configured from the UI.
7. **Run.** Every request from the puck flows through the pipeline exactly as drawn in doc 00.

## 4. The Assist pipeline and intent matching

Before any language model is involved, Home Assistant tries to match the transcript against sentence templates. "Play [artist]", "what's the weather", "what's the weather tomorrow", "set volume to 50 percent" all match built-in or Music Assistant intents and execute directly in tens of milliseconds. Only unmatched text reaches the agent. This is the "smaller router in front of a larger model" design from benchmark question A8, and it is why music and weather are fast and never hallucinated.

Setting: "prefer handling commands locally" on the pipeline makes the intent matcher run first even when a conversation agent is configured.

## 5. Why a VM and not Docker

Home Assistant offers several install methods. The two that matter here:

| Method | Add-ons (ESPHome, Music Assistant, Piper) | Discovery (mDNS) | Fit |
|---|---|---|---|
| Home Assistant OS in a UTM VM, bridged | Yes | Yes | Production |
| Home Assistant Container in Docker Desktop on macOS | No | No host networking on macOS Docker, so discovery breaks | Prototype shortcut only |

The VM costs 3 to 4 GB of memory and a few minutes of setup. The alternative is a $99 Home Assistant Green running Home Assistant OS natively, with the Mac purely as the inference box. That is cleaner and frees memory on the Mac; it is the fallback if the VM proves annoying.

## 6. Packages and components, and what they do for us

| Component | Role in the business logic |
|---|---|
| Home Assistant OS + Supervisor | The appliance. Runs Core and add-ons as managed containers, handles updates and backups. |
| Assist pipeline | The state machine STT → intents → agent → TTS, with streaming and the continue-conversation flag. |
| Intent matcher (`hassil` templates) | Deterministic handling of music and weather commands. |
| Wyoming integration | Connects the pipeline to our speech services on the Mac by host and port. |
| ESPHome integration and add-on | Adopts the puck, updates its firmware, exposes its controls. |
| Spotify integration | OAuth login, playback state, and control of any Spotify Connect device on the account. |
| Music Assistant (add-on + integration) | Library and playback engine that maps "play X" to a Spotify search and a Sonos stream. Doc 07. |
| Sonos integration | Discovers the Era 100 SL and exposes it as a media player. |
| Met.no integration | Weather entity with a daily and hourly forecast; drives the weather intents. |
| Recorder | Stores history in SQLite on the VM disk. Conversation history lives here and nowhere else. |
| Companion app (phone) | Push-to-talk Assist for the prototype before the puck arrives. |

## 7. Configuration we control

- VM: 2 vCPUs, 4 GB memory, 32 GB disk, bridged network, autostart with UTM at login.
- Pipeline: STT and TTS entities, agent, language, local-first setting, VAD sensitivity.
- Puck: wake word, pipeline assignment, LED brightness, volume.
- Recorder retention: 10 days is plenty; keeps the database small.
- Backups: nightly to a folder on the Mac that is itself backed up.
- Access: LAN only. No Nabu Casa cloud, no port forwarding. Remote access is out of scope.

## 8. Failure modes

- **Monthly release breaks an integration or the conversation API.** Read the release notes; the custom component's test suite pins the version. Update Home Assistant OS monthly, on purpose, not automatically.
- **VM does not start after a Mac reboot.** UTM set to launch at login with the VM set to autostart; a launchd health check restarts it if the API is unreachable.
- **Discovery fails.** Almost always the network mode. Bridged, not shared.
- **Recorder database grows.** Retention setting above.
- **Spotify token expires.** The integration refreshes automatically; if the developer app's credentials change, re-authenticate from the UI.

## 9. Concepts for newcomers

**Integration.** Home Assistant's word for a connector to a device or service: Spotify, Sonos, Wyoming, Met.no. Configured from the UI, produces entities.

**Entity.** A single thing with state: a media player, a weather forecast, an STT engine, a conversation agent. Pipelines are built by picking entities.

**Add-on.** A Docker container that Home Assistant OS manages for you: ESPHome, Piper, Music Assistant. Only available on Home Assistant OS or Supervised installs, which is why we run the OS image.

**Intent.** A structured meaning extracted from a sentence, such as `HassPlayMedia(artist="Radiohead")`. Home Assistant ships thousands of sentence templates that map speech to intents without a language model.

**mDNS / zeroconf.** How devices on a home network announce themselves by name without a central server. The puck, the Sonos, and the ESPHome add-on rely on it, and it does not cross Docker's network isolation on macOS.

**Bridged networking.** The VM appears on the Wi-Fi as its own machine with its own IP address, exactly like a separate computer. The alternative, shared or NAT networking, hides it behind the Mac and breaks discovery.

**Config flow.** The UI wizard an integration or custom component shows when you add it. Our component's config flow asks for the Ollama URL, model, MCP URL, and persona.

## 10. Sources

- Home Assistant installation methods and comparison: [home-assistant.io/installation](https://www.home-assistant.io/installation/)
- Home Assistant OS on macOS with UTM: [home-assistant.io/installation/macos](https://www.home-assistant.io/installation/macos)
- Assist pipelines and local voice setup: [home-assistant.io/voice_control/voice_remote_local_assistant](https://www.home-assistant.io/voice_control/voice_remote_local_assistant/)
- Wyoming integration: [home-assistant.io/integrations/wyoming](https://www.home-assistant.io/integrations/wyoming/)
- Spotify integration: [home-assistant.io/integrations/spotify](https://www.home-assistant.io/integrations/spotify/)
- Met.no integration: [home-assistant.io/integrations/met](https://www.home-assistant.io/integrations/met/)
- Home Assistant Green: [home-assistant.io/green](https://www.home-assistant.io/green/)

## 11. As built, 2026-09-06

Home Assistant OS 18.2 (core 2026.9.1) runs in the UTM VM at 192.168.1.156, set up end to end by `scripts/ha_setup.py`. What is in place:

| Piece | State |
|---|---|
| Onboarding | Owner account created, location "Studio", long-lived token in `.env` as `HA_TOKEN` |
| Add-ons | Samba 12.10.0, Piper 2.3.4, openWakeWord 2.1.1, Music Assistant 2.10.2, ESPHome 2026.8.2; all started, boot auto, watchdog on |
| Wyoming integrations | Whisper (Mac, 10300) and Kokoro (Mac, 10210) added by the script; Piper and openWakeWord discovered from their add-ons and confirmed; Music Assistant confirmed |
| Conversation agent | `conversation.studio_assistant` from our component (doc 04 §13) |
| Pipeline | "Jarvis": `stt.mlx_whisper` → `conversation.studio_assistant` → `tts.piper`, English, local intents preferred, set as the preferred pipeline |

Details learned on this build, all handled in the script:

- The API is on port 80. During onboarding port 8123 answers with a redirect to it; after onboarding 8123 stops listening altogether and `/api/onboarding` returns 404. Discovery therefore probes `/api/` (401 without a token is a healthy answer) and reuses the saved `HA_BASE` when there is one. The first version waited on 8123 for fifteen minutes.
- Flows in progress are listed only over the websocket (`config_entries/flow/progress`); the REST collection answers 405 to GET.
- The Wyoming config flow titles the entry after the remote service's name ("mlx-whisper", "kokoro") and the entry listing does not expose host or port, so the script records the entry ids it created in `.env` (`HA_WYOMING_WHISPER_ENTRY`, `HA_WYOMING_KOKORO_ENTRY`) and checks those on reruns. Before that check existed one rerun created a second Whisper and a second Kokoro entry (`stt.mlx_whisper_2`, `tts.kokoro_2`); they are harmless and can be removed from Settings → Devices & services.
- Restarting Home Assistant through the REST service call usually returns a dropped connection rather than a 200; the restart still happens and the API is back in about 30 s.
- Supervisor log endpoints (`/core/logs`) return plain text and cannot be read through the websocket proxy; the `system_log/list` websocket command gives the recent errors with full tracebacks and was enough to debug the component.

Memory on the 16 GB Mac while all of this runs: QEMU about 7.5 GB resident, Whisper 2.5 GB, Docker with SearXNG 1.7 GB, Kokoro about 1 GB, with 3.5 to 5.5 GB of swap in use. It works, but macOS killed background shell tasks for low memory twice during the setup, and this is the state the benchmark must not share (doc 01).
