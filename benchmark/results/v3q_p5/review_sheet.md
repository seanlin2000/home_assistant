# Review sheet

Read the answer, decide on gates and scores, then record them in review_sheet.yaml.

## Contents

- [qwen3.8-27b-medium](#review-qwen3-8-27b-medium): [A81](#review-qwen3-8-27b-medium-a81), [A82](#review-qwen3-8-27b-medium-a82), [A86](#review-qwen3-8-27b-medium-a86), [A87](#review-qwen3-8-27b-medium-a87)
- [qwen3.8-27b-low](#review-qwen3-8-27b-low): [A76](#review-qwen3-8-27b-low-a76), [A79](#review-qwen3-8-27b-low-a79), [A87](#review-qwen3-8-27b-low-a87), [B92](#review-qwen3-8-27b-low-b92)
- [qwen3.8-flash-next-medium](#review-qwen3-8-flash-next-medium): [A76](#review-qwen3-8-flash-next-medium-a76), [A78](#review-qwen3-8-flash-next-medium-a78), [A82](#review-qwen3-8-flash-next-medium-a82), [B94](#review-qwen3-8-flash-next-medium-b94)
- [qwen3.8-flash-next-low](#review-qwen3-8-flash-next-low): [A79](#review-qwen3-8-flash-next-low-a79), [A81](#review-qwen3-8-flash-next-low-a81), [B88](#review-qwen3-8-flash-next-low-b88), [B95](#review-qwen3-8-flash-next-low-b95)
- [qwen3.8-flash-next-off](#review-qwen3-8-flash-next-off): [A82](#review-qwen3-8-flash-next-off-a82), [A87](#review-qwen3-8-flash-next-off-a87), [B88](#review-qwen3-8-flash-next-off-b88), [B89](#review-qwen3-8-flash-next-off-b89)

<a id="review-qwen3-8-27b-medium"></a>

## qwen3.8-27b-medium (4 to review)

<a id="review-qwen3-8-27b-medium-a81"></a>

### qwen3.8-27b-medium / A81 (random sample)

**Question:** If I run a language model locally on my computer but use an external web-search API, what information can the search provider see? Explain what stays local, what gets transmitted, and how I can minimize data exposure.

**Searched:** True

**Spoken answer:**

> Good question, and it's a place where a lot of "local AI" setups quietly leak more than people expect. Here's how I'd break it down.

What stays local is the model and everything the model does. The weights, your prompts, the conversation history, the reasoning, and the final answer all get processed on your own hardware. None of that touches the search provider. If the model runs through Ollama, LM Studio, or Open WebUI in local mode, the inference is genuinely on your machine. That part of the privacy promise holds.

What gets transmitted is the search step. When the model decides it needs a fact, the search query it composes goes out to the provider over the internet. And that query is often the sensitive part — models tend to write queries like "best treatment for [your condition]" or "who is the CEO of [your employer]," carrying more context than you'd say out loud. Along with the query, the provider sees your API key (which ties every query to your account), your IP address, and a user agent string.

**Judge:** gates=['searched_on_no_search_question'], quality 4/5, judgment 2/3, spoken 0/2

- Correctly separates what stays local from the query, API key, IP and user agent that go out, and recommends SearXNG, a VPN, scrubbing queries and checking retention, but omits timing and frequency, searching only when needed and caching, and attributes a blog's point to 'Ollama's docs'.
- Ran two searches on a conceptual privacy question that needed none, though it used them sensibly and kept the advice honest about SearXNG's trade-offs.
- A six-paragraph essay with bracketed placeholders, cut by the word cap before any of the minimization advice reached the listener.

<a id="review-qwen3-8-27b-medium-a82"></a>

### qwen3.8-27b-medium / A82 (random sample)

**Question:** Explain the difference between an API, an MCP server, and a software tool. If I wanted to give a local LLM the ability to search the web, retrieve webpages, and summarize them, how would you architect the system?

**Searched:** False

**Spoken answer:**

> Happy to. These three concepts sit at different layers, so thinking of them in terms of "what is the contract, what is the package, and what is the thing that gets called" keeps them straight.

An API is the most general idea. It is a contract for how one piece of software talks to another: which endpoints or functions exist, what you send, what comes back. A web service like a search engine's query API, or even a library's function signatures in code, are all APIs. An API says nothing about who is on the other end or why they are asking.

A software tool is one discrete capability a program can invoke to get a job done: fetch this URL, run this calculation, look up this record. A tool is usually a function with a name, an input description, and an output. Tools are what an API is often made of, but the word "tool" carries the implication that an agent — a human or a program making decisions — is choosing when to use it.

**Judge:** gates=none, quality 4/5, judgment 3/3, spoken 0/2

- Defines API, tool and MCP correctly and lays out search and fetch tools in an MCP server, a tool-calling loop, and model-side summarizing with page truncation, but omits safeguards such as a cap on tool rounds, timeouts, and treating fetched text as untrusted.
- Answered a stable architecture question without searching and made a sensible design call against a separate summarize tool.
- A nine-paragraph essay cut by the word cap after the definitions, so the listener heard none of the architecture they asked for.

<a id="review-qwen3-8-27b-medium-a86"></a>

### qwen3.8-27b-medium / A86 (random sample)

**Question:** I have Philips Hue lights connected to a Hue Bridge. I want multiple people in my apartment to control the lights, including through voice commands. What is the best architecture for this, and what happens if the internet goes down?

**Searched:** True

**Spoken answer:**

> Here's the setup I'd recommend, and then what survives a power-and-network outage.

The core idea is that the Hue Bridge is your source of truth. Your bulbs talk to the bridge over Zigbee, and the bridge sits on your local Wi-Fi network. Everything else — phones, apps, voice assistants — is just a client talking to the bridge.

For multiple people on phones, use the Hue app's built-in sharing. In the app, under Settings, Home access, you invite each person by email. They accept the invite while signed into their own Philips Hue account — that part matters, because if they log into your account they inherit everything and you lose the point of separate access. The bridge is required for this, so having one is the right call. Each person can then control the same rooms and scenes from their own phone, and you can revoke anyone's access later from that same screen.

For voice, the bridge now supports Matter with multi-admin, which means you can link the same bridge to more than one ecosystem at once.

**Judge:** gates=['searched_on_no_search_question'], quality 3/5, judgment 2/3, spoken 0/2

- Correctly makes the bridge the local hub, explains Home access sharing and multi-admin voice, and says bridge automations and the local app survive an outage, but claims simple Alexa control generally keeps working offline and omits physical Hue switches for people without phones.
- Searched twice on a stable architecture question, the second a detour into the Google Assistant phone shutdown, though it hedged the outage behavior by platform.
- A long answer with a bulleted list, cut by the word cap before the internet-outage part the user asked about.

<a id="review-qwen3-8-27b-medium-a87"></a>

### qwen3.8-27b-medium / A87 (random sample)

**Question:** My projector is connected to a JBL Bluetooth speaker. Sometimes the audio becomes choppy when I connect my laptop, and playing video games on the projector causes more eye strain than playing on my monitor. What could cause these problems, and how would you systematically troubleshoot them?

**Searched:** False

**Spoken answer:**

> Good news is both of these are pretty typical problems, and you can work through them methodically.

The choppy audio when you connect your laptop is almost certainly interference. Bluetooth runs on the 2.4 gigahertz band, the same band as most Wi-Fi, so plugging in your laptop may mean its wireless card starts transmitting, or the laptop itself pairs its own Bluetooth audio and steals part of the bandwidth from the speaker. Other common culprits are a USB 3.0 hub or cable near the speaker — USB 3 is a notorious source of 2.4 gigahertz noise — and simply more devices fighting for one low-bandwidth audio stream. To troubleshoot in order: first, confirm the symptom is reproducible by disconnecting the laptop entirely and playing a long audio track, then reconnecting it while still playing. If choppiness returns, disable the laptop's Wi-Fi or switch it to 5 gigahertz if it supports dual band, and turn off Bluetooth on the laptop if you're not using it.

**Judge:** gates=none, quality 4/5, judgment 3/3, spoken 0/2

- Separates the two problems and gives ordered tests covering 2.4 GHz interference, the laptop's own Bluetooth, 5 GHz Wi-Fi, distance, firmware, brightness, ambient light, seating distance and breaks, but misses the DLP rainbow effect, input lag, and focus or keystone, and wrongly speaks of a projector backlight.
- Answered from general troubleshooting knowledge without searching and offered to look up the specific projector model instead of guessing it.
- Two dense paragraphs of roughly 700 words, cut by the word cap before the eye-strain half, which is a wall of text when read aloud.

[Back to top](#review-sheet)

<a id="review-qwen3-8-27b-low"></a>

## qwen3.8-27b-low (4 to review)

<a id="review-qwen3-8-27b-low-a76"></a>

### qwen3.8-27b-low / A76 (random sample)

**Question:** How did the Cold War end? Explain the three most important events that led to the dissolution of the Soviet Union, and distinguish between the causes and the immediate triggers.

**Searched:** False

**Spoken answer:**

> The Cold War ended not with a single dramatic moment but through a cascade of events between 1989 and 1991 that dissolved both the Soviet bloc in Eastern Europe and the Soviet Union itself. To understand it cleanly, it helps to separate the deep causes from the immediate triggers, and then to pick out three events that mattered most.

The long-term causes were structural. The Soviet command economy had been stagnating since the mid-seventies, unable to keep up with Western productivity, while the arms race and the war in Afghanistan were draining resources the system could no longer spare. Underneath all of that ran a web of ethnic and national tensions across the fifteen republics that the central government had managed by force for decades. None of these causes, by itself, made dissolution inevitable, but together they made the system brittle.

The three events I'd point to are these. First, Gorbachev's reforms, launched in 1985 and known as glasnost and perestroika.

**Judge:** gates=none, quality 3/5, judgment 3/3, spoken 0/2

- Causes (stagnant economy, arms race and Afghanistan, nationalism, reforms) and the Berlin Wall and August 1991 coup are correct, but it omits Ukraine's December 1991 referendum and the Belovezha Accords, which the reference names as the final triggers, and folds them into a vague 'in December 1991 the union was formally dissolved'.
- Answering from knowledge without searching was right for a stable history question, and it explicitly separated causes from triggers as asked.
- A six-paragraph essay that the word cap cut before any of the three events was explained, so the listener heard only the introduction and the causes.

<a id="review-qwen3-8-27b-low-a79"></a>

### qwen3.8-27b-low / A79 (random sample)

**Question:** Why are GPUs so effective at AI inference? Explain the differences between GPUs, ASICs, and specialized inference processors. Under what circumstances could a specialized chip outperform an NVIDIA GPU?

**Searched:** True

**Spoken answer:**

> Good question, and it's worth separating the "why" from the "which is better" part, because they're really two different questions.

Why GPUs are so effective at AI inference

Inference, for a large language model, is mostly two things happening repeatedly: giant matrix multiplications, and a lot of memory movement to pull the model's weights and the running conversation state. A GPU is built exactly for that shape of work. It has thousands of small cores that can each do a multiply-accumulate at the same time, so when you have a big matrix times a vector or matrix, all those cores light up in parallel instead of one core doing it step by step. On top of that, modern datacenter GPUs like NVIDIA's Hopper and Blackwell parts carry high-bandwidth memory, fast enough to stream those weights in without stalling the compute, and a mature software stack, CUDA, that most frameworks are written against. So the short version is: parallel compute plus fast memory plus a deep software ecosystem.

**Judge:** gates=['searched_on_no_search_question'], quality 5/5, judgment 1/3, spoken 0/2

- Covers parallel cores, high-bandwidth memory, CUDA, the memory-bandwidth limit on token-by-token generation, TPUs and Trainium as ASICs, Cerebras's on-chip memory, and when a specialized chip wins (fixed high-volume workloads, latency, power cost) or loses (changing models, training, software breadth).
- It ran search_and_read for a stable conceptual question that needed no search, and closed by inviting a follow-up instead of just answering.
- Standalone heading lines such as 'Why GPUs are so effective at AI inference' and a very long essay that the word cap cut after the first section would sound wrong read aloud.

<a id="review-qwen3-8-27b-low-a87"></a>

### qwen3.8-27b-low / A87 (random sample)

**Question:** My projector is connected to a JBL Bluetooth speaker. Sometimes the audio becomes choppy when I connect my laptop, and playing video games on the projector causes more eye strain than playing on my monitor. What could cause these problems, and how would you systematically troubleshoot them?

**Searched:** False

**Spoken answer:**

> Great question, and honestly these are two really common issues that people deal with more than they realize. Let me walk through each one.

**The choppy audio**

The most likely culprit is Bluetooth bandwidth and interference. Here's what's going on: your JBL speaker is already paired with the projector, and when you connect your laptop, the speaker is now juggling two sources. Most Bluetooth speakers, even the better JBLs, handle one audio source at a time cleanly. When a second device connects, the speaker has to negotiate a new connection, and that handshake can cause stuttering, especially if it drops to a lower-quality codec to make room.

On top of that, 2.4 gigahertz is a crowded band. Your laptop's Bluetooth is fighting with your WiFi, any USB 3.0 ports on the laptop (which are notorious for emitting 2.4 gigahertz noise), and possibly the projector's own wireless connection if it uses WiFi. All of that together can make the audio flaky.

**Judge:** gates=none, quality 3/5, judgment 3/3, spoken 0/2

- The audio half is sound (multipoint competition, 2.4 GHz interference, one source at a time, wired link, 5 GHz Wi-Fi), but the eye-strain half omits the DLP rainbow effect, blinking and breaks, and advises sitting closer, which the reference names as a cause of strain.
- No search was needed, and it separated the two problems and gave an ordered sequence of tests for each.
- Markdown bold headings like '**The choppy audio**' and a long essay that the word cap cut before any troubleshooting steps were heard.

<a id="review-qwen3-8-27b-low-b92"></a>

### qwen3.8-27b-low / B92 (random sample)

**Question:** Compare the current high-yield savings account interest rates offered by five major US banks. If I deposit $50,000 for one year, approximately how much interest would I earn at each bank? Identify any minimum balance requirements.

**Searched:** True

**Spoken answer:**

> I found a detailed comparison of the major US banks' savings rates as of early November 2026. One important caveat up front: none of these big banks actually offers what you'd typically call a "high-yield" savings account. Their rates are a fraction of what online banks are paying, which range from about 3.75% to 4.40% APY right now. Here's how the five biggest branch banks stack up:

**JPMorgan Chase** pays 0.01% APY on its standard savings account. Their Premier Savings tier goes up to 0.02%, but only if you maintain a linked Chase Premier Plus or Premier Platinum Checking account, which carries a $25 monthly fee. On $50,000 for a year, that's roughly $5 at the standard rate or $10 at the premium tier.

**Bank of America** pays 0.04% APY on its standard and Advantage Savings accounts. That works out to about $20 on $50,000 for a year.

**Judge:** gates=['missing_required_tool'], quality 3/5, judgment 2/3, spoken 0/2

- Chase, Bank of America, Wells Fargo and U.S. Bank rates match the Arca page and the interest figures ($5, $10, $20, $25, $1,000 on $50,000) are right, but the reply cuts off at '**Tr' before the fifth bank, gives no interest for any actual high-yield account, and lists monthly fees rather than minimum balances.
- It usefully pointed out that the big branch banks do not offer real high-yield rates and flagged that $50,000 falls outside U.S. Bank's 2.00% band, but it never said the rates are variable and change often.
- Markdown bold bank names such as '**JPMorgan Chase**', a long per-bank walkthrough, and a reply that ends mid-word.

[Back to top](#review-sheet)

<a id="review-qwen3-8-flash-next-medium"></a>

## qwen3.8-flash-next-medium (4 to review)

<a id="review-qwen3-8-flash-next-medium-a76"></a>

### qwen3.8-flash-next-medium / A76 (random sample)

**Question:** How did the Cold War end? Explain the three most important events that led to the dissolution of the Soviet Union, and distinguish between the causes and the immediate triggers.

**Searched:** True

**Spoken answer:**

> The short version is that the Cold War ended because the Soviet Union stopped being able to afford it, and then stopped being able to hold itself together. Two things that look like one event are actually separate: the end of the confrontation with the West, which was largely settled by 1989 to 1991, and the death of the Soviet state itself, which happened in December 1991.

Three events stand out.

The first is Gorbachev's reform program beginning in 1985, and especially his foreign policy turn. He took power believing the Brezhnev-era stagnation could be fixed through perestroika, meaning restructuring, and glasnost, meaning openness. Crucially, he also rethought security itself, emphasizing mutual restraint and non-coercion rather than threat, and he abandoned the Brezhnev Doctrine, which had committed the USSR to invading any satellite state whose Communist government was threatened. That single reversal is what made everything after it possible. Alongside Reagan, over four summits between 1985 and 1988 he negotiated the Intermediate-Range Nuclear Forces Treaty, which eliminated an entire class of nuclear weapons for the first time in the conflict's history, and he pulled Soviet troops out of Afghanistan, completed in early 1989.

**Judge:** gates=['searched_on_no_search_question'], quality 4/5, judgment 2/3, spoken 0/2

- Dates and order are right (Berlin Wall November 9, coup August 18 to 22, Belovezha December 8, resignation December 25, dissolution December 26) and causes are cleanly separated from triggers, but it counts Gorbachev's reform program, which it later lists as a cause, as one of the three key events, blurring the distinction it was asked to draw.
- It made three Wikipedia lookups for a stable history question that needed no search, though the lookups were harmless and nothing unverified was added.
- Seven long paragraphs ran past the word cap, so the listener heard only the intro and the first event and never reached the causes-versus-triggers part.

<a id="review-qwen3-8-flash-next-medium-a78"></a>

### qwen3.8-flash-next-medium / A78 (random sample)

**Question:** Why can a country have a strong stock market while its average citizens feel like the economy is getting worse? Give three concrete examples of how this happens.

**Searched:** True

**Spoken answer:**

> It happens because the stock index and the household budget measure two different things. A record index records the price of assets that most people barely own, while a family's sense of the economy is mostly wages, rent, and the price of getting through the day. Right now the gap is visible in the numbers: the S&P 500 is only a few percent below its October record and up roughly seven or eight percent this year, yet the University of Michigan's consumer sentiment index came in at 51.0 in its preliminary November reading, barely above the 44.8 that was the lowest figure in its records going back to the 1950s, set this past May.

First, ownership is extremely concentrated, so the gains barely touch most households. The Federal Reserve's Distributional Financial Accounts, updated in September and covering through the second quarter of this year, show the richest one percent of households holding about 32.9 trillion dollars in corporate equities and mutual fund shares. The entire bottom half of American households held about 374 billion, which means the top one percent holds roughly 88 times as much stock wealth as the bottom fifty percent.

**Judge:** gates=['searched_on_no_search_question'], quality 4/5, judgment 1/3, spoken 0/2

- It gives three distinct concrete mechanisms traceable to the excerpts (top 1 percent holding about 88 times the bottom half's stock, about 58 percent of S&P members in a bear market while a few mega caps carry the index, and rising essential costs with flat home prices), though the third bundles several loosely related figures and uses aggregate spending rather than prices against wages.
- It ran two web searches and pulled in this month's market and sentiment data for a conceptual economics question that needed no search, which made the answer longer and more time-bound than necessary.
- Five dense paragraphs packed with dollar figures and percentages ran past the word cap, so the listener heard only the intro and part of the first example.

<a id="review-qwen3-8-flash-next-medium-a82"></a>

### qwen3.8-flash-next-medium / A82 (random sample)

**Question:** Explain the difference between an API, an MCP server, and a software tool. If I wanted to give a local LLM the ability to search the web, retrieve webpages, and summarize them, how would you architect the system?

**Searched:** True

**Spoken answer:**

> Here's the cleanest way to separate the three, because they're often conflated.

**An API is a contract for a service.** It's a documented way for one program to ask another program to do something or hand over data, with defined endpoints, request shapes, and responses. The OpenWeather API, Stripe, a search provider like Brave or Serper, a REST endpoint on your own machine. The key point: an API knows nothing about language models. It has no idea a model is calling it. It's a general-purpose interface, designed for programmers.

**A software tool, in the agent sense, is a capability wrapped so a model can choose to use it.** It has a name, a natural-language description that a model can read and reason about, and a parameter schema the model must fill in. A tool is usually a thin shell around something else, often an API, sometimes a local function, a shell command, or a database query. What makes it a tool is not the implementation underneath; it's that it's exposed inside the model's context, the model emits a structured call saying "use this tool with these arguments," and the result comes back into the conversation as an observation.

**Judge:** gates=['searched_on_no_search_question'], quality 5/5, judgment 1/3, spoken 0/2

- It clearly separates API, tool (name, description, schema, harness runs it) and MCP server (open protocol exposing tools, resources and prompts), and lays out the model server, agent loop, search and fetch tools with text extraction and size caps, model-side summarization, and safeguards including tool-call caps, timeouts and treating fetched pages as untrusted.
- It ran two web searches, about the MCP spec version and local model picks, for a conceptual architecture question that needed none.
- It is a long multi-layer essay with markdown bold headings that ran far past the word cap, so the listener heard only the first two definitions.

<a id="review-qwen3-8-flash-next-medium-b94"></a>

### qwen3.8-flash-next-medium / B94 (random sample)

**Question:** Plan a five-day trip to Switzerland covering Lucerne, Interlaken, and Zermatt. Prioritize scenic train rides, lakes, and mountain viewpoints. Minimize strenuous hiking and explain which train passes or tickets would be most economical.

**Searched:** True

**Spoken answer:**

> I'll check current fares and pass prices so the ticket advice is actually accurate for 2026.

**Judge:** gates=['no_final_answer', 'too_many_tool_calls'], quality 0/5, judgment 0/3, spoken 0/2

- The final ASSISTANT message is empty, even though the searches had returned Swiss Travel Pass prices (CHF 254 for 3 days, CHF 309 for 4 days), the Half Fare Card price and the Gornergrat November closure.
- Searching was right, but it kept issuing parallel searches until it hit the tool-call limit and then gave no answer even when told to answer with what it had.
- Nothing was spoken.

[Back to top](#review-sheet)

<a id="review-qwen3-8-flash-next-low"></a>

## qwen3.8-flash-next-low (4 to review)

<a id="review-qwen3-8-flash-next-low-a79"></a>

### qwen3.8-flash-next-low / A79 (random sample)

**Question:** Why are GPUs so effective at AI inference? Explain the differences between GPUs, ASICs, and specialized inference processors. Under what circumstances could a specialized chip outperform an NVIDIA GPU?

**Searched:** True

**Spoken answer:**

> The short answer is that GPUs are good at AI inference because inference is mostly a memory-bandwidth problem wrapped in a matrix-multiply problem, and GPUs happen to be strong at both while remaining programmable.

Start with what actually happens when a large model generates a token. Autoregressive decoding is tiny in compute and enormous in data movement: for every token you generate, you have to read the model's weights and the KV cache. A seventy-billion-parameter model at sixteen-bit precision is about one hundred and forty gigabytes of weights, and an H100 has roughly three point three five terabytes a second of HBM bandwidth. Dividing one by the other, as a bound, means a single H100 cannot stream out a single sequence faster than about twenty-four tokens a second. The compute units are mostly waiting. That is why the tensor cores' enormous flop counts barely matter for single-stream generation, and why memory is the wall.

What GPUs do well is turn that weakness into a throughput story.

**Judge:** gates=['searched_on_no_search_question', 'too_many_tool_calls'], quality 3/5, judgment 1/3, spoken 0/2

- It explains the memory-bandwidth wall, CUDA and batching, TPU-style ASICs, Etched and the SRAM designs of Groq and Cerebras well, but breaks off mid-sentence at "when does a specialized chip beat an NVIDIA GPU?" so the third question is barely answered, and its 24-tokens-a-second H100 bound sits unreconciled beside the quoted 700 at batch one.
- It flagged that Sohu's figures are unverified vendor claims, but ran four searches and fetches plus calculator calls on a conceptual question that needed none, and hit the tool-call limit.
- A many-paragraph lecture dense with figures that the word cap cut after two paragraphs, so the listener heard only the bandwidth preamble.

<a id="review-qwen3-8-flash-next-low-a81"></a>

### qwen3.8-flash-next-low / A81 (random sample)

**Question:** If I run a language model locally on my computer but use an external web-search API, what information can the search provider see? Explain what stays local, what gets transmitted, and how I can minimize data exposure.

**Searched:** True

**Spoken answer:**

> Short version: the model staying on your machine protects your documents and your prompts, not your curiosity. The moment a tool call leaves your laptop, the search provider learns what you searched for, in the clear.

Here's the split. What stays local is everything you never send: your prompt, your chat history, your files, the model's weights and reasoning, and anything you keep out of the tool call. What leaves the machine is the query string itself, plus the API key, your public IP address, a timestamp, and request parameters like how many results you want, language, and country. Some providers also receive the URL you're asking them to read, if you use their extract, crawl, or "read this page" endpoints, which tells them not just what you looked for but what you intended to read. And because the query was written by your model on your behalf, it can smuggle out details you never meant to disclose. A model asked "what's the latest on the Henderson matter?"

**Judge:** gates=['searched_on_no_search_question'], quality 4/5, judgment 1/3, spoken 0/2

- It correctly lists what leaves (query, API key, IP, timestamp, parameters, and personal details leaking into model-written queries), what stays local, and sound mitigations including sanitizing queries, caching, a proxy and self-hosted SearXNG, but it never says that the websites the assistant fetches directly also see the user's IP.
- A conceptual architecture question needed no search, yet it ran four searches on Brave, Tavily, Bing and Google policies, padding the answer with provider trivia such as Bing grounding pricing.
- Six dense paragraphs with quoted example queries and a file name, far too long for speech and cut by the word cap mid-example.

<a id="review-qwen3-8-flash-next-low-b88"></a>

### qwen3.8-flash-next-low / B88 (random sample)

**Question:** What are the five most important developments in open-source AI models over the past 30 days? Compare the latest releases from OpenAI's competitors, including DeepSeek, Qwen, Meta, and Mistral.

**Searched:** True

**Spoken answer:**

> I'll dig into what's shipped in the last month or so. Let me search several angles.Let me get specifics on Qwen, Meta, and Mistral.Here's what I found for the window running roughly from mid-October through today, November 12.

The biggest one is Mistral. On October 29 it released the full weights of Mistral Large 4, nicknamed "Le Chonk" — a trillion-and-a-half-billion-parameter mixture-of-experts model with about 49 billion active parameters per token and a 1.6-billion-parameter vision encoder, previewed on October 6 and downloadable from Hugging Face to serve with vLLM or SGLang, with an NVIDIA NIM container too. Mistral claims it now leads all open-weight models on agentic coding: 48 percent on the Artificial Analysis Coding Agent Index, effectively tied with GLM-5.3 but using 47 percent fewer tokens per task, 41 percent on Terminal-Bench 4.0, and top spot on Cognition's FrontierCode 2.

**Judge:** gates=['too_many_tool_calls'], quality 3/5, judgment 3/3, spoken 0/2

- The Mistral Large 4, Kimi K3.1 Pro, Tencent Hy4 and DeepSeek items are dated and sourced from the excerpts with sensible caveats, but it garbles Large 4's 1.05T size as "a trillion-and-a-half-billion", and the answer stops mid-sentence in the fifth item before giving any detail on Meta's closed Muse Ember.
- It searched for a current-news question, kept to the 30-day window, and flagged that Tencent's ranking is its own evaluation and that Hy4's weights are still only promised.
- Two tool-use preambles run together into a dense, number-heavy monologue that the word cap cut in the middle of the first item.

<a id="review-qwen3-8-flash-next-low-b95"></a>

### qwen3.8-flash-next-low / B95 (random sample)

**Question:** Imagine I want to build a private, locally hosted voice assistant that can answer general questions, search the web, control smart-home devices, and have natural conversations. I have a $1,000 hardware budget. Propose an architecture, explain the components, identify the biggest limitations, and prioritize what I should build first.

**Searched:** True

**Spoken answer:**

> Here's the shape I'd give this, and the honest reason for it: on a thousand dollars, the interesting constraint isn't the language model, it's the audio path.

Start with the brain. Skip Raspberry Pi entirely this year — the 16 gigabyte Pi 5 just went to three hundred eighty-five dollars after the DRAM shortage, which is absurd value for a device whose whole job is inference. Buy a used small-form-factor office desktop, something like an OptiPlex or ThinkCentre with a modern six-core chip and thirty-two gigabytes of RAM, around two hundred to two-fifty, and put a used RTX 3060 twelve-gigabyte card in it. Those ran about two-ninety-five on verified eBay sold listings as of this month, with current asking prices nearer four hundred, so budget three-fifty. I'd specifically warn against the used RTX 3090: it's the card everyone names, but sold averages are sitting around one thousand fifty to twelve hundred, so it consumes your entire budget and leaves nothing for microphones.

**Judge:** gates=['fabricated_current_fact', 'too_many_tool_calls'], quality 2/5, judgment 2/3, spoken 0/2

- The core stack (Home Assistant, Ollama, faster-whisper, Piper, Wyoming, SearXNG, Voice Preview Edition) and the in-budget pricing of the RTX 3060, Pi 5 and 3090 follow the sources, but the used office desktop is priced "around two hundred to two-fifty" with no source, and the answer breaks off at "For extra rooms," so it never states the biggest limitations or the build order.
- It correctly ruled out the 3090 on the sources' prices, noted that the trackers disagree on the A770, and flagged that SearXNG snippets are noisy, but it used up the tool-call limit and asserted an unsourced desktop price.
- It is long, dense paragraphs of prices and product names, and the word cap cut it after the first hardware paragraph.

[Back to top](#review-sheet)

<a id="review-qwen3-8-flash-next-off"></a>

## qwen3.8-flash-next-off (4 to review)

<a id="review-qwen3-8-flash-next-off-a82"></a>

### qwen3.8-flash-next-off / A82 (random sample)

**Question:** Explain the difference between an API, an MCP server, and a software tool. If I wanted to give a local LLM the ability to search the web, retrieve webpages, and summarize them, how would you architect the system?

**Searched:** True

**Spoken answer:**

> Let me check the current state of MCP so I get the details right.Here's how I'd separate the three ideas, because they sit at different layers rather than competing with each other.

**An API is a contract for a program to talk to another program.** It defines endpoints, request and response shapes, auth, and error semantics — an HTTP interface you call deterministically, from code, knowing exactly what goes in and out. A search engine's REST endpoint is an API. Nothing about it is AI-specific; APIs predate LLMs by decades.

**A tool is the unit of action a model is allowed to take.** It's a named capability with a description and a typed input schema — "web_search, takes a query string and a result count" — that the model can decide to invoke on its own based on the conversation. The critical part is that the model only *requests* a call; your code executes it and feeds the result back. That's function calling. A tool is often implemented as a thin wrapper around an API, but not always: a tool could be a pure local computation, or a database query, or a shell command.

**Judge:** gates=['searched_on_no_search_question', 'too_many_tool_calls'], quality 3/5, judgment 1/3, spoken 0/2

- The API, tool, and MCP server distinctions are correct and well layered, but the architecture breaks off at "Two. Fetch. Download", so the fetch and clean steps, the agent loop, and safeguards like round caps and treating fetched text as untrusted are never given.
- A conceptual architecture question needed no search, yet the assistant made seven search and fetch calls on MCP specs and vendor guides.
- It uses bold markdown lead-ins ("**An API is a contract...**"), runs very long, and was cut off by the word cap.

<a id="review-qwen3-8-flash-next-off-a87"></a>

### qwen3.8-flash-next-off / A87 (random sample)

**Question:** My projector is connected to a JBL Bluetooth speaker. Sometimes the audio becomes choppy when I connect my laptop, and playing video games on the projector causes more eye strain than playing on my monitor. What could cause these problems, and how would you systematically troubleshoot them?

**Searched:** False

**Spoken answer:**

> I’ll cover both issues separately, since they have different root causes.

**Choppy Bluetooth audio when a laptop connects**

The most likely culprit is that the projector itself is acting as the Bluetooth source, so your laptop isn’t talking directly to the JBL speaker; it’s sending audio to the projector over HDMI or Wi-Fi, and the projector relays it out to the speaker. That double-hop is where stutter usually lives. Projectors often have weak Bluetooth implementations, and they can fall back from a high-quality codec like aptX or LDAC to SBC when signal conditions get crowded, which sounds choppy at exactly the moments interference spikes.

There are three specific things I’d suspect:

First, bandwidth and interference on the projector’s side. If your laptop is also using Wi‑Fi heavily for gaming or streaming while the projector handles Bluetooth on 2.4 GHz, you’re sharing the same crowded band. Many projectors have poor shielding and small antennas.

Second, distance and line of sight.

**Judge:** gates=none, quality 2/5, judgment 3/3, spoken 0/2

- The audio half is solid (the speaker paired to both devices, 2.4 GHz interference, distance, a weak projector radio, one-change-at-a-time tests, a dedicated transmitter), but the eye-strain half breaks off at "This one is almost always about brightness, flick", so half the question goes unanswered.
- It answered from knowledge without searching and separated the two problems with an ordered test plan, as the question asked.
- It uses bold markdown headers and a long multi-paragraph structure, and the word cap cut it off early in the audio section.

<a id="review-qwen3-8-flash-next-off-b88"></a>

### qwen3.8-flash-next-off / B88 (random sample)

**Question:** What are the five most important developments in open-source AI models over the past 30 days? Compare the latest releases from OpenAI's competitors, including DeepSeek, Qwen, Meta, and Mistral.

**Searched:** True

**Spoken answer:**

> I'll look up the most recent open-source model releases before I compare them.Good coverage so far. Let me check two trackers directly for the specific releases from DeepSeek, Qwen, Meta and Mistral in this window.Let me pin down DeepSeek's and Mistral's specific news in this window.One more check on Meta's side, since one source mentions a November Meta release.I have enough on the four named labs; one more check for notable open developments from other labs in this window.Here's what I found for the roughly thirty days from mid-October to today, November 12, 2026. One framing note first: two of the four labs you named are no longer doing this the way they used to. Meta has dropped the Llama name entirely and moved to a "Muse" brand, and Qwen's headline release this month is hosted-only, not open weights. That shift is itself one of the bigger stories of the month.

My five most important developments, in the order I'd rank them:

First, Mistral released the weights for Mistral Large 4 on October 29.

**Judge:** gates=['too_many_tool_calls'], quality 2/5, judgment 2/3, spoken 0/2

- The Mistral Large 4 (October 29) and DeepSeek V4.1-Flash-1017 (October 17) details all trace to the excerpts, and the framing note on Meta's Muse brand and Qwen4-Max being hosted-only is accurate, but the reply breaks off after only two of the five developments, so the promised comparison of Meta and Qwen never arrives.
- Searching was right and it sensibly flagged that Qwen's new release has no open weights, but it spent nine tool calls on detail and ran out of room before covering what was asked.
- The listener heard five run-together narration lines about searching, then dense, spec-heavy paragraphs that the word cap cut off after the first item.

<a id="review-qwen3-8-flash-next-off-b89"></a>

### qwen3.8-flash-next-off / B89 (random sample)

**Question:** What is the current state of the AI inference chip startup industry? Compare Etched, MatX, Positron, Cerebras, SambaNova, and Fractile in terms of funding, valuation, technology, and commercial progress.

**Searched:** True

**Spoken answer:**

> I'll research each of these companies to give you an accurate current picture.Let me check the current Cerebras stock price and a couple of industry-level data points.Here's the picture as of today, November 12, 2026. The short version: inference chip startups have gone from fringe bets to one of the most heavily funded corners of venture capital, and the field has now split into companies actually shipping silicon versus companies still designing it.

The industry backdrop first. PitchBook reported in October that VC-backed inference chip deals hit 5.2 billion dollars in 2025 and were on pace to beat that in 2026, with 4.2 billion raised through late August, while the median valuation of AI chip makers had risen ninefold in two years, from roughly 194 million dollars to about 1.7 billion. Crunchbase counted around 10.7 billion invested in semiconductor startups through early June. The thesis driving all of it is that inference, not training, becomes the dominant compute bill — one estimate PitchBook cites puts inference at roughly 75 percent of AI compute demand by 2030, though McKinsey's figure is closer to 60 percent.

**Judge:** gates=['too_many_tool_calls'], quality 2/5, judgment 2/3, spoken 0/2

- The industry backdrop (PitchBook's $5.2 billion and $4.2 billion, the $194 million to $1.7 billion median) and the Cerebras section (IPO at $185, YCharts' $22.4 billion market cap, $510 million revenue, the OpenAI deal, CS-4) all trace to the excerpts, but the reply breaks off at "**SambaNova** is", so five of the six companies are never compared.
- Searching each company was right and it framed the field as shipping versus still designing, but it spent ten tool calls and so much length on Cerebras that the comparison never happened.
- It uses bold markdown company headers and long dense paragraphs, opens with narrated tool steps, and the word cap cut it off in the backdrop.

[Back to top](#review-sheet)
