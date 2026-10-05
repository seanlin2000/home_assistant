# Voice Pipeline
<!-- complexity: packages=3 parts=3 concepts=3 tier=deep -->

This page covers the voice pipeline, everything between your voice and the agent's text, and back again. A speech-to-text model turns what you say into text, Home Assistant passes that text to the agent, and a text-to-speech model turns the answer into sound on the device that asked. The speech servers talk to Home Assistant over a small network protocol called Wyoming, and until the puck arrives the microphone is the Companion app on a phone or the Assist window in a browser.

## Where this fits

```mermaid
flowchart TB
--8<-- "_includes/system_map.mmd"
class puck,stt,tts,piper,whisper current
```

## Key definitions

| Term | Meaning |
|---|---|
| Wyoming | A small line-based protocol that Home Assistant uses to talk to speech services over TCP, so a speech model can run on any machine it can reach by host and port. |
| Speech to text (STT) | A model that takes recorded audio and returns the text spoken in it. |
| Text to speech (TTS) | A model that takes text and returns audio of a voice speaking it. |
| Wake word | A short phrase, such as "Hey Jarvis", that a tiny always-on model listens for before a device sends any audio anywhere. |
| Voice activity detection (VAD) | Deciding from the audio when a person has started and stopped speaking. |
| PCM audio | Uncompressed sound stored as a sequence of integer samples, described by a sample rate, a sample width, and a channel count. |
| Time to first audio | How long a text-to-speech server takes from receiving text to sending its first audio chunk. |
| Phonemizer | A program that turns written text into the sequence of speech sounds a text-to-speech model pronounces. |
| ESPHome | A firmware framework for small Wi-Fi microcontrollers, configured in YAML and integrated with Home Assistant. |
| Far-field microphones | Microphones and processing built to hear a voice across a room, through echoes and background noise, rather than next to the mouth. |
| Acoustic echo cancellation | Subtracting the sound a device is playing from what its microphones hear, so it can listen while it talks. |

## Packages and tools

| Tool | What it is | How this part uses it |
|---|---|---|
| `wyoming` 1.7.2 | The Python library for the Wyoming protocol: event classes such as `Transcribe`, `AudioChunk`, and `Synthesize`, and a TCP client and server | Both speech servers are built on it; `scripts/voice_check.py` uses its `AsyncTcpClient` to talk to them without Home Assistant |
| `wyoming-mlx-whisper` 1.5.0 and `mlx-whisper` 0.4.3 | A Wyoming server around OpenAI's Whisper model, run through MLX on the Mac's GPU | Speech to text on port 10300, which Home Assistant sees as `stt.mlx_whisper` |
| `wyoming-kokoro-torch` 3.2.0 and `kokoro` 0.9.4 | A Wyoming server around the Kokoro-82M text-to-speech model, run through PyTorch | Text to speech on port 10210, through our `kokoro-server` entry point, which Home Assistant sees as `tts.kokoro` |
| `hexgrad/Kokoro-82M` weights | The model file `kokoro-v1_0.pth` and its `config.json`, published on Hugging Face | `scripts/services.sh install` downloads them once and links them into `~/.cache/wyoming-kokoro`, the server's data directory. Voices download on first use |
| espeak-ng | A phonemizer, installed with Homebrew from the `Brewfile` | The fallback in Kokoro's English text processing. `misaki`, which `kokoro` installs, turns text into phonemes from its own dictionaries and hands espeak-ng only what they do not cover |
| Piper add-on 2.3.4 | Home Assistant's own neural text-to-speech engine, running as an add-on inside the VM | The pipeline's default text-to-speech entity, `tts.piper`, with the voice `en_US-lessac-medium` and streaming on |
| openWakeWord add-on 2.1.1 | A server-side wake word engine, running as an add-on | Installed with threshold 0.5 and trigger level 1, and not assigned to the pipeline, because the puck detects the wake word on its own chip |
| ESPHome add-on 2026.8.2 | The firmware framework and the add-on that adopts devices running it | Waits for the puck, to discover it on the network and expose its wake word selector, LEDs, and media player |
| Home Assistant Voice Preview Edition | A small puck with far-field microphones, echo cancellation, an on-device wake word, a speaker, and a mute switch | The microphone and speaker the system is built for, not connected yet |
| Home Assistant Companion app | Home Assistant's phone app, with a push-to-talk Assist button | The microphone today; its audio goes through the real Jarvis pipeline |
| launchd | macOS's service manager | Runs Whisper and Kokoro as two agents that start at login and restart when they exit |

