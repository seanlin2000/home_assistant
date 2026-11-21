// The pronunciation tab: the words a voice says wrong and what it is given instead, one dictionary per (model, voice). It loads before app.js and
// only defines functions, which use app.js's helpers ($, el, sectionHead, plural, getJsonOrReason) once called. Every change names the revision this page last read; one refused because another tab saved first reloads
// the dictionary and says so.

const PRONUNCIATION_SAMPLE = "Xi Jinping met Nikola Jokic at Nvidia.";
const pron = { dictionaries: null, key: null, view: null, draft: { written: "", say_as: "" }, editing: null, confirming: null, filter: "", sentence: PRONUNCIATION_SAMPLE, spoken: "", audio: null };

const pronBase = () => `/api/pronunciations/${pron.key.model}/${pron.key.voice}`;
const pronKeyLabel = (key) => `${key.model[0].toUpperCase()}${key.model.slice(1)} · ${key.voice}${key.speaking ? " (speaking now)" : ""}`;
const isPhonemes = (sayAs) => /^\/.+\/$/.test(sayAs);
const sameWord = (left, right) => left.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase() === right.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase();

async function refreshPronunciation() {
  try {
    pron.dictionaries = pron.dictionaries || (await getJsonOrReason("/api/pronunciations"));
    pron.key = pron.key || pron.dictionaries.find((key) => key.speaking) || pron.dictionaries[0] || null;
    if (pron.key) pron.view = await getJsonOrReason(pronBase());
    renderPronunciation();
  } catch (error) {
    $("pronunciation-page").replaceChildren(el("section", { class: "panel" }, sectionHead("Pronunciation"), el("div", { class: "note-line" }, String(error.message || error))));
  }
}

function renderPronunciation() {
  if (!pron.key) {
    $("pronunciation-page").replaceChildren(el("section", { class: "panel" }, sectionHead("Pronunciation"), el("div", { class: "note-line" }, "No voice has a pronunciation dictionary yet.")));
    return;
  }
  $("pronunciation-page").replaceChildren(el("div", { class: "pron-layout" }, wordsPanel(), el("div", { class: "pron-side" }, sentencePanel(), historyPanel())));
}

// ---- the words

function wordsPanel() {
  const view = pron.view;
  return el(
    "section",
    { class: "panel", "aria-label": "Pronunciation dictionary" },
    el("div", { class: "panel-head" }, el("h2", {}, "Pronunciation"), voicePicker(), el("span", { class: "panel-note" }, `revision ${view.revision} · ${plural(view.entries.length, "word")}`)),
    gitStatus(view),
    addForm(),
    el("div", { id: "pron-error", class: "pron-error", role: "alert" }),
    el("input", { type: "search", class: "pron-search", placeholder: "Find a word", "aria-label": "Find a word", value: pron.filter, oninput: (event) => filterWords(event.target.value) }),
    el("table", { class: "parts pron-table" }, el("thead", {}, el("tr", {}, el("th", {}, "Written"), el("th", {}, "Said as"), el("th", { class: "pron-actions" }, ""))), el("tbody", { id: "pron-rows" }, wordRows())),
  );
}

function voicePicker() {
  if (pron.dictionaries.length < 2) return el("span", { class: "badge" }, pronKeyLabel(pron.key));
  const picker = el(
    "select",
    { class: "pron-picker", "aria-label": "Voice", onchange: (event) => chooseVoice(pron.dictionaries[Number(event.target.value)]) },
    pron.dictionaries.map((key, index) => el("option", { value: index, selected: key.model === pron.key.model && key.voice === pron.key.voice }, pronKeyLabel(key))),
  );
  return picker;
}

function chooseVoice(key) {
  Object.assign(pron, { key, editing: null, confirming: null, filter: "" });
  refreshPronunciation();
}

// The dashboard edits the live copy; git catches up when the laptop runs the pull command and its pull request is merged.
function gitStatus(view) {
  const notes = [];
  if (view.source !== "live") notes.push(el("div", { class: "note-line" }, `The voice reads ${view.source === "git" ? "git's copy" : view.source === "history" ? "the newest saved version" : "no dictionary"} until the first save here.`));
  if (!view.in_git) {
    const gitSide = view.git_revision === null ? "git has no copy" : `git has revision ${view.git_revision}`;
    notes.push(el("div", { class: "pron-banner" }, `Not in git yet: live revision ${view.revision}, ${gitSide}. On the laptop, run `, el("code", {}, "uv run pronunciations pull"), " and merge its pull request."));
  }
  return notes;
}

