"""Tell Home Assistant the voice may have changed, after the voice agent restarts with another engine (scripts/services.sh voice-engine, or a
deploy that changes config/voice.toml).

Home Assistant reads a Wyoming server's description once, when its entry loads, so the entry is reloaded to read the new voice's. It also keeps
every reply it has spoken in a cache keyed by the text and the entity, not the engine behind it, so a fixed reply such as "Turned on the lights"
would go on playing in the old voice; the cache is cleared. The voice is waited for first, so the reload finds it listening.

    .venv/bin/voice handoff
"""

import asyncio
import os
import sys

from dotenv import dotenv_values, load_dotenv

from ops import smoke
from ops.ha_client import HomeAssistant

# scripts/ha_setup.py records the entry it made for the voice's port under this name; the key says kokoro because the entry predates OmniVoice.
VOICE_ENTRY_KEY = "HA_WYOMING_KOKORO_ENTRY"


async def hand_over(ha: HomeAssistant, entry_id: str | None) -> list[str]:
    done = []
    if entry_id:
        await ha.post(f"/api/config/config_entries/entry/{entry_id}/reload")
        done.append(f"reloaded the Wyoming entry {entry_id}")
    await ha.post("/api/services/tts/clear_cache")
    return done + ["cleared the text-to-speech cache"]


async def wait_then_hand_over(ha: HomeAssistant, entry_id: str | None) -> list[str]:
    try:
        label, ok, answer, _ = await smoke.voice_check(smoke.voice_target(smoke.LOCAL_HOST, None), smoke.VOICE_READY_TIMEOUT_SECONDS)
        print(f"voice handoff: {'the voice answers' if ok else 'the voice does NOT answer'}: {answer}", flush=True)
        return await hand_over(ha, entry_id)
    finally:
        await ha.close()


def main() -> int:
    load_dotenv(smoke.PROJECT_DIR / ".env")
    host = os.environ.get("HA_HOST")
    if not host:
        print("voice handoff: HA_HOST is not set in .env; Home Assistant was not told", file=sys.stderr)
        return 1
    entry_id = dotenv_values(smoke.PROJECT_DIR / ".env").get(VOICE_ENTRY_KEY)
    ha = HomeAssistant(host, os.environ.get("HA_TOKEN", ""), os.environ.get("HA_BASE"))
    try:
        done = asyncio.run(wait_then_hand_over(ha, entry_id))
    except Exception as error:  # noqa: BLE001 - reported, and the voice still speaks; Home Assistant just keeps its old description and cache
        print(f"voice handoff: Home Assistant was not told: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    print(f"voice handoff: {'; '.join(done)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
