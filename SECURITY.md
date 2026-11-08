# Security

## Reporting

Open a private security advisory on GitHub, or email the maintainer listed in
`pyproject.toml`. Please do not publish a working exploit before a fix.

## What this project does

The bridge advertises a Linux machine as an Apple TV over Apple's undocumented
Companion Link protocol and injects input events through `/dev/uinput`. That is
powerful by design: a paired phone can send keys to the focused desktop.

## Operational guidance

- Treat `~/.config/apple-tv-remote/state.json` as a credential (mode 0600).
- Use the pairing window only on a trusted LAN. Anyone who can see the PIN can
  pair while the window is open.
- Never expose the control port (default 47832) to the internet.
- Do not run the daemon as root. Grant `/dev/uinput` and `/dev/cec*` to the
  session user instead (see `contrib/udev/` and `docs/REQUIREMENTS.md`).
- The PIN card passes the PIN in a short-lived local subprocess argument; it is
  visible to the same user in `ps`. The PIN is also in the journal and
  `last-pin` by design.