function addForm() {
  const written = el("input", { id: "pron-written", class: "pron-input", placeholder: "Xi Jinping", value: pron.draft.written, oninput: (event) => (pron.draft.written = event.target.value) });
  const sayAs = el("input", { id: "pron-say-as", class: "pron-input", placeholder: "She Jin Ping", value: pron.draft.say_as, oninput: (event) => (pron.draft.say_as = event.target.value) });
  return el(
    "form",
    { class: "pron-form", onsubmit: addWord },
    el("label", { class: "pron-field" }, el("span", {}, "Written"), written),
    el("label", { class: "pron-field" }, el("span", {}, "Say it as"), sayAs),
    el("div", { class: "pron-buttons" }, playButton("▶ Before", () => ({ text: pron.draft.written, respell: false })), playButton("▶ After", () => ({ text: pron.draft.written, respell: true, candidate: draftEntry() })), el("button", { type: "submit", class: "button primary" }, "Add")),
    el("div", { class: "pron-hint" }, "Respell it the way it sounds. For exact sounds, write phonemes between slashes, like ", el("code", {}, "/ʃˈi ʤˈɪn pˈɪŋ/"), ". Before plays the word as the voice says it now; After, with your spelling."),
  );
}

const draftEntry = () => ({ revision: pron.view.revision, written: pron.draft.written, say_as: pron.draft.say_as });

function wordRows() {
  const shown = pron.view.entries.filter((entry) => !pron.filter || `${entry.written} ${entry.say_as}`.toLowerCase().includes(pron.filter.toLowerCase()));
  if (!shown.length) return el("tr", {}, el("td", { colspan: 3, class: "note-line" }, pron.view.entries.length ? "No word matches." : "No words yet. Add the first one above."));
  return shown.map((entry) => (pron.editing === entry.written ? editingRow(entry) : pron.confirming === entry.written ? confirmingRow(entry) : wordRow(entry)));
}

function wordRow(entry) {
  return el(
    "tr",
    {},
    el("td", {}, entry.written),
    el("td", { class: isPhonemes(entry.say_as) ? "pron-phonemes" : "" }, entry.say_as),
    el(
      "td",
      { class: "pron-actions" },
      playButton("▶", () => ({ text: entry.written, respell: true }), `Hear ${entry.written} as the voice says it now`),
      el("button", { type: "button", class: "button", onclick: () => startEditing(entry.written) }, "Edit"),
      el("button", { type: "button", class: "button", onclick: () => startConfirming(entry.written) }, "Delete"),
    ),
  );
}

function editingRow(entry) {
  const written = el("input", { class: "pron-input", value: entry.written, "aria-label": "Written" });
  const sayAs = el("input", { class: "pron-input", value: entry.say_as, "aria-label": "Say it as" });
  const save = () => changeWord({ written: written.value, say_as: sayAs.value, replaces: entry.written });
  const keys = (event) => (event.key === "Enter" ? save() : event.key === "Escape" ? startEditing(null) : null);
  written.addEventListener("keydown", keys);
  sayAs.addEventListener("keydown", keys);
  return el(
    "tr",
    { class: "pron-editing" },
    el("td", {}, written),
    el("td", {}, sayAs),
    el(
      "td",
      { class: "pron-actions" },
      playButton("▶ After", () => ({ text: written.value, respell: true, candidate: { revision: pron.view.revision, written: written.value, say_as: sayAs.value, replaces: entry.written } })),
      el("button", { type: "button", class: "button primary", onclick: save }, "Save"),
      el("button", { type: "button", class: "button", onclick: () => startEditing(null) }, "Cancel"),
    ),
  );
}

function confirmingRow(entry) {
  return el(
    "tr",
    { class: "pron-confirming" },
    el("td", { colspan: 2 }, `Delete “${entry.written} → ${entry.say_as}”? The voice goes back to its own reading from the next sentence.`),
    el(
      "td",
      { class: "pron-actions" },
      el("button", { type: "button", class: "button danger", onclick: () => deleteWord(entry.written) }, "Delete"),
      el("button", { type: "button", class: "button", onclick: () => startConfirming(null) }, "Cancel"),
    ),
  );
}

function startEditing(written) {
  Object.assign(pron, { editing: written, confirming: null });
  $("pron-rows").replaceChildren(...[wordRows()].flat());
  if (written) $("pron-rows").querySelector(".pron-editing input")?.focus();
}

function startConfirming(written) {
  Object.assign(pron, { confirming: written, editing: null });
  $("pron-rows").replaceChildren(...[wordRows()].flat());
}

function filterWords(text) {
  pron.filter = text;
  $("pron-rows").replaceChildren(...[wordRows()].flat());
}

async function addWord(event) {
  event.preventDefault();
  if (await changeWord({ written: pron.draft.written, say_as: pron.draft.say_as })) {
    pron.draft = { written: "", say_as: "" };
    renderPronunciation();
    $("pron-written").focus();
  }
}

