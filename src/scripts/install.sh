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

# Tracks whether step 7 staged hardening that needs a reboot to take effect.
REBOOT_REQUIRED=0

echo "==> Installing USB Defense System..."

echo "==> Step 1/9: Installing system packages (this may take a while)"
# Note: on Rocky/RHEL, venv ships with the base python3 package — there is no separate python3-venv.
# X11 is installed alongside Wayland so the lockdown overlay has a working
# grabKeyboard/grabMouse path. v0.2 defaults to X11; Wayland is opt-in.
dnf install -y \
  python3 python3-pip \
  usbguard \
  alsa-utils \
  pulseaudio-utils \
  libnotify \
  xorg-x11-server-Xorg xorg-x11-xinit \
  xcb-util xcb-util-image xcb-util-keysyms \
  xcb-util-renderutil xcb-util-wm xcb-util-cursor \
  libxkbcommon-x11 \
  --setopt=install_weak_deps=False

echo "==> Step 2/9: Creating directories and 'usbdefense' group"
mkdir -p "$INSTALL_DIR" "$ETC_DIR" "$LOG_DIR" "$LIB_DIR" "$INSTALL_DIR/assets"
# The IPC socket is owned by root:usbdefense (0660) so only users in this
# group can talk to the daemon. Add the installing user (if any).
groupadd -f usbdefense
if [[ -n "${SUDO_USER:-}" && "$SUDO_USER" != "root" ]]; then
  usermod -a -G usbdefense "$SUDO_USER" || true
  echo "  Added $SUDO_USER to usbdefense group (re-login required for it to take effect)"
fi

echo "==> Step 3/9: Copying source code"
cp -r "$PROJECT_ROOT/usbguard_defense" "$INSTALL_DIR/"
cp -f "$PROJECT_ROOT/pyproject.toml" "$INSTALL_DIR/" 2>/dev/null || true
cp -f "$PROJECT_ROOT/requirements.txt" "$INSTALL_DIR/" 2>/dev/null || true
cp -r "$PROJECT_ROOT/assets/." "$INSTALL_DIR/assets/" 2>/dev/null || \
  echo "  (no assets to copy yet — alarm.wav must be placed manually)"

echo "==> Step 4/9: Creating Python virtualenv and installing package"
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip wheel setuptools
# Proper editable install via pyproject.toml. Installs PyQt5/pyudev/PyYAML
# and (new in v0.2) argon2-cffi as deps.
"$INSTALL_DIR/venv/bin/pip" install -e "$INSTALL_DIR/"

echo "==> Step 5/9: Installing config files"
[[ -f "$ETC_DIR/config.yaml" ]] || cp "$PROJECT_ROOT/config/config.yaml" "$ETC_DIR/"
# Note: whitelist.json is initialised by the setup wizard (step 9) so it
# can be HMAC-signed at the same time. We don't copy a stub here.

echo "==> Step 6/9: Configuring USBGuard"
[[ -f /etc/usbguard/rules.conf.original ]] || \
  cp /etc/usbguard/rules.conf /etc/usbguard/rules.conf.original 2>/dev/null || true
cp "$PROJECT_ROOT/config/usbguard-rules.conf" /etc/usbguard/rules.conf
systemctl enable --now usbguard

echo "==> Step 7/9: Staging X11 + logind hardening (activates on next reboot)"
# All changes in this step are written to disk but NOT applied to the running
# system. Applying them live (HUP logind, mask autovt on the active TTY,
# sysctl --system) can drop the seat of an active graphical session and
# leave the workstation with no input. We require a reboot instead.
mkdir -p /etc/X11/xorg.conf.d
cp "$PROJECT_ROOT/config/xorg-novtswitch.conf" /etc/X11/xorg.conf.d/99-usbdefense-novtswitch.conf

# Tell GDM to default to GNOME-on-Xorg, not Wayland. grabKeyboard/grabMouse
# is a silent no-op on Wayland; X11 is required for the overlay to actually
# trap input. Existing user sessions are not affected — change applies
# next login.
if [[ -f /etc/gdm/custom.conf ]]; then
  sed -i 's/^#\?WaylandEnable=.*/WaylandEnable=false/' /etc/gdm/custom.conf || true
  grep -q '^WaylandEnable=' /etc/gdm/custom.conf || \
    sed -i '/^\[daemon\]/a WaylandEnable=false' /etc/gdm/custom.conf || true
fi

# Persistent logind drop-in: tells systemd-logind to never auto-allocate
# extra virtual terminals. Combined with masked autovt@ units, this closes
# the gap where logind would respawn a getty as soon as we masked it.
# NOTE: not HUPing logind here — re-reading NAutoVTs=0 / ReserveVT=0 on a
# running graphical session can drop the active seat and kill input.
mkdir -p /etc/systemd/logind.conf.d
cp "$PROJECT_ROOT/config/logind-no-autovts.conf" \
   /etc/systemd/logind.conf.d/50-usbdefense.conf

