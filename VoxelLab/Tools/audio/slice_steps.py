"""Cut the footstep recordings into one-shot steps.

    ../Tools/.venv/bin/python Tools/audio/slice_steps.py [-v]

  SourceArt/Audio/Raw/Footsteps<Surface>.wav  ->  SourceArt/Audio/S_Step_<Surface>_<n>.wav   (mono, 48 kHz, 16 bit)

Each recording is one take of many steps. A step is a burst of the loudness envelope (heel and toe together: bursts
closer than GAP are one step). Per step: start a little before the first rise (LEAD), run to where it has died away
(or just short of the next step), fade out. Thrown out: steps cut by the ends of the file, weak ones, ones much longer
than the rest (two steps run together) and ones that ring into the next. Of what is left the KEEP nearest the
typical loudness and length are kept, in the order they were recorded, and all brought to one loudness (the same for
every surface, so the game's volumes mean the same on each).
"""
import os
import sys

import numpy as np
from scipy import signal
from scipy.io import wavfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RAW = os.path.join(ROOT, "SourceArt", "Audio", "Raw")
OUT = os.path.join(ROOT, "SourceArt", "Audio")
SURFACES = ["Dirt", "Cement", "Wood", "Carpet"]

SR = 48000          # output rate
KEEP = 8            # variations per surface
LEAD = 0.008        # s of lead-in before the onset
FADE_IN = 0.003
FADE_OUT = 0.060
GAP = 0.20          # s: bursts closer than this are one step (heel, then toe)
MAX_LEN = 0.60      # s
MIN_LEN = 0.12
TAIL_DB = -34.0     # the step ends where its envelope falls this far under its peak
TARGET_DB = -20.0   # loudness of the loudest 50 ms of every clip (RMS, dBFS)
PEAK_DB = -1.0      # and no sample over this
VERBOSE = "-v" in sys.argv


def db(x):
    return 20.0 * np.log10(np.maximum(x, 1e-9))


