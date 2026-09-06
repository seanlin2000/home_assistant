# 05. Voice pipeline

## 1. Purpose

Everything between your voice and the agent's text, and back: the puck that hears "Hey Jarvis" and streams audio, the speech-to-text model that turns audio into words, and the text-to-speech engines that turn the answer into sound. All of it runs in the studio. The speech models run on the Mac's GPU outside the Home Assistant VM and plug into the pipeline over a small network protocol called Wyoming.

## 2. Diagram

```
   Voice Preview Edition puck                              Home Assistant (VM)                    native macOS (.venv)
 ┌──────────────────────────────┐                        ┌──────────────────────┐              ┌────────────────────────┐
 │ 2 MEMS mics                  │                        │ Assist pipeline       │   Wyoming    │ wyoming-mlx-whisper    │
 │   ↓                          │                        │                       │  audio-chunk │  whisper-large-v3-turbo│
 │ XMOS XU316 chip              │                        │  1. receive audio ────┼──────────────▶  on GPU via MLX       │
 │   echo cancel, noise suppress│  ESPHome voice         │  2. transcript ◀──────┼──────────────│  → transcript          │
 │   ↓                          │  assistant protocol    │                       │              └────────────────────────┘
 │ ESP32-S3                     │  over Wi-Fi            │  3. intents / agent   │
 │   microWakeWord "Hey Jarvis" │──── audio stream ─────▶│                       │              ┌────────────────────────┐
 │   only after wake word       │                        │  4. answer text,      │   Wyoming    │ Kokoro Wyoming server  │
 │   ↓                          │◀─── reply audio ───────│     sentence by       │  synthesize  │  82M params, CPU/MLX   │
 │ small speaker, 3.5 mm out    │                        │     sentence ─────────┼──────────────▶ or                     │
 │ LED ring, dial, mute switch  │                        │                       │◀──audio──────│ Piper (HA add-on)      │
 └──────────────────────────────┘                        │  5. continue          │              └────────────────────────┘
                                                         │     conversation:     │
                                                         │     puck reopens mic  │
                                                         └──────────────────────┘
```

## 3. How it works, step by step

1. **Wake word on the puck.** The puck's ESP32-S3 runs microWakeWord, a small neural network trained on one phrase. It processes the microphone stream locally and forever; nothing is sent anywhere until it fires. "Hey Jarvis" is one of three phrases shipped on the device.
2. **Audio conditioning.** Before the wake word model and before streaming, the XMOS chip applies acoustic echo cancellation (so the puck can hear you while it is speaking) and noise suppression. This is what makes across-the-room pickup work in a studio.
3. **Streaming to Home Assistant.** After the wake word, the puck streams 16 kHz audio over Wi-Fi to Home Assistant using ESPHome's voice assistant protocol. Voice activity detection decides when you have stopped talking.
4. **Speech to text.** The pipeline forwards the audio to a Wyoming speech-to-text service. Ours is `wyoming-mlx-whisper` running natively on the Mac, using OpenAI's Whisper large-v3-turbo model through Apple's MLX so it runs on the GPU. It returns the transcript. English-only configuration keeps it fast and accurate.
5. **Intents, then the agent.** Covered in docs 04 and 06.
6. **Text to speech.** The agent's answer streams back sentence by sentence. The pipeline sends each sentence to the selected Wyoming text-to-speech service and plays the audio on the puck as it arrives. Two services are installed: Piper (Home Assistant's official add-on, fast, plain) and Kokoro (a community Wyoming wrapper around an 82M-parameter model with natural voices). Switching is a dropdown in the pipeline settings. You pick by listening on the real puck in the real room.
7. **Follow-up.** With `continue_conversation`, the puck reopens the microphone after the reply for a few seconds, so "and tomorrow?" works without the wake word.

## 4. Latency budget

| Stage | Typical | Notes |
|---|---|---|
| Wake word to streaming | <100 ms | on device |
| End of speech detection | 300 to 800 ms | voice activity detection needs silence to be sure |
| Whisper large-v3-turbo on M1 Pro (MLX) | near real-time, so ~0.5 s for a 5 s utterance | faster on the M6 |
| Agent: time to first token | 0.5 to 2 s without search on the production Mac | see doc 02 |
| Filler sentence via TTS | 0.05 s (Piper) or 0.2 s (Kokoro) | heard while the search runs |
| Search plus second model call | 2 to 5 s on the production Mac | the delay you accepted |
| TTS per subsequent sentence | 0.05 to 0.3 s | overlaps with playback of the previous sentence |

Kokoro synthesizes about 14 times faster than real time on an M1 CPU, so a ten-second answer costs under a second of synthesis, spread across sentences. The one thing to verify in the prototype is whether the Kokoro wrapper supports Wyoming's streaming synthesis events. If it does not, Home Assistant waits for the whole answer before speaking through Kokoro, which adds roughly a second and blunts the filler sentence. The fallback is a Wyoming server of our own (about 150 lines with the `wyoming` and `kokoro` packages) that streams.

## 5. Packages and what they do for us

