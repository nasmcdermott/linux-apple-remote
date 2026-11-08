"""Companion Link server: make this Linux box appear as an Apple TV.

This is a Linux adaptation of the MIT-licensed ``windows-apple-remote`` server
by Arya Kavian.  The HAP pairing/verification and Companion framing are pyatv
internals; the Linux-specific part is the action mapping and the output sink.

Protocol summary (see pyatv's Companion Link docs and the upstream project):

* advertise ``_companion-link._tcp`` with Apple-TV-like TXT records
* HAP pair-setup (PIN) then pair-verify (Ed25519 / X25519)
* ChaCha20-Poly1305 encrypted OPACK frames
* ``_hidC`` button frames and ``_hidT`` touch frames carry the remote input
"""

from __future__ import annotations

import asyncio
import binascii
import hashlib
import json
import logging
import os
import secrets
import tempfile
import uuid
from pathlib import Path

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey
from pyatv.auth.hap_srp import hkdf_expand
from pyatv.auth.hap_tlv8 import ErrorCode, TlvValue, read_tlv, write_tlv
from pyatv.protocols.companion import MediaControlFlags
from pyatv.protocols.companion.api import MediaControlCommand
from pyatv.protocols.companion.connection import FrameType
from pyatv.protocols.companion.server_auth import (
    CompanionServerAuth,
    generate_keys,
    new_server_session,
)
from pyatv.support import chacha20, opack

from .pairing import PairingGate

_LOGGER = logging.getLogger(__name__)

AUTH_FRAMES = {FrameType.PS_Start, FrameType.PS_Next, FrameType.PV_Start, FrameType.PV_Next}
OPACK_FRAMES = AUTH_FRAMES | {FrameType.U_OPACK, FrameType.E_OPACK, FrameType.P_OPACK}
RESPONSE = 3  # "_t" value of a response

# Device facts known to make the iOS Control Center remote open a TVRC session.
# AppleTV14,1 (Apple TV 4K 3rd gen) + 715.2 is what enables the Control Center
# Power button; rpFl bit 8 (0x100) advertises MediaControl for volume/mute.
MODEL = "AppleTV14,1"
SOURCE_VERSION = "715.2"
RP_FLAGS = "0x36782"
SERVICE_TYPES = [
    "com.apple.tvremoteservices",
    "com.apple.bluetooth.remote",
    "com.apple.siri.wakeup",
    "com.apple.home.messaging",
    "com.apple.workflow.remotewidgets",
    "com.apple.devicediscoveryui.rapportwake",
]

# Companion HID command code -> semantic action.  Raw integers are used on
# purpose: iOS 26 repurposes 18/19 for Mute/Power, and older pyatv enums do not
# always name those the same way.
HID_ACTIONS: dict[int, str | None] = {
    1: "up",
    2: "down",
    3: "left",
    4: "right",
    5: "back",  # Menu
    6: "select",
    7: "home",  # TV button
    8: "volume_up",
    9: "volume_down",
    10: None,  # Siri: no microphone path in this prototype
    11: None,  # Screensaver
    12: None,  # Sleep: do not suspend the desktop from a remote tap
    13: None,  # Wake
    14: "play_pause",
    15: "channel_up",
    16: "channel_down",
    17: "guide",
    18: "mute",  # iOS 26 Control Center Mute
    19: "power",  # iOS 26 Control Center Power key
}

MCC_ACTIONS = {
    MediaControlCommand.Play: "play_pause",
    MediaControlCommand.Pause: "play_pause",
    MediaControlCommand.NextTrack: "next",
    MediaControlCommand.PreviousTrack: "previous",
}

MEDIA_FLAGS = (
    MediaControlFlags.Play
    | MediaControlFlags.Pause
    | MediaControlFlags.NextTrack
    | MediaControlFlags.PreviousTrack
    | MediaControlFlags.Volume
)

SWIPE_FRACTION = 0.15  # a swipe must cover this share of the touch surface
BUTTON_RELEASES = frozenset((0, 2))  # iOS uses 2; watchOS uses 0
BUTTON_PRESS = 1

