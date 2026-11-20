# 00. System overview

## 1. Purpose

A voice assistant for a 500 square foot studio that keeps its data at home. You say "Hey Jarvis" and ask a question; it answers from its own knowledge or, when the question needs current information, from a web search. It also plays Spotify and reports the weather. Everything that can run locally does: the wake word, speech recognition, the language model, speech synthesis, and the search aggregator. The only traffic that leaves the apartment is the search query itself, Spotify's API calls, and a pair of coordinates for the weather service.

Priorities, in order: (1) answering questions well, including with web search, (2) Spotify, (3) weather.

## 2. Diagram

```
                                   YOUR STUDIO (everything inside this box stays local)
 ┌───────────────────────────────────────────────────────────────────────────────────────────────────────┐
 │                                                                                                       │
 │   "Hey Jarvis, who won                                                                                │
 │    the Ballon d'Or?"        Wi-Fi                 Mac (always on)                                     │
 │   ┌────────────────┐  audio ──────▶  ┌──────────────────────────────────────────────────────────┐    │
 │   │ Voice PE puck  │                 │ Home Assistant OS (virtual machine)                       │    │
 │   │  2 far-field   │  reply ◀──────  │                                                           │    │
 │   │  mics, speaker │                 │   Assist pipeline                                         │    │
 │   │  wake word     │                 │   ┌──────┐   ┌─────────┐   ┌───────────────┐   ┌──────┐  │    │
 │   │  runs on-device│                 │   │ STT  │──▶│ intents │──▶│ our agent      │──▶│ TTS  │  │    │
 │   └────────────────┘                 │   └──┬───┘   └────┬────┘   └──────┬────────┘   └──┬───┘  │    │
 │                                      │      │            │               │                │      │    │
 │   ┌────────────────┐                 │      │     "play X", "weather"    │ LLM calls      │      │    │
 │   │ Sonos speaker  │◀── music ───────│      │     handled without LLM    │                │      │    │
 │   └────────────────┘                 │      │            │               │                │      │    │
 │                                      └──────┼────────────┼───────────────┼────────────────┼──────┘    │
 │                                             ▼            ▼               ▼                ▼           │
 │                                      ┌───────────┐ ┌───────────┐  ┌─────────────┐  ┌────────────┐   │
 │                                      │ Whisper   │ │ Music     │  │ Ollama +    │  │ Kokoro or  │   │
 │                                      │ (MLX, GPU)│ │ Assistant │  │ chosen model│  │ Piper      │   │
 │                                      └───────────┘ └─────┬─────┘  └──────┬──────┘  └────────────┘   │
 │                                                          │               │ tool call                │
 │                                                          │        ┌──────▼──────────┐               │
 │                                                          │        │ web_search_mcp  │               │
 │                                                          │        │ (ours, Python)  │               │
 │                                                          │        └──────┬──────────┘               │
 │                                                          │        ┌──────▼──────────┐               │
 │                                                          │        │ SearXNG (Docker)│               │
 │                                                          │        └──────┬──────────┘               │
 └──────────────────────────────────────────────────────────┼───────────────┼───────────────────────────┘
                                                            ▼               ▼
                                              Spotify API, Met.no     Google / Bing / Brave / DuckDuckGo
                                              (leaves the network)    (search query leaves the network)
```

## 3. How a question flows, step by step

1. The puck listens continuously for "Hey Jarvis" using a tiny neural network on its own chip. No audio leaves the puck until the wake word fires.
2. After the wake word, the puck streams your speech over Wi-Fi to Home Assistant, which runs in a virtual machine on the Mac.
3. Home Assistant's Assist pipeline sends the audio to Whisper, a speech-to-text model running on the Mac's GPU, and gets back text.
4. The pipeline first tries its built-in intent matcher. "Play Radiohead" and "what's the weather" match fixed sentence patterns and are handled directly, without a language model. This is fast and deterministic.
5. Anything else goes to our conversation agent, a small Python component we write. It sends the conversation to the language model through Ollama.
6. If the model decides it needs current information, it asks for the `web_search` tool. Our agent immediately streams a short filler sentence ("Let me pull some sources on that") so the puck starts speaking while the search runs. The search goes to our MCP server, which queries a self-hosted SearXNG, fetches the top pages, extracts the readable text, and returns excerpts. The model reads them and writes the answer.
7. The answer streams sentence by sentence to a text-to-speech engine (Kokoro or Piper) and plays on the puck.
8. The agent marks the conversation as continuing, so the puck listens for a follow-up for a few seconds without needing the wake word again.

