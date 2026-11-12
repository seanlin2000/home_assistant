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

> Good question, and the short answer is: far less than most people worry about, but a bit more than "just the search term" — it depends on how the software is wired.

What stays local. The model's weights, the full conversation history, everything the model generates, and any files you keep on disk never leave your machine. The search provider is not your model host. It's a plain API, the same kind you'd call from a web app. It has no visibility into your chat unless your program explicitly sends parts of it.

What gets transmitted. At minimum, every request carries the search query itself, along with standard network metadata: your IP address, a timestamp, and headers like your API key, which identifies your account. Some providers also log the user agent and referer. The response — search results, snippets, links — comes back to you locally and then gets fed into your model's context, but that part is one-way inbound. The real exposure comes from what your local program puts in the request.

**Judge:** gates=none, quality 4/5, judgment 3/3, spoken 1/2

- It correctly names the query, IP address, timestamp, API key, and user agent as transmitted, the conversation and model output as local, and gives sound minimization steps (minimal queries, VPN, retention policy), but it omits that fetched websites also see the IP and does not mention a privacy-focused or self-hosted proxy such as SearXNG.
- Answering from knowledge without a search was correct, and it flagged that exposure depends on how the tool builds its queries rather than assuming.
- Plain prose without markdown, but at four long paragraphs it ran past the word cap and the listener never heard the minimization steps.

<a id="review-qwen3-8-27b-medium-a82"></a>

### qwen3.8-27b-medium / A82 (random sample)

**Question:** Explain the difference between an API, an MCP server, and a software tool. If I wanted to give a local LLM the ability to search the web, retrieve webpages, and summarize them, how would you architect the system?

**Searched:** False

**Spoken answer:**

> Let's take these three apart, because they're often conflated, and they actually live at different layers of the stack.

A software tool is the broadest term. It's any program that does a job: a calculator, an image editor, a script that scrapes a website, a database. It has no particular contract about how other programs talk to it. You could use it from a command line, from a GUI, or from inside another program, and none of that is standardized.

An API is a specific contract for how one program talks to another. "Application Programming Interface" sounds abstract, but it just means an agreed-upon way to ask a program for something and get something back: here's the endpoint, here's the format of the request, here's the format of the response. The weather service I might call to answer a forecast question is an API. A REST API, a database query interface, even a command line can function as one if the inputs and outputs are well defined.

**Judge:** gates=none, quality 4/5, judgment 3/3, spoken 0/2

- It distinguishes API, MCP, and tool correctly and lays out a sound architecture (MCP server with web_search and fetch_page, length caps, timeouts, an agent loop, summarizing by the model itself), but it never mentions treating fetched text as untrusted (prompt injection) or caching.
- No search was needed for a conceptual architecture question, and its caveat that small local models struggle with tool-argument formats is a useful, honest judgment.
- It runs to about ten long paragraphs, a wall of text read aloud, and the word cap cut it before the architecture part even began.

<a id="review-qwen3-8-27b-medium-a86"></a>

### qwen3.8-27b-medium / A86 (random sample)

**Question:** I have Philips Hue lights connected to a Hue Bridge. I want multiple people in my apartment to control the lights, including through voice commands. What is the best architecture for this, and what happens if the internet goes down?

**Searched:** True

**Spoken answer:**

> Here's the architecture I'd recommend, in layers.

The core is the Hue Bridge itself. It's a Zigbee hub that lives on your local network, so the important thing is to plug it into your router with an Ethernet cable, and ideally reserve a fixed IP address for it in the router settings so DHCP renewals don't cause dropouts. All your bulbs and any Hue switches or sensors pair to the bridge over Zigbee. If the apartment is big or has thick walls, a powered Hue smart plug or sensor in another room works as a Zigbee repeater to keep the mesh reliable.

For multiple people, the simplest setup is: each person downloads the Hue app, creates or signs in to their own Hue account, and adds the same bridge by entering its code. That gives everyone full local app control on their own phone without sharing credentials, and scenes and rooms stay in sync because they live on the bridge. For voice, pick one assistant ecosystem rather than mixing several. If you go with Alexa or Google, each person ideally has their own speaker and links Hue under their own account.

**Judge:** gates=['searched_on_no_search_question'], quality 3/5, judgment 1/3, spoken 1/2