# Actions that are held down until the phone sends the release.  This lets
# Plasma Bigscreen's own hold gestures work (long-press Select on a task =
# "Hold to close…").  Everything else stays a normal tap on release.
HOLD_ACTIONS = frozenset({"select"})

# Buttons that auto-repeat while the phone keeps them pressed, like a physical
# TV remote.  The first step fires immediately; after HOLD_DELAY the bridge
# repeats it every HOLD_INTERVAL until the release frame arrives.  Volume is
# slower because each step shells out to cec-policy (and the CEC queue is
# intentionally small).
REPEAT_ACTIONS = frozenset(
    {
        "up",
        "down",
        "left",
        "right",
        "channel_up",
        "channel_down",
        "volume_up",
        "volume_down",
    }
)
SLOW_REPEAT_ACTIONS = frozenset({"volume_up", "volume_down"})
HOLD_DELAY = 0.45
HOLD_INTERVAL = 0.12
SLOW_HOLD_INTERVAL = 0.30


def _as_int(value) -> int | None:
    """Best-effort int coercion for wire fields sent as int or string."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class _RefTable(list):
    """OPACK back-reference table matching Apple's encoder (and pyatv's pack()).

    pyatv's decoder tables 1-byte objects ('' and b'') and dedupes by ==, which
    makes a later reference resolve one slot off for iOS 27's ``_systemInfo``.
    """

    def __contains__(self, value):
        return any(type(item) is type(value) and item == value for item in self)

    def append(self, value):
        if value not in ("", b""):
            super().append(value)


def unpack_opack(data):
    return opack._unpack(data, _RefTable())[0]  # pylint: disable=protected-access


def _atomic_private_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        tmp.chmod(0o600)
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


class Identity:
    """Persistent server identity and paired devices, stored as private JSON."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path).expanduser()
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            data = {}
        self.id: str = data.get("id") or str(uuid.uuid4()).upper()
        self.seed: bytes = (
            bytes.fromhex(data["seed"]) if "seed" in data else secrets.token_bytes(32)
        )
        self.clients: dict[str, str] = data.get("clients", {})
        self.save()

    def save(self) -> None:
        payload = {
            "version": 1,
            "id": self.id,
            "seed": self.seed.hex(),
            "clients": self.clients,
        }
        _atomic_private_write(self.path, json.dumps(payload, indent=2) + "\n")

    def txt_record(self) -> dict[str, str]:
        """mDNS TXT properties of an Apple TV, with stable IDs derived from the seed."""
        digest = hashlib.sha256(self.seed).hexdigest()
        mac = ":".join(digest[i : i + 2] for i in range(48, 60, 2)).upper()
        return {
            "rpMac": "2",
            "rpFl": RP_FLAGS,
            "rpMd": MODEL,
            "rpVr": SOURCE_VERSION,
            "rpHN": digest[0:12],
            "rpHA": digest[12:24],
            "rpAD": digest[24:36],
            "rpHI": digest[36:48],
            "rpBA": mac,
            "rpMRtID": self.id,
        }

    def _uuid(self, label: bytes) -> str:
        return str(uuid.UUID(hashlib.sha256(self.seed + label).hexdigest()[:32])).upper()

    def system_info(self, name: str, port: int) -> dict:
        txt = self.txt_record()
        return {
            "name": name,
            "model": MODEL,
            "_sv": SOURCE_VERSION,
            "_i": txt["rpHI"],
            "_idsID": self._uuid(b"ids"),
            "_pubID": txt["rpBA"],
            "_mrID": self.id,
            "_mRtID": self.id,
            "_lP": port,
            "_stA": SERVICE_TYPES,
            "_sf": 65536,
            "_bf": 1920,
            "_cf": 512,
            "_clFl": 128,
            "_msSt": 1,
            "_msRo": 1,
            "_dCapF": 1,
            "_siriInfo": {
                "collectorElectionVersion": 1.0,
                "peerData": {
                    "productType": MODEL,
                    "userInterfaceIdiom": "ZEUS",
                    "userAssignedDeviceName": name,
                    "assistantIdentifier": self._uuid(b"assistant"),
                    "sharedUserIdentifier": self._uuid(b"user"),
                    "isLocationSharingDevice": False,
                    "isSiriCloudSyncEnabled": False,
                },
                "audio-session-coordination.system-info": {
                    "isSupportedAndEnabled": False,
                    "mediaRemoteGroupIdentifier": self._uuid(b"group"),
                    "mediaRemoteRouteIdentifier": self.id,
                },
            },
        }


