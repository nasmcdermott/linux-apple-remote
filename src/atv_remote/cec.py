"""HDMI-CEC integration via the existing cec-policy controller.

Volume, mute and TV-on are delegated to the same `cec-policy` script used by
the Fire TV remote.  That keeps one owner of the CEC adapter and the user's
existing CEC configuration (`/etc/cec-livingroom.conf`, volume target, wake
budget, etc.) authoritative.

`cec-policy` is safe to run as the session user when /dev/cec* is writable
(Fedora's video group / uaccess on this box).  Volume calls are coalesced on a
small worker so a held volume button cannot build a backlog; the TV-on wake is
detached because `powerkey` wake can take up to the configured budget (60 s by
default).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

KNOWN_POLICY_PATHS = (
    "/usr/local/bin/cec-policy",
    "/usr/bin/cec-policy",
    "/usr/local/lib/cec-livingroom/cec-policy",
    str(Path.home() / ".local/bin/cec-policy"),
)


def find_policy(explicit: str = "auto") -> str | None:
    """Resolve the cec-policy script, or None if it is not installed."""
    if explicit and explicit != "auto":
        path = Path(explicit).expanduser()
        return str(path) if path.is_file() and os.access(path, os.X_OK) else None
    for candidate in (shutil.which("cec-policy"), *KNOWN_POLICY_PATHS):
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def cec_adapters() -> list[str]:
    return sorted(str(path) for path in Path("/dev").glob("cec*"))


class _RateLimiter:
    """At most `limit` CEC actions per rolling second (matches the Fire remote)."""

    def __init__(self, limit: int = 8) -> None:
        self.limit = limit
        self._sent: list[float] = []

    def allowed(self) -> bool:
        now = time.monotonic()
        self._sent = [stamp for stamp in self._sent if now - stamp < 1.0]
        if len(self._sent) >= self.limit:
            return False
        self._sent.append(now)
        return True


@dataclass
class CecConfig:
    # CEC is optional hardware/software, so it is opt-in.  Enabling it without
    # cec-policy and a writable /dev/cec* is harmless (the bridge logs a
    # warning and falls back to ordinary keys), but a first install should not
    # depend on it.
    enabled: bool = False
    policy: str = "auto"
    volume: bool = True
    mute: bool = True
    power_on: bool = True
    timeout: int = 15

    def validate(self) -> None:
        self.timeout = max(1, int(self.timeout))
        self.policy = str(self.policy or "auto")


class CecPolicy:
    """Serialized wrapper around `cec-policy volume` plus detached wake."""

    def __init__(self, binary: str, timeout: int = 15) -> None:
        self.binary = binary
        self.timeout = timeout
        # Coalesce volume steps: a held button produces faster requests than
        # cec-policy can execute.  Keep only the newest pending step instead of
        # building a backlog that keeps stepping after the button is released.
        self._pending: str | None = None
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = False
        self._rate = _RateLimiter()
        self._last_wake = 0.0
        self._thread = threading.Thread(target=self._worker, name="cec-policy", daemon=True)
        self._thread.start()
        _LOGGER.info("CEC policy: %s", binary)

    @classmethod
    def from_config(cls, config: CecConfig) -> CecPolicy | None:
        binary = find_policy(config.policy)
        if not binary:
            _LOGGER.warning(
                "CEC enabled but cec-policy was not found (looked on PATH and %s)",
                ", ".join(KNOWN_POLICY_PATHS),
            )
            return None
        adapters = cec_adapters()
        if not adapters:
            _LOGGER.warning("CEC enabled but no /dev/cec* adapter exists; using key output")
            return None
        if not os.access(adapters[0], os.W_OK):
            _LOGGER.warning(
                "CEC enabled but %s is not writable; using key output (add the user to video?)",
                adapters[0],
            )
            return None
        return cls(binary, timeout=config.timeout)

    def volume(self, direction: str) -> bool:
        if direction not in ("up", "down", "mute"):
            return False
        if not self._rate.allowed():
            _LOGGER.warning("CEC volume/%s: rate-guarded", direction)
            return False
        with self._lock:
            self._pending = direction
        self._wake.set()
        return True

    def wake(self) -> bool:
        """Fire the same TV-on sequence as the Fire remote power key."""
        now = time.monotonic()
        if now - self._last_wake < 3.0:
            _LOGGER.info("CEC wake/powerkey: debounced")
            return False
        self._last_wake = now
        try:
            subprocess.Popen(
                [self.binary, "wake", "--reason", "powerkey"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            _LOGGER.info("CEC wake/powerkey: launched")
            return True
        except OSError as exc:
            _LOGGER.warning("CEC wake/powerkey failed: %s", exc)
            return False

    def _worker(self) -> None:
        while True:
            self._wake.wait()
            self._wake.clear()
            if self._stop:
                return
            with self._lock:
                direction = self._pending
                self._pending = None
            if direction is not None:
                self._run_volume(direction)

    def _run_volume(self, direction: str) -> None:
        try:
            result = subprocess.run(
                [self.binary, "volume", direction],
                timeout=self.timeout,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                _LOGGER.warning(
                    "CEC volume/%s failed (rc=%s): %s",
                    direction,
                    result.returncode,
                    (result.stderr or result.stdout).strip(),
                )
            else:
                _LOGGER.info("CEC volume/%s: ok", direction)
        except (OSError, subprocess.TimeoutExpired) as exc:
            _LOGGER.warning("CEC volume/%s failed: %s", direction, exc)

    def close(self) -> None:
        self._stop = True
        self._wake.set()


class CecOutput:
    """Output wrapper: CEC for volume/mute/power, keys for everything else."""

    def __init__(self, inner, policy: CecPolicy, config: CecConfig) -> None:
        self.inner = inner
        self.policy = policy
        self.config = config
        self.name = f"{getattr(inner, 'name', 'output')}+cec"

    @property
    def device_path(self) -> str:
        return getattr(self.inner, "device_path", "")

    def press(self, action: str) -> bool:
        if action in ("volume_up", "volume_down") and self.config.volume:
            return self.policy.volume("up" if action == "volume_up" else "down")
        if action == "mute" and self.config.mute:
            return self.policy.volume("mute")
        if action == "power":
            # KEY_POWER still reaches systemd-logind/Plasma, which shows the
            # sleep/restart/logout/cancel menu exactly like the Fire remote.
            emitted = self.inner.press("power")
            if self.config.power_on:
                self.policy.wake()
            return emitted
        return self.inner.press(action)

    def hold(self, action: str) -> bool:
        # CEC actions are taps; only ordinary keys (e.g. Select) are held.
        return self.inner.hold(action)

    def release(self, action: str) -> bool:
        return self.inner.release(action)

    def close(self) -> None:
        self.policy.close()
        self.inner.close()