## How it works

### One question, end to end

```mermaid
flowchart TB
--8<-- "_includes/palette.mmd"
%% grid: .        puck     .
%% grid: stt      intents  tts
%% grid: .        .        piper>
%% grid: whisper  .        <kokoro
%% peers: puck stt intents tts piper whisper kokoro
%% column-gap: 160
puck("Puck")
subgraph mac["the Mac, 192.168.1.152"]
  subgraph haos["Home Assistant OS, a VM at 192.168.1.156"]
    stt("speech to text<br/>stt.mlx_whisper")
    intents("intent matcher<br/>or our agent")
    tts("text to speech<br/>tts.piper or kokoro")
    piper("Piper add-on<br/>Wyoming, in the VM")
  end
  whisper("Whisper, on the GPU<br/>Wyoming, port 10300")
  kokoro("Kokoro, on the CPU<br/>Wyoming, port 10210")
end
puck -- "audio" --> stt
stt -- "text" --> intents
intents -- "the answer" --> tts
tts -- "speech" --> puck
stt -- "audio" --> whisper
whisper -- "text" --> stt
tts -- "text" --> kokoro
kokoro -- "speech" --> tts
tts -- "text" --> piper
piper -- "speech" --> tts
class puck hw
class stt,intents,tts,whisper,piper third
class kokoro ours
```

Every spoken question runs through the Assist pipeline named "Jarvis", Home Assistant's chain of stages for one request (see [Home Assistant](06_home_assistant_core.md#assist-pipeline-and-intent-matcher)). `scripts/ha_setup.py` creates it over the websocket API with these settings:

| Stage or setting | Entity or value |
|---|---|
| Speech to text | `stt.mlx_whisper`, language `en` |
| Conversation | `conversation.studio_assistant`, language `en` |
| Text to speech | `tts.piper`, language `en_US`; `--tts kokoro` picks `tts.kokoro` instead |
| Wake word | None, because the puck detects it on its own chip |
| `prefer_local_intents` | On, so Home Assistant's fixed sentences answer first and the agent gets the rest |
| Preferred pipeline | Yes, so the Companion app and the browser use it without being told |

Home Assistant reaches each speech server over a Wyoming connection:

- One TCP connection carries a sequence of events. Each event is one line of JSON naming its type, such as `transcribe` or `audio-chunk`, optionally followed by a binary payload, which is how raw audio travels without being encoded as text.
- Home Assistant opens a fresh connection for each request and closes it when the request is done.
- To learn what a server offers, it sends `describe`. The `info` event that comes back lists the models, the voices, and whether the server accepts streamed text.

Two things the [conversation agent](04_conversation_agent.md) does shape what you hear on the way back:

- **The filler sentence.** When the model asks for a tool, the agent streams a short sentence such as "Let me pull some sources on that." first, so the speaker starts before the search finishes.
- **`continue_conversation`.** By default an ordinary answer carries this flag, at most twice in a row, which tells the device to listen again for a few seconds, so "and tomorrow?" works without the wake word. The reply to speech not meant for the assistant is empty, so the pipeline skips text to speech, and neither it nor "Okay.", the reply to "never mind", carries the flag.

### Speech to text

Whisper is a model that reads a whole clip of audio and writes out the text in it. The upstream server, `wyoming-mlx-whisper`, buffers every `audio-chunk` and transcribes only after `audio-stop`, in one call, then sends a single `transcript` event and closes the connection. Two things follow:

