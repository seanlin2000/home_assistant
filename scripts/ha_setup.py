"""Bring a fresh Home Assistant OS instance to the state the design describes, without touching the UI.

Steps (each is skipped when already done, so the script can be re-run):
  1. onboarding: create the owner account, finish the onboarding wizard, mint a long-lived token (saved to .env as HA_TOKEN)
  2. add-ons: Samba (for deploys), Piper (text to speech), Music Assistant, ESPHome (for the puck), openWakeWord (optional server-side wake word)
  3. integrations: Wyoming entries for Whisper and Kokoro on the Mac, confirm the discovered Piper add-on, add studio_assistant
  4. pipeline: an Assist pipeline "Jarvis" using Whisper, studio_assistant, and Piper, set as preferred

    uv run python scripts/ha_setup.py --host 192.168.1.60          # first run
    uv run python scripts/ha_setup.py --host 192.168.1.60 --only pipeline

Credentials: HA_ADMIN_USER / HA_ADMIN_PASSWORD / HA_SAMBA_PASSWORD are read from .env and generated if missing. Everything lives on the LAN.
"""

import argparse
import asyncio
import json
import os
import secrets
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import dotenv_values, load_dotenv

from ops.ha_client import HomeAssistant, entity_id, wait_for_api

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))  # scripts/ is not a package; make `ops` importable when run as a file
ENV_PATH = PROJECT / ".env"
MAC_IP_DEFAULT = "192.168.1.152"
STEPS = ("onboarding", "addons", "integrations", "pipeline")
ADDONS = {
    "core_samba": {"options": None},  # options are filled in at runtime with the generated password
    "core_piper": {
        "options": {"voice": "en_US-lessac-medium", "speaker": 0, "length_scale": 1, "noise_scale": 0.667, "noise_w": 0.333, "max_piper_procs": 1, "update_voices": True, "streaming": True}
    },
    "d5369777_music_assistant": {"options": {"log_level": "info"}},
    "5c53de3b_esphome": {"options": None},
    "core_openwakeword": {"options": {"threshold": 0.5, "trigger_level": 1}},
}
WYOMING_SERVICES = {"whisper": ("Whisper on the Mac", 10300), "kokoro": ("Kokoro on the Mac", 10210)}
PIPELINE_NAME = "Jarvis"


def env_value(name: str, generate: bool = False) -> str:
    values = dotenv_values(ENV_PATH)
    if values.get(name):
        return str(values[name])
    if not generate:
        raise SystemExit(f"{name} missing from .env")
    value = secrets.token_urlsafe(18)
    save_env(name, value)
    return value


def save_env(name: str, value: str) -> None:
    lines = ENV_PATH.read_text().splitlines() if ENV_PATH.exists() else []
    lines = [line for line in lines if not line.startswith(f"{name}=")]
    lines.append(f"{name}={value}")
    ENV_PATH.write_text("\n".join(lines) + "\n")
    ENV_PATH.chmod(0o600)


# ---------------------------------------------------------------- step 1: onboarding


async def onboarding(ha: HomeAssistant, args: argparse.Namespace) -> None:
    existing = dotenv_values(ENV_PATH).get("HA_TOKEN")
    if existing:
        ha.token = existing
        print("onboarding: already done (HA_TOKEN present)")
        return
    steps = await ha.get("/api/onboarding")
    pending = {step["step"] for step in steps if not step["done"]}
    client_id = f"{ha.base}/"
    username = env_value("HA_ADMIN_USER", generate=False) if dotenv_values(ENV_PATH).get("HA_ADMIN_USER") else "sean"
    save_env("HA_ADMIN_USER", username)
    password = env_value("HA_ADMIN_PASSWORD", generate=True)
    if "user" in pending:
        result = await ha.post("/api/onboarding/users", {"client_id": client_id, "name": "Sean", "username": username, "password": password, "language": "en"})
        access = await exchange_code(ha, client_id, result["auth_code"])
    else:
        access = await password_login(ha, client_id, username, password)
    ha.token = access
    if "core_config" in pending:
        await ha.post("/api/onboarding/core_config", {})
    if "analytics" in pending:
        await ha.post("/api/onboarding/analytics", {})
    if "integration" in pending:
        await ha.post("/api/onboarding/integration", {"client_id": client_id, "redirect_uri": f"{client_id}?auth_callback=1"})
    await ha.ws(
        {
            "type": "config/core/update",
            "location_name": "Studio",
            "time_zone": args.time_zone,
            "unit_system": "us_customary",
            "currency": "USD",
            "country": "US",
            "language": "en",
            "latitude": args.latitude,
            "longitude": args.longitude,
        }
    )
    token = await ha.ws({"type": "auth/long_lived_access_token", "client_name": "studio_assistant tooling", "lifespan": 3650})
    save_env("HA_TOKEN", token)
    save_env("HA_HOST", ha.host)
    ha.token = token
    print(f"onboarding: owner '{username}' created, long-lived token saved to .env")


