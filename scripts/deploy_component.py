"""Copy custom_components/studio_assistant (with a vendored assistant_core) into Home Assistant's config share and restart Home Assistant.

Home Assistant OS exposes /config over SMB once the Samba add-on is running (scripts/ha_setup.py installs it). This script mounts the share,
syncs the component, unmounts, and asks Home Assistant to restart so the new code is loaded.

    uv run python scripts/deploy_component.py            # uses HA_HOST, HA_SAMBA_USER, HA_SAMBA_PASSWORD, HA_TOKEN from .env
    uv run python scripts/deploy_component.py --no-restart
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path

import httpx
from dotenv import load_dotenv

PROJECT = Path(__file__).resolve().parent.parent
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
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)


def restart_home_assistant(host: str, token: str) -> None:
    base = os.environ.get("HA_BASE") or f"http://{host}:8123"
    response = httpx.post(f"{base}/api/services/homeassistant/restart", headers={"Authorization": f"Bearer {token}"}, timeout=30)
    response.raise_for_status()
    print("Home Assistant restarting")


if __name__ == "__main__":
    sys.exit(main())
