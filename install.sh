#!/usr/bin/env bash
# Install the Apple TV Remote bridge for the current user.
#
# Writes only under $HOME and this checkout:
#   .venv/                                  Python environment
#   ~/.local/bin/atv-remote                 launcher symlink
#   ~/.config/apple-tv-remote/              config + pairing state
#   ~/.config/systemd/user/                 optional user service
#
# It never uses sudo and never edits system files.

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV="${VENV:-$ROOT/.venv}"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/apple-tv-remote"
CONFIG="$CONFIG_DIR/config.toml"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT="$UNIT_DIR/apple-tv-remote.service"
NAME="${NAME:-$(uname -n)}"
PORT="${PORT:-47832}"
ADDRESS="${ADDRESS:-}"
BACKEND="${BACKEND:-uinput}"
PAIRING_WINDOW="${PAIRING_WINDOW:-600}"
WITH_CEC="${WITH_CEC:-0}"
PIN_DISPLAY="${PIN_DISPLAY:-auto}"
INSTALL_SERVICE=1
FORCE_CONFIG=0
WITH_TESTS=0

usage() {
  cat <<'EOF'
Usage: ./install.sh [options]

Options:
  --name NAME             name shown on the iPhone (default: hostname)
  --port PORT             TCP control port (default: 47832; 0 = random)
  --address ADDR          IPv4 address to advertise (default: auto-detect)
  --backend NAME          uinput (default), mpris, or log
  --pairing-window SEC    seconds a new pairing is accepted (default: 600)
  --cec                   opt in to HDMI-CEC volume/mute/TV-on
  --no-cec                keep CEC off (default)
  --pin-display MODE      auto (GUI if available), qt, notification, none
  --venv PATH             Python environment location (default: ./.venv)
  --no-service            install files but do not create/enable a systemd user unit
  --force-config          overwrite an existing config.toml
  --with-tests            also install pytest/pytest-asyncio
  -h, --help              show this help

Environment: NAME, PORT, ADDRESS, BACKEND, PAIRING_WINDOW, WITH_CEC,
             PIN_DISPLAY, VENV, BIN_DIR
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name) NAME="${2:?missing value}"; shift 2 ;;
    --port) PORT="${2:?missing value}"; shift 2 ;;
    --address) ADDRESS="${2:?missing value}"; shift 2 ;;
    --backend) BACKEND="${2:?missing value}"; shift 2 ;;
    --pairing-window) PAIRING_WINDOW="${2:?missing value}"; shift 2 ;;
    --cec) WITH_CEC=1; shift ;;
    --no-cec) WITH_CEC=0; shift ;;
    --pin-display) PIN_DISPLAY="${2:?missing value}"; shift 2 ;;
    --venv) VENV="${2:?missing value}"; shift 2 ;;
    --no-service) INSTALL_SERVICE=0; shift ;;
    --force-config) FORCE_CONFIG=1; shift ;;
    --with-tests) WITH_TESTS=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$BACKEND" in
  uinput|mpris|log) ;;
  *) echo "error: --backend must be uinput, mpris or log" >&2; exit 2 ;;
esac
case "$PIN_DISPLAY" in
  auto|qt|notification|none) ;;
  *) echo "error: --pin-display must be auto, qt, notification or none" >&2; exit 2 ;;
esac

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "error: $PYTHON not found (need Python 3.11+)" >&2
  exit 1
fi
if ! "$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "error: Python 3.11+ required (found $("$PYTHON" -V 2>&1))" >&2
  exit 1
fi

# The PIN card runs in the *system* Python (not the project venv), because
# distros ship PySide6 as a system package.  Accept any python3 that can
# import it, including an explicit ATV_PIN_GUI_PYTHON override.
if [[ "$PIN_DISPLAY" == "auto" || "$PIN_DISPLAY" == "qt" ]]; then
GUI_PYTHON=""
for candidate in "${ATV_PIN_GUI_PYTHON:-}" python3 /usr/bin/python3; do
  [[ -n "$candidate" ]] || continue
  command -v "$candidate" >/dev/null 2>&1 || continue
  if "$candidate" -c 'import PySide6' >/dev/null 2>&1; then
    GUI_PYTHON="$candidate"
    break
  fi
done
if [[ -z "$GUI_PYTHON" ]]; then
  cat >&2 <<'EOF'
note: PySide6 (Qt Quick) was not found, so the top-right PIN card will not
      appear. Pairing still works: the PIN is printed in the log and available
      with 'atv-remote pin'.
      Install the distro package for PySide6 QtQuick, e.g.:
        Fedora:        sudo dnf install python3-pyside6
        Debian/Ubuntu: sudo apt install python3-pyside6.qml
        Arch:          sudo pacman -S pyside6
        openSUSE:      sudo zypper install python3-pyside6
      Then run ./install.sh again (or set ATV_PIN_GUI_PYTHON=/path/to/python3).
EOF
fi

