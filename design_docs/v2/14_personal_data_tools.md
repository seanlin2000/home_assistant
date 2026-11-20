# 14. Personal-data tools

Status: building

## 1. Purpose

Personal-data tools read things that come only to you: your newsletters now, and later your calendar, your mail, Reddit and X, and bank statements (doc 00 §4). This version covers newsletters. Each later reader gets its own section here when it is designed.

The newsletters are WSJ Markets A.M. and P.M., NYT The Morning, and Matt Levine's Money Stuff, about four or five a day. Jarvis should answer:

- "What's in my newsletters today?"
- "What's in Money Stuff today?"
- "Summarize the Binance section."
- "Anything on Nvidia?"
- "Read me Money Stuff", which reads the newsletter aloud word for word, a few minutes at a time.

**Jarvis never touches Gmail.** Once an hour, a job copies one Gmail label to markdown files on the Studio. The tools read only those files. The job holds the mailbox password, and the model never sees it.

## 2. Diagram

```
 EVERY HOUR: GMAIL TO THE STUDIO

 ╭──────────────────────╮              ╭──────────────────────╮              ╭──────────────────────╮              ╭══════════════════════╮
 │     Gmail label      │ IMAP, read   │       pull job       │ raw email    │      converter       │ sections     │     day folders      │
 │     Newsletters      │─────────────▶│   dmarc=pass only    │─────────────▶│   no ads, no emoji   │─────────────▶│  markdown, 30 days   │
 ╰──────────────────────╯              ╰──────────────────────╯              ╰──────────────────────╯              ╰══════════════════════╯

 LIST AND SUMMARIZE

 ╭──────────────────────╮              ╭──────────────────────╮              ╭──────────────────────╮              ╭──────────────────────╮
 │    your question     │              │   main model call    │ tool call    │  list or summarize   │              │       speaker        │
 │  what's new today?   │─────────────▶│     picks a tool     │─────────────▶│  reads day folders   │              │  Kokoro on the puck  │
 ╰──────────────────────╯              ╰──────────────────────╯              ╰──────────────────────╯              ╰──────────────────────╯
                                             │     ▲ cleaned text, marked untrusted      │                                     ▲
                                             │     └─────────────────────────────────────┘                                     │
                                             │                                                                                 │ its answer
                                             └─────────────────────────────────────────────────────────────────────────────────┘

 READ ALOUD

 ╭──────────────────────╮              ╭──────────────────────╮              ╭──────────────────────╮              ╭──────────────────────╮
 │    your question     │              │   main model call    │ tool call    │   newsletter_read    │ the part     │       speaker        │
 │ read me Money Stuff  │─────────────▶│    picks the tool    │─────────────▶│  one 3-minute part   │─────────────▶│   no model between   │
 ╰──────────────────────╯              ╰──────────────────────╯              ╰──────────────────────╯              ╰──────────────────────╯
```

## 3. How it works, step by step

### 3.1 Gmail setup

All newsletters arrive in one Gmail account kept for them. You set it up once, at the Studio's keyboard:

1. Turn on 2-Step Verification. Gmail gives app passwords only to accounts that have it.
2. Create a label named `Newsletters`, with **Show in IMAP** ticked in the label settings.
3. Create a filter: mail from the newsletters' senders gets the label.
4. Create an app password, and store it in the Studio's Keychain with the account's address as the item's account:

   ```
   security add-generic-password -U -s studio-assistant-gmail -a <gmail address> -w
   ```

**The filter is the allowlist.** Code holds no list of senders. To add or drop a newsletter, edit the filter in Gmail.

**Every newsletter is subscribed with this address.** A newsletter forwarded from another account fails the sender check in §3.2 and is skipped.

### 3.2 The hourly pull

A launchd agent, `newsletters`, runs `newsletters-pull` every hour (`StartInterval` 3600).

