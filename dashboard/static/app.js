// The exchange dashboard page (design doc v2/13). It polls the day list every two seconds; when the newest day gains an exchange, the sidebar
// refreshes and, while "Open new exchanges" is on (or the page is waiting for the answer to a typed question), the new exchange opens.

const POLL_MS = 2000;
const SHORT_RESULT_CHARS = 600;
const state = { openNextArrival: false, asking: false, live: null, days: [], day: null, summaries: [], selected: null, detail: null, today: null, view: "exchanges", layouts: new Map(), drawerCard: null, drawerTab: "sources" };
const SEGMENT_KINDS = [
  ["system", "system rules"],
  ["tools", "tool definitions"],
  ["earlier", "earlier exchanges"],
  ["block", "per-question block"],
  ["question", "question"],
  ["tool_round", "tool rounds"],
  ["rest", "closing markers"],
];
const VERDICT_MARKS = { expected: "✓", early: "!", full_reread: "✕", unknown: "?" };
const MACHINE_PARTS = [
  ["app_bytes", "mem-app", "app memory", "what apps allocated for themselves"],
  ["wired_bytes", "mem-wired", "wired", "kept in RAM for the system and the GPU; llama-server's model weights are here"],
  ["compressed_bytes", "mem-compressed", "compressed", "squeezed by macOS to make room"],
  ["cached_files_bytes", "mem-cached", "cached files", "file contents and purgeable memory, which macOS frees first"],
  ["free_bytes", "mem-free", "free", "not in use"],
];
const chat = { id: newConversationId(), history: [] };

const $ = (id) => document.getElementById(id);

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat(Infinity)) {
    if (child !== null && child !== undefined && child !== false) node.append(child instanceof Node ? child : String(child));
  }
  return node;
}

async function getJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`${path}: ${response.status}`);
  return response.json();
}

// For views that can be unavailable (llama-server down, a trace gone): the error says why, in the server's words.
async function getJsonOrReason(path) {
  const response = await fetch(path, { cache: "no-store" });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `${path}: ${response.status}`);
  return body;
}

const seconds = (value) => (value === null || value === undefined ? "–" : `${value.toFixed(value < 10 ? 2 : 1)}s`);
const localTime = (iso) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
const kilo = (chars) => (chars >= 1000 ? `${(chars / 1000).toFixed(1)}k chars` : `${chars} chars`);
const wordsOnly = (text) => text.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
const argumentText = (args) => Object.entries(args).map(([key, value]) => `${key}=${JSON.stringify(value)}`).join(", ");
const tokensPerSecond = (perSecond) => (perSecond === null || perSecond === undefined ? "–" : `${Math.round(perSecond)} tok/s`);
const count = (tokens) => tokens.toLocaleString();
// Binary gigabytes, labelled GB the way Activity Monitor labels them, so the two read the same.
const memorySize = (bytes) => (bytes < 1024 ** 3 ? `${Math.round(bytes / 1024 ** 2)} MB` : `${(bytes / 1024 ** 3).toFixed(bytes < 10 * 1024 ** 3 ? 2 : 1)} GB`);
const processCount = (processes) => `${processes} process${processes === 1 ? "" : "es"}`;


async function poll() {
  try {
    const [days, latest, today] = await Promise.all([getJson("/api/days"), getJson("/api/latest"), getJson("/api/today")]);
    $("model").textContent = latest ? latest.model : "";
    renderToday(today);
    if (state.view === "cache") refreshSlots();
    if (state.view === "memory") refreshMemory();
    setStatus("live", "live");
    await takeDays(days);
  } catch (error) {
    setStatus("down", "dashboard unreachable, retrying");
  }
  setTimeout(poll, POLL_MS);
}

// Today's averages sit in the header, and each response's card compares itself with them.
function renderToday(today) {
  state.today = today;
  const parts = today.responses
    ? [`Today · ${today.responses} responses`, `prefill avg ${seconds(today.prefill_seconds)} · ${tokensPerSecond(today.prefill_tokens_per_second)}`, `decode avg ${seconds(today.decode_seconds)} · ${tokensPerSecond(today.decode_tokens_per_second)}`]
    : ["Today · no responses yet"];
  $("today").replaceChildren(...parts.map((part) => el("span", {}, part)));
}

function setStatus(kind, text) {
  $("status").className = `status ${kind}`;
  $("status").textContent = text;
}

async function takeDays(days) {
  const newest = days[0];
  const before = state.days.find((day) => newest && day.day === newest.day);
  const grew = state.days.length > 0 && newest && (!before || before.exchanges < newest.exchanges);
  state.days = days;
  renderDayPicker();
  if (state.day === null) return newest && openDay(firstDay(days));
  if (!grew) return;
  const follow = state.openNextArrival || $("follow").checked;
  state.openNextArrival = false;
  if (follow) await openDay(newest.day, { openLatest: true });
  else if (state.day === newest.day) await openDay(newest.day, { keepSelection: true });
}

function firstDay(days) {
  const fromHash = selectionFromHash();
  return fromHash && days.some((day) => day.day === fromHash.day) ? fromHash.day : days[0].day;
}

async function openDay(day, { openLatest = false, keepSelection = false } = {}) {
  const previousCount = state.day === day ? state.summaries.length : null;
  state.day = day;
  state.summaries = await getJson(`/api/days/${day}/exchanges`);
  renderDayPicker();
  renderList(previousCount);
  if (keepSelection) return;
  const fromHash = selectionFromHash();
  if (!openLatest && fromHash && fromHash.day === day) await openExchange(fromHash.day, fromHash.index);
  else await openExchange(day, state.summaries.length - 1);
}

