"""End-to-end tests: pyatv's Companion client pairs with our server and presses buttons."""

import asyncio
from ipaddress import IPv4Address

import pyatv
import pytest
from pyatv.conf import AppleTV, ManualService
from pyatv.const import Protocol

from atv_remote.server import Identity, RemoteServer


async def start(tmp_path, actions, pins):
    identity = Identity(tmp_path / "state.json")
    loop = asyncio.get_running_loop()
    server = await loop.create_server(
        lambda: RemoteServer(identity, "Test PC", actions.append, pins.append),
        "127.0.0.1",
        0,
    )
    return server, identity, server.sockets[0].getsockname()[1]


def config(identity, port, credentials=None):
    conf = AppleTV(IPv4Address("127.0.0.1"), "Test PC")
    conf.add_service(
        ManualService(identity.id, Protocol.Companion, port, {}, credentials=credentials)
    )
    return conf


async def pair(identity, port, pins):
    pairing = await pyatv.pair(config(identity, port), Protocol.Companion, asyncio.get_running_loop())
    await pairing.begin()
    pairing.pin(pins[-1])
    await pairing.finish()
    await pairing.close()
    assert pairing.has_paired
    return pairing.service.credentials


async def test_pair_and_control(tmp_path):
    actions, pins = [], []
    server, identity, port = await start(tmp_path, actions, pins)
    credentials = await pair(identity, port, pins)
    assert len(identity.clients) == 1
    assert len(Identity(tmp_path / "state.json").clients) == 1  # persisted

    atv = await pyatv.connect(config(identity, port, credentials), asyncio.get_running_loop())
    try:
        await atv.remote_control.play_pause()
        await atv.remote_control.volume_up()
        await atv.remote_control.next()
        await atv.remote_control.left()
        await atv.remote_control.select()
    finally:
        atv.close()
        server.close()

    assert actions == ["play_pause", "volume_up", "next", "left", "select"]


async def test_wrong_pin_is_rejected(tmp_path):
    actions, pins = [], []
    server, identity, port = await start(tmp_path, actions, pins)
    pairing = await pyatv.pair(config(identity, port), Protocol.Companion, asyncio.get_running_loop())
    await pairing.begin()
    pairing.pin((int(pins[-1]) + 1) % 10000)
    try:
        await pairing.finish()
    except Exception:  # noqa: BLE001, S110 - the point is that it must fail
        pass
    await pairing.close()
    server.close()
    assert identity.clients == {}


async def test_unpaired_device_cannot_control(tmp_path):
    actions, pins = [], []
    server, identity, port = await start(tmp_path, actions, pins)
    credentials = await pair(identity, port, pins)
    identity.clients.clear()  # server forgets the device

    try:
        atv = await pyatv.connect(config(identity, port, credentials), asyncio.get_running_loop())
        await atv.remote_control.play_pause()
        atv.close()
    except Exception:  # noqa: BLE001, S110 - unpaired control must fail
        pass
    server.close()
    assert actions == []


def test_opack_references_after_empty_string():
    # Shape of iOS 27's _systemInfo: an '' before a repeated key.
    from pyatv.support import opack

    from atv_remote.server import unpack_opack

    message = {"_c": {"m": "", "_idsCID": "abc", "_i": "58b4", "n": 128}, "_i": "_systemInfo", "f": 128.0}
    data = opack.pack(message)
    assert opack.unpack(data)[0] != message  # pyatv's decoder gets this wrong
    assert unpack_opack(data) == message


class _Transport:
    def __init__(self):
        self.messages = []

    def get_extra_info(self, key):
        return ("127.0.0.1", 49152)

    def write(self, data):
        from atv_remote.server import unpack_opack

        self.messages.append(unpack_opack(data[4:]))

    def close(self):
        pass