async def exchange_code(ha: HomeAssistant, client_id: str, code: str) -> str:
    response = await ha.http.post("/auth/token", data={"grant_type": "authorization_code", "code": code, "client_id": client_id})
    response.raise_for_status()
    return response.json()["access_token"]


async def password_login(ha: HomeAssistant, client_id: str, username: str, password: str) -> str:
    flow = (await ha.http.post("/auth/login_flow", json={"client_id": client_id, "handler": ["homeassistant", None], "redirect_uri": client_id})).json()
    result = (await ha.http.post(f"/auth/login_flow/{flow['flow_id']}", json={"client_id": client_id, "username": username, "password": password})).json()
    return await exchange_code(ha, client_id, result["result"])


# ---------------------------------------------------------------- step 2: add-ons


async def addons(ha: HomeAssistant, args: argparse.Namespace) -> None:
    await ha.supervisor("post", "/store/reload")
    samba_password = env_value("HA_SAMBA_PASSWORD", generate=True)
    save_env("HA_SAMBA_USER", "homeassistant")
    ADDONS["core_samba"]["options"] = {
        "workgroup": "WORKGROUP",
        "username": "homeassistant",
        "password": samba_password,
        "allow_hosts": ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "fe80::/10"],
        "compatibility_mode": False,
        "veto_files": ["._*", ".DS_Store", "Thumbs.db", "icon?", ".Trashes"],
        "local_master": True,
        "enabled_shares": ["addons", "backup", "config", "media", "share", "ssl"],
    }
    for slug, spec in ADDONS.items():
        await install_addon(ha, slug, spec["options"])


async def install_addon(ha: HomeAssistant, slug: str, options: dict[str, Any] | None) -> None:
    info = await ha.supervisor("get", f"/addons/{slug}/info")
    if info["version"] is None:
        print(f"addons: installing {slug} ...")
        try:
            await ha.supervisor("post", f"/store/addons/{slug}/install")
        except RuntimeError as error:
            # The websocket proxy gives up before a long image pull finishes and reports an empty unknown_error while the Supervisor carries on.
            print(f"addons: install call for {slug} returned {error}; waiting for the Supervisor to finish")
        info = await wait_for_addon(ha, slug)
    else:
        print(f"addons: {slug} already installed ({info['version']})")
    if options is not None:
        # Merge over the add-on's own defaults: add-ons add required options over time (Samba gained network_discovery) and a partial payload is rejected.
        current = (await ha.supervisor("get", f"/addons/{slug}/info")).get("options") or {}
        await ha.supervisor("post", f"/addons/{slug}/options", {"options": {**current, **options}})
    if info["state"] != "started":
        try:
            await ha.supervisor("post", f"/addons/{slug}/start")
        except RuntimeError as error:
            print(f"addons: start call for {slug} returned {error}; waiting for it to come up")
        await wait_for_addon(ha, slug, state="started")
    await ha.supervisor("post", f"/addons/{slug}/options", {"boot": "auto", "watchdog": True})


