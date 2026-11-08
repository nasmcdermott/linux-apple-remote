# Linux Apple Remote

Control a Linux media PC with the **Apple TV Remote app on iPhone or iPad** —
the same app you use for an Apple TV. The bridge advertises the machine as an
Apple TV over **Companion Link**, pairs with the phone, and injects ordinary
Linux key events through `uinput`.

This is an independent Linux adaptation, not a fork of the Windows project and
not affiliated with or endorsed by Apple or the upstream author. See
[License and credits](#license-and-credits).

```
iPhone / iPad Apple TV Remote
        │  Companion Link / mDNS / HAP / ChaCha20
        ▼
  atv-remote (this project)
        │  semantic actions
        ▼
  uinput virtual keyboard  (Wayland, X11, KDE, GNOME, TTY)
```

It is a **media / arrow-key remote**, not a full desktop remote: D-pad, Select,
Back, Home, Play/Pause, Next/Previous, volume/mute, power, channel and guide.
It does not stream video and does not implement Siri/voice.

Status: **usable prototype**. Tested with a real iPhone, Plasma Bigscreen
Wayland, and a real `/dev/uinput` device. The iOS side of the protocol is
reverse-engineered and can change with iOS releases.

## Quick start

Requirements:

- Linux with **Python 3.11+** and a writable `/dev/uinput`
- Phone and PC on the same LAN (mDNS, UDP 5353)
- Optional PIN card: PySide6 (Qt Quick) and, on KDE Wayland, `layer-shell-qt`
- Optional PIN notification: `notify-send` / libnotify
- Optional CEC volume/mute/TV-on: the `cec-policy` script from the companion
  `fedora-cec-toolkit` project

```sh
git clone https://github.com/nasmcdermott/linux-apple-remote.git
cd linux-apple-remote
./install.sh

atv-remote doctor     # permissions, CEC, firewall, PIN GUI
atv-remote pair       # open the pairing window
```

On the iPhone: open **Apple TV Remote**, select the machine name, and enter the
four-digit PIN shown in the top-right card. If the card cannot start, the PIN is
printed in the log and available with `atv-remote pin`.

The installer writes only inside your home directory and the checkout:
`./.venv`, `~/.local/bin/atv-remote`, `~/.config/apple-tv-remote/`, and
`~/.config/systemd/user/apple-tv-remote.service`. It never runs `sudo`.

Useful options:

```sh
./install.sh --name "Living Room"     # optional override; default: OS hostname
./install.sh --cec                    # opt in to HDMI-CEC volume/mute/TV-on
./install.sh --pin-display notification  # notify-send instead of the Qt card
./install.sh --pin-display none          # log/atv-remote pin only
./install.sh --match-blur-corners     # round Better Blur DX/Blur Plus to the card
./install.sh --address 192.168.1.50   # pin the advertised interface
./install.sh --backend mpris          # media-only, no /dev/uinput access
./install.sh --no-service             # foreground only
./install.sh --force-config           # rewrite config.toml
./install.sh --with-tests             # install pytest too
./install.sh --mouse-mode home        # TV button = home signal (trackpad or home)
```

Hardware-specific extras stay off by default. CEC needs `cec-policy` and a
writable `/dev/cec*`; without it, volume/mute use ordinary media keys and Power
still opens the desktop menu. `--cec` only affects a newly written config —
edit an existing `config.toml` or rerun with `--force-config`.

## Default key map

| iPhone remote | Linux action |
|---|---|
| D-pad or swipe | Arrow keys |
| Select / touch-pad tap | Enter |
| Back / Menu | Esc |
| TV / Home | `home` action (Bigscreen home or Meta); or trackpad mode (see `mouse_mode`) |
| Play/Pause | Play/Pause media key |
| Next / Previous | Next/Previous track |
| Volume ± | CEC volume via `cec-policy` (or media keys) |
| Mute | CEC mute via `cec-policy` (or mute key) |
| Power | `KEY_POWER` (desktop power menu) + optional CEC TV-on |
| Channel ± | `KEY_CHANNELUP` / `KEY_CHANNELDOWN` |
| Guide | Bigscreen Home/Search/Tasks overlay (same D-Bus call as the Fire TV remote) |

Every mapping can be changed in `~/.config/apple-tv-remote/config.toml`; see
[Configuration](#configuration).

## Behavior notes

### Long press Select

Select is a real key-down/key-up hold, not a 20 ms tap. In Plasma Bigscreen,
open **Tasks**, focus an app, and hold Select for about a second — the tile
shows **“Hold to close…”** and the app closes on release. A short press still
activates the focused app.

### Hold to repeat — and its limit

The bridge repeats a button only when the phone reports that it is still held
down (`state=1`, a real gap, then `state=2`). Apple's app sends different input
for different buttons:

| Button | Frames from the app | Result |
|---|---|---|
| Channel ± | held press | auto-repeats |
| Select | held press | Bigscreen long-press works |
| Arrows (D-pad or swipe) | one-shot press+release (~20 ms) | one step per tap |
| Volume ± (hardware) | one-shot press+release (~1 ms) | one CEC step per press |

Channel ± repeats `KEY_CHANNELUP`/`KEY_CHANNELDOWN`. Arrows and Volume ± cannot
auto-repeat from Apple's app because it sends a complete tap; the bridge cannot
invent the missing hold. A physical remote or a client that actually holds the
button will repeat, because the repeat code is shared.

### Home and Guide

`home = "auto"` detects Plasma Bigscreen and emits `KEY_HOMEPAGE`, which is
bound to Bigscreen's “Toggle Bigscreen Home Screen”. On a regular KDE/GNOME
session it emits a Meta tap.

`guide = "bigscreen_overlay"` calls
`org.kde.PlasmaShell.activateLauncherMenu` — the same call the Fire TV remote
uses — so it opens the exact Bigscreen quick-settings overlay. On a non-Plasma
session it falls back to `KEY_MENU`.

### Power and CEC

Power always emits `KEY_POWER`, so the desktop shows its normal
sleep / power off / restart / log out / cancel menu. With `[cec].power_on =
true`, the bridge also launches `cec-policy wake --reason powerkey` to turn the
TV on and select the PC input.

CEC is **opt-in** (`[cec].enabled = false` by default). When enabled, volume
and mute go to the same `cec-policy` controller as the Fire TV remote. The
bridge never touches PipeWire/Plasma software volume. If CEC is unavailable,
volume/mute fall back to ordinary media keys.

Enable it with `./install.sh --cec` (new config) or by setting
`[cec].enabled = true` in an existing config and restarting the service.

### Pairing PIN card

A small Qt Quick card appears in the top-right when a new phone starts pairing
and stays until pairing succeeds or the window expires.

- KDE Wayland: layer-shell card; GNOME Wayland: transparent full-screen overlay;
  X11: normal top-right window.
- Colors, fonts and scaling come from `kdeglobals` (window background/foreground,
  selection accent, button and inactive-text colors, font family and point size)
  and follow the light/dark color scheme. GNOME uses `gsettings`; other desktops
  get a neutral palette. The whole card scales with the desktop font size.
- The card has **no painted-in white glass sheen**. It is a translucent rounded
  surface and asks KWin for blur behind its rounded shape, so Better Blur DX,
  Force Blur, Blur Plus, Liquid Glass and other compositor effects decide how
  strong the blur is. When no blur effect is available, the card falls back to a
  nearly opaque fill so the PIN stays legible.
- A subtle ring in the system accent color pulses around the card.
- Blur is compositor-driven. The card asks KWin for a rounded blur region; if a
  third-party effect rounds its own region (for example Better Blur DX
  `CornerRadius`), you may see a faint square fringe at the corners.
  `atv-remote doctor` reports the effect's current radius, and
  `atv-remote match-blur-corners` (or `./install.sh --match-blur-corners`)
  sets Better Blur DX / Blur Plus to the card radius and reloads KWin. It is
  opt-in because it also rounds blur corners on other windows; the previous
  `kwinrc` is saved as `~/.config/kwinrc.bak-apple-tv-remote`.
- It runs in the **system** Python with PySide6, not the project venv.
- `pin_display` chooses the presentation:

  | Value | Behavior |
  |---|---|
  | `auto` (default) | GUI if available, otherwise log only |
  | `qt` | require the GUI; log fallback |
  | `notification` | opt-in `notify-send` card/notification instead of Qt |
  | `none` | log and `atv-remote pin` only |

  The PIN is always written to the journal and kept in `last-pin` for
  `atv-remote pin`.

### `mouse_mode` (TV button behavior)

| Value | Behavior |
|---|---|
| `trackpad` (default) | Touch area becomes a trackpad: drag moves cursor, tap = left click |
| `home` | TV button sends `home` action (Bigscreen `KEY_HOMEPAGE` or Meta) |

## Configuration

`~/.config/apple-tv-remote/config.toml`:

```toml
[remote]
# name = "Linux TV"   # optional; default: OS hostname (fallback: "Linux TV")
port = 47832
backend = "uinput"        # uinput | mpris | log
device_name = "Apple TV Remote Bridge"
pairing_window = 600      # seconds; 0 disables new pairings
pin_display = "auto"      # auto | qt | notification | none
mouse_mode = "trackpad"   # trackpad | home
# address = "192.168.1.50" # if auto-detection picks the wrong interface

[keys]
up = "KEY_UP"
down = "KEY_DOWN"
left = "KEY_LEFT"
right = "KEY_RIGHT"
select = "KEY_ENTER"
back = "KEY_ESC"
home = "auto"
play_pause = "KEY_PLAYPAUSE"
next = "KEY_NEXTSONG"
previous = "KEY_PREVIOUSSONG"
volume_up = "KEY_VOLUMEUP"
volume_down = "KEY_VOLUMEDOWN"
mute = "KEY_MUTE"
power = "KEY_POWER"
channel_up = "KEY_CHANNELUP"
channel_down = "KEY_CHANNELDOWN"
guide = "bigscreen_overlay"   # or any KEY_* name

[cec]
enabled = false        # opt in with --cec or set true
policy = "auto"
volume = true          # applies only when enabled
mute = true
power_on = true        # cec-policy wake --reason powerkey on Power
timeout = 15
```

`name` is optional. If it is omitted, the bridge advertises the machine's current
OS hostname; if the hostname cannot be read, it falls back to `Linux TV`. Set
`name` only when you want a fixed name instead of the hostname.

Remove a mapping line to make that button do nothing. Restart after editing:

```sh
systemctl --user restart apple-tv-remote
```

Commands:

```sh
atv-remote doctor          # permissions, CEC, firewall, service, pairings
atv-remote keys            # show the active mapping
atv-remote config show
atv-remote config init --force
atv-remote run -v          # foreground with debug logging
atv-remote pair
atv-remote pin
atv-remote preview-pin     # show the PIN card for 8 s
atv-remote match-blur-corners  # opt in: round force-blur to the card radius
atv-remote unpair --list
atv-remote unpair --all
```

## Compatibility

- **Distros:** reference system is Fedora 44 KDE Plasma Bigscreen Wayland.
  Debian/Ubuntu, Arch, openSUSE and other systemd distros work with the same
  Python package. Non-systemd distros work too: run `atv-remote run` from your
  init/session autostart and skip the service.
- **Display server:** `uinput` is below Wayland/X11, so keys work everywhere,
  including a TTY. The PIN card adapts to KDE, GNOME, X11 and unknown sessions.
- **Python:** 3.11+. The installer uses `uv` if present, otherwise `venv`+`pip`.
- **D-Bus:** Guide prefers `busctl`, then `gdbus`, then `dbus-send`, so it also
  works on systems without systemd.
- **CEC:** optional; `cec-policy` is found on `PATH`, in `/usr/local/bin`,
  `/usr/bin`, the CEC toolkit directory, and `~/.local/bin`.

Package names and per-distro setup are in
[`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md).

## Install methods and releases

The recommended path is the **source checkout + `install.sh`** (or a GitHub
Release wheel). The bridge needs host access to `/dev/uinput`, `/dev/cec*`, the
session D-Bus, and LAN mDNS; that makes sandboxed packaging a poor fit.

- **Primary:** source tarball + `install.sh` + systemd user unit.
- **Recommended next:** publish to PyPI and install with
  `pipx install linux-apple-remote`, then use the unit in
  `contrib/systemd/`.
- **Later/optional:** `.rpm`/`.deb` via `nfpm` or distro packaging.
- **Not recommended:** Flatpak, Snap, Docker, AppImage. They either cannot
  reach `/dev/uinput` and CEC, cannot call the host Plasma D-Bus, or add a
  second mDNS stack. See [`docs/PACKAGING.md`](docs/PACKAGING.md).

## Troubleshooting

### The iPhone does not see the bridge

- Phone and PC must be on the same LAN, not guest Wi-Fi or another VLAN.
- Allow mDNS (UDP 5353). With firewalld:

  ```sh
  sudo firewall-cmd --add-service=mdns
  sudo firewall-cmd --permanent --add-service=mdns && sudo firewall-cmd --reload
  ```

  With ufw: `sudo ufw allow 5353/udp`.
- `atv-remote doctor` shows the advertised address and firewall state. If it
  picked a VPN/Docker interface, set `address` in the config.

### `cannot open /dev/uinput`

```sh
test -w /dev/uinput
sudo setfacl -m u:"$USER":rw /dev/uinput          # temporary
# persistent:
sudo install -Dm644 contrib/udev/99-uinput.rules /etc/udev/rules.d/99-uinput.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

Or use the media-only fallback: `./install.sh --backend mpris --force-config`.

### Pairing fails or the connection closes

- Reopen the window with `atv-remote pair`; the PIN must be entered while it is
  open.
- If the phone keeps a stale credential, run `atv-remote unpair --all` and pair
  again.
- Run `atv-remote run -v` and open an issue with the log (it contains no PINs or
  keys).

### The PIN card does not appear

- `atv-remote doctor` reports `pin display: mode=... gui=yes/no
  notification=yes/no`.
- Install PySide6 QtQuick (`python3-pyside6`, `python3-pyside6.qml`, or
  `pyside6`) and `layer-shell-qt` on KDE Wayland.
- Prefer notifications? Set `pin_display = "notification"` and install
  `notify-send` / libnotify.
- The card only appears for a **new** pairing. Use `atv-remote preview-pin` to
  test it.
- Without either, use `atv-remote pin` or `journalctl --user -u
  apple-tv-remote -f`.

### Guide / channel buttons

Guide and Channel ± are Companion HID 17/15/16, mapped to the Bigscreen overlay
and `KEY_CHANNELUP`/`KEY_CHANNELDOWN`. If pressing them logs `Action: select`,
the app is not sending the discrete code. Run `atv-remote run -v` and inspect the
raw `_hidC` lines.

### Keys go to the wrong window

`uinput` injects at the kernel input layer, so keys go to whatever has focus —
the same as a physical keyboard. Bring Bigscreen forward first.

## Security

- `~/.config/apple-tv-remote/state.json` is a credential (server seed and paired
  client keys, mode 0600). Treat it like an SSH private key.
- Pairing is time-limited and closes after success. Anyone on the LAN who can see
  the PIN during the window can pair; use a trusted network.
- The control port is LAN-only. Do not expose it to the internet.
- No Siri/voice path is implemented; the Siri button is acknowledged and
  ignored.

## Uninstall

```sh
./uninstall.sh            # stop service, remove unit + launcher; keep config/state
./uninstall.sh --purge    # also remove .venv and ~/.config/apple-tv-remote
./uninstall.sh --dry-run
```

The source checkout is never deleted.

## License and credits

**MIT** — the same license as the upstream Companion server this project
adapts, so the code can be reused and extended freely. See `LICENSE`,
`NOTICE.md`, and [`docs/CREDITS.md`](docs/CREDITS.md) for upstream attribution
and the license of every runtime component.

MIT means you may copy, modify, publish, sublicense or sell this code, provided
you keep the copyright and permission notices. If you build on it, keep the
`LICENSE`, `NOTICE.md` and `LICENSES/` files with the code, and say what you
changed. This project is an independent adaptation, not an official port; the
upstream author and Apple do not endorse it.

The Companion server is a Linux adaptation of
[`aryakvn/windows-apple-remote`](https://github.com/aryakvn/windows-apple-remote)
by **Arya Kavian** (MIT). The Apple TV identity and iOS 26/27 handling were
cross-checked against
[`vb3/atvr4samsung`](https://github.com/vb3/atvr4samsung) by **vb3** (MIT).
It also builds on [`pyatv`](https://github.com/postlund/pyatv) by **Pierre Ståhl
(postlund)** (MIT) for Companion/HAP internals. The output layer (uinput,
MPRIS, log), CEC integration, power handling, PIN card and Guide/overlay
behavior are new.

Apple, Apple TV, Siri Remote and related marks are trademarks of Apple Inc.
This project is not affiliated with or endorsed by Apple.

## Roadmap

- **Siri Remote input backend:** reuse the action interface for physical Siri
  Remotes (gen 1 / gen 3), for users who want a real held D-pad.
- **Optional full-desktop mode:** RDP/VNC/Sunshine are deliberately out of
  scope for media navigation.
- **iOS protocol drift:** the main maintenance risk; iOS 26/27 changed touch
  phases, media-control flags and top-shelf requests.