// An exchange's address is #/day/line, or #/cache/day/line or #/memory/day/line to open the page on another tab.
function selectionFromHash() {
  const match = location.hash.match(/^#\/(?:cache\/|memory\/)?(\d{4}-\d{2}-\d{2})\/(\d+)$/);
  return match ? { day: match[1], index: Number(match[2]) } : null;
}

async function openExchange(day, index) {
  if (index < 0) return renderEmptyDay();
  closeDrawer();
  closeSidebar();
  state.live = null;
  state.selected = { day, index };
  history.replaceState(null, "", exchangeAddress());
  renderList();
  state.detail = await getJson(`/api/days/${day}/exchanges/${index}`);
  continueConversationOf(state.detail);
  renderExchange(state.detail);
  if (state.view === "cache") renderPromptLayout();
}

function startNewChat() {
  closeDrawer();
  closeSidebar();
  state.live = null;
  state.selected = null;
  state.detail = null;
  history.replaceState(null, "", location.pathname);
  chat.id = newConversationId();
  chat.history = [];
  renderList();
  renderGreeting();
  $("ask-input").focus();
}


function renderGreeting() {
  $("thread").replaceChildren(
    el("div", { class: "greeting" }, el("h2", {}, "What can I help with?"), el("p", {}, "Ask Jarvis a question to watch it answer: each tool it calls, what the tools returned, and how long every step took.")),
  );
}

function renderEmptyDay() {
  $("thread").replaceChildren(el("div", { class: "greeting" }, el("h2", {}, "Nothing yet"), el("p", {}, "No exchanges on this day yet. New ones appear about a second after the answer ends.")));
}

function renderDayPicker() {
  const picker = $("day");
  picker.replaceChildren(...state.days.map((day) => el("option", { value: day.day, selected: day.day === state.day }, `${day.day} (${day.exchanges})`)));
}

function renderList(previousCount = null) {
  const rows = state.summaries.map((summary, index) => listRow(summary, index, previousCount !== null && index >= previousCount)).reverse();
  $("list").replaceChildren(...rows);
}

function listRow(summary, index, fresh) {
  const selected = state.selected && state.selected.day === summary.day && state.selected.index === index;
  const meta = [localTime(summary.recorded_at), seconds(summary.total_seconds), summary.route, ...summary.tools].filter(Boolean).join(" · ");
  return el(
    "button",
    { class: `row${selected ? " selected" : ""}${fresh ? " fresh" : ""}`, type: "button", title: summary.user_text, onclick: () => openExchange(summary.day, index) },
    el("div", { class: "row-text" }, summary.user_text || "(no question)"),
    el("div", { class: "row-meta" }, summary.failed && el("span", { class: "flag" }, "⚠ "), meta),
  );
}


function renderExchange(detail) {
  const record = detail.record;
  const earlier = earlierTurns(detail);
  const thread = el(
    "div",
    { class: "thread-inner" },
    earlier,
    earlier.length > 0 && el("div", { class: "divider" }, `this exchange · ${localTime(record.recorded_at)}`),
    userTurn(record.user_text, questionNotes(detail)),
    assistantTurn(detail),
  );
  $("thread").replaceChildren(thread);
  $("thread").scrollTop = 0;
}

// Earlier questions in this conversation. One that has its own exchange record opens its steps and timing in place when clicked.
function earlierTurns(detail) {
  const unmatched = [...detail.earlier_exchanges];
  const pairs = questionAnswerPairs(detail.earlier_messages);
  const shown = pairs.length ? pairs : unmatched.map((summary) => ({ question: summary.user_text, answer: summary.final_answer }));
  return shown.map((pair) => earlierTurn(pair, takeMatching(unmatched, pair.question)));
}

function questionAnswerPairs(messages) {
  const pairs = [];
  for (const message of spokenMessages(messages)) {
    if (message.role === "user") pairs.push({ question: message.content, answer: "" });
    else if (pairs.length) pairs[pairs.length - 1].answer = message.content;
  }
  return pairs;
}

function takeMatching(summaries, question) {
  const index = summaries.findIndex((summary) => wordsOnly(summary.user_text) === wordsOnly(question));
  return index < 0 ? null : summaries.splice(index, 1)[0];
}

function earlierTurn(pair, summary) {
  const answer = el("div", { class: "answer earlier" }, pair.answer || "(no answer)");
  if (!summary) return el("div", { class: "earlier-exchange" }, userTurn(pair.question, [], "earlier"), answer);
  const hint = el("span", { class: "expand-hint" }, "Show steps and timing ›");
  const question = userTurn(pair.question, [el("span", {}, `${localTime(summary.recorded_at)} · ${seconds(summary.total_seconds)} · `, hint)], "earlier opens");
  const turn = el("div", { class: "earlier-exchange" }, question, answer);
  question.addEventListener("click", () => toggleEarlier(turn, summary));
  return turn;
}

async function toggleEarlier(turn, summary) {
  const opening = !turn.classList.contains("expanded");
  if (opening && !turn.querySelector(".assistant-turn")) turn.append(assistantTurn(await getJson(`/api/days/${summary.day}/exchanges/${summary.index}`)));
  turn.classList.toggle("expanded", opening);
  turn.querySelector(".expand-hint").textContent = opening ? "Hide steps and timing" : "Show steps and timing ›";
}

function spokenMessages(messages) {
  return messages.filter((message) => message.role === "user" || (message.role === "assistant" && message.content));
}

function userTurn(text, notes, extraClass = "") {
  return el("div", { class: `user-turn ${extraClass}` }, el("div", { class: "bubble" }, text || "(no question)"), notes.map((note) => el("div", { class: "under-bubble" }, note)));
}

function questionNotes(detail) {
  const record = detail.record;
  const notes = [record.source === "home_assistant" ? `🎤 spoken · ${localTime(record.recorded_at)}` : `typed · ${record.source} · ${localTime(record.recorded_at)}`];
  if (detail.speech && detail.speech.heard && wordsOnly(detail.speech.heard) !== wordsOnly(record.user_text)) notes.push(`Whisper heard: “${detail.speech.heard}”`);
  return notes;
}

function assistantTurn(detail) {
  const record = detail.record;
  return el(
    "div",
    { class: "assistant-turn" },
    record.route && el("div", { class: "activity" }, `↪ router chose ${record.route.route}${record.route.also.length ? ` then ${record.route.also.join(", ")}` : ""} (${record.route.source}${record.route.detail ? `: ${record.route.detail}` : ""})`),
    detail.filler_text && el("div", { class: "activity filler" }, `🔊 “${detail.filler_text}”`, el("span", { class: "time" }, `spoken at ${seconds(record.time_to_first_spoken_seconds)} while the tools ran`)),
    detail.turns.map(turnElements),
    answerElement(record),
    sourceChips(detail),
    el("div", { class: "meta" }, metaBadges(detail)),
    speedCard(detail),
    timingCard(detail),
    detail.system_prompt && fold(`System prompt (${detail.system_prompt.length} chars)`, detail.system_prompt),
    !detail.has_trace && el("div", { class: "note-line" }, "The full tool text for this exchange is gone (no trace kept, or older than 14 days); sizes and times remain."),
  );
}

function turnElements(turn) {
  return [
    turn.thinking && fold(`💭 Thought for ${turn.thinking.split(/\s+/).length} words`, turn.thinking),
    turn.text.trim() && el("div", { class: "said-beside" }, el("span", { class: "label" }, "written beside the tool calls"), turn.text),
    turn.tools.map(toolCard),
  ];
}

function answerElement(record) {
  if (record.stayed_silent) return el("div", { class: "answer silent" }, "🔇 Stayed silent: the model judged the speech was not meant for it.");
  return el("div", { class: "answer" }, record.final_answer || "(empty)");
}

function fold(title, text) {
  return el("details", { class: "fold" }, el("summary", {}, title), el("pre", {}, text));
}

function metaBadges(detail) {
  const record = detail.record;
  const badges = [
    el("span", { title: "the model that answered this exchange" }, record.model),
    el("span", {}, `total ${seconds(record.total_seconds)}`),
    el("span", {}, `first word ${seconds(record.time_to_first_spoken_seconds)}`),
    el("span", {}, `${record.model_calls.length} model calls · ${record.tool_calls.length} tool calls`),
    el("span", {}, `${record.spoken_chars} chars spoken`),
    record.untrusted && el("span", { class: "badge warn" }, "read untrusted text"),
  ];
  return [...badges, ...failureFlags(record).map((flag) => el("span", { class: "badge bad" }, flag))];
}

function failureFlags(record) {
  const flags = [];
  if (record.error) flags.push(`error: ${record.error}`);
  if (record.truncated) flags.push("answer cut at the word budget");
  if (record.hit_tool_round_cap) flags.push("hit the tool round cap");
  if (record.malformed_tool_call_count) flags.push(`${record.malformed_tool_call_count} malformed tool calls`);
  if (record.empty_completion_retries) flags.push(`${record.empty_completion_retries} empty replies retried`);
  if (!record.final_answer.trim() && !record.stayed_silent) flags.push("no answer");
  return flags;
}


function sourceChips(detail) {
  const cards = detail.turns.flatMap((turn) => turn.tools).filter((card) => card.evidence);
  const chips = cards.flatMap((card) => card.evidence.sources.filter((source) => source.starred).map((source) => sourceChip(card, source)));
  return chips.length > 0 && el("div", { class: "source-chips" }, chips);
}

function sourceChip(card, source) {
  const label = source.site || source.title;
  return el("button", { type: "button", class: "chip", title: `${source.title}: holds most of the answer's distinctive words`, onclick: () => openDrawer(card, source) }, el("span", { class: "star" }, "★"), el("span", {}, label));
}

function toolCard(card) {
  const badges = [card.refused && el("span", { class: "badge bad" }, "refused"), card.repeated && el("span", { class: "badge warn" }, "repeat"), card.error && el("span", { class: "badge bad" }, card.error)];
  const opens = card.result !== null;
  const head = el(
    "div",
    { class: `tool-head${opens ? " opens" : ""}`, onclick: opens ? () => openDrawer(card) : undefined, title: opens ? "Open the full text" : undefined },
    el("span", { class: "tool-icon" }, "🔧"),
    el("span", { class: "tool-name" }, card.name),
    el("span", { class: "tool-args", title: argumentText(card.arguments) }, argumentText(card.arguments)),
    badges,
    el("span", { class: "tool-stats" }, `${seconds(card.seconds)} · ${kilo(card.result_chars)}`),
    opens && el("span", { class: "tool-open" }, "full text ›"),
  );
  return el("div", { class: `tool-card${card.error || card.refused ? " failed" : ""}` }, head, opens && toolBody(card));
}

function toolBody(card) {
  const evidence = card.evidence;
  const numbered = evidence && evidence.sources.some((source) => source.rank !== null);
  if (numbered) return el("div", { class: "tool-body" }, evidence.header && el("div", { class: "tool-header-line" }, evidence.header), evidence.sources.map(sourceRow));
  const text = evidence ? evidence.sources.map((source) => source.text).join("\n") : card.result;
  const shown = text.length > SHORT_RESULT_CHARS ? `${text.slice(0, SHORT_RESULT_CHARS)}…` : text;
  return el("div", { class: "tool-body" }, el("pre", {}, shown));
}

function sourceRow(source) {
  const coverage = el("div", { class: "coverage", title: `${Math.round(source.coverage * 100)}% of the answer's words` }, el("i", { style: `width:${source.coverage * 100}%` }));
  return el(
    "div",
    { class: `source-row${source.read ? "" : " unread"}` },
    el("span", { class: "rank" }, source.rank),
    el("span", { class: "site" }, source.site || ""),
    el("span", { class: "title", title: source.title }, source.title + (source.read ? "" : " (snippet only)")),
    coverage,
    el("span", { class: "size" }, kilo(source.text.length)),
    el("span", { class: "star", title: source.starred ? "holds most of the answer's distinctive words" : "" }, source.starred ? "★" : ""),
  );
}


function speedCard(detail) {
  const speed = detail.speed;
  if (!speed) return null;
  const today = state.today && state.today.responses ? state.today : null;
  const cell = (text, kind = "") => el("span", { class: kind }, text);
  const row = (phase, phaseSeconds, tokens, tokensText, average) => [cell(phase, "phase"), cell(seconds(phaseSeconds)), cell(tokensText), cell(tokensPerSecond(phaseSeconds > 0 ? tokens / phaseSeconds : null)), versusAverage(phaseSeconds, average)];
  return el(
    "div",
    { class: "speed-card" },
    el("div", { class: "speed-title" }, "This response"),
    el(
      "div",
      { class: "speed-grid" },
      ["", "time", "tokens", "speed", "vs today's average"].map((heading) => cell(heading, "head")),
      row("prefill", speed.prefill_seconds, speed.prefill_tokens, `${count(speed.prefill_tokens)} read, ${count(speed.cached_tokens)} cached`, today && today.prefill_seconds),
      row("decode", speed.decode_seconds, speed.decode_tokens, `${count(speed.decode_tokens)} written`, today && today.decode_seconds),
    ),
    perCallLine(detail.record.model_calls),
  );
}

function versusAverage(phaseSeconds, average) {
  if (average === null || average === undefined) return el("span", { class: "versus" }, "–");
  const difference = phaseSeconds - average;
  if (Math.abs(difference) < 0.005) return el("span", { class: "versus" }, "the same");
  return el("span", { class: `versus ${difference > 0 ? "slower" : "faster"}` }, `${seconds(Math.abs(difference))} ${difference > 0 ? "slower" : "faster"}`);
}

// Numbered as in the timing chart, so "model #2" names the same call in both.
function perCallLine(modelCalls) {
  const timed = modelCalls.map((stats, index) => ({ stats, number: index + 1 })).filter(({ stats }) => stats.prompt_eval_seconds !== null && stats.generation_seconds !== null);
  if (timed.length < 2) return null;
  return el("div", { class: "speed-calls" }, timed.map(({ stats, number }) => `model #${number}: prefill ${seconds(stats.prompt_eval_seconds)}, decode ${seconds(stats.generation_seconds)}`).join(" · "));
}

function timingCard(detail) {
  const timeline = detail.timeline;
  const note = [timeline.approximate ? "approximate: this exchange was recorded before steps were timestamped" : "", detail.speech ? "" : "speech timings not available"].filter(Boolean).join(" · ");
  return el(
    "details",
    { class: "fold timing", open: true },
    el("summary", {}, `Timing · ${seconds(timeline.total_seconds)} total, first word at ${seconds(timeline.first_spoken_seconds)}`),
    note && el("div", { class: "timing-note" }, note),
    timelineGrid(timeline),
    timelineLegend(),
  );
}

function timelineGrid(timeline) {
  const ends = timeline.bars.map((bar) => bar.start + bar.seconds);
  const low = Math.min(0, ...timeline.bars.map((bar) => bar.start));
  const high = Math.max(timeline.total_seconds, ...ends, 0.1);
  const position = (value) => `${((value - low) / (high - low)) * 100}%`;
  const ticks = tickValues(low, high);
  const grid = el("div", { class: "timeline" });
  grid.append(el("div"), el("div", { class: "axis" }, ticks.map((tick) => el("span", { style: `left:${position(tick)}` }, `${tick}s`))), el("div"));
  for (const bar of timeline.bars) {
    const track = el("div", { class: "track" }, ticks.map((tick) => el("div", { class: "gridline", style: `left:${position(tick)}` })), markers(timeline, position), barElement(bar, position));
    grid.append(el("div", { class: "lane-label", title: bar.label }, bar.label), track, el("div", { class: "lane-seconds" }, seconds(bar.seconds)));
  }
  return grid;
}

function markers(timeline, position) {
  const spoken = timeline.first_spoken_seconds;
  return [
    el("div", { class: "marker", style: `left:${position(0)}`, title: "the question reaches the agent" }),
    spoken !== null && el("div", { class: "marker spoken", style: `left:${position(spoken)}`, title: `first word spoken at ${seconds(spoken)}` }),
  ];
}

function tickValues(low, high) {
  const span = high - low;
  const step = [0.25, 0.5, 1, 2, 5, 10, 20, 30, 60].find((candidate) => span / candidate <= 8) || 120;
  const ticks = [];
  for (let tick = Math.ceil(low / step) * step; tick <= high + 1e-9; tick += step) ticks.push(Number(tick.toFixed(2)));
  return ticks;
}

function barElement(bar, position) {
  const node = el("div", { class: `bar ${bar.lane}${bar.failed ? " failed" : ""}`, style: `left:${position(bar.start)};width:calc(${position(bar.start + bar.seconds)} - ${position(bar.start)})` });
  node.append(...(bar.lane === "model" ? modelSegments(bar) : [el("i", { style: "flex:1" })]));
  attachTooltip(node, () => barTooltip(bar));
  return node;
}

function modelSegments(bar) {
  const load = bar.load_seconds || 0;
  const read = bar.read_seconds || 0;
  const write = bar.write_seconds || 0;
  const other = Math.max(bar.seconds - load - read - write, 0);
  const parts = [["seg-load", load], ["seg-read", read], ["seg-write", write], ["seg-other", other]];
  return parts.filter(([, value]) => value > 0).map(([kind, value]) => el("i", { class: kind, style: `flex:${value}` }));
}

function barTooltip(bar) {
  const lines = [`${bar.label}: ${seconds(bar.seconds)} starting at ${seconds(bar.start)}`];
  if (bar.load_seconds) lines.push(`loading the model ${seconds(bar.load_seconds)}`);
  if (bar.read_seconds !== null && bar.read_seconds !== undefined) lines.push(`reading the prompt ${seconds(bar.read_seconds)}`);
  if (bar.write_seconds !== null && bar.write_seconds !== undefined) lines.push(`writing ${seconds(bar.write_seconds)}`);
  if (bar.detail) lines.push(bar.detail);
  return lines.join("\n");
}

function timelineLegend() {
  const entry = (style, text) => el("span", {}, el("i", { style }), text);
  return el(
    "div",
    { class: "legend" },
    entry("background:var(--speech)", "speech (Home Assistant)"),
    entry("background:var(--router)", "router"),
    entry("background:var(--model-read)", "model reading the prompt"),
    entry("background:var(--model-write)", "model writing"),
    entry("background:repeating-linear-gradient(135deg,var(--model-load) 0 3px,transparent 3px 6px)", "model loading"),
    entry("background:var(--tool)", "tool"),
    entry("border-left:2px dashed var(--speech);width:0;border-radius:0", "first word spoken"),
  );
}

function attachTooltip(node, textFor) {
  const tooltip = $("tooltip");
  node.addEventListener("mousemove", (event) => {
    tooltip.textContent = textFor();
    tooltip.hidden = false;
    tooltip.style.left = `${Math.min(event.clientX + 14, window.innerWidth - tooltip.offsetWidth - 8)}px`;
    tooltip.style.top = `${event.clientY + 14}px`;
  });
  node.addEventListener("mouseleave", () => (tooltip.hidden = true));
}


function openDrawer(card, source = null) {
  state.drawerCard = card;
  state.drawerTab = "sources";
  $("drawer").hidden = false;
  $("drawer-title").textContent = `${card.name}(${argumentText(card.arguments)})`;
  renderDrawer();
  if (source && source.rank !== null) document.getElementById(`source-${source.rank}`)?.scrollIntoView();
}

function renderDrawer() {
  const card = state.drawerCard;
  for (const tab of document.querySelectorAll(".tab")) tab.classList.toggle("active", tab.dataset.tab === state.drawerTab);
  const body = $("drawer-body");
  body.scrollTop = 0;
  if (state.drawerTab === "raw" || !card.evidence) return body.replaceChildren(el("pre", { class: "raw" }, card.result));
  const evidence = card.evidence;
  const pattern = termPattern(evidence.terms);
  const terms = el("div", { class: "terms" }, evidence.terms.length ? ["Answer words looked for: ", evidence.terms.map((term) => el("mark", {}, term))] : "The answer has no words the question did not already use.");
  const header = evidence.header && el("div", { class: "tool-header-line" }, evidence.header);
  const footer = evidence.footer && el("div", { class: "tool-header-line" }, `Closing note to the model: ${evidence.footer}`);
  body.replaceChildren(...[terms, header, ...evidence.sources.map((source) => drawerSource(source, pattern)), footer].filter(Boolean));
}

function drawerSource(source, pattern) {
  const meta = `${source.read ? "" : "snippet only · "}${kilo(source.text.length)} · ${Math.round(source.coverage * 100)}% of the answer's words${source.starred ? " ★" : ""}`;
  const text = el("pre");
  text.innerHTML = highlighted(source.text, pattern);
  return el(
    "div",
    { class: "source", id: source.rank !== null ? `source-${source.rank}` : undefined },
    el("h3", {}, source.rank !== null ? `[${source.rank}] ` : "", source.title),
    source.url && el("a", { href: source.url, target: "_blank", rel: "noreferrer noopener" }, source.url),
    el("div", { class: "source-meta" }, meta),
    text,
  );
}

function termPattern(terms) {
  if (!terms.length) return null;
  const escaped = terms.map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  return new RegExp(`\\b(${escaped.join("|")})\\b`, "gi");
}

function escapeHtml(text) {
  return text.replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
}

function highlighted(text, pattern) {
  const escaped = escapeHtml(text);
  return pattern ? escaped.replace(pattern, "<mark>$1</mark>") : escaped;
}

function closeDrawer() {
  $("drawer").hidden = true;
  state.drawerCard = null;
}


function newConversationId() {
  return `dashboard-${Date.now().toString(36)}`;
}

// A question typed while an exchange is open continues that exchange's conversation, as a follow-up spoken to the speaker would.
function continueConversationOf(detail) {
  const record = detail.record;
  const earlier = spokenMessages(detail.earlier_messages).map((message) => ({ role: message.role, content: message.content }));
  chat.id = record.conversation_id || newConversationId();
  chat.history = [...earlier, { role: "user", content: record.user_text }, { role: "assistant", content: record.final_answer }];
}

async function askQuestion(event) {
  event.preventDefault();
  const question = $("ask-input").value.trim();
  if (!question || state.asking) return;
  $("ask-input").value = "";
  fitComposer();
  setAsking(true);
  state.openNextArrival = true;
  const conversation = [...chat.history, { role: "user", content: question }];
  const answer = await streamAnswer({ conversation_id: chat.id, conversation });
  if (answer === null) state.openNextArrival = false;
  else chat.history = [...conversation, { role: "assistant", content: answer }];
  setAsking(false);
}

async function streamAnswer(request) {
  const live = { question: request.conversation[request.conversation.length - 1].content, steps: [], answer: "", model: null, done: false, error: null };
  state.live = live;
  $("live-turn")?.removeAttribute("id");
  renderLive(live);
  try {
    const response = await fetch("/api/ask", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(request) });
    if (!response.ok) throw new Error((await response.json()).error || response.status);
    await readLines(response, (line) => takeEvent(live, JSON.parse(line)));
  } catch (error) {
    live.error = String(error.message || error);
  }
  renderLive(live);
  return live.error ? null : live.answer;
}