1. **Connect.** Open `imap.gmail.com` over TLS with a 30-second timeout. Without one, a single hung run would block every later run. Read the address and app password from the Keychain (§3.8, item 5).
2. **Open the label read-only.** `EXAMINE Newsletters`, not `SELECT`, so the job cannot mark, move or delete anything.
3. **Find recent mail.** `SEARCH SINCE` two days back. The overlap means one missed run loses nothing.
4. **Fetch.** `FETCH (INTERNALDATE BODY.PEEK[])` gets the raw message and the time Gmail received it, without marking it read.
5. **Check the sender.** Keep a message only if the topmost `Authentication-Results` header, the one Gmail's own server (`mx.google.com`) wrote, says `dmarc=pass`. Lower headers are ignored, because a sender can write those. A skipped message is logged by its sender's domain only.
6. **Convert and save** each kept message (§3.3 and §3.4).
7. **Record the outcome** in `status.json`: the time of the last success, and the time and reason of the last failure.

**When the pull fails,** the job logs one of three named reasons and exits with status 1, so launchd records the failure. Files already saved are kept.

| Reason | Usual cause |
|---|---|
| Sign-in refused (`AUTHENTICATIONFAILED`) | The app password was revoked, or 2-Step Verification was turned off |
| Label not found (`NO` to `EXAMINE`) | The label was renamed, or Show in IMAP is unticked |
| Network | Gmail or the home connection is down |

**The health check** (doc 10) fails when the last success in `status.json` is more than three hours old.

### 3.3 From email to markdown

Each publisher writes real HTML, `h1` to `h4`, `p`, `li` and `blockquote`, inside layout tables. The converter walks those blocks with `lxml.html`:

| HTML | Markdown |
|---|---|
| `h1` to `h4` | a section heading |
| a short `p` that is bold throughout | a section heading too: The Skint marks its days ("tuesday") this way, with no heading tags |
| `p`, `li` | a paragraph |
| `blockquote` | `>` lines, so a quotation stays apart from the author's own words |
| `tr` of a data table | one line of cells |
| a link | its text only; the address is dropped |

A block nested inside another block is skipped, so no text is written twice. A space goes wherever a block starts or ends, so two paragraphs inside one quotation never run together ("$100.Me:").

**Removed at this step:**

