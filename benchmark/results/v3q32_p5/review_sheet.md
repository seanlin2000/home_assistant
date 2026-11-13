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

> The model weights, your full conversation history, any local files, and everything your model computes internally all stay on your machine. What leaves is much narrower: the search query string itself, plus HTTP metadata like your IP address, user-agent, and the API key that authenticates you to the provider. So if you phrase a query with someone's name, a medical condition, or project details, that text reaches the search company's servers and may be logged.

To minimize exposure, strip or replace personally identifying details before sending a query, review the provider's data-retention policy, route requests through a VPN or local proxy, and scope your API key so it grants only search access, not a full account. If you can, use a search API with a clear no-logging pledge, or run a local search index like a self-hosted crawler so the query never leaves your network at all.

**Judge:** gates=none, quality 4/5, judgment 3/3, spoken 2/2

- It correctly separates what stays local from the query text, IP, user agent and API key that are sent, and gives sound mitigations like stripping personal details, VPN and retention review, but omits that fetched websites also see the IP and misses searching only when needed or a metasearch proxy like SearXNG.
- Stable architecture question answered without a needless search, with a concrete example of how a query can leak personal details.
- Two plain-prose paragraphs with no lists or markup, a reasonable length for a three-part question.

<a id="review-qwen3-8-27b-medium-a82"></a>

### qwen3.8-27b-medium / A82 (random sample)

**Question:** Explain the difference between an API, an MCP server, and a software tool. If I wanted to give a local LLM the ability to search the web, retrieve webpages, and summarize them, how would you architect the system?

**Searched:** False

**Spoken answer:**

> An API is a general interface—just a set of functions other software can call, like a weather service or a search engine. A tool is any small program or function you wire into an LLM to do one job, like fetching a page or calling that API. An MCP server is a standard package of tools plus instructions, spoken in a common protocol, so the LLM framework can discover and use them without custom code.

To give a local model web access, I'd build two or three small MCP tools: one that calls a search API, one that fetches and strips a page down to text, and one that hands the text to the model for summarization. Your local app, something like Ollama behind a framework, talks to the MCP server, which talks to the web. Each step stays simple and swappable.

**Judge:** gates=none, quality 3/5, judgment 3/3, spoken 2/2

- The API, tool and MCP definitions are broadly right and it proposes search and fetch-and-strip tools behind an MCP server, but it never describes the agent loop that runs tool calls and returns results, treats summarization as a separate tool, and gives no safeguards such as round caps or treating fetched text as untrusted.
- Stable software-architecture question answered without searching, which was the right call.
- Two compact plain-prose paragraphs with no lists or markup.

<a id="review-qwen3-8-27b-medium-a86"></a>

### qwen3.8-27b-medium / A86 (random sample)

**Question:** I have Philips Hue lights connected to a Hue Bridge. I want multiple people in my apartment to control the lights, including through voice commands. What is the best architecture for this, and what happens if the internet goes down?

**Searched:** False

**Spoken answer:**

> The simplest good setup: keep the Hue Bridge as the single hub. Everyone installs the Hue app and gets added as a user on the same bridge, which handles local Wi-Fi control, scenes, schedules and firmware. For voice, each person links their own assistant account — Alexa or Google Home skill, or Apple HomeKit — to the same bridge, so each person keeps their own voice profile.

On outages: the bridge and app keep working fully locally as long as the router is up, since Hue talks over your LAN. Local automations, scenes and HomeKit still run too. The one thing that breaks is cloud voice processing — Alexa and Google can't understand commands offline. An Apple HomePod with Siri Shortcuts is the exception, since it handles many Hue commands on-device. So if offline voice matters, HomeKit is your most resilient option.

**Judge:** gates=none, quality 4/5, judgment 3/3, spoken 2/2

- It correctly makes the bridge the hub with shared app users and linked voice assistants, and says local control and HomeKit survive an outage while Alexa and Google stop, but it omits physical Hue switches and overstates HomePod Siri handling Hue commands on-device.
- Stable smart-home architecture answered without searching, which was the right call.
- Leads with the recommended setup and covers outages in two plain-prose paragraphs without lists.

<a id="review-qwen3-8-27b-medium-a87"></a>

### qwen3.8-27b-medium / A87 (random sample)