async function readLines(response, onLine) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffered = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffered += decoder.decode(value, { stream: true });
    const lines = buffered.split("\n");
    buffered = lines.pop();
    lines.filter((line) => line.trim()).forEach(onLine);
  }
}

function takeEvent(live, event) {
  if (event.event === "filler") live.steps.push({ kind: "filler", text: `🔊 “${event.text}”` });
  else if (event.event === "tool_started") live.steps.push({ kind: "tool", text: `🔧 ${event.call.name}(${argumentText(event.call.arguments)})`, time: "running…" });
  else if (event.event === "tool_finished") finishToolStep(live, event);
  else if (event.event === "answer") live.answer += event.text;
  else if (event.event === "error") live.error = event.message;
  else if (event.event === "done") finishLive(live, event.transcript);
  renderLive(live);
}

function finishToolStep(live, event) {
  const step = live.steps.find((candidate) => candidate.kind === "tool" && candidate.time === "running…");
  if (step) step.time = `${seconds(event.seconds)}${event.error ? ` · ${event.error}` : ""}`;
}

function finishLive(live, transcript) {
  live.done = true;
  live.model = transcript.model;
  live.total = transcript.total_seconds;
}

// The live turn is drawn under whatever the thread already shows, until the recorded exchange arrives and replaces it (state.live is then cleared).
function renderLive(live) {
  if (state.live !== live) return;
  const box = liveBox();
  box.replaceChildren(userTurn(live.question, ["typed · dashboard · now"]), liveAssistantTurn(live));
  $("thread").scrollTop = $("thread").scrollHeight;
}

