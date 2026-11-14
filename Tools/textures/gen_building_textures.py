#!/usr/bin/env python3
"""Draws the building texture set (castle, farm, mine) into SourceArt/Textures as T_Bld_*.png.

Run with the tools venv:   Tools/.venv/bin/python Tools/textures/gen_building_textures.py

Same rules as gen_world_textures.py, whose canvas, helpers and palettes it reuses: every texture is drawn
deliberately from a small fixed palette, noise only chooses between authored options, and the density is
4 cm per texel. `*_N.png` are tangent-space normal maps from the height the drawing code lays down.

Alpha is a MASK, not opacity, on the opaque textures (M_Building): 255 = plain, 153 = the texel takes the
team colour (frieze) or glints (gold ore). On the card textures (M_BuildingCard: wheat, banner, awning,
leaves, flame) alpha 0 is a hole, 153 is opaque and team-coloured, 255 is opaque and plain.
A contact sheet per texture is written to Saved/TexturePreview/.
"""
import math
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_world_textures import (BARK, EARTH, GRASS_MOSS, SAND, WOOD, Tile, mix, partition, rgb,  # noqa: E402
                                stone_block, value_noise)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "SourceArt", "Textures")
PREVIEW = os.path.join(ROOT, "Saved", "TexturePreview")
TEAM = 153                    # alpha of a team-coloured / glinting texel


def pal(*hexes):
    return [rgb(h) for h in hexes]


# ---------------------------------------------------------------------------------------- palettes
# All sit inside the world's sandstone / earth / wood ranges (gen_world_textures.py), a step warmer or paler.
ROSE = pal("#5e4532", "#86654a", "#a98560", "#c2a078", "#d6b98f", "#e4cda6")       # rosier sandstone, a few blocks
PALE = pal("#6a5a42", "#93825f", "#b5a57c", "#cfc096", "#e0d4ae", "#ece3c4")       # sun-bleached sandstone, dressed trim
MUD = pal("#3f3122", "#5c4730", "#786042", "#927853", "#a98f66", "#bfa67c")        # mudbrick
PLASTER = pal("#7d6c50", "#a39171", "#c0b08c", "#d3c5a2", "#e1d6b8", "#ece4cc")    # mud-lime plaster
CLAY = pal("#6c5a40", "#8a7654", "#a38f68", "#b8a57d", "#c9b891", "#d8c9a4")       # packed-clay roof
THATCH = pal("#3e3219", "#5c4b24", "#7d6830", "#9c853f", "#b9a253", "#d2bd6e")     # reed thatch, hay
WHEAT = pal("#5f4c1c", "#8a6f24", "#b59230", "#d6b444", "#ecd067", "#f8e596")      # ripe barley
SOIL = pal("#231a13", "#33271b", "#463625", "#5a4631", "#705a40")                  # tilled earth
BRONZE = pal("#33230f", "#5c3e1a", "#876026", "#b08336", "#d3a84e", "#efd27e")
GOLD = pal("#7a5612", "#b5841c", "#e2b634", "#fbe06c", "#fff6b8")
ORE = pal("#1f1c19", "#2f2b26", "#433d35", "#585147", "#6f675b")                   # dark host rock
TERRA = pal("#4f2c1c", "#74432a", "#96593a", "#b3744c", "#cb9166", "#dfb088")      # terracotta
OLIVE = pal("#232c1c", "#354229", "#4b5b38", "#64774a", "#82935f", "#a7b384")      # olive leaves, silvery tips
GREY = pal("#6b6b6b", "#838383", "#9c9c9c", "#b4b4b4", "#cacaca")                  # team cloth / glaze: tinted by TeamColor
CREAM = pal("#8f7f5e", "#b7a680", "#d6c8a2", "#e9dfc0")
FLAME = pal("#8a2a0c", "#d2561a", "#f39a2c", "#ffd45a", "#fff4b8")
DARK = pal("#0f0c09", "#17120d", "#211a12")


def put_a(t, x, y, col, a=255, wrap_y=False):
    """Tile.put with an explicit alpha."""
    x %= t.w
    if wrap_y:
        y %= t.h
    elif y < 0 or y >= t.h:
        return
    t.c[y, x] = col
    t.a[y, x] = a


def stain(t, rng, n, tone, lo=5, hi=16, amt=0.4):
    """Rain stains running down the face."""
    for _ in range(n):
        x, y = int(rng.integers(t.w)), int(rng.integers(t.h))
        for d in range(int(rng.integers(lo, hi))):
            c = t.get(x, y + d)
            t.put(x, y + d, mix(c, tone, amt * (1.0 - d / hi * 0.6)), t.hgt[(y + d) % t.h, x % t.w])
            if rng.random() < 0.25:
                x += int(rng.choice([-1, 1]))


# ---------------------------------------------------------------------------------------- masonry
def ashlar(seed, courses, wmin, wmax, sets, probs, chip=0.4, missing=1, stains=12, holes=0):
    """Coursed sandstone. `courses` are the course heights (texels), summing to the tile height; block widths vary
    within a course and no joint lines up with the one below. `missing` blocks leave shadowed sockets (0 in the
    shipped tiles: a socket in a tiling texture repeats every 5 m, so the buildings cut theirs as real recesses)."""
    rng = np.random.default_rng(seed)
    W, H = 128, int(sum(courses))
    gap = SAND[0]
    t = Tile(W, H, gap)
    y = 0
    last_off = None
    gone = set(int(v) for v in rng.choice(len(courses), size=missing, replace=False)) if missing else set()
    for r, ch in enumerate(courses):
        off = int(rng.integers(0, 16))
        while last_off is not None and not (4 <= abs(off - last_off) <= 12):
            off = int(rng.integers(0, 16))
        last_off = off
        x = off
        widths = partition(rng, W, wmin, wmax)
        hole_at = int(rng.integers(len(widths))) if r in gone else -1
        for k, bw in enumerate(widths):
            tones = sets[int(rng.choice(len(sets), p=probs))]
            if k == hole_at and bw >= 10:
                # the socket of a lost block: dark, with rubble and a lit lower lip
                for j in range(ch - 1):
                    for i in range(bw - 1):
                        c = DARK[2] if j < ch - 3 else mix(DARK[2], SAND[1], 0.5)
                        t.put(x + i, y + j, c, 0.15)
                for i in range(1, bw - 2):
                    if rng.random() < 0.6:
                        t.put(x + i, y + ch - 2, SAND[2] if rng.random() < 0.5 else SAND[1], 0.4)
                for j in range(ch - 1):
                    t.put(x, y + j, DARK[0], 0.1)
                for i in range(bw - 1):
                    t.put(x + i, y, DARK[0], 0.1)
            else:
                stone_block(t, rng, x, y, bw, ch, tones, gap, base_h=1.0 + rng.uniform(-0.08, 0.1), chip=chip, tilt=False)
            x += bw
        y += ch
    stain(t, rng, stains, SAND[1])
    for _ in range(holes):                                 # putlog holes / weep holes: small dark squares
        x, y = int(rng.integers(W)), int(rng.integers(H))
        t.rect(x, y, 2, 2, DARK[1], 0.2)
        t.put(x, y + 2, SAND[5]); t.put(x + 1, y + 2, SAND[5])
    return t