**Question:** My projector is connected to a JBL Bluetooth speaker. Sometimes the audio becomes choppy when I connect my laptop, and playing video games on the projector causes more eye strain than playing on my monitor. What could cause these problems, and how would you systematically troubleshoot them?

**Searched:** False

**Spoken answer:**

> Most often, the choppy audio is interference in the 2.4 gigahertz band, where Bluetooth and your laptop's Wi-Fi share the same crowded space, so adding the laptop clogs the channel. To test it, cut the laptop's Wi-Fi and Bluetooth, or simply wire the speaker to the projector with a 3.5 or optical cable. If the stutter stops, that is your culprit.

The eye strain makes sense, too. Projectors flicker at a lower refresh rate, run with less brightness and contrast, and throw a bigger, softer image that bounces off a bright room, so your eyes work harder.

Work it systematically, one variable at a time. Fix the audio first with a wired connection to rule out the interference. Then, for the display, dim the room, raise the brightness and contrast, sit closer, and cut the blue light. That isolates each problem instead of chasing both at once.

**Judge:** gates=none, quality 3/5, judgment 3/3, spoken 2/2

- It names 2.4 GHz interference and a wired-cable test and separates the two problems in order, but misses the laptop competing for the speaker's connection, the DLP rainbow effect, focus and input lag, and advises sitting closer when sitting too close is a likely cause of strain.
- Stable troubleshooting answered without searching, and it isolates one variable at a time as the question asked.
- Plain prose in three short paragraphs that leads with the likely audio cause and has no lists or markup.

