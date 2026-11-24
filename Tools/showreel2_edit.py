#!/usr/bin/env python3
"""The second and third showreels' edits (the frames: Tools/showreel.py rec2, Saved/Showreel/<reel>/frames/<shot>).

    python Tools/showreel2_edit.py clips  battle|kingdom   -> <reel>/clips/<shot>.mp4   (each take whole, no sound)
    python Tools/showreel2_edit.py sheet  battle|kingdom   -> <reel>/contact_sheet.jpg (a frame from each cut, in order)
    python Tools/showreel2_edit.py edit   battle|kingdom   -> <reel>/SovereignRealms_<Name>.mp4 and its poster .jpg
    python Tools/showreel2_edit.py peek   battle|kingdom <shot> [n]   -> a strip of n frames of one take (to judge it)

Each reel: an EDL (shot, cut-in time in the edit, the take's first frame used, and optionally its speed: 0.5 plays
a take recorded at 60 steps a second at half speed), cut on Ruach's beat; a grade of its own; an end card where the
picture has gone to black before the logo comes in (nothing under it). Encoded with the song by Blender's sequencer
(Tools/showreel_edit.py's encode: H.264 / AAC, 1920 x 1080, 30 fps).
"""
import glob
import os
import shutil
import sys

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import showreel_edit as E   # noqa: E402  (encode, the song, Blender)

ROOT = E.ROOT
OUT = E.OUT
FPS = 30
BRAND = os.path.join(ROOT, "References", "Branding")

# Ruach's grids (fitted to the song's onsets: Saved/Showreel/work2/beats2.py): the battle section is on a 0.4210 s
# beat from 140.395 s (its bars: 147.131, 148.815, ... the section breaks off at 179.127); the intro's on 0.4314 s
# from 2.97 s (its swell at 27.17, the hit at 30.58).
REELS = {
    "battle": dict(
        dir="reel2_battle", title="SovereignRealms_Battle", song_in=148.815, length=32.5, beat=0.4210,
        fade_in=0.0, music_fade_in=0.05, music_fade_out=1.4,
        grade=dict(sat=1.14, contrast=1.10, lift=-0.015, warm=0.0, vignette=0.22),
        logo="sovereign_realms_wordmark.png", logo_w=1100, logo_in=30.3, dark_from=29.2, dark_to=30.2,
        poster=("b_charge_lens", 42),
        edl=[
            ('b_rush', 0.000, 0),
            ('b_landing', 3.368, 100),
            ('b_jonathan', 5.894, 0),
            ('b_clash_low', 9.262, 20),
            ('b_corners', 12.630, 40),
            ('b_tower_volley', 14.314, 99),
            ('b_charge_lens', 15.998, 20),
            ('b_jonathan2', 18.524, 0),
            ('b_wave', 21.892, 30),
            ('b_king_charge', 25.260, 5, 0.8),
        ],
    ),
    "kingdom": dict(
        dir="reel3_kingdom", title="SovereignRealms_Kingdom", song_in=2.97, length=31.0, beat=0.4314,
        fade_in=0.3, music_fade_in=0.4, music_fade_out=1.6,
        grade=dict(sat=1.06, contrast=1.05, lift=0.0, warm=0.03, vignette=0.28),
        logo="sovereign_realms_logo_full.png", logo_w=760, logo_in=27.6, dark_from=26.4, dark_to=27.5,
        poster=("k_flowers", 100),
        edl=[
            ('k_ship', 0.000, 60),
            ('k_vista', 3.451, 20),
            ('k_flowers', 6.902, 20),
            ('k_canopy', 10.354, 20),
            ('k_march', 13.805, 10),
            ('k_jonathan', 16.393, 20),
            ('k_town', 19.844, 40),
            ('k_castle', 22.433, 0),
        ],
    ),
}


def frames_dir(reel, shot):
    return os.path.join(OUT, REELS[reel]["dir"], "frames", shot)


def load(reel, shot, i):
    files = sorted(glob.glob(os.path.join(frames_dir(reel, shot), "f_*.png")))
    i = int(min(max(i, 0), len(files) - 1))
    return np.asarray(Image.open(files[i]).convert("RGB")), len(files)


def grade(a, g, vig):
    x = a.astype(np.float32) / 255.0
    lum = (x * np.array([0.2126, 0.7152, 0.0722], np.float32)).sum(-1, keepdims=True)
    x = lum + (x - lum) * g["sat"]
    x = (x - 0.5) * g["contrast"] + 0.5 + g["lift"]
    if g["warm"]:
        x = x * np.array([1 + g["warm"], 1 + g["warm"] * 0.3, 1 - g["warm"]], np.float32)
    return x * vig


def vignette(strength):
    h, w = 1080, 1920
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.hypot((xx - w / 2) / (w / 2), (yy - h / 2) / (h / 2)) / np.sqrt(2)
    return (1 - strength * np.clip((r - 0.45) / 0.55, 0, 1) ** 2)[..., None]


