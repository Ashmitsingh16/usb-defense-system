#!/usr/bin/env bash
# USB Defense System — installer for Rocky Linux 9
#
# Run as root from the project source directory:
#   sudo ./scripts/install.sh

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="/usr/lib/usb-defense"
ETC_DIR="/etc/usb-defense"
LOG_DIR="/var/log/usb-defense"
LIB_DIR="/var/lib/usb-defense"
RUN_DIR="/run/usb-defense"

if [[ "$EUID" -ne 0 ]]; then
  echo "ERROR: must run as root (try: sudo $0)"
  exit 1
fi

echo "==> Installing USB Defense System..."

echo "==> Step 1/8: Installing system packages (this may take a while)"
# Note: on Rocky/RHEL, venv ships with the base python3 package — there is no separate python3-venv.
dnf install -y \
  python3 python3-pip \
  usbguard \
  alsa-utils \
  pulseaudio-utils \
  libnotify \
  --setopt=install_weak_deps=False

echo "==> Step 2/8: Creating directories"
mkdir -p "$INSTALL_DIR" "$ETC_DIR" "$LOG_DIR" "$LIB_DIR" "$INSTALL_DIR/assets"

echo "==> Step 3/8: Copying source code"
cp -r "$PROJECT_ROOT/usbguard_defense" "$INSTALL_DIR/"
cp -f "$PROJECT_ROOT/pyproject.toml" "$INSTALL_DIR/" 2>/dev/null || true
cp -f "$PROJECT_ROOT/requirements.txt" "$INSTALL_DIR/" 2>/dev/null || true
cp -r "$PROJECT_ROOT/assets/." "$INSTALL_DIR/assets/" 2>/dev/null || \
  echo "  (no assets to copy yet — alarm.wav must be placed manually)"

echo "==> Step 4/8: Creating Python virtualenv and installing package"
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip wheel setuptools
# Proper editable install via pyproject.toml — replaces the previous
# symlink-into-site-packages hack. Installs PyQt5/pyudev/PyYAML as deps.
"$INSTALL_DIR/venv/bin/pip" install -e "$INSTALL_DIR/"

echo "==> Step 5/8: Installing config files"
[[ -f "$ETC_DIR/config.yaml" ]] || cp "$PROJECT_ROOT/config/config.yaml" "$ETC_DIR/"
[[ -f "$ETC_DIR/whitelist.json" ]] || cp "$PROJECT_ROOT/config/whitelist.json" "$ETC_DIR/"
chmod 600 "$ETC_DIR/whitelist.json"
chown root:root "$ETC_DIR/whitelist.json"

echo "==> Step 6/8: Configuring USBGuard"
[[ -f /etc/usbguard/rules.conf.original ]] || \
  cp /etc/usbguard/rules.conf /etc/usbguard/rules.conf.original 2>/dev/null || true
cp "$PROJECT_ROOT/config/usbguard-rules.conf" /etc/usbguard/rules.conf
systemctl enable --now usbguard

echo "==> Step 7/8: Installing systemd service"
cp "$PROJECT_ROOT/systemd/usb-defense.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable usb-defense.service

echo "==> Step 8/8: Installing UI launcher"
mkdir -p /etc/xdg/autostart
cp "$PROJECT_ROOT/systemd/usb-defense-ui.desktop" /etc/xdg/autostart/
ln -sfn "$INSTALL_DIR/venv/bin/python" /usr/local/bin/usb-defense-py

# Make append-only event log
touch "$LOG_DIR/events.log"
chown root:root "$LOG_DIR/events.log"
chmod 600 "$LOG_DIR/events.log"
chattr +a "$LOG_DIR/events.log" 2>/dev/null || \
  echo "  (chattr +a failed — filesystem may not support it)"

echo
echo "================================================================"
echo "  USB Defense System installed successfully!"
echo
echo "  To start the daemon now:    sudo systemctl start usb-defense"
echo "  To check daemon status:     sudo systemctl status usb-defense"
echo "  To view daemon logs:        sudo journalctl -u usb-defense -f"
echo "  To open the UI:             usb-defense-py -m usbguard_defense.ui.main"
echo
echo "  Config files:               $ETC_DIR/"
echo "  Source code:                $INSTALL_DIR/usbguard_defense/"
echo "  Event log:                  $LOG_DIR/events.log"
echo
echo "  IMPORTANT: place an alarm sound at $INSTALL_DIR/assets/alarm.wav"
echo "             before triggering lockdown — otherwise no audio."
echo "================================================================"
