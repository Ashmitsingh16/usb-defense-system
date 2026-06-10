"""Build the user-facing PDF guide for USB Defense.

Run from the project root on the Windows host that has reportlab installed:
    python scripts/build_guide_pdf.py

Output: %USERPROFILE%\\Desktop\\USB-Defense-Guide.pdf

The guide is deliberately self-contained — it does not reference any file
inside the repo, so it can be handed to an operator/teacher who only has
the source tarball and a fresh Fedora/RHEL/Rocky machine.
"""

from __future__ import annotations

import os
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak,
    Preformatted, KeepTogether,
)


OUTPUT = Path(os.path.expanduser("~/Desktop/USB-Defense-Guide.pdf"))


def _resolve_output() -> Path:
    """If the target PDF is held open by a PDF viewer the write fails with
    PermissionError. Fall back to a timestamped sibling so the rebuild
    never fails silently. Caller should report the actual path written.
    """
    try:
        # Touch-test: open for write without truncating
        with open(OUTPUT, "ab"):
            pass
        return OUTPUT
    except (PermissionError, OSError):
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        alt = OUTPUT.with_name(f"USB-Defense-Guide-{ts}.pdf")
        return alt


def _styles():
    base = getSampleStyleSheet()
    base.add(ParagraphStyle(
        "Title2", parent=base["Heading1"],
        fontName="Helvetica-Bold", fontSize=22, leading=26,
        spaceAfter=4*mm, textColor=HexColor("#0b3d91"),
    ))
    base.add(ParagraphStyle(
        "H1", parent=base["Heading1"],
        fontName="Helvetica-Bold", fontSize=15, leading=19,
        spaceBefore=6*mm, spaceAfter=2*mm, textColor=HexColor("#0b3d91"),
    ))
    base.add(ParagraphStyle(
        "H2", parent=base["Heading2"],
        fontName="Helvetica-Bold", fontSize=12, leading=15,
        spaceBefore=4*mm, spaceAfter=1*mm, textColor=HexColor("#222222"),
    ))
    base.add(ParagraphStyle(
        "Body2", parent=base["BodyText"],
        fontName="Helvetica", fontSize=10.5, leading=14, spaceAfter=2*mm,
    ))
    base.add(ParagraphStyle(
        "Warn", parent=base["BodyText"],
        fontName="Helvetica-Bold", fontSize=10.5, leading=14,
        textColor=HexColor("#a30000"), spaceAfter=2*mm,
    ))
    base.add(ParagraphStyle(
        "Note", parent=base["BodyText"],
        fontName="Helvetica-Oblique", fontSize=10, leading=13,
        textColor=HexColor("#555555"), spaceAfter=2*mm,
    ))
    return base


def _code(text: str) -> Preformatted:
    return Preformatted(
        text,
        style=ParagraphStyle(
            "Code", fontName="Courier", fontSize=9.5, leading=12,
            leftIndent=8, backColor=HexColor("#f3f3f3"),
            borderColor=HexColor("#dddddd"), borderWidth=0.5,
            borderPadding=4, spaceAfter=3*mm,
        ),
    )


