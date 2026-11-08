# Optional system integration

`install.sh` is deliberately user-level: it never runs `sudo` and never edits
system files. These files are the two optional system changes users normally
want, kept separate so the choice is explicit.

## `/dev/uinput` access

```sh
sudo install -Dm644 contrib/udev/99-uinput.rules /etc/udev/rules.d/99-uinput.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
test -w /dev/uinput && echo writable
```

The rule grants the active local session access via `uaccess` (and the `input`
group). Most desktop distros need this; some already ship an equivalent rule.

## systemd user service

The repository installer generates and enables
`~/.config/systemd/user/apple-tv-remote.service` automatically. For a
`pipx`/system installation, copy the template instead:

```sh
mkdir -p ~/.config/systemd/user
cp contrib/systemd/apple-tv-remote.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now apple-tv-remote
```

On a distro without systemd, run `atv-remote run` from your init system or
session autostart. The bridge itself only needs a user session; `uinput` works
without systemd.
