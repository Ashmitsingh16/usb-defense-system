#!/usr/bin/env bash
# USB Defense System — uninstaller
#
# Removes the installed daemon, UI, systemd unit, and X11 hardening.
# Preserves /etc/usb-defense/ (whitelist, hashes, master key) and
# /var/log/usb-defense/ (event log) — delete those manually if you
# actually want a clean wipe.

set -euo pipefail

if [[ "$EUID" -ne 0 ]]; then
  echo "ERROR: must run as root"
  exit 1
fi

echo "==> Stopping services"
systemctl stop usb-defense.service 2>/dev/null || true
systemctl disable usb-defense.service 2>/dev/null || true

# If the daemon crashed mid-lockdown the getty / autovt units are still
# masked. Always unmask them before walking away so the user isn't
# locked out of their console.
for n in 1 2 3 4 5 6; do
  systemctl unmask "getty@tty${n}.service"  2>/dev/null || true
  systemctl unmask "autovt@tty${n}.service" 2>/dev/null || true
done

# Drop the persistent logind drop-in and the runtime one (if the
# daemon crashed before it could clean up).
rm -f /etc/systemd/logind.conf.d/50-usbdefense.conf
rm -f /run/systemd/logind.conf.d/50-usbdefense-lock.conf
systemctl kill -s HUP systemd-logind.service 2>/dev/null || true

# Restore Magic SysRq to the kernel default. install.sh set it to 0;
# remove the drop-in so the next reboot picks up whatever the
# distribution defaults to.
rm -f /etc/sysctl.d/99-usbdefense.conf
sysctl --system >/dev/null 2>&1 || true

echo "==> Removing files"
rm -f /etc/systemd/system/usb-defense.service
rm -f /etc/xdg/autostart/usb-defense-ui.desktop
rm -f /usr/local/bin/usb-defense-py
rm -f /etc/X11/xorg.conf.d/99-usbdefense-novtswitch.conf
rm -rf /usr/lib/usb-defense
rm -rf /run/usb-defense

# Restore original USBGuard rules if backup exists
if [[ -f /etc/usbguard/rules.conf.original ]]; then
  cp /etc/usbguard/rules.conf.original /etc/usbguard/rules.conf
  echo "  Restored original USBGuard rules"
fi

# Re-enable Wayland in GDM (we explicitly disabled it during install).
# Best-effort: if the user has hand-tuned custom.conf since, leave it.
if [[ -f /etc/gdm/custom.conf ]] && grep -q '^WaylandEnable=false' /etc/gdm/custom.conf; then
  sed -i 's/^WaylandEnable=false/#WaylandEnable=false/' /etc/gdm/custom.conf || true
  echo "  Re-enabled Wayland in GDM (commented out WaylandEnable=false)"
fi

systemctl daemon-reload

# Remove the dedicated group. Group membership isn't preserved across
# uninstalls — operators who reinstall will need to be re-added with
# `usermod -a -G usbdefense <name>`. We skip this if it would orphan
# files we don't own (extremely unlikely on this layout).
if getent group usbdefense >/dev/null; then
  groupdel usbdefense 2>/dev/null || \
    echo "  (could not remove usbdefense group — non-fatal)"
fi

echo
echo "Configuration kept at /etc/usb-defense (delete manually if desired)"
echo "Event log kept at /var/log/usb-defense (delete manually if desired)"
echo
echo "To wipe everything including secrets:"
echo "    sudo rm -rf /etc/usb-defense /var/log/usb-defense /var/lib/usb-defense"
echo
echo "Removal complete. You may need to log out and back in for the"
echo "Wayland change to take effect on the next session."
