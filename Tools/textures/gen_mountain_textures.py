#!/usr/bin/env python3
"""Mountain ground textures, made from two CC0 photo textures (Poly Haven) crushed into the game's pixel style:

    Tools/.venv/bin/python Tools/textures/gen_mountain_textures.py
    SourceArt/Textures/Sources/PolyHaven/rock_face_03_diff_1k.jpg -> SourceArt/Textures/T_MountainRock.png  (128 px)
    SourceArt/Textures/Sources/PolyHaven/snow_02_diff_1k.jpg      -> SourceArt/Textures/T_Snow.png          (128 px)

Each source is laid 2 x 2 (so a 128 px tile, 512 cm at 4 cm per texel, carries about the photo's real size twice
over), box-filtered down to texels, its contrast stretched, then every texel is snapped to the nearest tone of a short
hand-picked ramp (the rock ramp of gen_world_textures.py, a cold snow ramp), so the result sits in the same palette
as the drawn textures and has no photographic gradients left. M_Terrain uses them on high ground (bare rock above
the tree line, snow above that). Sources and licences: SourceArt/Textures/Sources/PolyHaven/CREDITS.md.
"""
import os

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "SourceArt", "Textures", "Sources", "PolyHaven")
OUT = os.path.join(ROOT, "SourceArt", "Textures")


def ramp(*hexes):
    return np.array([[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in hexes], np.float32)


# rock: the boulder ramp of gen_world_textures.py (ROCK), so high ground and the field's boulders are one stone
ROCK = ramp("#35352c", "#4c4d40", "#666756", "#80806b", "#9a9981", "#b1ae95")
SNOW = ramp("#8fa0b4", "#aebccb", "#c9d3de", "#dde4ea", "#edf1f3")


def crush(src, pal, size=128, repeat=2, gamma=1.0, spread=1.0):
    im = Image.open(os.path.join(SRC, src)).convert("L")
    cell = size // repeat
    small = np.asarray(im.resize((cell, cell), Image.BOX), np.float32) / 255.0
    lo, hi = np.percentile(small, 2), np.percentile(small, 98)
    v = np.clip((small - lo) / max(hi - lo, 1e-6), 0.0, 1.0) ** gamma
    v = 0.5 + (v - 0.5) * spread
    v = np.tile(v, (repeat, repeat))
    idx = np.clip((v * len(pal)).astype(int), 0, len(pal) - 1)
    # no lone texels: a texel that differs from all four neighbours takes the commonest neighbour tone
    for _ in range(2):
        n = [np.roll(idx, s, a) for a in (0, 1) for s in (-1, 1)]
        lone = np.all([k != idx for k in n], axis=0)
        idx = np.where(lone, np.median(np.stack(n), axis=0).astype(int), idx)
    return Image.fromarray(pal[idx].astype(np.uint8))


def main():
    crush("rock_face_03_diff_1k.jpg", ROCK, gamma=0.9).save(os.path.join(OUT, "T_MountainRock.png"))
    crush("snow_02_diff_1k.jpg", SNOW, gamma=0.7, spread=0.9).save(os.path.join(OUT, "T_Snow.png"))
    print("wrote T_MountainRock.png, T_Snow.png")


if __name__ == "__main__":
    main()