def build() -> None:
    out = _resolve_output()
    doc = SimpleDocTemplate(
        str(out), pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=18*mm, bottomMargin=18*mm,
        title="USB Defense System — Operator Guide",
        author="USB Defense Project",
    )
    S = _styles()
    flow = []
    P = lambda txt, sty="Body2": flow.append(Paragraph(txt, S[sty]))
    SP = lambda h=3: flow.append(Spacer(1, h*mm))

    # ── Cover
    P("USB Defense System", "Title2")
    P("Operator Guide &mdash; install, test, and remove", "H2")
    P(
        "This guide is written for a single physical machine running "
        "<b>Fedora 40+</b>, <b>Rocky Linux 9</b>, or <b>RHEL 8</b>. "
        "All commands are run in a terminal as a normal user with "
        "<font face='Courier'>sudo</font> privileges. The product blocks "
        "any USB device that is not explicitly whitelisted, locks the "
        "screen on intrusion, and logs every event to an append-only file.",
    )
    SP()
    P("Read the WARNING below before you run anything.", "Warn")
    P(
        "Once installed, the system replaces the default USBGuard policy "
        "with one that allows ONLY the USB devices that were plugged in "
        "at install time. If you install with the wrong keyboard/mouse "
        "attached, you will be locked out on the next reboot. The recovery "
        "procedure (Section 6) requires access to the GRUB menu.",
        "Warn",
    )

    # ── 1. Prerequisites
    P("1. Prerequisites", "H1")
    P("Hardware:", "H2")
    P(
        "&bull; A physical PC (or VM) you can reboot, with at least 4 GB RAM.<br/>"
        "&bull; The keyboard and mouse you intend to use must be plugged in "
        "<b>before</b> you start the installer.<br/>"
        "&bull; Internet access for the dnf package install (about 200 MB)."
    )
    P("Operating system:", "H2")
    P(
        "&bull; <b>Fedora 40 or newer</b> &mdash; default Python 3.12, defaults to Wayland.<br/>"
        "&bull; <b>Rocky Linux 9</b> &mdash; default Python 3.9, X11 session available.<br/>"
        "&bull; <b>RHEL 8.4 or newer</b> &mdash; default Python 3.6; the installer "
        "auto-enables the <font face='Courier'>python39</font> AppStream module."
    )
    P("Software you must have already:", "H2")
    P(
        "&bull; A working <font face='Courier'>sudo</font> setup for your user.<br/>"
        "&bull; <font face='Courier'>git</font> (only if you are cloning, not extracting a tarball).<br/>"
        "&bull; A graphical session you can log out of and back into.<br/>"
        "&bull; An X11 session registered with GDM (the installer checks "
        "<font face='Courier'>/usr/share/xsessions/</font> and warns if empty)."
    )
    P("X11 session per distro &mdash; the lockdown overlay needs X11:", "H2")
    P(
        "&bull; <b>RHEL 8 / Rocky 9</b>: <font face='Courier'>sudo dnf install gnome-classic-session</font><br/>"
        "&bull; <b>Fedora 40</b>: <font face='Courier'>sudo dnf install gnome-session-xsession</font> (deprecated, still works)<br/>"
        "&bull; <b>Fedora 41+</b>: <font face='Courier'>sudo dnf install i3</font> "
        "(or <font face='Courier'>openbox</font> / <font face='Courier'>xfce</font>) "
        "&mdash; GNOME-on-Xorg was removed.<br/><br/>"
        "After installing, log out and pick the X11 session at the GDM login screen "
        "(little gear icon next to your name). Verify with: "
        "<font face='Courier'>echo $XDG_SESSION_TYPE</font> &mdash; should print "
        "<font face='Courier'>x11</font>."
    )
    P("Secure Boot &amp; kernel lockdown:", "H2")
    P(
        "Secure Boot does NOT block USBGuard &mdash; USBGuard authorizes devices "
        "via <font face='Courier'>/sys/bus/usb/devices/*/authorized</font>, which "
        "is writable under both Secure Boot and integrity-mode kernel lockdown. "
        "The installer prints both states up front so you can confirm. If a USB "
        "still does not enumerate on a managed lab PC, the cause is almost "
        "always in BIOS &mdash; check &ldquo;USB Ports&rdquo;, &ldquo;XHCI hand-off&rdquo;, "
        "or a corporate USB-block policy, not USBGuard."
    )

    # ── 2. Get the source
    P("2. Get the source code", "H1")
    P("Either clone the repo:")
    flow.append(_code("git clone <repo-url> usb-defense\ncd usb-defense"))
    P("&hellip; or extract a tarball and cd into it:")
    flow.append(_code("tar xzf usb-defense-vX.Y.Z.tar.gz\ncd usb-defense-vX.Y.Z"))
    P(
        "You should now see a <font face='Courier'>scripts/</font> directory "
        "containing <font face='Courier'>install.sh</font> and "
        "<font face='Courier'>uninstall.sh</font>.",
    )

    # ── 3. Install
    P("3. Install", "H1")
    P(
        "Plug in the keyboard and mouse you will keep using. Then run the "
        "installer with <b>sudo</b>:",
    )
    flow.append(_code("sudo ./scripts/install.sh"))
    P("Before step 1 the installer prints two pre-flight blocks:")
    P(
        "&bull; <b>Detected distro</b> &mdash; confirms ID and version.<br/>"
        "&bull; <b>Pre-flight: Secure Boot + kernel lockdown state</b> &mdash; "
        "informational. If &ldquo;Secure Boot: enabled&rdquo; and a USB later "
        "refuses to enumerate, the cause is BIOS not USBGuard."
    )
    P("Then the nine numbered steps:")
    P(
        "<b>1/9</b> &nbsp;Install system packages via dnf, then check that an X11 "
        "session is registered in <font face='Courier'>/usr/share/xsessions/</font>. "
        "If empty you get a clear warning with the right dnf command for your distro.<br/>"
        "<b>2/9</b> &nbsp;Create directories and the <font face='Courier'>usbdefense</font> group.<br/>"
        "<b>3/9</b> &nbsp;Copy source code into <font face='Courier'>/usr/lib/usb-defense/</font>.<br/>"
        "<b>4/9</b> &nbsp;Create the Python virtualenv (pip will pull PyQt5, takes a minute).<br/>"
        "<b>5/9</b> &nbsp;Install config files into <font face='Courier'>/etc/usb-defense/</font>.<br/>"
        "<b>6/9</b> &nbsp;Snapshot every USB device currently attached as an explicit allow rule.<br/>"
        "<b>7/9</b> &nbsp;Stage X11 / logind / sysctl hardening (applied on next reboot).<br/>"
        "<b>8/9</b> &nbsp;Install the systemd unit and UI launcher.<br/>"
        "<b>9/9</b> &nbsp;Run the interactive first-run wizard, then "
        "<font face='Courier'>chattr +i</font> the whitelist files (see Section 4, Test 5)."
    )
    P("During step 9 the wizard will:", "H2")
    P(
        "&bull; Ask for an admin password twice (hidden input).<br/>"
        "&bull; Generate the master HMAC key.<br/>"
        "&bull; Display a 16-character <b>paper recovery code</b>. Write it down on paper.<br/>"
        "&bull; Wait for you to press <b>Enter</b>."
    )
    P(
        "After Enter, the installer starts the daemon and prints a "
        "&ldquo;REBOOT REQUIRED&rdquo; banner. Reboot now:",
    )
    flow.append(_code("sudo systemctl reboot"))
    P(
        "The hardening (no Ctrl+Alt+F1..F6 escape, no SysRq, autovt masked) "
        "takes effect on this reboot.",
    )

    flow.append(PageBreak())

    # ── 4. Verify it actually works
    P("4. Test that it works", "H1")
    P("Test 1 &mdash; daemon is running:", "H2")
    flow.append(_code("sudo systemctl status usb-defense"))
    P(
        "Expect <font face='Courier'>active (running)</font>. Press q to exit.",
    )

    P("Test 2 &mdash; USBGuard is enforcing:", "H2")
    flow.append(_code("sudo usbguard list-devices"))
    P(
        "Every line should start with <b>allow</b> for the devices that were "
        "attached at install time. Anything plugged in later will appear as "
        "<b>block</b> until you authorize it via the UI.",
    )

    P("Test 3 &mdash; open the UI:", "H2")
    flow.append(_code("usb-defense-py -m usbguard_defense.ui.main"))
    P(
        "Log in once with the admin password you set in step 9. The Devices "
        "tab lists allowed USBs; the Event Log tab shows the audit trail.",
    )

    P("Test 4 &mdash; trigger a real lockdown:", "H2")
    P(
        "Plug in any USB stick that is NOT already whitelisted. Within one "
        "second you should see:"
    )
    P(
        "&bull; A full-screen overlay covering every monitor.<br/>"
        "&bull; Ctrl+Alt+F1..F6 does not switch to a TTY.<br/>"
        "&bull; The block event in <font face='Courier'>/var/log/usb-defense/events.log</font>."
    )
    P("Clear the lockdown by entering the admin password in the overlay prompt.")

    P("Test 5 &mdash; whitelist is locked from terminal edits:", "H2")
    P(
        "From another terminal try to add a fake device by editing the file "
        "directly (this is the attack scenario where someone with sudo tries "
        "to bypass the UI):"
    )
    flow.append(_code(
        "sudo sh -c 'echo evil >> /etc/usb-defense/whitelist.json'"
    ))
    P("You should see this exact error:")
    flow.append(_code(
        "sh: line 1: /etc/usb-defense/whitelist.json: Operation not permitted"
    ))
    P(
        "The file is <font face='Courier'>chattr +i</font> (immutable), so the "
        "open-for-write fails at the kernel level &mdash; the edit cannot even "
        "be attempted. Confirm the flag:"
    )
    flow.append(_code("lsattr /etc/usb-defense/whitelist.json"))
    P("Output line should start with <font face='Courier'>----i---------</font> (the &lsquo;i&rsquo; is the immutable bit).")
    P("Second-layer defense &mdash; if someone clears <font face='Courier'>+i</font> and edits anyway:", "H2")
    flow.append(_code(
        "sudo chattr -i /etc/usb-defense/whitelist.json\n"
        "sudo sh -c 'echo evil >> /etc/usb-defense/whitelist.json'\n"
        "sudo systemctl restart usb-defense\n"
        "sudo tail -5 /var/log/usb-defense/events.log"
    ))
    P(
        "The HMAC signature on <font face='Courier'>whitelist.sig</font> no "
        "longer matches the tampered JSON, so the daemon fails closed: the "
        "entire whitelist is treated as empty and a "
        "<font face='Courier'>WHITELIST_TAMPER</font> event is written to "
        "the audit log. Recover by re-running the setup wizard or by "
        "re-enrolling devices through the UI &mdash; both paths re-sign "
        "and re-lock the file."
    )

    # ── 5. Uninstall / delete
    P("5. Uninstall &mdash; remove from the PC", "H1")
    P("From the source directory:", "H2")
    P("Keep the event log and secrets (default):")
    flow.append(_code("sudo ./scripts/uninstall.sh"))
    P("Or wipe everything (logs, master key, admin hash, recovery code):")
    flow.append(_code("sudo ./scripts/uninstall.sh --wipe"))
    P("Then reboot so the sysctl/logind defaults come back:", "H2")
    flow.append(_code("sudo systemctl reboot"))
    P("Verify the cleanup:", "H2")
    flow.append(_code("systemctl status usb-defense          # should say: not-found\n"
                      "ls /etc/usb-defense /var/log/usb-defense 2>&1 | head\n"
                      "                                       # No such file (with --wipe)\n"
                      "ls /etc/usbguard/rules.conf            # restored to original"))
    P(
        "The original USBGuard rules file is restored from "
        "<font face='Courier'>/etc/usbguard/rules.conf.original</font> if the "
        "uninstaller finds the backup. If it does not, run "
        "<font face='Courier'>sudo systemctl disable --now usbguard</font> "
        "to fully relax the policy.",
    )

    flow.append(PageBreak())

    # ── 6. Recovery
    P("6. Recovery &mdash; if the PC will not accept keyboard/mouse after reboot", "H1")
    P(
        "This means USBGuard has not been told about your input devices &mdash; "
        "either you reinstalled with a different keyboard/mouse attached, or "
        "the install was interrupted. The keyboard still works at the GRUB "
        "menu (that is BIOS USB, before Linux loads). Procedure:",
    )
    P("Step 1 &mdash; mask USBGuard at boot:", "H2")
    P(
        "Power on. At the GRUB menu, press any key fast to stop the countdown. "
        "Highlight the top kernel entry. Press <b>e</b> to edit."
    )
    P(
        "Find the line that starts with <font face='Courier'>linux</font> or "
        "<font face='Courier'>linux16</font>. Scroll to the end of that line, "
        "add one space, then type:"
    )
    flow.append(_code("systemd.mask=usbguard.service"))
    P("Press <b>Ctrl+X</b> (or F10) to boot. Log in normally.")
    P("Step 2 &mdash; regenerate proper USBGuard rules:", "H2")
    flow.append(_code(
        "sudo usbguard generate-policy | sudo tee /etc/usbguard/rules.conf > /dev/null\n"
        "sudo chmod 600 /etc/usbguard/rules.conf\n"
        "sudo systemctl unmask usbguard.service\n"
        "sudo systemctl restart usbguard"
    ))
    P(
        "This snapshots the keyboard/mouse you actually have now and writes "
        "them as explicit allow rules. The mask in step 1 was one-time only; "
        "the next normal boot will use the new rules.",
    )
    P("Step 3 &mdash; reboot and confirm:", "H2")
    flow.append(_code("sudo systemctl reboot"))
    P("Keyboard and mouse should work normally on the login screen.")

    # ── 7. What to do if the install hangs
    P("7. If the installer hangs at step 8 or step 9", "H1")
    P("The installer prints sub-step lines such as:", "H2")
    P(
        "&bull; <font face='Courier'>&rarr; systemctl daemon-reload (timeout 15s)</font><br/>"
        "&bull; <font face='Courier'>&rarr; systemctl enable usb-defense.service (timeout 15s)</font><br/>"
        "&bull; <font face='Courier'>==&gt; Starting USB Defense daemon (timeout 45s)&hellip;</font>"
    )
    P(
        "The last line printed is where it is stuck. Each line has a built-in "
        "timeout, so the script aborts with a clear error within 15&ndash;45 seconds; "
        "it cannot truly hang forever.",
    )
    P("Specific cases:", "H2")
    P(
        "<b>&ldquo;New admin password:&rdquo;</b> appears and nothing changes when "
        "you type &mdash; this is normal, getpass hides input. Just type and press Enter."
    )
    P(
        "<b>&ldquo;Press Enter once you have written the code down&rdquo;</b> &mdash; "
        "the recovery code is shown above this line. Write it down on PAPER, "
        "then press Enter. The install is NOT done until you press Enter."
    )
    P(
        "<b>&ldquo;Starting USB Defense daemon&hellip;&rdquo; for &gt;45s</b> &mdash; "
        "the daemon failed to send <font face='Courier'>READY=1</font>. The "
        "installer auto-dumps the last 30 journal lines. Read the Python error, "
        "fix it, then:"
    )
    flow.append(_code("sudo systemctl restart usb-defense.service"))

    # ── 8. USB still won't enumerate
    P("8. If a USB still won't enumerate after install", "H1")
    P(
        "USB Defense is not the only thing that can stop a USB from showing up. "
        "Triage in this order &mdash; the first three checks are free and fast."
    )
    P("Check 1 &mdash; is USBGuard actively blocking it?", "H2")
    flow.append(_code("sudo usbguard list-devices"))
    P(
        "If the device appears with target <font face='Courier'>block</font>, "
        "USBGuard is doing its job &mdash; authorize it through the UI. If the "
        "device does NOT appear at all, USBGuard never saw it. Move to Check 2."
    )
    P("Check 2 &mdash; did the kernel see the device?", "H2")
    flow.append(_code("sudo dmesg --since '30 seconds ago' | grep -i usb"))
    P(
        "Expect lines like <font face='Courier'>new high-speed USB device number...</font> "
        "and a VID:PID. If nothing appears, the kernel never saw the device. "
        "That is a hardware/BIOS issue, not a USB Defense issue."
    )
    P("Check 3 &mdash; Secure Boot and lockdown state:", "H2")
    flow.append(_code(
        "mokutil --sb-state                       # SecureBoot enabled/disabled\n"
        "cat /sys/kernel/security/lockdown        # none / integrity / confidentiality"
    ))
    P(
        "These are FYI only. Neither value blocks USBGuard. Their main use is "
        "ruling out conspiracy theories during triage."
    )
    P("Check 4 &mdash; BIOS USB settings:", "H2")
    P(
        "On managed lab PCs the most common cause of &ldquo;USB won&rsquo;t work&rdquo; "
        "is a BIOS policy. Reboot into the firmware setup (F2 / F10 / Del at boot) "
        "and verify:"
    )
    P(
        "&bull; <b>USB Ports / Front USB / Rear USB</b> &mdash; all set to Enabled.<br/>"
        "&bull; <b>XHCI Hand-off</b> &mdash; Enabled (lets the kernel take over USB 3.x ports).<br/>"
        "&bull; <b>Legacy USB Support</b> &mdash; Enabled (especially for older keyboards).<br/>"
        "&bull; Any vendor &ldquo;Device Guard&rdquo; or &ldquo;BIOS USB whitelist&rdquo; option &mdash; Disabled or configured."
    )
    P("Check 5 &mdash; is it our daemon panicking?", "H2")
    flow.append(_code("sudo journalctl -u usb-defense -n 50 --no-pager"))
    P(
        "Look for Python tracebacks or &ldquo;WHITELIST_TAMPER&rdquo; lines. "
        "If the whitelist is in tamper state every USB is rejected; re-run the "
        "setup wizard or re-enroll through the UI to fix it."
    )

    # ── 9. Quick reference
    P("9. Quick reference", "H1")
    flow.append(_code(
        "# Status and logs\n"
        "sudo systemctl status usb-defense\n"
        "sudo journalctl -u usb-defense -f\n"
        "sudo tail -f /var/log/usb-defense/events.log\n"
        "\n"
        "# Open the UI\n"
        "usb-defense-py -m usbguard_defense.ui.main\n"
        "\n"
        "# Add another user to the IPC group\n"
        "sudo usermod -a -G usbdefense <username>\n"
        "\n"
        "# Regenerate the paper recovery code (invalidates the old one)\n"
        "sudo /usr/lib/usb-defense/venv/bin/python \\\n"
        "     scripts/setup.py --regenerate-recovery\n"
        "\n"
        "# Inspect currently authorized USB devices\n"
        "sudo usbguard list-devices\n"
        "\n"
        "# Full uninstall + wipe secrets\n"
        "sudo ./scripts/uninstall.sh --wipe\n"
        "sudo systemctl reboot"
    ))
    P(
        "&mdash; End of guide &mdash;",
        "Note",
    )

    doc.build(flow)
    print(f"Wrote {out}")
    if out != OUTPUT:
        print(f"NOTE: target {OUTPUT} was locked (PDF viewer open). "
              f"Close it and re-run, or use the timestamped file above.")


if __name__ == "__main__":
    build()