class RemoteServer(CompanionServerAuth, asyncio.Protocol):
    """One connection from an iOS device."""

    def __init__(
        self,
        identity: Identity,
        name: str,
        on_action,
        on_pin,
        *,
        on_hold=None,
        on_release=None,
        pairing_gate: PairingGate | None = None,
        on_paired=None,
    ) -> None:
        super().__init__(name, unique_id=identity.id)
        self.keys = generate_keys(identity.seed)
        self.identity = identity
        self.on_action = on_action
        self.on_pin = on_pin
        self.on_hold = on_hold
        self.on_release = on_release
        self.on_paired = on_paired
        self.pairing_gate = pairing_gate
        self.transport = None
        self.buffer = b""
        self.chacha = None
        self._client_verify_pub = None
        self._touchpad = (1000.0, 1000.0)
        self._touch_start: tuple[float, float] | None = None
        self._last_touch: tuple[float, float] | None = None
        self._volume = 0.5
        self._held: str | None = None
        self._repeat_action: str | None = None
        self._repeat_task: asyncio.Task | None = None

    # asyncio.Protocol

    def connection_made(self, transport) -> None:
        self.transport = transport
        _LOGGER.info("Device connected: %s", transport.get_extra_info("peername"))

    def connection_lost(self, exc) -> None:
        _LOGGER.info("Device disconnected")
        # Never leave a key stuck down or a repeat loop running if the phone
        # drops mid-hold.
        self._stop_repeat()
        self._release_held()
        self.transport = None

    def data_received(self, data: bytes) -> None:
        self.buffer += data
        while len(self.buffer) >= 4:
            end = 4 + int.from_bytes(self.buffer[1:4], "big")
            if len(self.buffer) < end:
                return
            header, payload = self.buffer[:4], self.buffer[4:end]
            self.buffer = self.buffer[end:]
            try:
                self._handle_frame(header, payload)
            except Exception:
                _LOGGER.exception("Bad frame (type %d), closing connection", header[0])
                if self.transport:
                    self.transport.close()
                return

    def _handle_frame(self, header: bytes, payload: bytes) -> None:
        frame_type = FrameType(header[0])
        if self.chacha and payload:
            payload = self.chacha.decrypt(payload, aad=header)
        if frame_type not in OPACK_FRAMES:
            _LOGGER.debug("Ignoring %s frame: %s", frame_type, payload.hex())
            return
        message = unpack_opack(payload) if payload else {}
        if frame_type in AUTH_FRAMES:
            self.handle_auth_frame(frame_type, message)
        elif frame_type == FrameType.E_OPACK and self.chacha:
            _LOGGER.debug("Received: %s", message)
            self._handle_message(message)
        else:
            _LOGGER.debug("Ignoring %s frame", frame_type)

    # CompanionServerAuth hooks

    def send_to_client(self, frame_type: FrameType, data: dict) -> None:
        payload = opack.pack(data)
        length = len(payload) + (16 if self.chacha else 0)
        header = bytes([frame_type.value]) + length.to_bytes(3, "big")
        if self.chacha:
            payload = self.chacha.encrypt(payload, aad=header)
        if self.transport:
            self.transport.write(header + payload)

    def enable_encryption(self, output_key: bytes, input_key: bytes) -> None:
        self.chacha = chacha20.Chacha20Cipher(output_key, input_key, nonce_length=12)

    def _m1_setup(self, pairing_data: dict) -> None:
        if self.pairing_gate and not self.pairing_gate.allowed():
            _LOGGER.warning(
                "Rejected a pairing attempt: the pairing window is closed. "
                "Run 'atv-remote pair' and try again."
            )
            if self.transport:
                self.transport.close()
            return
        pin = f"{secrets.randbelow(10000):04d}"
        self.session, self.salt = new_server_session(self.keys, pin)
        self.on_pin(pin)
        super()._m1_setup(pairing_data)

    def _m5_setup(self, pairing_data: dict) -> None:
        srp_key = binascii.unhexlify(self.session.key)
        session_key = hkdf_expand("Pair-Setup-Encrypt-Salt", "Pair-Setup-Encrypt-Info", srp_key)
        cipher = chacha20.Chacha20Cipher(session_key, session_key)
        tlv = read_tlv(cipher.decrypt(pairing_data[TlvValue.EncryptedData], nonce=b"PS-Msg05"))
        client_id, client_ltpk = tlv[TlvValue.Identifier], tlv[TlvValue.PublicKey]
        ios_x = hkdf_expand(
            "Pair-Setup-Controller-Sign-Salt", "Pair-Setup-Controller-Sign-Info", srp_key
        )
        Ed25519PublicKey.from_public_bytes(client_ltpk).verify(
            tlv[TlvValue.Signature], ios_x + client_id + client_ltpk
        )

        acc_x = hkdf_expand(
            "Pair-Setup-Accessory-Sign-Salt", "Pair-Setup-Accessory-Sign-Info", srp_key
        )
        info = {"name": self.device_name, "model": MODEL}
        reply = write_tlv(
            {
                TlvValue.Identifier: self.unique_id,
                TlvValue.PublicKey: self.keys.auth_pub,
                TlvValue.Signature: self.keys.sign.sign(acc_x + self.unique_id + self.keys.auth_pub),
                TlvValue.Name: opack.pack(info),
            }
        )
        encrypted = cipher.encrypt(reply, nonce=b"PS-Msg06")
        self.send_to_client(
            FrameType.PS_Next,
            {"_pd": write_tlv({TlvValue.SeqNo: b"\x06", TlvValue.EncryptedData: encrypted})},
        )

        self.identity.clients[client_id.decode()] = client_ltpk.hex()
        self.identity.save()
        _LOGGER.info("Paired with %s", client_id.decode())
        print("Paired. The device is remembered for next time.", flush=True)
        if self.on_paired:
            try:
                self.on_paired()
            except Exception:  # pragma: no cover - callback is best effort
                _LOGGER.exception("on_paired callback failed")
        self.enable_encryption(
            hkdf_expand("", "ServerEncrypt-main", srp_key),
            hkdf_expand("", "ClientEncrypt-main", srp_key),
        )

    def _m1_verify(self, pairing_data: dict) -> None:
        self._client_verify_pub = pairing_data[TlvValue.PublicKey]
        super()._m1_verify(pairing_data)

    def _m3_verify(self, pairing_data: dict) -> None:
        shared = self.keys.verify.exchange(
            X25519PublicKey.from_public_bytes(self._client_verify_pub)
        )
        session_key = hkdf_expand("Pair-Verify-Encrypt-Salt", "Pair-Verify-Encrypt-Info", shared)
        server_pub = self.keys.verify_pub.public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        try:
            cipher = chacha20.Chacha20Cipher(session_key, session_key)
            tlv = read_tlv(cipher.decrypt(pairing_data[TlvValue.EncryptedData], nonce=b"PV-Msg03"))
            client_id = tlv[TlvValue.Identifier]
            ltpk = bytes.fromhex(self.identity.clients[client_id.decode()])
            Ed25519PublicKey.from_public_bytes(ltpk).verify(
                tlv[TlvValue.Signature], self._client_verify_pub + client_id + server_pub
            )
        except (KeyError, InvalidSignature, InvalidTag):
            _LOGGER.info("Unpaired device, asking it to pair")
            error = {TlvValue.SeqNo: b"\x04", TlvValue.Error: bytes([ErrorCode.Authentication])}
            self.send_to_client(FrameType.PV_Next, {"_pd": write_tlv(error)})
            return
        _LOGGER.info("Verified %s", client_id.decode())
        super()._m3_verify(pairing_data)

    # Remote commands

    def _handle_message(self, message: dict) -> None:
        ident = message.get("_i")
        content = message.get("_c", {})
        if not isinstance(content, dict):
            content = {}
        reply: dict = {}

        if ident == "_systemInfo":
            port = self.transport.get_extra_info("sockname")[1] if self.transport else 0
            reply = self.identity.system_info(self.device_name, port)
        elif ident == "_hidC":
            # Some senders encode _hBtS/_hidC as strings; coerce both so a
            # button is never silently dropped because of a wire type.
            state = _as_int(content.get("_hBtS"))
            code = _as_int(content.get("_hidC"))
            action = HID_ACTIONS.get(code) if code is not None else None
            _LOGGER.debug("HID code=%r state=%r -> %r", code, state, action)
            if action is None:
                if code is not None:
                    _LOGGER.debug("Ignoring HID button code %r", code)
            elif state == BUTTON_PRESS:
                self._button_down(action)
            elif state in BUTTON_RELEASES:
                self._button_up(action)
            else:
                _LOGGER.debug("HID button %r with unknown state %r", code, state)
        elif ident == "_mcc":
            try:
                command = MediaControlCommand(content.get("_mcc"))
            except (TypeError, ValueError):
                command = None
            if command == MediaControlCommand.GetVolume:
                reply = {"_vol": self._volume}
            elif command == MediaControlCommand.SetVolume:
                try:
                    new = float(content.get("_vol", self._volume))
                except (TypeError, ValueError):
                    new = self._volume
                if new != self._volume:
                    self._act("volume_up" if new > self._volume else "volume_down")
                self._volume = max(0.0, min(1.0, new))
            elif command is not None:
                self._act(MCC_ACTIONS.get(command))
        elif ident == "_hidT":
            self._touch(content)
        elif ident == "_touchStart":
            try:
                self._touchpad = (
                    float(content.get("_width", 1000.0)),
                    float(content.get("_height", 1000.0)),
                )
            except (TypeError, ValueError):
                self._touchpad = (1000.0, 1000.0)
            reply = {"_i": 1}  # the remote gives up without a touch device id
        elif ident == "FetchMediaControlStatus":
            reply = {"MediaControlFlags": int(MEDIA_FLAGS)}
        elif ident == "_sessionStart":
            reply = {"_sid": secrets.randbits(32)}
        elif ident == "TVRCSessionStart":
            reply = dict(content)
        elif ident == "FetchAttentionState":
            reply = {"state": 3}  # awake
        elif ident == "_interest" and "_iMC" in content.get("_regEvents", []):
            self._send("_iMC", message.get("_x", 0), 1, {"_mcF": int(MEDIA_FLAGS)})

        # Answer everything: tvremoted ends the session on "No request handler",
        # and extra acks are ignored by the phone.
        self._reply(message, _c=reply)

    def _touch(self, content: dict) -> None:
        """Map a touchpad swipe to an arrow key.

        Taps are deliberately handled by the discrete Select button; a small
        movement below the threshold does nothing, so one tap cannot produce
        two Enter presses.  iOS 27 may omit the release coordinates, in which
        case the last move point is used.
        """
        try:
            phase = int(content.get("_tPh", -1))
            x = float(content.get("_cx", 0.0))
            y = float(content.get("_cy", 0.0))
        except (TypeError, ValueError):
            return
        point = (x, y)

        if phase == 1:  # press
            self._touch_start = point
            self._last_touch = point
            return
        if phase in (2, 3):  # move / legacy hold
            self._last_touch = point
            return
        if phase != 4:  # release
            return

        start = self._touch_start
        self._touch_start = None
        if start is None:
            return
        end = point if (x or y) else (self._last_touch or start)
        dx, dy = end[0] - start[0], end[1] - start[1]
        width, height = self._touchpad
        if abs(dx) >= abs(dy) and abs(dx) > width * SWIPE_FRACTION:
            self._act("right" if dx > 0 else "left")
        elif abs(dy) > abs(dx) and abs(dy) > height * SWIPE_FRACTION:
            self._act("down" if dy > 0 else "up")

    def _button_down(self, action: str) -> None:
        """Handle the press half of a button.

        * ``HOLD_ACTIONS`` (Select) start a key-down hold and finish on release.
        * ``REPEAT_ACTIONS`` (arrows, channel, volume) fire once immediately and
          auto-repeat until the release frame, like a physical TV remote.
        * Everything else keeps the original "act on release" behavior.

        Duplicate press frames for the button already held are ignored, and
        pressing another button stops the previous hold/repeat first.
        """
        if self._held == action or self._repeat_action == action:
            return
        self._stop_repeat()
        self._release_held()
        if action in REPEAT_ACTIONS:
            self._start_repeat(action)
            return
        if action not in HOLD_ACTIONS or self.on_hold is None:
            return
        try:
            if self.on_hold(action):
                self._held = action
                _LOGGER.debug("Holding %s", action)
        except Exception:  # pragma: no cover - never tear down the remote
            _LOGGER.exception("Output backend failed to hold %s", action)

    def _button_up(self, action: str) -> None:
        if self._repeat_action == action:
            self._stop_repeat()
            return
        if self._held == action:
            self._release_held()
            return
        self._release_held()
        self._act(action)

    def _start_repeat(self, action: str) -> None:
        """Emit the first step now and schedule the rest until release."""
        self._repeat_action = action
        self._act(action)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Synchronous test/CLI context: the first step is all we can do.
            # Keep the action marked so the release does not fire it twice.
            return
        self._repeat_task = loop.create_task(self._repeat(action))

    async def _repeat(self, action: str) -> None:
        interval = SLOW_HOLD_INTERVAL if action in SLOW_REPEAT_ACTIONS else HOLD_INTERVAL
        try:
            await asyncio.sleep(HOLD_DELAY)
            while self._repeat_action == action:
                self._emit(action, repeat=True)
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            pass

    def _stop_repeat(self) -> None:
        action, self._repeat_action = self._repeat_action, None
        task, self._repeat_task = self._repeat_task, None
        if task is not None and not task.done():
            task.cancel()
        if action:
            _LOGGER.debug("Stopped repeat %s", action)

    def _release_held(self) -> None:
        action, self._held = self._held, None
        if not action:
            return
        _LOGGER.debug("Releasing held %s", action)
        try:
            if self.on_release is not None:
                self.on_release(action)
        except Exception:  # pragma: no cover - never tear down the remote
            _LOGGER.exception("Output backend failed to release %s", action)

    def _emit(self, action: str, *, repeat: bool = False) -> None:
        if not action:
            return
        if repeat:
            _LOGGER.debug("Repeat: %s", action)
        else:
            _LOGGER.info("Action: %s", action)
        try:
            self.on_action(action)
        except Exception:  # pragma: no cover - never tear down the remote for a key error
            _LOGGER.exception("Output backend failed for action %s", action)

    def _act(self, action: str | None) -> None:
        if not action:
            return
        self._release_held()
        self._emit(action)

    def _send(self, ident: str, xid: int, msg_type: int, content: dict) -> None:
        self._write({"_i": ident, "_x": xid, "_t": msg_type, "_c": content})

    def _reply(self, request: dict, **fields) -> None:
        self._write({"_x": request.get("_x", 0), "_t": RESPONSE, **fields})

    def _write(self, message: dict) -> None:
        _LOGGER.debug("Sending: %s", message)
        self.send_to_client(FrameType.E_OPACK, message)