- Voice activity detection has to decide you have stopped talking before transcription can start.
- The whole clip's transcription time sits in the [latency budget](#the-latency-budget).

What this repository chooses for it:

- **Native, on the GPU.** The server runs as a process on the Mac, not in the VM or a container, because only a native process can reach the GPU through Metal and MLX (see [LLMs on Apple Silicon](02_local_llm.md)).
- **The model.** `mlx-community/whisper-large-v3-turbo` downloads from Hugging Face on the first start. On the prototype the process holds about 2.5 GB of memory.
- **English only.** `--language en` skips language detection. The server ignores the language in the `transcribe` event, so this flag is what decides.

`scripts/services.sh install` writes one launchd agent per server; these are the two lines that start them:

*From `scripts/services.sh`, `install_agents`:*

```bash
    ENV_KEYS=() ENV_VALUES=()
    write_plist whisper "$PROJECT_DIR/.venv/bin/wyoming-mlx-whisper" --uri tcp://0.0.0.0:10300 --model mlx-community/whisper-large-v3-turbo --language en
    write_plist kokoro "$PROJECT_DIR/.venv/bin/kokoro-server" --uri tcp://0.0.0.0:10210 --voice af_heart --data-dir "$HOME/.cache/wyoming-kokoro" --streaming --device cpu
```

