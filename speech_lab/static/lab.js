// The speech lab page: records from the microphone as WAV, sends it to the recognizer, and sends voice settings to Qwen3-TTS or OmniVoice.
"use strict";

const byId = (id) => document.getElementById(id);
const state = { catalog: null, recordingBase64: null, referenceBase64: null, recorder: null, lastTranscriptLanguage: null };

// ---------- shared helpers

async function postJson(path, body) {
  const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!response.ok) {
    const problem = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(problem.error || response.statusText);
  }
  return response;
}

function blobToBase64(blob) {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",")[1]);
    reader.readAsDataURL(blob);
  });
}

function numberOf(id) {
  const value = byId(id).value;
  return value === "" ? null : Number(value);
}

function fillSelect(select, values, labels = {}) {
  const previous = select.value;
  select.replaceChildren(...values.map((value) => new Option(labels[value] || value, value)));
  if (values.includes(previous)) select.value = previous;
}

function chips(container, phrases, onPick) {
  container.replaceChildren(...phrases.map((phrase) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip";
    chip.textContent = phrase;
    chip.addEventListener("click", () => onPick(phrase));
    return chip;
  }));
}

// ---------- recording: raw samples from the microphone, written out as 16-bit WAV at the browser's own rate

async function startRecording() {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
  const context = new AudioContext();
  const source = context.createMediaStreamSource(stream);
  const processor = context.createScriptProcessor(4096, 1, 1);
  const pieces = [];
  processor.onaudioprocess = (event) => pieces.push(new Float32Array(event.inputBuffer.getChannelData(0)));
  source.connect(processor);
  processor.connect(context.destination);
  state.recorder = { stream, context, source, processor, pieces, startedAt: performance.now() };
}

async function stopRecording() {
  const { stream, context, source, processor, pieces } = state.recorder;
  processor.disconnect();
  source.disconnect();
  stream.getTracks().forEach((track) => track.stop());
  const sampleRate = context.sampleRate;
  await context.close();
  state.recorder = null;
  return encodeWav(pieces, sampleRate);
}

function encodeWav(pieces, sampleRate) {
  const length = pieces.reduce((total, piece) => total + piece.length, 0);
  const buffer = new ArrayBuffer(44 + length * 2);
  const view = new DataView(buffer);
  const writeText = (offset, text) => [...text].forEach((letter, index) => view.setUint8(offset + index, letter.charCodeAt(0)));
  writeText(0, "RIFF"); view.setUint32(4, 36 + length * 2, true); writeText(8, "WAVE");
  writeText(12, "fmt "); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true); view.setUint32(28, sampleRate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  writeText(36, "data"); view.setUint32(40, length * 2, true);
  let offset = 44;
  for (const piece of pieces) {
    for (const sample of piece) {
      view.setInt16(offset, Math.max(-1, Math.min(1, sample)) * 0x7fff, true);
      offset += 2;
    }
  }
  return new Blob([buffer], { type: "audio/wav" });
}

async function useRecording(blob) {
  state.recordingBase64 = await blobToBase64(blob);
  state.recordingBlob = blob;
  byId("recording").src = URL.createObjectURL(blob);
  byId("recording").hidden = false;
  byId("transcribe").disabled = false;
}

byId("record").addEventListener("click", async () => {
  const button = byId("record");
  if (!state.recorder) {
    try {
      await startRecording();
    } catch (error) {
      byId("record-status").textContent = `Microphone unavailable: ${error.message}`;
      return;
    }
    button.textContent = "■ Stop";
    button.classList.add("recording");
    byId("record-status").textContent = "Recording…";
    return;
  }
  const seconds = ((performance.now() - state.recorder.startedAt) / 1000).toFixed(1);
  const blob = await stopRecording();
  button.textContent = "● Record";
  button.classList.remove("recording");
  byId("record-status").textContent = `${seconds} s recorded`;
  await useRecording(blob);
  await transcribe();
});

byId("audio-file").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (file) await useRecording(file);
});

// ---------- recognizer

