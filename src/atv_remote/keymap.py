"""Semantic actions and their default Linux key codes.

The Companion protocol speaks in Apple HID button codes; ``server.py`` translates
those to the action names below.  Output backends translate actions to whatever
the host understands (``uinput`` key codes, ``playerctl`` commands, ...).

Keep this module free of network/protocol imports so it is trivial to test.
"""

from __future__ import annotations

import os

from evdev import ecodes

# Actions the bridge can emit.  This is the stable interface between the
# Companion input backend and the output backends.
ACTIONS = (
    "up",
    "down",
    "left",
    "right",
    "select",
    "back",
    "home",
    "play_pause",
    "next",
    "previous",
    "volume_up",
    "volume_down",
    "mute",
    "power",
    "channel_up",
    "channel_down",
    "guide",
)

# The defaults are deliberately "TV remote on a desktop":
#   - arrows / Enter / Esc navigate almost every media app and browser
#   - Play/Pause, Next, Previous, volume and mute are standard media keys
#   - Home is "auto": Plasma Bigscreen's own shortcut is "Home Page"
#     (KEY_HOMEPAGE); a regular KDE/GNOME desktop uses a Meta tap
DEFAULT_KEYMAP: dict[str, str] = {
    "up": "KEY_UP",
    "down": "KEY_DOWN",
    "left": "KEY_LEFT",
    "right": "KEY_RIGHT",
    "select": "KEY_ENTER",
    "back": "KEY_ESC",
    "home": "auto",
    "play_pause": "KEY_PLAYPAUSE",
    "next": "KEY_NEXTSONG",
    "previous": "KEY_PREVIOUSSONG",
    "volume_up": "KEY_VOLUMEUP",
    "volume_down": "KEY_VOLUMEDOWN",
    "mute": "KEY_MUTE",
    "power": "KEY_POWER",
    "channel_up": "KEY_CHANNELUP",
    "channel_down": "KEY_CHANNELDOWN",
    "guide": "bigscreen_overlay",
}


BIGSCREEN_HOME_KEY = "KEY_HOMEPAGE"
DESKTOP_HOME_KEY = "KEY_LEFTMETA"

# Values that are not Linux key names.  The output backend implements them as
# a desktop action instead of an evdev key press.
#   bigscreen_overlay: open Plasma Bigscreen's home overlay (Home/Search/Tasks)
#   via the same org.kde.PlasmaShell.activateLauncherMenu D-Bus call the Fire
#   TV remote uses.  Falls back to KEY_MENU when Plasma is unavailable.
SPECIAL_KEYS = frozenset({"bigscreen_overlay"})


def is_bigscreen_session() -> bool:
    """True for Plasma Bigscreen (Wayland or X11).

    Bigscreen binds the ``Home Page`` key to "Toggle Bigscreen Home Screen";
    a regular desktop binds Meta to the launcher/overview.  Use the session
    environment, not the output backend, so this works on Wayland and X11.
    """
    session = os.environ.get("DESKTOP_SESSION") or os.environ.get("XDG_SESSION_DESKTOP") or ""
    current = os.environ.get("XDG_CURRENT_DESKTOP") or ""
    return "bigscreen" in session.lower() or "bigscreen" in current.lower()


def resolve_key_name(action: str, key_name: str) -> str:
    """Resolve the special ``auto`` value, if used.

    Values in :data:`SPECIAL_KEYS` are returned unchanged; the output backend
    runs them as desktop actions rather than evdev key presses.
    """
    if key_name in SPECIAL_KEYS:
        return key_name
    if key_name != "auto":
        return key_name
    if action != "home":
        raise ValueError(f"'auto' is only supported for the home action, not {action!r}")
    return BIGSCREEN_HOME_KEY if is_bigscreen_session() else DESKTOP_HOME_KEY


def code_for(key_name: str) -> int:
    """Return the Linux input event code for a ``KEY_*`` name.

    Raises ``ValueError`` with a useful message instead of a bare KeyError so a
    typo in ``config.toml`` produces a clear startup error.
    """
    code = ecodes.ecodes.get(key_name)
    if code is None:
        raise ValueError(f"unknown Linux key name: {key_name!r} (expected something like KEY_UP)")
    return code


def validate_keymap(keymap: dict[str, str]) -> dict[str, str]:
    """Validate and return a copy of ``keymap``.

    Unknown actions are ignored (forward compatibility); unknown key names are
    errors.  Every action in :data:`ACTIONS` may be absent, in which case that
    button does nothing.
    """
    validated: dict[str, str] = {}
    for action, key_name in keymap.items():
        if action not in ACTIONS:
            continue
        if key_name in SPECIAL_KEYS:
            pass  # implemented by the output backend, not an evdev key
        elif key_name == "auto":
            resolve_key_name(action, key_name)  # validates that auto is allowed here
        else:
            code_for(key_name)  # validate eagerly
        validated[action] = key_name
    return validated
