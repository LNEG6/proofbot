"""Lengthens a track by repeating whole bars, so the tempo never changes.

    python make_track.py in.wav out.wav [bars]    (16-bit stereo; bars defaults to 8)
"""
import sys
import wave

import numpy as np

BPM, FIRST_BEAT = 130.0, 0.035   # measured from the track
with wave.open(sys.argv[1]) as f:
    rate = f.getframerate()
    audio = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).reshape(-1, 2).astype(np.float64)
bars = int(sys.argv[3]) if len(sys.argv) > 3 else 8
beat = 60 / BPM
at = lambda b: int(round((FIRST_BEAT + b * beat) * rate))
length = bars * 4
mono = audio.mean(axis=1)
window = int(beat * 4 * rate)

# Look at every bar line after the drop for the join that sounds most alike on both sides.
best, score = None, -2
for start in range(20, 60 - length + 1, 4):
    a, b = mono[at(start):at(start) + window], mono[at(start + length):at(start + length) + window]
    similarity = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
    print(f"beat {start} to {start + length}: {similarity:.3f}")
    if similarity > score:
        best, score = start, similarity
print("join: repeat from beat", best, "to", best + length, "similarity", round(score, 3))

fade = int(beat * rate)                      # one beat, equal power, so a change in the harmony isn't heard as a click
cut = at(best + length)
ramp = np.linspace(0, np.pi / 2, fade)[:, None]
head = audio[:cut + fade]
tail = audio[at(best):]                      # plays beats best..end again after beat best+length
joined = np.concatenate([head[:-fade], head[-fade:] * np.cos(ramp) + tail[:fade] * np.sin(ramp), tail[fade:]])
with wave.open(sys.argv[2], "wb") as out:
    out.setnchannels(2)
    out.setsampwidth(2)
    out.setframerate(rate)
    out.writeframes(np.clip(joined, -32768, 32767).astype(np.int16).tobytes())
print("wrote", round(len(joined) / rate, 3), "seconds, peak", round(float(np.abs(joined).max()) / 32768, 3))