def smooth(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def logo_layer(name, w):
    lg = Image.open(os.path.join(BRAND, name)).convert("RGBA")
    lg = lg.resize((w, int(lg.height * w / lg.width)), Image.LANCZOS)
    layer = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
    layer.paste(lg, ((1920 - lg.width) // 2, (1080 - lg.height) // 2), lg)
    a = np.asarray(layer).astype(np.float32) / 255.0
    return a[..., :3], a[..., 3:4]


def cuts(reel):
    R = REELS[reel]
    n = int(round(R["length"] * FPS))
    edl = R["edl"]
    c = [int(round(e[1] * FPS)) for e in edl] + [n]
    return n, c


def source_index(e, k):
    """the take's frame for the k-th frame of this cut"""
    speed = e[3] if len(e) > 3 else 1.0
    return e[2] + k * speed


def frame_at(reel, e, k):
    s = source_index(e, k)
    a, n = load(reel, e[0], int(s))
    if abs(s - int(s)) > 1e-3 and int(s) + 1 < n:
        b, _ = load(reel, e[0], int(s) + 1)
        u = s - int(s)
        a = (a.astype(np.float32) * (1 - u) + b.astype(np.float32) * u).astype(np.uint8)
    return a


def edit(reel):
    R = REELS[reel]
    n, c = cuts(reel)
    work = os.path.join(OUT, R["dir"], "edit_frames")
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work)
    vig = vignette(R["grade"]["vignette"])
    lrgb, lal = logo_layer(R["logo"], R["logo_w"])
    rows = []
    for i, e in enumerate(R["edl"]):
        a, b = c[i], c[i + 1]
        for f in range(a, b):
            t = f / FPS
            v = 1.0
            if R["fade_in"] and t < R["fade_in"]:
                v *= smooth(t / R["fade_in"])
            if t > R["dark_from"]:
                v *= 1.0 - smooth((t - R["dark_from"]) / (R["dark_to"] - R["dark_from"]))
            if v > 0.002:
                x = grade(frame_at(reel, e, f - a), R["grade"], vig) * v
            else:
                x = np.zeros((1080, 1920, 3), np.float32)
            la = smooth((t - R["logo_in"]) / 0.6) * (1.0 - smooth((t - (R["length"] - 0.8)) / 0.8))
            if la > 0:
                al = lal * la
                x = x * (1 - al) + lrgb * al
            Image.fromarray((np.clip(x, 0, 1) * 255 + 0.5).astype(np.uint8)).save(os.path.join(work, "e_%04d.png" % f), compress_level=1)
        rows.append((e[0], a, b, source_index(e, 0), source_index(e, b - a - 1)))
    for r in rows:
        print("  %-22s edit %5.2f-%5.2f s, take frames %.0f-%.0f" % (r[0], r[1] / FPS, r[2] / FPS, r[3], r[4]))
    out = os.path.join(OUT, R["dir"], R["title"] + ".mp4")
    E.encode(work, out, [E.SONG, str(R["song_in"]), str(R["music_fade_in"]), str(R["music_fade_out"])])
    if R["poster"]:
        shot, k = R["poster"]
        p = grade(load(reel, shot, k)[0], R["grade"], vig)
        Image.fromarray((np.clip(p, 0, 1) * 255 + 0.5).astype(np.uint8)).save(os.path.join(OUT, R["dir"], R["title"] + "_poster.jpg"), quality=93)
    sheet(reel, from_edit=work)
    shutil.rmtree(work)


def sheet(reel, from_edit=None, cols=4):
    """a frame from the middle of each cut (from the composed edit if given), in order, 480 x 270 each"""
    R = REELS[reel]
    n, c = cuts(reel)
    tiles = []
    for i, e in enumerate(R["edl"]):
        a, b = c[i], c[i + 1]
        m = (a + b) // 2
        if from_edit:
            im = Image.open(os.path.join(from_edit, "e_%04d.png" % m)).convert("RGB")
        else:
            im = Image.fromarray(frame_at(reel, e, m - a))
        tiles.append(im.resize((480, 270), Image.LANCZOS))
    rows = (len(tiles) + cols - 1) // cols
    S = Image.new("RGB", (cols * 480, rows * 270), (0, 0, 0))
    for i, t in enumerate(tiles):
        S.paste(t, ((i % cols) * 480, (i // cols) * 270))
    p = os.path.join(OUT, R["dir"], "contact_sheet.jpg")
    S.save(p, quality=88)
    print(p)


def peek(reel, shot, n=8):
    files = sorted(glob.glob(os.path.join(frames_dir(reel, shot), "f_*.png")))
    idx = np.linspace(0, len(files) - 1, n).astype(int)
    cols = 4
    rows = (n + cols - 1) // cols
    S = Image.new("RGB", (cols * 480, rows * 270))
    for j, i in enumerate(idx):
        S.paste(Image.open(files[i]).convert("RGB").resize((480, 270), Image.LANCZOS), ((j % cols) * 480, (j // cols) * 270))
    p = os.path.join(OUT, "work2", "peek_%s.jpg" % shot)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    S.save(p, quality=85)
    print(p, "frames", list(idx))


def clips(reel):
    R = REELS[reel]
    d = os.path.join(OUT, R["dir"], "clips")
    os.makedirs(d, exist_ok=True)
    for f in sorted(glob.glob(os.path.join(OUT, R["dir"], "frames", "*"))):
        if os.path.isdir(f):
            E.encode(f, os.path.join(d, os.path.basename(f) + ".mp4"))


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "peek":
        peek(a[1], a[2], int(a[3]) if len(a) > 3 else 8)
    else:
        {"clips": clips, "edit": edit, "sheet": sheet}[a[0]](a[1])
