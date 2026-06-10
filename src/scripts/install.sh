#!/usr/bin/env bash
# USB Defense System — installer for Rocky Linux 9, RHEL 8, and Fedora 40+.
#
# Run as root from the project source directory:
#   sudo ./scripts/install.sh
#
# RHEL 8 note: the package declares requires-python>=3.9 but RHEL 8's
# default python3 is 3.6. This installer auto-enables the python39
# AppStream module and uses python3.9 for the venv when needed.
#
# Fedora 40+ note: ships python3.12 (no AppStream fallback needed) and
# defaults to Wayland. The lockdown overlay requires X11 to grab the
# keyboard/mouse — on Fedora 41+ the GNOME X11 session is removed, so
# the overlay degrades to a silent no-op unless a different X-capable
# session/WM is installed. The installer prints a clear warning at the
# end if it detects Fedora.

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

# Detect distro so we can (a) report it in the install log, (b) gate the
# RHEL 8-only python39 AppStream fallback, and (c) emit a Fedora-specific
# Wayland warning at the end. /etc/os-release is the standard mechanism
# and exists on every supported distro.
DISTRO_ID=""
DISTRO_VER=""
if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  DISTRO_ID="${ID:-}"
  DISTRO_VER="${VERSION_ID:-}"
fi
case "$DISTRO_ID" in
  rhel|rocky|fedora|centos)
    echo "  Detected distro: ${DISTRO_ID} ${DISTRO_VER}" ;;
  "")
    echo "  WARNING: could not detect distro from /etc/os-release — proceeding anyway" ;;
  *)
    echo "  WARNING: distro '$DISTRO_ID' is not officially supported (tested on rhel/rocky/fedora) — proceeding anyway" ;;
esac

# Pre-flight: report Secure Boot and kernel lockdown state. USBGuard's
# authorize/deauthorize uses sysfs writes that work fine under both
# integrity-mode lockdown and Secure Boot — but on managed lab machines
# we have seen confusing "my USB won't enumerate" reports that turned
# out to be unrelated BIOS USB-disable settings. Surfacing the state up
# front makes triage a one-line check instead of a debug session.
echo "==> Pre-flight: Secure Boot + kernel lockdown state"
sb_state="unknown (mokutil not installed)"
if command -v mokutil >/dev/null 2>&1; then
  sb_state="$(mokutil --sb-state 2>/dev/null | head -1 || echo unknown)"
elif [[ -d /sys/firmware/efi/efivars ]]; then
  # Fallback: read the EFI variable directly. The 5th byte is the SB flag.
  sb_var="$(ls /sys/firmware/efi/efivars/SecureBoot-* 2>/dev/null | head -1 || true)"
  if [[ -n "$sb_var" ]]; then
    if [[ "$(od -An -t x1 -j 4 -N 1 "$sb_var" 2>/dev/null | tr -d ' ')" == "01" ]]; then
      sb_state="SecureBoot enabled (read from EFI var)"
    else
      sb_state="SecureBoot disabled (read from EFI var)"
    fi
  else
    sb_state="legacy BIOS or SB var unreadable"
  fi
else
  sb_state="legacy BIOS (no /sys/firmware/efi)"
fi
echo "  Secure Boot:     $sb_state"

if [[ -r /sys/kernel/security/lockdown ]]; then
  ld_state="$(cat /sys/kernel/security/lockdown 2>/dev/null || echo unreadable)"
  echo "  Kernel lockdown: $ld_state"
else
  echo "  Kernel lockdown: not available (kernel < 5.4 or LSM not enabled)"
fi
echo "  Note: neither SB nor integrity-mode lockdown blocks USBGuard's"
echo "        /sys/bus/usb/.../authorized writes. If a USB still won't"
echo "        enumerate after install, also check BIOS 'USB ports' and"
echo "        'XHCI hand-off' settings."

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
  libnotify \
  xorg-x11-server-Xorg xorg-x11-xinit \
  xcb-util xcb-util-image xcb-util-keysyms \
  xcb-util-renderutil xcb-util-wm xcb-util-cursor \
  libxkbcommon-x11 \
  --setopt=install_weak_deps=False

# If the system python3 is older than 3.9 (RHEL 8 case), pull python39
# from the AppStream module so step 4 has an interpreter that satisfies
# the package's requires-python>=3.9. On Fedora 40+ this branch never
# fires because the default python3 is already 3.12; if pick_python ever
# does fail on Fedora we fall back to plain `dnf install python3.12`.
if ! pick_python; then
  case "$DISTRO_ID" in
    rhel|centos|rocky)
      echo "  System python3 < 3.9 — enabling python39 AppStream module"
      dnf module enable -y python39 || true
      dnf install -y python39 python39-pip
      ;;
    fedora|*)
      echo "  System python3 < 3.9 — installing python3.12"
      dnf install -y python3.12 python3.12-pip || \
        dnf install -y python3.11 python3.11-pip || \
        dnf install -y python3.10 python3.10-pip || true
      ;;
  esac
  pick_python || {
    echo "ERROR: could not install Python >= 3.9 — required by pyproject.toml"
    exit 1
  }
