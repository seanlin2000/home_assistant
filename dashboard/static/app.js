// The exchange dashboard page (design doc v2/13). It polls the day list every two seconds; when the newest day gains an exchange, the list
// refreshes and, while "Open new exchanges" is ticked, the new exchange opens.

const POLL_MS = 2000;
const CONVERSATION_QUIET_MS = 5 * 60 * 1000;
const SHORT_RESULT_CHARS = 600;
const state = { openNextArrival: false, days: [], day: null, summaries: [], selected: null, detail: null, drawerCard: null, drawerTab: "sources" };

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

const seconds = (value) => (value === null || value === undefined ? "–" : `${value.toFixed(value < 10 ? 2 : 1)}s`);
const localTime = (iso) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
const kilo = (chars) => (chars >= 1000 ? `${(chars / 1000).toFixed(1)}k chars` : `${chars} chars`);
const wordsOnly = (text) => text.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
const argumentText = (args) => Object.entries(args).map(([key, value]) => `${key}=${JSON.stringify(value)}`).join(", ");


async function poll() {
  try {
    const [days, latest] = await Promise.all([getJson("/api/days"), getJson("/api/latest")]);
    $("model").textContent = latest ? `model: ${latest.model}` : "";
    setStatus("live", "live");
    await takeDays(days);
  } catch (error) {
    setStatus("down", "dashboard unreachable, retrying");
  }
  setTimeout(poll, POLL_MS);
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
  const fromHash = selectionFromHash();
  if (state.day === null && newest) await openDay(fromHash && days.some((day) => day.day === fromHash.day) ? fromHash.day : newest.day);
  else if (grew && ($("follow").checked || state.openNextArrival)) await openDay(newest.day, { openLatest: true });
  if (grew) state.openNextArrival = false;
  else if (grew && state.day === newest.day) await openDay(newest.day, { keepSelection: true });
}

async function openDay(day, { openLatest = false, keepSelection = false } = {}) {
  const previousCount = state.day === day ? state.summaries.length : null;
  state.day = day;
  state.summaries = await getJson(`/api/days/${day}/exchanges`);
  renderDayPicker();
  renderList(previousCount);
  const fromHash = selectionFromHash();
  if (openLatest || (!keepSelection && !fromHash)) await openExchange(day, state.summaries.length - 1);
  else if (fromHash && !keepSelection && fromHash.day === day) await openExchange(fromHash.day, fromHash.index);
}

