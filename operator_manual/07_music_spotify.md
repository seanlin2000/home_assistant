# Music
<!-- complexity: packages=2 parts=2 concepts=2 tier=standard -->

This page covers how "Hey Jarvis, play Radiohead" turns into music on a speaker, through Home Assistant's built-in media commands and the Music Assistant add-on. No language model is involved: the sentence matches a fixed pattern and never reaches the [conversation agent](04_conversation_agent.md). Today Music Assistant runs inside the Home Assistant virtual machine, but the two ends are missing: Spotify is not authorised, and there is no network speaker, so nothing plays yet.

## Where this fits

```mermaid
flowchart TB
--8<-- "_includes/system_map.mmd"
class ma,sonos,spotify current
```

## Key definitions

| Term | Meaning |
|---|---|
| Provider and player | Music Assistant's two abstractions: a provider is where music comes from (Spotify), a player is where it goes (Sonos). |
| Spotify Connect | Spotify's mechanism for controlling playback on another device from any client. |
| OAuth | The login flow where you authorise an application to act on your account without giving it your password. |
| Fuzzy matching | Tolerant string comparison, so "Radio Head" resolves to Radiohead. |

## Packages and tools

| Tool | What it is | How this part uses it |
|---|---|---|
| Music Assistant add-on 2.10.2 | An open-source music library and streaming engine that runs as a Home Assistant add-on | Installed by `scripts/ha_setup.py`; searches Spotify, resolves the name, and streams the audio |
| Music Assistant integration | The Home Assistant side of the add-on, which exposes players as media player entities and registers media intents | Confirmed by `scripts/ha_setup.py`; carries a matched "play" command to the add-on |
| Spotify Web API and a developer app | Spotify's programming interface, reached with a free developer app's client id and secret; playback needs Premium | The provider, once the Spotify integration and Music Assistant each log in with OAuth |
| Sonos integration | Home Assistant's connector for Sonos speakers, which it finds on the network by mDNS | Turns the speaker into a media player entity that Music Assistant can stream to |
| Sonos Era 100 SL | A Wi-Fi speaker with no microphones | The planned player: always on and always reachable, unlike a Bluetooth speaker |
| Assist pipeline, `prefer_local_intents` | The Jarvis pipeline's setting that tries the built-in sentence patterns before the conversation agent | `scripts/ha_setup.py` sets it to `true`, so music commands never wait for the language model |

## How it works

### The path

1. The intent matcher in Home Assistant matches "play Radiohead" against one of its media sentence patterns.
2. Home Assistant hands the resulting intent to Music Assistant, with the studio's default player as the target.
3. Music Assistant searches its Spotify provider and resolves the name, so a misheard "Radio Head" still finds the artist.
4. Music Assistant streams the audio to the speaker over the local network, so the speaker never talks to Spotify itself.

A sentence that no pattern matches, such as "what did Radiohead release last year", goes to the [conversation agent](04_conversation_agent.md) instead.

### What this repository sets up

No Python in this repository handles music. `scripts/ha_setup.py` installs Music Assistant with the other add-ons, and its integrations step confirms the Music Assistant integration the add-on announces. `install_addon` installs, configures, and starts each add-on, skipping what is already done, and turns on start at boot and the Supervisor's watchdog:

*From `scripts/ha_setup.py`, `ADDONS` and `install_addon`:*

```python
ADDONS = {
    ...
    "d5369777_music_assistant": {"options": {"log_level": "info"}},
    ...
}
...
async def install_addon(ha: HomeAssistant, slug: str, options: dict[str, Any] | None) -> None:
    info = await ha.supervisor("get", f"/addons/{slug}/info")
    if info["version"] is None:
        print(f"addons: installing {slug} ...")
        ...
    else:
        print(f"addons: {slug} already installed ({info['version']})")
    ...
    if info["state"] != "started":
        ...
    await ha.supervisor("post", f"/addons/{slug}/options", {"boot": "auto", "watchdog": True})
```