fi
echo "  Using $PYTHON_BIN ($($PYTHON_BIN --version 2>&1))"

# Check that a graphical X11 session is registered with the display
# manager. The lockdown overlay relies on X11 grabKeyboard/grabMouse —
# under Wayland those calls are silent no-ops and the overlay cannot
# trap input. We do NOT auto-install gnome-session-xsession because the
# package name varies between RHEL 8 / Rocky 9 / Fedora and a missing
# package would kill the installer. We surface a clear warning instead.
echo "  Checking for an X11 session in /usr/share/xsessions/"
x11_session_found=0
if [[ -d /usr/share/xsessions ]]; then
  shopt -s nullglob
  for f in /usr/share/xsessions/*.desktop; do
    x11_session_found=1
    break
  done
  shopt -u nullglob
fi
if [[ "$x11_session_found" -eq 0 ]]; then
  echo "  WARNING: no *.desktop file in /usr/share/xsessions/ — GDM will only"
  echo "           offer Wayland and the lockdown overlay will not grab input."
  echo "           To fix, install an X11 session for your distro:"
  echo "             RHEL 8 / Rocky 9 : sudo dnf install gnome-classic-session"
  echo "             Fedora 40        : sudo dnf install gnome-session-xsession"
  echo "             Fedora 41+       : sudo dnf install i3   (or openbox / xfce)"
  echo "           Then log out and pick the X11 session at the login screen."
else
  echo "  X11 session present — overlay will be able to grab input."
fi

CURRENT_STEP="Step 2/9: creating directories and group"
echo "==> Step 2/9: Creating directories and 'usbdefense' group"
mkdir -p "$INSTALL_DIR" "$ETC_DIR" "$LOG_DIR" "$LIB_DIR"
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

# Snapshot the USB devices attached RIGHT NOW (real keyboard, mouse, hubs,
# internal webcam, etc.) as explicit `allow id VID:PID ...` rules. This is
# the only reliable way to keep input working across the first reboot on
# bare metal — the old static rule
#   allow with-interface 03:01:01 with-connect-type "hardwired"
# only matched VirtualBox-emulated HID and silently blocked real external
# USB keyboards/mice, locking the operator out (RHEL 8 bare-metal regression).
echo "  Snapshotting currently-attached USB devices as allow rules"
generated_rules="$(usbguard generate-policy)"
if [[ -z "$generated_rules" ]] || ! grep -q '^allow' <<<"$generated_rules"; then
  echo "ERROR: usbguard generate-policy produced no allow rules."
  echo "       Installing now would block all USB input after reboot."
  echo "       Plug in your keyboard/mouse and re-run the installer."
  exit 1
fi
if ! grep -qE 'with-interface[[:space:]]*[{[:space:]]*03:' <<<"$generated_rules"; then
  echo "ERROR: no HID (keyboard/mouse) detected by usbguard generate-policy."
  echo "       Installing now would lock the keyboard on reboot. Aborting."
  exit 1
fi
{
  cat <<'EOF'
# Generated by USB Defense installer via `usbguard generate-policy`.
# Each `allow id VID:PID ...` line below snapshots one USB device that was
# attached when the installer ran. Everything else is blocked by default;
# the daemon authorizes new devices at runtime via the signed whitelist
# (/etc/usb-defense/whitelist.json).
EOF
  echo "$generated_rules"
} > /etc/usbguard/rules.conf
chmod 600 /etc/usbguard/rules.conf

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
# Order matters: we set up the append-only event log and install
# the service file, but DO NOT start the daemon yet. The setup wizard
# in step 9 creates /etc/usb-defense/master.key and the signed
# whitelist; starting the daemon before that means it boots into a
# half-configured state and may race the perm setup on events.log.
#
# Each systemctl call below is bounded with `timeout 15` so a wedged
# dbus / systemd state cannot hold the installer forever. Verbose
# sub-step echoes mean a hang here points at one specific command
# rather than a generic "step 8 stuck".
echo "  → copying unit file"
cp "$PROJECT_ROOT/systemd/usb-defense.service" /etc/systemd/system/
echo "  → systemctl daemon-reload (timeout 15s)"
timeout 15 systemctl daemon-reload || {
  echo "ERROR: 'systemctl daemon-reload' did not finish within 15s."
  echo "       systemd or dbus is wedged. Try:"
  echo "           sudo systemctl daemon-reexec"
  echo "       then re-run this installer."
  exit 1
}
echo "  → systemctl enable usb-defense.service (timeout 15s)"
timeout 15 systemctl enable usb-defense.service || {
  echo "ERROR: 'systemctl enable usb-defense.service' did not finish within 15s."
  echo "       Inspect with: systemctl status usb-defense.service"
  exit 1
}
echo "  → installing autostart desktop entry"
mkdir -p /etc/xdg/autostart
cp "$PROJECT_ROOT/systemd/usb-defense-ui.desktop" /etc/xdg/autostart/
echo "  → installing /usr/local/bin/usb-defense-py launcher"
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
# The wizard calls getpass() and input(). Without a real TTY (e.g. piped
# stdin, or ssh without -t) those block forever and the install appears
# stuck at step 9. Surface that as a clear error before launching.
if ! [[ -t 0 && -t 1 ]]; then
  echo "ERROR: setup wizard needs an interactive terminal."
  echo "       stdin/stdout is not a TTY — getpass would hang silently."
  echo "       If you launched this over ssh, re-run with:"
  echo "           ssh -t <host> 'sudo ./scripts/install.sh'"
  echo "       Or finish the install by running the wizard yourself:"
  echo "           sudo $INSTALL_DIR/venv/bin/python $PROJECT_ROOT/scripts/setup.py"
  echo "           sudo systemctl start usb-defense.service"
  exit 1
fi
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

# Mark the whitelist + signature immutable so a second terminal cannot
# edit them with `sudo nano` or similar. The HMAC signature already makes
# such edits ineffective (daemon detects WHITELIST_TAMPER and fails closed)
# but +i blocks the write at the open() step too, so accidental edits
# fail immediately instead of silently corrupting the audit log. The
# daemon's whitelist.save() temporarily clears +i during legitimate UI
# saves and re-applies it after, so the UI remains the only working path
# to add/remove devices.
echo "==> Locking whitelist files (chattr +i)"
chattr +i /etc/usb-defense/whitelist.json 2>/dev/null || \
  echo "  (chattr +i failed — filesystem may not support it; HMAC still protects)"
chattr +i /etc/usb-defense/whitelist.sig 2>/dev/null || true

# Now that the master key, whitelist, admin password and recovery code
# are all in place, start the daemon. Verify it actually came up — if
# Type=notify times out the unit will report failed.
#
# The unit sets TimeoutStartSec=30, so `systemctl start` returns within
# ~30s in the worst case (daemon hangs before sending READY=1). We add
# a 45s outer timeout as a belt-and-braces guard in case systemctl
# itself wedges on dbus.
CURRENT_STEP="starting and verifying usb-defense daemon"
echo
echo "==> Starting USB Defense daemon (timeout 45s)..."
if ! timeout 45 systemctl start usb-defense.service; then
  echo
  echo "  ERROR: 'systemctl start usb-defense.service' did not return in 45s."
  echo "  The daemon probably failed to notify READY=1. Recent logs:"
  echo
  journalctl -u usb-defense.service -n 30 --no-pager || true
  echo
  echo "  Fix the underlying problem and:"
  echo "      sudo systemctl restart usb-defense.service"
  exit 1
fi
sleep 1
if ! systemctl is-active --quiet usb-defense.service; then
  echo
  echo "  ERROR: usb-defense daemon failed to start. Recent logs:"
  echo
  journalctl -u usb-defense.service -n 30 --no-pager || true
  echo
  echo "  Fix the underlying problem and:"
  echo "      sudo systemctl restart usb-defense.service"
  exit 1
fi
echo "  Daemon is active."

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
echo "  Log out and back in for the X11 session change AND the"
echo "  'usbdefense' group membership to take effect."
echo
echo "  To grant another user access to the UI:"
echo "      sudo usermod -a -G usbdefense <username>"
echo "================================================================"

if [[ "$DISTRO_ID" == "fedora" ]]; then
  echo
  echo "****************************************************************"
  echo "*  FEDORA NOTE — read this                                      *"
  echo "*                                                               *"
  echo "*  Fedora defaults to Wayland. The USB Defense lockdown overlay *"
  echo "*  uses X11 grabKeyboard/grabMouse to trap input — that call is *"
  echo "*  a silent no-op on Wayland. We set WaylandEnable=false in GDM *"
  echo "*  so the X11 session is preferred IF available.                *"
  echo "*                                                               *"
  echo "*  Fedora 40: GNOME on Xorg session is present but deprecated.  *"
  echo "*  Fedora 41+: GNOME on Xorg was removed. Either install an X11 *"
  echo "*  WM (e.g. dnf install i3 or openbox) or accept that the       *"
  echo "*  overlay will not grab input until you switch to X.           *"
  echo "*                                                               *"
  echo "*  Check after login: echo \$XDG_SESSION_TYPE                    *"
  echo "*    -> 'x11'      : overlay works                              *"
  echo "*    -> 'wayland'  : overlay is a no-op (event log still runs)  *"
  echo "****************************************************************"
fi

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