| Flag | What it sets |
|---|---|
| `--uri tcp://0.0.0.0:10300`, `:10210` | Listen on every interface, so the VM reaches the servers at the Mac's LAN address. `scripts/ha_setup.py` registers each with the Wyoming integration, which asks only for a host and a port |
| `--model`, `--language en` | Whisper's model and its fixed language |
| `--voice af_heart` | Kokoro's default voice, used when Home Assistant names none |
| `--data-dir ~/.cache/wyoming-kokoro` | Where Kokoro finds the weights that `prepare_kokoro` fetched from `hexgrad/Kokoro-82M`, and where it saves the voices it downloads |
| `--streaming` | Kokoro accepts streamed text; see [Text to speech](#text-to-speech) |
| `--device cpu` | Kokoro's PyTorch model runs on the CPU |

Three things keep both servers up:

- **launchd** starts each agent at login and starts it again whenever it exits, at most once every 10 seconds. Output goes to `whisper.log` and `kokoro.log` in `~/Library/Logs/studio-assistant/`.
- **The [health check](10_operations.md#the-health-check)** opens a TCP connection to ports 10300 and 10210 every 300 seconds. After two failures in a row it restarts that agent with `launchctl kickstart -k`, at most once every 30 minutes. An agent that is not loaded counts as stopped on purpose and is left alone.
- **The macOS firewall** asks once, per binary, whether to allow incoming connections. The answer must be yes, or the VM's calls time out.

### Text to speech

Kokoro speaks each sentence as soon as the agent finishes writing it, so you hear the first sentence while the agent writes the second. That is also why the filler sentence plays while a search runs.

The sentence splitting happens in the upstream server. Started with `--streaming`, it tells Home Assistant in its `info` that it accepts streamed text, and Home Assistant sends the answer piece by piece as the agent writes it. The server's sentence-boundary detector releases each complete sentence to the model, and the audio goes back as 16-bit PCM at 24 kHz, in chunks of 1,024 samples.

What `voice/kokoro_server.py` adds:

- **The problem.** The upstream handler builds a new Kokoro model and a new per-language pipeline for every connection, and Home Assistant opens a connection for every synthesis and every capability check. On this machine that costs one to two seconds before the first sample, the whole budget for the filler sentence.
- **The fix.** The `kokoro-server` entry point swaps the two classes the handler constructs for stand-ins that return one cached instance, then runs the upstream server unchanged. `pyproject.toml` registers the command.

The stand-in for the model and the entry point that installs it:

*From `voice/kokoro_server.py`, `SharedKModel` and `main`:*

```python
@functools.lru_cache(maxsize=None)
def shared_model(model: str, config: str) -> Any:
    return _ORIGINAL_MODEL(model=model, config=config)
...
class SharedKModel:
    """Stands in for kokoro.KModel: same constructor, returns the one cached instance. `.to(device)` and `.eval()` are cheap on an already-moved model."""

    def __new__(cls, model: str, config: str) -> Any:
        instance = shared_model(model, config)
        _MODELS_BY_ID[id(instance)] = instance
        return instance
...
def main() -> None:
    kokoro_handler.KModel = SharedKModel
    kokoro_handler.KPipeline = SharedKPipeline
    asyncio.run(upstream_main())
```

The pipeline can use either engine:

| | Piper | Kokoro |
|---|---|---|
| Runs | As an add-on inside the VM | Natively on the Mac, on the CPU |
| How Home Assistant finds it | Discovered from the add-on | A Wyoming entry for `192.168.1.152:10210` |
| Voice | `en_US-lessac-medium` | `af_heart` |
| Streaming | The add-on's `streaming` option, on | The `--streaming` flag |
| First sentence synthesized | About 0.05 s | About 0.2 s |
| Sound | Faster and plainer | More like a person |
| In the pipeline | The default, `tts.piper` | `tts.kokoro`, after `scripts/ha_setup.py --tts kokoro` |

Kokoro has 82 million parameters, takes about 1 GB of memory, and synthesizes a ten-second answer in under a second, spread across its sentences. Both engines advertise region codes such as `en_US` rather than `en`, which is why the pipeline's text-to-speech language is `en_US`. A pipeline saved with `en` is accepted by the editor and fails every run with `tts-not-supported`.

### The latency budget

What you feel is the silence between your last word and the first spoken word. These are the stages, in pipeline order:

| Stage | Time | Where the number comes from |
|---|---|---|
| Wake word to streaming, before you speak | Under 100 ms, on the puck | Design doc 05, latency budget |
| End of speech detected | 0.3 to 0.8 s | Design doc 05, latency budget |
| Whisper transcribes the clip | 2.7 s for a 3.7 s clip on the prototype | Design doc 05, as built |
| The agent's first sentence | 2.3 s with the model warm and no tool call; 35 s on the first question after a model load | Design doc 05, as built |
| First sentence through text to speech | 0.05 s with Piper, 0.2 s with Kokoro | Design doc 05, latency budget |
| Search and a second model call, when the agent searches | 2 to 5 s, heard as the filler sentence | Design doc 05, latency budget |
| Each later sentence through text to speech | 0.05 to 0.3 s, while the one before it plays | Design doc 05, latency budget |

Added up, the first sentence starts about 5 to 6 s after you stop talking on the prototype with the model warm, and the 35 s case is why Ollama [keeps the model resident](02_local_llm.md#keeping-a-model-resident).

### Today and with the puck

The puck is not connected yet. Until it is, the Companion app and the browser's Assist window stand in for it, and everything behind them is the real thing.

| Stage | Today | With the puck |
|---|---|---|
| Wake word | None. You hold the Assist button in the Companion app, or type in the browser | "Hey Jarvis", detected by microWakeWord on the puck's ESP32-S3, so no audio leaves the device until it fires. The openWakeWord add-on stays unused |
| Microphone | The phone's microphone | Two far-field microphones behind an XMOS chip that cancels its own playback and suppresses noise, so it hears you across the room, even while it speaks |
| Transport to Home Assistant | The Companion app's connection to the VM | ESPHome's voice assistant protocol over Wi-Fi, once the ESPHome add-on finds the puck by mDNS on the bridged network |
| Speech to text, agent, text to speech | Whisper on the Mac, `studio_assistant`, Piper or Kokoro | The same |
| Playback | The phone's speaker, or the browser | The puck's small speaker or its 3.5 mm line out, with an LED ring, a dial, and a mute switch that physically cuts the microphones |
| Follow-up | Press the Assist button again | After an ordinary answer, at most twice in a row, the puck reopens its microphone for a few seconds, because the reply carries `continue_conversation` |

When the puck arrives, the ESPHome add-on adopts it, its device page gets the Jarvis pipeline and "Hey Jarvis", and the rest of this page applies unchanged. [Hardware](08_hardware_and_deployment.md) covers the network side: the puck, the VM, and the Mac each need a fixed address, and the puck's own speaker is for voice, not music.

## Run it yourself

Everything here runs on the Mac, from the repository folder. `scripts/voice_check.py` is a small Wyoming client that talks to each server the way Home Assistant does, and these are the events it sends and receives:

| Command | Sends | Receives |
|---|---|---|
| `info` | `describe` | `info` |
| `tts` | One `synthesize` with the whole text | `audio-start`, `audio-chunk` events, `audio-stop` |
| `stt` | `transcribe`, `audio-start`, one `audio-chunk` per tenth of a second of audio, `audio-stop` | `transcript` |

Unlike Home Assistant, `tts` sends the whole text at once, but the server still splits it into sentences, so the time to first audio still shows sentence-at-a-time synthesis.

1. Check that the two speech services are up, because they are stopped whenever a benchmark needs the memory:

    ```bash
    scripts/services.sh status
    ```

    You want `whisper: listening on 10300` and `kokoro: listening on 10210`.

2. If either says `NOT listening`, load the agents and watch Whisper come up:

    ```bash
    scripts/services.sh start
    scripts/services.sh logs whisper      # Ctrl-C to stop tailing
    ```

    On a first start Whisper prints its URI, model, and language, then `Loading model...`, downloads the model from Hugging Face, and prints `Ready`; later starts skip the download. `scripts/services.sh logs kokoro` shows the same `Ready` for Kokoro.

3. Ask each server what it offers, with the same `describe` event Home Assistant sends:

    ```bash
    uv run python scripts/voice_check.py info --port 10300
    uv run python scripts/voice_check.py info --port 10210
    ```

    The first prints `asr: mlx-whisper models=['mlx-community/whisper-large-v3-turbo']`. The second prints `tts: kokoro supports_synthesize_streaming=True voices=[...]` with the first twelve voice names.

4. Synthesize a sentence with Kokoro and listen to it:

    ```bash
    uv run python scripts/voice_check.py tts --port 10210 --text "Let me work that out. Eighteen percent of two hundred forty-five dollars is forty-four dollars and ten cents." --out /tmp/kokoro.wav
    afplay /tmp/kokoro.wav
    ```

    The script prints one line of the form `tts: first audio after 0.00s, 0.0s of audio in 0.00s (0.0x real time), 0 chunks -> /tmp/kokoro.wav`, with your numbers. A first-audio time well below the total means the first sentence left before the second was synthesized. `--voice am_michael`, or any name from the `info` output, tries another voice.

5. Transcribe that file back with Whisper:

    ```bash
    uv run python scripts/voice_check.py stt --port 10300 --wav /tmp/kokoro.wav
    ```

    You get one line of the form `stt: 0.00s for 0.0s of audio -> 'Let me work that out. ...'`, with Whisper's own punctuation and capitalisation. On the prototype a clip takes a little less than its own length to transcribe. To try your own voice, record a 16-bit WAV with QuickTime or any recorder and pass it with `--wav`; the server converts it to 16 kHz mono.

6. Speak to the whole pipeline. Start the Home Assistant VM (see [Home Assistant](06_home_assistant_core.md#run-it-yourself)), then use either microphone:
    - **The Companion app** on a phone on the same Wi-Fi: add the server at `http://192.168.1.156`, sign in, tap the Assist icon, and hold the microphone button while you ask a question. Whisper hears you, the agent answers, and Piper speaks through the phone.
    - **The browser:** open `http://192.168.1.156`, open the Assist window, and type a question. Piper's audio plays in the browser.

    Listen for how soon the first sentence starts after you stop talking, about 5 to 6 s on the prototype with the model warm, and for whether the answer sounds like a person talking rather than a document being read.

7. When you are done, stop the two speech services and leave Ollama and the tool server running:

    ```bash
    launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.studio-assistant.whisper.plist
    launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.studio-assistant.kokoro.plist
    scripts/services.sh status         # ollama and mcp stay up; whisper and kokoro should be gone
    ```

    The health check reads an unloaded agent as stopped on purpose and does not restart it. `scripts/services.sh stop` unloads all five agents instead, including Ollama, the tool server, and the health check, and `scripts/services.sh start` brings everything back.

## Where to look in the code

| Path | What you find there |
|---|---|
| [`voice/kokoro_server.py`](https://github.com/seanlin2000/home_assistant/blob/main/voice/kokoro_server.py) | The `kokoro-server` entry point: `SharedKModel` and `SharedKPipeline`, which load the Kokoro model once and hand it to every connection, and `main`, which patches them into the upstream handler and starts the upstream server |
| [`scripts/voice_check.py`](https://github.com/seanlin2000/home_assistant/blob/main/scripts/voice_check.py) | A Wyoming client with three commands, `info`, `tts`, and `stt`: the events each connection sends, the timing lines they print, and `write_wav`, which turns audio chunks into a file |
| [`scripts/services.sh`](https://github.com/seanlin2000/home_assistant/blob/main/scripts/services.sh) | `install_agents`, which writes the Whisper and Kokoro launchd agents with their ports, model, voice, and flags; `prepare_kokoro`, which fetches and links the model weights; `status` and `logs` |
| [`scripts/ha_setup.py`](https://github.com/seanlin2000/home_assistant/blob/main/scripts/ha_setup.py) | `WYOMING_SERVICES` and `integrations`, which register the two servers by host and port; `ADDONS`, with the Piper and openWakeWord options; `pipeline`, which creates the Jarvis pipeline and its languages |
| [`pyproject.toml`](https://github.com/seanlin2000/home_assistant/blob/main/pyproject.toml) | The `voice` dependency group, `wyoming-kokoro-torch` and `wyoming-mlx-whisper`, and the `kokoro-server` script entry |
| [`Brewfile`](https://github.com/seanlin2000/home_assistant/blob/main/Brewfile) | `espeak-ng`, the fallback phonemizer Kokoro needs |
| [`ops/health.py`](https://github.com/seanlin2000/home_assistant/blob/main/ops/health.py) | The TCP probes on ports 10300 and 10210, the restart policy, and the rule that an unloaded agent counts as stopped on purpose |
| [`docs/VERSIONS.md`](https://github.com/seanlin2000/home_assistant/blob/main/docs/VERSIONS.md) | The versions of the Wyoming packages and of the Piper, openWakeWord, and ESPHome add-ons on the running system |

## Further reading

- Design doc: [`design_docs/v1/05_voice_pipeline.md`](https://github.com/seanlin2000/home_assistant/blob/main/design_docs/v1/05_voice_pipeline.md), which also lists the failure modes, from false wake-ups to cut-off transcripts, and what to tune for each
- [Wyoming protocol](https://github.com/rhasspy/wyoming), for the full list of event types and the exact wire format of an event and its binary payload
- [wyoming-mlx-whisper](https://pypi.org/project/wyoming-mlx-whisper/), for the server's flags and the Whisper models it can load
- [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M), for the model's voices, languages, and licence
- [Home Assistant streaming text to speech](https://www.home-assistant.io/integrations/tts/), for how the pipeline hands streamed text to an engine that supports it
- [Piper voice samples](https://rhasspy.github.io/piper-samples/), to hear the voices before changing `en_US-lessac-medium`
- [Voice Preview Edition](https://www.home-assistant.io/voice-pe/), for the puck's hardware, and [wake words on the puck](https://www.home-assistant.io/voice_control/about_wake_word/), for what the device detects on its own chip
