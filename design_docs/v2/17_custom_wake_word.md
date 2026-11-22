# 17. Custom wake word: "Hey Rotom"

Status: designed

## 1. Purpose

The assistant gets its own name, Rotom (said ROH-tom), and its own wake word, "Hey Rotom". The puck detects it on its own chip, as it detects "Hey Jarvis" today.

A wake word fails in two ways, and both frustrate people:

- **False wakes.** The puck wakes when nobody asked: the TV, a conversation, a word that sounds close.
- **Missed wakes.** Someone says "Hey Rotom" and nothing happens, so they repeat it louder or give up.

**The bar is the stock "Hey Jarvis" model, measured on the same people in the same room.** It has to work for everyone in the household and for visiting friends and family, whose voices are never recorded. "Hey Jarvis" stays loaded as the fallback until "Hey Rotom" has passed a live trial.

Most people who train a custom microWakeWord model end up with one that wakes too often or misses too often (§3.2). This doc copies, step by step, the recipe that produced the stock models, and adds what that recipe lacked: real voices from this house and audio recorded through the puck itself.

Out of scope:

- Detecting the wake word with speech recognition on the Studio. This was ruled out: the puck would stream every sound in the room all day, and the speech model would compete with the main model for memory bandwidth.
- Renaming the persona, the pipeline, the dashboard, and the docs. That is the last PR, after the wake word has passed its live trial.

## 2. Diagram

```
 OFFLINE, ON THE LAPTOP

 ╭──────────────────────╮              ╭──────────────────────╮              ╭──────────────────────╮              ╭──────────────────────╮
 │    training audio    │              │       training       │ candidate    │     offline test     │ gate A met   │     model files      │
 │ voices and negatives │─────────────▶│ pinned microWakeWord │─────────────▶│  beside Hey Jarvis   │─────────────▶│   committed to git   │
 ╰──────────────────────╯              ╰──────────────────────╯              ╰──────────────────────╯              ╰──────────────────────╯
             ▲                                                                           │
             └───────────────────────────────────────────────────────────────────────────┘ gate A failed: more data or new settings

 ON THE PUCK

 ╭──────────────────────╮              ╭──────────────────────╮              ╭──────────────────────╮
 │    puck firmware     │              │      live trial      │ gate B met   │      rename PR       │
 │   Rotom and Jarvis   │─────────────▶│  two weeks, gate B   │─────────────▶│ Jarvis becomes Rotom │
 ╰──────────────────────╯              ╰──────────────────────╯              ╰──────────────────────╯
                                                   │
                                                   └─▶ gate B failed: false wakes and misses become training audio, back to the top row
```

## 3. How it works, step by step

### 3.1 What made "Hey Jarvis" work

The puck runs Kevin Ahrendt's microWakeWord "Hey Jarvis" model (version 2). It has no model card of its own, but the framework's documentation, its training notebook, its negative datasets, and the stock firmware's comments together give the recipe:

| Step | What the stock models did |
|---|---|
| Wake word samples | Synthetic speech from the Piper sample generator, whose LibriTTS-R model holds 904 speakers and can blend them into new voices |
| Similar-sounding phrases | Generated with openWakeWord's tooling and trained as phrases *not* to wake on |
| Realism | Samples mixed with background sound (FSD50K, the Free Music Archive, WHAM!) and given room echo from the BIRD impulse responses |
| Sounds to ignore | Spectrogram sets published on Hugging Face (`kahrendt/microwakeword`): read speech (LibriSpeech, VOiCES), dinner-party conversation (CHiME-6), and sound with no speech (FMA, FSD50K, WHAM!) |
| Choosing the weights | First keep false wakes per hour on background audio under a target, then maximize detection |
| Testing | False wakes per hour, streaming, on the Dinner Party Corpus (DiPCo); misses on Picovoice's public wake word test set |
| Shipped settings | Probability cutoff 0.97, a detection must hold over 5 consecutive windows, 22,860-byte tensor arena |

**Results.** On Picovoice's test set, "Hey Jarvis" misses no recordings at about 0.12 false wakes per hour, and about 0.7% at about 0.05.

**The stock firmware's own numbers.** The "Wake word sensitivity" select in the Voice PE firmware (26.9.0) sets each model's cutoff and gives the false wakes per hour measured on all units and channels of DiPCo, a corpus of dinner-party conversation:

