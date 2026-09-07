# Trying out Phase 2 yourself

A hands-on tour of the proof of concept, one component at a time, from the outside in. Every step is a command you run from the project folder, with what you should see. Nothing here changes configuration; it only exercises what is already set up.

Time: about 45 minutes for the whole tour. You can stop after any section.

## Before you start: one heavy workload at a time

The Mac has 16 GB. The Home Assistant VM plus the speech services take about 12 GB with swap, and a benchmark run takes most of the machine too. They must not run together.

```bash
pgrep -fl benchmark-run || echo "no benchmark running"
```

If a benchmark is running, wait for it to finish (or ask me to pause it) before section 4. Sections 1 to 3 are light and safe at any time.

When you are done for the day, go to the last section and shut things down, so the next benchmark pass can start.

## The map

```
   you (browser, curl, or the Companion app)
        │
        ▼
  ┌───────────────────────────── Home Assistant OS VM  192.168.1.156 ─────────────────────────────┐
  │  Assist pipeline "Jarvis":  speech → text  ─▶  conversation.studio_assistant  ─▶  text → speech │
  │                              (Whisper, Mac)      (our component, calls the Mac)   (Piper add-on) │
  └────────────────────────────────────────────┬────────────────────────────────────────────────────┘
                                               │ LAN
  ┌────────────────────────────── the Mac  192.168.1.152 ─────────────────────────────────────────┐
  │  Ollama :11434         gemma4:e4b-it-qat, the language model                                   │
  │  web-search-mcp :8765  the tool server: 3 search tools + 8 calculator tools                    │
  │      └─▶ SearXNG :8080 (Docker, localhost only)  ─▶  Google, Bing, Brave, DuckDuckGo           │
  │  Whisper :10300        speech to text (Wyoming protocol)                                       │
  │  Kokoro  :10210        text to speech (Wyoming protocol), alternative to Piper                 │
  └────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Sections 1 to 3 talk to the Mac-side services directly. Section 4 brings up Home Assistant and goes through the whole chain. Section 5 is voice.

Secrets and addresses live in `.env` (never committed). Load them into your shell once per terminal:

```bash
cd ~/code/home_assistant
set -a; source .env; set +a
```

## 1. The language model on its own (Ollama)

Ollama is the program that runs the model. It always runs, as a background service.

```bash
scripts/services.sh status          # which of the four Mac services are listening
ollama ps                           # which model is loaded in memory right now
```

Talk to the model with no assistant logic at all:

```bash
ollama run gemma4:e4b-it-qat "In one sentence, why does bread rise?"
```

The first call after a while takes 5 to 30 seconds while the model loads; later calls answer in a second or two. `ollama ps` shows how long it stays loaded ("UNTIL"). This is the raw model: no persona, no tools, no word cap. Everything the assistant adds sits on top of this.

Speed numbers if you are curious (prompt processing and generation rates for one model, takes a minute):

```bash
uv run python scripts/benchmark_llm.py --help
```

## 2. The tool server (web search and calculator)

`web-search-mcp` is our own server. The model never touches the internet itself; it asks this server, over a protocol called MCP, to run a named tool with arguments and gets text back.

Check it is up and list its tools:

```bash
curl -s -o /dev/null -w "MCP server: %{http_code}\n" http://127.0.0.1:8765/mcp   # 400 is the healthy answer: it is alive but wants an MCP client, not a browser
```

Call tools by hand with the same client the Home Assistant component uses:

```bash
uv run python - <<'EOF'
import asyncio
from assistant_core.mcp_http import HttpMcpToolBox
from assistant_core.models import ToolCall

async def main():
    async with HttpMcpToolBox("http://127.0.0.1:8765/mcp") as tools:
        for spec in await tools.list_tools():
            print(f"{spec.name:18} {spec.description[:80]}")
        print()
        print(await tools.call(ToolCall(id="1", name="percent", arguments={"kind": "of", "a": 18, "b": 245})))
        print()
        print((await tools.call(ToolCall(id="2", name="search_and_read", arguments={"query": "Home Assistant Voice Preview Edition price"})))[:1500])

