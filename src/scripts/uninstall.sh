#!/usr/bin/env bash
# USB Defense System — uninstaller
#
# Removes the installed daemon, UI, systemd unit, and X11 hardening.
# By default preserves /etc/usb-defense/ (whitelist, hashes, master key)
# and /var/log/usb-defense/ (event log).
#
# Run as root:
#   sudo ./scripts/uninstall.sh           # keep secrets and event log
#   sudo ./scripts/uninstall.sh --wipe    # also wipe secrets and event log

set -euo pipefail

WIPE=0
if [[ "${1:-}" == "--wipe" ]]; then
  WIPE=1
fi

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
# NOTE: not HUPing logind here — same reason install.sh does not:
# re-reading NAutoVTs=0/ReserveVT=0 on a live graphical session can
# drop the active seat and freeze input. The drop-in file is gone, so
# the next reboot picks up the stock defaults.
rm -f /etc/systemd/logind.conf.d/50-usbdefense.conf
rm -f /run/systemd/logind.conf.d/50-usbdefense-lock.conf

# Restore Magic SysRq to the kernel default. install.sh dropped a
# sysctl file at /etc/sysctl.d/99-usbdefense.conf; removing it means
# the next reboot picks up whatever the distribution defaults to. We
# don't `sysctl --system` here — applying it live is harmless but
# unnecessary, and stays consistent with the install-time policy.
rm -f /etc/sysctl.d/99-usbdefense.conf

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

if [[ "$WIPE" -eq 1 ]]; then
  echo "==> Wiping secrets and event log (--wipe was passed)"
  # The event log is +a (append-only); clear that flag before unlinking.
  chattr -a /var/log/usb-defense/events.log 2>/dev/null || true
  rm -rf /etc/usb-defense /var/log/usb-defense /var/lib/usb-defense
fi

echo
echo "================================================================"
echo "  USB Defense System uninstalled."
if [[ "$WIPE" -eq 0 ]]; then
  echo
  echo "  Kept (re-run with --wipe to delete these too):"
  echo "    /etc/usb-defense      (password hash, master key, whitelist)"
  echo "    /var/log/usb-defense  (event log — note: append-only flag)"
  echo "    /var/lib/usb-defense  (persistent lockdown flag)"
fi
echo
echo "  Reboot to clear cached kernel.sysrq + logind defaults:"
echo "      sudo systemctl reboot"
echo "================================================================"
