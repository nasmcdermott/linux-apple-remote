# Credits and upstream licenses

This project is released under the **MIT License** (see `LICENSE`). It would not
exist without the following projects, libraries, and desktop components. The
list is split into code we adapted, protocol references, Python dependencies,
and the Linux/KDE software whose public interfaces we call.

## Code we adapted

### windows-apple-remote — MIT

- Author: Arya Kavian
- https://github.com/aryakvn/windows-apple-remote
- License text: [`LICENSES/windows-apple-remote-MIT.txt`](../LICENSES/windows-apple-remote-MIT.txt)

`src/atv_remote/server.py` is a Linux adaptation of its Companion Link server.
The HAP pair-setup/pair-verify flow, OPACK framing, Companion `_hidC` button
decoding, `_hidT` touch decoding, and the Apple TV identity/TXT-record shape
start from that project. The Windows key sink was replaced with Linux `uinput`
(plus `mpris` and `log` fallbacks), and the CEC, power, pairing-PIN, and
Guide/overlay behavior are new.

## Protocol references (no source copied)

### atvr4samsung — MIT

- Author: vb3
- https://github.com/vb3/atvr4samsung

Used to cross-check the Apple TV identity/TXT record (`rpMd`, `rpVr`, `rpFl`)
and iOS 26/27 Companion behavior. No source files are copied from it.

### pyatv — MIT

- Author: Pierre Ståhl (postlund)
- https://github.com/postlund/pyatv

`pyatv` is a runtime dependency, but its Companion client and protocol
implementation were also used as the reference for the `_hBtS` press/release
semantics (`1` = down, `2` = up), the `_hidC` action codes, and the
`FetchMediaControlStatus` / `_mcc` messages. The end-to-end test uses pyatv's
Companion client as the phone side.

### Apple Companion Link (unofficial)

Apple does not document the Companion Link remote protocol. The message names
and fields here were derived from the open-source projects above and from
observed traffic. No Apple source code or binaries are included. Apple, Apple
TV, Siri Remote, and related marks are trademarks of Apple Inc.; this project
is not affiliated with or endorsed by Apple.

## Runtime Python dependencies

| Package | Author / project | Version tested | License | What we use |
|---|---|---|---|---|
| `pyatv` | Pierre Ståhl (postlund) — https://github.com/postlund/pyatv | 0.18.x | MIT | `CompanionServerAuth`, HAP SRP, Ed25519/X25519, ChaCha20-Poly1305 OPACK framing |
| `srptools` | Igor Starikov (idlesign) — https://github.com/idlesign/srptools | 1.x | BSD-3-Clause | SRP pair-setup math (pinned below 2.0 because pyatv 0.18 uses the 1.x constructor) |
| `zeroconf` | The python-zeroconf authors, maintained by J. Nick Koston — https://github.com/python-zeroconf/python-zeroconf | 0.154 | LGPL-2.1-or-later | mDNS/DNS-SD advertisement of the fake Apple TV |
| `cryptography` | The Python Cryptographic Authority and contributors — https://github.com/pyca/cryptography | 50.x | Apache-2.0 OR BSD-3-Clause | Ed25519, X25519, HKDF, ChaCha20-Poly1305 |
| `evdev` | Georgi Valkov — https://github.com/gvalkov/python-evdev | 2.0 | BSD-3-Clause | `uinput` virtual keyboard and Linux key-code names |

## Linux and KDE software whose interfaces we use

These are not vendored or linked into the Python package. They are runtime
interfaces, desktop services, or optional effects.

