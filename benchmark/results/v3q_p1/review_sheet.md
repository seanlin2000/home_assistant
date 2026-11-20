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

**Searched:** False

**Spoken answer:**

> Good question, and the short answer is: less than you might think, but the one thing that leaves your machine is more revealing than it looks.

What stays local. The model weights, all inference, your full conversation history, the files the model reads from disk, and whatever it generates or writes back. None of that touches the search provider. They have no window into your prompt, your system instructions, or the answers your model produces.

What gets transmitted. The search API only ever receives the query string, plus the normal plumbing of any API call: your IP address, timestamps, a user-agent or client identifier, TLS-level details like which domain you're connecting to, and your API key, which ties every request to your account. Depending on the API, you can optionally send extra fields like context, instructions, or domain filters, and anything you put in those goes to them too. That's it, but there are two subtleties worth knowing.

The first subtlety is the important one: the query is not your words, it's the model's paraphrase of your intent.

**Judge:** gates=none, quality 4/5, judgment 3/3, spoken 1/2

- It correctly lists the query, IP, API key, timing and user agent, flags that the model's query can leak personal details, and gives sound mitigations, but it omits that fetched websites also see the IP and overstates SearXNG as zero external exposure when it still forwards queries to upstream engines.
- Answering a privacy-architecture question from knowledge without searching was right, and it pointed the user to the provider's retention policy rather than guessing it.
- Plain prose organized under spoken signposts, but it opens with filler and runs six paragraphs, so the word cap cut it before the mitigation advice.

<a id="review-qwen3-8-27b-medium-a82"></a>

### qwen3.8-27b-medium / A82 (random sample)

**Question:** Explain the difference between an API, an MCP server, and a software tool. If I wanted to give a local LLM the ability to search the web, retrieve webpages, and summarize them, how would you architect the system?

**Searched:** False

**Spoken answer:**

> Good question, and the three terms live at different layers, which is why people conflate them.

An API is a communication contract between two programs. It says what calls exist, what shape the requests and responses take, and how you authenticate. A web search service's API, for instance, is something like: send a query, get back a JSON list of results. It's aimed at code writing developers, and it knows nothing about LLMs.

A software tool is just a piece of software that does a job — a script, a command-line program, an app. In the LLM world the word takes on a more specific meaning: a tool is a callable function that a model can invoke, usually described by a name, a description, and a JSON schema of its inputs. When a model "uses a tool," it's really just emitting a structured request that some surrounding program executes and hands the result back.

An MCP server is the newest layer: a standard protocol — Model Context Protocol, created by Anthropic and now widely adopted — for packaging capabilities so LLM applications can discover and use them.

**Judge:** gates=none, quality 3/5, judgment 3/3, spoken 1/2

- The API, tool and MCP definitions are accurate and it rightly makes summarization the model's job, but the reply breaks off mid-sentence at 'gives better' before describing the page-fetch tool, the agent loop or any safeguards such as round caps and treating fetched text as untrusted.
- Answering a software-architecture question from knowledge without searching was the right call.
- Plain prose with no formatting, but it is long enough that the word cap cut it during the definitions and the written reply itself ends mid-sentence.

<a id="review-qwen3-8-27b-medium-a86"></a>

### qwen3.8-27b-medium / A86 (random sample)

**Question:** I have Philips Hue lights connected to a Hue Bridge. I want multiple people in my apartment to control the lights, including through voice commands. What is the best architecture for this, and what happens if the internet goes down?

**Searched:** True

**Spoken answer:**

> The setup you want is really three layers: the lights themselves, shared app access, and the voice assistant, and they each work a bit differently.

First, the lights and Bridge. Your Hue Bridge should stay plugged into your router with an Ethernet cable — it runs a local Zigbee network, so it does not need the internet to talk to the bulbs. That's the foundation for everything else and the reason your lights survive an outage.

Second, app access for everyone in the apartment. The best architecture is: one owner account owns the Bridge, and every other person gets their own Hue account and is invited into the home through the "Home access" or Device Sharing section of the Hue app. Each person signs in with their own email, accepts the invite, and then can control rooms, scenes, and switches from their own phone. The owner can give people lighting-only permission or full admin rights, and can remove someone's access at any time without touching the Bridge. This is better than everyone sharing one login, because you can revoke a roommate individually and see who has access.

**Judge:** gates=['searched_on_no_search_question'], quality 4/5, judgment 2/3, spoken 1/2