async function transcribe() {
  byId("transcribe").disabled = true;
  byId("record-status").textContent = "Transcribing… (the first time also loads the model)";
  try {
    const response = await postJson("/api/transcribe", {
      audio_wav_base64: state.recordingBase64,
      size: byId("asr-size").value,
      language: byId("asr-language").value || null,
      context: byId("asr-context").value,
      temperature: numberOf("asr-temperature"),
      top_p: numberOf("asr-top-p"),
      top_k: numberOf("asr-top-k"),
      min_p: numberOf("asr-min-p"),
      repetition_penalty: numberOf("asr-repetition"),
      max_tokens: numberOf("asr-max-tokens"),
    });
    showTranscript(await response.json());
    byId("record-status").textContent = "";
  } catch (error) {
    byId("record-status").textContent = `Failed: ${error.message}`;
  } finally {
    byId("transcribe").disabled = false;
  }
}

function showTranscript(result) {
  state.lastTranscriptLanguage = result.language;
  byId("transcript").textContent = result.text || "(nothing heard)";
  byId("transcript-stats").textContent =
    `Language: ${result.language || "?"} · ${result.audio_seconds} s of audio in ${result.total_seconds} s` +
    (result.load_seconds ? ` · model loaded in ${result.load_seconds} s` : "") + ` · peak ${result.peak_memory_gib} GiB`;
  byId("transcript-box").hidden = false;
}

byId("transcribe").addEventListener("click", transcribe);

byId("speak-transcript").addEventListener("click", () => {
  byId("text").value = byId("transcript").textContent;
  const language = (state.lastTranscriptLanguage || "").toLowerCase();
  selectIfOffered(byId("language"), language);
  selectIfOffered(byId("omni-language"), { english: "en", chinese: "zh" }[language] || "");
  byId("speak").scrollIntoView({ behavior: "smooth" });
});

function selectIfOffered(select, value) {
  if ([...select.options].some((option) => option.value === value)) select.value = value;
}

byId("use-as-reference").addEventListener("click", async () => {
  if (engine() === "qwen") {
    byId("variant").value = "Base";
    await refreshVoiceModel();
  }
  state.referenceBase64 = state.recordingBase64;
  byId("reference-audio").src = URL.createObjectURL(state.recordingBlob);
  byId("reference-audio").hidden = false;
  byId("reference-text").value = byId("transcript").textContent;
  byId("speak").scrollIntoView({ behavior: "smooth" });
});

// ---------- voice model choice: speakers and languages come from the chosen model's own config

function voiceChoice() {
  return { variant: byId("variant").value, size: byId("size").value, precision: byId("precision").value };
}

async function refreshVoiceModel() {
  const variant = byId("variant").value;
  if (variant === "VoiceDesign") byId("size").value = "1.7B";
  byId("size").querySelector('option[value="0.6B"]').disabled = variant === "VoiceDesign";
  byId("speaker-field").hidden = variant === "VoiceDesign";
  showEngineControls();
  byId("instruct-label").textContent = variant === "VoiceDesign" ? "Describe the voice: accent, age, pitch, mood" : "Style or emotion (optional)";
  chips(byId("instruct-chips"), variant === "VoiceDesign" ? state.catalog.voice_descriptions : state.catalog.style_suggestions, (phrase) => (byId("instruct").value = phrase));
  byId("model-note").textContent = "Reading the model's speakers and languages…";
  try {
    const facts = await (await postJson("/api/voice-model", voiceChoice())).json();
    const labels = Object.fromEntries(Object.entries(facts.dialects).map(([speaker, dialect]) => [speaker, `${speaker} (${dialect.replace("_", " ")})`]));
    fillSelect(byId("speaker"), facts.speakers, labels);
    fillSelect(byId("language"), facts.languages);
    byId("model-note").textContent = `${facts.repo_id}${facts.downloaded ? "" : " · not downloaded yet: the first Speak downloads it (2 to 4 GiB)"}`;
  } catch (error) {
    byId("model-note").textContent = `Could not read the model: ${error.message}`;
  }
}

["variant", "size", "precision"].forEach((id) => byId(id).addEventListener("change", refreshVoiceModel));