function liveBox() {
  const existing = $("live-turn");
  if (existing) return existing;
  let inner = $("thread").querySelector(".thread-inner");
  if (!inner) {
    inner = el("div", { class: "thread-inner" });
    $("thread").replaceChildren(inner);
  }
  const box = el("div", { id: "live-turn", class: "live-turn" });
  inner.append(box);
  return box;
}

function liveAssistantTurn(live) {
  const steps = live.steps.map((step) => el("div", { class: `activity ${step.kind}` }, step.text, step.time && el("span", { class: "time" }, step.time)));
  const answer = live.answer || live.done ? el("div", { class: "answer" }, live.answer || "(empty)", !live.done && el("span", { class: "cursor" })) : !live.error && el("div", { class: "answer" }, el("span", { class: "cursor" }));
  const footer = live.done && el("div", { class: "meta" }, el("span", {}, live.model), el("span", {}, `total ${seconds(live.total)}`), el("span", {}, "the full record opens in a moment"));
  const error = live.error && el("div", { class: "activity error" }, `Not answered: ${live.error}`);
  return el("div", { class: "assistant-turn" }, steps, answer, error, footer);
}

function setAsking(asking) {
  state.asking = asking;
  updateSendButton();
  if (!asking) $("ask-input").focus();
}

function updateSendButton() {
  $("ask-send").disabled = state.asking || !$("ask-input").value.trim();
}