| Sensitivity | okay_nabu (Dec 2024) | hey_jarvis (v2) | hey_mycroft (v2) |
|---|---|---|---|
| Slightly sensitive (default) | 0.85: 0.000 per hour | 0.97: 0.563 per hour | 0.99: 0.567 per hour |
| Moderately sensitive | 0.69: 0.376 | 0.92: 0.939 | 0.95: 1.502 |
| Very sensitive | 0.56: 0.751 | 0.83: 1.502 | 0.93: 1.878 |

DiPCo is several people talking for hours, close to the worst case for false wakes. **"Hey Jarvis" at its default wakes about once every two hours of dinner-party talk.** The newer okay_nabu model (December 2024, a larger network with a 37,000-byte arena, trained on seven languages) does not wake once at its default. It is the stretch reference: a model of its size runs on the puck.

**The older openWakeWord "Hey Jarvis"** shows the scale a good model takes:

- about 200,000 synthetic clips from two speech engines (WaveGlow on LibriTTS, VITS on VCTK), including blended voices;
- about 31,000 hours of audio to ignore: 10,000 hours each of mixed audio (ACAV100M), Common Voice, and podcasts, and 1,000 hours of music;
- similar-sounding phrases such as "hey jealous";
- a second-stage check, trained on the hardest negatives, that confirms each detection.

### 3.2 Why most custom models fail

**The official notebook is a starting point, not the recipe.** Its own warning says the model it produces "will most likely not be usable". Its defaults, against what the stock models had:

| Setting | Notebook default | What a good model needs |
|---|---|---|
| Wake word samples | 1,000 | Tens of thousands, many speakers and blends, varied speed |
| Similar-sounding phrases | None | Generated on purpose |
| Choosing weights by false wakes per hour | Turned off (`minimization_metric: None`) | On, with a target |
| Training steps | 10,000 at one learning rate | More, in stages |
| SpecAugment | Off | On in later stages |
| Pitch shift | 10% of samples | More, so that higher and lower voices are covered |
| Test samples | The same Piper voices as training | Real recordings, or a different speech engine; the notebook warns that same-engine tests score better than real use |

**What went wrong for others, and the step here that prevents it:**

| Failure reported | Where | Prevented by |
|---|---|---|
| Trained only on synthetic voices, the model woke far too often | HA forum | Real voices (§3.4), household audio as negatives, the false-wake gate (§3.8) |
| A daughter's high voice could not trigger any wake word; stock "Hey Jarvis" struggles with a wife and daughter | HA forum | Held-back higher voices in the test set, voice transforms, a per-speaker floor (§3.8) |
| A hosted trainer gave no control over network size, and the model's arena was too large | Reddit, Aug 2026 | Our own scripted training with a set arena budget (§3.6), and an early compile test (§3.9) |
| Deleting the stock `packages:` line to add a model, losing the stock config | Reddit, Aug 2026 | The model is appended to the stock list through our existing package file (§3.9) |
| `internal: true` hid the model from Home Assistant | HA forum | Left off (§3.9) |
| A GitHub "blob" link failed to compile | HA forum | The model is a local file in the repo (§3.9) |
| Builds broke between ESPHome versions | Reddit, HA forum | ESPHome is pinned at 2026.6.0, as the firmware already is |
| A custom model woke about 0.5 s later than okay_nabu | HA forum | Measured in the live trial (§3.8) |

Nabu Casa's support answered on 19 August 2026 that "there is no official Home Assistant documentation or officially supported workflow for generating custom MicroWakeWord models". This doc is that workflow for one phrase.

### 3.3 The phrase

**Wake on:** "Hey Rotom", said ROH-tom, and the natural relaxed form ROH-tum. Piper is fed respellings until its samples sound right by ear. The notebook's own example spells "computer" as `khum_puter`.

**Don't wake on (generated as negatives, then spoken by real people for the test set):**

- "Rotom" alone, and "Rotom" inside a sentence. The name comes up on TV (the Pokémon anime) and in conversation; only "Hey Rotom" should wake the puck.
- Close sounds: "hey Tom", "rotten", "Rotten Tomatoes", "row Tom", "photo", "Rhoda", "totem", "hey Ron", "hey Rowan".
- The list grows from the live trial (§3.10).

"Hey Rotom" has three syllables, as "Hey Jarvis" does. No published rule ties syllable count to accuracy; each phrase is measured on its own.

### 3.4 Data

