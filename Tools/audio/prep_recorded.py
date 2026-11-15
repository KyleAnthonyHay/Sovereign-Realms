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

CC0 sounds found online (SourceArt/Audio/Recorded/cc0, sources in its CREDITS.md):
  impactBell_heavy     -> S_BellCastle      (selecting the castle)
  sheep, birds         -> S_Sheep, S_Birds  (the farm: selecting it, and its life)
  impactMining         -> S_Mining          (selecting a mine)
  creak1-3             -> S_Creak           (watchtower; the catapult's arm, pitched down)
  drawKnife1-3         -> S_BladeDraw       (selecting the barracks)
  blacksmith, anvil    -> S_Anvil           (the barracks' armourer at work)
  impactPlank_medium   -> S_TargetThunk     (the archery range: arrows into the butts)
  saw (cut in strokes), chop -> S_Woodwork  (the siege workshop; sites going up)
  impactWood_heavy + impactSoft_heavy -> S_StoneImpact (a catapult stone landing)
  crowd                -> S_BattleLoop      (the roar over a big fight)
  wind_excerpt         -> S_WindLoop        (the high wind when zoomed far out)

Uses macOS afconvert to read the originals (24-bit / 96 kHz / stereo wav, ogg, flac) and soundfile to load them.
"""
import os
import subprocess
import tempfile
import wave

import numpy as np
import soundfile as sf

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "SourceArt", "Audio", "Recorded")
OUT = os.path.join(ROOT, "SourceArt", "Audio")
SR = 48000


def read(name):
    tmp = os.path.join(tempfile.mkdtemp(), "x.wav")
    subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@%d" % SR, "-c", "1", os.path.join(SRC, name), tmp], check=True)
    a, _ = sf.read(tmp)
    return a if a.ndim == 1 else a.mean(axis=1)


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


def cc0(name):
    return read(os.path.join("cc0", name))


def takes(base, clips, peak=0.85):
    for k, c in enumerate(clips):
        write(base if k == 0 else "%s_%d" % (base, k + 1), c, peak=peak)


def loudest(x, seconds, count):
    """The count loudest non-overlapping windows of x, faded at both ends."""
    n = int(seconds * SR)
    hop = n // 4
    scores = sorted(((np.sqrt(np.mean(x[i:i + n] ** 2)), i) for i in range(0, len(x) - n, hop)), reverse=True)
    picked = []
    for _, i in scores:
        if all(abs(i - j) >= n for j in picked):
            picked.append(i)
        if len(picked) == count:
            break
    f = int(0.08 * SR)
    out = []
    for i in sorted(picked):
        c = x[i:i + n].copy()
        c[:f] *= np.linspace(0, 1, f)
        c[-f:] *= np.linspace(1, 0, f)
        out.append(c)
    return out


def main_cc0():
    takes("BellCastle", [trim(cc0("impactBell_heavy_00%d.ogg" % k)) for k in (0, 1)], peak=0.8)
    takes("Sheep", [trim(cc0("sheep.flac"))])
    takes("Birds", loudest(cc0("birds.ogg"), 1.6, 3), peak=0.6)
    takes("Mining", [trim(cc0("impactMining_00%d.ogg" % k)) for k in range(5)])
    takes("Creak", [trim(cc0("creak%d.ogg" % k)) for k in (1, 2, 3)], peak=0.8)
    takes("BladeDraw", [trim(cc0("drawKnife%d.ogg" % k)) for k in (1, 2, 3)], peak=0.8)
    takes("Anvil", [trim(cc0("blacksmith.wav")), trim(cc0("anvil.ogg")[: int(1.6 * SR)])], peak=0.75)
    takes("TargetThunk", [trim(cc0("impactPlank_medium_00%d.ogg" % k)) for k in range(5)])
    saw = cc0("saw.ogg")
    strokes = [saw[int(a * SR): int((a + 1.1) * SR)].copy() for a in (0.3, 1.5, 2.7, 3.9)]
    for c in strokes:
        f = int(0.06 * SR)
        c[:f] *= np.linspace(0, 1, f)
        c[-f:] *= np.linspace(1, 0, f)
    takes("Woodwork", strokes + [trim(cc0("chop.ogg"))], peak=0.75)
    stones = []
    for k in range(5):
        a, b = trim(cc0("impactWood_heavy_00%d.ogg" % k)), trim(cc0("impactSoft_heavy_00%d.ogg" % k))
        m = np.zeros(max(len(a), len(b)))
        m[:len(a)] += a / max(np.abs(a).max(), 1e-6)
        m[:len(b)] += 0.8 * b / max(np.abs(b).max(), 1e-6)
        stones.append(m)
    takes("StoneImpact", stones, peak=0.9)
    write("BattleLoop", loop(cc0("crowd.ogg"), 1.0, 26.0, 0.6), peak=0.7)
    write("WindLoop", loop(cc0("wind_excerpt.wav"), 0.5, 23.5, 1.5), peak=0.7)


def mix(a, b, gain_b=0.8, delay=0.0):
    """Two takes layered (b a little later), each peak-normalised first."""
    a = a / max(np.abs(a).max(), 1e-6)
    b = b / max(np.abs(b).max(), 1e-6)
    d = int(delay * SR)
    m = np.zeros(max(len(a), len(b) + d))
    m[:len(a)] += a
    m[d:d + len(b)] += gain_b * b
    return m


def pitch(x, factor):
    """x played factor times faster (higher and shorter), by resampling."""
    n = int(len(x) / factor)
    return np.interp(np.linspace(0.0, len(x) - 1.0, n), np.arange(len(x)), x)


def main_replace():
    """Every sound that used to be synthesised (Tools/audio/gen_sounds.py) now comes from CC0 recordings."""
    takes("SwordHit", [trim(cc0("sword_clash_%d.ogg" % k)) for k in range(1, 7)])
    takes("ShieldBash", [trim(cc0("shield_block_%d.ogg" % k)) for k in range(1, 7)])
    for k in range(1, 4):   # more takes for the melee wind-up (the first is Recorded/sword_swing.wav)
        write("SwordSwing_%d" % (k + 1), trim(cc0("sword_swing_%d.ogg" % k)))
    takes("ArrowHitFlesh", [trim(cc0("impactPunch_medium_00%d.ogg" % k)) for k in range(5)])
    takes("ArrowHitWood", [trim(cc0("impactWood_light_00%d.ogg" % k)) for k in range(5)])
    takes("ArrowHitGround", [trim(cc0("impactSoft_medium_00%d.ogg" % k)) for k in range(5)], peak=0.7)
    takes("Select", [trim(cc0(n)) for n in ("ui_click1.ogg", "ui_click2.ogg")], peak=0.7)   # a crisp click
    takes("AttackAlert", [trim(cc0("question_002.ogg"))], peak=0.75)   # under attack: a short notification, no horn
    # a move order: a boot's dull thud with a soft wooden click on top (the click carries on small speakers)
    takes("Acknowledge", [mix(trim(cc0("footstep_wood_00%d.ogg" % k)), trim(cc0("drop_00%d.ogg" % d)), 0.45, 0.004)
                          for k, d in ((0, 2), (2, 3), (4, 4))], peak=0.6)
    takes("AttackOrder", [trim(cc0("blade_0%d.ogg" % k)) for k in (1, 2, 3)], peak=0.75)
    takes("UIClick", [trim(cc0("click_001.ogg"))], peak=0.7)   # (the pack's other clicks are only ~10 ms)
    takes("UIError", [trim(cc0("error_002.ogg")), trim(cc0("error_006.ogg"))], peak=0.7)
    takes("CoinPayout", [trim(cc0("item_coins_0%d.ogg" % k)) for k in (1, 2, 3, 4)], peak=0.75)
    takes("GrainPayout", [trim(cc0(n)) for n in ("dropLeather.ogg", "handleSmallLeather.ogg", "handleSmallLeather2.ogg")], peak=0.75)
    takes("BuildPlace", [trim(cc0("wood_slam_0%d.ogg" % k)) for k in (1, 2, 3, 4)])
    # a building finished: two last mallet knocks, then a small bell (the castle's bell, struck light and higher)
    knock = [trim(cc0("impactPlank_medium_00%d.ogg" % k)) for k in (1, 3)]
    ding = trim(pitch(cc0("impactBell_heavy_003.ogg"), 1.5))
    done = mix(knock[0], knock[1], 0.85, 0.16)
    takes("BuildComplete", [mix(done, ding, 0.55, 0.36)], peak=0.75)
    takes("RecruitReady", [trim(cc0("door_open_01.ogg"))], peak=0.75)
    takes("BuildingHit", [trim(cc0("bfh1_wood_hit_0%d.ogg" % k)) for k in (1, 2, 3)] + [trim(cc0("bfh1_rock_hit_01.ogg"))])
    # a building coming down: timbers splitting and stone tumbling, in waves over a second and a half
    rock = [trim(cc0("bfh1_rock_falling_0%d.ogg" % k)) for k in (1, 2, 3, 4)]
    wood = [trim(cc0("bfh1_wood_breaking_0%d.ogg" % k)) for k in (1, 2, 3, 4)]
    collapses = []
    for k in range(4):
        c = mix(wood[k], rock[k], 0.9, 0.12)
        c = mix(c, rock[(k + 1) % 4], 0.8, 0.45)
        c = mix(c, wood[(k + 2) % 4], 0.6, 0.8)
        c = mix(c, rock[(k + 3) % 4], 0.55, 1.15)
        collapses.append(c)
    takes("BuildingCollapse", collapses, peak=0.9)
    takes("WarHorn", [trim(cc0("war_horn.ogg"))], peak=0.8)
    takes("Pickaxe", [trim(cc0("impactMining_00%d.ogg" % k)) for k in range(5)], peak=0.75)
    takes("Hoe", [trim(cc0("footstep_grass_00%d.ogg" % k)) for k in range(5)], peak=0.75)
    takes("Victory", [trim(cc0("fanfare.ogg"))], peak=0.85)
    takes("Defeat", [trim(cc0("jingles_STEEL14.ogg"))], peak=0.85)
    write("AmbientLoop", cc0("amb_morning.ogg"), peak=0.7)   # already a seamless loop


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


def main_music():
    """SourceArt/Audio/Music/*.mp3 (in name order) -> S_Music_1.wav, _2, ...: 48 kHz 16-bit stereo, loudness matched,
    a short fade at each end (the game cross-fades between songs itself). The wavs are generated (not committed)."""
    src = os.path.join(ROOT, "SourceArt", "Audio", "Music")
    songs = sorted(f for f in os.listdir(src) if f.lower().endswith((".mp3", ".wav", ".m4a", ".flac")))
    for k, name in enumerate(songs):
        tmp = os.path.join(tempfile.mkdtemp(), "x.wav")
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@%d" % SR, "-c", "2", os.path.join(src, name), tmp], check=True)
        a, _ = sf.read(tmp)
        a = a * (10 ** (-16.0 / 20.0) / max(np.sqrt(np.mean(a ** 2)), 1e-6))   # same loudness (about -16 dB RMS)
        a = np.clip(a, -0.98, 0.98)
        f = int(0.5 * SR)
        a[:f] *= np.linspace(0, 1, f)[:, None]
        a[-f:] *= np.linspace(1, 0, f)[:, None]
        out = os.path.join(OUT, "S_Music_%d.wav" % (k + 1))
        sf.write(out, a, SR, subtype="PCM_16")
        print("wrote S_Music_%d.wav  %.0f s  (%s)" % (k + 1, len(a) / SR, name))


if __name__ == "__main__":
    main()
    main_cc0()
    main_replace()
    main_music()