function fitComposer() {
  const input = $("ask-input");
  input.style.height = "auto";
  input.style.height = `${input.scrollHeight}px`;
  updateSendButton();
}

function sendOnEnter(event) {
  if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
  event.preventDefault();
  $("composer").requestSubmit();
}


function exchangeAddress() {
  if (!state.selected) return location.pathname;
  return `#/${state.view === "exchanges" ? "" : `${state.view}/`}${state.selected.day}/${state.selected.index}`;
}

function showView(view) {
  state.view = view;
  if (state.selected) history.replaceState(null, "", exchangeAddress());
  for (const tab of document.querySelectorAll(".view-tab")) {
    tab.classList.toggle("active", tab.dataset.view === view);
    tab.setAttribute("aria-selected", String(tab.dataset.view === view));
  }
  $("thread").hidden = view !== "exchanges";
  $("composer").hidden = view !== "exchanges";
  $("cache-view").hidden = view !== "cache";
  $("memory-view").hidden = view !== "memory";
  closeDrawer();
  if (view === "cache") {
    refreshSlots();
    renderPromptLayout();
  }
  if (view === "memory") refreshMemory();
}

function sectionHead(title, ...notes) {
  return el("div", { class: "panel-head" }, el("h2", {}, title), notes.filter(Boolean).map((note) => el("span", { class: "panel-note" }, note)));
}

