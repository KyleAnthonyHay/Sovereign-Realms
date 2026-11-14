#!/usr/bin/env python3
"""Synthesises every game sound (no samples, no downloads): SourceArt/Audio/S_<Name>.wav, 44.1 kHz mono 16-bit.

  Tools/.venv/bin/python Tools/audio/gen_sounds.py        then   Tools/ue_py.py Tools/import_audio.py

The names match ESRSound (Source/SovereignRealms/Common/SRAudioSubsystem.h). Bronze-age flavour: bronze clangs,
wood and hide thuds, gut bowstrings, ram's-horn calls, frame drums, a lyre over a drone for the music bed.
Deterministic (fixed seed) so re-running reproduces the same files.
"""
import os
import wave

import numpy as np
from scipy import signal

SR = 44100
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "SourceArt", "Audio")
rng = np.random.default_rng(1717)


def t(dur):
    return np.arange(int(SR * dur)) / SR


def env(dur, attack=0.002, decay=0.2, curve=1.0):
    x = t(dur)
    a = np.clip(x / max(attack, 1e-4), 0, 1)
    d = np.exp(-np.maximum(x - attack, 0) / max(decay, 1e-4)) ** curve
    return a * d


def noise(dur):
    return rng.standard_normal(len(t(dur)))


def bp(x, lo, hi, order=2):
    b, a = signal.butter(order, [lo / (SR / 2), min(hi / (SR / 2), 0.99)], "band")
    return signal.lfilter(b, a, x)


def lp(x, f, order=2):
    b, a = signal.butter(order, min(f / (SR / 2), 0.99), "low")
    return signal.lfilter(b, a, x)


def hp(x, f, order=2):
    b, a = signal.butter(order, f / (SR / 2), "high")
    return signal.lfilter(b, a, x)


def mix(*parts):
    n = max(len(p) for p in parts)
    out = np.zeros(n)
    for p in parts:
        out[:len(p)] += p
    return out


def place(x, at, total):
    out = np.zeros(int(SR * total))
    i = int(SR * at)
    n = min(len(x), len(out) - i)
    out[i:i + n] += x[:n]
    return out


def clang(f0, dur=0.45, ratios=(1.0, 1.59, 2.71, 3.93, 5.4), decay=0.16, bright=1.0):
    x = t(dur)
    s = sum(np.sin(2 * np.pi * f0 * r * x + rng.uniform(0, 6)) * np.exp(-x / (decay / (1 + 0.35 * k))) * (bright ** k) / (1 + k)
            for k, r in enumerate(ratios))
    return s


def thud(f0=95, dur=0.25, drop=0.6, decay=0.07):
    x = t(dur)
    f = f0 * (1 + drop * np.exp(-x / 0.02))
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * env(dur, 0.001, decay)


def pluck(f0, dur, damping=0.996, bright=0.6):
    """Karplus-Strong string."""
    n = int(SR * dur)
    p = max(int(SR / f0), 2)
    buf = rng.uniform(-1, 1, p)
    buf = lp(buf, 1200 + 6000 * bright, 1)
    out = np.zeros(n)
    for i in range(n):
        v = buf[i % p]
        out[i] = v
        buf[i % p] = damping * 0.5 * (v + buf[(i + 1) % p])
    return out


def horn(f0, dur, vib=0.006, bright=0.55, attack=0.08, release=0.25):
    x = t(dur)
    f = f0 * (1 + vib * np.sin(2 * np.pi * 5.2 * x) * np.clip(x / 0.4, 0, 1))
    ph = 2 * np.pi * np.cumsum(f) / SR
    s = sum(np.sin(k * ph) * (bright ** (k - 1)) for k in range(1, 9))
    a = np.clip(x / attack, 0, 1) * np.clip((dur - x) / release, 0, 1)
    s = lp(s * a, 1800 + 2500 * bright)
    breath = bp(noise(dur), 800, 3000) * 0.04 * a
    return s + breath