HAVE_LAYERSHELL=0
for root in \
  /usr/lib64/qt6/qml \
  /usr/lib/qt6/qml \
  /usr/local/lib64/qt6/qml \
  /usr/local/lib/qt6/qml \
  /usr/lib/*/qt6/qml; do
  if [[ -d "$root/org/kde/layershell" ]]; then
    HAVE_LAYERSHELL=1
    break
  fi
done
if [[ "$HAVE_LAYERSHELL" -eq 0 && "${XDG_CURRENT_DESKTOP:-}" == *KDE* ]]; then
  cat >&2 <<'EOF'
note: the layer-shell-qt QML plugin was not found; the PIN card will use a
      transparent full-screen fallback instead of a true top-right layer.
      Install layer-shell-qt with your package manager (it is normally part of
      Plasma), e.g. sudo dnf install layer-shell-qt.
EOF
fi
fi  # PIN_DISPLAY == auto|qt

if [[ "$PIN_DISPLAY" == "notification" ]] && ! command -v notify-send >/dev/null 2>&1; then
  cat >&2 <<'EOF'
note: pin_display = "notification" was requested, but notify-send was not
      found. The PIN will only appear in the log and with 'atv-remote pin'.
      Install libnotify (package name: libnotify / libnotify-bin) if you want
      desktop notifications.
EOF
fi

# CEC is opt-in.  Only print hints; the install itself never depends on it.
CEC_POLICY=""
for candidate in \
  "$(command -v cec-policy 2>/dev/null || true)" \
  /usr/local/bin/cec-policy \
  /usr/bin/cec-policy \
  "$HOME/.local/bin/cec-policy"; do
  if [[ -n "$candidate" && -x "$candidate" ]]; then
    CEC_POLICY="$candidate"
    break
  fi
done
if [[ "$WITH_CEC" -eq 1 && -z "$CEC_POLICY" ]]; then
  cat >&2 <<'EOF'
warning: --cec was requested, but cec-policy was not found. CEC volume/mute
         will fall back to ordinary media keys and Power still opens the
         desktop menu. Install cec-policy (fedora-cec-toolkit) or set
         [cec].policy to your own script, then restart the service.
EOF
elif [[ "$WITH_CEC" -eq 0 && -n "$CEC_POLICY" ]]; then
  cat >&2 <<EOF
note: cec-policy was found at $CEC_POLICY, but CEC is opt-in and stays off.
      Enable it with:  ./install.sh --cec --force-config
      or set '[cec] enabled = true' in $CONFIG and restart the service.
EOF
fi

echo "==> Installing into $ROOT"
install_args=(-e "$ROOT")
if [[ "$WITH_TESTS" -eq 1 ]]; then
  install_args+=("pytest>=8" "pytest-asyncio>=0.23")
fi
if command -v uv >/dev/null 2>&1; then
  if [[ ! -x "$VENV/bin/python" ]]; then
    uv venv --python "$PYTHON" "$VENV"
  fi
  uv pip install --python "$VENV/bin/python" "${install_args[@]}"
else
  if [[ ! -x "$VENV/bin/python" ]]; then
    "$PYTHON" -m venv "$VENV"
  fi
  if ! "$VENV/bin/python" -m pip --version >/dev/null 2>&1; then
    echo "error: pip is missing from the venv. Install uv (recommended) or python3-pip." >&2
    exit 1
  fi
  "$VENV/bin/python" -m pip install --upgrade pip >/dev/null
  "$VENV/bin/pip" install "${install_args[@]}"
fi

mkdir -p "$BIN_DIR" "$CONFIG_DIR"
if [[ ! -f "$CONFIG" || "$FORCE_CONFIG" -eq 1 ]]; then
  init_args=(--name "$NAME" --port "$PORT" --backend "$BACKEND" --pairing-window "$PAIRING_WINDOW")
  if [[ -n "$ADDRESS" ]]; then init_args+=(--address "$ADDRESS"); fi
  if [[ "$WITH_CEC" -eq 1 ]]; then init_args+=(--cec); fi
  if [[ "$PIN_DISPLAY" != "auto" ]]; then init_args+=(--pin-display "$PIN_DISPLAY"); fi
  if [[ "$FORCE_CONFIG" -eq 1 ]]; then init_args+=(--force); fi
  "$VENV/bin/atv-remote" --config "$CONFIG" config init "${init_args[@]}" >/dev/null
  echo "==> Wrote config: $CONFIG"
else
  echo "==> Keeping existing config: $CONFIG"
  if [[ "$WITH_CEC" -eq 1 || "$PIN_DISPLAY" != "auto" || -n "$ADDRESS" ]]; then
    cat <<EOF
note: --cec/--pin-display/--address apply only to a newly written config.
      Edit $CONFIG or rerun with --force-config to rewrite it.
EOF
  fi
fi

ln -sfn "$VENV/bin/atv-remote" "$BIN_DIR/atv-remote"
echo "==> Launcher: $BIN_DIR/atv-remote"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "note: $BIN_DIR is not in PATH; use $VENV/bin/atv-remote or add it to PATH" ;;
esac

if [[ ! -w /dev/uinput ]]; then
  cat >&2 <<EOF

warning: /dev/uinput is not writable, so the uinput backend will not work.
  temporary:  sudo setfacl -m u:$(id -un):rw /dev/uinput
  persistent (recommended, one sudo command):
      sudo install -Dm644 "$ROOT/contrib/udev/99-uinput.rules" \\
        /etc/udev/rules.d/99-uinput.rules
      sudo udevadm control --reload-rules && sudo udevadm trigger
  or run:     sudo "$VENV/bin/atv-remote" --config "$CONFIG" run
  or media-only fallback:
              ./install.sh --backend mpris --force-config
EOF
fi

if command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state >/dev/null 2>&1; then
  if ! firewall-cmd --query-port=5353/udp >/dev/null 2>&1; then
    cat >&2 <<'EOF'

note: firewalld is running and mDNS (UDP 5353) is not open.
  The iPhone discovers the bridge over mDNS.  This is a system firewall change,
  so this installer does not do it for you.  Optional:
    temporary:  sudo firewall-cmd --add-service=mdns
    permanent:  sudo firewall-cmd --permanent --add-service=mdns && sudo firewall-cmd --reload
EOF
  fi
fi

if [[ "$INSTALL_SERVICE" -eq 1 ]] && command -v systemctl >/dev/null 2>&1; then
  mkdir -p "$UNIT_DIR"
  cat >"$UNIT" <<EOF
[Unit]
Description=Linux Apple Remote bridge (iPhone/iPad Companion remote)
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=simple
ExecStart="$VENV/bin/atv-remote" --config "$CONFIG" run
WorkingDirectory=$ROOT
Restart=on-failure
RestartSec=3
TimeoutStopSec=10
Environment=PYTHONUNBUFFERED=1
SyslogIdentifier=apple-tv-remote

[Install]
WantedBy=default.target
EOF
  echo "==> Wrote user unit: $UNIT"
  if systemctl --user daemon-reload 2>/dev/null; then
    # Clear a previous start-limit failure (for example after an upgrade that
    # briefly removed the launcher).
    systemctl --user reset-failed apple-tv-remote.service 2>/dev/null || true
    systemctl --user enable apple-tv-remote.service 2>/dev/null || true
    if systemctl --user is-active --quiet apple-tv-remote.service 2>/dev/null; then
      systemctl --user restart apple-tv-remote.service 2>/dev/null \
        && echo "==> Restarted apple-tv-remote.service"
    elif systemctl --user start apple-tv-remote.service 2>/dev/null; then
      echo "==> Started apple-tv-remote.service"
    else
      echo "note: could not start the user service (no user systemd session?)."
      echo "      run it in the foreground: $VENV/bin/atv-remote --config \"$CONFIG\" run"
    fi
  else
    echo "note: could not reach the user systemd manager."
    echo "      run it in the foreground: $VENV/bin/atv-remote --config \"$CONFIG\" run"
  fi
fi

DOCTOR_OUT="$("$VENV/bin/atv-remote" --config "$CONFIG" doctor 2>/dev/null || true)"
EFFECTIVE_NAME="$(printf '%s\n' "$DOCTOR_OUT" | sed -n 's/^name:    //p')"
EFFECTIVE_NAME="${EFFECTIVE_NAME:-$NAME}"
EFFECTIVE_BACKEND="$(printf '%s\n' "$DOCTOR_OUT" | sed -n 's/^backend: //p')"
EFFECTIVE_CEC="$(printf '%s\n' "$DOCTOR_OUT" | sed -n 's/^cec:     enabled=\([^ ]*\).*/\1/p')"
EFFECTIVE_PIN="$(printf '%s\n' "$DOCTOR_OUT" | sed -n 's/^pin display: mode=\([^ ]*\).*/\1/p')"

cat <<EOF

Installed.
Enabled: backend=${EFFECTIVE_BACKEND:-$BACKEND}, CEC=${EFFECTIVE_CEC:-false}, PIN=${EFFECTIVE_PIN:-auto}

Next steps:
  1. Open the pairing window:       atv-remote pair
  2. On the iPhone: open the Apple TV Remote app and select "$EFFECTIVE_NAME"
  3. Enter the 4-digit PIN shown in the top-right card
     (or run 'atv-remote pin' / read the service log).
  4. Test keys:                     atv-remote doctor
  5. Change mappings:               $CONFIG
EOF

if [[ "$INSTALL_SERVICE" -eq 1 ]]; then
  cat <<EOF

     Watch the log:                 journalctl --user -u apple-tv-remote -f
     Run in foreground:             $VENV/bin/atv-remote --config "$CONFIG" run -v
EOF
else
  cat <<EOF

     No service was installed.  Run in the foreground:
       $VENV/bin/atv-remote --config "$CONFIG" run -v
EOF
fi

cat <<EOF

Uninstall:
  $ROOT/uninstall.sh            # remove service + launcher
  $ROOT/uninstall.sh --purge    # also remove .venv and pairing state
EOF
