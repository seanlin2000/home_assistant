# Home Assistant
<!-- complexity: packages=3 parts=2 concepts=3 tier=deep -->

This page covers Home Assistant, the switchboard between you and everything else. It receives your question, spoken to the puck or typed, tries its fixed commands such as "play Radiohead" first, otherwise hands the sentence to our conversation agent, and speaks the answer back. It runs as its own operating system inside a virtual machine on the Mac, with its own address on the studio Wi-Fi.

## Where this fits

```mermaid
flowchart TB
--8<-- "_includes/system_map.mmd"
class stt,intents,agent,tts,ma current
```

## Key definitions

| Term | Meaning |
|---|---|
| Home Assistant OS | A complete Linux operating system image that runs Home Assistant Core, the Supervisor, and add-ons as containers. |
| Supervisor | The service inside Home Assistant OS that installs, starts, updates, and watches add-ons and applies operating-system updates. |
| Add-on | A Docker container that Home Assistant OS installs and manages for you, such as Piper or Music Assistant. |
| UTM | A free virtualisation app for macOS that runs virtual machines on Apple's hypervisor. |
| Bridged networking | A virtual machine setting that puts the VM on the host's network with its own address, as if it were a separate computer. |
| SMB share | A folder served over SMB, the network file-sharing protocol that macOS and Windows speak natively. |
| Integration | Home Assistant's word for a connector to a device or service, such as Spotify, Sonos, or Met.no, which produces entities. |
| Entity | A single thing with state in Home Assistant, such as a media player, a weather forecast, a speech-to-text engine, or a conversation agent. |
| Config flow | The wizard Home Assistant shows when you add an integration, which asks for its settings and checks them before saving. |
| Long-lived access token | A bearer token Home Assistant issues to one user for scripts, valid for years rather than minutes. |
| Assist pipeline | Home Assistant's chain of stages for one voice request (wake word, speech to text, intent matching or a conversation agent, text to speech), built by choosing one entity per stage. |
| Intent | A structured meaning extracted from a sentence, such as `HassMediaSearchAndPlay(search_query="Radiohead", media_class="artist")`. |
| Custom component | A Python package in Home Assistant's `custom_components/` folder that Home Assistant loads at startup, described by its `manifest.json`. |

## Packages and tools