asyncio.run(main())
EOF
```

You should see eleven tools, the percentage as `result: 44.10` with a plain-words line the model can read aloud, and numbered excerpts with URLs for the search. Those excerpts are exactly what the model reads before it answers a searched question.

Behind the search tool is SearXNG, a search aggregator running in Docker. You can use it like a search engine in your browser at http://127.0.0.1:8080 . It only listens on the Mac itself.

```bash
scripts/searxng.sh status
```

Safety you can test: the fetch tool refuses anything that is not a public web address. Try `fetch_page` with `{"url": "http://192.168.1.156/"}` in the snippet above and you get "Refused to fetch ... Only public web addresses can be read."

## 3. Speech services on the Mac (Whisper and Kokoro)

These speak the Wyoming protocol, a small line protocol Home Assistant uses for speech services. `scripts/voice_check.py` is a tiny Wyoming client so you can try them without Home Assistant.

Text to speech with Kokoro, then play it:

```bash
uv run python scripts/voice_check.py tts --port 10210 --text "Let me work that out. Eighteen percent of two hundred forty-five dollars is forty-four dollars and ten cents." --out /tmp/kokoro.wav
afplay /tmp/kokoro.wav
```

The command prints time to first audio and whether the server streamed (started sending audio before it finished synthesising). Streaming is what lets the filler sentence play while a search runs.

Speech to text with Whisper, feeding it the file you just made:

```bash
uv run python scripts/voice_check.py stt --port 10300 --wav /tmp/kokoro.wav
```

You should get the sentence back as text, with the time it took. To transcribe your own voice, record a 16 kHz mono WAV with QuickTime or any recorder, export as WAV, and pass it with `--wav`.

If either port is not listening, start the services (they were stopped to free memory for the benchmark):

```bash
scripts/services.sh start
scripts/services.sh logs whisper      # Ctrl-C to stop tailing
```

## 4. The whole chain through Home Assistant

Home Assistant runs as a virtual machine in UTM. Start it and wait for the API (about a minute):

```bash
scripts/haos_vm.sh start
until curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $HA_TOKEN" http://192.168.1.156/api/ | grep -q 200; do sleep 5; done; echo "Home Assistant is up"
```

### 4a. The web interface

Open http://192.168.1.156 in a browser. Sign in with `HA_ADMIN_USER` and `HA_ADMIN_PASSWORD` from `.env`.

Worth a look:

- **Settings → Devices & services.** The Wyoming Protocol card holds Whisper, Kokoro, Piper, and openWakeWord; Studio Assistant is our component; Music Assistant is the music layer for later. (Two duplicate Wyoming entries, "mlx-whisper" and "kokoro", were created by a setup rerun; delete them from the entry's three-dot menu.)
- **Settings → Voice assistants.** The "Jarvis" pipeline: speech to text `mlx-whisper`, conversation agent Studio Assistant, text to speech Piper. Click it to see or change any stage. Switch text to speech to Kokoro here if you want to compare voices.
- **Settings → Add-ons.** Samba (how we copy the component in), Piper, openWakeWord, Music Assistant, ESPHome (for the puck later).
- **Settings → System → Logs.** Where component errors show up. Look for `studio_assistant`.

### 4b. Chat with the assistant in the browser

Open the Overview dashboard, tap the three-dot menu at the top right, and choose **Assist**. Since the 2026.2 redesign there is no separate speech-bubble icon in the header; the entry lives in that menu, in the browser and in the Companion app alike. It opens a chat window on the Jarvis pipeline. Type:

- "Why does bread rise?" (answers from the model, 2 to 5 seconds once warm)
- "What is 18 percent of 245 dollars?" (you will see "Let me work that out." first, then the answer; that first sentence is the filler, spoken while the calculator runs)
- "Search the web for the current price of the Home Assistant Voice Preview Edition." (filler, then an answer built from the search excerpts, 10 to 25 seconds)
- "And what did I ask you first?" (follow-up; the conversation carries history)

The microphone button in the browser only works over HTTPS, which the VM does not have, so typing is the way here. Voice is in section 5.

### 4c. The same thing from the command line

This is the call the pipeline makes internally, and it returns timing you can see:

```bash
ask() { curl -s -m 240 -X POST http://192.168.1.156/api/conversation/process \
  -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
  -d "{\"text\": \"$1\", \"language\": \"en\", \"agent_id\": \"conversation.studio_assistant\"${2:+, \"conversation_id\": \"$2\"}}" \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["response"]["speech"]["plain"]["speech"]); print("conversation_id:", d["conversation_id"])'; }

time ask "If I put 300 dollars a month into an account paying 5 percent a year, how much do I have after 3 years?"
```

Pass the printed `conversation_id` as a second argument to continue the same conversation:

```bash
ask "And after 5 years?" 01M1VPD9JAPX816PT6V0PHNNVZ
```

### 4d. Watch the pieces work while you ask

In a second terminal, `ollama ps` shows the model resident while an answer streams, and `scripts/services.sh logs mcp` shows the tool server's request log. The most useful view is Home Assistant's own: Settings → Voice assistants → Jarvis → three dots → Debug. Open the last run and you see every stage with its timing (speech to text if you spoke, our agent, text to speech) and the exact text that passed between them.

## 5. Voice, with what you have today

There is no puck yet, but you can speak to the pipeline two ways:

- **Home Assistant Companion app** (iPhone or Android) on the same Wi-Fi. Add the server at http://192.168.1.156, sign in, then tap the Assist icon and hold the microphone. It uses the Jarvis pipeline: Whisper on the Mac hears you, the agent answers, Piper speaks. This is the closest thing to the puck experience.
- **Typed text with spoken reply** from the browser Assist window: type a question and Piper's audio plays in the browser.

What to listen for: how soon the filler sentence starts after you stop talking (target under 1.5 s on the final hardware; on this Mac with the model warm it is around 2 to 3 s), and whether the answer sounds like a person talking rather than a document.

## 6. Shutting down when you are done

Stop the memory-heavy parts so the next benchmark pass can run:

```bash
scripts/haos_vm.sh stop
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.studio-assistant.whisper.plist
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.studio-assistant.kokoro.plist
scripts/services.sh status         # ollama and mcp stay up; whisper and kokoro should be gone
```

Ollama and the tool server are small and always stay running.

## If something does not work

| Symptom | Likely cause | Check |
|---|---|---|
| `scripts/services.sh status` shows a port not listening | service stopped or crashed | `scripts/services.sh start`, then `scripts/services.sh logs NAME` |
| Assist answers "Sorry, I couldn't understand that" | pipeline could not reach the agent | Settings → System → Logs for `studio_assistant`; is Ollama up on the Mac? |
| Answer says it could not check the web | the tool server was unreachable from the VM | `curl http://192.168.1.152:8765/mcp` from the Mac; macOS firewall prompt for python was denied? |
| First answer takes 30+ seconds | model was not loaded | normal once per idle period; `ollama ps` |
| Text to speech fails with "not supported" | pipeline language set to `en` instead of `en_US` | Settings → Voice assistants → Jarvis → text to speech language |
| The Mac gets sluggish, apps get killed | VM plus speech services plus something else heavy | section 6, then Activity Monitor → Memory |

More depth on each piece: `design_docs/v1/` (04 the agent, 05 voice, 06 Home Assistant, 03 the tool server), and `design_docs/v1/DEVIATIONS.md` for everything that differed from the original plan.