async def wait_for_addon(ha: HomeAssistant, slug: str, timeout_seconds: int = 900, state: str | None = None) -> dict[str, Any]:
    """Poll until the add-on is installed (version set) and, if asked, in the given state."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        info = await ha.supervisor("get", f"/addons/{slug}/info")
        if info["version"] is not None and (state is None or info["state"] == state):
            return info
        await asyncio.sleep(10)
    raise SystemExit(f"add-on {slug} did not reach {state or 'installed'} within {timeout_seconds}s")


# ---------------------------------------------------------------- step 3: integrations


async def integrations(ha: HomeAssistant, args: argparse.Namespace) -> None:
    entries = await ha.get("/api/config/config_entries/entry")
    entry_ids = {entry["entry_id"] for entry in entries}
    saved = dotenv_values(ENV_PATH)
    for key, (title, port) in WYOMING_SERVICES.items():
        # The Wyoming flow titles the entry after the remote service name and the entry listing hides host and port, so the only reliable
        # rerun check is the entry id we recorded when we created it.
        env_key = f"HA_WYOMING_{key.upper()}_ENTRY"
        if saved.get(env_key) in entry_ids:
            print(f"integrations: wyoming {key} present")
            continue
        created = await run_flow(ha, "wyoming", {"host": args.mac_ip, "port": port}, title)
        save_env(env_key, created["result"]["entry_id"])
    await confirm_discovered_flows(ha)
    if not any(entry["domain"] == "studio_assistant" for entry in entries):
        await run_flow(ha, "studio_assistant", {"ollama_url": f"http://{args.mac_ip}:11434", "model": args.model, "mcp_url": f"http://{args.mac_ip}:8765/mcp"}, "Studio Assistant")
    else:
        print("integrations: studio_assistant present")


async def run_flow(ha: HomeAssistant, handler: str, user_input: dict[str, Any], label: str) -> dict[str, Any]:
    flow = await ha.post("/api/config/config_entries/flow", {"handler": handler})
    result = await ha.post(f"/api/config/config_entries/flow/{flow['flow_id']}", user_input)
    if result.get("type") != "create_entry":
        raise RuntimeError(f"{handler} flow did not create an entry: {json.dumps(result)[:400]}")
    print(f"integrations: added {label}")
    return result


async def confirm_discovered_flows(ha: HomeAssistant) -> None:
    """Add-ons such as Piper and Music Assistant announce themselves; their flows only need a confirmation click."""
    # Flows in progress are only listed over the websocket; REST answers 405 to GET on the flow collection.
    for flow in await ha.ws({"type": "config_entries/flow/progress"}):
        if flow.get("context", {}).get("source") != "hassio":
            continue
        result = await ha.post(f"/api/config/config_entries/flow/{flow['flow_id']}", {})
        print(f"integrations: confirmed discovered {flow['handler']} -> {result.get('type')}")


# ---------------------------------------------------------------- step 4: pipeline


async def pipeline(ha: HomeAssistant, args: argparse.Namespace) -> None:
    pipelines = await ha.ws({"type": "assist_pipeline/pipeline/list"})
    existing = next((item for item in pipelines["pipelines"] if item["name"] == PIPELINE_NAME), None)
    registry = await ha.ws({"type": "config/entity_registry/list"})
    stt = entity_id(registry, "stt", "wyoming", "whisper")
    tts = entity_id(registry, "tts", "wyoming", args.tts)
    agent = entity_id(registry, "conversation", "studio_assistant", "")
    payload = {
        "name": PIPELINE_NAME,
        "language": "en",
        "conversation_engine": agent,
        "conversation_language": "en",
        "stt_engine": stt,
        "stt_language": "en",
        "tts_engine": tts,
        "tts_language": "en_US",  # Piper and Kokoro advertise region codes (en_US, en_GB); a bare "en" is rejected at run time with tts-not-supported
        "tts_voice": None,
        "wake_word_entity": None,
        "wake_word_id": None,
        "prefer_local_intents": True,
    }
    if existing:
        await ha.ws({"type": "assist_pipeline/pipeline/update", "pipeline_id": existing["id"], **payload})
        pipeline_id = existing["id"]
    else:
        created = await ha.ws({"type": "assist_pipeline/pipeline/create", **payload})
        pipeline_id = created["id"]
    await ha.ws({"type": "assist_pipeline/pipeline/set_preferred", "pipeline_id": pipeline_id})
    print(f"pipeline: '{PIPELINE_NAME}' uses {stt} -> {agent} -> {tts} (preferred)")


# ---------------------------------------------------------------- main


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Configure Home Assistant for the studio assistant.")
    parser.add_argument("--host", default=os.environ.get("HA_HOST"), help="Home Assistant address (VM IP or homeassistant.local)")
    parser.add_argument("--mac-ip", default=os.environ.get("MAC_LAN_IP", MAC_IP_DEFAULT), help="LAN address of this Mac, where Ollama, Whisper, Kokoro, and the MCP server listen")
    parser.add_argument("--model", default=os.environ.get("ASSISTANT_MODEL", "gemma4:e4b-it-qat"), help="Ollama model tag for the agent")
    parser.add_argument("--tts", default="piper", choices=["piper", "kokoro"], help="which text-to-speech entity the pipeline uses")
    parser.add_argument("--only", action="append", choices=STEPS, help="run only these steps")
    parser.add_argument("--latitude", type=float, default=40.7484)
    parser.add_argument("--longitude", type=float, default=-73.9857)
    parser.add_argument("--time-zone", default="America/New_York")
    return parser.parse_args()


async def main_async() -> None:
    load_dotenv(ENV_PATH)
    args = parse_args()
    if not args.host:
        raise SystemExit("pass --host or set HA_HOST in .env")
    saved = dotenv_values(ENV_PATH)
    ha = HomeAssistant(args.host, saved.get("HA_TOKEN"), saved.get("HA_BASE"))
    await wait_for_api(ha)
    save_env("HA_BASE", ha.base)
    print(f"Home Assistant API at {ha.base}")
    for name, step in (("onboarding", onboarding), ("addons", addons), ("integrations", integrations), ("pipeline", pipeline)):
        if args.only and name not in args.only:
            continue
        await step(ha, args)
    await ha.close()


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
