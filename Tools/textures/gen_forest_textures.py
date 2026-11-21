#!/usr/bin/env python3
"""Draws the woods' pixel-art textures into SourceArt/Textures (phase 2 of the natural-world pass).

    Tools/.venv/bin/python Tools/textures/gen_forest_textures.py

  T_Leaves, T_LeavesBirch, T_LeavesMaple   64 x 48, alpha: one leafy clump of a broadleaf crown, unwrapped like
                                           T_Needles (v runs from the clump's top to its hanging rim, ragged alpha):
                                           oak greens, birch gold-green, maple reds and ambers
  T_BarkBirch                              32 x 64: white birch bark with dark lenticels
  T_Undergrowth                            160 x 32, alpha: sprite strip for the forest floor's cards: bracken (32),
                                           a bramble sprig (32), toadstools (16), bluebells (16), a sapling (32),
                                           dead bracken (32)
Same rules as gen_world_textures.py: small hand-picked palettes, authored marks, 4 cm per texel.
"""
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_world_textures import Tile, rgb, OUT, PREVIEW, BARK        # noqa: E402

OAK = [rgb(c) for c in ("#1b2a16", "#27401d", "#365a24", "#4d782b", "#6f9635", "#9db54a")]
BIRCH = [rgb(c) for c in ("#2f3b18", "#47591f", "#657d27", "#8a9c2e", "#b0b53a", "#d2cb55")]
MAPLE = [rgb(c) for c in ("#3a140f", "#5e1f12", "#8a2f14", "#b4481a", "#d6741f", "#eba637")]

# a leaf cluster: digits index the six-tone palette (0 dark .. 5 lit), '.' leaves what is under it
LEAF_MARKS = [
    [".45.",
     "3454",
     "2343",
     ".22."],
    ["..54.",
     ".4543",
     "34432",
     "2332.",
     ".21.."],
    [".44..",
     "4553.",
     "34442",
     ".3322",
     "..21."],
    ["45.",
     "344",
     "233",
     ".2."],
    [".5.4.",
     "45344",
     "34233",
     "23.22"],
]


def leaves(seed, pal, gaps=0.07):
    """One clump of a crown. Lit clusters over a dark body, a little darker toward the top of the tile (where the
    next clump overhangs), the lower rim scalloped."""
    rng = np.random.default_rng(seed)
    W, H = 64, 48
    t = Tile(W, H, pal[1], alpha=True)
    for y in range(H):
        for x in range(W):
            r = rng.random()
            t.c[y, x] = pal[0] if r < 0.3 else (pal[1] if r < 0.75 else pal[2])
    rows = [(1, -2, 0.45), (5, -2, 0.35), (9, -1, 0.3), (13, -1, 0.25), (17, -1, 0.2), (21, 0, 0.18), (25, 0, 0.12), (29, 0, 0.1), (33, 0, 0.05), (37, 0, 0.0), (40, 0, 0.0)]
    for ry, shift, skip in rows:
        x = int(rng.integers(0, 4))
        while x < W + 2:
            mark = LEAF_MARKS[int(rng.integers(len(LEAF_MARKS)))]
            yy = ry + int(rng.integers(-1, 2))
            sh = shift - (1 if rng.random() < 0.3 else 0) + (1 if rng.random() < 0.12 else 0)
            if rng.random() >= skip:
                for j, row in enumerate(mark):
                    for i, ch in enumerate(row):
                        if ch != "." and 0 <= yy + j < H:
                            t.c[yy + j, (x + i) % W] = pal[int(np.clip(int(ch) + sh, 0, 5))]
                for i in range(1, len(mark[0]) - 1):          # the shadow a cluster throws on the one below
                    if yy + len(mark) < H and rng.random() < 0.8:
                        t.c[yy + len(mark), (x + i) % W] = pal[0]
            x += len(mark[0]) + int(rng.integers(0, 2))
    t.a[:] = 255
    for _ in range(int(W * H * gaps / 6)):                    # sky through the leaves: small holes, more toward the rim
        x, y = int(rng.integers(W)), int(H * (0.35 + 0.65 * rng.random() ** 0.7))
        for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1), (-1, 0))[: int(rng.integers(2, 6))]:
            if 0 <= y + dy < H:
                t.a[y + dy, (x + dx) % W] = 0
    x = 0
    while x < W:                                              # the hanging rim: round lobes
        w = int(rng.integers(5, 10)); drop = int(rng.integers(4, 10))
        for i in range(w):
            if x + i < W:
                f = (i - (w - 1) / 2.0) / (w / 2.0)
                keep = max(int(round(drop * (1.0 - f * f))), 1)
                t.a[H - 10 + keep:, x + i] = 0
        x += w
    return t