- blocks whose class contains `native-ad` (WSJ's sponsored items)
- text 12 px or smaller, which holds photo credits and captions (NYT's credits are 11 px, WSJ's captions 12 px); a table row holding any is a photo caption and goes whole
- bare `Ad` lines, and lines starting "sponsored:" (The Skint's paid listings)
- footer and subscription lines: "Read in browser", "unsubscribe", "If you're not subscribed", "subscribe to …"
- link arrows, such as The Skint's leading ► and trailing >>
- any line containing an email address, such as "This email was sent to …"
- every emoji
- hidden characters, such as the zero-width padding after Money Stuff's preview line
- elements styled to stay hidden, such as that preview line itself
- everything from the first footer line on: "Sign up here", "You received this", "Follow Us", WSJ's "About Us", The Skint's "support us" and "forward to a friend"

**Joined at this step:**

- A heading with no text under it joins the next heading: NYT's "Today's Number" and "5,000" become one heading.
- Money Stuff's footnotes `[n] …` move from the end of the issue to the end of the section that cites `[n]`.

**The publication's name** is the subject's prefix ("The Morning:", "Money Stuff:") when the email confirms it: its `List-Id` names it, or its text says "the Money Stuff newsletter". Otherwise it is the sender's display name ("WSJ Markets A.M."), because a WSJ headline such as "Widgetron: A Breather Day" has a prefix too. Both WSJ letters come from one address, so the address cannot name them. A display name written all in lowercase ("the skint") is capitalized as a name.

**Why not trafilatura,** which the web tools use: on the samples it dropped WSJ's headline and a stock item, and flattened NYT's lead story into one table cell. trafilatura guesses which part of a page is the article, and a newsletter is all article, laid out in tables. Web pages keep trafilatura, because there the guess removes menus, banners and comments.

### 3.4 Files on disk

```
~/Library/Application Support/studio-assistant/newsletters/
├── status.json                              last success, last failure and its reason
├── read_cursor.json                         the issue and part read aloud last (§3.7)
├── 2026-11-16/
│   ├── 0612-wsj-markets-am-3f9a2c.md        one issue, cleaned
│   ├── 0612-wsj-markets-am-3f9a2c.eml       the raw message it came from
│   ├── 0631-the-morning-81d0e4.md
│   ├── 0631-the-morning-81d0e4.eml
│   └── …
└── 2026-11-17/
```

- **The folder date and file time** are Gmail's receipt time (`INTERNALDATE`) in local time, so an issue that arrives at 23:50 belongs to that day.
- **The name** is the time, a slug of the publication, and a short hash of the Message-ID, so two issues in the same minute never collide.
- **Front matter** holds the publication, subject, headline, receipt time, Message-ID, word count and section names. The tools list an issue without reading its body.
- **Atomic writes:** each file is written beside its final name and renamed into place, as the listings snapshots are (`utils/snapshot_utils.py`), so a tool never reads half a file.
- **Duplicates:** a Message-ID already saved in the look-back folders is skipped. A correction re-sent with the same publication and subject on the same day, under a new Message-ID, replaces the earlier issue.
- **The raw `.eml` is kept** so a better converter can rebuild the markdown without asking Gmail again.
- **Pruning:** each run deletes date folders older than 30 days, and only folders whose names are dates.

### 3.5 The three tools

| Tool | Arguments | Returns |
|---|---|---|
| `newsletters_list` | `date` ("today"), `newsletter` (""), `topic` ("") | Each issue's publication, headline, length and section names, in arrival order |
| `newsletter_summarize` | `newsletter`, `date` ("today"), `section` ("") | The cleaned text of one issue, or one section of it, for the model to summarize |
| `newsletter_read` | `newsletter` (""), `date` ("today"), `section` ("") | One part of about 500 words, spoken as it is (§3.6); a blank `newsletter` or `section="next"` continues the last reading |

**`newsletters_list`:**

- With `newsletter` set, it lists one issue's sections, so "what's in Money Stuff today?" needs no other tool. Blank lists every issue that day.
- With `topic` set, it keeps only the sections that mention the topic. With both set, it searches one issue.
- It returns no snippets. A sentence taken out of one of Levine's hypotheticals says the opposite of what he means.

**`newsletter_summarize`:**

- Cuts only between sections, never inside one, and names the sections it left out.
- Its description tells the model to summarize, to keep what a source reports apart from the author's opinion, and to say numbers as written.

**For all three:**

- Publication and section names are matched loosely (`utils/title_matching_utils.TitleMatcher`), so "the Morning" finds "The Morning".
- Every string argument has a maximum length: `date` 10 characters, `newsletter` and `section` 80, `topic` 40.

**Answers start from the list.** A whole day's issues come to 14,000 to 18,000 tokens, which fits in the context (§3.9) but takes about 20 seconds to read in. So the model lists first, then opens one issue or one section.

### 3.6 Speaking a result without the model

`newsletter_read` returns text for the speaker, not for the model. Rewriting Levine through a model would lose his voice, his irony and his exact numbers, so the harness speaks the tool's text as it is.

**The rule:** `config/tools.toml` gains `speaks_result`, set only for `newsletter_read`. After a tool round, the harness checks for exactly one call in that round, to a speaks-result tool, that was not refused, did not fail, was not a repeat, and returned text opening with a reading's first line (`utils/spoken_reading_utils.py`). If so:

1. It removes the untrusted wrapper from the result.
2. It streams the text to the speaker paragraph by paragraph, outside the 200-word cap on spoken answers. A capped reading would count as a failure.
3. It records the text as the exchange's answer, so the exchange log does not mark it failed.
4. It ends the exchange with no second model call.

Anything else takes the normal path: a refused or failed read, or a failure sentence such as "No newsletter matching …", goes back to the model, which says what went wrong.

**No filler sentence** is spoken before a reading. The file reads instantly, and the reading's first line says what is coming.

**The model never reads a reading.** A reading becomes part of the conversation, which Home Assistant replays with the next question (doc 04). The harness shortens a replayed reading to its first line, `[read aloud]` and its last line, so the next prompt stays small.

### 3.7 Reading in parts, and continuing

Home Assistant, our component and the harness all start a conversation over after five quiet minutes. They time the gap from when the answer was sent. A reading streams to the speaker in moments and then plays for minutes, so after a long reading "continue" would arrive with no history.

So `newsletter_read` returns about 500 words, roughly three minutes of speech, cut at a paragraph break. A part runs on into the next section when there is room, so a two-line teaser is never a part of its own, and each section that starts inside a part is announced by its name.

- **First line:** "Reading Money Stuff: Oh Jensen.", or "Reading Money Stuff: more of Oh Jensen." for a part that starts inside a section.
- **Last line:** "Next is more of Oh Jensen. Say continue to hear it.", or the next section's name. At the end of the issue: "That's the end of Money Stuff."

**"Continue"** works for two reasons:

- Home Assistant listens for a follow-up after every spoken answer, so you need no wake word.
- The last line, still in the replayed history, tells the model which part comes next.

**The read cursor** covers a reset conversation. `read_cursor.json` holds the issue and part read last, and `section="next"` reads the part after it. So "keep reading my newsletter" works an hour later.

### 3.8 Security: the new-tool checklist

The answers to doc 12 §3.12 for all three tools:

| # | Question | Answer |
|---|---|---|
| 1 | Tier, and does the output mark the exchange untrusted? | `read_private`, and yes. The newsletters you get are yours; their text is written by others. |
| 2 | Quarantined reader? | No. Cleanup at pull time replaces it; see below and `DEVIATIONS.md`. |
| 3 | Argument schema | Every string has a maximum length (§3.5). |
| 4 | What leaves the house? | Nothing when a tool runs: they read local files. The hourly pull talks only to Gmail. Newsletter text is the same for every subscriber, so it adds no private terms to the egress guard (doc 12 §3.4). |
| 5 | Credentials | An app password in the Keychain item `studio-assistant-gmail`, read only by the pull job. IMAP is opened read-only (`EXAMINE`). Neither the tool server nor the model can reach the mailbox. |
| 6 | Terms and rate limits | One sign-in an hour to your own mailbox, well within Gmail's IMAP limits. The text stays on the Studio for your own reading. |
| 7 | Benchmark questions | A new category K over a fixed day of made-up issues: list today, list one newsletter's sections, summarize a section, find a topic across issues. One category H issue plants an order in an article body, read through `newsletter_summarize`. Tool-choice checks make sure a summary request never picks `newsletter_read`, whose wrong pick would mean minutes of reading. |
| 8 | Failure sentences | "No newsletters for that day." / "No newsletter matching X; today's are …" / "The last pull failed at 07:00: Gmail refused the sign-in." |

**Why no quarantined reader.** Doc 12 §3.6 sends email through an extraction call that returns fixed fields. That suits a stranger's email. It would damage these newsletters:

- Levine argues through hypotheticals and irony, which an extraction flattens into claims he never made.
- A quotation and the author's reply to it must stay apart.
- Numbers must arrive exactly as written.

These senders are known, and the trust boundary is built from other parts:

- the curated label
- `dmarc=pass` from Gmail's own header
- ads and footers removed by rule
- the untrusted mark, which makes any act-tier tool ask you first (doc 12 §3.3)
- the egress guard on any later web search

**`newsletter_read` adds a path** from newsletter text to the speaker with no model in between. An injected order there is spoken aloud, never obeyed, because no model reads it.

**Keychain access.** Doc 12 §4 planned the `keyring` package. Like the Brave key, this secret is read with macOS's `security` command instead, which an unattended launchd job can run without an access dialog (`utils/keychain_utils.py`).

### 3.9 Context budget

Measured on the Studio on 2026-11-14:

| | Tokens |
|---|---|
| Conversation budget | 32,768 |
| Fixed prompt: system prompt and 23 tool definitions | about 6,030 |
| Room left for tool results, after the reply and history | about 22,000 |
| One issue after cleanup | 1,800 (Markets A.M.) to 6,300 (Money Stuff) |
| A whole day | about 14,000 to 18,000 |

The three new tool definitions add a few hundred tokens to the fixed prompt. A reading costs the model nothing, because it never passes through the model.

## 4. Packages and what they do for the business logic

| Package | What it does |
|---|---|
| Python's `imaplib` | Talks IMAP to Gmail: sign in, `EXAMINE`, `SEARCH`, `FETCH` |
| Python's `email` | Parses the raw message: headers, the HTML part, the receipt date |
| `lxml` (already a dependency) | Parses the HTML for the block walker |
| `PyYAML` (already a dependency) | Writes and reads each issue's front matter |
| macOS `security` | Reads the app password and address from the Keychain |
| `newsletters_mcp/` (ours) | The pull job, converter and store; the three tools |

No new dependencies.

## 5. Configuration we control

**`NewslettersSettings`**, read from `NEWSLETTERS_`-prefixed environment variables:

| Setting | Default | Purpose |
|---|---|---|
| `dir` | `~/Library/Application Support/studio-assistant/newsletters` | Where issues, `status.json` and the cursor live (`NEWSLETTERS_DIR`) |
| `mailbox` | `Newsletters` | The Gmail label |
| `look_back_days` | 2 | How far back each pull searches |
| `keep_days` | 30 | Date folders older than this are deleted |
| `imap_host` | `imap.gmail.com` | |
| `imap_timeout_seconds` | 30 | How long one IMAP step may hang before the pull gives up |
| `keychain_service` | `studio-assistant-gmail` | The Keychain item |
| `stale_after_hours` | 3 | The health check fails once the last good pull is older |
| `summary_max_words` | 6,000 | The most `newsletter_summarize` returns, cut between sections; above any issue seen so far (Money Stuff, about 4,700) |
| `reading_words` | 500 | The length of one part read aloud |
| `today` | unset | Pins "today", for the benchmark only |

**Elsewhere:**

- `config/tools.toml`: all three tools are `read_private` and `marks_untrusted`; `newsletter_read` also has `speaks_result`.
- The Gmail filter: which senders reach the label.
- `scripts/services.sh`: the hourly `newsletters` agent.

## 6. Failure modes

| Failure | What happens | What to do |
|---|---|---|
| The app password is revoked | Each pull fails with "sign-in refused"; the health check fails after three hours; the tools say when the last pull failed and why | Make a new app password and run the `security add-generic-password` command again |
| The label is renamed or hidden from IMAP | The pull fails with "label not found" | Restore the name, or tick Show in IMAP |
| A newsletter changes its HTML | Sections run together, or an ad slips through | Fix the converter, then rebuild from the kept `.eml` files |
| A newsletter arrives forwarded or spoofed | It fails `dmarc=pass` and is skipped; the log names the sender's domain | Subscribe with the newsletter address |
| The Studio is replaced by a new Mac | The move does not carry the app password, so the new Mac's pulls report "not set up" | Make a new app password and run the `security add-generic-password` command on the new Mac |
| A pull runs over SSH | The Keychain is locked to it, so the pull fails | Start it through launchd: `launchctl kickstart gui/$UID/com.studio-assistant.newsletters` |
| An article carries an injected order | Summarize: the exchange is untrusted, so an act-tier tool would ask you first, and the egress guard checks every search. Read: the order is spoken, not obeyed | Nothing; the benchmark's category H issue tests it |
| "Continue" comes after the five-minute reset | The history is gone | Say "keep reading my newsletter"; the read cursor knows the next part |

## 7. Concepts for newcomers

**IMAP.** The protocol mail programs use to read a mailbox on a server. Gmail shows each label as an IMAP folder. `EXAMINE` opens a folder read-only, and `BODY.PEEK` fetches a message without marking it read.

**App password.** A 16-character password Google issues for one program, usable only with 2-Step Verification on. Revoking it locks out that program alone.

**DMARC.** A sender's domain publishes a policy, and the receiving server checks that a message really comes from that domain. Gmail writes the result into an `Authentication-Results` header. `dmarc=pass` means the publisher's domain sent it.

**launchd agent.** macOS's way to run a program at login, or on a timer. `StartInterval` 3600 runs it every hour.

**Front matter.** A YAML block at the top of a markdown file, between `---` lines, holding facts about the file.

## 8. Sources

- IMAP4rev1, including `EXAMINE` and `BODY.PEEK`: [RFC 3501](https://www.rfc-editor.org/rfc/rfc3501)
- The `Authentication-Results` header: [RFC 8601](https://www.rfc-editor.org/rfc/rfc8601)
- DMARC: [RFC 7489](https://www.rfc-editor.org/rfc/rfc7489)
- Google app passwords: [support.google.com/accounts/answer/185833](https://support.google.com/accounts/answer/185833)
- Gmail in other mail programs (IMAP): [support.google.com/mail/answer/7126229](https://support.google.com/mail/answer/7126229)
- Python `imaplib`: [docs.python.org](https://docs.python.org/3/library/imaplib.html)
- `lxml.html`: [lxml.de/lxmlhtml.html](https://lxml.de/lxmlhtml.html)
- `StartInterval`: `man launchd.plist`
