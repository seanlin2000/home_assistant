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

> What stays local: the model weights, your full conversation history, and your original prompt. What gets transmitted: only the search query string you build for the API, plus the usual HTTP details — your IP address, request headers, user agent, and timing. The provider never sees your chat or prompt unless you paste them into the query. From the IP they can roughly infer your location, and the queries themselves reveal your interests and, if careless, personal details. To minimize exposure: send the shortest possible query, strip names and specifics from it, use an API key rather than an account, review the provider's data-retention policy, and consider routing requests through a proxy or running your own search frontend like SearXNG.

**Judge:** gates=none, quality 3/5, judgment 3/3, spoken 2/2

- It correctly covers the query string, IP, headers and timing going out, the conversation staying local, and SearXNG and retention policies as mitigations. But it advises using 'an API key rather than an account' as a privacy step, when the key itself ties every query to the account and billing identity, and it never mentions that fetched websites also see the IP.
- This is a stable conceptual question, so answering without a search was right, and it covered all three parts the user asked for.
- One compact paragraph whose spoken signposts ('What stays local', 'What gets transmitted', 'To minimize exposure') map onto the three parts, with no markdown or URLs.

<a id="review-qwen3-8-27b-medium-a82"></a>

### qwen3.8-27b-medium / A82 (random sample)

**Question:** Explain the difference between an API, an MCP server, and a software tool. If I wanted to give a local LLM the ability to search the web, retrieve webpages, and summarize them, how would you architect the system?

**Searched:** False

**Spoken answer:**

> An API is a contract for one service: send a structured request, get a response back, like a search API that takes a query and returns links. A software tool is any program that does a job, a scraper or a summarizer, runnable on its own. An MCP server sits above both. It's a standardized wrapper that exposes tools and data in one uniform format, so any model can discover and call them by name without custom glue code.

To give a local LLM web search, retrieval, and summarization, I'd run the model locally and pair it with a single MCP server exposing a search tool for finding links and a fetch tool that pulls and cleans page text. Summarization the model does itself from that text. The model plans the steps, calls each tool, then writes the summary.

**Judge:** gates=none, quality 3/5, judgment 3/3, spoken 2/2

- The API and MCP explanations and the local model plus one MCP server with search and fetch tools match the reference. But it defines a tool as 'any program that does a job, runnable on its own' instead of a function the model asks to call through a name and argument schema, and it leaves out the agent loop and safeguards like round caps, timeouts and treating fetched text as untrusted.
- This is a stable design question, so answering without a search was right.
- Two short prose paragraphs that answer the definitions first, then the architecture, with no lists or markup.

<a id="review-qwen3-8-27b-medium-a86"></a>

### qwen3.8-27b-medium / A86 (random sample)

**Question:** I have Philips Hue lights connected to a Hue Bridge. I want multiple people in my apartment to control the lights, including through voice commands. What is the best architecture for this, and what happens if the internet goes down?

**Searched:** False

**Spoken answer:**

> For a small apartment, keep it simple and local. Put your Hue Bridge on the 2.4 gig WiFi network; it's the Zigbee hub for all your bulbs. Then give each person their own account in the Hue app, added through the bridge, so everyone can control the lights on their phone without sharing login info.

For voice, the cleanest setup is a smart speaker that talks to the bridge locally — an Amazon Echo with the Hue skill, or a HomePod using Siri — rather than a cloud-only option like Google Assistant.

That local design is what saves you when the internet drops. The Hue app, the bridge, and local voice control all keep working because they only use your home network. What stops is anything cloud-dependent: Google Assistant commands, web access to your account, firmware updates, and the Hue Sync or entertainment app. So you lose convenience, not the lights themselves.

**Judge:** gates=none, quality 2/5, judgment 2/3, spoken 2/2

- It correctly calls the bridge the local Zigbee hub and says the Hue app keeps working offline, but it presents an Echo with the Hue skill as local voice control that survives an outage when Alexa stops without internet, says to put the bridge on 2.4 GHz WiFi, and never mentions physical switches.
- Not searching was right for a stable architecture question, but steering the user toward Alexa as the outage-proof voice option is a misleading recommendation on the question's central concern.
- Three short plain paragraphs that open with the recommendation, with no lists or markup.

<a id="review-qwen3-8-27b-medium-a87"></a>