def drum(f0=150, dur=0.4):
    return mix(thud(f0, dur, 0.9, 0.11), lp(noise(0.05), 2500) * env(0.05, 0.001, 0.012) * 0.6)


def norm(x, peak=0.89):
    x = x - np.mean(x)
    m = np.max(np.abs(x)) or 1.0
    return x / m * peak


def fade(x, fin=0.002, fout=0.01):
    n = len(x)
    a, b = int(SR * fin), int(SR * fout)
    if a:
        x[:a] *= np.linspace(0, 1, a)
    if b:
        x[-b:] *= np.linspace(1, 0, b)
    return x


# Replaced by recorded sounds (Tools/audio/prep_recorded.py): not synthesised, so a re-run never overwrites them.
RECORDED = {"BowRelease", "BuildHammer"}


def write(name, x, peak=0.89):
    if name in RECORDED:
        return
    x = fade(norm(x, peak))
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "S_%s.wav" % name)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    return path


def loop_seamless(x, xfade=1.5):
    """Crossfade the tail into the head so the file loops without a click."""
    n = int(SR * xfade)
    head, tail = x[:n].copy(), x[-n:].copy()
    w = np.linspace(0, 1, n)
    x = x[:-n].copy()
    x[:n] = head * w + tail * (1 - w)
    return x