def trim(seed):
    """Dressed coping / string course, 64 x 16: long pale slabs, a lit arris, a cut groove, a shadowed drip edge.
    v = 0 is the top edge of the band (the kit aligns it)."""
    rng = np.random.default_rng(seed)
    W, H = 64, 16
    t = Tile(W, H, PALE[3])
    for x in range(W):
        for y in range(H):
            if y == 0:
                c, h = PALE[5], 0.8
            elif y == 1:
                c, h = PALE[4], 1.0
            elif y in (9, 10):
                c, h = (PALE[1], 0.35) if y == 9 else (PALE[4], 0.9)        # groove and its lit lower lip
            elif y >= H - 2:
                c, h = (PALE[2], 0.8) if y == H - 2 else (PALE[0], 0.2)
            else:
                c, h = PALE[3], 1.0
            t.put(x, y, c, h)
    for x0 in (int(rng.integers(8, 24)), int(rng.integers(40, 56))):      # slab ends
        for y in range(H - 1):
            t.put(x0, y, PALE[1], 0.3)
            t.put(x0 + 1, y, PALE[4] if y not in (9,) else PALE[1], 0.9)
    for _ in range(26):                                                   # tooling dabs
        x, y = int(rng.integers(W)), int(rng.choice([3, 4, 5, 6, 7, 12]))
        for d in range(int(rng.integers(2, 6))):
            t.put(x + d, y, PALE[2] if rng.random() < 0.6 else PALE[4], 1.0)
    for _ in range(3):                                                    # chips out of the top arris
        x = int(rng.integers(W))
        t.put(x, 0, PALE[2], 0.4); t.put(x + 1, 0, PALE[2], 0.4); t.put(x, 1, PALE[2], 0.6)
    return t