def test_ios_remote_session_gets_answers(tmp_path):
    # Request sequence the iOS 27 Apple TV Remote sends after pair-verify.
    server = RemoteServer(Identity(tmp_path / "state.json"), "Test PC", print, print)
    server.transport = transport = _Transport()
    requests = [
        ("_systemInfo", {"name": "iPhone"}),
        ("_sessionStart", {"_sid": 1, "_srvT": "com.apple.tvremoteservices"}),
        ("TVRCSessionStart", {"ProtocolVersionKey": "1.2"}),
        ("FetchAttentionState", {}),
        ("FetchSiriRemoteInfo", {}),
        ("FetchSupportedActionsEvent", {}),
        ("FetchCurrentNowPlayingInfoEvent", {}),
        ("FetchCurrentTopShelfItemsEvent", {}),
        ("FetchMediaControlStatus", {}),
        ("_touchStart", {"_height": 1000.0, "_tFl": 0, "_width": 1000.0}),
        ("_tiStart", {}),
    ]
    for xid, (ident, content) in enumerate(requests):
        server._handle_message({"_i": ident, "_t": 2, "_c": content, "_x": xid})

    replies = {m["_x"]: m for m in transport.messages if m.get("_t") == 3}
    assert all("_ec" not in reply for reply in replies.values())
    assert set(replies) == set(range(len(requests)))
    info = replies[0]["_c"]
    assert info["_lP"] == 49152 and "com.apple.tvremoteservices" in info["_stA"]
    assert replies[9]["_c"] == {"_i": 1}
    assert replies[8]["_c"]["MediaControlFlags"]


def _session(tmp_path):
    server = RemoteServer(Identity(tmp_path / "state.json"), "Test PC", None, print)
    server.transport = _Transport()
    actions = []
    server.on_action = actions.append
    return server, actions


def _swipe(server, start, end):
    for phase, (x, y) in ((1, start), (3, end), (4, end)):
        server._handle_message(
            {"_i": "_hidT", "_t": 1, "_x": 0, "_c": {"_tPh": phase, "_cx": x, "_cy": y}}
        )


def test_touch_gestures(tmp_path):
    server, actions = _session(tmp_path)
    _swipe(server, (200, 500), (800, 500))  # right
    _swipe(server, (800, 500), (200, 500))  # left
    _swipe(server, (500, 800), (500, 500))  # up
    _swipe(server, (500, 400), (500, 600))  # down
    _swipe(server, (500, 500), (520, 510))  # jitter from a tap: ignored
    assert actions == ["right", "left", "up", "down"]


def test_buttons_act_on_release_only(tmp_path):
    server, actions = _session(tmp_path)
    for state in (1, 2):  # press, release
        server._handle_message(
            {"_i": "_hidC", "_t": 2, "_x": 1, "_c": {"_hidC": 6, "_hBtS": state}}
        )
    assert actions == ["select"]
    # watchOS sends 0 instead of 2
    server._handle_message(
        {"_i": "_hidC", "_t": 2, "_x": 1, "_c": {"_hidC": 7, "_hBtS": 0}}
    )
    assert actions == ["select", "home"]


def test_channel_guide_and_power_buttons(tmp_path):
    server, actions = _session(tmp_path)
    for code in (15, 16, 17, 19):
        server._handle_message(
            {"_i": "_hidC", "_t": 2, "_x": 1, "_c": {"_hidC": code, "_hBtS": 2}}
        )
    assert actions == ["channel_up", "channel_down", "guide", "power"]


def test_volume_from_iphone(tmp_path):
    server, actions = _session(tmp_path)
    for vol in (0.6, 0.7, 0.4):
        server._handle_message(
            {"_i": "_mcc", "_t": 2, "_x": 1, "_c": {"_mcc": 6, "_vol": vol}}
        )
    assert actions == ["volume_up", "volume_up", "volume_down"]


def test_every_action_has_a_key():
    from atv_remote.keymap import DEFAULT_KEYMAP
    from atv_remote.server import HID_ACTIONS, MCC_ACTIONS

    used = {a for a in HID_ACTIONS.values() if a} | set(MCC_ACTIONS.values())
    assert used <= set(DEFAULT_KEYMAP)