- It correctly makes the bridge the local Zigbee hub and correctly says that app, switches, sensors and bridge automations survive an outage while Alexa, Google and remote access stop, but it claims a HomePod mini runs Siri locally so voice keeps working offline, a doubtful claim that drives its main recommendation, and it never mentions a local option such as Home Assistant.
- It searched a stable architecture question that needed no search, and the troubleshooting pages it got back added nothing to the design.
- No formatting, but five long paragraphs that the word cap cut before the listener heard what happens when the internet goes down.

<a id="review-qwen3-8-27b-medium-a87"></a>

### qwen3.8-27b-medium / A87 (random sample)

**Question:** My projector is connected to a JBL Bluetooth speaker. Sometimes the audio becomes choppy when I connect my laptop, and playing video games on the projector causes more eye strain than playing on my monitor. What could cause these problems, and how would you systematically troubleshoot them?

**Searched:** False

**Spoken answer:**

> Those are two separate problems, so I would take them one at a time.

The choppiness when your laptop joins is almost certainly a bandwidth or interference issue on the Bluetooth link. A few likely culprits: your laptop might be on a Wi-Fi network that overlaps the Bluetooth 2.4 gigahertz band, so adding the laptop to the network or using it actively can flood that band and starve the speaker's audio. The laptop itself could also be advertising its own Bluetooth or Wi-Fi, adding to the congestion. Another possibility is that when the laptop connects, the projector switches audio output — for example, it may default to the laptop's HDMI or to a different audio path — and if the connection you're actually using degrades at that moment, you get drops. And finally, a simple overload: some projectors only handle one stable audio route well, and a second device pairing at the same time can cause the speaker to buffer.

To troubleshoot methodically, I'd isolate the variable.

**Judge:** gates=none, quality 4/5, judgment 3/3, spoken 1/2

- It separates the two problems and gives a staged isolation order for the audio (laptop Wi-Fi, then Bluetooth, unpair the laptop from the speaker, 5 GHz, wired fallback) and for eye strain (brightness, contrast, ambient light, refresh rate, focus and keystone), but it misses the DLP rainbow effect, taking breaks, and firmware updates.
- No search was needed, it ordered the tests one variable at a time, and it asked for the projector model only as an optional follow-up.
- Plain prose, but five dense paragraphs that the word cap cut right after "I'd isolate the variable", before any troubleshooting step.

