# Review sheet

Read the answer, decide on gates and scores, then record them in review_sheet.yaml.

## Contents

- [qwen3.8-27b-medium](#review-qwen3-8-27b-medium): [A81](#review-qwen3-8-27b-medium-a81), [A82](#review-qwen3-8-27b-medium-a82), [A86](#review-qwen3-8-27b-medium-a86), [A87](#review-qwen3-8-27b-medium-a87)
- [qwen3.8-flash-next-medium](#review-qwen3-8-flash-next-medium): [A76](#review-qwen3-8-flash-next-medium-a76), [A78](#review-qwen3-8-flash-next-medium-a78), [A82](#review-qwen3-8-flash-next-medium-a82), [B94](#review-qwen3-8-flash-next-medium-b94)

<a id="review-qwen3-8-27b-medium"></a>

## qwen3.8-27b-medium (4 to review)

<a id="review-qwen3-8-27b-medium-a81"></a>

### qwen3.8-27b-medium / A81 (random sample)

**Question:** If I run a language model locally on my computer but use an external web-search API, what information can the search provider see? Explain what stays local, what gets transmitted, and how I can minimize data exposure.

**Searched:** False

**Spoken answer:**

> The search provider only sees what you send to it, which is essentially your search query, usually a short text string, plus whatever metadata your connection carries, like your IP address, timestamps, and browser or client headers. Your conversation history, prompts, personal documents, and the model's internal reasoning all stay local on your machine.

To minimize exposure, strip queries down to the bare minimum, avoid embedding names or sensitive details in them, and if possible route requests through a VPN or proxy to hide your real IP. You can also use a search API that offers anonymous or no-logging tiers, or front it with a local caching layer so repeated lookups never leave your network at all.

**Judge:** gates=none, quality 4/5, judgment 3/3, spoken 2/2

- It correctly separates the transmitted query, IP and headers from local history and reasoning and gives sound mitigations (stripping queries, VPN, caching, no-logging tiers), but it omits that the API key ties every query to your account and billing identity and that fetched websites also see your IP.
- A conceptual privacy question needed no search, and the advice is concrete without inventing details about the user's setup.
- Two plain-prose paragraphs that lead with what the provider sees and contain no lists or formatting.

<a id="review-qwen3-8-27b-medium-a82"></a>

### qwen3.8-27b-medium / A82 (random sample)

**Question:** Explain the difference between an API, an MCP server, and a software tool. If I wanted to give a local LLM the ability to search the web, retrieve webpages, and summarize them, how would you architect the system?

**Searched:** False

**Spoken answer:**

> An API is a contract: a defined way to call something over the network, like a search engine's HTTP endpoint. A software tool is a program that does work — a scraper, a CLI, a library function. An MCP server is a specific standard, the Model Context Protocol, that wraps tools in a uniform format an LLM can discover and call: it advertises what tools exist, their inputs, and returns structured results, so you don't rewire the model every time you add a capability.

For your system, I'd build a small MCP server exposing three tools. First, a search tool that calls a public search API. Second, a fetch tool that pulls a URL, strips HTML to plain text, and truncates it to fit context. Third, a summarize tool that runs a local model over the retrieved text. Your local LLM — say via an Ollama-compatible endpoint — connects to the MCP server, picks the tool, and chains them: search, fetch, summarize.

**Judge:** gates=none, quality 3/5, judgment 3/3, spoken 1/2

- The API and MCP definitions and the search, fetch-and-truncate design are sound, but it defines a tool as any program ("a scraper, a CLI, a library function") rather than a function the model calls through a name and argument schema, never describes the agent loop that runs the calls, and gives no safeguards such as a tool-round cap, timeouts, or treating fetched text as untrusted.
- A conceptual architecture question needed no search, and the design suggestions are reasonable without inventing user preferences.
- Plain prose without formatting, but long enough that the word cap cut it off before the final sentence.

<a id="review-qwen3-8-27b-medium-a86"></a>

### qwen3.8-27b-medium / A86 (random sample)

**Question:** I have Philips Hue lights connected to a Hue Bridge. I want multiple people in my apartment to control the lights, including through voice commands. What is the best architecture for this, and what happens if the internet goes down?

**Searched:** False

**Spoken answer:**

> The cleanest setup is to make the bridge the single source of truth and give everyone a local path to it.

For each person, install the Hue app and have them sign in with their own Hue account, then join your bridge as a user — the bridge supports up to 25 users, so a few housemates are easy. That gives each of them direct app and room-level control on the local network.

For voice, pair the same bridge with a voice assistant per person — Alexa or Google Home for each, or Apple HomeKit (via the Hue app) if you want a local option that doesn't lean on their cloud.

If the internet drops: the lights stay on your local Zigbee network through the bridge on Wi-Fi, so the Hue app still works offline, and HomeKit plus Alexa/Google local-control commands still turn things on and off. What you lose is anything needing the cloud — remote access, Hue Sync, and creating new automations.

One caveat worth flagging: exact offline behavior for a given assistant depends on firmware and their local-control support, which does shift over time.

**Judge:** gates=none, quality 2/5, judgment 2/3, spoken 1/2

- The bridge-as-hub and local Hue app points are right, but it says "HomeKit plus Alexa/Google local-control commands still turn things on and off" when the internet drops, while the sketch says cloud voice assistants stop taking commands, and it never suggests physical switches.
- Not searching was reasonable and it flags that offline behavior depends on firmware and local-control support, but that caveat sits beside a confident wrong claim about Alexa and Google working offline.
- It leads with the architecture in plain prose, but five paragraphs are long for speech and "Alexa/Google" is a slash that would read awkwardly aloud.

<a id="review-qwen3-8-27b-medium-a87"></a>

### qwen3.8-27b-medium / A87 (random sample)

**Question:** My projector is connected to a JBL Bluetooth speaker. Sometimes the audio becomes choppy when I connect my laptop, and playing video games on the projector causes more eye strain than playing on my monitor. What could cause these problems, and how would you systematically troubleshoot them?

**Searched:** False

**Spoken answer:**

> Two separate problems. The audio: Bluetooth is one shared channel, so pairing a second device like your laptop doubles the traffic and can starve the speaker, causing choppiness. Wi‑Fi on 2.4 gigahertz, distance, or a low Bluetooth version can worsen it. Troubleshoot one variable at a time: re‑pair the speaker, keep it close with a clear line of sight, reduce other 2.4 gigahertz devices, upgrade to a newer Bluetooth dongle, and run a wired test as a control to confirm the projector's output is clean.

The eye strain: projectors generally flicker more and show softer, dimmer images than a monitor, which gaming amplifies. Lower the projector's brightness to match the room, enable a low‑flicker mode, raise its frame rate, and sit at a comfortable distance.

**Judge:** gates=none, quality 3/5, judgment 3/3, spoken 2/2

- It separates the two problems and names the laptop's Bluetooth traffic and 2.4 GHz interference, but its steps never include the obvious test of turning off the laptop's Bluetooth or unpairing it, and the eye-strain part misses focus and keystone, input lag, the DLP rainbow effect, game mode and breaks.
- Troubleshooting from knowledge without searching was right, and it proposes changing one variable at a time with a wired control test.
- Two compact plain-prose paragraphs, one per problem, with no lists or formatting.

[Back to top](#review-sheet)

<a id="review-qwen3-8-flash-next-medium"></a>

## qwen3.8-flash-next-medium (4 to review)

<a id="review-qwen3-8-flash-next-medium-a76"></a>

### qwen3.8-flash-next-medium / A76 (random sample)

**Question:** How did the Cold War end? Explain the three most important events that led to the dissolution of the Soviet Union, and distinguish between the causes and the immediate triggers.

**Searched:** False

**Spoken answer:**

> The Cold War ended not with a battle but with the Soviet system simply ceasing to hold itself together. The underlying causes were long-run: an economy hollowed out by stagnation and the arms race, and Mikhail Gorbachev's perestroika and glasnost, which loosened central control without reviving legitimacy, emboldening nationalist movements in Ukraine, the Baltics and elsewhere. The immediate triggers were three events. First, the Berlin Wall fell in November 1989, ending Soviet domination of Eastern Europe. Second, the failed hardliner coup against Gorbachev in August 1991 destroyed the Union's remaining authority and elevated Boris Yeltsin. Third, on 8 December 1991 Russia, Ukraine and Belarus signed the Belavezha Accords declaring the USSR dissolved; Gorbachev resigned on 25 December.

**Judge:** gates=none, quality 4/5, judgment 3/3, spoken 2/2

- Correctly separates stagnation, the arms race, Gorbachev's reforms and nationalism as causes from the Berlin Wall (Nov 1989), the August 1991 coup and the Belavezha Accords (8 Dec 1991) with correct dates, but omits Afghanistan and the Ukrainian referendum and labels the 1989 Wall fall a trigger rather than an Eastern European cause.
- Answered stable history from knowledge without searching, as expected, and explicitly drew the cause-versus-trigger distinction the question asked for.
- Plain prose that leads with the answer, and its length is justified by the three-part question with no lists or markdown.

<a id="review-qwen3-8-flash-next-medium-a78"></a>

### qwen3.8-flash-next-medium / A78 (random sample)

**Question:** Why can a country have a strong stock market while its average citizens feel like the economy is getting worse? Give three concrete examples of how this happens.

**Searched:** False

**Spoken answer:**

> The gap comes from what the market measures versus what households actually feel. First, index gains are concentrated: a handful of very large firms can lift the whole index while most companies are flat or falling, so the "market" rising says little about Main Street paychecks. Second, stock ownership is skewed — most households hold little or no equity directly, so rising prices build wealth mainly for those already wealthy, while wages and living costs move independently. Third, markets can reward the *effects* of a shaky economy: aggressive rate cuts, layoffs that boost margins, or inflation that pushes people into assets can lift prices while job security, rents, and groceries get worse. A stock index prices expected corporate profits, not the cost of a household's life.

**Judge:** gates=none, quality 4/5, judgment 3/3, spoken 1/2

- Gives distinct mechanisms matching the sketch (index gains concentrated in a few giant firms, skewed stock ownership, and rate cuts or margin-boosting layoffs lifting prices while rents and groceries worsen), though the third example bundles several mechanisms together and none is tied to a concrete instance.
- Answered a stable economics question from knowledge without searching and delivered three mechanisms rather than restating that the market is not the economy.
- Plain, well-paced prose that leads with the answer, but it contains a markdown slip in the asterisks around *effects* that a TTS engine may read aloud.

<a id="review-qwen3-8-flash-next-medium-a82"></a>

### qwen3.8-flash-next-medium / A82 (random sample)

**Question:** Explain the difference between an API, an MCP server, and a software tool. If I wanted to give a local LLM the ability to search the web, retrieve webpages, and summarize them, how would you architect the system?

**Searched:** False

**Spoken answer:**

> Three different layers. An API is a contract a service publishes — endpoints, request and response formats — for any client to call over the network. A software tool is one callable capability your agent has: a name, typed arguments, and a return value the model can decide to invoke. An MCP server is a standardized process, using JSON-RPC, that publishes tools, resources, and prompts to any compliant client, so the same toolset works across apps instead of being hardcoded into one.

For your local LLM: run an agent loop around the model with three tools — search, returning titles, snippets, and URLs from a paid search API; fetch, which downloads a page and strips it to clean text with a token cap; and summarize, either map-reduce over pages or a small dedicated model. Put search and fetch behind an MCP server so they're reusable.

**Judge:** gates=none, quality 4/5, judgment 3/3, spoken 2/2

- Clearly distinguishes an API contract, a callable tool with a name and typed arguments, and an MCP server publishing tools over JSON-RPC, and sketches a sound agent loop with search and capped fetch tools behind MCP, but it gives none of the sketch's safeguards (tool-round cap, timeouts, treating fetched text as untrusted).
- Answered a stable design question from knowledge without searching and gave a concrete architecture rather than generic advice.
- Two plain-prose paragraphs that lead with the three-layer distinction, at a length the two-part question warrants and with no markup.

<a id="review-qwen3-8-flash-next-medium-b94"></a>

### qwen3.8-flash-next-medium / B94 (random sample)

**Question:** Plan a five-day trip to Switzerland covering Lucerne, Interlaken, and Zermatt. Prioritize scenic train rides, lakes, and mountain viewpoints. Minimize strenuous hiking and explain which train passes or tickets would be most economical.

**Searched:** True

**Spoken answer:**

> Five days, no hard hiking: Day 1 Lucerne — Lake Lucerne boat cruise plus Rigi, whose cog railway is fully free on the Swiss Travel Pass. Day 2, the Lucerne–Interlaken Express over the Brünig Pass, covered by the pass. Day 3, funicular to Harder Kulm above Interlaken, then train to Mürren for the Lauterbrunnen valley views; both are low-effort, Mürren's base fare is included. Day 4, Interlaken to Zermatt via Spiez and the Lötschberg Base Tunnel. Day 5, the Gornergrat railway for the Matterhorn panorama at 50 percent off.

Most economical: the six-day second-class Swiss Travel Pass at CHF 399 — it covers every train, bus, boat and city transit on this route, with 25 to 50 percent off mountain railways. The four-day pass is CHF 309 if you can compress travel days.

**Judge:** gates=['fabricated_current_fact'], quality 3/5, judgment 2/3, spoken 1/2

- The route is geographically sensible and the CHF 399 six-day pass, CHF 309 four-day pass, CHF 54 Glacier reservation and October 11 to December 4 closure all match the excerpts, but it never compares the Half Fare Card or point-to-point tickets as the question asks.
- It searched and respected the Glacier Express seasonal closure, but stated pass rules no excerpt gives (Rigi fully free, Gornergrat at 50 percent off, 25 to 50 percent off mountain railways) as settled facts.
- Day-by-day plain prose with no markup, but it ran past the word cap, so the spoken output cut off the Glacier Express advice.

[Back to top](#review-sheet)