def test_select_hold_and_release(tmp_path):
    server, actions = _session(tmp_path)
    holds, releases = [], []
    server.on_hold = lambda action: holds.append(action) or True
    server.on_release = releases.append

    def button(code, state):
        server._handle_message(
            {"_i": "_hidC", "_t": 2, "_x": 1, "_c": {"_hidC": code, "_hBtS": state}}
        )

    button(6, 1)  # press: hold, no tap yet
    assert holds == ["select"]
    assert releases == []
    assert actions == []

    button(6, 2)  # release: finish the hold, still no extra tap
    assert releases == ["select"]
    assert actions == []


def test_hold_backend_that_cannot_hold_falls_back_to_tap(tmp_path):
    server, actions = _session(tmp_path)
    server.on_hold = lambda action: False
    server.on_release = lambda action: None

    def button(code, state):
        server._handle_message(
            {"_i": "_hidC", "_t": 2, "_x": 1, "_c": {"_hidC": code, "_hBtS": state}}
        )

    button(6, 1)
    button(6, 2)
    assert actions == ["select"]


def test_repeatable_button_acts_on_press(tmp_path):
    server, actions = _session(tmp_path)
    server.on_hold = lambda action: True
    server.on_release = lambda action: None

    def button(code, state):
        server._handle_message(
            {"_i": "_hidC", "_t": 2, "_x": 1, "_c": {"_hidC": code, "_hBtS": state}}
        )

    button(1, 1)  # up press: first step fires immediately
    assert actions == ["up"]
    button(1, 2)  # release: no duplicate
    assert actions == ["up"]


@pytest.mark.asyncio
async def test_holding_direction_repeats_until_release(tmp_path, monkeypatch):
    import atv_remote.server as server_module

    monkeypatch.setattr(server_module, "HOLD_DELAY", 0.02)
    monkeypatch.setattr(server_module, "HOLD_INTERVAL", 0.01)
    server, actions = _session(tmp_path)

    def button(code, state):
        server._handle_message(
            {"_i": "_hidC", "_t": 2, "_x": 1, "_c": {"_hidC": code, "_hBtS": state}}
        )

    button(2, 1)  # down press
    assert actions == ["down"]
    await asyncio.sleep(0.06)
    assert actions.count("down") >= 3

    button(2, 2)  # release stops the repeat
    count = len(actions)
    await asyncio.sleep(0.04)
    assert len(actions) == count


@pytest.mark.asyncio
async def test_duplicate_press_frames_do_not_double_step(tmp_path, monkeypatch):
    import atv_remote.server as server_module

    monkeypatch.setattr(server_module, "HOLD_DELAY", 0.02)
    monkeypatch.setattr(server_module, "HOLD_INTERVAL", 0.01)
    server, actions = _session(tmp_path)

    for _ in range(3):  # the app may resend the press while held
        server._handle_message(
            {"_i": "_hidC", "_t": 2, "_x": 1, "_c": {"_hidC": 2, "_hBtS": 1}}
        )
    assert actions == ["down"]
    server._handle_message(
        {"_i": "_hidC", "_t": 2, "_x": 1, "_c": {"_hidC": 2, "_hBtS": 2}}
    )


def test_connection_lost_releases_held_key(tmp_path):
    server, actions = _session(tmp_path)
    releases = []
    server.on_hold = lambda action: True
    server.on_release = releases.append
    server._handle_message(
        {"_i": "_hidC", "_t": 2, "_x": 1, "_c": {"_hidC": 6, "_hBtS": 1}}
    )
    server.connection_lost(None)
    assert releases == ["select"]
    assert actions == []


def test_hid_button_accepts_string_encoded_fields(tmp_path):
    server, actions = _session(tmp_path)
    server._handle_message(
        {"_i": "_hidC", "_t": 2, "_x": 1, "_c": {"_hidC": "6", "_hBtS": "2"}}
    )
    assert actions == ["select"]