## 4. Subsystems and their tech stacks

| Subsystem | Doc | Stack | Custom code? |
|---|---|---|---|
| Benchmark | 01 | Python harness, Ollama, frontier API as baseline and judge | Yes |
| Local LLM | 02 | Ollama on Apple Silicon, model chosen by benchmark | Config |
| Web search | 03 | SearXNG in Docker + our Python MCP server | Yes |
| Conversation agent | 04 | `assistant_core` package + Home Assistant custom component | Yes |
| Voice pipeline | 05 | Voice PE puck, ESPHome, Wyoming, Whisper via MLX, Kokoro, Piper | Config, maybe a small Wyoming server |
| Home Assistant | 06 | Home Assistant OS in a UTM VM | Config |
| Music | 07 | Spotify integration, Music Assistant, Sonos Era 100 SL | Config |
| Hardware and deployment | 08 | Mac mini, launchd, Docker Desktop, UTM | Config |
| Dev environment | 09 | uv, pyproject, lock file | Yes |

## 5. Open decisions and how they close

Two decisions are deliberately left open until the benchmark runs.

**Which model.** Candidates that fit the 16 GB MacBook used for the prototype: Gemma 4 E4B, Qwen 3.5-4B, Qwen 3.5-9B, gpt-oss-20b, and reduced-precision previews of Gemma 4 26B-A4B and Qwen 3.6-35B-A3B. A frontier model runs through the same harness as the quality ceiling. The benchmark (doc 01) scores them on twenty questions drawn from how you actually use an assistant.

**Which Mac.** The benchmark result picks the tier. If a small full-precision model is good enough, the 24 GB Mac mini M6 suffices. If only the 26B or 35B mixture-of-experts models are good enough, their production versions need about 16 to 20 GB by themselves, and with the speech models and the Home Assistant VM the total is 25 to 27 GB, which means the 32 GB M6. If nothing local is close enough, we say so before spending.

| Tier | Machine | Total with puck and Sonos | Runs comfortably |
|---|---|---|---|
| Budget | Mac mini M6, 24 GB, $1,100 | ~$1,360 | Gemma 4 E4B, Qwen 3.5-9B |
| Mid | Mac mini M6, 32 GB, $1,300 | ~$1,560 | Gemma 4 26B-A4B or Qwen 3.6-35B-A3B at 4-bit with room for everything else |
| High | Mac mini M5 Pro, 48 GB, ~$2,100 | ~$2,360 | Dense 27 to 31B models at speed, higher-precision MoE |

Prices are Apple's list prices for the Mac minis announced August 25, 2026. The M5 and M6 chips include GPU neural accelerators that cut time-to-first-token three to four times versus the M4, which matters most when the model reads a long page of search results.

## 6. Costs

| Build item | Cost |
|---|---|
| Mac mini M6, 24 or 32 GB | $1,100 or $1,300 |
| Home Assistant Voice Preview Edition | $69 |
| Sonos Era 100 SL, or the existing JBL Flip 5 over Bluetooth | $189 or $0 |
| All software and models | $0 |
| Benchmark API usage, per full run | $3 to $8 |
| **Total** | **$1,360 to $1,570** |

Running cost is about $2.50 a month in electricity. Spotify Premium is already paid. Search, weather, and models are free. Maintenance is one to two hours a month for the Home Assistant monthly release, plus occasional dependency and model updates that are each a single command.

## 7. Privacy boundary

| Data | Where it goes |
|---|---|
| Raw audio | Puck to Home Assistant VM to Whisper on the Mac. Never stored, never leaves the LAN. |
| Transcripts and conversation history | Home Assistant's database on the Mac. |
| Model weights and inference | Ollama on the Mac. |
| Search queries | SearXNG on the Mac forwards them to Google, Bing, Brave, and DuckDuckGo with no account and no cookies. The engines see the query text and the apartment's IP address. |
| Spotify commands | Spotify's API, tied to your Premium account, as with any Spotify client. |
| Weather | Latitude and longitude to Met.no. |
| Benchmark only | The twenty benchmark questions and the candidate models' answers go to a frontier API for the baseline run and for judging. They contain no personal data. |

