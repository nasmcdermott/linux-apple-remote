#!/usr/bin/env bash
# Remove the user-level installation.  The source checkout is never deleted.
#
#   ./uninstall.sh            stop/remove service + launcher, keep config/state and .venv
#   ./uninstall.sh --purge    also remove .venv and ~/.config/apple-tv-remote

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV="${VENV:-$ROOT/.venv}"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/apple-tv-remote"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT="$UNIT_DIR/apple-tv-remote.service"
PURGE=0
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: ./uninstall.sh [--purge] [--dry-run]

  --purge     also delete .venv and ~/.config/apple-tv-remote (pairings!)
  --dry-run   print what would be removed
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --purge) PURGE=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf 'would run: %q ' "$@"; printf '\n'
  else
    "$@"
  fi
}

if command -v systemctl >/dev/null 2>&1; then
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "would run: systemctl --user disable --now apple-tv-remote.service"
  else
    systemctl --user disable --now apple-tv-remote.service 2>/dev/null || true
  fi
fi

if [[ -f "$UNIT" ]]; then
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "would remove: $UNIT"
  else
    rm -f "$UNIT"
    systemctl --user daemon-reload 2>/dev/null || true
  fi
fi

if [[ -L "$BIN_DIR/atv-remote" || -f "$BIN_DIR/atv-remote" ]]; then
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "would remove: $BIN_DIR/atv-remote"
  else
    rm -f "$BIN_DIR/atv-remote"
  fi
fi

if [[ "$PURGE" -eq 1 ]]; then
  for path in "$VENV" "$CONFIG_DIR"; do
    if [[ -e "$path" ]]; then
      if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "would remove: $path"
      else
        rm -rf -- "$path"
      fi
    fi
  done
fi

if [[ "$DRY_RUN" -eq 0 ]]; then
  echo "Uninstalled."
  if [[ "$PURGE" -eq 0 ]]; then
    echo "Kept config/state in $CONFIG_DIR (use --purge to delete pairings too)."
  fi
fi
