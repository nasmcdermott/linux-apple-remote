# Requirements

The reference machine is **Fedora 44 KDE Plasma Bigscreen (Wayland)** with an
iPhone running Apple's Apple TV Remote app. The bridge is intentionally
distro-neutral: nothing in the Python package is Fedora-specific.

`install.sh` is user-level. It writes only under `$HOME` and the checkout and
never runs `sudo`. System packages and device permissions are listed separately.

## Hardware

| Item | Required? | Notes |
|---|---|---|
| iPhone or iPad with Apple TV Remote | Yes | Standalone app or the Control Center remote; tested with iOS 26/27. |
| Linux PC on the same LAN | Yes | Advertises itself as an Apple TV over mDNS. |
| HDMI-CEC adapter (`/dev/cec0`, `/dev/cec1`, …) | For CEC | Usually the GPU's HDMI output. Verify with `cec-ctl --playback` or your existing `cec-policy`. |
| TV with CEC enabled | For CEC | Must accept CEC volume/mute and power-on. |
| Physical remote | No | The phone replaces it. A Fire TV remote is handled separately by `fedora-cec-toolkit`. |

## Host operating system

- Linux with **Python 3.11+**.
- Wayland or X11 (or a TTY). Key injection uses `uinput`, below the display
  server.
- A writable `/dev/uinput`.
- Working mDNS/DNS-SD (UDP 5353) and a reachable TCP port (default **47832**).
- systemd is optional; it is only used to run the bridge as a user service.

### `/dev/uinput`

```sh
test -w /dev/uinput && echo writable
```

Temporary, current session only:

```sh
sudo setfacl -m u:"$USER":rw /dev/uinput
```

Persistent, recommended (the repository ships the rule):

```sh
sudo install -Dm644 contrib/udev/99-uinput.rules /etc/udev/rules.d/99-uinput.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

Some distros already grant `uaccess` for `/dev/uinput`; the rule is harmless if
they do.

## Python packages

`install.sh` creates `./.venv` and installs these from `pyproject.toml`:

| Package | Tested | License | Purpose |
|---|---|---|---|
| `pyatv` | 0.18.x | MIT | Companion server auth, HAP SRP, OPACK |
| `srptools` | 1.x (`<2`) | BSD-3-Clause | SRP pair-setup (pyatv 0.18 needs the 1.x API) |
| `zeroconf` | 0.154 | LGPL-2.1-or-later | mDNS/DNS-SD advertisement |
| `cryptography` | 50.x | Apache-2.0 OR BSD-3-Clause | Ed25519/X25519, HKDF, ChaCha20-Poly1305 |
| `evdev` | 2.0 | BSD-3-Clause | `uinput` virtual keyboard |

Base Python environment, per distro:

| Distro | Install |
|---|---|
| Fedora | `sudo dnf install python3 python3-pip` (or `uv`) |
| Debian/Ubuntu | `sudo apt install python3 python3-venv python3-pip` (or `uv`) |
| Arch | `sudo pacman -S python python-pip` (or `uv`) |
| openSUSE | `sudo zypper install python3 python3-pip` (or `uv`) |

## PIN card (GUI)

The PIN is shown by a separate Qt Quick process launched with the **system**
Python (not the project venv):

| Component | Purpose |
|---|---|
| PySide6 (Qt Quick) | Qt Quick runtime and Python bindings |
| `layer-shell-qt` | True top-right layer on KDE Wayland |

Package names vary; search for `pyside6` and `layer-shell` if these are not
exact:

| Distro | Example |
|---|---|
| Fedora | `sudo dnf install python3-pyside6 layer-shell-qt` |
| Debian/Ubuntu | `sudo apt install python3-pyside6.qml` + the Qt6 KDE layer-shell QML module |
| Arch | `sudo pacman -S pyside6 layer-shell-qt` |
| openSUSE | `sudo zypper install python3-pyside6 layer-shell-qt6` |

On GNOME Wayland the card uses a transparent full-screen fallback; on X11 it is
a normal top-right window. Without PySide6, pairing still works: the PIN is in
the journal and `atv-remote pin`.

Colors come from `kdeglobals` (KDE) or `gsettings` (GNOME); no theme package is
required.

### Optional glass blur

```sh
sudo dnf install kwin-effects-better-blur-dx   # Fedora example
```

Enable **Better Blur DX** in *System Settings → Desktop Effects* and make sure
`BlurNonMatching=true` (or add the window class). The card is readable without
it; it is just less glassy.

## Desktop / shell integration

| Component | Needed for |
|---|---|
| KDE Plasma / Plasma Bigscreen | Guide's `activateLauncherMenu`; Tasks “Hold to close…” (Select long-press) |
| systemd user manager | `apple-tv-remote.service` (optional) |
| `busctl`, `gdbus`, or `dbus-send` | Guide button D-Bus call (any one works) |

On a regular KDE/GNOME desktop, `home = "auto"` emits a Meta tap. On GNOME the
Guide button falls back to `KEY_MENU` because `activateLauncherMenu` is
Plasma-specific.

## HDMI-CEC (optional, off by default)

CEC is opt-in: `[cec].enabled = false` is the default. Enable it with
`./install.sh --cec` on a new install, or set `enabled = true` in an existing
config and restart the service. Without it, volume/mute use ordinary media
keys and Power still opens the desktop menu.

The bridge does not link `libcec` and does not touch PipeWire volume. It calls an
existing policy script:

- `cec-policy` on `PATH`
- `/usr/local/bin/cec-policy`
- `/usr/bin/cec-policy`
- `/usr/local/lib/cec-livingroom/cec-policy`
- `~/.local/bin/cec-policy`

The script must support:

```sh
cec-policy volume up
cec-policy volume down
cec-policy volume mute
cec-policy wake --reason powerkey
```

`/dev/cec*` must be readable/writable by the user, usually via the `video`
group or a udev `uaccess` rule.

## Optional media backend (`mpris`)

Without `/dev/uinput`, `backend = "mpris"` supports media/volume only:

```sh
# Fedora
sudo dnf install playerctl wireplumber
# Debian/Ubuntu
sudo apt install playerctl wireplumber
```

It deliberately does not implement arrows, Enter, Guide or Power.

## Network and firewall

- mDNS: UDP 5353 on the LAN.
- Control port: TCP 47832 (or the configured `port`).
- `atv-remote doctor` reports firewalld/ufw hints and the advertised address.

The bridge is LAN-only by design. Do not expose the port to the internet.

## Test and development tools (optional)

```sh
./install.sh --with-tests
# or: uv pip install -e '.[test]'
```

Also useful: `ruff`, `uv`, and Qt's `qmllint` (`qt6-qtdeclarative-devel` on
Fedora). See [`CREDITS.md`](CREDITS.md) for licenses.