async function changeWord(change) {
  if (!change.written.trim() || !change.say_as.trim()) return showPronunciationError("Fill in both the written form and how to say it.");
  const taken = pron.view.entries.find((entry) => sameWord(entry.written, change.written) && !(change.replaces && sameWord(change.replaces, entry.written)));
  if (taken) return showPronunciationError(`“${taken.written}” is already in the dictionary; edit that entry instead.`);
  return sendChange("PUT", "/entries", change);
}

async function deleteWord(written) {
  return sendChange("DELETE", "/entries", { written });
}

async function restoreVersion(version) {
  return sendChange("POST", "/restore", { version });
}

async function sendChange(method, path, body) {
  try {
    const response = await fetch(`${pronBase()}${path}`, { method, headers: { "content-type": "application/json" }, body: JSON.stringify({ revision: pron.view.revision, ...body }) });
    const answer = await response.json();
    if (response.status === 409) {
      Object.assign(pron, { editing: null, confirming: null });
      await refreshPronunciation();
      return showPronunciationError(answer.error);
    }
    if (!response.ok) return showPronunciationError(answer.error);
    Object.assign(pron, { view: answer, editing: null, confirming: null });
    renderPronunciation();
    return true;
  } catch (error) {
    return showPronunciationError(`The dashboard did not answer: ${error.message || error}`);
  }
}

function showPronunciationError(message) {
  const line = $("pron-error");
  if (line) line.textContent = message;
  return false;
}

// ---- hearing it

function playButton(label, body, title) {
  const button = el("button", { type: "button", class: "button", title: title || label });
  button.textContent = label;
  button.addEventListener("click", () => playPreview(button, body()));
  return button;
}

// The server builds what the voice is given (respelled or not) and returns it as a WAV, with the text it sent in a header.
async function playPreview(button, body) {
  if (!body.text.trim()) return showPronunciationError("Type something to hear first.");
  if (body.candidate && !body.candidate.say_as.trim()) return showPronunciationError("Fill in how to say it first.");
  if (pron.audio) pron.audio.pause();
  const label = button.textContent;
  button.disabled = true;
  button.textContent = "…";
  try {
    const response = await fetch(`${pronBase()}/preview`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
    if (!response.ok) return showPronunciationError((await response.json()).error);
    showPronunciationError("");
    const url = URL.createObjectURL(await response.blob());
    pron.audio = new Audio(url);
    pron.audio.addEventListener("ended", () => URL.revokeObjectURL(url));
    await pron.audio.play();
    return decodeURIComponent(response.headers.get("X-Spoken-Text") || "");
  } catch (error) {
    return showPronunciationError(`Could not play it: ${error.message || error}`);
  } finally {
    button.disabled = false;
    button.textContent = label;
  }
}

function sentencePanel() {
  const sentence = el("textarea", { class: "pron-sentence", rows: 3, "aria-label": "A sentence to hear", oninput: (event) => (pron.sentence = event.target.value) });
  sentence.value = pron.sentence;
  const spoken = el("div", { class: "pron-spoken" }, pron.spoken ? ["The voice is given: ", el("q", {}, pron.spoken)] : "");
  const hear = async (button, respell) => {
    const sent = await playPreview(button, { text: pron.sentence, respell });
    if (typeof sent === "string") {
      pron.spoken = sent;
      spoken.replaceChildren("The voice is given: ", el("q", {}, sent));
    }
  };
  const withDictionary = el("button", { type: "button", class: "button primary" }, "▶ With the dictionary");
  const without = el("button", { type: "button", class: "button" }, "▶ Without it");
  withDictionary.addEventListener("click", () => hear(withDictionary, true));
  without.addEventListener("click", () => hear(without, false));
  return el("section", { class: "panel", "aria-label": "Try a sentence" }, sectionHead("Try a sentence", "every saved word applied, as the voice will hear it"), sentence, el("div", { class: "pron-buttons" }, withDictionary, without), spoken);
}

// ---- history

function historyPanel() {
  const versions = pron.view.history;
  const rows = versions.length
    ? versions.map((version) =>
        el(
          "li",
          { class: "pron-version" },
          el(
            "div",
            { class: "pron-version-head" },
            el("strong", {}, `r${version.revision}`),
            el("span", { class: "panel-note" }, `${new Date(version.saved_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })} · ${plural(version.entries, "word")}`),
            version.revision === pron.view.revision ? el("span", { class: "badge" }, "current") : el("button", { type: "button", class: "button", onclick: () => restoreVersion(version.revision) }, "Restore"),
          ),
          el("ul", { class: "pron-changes" }, version.changes.map((change) => el("li", { class: change.startsWith("−") ? "removed" : change.startsWith("+") ? "added" : "" }, change))),
        ),
      )
    : [el("li", { class: "note-line" }, "No saves yet.")];
  return el("section", { class: "panel", "aria-label": "Saved versions" }, sectionHead("History", "the last 10 saves; a restore is saved as a new revision, so it can be undone too"), el("ol", { class: "pron-history" }, rows));
}
