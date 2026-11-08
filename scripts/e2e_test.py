#!/usr/bin/env python3
"""End-to-end smoke test without an iPhone.

Starts the real ``atv-remote`` CLI as a subprocess with the uinput backend,
pairs to it with pyatv's Companion client (the same protocol the iPhone
speaks), sends D-pad/Select/PlayPause, and asserts that the virtual keyboard
emitted the expected Linux key events.

Usage:
    .venv/bin/python scripts/e2e_test.py
    .venv/bin/python scripts/e2e_test.py --port 47833 --keep
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import select
import signal
import subprocess
import sys
import tempfile
import threading
import time
from ipaddress import IPv4Address
from pathlib import Path

import pyatv
from evdev import InputDevice, ecodes, list_devices
from pyatv.conf import AppleTV, ManualService
from pyatv.const import Protocol

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / ".venv" / "bin" / "atv-remote"
DEVICE_NAME = "Apple TV Remote Bridge E2E"


def read_until(proc: subprocess.Popen, marker: str, timeout: float = 15.0) -> str:
    end = time.time() + timeout
    while time.time() < end:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                raise RuntimeError(f"server exited with {proc.returncode}")
            continue
        print("server:", line, end="", flush=True)
        if marker in line:
            return line
    raise TimeoutError(f"timed out waiting for {marker!r}")


def find_device(timeout: float = 5.0) -> str:
    end = time.time() + timeout
    while time.time() < end:
        for path in list_devices():
            device = InputDevice(path)
            try:
                if device.name == DEVICE_NAME:
                    return path
            finally:
                device.close()
        time.sleep(0.1)
    raise RuntimeError(f"virtual device {DEVICE_NAME!r} not found")


def collect_events(path: str, seconds: float = 8.0) -> tuple[InputDevice, list[tuple[int, int, int]]]:
    device = InputDevice(path)
    events: list[tuple[int, int, int]] = []

    def reader() -> None:
        end = time.time() + seconds
        while time.time() < end:
            ready, _, _ = select.select([device], [], [], 0.2)
            if ready:
                try:
                    for event in device.read():
                        events.append((event.type, event.code, event.value))
                except OSError:
                    return

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    return device, events


async def pair_and_press(proc: subprocess.Popen, device_id: str, port: int) -> None:
    conf = AppleTV(IPv4Address("127.0.0.1"), "E2E Test")
    conf.add_service(ManualService(device_id, Protocol.Companion, port, {}, credentials=None))
    loop = asyncio.get_running_loop()

    pairing = await pyatv.pair(conf, Protocol.Companion, loop)
    await pairing.begin()
    line = read_until(proc, "Pairing PIN", 10)
    pin = re.search(r"Pairing PIN:\s*(\d{4})", line)
    if not pin:
        raise RuntimeError("server printed a PIN line without a 4-digit PIN")
    pairing.pin(pin.group(1))
    await pairing.finish()
    await pairing.close()
    if not pairing.has_paired:
        raise RuntimeError("pairing failed")
    print("paired with the fake Apple TV", flush=True)

    credentials = pairing.service.credentials
    conf2 = AppleTV(IPv4Address("127.0.0.1"), "E2E Test")
    conf2.add_service(
        ManualService(device_id, Protocol.Companion, port, {}, credentials=credentials)
    )
    atv = await pyatv.connect(conf2, loop)
    try:
        await atv.remote_control.up()
        await atv.remote_control.select()
        await atv.remote_control.play_pause()
    finally:
        atv.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=47833)
    parser.add_argument("--name", default="E2E Test")
    parser.add_argument("--keep", action="store_true", help="keep the temporary state directory")
    args = parser.parse_args()

    if not os.access("/dev/uinput", os.W_OK):
        print("skip: /dev/uinput is not writable; run with the uinput backend available", file=sys.stderr)
        return 2
    if not CLI.exists():
        print(f"error: {CLI} not found; run ./install.sh first", file=sys.stderr)
        return 2

    tmp = Path(tempfile.mkdtemp(prefix="atv-e2e-"))
    config = tmp / "config.toml"
    print(f"temporary state: {tmp}", flush=True)

    proc = subprocess.Popen(
        [
            str(CLI),
            "--config",
            str(config),
            "run",
            "--backend",
            "uinput",
            "--name",
            args.name,
            "--port",
            str(args.port),
            "--device-name",
            DEVICE_NAME,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    device = None
    try:
        read_until(proc, "Pairing window is open", 15)
        state = json.loads((tmp / "state.json").read_text(encoding="utf-8"))

        path = find_device()
        print(f"virtual keyboard: {path}", flush=True)
        device, events = collect_events(path)

        asyncio.run(pair_and_press(proc, state["id"], args.port))
        time.sleep(0.5)
        keys = {code for typ, code, value in events if typ == ecodes.EV_KEY and value == 1}
        print(f"key-down events: {sorted(keys)}", flush=True)
        expected = {ecodes.KEY_UP, ecodes.KEY_ENTER, ecodes.KEY_PLAYPAUSE}
        missing = expected - keys
        if missing:
            raise RuntimeError(f"missing key events: {sorted(missing)}")
        print("OK: iPhone protocol -> Companion -> uinput -> Linux key events", flush=True)
        return 0
    finally:
        if device is not None:
            device.close()
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        remainder = proc.stdout.read()
        if remainder:
            print("server:", remainder, end="", flush=True)
        if not args.keep:
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)
        else:
            print(f"kept: {tmp}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
