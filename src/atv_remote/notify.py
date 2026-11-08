"""Opt-in desktop notifications (best effort, never fatal).

This is only used when ``pin_display = "notification"``. The default is the
Qt Quick card; the log and ``atv-remote pin`` are always available.
"""

from __future__ import annotations

import logging
import shutil
import subprocess

_LOGGER = logging.getLogger(__name__)


def available() -> bool:
    """True when ``notify-send`` is on PATH."""
    return shutil.which("notify-send") is not None


def notify(summary: str, body: str = "", *, timeout_ms: int = 0) -> bool:
    """Show a desktop notification.  Returns False if it is unavailable."""
    binary = shutil.which("notify-send")
    if not binary:
        _LOGGER.debug("notify-send not found; skipping notification")
        return False
    command = [binary, "-a", "Apple TV Remote"]
    if timeout_ms > 0:
        command.extend(["-t", str(int(timeout_ms))])
    command.extend([summary, body])
    try:
        subprocess.run(command, check=False, timeout=3, capture_output=True)
        return True
    except (OSError, subprocess.TimeoutExpired) as exc:
        _LOGGER.debug("notify-send failed: %s", exc)
        return False