All audio lives outside the repo, in `~/Library/Application Support/studio-assistant/wake_word/`. None of it is ever committed (§3.11).

**Wake word samples, synthetic.**

- At least 50,000 Piper clips with the LibriTTS-R generator.
- Speakers held under 800: Piper's README warns that the dataset's last speakers have too few recordings and give artifacts.
- Speaker blends, speeds from 0.75 to 1.3, and varied expressiveness (Piper's noise scales).

**Wake word samples, real.**

- Each household member records "Hey Rotom" through the puck (§3.5):
  - at 1 m, 3 m, and across the room;
  - with the TV off and on;
  - while a reply is playing;
  - fast, slow, quiet, and called out.
- Voice transforms, as SEED does: the WORLD vocoder (pyworld) changes formants and pitch separately, so each take becomes about 20 natural-sounding voices across age and gender. The SEED author reported 98.5% detected at 0.19 false wakes per hour from about 180 samples of this kind; one person tested it, on their own voice.

**Held-back voices, for testing only.**

- Visitors record a set of "Hey Rotom" and "Hey Jarvis" takes through the puck. They are never trained on and never transformed.
- At least one higher voice is among them.
- A second speech engine, for testing only, so the test never shares a voice engine with training:
  - Kokoro's voices;
  - OmniVoice voices designed as children and older adults.

  Both engines are already installed.
- No held-back speaker is ever in training. Household members train the model, so their separate test takes show how well it knows voices it has heard. Only the held-back speakers show how it does with visitors.

**Sounds to ignore.**

- The `kahrendt/microwakeword` sets: about 9.7 GB, CC BY-NC 4.0, which allows non-commercial home use.
- The similar-sounding phrases of §3.3, generated by Piper.
- Several hours of this household: TV, podcasts, music, cooking, conversation, recorded in the room the puck sits in.
- From the live trial on: the audio after each false wake (§3.10).

### 3.5 Hearing what the puck hears

The model must train and test on audio that sounds like what it hears in use. On the puck, sound passes through the XMOS chip (echo cancellation and noise suppression) before the wake word model. The stock 26.9.0 config sets:

| Component | Microphone channels | Gain |
|---|---|---|
| `micro_wake_word` | channel 1 | `gain_factor: 4` |
| `voice_assistant` (the audio sent to Home Assistant) | channels 0 and 1 | none (`auto_gain: 0 dbfs`) |

**Capture.** Home Assistant saves the audio of every Assist run as a WAV file when `assist_pipeline: debug_recording_dir:` is set in its configuration. A recording session:

1. Wake the puck with "Hey Jarvis".
2. Say "Hey Rotom" several times, with pauses. Home Assistant ends each run at 15 seconds.
3. Repeat at each distance and condition in §3.4.

The setting fills the disk if left on, so it is set only for recording sessions.

**To confirm before any recording session:** which channel, and at what level, ends up in Home Assistant's WAV. If it is not channel 1, or the level differs from the ×4 the model sees, a capture-only firmware variant streams channel 1 instead. Training on the wrong channel would teach the model a sound it never hears.

### 3.6 Training

**The environment.**

- microWakeWord at a pinned commit, in a `wake-word` dependency group with its own environment, `.venv-wakeword`. This follows the pattern of the `speech` group and `scripts/speech_env.sh`: a group that conflicts with another gets its own environment.
- Piper sample generator, pyworld, and the training scripts in a new `wake_word/` package.

**Changes from the notebook:**

| Setting | Value |
|---|---|
| `minimization_metric` | `ambient_false_positives_per_hour`, with `target_minimization` at or below Hey Jarvis's measured rate (§3.8) |
| `maximization_metric` | `average_viable_recall`, as in the notebook |
| `negative_class_weight` | Raised from 20 step by step, while the per-speaker floor holds |
| Feature sets | Synthetic, real, and transformed positives as separate sets, each with its own `sampling_weight`. The negatives are the kahrendt sets, the similar-sounding phrases, and household audio, with household audio weighted up. |
| `training_steps`, `learning_rates` | Staged, for example a long run at 0.001 then a shorter one at 0.0001 |
| SpecAugment | On in the later stages |
| PitchShift probability | Raised from 0.1 |
| Network size | No larger than a 37,000-byte tensor arena, which okay_nabu shows the puck can hold |

**The machine.**

- The laptop (M1 Pro, 16 GB), or the Studio only with production stopped. Training never runs beside production.
- Each run's time is measured in the first training PR. Nothing here assumes how long a run takes.

**Every run is recorded:** the training config, the data counts, the pinned commit, and the evaluation results (§3.7). Any model can then be traced back to how it was made.

### 3.7 Offline evaluation

**The harness.** `pymicro-wakeword` (2.5.0) runs a microWakeWord `.tflite` in streaming mode with the same feature front end as the puck. It gives a probability for every 10 ms of audio. The harness:

1. Plays every test file through a model and records each detection at each cutoff, with the puck's 5-window rule.
2. Gives miss rates per speaker, and false wakes per hour per audio set.
3. Draws the curve of miss rate against false wakes per hour, and marks the cutoffs used.

**Check the harness first.** Before scoring any of our models, score the stock `hey_jarvis.tflite` on the puck recordings of people saying "Hey Jarvis". Then compare with how the puck behaves live for the same people. If the harness disagrees with the puck, no offline number can be trusted.

**What it scores:**

| Test set | "Hey Rotom" model | Stock "Hey Jarvis" |
|---|---|---|
| Held-back visitors, through the puck | Misses per speaker | Misses on the same people saying "Hey Jarvis" |
| Household test takes (separate from training takes) | Misses per speaker | Same |
| Kokoro and OmniVoice voices | Misses per voice | Same, from the same voices saying "Hey Jarvis" |
| DiPCo evaluation set | False wakes per hour | Same audio |
| Household audio (held out from training) | False wakes per hour | Same audio |
| Similar-sounding phrases spoken by real people | Count of wakes | Not applicable |

### 3.8 Acceptance gates

**Gate A, offline, before the model is flashed:**

| Measure | Bar |
|---|---|
| Misses, held-back voices overall | No more than Hey Jarvis's + 2 percentage points, on the same people |
| Misses, any single held-back speaker | At least 90% of their takes detected |
| False wakes per hour, DiPCo | No more than Hey Jarvis on the same audio (about 0.56 per hour at its default cutoff, measured again by our harness) |
| False wakes per hour, household audio | No more than Hey Jarvis on the same audio |
| Similar-sounding phrases (§3.3), spoken by real people | Each wakes the model in at most 1 of 20 takes; any phrase that wakes it at all is added as a negative for the next round |

**Gate B, a two-week live trial, with "Hey Jarvis" still loaded:**

| Measure | Bar | How it is counted |
|---|---|---|
| False wakes | At most 1 per day | Home Assistant's pipeline runs, pulled by `ops/pipeline_runs.py`: a "Hey Rotom" wake followed by no speech, or by speech the agent answers with its silent reply |
| Missed wakes | Gate A's rates | A drill on day 1 and day 14: each person says "Hey Rotom" 20 times from three spots, and misses are counted by hand. Misses leave no trace in any log, which is why the drill exists. |
| Delay to the wake chime | No longer than "Hey Jarvis" by ear | Noted during the drill |

Only after Gate B does "Hey Rotom" become the main wake word. Then the rename PR follows.

### 3.9 Firmware

The model goes into `firmware/voice_pe/interruption.yaml`, the package file that holds every change to the stock config (`docs/voice_pe_firmware.md`):

- **The model files.** `firmware/voice_pe/models/hey_rotom.json` and `hey_rotom.tflite`, committed to the repo. The manifest gives the cutoff, a sliding window of 5, and the tensor arena size from training.
- **Appending, not replacing.** A list in our package file is appended to the stock list of the same name, so adding a `micro_wake_word.models` entry keeps okay_nabu, hey_jarvis, hey_mycroft, and stop. The stock `packages:` line stays.
- **Visible in Home Assistant.** No `internal: true`, so the model shows in the device's wake word list.
- **Sensitivity.** The stock "Wake word sensitivity" select sets cutoffs for the three stock models only. An added action on the same select sets three "Hey Rotom" cutoffs, picked from our curve (§3.7) to match "Hey Jarvis"'s false wakes per hour at each level.
- **Two wake words.** Since Home Assistant 2025.10 a satellite can have two wake words, each with its own pipeline. "Hey Rotom" is the first and "Hey Jarvis" the second, both on the same pipeline. One forum user reported a first wake word that stopped responding with two set, so the trial checks both.
- **Version.** The firmware version moves to the next `-interruption` number, so the device page says which build runs.
- **Compile test first.** A placeholder model with the planned arena size is compiled and flashed in the first tooling PR. This shows whether five models fit in the puck's memory and CPU before any real training.

Build and flash use ESPHome 2026.6.0, as `docs/voice_pe_firmware.md` describes.

### 3.10 The retraining loop

- **False wakes.** The puck sends audio only after a wake, so the trigger itself is never captured. What comes after it is: the TV or the conversation that set it off. With `debug_recording_dir` on during the trial, that audio joins the household negatives, and any phrase that keeps waking the puck joins the similar-sounding list.
- **Misses.** A missed take from the drill is re-recorded through the puck, with the speaker's consent, and joins the real positives. A held-back visitor's take never joins training, or the test would no longer measure unknown voices.
- A retrained model goes through Gate A again before it is flashed.

### 3.11 Privacy

- Recordings of the household and visitors never enter git; the repository is public. A `.gitignore` rule covers the `wake_word/` data folders, and recordings live under Application Support.
- Everyone recorded agrees to it, knowing what the recordings are for. A visitor's recordings are deleted when they ask.
- The trained model is committed. It holds network weights, not audio, the same way Nabu Casa publishes "Hey Jarvis".

## 4. Packages and what they do for the business logic

| Package | What it does |
|---|---|
| microWakeWord (pinned commit) | Feature generation, augmentation, training, and conversion to the streaming, quantized `.tflite` the puck runs |
| piper-sample-generator, with the LibriTTS-R generator model | Synthetic "Hey Rotom" samples and similar-sounding phrases, in hundreds of voices and blends |
| `kahrendt/microwakeword` datasets | The sounds to ignore: speech, dinner-party talk, and non-speech, as ready-made spectrograms |
| pyworld | Turns each household take into about 20 voices across age and gender |
| pymicro-wakeword | Runs any microWakeWord model in streaming mode, with the puck's front end, for offline scoring |
| Kokoro, OmniVoice (already installed) | Test voices from engines training never sees |
| ESPHome 2026.6.0 | Builds and flashes the firmware |
| `wake_word/` (ours) | The capture helper, the generation and training scripts, the evaluation harness, and the run records |

The Piper generator model and the kahrendt datasets are downloads, about 10 GB in all. Each is fetched only with the go-ahead at build time.

## 5. Configuration we control

| Where | What |
|---|---|
| `~/Library/Application Support/studio-assistant/wake_word/` | Recordings, generated samples, features, and run records |
| The training config, one file per run | Feature sets with sampling and penalty weights, class weights, steps and learning rates, SpecAugment, and the selection metric and target (§3.6) |
| `firmware/voice_pe/models/hey_rotom.json` | Probability cutoff, sliding window 5, tensor arena size, feature step 10 ms |
| `firmware/voice_pe/interruption.yaml` | The model entry and the three sensitivity cutoffs |
| Home Assistant's `configuration.yaml` | `assist_pipeline: debug_recording_dir:`, set only during recording sessions and the live trial |
| Home Assistant's device page | Wake word 1 "Hey Rotom", wake word 2 "Hey Jarvis", and the sensitivity level |

## 6. Failure modes

| Failure | What happens | What to do |
|---|---|---|
| Trained mostly on synthetic voices | Scores well offline, wakes too often or misses real people | Weight real and transformed takes up; test only on held-back real voices |
| Training audio from the wrong channel or level | The model learns a sound the puck never hears | Confirm the channel (§3.5) before recording |
| A held-back speaker's takes leak into training | The test overstates how well unknown voices work | Keep held-back speakers in their own folder, which the training scripts never read |
| Higher voices missed | Children or some visitors cannot wake it | The per-speaker floor (§3.8), more pitch shift, more transformed voices |
| TV or conversation says "Rotom" | False wakes during shows | "Rotom" alone is a negative; add the show's audio to household negatives |
| The harness disagrees with the puck | Offline numbers mislead | Check the harness on stock "Hey Jarvis" first (§3.7) |
| The model does not fit | Compile or load fails, or the puck slows | Arena budget (§3.6), placeholder compile test (§3.9) |
| Two wake words misbehave | One of them stops responding | Seen once on the forum; the drill checks both, and "Hey Jarvis" alone is one setting away |
| The puck crashes mid-answer | Looks like a missed wake or a dead answer | Check pipeline runs and the puck's history before counting a miss |
| Licence of the negative datasets | CC BY-NC 4.0 | Home use only, which this is |

## 7. Concepts for newcomers

**Wake word model.** A small neural network that listens all the time, on the device, for one phrase. It runs every 30 ms on 40 spectrogram features and gives a probability that the phrase was just said. It never transcribes anything.

**Probability cutoff and sliding window.**

- The model fires when its probability stays above the cutoff for a run of windows: 5 on the puck, about 150 ms.
- A higher cutoff gives fewer false wakes and more misses.
- Cutoffs are stored as a number out of 255, so 0.97 is 247.

**False wakes per hour and miss rate.**

- False wakes per hour: how often the model fires on audio with no wake word, measured on hours of talk and noise.
- Miss rate: the share of real wake words it fails to catch.
- Lowering one raises the other; the curve between them is how two models are compared at the same setting.

**Negatives and similar-sounding phrases.** Audio the model must not wake on. Generic speech and noise teach it the world; phrases that sound like the wake word teach it the fine edge. Most guides agree negatives matter more than positives.

**Room impulse response.** A recording of how a room echoes a click. Applying it to a clean sample makes it sound as if it were said in that room.

**Echo cancellation (XMOS).** The puck's audio chip removes its own speaker's sound from the microphone signal, so it can hear a wake word over its own reply. The wake word model hears audio after this step, which is why training audio is recorded through the puck.

**Held-back speakers.** People whose voices are only ever used for testing. They stand in for visitors the model will never hear in training.

## 8. Sources

- microWakeWord README, training process, and data sources: <https://github.com/OHF-Voice/micro-wake-word>, [documentation/data_sources.md](https://github.com/OHF-Voice/micro-wake-word/blob/main/documentation/data_sources.md)
- microWakeWord training notebook: [notebooks/basic_training_notebook.ipynb](https://github.com/OHF-Voice/micro-wake-word/blob/main/notebooks/basic_training_notebook.ipynb)
- "Hey Jarvis" results on Picovoice's test set: [benchmarks/hey_jarvis_roc_curve.png](https://github.com/OHF-Voice/micro-wake-word/blob/main/benchmarks/hey_jarvis_roc_curve.png)
- Stock model manifests: [hey_jarvis.json](https://github.com/esphome/micro-wake-word-models/blob/main/models/v2/hey_jarvis.json), [okay_nabu 20241226.3 release](https://github.com/kahrendt/microWakeWord/releases/tag/okay_nabu_20241226.3)
- Experimental models trained with the notebook's defaults: <https://github.com/esphome/micro-wake-word-models/tree/main/models/v2/experiments>
- Negative datasets: <https://huggingface.co/datasets/kahrendt/microwakeword>
- Voice PE stock config 26.9.0 (microphone channels, sensitivity cutoffs and DiPCo numbers): <https://github.com/esphome/home-assistant-voice-pe/blob/26.9.0/home-assistant-voice.yaml>
- openWakeWord "Hey Jarvis" model card: <https://github.com/dscripka/openWakeWord/blob/main/docs/models/hey_jarvis.md>
- Piper sample generator: <https://github.com/rhasspy/piper-sample-generator>
- pymicro-wakeword: <https://github.com/OHF-Voice/pymicro-wakeword>
- ESPHome micro_wake_word: <https://esphome.io/components/micro_wake_word.html>
- Home Assistant, two wake words per satellite (2025.10): <https://www.home-assistant.io/blog/2025/10/22/voice-chapter-11>
- Home Assistant, saving Assist audio with `debug_recording_dir`: <https://www.home-assistant.io/voice_control/troubleshooting/>
- SEED, voice transforms from a handful of takes: <https://community.home-assistant.io/t/seed-train-a-custom-wake-word-from-just-a-handful-of-recordings-not-hundreds/1018736>
- HA forum, custom wake words on the Voice PE: <https://community.home-assistant.io/t/home-assistant-voice-pe-custom-wake-words-please/845139>
- Reddit, "Custom Wake Word in 2026" (read through Arctic Shift): <https://www.reddit.com/r/homeassistant/comments/1vkqiwm/custom_wake_word_in_2026/>
- TaterTotterson microWakeWord trainer for Apple Silicon, considered and not used: <https://github.com/TaterTotterson/microWakeWord-Trainer-AppleSilicon>
- Deepgram, negatives matter more than positives: <https://deepgram.com/learn/naively-training-a-wake-word-model-from-scratch>
- How to judge a wake word model by recall and false wakes per hour: <https://dev.to/buguatec/how-to-get-a-wake-word-model-in-2026-3amo>
