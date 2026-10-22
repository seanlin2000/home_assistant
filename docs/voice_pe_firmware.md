# Voice PE firmware with interruption

The firmware is two files in `firmware/voice_pe/`:

- `home-assistant-voice.yaml` is Nabu Casa's Voice Preview Edition config at release 26.9.0
  ([esphome/home-assistant-voice-pe](https://github.com/esphome/home-assistant-voice-pe/blob/26.9.0/home-assistant-voice.yaml)),
  byte for byte. It is never edited here.
- `interruption.yaml` is what gets built. It includes the stock config as an ESPHome package and holds every change, so reading it is
  reading the whole difference from stock.

| Change | Stock 26.9.0 | This build |
|---|---|---|
| Wake word while a request runs or a reply plays | Stops it; you say the wake word again to ask | Stops it, plays the wake chime, and listens for the next request |
| "Stop" while a request runs or a reply plays | Stops it | Unchanged |
| `voice_kit` component source | `dev` branch | The 26.9.0 tag |
| Firmware version in Home Assistant | `26.9.0` | `26.9.0-interruption.1` |
| Firmware updates | Home Assistant offers each Nabu Casa release | None; an upstream release is brought in by hand |

The interruption only adds to the stock wake word handler. An action that runs before it records whether the wake word interrupted the
assistant, the stock handler stops the request or reply as it always has, and an action after it starts listening again.

Nabu Casa's shipped firmware is built from a factory config that adds Wi-Fi setup over Bluetooth and USB (Improv) and the Nabu Casa
update entity on top of the stock config. The Wi-Fi setup is copied in, so a phone can still set up the device over Bluetooth after
pressing the center button. The update entity is left out: installing a stock release would replace this build and lose the interruption.
Wi-Fi credentials and the API encryption key are kept in the device's flash and survive an over-the-air update.

## How the packages merge

ESPHome merges the stock config into `interruption.yaml` before validating. Two rules decide how each change is written:

- A list in `interruption.yaml` is appended to the stock list of the same name. The `before_stock` package is declared ahead of the
  stock config, so its actions run first; the factory config uses the same trick.
- A single mapping replaces a stock list, which is how `external_components` swaps the `dev` branch for the 26.9.0 tag.

`esphome config firmware/voice_pe/interruption.yaml` prints the merged result.

## Build and flash

ESPHome 2026.6.0 is the version the stock 26.9.0 firmware was built with. `ESPHOME_DATA_DIR` keeps ESPHome's downloads and build
(a few GB, with vendored Python and shell scripts) out of the repo, where the pre-commit checks would scan them.

```
export ESPHOME_DATA_DIR=~/.cache/esphome/voice-pe
uvx --from esphome==2026.6.0 esphome compile firmware/voice_pe/interruption.yaml
uvx --from esphome==2026.6.0 esphome upload firmware/voice_pe/interruption.yaml --device home-assistant-voice-0a0f56.local
uvx --from esphome==2026.6.0 esphome logs firmware/voice_pe/interruption.yaml --device home-assistant-voice-0a0f56.local
```

The device's IP address works in place of the `.local` name.

## Taking a new upstream release

1. Replace `home-assistant-voice.yaml` with the release's file, unchanged, and build with the ESPHome version its `min_version` names.
2. Point `external_components` at the new tag and bump `version` in `interruption.yaml`.
3. A compile error naming an id (`master_mute_switch`, `timer_ringing`, `external_media_player`, `wake_sound`, `play_sound`,
   `improv_ble_in_progress`, `control_leds`) means upstream renamed something `interruption.yaml` uses.

## Back to stock

Flash the official firmware from <https://esphome.github.io/home-assistant-voice-pe/> over USB.
