#!/usr/bin/env bash
# USB Defense System — installer for Rocky Linux 9 and RHEL 8.
#
# Run as root from the project source directory:
#   sudo ./scripts/install.sh
#
# RHEL 8 note: the package declares requires-python>=3.9 but RHEL 8's
# default python3 is 3.6. This installer auto-enables the python39
# AppStream module and uses python3.9 for the venv when needed.

set -euo pipefail

# Print a clear "which step failed" message instead of just dumping a
# bash trace when something inside set -e trips.
CURRENT_STEP="pre-flight"
on_err() {
  local rc=$?
  echo
  echo "================================================================"
  echo "  ERROR: install.sh failed at: ${CURRENT_STEP}"
  echo "  Exit code: ${rc}    Line: ${BASH_LINENO[0]:-?}"
  echo
  echo "  Nothing past this point has been applied. Fix the underlying"
  echo "  problem and re-run: sudo ./scripts/install.sh"
  echo "================================================================"
  exit "$rc"
}
trap on_err ERR

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

# Pick a Python interpreter that satisfies pyproject.toml's
# requires-python>=3.9. On Rocky 9 the system python3 is 3.9, so we use
# it directly. On RHEL 8 the system python3 is 3.6, so we enable the
# python39 AppStream module first.
PYTHON_BIN=""
pick_python() {
  local cand ver
  for cand in python3.12 python3.11 python3.10 python3.9 python3; do
    command -v "$cand" >/dev/null 2>&1 || continue
    ver=$("$cand" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo "")
    case "$ver" in
      3.9|3.10|3.11|3.12|3.13)
        PYTHON_BIN="$cand"
        return 0
        ;;
    esac
  done
  return 1
}

CURRENT_STEP="Step 1/9: installing system packages"
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

# If the system python3 is older than 3.9 (RHEL 8 case), pull python39
# from the AppStream module so step 4 has an interpreter that satisfies
# the package's requires-python>=3.9.
if ! pick_python; then
  echo "  System python3 is older than 3.9 — enabling python39 AppStream module"
  dnf module enable -y python39 || true
  dnf install -y python39 python39-pip
  pick_python || {
    echo "ERROR: could not install Python >= 3.9 — required by pyproject.toml"
    exit 1
  }
fi
echo "  Using $PYTHON_BIN ($($PYTHON_BIN --version 2>&1))"

CURRENT_STEP="Step 2/9: creating directories and group"
echo "==> Step 2/9: Creating directories and 'usbdefense' group"
mkdir -p "$INSTALL_DIR" "$ETC_DIR" "$LOG_DIR" "$LIB_DIR" "$INSTALL_DIR/assets"
# The IPC socket is owned by root:usbdefense (0660) so only users in this
# group can talk to the daemon. Add the installing user (if any).
groupadd -f usbdefense
if [[ -n "${SUDO_USER:-}" && "$SUDO_USER" != "root" ]]; then
  usermod -a -G usbdefense "$SUDO_USER" || true
  echo "  Added $SUDO_USER to usbdefense group (re-login required for it to take effect)"
fi

CURRENT_STEP="Step 3/9: copying source code"
echo "==> Step 3/9: Copying source code"
cp -r "$PROJECT_ROOT/usbguard_defense" "$INSTALL_DIR/"
cp -f "$PROJECT_ROOT/pyproject.toml" "$INSTALL_DIR/" 2>/dev/null || true
cp -f "$PROJECT_ROOT/requirements.txt" "$INSTALL_DIR/" 2>/dev/null || true
cp -r "$PROJECT_ROOT/assets/." "$INSTALL_DIR/assets/" 2>/dev/null || true
# Guarantee an alarm.wav exists. The shipped one is normally copied above;
# if the repo was stripped, fall back to generating one with stdlib only
# (no venv needed — generate_alarm.py uses just wave/math/struct).
if [[ ! -f "$INSTALL_DIR/assets/alarm.wav" ]]; then
  echo "  No alarm.wav shipped — generating a default 2s siren"
  "$PYTHON_BIN" "$PROJECT_ROOT/scripts/generate_alarm.py" \
    "$INSTALL_DIR/assets/alarm.wav"
fi

CURRENT_STEP="Step 4/9: creating virtualenv and installing package"
echo "==> Step 4/9: Creating Python virtualenv and installing package"
"$PYTHON_BIN" -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip wheel setuptools
# Proper editable install via pyproject.toml. Installs PyQt5/pyudev/PyYAML
# and (new in v0.2) argon2-cffi as deps.
"$INSTALL_DIR/venv/bin/pip" install -e "$INSTALL_DIR/"

CURRENT_STEP="Step 5/9: installing config files"
echo "==> Step 5/9: Installing config files"
[[ -f "$ETC_DIR/config.yaml" ]] || cp "$PROJECT_ROOT/config/config.yaml" "$ETC_DIR/"
# Note: whitelist.json is initialised by the setup wizard (step 9) so it
# can be HMAC-signed at the same time. We don't copy a stub here.

CURRENT_STEP="Step 6/9: configuring USBGuard"
echo "==> Step 6/9: Configuring USBGuard"
[[ -f /etc/usbguard/rules.conf.original ]] || \
  cp /etc/usbguard/rules.conf /etc/usbguard/rules.conf.original 2>/dev/null || true
cp "$PROJECT_ROOT/config/usbguard-rules.conf" /etc/usbguard/rules.conf
systemctl enable --now usbguard

CURRENT_STEP="Step 7/9: staging X11 + logind hardening"
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

CURRENT_STEP="Step 8/9: installing systemd service and UI launcher"
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

CURRENT_STEP="Step 9/9: first-run setup ceremony"
echo "==> Step 9/9: First-run setup ceremony"
echo "    You will set an admin password and write down a one-time"
echo "    paper recovery code. This is the one ceremony that requires"
echo "    your attention — don't skip it."
echo
# Run the wizard without the ERR trap, so a user typo (e.g. mismatched
# passwords, then they re-try and finish successfully) doesn't kill the
# whole installer with a generic "step failed" message. We surface the
# wizard's own exit code instead.
trap - ERR
set +e
"$INSTALL_DIR/venv/bin/python" "$PROJECT_ROOT/scripts/setup.py"
setup_rc=$?
set -e
trap on_err ERR
if [[ $setup_rc -ne 0 ]]; then
  echo
  echo "  Setup wizard did not complete (exit $setup_rc). You can re-run it with:"
  echo "    sudo $INSTALL_DIR/venv/bin/python $PROJECT_ROOT/scripts/setup.py"
  exit 1
fi

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
if [[ ! -f "$INSTALL_DIR/assets/alarm.wav" ]]; then
  echo "  IMPORTANT: alarm.wav was not installed. Generate one with:"
  echo "      sudo $PYTHON_BIN $PROJECT_ROOT/scripts/generate_alarm.py \\"
  echo "           $INSTALL_DIR/assets/alarm.wav"
fi
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
