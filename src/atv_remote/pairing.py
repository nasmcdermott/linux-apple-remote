"""A tiny file-backed pairing window.

The bridge is an Apple TV impersonator: anyone on the LAN who can read the PIN
can pair.  Instead of leaving pairing open forever, the daemon only accepts a
new pair-setup while a timestamp file is fresh.  It is touched at startup, by
``atv-remote pair``, and removed after a successful pairing.

This is intentionally user-space only: no ports, sockets, or system services.
"""

from __future__ import annotations

import os
import time
from pathlib import Path


class PairingGate:
    def __init__(self, path: Path, window_seconds: int) -> None:
        self.path = Path(path)
        self.window_seconds = max(0, int(window_seconds))

    def touch(self) -> None:
        """Open (or extend) the pairing window."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(f"{time.time():.3f}\n", encoding="utf-8")
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    def close(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def allowed(self) -> bool:
        if self.window_seconds <= 0:
            return False
        try:
            age = time.time() - self.path.stat().st_mtime
        except FileNotFoundError:
            return False
        return 0 <= age < self.window_seconds

    def age(self) -> float | None:
        try:
            return max(0.0, time.time() - self.path.stat().st_mtime)
        except FileNotFoundError:
            return None

    def remove_stale_tmp(self) -> None:
        """Best-effort cleanup of an interrupted write (not currently used)."""
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