async function refreshSlots() {
  try {
    const view = await getJsonOrReason("/api/slots");
    $("slots").replaceChildren(sectionHead("Live slots", "from llama-server, every 2 s", `one pool of ${count(view.pool_tokens)} tokens`), el("div", { class: "slot-rows" }, view.slots.map(slotRow)));
  } catch (error) {
    $("slots").replaceChildren(sectionHead("Live slots"), el("div", { class: "note-line" }, String(error.message || error)));
  }
}

// A slot's meter is what it holds against the part of the pool the harness budgets for it; a slot may borrow past its share, so the meter stops full.
function slotRow(slot) {
  const holds = slot.holds_tokens;
  const meter = el("div", { class: "meter" }, el("i", { style: `width:${holds === null ? 0 : Math.min(holds / slot.share_tokens, 1) * 100}%` }));
  const amount = holds === null ? "empty since the server started" : `${count(holds)} / ${count(slot.share_tokens)}`;
  const row = el(
    "div",
    { class: "slot-row" },
    el("span", { class: "slot-name" }, `slot ${slot.slot}`, el("span", { class: "slot-role" }, slot.role)),
    meter,
    el("span", { class: "slot-amount" }, amount),
    el("span", { class: `slot-state${slot.processing ? " busy" : ""}` }, slot.processing ? "working" : "idle"),
  );
  attachTooltip(row, () => slotTooltip(slot));
  return row;
}

function slotTooltip(slot) {
  if (slot.last_prompt_tokens === null) return `slot ${slot.slot} has not served a request since llama-server started`;
  return [
    `slot ${slot.slot}, ${slot.role}: holds about ${count(slot.holds_tokens)} tokens`,
    `last request: ${count(slot.last_prompt_tokens)} prompt tokens, ${count(slot.last_cached_tokens || 0)} of them from the cache`,
    `then wrote ${count(slot.last_written_tokens || 0)} tokens`,
    `budgeted share of the pool: ${count(slot.share_tokens)} tokens`,
  ].join("\n");
}

async function renderPromptLayout() {
  const box = $("prompt-layout");
  const selected = state.selected;
  if (!selected) return box.replaceChildren(sectionHead("This exchange"), el("div", { class: "note-line" }, "Pick an exchange in the sidebar to see how its prompt was cached."));
  const summary = state.summaries[selected.index];
  const title = summary ? `“${summary.user_text}” · ${localTime(summary.recorded_at)}` : "";
  const key = `${selected.day}/${selected.index}`;
  if (!state.layouts.has(key)) box.replaceChildren(sectionHead("This exchange", title), el("div", { class: "note-line" }, "Rebuilding the prompt with llama-server…"));
  try {
    if (!state.layouts.has(key)) state.layouts.set(key, await getJsonOrReason(`/api/days/${selected.day}/exchanges/${selected.index}/prompt`));
    if (state.selected !== selected) return;
    box.replaceChildren(sectionHead("This exchange", title), ...layoutElements(state.layouts.get(key)));
  } catch (error) {
    if (state.selected === selected) box.replaceChildren(sectionHead("This exchange", title), el("div", { class: "note-line" }, String(error.message || error)));
  }
}

function layoutElements(layout) {
  if (!layout.calls.length) return [el("div", { class: "note-line" }, "No model call in this exchange.")];
  const longest = Math.max(...layout.calls.map((call) => call.prompt_tokens), 1);
  return [
    el("p", { class: "panel-lead" }, "Each model call's prompt, in tokens, split into the parts the harness lays out. The thin track under it shows what came from the cache and what was read fresh."),
    layout.note && el("div", { class: "timing-note" }, layout.note),
    promptChart(layout.calls, longest),
    promptLegend(layout.calls),
    el("div", { class: "verdicts" }, layout.calls.map(verdictLine)),
    partsTable(layout.calls[layout.calls.length - 1]),
    systemPromptFold(layout),
    layout.per_question_block && fold(`Per-question block (${segmentTokens(layout, "block")} tokens) · changes every question`, layout.per_question_block),
    toolsFold(layout),
  ];
}

function promptChart(calls, longest) {
  const position = (tokens) => `${(tokens / longest) * 100}%`;
  const ticks = tokenTicks(longest);
  const chart = el("div", { class: "prompt-chart" });
  chart.append(el("div", { class: "prompt-row" }, el("div"), el("div", { class: "axis" }, ticks.map((tick) => el("span", { style: `left:${position(tick)}` }, count(tick))))));
  for (const call of calls) {
    const gridlines = ticks.map((tick) => el("div", { class: "gridline", style: `left:${position(tick)}` }));
    const track = el("div", { class: "prompt-track" }, gridlines, segmentBar(call, position), cacheBar(call, position), cacheMarker(call, position));
    chart.append(el("div", { class: "prompt-row" }, el("div", { class: "lane-label" }, `model #${call.number}`), track, el("div", { class: "lane-seconds" }, cacheNumbers(call))));
  }
  return chart;
}

