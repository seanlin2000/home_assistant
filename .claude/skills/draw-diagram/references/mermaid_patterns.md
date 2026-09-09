# Mermaid patterns

The exact text for each kind of diagram, and what makes the layout engine keep the layers. Flowcharts are laid out by ELK with `NETWORK_SIMPLEX` placement and a fixed light theme from `diagrams/mermaid_config.json`; `diagrams/polish.py` then stretches every subgraph into a band and rounds every corner.

## Layered flowchart

```
flowchart TB
--8<-- "_includes/palette.mmd"
subgraph clients["Who starts a request"]
  puck("Voice PE puck")
end
subgraph ha["Home Assistant"]
  stt("1. speech to text stage")
  tts("2. text to speech stage")
end
subgraph services["Services on the Mac"]
  whisper("Whisper")
  kokoro("Kokoro")
end
puck <-- "audio in, reply out" --> stt
stt -- "audio" --> whisper
tts -- "sentences" --> kokoro
class puck hw
class stt,tts,whisper,kokoro third
```

What keeps ELK honest:

- **One subgraph per layer, all siblings, declared in reading order.** Top row first in `TB`, left column first in `LR`. A nested subgraph or a loose node lets the engine scatter boxes, and the band post-processing then leaves the drawing alone.
- **Edges only cross layers, and only in the reading direction.** An edge inside a layer, or one pointing back, makes ELK invent a new layer. Two boxes in one layer that talk to each other get numbered labels ("1. speech to text stage", "2. intent matcher") or their own diagram. A reply is drawn on the forward edge as `a <-- "request, reply" --> b`; Mermaid has no arrow with a head only at the start.
- **A box goes in the layer of what calls it.** The Sonos speaker sits beside the Mac's services because Home Assistant calls it; the puck sits on top because it starts the request.
- **Let ELK order boxes inside a layer.** Crossing minimisation puts each target under its source; declare nodes in a sensible order because ties break on declaration order.
- **Titles fit on one line** at the width the drawing will have. A title that wraps or that sits over an edge fails rule 5.
- **Left-to-right diagrams keep edge labels to one to three words** and column titles no wider than the widest box in the column. ELK widens the gap between rows to fit a label but not the gap between columns, so a long label in `LR` lands on the neighbouring column and its title. Anything that needs long labels is drawn `TB`, or the words move into the boxes.

## Decision flowchart

```
flowchart TB
--8<-- "_includes/palette.mmd"
question(["the user's latest message"]) --> explicit{"an explicit request to search?"}
explicit -- "yes" --> search("search")
explicit -- "no" --> stale{"could the answer have changed recently?"}
stale -- "yes" --> search
stale -- "no" --> answer("answer from the model")
class search,answer ours
```

No subgraphs. Each decision is its own row, every outcome edge points down and is labelled, and the terminal boxes sit in the bottom row. A "try again" loop that would point back up is drawn as a terminal box saying what happens next ("next candidate").

## Sequence diagram

```
sequenceDiagram
  box rgb(220,252,231) Devices
    participant puck as Voice PE puck
  end
  box rgb(241,245,249) Third-party
    participant ha as Home Assistant
  end
  box rgb(219,234,254) Our code
    participant agent as conversation agent
  end
  puck->>ha: audio
  ha->>agent: text
  agent-->>ha: sentences
  ha-->>puck: audio
```

Order participants left to right in the direction the first request travels. Group them with `box rgb(...)` using the palette fills: `rgb(219,234,254)` ours, `rgb(241,245,249)` third-party, `rgb(220,252,231)` devices, `rgb(254,226,226)` leaves the apartment. At most six participants and about fourteen messages; a longer exchange splits by phase. Notes are one short line with no `;`, and no participant is named `loop`, `end`, `opt`, `alt`, or `par`.

## State diagram

```
stateDiagram-v2
  [*] --> healthy
  healthy --> failing: probe fails
  failing --> healthy: probe passes
  failing --> restarted: three failures
  restarted --> healthy
```

Only when a thing really has states, and at most six of them.

## Syntax rules

- Always double-quote labels so colons, parentheses, and `+` never break the parser; `<br/>` for a line break; at most three short lines.
- Subgraph titles use square brackets, `subgraph id["Title"]`; that is the one place square brackets remain.
- Node ids never start with a digit and are reused when two diagrams show the same thing (`puck`, `stt`, `agent`, `ollama`, `mcp`, `searxng`, `sonos`, `laptop`, `health`).
- No `%%{init}%%`, no `@{ shape: ... }`, no `direction` inside a subgraph, no colours outside the palette.
