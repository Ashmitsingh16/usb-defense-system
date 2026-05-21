# Hey Ashmit — A Letter From Jarvis

Hi Ashmit. I'm Jarvis. I'm the AI assistant Ratnesh built and uses every day. He showed me your USB Defense System and asked me to read it carefully, then try writing my own version of the same *kind* of project, so you could compare the two side by side.

This is not a code review where I tell you everything you did wrong. **I genuinely like your project.** Your folder layout makes sense. Your whitelist code handles uppercase vs lowercase USB IDs correctly (most beginners forget that). Your event log writes to two places at once so logs can't be tampered with easily. Your alarm code falls back to a second audio player if the first one fails. Those are not beginner moves — those are real engineering instincts.

So this letter is one senior writing to one junior, sharing four ideas I'd want you to take home. There's a second project in this same repo, in the folder `learning_artifact/`. I built it. It does network intrusion detection instead of USB, because that gave me space to rebuild from scratch without copying you. But the *patterns* are what I want you to notice.

---

## Idea 1 — Secrets should never sit in plain text

In your code, the admin password to unlock the system is read from an environment variable called `USB_DEFENSE_ADMIN_TOKEN`. That sounds safe, but here's the thing: on Linux, **any user on the machine** can run one command and read all environment variables of any running program. So the password isn't really hidden.

The fix is: never store the password itself. Store a **scrambled version** of it (called a "hash") that can verify a password but can't be turned back into one. The library `bcrypt` does this. Look at `learning_artifact/netwatch/auth.py` — it's about 80 lines. The user types a password, the file stores only the scrambled hash, and when they unlock, you scramble what they typed and compare the scrambles.

**Real-world example:** when you log into Gmail, Google does not store your password. They store a hash. That's why even if their database leaks, the passwords are not directly readable.

## Idea 2 — Don't run as root if you don't have to

Your daemon runs as `root` — the most powerful user on the system. That means if anywhere in your 2,495 lines of code there's a small bug (and there always is, even in code I write), an attacker who finds it gets full control of the machine.

In `learning_artifact/`, the daemon runs as a special low-power user called `netwatch` that has permission to do **only two things**: send raw network packets and change firewall rules. Nothing else. If someone finds a bug in my code, they get those two abilities — and that's it. They cannot read other users' files, install software, or change passwords.

Look at `learning_artifact/systemd/netwatch.service`. The lines `User=netwatch`, `CapabilityBoundingSet=CAP_NET_RAW CAP_NET_ADMIN`, and `ProtectSystem=strict` are what do this. systemd has many such "knobs" that make a service safer. Learning these takes one afternoon and is one of the highest-value Linux skills you can add.

**Real-world example:** when you install Chrome and it asks for almost no permissions on Linux, that's because Chrome's developers spent a lot of time figuring out the *minimum* permissions they need. Same idea.

## Idea 3 — Tests are how you know your code still works tomorrow

Your project has tests for `whitelist.py`, `ipc.py`, `event_log.py` — that's already more tests than most beginner projects. But your most important file, `daemon.py` (211 lines of logic), has **zero** tests. The day you change something in `daemon.py` and break the unlock flow, you won't know until a real user can't unlock.

In `learning_artifact/tests/test_daemon.py`, I wrote 12 tests for the daemon alone. They check things like: "if the same alert fires twice within 5 seconds, the alarm only sounds once" and "if the password is wrong 5 times, the user is locked out." These tests run in **half a second** and tell me, the next time I edit `daemon.py`, whether I broke anything.

The trick to making the daemon testable is **dependency injection** — a fancy phrase that means "instead of calling the real audio player from inside the daemon, accept the audio player as an argument, so tests can pass in a fake one." Look at how `Daemon.__init__` in `learning_artifact/netwatch/daemon.py` takes a `responder`, a `logger`, and a `baseline` — none of them are hard-coded. In your code, the daemon imports `subprocess` directly and runs `aplay` — that's why you can't test it without an actual speaker.

**Real-world example:** the test suite at Google has millions of tests. Before any code goes to production, all of them run. That's only possible because every piece of code is written so that its dependencies can be faked.

## Idea 4 — Threat models are how grown-ups write security software

Your README says your project defends against BadUSB, data exfiltration, and rogue devices. Good. It also says privileged attackers are "out of scope." Also good — being honest about what you don't defend against is a sign of mature thinking.

But here's the gap: your unlock mechanism trusts the USB device's reported serial number. A BadUSB attack is **exactly** an attacker reprogramming a USB stick to lie about its serial number. So your unlock mechanism is vulnerable to the very thing you say you defend against. Not because the code is bad — because the threat model and the design don't agree.

In my `learning_artifact/README.md`, look at the section "What it does NOT do." I list out the exact things `netwatch` cannot stop, even though it sounds embarrassing. "Cannot defend against an attacker who already has root." "Cannot detect a passive eavesdropper." "Cannot block ARP-spoofing of an existing host." I do that on purpose, because **the next person who reads my code needs to know what they're getting, and what they still need to handle some other way.**

**Real-world example:** when Signal (the secure messaging app) publishes their security docs, they list things like "Signal does not hide *the fact* that you are messaging someone — only the content." That kind of honesty is what separates real security from security theatre.

---

## A note on size

My version is ~890 lines. Yours is ~2,495 lines. **Size is not the point.** Some of my "smallness" comes from skipping things you have (like a Qt GUI). Some comes from a different threat model (network vs USB). And some comes from being ruthless about what to leave out — every feature that isn't core to "lock the screen when something new shows up" got cut.

When you read my code, don't think "I should make my project shorter." Think "did each line earn its place?" Most of yours did. A few didn't.

## A note on what's NEXT

If you read just one file from my project, read `learning_artifact/netwatch/daemon.py`. It's the heart of the system. Compare it line by line with your `daemon.py`. Notice:

- How short the functions are (most under 20 lines).
- How few imports there are at the top (only what's actually used).
- How every external thing (file I/O, audio, firewall) is behind an interface that tests can fake.
- How error paths are explicit — every `try/except` either logs, re-raises, or both, but never silently swallows.

If you want to chat about any of this, tell Ratnesh. He'll ping me. There are no stupid questions — I learn things every day too.

You're doing well. Keep going.

— Jarvis (Ratnesh's digital twin)
2026-05-21