function segmentBar(call, position) {
  const bar = el("div", { class: "segments", style: `width:${position(call.prompt_tokens)}` });
  for (const segment of call.segments) {
    const node = el("i", { class: `segment seg-${segment.kind}`, style: `flex:${segment.tokens}` });
    attachTooltip(node, () => segmentTooltip(segment, call));
    bar.append(node);
  }
  return bar;
}

function segmentTooltip(segment, call) {
  const cached = call.cached_tokens || 0;
  const cachedPart = Math.max(Math.min(cached, segment.start + segment.tokens) - segment.start, 0);
  const origin = cachedPart === segment.tokens ? "all from the cache" : cachedPart === 0 ? "all read fresh" : `${count(cachedPart)} from the cache, ${count(segment.tokens - cachedPart)} read fresh`;
  return `${segment.label}: ${count(segment.tokens)} tokens (${count(segment.start)} to ${count(segment.start + segment.tokens)})\n${origin}`;
}

function cacheBar(call, position) {
  const cached = Math.min(call.cached_tokens || 0, call.prompt_tokens);
  return el(
    "div",
    { class: "cache-track", style: `width:${position(call.prompt_tokens)}` },
    cached > 0 && el("i", { class: "cached", style: `flex:${cached}` }),
    call.prompt_tokens > cached && el("i", { class: "fresh", style: `flex:${call.prompt_tokens - cached}` }),
  );
}

function cacheMarker(call, position) {
  if (!call.cached_tokens) return null;
  return el("div", { class: "cache-cut", style: `left:${position(call.cached_tokens)}`, title: `the cache stopped at token ${count(call.cached_tokens)}` });
}

function cacheNumbers(call) {
  if (call.cached_tokens === null) return `${count(call.prompt_tokens)}`;
  return `${count(call.cached_tokens)} cached · ${count(call.prompt_tokens - call.cached_tokens)} read`;
}

function tokenTicks(longest) {
  const step = [100, 250, 500, 1000, 2000, 2500, 5000, 10000].find((candidate) => longest / candidate <= 6) || 20000;
  const ticks = [];
  for (let tick = 0; tick <= longest; tick += step) ticks.push(tick);
  return ticks;
}

function promptLegend(calls) {
  const present = new Set(calls.flatMap((call) => call.segments.map((segment) => segment.kind)));
  const entry = (className, text) => el("span", {}, el("i", { class: className }), text);
  return el(
    "div",
    { class: "legend" },
    SEGMENT_KINDS.filter(([kind]) => present.has(kind)).map(([kind, label]) => entry(`seg-${kind}`, label)),
    entry("cached", "from the cache"),
    entry("fresh", "read fresh"),
  );
}

function verdictLine(call) {
  return el("div", { class: `verdict ${call.verdict}` }, el("span", { class: "verdict-mark", "aria-hidden": "true" }, VERDICT_MARKS[call.verdict]), el("span", { class: "verdict-call" }, `model #${call.number}`), el("span", {}, call.explanation));
}

// The table view of the last call's prompt, which holds every part: the chart's colors are not the only way to read it.
function partsTable(call) {
  const rows = call.segments.map((segment) =>
    el("tr", {}, el("td", {}, el("i", { class: `swatch seg-${segment.kind}` }), segment.label), el("td", { class: "number" }, count(segment.tokens)), el("td", { class: "number" }, `${Math.round((segment.tokens / call.prompt_tokens) * 100)}%`)),
  );
  return el(
    "details",
    { class: "fold" },
    el("summary", {}, `Parts of model #${call.number}'s prompt (${count(call.prompt_tokens)} tokens)`),
    el("table", { class: "parts" }, el("thead", {}, el("tr", {}, el("th", {}, "part"), el("th", { class: "number" }, "tokens"), el("th", { class: "number" }, "share"))), el("tbody", {}, rows)),
  );
}

function segmentTokens(layout, kind) {
  const last = layout.calls[layout.calls.length - 1];
  return count(last.segments.filter((segment) => segment.kind === kind).reduce((total, segment) => total + segment.tokens, 0));
}

function systemPromptFold(layout) {
  return fold(`System prompt (${segmentTokens(layout, "system")} tokens) · the same for every question, so it should always be cached`, layout.system_prompt);
}

function toolsFold(layout) {
  if (!layout.tools.length) return null;
  const rows = layout.tools.map((tool) => el("tr", {}, el("td", {}, tool.name), el("td", { class: "number" }, count(tool.tokens))));
  return el(
    "details",
    { class: "fold" },
    el("summary", {}, `Tool definitions (${segmentTokens(layout, "tools")} tokens for ${layout.tools.length} tools) · sent with every call, in a fixed order`),
    el("table", { class: "parts" }, el("thead", {}, el("tr", {}, el("th", {}, "tool"), el("th", { class: "number" }, "tokens alone"))), el("tbody", {}, rows)),
  );
}

// The memory tools run on the Mac the dashboard runs on, so a page opened from a laptop shows the serving Mac's memory.
async function refreshMemory() {
  try {
    const view = await getJsonOrReason("/api/memory");
    $("machine-memory").replaceChildren(...machineElements(view));
    $("process-memory").replaceChildren(...processElements(view));
    $("process-memory").hidden = false;
  } catch (error) {
    $("machine-memory").replaceChildren(sectionHead("This Mac"), el("div", { class: "note-line" }, String(error.message || error)));
    $("process-memory").hidden = true;
  }
}

function machineElements(view) {
  const machine = view.machine;
  return [sectionHead(machine.name, machine.chip, `${memorySize(machine.total_bytes)} of memory`, "read every 4 s"), setupHeadline(view), machineBar(machine), machineLegend(machine), ...machineNotes(machine)];
}

function setupHeadline(view) {
  const share = Math.round((view.setup_bytes / view.machine.total_bytes) * 100);
  return el("div", { class: "memory-headline" }, el("span", { class: "hero" }, memorySize(view.setup_bytes)), el("span", {}, `taken by the Home Assistant setup, ${share}% of this Mac's ${memorySize(view.machine.total_bytes)}`));
}

