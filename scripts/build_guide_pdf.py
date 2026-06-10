"""Build the user-facing PDF guide for USB Defense.

Run from the project root on the Windows host that has reportlab installed:
    python scripts/build_guide_pdf.py

Output: %USERPROFILE%\\Desktop\\USB-Defense-Guide.pdf

Terse command-first reference for an operator on Fedora 40+, Rocky 9, or
RHEL 8. Every command the operator may need is here; narrative is kept
to one or two lines per block.
"""

from __future__ import annotations

import os
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Preformatted,
)


OUTPUT = Path(os.path.expanduser("~/Desktop/USB-Defense-Guide.pdf"))


def _resolve_output() -> Path:
    """Fall back to a timestamped sibling if the canonical PDF is open in a
    viewer and locked for write."""
    try:
        with open(OUTPUT, "ab"):
            pass
        return OUTPUT
    except (PermissionError, OSError):
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        return OUTPUT.with_name(f"USB-Defense-Guide-{ts}.pdf")


def _styles():
    base = getSampleStyleSheet()
    base.add(ParagraphStyle(
        "Title2", parent=base["Heading1"],
        fontName="Helvetica-Bold", fontSize=18, leading=22,
        spaceAfter=2*mm, textColor=HexColor("#0b3d91"),
    ))
    base.add(ParagraphStyle(
        "H1", parent=base["Heading1"],
        fontName="Helvetica-Bold", fontSize=13, leading=16,
        spaceBefore=4*mm, spaceAfter=1*mm, textColor=HexColor("#0b3d91"),
    ))
    base.add(ParagraphStyle(
        "H2", parent=base["Heading2"],
        fontName="Helvetica-Bold", fontSize=10.5, leading=13,
        spaceBefore=2*mm, spaceAfter=0.5*mm, textColor=HexColor("#222222"),
    ))
    base.add(ParagraphStyle(
        "Body2", parent=base["BodyText"],
        fontName="Helvetica", fontSize=9.5, leading=12, spaceAfter=1*mm,
    ))
    base.add(ParagraphStyle(
        "Warn", parent=base["BodyText"],
        fontName="Helvetica-Bold", fontSize=9.5, leading=12,
        textColor=HexColor("#a30000"), spaceAfter=1*mm,
    ))
    return base


def _code(text: str) -> Preformatted:
    return Preformatted(
        text,
        style=ParagraphStyle(
            "Code", fontName="Courier", fontSize=8.8, leading=10.5,
            leftIndent=6, backColor=HexColor("#f3f3f3"),
            borderColor=HexColor("#dddddd"), borderWidth=0.4,
            borderPadding=3, spaceAfter=1.5*mm,
        ),
    )