The other piece is `"prefer_local_intents": True` in the Jarvis pipeline payload, which puts the intent matcher in front of our agent; [Assist pipeline and intent matcher](06_home_assistant_core.md#assist-pipeline-and-intent-matcher) shows the full payload.

### What is still missing

| End | State today | How to connect it |
|---|---|---|
| Spotify | Not authorised: no Spotify integration and no Spotify provider in Music Assistant | Create a free app in Spotify's developer dashboard, then log in with its client id and secret through the Spotify integration and Music Assistant's Spotify provider |
| Speaker | No network speaker on the Wi-Fi, so Music Assistant has no player | Put a Sonos speaker on the Wi-Fi, confirm the discovered Sonos integration, and make it Music Assistant's default player |

## Run it yourself

Start the virtual machine as in [Home Assistant](06_home_assistant_core.md#run-it-yourself) and open Home Assistant in a browser.

1. **Check the add-on.** Settings → Add-ons → Music Assistant shows it started, with "Start on boot" and "Watchdog" on.
2. **Check the integration.** Settings → Devices & services lists Music Assistant. Spotify and Sonos are not there yet.
3. **Check the pipeline.** Settings → Voice assistants → Jarvis has "Prefer handling commands locally" on.

Rerunning the add-on step, with `.env` loaded, reapplies the same settings and installs nothing:

```bash
uv run python scripts/ha_setup.py --only addons
```

Among its output you see `addons: d5369777_music_assistant already installed (2.10.2)`.

To connect the two ends:

1. **Create the Spotify app.** In Spotify's developer dashboard, create a free app and note its client id and secret.
2. **Add the Spotify integration.** Settings → Devices & services → Add integration → Spotify. Enter the client id and secret and finish the OAuth login with your Premium account.
3. **Add the Spotify provider.** In Music Assistant's panel, add Spotify under providers and log in the same way.
4. **Confirm the speaker.** Once a Sonos speaker is on the Wi-Fi, the Sonos integration appears in the discovered list on Settings → Devices & services; confirm it.
5. **Play.** Music Assistant now lists the speaker under players, and "play Radiohead" in the Assist window starts music.

Until a network speaker exists, the Spotify desktop app on the Mac can act as a Spotify Connect target with the Mac's audio sent to the JBL Flip 5 over Bluetooth, which fails for daily use because the Flip 5 powers off when idle and Bluetooth drops when the Mac sleeps.

## Where to look in the code

| Path | What you find there |
|---|---|
| [`scripts/ha_setup.py`](https://github.com/seanlin2000/home_assistant/blob/main/scripts/ha_setup.py) | The `ADDONS` table with the Music Assistant slug and options, `install_addon`, `confirm_discovered_flows` for add-ons that announce themselves, and the pipeline payload with `prefer_local_intents` |
| [`docs/VERSIONS.md`](https://github.com/seanlin2000/home_assistant/blob/main/docs/VERSIONS.md) | The add-on versions of record |
| [`design_docs/v1/07_music_spotify.md`](https://github.com/seanlin2000/home_assistant/blob/main/design_docs/v1/07_music_spotify.md) | The reasoning behind the speaker choice and the configuration the project intends to control |

## Further reading

- Design doc: [07_music_spotify.md](https://github.com/seanlin2000/home_assistant/blob/main/design_docs/v1/07_music_spotify.md), for the speaker alternatives that were weighed and the failure modes
- [Music Assistant documentation](https://www.music-assistant.io/), for providers, players, and the voice intents it registers
- [Home Assistant Spotify integration](https://www.home-assistant.io/integrations/spotify/), for the developer app setup and the Premium requirement
- [Sonos Era 100 SL](https://newsroom.sonos.com/262995-sonos-returns-to-the-system-that-built-the-brand-with-two-essential-speakers-for-the-home/), the speaker the design settles on