function machineBar(machine) {
  return el(
    "div",
    { class: "memory-bar" },
    MACHINE_PARTS.map(([field, className, label, meaning]) => memorySegment(className, machine[field], `${label}: ${memorySize(machine[field])}\n${meaning}`)),
  );
}

function memorySegment(className, bytes, tooltip) {
  const segment = el("i", { class: className, style: `flex:${bytes}` });
  attachTooltip(segment, () => tooltip);
  return segment;
}

function machineLegend(machine) {
  return el(
    "div",
    { class: "legend" },
    MACHINE_PARTS.map(([field, className, label]) => el("span", {}, el("i", { class: className }), `${label} ${memorySize(machine[field])}`)),
  );
}

function machineNotes(machine) {
  return [
    machine.gpu_in_use_bytes !== null && el("div", { class: "note-line" }, `The GPU holds ${memorySize(machine.gpu_in_use_bytes)} of the wired memory, most of it llama-server's model weights.`),
    machine.swap_used_bytes > 0 && el("div", { class: "note-line" }, `Swap: ${memorySize(machine.swap_used_bytes)} of ${memorySize(machine.swap_total_bytes)} written to disk because it did not fit in RAM.`),
  ].filter(Boolean);
}

function processElements(view) {
  const footprints = view.setup_bytes + view.others_bytes;
  return [
    sectionHead("By process", "each process's footprint, the figure Activity Monitor shows"),
    el("p", { class: "panel-lead" }, "A footprint counts what a process has compressed or swapped out, so on a Mac short of memory the footprints add up to more than its RAM. The dashed line marks the RAM."),
    processBar(view, Math.max(footprints, view.machine.total_bytes)),
    processLegend(),
    el("div", { class: "memory-tables" }, setupTable(view), othersTable(view)),
  ];
}

// llama-server's model weights sit next to its footprint, hatched: they are held by the GPU and appear in no process's footprint.
function processBar(view, scale) {
  const position = (bytes) => `${(bytes / scale) * 100}%`;
  const setupSegments = view.setup.flatMap((group) => [
    group.footprint_bytes > 0 && memorySegment("mem-setup", group.footprint_bytes, `${group.name}: ${memorySize(group.footprint_bytes)}, ${processCount(group.processes)}`),
    group.model_weights_bytes > 0 && memorySegment("mem-weights", group.model_weights_bytes, `${group.name}'s model weights: ${memorySize(group.model_weights_bytes)}\nmapped from the model file and held by the GPU`),
  ]);
  const otherSegments = view.others.map((group) => memorySegment("mem-other", group.total_bytes, `${group.name}: ${memorySize(group.total_bytes)}, ${processCount(group.processes)}`));
  return el(
    "div",
    { class: "process-track" },
    el("div", { class: "memory-bar", style: `width:${position(view.setup_bytes + view.others_bytes)}` }, setupSegments, otherSegments),
    el("div", { class: "ram-line", style: `left:${position(view.machine.total_bytes)}` }, el("span", {}, `${memorySize(view.machine.total_bytes)} of RAM`)),
  );
}

function processLegend() {
  const entry = (className, text) => el("span", {}, el("i", { class: className }), text);
  return el("div", { class: "legend" }, entry("mem-setup", "Home Assistant setup"), entry("mem-weights", "model weights, on the GPU"), entry("mem-other", "everything else"));
}

// Every component is listed, running or not, so a service that has stopped shows as stopped rather than vanishing.
function setupTable(view) {
  const rows = view.setup.map((group) =>
    el(
      "tr",
      { class: group.processes ? null : "not-running" },
      el("td", {}, el("i", { class: "swatch mem-setup" }), group.name, group.model_weights_bytes > 0 && el("span", { class: "row-note" }, `${memorySize(group.model_weights_bytes)} of it model weights`)),
      el("td", { class: "number" }, group.processes ? processCount(group.processes) : "not running"),
      el("td", { class: "number" }, group.processes ? memorySize(group.total_bytes) : "–"),
    ),
  );
  return memoryTable(`Home Assistant setup · ${memorySize(view.setup_bytes)}`, "component", rows);
}

function othersTable(view) {
  const rows = view.others.map((group) =>
    el("tr", {}, el("td", {}, el("i", { class: "swatch mem-other" }), group.name), el("td", { class: "number" }, processCount(group.processes)), el("td", { class: "number" }, memorySize(group.total_bytes))),
  );
  return memoryTable(`Everything else · ${memorySize(view.others_bytes)}`, "app", rows);
}

function memoryTable(title, nameHeading, rows) {
  return el(
    "div",
    {},
    el("h3", { class: "table-title" }, title),
    el("table", { class: "parts" }, el("thead", {}, el("tr", {}, el("th", {}, nameHeading), el("th", { class: "number" }, "processes"), el("th", { class: "number" }, "memory"))), el("tbody", {}, rows)),
  );
}

function openSidebar() {
  $("sidebar").classList.add("open");
  $("scrim").hidden = false;
}

function closeSidebar() {
  $("sidebar").classList.remove("open");
  $("scrim").hidden = true;
}

function stepThroughExchanges(event) {
  if (event.key === "Escape") return closeDrawer();
  if (!state.selected || ["SELECT", "INPUT", "TEXTAREA"].includes(event.target.tagName)) return;
  const step = { j: -1, ArrowDown: -1, k: 1, ArrowUp: 1 }[event.key];
  const index = state.selected.index + (step || 0);
  if (step && index >= 0 && index < state.summaries.length) openExchange(state.selected.day, index);
}

$("composer").addEventListener("submit", askQuestion);
$("ask-input").addEventListener("input", fitComposer);
$("ask-input").addEventListener("keydown", sendOnEnter);
$("new-chat").addEventListener("click", startNewChat);
$("sidebar-toggle").addEventListener("click", openSidebar);
$("scrim").addEventListener("click", closeSidebar);
$("drawer-close").addEventListener("click", closeDrawer);
for (const tab of document.querySelectorAll(".tab")) {
  tab.addEventListener("click", () => {
    state.drawerTab = tab.dataset.tab;
    renderDrawer();
  });
}
$("day").addEventListener("change", (event) => openDay(event.target.value));
for (const tab of document.querySelectorAll(".view-tab")) tab.addEventListener("click", () => showView(tab.dataset.view));
document.addEventListener("keydown", stepThroughExchanges);

renderGreeting();
const openingView = location.hash.match(/^#\/(cache|memory)(\/|$)/);
if (openingView) showView(openingView[1]);
poll();