| Package or component | Role in the business logic |
|---|---|
| Voice Preview Edition hardware | Two far-field microphones, XMOS audio front end, ESP32-S3 running the wake word, a small speaker, a 3.5 mm line out, a dial, a hardware mute switch that physically cuts the microphones. $69. |
| ESPHome (firmware and Home Assistant add-on) | The firmware on the puck and the integration that adopts it. Handles the audio streaming protocol and lets us change the wake word or LED behavior from a YAML file. |
| microWakeWord | The on-device wake word engine. Ships "Okay Nabu", "Hey Jarvis", "Hey Mycroft". Custom phrases are possible through openWakeWord on the server side at some cost in latency and accuracy; not needed. |
| `wyoming` | The protocol library. Newline-delimited JSON events with binary audio payloads over TCP: `audio-start`, `audio-chunk`, `transcribe`, `synthesize`, and so on. Any process that speaks it can be a pipeline stage. |
| `wyoming-mlx-whisper` and `mlx-whisper` | Speech to text on the Mac GPU. Default model whisper-large-v3-turbo. Runs from our `.venv`. Fallback `wyoming-faster-whisper` runs on the CPU with the `small` or `medium` model. |
| Piper (Home Assistant add-on) | Official neural text to speech. Near-instant, dozens of English voices, supports streaming. |
| Kokoro via `kokoro-wyoming` (or our own Wyoming server) | Natural-sounding text to speech, 82M parameters, Apache-licensed. Voices such as `af_heart`, `af_bella`, `am_michael`. Runs on the CPU fast enough; MLX and Core ML builds exist for more speed. |

## 6. Configuration we control

- Puck: wake word selection, LED and volume behavior, which pipeline it uses, all from the Home Assistant device page or the ESPHome YAML.
- Pipeline: which STT service, which TTS service and voice, language `en`, "prefer handling commands locally", the conversation agent.
- Whisper: model name, language `en`, beam size, port.
- Kokoro: voice, speed, port. Piper: voice, quality level.
- Where each service listens: all on the Mac's LAN address, ports fixed and documented, launched at login by launchd.

## 7. Failure modes

- **False wake-ups or missed wake-ups.** Tune sensitivity per wake word on the device page. "Hey Jarvis" is well trained; the mute switch is the hard guarantee.
- **Cut-off transcripts.** Voice activity detection ended too early. Raise the silence threshold in the pipeline settings.
- **Whisper misrecognizes names** (artists, places). Expected with any speech model; Music Assistant's fuzzy matching absorbs most of it for music. For questions, the agent can ask to confirm.
- **Kokoro wrapper not streaming.** Described above; fallback is our own server.
- **Puck cannot find Home Assistant.** Discovery uses mDNS, which is why Home Assistant runs in a bridged VM rather than a Docker container on the Mac.
- **Puck speaker is small.** Fine for voice, not for music. Music goes to the Sonos (doc 07).

## 8. Concepts for newcomers

**Far-field microphones.** Microphones and processing designed to pick up a voice several meters away in a room with echoes and background noise, as opposed to a phone held near the mouth. Two microphones let the chip estimate direction and suppress noise from elsewhere.

**Acoustic echo cancellation.** Subtracting the sound the device itself is playing from what the microphones hear, so it can listen while it talks. Without it, follow-up questions during playback fail.

**Voice activity detection (VAD).** Deciding when speech starts and stops. Too eager and it cuts you off; too patient and every answer starts late.

**Speech to text (STT).** Audio in, text out. Whisper is a family of open models from OpenAI; large-v3-turbo is the current speed and quality balance. "Near real-time" means a five-second utterance takes about five seconds or less to transcribe when processed as a whole, and much less on a fast GPU.

**Text to speech (TTS).** Text in, audio out. Piper and Kokoro are both neural models; Kokoro is larger and sounds more human. "14x real time" means one second of audio takes about 70 ms to produce.

**Wyoming.** The protocol tying the stages together. It matters because it decouples where a model runs from where Home Assistant runs; our speech models live on the Mac GPU, outside the VM, and Home Assistant only needs a host and port.

**ESPHome.** A firmware framework for small Wi-Fi microcontrollers, configured in YAML and integrated tightly with Home Assistant. The puck runs it.

**MEMS microphone.** A microphone built on a silicon chip. Small, cheap, consistent; the standard in voice devices.

## 9. Sources

- Voice Preview Edition hardware and specs: [home-assistant.io/voice-pe](https://www.home-assistant.io/voice-pe/)
- Wake words on the puck and custom wake words: [home-assistant.io/voice_control/about_wake_word](https://www.home-assistant.io/voice_control/about_wake_word/), [create_wake_word](https://www.home-assistant.io/voice_control/create_wake_word/)
- Wyoming protocol: [github.com/rhasspy/wyoming](https://github.com/rhasspy/wyoming)
- wyoming-mlx-whisper: [pypi.org/project/wyoming-mlx-whisper](https://pypi.org/project/wyoming-mlx-whisper/)
- Home Assistant streaming TTS: [home-assistant.io/integrations/tts](https://www.home-assistant.io/integrations/tts/)
- Piper voices and samples: [rhasspy.github.io/piper-samples](https://rhasspy.github.io/piper-samples/)
- Kokoro model: [huggingface.co/hexgrad/Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M), Wyoming wrapper: [github.com/nordwestt/kokoro-wyoming](https://github.com/nordwestt/kokoro-wyoming)
- Kokoro speed on Apple Silicon: [runanywhere.ai](https://www.runanywhere.ai/blog/metalrt-speech-fastest-stt-tts-apple-silicon)
