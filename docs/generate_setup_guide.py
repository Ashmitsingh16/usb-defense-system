"""Generate USB_Defense_Setup_Guide.pdf — minimal print-friendly version.

Covers every step from booting the host PC through running all three tests
inside the VM. Re-run when steps change.

Output path: ~/Desktop/USB_Defense_Setup_Guide.pdf
If the file is locked open in a PDF viewer, falls back to a timestamped
sibling so the run still succeeds.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


PREFERRED_OUT = Path.home() / "Desktop" / "USB_Defense_Setup_Guide.pdf"


styles = getSampleStyleSheet()
H1 = ParagraphStyle(
    "H1", parent=styles["Heading1"], fontSize=15, spaceAfter=4,
    spaceBefore=2, textColor=colors.HexColor("#0d1117"),
)
H2 = ParagraphStyle(
    "H2", parent=styles["Heading2"], fontSize=11, spaceAfter=2,
    spaceBefore=7, textColor=colors.HexColor("#1a4f8a"),
)
P = ParagraphStyle(
    "P", parent=styles["BodyText"], fontSize=9.2, leading=11.5, spaceAfter=3,
    alignment=TA_LEFT,
)
CODE = ParagraphStyle(
    "CODE", parent=P, fontName="Courier", fontSize=8.5, leading=10.5,
    leftIndent=8, rightIndent=8, spaceBefore=1, spaceAfter=4,
    backColor=colors.HexColor("#f2f2f2"), borderPadding=3,
    borderColor=colors.HexColor("#cccccc"), borderWidth=0.5,
)


def p(text): return Paragraph(text, P)
def h1(text): return Paragraph(text, H1)
def h2(text): return Paragraph(text, H2)


def code(text):
    safe = (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace("\n", "<br/>"))
    return Paragraph(safe, CODE)


def build_story() -> list:
    s: list = []

    s.append(h1("USB Defense System — Install &amp; Test"))
    s.append(p(
        "<b>Repo:</b> https://github.com/Ashmitsingh16/usb-defense-system  "
        "·  <b>Version:</b> v0.2.0  ·  <b>Time:</b> ~25 min from boot"
    ))
    s.append(p(
        "<b>Assumes:</b> Windows PC with VirtualBox already installed, "
        "and an existing VM with RHEL 9 (or Rocky 9) ready to start. "
        "VM needs internet for the one-time install."
    ))

    s.append(h2("1. Boot the Windows PC and open VirtualBox"))
    s.append(p(
        "Power on the PC, log into Windows. Press the Windows key, type "
        "<b>VirtualBox</b>, click <b>Oracle VirtualBox</b>."
    ))

    s.append(h2("2. Start the VM"))
    s.append(p(
        "In VirtualBox Manager, double-click the RHEL VM in the left panel "
        "(or right-click → <b>Start → Normal Start</b>). Wait for the login "
        "screen inside the VM."
    ))

    s.append(h2("3. Log into the VM"))
    s.append(p(
        "Click your user, type the Linux password, press Enter. Wait for "
        "the desktop to load."
    ))

    s.append(h2("4. Open Terminal"))
    s.append(p(
        "Click <b>Activities</b> (top-left), type <b>terminal</b>, click "
        "<b>Terminal</b>. Confirm sudo works:"
    ))
    s.append(code("sudo -v"))
    s.append(p("Type your password when asked."))

    s.append(h2("5. Install git and clone the project"))
    s.append(code(
        "sudo dnf install -y git\n"
        "cd ~ &amp;&amp; git clone https://github.com/Ashmitsingh16/usb-defense-system.git\n"
        "cd usb-defense-system"
    ))

    s.append(h2("6. Run the installer"))
    s.append(code("sudo bash src/scripts/install.sh"))
    s.append(p(
        "<b>Step 9 of the installer is interactive.</b> When prompted: type an "
        "8+ char admin password (twice, screen will NOT echo what you type). "
        "Then a 16-character recovery code appears in a banner — <b>WRITE "
        "IT ON PAPER</b> (shown only once). Press Enter."
    ))

    s.append(h2("7. Switch to GNOME on Xorg session"))
    s.append(p(
        "Log out of GNOME (top-right power icon → username → Log Out). At "
        "the login screen click your user. <b>Before</b> typing the password, "
        "click the gear icon ⚙ at the bottom-right of the password field "
        "and select <b>GNOME on Xorg</b> (not plain GNOME). Type password, log in."
    ))

    s.append(h2("8. Verify session and group membership"))
    s.append(code('echo "Session: $XDG_SESSION_TYPE" &amp;&amp; groups'))
    s.append(p(
        "Expect <code>Session: x11</code> and <code>usbdefense</code> in groups. "
        "If <code>usbdefense</code> is missing, log out and log back in once more."
    ))

    s.append(h2("9. Launch the UI"))
    s.append(code(
        "cd /usr/lib/usb-defense &amp;&amp; ./venv/bin/python -m \\\n"
        "  usbguard_defense.ui.main &gt; /tmp/ui.log 2&gt;&amp;1 &amp;"
    ))
    s.append(p("Dark window appears. Bottom status bar reads <b>Connected to daemon</b>."))

    s.append(h2("Test 1 — Password-gated whitelist add"))
    s.append(p(
        "UI → <b>Whitelist Manager</b> → <b>+ Add Device</b>. Fill: Label=Test, "
        "VID=0000, PID=0000, Serial=TEST001, Class=MassStorage. Click OK. "
        "Try a wrong password first (rejected with popup). Try the correct "
        "admin password (device added to list)."
    ))

    s.append(h2("Test 2 — Trigger lockdown, unlock with password"))
    s.append(code(
        "sudo /usr/lib/usb-defense/venv/bin/python \\\n"
        "  -m usbguard_defense.tests.simulate lockdown"
    ))
    s.append(p(
        "Screen turns red with SYSTEM LOCKED banner. Click <b>Unlock with "
        "admin password</b>. Wrong password rejected with inline error. "
        "Correct password clears the lockdown."
    ))

    s.append(h2("Test 3 — Tamper detection (headline feature)"))
    s.append(code(
        "sudo cp /etc/usb-defense/whitelist.json /tmp/wl.bak\n"
        "sudo cp /etc/usb-defense/whitelist.sig /tmp/sig.bak\n"
        'echo " " | sudo tee -a /etc/usb-defense/whitelist.json &gt; /dev/null\n'
        "sudo systemctl restart usb-defense\n"
        "sudo journalctl -u usb-defense -n 5 --no-pager"
    ))
    s.append(p(
        "Journal shows <b>WHITELIST TAMPER DETECTED</b>. UI status bar reads "
        "<b>Whitelist tamper detected — daemon refusing to load entries</b>."
    ))

    s.append(h2("Restore clean state (after Test 3)"))
    s.append(code(
        "sudo cp /tmp/wl.bak /etc/usb-defense/whitelist.json &amp;&amp; \\\n"
        "  sudo cp /tmp/sig.bak /etc/usb-defense/whitelist.sig &amp;&amp; \\\n"
        "  sudo systemctl restart usb-defense"
    ))

    s.append(h2("Cleanup — remove EVERYTHING from this PC (not yours)"))
    s.append(p(
        "Two options. Pick (A) if a pre-install VM snapshot exists, (B) otherwise."
    ))
    s.append(p("<b>(A) Easiest — restore a VM snapshot:</b>"))
    s.append(p(
        "Power off the VM inside (top-right power icon → Power Off). On the "
        "Windows host, open VirtualBox Manager → right-click the VM → "
        "<b>Snapshots</b> → pick a pre-install snapshot → <b>Restore</b>. "
        "30 seconds, no trace left."
    ))
    s.append(p("<b>(B) Command-line wipe (paste lines one at a time):</b>"))
    s.append(code(
        "# Stop daemon, run the official uninstaller (removes the systemd\n"
        "# unit, X11 config, usbdefense group, daemon files, etc.)\n"
        "sudo bash ~/usb-defense-system/src/scripts/uninstall.sh\n"
        "\n"
        "# Wipe secrets, event log, and persistent state (uninstaller\n"
        "# preserves these by design — must be removed manually):\n"
        "sudo rm -rf /etc/usb-defense /var/log/usb-defense /var/lib/usb-defense\n"
        "\n"
        "# Remove the cloned source code:\n"
        "rm -rf ~/usb-defense-system\n"
        "\n"
        "# Remove demo backup + UI log files from /tmp:\n"
        "rm -f /tmp/wl.bak /tmp/sig.bak /tmp/ui.log\n"
        "\n"
        "# Clear your shell history (removes typed sudo passwords etc.):\n"
        "history -c &amp;&amp; history -w &amp;&amp; rm -f ~/.bash_history"
    ))
    s.append(p("<b>Verify nothing remains:</b>"))
    s.append(code(
        "which usb-defense-py             # prints nothing\n"
        "ls /etc/usb-defense              # 'No such file or directory'\n"
        "systemctl status usb-defense     # 'could not be found'\n"
        "ls ~/usb-defense-system          # 'No such file or directory'"
    ))

    s.append(Spacer(1, 0.2 * cm))
    s.append(p(
        "<i>If UI fails with 'Could not load Qt platform plugin xcb': "
        "<code>sudo dnf install -y xcb-util xcb-util-image xcb-util-keysyms "
        "xcb-util-renderutil xcb-util-wm xcb-util-cursor libxkbcommon-x11</code> "
        "then re-launch the UI.</i>"
    ))

    return s


def _resolve_out() -> Path:
    """Try the preferred path; if locked, fall back to a timestamped sibling."""
    try:
        with PREFERRED_OUT.open("wb") as fh:
            fh.write(b"")
        return PREFERRED_OUT
    except PermissionError:
        stamp = _dt.datetime.now().strftime("%H%M%S")
        fallback = PREFERRED_OUT.with_stem(f"{PREFERRED_OUT.stem}_{stamp}")
        return fallback


def main() -> None:
    out = _resolve_out()
    doc = SimpleDocTemplate(
        str(out), pagesize=A4,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=1.2 * cm, bottomMargin=1.2 * cm,
        title="USB Defense System — Quick Install Guide",
        author="USB Defense Project",
    )
    doc.build(build_story())
    print(f"PDF written: {out}")
    if out != PREFERRED_OUT:
        print(
            "  (Original path was locked — likely open in a PDF viewer. "
            "Close the viewer and re-run to write to the canonical path.)"
        )


if __name__ == "__main__":
    main()
