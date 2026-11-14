#!/usr/bin/env python3
"""Draws the world's pixel-art texture set into SourceArt/Textures (PNG, tileable).

Run with the tools venv:   Tools/.venv/bin/python Tools/textures/gen_world_textures.py
(needs pillow + numpy:     python3 -m venv Tools/.venv && Tools/.venv/bin/pip install pillow numpy shapely mapbox-earcut)

Every texture is drawn deliberately (placed blades, laid stone courses, set cobbles) from a small
hand-picked palette; noise is only ever used to choose between a few authored options.
World texel density is 4 cm per texel everywhere (see Docs/VISUAL_CONTRACT.md), so a 128 px
tile covers 512 cm. `*_N.png` are tangent-space normal maps derived from the height the
drawing code lays down next to the colour (stones proud of their joints), so the low sun rakes
across courses and cobbles. A contact sheet is written to Saved/TexturePreview/sheet.png.
"""
import os
import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "SourceArt", "Textures")
PREVIEW = os.path.join(ROOT, "Saved", "TexturePreview")


def rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.uint8)


def mix(a, b, t):
    return (a.astype(float) * (1 - t) + b.astype(float) * t + 0.5).astype(np.uint8)


class Tile:
    """A wrapping RGB(+A) canvas with an optional height layer."""

    def __init__(self, w, h, fill, alpha=False):
        self.w, self.h = w, h
        self.c = np.zeros((h, w, 3), np.uint8)
        self.c[:] = fill
        self.a = np.zeros((h, w), np.uint8) if alpha else None
        self.hgt = np.zeros((h, w), np.float32)

    def put(self, x, y, col, height=None, wrap_y=True):
        x %= self.w
        if wrap_y:
            y %= self.h
        elif y < 0 or y >= self.h:
            return
        self.c[y, x] = col
        if self.a is not None:
            self.a[y, x] = 255
        if height is not None:
            self.hgt[y, x] = height

    def get(self, x, y):
        return self.c[y % self.h, x % self.w]

    def rect(self, x0, y0, w, h, col, height=None):
        for y in range(y0, y0 + h):
            for x in range(x0, x0 + w):
                self.put(x, y, col, height)

    def image(self):
        if self.a is None:
            return Image.fromarray(self.c)
        return Image.fromarray(np.dstack([self.c, self.a]))

    def normal_image(self, strength=1.6):
        hmap = self.hgt
        dx = (np.roll(hmap, -1, 1) - np.roll(hmap, 1, 1)) * 0.5
        dy = (np.roll(hmap, -1, 0) - np.roll(hmap, 1, 0)) * 0.5
        n = np.dstack([-dx * strength, -dy * strength, np.ones_like(hmap)])
        n /= np.linalg.norm(n, axis=2, keepdims=True)
        return Image.fromarray(((n * 0.5 + 0.5) * 255 + 0.5).astype(np.uint8))