- It correctly lays out the Bridge as the local Zigbee hub, per-person Hue accounts invited through Home access, a linked voice assistant and physical tap switches, and says the app, automations and switches survive an outage while Alexa and Google voice stops, but it never mentions that Apple Home with a home hub or a local controller like Home Assistant keeps voice working offline.
- The architecture and outage reasoning are sound, but it ran two web searches for a question it could answer from stable knowledge.
- Plain prose with spoken signposts, but at six long paragraphs the word cap cut it before the internet-outage part the user specifically asked about.

<a id="review-qwen3-8-27b-medium-a87"></a>

### qwen3.8-27b-medium / A87 (random sample)

**Question:** My projector is connected to a JBL Bluetooth speaker. Sometimes the audio becomes choppy when I connect my laptop, and playing video games on the projector causes more eye strain than playing on my monitor. What could cause these problems, and how would you systematically troubleshoot them?

**Searched:** False

**Spoken answer:**

> Both of those sound like classic "two devices fighting over one thing" problems, so let me walk through each one.

The choppiness when you connect your laptop is almost certainly Bluetooth interference or bandwidth contention. Bluetooth audio and the 2.4 gigahertz radio band that Wi-Fi and other Bluetooth devices use are crowded neighbors, and a laptop adds another potential 2.4 gigahertz source on top. There are a few likely culprits. First, the speaker may be bonded to two devices at once — if both the projector and the laptop are paired, the speaker can be alternating or struggling between them. Second, your laptop's Bluetooth adapter and its Wi-Fi card typically share the same 2.4 gigahertz radio, so heavy wireless traffic on the laptop can starve the audio. Third, simple distance or obstacles matter: a laptop sitting between the projector and the speaker, or with its own Bluetooth dongle pointed the wrong way, can degrade the link.

To troubleshoot this systematically, I'd isolate variables one at a time.

**Judge:** gates=none, quality 4/5, judgment 3/3, spoken 1/2

- It separates the two problems and gives an ordered one-variable-at-a-time plan covering multipoint pairing, 2.4 GHz contention, 5 GHz Wi-Fi, firmware and a wired test, plus room brightness, focus, keystone, DLP flicker and blinking, though it misses the larger field of view and input lag or game mode.
- Answering a troubleshooting question from knowledge without searching was right, and it gave an order of tests instead of guessing a single cause.
- Plain prose, but five long paragraphs meant the word cap cut it at the start of the audio troubleshooting steps, so the eye-strain half was never heard.