def build() -> None:
    out = _resolve_output()
    doc = SimpleDocTemplate(
        str(out), pagesize=A4,
        leftMargin=14*mm, rightMargin=14*mm,
        topMargin=14*mm, bottomMargin=14*mm,
        title="USB Defense - Operator Cheatsheet",
        author="USB Defense Project",
    )
    S = _styles()
    flow = []
    P = lambda txt, sty="Body2": flow.append(Paragraph(txt, S[sty]))
    SP = lambda h=1: flow.append(Spacer(1, h*mm))

    # ── Header
    P("USB Defense &mdash; Operator Cheatsheet", "Title2")
    P(
        "Fedora 40+ / Rocky 9 / RHEL 8. Run every command in a terminal "
        "as a normal user with sudo. Plug in the keyboard and mouse you "
        "will keep using <b>before</b> step 1."
    )
    P(
        "WARNING: installing with a different keyboard/mouse will lock you out on "
        "next reboot. Recovery via GRUB in Section 5.",
        "Warn",
    )

    # ── 1. Install
    P("1. Install", "H1")
    P("Get the source:")
    flow.append(_code(
        "git clone https://github.com/Ashmitsingh16/usb-defense-system.git\n"
        "cd usb-defense-system"
    ))
    P("Optional &mdash; pre-install the X11 session (skip on Fedora 41+, see notes):")
    flow.append(_code(
        "# RHEL 8 / Rocky 9:\n"
        "sudo dnf install gnome-classic-session\n"
        "# Fedora 40:\n"
        "sudo dnf install gnome-session-xsession\n"
        "# Fedora 41+ (no GNOME X11 session ships):\n"
        "sudo dnf install i3"
    ))
    P("Run the installer:")
    flow.append(_code("sudo ./scripts/install.sh"))
    P(
        "Steps 1&ndash;8 are automatic. Step 9 is the interactive wizard. Type "
        "the admin password twice (input is hidden), then a paper recovery code "
        "is shown ONCE &mdash; write it down on paper, then press <b>Enter</b>. "
        "The daemon starts, then a REBOOT REQUIRED banner appears. Reboot now:"
    )
    flow.append(_code("sudo systemctl reboot"))

    # ── 2. Test
    P("2. Test", "H1")
    P("Daemon is running:")
    flow.append(_code("sudo systemctl status usb-defense"))
    P("USBGuard is enforcing &mdash; allowed devices should print <font face='Courier'>allow</font>:")
    flow.append(_code("sudo usbguard list-devices"))
    P("Open the UI:")
    flow.append(_code("usb-defense-py -m usbguard_defense.ui.main"))
    P(
        "Trigger a real lockdown by plugging in any USB that is NOT whitelisted. "
        "Overlay should appear within 1 second. Clear it by typing the admin "
        "password into the overlay prompt."
    )
    P("Whitelist file is immutable &mdash; terminal edit must fail:")
    flow.append(_code(
        "sudo sh -c 'echo evil >> /etc/usb-defense/whitelist.json'\n"
        "# expected: sh: ...whitelist.json: Operation not permitted\n"
        "lsattr /etc/usb-defense/whitelist.json\n"
        "# expected: ----i---------"
    ))
    P("Live tail of the audit log:")
    flow.append(_code("sudo tail -f /var/log/usb-defense/events.log"))

    # ── 3. If the installer hangs at step 8/9 or 9/9
    P("3. If the installer hangs at step 8/9 or 9/9", "H1")
    P(
        "The installer now prints sub-step lines and bounds each command with "
        "a timeout. The LAST line on screen tells you where it is stuck. "
        "Find your line below and run the recovery."
    )

    P("3a. Stuck at: <font face='Courier'>&rarr; systemctl daemon-reload (timeout 15s)</font>", "H2")
    P("Wait 15 seconds. The installer aborts. Then:")
    flow.append(_code(
        "sudo systemctl daemon-reexec\n"
        "sudo ./scripts/install.sh    # re-run, idempotent"
    ))

    P("3b. Stuck at: <font face='Courier'>&rarr; systemctl enable usb-defense.service</font>", "H2")
    P("Wait 15 seconds for the abort. Then:")
    flow.append(_code(
        "sudo systemctl daemon-reexec\n"
        "sudo systemctl reset-failed\n"
        "sudo ./scripts/install.sh"
    ))

    P("3c. Stuck at: <font face='Courier'>New admin password:</font>", "H2")
    P(
        "Input is hidden by design &mdash; <b>type your password and press Enter</b>. "
        "The terminal shows nothing while you type. If you started over SSH "
        "without <font face='Courier'>-t</font>, abort with Ctrl+C and re-run:"
    )
    flow.append(_code("ssh -t <host> 'sudo /path/to/usb-defense/scripts/install.sh'"))

    P("3d. Stuck at: <font face='Courier'>Press Enter once you have written the code down...</font>", "H2")
    P(
        "Recovery code is on the lines above. Write it on paper, then "
        "<b>press Enter</b>. Install is NOT done until you press Enter."
    )

    P("3e. Stuck at: <font face='Courier'>Starting USB Defense daemon (timeout 45s)...</font>", "H2")
    P("Wait 45 seconds. The installer dumps the last 30 journal lines automatically. Read the Python error, then:")
    flow.append(_code(
        "sudo journalctl -u usb-defense -n 50 --no-pager\n"
        "# fix the underlying error, then:\n"
        "sudo systemctl restart usb-defense.service"
    ))

    P("3f. Universal abort (works for any hang)", "H2")
    flow.append(_code(
        "# Ctrl+C to abort the installer, then:\n"
        "sudo systemctl stop usb-defense.service 2>/dev/null\n"
        "sudo systemctl disable usb-defense.service 2>/dev/null\n"
        "sudo ./scripts/install.sh    # the installer is idempotent"
    ))

    # ── 4. If the keyboard / mouse dies after reboot
    P("4. If keyboard/mouse stops working after reboot", "H1")
    P(
        "Cause: USBGuard does not have your real keyboard whitelisted. "
        "The keyboard still works at the GRUB menu (BIOS USB)."
    )
    P("Step 1 &mdash; at the GRUB menu, press any key to stop the countdown. Press <b>e</b> on the top entry. Find the line starting with <font face='Courier'>linux</font> or <font face='Courier'>linux16</font>. Add at the end:")
    flow.append(_code("systemd.mask=usbguard.service"))
    P("Press <b>Ctrl+X</b> to boot. Log in normally.")
    P("Step 2 &mdash; regenerate the rules from real hardware:")
    flow.append(_code(
        "sudo usbguard generate-policy | sudo tee /etc/usbguard/rules.conf > /dev/null\n"
        "sudo chmod 600 /etc/usbguard/rules.conf\n"
        "sudo systemctl unmask usbguard.service\n"
        "sudo systemctl restart usbguard\n"
        "sudo systemctl reboot"
    ))
    P("After reboot, keyboard and mouse work normally.")

    # ── 5. Uninstall / delete from the PC
    P("5. Uninstall / delete from the PC", "H1")
    P("Keep secrets + event log (default):")
    flow.append(_code("sudo ./scripts/uninstall.sh"))
    P("Wipe everything (logs, master key, admin hash, recovery code, whitelist):")
    flow.append(_code("sudo ./scripts/uninstall.sh --wipe"))
    P("Then reboot so sysctl/logind defaults come back:")
    flow.append(_code("sudo systemctl reboot"))
    P("Confirm everything is gone:")
    flow.append(_code(
        "systemctl status usb-defense         # expect: not-found\n"
        "ls /etc/usb-defense 2>&1 | head      # expect: No such file (after --wipe)\n"
        "sudo usbguard list-devices           # original rules restored"
    ))

    # ── 6. Other useful commands
    P("6. Other useful commands", "H1")
    flow.append(_code(
        "# Daemon logs (live)\n"
        "sudo journalctl -u usb-defense -f\n"
        "\n"
        "# Add another user to the IPC group\n"
        "sudo usermod -a -G usbdefense <username>\n"
        "\n"
        "# Regenerate the paper recovery code (invalidates the old one)\n"
        "sudo /usr/lib/usb-defense/venv/bin/python \\\n"
        "     scripts/setup.py --regenerate-recovery\n"
        "\n"
        "# Check Secure Boot / kernel lockdown (FYI, neither blocks USBGuard)\n"
        "mokutil --sb-state\n"
        "cat /sys/kernel/security/lockdown\n"
        "\n"
        "# If a USB will not enumerate at all, check the kernel saw it:\n"
        "sudo dmesg --since '30 seconds ago' | grep -i usb"
    ))

    doc.build(flow)
    print(f"Wrote {out}")
    if out != OUTPUT:
        print(f"NOTE: target {OUTPUT} was locked (PDF viewer open). "
              f"Close it and re-run, or keep the timestamped file above.")


if __name__ == "__main__":
    build()