### qwen3.8-27b-medium / A87 (random sample)

**Question:** My projector is connected to a JBL Bluetooth speaker. Sometimes the audio becomes choppy when I connect my laptop, and playing video games on the projector causes more eye strain than playing on my monitor. What could cause these problems, and how would you systematically troubleshoot them?

**Searched:** False

**Spoken answer:**

> Both are pretty classic, so let's sort them out.

The choppy audio is almost certainly a Bluetooth bandwidth or interference issue. A speaker sharing one 2.4‑GHz radio with your laptop—especially a wireless mouse, keyboard, or Wi‑Fi adapter on the same band—gets starved. Pairing the laptop to the same speaker can split the link into two half‑duplex streams and drop packets. To work through it: first, put the laptop on wired if you can, or a 5 GHz band, and switch the mouse and keyboard to wired or a USB dongle. Move the speaker's Bluetooth antenna away from the laptop and other 2.4 GHz gear, and check nothing's in between. Try updating the speaker and projector firmware, and re‑pair from scratch. If you only ever play one source at a time, keep the laptop unpaired and accept the tradeoff. If it still stutters, the problem's likely the source's Bluetooth stack, and a direct 3.

**Judge:** gates=none, quality 3/5, judgment 2/3, spoken 0/2

- The audio half covers the laptop competing for the speaker, 2.4 GHz interference, moving to 5 GHz, firmware and a wired fallback. The eye-strain half skips field of view, seating distance, input lag and the DLP rainbow effect, its advice to turn off flicker reduction is dubious, and the word cap cut the spoken output before any eye-strain content was heard.
- Not searching was right and it separated the two problems and gave an order of tests, but it called the audio cause 'almost certainly' bandwidth or interference without saying that was a guess.
- A long, multi-paragraph answer that ran past the word cap and stopped mid-sentence at 'a direct 3.', so the listener never heard the second problem.