| Software | Author / project | License (Fedora package) | How it is used |
|---|---|---|---|
| Linux kernel `uinput` / `evdev` | Linux kernel contributors — https://kernel.org | GPL-2.0-only | The virtual keyboard that injects keys below Wayland/X11 |
| systemd user services | systemd contributors — https://systemd.io | LGPL-2.1-or-later | `apple-tv-remote.service` and `systemctl --user` |
| `busctl` (systemd) | systemd contributors | LGPL-2.1-or-later | Guide button calls `org.kde.PlasmaShell.activateLauncherMenu` |
| KDE Plasma / Plasma Bigscreen | KDE Community — https://kde.org | GPL-2.0-or-later (mixed) | `activateLauncherMenu` D-Bus API; Bigscreen's hold-to-close task gesture that Select long-press drives |
| KWin Better Blur DX | KWin effects contributors | GPL-3.0 (Fedora); source headers GPL-2.0-or-later | Optional compositor blur behind the translucent PIN card |
| layer-shell-qt | KDE Community | BSD-3-Clause AND CC0-1.0 AND LGPL-3.0-or-later AND MIT | `org.kde.layershell` QML surface for the top-right PIN card on KDE Wayland |
| Qt 6 / Qt Quick | The Qt Company and contributors — https://qt.io | LGPL-3.0-only OR GPL-3.0-only WITH Qt-GPL-exception-1.0 | QML runtime for the PIN card |
| PySide6 | Qt for Python contributors | LGPL-3.0-only OR GPL-3.0-only WITH Qt-GPL-exception-1.0 | Python bindings that launch the PIN card |
| libcec | Pulse-Eight Limited — https://github.com/Pulse-Eight/libcec | GPL-2.0-or-later | Used by Plasma Bigscreen's CEC input handler; this project calls `cec-policy` instead of linking libcec |
| `libnotify` / `notify-send` | GNOME contributors — https://gitlab.gnome.org/GNOME/libnotify | LGPL-2.1-or-later | Optional opt-in PIN notification |
| WirePlumber (`wpctl`) | PipeWire team and contributors — https://pipewire.pages.freedesktop.org/wireplumber/ | MIT | Optional `mpris` backend volume control |
| PulseAudio utilities (`pactl`) | Lennart Poettering and contributors — https://www.freedesktop.org/wiki/Software/PulseAudio/ | LGPL-2.1-or-later | Optional `mpris` backend fallback |
| `playerctl` | Tony Crisci and contributors — https://github.com/altdesktop/playerctl | LGPL-3.0-or-later | Optional `mpris` backend media control |
| firewalld | firewalld contributors — https://firewalld.org | GPL-2.0-or-later | Runtime firewall check in `atv-remote doctor`; mDNS must be allowed |

## Companion projects by the same author

These are separate projects by the Linux Apple Remote maintainer and are
referenced, not bundled:

- **fedora-cec-toolkit** — owns `/usr/local/bin/cec-policy` and the Fire TV
  remote volume/power observer. The Apple bridge calls `cec-policy` for CEC
  volume, mute, and TV wake.
- **fire-remote-client** — documents the Fire TV remote's Menu consumer usage
  (`0x0040` → `KEY_MENU`) and uses
  `org.kde.PlasmaShell.activateLauncherMenu` to open the Bigscreen home overlay.
  The Guide mapping uses that same D-Bus call.

## Test and build tooling

| Tool | Author / project | License | Use |
|---|---|---|---|
| pytest | pytest-dev contributors — https://pytest.org | MIT | Unit/integration tests |
| pytest-asyncio | pytest-dev contributors | Apache-2.0 | Async Companion server tests |
| Ruff | Astral Software — https://astral.sh/ruff | MIT | Linting |
| uv | Astral Software — https://astral.sh/uv | Apache-2.0 OR MIT | Virtualenv and wheel build |
| hatchling | Ofek Lev and contributors — https://hatch.pypa.io | MIT | Build backend |
| Qt `qmllint` | The Qt Company and contributors | LGPL-3.0-only OR GPL-3.0-only WITH Qt-GPL-exception-1.0 | QML lint |

## Fonts and icons

The PIN card uses the host's configured UI font (for example `SF Pro Text` on
this machine) and draws its small TV glyph with QML primitives, so it does not
bundle or redistribute any font or icon artwork. KDE's icon theme is not
required by the card.