function selectionFromHash() {
  const match = location.hash.match(/^#\/(\d{4}-\d{2}-\d{2})\/(\d+)$/);
  return match ? { day: match[1], index: Number(match[2]) } : null;
}

async function openExchange(day, index) {
  if (index < 0) return renderEmpty();
  closeDrawer();
  state.selected = { day, index };
  history.replaceState(null, "", `#/${day}/${index}`);
  renderList();
  state.detail = await getJson(`/api/days/${day}/exchanges/${index}`);
  renderExchange(state.detail);
}

function renderEmpty() {
  $("exchange").replaceChildren(el("p", { class: "empty" }, "No exchanges on this day yet. New ones appear about a second after the answer ends."));
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
  return el(
    "button",
    { class: `row${selected ? " selected" : ""}${fresh ? " fresh" : ""}`, type: "button", onclick: () => openExchange(summary.day, index) },
    el("div", { class: "row-top" }, el("span", {}, localTime(summary.recorded_at)), summary.route && el("span", { class: "pill" }, summary.route), summary.failed && el("span", { class: "flag" }, "⚠"), el("span", { class: "seconds" }, seconds(summary.total_seconds))),
    el("div", { class: "row-text" }, summary.user_text || "(no question)"),
    summary.tools.length > 0 && el("div", { class: "row-tools" }, summary.tools.join(" · ")),
  );
}


function renderExchange(detail) {
  const record = detail.record;
  $("exchange").replaceChildren(
    el("div", { class: "head" }, el("h2", {}, record.user_text || "(no question)"), el("div", { class: "meta" }, metaPills(detail))),
    timingCard(detail),
    conversationCard(detail),
  );
}

function metaPills(detail) {
  const record = detail.record;
  const pills = [
    el("span", { class: "pill" }, localTime(record.recorded_at)),
    el("span", { class: "pill", title: "the model that answered this exchange" }, `model: ${record.model}`),
    el("span", { class: "pill" }, `total ${seconds(record.total_seconds)}`),
    el("span", { class: "pill" }, `first word ${seconds(record.time_to_first_spoken_seconds)}`),
    el("span", { class: "pill" }, `${record.model_calls.length} model calls · ${record.tool_calls.length} tool calls`),
    record.source !== "home_assistant" && el("span", { class: "pill" }, record.source),
    record.untrusted && el("span", { class: "pill warn" }, "read untrusted text"),
  ];
  for (const flag of failureFlags(record)) pills.push(el("span", { class: "pill bad" }, flag));
  return pills;
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


function timingCard(detail) {
  const timeline = detail.timeline;
  const note = [timeline.approximate ? "approximate: this exchange was recorded before steps were timestamped" : "", detail.speech ? "" : "speech timings not available"].filter(Boolean).join(" · ");
  return el("section", { class: "card" }, el("div", { class: "card-title" }, "Timing", note && el("span", { class: "note" }, note)), timelineGrid(timeline), timelineLegend());
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


function conversationCard(detail) {
  const record = detail.record;
  const chat = el("div", { class: "chat" });
  if (detail.earlier_messages.length) chat.append(earlierFold(detail.earlier_messages));
  chat.append(el("div", { class: "bubble user" }, el("span", { class: "who" }, "🎤 question"), record.user_text));
  if (detail.speech && detail.speech.heard && wordsOnly(detail.speech.heard) !== wordsOnly(record.user_text)) chat.append(el("div", { class: "note-line" }, `Whisper heard: “${detail.speech.heard}”`));
  if (record.route) chat.append(el("div", { class: "note-line" }, `router → ${record.route.route}${record.route.also.length ? ` then ${record.route.also.join(", ")}` : ""} (${record.route.source}${record.route.detail ? `: ${record.route.detail}` : ""})`));
  if (detail.filler_text) chat.append(el("div", { class: "bubble agent filler" }, el("span", { class: "who" }, `🔊 filler at ${seconds(record.time_to_first_spoken_seconds)}`), detail.filler_text));
  detail.turns.forEach((turn) => chat.append(...turnElements(turn)));
  chat.append(answerBubble(record));
  const extras = [detail.system_prompt && fold(`System prompt (${detail.system_prompt.length} chars)`, detail.system_prompt), !detail.has_trace && el("div", { class: "note-line" }, "The full tool text for this exchange is gone (no trace kept, or older than 14 days); sizes and times remain.")];
  return el("section", { class: "card" }, el("div", { class: "card-title" }, "Conversation"), chat, ...extras.filter(Boolean));
}

function earlierFold(messages) {
  const shown = messages.filter((message) => message.role === "user" || (message.role === "assistant" && message.content));
  const bubbles = shown.map((message) => el("div", { class: `bubble ${message.role === "user" ? "user" : "agent"} earlier` }, message.content));
  const details = el("details", { class: "fold" }, el("summary", {}, `${shown.length} earlier messages in this conversation`), el("div", { class: "chat" }, bubbles));
  return details;
}

function fold(title, text) {
  return el("details", { class: "fold" }, el("summary", {}, title), el("pre", {}, text));
}

function turnElements(turn) {
  const elements = [];
  if (turn.thinking) elements.push(fold(`💭 thinking (${turn.thinking.split(/\s+/).length} words)`, turn.thinking));
  if (turn.text.trim()) elements.push(el("div", { class: "bubble agent" }, el("span", { class: "who" }, "written beside the tool calls"), turn.text));
  for (const card of turn.tools) elements.push(toolCard(card));
  return elements;
}

function answerBubble(record) {
  if (record.stayed_silent) return el("div", { class: "bubble agent silent" }, el("span", { class: "who" }, "🔇 stayed silent"), "The model judged the speech was not meant for it.");
  return el("div", { class: "bubble agent" }, el("span", { class: "who" }, `🔊 answer from ${record.model} · ${record.spoken_chars} chars spoken`), record.final_answer || "(empty)");
}


function toolCard(card) {
  const badges = [card.refused && el("span", { class: "pill bad" }, "refused"), card.repeated && el("span", { class: "pill warn" }, "repeat"), card.error && el("span", { class: "pill bad" }, card.error)];
  const opens = card.result !== null;
  const head = el(
    "div",
    { class: "tool-head", onclick: opens ? () => openDrawer(card) : undefined, title: opens ? "Open the full text" : undefined },
    el("span", {}, "🔧"),
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


function openDrawer(card) {
  state.drawerCard = card;
  $("drawer").hidden = false;
  $("drawer-title").textContent = `${card.name}(${argumentText(card.arguments)})`;
  renderDrawer();
}

function renderDrawer() {
  const card = state.drawerCard;
  for (const tab of document.querySelectorAll(".tab")) tab.classList.toggle("active", tab.dataset.tab === state.drawerTab);
  const body = $("drawer-body");
  if (state.drawerTab === "raw") return body.replaceChildren(el("pre", { class: "raw" }, card.result));
  const evidence = card.evidence;
  const pattern = termPattern(evidence.terms);
  const terms = el("div", { class: "terms" }, evidence.terms.length ? ["Answer words looked for: ", evidence.terms.map((term) => el("mark", {}, term))] : "The answer has no words the question did not already use.");
  const header = evidence.header && el("div", { class: "tool-header-line" }, evidence.header);
  const footer = evidence.footer && el("div", { class: "tool-header-line" }, `Closing note to the model: ${evidence.footer}`);
  body.replaceChildren(...[terms, header, ...evidence.sources.map((source) => drawerSource(source, pattern)), footer].filter(Boolean));
  body.scrollTop = 0;
}

function drawerSource(source, pattern) {
  const meta = `${source.read ? "" : "snippet only · "}${kilo(source.text.length)} · ${Math.round(source.coverage * 100)}% of the answer's words${source.starred ? " ★" : ""}`;
  const text = el("pre");
  text.innerHTML = highlighted(source.text, pattern);
  return el(
    "div",
    { class: "source" },
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


const chat = { id: newConversationId(), history: [], lastAsked: 0 };

function newConversationId() {
  return `dashboard-${Date.now().toString(36)}`;
}

function startNewConversation() {
  chat.id = newConversationId();
  chat.history = [];
  showLive([el("span", {}, "New conversation.")]);
}

async function askQuestion(event) {
  event.preventDefault();
  const question = $("ask-input").value.trim();
  if (!question) return;
  if (Date.now() - chat.lastAsked > CONVERSATION_QUIET_MS) startNewConversation();
  chat.lastAsked = Date.now();
  $("ask-input").value = "";
  setAsking(true);
  const conversation = [...chat.history, { role: "user", content: question }];
  const answer = await streamAnswer({ conversation_id: chat.id, conversation });
  if (answer !== null) chat.history = [...conversation, { role: "assistant", content: answer }];
  state.openNextArrival = answer !== null;
  setAsking(false);
}

async function streamAnswer(request) {
  const live = { question: question(request), steps: [], answer: "" };
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

const question = (request) => request.conversation[request.conversation.length - 1].content;

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
  if (event.event === "filler") live.steps.push(`🔊 ${event.text}`);
  else if (event.event === "tool_started") live.steps.push(`🔧 ${event.call.name}(${argumentText(event.call.arguments)})`);
  else if (event.event === "tool_finished") live.steps.push(`   done in ${seconds(event.seconds)}${event.error ? ` (${event.error})` : ""}`);
  else if (event.event === "answer") live.answer += event.text;
  else if (event.event === "error") live.error = event.message;
  else if (event.event === "done") live.done = true;
  renderLive(live);
}

function renderLive(live) {
  const lines = [el("div", {}, `🎤 ${live.question}`), ...live.steps.map((step) => el("div", {}, step))];
  if (live.answer) lines.push(el("div", { class: "answer" }, `🔊 ${live.answer}`));
  if (live.error) lines.push(el("div", { class: "error" }, `Not answered: ${live.error}`));
  else if (!live.done) lines.push(el("div", {}, "…"));
  showLive(lines);
}

function showLive(lines) {
  const box = $("ask-live");
  box.hidden = false;
  box.replaceChildren(...lines);
  box.scrollTop = box.scrollHeight;
}

function setAsking(asking) {
  $("ask-send").disabled = asking;
  $("ask-input").disabled = asking;
  if (!asking) $("ask-input").focus();
}

$("ask").addEventListener("submit", askQuestion);
$("ask-new").addEventListener("click", startNewConversation);
$("drawer-close").addEventListener("click", closeDrawer);
for (const tab of document.querySelectorAll(".tab")) {
  tab.addEventListener("click", () => {
    state.drawerTab = tab.dataset.tab;
    renderDrawer();
  });
}
$("day").addEventListener("change", (event) => openDay(event.target.value));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeDrawer();
  if (!state.selected || ["SELECT", "INPUT"].includes(event.target.tagName)) return;
  const step = { j: -1, ArrowDown: -1, k: 1, ArrowUp: 1 }[event.key];
  const index = state.selected.index + (step || 0);
  if (step && index >= 0 && index < state.summaries.length) openExchange(state.selected.day, index);
});

poll();
