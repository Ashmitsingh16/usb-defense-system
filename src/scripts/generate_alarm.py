#!/usr/bin/env python3
"""Generate a simple alarm.wav file for the lockdown alarm.

Produces a 2-second siren-style tone alternating between two frequencies.
Run on the Rocky Linux machine after install:
    python3 generate_alarm.py /usr/lib/usb-defense/assets/alarm.wav

No external deps — uses only stdlib (wave, math, struct).
"""

from __future__ import annotations

import math
import struct
import sys
import wave
from pathlib import Path


SAMPLE_RATE = 44100
DURATION_SEC = 2.0
FREQ_LOW = 600
FREQ_HIGH = 900
SWITCH_HZ = 4  # how many high/low alternations per second
AMPLITUDE = 0.6


def generate_samples() -> list[int]:
    samples: list[int] = []
    n_samples = int(SAMPLE_RATE * DURATION_SEC)
    for i in range(n_samples):
        t = i / SAMPLE_RATE
        # Square-wave switch between two pitches
        use_high = int(t * SWITCH_HZ * 2) % 2 == 0
        freq = FREQ_HIGH if use_high else FREQ_LOW
        # Apply a small fade-in/out to avoid clicks at loop boundaries
        envelope = 1.0
        fade = 0.02 * SAMPLE_RATE
        if i < fade:
            envelope = i / fade
        elif i > n_samples - fade:
            envelope = (n_samples - i) / fade
        value = AMPLITUDE * envelope * math.sin(2 * math.pi * freq * t)
        samples.append(int(value * 32767))
    return samples


def write_wav(out_path: Path, samples: list[int]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(b"".join(struct.pack("<h", s) for s in samples))


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "alarm.wav")
    samples = generate_samples()
    write_wav(out, samples)
    print(f"Wrote alarm to {out} ({out.stat().st_size} bytes, {DURATION_SEC}s siren)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