def value_noise(rng, w, h, cell):
    """Tileable value noise 0..1 (only used to pick between authored options)."""
    gw, gh = max(w // cell, 1), max(h // cell, 1)
    g = rng.random((gh, gw))
    ys, xs = np.mgrid[0:h, 0:w]
    fx, fy = xs / cell, ys / cell
    x0, y0 = np.floor(fx).astype(int), np.floor(fy).astype(int)
    tx, ty = fx - x0, fy - y0
    tx, ty = tx * tx * (3 - 2 * tx), ty * ty * (3 - 2 * ty)
    a = g[y0 % gh, x0 % gw]; b = g[y0 % gh, (x0 + 1) % gw]
    c = g[(y0 + 1) % gh, x0 % gw]; d = g[(y0 + 1) % gh, (x0 + 1) % gw]
    return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty


# ---------------------------------------------------------------------------------------- palettes
# Albedo, as painted. The warm key light and the grade push them yellower on screen, so the greens
# are held a little cooler and darker here than they read in the references.
GRASS = [rgb(c) for c in ("#3a4424", "#49542a", "#5a6530", "#6d7638", "#838742")]       # dark .. light olive
GRASS_MOSS = [rgb(c) for c in ("#323f23", "#3e4d28", "#4b5c2d", "#5c6c33", "#70803b")]   # deeper, mossier
GRASS_DRY = [rgb(c) for c in ("#4b4a28", "#5e5c2f", "#737038", "#888342", "#9d964f")]    # straw patches
EARTH = [rgb(c) for c in ("#382f20", "#4a3f2a", "#5f5238", "#756646", "#8b7b57")]        # dark .. light soil
STONE = [rgb(c) for c in ("#352d22", "#524636", "#6e604a", "#89785d", "#a39071", "#baa786")]   # cliff courses (warm grey)
COBBLE = [rgb(c) for c in ("#39352b", "#524e40", "#6b6654", "#827c67", "#98917a", "#aca58c")]  # road stones (grey-green)
ROCK = [rgb(c) for c in ("#35352c", "#4c4d40", "#666756", "#80806b", "#9a9981", "#b1ae95")]    # boulders
SAND = [rgb(c) for c in ("#5c4a34", "#806a49", "#a08a61", "#b9a377", "#cfbb8c", "#dfcea2")]    # sandstone ashlar
PINE = [rgb(c) for c in ("#162318", "#213324", "#2e4a2b", "#456833", "#6a8a3a", "#93a848")]    # needles dark .. lit tip
BARK = [rgb(c) for c in ("#2a1d15", "#3d2a1e", "#54392a", "#6e4c37", "#8a6448")]
WOOD = [rgb(c) for c in ("#33241a", "#4a3424", "#634731", "#7c5c40", "#967452")]
WATER = [rgb(c) for c in ("#16363d", "#1f4a50", "#2b6165", "#44807f", "#79b3a6", "#c2e3d2")]


# ---------------------------------------------------------------------------------------- grass
# Hand-pixelled turf marks. Digits index the 5-tone palette (0 dark .. 4 highlight), '.' is empty.
# Each is a few blades lying over, tips toward the top of the texture (world +X, up the screen).
TURF_MARKS = [
    ["...34",
     "..33.",
     ".322.",
     "221..",
     "10..."],
    ["..44.",
     ".333.",
     ".332.",
     "2321.",
     "110.."],
    [".4.3.",
     ".3.33",
     "3323.",
     ".222.",
     ".110."],
    ["3...4",
     "33.33",
     ".3232",
     ".2221",
     "..10."],
    [".43..",
     "..33.",
     "..232",
     ".2221",
     ".110."],
    ["..3..",
     ".433.",
     ".3322",
     "22321",
     ".1100"],
]


GRASS_CALM = 0.74      # how much of each turf palette's spread is kept (1 = the first, noisier pass)


def calm(pal, keep=GRASS_CALM):
    """Pulls a 5-tone palette toward its middle tone: the same hues, less contrast between neighbours."""
    mid = pal[2].astype(float)
    return [(mid + (c.astype(float) - mid) * keep + 0.5).astype(np.uint8) for c in pal]


def grass(seed, pal, highlights=0.5, sparse=0.0):
    """Tufted top-down turf: authored blade marks laid like shingles from the back row forward, so
    each overlaps the one behind it and leaves dark thatch showing in the gaps.
    Kept calm so troop sprites read against it: the palette is drawn in (GRASS_CALM), a blade mark spans only
    three neighbouring tones, and the lighter and darker tones come in clumps 6 to 10 texels across (a tileable
    value-noise pick per mark) instead of texel by texel. Measured against the first pass: a third less
    luminance step between neighbouring texels (0.057 -> 0.038), a fifth less spread overall."""
    rng = np.random.default_rng(seed)
    W = H = 128
    pal = calm(pal)
    t = Tile(W, H, pal[1])
    for _ in range(160):                                   # thatch under the blades
        t.put(rng.integers(W), rng.integers(H), pal[0])
    clump = value_noise(rng, W, H, 8) * 0.8 + value_noise(rng, W, H, 16) * 0.2
    soften = {"0": "1", "1": "1", "2": "2", "3": "3", "4": "3"}
    cw, ch = 4, 3
    rows_n = H // ch
    placed = []
    for gy in range(rows_n):
        row = []
        for gx in range(W // cw):
            if rng.random() < sparse:
                continue
            x = gx * cw + int(rng.integers(0, 3)) + (2 if gy % 2 else 0)
            y = gy * ch + int(rng.integers(0, 2))
            marks = TURF_MARKS[int(rng.integers(len(TURF_MARKS)))]
            c = float(clump[y % H, x % W])
            shift = -1 if c < 0.4 else (1 if c > 0.62 else 0)      # tone by clump, not by tuft
            if not (shift == 1 and rng.random() < highlights * 0.5):   # a few tufts in the light clumps keep a bright tip
                marks = ["".join(soften.get(ch, ch) for ch in r) for r in marks]
            row.append((x, y, marks, shift, rng.random() < 0.5))
        placed.append(row)
    # Shingle order has to hold across the wrap too: a mark may only cover marks from the rows just behind it
    # (cyclically), so the last row tucks under the first exactly as every other row tucks under the next.
    owner = np.full((H, W), -1, int)
    for r, row in enumerate(placed):
        for x, y, marks, shift, flip in row:
            for j, line in enumerate(marks):
                if flip:
                    line = line[::-1]
                for i, ch in enumerate(line):
                    if ch == ".":
                        continue
                    px_, py_ = (x + i) % W, (y + j) % H
                    q = owner[py_, px_]
                    if q < 0 or (r - q) % rows_n <= rows_n // 2:
                        t.c[py_, px_] = pal[int(np.clip(int(ch) + shift, 0, 4))]
                        owner[py_, px_] = r
    return t


# ---------------------------------------------------------------------------------------- stone helpers
def stone_block(t, rng, x0, y0, w, h, tones, gap, base_h=1.0, chip=0.5, round_corners=1, tilt=True):
    """A dressed / weathered block: body tone, lit top-left edges, shaded bottom-right edges,
    clipped corners, a few dabs of neighbouring tone and the odd chip. Leaves a 1 px joint on the
    right and bottom. `tones` is (shade, body, light, highlight)."""
    shade, body, light, hi = tones
    bw, bh = w - 1, h - 1
    tx, ty = (rng.uniform(-0.12, 0.12), rng.uniform(-0.12, 0.12)) if tilt else (0.0, 0.0)
    cut = {(0, 0): rng.random() < 0.8, (bw - 1, 0): rng.random() < 0.8,
           (0, bh - 1): rng.random() < 0.8, (bw - 1, bh - 1): rng.random() < 0.9} if round_corners else {}
    for j in range(bh):
        for i in range(bw):
            if cut.get((i, j)):
                t.put(x0 + i, y0 + j, gap, 0.0)
                continue
            col = body
            if j == 0 or i == 0:
                col = light
            if j == bh - 1 or i == bw - 1:
                col = shade
            if (j == 0 and i == bw - 1) or (i == 0 and j == bh - 1):
                col = body
            hh = base_h + tx * (i - bw / 2) / max(bw, 1) + ty * (j - bh / 2) / max(bh, 1)
            if j in (0, bh - 1) or i in (0, bw - 1):
                hh -= 0.35
            t.put(x0 + i, y0 + j, col, hh)
    # highlight run along the top edge (not the whole edge: hand-placed)
    if bw > 4:
        a = rng.integers(1, max(bw // 2, 2)); b = rng.integers(a + 1, bw - 1)
        for i in range(a, b):
            t.put(x0 + i, y0, hi if rng.random() < 0.8 else light, base_h - 0.3)
    # dabs of tone variation inside
    for _ in range(max(1, bw * bh // 22)):
        i, j = rng.integers(1, max(bw - 2, 2)), rng.integers(1, max(bh - 1, 2))
        col = light if rng.random() < 0.5 else shade
        for d in range(rng.integers(1, 4)):
            if i + d < bw - 1 and j < bh - 1:
                t.put(x0 + i + d, y0 + j, mix(body, col, 0.7), base_h)
    # a chip out of an edge, or a crack
    if rng.random() < chip and bw > 5 and bh > 4:
        if rng.random() < 0.5:
            i = rng.integers(2, bw - 2)
            t.put(x0 + i, y0 + bh - 1, gap, 0.0); t.put(x0 + i + 1, y0 + bh - 1, gap, 0.0)
            t.put(x0 + i, y0 + bh - 2, shade, base_h - 0.3)
        else:
            i, j = rng.integers(2, bw - 2), 1
            while j < bh - 1:
                t.put(x0 + i, y0 + j, shade, base_h - 0.5)
                j += 1
                i += rng.choice([-1, 0, 0, 1])
                if i < 1 or i > bw - 2:
                    break


def partition(rng, total, lo, hi):
    """Random run lengths in [lo, hi] that sum exactly to `total`."""
    out = []
    left = total
    while left > 0:
        n = int(rng.integers(lo, hi + 1))
        if left - n < lo:
            n = left if left <= hi + lo // 2 else left - lo
        out.append(n)
        left -= n
    return out


def cliff(seed):
    """Cliff face, v = depth below the turf: a band of root-bound soil, then coursed stone.
    Courses step and blocks vary so it reads as weathered strata rather than masonry."""
    rng = np.random.default_rng(seed)
    W, H = 128, 128
    gap = STONE[0]
    t = Tile(W, H, gap)
    y = 0
    # --- soil band under the turf: dark earth, pebbles, hanging roots
    soil_h = 5
    for yy in range(soil_h):
        for xx in range(W):
            r = rng.random()
            col = EARTH[2] if r < 0.55 else (EARTH[1] if r < 0.85 else EARTH[3])
            t.put(xx, yy, col, 0.55)
    for _ in range(14):                                    # short horizontal strata dashes
        xx, yy = rng.integers(W), rng.integers(1, soil_h - 1)
        for d in range(rng.integers(3, 8)):
            t.put(xx + d, yy, EARTH[3] if yy % 2 else EARTH[1], 0.6)
    for _ in range(7):                                     # pebbles bedded in the soil
        xx, yy = rng.integers(W), 1
        w = rng.integers(2, 5)
        for d in range(w):
            t.put(xx + d, yy, STONE[4] if d < w - 1 else STONE[2], 0.9)
            t.put(xx + d, yy + 1, STONE[2] if d else STONE[3], 0.9)
            t.put(xx + d, yy + 2, EARTH[0], 0.4)
    for _ in range(9):                                     # roots
        xx, yy = rng.integers(W), 0
        for d in range(rng.integers(4, soil_h + 2)):
            t.put(xx, yy + d, EARTH[3] if d % 3 else EARTH[4], 0.75)
            xx += rng.choice([-1, 0, 0, 0, 1])
    y = soil_h
    # --- stone courses
    tone_sets = [
        (STONE[1], STONE[2], STONE[3], STONE[4]),
        (STONE[2], STONE[3], STONE[4], STONE[5]),
        (STONE[1], STONE[2], STONE[3], STONE[3]),
        (EARTH[1], EARTH[2], EARTH[3], EARTH[4]),           # earthy block
        (STONE[2], STONE[3], STONE[4], STONE[5]),
    ]
    rows = partition(rng, H - soil_h, 9, 16)
    for r, rh in enumerate(rows):
        x = int(rng.integers(0, 12))
        widths = partition(rng, W, 8, 26)
        for bw in widths:
            tones = tone_sets[int(rng.choice(len(tone_sets), p=[0.3, 0.22, 0.2, 0.13, 0.15]))]
            jig = int(rng.choice([0, 0, 0, 1, -1]))        # courses are not ruled lines
            if bw >= 16 and rng.random() < 0.14:            # two smaller stones stacked in one slot
                h1 = rh // 2 + int(rng.integers(-1, 2))
                stone_block(t, rng, x, y + jig, bw, h1, tones, gap)
                stone_block(t, rng, x, y + jig + h1, bw, rh - h1, tone_sets[int(rng.integers(0, 3))], gap)
            else:
                stone_block(t, rng, x, y + jig, bw, rh, tones, gap, base_h=1.0 + rng.uniform(-0.1, 0.15))
            if rng.random() < 0.2:                         # moss creeping on the block's top edge
                for d in range(rng.integers(2, bw - 2)):
                    if rng.random() < 0.75:
                        t.put(x + 1 + d, y + jig, GRASS_MOSS[2] if rng.random() < 0.6 else GRASS_MOSS[1])
            x += bw
        y += rh
    return t


def lip(seed, pal):
    """The turf hanging over a cliff top (RGBA). Row 0 is the cliff's top edge. Alpha 255 = grass,
    alpha 110 = the shadow the fringe throws on the stone below it, 0 = bare cliff."""
    rng = np.random.default_rng(seed)
    W, H = 128, 24
    t = Tile(W, H, pal[1], alpha=True)
    length = np.zeros(W, int)
    x = 0
    while x < W:                                           # clumps of hanging blades: toothed profile
        w = int(rng.integers(3, 8))
        peak = int(rng.choice([4, 5, 6, 7, 8, 9, 11, 13], p=[0.12, 0.16, 0.18, 0.16, 0.14, 0.1, 0.08, 0.06]))
        mid = rng.integers(0, w)
        for i in range(w):
            if x + i < W:
                length[x + i] = max(3, peak - abs(i - mid) * int(rng.integers(1, 3)) - int(rng.integers(0, 2)))
        x += w
    length[-1] = length[0]
    for x in range(W):
        L = length[x]
        for y in range(L):
            f = y / max(L - 1, 1)
            if y <= 1:
                col = pal[3] if rng.random() < 0.55 else pal[2]      # rolled-over top catches the light
            elif f < 0.45:
                col = pal[2] if rng.random() < 0.6 else pal[1]
            elif f < 0.8:
                col = pal[1] if rng.random() < 0.7 else pal[0]
            else:
                col = pal[0]
            t.put(x, y, col, wrap_y=False)
        for y in range(L, min(L + 3, H)):                  # contact shadow under the fringe
            t.c[y, x] = (0, 0, 0)
            t.a[y, x] = 110 if y < L + 2 else 60
    for _ in range(46):                                    # single lighter blades laid over the fringe
        x = int(rng.integers(W)); L = length[x]
        for y in range(1, max(L - 1, 2)):
            t.put(x, y, pal[3] if y < L // 2 else pal[2], wrap_y=False)
    return t


# ---------------------------------------------------------------------------------------- ground
def dirt(seed):
    """Packed earth: short raked dashes with a shadow under each, pebbles bedded in."""
    rng = np.random.default_rng(seed)
    W = H = 128
    t = Tile(W, H, EARTH[2])
    t.hgt[:] = 0.5
    n = value_noise(rng, W, H, 16)
    t.c[n > 0.6] = mix(EARTH[2], EARTH[3], 0.5)
    for gy in range(H // 3):
        for gx in range(W // 6):
            if rng.random() < 0.18:
                continue
            x = gx * 6 + rng.integers(0, 6) + (3 if gy % 2 else 0)
            y = gy * 3 + rng.integers(0, 3)
            L = int(rng.integers(2, 6))
            light = EARTH[4] if rng.random() < 0.3 else EARTH[3]
            for d in range(L):
                t.put(x + d, y, light, 0.6)
                t.put(x + d, y + 1, EARTH[1], 0.4)
            t.put(x + L, y + 1, EARTH[0], 0.35)
    for _ in range(46):                                    # pebbles
        x, y = int(rng.integers(W)), int(rng.integers(H))
        w, h = int(rng.integers(2, 5)), int(rng.integers(2, 4))
        tone = int(rng.integers(2, 4))
        for j in range(h):
            for i in range(w):
                if (i in (0, w - 1)) and (j in (0, h - 1)) and w > 2:
                    continue
                col = COBBLE[tone + 1] if j == 0 else (COBBLE[tone - 1] if j == h - 1 else COBBLE[tone])
                t.put(x + i, y + j, col, 0.95)
        for i in range(w):
            t.put(x + i + 1, y + h, EARTH[0], 0.3)
    return t


def cobble(seed):
    """An old road: flat fieldstones set in staggered, uneven rows; earth and a little moss between."""
    rng = np.random.default_rng(seed)
    W = H = 128
    gap = mix(EARTH[0], COBBLE[0], 0.5)
    t = Tile(W, H, gap)
    for _ in range(500):
        t.put(rng.integers(W), rng.integers(H), EARTH[1], 0.05)
    tone_sets = [(COBBLE[1], COBBLE[2], COBBLE[3], COBBLE[4]), (COBBLE[2], COBBLE[3], COBBLE[4], COBBLE[5]),
                 (COBBLE[1], COBBLE[2], COBBLE[3], COBBLE[3]), (STONE[1], STONE[2], STONE[3], STONE[4])]
    y = 0
    for rh in partition(rng, H, 7, 11):
        x = int(rng.integers(0, 9))
        for bw in partition(rng, W, 7, 14):
            if rng.random() < 0.07:                        # a stone gone: earth and moss in the hole
                for _ in range(bw):
                    t.put(x + rng.integers(bw), y + rng.integers(rh), GRASS_MOSS[int(rng.integers(1, 3))], 0.1)
            else:
                dy = int(rng.choice([0, 0, 1]))
                hh = rh - int(rng.choice([0, 0, 1]))
                stone_block(t, rng, x, y + dy, bw, hh, tone_sets[int(rng.choice(4, p=[0.34, 0.26, 0.24, 0.16]))], gap,
                            base_h=1.0 + rng.uniform(-0.12, 0.12), chip=0.3)
            x += bw
        y += rh
    return t


def rock(seed):
    """Boulder skin: angular planes of slightly different tone with dark fissures between, lit edges."""
    rng = np.random.default_rng(seed)
    W = H = 64
    pts = rng.random((14, 2)) * [W, H]
    tone = rng.choice([2, 2, 3, 3, 4], size=len(pts))
    ys, xs = np.mgrid[0:H, 0:W]
    best = np.full((H, W), 1e9); second = np.full((H, W), 1e9); idx = np.zeros((H, W), int)
    for i, (px, py) in enumerate(pts):
        dx = np.abs(xs - px); dx = np.minimum(dx, W - dx)
        dy = np.abs(ys - py); dy = np.minimum(dy, H - dy)
        d = dx * 0.8 + dy * 1.25 + np.maximum(dx, dy) * 0.4          # angular, slightly flattened cells
        closer = d < best
        second = np.where(closer, best, np.minimum(second, d))
        idx = np.where(closer, i, idx)
        best = np.where(closer, d, best)
    t = Tile(W, H, ROCK[2])
    for y in range(H):
        for x in range(W):
            k = tone[idx[y, x]]
            t.put(x, y, ROCK[k], 1.0)
    edge = (second - best) < 1.3
    for y in range(H):
        for x in range(W):
            if edge[y, x]:
                t.put(x, y, ROCK[1] if rng.random() < 0.75 else ROCK[0], 0.2)
            elif edge[(y - 1) % H, x] or edge[y, (x - 1) % W]:      # lit rim below / right of a fissure
                k = tone[idx[y, x]]
                t.put(x, y, ROCK[min(k + 1, 5)], 0.85)
            elif edge[(y + 1) % H, x]:
                k = tone[idx[y, x]]
                t.put(x, y, ROCK[max(k - 1, 1)], 0.85)
    for _ in range(50):                                    # pitting
        x, y = int(rng.integers(W)), int(rng.integers(H))
        if not edge[y, x]:
            k = tone[idx[y, x]]
            t.put(x, y, ROCK[max(k - 1, 1)], 0.8)
            if rng.random() < 0.5:
                t.put(x + 1, y, ROCK[max(k - 1, 1)], 0.8)
    return t


def sandstone(seed):
    """Weathered ashlar for the ruin: regular courses, half-bond, stains and missing arrises."""
    rng = np.random.default_rng(seed)
    W, H = 128, 64
    gap = SAND[0]
    t = Tile(W, H, gap)
    tone_sets = [(SAND[2], SAND[3], SAND[4], SAND[5]), (SAND[1], SAND[2], SAND[3], SAND[4]), (SAND[2], SAND[3], SAND[4], SAND[4])]
    y = 0
    for r in range(H // 8):
        x = 0 if r % 2 == 0 else 8
        for bw in ([16] * 8 if rng.random() < 0.6 else partition(rng, W, 12, 20)):
            stone_block(t, rng, x, y, bw, 8, tone_sets[int(rng.choice(3, p=[0.5, 0.28, 0.22]))], gap, chip=0.35, tilt=False)
            x += bw
        y += 8
    for _ in range(10):                                    # rain stains running down
        x, y = int(rng.integers(W)), int(rng.integers(H))
        for d in range(rng.integers(5, 14)):
            c = t.get(x, y + d)
            t.put(x, y + d, mix(c, SAND[1], 0.45), t.hgt[(y + d) % H, x % W])
            if rng.random() < 0.3:
                x += rng.choice([-1, 1])
    return t


# ---------------------------------------------------------------------------------------- trees
BOUGH_TIPS = [
    [".55.",
     "4544",
     ".443",
     ".33.",
     "..2."],
    ["554.",
     "4543",
     ".433",
     "..32",
     "..2."],
    [".455",
     "4544",
     "344.",
     "33..",
     "2..."],
    [".5.",
     "454",
     "443",
     ".3.",
     ".2."],
]


def needles(seed):
    """One conifer bough tier, unwrapped: v runs from under the tier above (dark) to the drooping
    rim (lit tips, ragged alpha). Bough tips are authored marks laid in overlapping rows."""
    rng = np.random.default_rng(seed)
    W, H = 64, 48
    t = Tile(W, H, PINE[1], alpha=True)
    for y in range(H):
        for x in range(W):
            r = rng.random()
            t.c[y, x] = PINE[0] if r < 0.45 else (PINE[1] if r < 0.85 else PINE[2])
    for ry, shift, skip in [(1, -3, 0.5), (7, -3, 0.4), (13, -3, 0.35), (19, -2, 0.3), (25, -2, 0.2), (30, -1, 0.15), (35, 0, 0.1), (40, 0, 0.0), (43, 0, 0.0)]:
        x = int(rng.integers(0, 4))
        while x < W + 2:
            rows = BOUGH_TIPS[int(rng.integers(len(BOUGH_TIPS)))]
            yy = ry + int(rng.integers(-1, 2))
            sh = shift - (1 if rng.random() < 0.3 else 0)
            if rng.random() >= skip:
                for j, row in enumerate(rows):
                    for i, ch in enumerate(row):
                        if ch != "." and 0 <= yy + j < H:
                            t.c[yy + j, (x + i) % W] = PINE[int(np.clip(int(ch) + sh, 0, 5))]
                for i in range(len(rows[0])):                 # shadow under the tip
                    if yy + 5 < H:
                        t.c[yy + 5, (x + i) % W] = PINE[0]
            x += len(rows[0]) + int(rng.integers(0, 3))
    # ragged rim: toothed lower edge
    t.a[:] = 255
    x = 0
    while x < W:
        w = int(rng.integers(4, 8)); peak = int(rng.integers(5, 11))
        for i in range(w):
            if x + i < W:
                keep = max(peak - int(abs(i - (w - 1) / 2.0) * 2.4), 1)
                t.a[H - 10 + keep:, x + i] = 0
        x += w
    return t


def bark(seed):
    rng = np.random.default_rng(seed)
    W, H = 32, 64
    t = Tile(W, H, BARK[1])
    for x in range(W):
        y = int(rng.integers(H))
        while y < H * 2:
            L = int(rng.integers(4, 14))
            col = BARK[int(rng.choice([0, 1, 2, 2, 3], p=[0.2, 0.25, 0.3, 0.0, 0.25]))]
            for d in range(L):
                t.put(x, y + d, col, 1.0 if col is BARK[3] else 0.5)
            y += L + int(rng.integers(0, 3))
    for _ in range(26):                                    # lit ridges and knots
        x, y = int(rng.integers(W)), int(rng.integers(H))
        for d in range(rng.integers(3, 9)):
            t.put(x, y + d, BARK[4], 1.0)
            t.put(x + 1, y + d, BARK[0], 0.2)
    return t


def wood(seed):
    """Weathered planks, grain along u. 64 x 32, tiles both ways (four 8-texel boards)."""
    rng = np.random.default_rng(seed)
    W, H = 64, 32
    t = Tile(W, H, WOOD[2])
    for py in range(0, H, 8):
        tone = int(rng.integers(1, 4))
        for y in range(py, py + 8):
            for x in range(W):
                col = WOOD[tone]
                if y == py:
                    col = WOOD[min(tone + 1, 4)]
                if y == py + 7:
                    col = WOOD[0]
                t.put(x, y, col)
        for _ in range(7):
            x, y = int(rng.integers(W)), py + int(rng.integers(1, 7))
            for d in range(rng.integers(4, 16)):
                t.put(x + d, y, WOOD[max(tone - 1, 0)] if rng.random() < 0.6 else WOOD[min(tone + 1, 4)])
        x = int(rng.integers(W))                           # a board end
        for y in range(py, py + 8):
            t.put(x, y, WOOD[0])
    return t


def log_end(seed):
    """Sawn end of a log, 16 x 16: growth rings inside a bark rim."""
    rng = np.random.default_rng(seed)
    W = H = 16
    t = Tile(W, H, BARK[1])
    c = 7.5
    for y in range(H):
        for x in range(W):
            r = ((x - c) ** 2 + (y - c) ** 2) ** 0.5
            if r > 7.6:
                col = BARK[1]
            elif r > 6.4:
                col = BARK[2]
            else:
                k = int(r + rng.uniform(-0.2, 0.2))
                col = [WOOD[4], WOOD[3], WOOD[4], WOOD[2]][k % 4]
            t.put(x, y, col)
    t.put(7, 7, WOOD[1]); t.put(8, 8, WOOD[1])
    return t


# ---------------------------------------------------------------------------------------- water / sprites
FLOW_TEXELS = (2, 3)      # the river's downstream direction in texture space (x right, y down): M_Water slides T_Water
                          # along it, and the streaks are drawn lying that way. Matches FLOW_DIR in gen_battlefield.py.
GRAVEL = [rgb(c) for c in ("#5d5a48", "#77735c", "#928c71", "#aaa487", "#c2bc9d", "#d8d3b6")]   # a ford's bed, dry tones (the water tints it)


def water(seed):
    """Running water seen from above: calm pools of two close teals in broad patches, with sparse ripple streaks lying
    along the current (FLOW_TEXELS), each a light line with a dark one under its lee side, and the odd glint."""
    rng = np.random.default_rng(seed)
    W = H = 128
    t = Tile(W, H, WATER[1])
    n = value_noise(rng, W, H, 32) * 0.6 + value_noise(rng, W, H, 16) * 0.4
    t.c[n < 0.44] = WATER[0]
    t.c[n > 0.66] = mix(WATER[1], WATER[2], 0.6)
    fx, fy = FLOW_TEXELS
    for _ in range(84):
        x, y = int(rng.integers(W)), int(rng.integers(H))
        L = int(rng.integers(6, 17))
        bright = rng.random()
        tone = WATER[3] if bright < 0.72 else WATER[4]
        bend = int(rng.integers(3, 6))                         # a streak wavers a texel now and then
        for k in range(L):
            px_, py_ = x + (k * fx) // fy + ((k // bend) % 2), y + k
            t.put(px_, py_, WATER[2] if k in (0, L - 1) else tone)        # the ends fade
            if 0 < k < L - 1:
                t.put(px_ + 1, py_, WATER[0])
        if bright > 0.9:
            t.put(x + ((L // 2) * fx) // fy, y + L // 2, WATER[5])
    return t


def gravel(seed):
    """The bed of a ford: rounded pale pebbles packed on dark wet sand, a few larger stones."""
    rng = np.random.default_rng(seed)
    W = H = 128
    t = Tile(W, H, GRAVEL[1])
    n = value_noise(rng, W, H, 16)
    t.c[n > 0.6] = mix(GRAVEL[1], GRAVEL[2], 0.5)
    for _ in range(300):
        t.put(rng.integers(W), rng.integers(H), GRAVEL[0])
    for i in range(1000):
        x, y = int(rng.integers(W)), int(rng.integers(H))
        big = i < 40
        w, h = (int(rng.integers(5, 9)), int(rng.integers(4, 7))) if big else (int(rng.integers(2, 5)), int(rng.integers(2, 4)))
        tone = int(rng.integers(2, 5))
        for j in range(h):
            for k in range(w):
                if (k in (0, w - 1)) and (j in (0, h - 1)) and w > 2:
                    continue
                col = GRAVEL[min(tone + 1, 5)] if j == 0 else (GRAVEL[tone - 1] if j == h - 1 else GRAVEL[tone])
                t.put(x + k, y + j, col)
    return t


def tufts(seed):
    """Sprite strip for foliage cards, 96 x 24: tall grass (16), short grass (16), dry reeds (16),
    fern (24), flowers (24). Blades are one texel wide, lighter toward the tip, rooted on the bottom row."""
    rng = np.random.default_rng(seed)
    W, H = 96, 24
    t = Tile(W, H, GRASS[2], alpha=True)

    def stalk(cx, height, lean, pal, x_lo, x_hi, curl=0.0):
        x = float(cx)
        for i in range(height):
            f = i / max(height - 1, 1)
            col = pal[1] if f < 0.3 else (pal[2] if f < 0.62 else (pal[3] if f < 0.9 else pal[4]))
            px = int(round(x))
            if x_lo <= px < x_hi:
                t.put(px, H - 1 - i, col, wrap_y=False)
            x += lean * (0.35 + f) + curl * f * f

    for x_lo, (n, hmin, hmax, pal) in zip((0, 16, 32), [(8, 9, 19, GRASS), (9, 4, 9, GRASS), (7, 10, 21, GRASS_DRY)]):
        for k in range(n):
            cx = x_lo + 2 + int(rng.integers(0, 12))
            stalk(cx, int(rng.integers(hmin, hmax + 1)), rng.uniform(-0.3, 0.3), pal, x_lo, x_lo + 16, rng.uniform(-0.5, 0.5))
        for k in range(5):                                  # a dark root tuft so the card sits in the turf
            t.put(x_lo + 3 + int(rng.integers(0, 10)), H - 1, pal[0], wrap_y=False)
    # fern: fronds arcing out from one root, pinnae either side of each rib
    FERN = [rgb(c) for c in ("#34492a", "#44602f", "#587a36", "#6f9140", "#8aa64c")]
    x_lo, x_hi = 48, 72
    root_x = x_lo + 12
    for ang in (-74, -50, -26, -6, 14, 36, 58, 76):
        a = np.radians(ang + rng.uniform(-5, 5))
        L = int(rng.integers(11, 17))
        x, y = float(root_x), float(H - 1)
        for i in range(L):
            f = i / L
            col = FERN[2] if f < 0.35 else (FERN[3] if f < 0.75 else FERN[4])
            px, py = int(round(x)), int(round(y))
            if x_lo <= px < x_hi and 0 <= py < H:
                t.put(px, py, col, wrap_y=False)
                if i > 1 and i % 2 == 0:
                    for sgn in (-1, 1):
                        qx, qy = px + (sgn if abs(ang) < 40 else 0), py + (0 if abs(ang) < 40 else sgn)
                        if x_lo <= qx < x_hi and 0 <= qy < H:
                            t.put(qx, qy, FERN[3] if f > 0.45 else FERN[1], wrap_y=False)
            x += np.sin(a) * (0.6 + 0.45 * f)
            y -= np.cos(a) * (1.0 - 0.8 * f) + 0.02
    # flowers: low leaves with small pale blossoms
    x_lo = 72
    petals = [rgb(c) for c in ("#e9e2d0", "#d9b8c0", "#c7ccdf")]
    for k in range(9):
        cx = x_lo + 3 + int(rng.integers(0, 18))
        hgt = int(rng.integers(3, 9))
        stalk(cx, hgt, rng.uniform(-0.25, 0.25), GRASS_MOSS, x_lo, x_lo + 24)
        if rng.random() < 0.75:
            pc = petals[int(rng.integers(3))]
            top = H - 1 - hgt
            for dx, dy in ((0, 0), (-1, 0), (1, 0), (0, -1)):
                if x_lo <= cx + dx < x_lo + 24 and top + dy >= 0:
                    t.put(cx + dx, top + dy, pc, wrap_y=False)
            t.put(cx, top, rgb("#d6b84a"), wrap_y=False)
    return t


def banner(seed):
    """Cloth banner, 16x40 RGBA: deep blue field, muted gold border and device, swallow-tail."""
    rng = np.random.default_rng(seed)
    W, H = 16, 40
    blue = [rgb(c) for c in ("#182a4c", "#223a68", "#2f4f86")]
    gold = [rgb(c) for c in ("#7d6428", "#a8893a", "#cdb05a")]
    t = Tile(W, H, blue[1], alpha=True)
    for y in range(H):
        notch = max(0, y - (H - 8))                         # swallow-tail cut
        for x in range(W):
            if abs(x - 7.5) < notch * 0.9:
                continue
            col = blue[1]
            if x in (3, 4, 11, 12) and y % 5 < 4:
                col = blue[0]                               # folds
            if x in (6, 7):
                col = blue[2]
            if x in (0, W - 1) or y == 0:
                col = gold[1]
            if x in (1, W - 2) or y == 1:
                col = gold[0]
            t.put(x, y, col, wrap_y=False)
    for (x, y) in [(7, 10), (8, 10), (6, 11), (9, 11), (7, 12), (8, 12), (7, 13), (8, 13), (5, 14), (6, 14), (7, 14), (8, 14), (9, 14), (10, 14),
                   (7, 15), (8, 15), (7, 16), (8, 16), (7, 17), (8, 17)]:       # a small sword-and-crown device
        t.put(x, y, gold[2] if y < 14 else gold[1], wrap_y=False)
    return t


def lens_dirt(seed):
    """Not pixel art: a soft, mostly black smudge-and-speck mask for the bloom's lens dirt (512 x 288)."""
    from PIL import ImageFilter, ImageDraw
    rng = np.random.default_rng(seed)
    W, H = 512, 288
    img = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(img)
    for _ in range(46):                                    # out-of-focus dust discs
        r = float(rng.uniform(6, 34)); x, y = float(rng.uniform(0, W)), float(rng.uniform(0, H))
        v = int(rng.uniform(22, 90))
        d.ellipse([x - r, y - r, x + r, y + r], outline=v, width=int(rng.integers(1, 3)))
        d.ellipse([x - r + 2, y - r + 2, x + r - 2, y + r - 2], fill=int(v * 0.45))
    img = img.filter(ImageFilter.GaussianBlur(1.6))
    smear = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(smear)
    for _ in range(14):                                    # wiped streaks
        x, y = float(rng.uniform(0, W)), float(rng.uniform(0, H))
        d.line([x, y, x + float(rng.uniform(-150, 150)), y + float(rng.uniform(-40, 40))], fill=int(rng.uniform(18, 46)), width=int(rng.integers(6, 22)))
    smear = smear.filter(ImageFilter.GaussianBlur(9))
    a = np.maximum(np.array(img, np.float32), np.array(smear, np.float32))
    ys, xs = np.mgrid[0:H, 0:W]
    edge = np.clip(np.hypot((xs - W / 2) / (W / 2), (ys - H / 2) / (H / 2)), 0, 1.3)       # dirtier toward the rim of the glass
    a = np.clip(a * (0.35 + 0.9 * edge), 0, 255).astype(np.uint8)
    return Image.fromarray(np.dstack([a, a, a]))


# ---------------------------------------------------------------------------------------- build
def build():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(PREVIEW, exist_ok=True)
    tiles = {
        "T_Grass": grass(11, GRASS),
        "T_GrassMoss": grass(12, GRASS_MOSS, highlights=0.1, sparse=0.12),
        "T_GrassDry": grass(13, GRASS_DRY, highlights=0.3, sparse=0.2),
        "T_Dirt": dirt(21),
        "T_Cobble": cobble(22),
        "T_Cliff": cliff(31),
        "T_Lip": lip(32, calm(GRASS)),
        "T_Rock": rock(41),
        "T_Sandstone": sandstone(42),
        "T_Needles": needles(51),
        "T_Bark": bark(52),
        "T_Wood": wood(53),
        "T_LogEnd": log_end(54),
        "T_Water": water(61),
        "T_Gravel": gravel(62),
        "T_Tufts": tufts(71),
        "T_Banner": banner(72),
    }
    normals = {"T_Cliff": 1.8, "T_Cobble": 1.6, "T_Rock": 1.5, "T_Sandstone": 1.6, "T_Dirt": 1.0}
    for name, t in tiles.items():
        t.image().save(os.path.join(OUT, name + ".png"))
        if name in normals:
            t.normal_image(normals[name]).save(os.path.join(OUT, name + "_N.png"))
    lens_dirt(81).save(os.path.join(OUT, "T_LensDirt.png"))
    # contact sheet: each tile repeated 2x2 (to show seams) and blown up 4x, nearest
    cells = []
    for name, t in tiles.items():
        im = t.image().convert("RGBA")
        bg = Image.new("RGBA", im.size, (70, 60, 90, 255))
        bg.alpha_composite(im)
        rep = Image.new("RGBA", (im.width * 2, im.height * 2))
        for j in range(2):
            for i in range(2):
                rep.paste(bg, (i * im.width, j * im.height))
        cells.append((name, rep.resize((rep.width * 3, rep.height * 3), Image.NEAREST)))
    for name, im in cells:
        im.convert("RGB").save(os.path.join(PREVIEW, name + ".png"))
    print("wrote %d textures to %s" % (len(tiles) + len(normals), OUT))


if __name__ == "__main__":
    build()
