# Voice PE firmware with barge-in

`firmware/voice_pe/home-assistant-voice.yaml` is Nabu Casa's Voice Preview Edition config at release 26.9.0
([esphome/home-assistant-voice-pe](https://github.com/esphome/home-assistant-voice-pe/blob/26.9.0/home-assistant-voice.yaml)), with these changes.
Each one is marked `studio-assistant:` in the file.

| Change | Stock 26.9.0 | This build |
|---|---|---|
| Wake word while a request runs or a reply plays | Stops it; you say the wake word again to ask | Stops it, plays the wake chime, and listens for the next request |
| "Stop" while a request runs or a reply plays | Stops it | Unchanged |
| Arming "Stop" for a reply | Gives up if the audio has not started 5 s after the stream is announced | Waits up to 30 s, so slow tool-backed replies can still be stopped |
| `voice_kit` component source | `dev` branch | The 26.9.0 tag |
| Firmware version in Home Assistant | `26.9.0` | `26.9.0-barge-in.1` |
| Wi-Fi setup | Improv over Bluetooth or USB | Improv over USB only |

It is built from the plain config, as ESPHome's "Take control" does, not the factory one. That drops the Bluetooth setup and the
Nabu Casa update entity, so Home Assistant no longer offers stock firmware over this build. Wi-Fi credentials and the API encryption key
are kept in the device's flash and survive an over-the-air update. If the Wi-Fi credentials are ever lost, plug the device into a computer
and set them from <https://esphome.github.io/home-assistant-voice-pe/>.

## Build and flash

ESPHome 2026.6.0 is the version the stock 26.9.0 firmware was built with. `ESPHOME_DATA_DIR` keeps ESPHome's downloads and build
(a few GB, with vendored Python and shell scripts) out of the repo, where the pre-commit checks would scan them.

```
export ESPHOME_DATA_DIR=~/.cache/esphome/voice-pe
uvx --from esphome==2026.6.0 esphome compile firmware/voice_pe/home-assistant-voice.yaml
uvx --from esphome==2026.6.0 esphome upload firmware/voice_pe/home-assistant-voice.yaml --device home-assistant-voice-0a0f56.local
uvx --from esphome==2026.6.0 esphome logs firmware/voice_pe/home-assistant-voice.yaml --device home-assistant-voice-0a0f56.local
```

The device's IP address works in place of the `.local` name.

## Back to stock

Flash the official firmware from <https://esphome.github.io/home-assistant-voice-pe/> over USB. Updating to a newer upstream release
means copying its `home-assistant-voice.yaml` over `firmware/voice_pe/home-assistant-voice.yaml` and reapplying the marked changes.