[Back to top](#review-sheet)

<a id="review-qwen3-8-27b-low"></a>

## qwen3.8-27b-low (4 to review)

<a id="review-qwen3-8-27b-low-a76"></a>

### qwen3.8-27b-low / A76 (random sample)

**Question:** How did the Cold War end? Explain the three most important events that led to the dissolution of the Soviet Union, and distinguish between the causes and the immediate triggers.

**Searched:** False

**Spoken answer:**

> The Cold War ended not with a single dramatic event but through a sequence of collapses that made the Soviet system unable to hold itself together. By the time the Soviet Union was formally dissolved on December twenty-sixth, nineteen ninety-one, the process had been in motion for over a year.

Here are the three most important events, and I'll separate the deeper causes from the immediate triggers as you asked.

**The first is the fall of the Berlin Wall in November of nineteen eighty-nine**, and more broadly the wave of revolutions across Eastern Europe that swept out every communist government from Poland to Romania in that single year. This is best understood as a consequence of Gorbachev's reforms. He had introduced glasnost, which meant openness, and perestroika, which meant restructuring the economy, and crucially he had abandoned the Brezhnev Doctrine, which had justified Soviet military intervention whenever a satellite state drifted away. Without the threat of tanks, the opposition movements in Eastern Europe moved faster than anyone expected.

**Judge:** gates=none, quality 3/5, judgment 3/3, spoken 0/2

- The Berlin Wall, August 1991 coup and December 8 Belovezha Accords are correct and causes are separated from triggers as the sketch asks, but the closing summary says 'the coup failed in eighty-one' (a wrong date) and the text contains a stray Chinese word ('延缓ed').
- Answering from stable historical knowledge without searching was right, and it explicitly labels the economy, nationalism and reforms as causes and the coup and accords as triggers.
- A multi-paragraph wall of text with bold markdown headings that the word cap cut off partway through the first event, so the listener never heard the coup, the accords or the causes-versus-triggers distinction.

<a id="review-qwen3-8-27b-low-a79"></a>

### qwen3.8-27b-low / A79 (random sample)

**Question:** Why are GPUs so effective at AI inference? Explain the differences between GPUs, ASICs, and specialized inference processors. Under what circumstances could a specialized chip outperform an NVIDIA GPU?

**Searched:** False

**Spoken answer:**

> GPUs are effective at AI inference for a few interconnected reasons. First, inference is dominated by matrix multiplication and vector operations, and GPUs have thousands of small cores that can execute those operations in parallel. Second, modern GPU architectures pair those cores with very high-bandwidth memory, often HBM, so the compute units aren't starved waiting for data. Third, the arithmetic intensity of a forward pass — the ratio of floating-point operations to bytes moved — happens to sit right in the sweet spot where a GPU's compute-to-memory ratio shines. Finally, there's the software ecosystem: CUDA, TensorRT, cuDNN, and the model serving stacks built on top of them mean that even a less-than-perfectly-matched workload can still get decent utilization.

Now for the differences between the three categories.

A GPU is a general-purpose parallel processor. It was designed for graphics, repurposed for machine learning, and has become the default because it handles a wide range of workloads — training, inference, different model families, different precision levels — without redesigning the silicon.

**Judge:** gates=none, quality 4/5, judgment 3/3, spoken 0/2

- It covers parallel cores, HBM, CUDA, the TPU as an ASIC, Groq as an inference processor, and fixed-workload, latency and edge cases where specialized chips win, but it says a forward pass's arithmetic intensity sits in the GPU's sweet spot instead of noting token generation is memory-bandwidth bound.
- Explaining stable hardware architecture without searching was right, and it gives the balancing case where GPUs win when workloads change.
- Eleven paragraphs of dense technical prose is a wall of text for a voice reply, and the word cap cut it off before the ASIC comparison.

<a id="review-qwen3-8-27b-low-a87"></a>

### qwen3.8-27b-low / A87 (random sample)

**Question:** My projector is connected to a JBL Bluetooth speaker. Sometimes the audio becomes choppy when I connect my laptop, and playing video games on the projector causes more eye strain than playing on my monitor. What could cause these problems, and how would you systematically troubleshoot them?

**Searched:** False

**Spoken answer:**

> These are two separate problems, so let's take them one at a time.

**The choppy audio**

The most likely cause is that your JBL speaker is handling two Bluetooth sources at once. Most JBL speakers support what they call multipoint, which lets them pair with two devices simultaneously, but the audio quality drops when both are active. The speaker is essentially splitting its limited Bluetooth bandwidth between the projector and your laptop, and that's where the choppiness creeps in.

There are a few other contributors to rule out. Bluetooth shares the 2.4 gigahertz band with Wi-Fi and USB 3.0 devices, so if your laptop's Wi-Fi adapter or a nearby USB hub is active, it can introduce interference. Your laptop's power management settings may also be putting the Bluetooth adapter to sleep briefly, which causes micro-dropouts. And firmware bugs on any of the three devices — speaker, projector, or laptop — can all manifest as audio stuttering.

Here's how I'd work through it systematically.

**Judge:** gates=none, quality 4/5, judgment 3/3, spoken 0/2

- It separates the two problems, names multipoint competition, 2.4 GHz interference and firmware with an ordered test sequence ending in a wired control, and covers motion blur, softness, seating distance, ambient light and DLP color-wheel effects, though it skips input lag and game mode and the message breaks off mid-sentence on the 20-20-20 rule.
- Generic troubleshooting needed no search, and it isolates variables one at a time as a systematic approach should.
- Bold markdown headings and about a dozen long paragraphs make a formatted wall of text, which the word cap cut off before the troubleshooting steps.

<a id="review-qwen3-8-27b-low-b92"></a>

### qwen3.8-27b-low / B92 (random sample)

**Question:** Compare the current high-yield savings account interest rates offered by five major US banks. If I deposit $50,000 for one year, approximately how much interest would I earn at each bank? Identify any minimum balance requirements.

**Searched:** True

**Spoken answer:**

> Let me confirm a couple of the rates and the minimum-balance details before I summarize.Let me verify the interest math.Here's what I found across five well-known U.S. banks, with rates confirmed on or near this week. I'm using the standard account each offers, and assuming you leave the full $50,000 untouched for a year at a constant rate. Because these are variable rates, the real figure will depend on how the banks move their APYs over the next twelve months, so treat these as estimates.

Ally's Online Savings pays 3.20% APY, which on $50,000 comes to about $1,600 for the year, and it has no minimum balance requirement. Capital One 360 Performance Savings is right on top of Ally at 3.20%, also roughly $1,600 a year, with a $0 minimum to open. Marcus by Goldman Sachs' Online Savings runs a bit higher at 3.

**Judge:** gates=['too_many_tool_calls'], quality 3/5, judgment 3/3, spoken 1/2

- The Ally, Capital One, Marcus, SoFi base and EverBank rates and the zero minimums trace to the fininfoblog and Banksparency excerpts and the yearly interest figures are correct, but it says SoFi's 4.40 percent boost for up to six months would earn 'about $2,200 in that window', which is a full year's interest at that rate, about double the six-month figure.
- It searched for current rates, said they are variable and that the figures are estimates assuming a constant rate, flagged EverBank's new-account-only fine print, and noted the big branch banks pay almost nothing.
- Plain prose with no lists, but the tool-call preambles ('Let me verify the interest math.') ran into the spoken text, and the long five-bank paragraph was cut by the word cap at Marcus.

[Back to top](#review-sheet)

<a id="review-qwen3-8-flash-next-medium"></a>

## qwen3.8-flash-next-medium (4 to review)

<a id="review-qwen3-8-flash-next-medium-a76"></a>

### qwen3.8-flash-next-medium / A76 (random sample)

**Question:** How did the Cold War end? Explain the three most important events that led to the dissolution of the Soviet Union, and distinguish between the causes and the immediate triggers.

**Searched:** True

**Spoken answer:**

> The Cold War and the Soviet Union ended at different moments, and it helps to separate them. The Cold War is usually dated as ending in 1989, when Bush and Gorbachev met off Malta on December second and third and declared it over; the Soviet Union itself did not formally cease to exist until December twenty-sixth, 1991. The arms race had already been winding down before that, especially after Gorbachev and Reagan signed the INF Treaty on December eighth, 1987, which eliminated an entire class of intermediate-range nuclear missiles.

Now, the distinction you asked about. Causes are the deep conditions that made the system unable to keep going; triggers are the specific events that made collapse sudden and irreversible once those conditions were already in place.

The causes were mostly structural. First, long economic stagnation. Soviet growth had been sliding since the 1970s, and the country had become dependent on oil export revenue; when oil prices fell in the mid-1980s, that cushion disappeared, and the command economy could not correct itself.

**Judge:** gates=['searched_on_no_search_question', 'too_many_tool_calls'], quality 5/5, judgment 1/3, spoken 0/2

- The answer names stagnation, the arms burden, nationalism and glasnost/perestroika as causes and gives the 1989 revolutions, the August 19-21 1991 coup and the December 8 1991 Belovezha Accords (with the December 1 Ukrainian referendum and December 26 dissolution) as the events, all with correct dates and order.
- A stable history question needed no search, yet the assistant made seven Wikipedia and web_search calls before answering.
- The reply is a multi-paragraph essay that the word cap cut off before the listener reached any of the three events.

<a id="review-qwen3-8-flash-next-medium-a78"></a>

### qwen3.8-flash-next-medium / A78 (random sample)

**Question:** Why can a country have a strong stock market while its average citizens feel like the economy is getting worse? Give three concrete examples of how this happens.

**Searched:** True

**Spoken answer:**

> The short answer is that a stock index measures the value of companies, not the finances of households, and right now those two things have genuinely come apart. The United States is a good illustration of that, and there are three concrete mechanisms behind it.

First, almost all the stock market is owned by a small slice of households. According to the Federal Reserve's Distributional Financial Accounts for the second quarter of this year, the richest ten percent of American households held about 88 percent of corporate equities and mutual fund shares, and the top one percent alone held roughly 51 percent of them. The bottom half of households held about one percent. The Lazard Asset Management team pointed out a related fact: around 42 percent of Americans have no stock market investment at all, so a record high in the S&P 500 simply does not show up on their balance sheets. Worse, the middle has been shrinking. Households between the 50th and 90th percentiles by net worth held 17.

**Judge:** gates=['searched_on_no_search_question', 'too_many_tool_calls'], quality 5/5, judgment 1/3, spoken 0/2

- It gives three distinct mechanisms (top ten percent holding about 88 percent of equities, gains concentrated in a few AI mega-caps, and buybacks with real wages lagging inflation), each with figures traceable to the Fed, Lazard, J.P. Morgan and Neuberger excerpts.
- A conceptual economics question needed no search, but the assistant ran four search_and_read calls plus two pointless calculator calls such as 50.9 / 1.
- Four dense, statistic-heavy paragraphs were cut by the word cap mid-number, leaving the listener with only the first mechanism.

<a id="review-qwen3-8-flash-next-medium-a82"></a>

### qwen3.8-flash-next-medium / A82 (random sample)

**Question:** Explain the difference between an API, an MCP server, and a software tool. If I wanted to give a local LLM the ability to search the web, retrieve webpages, and summarize them, how would you architect the system?

**Searched:** True

**Spoken answer:**

> Think of the three as different levels of the same stack.

An API is a contract between pieces of software. It says: send a request shaped like this and you'll get a response shaped like that. A REST endpoint, a GraphQL schema, a library function signature, JSON-RPC — all APIs. The audience is a deterministic program that already knows exactly which call to make and what to do with the answer.

A tool is an API aimed at a model instead of at a programmer. It's a callable thing plus three extra ingredients: a natural-language description of when to use it, a typed parameter schema the model can fill in, and the assumption that the model itself decides whether to invoke it and what to do with the result. So every tool contains an API, but the tool wrapping is what turns a capability into something an agent can choose. The other half of a tool is the runtime that actually intercepts the model's request, executes it, and feeds the output back into the context window.

**Judge:** gates=['searched_on_no_search_question'], quality 5/5, judgment 1/3, spoken 0/2

- It distinguishes API, tool (description plus schema plus runtime) and MCP server (tools, resources, prompts over JSON-RPC), then lays out a local model, an agent loop with a call budget, search and capped fetch tools, caching and treating fetched text as untrusted.
- A conceptual architecture question needed no search, yet it searched for the MCP spec version and worked the July 2026 release details into the answer.
- Ten paragraphs of architecture prose ran far past the word cap, which cut it off after the tool definition.

<a id="review-qwen3-8-flash-next-medium-b94"></a>

### qwen3.8-flash-next-medium / B94 (random sample)

**Question:** Plan a five-day trip to Switzerland covering Lucerne, Interlaken, and Zermatt. Prioritize scenic train rides, lakes, and mountain viewpoints. Minimize strenuous hiking and explain which train passes or tickets would be most economical.

**Searched:** True

**Spoken answer:**

> I'll check current prices and coverage for the Swiss passes before laying out the plan.Good detail so far. Let me nail down the Interlaken-side options and the cost comparison between the pass and the half-fare alternative.

**Judge:** gates=['no_final_answer', 'too_many_tool_calls'], quality 0/5, judgment 0/3, spoken 0/2

- The final ASSISTANT message is empty: after gathering pass prices, the Gornergrat 2-14 November closure and the Pilatus and Stanserhorn seasonal closures, it never produced the itinerary.
- Searching was right for current prices and closures, but it failed the central task by never delivering a plan or a pass recommendation.
- No final answer was spoken; the user heard only mid-search narration such as 'Good detail so far.'

[Back to top](#review-sheet)

<a id="review-qwen3-8-flash-next-low"></a>

## qwen3.8-flash-next-low (4 to review)

<a id="review-qwen3-8-flash-next-low-a79"></a>

### qwen3.8-flash-next-low / A79 (random sample)

**Question:** Why are GPUs so effective at AI inference? Explain the differences between GPUs, ASICs, and specialized inference processors. Under what circumstances could a specialized chip outperform an NVIDIA GPU?

**Searched:** True

**Spoken answer:**

> I'll ground the "current landscape" part with a quick search, then explain the architecture side.The short answer is that inference is mostly a very specific kind of math — huge matrix multiplications and attention — and GPUs happen to be exceptionally good at exactly that kind of math, while also being programmable enough to handle whatever the model researchers invent next.

Break it into two halves, because modern large language model inference has two phases with completely different bottlenecks. The first is prefill, where all your prompt tokens are processed at once. That is compute-bound: lots of arithmetic per byte of weight read, which is where a GPU's thousands of parallel cores and its dedicated matrix-multiply units, the tensor cores, earn their keep. The second is decode, where the model generates one token at a time, and every step has to stream essentially the entire set of weights through the chip to do a handful of arithmetic on them. That phase is memory-bandwidth-bound, not compute-bound, and its arithmetic intensity is close to one operation per byte.

**Judge:** gates=['searched_on_no_search_question'], quality 5/5, judgment 1/3, spoken 0/2

- It explains parallel cores, tensor cores, HBM and memory-bound decode, credits CUDA and the software stack, contrasts TPU systolic arrays with Groq SRAM, Cerebras wafer-scale and Etched/Taalas hard-wiring, and lists when specialized chips win or lose, matching the reference sketch, with every figure it cites present in the excerpts.
- A conceptual hardware question needed no search, but the assistant opened with "I'll ground the current landscape part with a quick search" and made two search_and_read calls.
- The six-paragraph reply was cut by the word cap after the prefill/decode paragraph, so the listener never heard the GPU-versus-ASIC comparison or when a specialized chip wins.

<a id="review-qwen3-8-flash-next-low-a81"></a>

### qwen3.8-flash-next-low / A81 (random sample)

**Question:** If I run a language model locally on my computer but use an external web-search API, what information can the search provider see? Explain what stays local, what gets transmitted, and how I can minimize data exposure.

**Searched:** True

**Spoken answer:**

> Short version: the model stays private, but the query is a leak, and the leak is bigger than most people expect because the search query is derived from your prompt.

Here is the anatomy. What definitely stays on your machine: the model weights, your full conversation, everything you paste into the context window, and any local files the model reads. What leaves your machine, for every single search call, is the query string your agent constructs plus account metadata. That query string matters more than it looks, because a local model tends to write a search query that is a compressed version of what you were just talking about. If you were discussing a specific patient, a client's name, an internal project codename, a file path, a law firm matter, or a stock position, the model will often put those words directly into the query. Alongside it the provider sees your API key, your source IP address, timestamps, request counts, and user agent. So the provider learns when you searched, from where, how often, and roughly what you were working on, even if it never sees your actual prompt.

**Judge:** gates=['searched_on_no_search_question', 'too_many_tool_calls'], quality 5/5, judgment 1/3, spoken 0/2

- It covers everything in the reference sketch: the query string carrying conversation details, API key, IP, timing and user agent; fetched sites seeing the IP; the conversation and weights staying local; and query hygiene, SearXNG, VPN, caching and reading retention terms, with the Brave 90-day and Tavily details matching the fetched policies.
- A conceptual privacy question needed no search, yet the assistant made seven tool calls across searches and page fetches.
- The five long paragraphs were cut by the word cap after the first section, so the listener never heard how to minimize exposure.

<a id="review-qwen3-8-flash-next-low-b88"></a>

### qwen3.8-flash-next-low / B88 (random sample)

**Question:** What are the five most important developments in open-source AI models over the past 30 days? Compare the latest releases from OpenAI's competitors, including DeepSeek, Qwen, Meta, and Mistral.

**Searched:** True

**Spoken answer:**

> I'll search for what's happened in open-source AI over the last month, then look at each lab's latest release.Here's what I found, with the caveat that "open source" has become slippery: nearly everything released in the last month is open *weights* — downloadable, often commercially usable, but rarely OSI-open-source in the strict sense. I'll flag which ones actually shipped weights, because two of the biggest announcements didn't.

The single biggest event for self-hosters was Mistral putting its trillion-parameter model on Hugging Face on October 29. Mistral Large 4, nicknamed Le Chonk, is a mixture-of-experts model with about 1.05 trillion total parameters, 52 billion active per token, a 1.6 billion-parameter vision encoder and a one-million-token context window, plus a speculative-decoding draft head Mistral measured at up to 1.9 times higher throughput. It's licensed under what Mistral calls the Ecosystem Open-Weight License, an MIT derivative with one real catch: if you want to resell the model as a hosted service, you need a separate commercial deal from Mistral.

**Judge:** gates=['too_many_tool_calls'], quality 4/5, judgment 3/3, spoken 0/2

- All five developments (Mistral Large 4 weights on October 29, Tencent Hy4 on November 4, DeepSeek V4.1-Flash-1017 and the Huawei V5 reports, Qwen4-Max-Preview on November 11, Meta Muse Ember on November 9) are dated within the window and traceable to the excerpts, but the final message breaks off mid-sentence at "it runs only on" and skips Kimi K3.1 Pro's weight release that the results mention.
- It searched for a current-news question and was careful to say that Hy4 weights had not been confirmed, that Qwen4-Max and Muse Ember are not open, and that the V5 parameter count is rumor.
- A very long multi-paragraph reply with markdown emphasis (*weights*) was cut by the word cap after the first development, so the listener heard almost none of the comparison.

<a id="review-qwen3-8-flash-next-low-b95"></a>

### qwen3.8-flash-next-low / B95 (random sample)

**Question:** Imagine I want to build a private, locally hosted voice assistant that can answer general questions, search the web, control smart-home devices, and have natural conversations. I have a $1,000 hardware budget. Propose an architecture, explain the components, identify the biggest limitations, and prioritize what I should build first.

**Searched:** True

**Spoken answer:**

> Here's the architecture I'd build, and the honest reason it works in 2026: every piece of a local voice assistant already exists as a mature open-source component, so the project is plumbing, not research. The interesting decisions are about what you *don't* build yet, and about the fact that "$1,000 of hardware" currently buys noticeably less than it used to.

**The pipeline

**Judge:** gates=['too_many_tool_calls'], quality 1/5, judgment 0/3, spoken 0/2

- The final message is one framing paragraph that breaks off at "**The pipeline", so it names no components, no hardware within the $1,000 budget, no limitations and no build order, beyond the remark that $1,000 buys less than it used to.
- Searching for current hardware prices was right, but the assistant spent all ten tool calls searching and delivered no architecture, which fails the central point.
- The fragment contains markdown (*don't* and **The pipeline) and stops mid-heading, which would sound broken aloud.

[Back to top](#review-sheet)

<a id="review-qwen3-8-flash-next-off"></a>

## qwen3.8-flash-next-off (4 to review)

<a id="review-qwen3-8-flash-next-off-a82"></a>

### qwen3.8-flash-next-off / A82 (random sample)

**Question:** Explain the difference between an API, an MCP server, and a software tool. If I wanted to give a local LLM the ability to search the web, retrieve webpages, and summarize them, how would you architect the system?

**Searched:** True

**Spoken answer:**

> I'll ground this in current MCP details before explaining the architecture.Let me confirm the current MCP primitives and a couple of practical local-model details.Good. Let me check what local models currently handle tool calling reliably and what retrieval options exist.Let me get concrete pricing numbers so my recommendation is grounded.Here's how I'd separate the three ideas, then the build.

**An API is a contract for software.** It says: send me this request in this format, at this address, and I'll return this response. It's designed for programs to call programs. A REST endpoint that returns JSON search results is an API. Nothing about it knows or cares that a language model is involved.

**A tool is a unit of action offered to the model.** It's a name, a plain-English description of what it does, and a schema saying which arguments it takes. The critical part is the description, because that's what the model reads to decide whether to use it and when. A tool usually wraps an API, but not always — a tool could wrap a local function that reads a file, or one that runs a shell command, with no network call at all.

**Judge:** gates=['searched_on_no_search_question', 'too_many_tool_calls'], quality 2/5, judgment 1/3, spoken 0/2

- The API, tool and MCP definitions are accurate and well distinguished, but the architecture breaks off mid-sentence in layer one of four ('far more often than on bad prose'), so the agent loop, search and fetch tools, summarizing, and safeguards are never described.
- It made eight tool calls, including search API pricing and model rankings nobody asked for, on a conceptual design question that needed no search, which tripped the tool-call limit.
- Four filler preambles run together, bold markdown leads each paragraph, and the long answer was cut by the word cap before the architecture was spoken.

<a id="review-qwen3-8-flash-next-off-a87"></a>

### qwen3.8-flash-next-off / A87 (random sample)

**Question:** My projector is connected to a JBL Bluetooth speaker. Sometimes the audio becomes choppy when I connect my laptop, and playing video games on the projector causes more eye strain than playing on my monitor. What could cause these problems, and how would you systematically troubleshoot them?

**Searched:** True

**Spoken answer:**

> I'll ground this in what people actually run into with these setups before answering. Let me check a couple of sources.Let me read a couple of the more detailed ones.Let me check what people say specifically about projectors causing more strain than monitors, since that's counterintuitive.One more check on the specific symptom of choppy audio appearing when a laptop joins the setup.Here's what I think is going on, and then a way to test it that doesn't involve changing five things at once.

**Why the audio goes choppy when the laptop joins**

Bluetooth audio lives in the 2.4 gigahertz band, which is exactly where most Wi-Fi and a lot of cheap USB 3.0 gear also lives. When you connect a laptop, three new things enter that environment at once: the laptop's own Wi-Fi traffic, its Bluetooth radio competing for the same airwaves, and often a USB 3.0 hub or external drive spewing broadband radio noise. The most common culprits, in rough order of likelihood:

Radio interference is the big one.

**Judge:** gates=['searched_on_no_search_question', 'too_many_tool_calls'], quality 2/5, judgment 1/3, spoken 0/2

- The audio section names 2.4 GHz interference, codec and distance but misses the laptop also connecting to the JBL speaker, and pads with laptop-side Windows power and microphone-profile fixes that don't fit a projector-to-speaker link; the eye-strain section breaks off after its first cause ('far more total light hitting'), and the promised one-change-at-a-time test order never arrives.
- It made seven tool calls on a general troubleshooting question that needed no search, tripping the tool-call limit, and transplanted Windows-headset advice from a fetched page without checking that it fit this setup.
- Four filler preambles run together, bold markdown headings, and a long wall of text that the word cap cut after one sentence of the first cause.

<a id="review-qwen3-8-flash-next-off-b88"></a>

### qwen3.8-flash-next-off / B88 (random sample)

**Question:** What are the five most important developments in open-source AI models over the past 30 days? Compare the latest releases from OpenAI's competitors, including DeepSeek, Qwen, Meta, and Mistral.

**Searched:** True

**Spoken answer:**

> I'll look into recent open-source model releases across those labs.Good grounding on October. Now let me pin down what happened in November specifically.Now let me check Meta's side and what specifically landed in November.Let me get a fuller picture of the November releases and DeepSeek's status.Here's what I found for the window of roughly October 13 through November 12, 2026. One framing note first: strictly speaking, almost none of these are "open source" — they're open *weights* with conditions. DeepSeek is the main lab still using plain MIT; the others all attach strings. That distinction turned out to be one of the real stories of the month.

**Five developments I'd rank as most important**

One: Mistral shipped weights at trillion-parameter scale, with a catch. Mistral Large 4, nicknamed "Le Chonk," went onto Hugging Face on October 29 — about 1 trillion total parameters, 49 billion active per token (52 billion counting embedding and output layers), natively multimodal, 1 million token context, trained from scratch on roughly 3,800 NVIDIA Grace Blackwell GPUs in European datacenters.

**Judge:** gates=['too_many_tool_calls'], quality 2/5, judgment 2/3, spoken 0/2

- The Mistral Large 4 (October 29) and Muse Spark Open (October 15) details all trace to the retrieved excerpts, but the message breaks off mid-sentence in the third item ('a 552'), so it never reaches developments four and five or Qwen (whose Qwen4-Max-Preview of November 11 was retrieved).
- Searching was right for news from the past 30 days and the open-weights-versus-open-source framing is a good call, but eight tool calls hit the limit and the answer over-detailed two items at the cost of the rest.
- Four filler preambles run together, a bold markdown heading, and dense spec-heavy paragraphs that the word cap cut during the first of five items.

<a id="review-qwen3-8-flash-next-off-b89"></a>

### qwen3.8-flash-next-off / B89 (random sample)

**Question:** What is the current state of the AI inference chip startup industry? Compare Etched, MatX, Positron, Cerebras, SambaNova, and Fractile in terms of funding, valuation, technology, and commercial progress.

**Searched:** True

**Spoken answer:**

> I'll research the current state of these companies before comparing them.Now let me look into Positron, Cerebras, SambaNova, and Fractile.Now SambaNova and Fractile.Let me read more detail on Fractile and check Cerebras's latest stock price.Let me check Cerebras's Q3 earnings report due today, and look at the broader industry picture.Here's where things stand as of today, November 12th, 2026. The short version: inference has become the industry's battleground, capital is flowing at levels that look like frontier-model funding rather than chip-startup funding, and only one of these six companies has actually proven its business in the public markets — while two others have raised enormous sums without shipping a production chip at all.

**Etched** is the momentum story. It went from a five billion dollar valuation in December 2025, to ten point three billion in July on a three hundred million Series C led by Sequoia with Andreessen Horowitz and SK Hynix, then doubled to twenty one billion just weeks later in August on a seven hundred million Series D led by Jane Street.

**Judge:** gates=['too_many_tool_calls'], quality 2/5, judgment 2/3, spoken 0/2

- The overview and the Etched and Positron figures ($21B Series D, $40-50B talks, $875M at $5B, Asimov tapeout) all trace to the excerpts, but the message breaks off mid-sentence in Positron ('TSMC's N3') and never covers MatX, Cerebras, SambaNova or Fractile, although all were retrieved.
- Searching was right and the opening rightly separates proven businesses from unshipped ones, but it made ten tool calls (including a stock-price check) up to the limit and then spent its length on deep detail for the first two companies.
- Five filler preambles run together, bold markdown company names, and dense number-heavy paragraphs that the word cap cut during the first company.

[Back to top](#review-sheet)