[Back to top](#review-sheet)

<a id="review-qwen3-8-flash-next-medium"></a>

## qwen3.8-flash-next-medium (4 to review)

<a id="review-qwen3-8-flash-next-medium-a76"></a>

### qwen3.8-flash-next-medium / A76 (random sample)

**Question:** How did the Cold War end? Explain the three most important events that led to the dissolution of the Soviet Union, and distinguish between the causes and the immediate triggers.

**Searched:** False

**Spoken answer:**

> The Cold War ended not with a battle but with the Soviet system exhausting itself. The deep causes were economic: decades of stagnation, a bloated military and arms race that starved consumer production, and the loss of cheap Eastern European markets. Gorbachev's reforms, glasnost and perestroika, were meant to save the system but instead loosened censorship and empowered nationalist movements. The immediate triggers were sharper: the fall of the Berlin Wall in November 1989, which ended Soviet control of Eastern Europe; the failed hardliner coup in August 1991, which destroyed central authority; and Gorbachev's resignation on December 25, 1991.

**Judge:** gates=none, quality 3/5, judgment 3/3, spoken 2/2

- It separates causes from triggers and dates the Berlin Wall and the August 1991 coup correctly, but its third trigger is Gorbachev's resignation (an outcome) instead of the Ukrainian referendum and Belovezha Accords, and it leaves out Afghanistan and the republics' nationalism as causes.
- Answering stable history from knowledge without searching was the right call, and nothing in the question needed an assumption or pushback.
- Four sentences of plain prose that open with the answer, a reasonable length for a three-part explanation.

<a id="review-qwen3-8-flash-next-medium-a78"></a>

### qwen3.8-flash-next-medium / A78 (random sample)

**Question:** Why can a country have a strong stock market while its average citizens feel like the economy is getting worse? Give three concrete examples of how this happens.

**Searched:** True

**Spoken answer:**

> The core reason is that "the market" is a weighted average, not a household budget. Three concrete ways they diverge:

One, narrow leadership. The ten largest US stocks now make up roughly 40 percent of the S&P 500, up from about 23 percent in 2020, and the Magnificent Seven account for over a third of the index. If a handful of AI-related mega-caps surge, the index posts record gains while the median company's stock does nothing, and most households own few or no direct equities.

Two, profits without wages. Mega-cap leaders earn pricing power in a higher-for-longer rate regime, so margins and buybacks rise while real pay for ordinary workers lags the headline index.

Three, costs that indexes ignore. Rents, insurance, groceries and healthcare are not in the S&P 500. A country can set records in equities while the same households feel poorer because their biggest expenses keep climbing.

**Judge:** gates=['searched_on_no_search_question'], quality 4/5, judgment 1/3, spoken 1/2

- It gives three distinct mechanisms (mega-cap concentration, with the roughly 40 percent top-ten share taken from the Fidelity excerpt, profits and buybacks outpacing wages, and rent and grocery costs the index ignores), though the 'pricing power in a higher-for-longer rate regime' link to wages is muddled.
- It ran a web search for a conceptual economics question that needed none, which the harness flagged as searched_on_no_search_question.
- It opens with the core reason, but the 'One, Two, Three' paragraphs run past 120 words and read like a spoken list.

<a id="review-qwen3-8-flash-next-medium-a82"></a>

### qwen3.8-flash-next-medium / A82 (random sample)

**Question:** Explain the difference between an API, an MCP server, and a software tool. If I wanted to give a local LLM the ability to search the web, retrieve webpages, and summarize them, how would you architect the system?

**Searched:** False

**Spoken answer:**

> An API is a contract: a defined way for software to expose capabilities over a network, typically endpoints that take structured requests and return structured responses. A software tool is any program or function an agent can invoke to do a concrete job, like fetching a URL or running a search query. An MCP server is a specific standard for packaging those tools so an AI client can discover and call them uniformly, handling connection, listing available tools, and routing calls, rather than each agent writing bespoke integrations.

For a local LLM with web abilities, I'd build it in layers. First, a search API client, a tool wrapping something like Serper or Bing, returning ranked titles and URLs. Second, a retrieval tool that fetches a URL and strips HTML to readable text, keeping output bounded to fit context. Third, a summarizer, either the local model itself running over the retrieved text, or a small local model for speed.

I'd wrap the search and fetch tools in a single MCP server, so the local model, through a runner like Ollama's tool support or a LiteLLM proxy, can see them, decide when to search, pick which pages to read, and then summarize.

**Judge:** gates=none, quality 4/5, judgment 3/3, spoken 1/2

- The API, tool and MCP definitions are accurate, and the layered design (search tool, bounded fetch tool, local model summarizing, all behind one MCP server, with a cache and length caps) matches the reference, but it never treats fetched text as untrusted and gives no cap on tool rounds or timeouts.
- Answering a stable design question from knowledge without searching was right.
- Plain prose with no markdown, but it runs long enough that the harness word cap cut the spoken output.

<a id="review-qwen3-8-flash-next-medium-b94"></a>

### qwen3.8-flash-next-medium / B94 (random sample)

**Question:** Plan a five-day trip to Switzerland covering Lucerne, Interlaken, and Zermatt. Prioritize scenic train rides, lakes, and mountain viewpoints. Minimize strenuous hiking and explain which train passes or tickets would be most economical.

**Searched:** True

**Spoken answer:**

> Five days, three bases, no serious hiking.

Day one in Lucerne: a paddle steamer across Lake Lucerne to Vitznau, then the cogwheel railway up Mount Rigi — the one major summit fully free with the pass — and back by cable car through Weggis. Day two, the Lucerne–Interlaken Express over the Brünig Pass, free with no reservation, then an afternoon cruise on Lake Brienz or Thun. Day three, the Harder Kulm funicular above Interlaken, or the train-and-cable-car chain to Mürren, both viewpoint-only. Day four, travel to Zermatt and ride the Gornergrat railway, half price, for the Matterhorn panorama. Day five, home.

Cheapest: the 6-day consecutive Swiss Travel Pass, second class, 399 Swiss francs in 2026, covering every train, boat and funicular leg except Gornergrat's half-fare supplement.

**Judge:** gates=['fabricated_current_fact'], quality 2/5, judgment 2/3, spoken 1/2

- The route (Lucerne with Rigi, Interlaken lakes, Zermatt with Gornergrat) is sensible and the 399 and 309 franc pass prices are sourced, but it never compares the Half Fare Card, point-to-point tickets or the 4-day Flex pass, and it claims the 6-day pass covers 'every train, boat and funicular leg except Gornergrat', which contradicts the sources saying most mountain transport is only half price.
- Searching current pass prices and coverage was right, but it recommended a 6-day pass for a five-day trip without weighing cheaper alternatives the sources listed.
- It opens with a one-line frame, but the day-by-day itinerary plus pass explanation ran long enough for the harness word cap to cut it.

[Back to top](#review-sheet)
