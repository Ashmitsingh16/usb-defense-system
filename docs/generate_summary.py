"""Generate USB_Project_Summary.pdf — one-page tech overview.

Written to ~/Desktop. Plain, terse, single page. For the teacher.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


OUT = Path.home() / "Desktop" / "USB_Project_Summary.pdf"


styles = getSampleStyleSheet()
H = ParagraphStyle(
    "H", parent=styles["Heading2"], fontSize=11, spaceBefore=6,
    spaceAfter=2, textColor=colors.HexColor("#1a4f8a"),
)
TITLE = ParagraphStyle(
    "TITLE", parent=styles["Heading1"], fontSize=14, spaceAfter=4,
    textColor=colors.HexColor("#0d1117"),
)
P = ParagraphStyle(
    "P", parent=styles["BodyText"], fontSize=9.4, leading=12,
    spaceAfter=3, alignment=TA_LEFT,
)


def p(t): return Paragraph(t, P)
def h(t): return Paragraph(t, H)


def build():
    s = []
    s.append(Paragraph("USB Defense System &mdash; what&rsquo;s inside", TITLE))
    s.append(p(
        "A root daemon on Rocky Linux 9 that watches every USB plug-in, "
        "checks the device against a signed whitelist, blocks unknowns at "
        "the kernel, and locks the screen until cleared with an admin "
        "password. Fully offline &mdash; no network code anywhere."
    ))

    s.append(h("Languages"))
    s.append(p(
        "Python 3 for the daemon, UI, tests, and tooling (~3000 lines, ~95% "
        "of the project). Bash for the install / uninstall scripts. YAML for "
        "config. JSON for the whitelist. No JavaScript, no HTML, no web."
    ))

    s.append(h("Stack"))
    s.append(p(
        "<b>USBGuard</b> &mdash; kernel-side USB authorization layer. "
        "<b>systemd</b> &mdash; service supervision, auto-start, watchdog. "
        "<b>pyudev</b> &mdash; USB hotplug events from the kernel. "
        "<b>PyQt5</b> &mdash; full-screen lockdown overlay + management UI. "
        "<b>argon2-cffi</b> (argon2id) &mdash; admin password hashing, memory-hard. "
        "<b>HMAC-SHA256</b> &mdash; whitelist tamper detection. "
        "<b>Crockford Base32</b> &mdash; 16-character one-time paper recovery code. "
        "<b>pulseaudio + alsa-utils</b> &mdash; alarm playback. "
        "<b>libnotify</b> &mdash; desktop notifications. "
        "<b>chattr +a</b> on ext4 &mdash; append-only event log. "
        "<b>X11 / Xorg</b> &mdash; required for the lockdown overlay to grab "
        "keyboard + mouse (Wayland silently ignores grabs). "
        "<b>VirtualBox</b> on Windows host &mdash; deployment target."
    ))

    s.append(h("Features"))
    s.append(p(
        "Whitelist by VID : PID : Serial &mdash; anything else is blocked at "
        "the kernel before it ever mounts. Red full-screen lockdown with "
        "audible alarm fires the instant an unknown USB / hard disk / pen "
        "drive is plugged in. Unlock requires the admin password (argon2id "
        "hash, set during install) or the one-time 16-char paper code. "
        "Whitelist is HMAC-signed; any hand-edit causes the daemon to "
        "fail-closed and refuse every device. Persistent lockdown flag "
        "survives reboot &mdash; can&rsquo;t be cleared by power-cycling. "
        "Append-only event log records every plug, block, unlock. IPC over a "
        "Unix socket between root daemon and the <code>usbdefense</code>-group "
        "user UI. Auto-starts on every boot."
    ))

    s.append(h("Honest limits"))
    s.append(p(
        "BadUSB devices with reprogrammable firmware can fake their identity "
        "&mdash; defeated by hardware procurement, not software. Pressing "
        "Ctrl+Alt+F3 during lockdown still escapes to a text console &mdash; "
        "queued for Phase 2. Pulling the SSD out and reading it on another "
        "machine is not in the threat model."
    ))

    s.append(h("Numbers"))
    s.append(p(
        "Version 0.2.0 (Phase 1 hardening). 88 unit tests passing. Zero "
        "paid dependencies, zero external services, zero LAN code."
    ))

    return s


def main():
    SimpleDocTemplate(
        str(OUT), pagesize=A4,
        leftMargin=1.6 * cm, rightMargin=1.6 * cm,
        topMargin=1.2 * cm, bottomMargin=1.2 * cm,
        title="USB Defense System &mdash; Summary",
        author="USB Defense Project",
    ).build(build())
    print(f"PDF written: {OUT}")


if __name__ == "__main__":
    main()
