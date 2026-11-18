"""Secrets in the macOS Keychain, read with the `security` tool. The tool stored them and so reads them back without the access dialog that would
stall an unattended launchd run (design doc v2/14 section 3.8). Every reader answers None, or False, when the item is missing, the Keychain is locked,
or this is not a Mac."""

import re
import shutil
import subprocess

ACCOUNT_ATTRIBUTE = re.compile(r'^\s*"acct"<blob>="(.*)"\s*$', re.MULTILINE)


def keychain_secret(service: str, account: str) -> str | None:
    found = find_generic_password(["-s", service, "-a", account, "-w"])
    if found is None or found.returncode != 0:
        return None
    return found.stdout.strip() or None


def keychain_item_stored(service: str, account: str) -> bool:
    """Asked without reading the secret: unlike reading it, this works from an SSH session too."""
    found = find_generic_password(["-s", service, "-a", account])
    return found is not None and found.returncode == 0


def keychain_account(service: str) -> str | None:
    """The account the item was stored under, such as the Gmail address the newsletters are read from, so the address lives only in the Keychain."""
    found = find_generic_password(["-s", service])
    if found is None or found.returncode != 0:
        return None
    return account_from_attributes(found.stdout)


def account_from_attributes(attributes: str) -> str | None:
    match = ACCOUNT_ATTRIBUTE.search(attributes)
    return match.group(1) if match else None


def find_generic_password(arguments: list[str]) -> subprocess.CompletedProcess[str] | None:
    if shutil.which("security") is None:
        return None
    return subprocess.run(["security", "find-generic-password", *arguments], capture_output=True, text=True)