## 8. Phase plan

| Phase | Deliverable | Buys anything? |
|---|---|---|
| 0 | These design docs, frozen as v0 | No |
| 1 | Benchmark harness, web search MCP server, results on the M1 Pro MacBook | No |
| Gate | Model and Mac tier chosen from the results | No |
| 2 | Rest of the proof of concept on the MacBook: Home Assistant, speech, conversation agent, Spotify through the Flip 5 | Optionally the $69 puck |
| 3 | Buy the Mac, puck, and speaker; deploy the same layout on the Mac mini | Yes |

## 9. Concepts for newcomers

**Large language model (LLM).** A neural network that predicts the next token (roughly a word fragment) given everything before it. Run in a loop, it writes answers. Its knowledge is frozen at training time, which is why current facts need a search tool.

**Tokens per second versus time to first token.** Two different speeds. Time to first token is how long the model takes to read the prompt before it starts writing, and it grows with prompt length. Tokens per second is how fast it writes once started. Speech plays at about three to four tokens per second, so any model above that keeps up once it starts; the wait you notice is time to first token, especially after a search stuffs several thousand tokens of page text into the prompt.

**Tool calling.** Instead of answering, the model can emit a structured request such as `web_search(query="current federal funds rate")`. Our code runs the tool, appends the result to the conversation, and calls the model again. The model never touches the network itself.

**Mixture of experts (MoE).** A model whose layers are split into many "experts," with a small router picking a few per token. A 26B-parameter MoE with 4B active parameters must hold all 26B in memory but only computes with 4B per token, so it is nearly as fast as a 4B model while being much smarter. This is why MoE models dominate the candidate list: memory is what a Mac has plenty of, and compute is what it lacks.

**Quantization.** Storing model weights at 4 bits instead of 16 cuts memory by four times with a small quality loss. 3-bit cuts further with a larger loss. The benchmark tests some models at 3-bit only because that is what fits the prototype machine; the production machine would run them at 4-bit.

**Unified memory.** On Apple Silicon the CPU and GPU share one pool of memory. A 32 GB Mac can hold a 20 GB model on the GPU, which a PC graphics card with 16 GB of dedicated memory cannot.

**Wake word.** A tiny always-on model that listens for one phrase and nothing else. It runs on the puck's microcontroller so the microphone stream never leaves the device until you address it.

**Wyoming.** A simple protocol Home Assistant uses to talk to speech services (speech to text, text to speech, wake word) over the network. Any program that speaks Wyoming can plug into the pipeline, which is how we run Whisper and Kokoro on the Mac's GPU outside the Home Assistant VM.

**MCP (Model Context Protocol).** A standard way to expose tools to a language model over HTTP. Our search server speaks MCP so the same tool works from our agent, from Claude Desktop, or from any other MCP client.

**Home Assistant.** An open-source home automation platform. We use it less for automation and more as the plumbing that already knows how to talk to the puck, run a speech pipeline, control Spotify and Sonos, and host our agent.

## 10. Sources

- Apple Mac mini M6 / M5 Pro announcement and pricing, August 25, 2026: [9to5Mac](https://9to5mac.com/2026/08/25/apple-announces-new-mac-mini-heres-everything-new/), [Daring Fireball configuration list](https://daringfireball.net/2026/08/configurations_and_pricing_for_new_mac_minis_and_mac_studios)
- Apple, "Exploring LLMs with MLX and the Neural Accelerators in the M5 GPU": [machinelearning.apple.com](https://machinelearning.apple.com/research/exploring-llms-mlx-m5)
- Home Assistant Voice Preview Edition: [home-assistant.io/voice-pe](https://www.home-assistant.io/voice-pe/)
- Gemma 4 announcement: [blog.google](https://blog.google/innovation-and-ai/technology/developers-tools/gemma-4/)
- Sonos Era 100 SL pricing: [Tom's Guide](https://www.tomsguide.com/audio/speakers/sonos-launches-two-new-speakers-for-2026-what-you-need-to-know-about-sonos-play-and-era-100-sl)
- JBL Flip 5 has no AUX input: [SoundGuys review](https://www.soundguys.com/jbl-flip-5-review-32589/)
