# Notices and upstream attribution

**Linux Apple Remote** is an independent Linux adaptation, not a fork of the
upstream project and not affiliated with or endorsed by the upstream author or
Apple Inc. It is MIT-licensed (see `LICENSE`).

The Companion Link server in `src/atv_remote/server.py` is a Linux adaptation of
**windows-apple-remote** by Arya Kavian:

- https://github.com/aryakvn/windows-apple-remote
- MIT License, Copyright (c) 2026 Arya Kavian
- Full license text: `LICENSES/windows-apple-remote-MIT.txt`

The Apple TV identity/TXT record fields and the iOS 26/27 protocol handling were
cross-checked against **atvr4samsung** by vb3:

- https://github.com/vb3/atvr4samsung
- MIT License (see the upstream repository)
- No source files are copied from this project; it is used as a protocol
  reference and for validation.

The Companion protocol also builds on **pyatv** by Pierre Ståhl (postlund),
which is both a runtime dependency and a protocol reference:

- https://github.com/postlund/pyatv
- MIT License
- No source files are copied from this project.

Runtime dependencies keep their own licenses:

- pyatv by Pierre Ståhl (postlund) — MIT
- srptools by Igor Starikov (idlesign) — BSD-3-Clause
- zeroconf by the python-zeroconf authors — LGPL-2.1-or-later
- cryptography by the Python Cryptographic Authority — Apache-2.0 OR
  BSD-3-Clause
- evdev by Georgi Valkov — BSD-3-Clause

The PIN card and Guide button also use KDE/Qt interfaces: Plasma Bigscreen's
`org.kde.PlasmaShell.activateLauncherMenu` D-Bus method, `layer-shell-qt`, Qt 6
and PySide6. Those components keep their own licenses. A complete
component-by-component list is in [`docs/CREDITS.md`](docs/CREDITS.md).

Apple, Apple TV, Siri Remote and related marks are trademarks of Apple Inc.
This project is not affiliated with or endorsed by Apple.