def main():
    S = {}
    # ---------------------------------------------------------------- combat
    S["SwordHit"] = mix(clang(780, 0.5, decay=0.14), clang(1230, 0.35, decay=0.08) * 0.5,
                        hp(noise(0.03), 2500) * env(0.03, 0.0005, 0.006) * 1.2, thud(140, 0.12, 0.3, 0.03) * 0.5)
    S["ShieldBash"] = mix(thud(85, 0.35, 0.8, 0.09) * 1.4, lp(noise(0.12), 900) * env(0.12, 0.001, 0.03),
                          clang(520, 0.4, decay=0.12, bright=0.7) * 0.45)
    twang = pluck(165, 0.45, 0.993, 0.8)
    whoosh = bp(noise(0.3), 900, 4000) * np.sin(np.pi * np.clip(t(0.3) / 0.3, 0, 1)) ** 2 * 0.35
    S["BowRelease"] = mix(twang * env(0.45, 0.001, 0.12), place(whoosh, 0.02, 0.4))
    S["ArrowHitFlesh"] = mix(lp(noise(0.08), 1400) * env(0.08, 0.001, 0.018), thud(95, 0.12, 0.4, 0.035) * 0.7)
    S["ArrowHitWood"] = mix(bp(noise(0.06), 900, 2600) * env(0.06, 0.0005, 0.01) * 1.3,
                            np.sin(2 * np.pi * 420 * t(0.18)) * env(0.18, 0.0005, 0.04) * 0.6,
                            np.sin(2 * np.pi * 1130 * t(0.1)) * env(0.1, 0.0005, 0.02) * 0.3)
    S["ArrowHitGround"] = lp(noise(0.07), 1100) * env(0.07, 0.001, 0.015)
    fall = mix(thud(70, 0.45, 0.5, 0.12) * 1.3, place(lp(noise(0.25), 1600) * env(0.25, 0.005, 0.07) * 0.6, 0.03, 0.5))
    groan = bp(noise(0.35), 350, 900) * np.sin(np.pi * np.clip(t(0.35) / 0.35, 0, 1)) * 0.35
    S["Death"] = mix(place(groan, 0.0, 0.6), place(fall, 0.12, 0.6))
    # ---------------------------------------------------------------- orders / UI
    tick = lambda f, d=0.03: bp(noise(d), f * 0.7, f * 1.4) * env(d, 0.0003, d * 0.18)
    S["Select"] = mix(tick(2600), place(tick(3400) * 0.6, 0.035, 0.08))
    jingle = sum(place(clang(2800 + 500 * k, 0.12, decay=0.03) * 0.5, 0.025 * k, 0.2) for k in range(3))
    S["Acknowledge"] = mix(jingle, place(lp(noise(0.08), 1500) * env(0.08, 0.003, 0.02) * 0.4, 0.0, 0.2))
    S["AttackOrder"] = mix(drum(160, 0.35), place(drum(130, 0.3) * 0.8, 0.11, 0.45), place(jingle * 0.5, 0.0, 0.45))
    S["UIClick"] = mix(tick(2200, 0.025), np.sin(2 * np.pi * 900 * t(0.03)) * env(0.03, 0.0003, 0.006) * 0.4)
    buzz = lambda d: lp(signal.square(2 * np.pi * 150 * t(d)) * env(d, 0.002, d * 0.6), 900)
    S["UIError"] = mix(buzz(0.09), place(buzz(0.12), 0.12, 0.26))
    # ---------------------------------------------------------------- economy / building
    S["CoinPayout"] = sum(place(clang(rng.uniform(3200, 4600), 0.25, ratios=(1.0, 2.76, 5.4), decay=0.06), 0.045 * k + rng.uniform(0, 0.02), 0.45) * (1 - 0.15 * k)
                          for k in range(4))
    S["GrainPayout"] = bp(noise(0.4), 2500, 9000) * (0.5 + 0.5 * np.sin(2 * np.pi * 23 * t(0.4)) ** 2) * env(0.4, 0.03, 0.12)
    S["BuildPlace"] = mix(thud(60, 0.6, 0.6, 0.18) * 1.5, place(lp(noise(0.5), 2200) * env(0.5, 0.01, 0.12) * 0.5, 0.04, 0.7))
    knock = lambda: mix(thud(240, 0.12, 0.3, 0.025), bp(noise(0.03), 1500, 4000) * env(0.03, 0.0003, 0.006) * 0.6)
    S["BuildHammer"] = mix(knock(), place(knock() * 0.8, 0.16, 0.35))
    fan = mix(place(horn(196, 0.32), 0.0, 1.2), place(horn(294, 0.32), 0.28, 1.2), place(horn(392, 0.6), 0.56, 1.2))
    S["BuildComplete"] = fan
    S["RecruitReady"] = mix(horn(220, 0.55, bright=0.5), place(drum(170, 0.3) * 0.6, 0.0, 0.6))
    S["BuildingHit"] = mix(thud(110, 0.25, 0.4, 0.06), lp(noise(0.12), 1800) * env(0.12, 0.001, 0.03) * 0.8,
                           place(lp(noise(0.2), 3000) * env(0.2, 0.005, 0.05) * 0.25, 0.04, 0.3))
    rumble = lp(np.cumsum(noise(2.8)) * 0.02, 200) * env(2.8, 0.05, 0.9)
    crackle = sum(place(bp(noise(0.05), 800, 4000) * env(0.05, 0.0005, 0.01) * rng.uniform(0.2, 0.7), rng.uniform(0.0, 1.8), 2.8) for _ in range(40))
    S["BuildingCollapse"] = mix(rumble * 3.0, crackle, thud(55, 1.2, 0.4, 0.3) * 1.2)
    S["WarHorn"] = mix(horn(147, 1.9, vib=0.01, bright=0.62, attack=0.25, release=0.6), horn(147 * 1.5, 1.9, vib=0.01, bright=0.4, attack=0.35, release=0.6) * 0.25)
    S["Pickaxe"] = mix(clang(2100, 0.2, ratios=(1.0, 2.3, 3.8), decay=0.04), lp(noise(0.06), 3000) * env(0.06, 0.0005, 0.01) * 0.5)
    S["Hoe"] = mix(lp(noise(0.1), 900) * env(0.1, 0.001, 0.025), thud(120, 0.1, 0.2, 0.02) * 0.4)
    # ---------------------------------------------------------------- match end
    S["Victory"] = mix(*[place(horn(f, d, bright=0.6), at, 3.4) for f, d, at in
                         ((196, 0.4, 0.0), (247, 0.4, 0.35), (294, 0.4, 0.7), (392, 1.6, 1.05), (294, 1.6, 1.05))],
                       place(drum(150, 0.4), 1.05, 3.4), place(drum(150, 0.4), 0.0, 3.4))
    S["Defeat"] = mix(*[place(horn(f, d, bright=0.45, vib=0.012), at, 3.6) for f, d, at in
                        ((220, 0.8, 0.0), (196, 0.8, 0.7), (174.6, 0.8, 1.4), (146.8, 1.8, 2.0))])
    # ---------------------------------------------------------------- beds
    dur = 32.0
    wind = lp(noise(dur), 700) * (0.55 + 0.45 * np.sin(2 * np.pi * t(dur) / 11.0) ** 2) * (0.7 + 0.3 * np.sin(2 * np.pi * t(dur) / 4.3))
    leaves = bp(noise(dur), 3000, 9000) * 0.06 * (0.5 + 0.5 * np.sin(2 * np.pi * t(dur) / 7.0) ** 4)
    birds = np.zeros(len(t(dur)))
    for _ in range(26):
        at = rng.uniform(0.5, dur - 2.0)
        f0 = rng.uniform(2600, 4200)
        for k in range(int(rng.integers(2, 6))):
            d = rng.uniform(0.06, 0.14)
            x = t(d)
            chirp = np.sin(2 * np.pi * np.cumsum(f0 * (1 + 0.35 * np.sin(np.pi * x / d))) / SR) * np.sin(np.pi * x / d) ** 2
            birds += place(chirp * rng.uniform(0.05, 0.12), at + k * rng.uniform(0.09, 0.16), dur)
    S["AmbientLoop"] = loop_seamless(mix(wind * 0.5, leaves, birds))
    # music: a lyre (plucked strings) walking a D dorian figure over a drone and a slow frame drum, ~80 bpm
    mdur = 48.0
    beat = 60 / 80
    scale = [146.8, 164.8, 174.6, 196.0, 220.0, 246.9, 261.6, 293.7, 329.6]
    pattern = [0, 4, 7, 4, 3, 4, 2, 1, 0, 4, 7, 8, 7, 4, 5, 4, 3, 2, 3, 4, 7, 4, 2, 0]
    lyre = np.zeros(len(t(mdur)))
    k = 0
    at = 0.0
    while at < mdur - 2.5:
        n = pattern[k % len(pattern)]
        lyre += place(pluck(scale[n], 2.2, 0.9975, 0.5) * 0.35, at, mdur)
        if k % 4 == 0:
            lyre += place(pluck(scale[n] / 2, 2.5, 0.998, 0.35) * 0.25, at, mdur)
        at += beat * (1.0 if k % 8 != 7 else 2.0)
        k += 1
    drone = sum(np.sin(2 * np.pi * f * t(mdur) + rng.uniform(0, 6)) * a for f, a in ((73.4, 0.18), (110.0, 0.1), (146.8, 0.06)))
    drone = lp(drone * (0.8 + 0.2 * np.sin(2 * np.pi * t(mdur) / 9.0)), 600)
    drums = sum(place(drum(110, 0.6) * 0.35, i * beat * 4, mdur) + place(drum(140, 0.4) * 0.18, i * beat * 4 + beat * 2.5, mdur)
                for i in range(int(mdur / (beat * 4))))
    S["MusicLoop"] = loop_seamless(mix(lyre, drone, drums), 2.0)

    for name, x in S.items():
        peak = 0.6 if name in ("AmbientLoop", "MusicLoop") else 0.89
        print("wrote", write(name, x, peak), "%.2fs" % (len(x) / SR))


if __name__ == "__main__":
    main()
