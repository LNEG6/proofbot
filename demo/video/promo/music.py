"""An original soundtrack for the film, made from sine waves and noise, so there is no licence to worry about.

    python music.py out.wav
"""
import sys
import wave

import numpy as np

RATE, LENGTH = 44100, 65.5
CUTS = [6.9, 10.3, 15.6, 28.2, 34.2, 46.0, 51.5, 57.5, 60.8]   # scene changes in index.html
DROP = 24.1                                               # the wrong paths die
BAR = 4.8
CHORDS = [(110.0, 164.81, 220.0, 261.63), (87.31, 130.81, 174.61, 261.63),
          (130.81, 164.81, 196.0, 246.94), (98.0, 146.83, 196.0, 293.66)]
n = int(RATE * LENGTH)
t = np.arange(n) / RATE
rng = np.random.default_rng(7)


def envelope(at, attack, decay):
    x = t - at
    return np.where(x < 0, 0.0, np.minimum(x / attack, 1.0) * np.exp(-np.maximum(x - attack, 0) / decay))


def lowpass(signal, amount):
    out = np.zeros_like(signal)
    level = 0.0
    for i, value in enumerate(signal):
        level += amount * (value - level)
        out[i] = level
    return out


left, right = np.zeros(n), np.zeros(n)

# Slow pad: four detuned chords, fading into each other.
for index in range(int(LENGTH / BAR) + 1):
    start = index * BAR
    shape = np.clip((t - start) / 1.6, 0, 1) * np.clip((start + BAR + 1.6 - t) / 1.6, 0, 1)
    for note in CHORDS[index % 4]:
        for detune, pan in ((0.997, 0.8), (1.003, 0.2)):
            tone = np.sin(2 * np.pi * note * detune * t + index) + 0.25 * np.sin(4 * np.pi * note * detune * t)
            left += tone * shape * pan * 0.028
            right += tone * shape * (1 - pan) * 0.028

# A quiet pulse, a little faster once the paths start spreading.
for beat in np.arange(0.6, LENGTH - 3, 1.2):
    level = 0.05 if beat < 15.6 else 0.09
    hit = np.sin(2 * np.pi * 55 * t) * envelope(beat, 0.008, 0.16) * level
    left += hit
    right += hit

# High shimmer while the paths spread, cut off when they die.
rise = np.clip((t - 16.0) / (DROP - 16.0), 0, 1) ** 2 * (t < DROP)
shimmer = lowpass(rng.normal(0, 1, n), 0.14)
shimmer -= lowpass(shimmer, 0.01)
left += shimmer * rise * 0.22
right += np.roll(shimmer, 900) * rise * 0.22

# The drop: a deep hit, then a clean high note for the one line that's left.
deep = np.sin(2 * np.pi * 41.2 * t) * envelope(DROP, 0.01, 1.3) * 0.5
left += deep
right += deep
for note, gain in ((880.0, 0.05), (1318.5, 0.03)):
    ping = np.sin(2 * np.pi * note * t) * envelope(DROP + 0.25, 0.02, 2.2) * gain
    left += ping
    right += ping

# A soft whoosh into every scene change.
whoosh = lowpass(rng.normal(0, 1, n), 0.05)
for cut in CUTS:
    shape = np.clip(1 - np.abs(t - cut) / 0.45, 0, 1) ** 2
    left += whoosh * shape * 0.5
    right += whoosh * shape * 0.5

# Warning tone when the contradiction stops the job.
stop = 34.2 + 6.2
alert = np.sin(2 * np.pi * 220 * t) * envelope(stop, 0.01, 0.5) * 0.09 + np.sin(2 * np.pi * 277.18 * t) * envelope(stop, 0.01, 0.5) * 0.07
left += alert
right += alert

fade = np.clip(t / 1.2, 0, 1) * np.clip((LENGTH - t) / 3.0, 0, 1)
stereo = np.stack([left * fade, right * fade], axis=1)
stereo = np.tanh(stereo * 1.4)
stereo *= 0.8 / np.abs(stereo).max()
with wave.open(sys.argv[1], "wb") as out:
    out.setnchannels(2)
    out.setsampwidth(2)
    out.setframerate(RATE)
    out.writeframes((stereo * 32767).astype(np.int16).tobytes())
print("wrote", sys.argv[1], f"{LENGTH:.0f}s, rms {20 * np.log10(np.sqrt((stereo ** 2).mean())):.1f} dB")
