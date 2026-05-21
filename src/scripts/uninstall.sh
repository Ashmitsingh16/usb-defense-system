#!/usr/bin/env bash
# USB Defense System — uninstaller

set -euo pipefail

if [[ "$EUID" -ne 0 ]]; then
  echo "ERROR: must run as root"
  exit 1
fi

echo "==> Stopping services"
systemctl stop usb-defense.service 2>/dev/null || true
systemctl disable usb-defense.service 2>/dev/null || true

echo "==> Removing files"
rm -f /etc/systemd/system/usb-defense.service
rm -f /etc/xdg/autostart/usb-defense-ui.desktop
rm -f /usr/local/bin/usb-defense-py
rm -rf /usr/lib/usb-defense
rm -rf /run/usb-defense

# Restore original USBGuard rules if backup exists
if [[ -f /etc/usbguard/rules.conf.original ]]; then
  cp /etc/usbguard/rules.conf.original /etc/usbguard/rules.conf
  echo "  Restored original USBGuard rules"
fi

systemctl daemon-reload

echo
echo "Configuration kept at /etc/usb-defense (delete manually if desired)"
echo "Event log kept at /var/log/usb-defense (delete manually if desired)"
echo "Removal complete."