// ---------- engine choice: Qwen3-TTS and OmniVoice share the text and the recording to clone, nothing else

function engine() {
  return byId("engine").value;
}

function showEngineControls() {
  const omnivoice = engine() === "omnivoice";
  const variant = byId("variant").value;
  byId("engine-tag").textContent = omnivoice ? "OmniVoice" : "Qwen3-TTS";
  byId("qwen-controls").hidden = omnivoice;
  byId("qwen-settings").hidden = omnivoice;
  byId("omnivoice-controls").hidden = !omnivoice;
  byId("omni-settings").hidden = !omnivoice;
  byId("nonverbal-field").hidden = !omnivoice;
  byId("instruct-field").hidden = omnivoice || variant === "Base";
  byId("reference-field").hidden = !omnivoice && variant !== "Base";
  byId("reference-label").textContent = omnivoice ? "Voice to clone (optional; the attributes above still apply on top)" : "Voice to clone (24 kHz is best)";
}

byId("engine").addEventListener("change", showEngineControls);

function buildAttributePickers() {
  const pickers = Object.entries(state.catalog.omnivoice_attributes).map(([category, values]) => {
    const label = document.createElement("label");
    const select = document.createElement("select");
    select.dataset.category = category;
    select.replaceChildren(new Option("any", ""), ...values.map((value) => new Option(value, value)));
    select.addEventListener("change", composeAttributes);
    label.append(category, select);
    return label;
  });
  byId("omni-attributes").replaceChildren(...pickers);
}

function composeAttributes() {
  const picked = [...byId("omni-attributes").querySelectorAll("select")].map((select) => select.value).filter(Boolean);
  byId("omni-instruct").value = picked.join(", ");
}

function insertAtCursor(textarea, snippet) {
  const { selectionStart, selectionEnd, value } = textarea;
  textarea.value = value.slice(0, selectionStart) + snippet + value.slice(selectionEnd);
  textarea.focus();
  textarea.selectionStart = textarea.selectionEnd = selectionStart + snippet.length;
}

byId("clear-reference").addEventListener("click", () => {
  state.referenceBase64 = null;
  byId("reference-file").value = "";
  byId("reference-audio").hidden = true;
  byId("reference-text").value = "";
});

byId("reference-file").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  state.referenceBase64 = await blobToBase64(file);
  byId("reference-audio").src = URL.createObjectURL(file);
  byId("reference-audio").hidden = false;
});

// ---------- speaker

function speechRequest() {
  const variant = byId("variant").value;
  return {
    ...voiceChoice(),
    text: byId("text").value,
    language: byId("language").value,
    speaker: variant === "VoiceDesign" ? null : byId("speaker").value || null,
    instruct: variant === "Base" ? "" : byId("instruct").value,
    temperature: numberOf("temperature"),
    top_k: numberOf("top-k"),
    top_p: numberOf("top-p"),
    repetition_penalty: numberOf("repetition"),
    max_tokens: numberOf("max-tokens"),
    streaming_interval: numberOf("streaming-interval"),
    streaming_context_size: numberOf("streaming-context"),
    reference_audio_wav_base64: variant === "Base" ? state.referenceBase64 : null,
    reference_text: variant === "Base" && state.referenceBase64 ? byId("reference-text").value : "",
  };
}

function omnivoiceRequest() {
  return {
    text: byId("text").value,
    language: byId("omni-language").value,
    instruct: byId("omni-instruct").value,
    duration_seconds: numberOf("omni-duration"),
    num_steps: numberOf("omni-steps"),
    guidance_scale: numberOf("omni-guidance"),
    class_temperature: numberOf("omni-class-temperature"),
    position_temperature: numberOf("omni-position-temperature"),
    layer_penalty_factor: numberOf("omni-layer-penalty"),
    t_shift: numberOf("omni-t-shift"),
    reference_max_seconds: numberOf("omni-reference-seconds"),
    reference_audio_wav_base64: state.referenceBase64,
    reference_text: state.referenceBase64 ? byId("reference-text").value : "",
  };
}