| Tool | What it is | How this part uses it |
|---|---|---|
| UTM 4.7.5 | A virtualisation app for macOS, installed with `brew install --cask utm`, that runs QEMU virtual machines on Apple's hypervisor | Runs the Home Assistant OS disk image as a VM named "Home Assistant" with 4 GB of memory, 2 cores, UEFI boot, and a bridged network interface. `utmctl`, its command line, is what `scripts/haos_vm.sh` and the health check call to start, stop, and query it |
| Home Assistant OS 18.2, Core 2026.9.1 | The appliance image and the Python application inside it | The VM's whole operating system. Core serves the web interface and the REST and websocket APIs on port 80 of the VM's address, runs the Assist pipeline, and loads our custom component from `/config/custom_components/` |
| Supervisor and the add-ons: Samba 12.10.0, Piper 2.3.4, openWakeWord 2.1.1, Music Assistant 2.10.2, ESPHome 2026.8.2 | The Supervisor is the add-on manager inside Home Assistant OS; each add-on is a container it runs | Samba is how code is copied into the VM. Piper is the text-to-speech engine the Jarvis pipeline uses. openWakeWord is a server-side wake word engine, installed and idle. Music Assistant is the music layer (see [Music](07_music_spotify.md)). ESPHome adopts the puck (see [Voice Pipeline](05_voice_pipeline.md#today-and-with-the-puck)). All five start at boot with the Supervisor's watchdog on |
| Wyoming integration | Home Assistant's built-in connector for speech services that speak the Wyoming protocol | One entry per service: Whisper at `192.168.1.152:10300` and Kokoro at `192.168.1.152:10210` on the Mac, added by the setup script, plus Piper and openWakeWord discovered from their add-ons. Each entry produces an `stt.` or `tts.` entity the pipeline can pick |
| Laptop-side clients: `httpx` 0.28.1, `websockets` 17.1, `python-dotenv` 1.2.3 | An async HTTP client, a websocket client, and a reader of `KEY=value` files, all pinned in `uv.lock` | `ops/ha_client.py` reaches Home Assistant's REST and websocket APIs with the first two; the setup and deploy scripts read `.env` with the third |
| `mount_smbfs` and `osascript` | macOS's SMB mounter and its AppleScript runner | The deploy script mounts `//192.168.1.156/config` with the first; `scripts/haos_vm.sh create` tells UTM to build the VM with the second |

## How it works

### The virtual machine

```mermaid
flowchart TB
--8<-- "_includes/palette.mmd"
%% grid: .      .   .           puck  laptop
%% grid: piper  ma  others      core  samba
%% grid: .      .   supervisor  .     .
%% grid: .      .   utm         .     .
%% peers: puck laptop piper ma others core samba supervisor utm
puck("voice puck<br/>on the Wi-Fi")
laptop("laptop<br/>on the Wi-Fi")
subgraph mac["the Mac, 192.168.1.152"]
  subgraph haos["Home Assistant OS, a virtual machine with its own address: 192.168.1.156"]
    piper("Piper<br/>text to speech")
    ma("Music Assistant<br/>plays music")
    others("openWakeWord<br/>and ESPHome")
    core("Home Assistant Core<br/>web UI and API")
    samba("Samba<br/>/config as a share")
    supervisor("Supervisor<br/>runs each container")
  end
  utm("UTM<br/>runs the VM")
end
puck -- "audio" --> core
laptop -- "HTTP :80" --> core
laptop -- "SMB" --> samba
supervisor --> piper
supervisor --> ma
supervisor --> others
supervisor --> core
supervisor --> samba
utm -- "boots" --> supervisor
class puck,laptop hw
class piper,ma,others,core,samba,supervisor,utm third
style haos stroke:#f59e0b,stroke-width:4px
```

Why Home Assistant runs in a virtual machine:

- Home Assistant OS is not an app you install on the Mac. It is a whole Linux operating system, shipped as a disk image (`vm/haos_generic-aarch64-18.2.qcow2.xz`), that expects a computer of its own; UTM gives it a virtual one.
- Only Home Assistant OS can run add-ons, and this system needs five: Samba, Piper, Music Assistant, ESPHome, and openWakeWord.
- A Home Assistant container under Docker Desktop on macOS can do neither of the two things that matter. It cannot run add-ons, and it sits behind the Mac, so it never receives the multicast packets of mDNS, the way devices on a home network announce themselves by name. With bridged networking the VM gets its own address, `192.168.1.156`, and announces itself as `homeassistant.local`, so the puck and the Sonos find it like any other computer.
- The VM costs memory. With its add-ons running, the QEMU process holds about 7.5 GB of the 16 GB prototype, so the VM and a benchmark run never share the machine.

The VM has three ways in:

| Way in | Where | Used by |
|---|---|---|
| Web UI and API, REST and websocket | Port 80 of the VM's address | The setup script, the deploy, the health check, the smoke test, and your browser |
| The `/config` folder as an SMB share, served by the Samba add-on | `//192.168.1.156/config` | The deploy, which copies our custom component into `/config/custom_components/` |
| `utmctl`, UTM's command line | The Mac that hosts the VM | `scripts/haos_vm.sh` and the [health check](10_operations.md#the-health-check), to start, stop, and query the VM |

`scripts/haos_vm.sh create` builds the VM through UTM's AppleScript interface, without a click in the app.

*From `scripts/haos_vm.sh`, `create_vm`:*

```bash
VM_NAME="${HAOS_VM_NAME:-Home Assistant}"
VM_MEMORY_MB="${HAOS_VM_MEMORY_MB:-4096}"
VM_CPUS="${HAOS_VM_CPUS:-2}"
BRIDGE_INTERFACE="${HAOS_BRIDGE_INTERFACE:-$(route -n get default 2>/dev/null | awk '/interface:/{print $2}')}"
...
    osascript <<EOF
tell application "UTM"
	set diskImage to POSIX file "$image"
	set newVM to make new virtual machine with properties {backend:qemu, configuration:{name:"$VM_NAME", notes:"Home Assistant OS, created by scripts/haos_vm.sh", architecture:"aarch64", memory:$VM_MEMORY_MB, cpu cores:$VM_CPUS, uefi:true, hypervisor:true, drives:{{source:diskImage, interface:virtio}}, network interfaces:{{mode:bridged, host interface:"$BRIDGE_INTERFACE"}}}}
	return id of newVM
end tell
EOF
```

The four environment variables at the top let another Mac, such as the planned Mac mini, change the VM's name, memory, cores, or bridge interface without editing the script. The bridge defaults to the interface that carries the Mac's default route.

### The setup script

```mermaid
flowchart TB
--8<-- "_includes/palette.mmd"
%% grid: onboarding  addons  integrations  pipeline
%% grid: .           env     .             .
%% peers: onboarding addons integrations pipeline
onboarding("1. onboarding<br/>owner account, location<br/>a ten-year token")
addons("2. add-ons<br/>install and start five<br/>restarted if they die")
integrations("3. integrations<br/>Whisper, Kokoro, add-ons<br/>and our agent")
pipeline("4. pipeline<br/>Jarvis, built from<br/>Whisper, agent, Piper")
env[(".env<br/>on the laptop")]
onboarding --> addons
addons --> integrations
integrations --> pipeline
onboarding -- "HA_TOKEN" --> env
addons -- "HA_SAMBA_PASSWORD" --> env
integrations -- "two#nbsp;Wyoming#nbsp;entry#nbsp;ids" --> env
class onboarding,addons,integrations,pipeline,env ours
```

`scripts/ha_setup.py` takes a fresh Home Assistant OS to the configured one without the web interface. Every step first checks whether its work is already done, so the script can be rerun and adds only what is missing. Before any step, every run finds the API and saves its base URL to `.env` as `HA_BASE`.

1. **Onboarding.** Creates the owner account, sets the location to "Studio" with the time zone and coordinates from the command line, and finishes the first-boot wizard a person would otherwise click through. It saves `HA_ADMIN_USER`, `HA_ADMIN_PASSWORD` (generated if missing), `HA_HOST`, and `HA_TOKEN`, a long-lived access token with a 3,650-day lifespan that every later script call carries.
2. **Add-ons.** Installs Samba, Piper, Music Assistant, ESPHome, and openWakeWord, sets each one's options, starts it, and sets it to start at boot under the Supervisor's watchdog. It saves `HA_SAMBA_USER` and `HA_SAMBA_PASSWORD` (generated if missing), and Samba serves its shares only to private address ranges.
3. **Integrations.** Adds Wyoming entries for Whisper (port 10300) and Kokoro (port 10210) on the Mac and saves each entry's id, the only reliable rerun check because the entry listing hides host and port. It then confirms the flows the add-ons opened when they announced themselves, and runs our component's config flow with `http://192.168.1.152:11434`, the model tag (`gemma4:e4b-it-qat` unless `ASSISTANT_MODEL` says otherwise), and `http://192.168.1.152:8765/mcp`.
4. **Pipeline.** Builds "Jarvis", described under [Assist pipeline and intent matcher](#assist-pipeline-and-intent-matcher).
5. **Weather.** Copies Home Assistant's location, time zone, and unit system into `.env` as `WEATHER_LATITUDE`, `WEATHER_LONGITUDE`, `WEATHER_TIMEZONE`, and `WEATHER_UNITS` for the forecast tool, and hides every `weather.*` entity from Assist. `scripts/services.sh install` must run afterwards so the tool server receives the new values.

Home Assistant answers some requests only over REST and others only over its websocket:

| API | What the scripts use it for |
|---|---|
| REST, under `/api/` | Onboarding, config flows, service calls such as restart, and the conversation endpoint |
| Websocket, at `/api/websocket` | Minting tokens, the location settings, the entity registry, pipelines, flows in progress, and the Supervisor proxy that installs and starts add-ons |

`ops/ha_client.py` hides the split. Its `ws` method opens a fresh websocket for each command, authenticates, sends one message, and returns the reply, so callers manage no connection. `discover_base` finds the API by asking `/api/` on port 8123 and then on port 80, and accepts any answer below 500, including the 401 an unauthenticated request gets.

### Assist pipeline and intent matcher

```mermaid
flowchart TB
--8<-- "_includes/palette.mmd"
%% grid: .    puck     puck     .
%% grid: stt  intents  builtin  tts
%% grid: .    .        agent    .
%% peers: puck stt intents builtin tts agent
puck("voice puck<br/>or the Assist app")
stt("speech to text<br/>stt.mlx_whisper")
intents("intent matcher<br/>fixed sentences")
builtin("built-in handler<br/>music, weather")
tts("text to speech<br/>tts.piper")
agent("our agent<br/>studio_assistant")
puck -- "audio" --> stt
stt -- "text" --> intents
intents -- "match" --> builtin
builtin -- "reply" --> tts
tts -- "speech" --> puck
intents -- "no match" --> agent
agent -- "the answer, streamed" --> tts
class puck hw
class stt,intents,builtin,tts third
class agent ours
```

A pipeline is the chain of stages one request passes through, and building one means choosing an entity for each stage. The setup script's fourth step looks up three entities in the entity registry: the Wyoming speech-to-text entity for Whisper, the Wyoming text-to-speech entity for Piper, and the conversation entity our component registered. It creates or updates "Jarvis" from them and marks it as the preferred pipeline, the one Home Assistant uses unless told otherwise.

*From `scripts/ha_setup.py`, `pipeline`:*

```python
    stt = entity_id(registry, "stt", "wyoming", "whisper")
    tts = entity_id(registry, "tts", "wyoming", args.tts)
    agent = entity_id(registry, "conversation", "studio_assistant", "")
    payload = {
        "name": PIPELINE_NAME,
        "language": "en",
        "conversation_engine": agent,
        "conversation_language": "en",
        "stt_engine": stt,
        "stt_language": "en",
        "tts_engine": tts,
        "tts_language": "en_US",  # Piper and Kokoro advertise region codes (en_US, en_GB); a bare "en" is rejected at run time with tts-not-supported
        "tts_voice": None,
        "wake_word_entity": None,
        "wake_word_id": None,
        "prefer_local_intents": True,
    }
```

Two values in that payload matter most:

| Value | Why |
|---|---|
| `tts_language: "en_US"` | Piper and Kokoro advertise region codes, and a pipeline that asks for a bare `en` fails at run time with "tts-not-supported" |
| `prefer_local_intents: True` | Puts the intent matcher in front of our agent. Home Assistant's thousands of English sentence templates, plus Music Assistant's own, answer "play Radiohead" and "set volume to 50 percent" in tens of milliseconds with no language model. Only a sentence no template matches reaches `conversation.studio_assistant`, and so does every weather question: with no weather entity exposed to Assist, the built-in weather intent finds nothing to answer from |

When a sentence does reach our agent:

- **What it receives.** A `ConversationInput` with the sentence, and a chat log that holds the earlier exchanges of the same conversation, keyed by the conversation id.
- **Streaming.** Our entity declares that it supports streaming, so each sentence reaches text to speech as soon as the agent produces it, and the filler sentence plays while a search runs.
- **Follow-ups.** While the continue-conversation option is on, which it is by default, an ordinary answer carries `continue_conversation=True`, so the puck listens for a follow-up without a new wake word, at most `max_follow_ups` times in a row (two by default). An empty reply to speech not meant for the assistant, or "Okay.", does not carry it.
- **The text-only entrance.** `POST /api/conversation/process` with an `agent_id` hands text straight to that agent, skipping speech to text, the intent matcher, and text to speech, and returns the reply and the conversation id as JSON. The [smoke test](10_operations.md#deploy-smoke-test-and-rollback) uses it, and so does [Run it yourself](#run-it-yourself).

[Conversation Agent](04_conversation_agent.md) covers what happens inside the agent; [Voice Pipeline](05_voice_pipeline.md) covers the speech stages on either side of it.

### The custom component

```mermaid
flowchart LR
--8<-- "_includes/palette.mmd"
%% grid: stage  mount  swap     restart  wait
%% grid: .      .      restore  .        .
%% peers: stage mount swap restart wait restore
stage("1. stage<br/>our component with<br/>assistant_core")
mount("2. mount<br/>the VM's /config<br/>share over SMB")
swap("3. swap folders<br/>old one kept aside<br/>until copied")
restart("4. restart<br/>Home Assistant<br/>through its API")
wait("5. wait<br/>poll /api/ until<br/>it answers")
restore("restore<br/>the old folder<br/>and stop")
stage --> mount
mount --> swap
swap --> restart
restart --> wait
swap -- "copy fails" --> restore
class stage,mount,swap,restart,wait,restore ours
```

Home Assistant loads the Python packages under `/config/custom_components/` at startup, and that folder is on the VM's disk, so shipping our code means copying files across the network and restarting. The copy carries `assistant_core` under `vendor/` because it is not on PyPI; the component's `__init__.py` adds `vendor/` to the import path when the folder exists, so the same source runs from the repository in tests and from the vendored copy in the VM.

`scripts/deploy_component.py` does it in five steps:

1. **Stage.** Copy the component, with `assistant_core` under `vendor/`, into a temporary folder: the exact tree that will land in the VM.
2. **Mount.** Mount the Samba add-on's `config` share with `mount_smbfs`, as `HA_SAMBA_USER` with `HA_SAMBA_PASSWORD`.
3. **Swap.** Rename the deployed folder to `studio_assistant.prev`, copy the staged one in, then delete `.prev`. If the copy fails, delete the partial copy, rename `.prev` back, and stop.
4. **Restart.** Call `POST /api/services/homeassistant/restart`. Home Assistant often drops the connection as it shuts down instead of answering, and the script treats that as success.
5. **Wait.** Poll `/api/` every 5 seconds, for up to 300 seconds, until it answers with an authenticated 200.

Whether the copy succeeds or fails, a `finally` block unmounts the share and deletes the staging folder. Home Assistant is usually back about thirty seconds after the restart.

*From `scripts/deploy_component.py`, `sync`:*

```python
def sync(source: Path, target: Path) -> None:
    """Replace the deployed tree, keeping the previous one aside until the copy has finished so a failure halfway leaves the old component in place."""
    previous = target.with_name(target.name + ".prev")
    if previous.exists():
        shutil.rmtree(previous)
    if target.exists():
        target.rename(previous)
    try:
        shutil.copytree(source, target)
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        if previous.exists():
            previous.rename(target)
        raise
    if previous.exists():
        shutil.rmtree(previous)
```

On the Mac mini nobody runs the script by hand; [Operations](10_operations.md#deploy-smoke-test-and-rollback) covers the whole protocol:

- `ops/deploy.py` compares the old and new commits of a deploy, and its rules table maps any change under `custom_components/` or `assistant_core/` to the `deploy_component` action, which runs this script through the project's virtual environment.
- Before that, it checks that the versions pinned in `manifest.json` agree with `uv.lock`, because Home Assistant installs the manifest's requirements into its own environment and the vendored code must run against the `ollama` and `pydantic` it was tested with.

Three files decide what Home Assistant does with the folder:

| File | What Home Assistant does with it |
|---|---|
| `manifest.json` | Reads it at startup: the domain `studio_assistant`, `config_flow: true`, a dependency on the `conversation` integration, and the pinned requirements `ollama==0.6.2` and `pydantic>=2.0`, which it installs before importing our code |
| `config_flow.py` | Runs the config flow once, when the integration is added: a form for the Ollama URL, the model tag, and the MCP URL, checked against Ollama's `/api/tags` (the address must answer and list the model) before the entry is saved. It also runs the options flow behind the entry's Configure button, which edits the answer policy: model, temperature, spoken word budget, tool rounds, context window, output cap, thinking, tool timeout, whether to listen for a follow-up after an answer, and how many follow-ups in a row before the wake word is needed again |
| `__init__.py` | Runs `async_setup_entry` on every start. It forwards the saved entry to the conversation platform, which creates `conversation.studio_assistant`, and registers a listener that reloads the entry when the options change, so a new model tag takes effect without a restart |

## Run it yourself

Everything below runs from the repository folder with `.env` loaded (`set -a; source .env; set +a`). The VM and a benchmark must not run at the same time, so check first:

```bash
pgrep -fl benchmark-run || echo "no benchmark running"
scripts/haos_vm.sh status
```

`status` prints `stopped` or `started`. Start the VM and wait for the API, which takes about a minute after a normal stop and a few minutes on a first boot:

```bash
scripts/haos_vm.sh start
until curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $HA_TOKEN" http://192.168.1.156/api/ | grep -q 200; do sleep 5; done; echo "Home Assistant is up"
```

`scripts/haos_vm.sh ip` prints the address the VM was given, which is `192.168.1.156` on the studio network. Now open `http://192.168.1.156` in a browser and sign in with `HA_ADMIN_USER` and `HA_ADMIN_PASSWORD` from `.env`. Four settings pages show the pieces this page describes:

| Page | What you see |
|---|---|
| Settings, Devices & services | The Wyoming Protocol card with Whisper, Kokoro, Piper, and openWakeWord; Studio Assistant, our component, with a Configure button that opens the options flow; Music Assistant |
| Settings, Voice assistants | The "Jarvis" pipeline: speech to text `mlx-whisper`, conversation agent Studio Assistant, text to speech Piper. Click it to change any stage; switching text to speech to Kokoro here is how you compare voices |
| Settings, Add-ons | Samba, Piper, openWakeWord, Music Assistant, and ESPHome, each with its state, version, and log |
| Settings, System, Logs | Where component errors appear. Search for `studio_assistant` |

To chat with the assistant, open the Overview dashboard, tap the three-dot menu at the top right, and choose Assist. It opens a chat on the Jarvis pipeline:

| You type | You see |
|---|---|
| "Why does bread rise?" | An answer in two to five seconds once the model is warm |
| "What is 18 percent of 245 dollars?" | "Let me work that out." first, the filler sentence, then the answer from the calculator |
| "And what did I ask you first?" | The agent recalls it, because the chat log carries the conversation |

The browser's microphone button needs HTTPS, which the VM does not have, so typing is the way here; the Companion app on a phone gives you voice.

The same conversation from the command line goes through the text-only entrance described under [Assist pipeline and intent matcher](#assist-pipeline-and-intent-matcher) and shows the timing. The helper reads the JSON reply with `jq`, which ships with macOS:

```bash
ask() { curl -s -m 240 -X POST http://192.168.1.156/api/conversation/process \
  -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
  -d "{\"text\": \"$1\", \"language\": \"en\", \"agent_id\": \"conversation.studio_assistant\"${2:+, \"conversation_id\": \"$2\"}}" \
  | jq -r '.response.speech.plain.speech, "conversation_id: \(.conversation_id)"'; }

time ask "If I put 300 dollars a month into an account paying 5 percent a year, how much do I have after 3 years?"
```

You see the spoken answer, a `conversation_id`, and the elapsed time. Pass that id as a second argument to continue the same conversation:

```bash
ask "And after 5 years?" 01M1VPD9JAPX816PT6V0PHNNVZ
```

To watch the stages, go to Settings, Voice assistants, Jarvis, the three-dot menu, then Debug. Open the last run and every stage is listed with its timing and the exact text that passed between them: speech to text if you spoke, our agent, then text to speech. In a second terminal, `ollama ps` shows the model resident while an answer streams and `scripts/services.sh logs mcp` shows the tool server's request log.

If you have changed the component and want the VM to run it, deploy it; the copy takes seconds and the restart about thirty:

```bash
uv run python scripts/deploy_component.py
```

You see `deployed to //192.168.1.156/config/custom_components/studio_assistant`, then `Home Assistant restarting ...` and `Home Assistant back up`. Pass `--no-restart` to copy without restarting.

When you are done, stop the VM so the memory is free for the next benchmark pass:

```bash
scripts/haos_vm.sh stop
scripts/haos_vm.sh status
```

The rows of the troubleshooting table that belong to this page:

| Symptom | Likely cause | Check |
|---|---|---|
| Assist answers "Sorry, I couldn't understand that" | the pipeline could not reach the agent | Settings, System, Logs for `studio_assistant`; is Ollama up on the Mac? |
| The answer says it could not check the web | the tool server was unreachable from the VM | `curl http://192.168.1.152:8765/mcp` from the Mac; was the macOS firewall prompt for python denied? |
| Text to speech fails with "not supported" | pipeline language set to `en` instead of `en_US` | Settings, Voice assistants, Jarvis, text to speech language |
| The Mac gets sluggish and apps get killed | the VM, the speech services, and something else heavy at once | stop the VM as above, then Activity Monitor, Memory |

## Where to look in the code

| Path | What you find there |
|---|---|
| [`scripts/haos_vm.sh`](https://github.com/seanlin2000/home_assistant/blob/main/scripts/haos_vm.sh) | `create_vm`, which builds the VM through UTM's AppleScript interface with bridged networking; the `start`, `stop`, and `status` wrappers around `utmctl`; `resolve_ip` for `homeassistant.local` |
| [`scripts/ha_setup.py`](https://github.com/seanlin2000/home_assistant/blob/main/scripts/ha_setup.py) | The five rerunnable steps: `onboarding`, `addons` with the option tables, `integrations` with `run_flow` and `confirm_discovered_flows`, `pipeline` with the Jarvis payload, and `weather` with `save_home_location` and `hide_weather_entities_from_assist` |
| [`ops/ha_client.py`](https://github.com/seanlin2000/home_assistant/blob/main/ops/ha_client.py) | `HomeAssistant`: `discover_base`, REST `get` and `post`, the one-shot `ws` command, the `supervisor` proxy; `wait_for_api`, `entity_id`, and `converse`, the text-only call |
| [`scripts/deploy_component.py`](https://github.com/seanlin2000/home_assistant/blob/main/scripts/deploy_component.py) | `stage_component`, which vendors `assistant_core`; `mount` and `sync` over the Samba share; `restart_and_wait` |
| [`ops/deploy.py`](https://github.com/seanlin2000/home_assistant/blob/main/ops/deploy.py) | The `RULES` table that maps changed paths to actions, `deploy_component` among them, and `manifest_lock_mismatches`, the preflight that compares `manifest.json` with `uv.lock` |
| [`custom_components/studio_assistant/manifest.json`](https://github.com/seanlin2000/home_assistant/blob/main/custom_components/studio_assistant/manifest.json) | The domain, the `conversation` dependency, the pinned requirements, and the component version |
| [`custom_components/studio_assistant/config_flow.py`](https://github.com/seanlin2000/home_assistant/blob/main/custom_components/studio_assistant/config_flow.py) | `StudioAssistantConfigFlow` with the Ollama check, and `StudioAssistantOptionsFlow` with the answer policy form |
| [`custom_components/studio_assistant/__init__.py`](https://github.com/seanlin2000/home_assistant/blob/main/custom_components/studio_assistant/__init__.py) | The `vendor/` import path, `async_setup_entry`, and the reload-on-options listener |
| [`ops/pipeline_runs.py`](https://github.com/seanlin2000/home_assistant/blob/main/ops/pipeline_runs.py) | The websocket commands that read the Debug view's pipeline runs from the laptop |
| [`docs/VERSIONS.md`](https://github.com/seanlin2000/home_assistant/blob/main/docs/VERSIONS.md) | The UTM, Home Assistant OS, Core, and add-on versions on the running system, and the rule for updating Home Assistant monthly |

## Further reading

- Design doc: [`design_docs/v1/06_home_assistant_core.md`](https://github.com/seanlin2000/home_assistant/blob/main/design_docs/v1/06_home_assistant_core.md), whose as-built appendix records the API port, the flow-listing quirks, and the memory the VM takes on the prototype
- [Home Assistant installation methods](https://www.home-assistant.io/installation/), for the table of which install can run add-ons and which cannot
- [Home Assistant OS on macOS](https://www.home-assistant.io/installation/macos), the page the UTM setup follows, with the bridged-network step
- [Assist pipelines and local voice](https://www.home-assistant.io/voice_control/voice_remote_local_assistant/), for how the stages are chosen and what "prefer handling commands locally" does
- [The Wyoming integration](https://www.home-assistant.io/integrations/wyoming/), for how a host and port become an `stt.` or `tts.` entity
