"""Copy custom_components/studio_assistant (with a vendored assistant_core) into Home Assistant's config share and restart Home Assistant.

Home Assistant OS exposes /config over SMB once the Samba add-on is running (scripts/ha_setup.py installs it). This script mounts the share,
syncs the component, unmounts, and asks Home Assistant to restart so the new code is loaded.

    uv run python scripts/deploy_component.py            # uses HA_HOST, HA_SAMBA_USER, HA_SAMBA_PASSWORD, HA_TOKEN from .env
    uv run python scripts/deploy_component.py --no-restart
"""

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path

import httpx
from dotenv import load_dotenv

from ops.ha_client import HomeAssistant, wait_for_api

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))  # scripts/ is not a package; make `ops` importable when run as a file
COMPONENT = PROJECT / "custom_components" / "studio_assistant"
CORE = PROJECT / "assistant_core"
VENDOR_EXCLUDE = {"anthropic_client.py", "__pycache__"}


def main() -> None:
    load_dotenv(PROJECT / ".env")
    args = parse_args()
    host = args.host or os.environ["HA_HOST"]
    user = os.environ["HA_SAMBA_USER"]
    password = os.environ["HA_SAMBA_PASSWORD"]
    staged = stage_component()
    mount_point = Path(tempfile.mkdtemp(prefix="ha-config-"))
    try:
        mount(host, user, password, mount_point)
        target = mount_point / "custom_components" / "studio_assistant"
        sync(staged, target)
        print(f"deployed to //{host}/config/custom_components/studio_assistant")
    finally:
        unmount(mount_point)
        shutil.rmtree(staged.parent, ignore_errors=True)
    if not args.no_restart:
        restart_home_assistant(host, os.environ["HA_TOKEN"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deploy the studio_assistant component to Home Assistant.")
    parser.add_argument("--host", help="Home Assistant address; default HA_HOST from .env")
    parser.add_argument("--no-restart", action="store_true", help="copy files but do not restart Home Assistant")
    return parser.parse_args()


def stage_component() -> Path:
    """Build the exact tree that will land in /config: the component plus assistant_core under vendor/."""
    staging = Path(tempfile.mkdtemp(prefix="studio_assistant-")) / "studio_assistant"
    shutil.copytree(COMPONENT, staging, ignore=shutil.ignore_patterns("__pycache__", "vendor"))
    shutil.copytree(CORE, staging / "vendor" / "assistant_core", ignore=shutil.ignore_patterns(*VENDOR_EXCLUDE))
    return staging


def mount(host: str, user: str, password: str, mount_point: Path) -> None:
    url = f"//{urllib.parse.quote(user)}:{urllib.parse.quote(password, safe='')}@{host}/config"
    subprocess.run(["mount_smbfs", url, str(mount_point)], check=True)


def unmount(mount_point: Path) -> None:
    subprocess.run(["umount", str(mount_point)], check=False)
    shutil.rmtree(mount_point, ignore_errors=True)


def sync(source: Path, target: Path) -> None:
    """Replace the deployed tree, keeping the previous one aside until the copy has finished so a failure halfway leaves the old component in place."""
    previous = target.with_name(target.name + ".prev")
    if previous.exists():
        shutil.rmtree(previous)
    if target.exists():
        target.rename(previous)
    try:
        shutil.copytree(source, target)
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        if previous.exists():
            previous.rename(target)
        raise
    if previous.exists():
        shutil.rmtree(previous)


def restart_home_assistant(host: str, token: str) -> None:
    asyncio.run(restart_and_wait(HomeAssistant(host, token, os.environ.get("HA_BASE") or f"http://{host}:8123")))


async def restart_and_wait(ha: HomeAssistant) -> None:
    try:
        await ha.post("/api/services/homeassistant/restart")
    except httpx.RemoteProtocolError:
        pass  # Home Assistant 2026.9 often drops the connection as it shuts down instead of answering the restart call; the restart still happens.
    print("Home Assistant restarting ...", flush=True)
    await asyncio.sleep(5)
    await wait_for_api(ha, timeout_seconds=300, ok_statuses=(200,), poll_seconds=5)
    await ha.close()
    print("Home Assistant back up")


if __name__ == "__main__":
    sys.exit(main())