[Back to top](#review-sheet)

<a id="review-qwen3-8-flash-next-medium"></a>

## qwen3.8-flash-next-medium (4 to review)

<a id="review-qwen3-8-flash-next-medium-a76"></a>

### qwen3.8-flash-next-medium / A76 (random sample)

**Question:** How did the Cold War end? Explain the three most important events that led to the dissolution of the Soviet Union, and distinguish between the causes and the immediate triggers.

**Searched:** False

**Spoken answer:**

> The long causes were economic stagnation, the arms race drain, Chernobyl's legitimacy damage, and nationalist movements in the republics. The events that did the actual work were three. First, Gorbachev's perestroika and glasnost from 1985 loosened censorship and central control without fixing the economy, opening space for dissent. Second, the Berlin Wall falling in November 1989, and Moscow's refusal to shoot protesters, ended the Soviet grip on Eastern Europe overnight. Third, the hardliner coup against Gorbachev in August 1991 collapsed in days but destroyed the last remaining authority of the central government, accelerating declarations of independence. Gorbachev's resignation on December 25, 1991 was the formal end.

**Judge:** gates=none, quality 3/5, judgment 2/3, spoken 2/2

- The causes and the Berlin Wall and August 1991 coup are right with correct dates, but it counts perestroika and glasnost as a triggering event when the sketch treats reform as a cause, and it leaves out the Ukrainian referendum and the Belovezha Accords.
- Answering from knowledge without a search was right, but the cause-versus-trigger split the question asked for is blurred by listing Gorbachev's reforms among the 'events that did the actual work'.
- One plain-prose paragraph that leads with the causes and walks through first, second and third events, a fitting length for a three-part history question.

<a id="review-qwen3-8-flash-next-medium-a78"></a>

### qwen3.8-flash-next-medium / A78 (random sample)

**Question:** Why can a country have a strong stock market while its average citizens feel like the economy is getting worse? Give three concrete examples of how this happens.

**Searched:** True

**Spoken answer:**

> It happens because stock prices measure the value of a few companies, while daily life measures wages, prices, and debt — and the gains are concentrated. Three concrete examples:

One, ownership is lopsided. Fed data show the wealthiest ten percent of US households hold about eighty-seven percent of equities, so years of double-digit market gains land mostly in a small slice of accounts, while the bottom half holds roughly three percent of household wealth.

Two, wages lag assets. Real average hourly earnings were up only about one and a half percent in April 2026, even as the S&P 500 posted a fourth straight year of double-digit gains, so paychecks don't buy what the index suggests.

Three, the same boom raises the cost of living. Mortgage rates climbed above seven percent, housing stayed unaffordable, and household debt hit eighteen point eight trillion dollars with delinquencies at their highest since 2017. Economists call this a K-shaped economy.

**Judge:** gates=['searched_on_no_search_question'], quality 4/5, judgment 1/3, spoken 1/2

- It gives three sourced mechanisms (the top ten percent owning about 87 percent of equities, real wages up about 1.4 percent while the S&P 500 climbed, and housing and debt costs), but the first two overlap as asset-versus-wage stories, and it rounds 1.4 to 'one and a half'.
- It ran a web search for a conceptual economics question that should have been answered from knowledge.
- It leads with the answer in plain prose, but at four paragraphs and about 150 words it runs well past the 110-word limit it was given.

<a id="review-qwen3-8-flash-next-medium-a82"></a>

### qwen3.8-flash-next-medium / A82 (random sample)

**Question:** Explain the difference between an API, an MCP server, and a software tool. If I wanted to give a local LLM the ability to search the web, retrieve webpages, and summarize them, how would you architect the system?

**Searched:** False

**Spoken answer:**

> An API is a contract for calling a service: fixed endpoints, request and response formats, designed for any client. A software tool is a self-contained capability — a function, script, or program that does one job, like a search or a text splitter. An MCP server is a specific kind of program that wraps tools, data, and prompts behind the Model Context Protocol, an open standard, so any compliant client can discover what it offers and call it without bespoke glue code.

For your system: run a local model with a tool-calling loop, and an MCP server exposing three tools — search returning ranked URLs and snippets, fetch converting a page to clean text, and a summarize step you can run on the model itself. Add token budgets, cached page text, and rate limits, and keep search keys server-side so the model never sees them.

**Judge:** gates=none, quality 4/5, judgment 3/3, spoken 2/2

- The API and MCP definitions and the local model, tool loop, search, fetch and summarize architecture match the sketch, but 'tool' is described generically instead of as a schema-described function the model asks to call, and it gives no safeguard for treating fetched text as untrusted or capping tool rounds.
- Answering a conceptual architecture question without searching was right, and it adds practical points such as keeping search keys server-side.
- Two plain-prose paragraphs, definitions first and then the design, with no lists or markup.

<a id="review-qwen3-8-flash-next-medium-b94"></a>

### qwen3.8-flash-next-medium / B94 (random sample)

**Question:** Plan a five-day trip to Switzerland covering Lucerne, Interlaken, and Zermatt. Prioritize scenic train rides, lakes, and mountain viewpoints. Minimize strenuous hiking and explain which train passes or tickets would be most economical.

**Searched:** True

**Spoken answer:**

> Five days, low effort, rail-first. Day one, Lucerne: a scheduled Lake Lucerne cruise and the Rigi cog railway or Stanserhorn cable car, both fully included in the pass, with viewpoints reached by boat and lift rather than feet. Day two, the Lucerne–Interlaken Express over the Brünig pass, covered in full with no reservation. Day three, a Lake Brienz boat to Giessbach and the Harder Kulm funicular, about half price with the pass, a far cheaper alternative to Jungfraujoch. Day four, Interlaken to Zermatt via Spiez and Visp. Day five, the Gornergrat cog railway for the Matterhorn view, half price.

Ticket: the Swiss Travel Pass, second class. Six consecutive days is CHF 399; a four-day pass is CHF 309 if you skip pass travel on arrival and departure days. It covers all trains, boats, city transport and those free mountain excursions.

**Judge:** gates=none, quality 3/5, judgment 2/3, spoken 1/2

- The Lucerne, Interlaken, Zermatt order, the Rigi and Lake Lucerne cruise covered by the pass, the CHF 399 and 309 pass prices and the Glacier Express maintenance closure all match the sources, but it never compares the Half Fare Card or point-to-point tickets, a key element of the sketch.
- It avoided strenuous hiking and respected the Glacier Express closure, but it recommended the Swiss Travel Pass without weighing cheaper alternatives, and the Oberalp aside does not fit the itinerary.
- A day-by-day plan in prose that ran past the word cap, which cut the closing seasonal caveat.

[Back to top](#review-sheet)