def mudbrick(seed):
    """Sun-dried brick, 8 x 4 texel bricks in running bond; straw flecks, a few eroded bricks."""
    rng = np.random.default_rng(seed)
    W = H = 128
    gap = MUD[0]
    t = Tile(W, H, gap)
    damp = value_noise(rng, W, H, 32)
    for r in range(H // 4):
        y = r * 4
        x = (0 if r % 2 == 0 else 4) + int(rng.integers(0, 2))
        for bw in partition(rng, W, 7, 10):
            k = 2 + (1 if rng.random() < 0.3 else 0) - (1 if damp[y, x % W] < 0.35 else 0)
            k = int(np.clip(k + int(rng.choice([-1, 0, 0, 0, 1])), 1, 4))
            eroded = rng.random() < 0.07
            for j in range(3):
                for i in range(bw - 1):
                    c = MUD[k]
                    if j == 0:
                        c = MUD[min(k + 1, 5)]
                    if j == 2 or i == bw - 2:
                        c = MUD[max(k - 1, 0)]
                    if eroded and (j == 2 or (i in (0, bw - 2))):
                        c = gap
                    t.put(x + i, y + j, c, 0.0 if c is gap else 1.0 - (0.3 if j != 1 else 0.0))
            if rng.random() < 0.35:                         # chopped straw in the mud
                t.put(x + int(rng.integers(1, max(bw - 2, 2))), y + 1, PLASTER[2], 1.0)
            x += bw
    stain(t, rng, 10, MUD[1], amt=0.35)
    return t


def plaster(seed, brick):
    """Mud-lime render over brick: trowel strokes, hairline cracks, and patches fallen away to the brick."""
    rng = np.random.default_rng(seed)
    W = H = 128
    t = Tile(W, H, PLASTER[3])
    t.hgt[:] = 1.0
    n = value_noise(rng, W, H, 32)
    t.c[n < 0.38] = PLASTER[2]
    t.c[n > 0.74] = PLASTER[4]
    for gy in range(H // 4):                                 # trowel strokes
        for gx in range(W // 10):
            if rng.random() < 0.45:
                continue
            x = gx * 10 + int(rng.integers(0, 10)) + (5 if gy % 2 else 0)
            y = gy * 4 + int(rng.integers(0, 4))
            L = int(rng.integers(3, 9))
            for d in range(L):
                t.put(x + d, y, PLASTER[4] if rng.random() < 0.8 else PLASTER[5], 1.05)
                t.put(x + d, y + 1, PLASTER[2], 0.95)
    for _ in range(7):                                       # cracks
        x, y = int(rng.integers(W)), int(rng.integers(H))
        for d in range(int(rng.integers(10, 34))):
            t.put(x, y, PLASTER[0], 0.4)
            t.put(x + 1, y, PLASTER[5], 1.0)
            y += 1
            if rng.random() < 0.45:
                x += int(rng.choice([-1, 1]))
    blob = value_noise(rng, W, H, 32) * 0.7 + value_noise(rng, W, H, 8) * 0.3
    hole = blob > 0.81                                       # where the render has fallen off
    for y in range(H):
        for x in range(W):
            if hole[y, x]:
                t.put(x, y, brick.get(x, y), 0.45 * brick.hgt[y % brick.h, x % brick.w])
    for y in range(H):
        for x in range(W):
            if hole[y, x]:
                continue
            if hole[(y - 1) % H, x]:                         # lit lip under a patch
                t.put(x, y, PLASTER[5], 1.0)
            elif hole[(y + 1) % H, x]:                       # the render's thickness, in shadow above the brick
                t.put(x, y, PLASTER[1], 0.8)
            elif hole[y, (x + 1) % W] or hole[y, (x - 1) % W]:
                t.put(x, y, PLASTER[2], 0.9)
    stain(t, rng, 14, PLASTER[1], lo=8, hi=26, amt=0.45)
    return t


def roof_clay(seed):
    """Flat roof of rolled clay: pale, crazed with fine cracks, a few pebbles and swept streaks."""
    rng = np.random.default_rng(seed)
    W = H = 128
    t = Tile(W, H, CLAY[3])
    t.hgt[:] = 1.0
    n = value_noise(rng, W, H, 32)
    t.c[n < 0.4] = CLAY[2]
    t.c[n > 0.72] = CLAY[4]
    pts = rng.random((22, 2)) * [W, H]
    ys, xs = np.mgrid[0:H, 0:W]
    best = np.full((H, W), 1e9); second = np.full((H, W), 1e9)
    for px_, py_ in pts:
        dx = np.abs(xs - px_); dx = np.minimum(dx, W - dx)
        dy = np.abs(ys - py_); dy = np.minimum(dy, H - dy)
        d = np.hypot(dx, dy)
        closer = d < best
        second = np.where(closer, best, np.minimum(second, d))
        best = np.where(closer, d, best)
    edge = (second - best) < 0.9
    for y in range(H):
        for x in range(W):
            if edge[y, x] and rng.random() < 0.8:
                t.put(x, y, CLAY[1] if rng.random() < 0.7 else CLAY[0], 0.4)
            elif edge[(y - 1) % H, x] and rng.random() < 0.5:
                t.put(x, y, CLAY[5], 1.0)
    for gy in range(H // 5):                                 # swept streaks
        for gx in range(W // 12):
            if rng.random() < 0.5:
                continue
            x = gx * 12 + int(rng.integers(0, 12)); y = gy * 5 + int(rng.integers(0, 5))
            for d in range(int(rng.integers(3, 8))):
                t.put(x + d, y, CLAY[4] if rng.random() < 0.7 else CLAY[2], 1.0)
    for _ in range(18):                                      # pebbles
        x, y = int(rng.integers(W)), int(rng.integers(H))
        t.put(x, y, CLAY[5], 1.2); t.put(x + 1, y, CLAY[4], 1.2); t.put(x, y + 1, CLAY[1], 0.8); t.put(x + 1, y + 1, CLAY[0], 0.7)
    return t


# ---------------------------------------------------------------------------------------- timber
def beam(seed):
    """One squared timber, grain along u, 64 x 16 (v wraps every 64 cm): no board edges, adze marks, checks."""
    rng = np.random.default_rng(seed)
    W, H = 64, 16
    t = Tile(W, H, WOOD[2])
    for y in range(H):
        tone = 2 if y % 5 else 1
        for x in range(W):
            t.put(x, y, WOOD[tone])
    for _ in range(26):                                      # long grain streaks
        x, y = int(rng.integers(W)), int(rng.integers(H))
        col = WOOD[int(rng.choice([1, 1, 3, 3, 4], p=[0.3, 0.2, 0.3, 0.1, 0.1]))]
        for d in range(int(rng.integers(6, 26))):
            t.put(x + d, y, col)
            if rng.random() < 0.08:
                y += int(rng.choice([-1, 1]))
    for _ in range(3):                                       # knots
        x, y = int(rng.integers(W)), int(rng.integers(2, H - 3))
        for dx, dy, c in ((0, 0, 0), (1, 0, 0), (-1, 0, 1), (2, 0, 1), (0, -1, 1), (1, -1, 1), (0, 1, 3), (1, 1, 3)):
            t.put(x + dx, y + dy, WOOD[c])
    for _ in range(5):                                       # drying checks
        x, y = int(rng.integers(W)), int(rng.integers(H))
        for d in range(int(rng.integers(4, 12))):
            t.put(x + d, y, WOOD[0])
            t.put(x + d, y + 1, WOOD[3])
    return t


def planks(seed):
    """Boards along u, 8 texels wide, 64 x 64: nail heads at the board ends, gaps, one split board."""
    rng = np.random.default_rng(seed)
    W = H = 64
    t = Tile(W, H, WOOD[2])
    for b in range(H // 8):
        py = b * 8
        tone = int(rng.choice([1, 2, 2, 3]))
        for y in range(py, py + 8):
            for x in range(W):
                c = WOOD[tone]
                if y == py:
                    c = WOOD[min(tone + 1, 4)]
                if y == py + 7:
                    c = WOOD[0]
                t.put(x, y, c)
        for _ in range(6):
            x, y = int(rng.integers(W)), py + int(rng.integers(1, 7))
            for d in range(int(rng.integers(5, 18))):
                t.put(x + d, y, WOOD[max(tone - 1, 0)] if rng.random() < 0.6 else WOOD[min(tone + 1, 4)])
        x = int(rng.integers(W))                             # board end with two nails
        for y in range(py, py + 8):
            t.put(x, y, WOOD[0])
        for dy in (2, 5):
            t.put(x + 2, py + dy, BRONZE[1]); t.put(x - 2, py + dy, BRONZE[1])
            t.put(x + 2, py + dy - 1, BRONZE[4])
    return t


def door(seed):
    """Double-leaf gate, 64 x 64 (256 x 256 cm): upright boards, three bronze straps with studs, ring pulls."""
    rng = np.random.default_rng(seed)
    W = H = 64
    t = Tile(W, H, WOOD[1])
    for x in range(W):
        board = x // 8
        tone = [1, 2, 1, 2, 2, 1, 2, 1][board]
        for y in range(H):
            c = WOOD[tone]
            if x % 8 == 0:
                c = WOOD[min(tone + 1, 4)]
            if x % 8 == 7:
                c = WOOD[0]
            t.put(x, y, c)
    for _ in range(60):                                      # upright grain
        x, y = int(rng.integers(W)), int(rng.integers(H))
        if x % 8 in (0, 7):
            continue
        tone = [1, 2, 1, 2, 2, 1, 2, 1][x // 8]
        for d in range(int(rng.integers(4, 16))):
            t.put(x, y + d, WOOD[max(tone - 1, 0)] if rng.random() < 0.65 else WOOD[tone + 1])
    for y in range(H):                                       # the meeting stiles and the dark seam between the leaves
        t.put(31, y, DARK[1]); t.put(32, y, DARK[2])
        t.put(30, y, WOOD[3]); t.put(33, y, WOOD[1])
    for y0 in (5, 28, 51):                                   # bronze straps
        for x in range(W):
            if x in (31, 32):
                continue
            for j, c in enumerate((BRONZE[4], BRONZE[3], BRONZE[3], BRONZE[2], BRONZE[1])):
                t.put(x, y0 + j, c)
            t.put(x, y0 + 5, DARK[2])                        # the strap's shadow on the boards
        for x in range(3, W, 8):                             # studs
            if x in (27, 35):
                pass
            t.put(x, y0 + 1, BRONZE[5]); t.put(x + 1, y0 + 1, BRONZE[4])
            t.put(x, y0 + 2, BRONZE[4]); t.put(x + 1, y0 + 2, BRONZE[1])
    for cx in (25, 36):                                      # ring pulls
        ring = ["..33..", ".4..2.", "4....1", "3....1", ".2..1.", "..11.."]
        for j, row in enumerate(ring):
            for i, ch in enumerate(row):
                if ch != ".":
                    t.put(cx + i - 2, 36 + j, BRONZE[int(ch) + 1 if int(ch) < 5 else 5])
        t.put(cx, 35, BRONZE[5]); t.put(cx + 1, 35, BRONZE[3])
    for y in range(H - 4, H):                                # scuffed, damp foot
        for x in range(W):
            if rng.random() < 0.55 + 0.1 * (y - (H - 4)):
                t.put(x, y, mix(t.get(x, y), DARK[2], 0.45))
    return t


def shutter(seed):
    """Small plank shutter / lattice for windows, 16 x 16: slats with a cross batten."""
    rng = np.random.default_rng(seed)
    t = Tile(16, 16, WOOD[1])
    for y in range(16):
        for x in range(16):
            c = WOOD[2] if y % 4 in (0, 1) else (WOOD[1] if y % 4 == 2 else DARK[2])
            if y % 4 == 0:
                c = WOOD[3]
            t.put(x, y, c)
    for x in (3, 12):
        for y in range(16):
            t.put(x, y, WOOD[3]); t.put(x + 1, y, WOOD[0])
    for x, y in ((3, 2), (12, 2), (3, 13), (12, 13)):
        t.put(x, y, BRONZE[4])
    return t


# ---------------------------------------------------------------------------------------- roofs, fields
def thatch(seed, tones=THATCH):
    """Reed thatch laid in overlapping tiers, 64 x 64: v runs down the slope. Each tier is combed strands with a
    ragged, shadowed lower edge."""
    rng = np.random.default_rng(seed)
    W = H = 64
    t = Tile(W, H, tones[2])
    tier = 16
    for ty in range(0, H, tier):
        ragged = [int(rng.choice([0, 0, 1, 1, 2, 3])) for _ in range(W)]
        for x in range(W):
            k = int(rng.choice([2, 3, 3, 4]))
            for j in range(tier):
                if rng.random() < 0.12:
                    k = int(np.clip(k + int(rng.choice([-1, 1])), 1, 5))
                c = tones[k]
                h = 0.35 + 0.65 * j / tier                   # each tier stands proud toward its lower edge
                if j < 2:
                    c, h = tones[max(k - 2, 0)], 0.2         # tucked under the tier above
                elif j == 2:
                    c = tones[max(k - 1, 1)]
                if j >= tier - ragged[x]:
                    c, h = tones[0], 0.1                     # gap between reed ends: the shadow under the tier
                elif j == tier - ragged[x] - 1:
                    c = tones[min(k + 1, 5)]                 # cut reed ends catch the light
                t.put(x, ty + j, c, h)
        for _ in range(5):                                   # binding stitches
            x = int(rng.integers(W)); y = ty + int(rng.integers(5, 10))
            for d in range(int(rng.integers(3, 7))):
                t.put(x + d, y, tones[1], 0.7)
    return t


def soil(seed):
    """Tilled furrows along u, 64 x 64: a ridge every 8 texels (32 cm), lit crest, dark trough, clods."""
    rng = np.random.default_rng(seed)
    W = H = 64
    t = Tile(W, H, SOIL[2])
    prof = [(4, 1.0), (3, 0.9), (2, 0.7), (1, 0.45), (0, 0.2), (0, 0.2), (1, 0.45), (2, 0.7)]
    for y in range(H):
        k, h = prof[y % 8]
        for x in range(W):
            kk = int(np.clip(k + int(rng.choice([-1, 0, 0, 0, 1])), 0, 4))
            t.put(x, y, SOIL[kk], h)
    for _ in range(40):                                      # clods
        x, y = int(rng.integers(W)), int(rng.integers(H))
        t.put(x, y, SOIL[4], 1.0); t.put(x + 1, y, SOIL[3], 1.0); t.put(x, y + 1, SOIL[0], 0.3); t.put(x + 1, y + 1, SOIL[0], 0.3)
    for _ in range(14):                                      # stubble / straw
        x, y = int(rng.integers(W)), int(rng.integers(H))
        t.put(x, y, WHEAT[2], 0.9)
    return t


def wheat(seed):
    """One row of ripe barley as a card strip, 64 x 32 RGBA, tiles along u. Stalks root on the bottom row."""
    rng = np.random.default_rng(seed)
    W, H = 64, 32
    t = Tile(W, H, WHEAT[2], alpha=True)
    for x in range(W):                                        # the dense foot of the row
        for y in range(H - 6, H):
            if rng.random() < 0.55 + 0.09 * (y - (H - 6)):
                put_a(t, x, y, WHEAT[0] if y > H - 3 else WHEAT[1])
    x = 0
    while x < W:
        hgt = int(rng.integers(14, 22))
        lean = float(rng.uniform(-0.12, 0.12))
        fx = float(x)
        for i in range(hgt):
            f = i / hgt
            c = WHEAT[1] if f < 0.35 else (WHEAT[2] if f < 0.7 else WHEAT[3])
            put_a(t, int(round(fx)), H - 1 - i, c)
            fx += lean
        ex = int(round(fx)); ey = H - 1 - hgt
        ear = ["43", "53", "42", "53", "42", "32"]            # the ear: two columns of grains
        for j, row in enumerate(ear):
            for i, ch in enumerate(row):
                put_a(t, ex + i, ey - len(ear) + 1 + j, WHEAT[int(ch)])
        put_a(t, ex, ey - len(ear), WHEAT[5]); put_a(t, ex + 1, ey - len(ear) - 1, WHEAT[4])     # awns
        if rng.random() < 0.5:
            put_a(t, ex - 1, ey - len(ear) - 1, WHEAT[4])
        x += int(rng.integers(2, 4))
    return t


# ---------------------------------------------------------------------------------------- cloth, glaze, metal
def banner(seed):
    """Hanging banner, 16 x 64 RGBA: the cloth is 16 x 48 (64 x 192 cm), swallow-tailed. Field in team colour
    (grey, alpha TEAM), woven gold border and a sun-over-ramparts device (alpha 255)."""
    W, H = 16, 64
    t = Tile(W, H, GREY[2], alpha=True)
    gold = [BRONZE[2], BRONZE[4], BRONZE[5]]
    for y in range(48):
        notch = max(0, y - 39)
        for x in range(W):
            if abs(x - 7.5) < notch * 0.85:
                continue
            c, a = GREY[2], TEAM
            if x in (3, 12):
                c = GREY[1]                                   # folds
            if x in (4, 11) and y % 7 < 5:
                c = GREY[0]
            if x in (6, 7, 8):
                c = GREY[3]
            if y > 30 and x in (5, 10):
                c = GREY[1]
            if x in (0, W - 1) or y == 0:
                c, a = gold[1], 255
            if x in (1, W - 2) or y == 1:
                c, a = gold[0], 255
            if y == 0 and x % 2:
                c, a = gold[2], 255
            put_a(t, x, y, c, a)
    device = ["...1..1..1...",
              "....1.1.1....",
              ".....222.....",
              ".11.22222.11.",
              ".....222.....",
              "....1.1.1....",
              "...1..1..1...",
              ".............",
              ".22..22..22..",
              ".2222222222..",
              ".2222222222..",
              ".............",
              "..11111111...",]
    for j, row in enumerate(device):
        for i, ch in enumerate(row):
            if ch != ".":
                put_a(t, 2 + i, 9 + j, gold[int(ch)], 255)
    return t


def awning(seed):
    """Striped awning cloth, 32 x 32 RGBA, tiles: broad team stripes and cream, weave shading."""
    rng = np.random.default_rng(seed)
    W = H = 32
    t = Tile(W, H, CREAM[2], alpha=True)
    for y in range(H):
        for x in range(W):
            band = (x // 8) % 2
            if band == 0:
                c, a = GREY[2] if y % 4 else GREY[1], TEAM
                if x % 8 == 0:
                    c = GREY[3]
            else:
                c, a = CREAM[2] if y % 4 else CREAM[1], 255
                if x % 8 == 0:
                    c = CREAM[3]
                if x % 8 == 7:
                    c = CREAM[1]
            put_a(t, x, y, c, a)
    for _ in range(10):                                       # faded, patched spots
        x, y = int(rng.integers(W)), int(rng.integers(H))
        t.c[y, x] = mix(t.c[y, x], CREAM[0], 0.4)
    return t


def frieze(seed):
    """Glazed-brick band for the wall heads, 64 x 16 RGBA mask: team-coloured glaze, gold rules, a stepped
    rampart motif and discs in cream / gold every 16 texels. v = 0 is the band's top edge."""
    W, H = 64, 16
    t = Tile(W, H, GREY[2], alpha=True)
    for y in range(H):
        for x in range(W):
            c = GREY[2]
            if (x + (4 if (y // 4) % 2 else 0)) % 8 == 0 or y % 4 == 3:
                c = GREY[0]                                   # brick joints in the glaze
            elif y % 4 == 0:
                c = GREY[3]
            put_a(t, x, y, c, TEAM)
    for x in range(W):
        for y, c in ((0, PALE[4]), (1, BRONZE[4]), (2, BRONZE[2]), (13, BRONZE[4]), (14, BRONZE[2]), (15, PALE[1])):
            put_a(t, x, y, c, 255)
    motif = ["....33....",
             "...3443...",
             "..334433..",
             ".33444433.",
             ".33333333.",
             "3344444433",
             "3333333333"]
    for cx in (3, 35):
        for j, row in enumerate(motif):
            for i, ch in enumerate(row):
                if ch != ".":
                    put_a(t, cx + i, 4 + j, CREAM[3] if ch == "4" else CREAM[1], 255)
    disc = [".22.", "2332", "2332", ".22."]
    for cx in (22, 54):
        for j, row in enumerate(disc):
            for i, ch in enumerate(row):
                if ch != ".":
                    put_a(t, cx + i, 6 + j, BRONZE[5] if ch == "3" else BRONZE[3], 255)
    return t


def bronze(seed):
    """Hammered bronze sheet, 32 x 32: planished dimples, rivets on a 16 texel grid, a little verdigris."""
    rng = np.random.default_rng(seed)
    W = H = 32
    t = Tile(W, H, BRONZE[3])
    n = value_noise(rng, W, H, 8)
    t.c[n < 0.4] = BRONZE[2]
    t.c[n > 0.75] = BRONZE[4]
    for _ in range(40):
        x, y = int(rng.integers(W)), int(rng.integers(H))
        t.put(x, y, BRONZE[5] if rng.random() < 0.4 else BRONZE[4]); t.put(x + 1, y + 1, BRONZE[1])
    for gx in (3, 19):
        for gy in (3, 19):
            t.put(gx, gy, BRONZE[5]); t.put(gx + 1, gy, BRONZE[4]); t.put(gx, gy + 1, BRONZE[3]); t.put(gx + 1, gy + 1, BRONZE[0])
    for _ in range(8):
        t.put(int(rng.integers(W)), int(rng.integers(H)), rgb("#5f7f66"))
    return t


def ore(seed):
    """Broken gold ore, 64 x 64 RGBA mask: dark angular rock, quartz seams, gold veins and nuggets (alpha TEAM =
    glint, picked up by the material's Glow)."""
    rng = np.random.default_rng(seed)
    W = H = 64
    pts = rng.random((22, 2)) * [W, H]
    tone = rng.choice([1, 2, 2, 3, 3, 4], size=len(pts))
    ys, xs = np.mgrid[0:H, 0:W]
    best = np.full((H, W), 1e9); second = np.full((H, W), 1e9); idx = np.zeros((H, W), int)
    for i, (px_, py_) in enumerate(pts):
        dx = np.abs(xs - px_); dx = np.minimum(dx, W - dx)
        dy = np.abs(ys - py_); dy = np.minimum(dy, H - dy)
        d = dx * 0.9 + dy * 1.1 + np.maximum(dx, dy) * 0.4
        closer = d < best
        second = np.where(closer, best, np.minimum(second, d))
        idx = np.where(closer, i, idx)
        best = np.where(closer, d, best)
    t = Tile(W, H, ORE[2], alpha=True)
    t.a[:] = 255
    edge = (second - best) < 1.2
    for y in range(H):
        for x in range(W):
            k = int(tone[idx[y, x]])
            c = ORE[k]
            if edge[y, x]:
                c = ORE[0]
            elif edge[(y - 1) % H, x] or edge[y, (x - 1) % W]:
                c = ORE[min(k + 1, 4)]
            t.c[y, x] = c
    for _ in range(9):                                        # gold veins wandering through the rock
        x, y = int(rng.integers(W)), int(rng.integers(H))
        for d in range(int(rng.integers(6, 20))):
            c = GOLD[int(rng.choice([1, 2, 2, 3]))]
            put_a(t, x, y, c, TEAM if c is not GOLD[1] else 255, wrap_y=True)
            if rng.random() < 0.3:
                put_a(t, x, y + 1, GOLD[0], 255, wrap_y=True)
            x += 1
            if rng.random() < 0.5:
                y += int(rng.choice([-1, 1]))
    for _ in range(16):                                       # nuggets
        x, y = int(rng.integers(W)), int(rng.integers(H))
        put_a(t, x, y, GOLD[3], TEAM, wrap_y=True); put_a(t, x + 1, y, GOLD[2], TEAM, wrap_y=True)
        put_a(t, x, y + 1, GOLD[1], 255, wrap_y=True); put_a(t, x + 1, y + 1, GOLD[0], 255, wrap_y=True)
        if rng.random() < 0.4:
            put_a(t, x, y - 1, GOLD[4], TEAM, wrap_y=True)
    return t


def gold(seed):
    """A heap of washed gold: nuggets shingled over a dark ground, 32 x 32 RGBA mask (alpha TEAM = glint)."""
    rng = np.random.default_rng(seed)
    W = H = 32
    t = Tile(W, H, GOLD[0], alpha=True)
    t.a[:] = 255
    for y in range(H):
        for x in range(W):
            t.c[y, x] = BRONZE[0] if rng.random() < 0.6 else BRONZE[1]
    shapes = [[".43.", "4322", "3221", ".11."], ["43.", "322", "211"], [".4.", "432", "321", ".1."], ["433.", "3221", ".11."], ["43", "21"]]
    for gy in range(H // 4):
        for gx in range(W // 4):
            if rng.random() < 0.08:
                continue
            x = gx * 4 + int(rng.integers(0, 3)) + (2 if gy % 2 else 0); y = gy * 4 + int(rng.integers(0, 2))
            shp = shapes[int(rng.integers(len(shapes)))]
            dull = rng.random() < 0.25
            for j, row in enumerate(shp):
                for i, ch in enumerate(row):
                    if ch == ".":
                        continue
                    k = max(int(ch) - (1 if dull else 0), 0)
                    put_a(t, x + i, y + j, GOLD[k], TEAM if k >= 3 else 255, wrap_y=True)
    return t


def pot(seed):
    """Storage jar skin, 32 x 32: u runs round the jar, v from the rim down. A painted zigzag band on the shoulder."""
    rng = np.random.default_rng(seed)
    W = H = 32
    t = Tile(W, H, TERRA[3])
    for y in range(H):
        k = 3
        if y < 2:
            k = 1
        elif y < 4:
            k = 4
        elif y > H - 5:
            k = 2 if y < H - 2 else 1
        for x in range(W):
            kk = int(np.clip(k + (1 if (x + y // 3) % 11 == 0 else 0) - (1 if rng.random() < 0.06 else 0), 0, 5))
            t.put(x, y, TERRA[kk])
    for x in range(W):                                        # shoulder band
        t.put(x, 7, TERRA[0]); t.put(x, 13, TERRA[0])
        for y in range(8, 13):
            t.put(x, y, CREAM[2])
        zy = 8 + [0, 1, 2, 3, 4, 3, 2, 1][x % 8]
        t.put(x, zy, TERRA[1])
        t.put(x, 8 + (4 - (zy - 8)), TERRA[1]) if x % 8 in (0, 4) else None
    for _ in range(8):                                        # firing marks
        x, y = int(rng.integers(W)), int(rng.integers(15, H - 4))
        for d in range(int(rng.integers(2, 5))):
            t.put(x + d, y, TERRA[2])
    return t


def leaves(seed):
    """Olive canopy, 64 x 64 RGBA: small lance leaves in clusters. On the masked shell alpha 0 is a gap; the opaque
    core under it uses the same texture and shows the dark fill."""
    rng = np.random.default_rng(seed)
    W = H = 64
    t = Tile(W, H, OLIVE[0], alpha=True)
    for y in range(H):
        for x in range(W):
            t.c[y, x] = OLIVE[1] if rng.random() < 0.7 else OLIVE[0]
    strokes = [((0, 0), (1, -1), (2, -2)), ((0, 0), (1, 0), (2, -1), (3, -1)), ((0, 0), (0, -1), (1, -2)),
               ((0, 0), (-1, -1), (-2, -2)), ((0, 0), (1, 0), (2, 0)), ((0, 0), (-1, -1), (-1, -2), (-2, -3))]
    for gy in range(H // 3):
        for gx in range(W // 3):
            if rng.random() < 0.1:
                continue
            x = gx * 3 + int(rng.integers(0, 3)); y = gy * 3 + int(rng.integers(0, 3))
            s = strokes[int(rng.integers(len(strokes)))]
            base = int(rng.choice([2, 2, 3, 3, 3, 4]))
            for i, (dx, dy) in enumerate(s):
                k = min(base + (1 if i == len(s) - 1 else 0), 5)
                put_a(t, x + dx, y + dy, OLIVE[k], 255, wrap_y=True)
    return t


def flame(seed):
    """A small fire, 16 x 16 RGBA card: authored tongue, hot core."""
    t = Tile(16, 16, FLAME[1], alpha=True)
    art = ["................",
           ".......1........",
           ".......11.......",
           "......121.......",
           "......1221..1...",
           "...1..12321.1...",
           "...1.1233211....",
           "...11233432.....",
           "...122344321....",
           "..12234444321...",
           "..12344554321...",
           "..12345555321...",
           "..12345555421...",
           "...1234554321...",
           "...012344321....",
           "....0122221....."]
    for j, row in enumerate(art):
        for i, ch in enumerate(row):
            if ch != ".":
                put_a(t, i, j, FLAME[min(int(ch), 4)] if ch != "0" else FLAME[0], 255)
    return t


def dark(seed):
    rng = np.random.default_rng(seed)
    t = Tile(16, 16, DARK[1])
    for _ in range(40):
        t.put(int(rng.integers(16)), int(rng.integers(16)), DARK[int(rng.integers(0, 3))])
    return t


# ---------------------------------------------------------------------------------------- battle damage, new roofs
CHAR = pal("#0c0a09", "#171412", "#241f1b", "#342d27", "#4a4138", "#6b645a")       # soot, charred timber, ash
TILE = [mix(a, b, 0.58) for a, b in zip(TERRA, CLAY)]                              # sun-faded terracotta roof tiles

# T_Bld_Scorch is an atlas of soot marks (256 x 128 texels). name -> (x, y, w, h) in texels; plumes have their
# foot on the bottom edge of their cell. Mirrored by SCORCH in Tools/blender/bldkit.py (in cm: x 4).
SCORCH_CELLS = {
    "plume_l": (0, 0, 64, 96), "plume_m": (64, 0, 48, 64), "plume_s": (112, 0, 32, 48), "blot_l": (144, 0, 64, 64),
    "blot_s": (208, 0, 32, 32), "streak": (240, 0, 16, 64), "smear": (0, 96, 64, 32), "plume_m2": (64, 64, 48, 64),
    "blot_m": (112, 64, 48, 48), "lick": (160, 64, 32, 64), "blot_w": (192, 64, 64, 40),
}


def char(seed):
    """Charred timber / burnt thatch, 64 x 64, tiles: alligatored black blocks, grey ash on the lit edges."""
    rng = np.random.default_rng(seed)
    W = H = 64
    t = Tile(W, H, CHAR[1])
    y = 0
    while y < H:
        ch = int(rng.choice([5, 6, 7, 8]))
        ch = min(ch, H - y)
        x = int(rng.integers(0, 6))
        end = x + W
        while x < end:
            bw = min(int(rng.integers(5, 12)), end - x)
            tone = int(rng.choice([1, 1, 2, 2, 3]))
            for j in range(ch):
                for i in range(bw):
                    c = CHAR[tone]
                    if j == 0 or i == 0:
                        c = CHAR[0]                           # the crack
                    elif j == 1 and i > 1 and rng.random() < 0.7:
                        c = CHAR[min(tone + 2, 5)]            # ash on the lit arris
                    elif rng.random() < 0.06:
                        c = CHAR[min(tone + 1, 4)]
                    t.put(x + i, y + j, c)
            x += bw
        y += ch
    for _ in range(10):                                      # flecks of pale ash
        x, y = int(rng.integers(W)), int(rng.integers(H))
        t.put(x, y, CHAR[5]); t.put(x + 1, y, CHAR[4])
    return t


def scorch(seed):
    """Soot marks as cut-outs (card slot): black hearts, brown-grey fringes that break up in a dither."""
    rng = np.random.default_rng(seed)
    W, H = 256, 128
    t = Tile(W, H, CHAR[1], alpha=True)
    for name, (cx, cy, cw, chh) in SCORCH_CELLS.items():
        n1 = value_noise(rng, cw, chh, 8)
        n2 = value_noise(rng, cw, chh, 4)
        tongues = [(rng.uniform(0.18, 0.82), rng.uniform(0.55, 1.0), rng.uniform(0.10, 0.2)) for _ in range(5)]
        for j in range(1, chh - 1):
            for i in range(1, cw - 1):
                fx = (i + 0.5) / cw - 0.5                     # -0.5 .. 0.5
                fy = 1.0 - (j + 0.5) / chh                    # 0 at the foot .. 1 at the top
                if name.startswith("blot"):
                    d = math.hypot(fx, fy - 0.5) * 2.0
                    f = 1.0 - d
                elif name == "smear":
                    f = min(1.0 - abs(fx) * 2.0, 1.0 - fy) * 1.3
                elif name in ("streak", "lick"):
                    f = (1.0 - abs(fx) * 2.0) * (1.0 - fy * 0.85)
                else:                                         # plume: a broad foot, tongues licking upward
                    f = (1.0 - abs(fx) * 2.0 / (1.0 - 0.45 * fy)) * (1.0 - fy) * 2.2
                    for tx, th, tw in tongues:
                        if fy < th:
                            f = max(f, (1.0 - abs(fx + 0.5 - tx) / tw) * (1.0 - fy / th) * 1.6)
                f += (n1[j, i] - 0.5) * 0.5 + (n2[j, i] - 0.5) * 0.25
                edge = min(i, cw - 1 - i, j, (chh - 1 - j) if name.startswith("blot") else 99) / 3.0
                f = min(f, edge)
                if f <= 0.06:
                    continue
                if f < 0.34 and (i + j) % 2:                  # the fringe breaks up: the wall shows through
                    continue
                if f < 0.16 and (j % 2 or rng.random() < 0.4):
                    continue
                if f < 0.5 and (i % 2 == 0 and j % 2 == 0):
                    continue
                tone = 0 if f > 0.8 else 1 if f > 0.56 else 2 if f > 0.36 else 3
                if rng.random() < 0.12:
                    tone = min(tone + 1, 4)
                put_a(t, cx + i, cy + j, CHAR[tone], 255)
    return t


def target(seed):
    """Face of a straw archery butt, 32 x 32 (128 cm across): coiled straw, painted rings, a bronze-gold centre."""
    rng = np.random.default_rng(seed)
    W = H = 32
    t = Tile(W, H, THATCH[1])
    for y in range(H):
        for x in range(W):
            d = math.hypot(x - 15.5, y - 15.5)
            ring = int(d) % 3
            c = THATCH[3] if ring else THATCH[1]              # the coil
            if rng.random() < 0.2:
                c = THATCH[4] if ring else THATCH[2]
            if d < 3.0:
                c = BRONZE[4] if d < 1.6 else BRONZE[3]
            elif d < 6.5:
                c = TERRA[2] if rng.random() < 0.85 else TERRA[1]
            elif d < 9.5:
                c = CREAM[2] if rng.random() < 0.85 else CREAM[1]
            elif d < 12.5:
                c = TERRA[2] if rng.random() < 0.85 else TERRA[3]
            elif d >= 15.5:
                c = THATCH[0]
            t.put(x, y, c)
    for (x, y) in ((19, 12), (11, 18), (22, 20)):             # arrow holes
        t.put(x, y, DARK[1])
    return t


def roof_tile(seed):
    """Terracotta pan-and-cover tiles, 64 x 64, v runs down the slope: pans 5 texels wide between raised covers,
    each course 8 texels with a shadowed lower lip."""
    rng = np.random.default_rng(seed)
    W = H = 64
    t = Tile(W, H, TILE[2])
    for row in range(H // 8):
        for col in range(W // 8):
            tone = int(rng.choice([2, 2, 3, 3, 1, 4], p=[0.36, 0.26, 0.16, 0.1, 0.08, 0.04]))
            for j in range(8):
                for i in range(8):
                    if i < 5:                                 # the pan
                        c, h = TILE[tone], 0.5
                        if i == 0:
                            c, h = TILE[max(tone - 2, 0)], 0.3       # in the cover's shadow
                        if j == 7:
                            c, h = TILE[max(tone - 2, 0)], 0.2       # under the next course
                        elif j == 6:
                            c = TILE[min(tone + 1, 5)]
                    else:                                     # the cover
                        k = (tone + 1, tone + 2, tone)[i - 5]
                        c, h = TILE[int(np.clip(k, 0, 5))], 1.0
                        if j == 7:
                            c, h = TILE[max(tone - 1, 0)], 0.5
                    t.put(col * 8 + i, row * 8 + j, c, h)
        for _ in range(3):                                    # lichen and chips
            x, y = int(rng.integers(W)), row * 8 + int(rng.integers(1, 6))
            t.put(x, y, mix(TILE[1], GRASS_MOSS[3], 0.5) if rng.random() < 0.5 else TILE[5])
    return t


WATER = pal("#1c3a3c", "#28524f", "#376b63", "#4c887a", "#7fb3a0", "#c8e2cf")     # still trough water, muted teal


def water(seed):
    """Still water in a trough, 32 x 32, tiles: dark teal with a few short pale ripples and glints."""
    rng = np.random.default_rng(seed)
    W = H = 32
    t = Tile(W, H, WATER[1])
    n = value_noise(rng, W, H, 8)
    for y in range(H):
        for x in range(W):
            t.put(x, y, WATER[0] if n[y, x] < 0.3 else (WATER[2] if n[y, x] > 0.68 else WATER[1]))
    for _ in range(11):                                       # ripples: short horizontal dashes, lit above, dark below
        x, y, L = int(rng.integers(W)), int(rng.integers(H)), int(rng.integers(3, 8))
        for i in range(L):
            t.put(x + i, y, WATER[3])
            t.put(x + i, y + 1, WATER[0])
        if rng.random() < 0.5:
            t.put(x + L // 2, y, WATER[4])
    for _ in range(4):
        t.put(int(rng.integers(W)), int(rng.integers(H)), WATER[5])
    return t



# ---------------------------------------------------------------------------------------- build
def build():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(PREVIEW, exist_ok=True)
    A = (SAND[2], SAND[3], SAND[4], SAND[5]); B = (SAND[1], SAND[2], SAND[3], SAND[4]); C = (SAND[2], SAND[3], SAND[4], SAND[4])
    R = (ROSE[2], ROSE[3], ROSE[4], ROSE[5]); P = (PALE[2], PALE[3], PALE[4], PALE[5]); D = (SAND[0], SAND[1], SAND[2], SAND[3])
    brick = mudbrick(111)
    tiles = {
        # curtain walls: mixed course heights, long and short blocks
        "T_Bld_Ashlar": ashlar(101, [8, 8, 10, 6, 8, 8, 8, 10, 6, 8, 8, 8, 10, 6, 8, 8], 10, 22, [A, B, C, R, P], [0.4, 0.17, 0.18, 0.13, 0.12], missing=0, holes=3),
        # towers and the battered base: big, darker, more weathered blocks
        "T_Bld_AshlarLarge": ashlar(102, [16, 14, 18, 16, 16, 14, 18, 16], 20, 34, [B, C, D, R, A], [0.36, 0.22, 0.14, 0.12, 0.16], chip=0.7, missing=0, stains=22),
        "T_Bld_Trim": trim(103),
        "T_Bld_Mudbrick": brick,
        "T_Bld_Plaster": plaster(112, brick),
        "T_Bld_RoofClay": roof_clay(113),
        "T_Bld_Beam": beam(121),
        "T_Bld_Planks": planks(122),
        "T_Bld_Door": door(123),
        "T_Bld_Shutter": shutter(124),
        "T_Bld_Thatch": thatch(131),
        "T_Bld_Soil": soil(132),
        "T_Bld_Wheat": wheat(133),
        "T_Bld_Banner": banner(141),
        "T_Bld_Awning": awning(142),
        "T_Bld_Frieze": frieze(143),
        "T_Bld_Bronze": bronze(144),
        "T_Bld_Ore": ore(151),
        "T_Bld_Gold": gold(156),
        "T_Bld_Pot": pot(152),
        "T_Bld_Leaves": leaves(153),
        "T_Bld_Flame": flame(154),
        "T_Bld_Dark": dark(155),
        "T_Bld_Char": char(161),
        "T_Bld_Scorch": scorch(162),
        "T_Bld_Target": target(163),
        "T_Bld_RoofTile": roof_tile(164),
        "T_Bld_Water": water(165),
    }
    normals = {"T_Bld_Ashlar": 1.7, "T_Bld_AshlarLarge": 1.9, "T_Bld_Trim": 1.4, "T_Bld_Mudbrick": 1.3, "T_Bld_Plaster": 1.2,
               "T_Bld_RoofClay": 1.0, "T_Bld_Thatch": 1.6, "T_Bld_Soil": 1.8,
               "T_Bld_RoofTile": 1.5}
    for name, t in tiles.items():
        t.image().save(os.path.join(OUT, name + ".png"))
        if name in normals:
            t.normal_image(normals[name]).save(os.path.join(OUT, name + "_N.png"))
    Image.fromarray(np.full((4, 4, 3), (128, 128, 255), np.uint8)).save(os.path.join(OUT, "T_Bld_Flat_N.png"))
    # contact sheet: every tile 2 x 2 (seams), 3x nearest, on a dark ground; masks shown as-is
    cells = []
    for name, t in tiles.items():
        im = t.image().convert("RGBA")
        if t.a is not None:
            arr = np.array(im)
            arr[..., 3] = np.where(arr[..., 3] > 0, 255, 0)
            im = Image.fromarray(arr)
        bg = Image.new("RGBA", im.size, (52, 46, 70, 255))
        bg.alpha_composite(im)
        rep = Image.new("RGBA", (im.width * 2, im.height * 2))
        for j in range(2):
            for i in range(2):
                rep.paste(bg, (i * im.width, j * im.height))
        k = 3 if im.width >= 64 else 6
        big = rep.resize((rep.width * k, rep.height * k), Image.NEAREST).convert("RGB")
        big.save(os.path.join(PREVIEW, name + ".png"))
        cells.append(big)
    w = sum(c.width + 8 for c in cells[:8])
    rows = [cells[i:i + 6] for i in range(0, len(cells), 6)]
    sheet = Image.new("RGB", (max(sum(c.width + 8 for c in r) for r in rows), sum(max(c.height for c in r) + 8 for r in rows)), (30, 28, 40))
    y = 0
    for r in rows:
        x = 0
        for c in r:
            sheet.paste(c, (x, y)); x += c.width + 8
        y += max(c.height for c in r) + 8
    sheet.save(os.path.join(PREVIEW, "buildings_sheet.png"))
    print("wrote %d building textures to %s" % (len(tiles) + len(normals) + 1, OUT))


if __name__ == "__main__":
    build()
