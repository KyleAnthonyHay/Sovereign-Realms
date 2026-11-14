#!/usr/bin/env python3
"""Turns the recorded sounds in SourceArt/Audio/Recorded into game sounds (SourceArt/Audio/S_<Name>[_N].wav):
48 kHz mono 16-bit (positioned sounds must be mono), peak-normalised, silent tails trimmed. Run with the project's
venv: Tools/.venv/bin/python Tools/audio/prep_recorded.py, then import (Tools/ue_py.py Tools/import_audio.py).

  bow_release_1/2.wav  -> S_BowRelease, S_BowRelease_2      (replace the synthesised one; gen_sounds.py skips it)
  arrow_fly.wav        -> S_ArrowFly                         (rides on each arrow; pitched down for catapult stones)
  sword_swing.wav      -> S_SwordSwing                       (melee wind-up)
  horse_snort_1/2.wav  -> S_HorseSnort, S_HorseSnort_2
  horse_pass_by.wav    -> S_GallopLoop                       (its loudest two seconds, cross-faded into a loop)
  hammer_nail.wav      -> S_BuildHammer, S_BuildHammer_2..5  (its five blows, one take each; replaces the synthesised one)
Uses macOS afconvert to read the 24-bit / 96 kHz / stereo originals.
"""
import os
import subprocess
import tempfile
import wave

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "SourceArt", "Audio", "Recorded")
OUT = os.path.join(ROOT, "SourceArt", "Audio")
SR = 48000


def read(name):
    tmp = os.path.join(tempfile.mkdtemp(), "x.wav")
    subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@%d" % SR, "-c", "1", os.path.join(SRC, name), tmp], check=True)
    with wave.open(tmp) as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float64) / 32768.0


def trim(x, floor_db=-55.0):
    env = np.abs(x)
    above = np.nonzero(env > 10 ** (floor_db / 20.0))[0]
    if len(above) == 0:
        return x
    x = x[max(above[0] - int(0.003 * SR), 0): min(above[-1] + int(0.02 * SR), len(x))]
    fade = min(len(x) // 4, int(0.03 * SR))
    x = x.copy()
    x[-fade:] *= np.linspace(1.0, 0.0, fade)
    return x


def write(name, x, peak=0.89):
    x = x * (peak / max(np.abs(x).max(), 1e-6))
    with wave.open(os.path.join(OUT, "S_%s.wav" % name), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    print("wrote S_%s.wav  %.2f s" % (name, len(x) / SR))


def loop(x, start, end, xfade):
    """x[start:end] made seamless: its last xfade seconds blend into its first."""
    a, b, f = int(start * SR), int(end * SR), int(xfade * SR)
    seg = x[a:b].copy()
    t = np.linspace(0.0, 1.0, f)
    head = seg[:f] * np.sqrt(t) + seg[-f:] * np.sqrt(1.0 - t)    # equal-power crossfade
    return np.concatenate([head, seg[f:-f]])


def split_hits(x, threshold=0.5, min_gap=0.15):
    """Cuts a run of separate blows into one clip per blow (each from its onset to just before the next)."""
    env = np.abs(x)
    onsets, last = [], -min_gap * SR
    for i in np.nonzero(env > threshold)[0]:
        if i - last >= min_gap * SR:
            onsets.append(i)
        last = i if i - last >= min_gap * SR else last
    cuts = onsets + [len(x)]
    return [x[max(cuts[k] - int(0.002 * SR), 0): cuts[k + 1] - int(0.01 * SR)] for k in range(len(onsets))]


def main():
    write("BowRelease", trim(read("bow_release_1.wav")))
    write("BowRelease_2", trim(read("bow_release_2.wav")))
    write("ArrowFly", trim(read("arrow_fly.wav")), peak=0.8)
    write("SwordSwing", trim(read("sword_swing.wav")))
    write("HorseSnort", trim(read("horse_snort_1.wav")), peak=0.8)
    write("HorseSnort_2", trim(read("horse_snort_2.wav")), peak=0.8)
    write("GallopLoop", loop(read("horse_pass_by.wav"), 0.95, 3.15, 0.25), peak=0.8)
    for k, hit in enumerate(split_hits(read("hammer_nail.wav"))[:6]):
        write("BuildHammer" if k == 0 else "BuildHammer_%d" % (k + 1), trim(hit), peak=0.8)


if __name__ == "__main__":
    main()