[Back to top](#review-sheet)

<a id="review-qwen3-8-27b-low"></a>

## qwen3.8-27b-low (4 to review)

<a id="review-qwen3-8-27b-low-a76"></a>

### qwen3.8-27b-low / A76 (random sample)

**Question:** How did the Cold War end? Explain the three most important events that led to the dissolution of the Soviet Union, and distinguish between the causes and the immediate triggers.

**Searched:** False

**Spoken answer:**

> The Cold War ended through a combination of long-simmering structural failures and a few sharp turning points that turned a slow decline into a sudden collapse. The distinction matters, because the causes made the Soviet Union vulnerable, while the triggers made the dissolution feel inevitable and unstoppable in a matter of months.

The three most important events are these.

First, Gorbachev's reforms in the mid-1980s — perestroika and glasnost. This is a cause, not a trigger. Gorbachev recognized the Soviet economy was stagnating and that it could not keep up with the arms race, so he tried to open up political life and restructure the economy. What he didn't fully appreciate was that opening the tap on information and debate would make the system's failures visible in a way they'd never been before. People could finally compare their living standards to the West, and the myths that held the system together — the idea that the Soviet system was fair, efficient, and on the rise — lost their power.

**Judge:** gates=none, quality 3/5, judgment 3/3, spoken 1/2

- It correctly frames economic stagnation and Gorbachev's reforms as causes and the August 1991 coup as the key trigger, but it spends one of its three events on the reforms, leaves out the Ukrainian referendum, the Belovezha Accords and Gorbachev's December resignation, barely touches nationalism, and lists the Velvet Revolution as coming before the Wall fell.
- Answering this stable history question from knowledge without searching was the right call, and it does draw the cause-versus-trigger distinction the user asked for.
- It is plain prose but runs to several long paragraphs, and the word cap cut it off partway through the first event, so the listener never heard the Wall, the coup, or the summary.

<a id="review-qwen3-8-27b-low-a79"></a>

### qwen3.8-27b-low / A79 (random sample)

**Question:** Why are GPUs so effective at AI inference? Explain the differences between GPUs, ASICs, and specialized inference processors. Under what circumstances could a specialized chip outperform an NVIDIA GPU?

**Searched:** True

**Spoken answer:**

> I'll do a quick search to make sure I'm current on the specialized inference chip landscape, then walk through the three parts.Here's the short version of each part.

Why GPUs work so well for AI inference. A transformer model, whether you're training it or running it, is overwhelmingly big matrix multiplications. GPUs have thousands of small cores that can crunch many of those multiplies at once, so they match the shape of the work. Modern ones also add dedicated tensor cores that are tuned exactly for those dot products, and they pair that with huge amounts of fast high-bandwidth memory. That second point matters more than people think: running a model is usually limited not by how fast you can multiply, but by how fast you can stream the model's weights through memory. So a GPU that pairs big compute with lots of high-speed memory fits inference well. On top of all that sits CUDA, which has been tuned for over a decade, so the whole software stack just runs on it with almost no rework.

**Judge:** gates=['searched_on_no_search_question'], quality 4/5, judgment 1/3, spoken 1/2

- It covers matrix multiplication, tensor cores, memory-bound inference, CUDA, TPUs as ASICs, Groq, Cerebras and SambaNova, and when a stable, high-volume workload favours a specialized chip, but it says hyperscaler chips 'simply aren't available to rent' (TPUs are rentable on Google Cloud), gives no architectural detail such as on-chip SRAM or wafer-scale chips, and garbles 'the less the ASIC's advantage shrinks'.
- It ran search_and_read for a conceptual question it could answer from stable knowledge, which was a needless search, though the answer did not lean on the time-sensitive figures it got back.
- It runs to about nine paragraphs, opens with the spoken search preamble run straight into the answer, and the word cap cut it off after the first section.

<a id="review-qwen3-8-27b-low-a87"></a>

### qwen3.8-27b-low / A87 (random sample)

**Question:** My projector is connected to a JBL Bluetooth speaker. Sometimes the audio becomes choppy when I connect my laptop, and playing video games on the projector causes more eye strain than playing on my monitor. What could cause these problems, and how would you systematically troubleshoot them?

**Searched:** False

**Spoken answer:**

> These are two separate issues, so let me take them in turn.

The choppy audio almost certainly comes down to Bluetooth bandwidth and interference. Bluetooth is a shared radio, and it operates on the same two-point-four gigahertz band as Wi-Fi and a lot of wireless peripherals. When your laptop is connected, a few things can happen at once. The laptop might be using Bluetooth for its own wireless mouse or keyboard, and every additional device on that band eats into the capacity. More directly, if the JBL speaker is paired to the projector and the laptop is also broadcasting or searching over Bluetooth, the speaker can momentarily lose its primary stream while the radio gets congested. You can also get a problem where the laptop and the projector are both trying to be the audio source, and the speaker drops frames as it switches.

To work through it systematically, first confirm exactly which device the speaker is paired to. If it's paired to the projector, the audio path is projector to speaker. Then check whether the laptop is running a Bluetooth mouse, keyboard, or any other wireless peripheral.

**Judge:** gates=none, quality 4/5, judgment 3/3, spoken 1/2

- It separates the two problems and gives an ordered test sequence: Bluetooth congestion and competing sources, a wired aux test, distance, and 5 GHz Wi-Fi for the audio; contrast against room light, focus and keystone, DLP color-wheel flicker, and image size for the eye strain. It never says to unpair the speaker from the laptop or update firmware, it leaves out game mode, input lag and seating distance, and it oddly suggests a 2.4 GHz dongle to relieve 2.4 GHz congestion.
- Answering this troubleshooting question from knowledge without searching was right, and it changes one thing at a time as the user asked.
- It is plain prose but runs to about eleven paragraphs, and the word cap cut it early in the audio steps, so the listener never heard the eye-strain half.

<a id="review-qwen3-8-27b-low-b92"></a>

### qwen3.8-27b-low / B92 (random sample)

**Question:** Compare the current high-yield savings account interest rates offered by five major US banks. If I deposit $50,000 for one year, approximately how much interest would I earn at each bank? Identify any minimum balance requirements.

**Searched:** True

**Spoken answer:**

> The results I got back are mostly about online-only banks. You asked specifically about major US banks, so let me pull rates from the big traditional national banks.I have the big-picture numbers. Let me pull the specific per-bank advertised rates from the comparison page to be precise about each major bank.The "big five" traditional banks are the likely intended meaning here, but I need their specific premium-tier numbers rather than just the 0.01% standard rates. Let me pull those.Let me confirm Citi's current rate and US Bank details to complete the five.I have what I need to answer, and I want to flag something important about the premise.

Here's the key finding: the five largest US banks — Chase, Bank of America, Wells Fargo, Citi, and US Bank — do not really offer high-yield savings accounts. Their standard rates are nearly zero, and even their best-tier relationship accounts pay only a few hundredths of a percent. So at $50,000, the interest you'd earn over a year is tiny at every one of them.

**Judge:** gates=['missing_required_tool', 'too_many_tool_calls'], quality 3/5, judgment 2/3, spoken 1/2

- The big-bank figures are sourced and the interest follows from them (Chase 0.01% for about $5, Bank of America 0.04% for about $20 with a $100 minimum, Wells Fargo Platinum 0.05% only with Premier Checking, U.S. Bank's 2.00% only on $5,000 to $24,999.99), but it reads 'major US banks' as the big traditional banks, so the actual high-yield accounts get only one line ('4.2% to 4.4%, roughly $2,100 to $2,200') with no per-bank comparison or minimums, it gives no figure for Citi, and the message ends on a dangling 'Let me show you that contrast quickly' with calculator calls that never ran.
- Pointing out that big banks don't really offer high-yield savings and declining to guess Citi's rate were good calls, but it spent ten tool calls until it hit the limit and never says that these rates are variable and change often.
- It opens with process talk about flagging the premise, runs through bank-by-bank paragraphs full of percentages, ends on a promise it never keeps, and the word cap cut it before any dollar figure was heard.

[Back to top](#review-sheet)

<a id="review-qwen3-8-flash-next-medium"></a>

## qwen3.8-flash-next-medium (4 to review)

<a id="review-qwen3-8-flash-next-medium-a76"></a>

### qwen3.8-flash-next-medium / A76 (random sample)

**Question:** How did the Cold War end? Explain the three most important events that led to the dissolution of the Soviet Union, and distinguish between the causes and the immediate triggers.

**Searched:** True

**Spoken answer:**

> I'll check a couple of the specifics so the dates and sequences are right.The Cold War ended in two stages that are worth keeping separate. The first was diplomatic: by late 1989 the two superpowers had stopped treating each other as adversaries. The second was internal: the Soviet Union itself fell apart in 1991. Bush and Gorbachev met at Malta on the second and third of December 1989, a few weeks after the Berlin Wall fell, and declared the Cold War over. Nothing was signed there; the point was the mutual announcement that the confrontation was finished. A year and a half later, in July 1991, the Warsaw Pact was formally dissolved at Prague, and at a summit that month Gorbachev and Bush declared a US–Soviet strategic partnership, which most historians take as the definitive end.

Now the three events that actually dissolved the Soviet Union.

The first is the revolutions of 1989, with the fall of the Berlin Wall on the ninth of November as their emblem.

**Judge:** gates=['searched_on_no_search_question'], quality 5/5, judgment 1/3, spoken 0/2

- The written answer names the 1989 revolutions, the August 1991 coup, and the Belavezha Accords with correct dates (Ukraine referendum December 1, resignation December 25, dissolution December 26) and cleanly separates economy, arms race, nationalism and reform as causes from the dated triggers.
- It made three tool calls, including a web search, for stable history that the reference expects answered without searching.
- The reply runs to several long paragraphs, so the word cap cut it off right after the first of the three events and the listener never heard the rest.

<a id="review-qwen3-8-flash-next-medium-a78"></a>

### qwen3.8-flash-next-medium / A78 (random sample)

**Question:** Why can a country have a strong stock market while its average citizens feel like the economy is getting worse? Give three concrete examples of how this happens.

**Searched:** True

**Spoken answer:**

> The short version is that a stock index measures what companies earn, not what households keep. Those two can move in opposite directions for long stretches, and right now in the United States they clearly are. The S&P 500 hit record highs in 2026, up roughly twelve percent through the end of September and about seventy percent over five years, while the University of Michigan's sentiment index sat at 51 in early November, still around ten percent below where it was in February, with cost of living the dominant complaint. Three mechanisms explain the gap.

First, the gains land almost entirely on people who already own a lot of stock. Federal Reserve data cited by JPMorgan shows households in the top income quintile holding about 56.3 trillion dollars in stocks and mutual funds, which is 87 percent of all household stock wealth. A rally that adds trillions to that group is, for the majority of families with little or no equity, close to invisible. Sentiment surveys show this directly: in the November reading, confidence actually improved among lower and middle wealth households but fell five percent among the consumers with the largest stock portfolios, whose mood tracked a choppy market instead of rising with it.

**Judge:** gates=['searched_on_no_search_question', 'too_many_tool_calls'], quality 3/5, judgment 1/3, spoken 0/2

- It gives three distinct mechanisms the reference accepts (concentrated stock ownership, prices outpacing wages, profits from pricing power and AI), but it credits the warning that AI gains skip ordinary workers to 'Goldman's own analyst' when the excerpt attributes it to Zandi, and it cites sentiment rising among low-wealth households as evidence for its first point when that cuts the other way.
- It made four web searches plus calculator calls, exceeding the tool-call limit, on a conceptual economics question that needed no search.
- It is a long wall of statistics that the word cap cut off after the first mechanism, so the listener heard only one of the three examples.

<a id="review-qwen3-8-flash-next-medium-a82"></a>

### qwen3.8-flash-next-medium / A82 (random sample)

**Question:** Explain the difference between an API, an MCP server, and a software tool. If I wanted to give a local LLM the ability to search the web, retrieve webpages, and summarize them, how would you architect the system?

**Searched:** True

**Spoken answer:**

> Think of them as three different levels of the same stack.

An API is a contract between programs. It's a published surface — endpoints, request and response shapes, error codes, versioning — that says: send me this JSON and I'll give you that JSON back. It predates LLMs entirely, and it knows nothing about them. A REST or gRPC API is designed for a developer who wrote the calling code by hand, once, at build time.

A software tool is the broader idea: any named capability you can invoke to do one job — a library function, a CLI command, a shell script, a calculator. In the agent world a "tool" means something more specific: a capability packaged with three things — a name, a natural-language description, and a typed parameter schema — precisely so a model can read that description at inference time and decide on its own whether to call it and with what arguments. That description field is the whole point. An API doesn't have one; a tool does, because its caller is a language model, not a programmer.

**Judge:** gates=['searched_on_no_search_question'], quality 2/5, judgment 1/3, spoken 0/2

- The API, tool and MCP definitions match the reference well, but the reply breaks off mid-sentence ('a single noisy 40,00') after only the inference layer and agent loop, so the search and page-fetch tools, model-side summarizing and prompt-injection safeguards are never covered.
- It ran two web searches on stable software-architecture concepts that the reference expects answered without searching.
- It is a long multi-paragraph lecture that the word cap cut off after the tool definition, so the listener heard neither the MCP explanation nor any of the architecture.

<a id="review-qwen3-8-flash-next-medium-b94"></a>

### qwen3.8-flash-next-medium / B94 (random sample)

**Question:** Plan a five-day trip to Switzerland covering Lucerne, Interlaken, and Zermatt. Prioritize scenic train rides, lakes, and mountain viewpoints. Minimize strenuous hiking and explain which train passes or tickets would be most economical.

**Searched:** True

**Spoken answer:**

> I'll look up current Swiss rail fares and pass options before building the itinerary.

**Judge:** gates=['no_final_answer', 'too_many_tool_calls'], quality 0/5, judgment 0/3, spoken 0/2

- The final assistant message is empty even though the searches had returned pass prices, Gornergrat and Harder Kulm fares and closures, so no itinerary or pass comparison was given.
- Searching was right, but it kept searching until it hit the tool-call limit and then produced no answer.
- Only the opening line about looking up fares was spoken, and no answer followed.

[Back to top](#review-sheet)

<a id="review-qwen3-8-flash-next-low"></a>

## qwen3.8-flash-next-low (4 to review)

<a id="review-qwen3-8-flash-next-low-a79"></a>

### qwen3.8-flash-next-low / A79 (random sample)

**Question:** Why are GPUs so effective at AI inference? Explain the differences between GPUs, ASICs, and specialized inference processors. Under what circumstances could a specialized chip outperform an NVIDIA GPU?

**Searched:** True

**Spoken answer:**

> I'll ground this in what's current on the chip landscape before explaining.The short version is that inference, especially the part where a model generates a token at a time, is not really a math problem so much as a plumbing problem, and the specialized chips are the ones trying to fix the plumbing rather than add more arithmetic.

Start with why GPUs work at all. A transformer forward pass is almost entirely a sequence of very large matrix multiplications and a handful of elementwise operations. That is the ideal workload for a GPU: thousands of simple arithmetic units doing the same thing to different data at once, no branches, no control flow, and tensor cores built specifically to chew through 16-bit and 8-bit matrix products. Modern transformer layers are also naturally parallel along the width dimension, so you can slice one matrix product across many processors and stitch the result back together. What a GPU does not have, in proportion, is memory bandwidth. An H100 or H200 has enormous flops, but its HBM delivers single-digit terabytes per second, and during autoregressive decoding that bandwidth is the bottleneck: to produce one token, the chip must read essentially every weight in the model once, while the number of multiply-accumulate operations per byte read is low.

**Judge:** gates=['searched_on_no_search_question'], quality 4/5, judgment 2/3, spoken 0/2

- It correctly covers matrix multiplication on parallel tensor cores, decode being limited by memory bandwidth, Etched, TPU, Groq SRAM and Cerebras, and when a specialized chip wins or loses, but it leaves out NVIDIA's CUDA software ecosystem as a reason GPUs dominate.
- The question was conceptual and needed no search, yet it made four search calls, though it was careful to label Etched's 500,000 tokens per second as an unverified vendor claim.
- Six long paragraphs full of jargon hit the word cap, so the listener heard only the GPU section and none of the comparison or the answer about when a specialized chip wins.

<a id="review-qwen3-8-flash-next-low-a81"></a>

### qwen3.8-flash-next-low / A81 (random sample)

**Question:** If I run a language model locally on my computer but use an external web-search API, what information can the search provider see? Explain what stays local, what gets transmitted, and how I can minimize data exposure.

**Searched:** True

**Spoken answer:**

> Here's the mental model: your local model keeps your data private, but every search call is a small disclosure, and the search provider is the one party you're handing information to.

**What stays local.** Your model weights, your conversation history, your documents, your embeddings, and anything you've cached on disk. Nothing about your corpus leaves your machine unless the agent decides to put it in a query. That's the important part: the provider never sees your documents — only whatever the agent decides to type into the search box.

**What gets transmitted.** Four things, usually. First, the query string itself, which in practice is derived from your prompt or from your documents, so anything the model quotes or paraphrases into that query is now disclosed — names, email addresses, ticket numbers, code snippets, unpublished manuscript language, all of it. Second, your API key, which identifies your account, and since providers require billing details, the account is tied to your name, email, and payment card held by a processor like Stripe.

**Judge:** gates=['searched_on_no_search_question'], quality 4/5, judgment 2/3, spoken 0/2

- It covers the query text, the API key tied to billing identity, IP address, and timing metadata, plus what stays local and the mitigations (query hygiene, SearXNG, VPN, retention tiers), with Brave's 90-day and SerpApi's 31-day retention traced to excerpts, but it says Tavily stores 'session identifiers' when the excerpt says it hashes human IDs.
- The architecture question needed no search, so the three search_and_read calls were unnecessary, though it flagged that provider policies change.
- It uses bold markdown headings such as '**What stays local.**' and runs to six long paragraphs, and the word cap cut it off before the mitigation advice.

<a id="review-qwen3-8-flash-next-low-b88"></a>

### qwen3.8-flash-next-low / B88 (random sample)

**Question:** What are the five most important developments in open-source AI models over the past 30 days? Compare the latest releases from OpenAI's competitors, including DeepSeek, Qwen, Meta, and Mistral.

**Searched:** True

**Spoken answer:**

> I'll search for recent open-source AI model news across those labs.Here's what stands out over the last month, with the caveat that a lot of this comes from aggregator sites rather than the labs themselves, so exact dates and scores should be treated as approximate.

The biggest single event was probably Moonshot AI's Kimi K3.1 Pro. It went live through the API on October 23, and the full weights landed on Hugging Face in early November — sources disagree on whether that was November 2 or November 4. It's a roughly 2.8 trillion parameter mixture of experts with about 104 billion active, a million token context window and native vision, and it's currently topping open-weight rankings, with one leaderboard scoring it 74.6 ahead of last generation's Kimi K3 at 69.2. Moonshot also cut prices while raising capability: two dollars per million input tokens and ten per million output, about a third less than Kimi K3, plus a faster "Highspeed" variant the same day.

**Judge:** gates=['too_many_tool_calls'], quality 5/5, judgment 3/3, spoken 0/2

- All five developments come from the search results and fall in the 30-day window (Kimi K3.1 Pro Oct 23 with weights Nov 2 or 4, Mistral Large 4 weights Oct 29, Muse Spark Open Oct 15, DeepSeek V4.1-Flash-1017 Oct 17, Qwen4-Max-Preview Nov 11 with no weights), it reports the conflicting dates honestly, and it compares the requested labs.
- It searched as needed, warned that the figures come from aggregator sites, and said plainly that Qwen has no open-weight release this month instead of inventing one.
- Eight dense paragraphs of parameters, prices and benchmark scores hit the word cap, so the listener heard only the Kimi item.

<a id="review-qwen3-8-flash-next-low-b95"></a>

### qwen3.8-flash-next-low / B95 (random sample)

**Question:** Imagine I want to build a private, locally hosted voice assistant that can answer general questions, search the web, control smart-home devices, and have natural conversations. I have a $1,000 hardware budget. Propose an architecture, explain the components, identify the biggest limitations, and prioritize what I should build first.

**Searched:** True

**Spoken answer:**

> 

**Judge:** gates=['no_final_answer', 'too_many_tool_calls'], quality 0/5, judgment 0/3, spoken 0/2

- The transcript ends with calculator calls and no final ASSISTANT text, so no architecture, components, limitations or build order were given.
- Searching current hardware prices was right, but it kept searching past the tool-call limit and never produced an answer, failing the central point.
- Nothing was spoken because there is no final reply.

[Back to top](#review-sheet)

<a id="review-qwen3-8-flash-next-off"></a>

## qwen3.8-flash-next-off (4 to review)

<a id="review-qwen3-8-flash-next-off-a82"></a>

### qwen3.8-flash-next-off / A82 (random sample)

**Question:** Explain the difference between an API, an MCP server, and a software tool. If I wanted to give a local LLM the ability to search the web, retrieve webpages, and summarize them, how would you architect the system?

**Searched:** False

**Spoken answer:**

> I know this material well enough to explain it without looking anything up. Here's how I'd lay it out.

An API is a contract between two pieces of software that already exist. It defines endpoints, inputs, outputs, and error behavior, and you call it the way you'd call any other program: you write code against it. A weather service with a JSON endpoint is an API. The API doesn't know or care that an AI model exists; it's just a stable interface over some capability.

A software tool, in the agent sense, is a unit of capability wrapped so that a model can invoke it. It has three parts: a name and description the model reads, a typed input schema, and an execution step that actually does something and returns a result. A tool is usually thin. Underneath it there's often just an API call, or a shell command, or a function already in your process. The important part is the wrapper: the schema and the description are what let a model decide when to use it and how to fill in the arguments.

**Judge:** gates=none, quality 2/5, judgment 3/3, spoken 1/2

- The definitions of an API, a tool (name, description, schema, execution) and an MCP server match the reference, but the reply stops mid-sentence at 'Tool one is search. It wraps a real', so the architecture (agent loop, search and fetch tools, summarizing) and every safeguard are missing.
- It correctly answered a conceptual design question from knowledge without searching.
- The plain prose is listenable, but the reply is far too long and the word cap cut it before the architecture part even began.

<a id="review-qwen3-8-flash-next-off-a87"></a>

### qwen3.8-flash-next-off / A87 (random sample)

**Question:** My projector is connected to a JBL Bluetooth speaker. Sometimes the audio becomes choppy when I connect my laptop, and playing video games on the projector causes more eye strain than playing on my monitor. What could cause these problems, and how would you systematically troubleshoot them?

**Searched:** True

**Spoken answer:**

> I'll ground a couple of the specifics here — Bluetooth audio behavior with multiple devices, and projector flicker/eye-strain causes — before laying out the troubleshooting steps.Let me check one more thing — how JBL speakers behave with several devices connected at once, since that's central to the "when I connect my laptop" clue.Here's what I think is going on with each problem, and then a clean way to work through them one variable at a time.

**Why the audio gets choppy when the laptop joins**

The most likely cause is that Bluetooth and 2.4 gigahertz Wi‑Fi share the same radio band, and your laptop is a busy 2.4 GHz citizen. Bluetooth hops frequencies to dodge noise, but a laptop blasting Wi‑Fi on 2.4 GHz — especially while downloading, syncing, or streaming — crowds out those hops and packets get dropped. That's exactly the pattern you describe: fine until the laptop connects, then choppy. Windows is reportedly particularly bad about handling this coexistence.

**Judge:** gates=['searched_on_no_search_question'], quality 2/5, judgment 1/3, spoken 0/2

- Its audio causes (2.4 GHz interference, JBL multipoint contention, the Windows hands-free profile, drivers) are sound, but the eye-strain section breaks off mid-sentence after refresh rate and input lag, so it misses brightness against room light, field of view, seating distance and the DLP rainbow effect, and it never gives the ordered troubleshooting steps the question asked for.
- It made four web searches for a troubleshooting question that could be answered from general knowledge.
- It uses bold markdown headings, speaks its tool-use narration aloud, and is so long that the word cap cut it after the first paragraph about audio.

<a id="review-qwen3-8-flash-next-off-b88"></a>

### qwen3.8-flash-next-off / B88 (random sample)

**Question:** What are the five most important developments in open-source AI models over the past 30 days? Compare the latest releases from OpenAI's competitors, including DeepSeek, Qwen, Meta, and Mistral.

**Searched:** True

**Spoken answer:**

> I'll look up the recent open-source model releases before comparing them.Good start. Let me pin down what landed in the last two weeks specifically.Now let me check Meta's side and what else landed in the last two weeks.One more check on whether DeepSeek and Z.ai actually shipped today.Let me check two loose ends: whether DeepSeek or Z.ai shipped anything today, and whether Meta has moved since October 15.Here's what I found for the roughly October 13 to November 12 window, with the caveat that this is a fast-moving field and some of these numbers are vendor-reported rather than independently verified.

**One: Moonshot published the weights for Kimi K3.1 Pro.** This is arguably the biggest single event in the window. The model launched as an API on October 23, with Moonshot promising full weights by November 4; the Hugging Face repo actually appeared on November 2, ungated. It's a 2.8 trillion parameter mixture-of-experts with about 104 billion active per token and a one-million-token context, and Artificial Analysis now scores it highest of any open-weights model on its Intelligence Index, around 46.

**Judge:** gates=['too_many_tool_calls'], quality 2/5, judgment 2/3, spoken 0/2

- The three developments it covers are accurate and sourced (Kimi K3.1 Pro weights on November 2, Mistral Large 4 weights on October 29, DeepSeek V4.1-Flash-1017 on October 17 with its Terminal-Bench and DeepSWE figures), but the reply breaks off mid-sentence on DeepSeek, so Qwen (Qwen4-Max preview, no open weights) and Meta (Muse Spark Open), both named in the question, and two of the five developments never appear.
- Searching was right and it flagged vendor-reported numbers, but it spent all ten tool calls chasing loose ends instead of answering with the substantial material it already had.
- It uses bold markdown headings, speaks five tool-use narration lines aloud, and is a wall of detail that the word cap cut in the first item.

<a id="review-qwen3-8-flash-next-off-b89"></a>

### qwen3.8-flash-next-off / B89 (random sample)

**Question:** What is the current state of the AI inference chip startup industry? Compare Etched, MatX, Positron, Cerebras, SambaNova, and Fractile in terms of funding, valuation, technology, and commercial progress.

**Searched:** True

**Spoken answer:**

> I'll research the current state of these AI inference chip startups.Here's where the inference chip sector stands as of today, November 12, 2026. The short version: capital is flooding in faster than silicon is coming out. Most of these companies are being valued on order books and architectural promises rather than shipped revenue, and the one company that actually has real revenue on a public balance sheet — Cerebras — has seen its market value collapse by about forty percent since its May IPO. The formative event of the year was Nvidia's Christmas Eve 2025 deal to take Groq's assets, IP and team for twenty billion dollars, which observers read as Nvidia conceding that a competing inference architecture was necessary rather than something it could build itself.

**Etched** is the standout on paper. Founded in 2022 by three Harvard dropouts, it went from roughly five billion dollars valuation in December 2025 with a five hundred million dollar round, to ten point three billion in July with a three hundred million Series C led by Sequoia alongside Andreessen Horowitz, Jane Street and SK Hynix, then to twenty-one billion on August 18 with a seven hundred million Series D led by Jane Street.

**Judge:** gates=['too_many_tool_calls'], quality 2/5, judgment 2/3, spoken 0/2

- It opens with a sourced overview (Cerebras down about 40 percent since its IPO, matching the $39.82B to $24.01B figures, and the $20B Nvidia-Groq deal) and gives accurate Etched and SambaNova figures, but it breaks off mid-sentence in the SambaNova paragraph, so MatX, Positron, Cerebras's own profile and Fractile, four of the six companies asked about, are never covered even though the searches returned figures for all of them.
- Searching was right, and it labeled Etched's $40-50B offers as bids rather than a closed valuation, but it spent its last calls on extra searches instead of fitting the six companies into a short answer.
- It uses bold markdown company names and has dense, number-packed paragraphs of well over a hundred words each, a wall of text that the word cap cut in the Etched section.

[Back to top](#review-sheet)