byId("speak-button").addEventListener("click", async () => {
  const omnivoice = engine() === "omnivoice";
  const request = omnivoice ? omnivoiceRequest() : speechRequest();
  byId("speak-button").disabled = true;
  byId("speak-status").textContent = "Speaking… (the first time also loads the model)";
  try {
    const response = await postJson(omnivoice ? "/api/speak-omnivoice" : "/api/speak", request);
    const stats = JSON.parse(response.headers.get("X-Synthesis-Stats"));
    addClip(await response.blob(), stats, request, omnivoice ? omnivoiceClipTitle(request) : qwenClipTitle(request));
    byId("speak-status").textContent = "";
  } catch (error) {
    byId("speak-status").textContent = `Failed: ${error.message}`;
  } finally {
    byId("speak-button").disabled = false;
  }
});

function qwenClipTitle(request) {
  const voice = request.variant === "VoiceDesign" ? request.instruct : `${request.speaker || "default"}${request.instruct ? ` · “${request.instruct}”` : ""}`;
  const settings = `temp ${request.temperature}, top k ${request.top_k}, top p ${request.top_p}, rep ${request.repetition_penalty}`;
  return { heading: `Qwen3-TTS ${request.variant} ${request.size} ${request.precision} · ${request.language} · ${voice}`, settings };
}

function omnivoiceClipTitle(request) {
  const voice = `${request.instruct || "model's choice"}${request.reference_audio_wav_base64 ? " · cloned" : ""}`;
  const settings = `${request.num_steps} steps, guidance ${request.guidance_scale}, class temp ${request.class_temperature}, position temp ${request.position_temperature}`;
  return { heading: `OmniVoice · ${request.language || "detect"} · ${voice}`, settings };
}

function addClip(blob, stats, request, title) {
  const clip = document.createElement("article");
  clip.className = "clip";
  const heading = document.createElement("p");
  heading.className = "clip-title";
  heading.textContent = title.heading;
  const audio = document.createElement("audio");
  audio.controls = true;
  audio.src = URL.createObjectURL(blob);
  const numbers = document.createElement("p");
  numbers.className = "stats";
  numbers.textContent =
    `First audio ${stats.first_audio_seconds} s · ${stats.audio_seconds} s of speech in ${stats.total_seconds} s` +
    ` (${(stats.audio_seconds / stats.total_seconds).toFixed(1)}× real time)` +
    (stats.load_seconds ? ` · loaded in ${stats.load_seconds} s` : "") + ` · peak ${stats.peak_memory_gib} GiB · ${title.settings}`;
  const text = document.createElement("p");
  text.className = "clip-text";
  text.textContent = request.text;
  clip.append(heading, audio, numbers, text);
  byId("clips").prepend(clip);
  audio.play().catch(() => {});
}

byId("unload").addEventListener("click", async () => {
  await postJson("/api/unload", {});
  byId("speak-status").textContent = "Models unloaded.";
});

// ---------- start

async function start() {
  state.catalog = await (await fetch("/api/catalog")).json();
  fillSelect(byId("asr-language"), ["", ...state.catalog.recognizer_languages], { "": "Detect" });
  const sentences = state.catalog.test_sentences;
  byId("text").value = sentences.English;
  chips(byId("sentence-buttons"), Object.keys(sentences), (name) => {
    byId("text").value = sentences[name];
    selectIfOffered(byId("language"), { English: "english", Chinese: "chinese", Mixed: "chinese" }[name]);
    selectIfOffered(byId("omni-language"), { English: "en", Chinese: "zh", Mixed: "zh" }[name]);
  });
  const omnivoiceLanguages = state.catalog.omnivoice_languages;
  fillSelect(byId("omni-language"), Object.keys(omnivoiceLanguages), Object.fromEntries(Object.entries(omnivoiceLanguages).map(([code, name]) => [code, code ? `${name} (${code})` : "Detect"])));
  buildAttributePickers();
  chips(byId("nonverbal-chips"), state.catalog.omnivoice_nonverbal_tags, (tag) => insertAtCursor(byId("text"), tag));
  await refreshVoiceModel();
}

start();
