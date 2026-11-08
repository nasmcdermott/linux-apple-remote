# Packaging and publishing

## Recommended release format

**Ship it as a source checkout with `install.sh`, plus a Python wheel.**

That matches what the bridge actually needs:

- `/dev/uinput` access (a host kernel device)
- optional `/dev/cec*` access
- the user's session D-Bus (`org.kde.PlasmaShell`)
- LAN mDNS (UDP 5353) and a LAN control port
- the system Python + system PySide6 for the PIN card

A Python package + a user systemd unit is the smallest thing that can grant
those. It also keeps the install user-level and auditable.

### Why not the alternatives

| Format | Verdict | Reason |
|---|---|---|
| **Flatpak** | Not recommended | Needs `--device=all` for uinput/CEC, host D-Bus for plasmashell, and LAN mDNS. The sandbox adds friction without solving distribution. |
| **Snap** | Not recommended | Same device/D-Bus confinement problems; `uinput` and CEC are not classic-snap friendly. |
| **Docker / Podman** | Not recommended | Wrong layer: the bridge must inject input into the *host* session and call host D-Bus. A container cannot do that cleanly. |
| **AppImage** | Not recommended | Still needs host Python/PySide6 and uinput; adds a bundling layer for little gain. |
| **`.rpm` / `.deb`** | Later, optional | Nice for distro users, but needs packaging per distro and udev/polkit review. `nfpm` can generate both from one spec. |
| **PyPI + pipx** | Recommended next | Cross-distro, simple upgrade path, and `contrib/systemd/` supplies the unit. |

## GitHub upload

The repository is already prepared with `LICENSE`, `NOTICE.md`, `.gitignore`,
CI, tests and the install scripts. From the checkout:

```sh
git init -b main
git add -A
git commit -m "Initial public release"

# With the GitHub CLI (recommended):
gh repo create apple-tv-remote --public --source=. --remote=origin --push

# Or create the repository on github.com, then:
git remote add origin git@github.com:OWNER/apple-tv-remote.git
git push -u origin main
```

Replace `OWNER` in `pyproject.toml` (`[project.urls]`) and in the README clone
URL before publishing. Use a GitHub release tag such as `v0.1.0`.

### Release checklist

```sh
.venv/bin/pytest -q
uvx ruff check src tests scripts
.venv/bin/python scripts/e2e_test.py
.venv/bin/python -m build          # wheel + sdist (install `build` first)
```

Attach the wheel and sdist to the GitHub release. The wheel includes the QML
card files; the sdist includes docs, tests, contrib and the install scripts.

## PyPI (recommended follow-up)

```sh
python -m build
python -m twine upload dist/*
```

Then users can install without the checkout:

```sh
pipx install apple-tv-remote-linux
mkdir -p ~/.config/systemd/user
cp contrib/systemd/apple-tv-remote.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now apple-tv-remote
```

The PIN card still uses the system Python + PySide6; the pipx environment only
runs the daemon and the uinput/mDNS code.

## License choice

**MIT** is already in `LICENSE` and is the right default here:

- it matches the upstream `windows-apple-remote` Companion server and pyatv;
- it is compatible with redistributing the adapted server code;
- it is the least friction for other users who want to add a Siri Remote
  backend or package the bridge.

Use **Apache-2.0** instead only if explicit patent protection matters more than
simplicity. Do not use GPL for the combined work unless every adapted file is
compatible; the current adaptation is MIT, so MIT keeps the whole tree simple.
