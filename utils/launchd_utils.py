"""Asking launchd to run one of this project's agents now, from code that is not that agent."""

import os
import shutil
import subprocess

from ops import paths


def wake_agent(name: str) -> None:
    """Asks launchd to start the agent and returns at once, without waiting for it to run. An agent that is already running is left to finish;
    one that is not installed (the laptop, a test) makes launchctl fail quietly."""
    if shutil.which("launchctl") is None:
        return
    target = f"gui/{os.getuid()}/{paths.LAUNCHD_PREFIX}.{name}"
    subprocess.Popen(["launchctl", "kickstart", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