def load(path):
    sr, d = wavfile.read(path)
    x = d.astype(np.float64)
    x /= float(np.iinfo(d.dtype).max) if np.issubdtype(d.dtype, np.integer) else 1.0
    if x.ndim > 1:
        x = x.mean(axis=1)
    if sr != SR:
        g = np.gcd(sr, SR)
        x = signal.resample_poly(x, SR // g, sr // g)
    # rumble out (handling noise, room hum): steps have nothing useful under 40 Hz
    sos = signal.butter(2, 40.0, "highpass", fs=SR, output="sos")
    return signal.sosfiltfilt(sos, x)


def envelope(x, ms):
    n = max(1, int(SR * ms / 1000.0))
    return np.sqrt(signal.fftconvolve(x * x, np.ones(n) / n, mode="same").clip(0))


def loud(x):
    """RMS of the loudest 50 ms."""
    return float(envelope(x, 50.0).max())


def find_steps(x):
    env = envelope(x, 6.0)
    floor = np.percentile(env, 15)
    peak = np.percentile(env, 99.9)
    on = max(floor * 4.0, peak * 10 ** (-22.0 / 20.0))      # a burst: well over the floor
    hot = env > on
    edges = np.flatnonzero(np.diff(hot.astype(np.int8)))
    if hot[0]:
        edges = np.r_[0, edges]
    if hot[-1]:
        edges = np.r_[edges, len(env) - 1]
    bursts = [(int(a), int(b)) for a, b in zip(edges[0::2], edges[1::2]) if b - a > SR * 0.004]
    steps = []
    for a, b in bursts:
        if steps and a - steps[-1][1] < GAP * SR:
            steps[-1][1] = b
        else:
            steps.append([a, b])
    return env, floor, steps


def slice_surface(name):
    x = load(os.path.join(RAW, "Footsteps%s.wav" % name))
    env, floor, steps = find_steps(x)
    cands, rejected = [], []
    for i, (a, b) in enumerate(steps):
        nxt = steps[i + 1][0] if i + 1 < len(steps) else len(x)
        pk = env[a:b + 1].max()
        # onset: back from the burst to where the envelope is still near the floor
        s = a
        lim = max(0, a - int(0.03 * SR))
        while s > lim and env[s] > max(floor * 2.0, pk * 10 ** (-40.0 / 20.0)):
            s -= 1
        s = max(0, s - int(LEAD * SR))
        # end: where it has died away after the last burst
        e = b
        quiet = max(floor * 1.5, pk * 10 ** (TAIL_DB / 20.0))
        stop = min(len(x), s + int(MAX_LEN * SR), nxt - int(0.02 * SR))
        while e < stop and env[e] > quiet:
            e += 1
        rang = e >= stop and env[min(e, len(env) - 1)] > quiet * 2.0
        e = min(len(x), e + int(FADE_OUT * SR * 0.5))
        info = dict(i=i, t=s / SR, len=(e - s) / SR, pk=db(pk), s=s, e=e)
        if a < int(0.01 * SR) or (i + 1 == len(steps) and len(x) - b < int(0.05 * SR)):
            rejected.append((info, "cut by the end of the take"))
        elif info["len"] < MIN_LEN:
            rejected.append((info, "too short (a click, not a step)"))
        elif rang:
            rejected.append((info, "runs into the next step"))
        else:
            info["loud"] = db(loud(x[s:e]))
            cands.append(info)
    if cands:
        ml = np.median([c["loud"] for c in cands])
        mlen = np.median([c["len"] for c in cands])
        ok = []
        for c in cands:
            if c["loud"] < ml - 6.0:
                rejected.append((c, "weak (%.1f dB under the rest)" % (ml - c["loud"])))
            elif c["len"] > mlen * 1.6:
                rejected.append((c, "doubled (%.2f s against %.2f s)" % (c["len"], mlen)))
            else:
                ok.append(c)
        # the most typical ones, then back in recorded order
        ok.sort(key=lambda c: abs(c["loud"] - ml) / 3.0 + abs(c["len"] - mlen) / max(mlen, 1e-3))
        for c in ok[KEEP:]:
            rejected.append((c, "spare (further from the typical step)"))
        ok = sorted(ok[:KEEP], key=lambda c: c["s"])
    else:
        ok = []
    for old in os.listdir(OUT):
        if old.startswith("S_Step_%s_" % name) and old.endswith(".wav"):
            os.remove(os.path.join(OUT, old))
    print("%s: %d steps found, %d kept, %d rejected" % (name, len(steps), len(ok), len(rejected)))
    for n, c in enumerate(ok, 1):
        clip = x[c["s"]:c["e"]].copy()
        fi, fo = int(FADE_IN * SR), min(int(FADE_OUT * SR), len(clip) // 2)
        clip[:fi] *= np.linspace(0.0, 1.0, fi)
        clip[-fo:] *= np.cos(np.linspace(0.0, np.pi / 2, fo)) ** 2
        gain = 10 ** (TARGET_DB / 20.0) / loud(clip)
        gain = min(gain, 10 ** (PEAK_DB / 20.0) / np.abs(clip).max())
        clip *= gain
        path = os.path.join(OUT, "S_Step_%s_%d.wav" % (name, n))
        wavfile.write(path, SR, np.round(clip * 32767.0).astype(np.int16))
        print("  %-22s from %5.2f s  %.3f s  gain %+5.1f dB  loud %5.1f dB  peak %5.1f dB" % (
            os.path.basename(path), c["t"], len(clip) / SR, db(gain), db(loud(clip)), db(np.abs(clip).max())))
    for c, why in sorted(rejected, key=lambda r: r[0]["s"]):
        if VERBOSE or not why.startswith("spare"):
            print("  rejected %5.2f s (%.2f s): %s" % (c["t"], c["len"], why))
    return len(ok)


if __name__ == "__main__":
    for s in SURFACES:
        slice_surface(s)
