# 07. Music and Spotify

## 1. Purpose

"Hey Jarvis, play Radiohead" starts music on a proper speaker within a couple of seconds, with no language model involved. Spotify is the catalog (you have Premium, which programmatic control requires), Music Assistant is the engine that resolves the request and streams it, and the speaker is a Sonos Era 100 SL over Wi-Fi. Your JBL Flip 5 has no wired input, so it can only be used over Bluetooth from the Mac, which is kept as the zero-cost prototype path.

## 2. Diagram

```
  "play Radiohead"
        │
        ▼
  Assist pipeline ── intent matcher ── HassPlayMedia / Music Assistant intent ──▶ Music Assistant (add-on)
                       (no LLM)                                                   │
                                                                                  │ 1. search "Radiohead" in
                                                                                  │    the Spotify provider
                                                                                  │ 2. pick artist radio / top tracks
                                                                                  │ 3. stream to the player
                                                                                  ▼
                        ┌────────────────────── Wi-Fi ───────────────────┐   ┌──────────────┐
                        │                                                 ▼   │ Spotify Web  │
                        │                                        ┌──────────────┐  API (OAuth)│
                        │  production                            │ Sonos Era    │◀────────────┘
                        │                                        │ 100 SL       │  catalog, playback
                        │                                        │ (no mics)    │  state; account-bound
                        │                                        └──────────────┘
                        │
                        │  prototype fallback
                        └──▶ Spotify desktop app on the Mac (a Spotify Connect target)
                                  │ macOS audio output
                                  ▼ Bluetooth
                             JBL Flip 5 (powers off when idle; drops when the Mac sleeps)
```

## 3. How it works, step by step

1. **Spotify authorization, once.** You create a free app in the Spotify developer dashboard, which yields a client id and secret. The Home Assistant Spotify integration uses them for an OAuth login to your Premium account and stores the refresh token locally. Music Assistant's Spotify provider logs in the same way.
2. **Speaker discovery.** The Sonos integration finds the Era 100 SL by mDNS and exposes it as a media player. Music Assistant sees it as a player it can stream to.
3. **A voice command arrives.** The transcript "play Radiohead" matches a media intent before the agent is consulted. Music Assistant receives the request with the target player set to the studio's default.
4. **Resolution.** Music Assistant searches the Spotify provider, applies fuzzy matching (Whisper will sometimes hear "Radio Head"), decides between artist, album, track, or playlist, and queues it.
5. **Playback.** Music Assistant streams to the Sonos over the LAN. Transport commands ("pause", "next", "volume down") are further intents handled the same way.
6. **Talking over music.** The puck's echo cancellation and the Sonos being a separate device mean "Hey Jarvis" still works during playback; Home Assistant can duck the music volume while the assistant speaks.

## 4. Why Sonos Era 100 SL

- Wi-Fi, so it is always reachable and always on. Bluetooth speakers power down when idle and must be paired to exactly one source.
- Native Spotify Connect and native Music Assistant and Home Assistant support.
- The "SL" variant has no microphones, which suits a system whose whole point is that only the puck listens.
- $189, under the $200 you set.
- It can double as a second output for spoken announcements if you ever want louder replies than the puck's small speaker.

Alternatives considered: IKEA Symfonisk (being phased out), a WiiM streamer plus a powered speaker (two boxes), and keeping the Flip 5 (below).

## 5. The Flip 5 path

The Flip 5 has Bluetooth and nothing else. From the Mac it works like this: the Spotify desktop app runs on the Mac and registers as a Spotify Connect target; the Home Assistant Spotify integration or Music Assistant targets it; the Mac's audio output is paired to the Flip 5. It is fine for the prototype. It is not fine for daily voice use because the Flip 5 turns itself off after idling and Bluetooth drops when the Mac sleeps, so "play some music" will sometimes fail until you press a button.

## 6. Packages and components, and what they do for us

| Component | Role in the business logic |
|---|---|
| Spotify Web API and a free developer app | Authorization and catalog access. Premium required for playback control. |
| Home Assistant Spotify integration | OAuth handling, playback state, control of any Connect device on the account. |
| Music Assistant (add-on) | Search, fuzzy matching, queue, streaming to players. Under the hood its Spotify provider uses `librespot`, an open-source Spotify client, to fetch audio. |
| Music Assistant integration | Exposes players to Home Assistant and registers the media intents the voice pipeline uses. |
| Sonos integration | Discovery and control of the Era 100 SL. |
| Sonos Era 100 SL | The speaker. |

## 7. Configuration we control

- Spotify developer app credentials, stored in Home Assistant's secrets and in `secrets/` locally, never in git.
- Music Assistant: default player for voice commands, Spotify as the preferred provider, whether "play X" prefers artist radio or top tracks.
- Volume ducking while the assistant speaks.
- Sonos: fixed IP reservation on the router to keep discovery reliable.

## 8. Failure modes

- **Name misheard.** Fuzzy matching handles most cases; otherwise "did you mean" is a follow-up the agent can ask.
- **Spotify token or credentials invalid.** Re-authenticate from the Home Assistant UI; the developer app itself does not expire.
- **Sonos not found.** Bridged VM networking and a fixed IP.
- **Flip 5 asleep or unpaired.** Expected; that is why it is the prototype path only.
- **Music Assistant update changes intents.** It follows the Home Assistant monthly cycle; test after updates.

## 9. Concepts for newcomers

**Spotify Connect.** Spotify's mechanism for controlling playback on another device from any client. A Sonos speaker or the Spotify desktop app can be a Connect target.

**OAuth.** The login flow where you authorize an application to act on your account without giving it your password. The application gets tokens it refreshes automatically.

**Provider and player.** Music Assistant's two abstractions: a provider is where music comes from (Spotify), a player is where it goes (Sonos).

**Fuzzy matching.** Tolerant string comparison, so "Radio Head" resolves to Radiohead.

**Ducking.** Temporarily lowering music volume while speech plays.

## 10. Sources

- Home Assistant Spotify integration (Premium requirement, developer app setup): [home-assistant.io/integrations/spotify](https://www.home-assistant.io/integrations/spotify/)
- Music Assistant documentation: [music-assistant.io](https://www.music-assistant.io/)
- Sonos Era 100 SL announcement and price: [Tom's Guide](https://www.tomsguide.com/audio/speakers/sonos-launches-two-new-speakers-for-2026-what-you-need-to-know-about-sonos-play-and-era-100-sl), [Sonos newsroom](https://newsroom.sonos.com/262995-sonos-returns-to-the-system-that-built-the-brand-with-two-essential-speakers-for-the-home/)
- JBL Flip 5 has no AUX input: [SoundGuys](https://www.soundguys.com/jbl-flip-5-review-32589/), [TechRadar](https://techradar.com/reviews/jbl-flip-5)
