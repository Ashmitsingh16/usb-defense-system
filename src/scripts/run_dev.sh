#!/usr/bin/env bash
# Development runner — sets up a local virtualenv and launches daemon + UI
# without doing a full system install. Useful for iteration on Rocky.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$PROJECT_ROOT/.venv"

if [[ ! -d "$VENV" ]]; then
  echo "==> Creating local virtualenv"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --upgrade pip wheel
  "$VENV/bin/pip" install -r "$PROJECT_ROOT/requirements.txt"
fi

# Use local config dirs (don't touch /etc)
export USB_DEFENSE_CONFIG="$PROJECT_ROOT/.dev/config.yaml"
mkdir -p "$PROJECT_ROOT/.dev"
[[ -f "$USB_DEFENSE_CONFIG" ]] || cp "$PROJECT_ROOT/config/config.yaml" "$USB_DEFENSE_CONFIG"

case "${1:-ui}" in
  daemon)
    sudo -E "$VENV/bin/python" -m usbguard_defense.daemon
    ;;
  ui)
    "$VENV/bin/python" -m usbguard_defense.ui.main
    ;;
  test)
    "$VENV/bin/python" -m usbguard_defense.tests.simulate
    ;;
  *)
    echo "usage: $0 [daemon|ui|test]"
    exit 1
    ;;
esac