def birch_bark(seed):
    rng = np.random.default_rng(seed)
    W, H = 32, 64
    pal = [rgb(c) for c in ("#2b2622", "#8f8a7c", "#b9b4a4", "#d6d1c0", "#ebe6d6")]
    t = Tile(W, H, pal[3])
    for y in range(H):
        for x in range(W):
            r = rng.random()
            t.c[y, x] = pal[2] if r < 0.22 else (pal[3] if r < 0.8 else pal[4])
    for _ in range(26):                                       # lenticels: short dark dashes across the trunk
        x, y, L = int(rng.integers(W)), int(rng.integers(H)), int(rng.integers(3, 9))
        for d in range(L):
            t.put(x + d, y, pal[0])
            if rng.random() < 0.35:
                t.put(x + d, y + 1, pal[1])
    for _ in range(5):                                        # a scar where a bough fell
        x, y = int(rng.integers(W)), int(rng.integers(H))
        for dx, dy in ((0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1), (1, -1), (1, 2), (3, 1), (-1, 0)):
            t.put(x + dx, y + dy, pal[0])
        for dx in range(-2, 5):
            t.put(x + dx, y + 3, pal[1])
    return t


def undergrowth(seed):
    rng = np.random.default_rng(seed)
    W, H = 160, 32
    t = Tile(W, H, OAK[2], alpha=True)
    FERN = [rgb(c) for c in ("#2c4224", "#3b592a", "#4f7431", "#688c3a", "#86a548")]
    DEAD = [rgb(c) for c in ("#3d2c1a", "#5a4022", "#7a5a2c", "#9a7838", "#b9974a")]

    def put(x, y, col, lo, hi):
        if lo <= x < hi and 0 <= y < H:
            t.put(x, y, col, wrap_y=False)

    def bracken(x_lo, pal, n):
        root = x_lo + 16
        for ang in np.linspace(-80, 80, n):
            a = np.radians(ang + rng.uniform(-6, 6))
            L = int(rng.integers(15, 23))
            x, y = float(root + rng.integers(-1, 2)), float(H - 1)
            for i in range(L):
                f = i / L
                col = pal[2] if f < 0.3 else (pal[3] if f < 0.7 else pal[4])
                px, py = int(round(x)), int(round(y))
                put(px, py, col, x_lo, x_lo + 32)
                if i > 1:                                       # pinnae, shorter toward the tip
                    reach = 1 + int((1.0 - f) * 2.2)
                    for sgn in (-1, 1):
                        for k in range(1, reach + 1):
                            if (i + k) % 2:
                                continue
                            qx = px + (sgn * k if abs(ang) < 42 else 0)
                            qy = py + (0 if abs(ang) < 42 else sgn * k)
                            put(qx, qy, pal[3] if f > 0.4 else pal[1], x_lo, x_lo + 32)
                x += np.sin(a) * (0.62 + 0.5 * f)
                y -= np.cos(a) * (1.05 - 0.85 * f) + 0.03
        for k in range(6):
            put(root - 3 + k, H - 1, pal[0], x_lo, x_lo + 32)

    bracken(0, FERN, 9)
    # bramble sprig: arching canes with leaves in threes and a few dark berries
    x_lo = 32
    for k in range(4):
        x, y = float(x_lo + 8 + k * 5 + rng.integers(-1, 2)), float(H - 1)
        lean = rng.uniform(-0.75, 0.75)
        L = int(rng.integers(14, 24))
        for i in range(L):
            f = i / L
            put(int(round(x)), int(round(y)), rgb("#4a3324") if f < 0.6 else rgb("#5e4a2a"), x_lo, x_lo + 32)
            if i % 4 == 2:
                for dx, dy, c in ((-1, 0, 3), (1, 0, 3), (0, -1, 4), (-2, 0, 2), (2, 0, 2), (-1, -1, 4), (1, -1, 3)):
                    put(int(round(x)) + dx, int(round(y)) + dy, OAK[c], x_lo, x_lo + 32)
                if rng.random() < 0.4:
                    put(int(round(x)) + int(rng.integers(-2, 3)), int(round(y)) + 1, rgb("#3b1d3a"), x_lo, x_lo + 32)
            x += lean * (0.3 + 1.1 * f)
            y -= 1.0 - 0.75 * f * f
    # toadstools: red caps flecked white on pale stems, a brown pair beside them
    x_lo = 64
    for cx, hgt, wd, cap, fleck in ((68, 6, 2, rgb("#b5301f"), True), (73, 9, 3, rgb("#c93a22"), True), (77, 4, 2, rgb("#8a5a34"), False), (71, 3, 1, rgb("#9c6a3c"), False)):
        for i in range(hgt):
            put(cx, H - 1 - i, rgb("#d9cfb4"), x_lo, x_lo + 16)
        top = H - 1 - hgt
        for dy in range(2):
            w = wd - (1 if dy == 0 else 0)
            for dx in range(-w, w + 1):
                put(cx + dx, top + dy - 1, cap, x_lo, x_lo + 16)
        put(cx, top - 2, cap, x_lo, x_lo + 16)
        for dx in range(-wd + 1, wd):
            put(cx + dx, top + 1, rgb("#5a2418") if fleck else rgb("#4a3020"), x_lo, x_lo + 16)
        if fleck:
            put(cx - 1, top - 1, rgb("#f0ead8"), x_lo, x_lo + 16)
            put(cx + 1, top, rgb("#f0ead8"), x_lo, x_lo + 16)
    # bluebells: nodding stems over strap leaves
    x_lo = 80
    for k in range(6):
        cx = x_lo + 2 + int(rng.integers(0, 12))
        hgt = int(rng.integers(7, 14))
        lean = rng.uniform(-0.2, 0.2)
        x = float(cx)
        for i in range(hgt):
            put(int(round(x)), H - 1 - i, OAK[3] if i < hgt * 0.6 else OAK[4], x_lo, x_lo + 16)
            x += lean
        nod = 1 if rng.random() < 0.5 else -1
        for j in range(3):
            put(int(round(x)) + nod * (1 if j else 0), H - 1 - hgt + j * 2, rgb("#5466c4") if j % 2 == 0 else rgb("#7f8fe0"), x_lo, x_lo + 16)
        for i in range(int(rng.integers(3, 6))):
            put(cx + (1 if k % 2 else -1) * (1 + i // 2), H - 1 - i, OAK[2], x_lo, x_lo + 16)
    # sapling: a thin stem with a few leaf clusters
    x_lo = 96
    x = float(x_lo + 16)
    for i in range(27):
        put(int(round(x)), H - 1 - i, BARK[2] if i < 16 else BARK[3], x_lo, x_lo + 32)
        if i > 6 and i % 3 == 0:
            side = 1 if (i // 3) % 2 else -1
            for k in range(1, int(rng.integers(3, 7))):
                put(int(round(x)) + side * k, H - 1 - i - k // 2, BARK[2], x_lo, x_lo + 32)
            ex, ey = int(round(x)) + side * 5, H - 1 - i - 2
            mark = LEAF_MARKS[int(rng.integers(len(LEAF_MARKS)))]
            for j, row in enumerate(mark):
                for ii, ch in enumerate(row):
                    if ch != ".":
                        put(ex + ii - 2, ey + j - 2, OAK[int(ch)], x_lo, x_lo + 32)
        x += rng.uniform(-0.12, 0.12)
    for j, row in enumerate(LEAF_MARKS[1]):
        for ii, ch in enumerate(row):
            if ch != ".":
                put(int(round(x)) + ii - 2, H - 30 + j, OAK[int(ch)], x_lo, x_lo + 32)
    bracken(128, DEAD, 7)
    return t


def build():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(PREVIEW, exist_ok=True)
    tiles = {"T_Leaves": leaves(151, OAK), "T_LeavesBirch": leaves(152, BIRCH, gaps=0.16), "T_LeavesMaple": leaves(153, MAPLE, gaps=0.1),
             "T_BarkBirch": birch_bark(154), "T_Undergrowth": undergrowth(155)}
    for name, t in tiles.items():
        t.image().save(os.path.join(OUT, name + ".png"))
        im = t.image().convert("RGBA")
        bg = Image.new("RGBA", im.size, (70, 60, 90, 255))
        bg.alpha_composite(im)
        bg.resize((bg.width * 6, bg.height * 6), Image.NEAREST).convert("RGB").save(os.path.join(PREVIEW, name + ".png"))
    print("wrote %d textures to %s" % (len(tiles), OUT))


if __name__ == "__main__":
    build()