# Stage the autovt@ttyN masks by writing symlinks to /dev/null in
# /etc/systemd/system. This is exactly what `systemctl mask` does on disk,
# but it does not touch the running systemd state — so the masks take
# effect on the next boot without disturbing the active session's TTY.
for n in 1 2 3 4 5 6; do
  ln -sfn /dev/null "/etc/systemd/system/autovt@tty${n}.service"
done

# Disable Magic SysRq. Without this, a local user can press
# Alt+SysRq+R to take the keyboard back from the X overlay
# (defeating grabKeyboard), or Alt+SysRq+REISUB to force-reboot
# straight out of lockdown.
# NOTE: not running `sysctl --system` here — applying kernel.sysrq=0 live
# removes the one emergency keyboard escape (Alt+SysRq+REISUB) right when
# a frozen X session would need it. The setting takes effect on next boot.
cat > /etc/sysctl.d/99-usbdefense.conf <<'EOF'
# Installed by USB Defense System.
# Disables Magic SysRq so the lockdown overlay cannot be bypassed
# via the kernel's emergency keyboard hotkeys.
kernel.sysrq = 0
EOF

REBOOT_REQUIRED=1

echo "==> Step 8/9: Installing systemd service + UI launcher"
cp "$PROJECT_ROOT/systemd/usb-defense.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now usb-defense.service
mkdir -p /etc/xdg/autostart
cp "$PROJECT_ROOT/systemd/usb-defense-ui.desktop" /etc/xdg/autostart/
ln -sfn "$INSTALL_DIR/venv/bin/python" /usr/local/bin/usb-defense-py

# Make append-only event log. Temporarily clear the append-only attribute
# (if a previous install set it) so the chown/chmod below don't fail with
# "Operation not permitted" — chattr +a freezes most metadata operations.
chattr -a "$LOG_DIR/events.log" 2>/dev/null || true
touch "$LOG_DIR/events.log"
chown root:root "$LOG_DIR/events.log"
chmod 600 "$LOG_DIR/events.log"
chattr +a "$LOG_DIR/events.log" 2>/dev/null || \
  echo "  (chattr +a failed — filesystem may not support it)"

echo "==> Step 9/9: First-run setup ceremony"
echo "    You will set an admin password and write down a one-time"
echo "    paper recovery code. This is the one ceremony that requires"
echo "    your attention — don't skip it."
echo
"$INSTALL_DIR/venv/bin/python" "$PROJECT_ROOT/scripts/setup.py" || {
  echo
  echo "  Setup wizard did not complete. You can re-run it with:"
  echo "    sudo $INSTALL_DIR/venv/bin/python $PROJECT_ROOT/scripts/setup.py"
  exit 1
}

echo
echo "================================================================"
echo "  USB Defense System installed successfully!"
echo
echo "  Daemon is already running (auto-started above)."
echo "  To check daemon status:     sudo systemctl status usb-defense"
echo "  To view daemon logs:        sudo journalctl -u usb-defense -f"
echo "  To open the UI:             usb-defense-py -m usbguard_defense.ui.main"
echo "  To regenerate paper code:   sudo $INSTALL_DIR/venv/bin/python \\"
echo "                                $PROJECT_ROOT/scripts/setup.py \\"
echo "                                --regenerate-recovery"
echo
echo "  Config files:               $ETC_DIR/"
echo "  Source code:                $INSTALL_DIR/usbguard_defense/"
echo "  Event log:                  $LOG_DIR/events.log"
echo
echo "  IMPORTANT: place an alarm sound at $INSTALL_DIR/assets/alarm.wav"
echo "             before triggering lockdown — otherwise no audio."
echo "  Log out and back in for the X11 session change AND the"
echo "  'usbdefense' group membership to take effect."
echo
echo "  To grant another user access to the UI:"
echo "      sudo usermod -a -G usbdefense <username>"
echo "================================================================"

if [[ "$REBOOT_REQUIRED" -eq 1 ]]; then
  echo
  echo "****************************************************************"
  echo "*  REBOOT REQUIRED                                              *"
  echo "*                                                               *"
  echo "*  Step 7 staged X11 + logind + sysctl hardening on disk but    *"
  echo "*  did NOT apply it to the running system, to avoid freezing    *"
  echo "*  an active graphical session. The hardening (no VT switch,    *"
  echo "*  autovt masking, kernel.sysrq=0) takes effect on next boot.   *"
  echo "*                                                               *"
  echo "*  Until you reboot, the daemon is running but the lockdown     *"
  echo "*  overlay can be bypassed via Ctrl+Alt+F1..F6 or SysRq.        *"
  echo "*                                                               *"
  echo "*  Reboot now:    sudo systemctl reboot                         *"
  echo "****************************************************************"
fi
