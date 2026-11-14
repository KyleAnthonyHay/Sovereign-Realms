#!/usr/bin/env python3
"""Turns the recorded sounds in SourceArt/Audio/Recorded into game sounds (SourceArt/Audio/S_<Name>[_N].wav):
48 kHz mono 16-bit (positioned sounds must be mono), peak-normalised, silent tails trimmed. Run with the project's
venv: Tools/.venv/bin/python Tools/audio/prep_recorded.py, then import (Tools/ue_py.py Tools/import_audio.py).

  bow_release_1/2.wav  -> S_BowRelease, S_BowRelease_2      (replace the synthesised one; gen_sounds.py skips it)
  arrow_fly.wav        -> S_ArrowFly                         (rides on each arrow; pitched down for catapult stones)
  sword_swing.wav      -> S_SwordSwing                       (melee wind-up)
  horse_snort_1/2.wav  -> S_HorseSnort, S_HorseSnort_2
  horse_pass_by.wav    -> S_GallopLoop                       (its loudest two seconds, cross-faded into a loop)
  fire_crackle.wav     -> S_FireCrackle                      (a flare-up: when a building catches, and now and then)
                       -> S_FireLoop                         (a steady burn: a low flame roar from shaped noise with
                                                              crackle grains cut from the recording scattered through
                                                              it; built circular, so it loops without a seam)
  death_grunt_1..4.wav -> S_Death, S_Death_2..4             (a troop falls; replaces the synthesised cry)
  horse_neigh.wav      -> S_HorseNeigh                       (a rider leaves the stable; a charge lands)
  marching.wav         -> S_MarchLoop                        (twelve steady seconds - twelve paces - cross-faded)
  catapult_break.wav   -> S_CatapultBreak                    (a catapult destroyed: timber bursting apart)
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


def fire_loop(x, seconds=6.0, grains=46, seed=7):
    """A seamless burning-fire bed: periodic low noise (the roar), slowly breathing, with crackles from x."""
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    # the roar: noise shaped in the frequency domain (1/f, 70-900 Hz) and turned back with an inverse FFT, which
    # makes it exactly periodic over n samples
    f = np.fft.rfftfreq(n, 1.0 / SR)
    spec = (rng.normal(size=len(f)) + 1j * rng.normal(size=len(f))) / np.maximum(f, 20.0) ** 0.5
    spec *= 1.0 / (1.0 + (f / 900.0) ** 4) * (1.0 - 1.0 / (1.0 + (f / 70.0) ** 4))
    roar = np.fft.irfft(spec, n)
    roar /= np.sqrt(np.mean(roar ** 2))
    t = np.arange(n) / n
    breathe = 0.78 + 0.12 * np.sin(2 * np.pi * 2 * t + 0.4) + 0.08 * np.sin(2 * np.pi * 5 * t + 1.3)   # whole cycles: periodic
    out = roar * breathe * 0.09
    # crackles: short grains round the recording's transients, placed at random (wrapping round the end)
    env = np.abs(x)
    peaks = [i for i in range(int(0.05 * SR), len(x) - int(0.06 * SR), int(0.004 * SR)) if env[i] > 0.12]
    for _ in range(grains):
        c = peaks[rng.integers(len(peaks))]
        g_len = int(rng.uniform(0.03, 0.09) * SR)
        g = x[c - g_len // 4: c - g_len // 4 + g_len] * np.hanning(g_len)
        at = rng.integers(n)
        idx = (at + np.arange(g_len)) % n
        out[idx] += g * rng.uniform(0.15, 0.7)
    return out


def main():
    write("BowRelease", trim(read("bow_release_1.wav")))
    write("BowRelease_2", trim(read("bow_release_2.wav")))
    write("ArrowFly", trim(read("arrow_fly.wav")), peak=0.8)
    write("SwordSwing", trim(read("sword_swing.wav")))
    write("HorseSnort", trim(read("horse_snort_1.wav")), peak=0.8)
    write("HorseSnort_2", trim(read("horse_snort_2.wav")), peak=0.8)
    write("GallopLoop", loop(read("horse_pass_by.wav"), 0.95, 3.15, 0.25), peak=0.8)
    write("CatapultBreak", trim(read("catapult_break.wav")))
    for k in range(4):
        write("Death" if k == 0 else "Death_%d" % (k + 1), trim(read("death_grunt_%d.wav" % (k + 1))), peak=0.85)
    write("HorseNeigh", trim(read("horse_neigh.wav")), peak=0.85)
    write("MarchLoop", loop(read("marching.wav"), 1.5, 13.8, 0.3), peak=0.8)
    fire = read("fire_crackle.wav")
    write("FireCrackle", trim(fire), peak=0.8)
    write("FireLoop", fire_loop(fire / max(np.abs(fire).max(), 1e-6)), peak=0.7)
    for k, hit in enumerate(split_hits(read("hammer_nail.wav"))[:6]):
        write("BuildHammer" if k == 0 else "BuildHammer_%d" % (k + 1), trim(hit), peak=0.8)


if __name__ == "__main__":
    main()
