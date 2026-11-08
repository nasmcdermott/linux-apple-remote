# Notices and upstream attribution

This project is MIT-licensed (see `LICENSE`).

The Companion Link server in `src/atv_remote/server.py` is a Linux adaptation of
**windows-apple-remote** by Arya Kavian:

- https://github.com/aryakvn/windows-apple-remote
- MIT License, Copyright (c) 2026 Arya Kavian
- Full license text: `LICENSES/windows-apple-remote-MIT.txt`

The Apple TV identity/TXT record fields and the iOS 26/27 protocol handling were
cross-checked against **atvr4samsung** by vb3:

- https://github.com/vb3/atvr4samsung
- MIT License
- No source files are copied from this project; it is used as a protocol
  reference and for validation.

Runtime dependencies keep their own licenses:

- pyatv (MIT), zeroconf (LGPL-2.1-or-later), cryptography (Apache-2.0/BSD),
  evdev (BSD-3-Clause).

The PIN card and Guide button also use KDE/Qt interfaces: Plasma Bigscreen's
`org.kde.PlasmaShell.activateLauncherMenu` D-Bus method, `layer-shell-qt`, Qt 6
and PySide6. Those components keep their own licenses. A complete
component-by-component list is in [`docs/CREDITS.md`](docs/CREDITS.md).

Apple, Apple TV, Siri Remote and related marks are trademarks of Apple Inc.
This project is not affiliated with or endorsed by Apple.
