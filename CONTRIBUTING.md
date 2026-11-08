# Contributing

Thanks for helping. The project is small and the interfaces are deliberately
stable.

## Development setup

```sh
python3 -m venv .venv
./install.sh --with-tests
.venv/bin/python scripts/e2e_test.py
.venv/bin/pytest -q
uvx ruff check src tests scripts
```

The end-to-end test does not need an iPhone: it pairs with pyatv's Companion
client and checks the Linux key events produced by the virtual keyboard.

## Design boundaries

- `src/atv_remote/keymap.py` is the stable action interface. A new input backend
  (for example a physical Siri Remote) should emit those action names.
- `src/atv_remote/output.py` owns Linux key injection. Keep distro-specific
  commands optional and behind `shutil.which()`.
- `src/atv_remote/server.py` owns the Companion protocol. Keep it free of
  desktop-specific code.
- The PIN card is a separate process (`pin_gui.py` + QML) so the daemon never
  depends on PySide6.

## Pull requests

- Add or update a test for behavior changes.
- Run `ruff` and `pytest` before opening the PR.
- Keep system changes out of `install.sh`; put optional udev/systemd files in
  `contrib/` and document the sudo command.
- Do not add a bundled binary, Apple code, or a dependency with an incompatible
  license. See `NOTICE.md` and `docs/CREDITS.md`.
