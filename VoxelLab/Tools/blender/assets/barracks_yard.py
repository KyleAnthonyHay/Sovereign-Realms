"""SM_BarracksYard: the barracks compound, remade after References/Remake/barracks.png.

A long timber-and-stone hall with a green gable roof (ridge left-right) at the back (+Y), a tall cross gable over an
open central bay (crossed-swords banner, weapon rack inside, flag on the peak), a stone chimney, a canvas awning over a
table on the left, a lean-to shed with crates on the right; in front (-Y) a big fenced dirt training yard with a
crossed-swords mark in the dirt, stone-footed lantern posts at the front corners and a timber gate arch (banner, two
hanging lanterns) in the middle of the front fence, a cobble path leading out of the gate.

The three training dummies are NOT in the mesh: they are listed in the sidecar JSON as props (SM_TrainingDummy).

Pivot: centre of the compound's footprint at ground level; the yard's dirt top is at z = 0.125.
Everything is written in voxels counted from that centre (CVox), 8 voxels = 1 m.

Run:  Blender -b --factory-startup --python Tools/blender/assets/barracks_yard.py -- [--no-render] [--views a,b] [--samples n]
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import math
import numpy as np
import voxlib as V
import voxkit as K
from voxlib import Vox

VOX = 0.125
FINE = 0.0625
E = 24                                    # eaves of the hall and of the cross gable: 3.0 m
RISE, CRISE = 4, 5                        # step heights of the hall's roof and of the steeper cross gable
HX0, HX1, HY0, HY1 = -66, 44, 24, 64      # hall core walls (x -8.25 .. 5.5 m, y 3 .. 8 m)
BX0, BX1, BY0 = -14, 22, 12               # the bay under the cross gable (core), its front wall at y = 1.5 m
OX0, OX1, OZ1 = -10, 18, 22               # the bay's opening: 3.5 m wide, 2.5 m tall above its floor (z = 2)
SX1 = 74                                  # the shed runs from the hall's east end to x = 9.25 m
FY = -66                                  # the front fence's centre line (y = -8.25 m)
FX = 72                                   # the side fences' centre lines (x = +-9.0 m)
GX = 10                                   # the gate's clear half width (2.5 m opening)

WOODS = ["#ffffff", "#f4dcc0", "#ffe9cc", "#e8ccaa", "#fff2d8", "#eed2b0"]
BARGE = ["#f2d2ae", "#e4be96", "#f8dcb8", "#dab48c", "#eccaa2", "#e8c49c"]
LEAFS = ["#ffffff", "#e6f2a6", "#cfe690", "#f2f6b4", "#b8dc7c"]
DARK = "#8c7458"
FRAME = "#d8b890"
STEEL = "#c3c7cf"
STEEL_DARK = "#8a8e98"
SHAFT = "#ffdcae"
CANVAS = ["#efe0b2", "#e6d5a2", "#f3e6bc"]
DIRT = ["#eec29a", "#f6cda6", "#fcd6b0", "#ffdfbc", "#ffe6c6"]      # dark .. light
CHALK = "#f2ead6"
RAIL = ["#e2ccac", "#d2bc9c", "#ead4b4"]


def hsh(*k):
    h = 2166136261
    for x in k:
        h = ((h ^ (int(x) & 0xffffffff)) * 16777619) & 0xffffffff
    h ^= h >> 15
    h = (h * 2246822519) & 0xffffffff
    h ^= h >> 13
    return (h & 0xffffff) / float(1 << 24)


def wood(*k):
    return WOODS[int(hsh(*k) * len(WOODS)) % len(WOODS)]


def barge(*k):
    return BARGE[int(hsh(*k) * len(BARGE)) % len(BARGE)]


def leaf(*k):
    return LEAFS[int(hsh(*k) * len(LEAFS)) % len(LEAFS)]


class CVox(Vox):
    """A Vox grid addressed in voxels counted from the compound's centre (x, y), z from the ground."""

    def __init__(self, nx, ny, nz, voxel, sx, sy, name="vox", seed=0):
        super().__init__(nx, ny, nz, voxel, origin=(sx, sy, 0), name=name, seed=seed)
        self.sx, self.sy = int(sx), int(sy)

    def _clip(self, x0, y0, z0, x1, y1, z1):
        return Vox._clip(self, x0 + self.sx, y0 + self.sy, z0, x1 + self.sx, y1 + self.sy, z1)

    def get(self, x, y, z):
        return Vox.get(self, x + self.sx, y + self.sy, z)

    def solid(self, x, y, z):
        return self.get(x, y, z) is not None

    def stamp(self, other, x, y, z, rot=0, overwrite=True):
        return Vox.stamp(self, other, x + self.sx, y + self.sy, z, rot, overwrite)

    def ellipsoid(self, cx, cy, cz, *a, **k):
        return Vox.ellipsoid(self, cx + self.sx, cy + self.sy, cz, *a, **k)

    def cgrid(self):
        X, Y, Z = self.grid()
        return X - self.sx, Y - self.sy, Z


# ---------------------------------------------------------------------------------------------------- pieces
# (copied from barracks.py and adapted: that script runs its own main() on import)

def gable(v, a0, a1, b0, b1, z, ridge="x", run=4, rise=3, bw0=4, bw1=4, seed=0):
    """A solid stepped gable roof. `a` runs along the ridge, `b` across it. The first bw0 / last bw1 voxels along the
    ridge are the barge boards: big wooden blocks stepping up the gable end. Returns the z of the top of the ridge."""
    def put(al, ah, bl, bh, zl, zh, mat, col=None):
        if ridge == "x":
            v.box(al, bl, zl, ah, bh, zh, mat, col)
        else:
            v.box(bl, al, zl, bh, ah, zh, mat, col)

    steps = int(np.ceil((b1 - b0) / 2.0 / run))
    t0, t1 = a0 + bw0, a1 - bw1
    for i in range(steps):
        lo, hi = b0 + i * run, b1 - i * run
        zl = z + i * rise
        put(t0, t1, lo, hi, zl, zl + rise, "roof")
        if i == 0:
            put(t0, t1, lo, hi, zl, zl + 1, "beam")
            put(t0, t1, lo, lo + 1, zl, zl + 2, "beam")
            put(t0, t1, hi - 1, hi, zl, zl + 2, "beam")
    top = z + steps * rise
    mid = (b0 + b1) // 2
    put(t0, t1, mid - 1, mid + 1, top, top + 2, "beam", "#e8d0b0")
    for end, (c0, c1) in enumerate(((a0, t0 + 1), (t1 - 1, a1))):
        if c1 - c0 <= 1:
            continue
        for i in range(steps):
            lo, hi = b0 + i * run, b1 - i * run
            zl = z + i * rise
            put(c0, c1, lo, min(lo + run + 1, mid), zl - 1, zl + rise + 1, "plank", barge(seed, end, i, 0))
            put(c0, c1, max(hi - run - 1, mid), hi, zl - 1, zl + rise + 1, "plank", barge(seed, end, i, 1))
        put(c0, c1, mid - 1, mid + 1, top - 2 * rise, top - 1, "plank", barge(seed, end, 98))
        put(c0, c1, mid - 2, mid + 2, top - 1, top + 3, "plank", barge(seed, end, 99))
    return top + 2


def gable_face(v, layer, b0, b1, z, ridge, run, rise, mat, color=None):
    """Dress the gable wall (the voxel layer just inside the barge boards) with a wall material."""
    steps = int(np.ceil((b1 - b0) / 2.0 / run))
    for i in range(steps):
        lo, hi = b0 + i * run + run + 1, b1 - i * run - run - 1
        if hi <= lo:
            break
        zl = z + i * rise
        if ridge == "x":
            v.box(layer, lo, zl, layer + 1, hi, zl + rise, mat, color)
        else:
            v.box(lo, layer, zl, hi, layer + 1, zl + rise, mat, color)


def window(v, axis, core, out, a0, z0, w=5, h=7, bars=True):
    """A glowing window in a wall. core: the wall's outermost core layer on `axis`, out: +1/-1 the way it faces."""
    def put(layer, al, ah, zl, zh, mat, col=None):
        if axis == "y":
            v.box(al, layer, zl, ah, layer + 1, zh, mat, col)
        else:
            v.box(layer, al, zl, layer + 1, ah, zh, mat, col)

    r, s = core + out, core + 2 * out
    put(r, a0 - 1, a0 + w + 1, z0 - 1, z0 + h + 1, None)
    put(core, a0, a0 + w, z0, z0 + h, "window")
    put(r, a0 - 1, a0, z0 - 1, z0 + h + 1, "beam", FRAME)
    put(r, a0 + w, a0 + w + 1, z0 - 1, z0 + h + 1, "beam", FRAME)
    put(r, a0 - 1, a0 + w + 1, z0 + h, z0 + h + 1, "beam", FRAME)
    put(r, a0 - 1, a0 + w + 1, z0 - 1, z0, "beam", FRAME)
    if bars:
        if w % 2:
            put(core, a0 + w // 2, a0 + w // 2 + 1, z0, z0 + h, "beam", FRAME)
        else:
            put(core, a0 + w // 2, a0 + w // 2 + 1, z0, z0 + h, "beam", FRAME)
        put(core, a0, a0 + w, z0 + h // 2, z0 + h // 2 + 1, "beam", FRAME)
    put(s, a0 - 2, a0 + w + 2, z0 - 1, z0, "beam")
    put(s, a0 - 1, a0 + w + 1, z0 + h, z0 + h + 1, "beam")


def paint_rows(g, rows, pal, x0, y, ztop, depth=1, mat="paint"):
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch in ". ":
                continue
            e = pal[ch]
            m, c = e if isinstance(e, tuple) else (mat, e)
            g.box(x0 + i, y, ztop - 1 - j, x0 + i + 1, y + depth, ztop - j, m, c)


def flantern(f, cx, cy, ztop, chain=2):
    """A hanging lantern in a 6.25 cm grid: 6 px wide, hook at ztop. Returns the z of its underside."""
    z = ztop - chain
    f.box(cx - 1, cy - 1, z, cx + 1, cy + 1, ztop, "metal")
    f.box(cx - 2, cy - 2, z - 1, cx + 2, cy + 2, z, "metal")
    f.box(cx - 3, cy - 3, z - 2, cx + 3, cy + 3, z - 1, "metal")
    zb = z - 8
    f.box(cx - 2, cy - 2, zb, cx + 2, cy + 2, z - 2, "glow", "lantern")
    for dx in (cx - 3, cx + 2):
        for dy in (cy - 3, cy + 2):
            f.box(dx, dy, zb, dx + 1, dy + 1, z - 2, "metal")
    f.box(cx - 3, cy - 3, zb - 1, cx + 3, cy + 3, zb, "metal")
    f.box(cx - 1, cy - 1, zb - 2, cx + 1, cy + 1, zb - 1, "metal")
    return zb - 2


def spear(g, x, y, z0, z1, axis="x"):
    g.box(x, y, z0, x + 1, y + 1, z1, "post", SHAFT)
    g.box(x, y, z1, x + 1, y + 1, z1 + 1, "gold")
    if axis == "x":
        g.box(x - 1, y, z1 + 1, x + 2, y + 1, z1 + 3, "paint", STEEL)
    else:
        g.box(x, y - 1, z1 + 1, x + 1, y + 2, z1 + 3, "paint", STEEL)
    g.box(x, y, z1 + 3, x + 1, y + 1, z1 + 5, "paint", STEEL)


def sword(g, x, y, z0, blade=13):
    g.box(x, y, z0, x + 1, y + 1, z0 + 1, "paint", STEEL)
    g.box(x, y, z0 + 1, x + 2, y + 1, z0 + blade, "paint", STEEL)
    g.box(x + 1, y, z0 + 2, x + 2, y + 1, z0 + blade, "paint", STEEL_DARK)
    g.box(x - 2, y, z0 + blade, x + 4, y + 1, z0 + blade + 1, "gold")
    g.box(x, y, z0 + blade + 1, x + 2, y + 1, z0 + blade + 5, "paint", "wood_dark")
    g.box(x - 1, y, z0 + blade + 5, x + 3, y + 1, z0 + blade + 7, "gold")


def arrows(g, x0, y0, z, n=5, seed=0):
    for k in range(n):
        x = x0 + int(hsh(seed, k, 1) * 6)
        y = y0 + int(hsh(seed, k, 2) * 6)
        h = 5 + int(hsh(seed, k, 3) * 4)
        g.box(x, y, z, x + 1, y + 1, z + h, "post", SHAFT)
        g.box(x, y, z + h, x + 1, y + 1, z + h + 2, "paint", "white" if k % 2 else "red")


def place(parts, x, y, z, rot=0):
    """Move a prop (a list of grids with their own offsets) to x, y, z metres, turned `rot` quarter turns."""
    for p in parts:
        ox, oy, oz = p.offset
        for _ in range(rot % 4):
            ox, oy = -oy, ox
        p.at(x + ox, y + oy, z + oz, p.rot + rot)
    return parts


def swords_rows(n=14):
    """Crossed swords, points up: S blade, s blade shade, G gold hilt."""
    g = [["."] * n for _ in range(n)]
    for mirror in (1, 0):
        def P(r, c, ch):
            if mirror:
                c = n - 1 - c
            if 0 <= r < n and 0 <= c < n:
                g[r][c] = ch
        for r in range(0, n - 4):
            P(r, r, "S")
            if r > 0:
                P(r, r - 1, "s")
            if r < n - 5:
                P(r, r + 1, "S")
        k = n - 4
        for d in (-2, -1, 0, 1, 2):
            P(k - d, k + d, "G")
        for (a, b) in ((1, 1), (2, 2), (3, 3), (2, 3), (3, 2)):
            P(k + a, k + b, "G")
    return ["".join(r) for r in g]


SWORDS_SMALL = [
    "S....S",
    ".S..S.",
    ".S..S.",
    "..SS..",
    "..SS..",
    ".G..G.",
    "GG..GG",
    "G....G",
]
EMBLEM_PAL = {"S": "#f1f1ea", "s": "#bfc3c8", "G": "gold", "T": "gold", "t": "gold_light"}


def make_banner(pattern, pal=EMBLEM_PAL, w=16, h=26, notch=5, rod=True, ey0=4, name="banner"):
    """Green banner with gold border, emblem and swallow-tail foot (6.25 cm voxels) in the XZ plane facing -Y; origin =
    middle of the top. Marked as hanging cloth (sways in the engine)."""
    ew = max(len(r) for r in pattern)
    ex0 = (w - ew) // 2
    inside = np.zeros((h, w), bool)
    for j in range(h):
        for i in range(w):
            k = j - (h - notch)
            cut = k >= 0 and abs(i - (w - 1) / 2.0) < (k + 1) * (w / 2.0 - 2) / notch
            inside[j, i] = not cut
    top = h + 2 if rod else h
    v = Vox(w + 2, 2, top, FINE, origin=((w + 2) / 2.0, 1, top), name=name)
    for j in range(h):
        for i in range(w):
            if not inside[j, i]:
                continue
            border = i == 0 or i == w - 1 or j == 0 or j == h - 1 or (j + 1 < h and not inside[j + 1, i]) \
                or (i > 0 and not inside[j, i - 1]) or (i + 1 < w and not inside[j, i + 1])
            col = "gold" if border else "banner"
            pj, pi = j - ey0, i - ex0
            if not border and 0 <= pj < len(pattern) and 0 <= pi < len(pattern[pj]) and pattern[pj][pi] not in ". ":
                col = pal[pattern[pj][pi]]
            elif not border and (i * 7 + j * 3) % 11 == 0:
                col = "banner_dark"
            elif not border and (i * 5 + j * 9) % 13 == 0:
                col = "banner_light"
            z = h - 1 - j
            v.box(i + 1, 0, z, i + 2, 1, z + 1, "paint", col)
    if rod:
        v.box(0, 0, h, w + 2, 2, h + 2, "beam")
        v.box(0, 0, h, 1, 2, h + 2, "gold")
        v.box(w + 1, 0, h, w + 2, 2, h + 2, "gold")
    v.hang()
    return v


def rack_parts(n=5):
    """The weapon rack: 1.5 m wide, spears to 1.65 m. Origin: centre of its base; the weapons face -Y."""
    b = Vox(12, 6, 12, VOX, origin=(6, 3, 0), name="rack")
    for x in (0, 10):
        b.box(x, 0, 0, x + 2, 6, 1, "beam")
        b.box(x, 1, 1, x + 2, 5, 2, "beam", WOODS[3])
        b.box(x, 2, 1, x + 2, 4, 11, "post")
        b.box(x, 2, 11, x + 2, 4, 12, "beam", WOODS[2])
    b.box(1, 1, 2, 11, 2, 4, "beam", WOODS[1])
    b.box(1, 3, 9, 11, 4, 11, "beam", WOODS[1])
    b.box(2, 2, 0, 10, 3, 1, "plank")
    f = Vox(24, 12, 32, FINE, origin=(12, 6, 0), name="rack_fine")
    xs = [5, 9, 12, 15, 19][:n] if n == 5 else list(np.linspace(5, 19, n).round().astype(int))
    for k, x in enumerate(xs):
        if k % 2 == 0:
            spear(f, x, 5, 2, 22 + (k % 3))
        else:
            sword(f, x - 1, 5, 2, blade=12)
    return [b, f]


def m(vox):
    """Voxels (from the centre) -> metres."""
    return vox * VOX


# ---------------------------------------------------------------------------------------------------- the compound

def build_yard():
    rng = np.random.default_rng(21)
    # the main grid: x -9.75 .. 9.75 m, y -10 .. 9 m, z 0 .. 8.5 m
    v = CVox(156, 152, 80, VOX, 78, 80, "yard", seed=7)
    # small things around the hall (6.25 cm): x -9.5 .. 9.5 m, y 0 .. 8.75 m, z 0 .. 7 m
    f = CVox(304, 140, 124, FINE, 152, 0, "yard_fine", seed=3)
    # small things on the gate: x -3 .. 3 m, y -9 .. -7.25 m
    g = CVox(96, 28, 64, FINE, 48, 144, "gate_fine", seed=5)
    # the yard's dirt floor in 25 cm cells: one cell from z -0.125 to 0.125 m
    d = CVox(76, 46, 1, 0.25, 38, 34, "yard_dirt", seed=9).at(0, 0, -0.125)
    extra = []

    def P(axis, layer, a0, a1, z0, z1, mat, col=None):
        """A box on a wall face: axis 'y' -> x a0..a1 at y = layer; axis 'x' -> y a0..a1 at x = layer."""
        if axis == "y":
            v.box(a0, layer, z0, a1, layer + 1, z1, mat, col)
        else:
            v.box(layer, a0, z0, layer + 1, a1, z1, mat, col)

    # ================================================================ the hall
    v.box(HX0 - 2, HY0 - 2, 0, HX1 + 1, HY1 + 2, 4, "stone")                      # footing of big blocks
    v.box(HX0, HY0, 0, HX1, HY1, E, "brick")                                      # walls: small grey stones
    v.box(HX0, HY0, 0, -44, HY1, E, "stone")                                      # the west end is big stone blocks
    v.box(BX0, BY0, 0, BX1, HY0, E, "brick")                                      # the bay's walls

    def dress(axis, core, out, a0, a1, posts, base=7, plate=True):
        """Timber dressing on a wall face: a stone base course, a sill beam, a top plate and posts, all proud."""
        r = core + out
        P(axis, r, a0, a1, 0, base, "stone")
        P(axis, r, a0, a1, base, base + 1, "beam", WOODS[3])
        if plate:
            P(axis, r, a0, a1, E - 3, E, "beam", wood(core, a0))
        for p in posts:
            P(axis, r, p, p + 3, base, E, "post", wood(core, p, 1))
            P(axis, r + out, p, p + 3, base - 1, E, "post", wood(core, p, 1))
            P(axis, r + out, p - 1, p + 4, base - 2, base - 1, "beam", WOODS[3])    # a little cap on the base

    dress("y", HY0, -1, HX0, BX0, (HX0 - 1, -46, -27))                            # front, west of the bay
    dress("y", HY0, -1, BX1, HX1, (41,))                                          # front, east of the bay
    dress("y", HY1 - 1, 1, HX0, HX1, (HX0 - 1, -40, -14, 12, 41))                 # back
    dress("x", HX0, -1, HY0, HY1, (HY0 - 1, 42, HY1 - 2))                         # west end
    dress("x", HX1 - 1, 1, HY0, HY1, ())                                          # east end (inside the shed)
    dress("x", BX0, -1, BY0, HY0, (), plate=False)                                # the bay's sides
    dress("x", BX1 - 1, 1, BY0, HY0, (), plate=False)
    # the west end's stone wall: no proud timber course between the posts, just the stones
    v.box(HX0 - 1, HY0, 8, HX0, HY1, E - 3, None)
    v.box(HX0 - 1, HY0, 7, HX0, HY1, 8, "stone")
    v.box(-63, HY0 - 1, 7, -46, HY0, 8, "stone")

    # windows (glowing), with flower boxes under the front ones
    window(v, "y", HY0, -1, -59, 10, w=6, h=8)                                     # west front (stone)
    window(v, "y", HY0, -1, -38, 11, w=5, h=6)                                     # under the awning
    window(v, "y", HY0, -1, -22, 10, w=5, h=8)                                     # by the bay
    window(v, "y", HY0, -1, 30, 10, w=6, h=8)                                      # east front
    for a0 in (-56, -30, -4, 24):
        window(v, "y", HY1 - 1, 1, a0, 10, w=5, h=8)
    window(v, "x", HX0, -1, 32, 10, w=5, h=8)
    window(v, "x", HX0, -1, 50, 10, w=5, h=8)

    # ---- the roofs: the hall's (ridge along X), then the cross gable over the bay (ridge along Y) cut into it
    gable(v, HX0 - 4, HX1 + 4, HY0 - 4, HY1 + 4, E, "x", 4, RISE, 4, 4, seed=1)
    gable_face(v, HX0, HY0 - 4, HY1 + 4, E, "x", 4, RISE, "brick")
    gable_face(v, HX1 - 1, HY0 - 4, HY1 + 4, E, "x", 4, RISE, "brick")
    window(v, "x", HX0, -1, 41, 31, w=4, h=6)                                     # a small window in the west gable
    v.box(HX0 - 2, HY0 - 3, E - 1, HX0, HY1 + 3, E + 1, "beam")                    # tie beams under the gables
    v.box(HX1, HY0 - 3, E - 1, HX1 + 2, HY1 + 3, E + 1, "beam")
    top = gable(v, BY0 - 4, 50, BX0 - 4, BX1 + 4, E, "y", 4, CRISE, 4, 4, seed=2)
    gable_face(v, BY0, BX0 - 4, BX1 + 4, E, "y", 4, CRISE, "plank", "#c8a07a")
    gable_face(v, 45, BX0 - 4, BX1 + 4, E, "y", 4, CRISE, "brick")
    v.box(BX0 - 2, BY0 - 2, E, BX1 + 2, BY0, E + 2, "beam", WOODS[2])               # tie beam at the gable's foot
    for x in (-6, 14):                                                              # two studs of the gable frame
        v.box(x, BY0 - 1, E + 2, x + 2, BY0, E + 10, "post", WOODS[3])
    for x in range(HX0, HX1, 12):                                                   # rafter ends under the eaves
        if BX0 - 6 < x < BX1 + 4:
            continue
        v.box(x, HY0 - 3, E - 2, x + 2, HY0, E, "beam", WOODS[3])
        v.box(x, HY1, E - 2, x + 2, HY1 + 3, E, "beam", WOODS[3])

    # metal studs on the barge blocks (front of the cross gable, west end of the hall)
    for i in range(6):
        zf = 2 * (E + CRISE * i) + 1
        lo, hi = BX0 - 4 + 4 * i, BX1 + 4 - 4 * i
        for xf in (2 * lo + 3, 2 * hi - 5):
            f.box(xf, 2 * (BY0 - 4) - 1, zf, xf + 2, 2 * (BY0 - 4), zf + 2, "metal")
    for i in range(6):
        zf = 2 * (E + RISE * i) + 1
        lo, hi = HY0 - 4 + 4 * i, HY1 + 4 - 4 * i
        for yf in (2 * lo + 3, 2 * hi - 5):
            f.box(2 * (HX0 - 4) - 1, yf, zf, 2 * (HX0 - 4), yf + 2, zf + 2, "metal")

    # ---- chimney (west, behind the ridge)
    v.box(-58, 46, E, -49, 55, 60, "stone")
    v.box(-59, 45, 60, -48, 56, 63, "stone", "#f0e6d8")
    v.box(-57, 47, 62, -50, 54, 63, "paint", "#1c1816")
    v.chunky("stone", cell=2, p=0.25, seed=6, region=(-60, 44, 44, -47, 57, 60))

    # ================================================================ the bay
    for x in range(-16, 24, 4):                                                     # stone landing in front: slabs
        for y in range(4, BY0, 4):
            v.box(x, y, 0, x + 4, y + 4, 2, "stone", ["#ffffff", "#ece6dc", "#f6f0e6"][int(hsh(x, y, 1) * 3)])
    v.clear(OX0, BY0 - 2, 2, OX1, 40, OZ1)                                          # the open bay, 3.5 m deep
    v.box(OX0, BY0, 1, OX1, 40, 2, "plank", WOODS[1])                                # plank floor
    v.box(OX0, 40, 2, OX1, 41, OZ1, "plank", "#ffe6b8")                             # back wall
    v.box(OX0 - 1, BY0, 2, OX0, 40, OZ1, "plank", "#f0d0a0")                        # side walls
    v.box(OX1, BY0, 2, OX1 + 1, 40, OZ1, "plank", "#f0d0a0")
    for y in (18, 26, 34):                                                          # ceiling beams
        v.box(OX0, y, OZ1 - 1, OX1, y + 2, OZ1, "beam", WOODS[3])
    v.box(OX0, 38, 8, OX1, 39, 9, "beam", WOODS[1])                                  # a rail along the back wall
    for x in (-15, 18):                                                             # the big posts
        v.box(x, BY0 - 2, 0, x + 5, BY0 + 1, E, "post", wood(x, 3))
        v.box(x - 1, BY0 - 3, 0, x + 6, BY0 + 2, 3, "stone")
    v.box(-15, BY0 - 2, OZ1, 23, BY0 + 1, E, "beam", WOODS[2])                     # lintel
    for k in range(3):                                                              # braces in the top corners
        v.box(OX0 + k, BY0 - 2, OZ1 - 3 + k, OX0 + k + 1, BY0, OZ1 - 2 + k, "beam", WOODS[3])
        v.box(OX1 - 1 - k, BY0 - 2, OZ1 - 3 + k, OX1 - k, BY0, OZ1 - 2 + k, "beam", WOODS[3])
    for cx in (-6, 8, 22):                                                          # gold plates on the lintel
        f.box(cx - 2, 2 * BY0 - 5, 2 * OZ1 + 1, cx + 2, 2 * BY0 - 4, 2 * OZ1 + 3, "gold")
    extra += place(rack_parts(), m(8), m(37.5), m(2))                               # weapon rack on the back wall
    v.stamp(K.barrel(), -6, 35, 2)
    v.stamp(K.crate(6), -6, 28, 2)
    v.box(-9, 25, 8, -3, 31, 9, "plank", WOODS[1])
    arrows(f, -16, 52, 18, n=6, seed=3)
    flantern(f, -12, 62, 2 * OZ1, chain=1)                                          # the lamp that lights the bay
    # lanterns on iron arms beside the bay and by the east window
    for (cx, side) in ((-34, -1), (54, 1)):
        ax0 = -30 if side < 0 else 46
        f.box(min(ax0, cx) - 1, 2 * BY0 - 4, 42, max(ax0, cx) + 1, 2 * BY0 - 2, 44, "metal")
        flantern(f, cx, 2 * BY0 - 3, 42)
    f.box(54 - 1, 2 * BY0 - 4, 42, 54 + 1, 2 * HY0, 44, "metal")                    # (its arm reaches the wall)

    # ---- the big banner over the bay and the flag on the peak
    v.box(-2, BY0 - 3, 40, -1, BY0 - 1, 42, "beam")
    v.box(9, BY0 - 3, 40, 10, BY0 - 1, 42, "beam")
    extra.append(make_banner(swords_rows(14), w=20, h=30, notch=6, ey0=5).at(m(4), m(BY0 - 1.75), m(41.5)))
    v.box(3, BY0 - 3, top - 4, 5, BY0 - 1, top + 16, "post")
    v.box(2, BY0 - 4, top - 4, 6, BY0, top - 1, "beam", WOODS[3])
    v.box(2, BY0 - 4, top + 16, 6, BY0, top + 18, "gold")
    extra.append(K.flag("swords", w=24, h=14).at(m(5), m(BY0 - 2), m(top + 8.5)))

    # ================================================================ the awning (west of the bay)
    AX0, AX1 = -45, -27
    v.box(AX0, HY0 - 1, 21, AX1, HY0, 23, "beam", WOODS[3])                          # wall rail
    for k, (ya, yb) in enumerate(((19, 23), (15, 19), (12, 15))):
        v.box(AX0, ya, 22 - k, AX1, yb, 23 - k, "wool", CANVAS[k % 3])
    for x in (AX0, AX1 - 2):
        v.box(x, 12, 0, x + 2, 14, 20, "post")
        v.box(x - 1, 11, 0, x + 3, 15, 2, "stone")
    v.box(AX0, 12, 19, AX1, 13, 20, "beam")                                          # front beam
    scallop = [0, 2, 3, 3, 2, 0]
    for i in range(2 * AX0, 2 * AX1):
        dz = scallop[(i - 2 * AX0) % 6]
        f.box(i, 22, 34 - dz + 1, i + 1, 24, 40, "wool", CANVAS[0])
        f.box(i, 22, 34 - dz, i + 1, 24, 34 - dz + 1, "paint", "gold")
    v.box(-41, 15, 5, -32, 19, 6, "plank")                                           # table with mugs
    for (x, y) in ((-41, 15), (-33, 15), (-41, 18), (-33, 18)):
        v.box(x, y, 0, x + 1, y + 1, 5, "post")
    v.box(-40, 17, 2, -33, 18, 3, "beam", WOODS[3])
    for (x, y) in ((-79, 32), (-72, 34), (-68, 31)):
        f.box(x, y, 12, x + 2, y + 2, 15, "paint", STEEL)
        f.box(x, y, 14, x + 2, y + 2, 15, "paint", STEEL_DARK)
        f.box(x + 2, y, 13, x + 3, y + 1, 14, "paint", STEEL_DARK)
    f.box(-76, 35, 12, -72, 38, 13, "plank", WOODS[1])
    f.box(-75, 36, 13, -73, 37, 14, "paint", "#d8a850")
    v.box(-40, 12, 3, -33, 14, 4, "plank", WOODS[1])                                 # bench
    v.box(-40, 12, 0, -39, 14, 3, "post")
    v.box(-34, 12, 0, -33, 14, 3, "post")
    v.stamp(K.crate(6), 33, 18, 0)                                                   # crates by the east front wall
    v.stamp(K.crate(6), 39, 18, 0)
    v.stamp(K.crate(4), 36, 18, 6)
    v.stamp(K.crate(5), -19, 18, 0)                                                  # and a box under the west window
    v.stamp(K.crate(6), -49, 15, 0)                                                  # a crate by the corner
    v.stamp(K.crate(4), -48, 15, 6)

    # small banner on the post at the west end of the awning
    v.box(-48, HY0 - 4, 17, -43, HY0 - 3, 18, "beam", WOODS[2])
    extra.append(make_banner(SWORDS_SMALL, w=10, h=16, notch=3, rod=True, ey0=3).at(m(-44.5), m(HY0 - 4.5), m(18)))

    # ================================================================ the shed (east)
    v.box(HX1, 20, 0, SX1, 66, 1, "cobble")
    v.box(HX1, 60, 0, SX1 - 4, 62, 4, "stone")                                       # back wall: stone foot, planks
    for k in range(8):
        x0 = HX1 + 4 * k
        zt = 24 - k
        v.box(x0, 20, zt - 2, x0 + 4, 66, zt - 1, "plank", WOODS[k % 6])
        v.box(x0, 20, zt - 1, x0 + 4, 66, zt, "roof")
        for (ya, yb) in ((20, 22), (64, 66)):
            v.box(x0, ya, zt - 2, x0 + 4, yb, zt + 1, "plank", barge(31, k, ya))
        if x0 < SX1 - 4:
            v.box(x0, 60, 4, x0 + 4, 62, zt - 2, "plank", wood(32, k))
    v.box(SX1 + 1, 20, 15, SX1 + 2, 66, 17, "beam")
    for y in (24, 42, 59):
        v.box(SX1 - 4, y, 0, SX1, y + 4, 16, "post")
        v.box(SX1 - 5, y - 1, 0, SX1 + 1, y + 5, 3, "stone")
    v.box(SX1 - 4, 22, 15, SX1, 64, 17, "beam", WOODS[3])
    for k in range(3):
        v.box(SX1 - 5 - k, 24, 13 + k, SX1 - 4 - k, 28, 14 + k, "beam", WOODS[3])
    for z in (4, 9):
        v.box(SX1 - 3, 28, z, SX1 - 1, 59, z + 1, "beam", WOODS[1])                   # rails on the east side
    for (x, y, z) in ((50, 30, 1), (56, 30, 1), (53, 31, 7), (50, 36, 1), (62, 34, 1)):
        v.stamp(K.crate(6), x, y, z)
    v.stamp(K.barrel(), 62, 52, 1)
    v.stamp(K.barrel(), 56, 54, 1)
    v.stamp(K.barrel(), 66, 47, 1)
    v.box(48, 44, 1, 54, 50, 6, "plank", WOODS[2])                                    # arrow crate
    v.box(48, 44, 1, 54, 50, 6, "beam")
    v.box(49, 45, 1, 53, 49, 6, "plank", WOODS[2])
    v.clear(49, 45, 5, 53, 49, 6)
    arrows(f, 98, 90, 10, n=7, seed=5)
    v.box(58, 42, 1, 64, 46, 5, "hay")
    v.box(SX1 - 3, 23, 13, SX1 - 1, 24, 14, "beam", WOODS[2])
    extra.append(make_banner(SWORDS_SMALL, w=10, h=16, notch=3, rod=True, ey0=3).at(m(SX1 - 2), m(23.25), m(14)))

    # ================================================================ moss, vines, flowers on the hall
    X, Y, Z = v.cgrid()
    roof_top = v.exposed("+z") & v.mask("roof")
    n = V.noise3(v.n, 7, 5)
    west_front = (X < BX0 - 4) & (Y < 40)
    v.where(roof_top & (n > 0.62), "moss")
    v.where(roof_top & west_front & (n > 0.50), "moss")
    v.where(roof_top & west_front & (Y < 26) & (X > -64) & (n > 0.36), "moss")
    v.where(roof_top & (X > HX1) & (n > 0.55), "moss")
    v.scatter("roof", "moss", p=0.04, seed=4, direction="+z")
    v.scatter("stone", "mossy_stone", p=0.10, seed=8, direction="+z", region=(-78, 0, 0, 78, 72, 68))
    v.scatter("stone", "mossy_stone", p=0.05, seed=9, region=(-78, 0, 0, 78, 72, 4))

    def hang(x, y, z, n_max, p=0.7):
        if rng.random() > p:
            return
        for k in range(int(rng.integers(1, n_max + 1))):
            if v.solid(x, y, z - k):
                break
            v.set(x, y, z - k, "leaves", LEAFS[int(rng.integers(len(LEAFS)))])

    for x in range(HX0 - 2, BX0 - 4):                                                # hanging from the west front eave
        lush = 6 if (-60 < x < -46 or -30 < x < -19) else 3
        hang(x, HY0 - 5, E + 2, lush, 0.85 if lush == 6 else 0.5)
        if rng.random() < 0.55:
            v.set(x, HY0 - 4, E + 3, "leaves", LEAFS[int(rng.integers(len(LEAFS)))])
    for y in range(BY0 - 3, HY0 - 4):                                                # down the cross gable's west eave
        hang(BX0 - 5, y, E + 1, 4, 0.5)
    for x in range(-10, 30):                                                         # the back eave
        hang(x, HY1 + 4, E + 2, 4, 0.4)
    for z in range(0, 20):                                                           # ivy on the west front corner
        for y in range(HY0 - 2, HY0 + 8):
            if rng.random() < 0.55 - 0.022 * z and not v.solid(HX0 - 3, y, z) and v.solid(HX0 - 2, y, z):
                v.set(HX0 - 3, y, z, "leaves", LEAFS[int(rng.integers(len(LEAFS)))])
    for z in range(E + 12, 56):                                                      # and up the chimney
        for x in range(-58, -49):
            if rng.random() < 0.5 - 0.03 * (z - E - 12) and not v.solid(x, 45, z) and v.solid(x, 46, z):
                v.set(x, 45, z, "leaves", LEAFS[int(rng.integers(len(LEAFS)))])

    def flower_box(axis, layer, out, a0, w, z, seed):
        """A planter under a window: layer = the sill's layer, it hangs one voxel further out."""
        cols = ["flower_white", "flower_yellow", "flower_pink", "flower_orange", "red"]
        for a in range(a0 - 1, a0 + w + 1):
            for dd in (0, out):
                x, y = (a, layer + dd) if axis == "y" else (layer + dd, a)
                v.box(x, y, z - 2, x + 1, y + 1, z, "plank", WOODS[3])
                if dd == out:
                    v.set(x, y, z, "leaves", leaf(seed, a))
                    if hsh(seed, a, 7) < 0.8:
                        fx, fy = 2 * x + int(hsh(seed, a, 1) * 2), 2 * y + int(hsh(seed, a, 2) * 2)
                        c = cols[int(hsh(seed, a, 3) * len(cols))]
                        f.box(fx, fy, 2 * z + 2, fx + 1, fy + 1, 2 * z + 4, "paint", c)
                        f.box(fx - (1 if axis == "y" else 0), fy - (1 if axis == "x" else 0), 2 * z + 3,
                              fx + (2 if axis == "y" else 1), fy + (2 if axis == "x" else 1), 2 * z + 4, "paint", c)

    flower_box("y", HY0 - 2, -1, -59, 6, 9, 1)
    flower_box("y", HY0 - 2, -1, -22, 5, 9, 2)
    flower_box("y", HY0 - 2, -1, 30, 6, 9, 3)
    flower_box("x", HX0 - 2, -1, 32, 5, 9, 4)

    for (x, y, z) in np.argwhere(v.mask("moss") & v.exposed("+z")):                  # little white flowers on the moss
        x, y = x - v.sx, y - v.sy
        if y < HY0 + 4 and x < BX0 - 4 and rng.random() < 0.18:
            fx, fy = 2 * x + int(rng.integers(2)), 2 * y + int(rng.integers(2))
            f.box(fx, fy, 2 * z + 2, fx + 1, fy + 1, 2 * z + 3, "leaves")
            f.box(fx - 1, fy, 2 * z + 3, fx + 2, fy + 1, 2 * z + 4, "paint", "flower_white")
            f.box(fx, fy - 1, 2 * z + 3, fx + 1, fy + 2, 2 * z + 4, "paint", "flower_white")
            f.box(fx, fy, 2 * z + 3, fx + 1, fy + 1, 2 * z + 5, "paint", "flower_yellow")

    # stone texture: chunky blocks and warm tints (the hall's stones only, before the yard's are added)
    v.chunky("stone", p=0.3, seed=2, region=(-78, HY0 - 4, 0, 78, 72, E + 40))
    v.tint("stone", "#e9e2d6", p=0.3, seed=4, cell=4)
    v.tint("stone", "#fff4e2", p=0.2, seed=9, cell=4)

    # ================================================================ the yard
    dn = V.noise3((76, 46, 1), 7, seed=41)[:, :, 0]

    def dirt_col(xm, ym):
        """Soft patches of lighter and darker dirt (smooth noise over 25 cm cells, a little speckle)."""
        i, j = int(math.floor(xm / 0.25)) + 38, int(math.floor(ym / 0.25)) + 34
        lvl = (dn[min(max(i, 0), 75), min(max(j, 0), 45)] - 0.32) / 0.36 * len(DIRT)
        k = hsh(i, j, 77)
        lvl += -1 if k < 0.06 else (1 if k > 0.95 else 0)
        return DIRT[int(min(max(lvl, 0), len(DIRT) - 1))]

    for i in range(-37, 37):
        for j in range(-34, 12):
            xm, ym = (i + 0.5) * 0.25, (j + 0.5) * 0.25
            if (i in (-37, 36) or j == -34) and hsh(i, j, 5) < 0.35:
                continue                                                             # a ragged edge under the fence
            d.set(i, j, 0, "dirt", dirt_col(xm, ym))
    for i in range(-37, 37):                                                         # a few gravel cells
        for j in range(-34, 12):
            if hsh(i, j, 9) < 0.006 and d.solid(i, j, 0):
                d.set(i, j, 0, "gravel", "#f6dcbc")

    # the crossed swords marked in the dirt (in 12.5 cm cells: a hole in the coarse floor, filled finer)
    MCX, MCY = 4, -22
    d.clear((MCX - 16) // 2, (MCY - 12) // 2, 0, (MCX + 16) // 2, (MCY + 12) // 2, 1)
    for x in range(MCX - 16, MCX + 16):
        for y in range(MCY - 12, MCY + 12):
            v.set(x, y, 0, "dirt", dirt_col((x + 0.5) * VOX, (y + 0.5) * VOX))
    for sgn in (1, -1):
        p0 = np.array([MCX - sgn * 9.5, MCY - 9.0])
        p1 = np.array([MCX + sgn * 10.0, MCY + 9.5])
        L = float(np.linalg.norm(p1 - p0))
        u = (p1 - p0) / L
        nrm = np.array([-u[1], u[0]])
        for x in range(MCX - 16, MCX + 16):
            for y in range(MCY - 12, MCY + 12):
                q = np.array([x + 0.5, y + 0.5]) - p0
                s, t = float(q @ u), abs(float(q @ nrm))
                on = (s >= -0.3 and s < 1.6 and t < 1.2) or (1.6 <= s < 5.0 and t < 0.6) \
                    or (5.0 <= s < 6.6 and t < 3.6) or (6.6 <= s < L - 2.5 and t < 1.05) \
                    or (L - 2.5 <= s < L + 0.3 and t < 1.05 * (L + 0.3 - s) / 2.8)
                if on and hsh(x, y, 3) > 0.06:
                    v.set(x, y, 0, "paint", CHALK)

    # pebbles and tufts of grass on the dirt
    for k in range(36):
        x = int(rng.integers(-70, 70))
        y = int(rng.integers(-64, 20))
        if k % 3 and abs(abs(x) - 70) > 8 and abs(y + 64) > 8:
            continue                                                                 # most of them near the fence
        if abs(x - MCX) < 17 and abs(y - MCY) < 13:
            continue
        if hsh(k, 1) < 0.6:
            v.set(x, y, 1, "stone", "#e0d8cc")
            if hsh(k, 2) < 0.3:
                v.set(x + 1, y, 1, "stone", "#d4ccc0")
        else:
            v.set(x, y, 1, "leaves", leaf(k))

    # ---- fence: chunky posts with pale caps and two thick rails
    def post(x, y, h=9):
        v.box(x - 2, y - 2, 0, x + 2, y + 2, h - 1, "post", WOODS[1])
        v.box(x - 2, y - 2, h - 1, x + 2, y + 2, h, "post", WOODS[4])

    def rails_x(x0, x1, y):
        v.box(x0, y - 1, 2, x1, y + 1, 4, "plank", RAIL[1])
        v.box(x0, y - 1, 5, x1, y + 1, 8, "plank", RAIL[0])

    def rails_y(y0, y1, x):
        v.box(x - 1, y0, 2, x + 1, y1, 4, "plank", RAIL[1])
        v.box(x - 1, y0, 5, x + 1, y1, 8, "plank", RAIL[0])

    rails_x(-FX, -GX - 5, FY)
    rails_x(GX + 5, FX, FY)
    rails_y(FY, HY0 - 2, -FX)
    rails_y(FY, 24, FX)
    v.box(-FX, HY0 - 3, 2, HX0 - 2, HY0 - 1, 4, "plank", RAIL[1])                     # the west fence meets the hall
    v.box(-FX, HY0 - 3, 5, HX0 - 2, HY0 - 1, 8, "plank", RAIL[0])
    for x in (-60, -48, -36, -24, 24, 36, 48, 60):
        post(x, FY)
    for y in (-53, -40, -27, -14, -1, 12):
        post(-FX, y)
        post(FX, y)
    post(-FX, HY0 - 2, 10)
    # stone-footed lantern posts at the front corners
    for cx in (-FX, FX):
        v.box(cx - 3, FY - 3, 0, cx + 4, FY + 4, 4, "stone")
        v.box(cx - 2, FY - 2, 4, cx + 3, FY + 3, 10, "stone")
        v.box(cx - 3, FY - 3, 10, cx + 4, FY + 4, 11, "beam", WOODS[3])
        K.lantern(v, cx + 1, FY + 1, 11, 4)

    # ---- the gate: two stout posts on stone feet, a beam across, braces, a banner and two hanging lanterns
    for x0 in (-GX - 5, GX):
        v.box(x0 - 1, FY - 3, 0, x0 + 6, FY + 4, 6, "stone")
        v.box(x0, FY - 2, 6, x0 + 5, FY + 3, 29, "post", WOODS[1])
        v.box(x0, FY - 2, 29, x0 + 5, FY + 3, 31, "post", WOODS[4])
        v.box(x0 + 1, FY - 1, 31, x0 + 4, FY + 2, 32, "post", WOODS[2])
    v.box(-GX - 9, FY - 2, 25, GX + 9, FY + 2, 29, "beam", WOODS[2])
    for xe in (-GX - 9, GX + 7):
        v.box(xe, FY - 2, 24, xe + 2, FY + 2, 29, "beam", WOODS[3])
    for k in range(3):
        v.box(-GX + k, FY - 1, 22 + k, -GX + k + 1, FY + 1, 23 + k, "beam", WOODS[3])
        v.box(GX - 1 - k, FY - 1, 22 + k, GX - k, FY + 1, 23 + k, "beam", WOODS[3])
    v.chunky("stone", cell=2, p=0.3, seed=11, region=(-78, -80, 0, 78, -50, 12))
    for (cx, side) in ((-2 * GX - 18, -1), (2 * GX + 18, 1)):
        g.box(min(cx, side * (2 * GX + 10)) - 1, 2 * FY - 1, 46, max(cx, side * (2 * GX + 10)) + 1, 2 * FY + 1, 48, "metal")
        flantern(g, cx, 2 * FY, 46, chain=3)
    v.box(-4, FY - 3, 24, -3, FY - 2, 25, "beam")
    v.box(3, FY - 3, 24, 4, FY - 2, 25, "beam")
    extra.append(make_banner(SWORDS_SMALL, w=12, h=18, notch=4, rod=True, ey0=4).at(0, m(FY - 2.5), m(25)))

    # ---- the cobble path out of the gate
    for row, y in enumerate(range(-80, FY + 4, 2)):
        sh = 1 if row % 2 else 0
        for x in range(-10 + sh, 10, 2):
            if (x < -8 or x > 7) and hsh(x, y, 4) < 0.5:
                continue
            if y < -76 and hsh(x, y, 6) < 0.25 * (-75 - y):
                continue
            col = ["#ffffff", "#ece4d8", "#f8f0e4", "#e0d8cc", "#d4ccc0"][int(hsh(x, y, 2) * 5)]
            v.box(max(x, -10), y, 0, min(x + 2, 10), y + 2, 1, "cobble", col)
    v.scatter("cobble", "gravel", p=0.08, seed=3, region=(-12, -80, 0, 12, FY + 3, 1))

    # grass tufts along the fence's foot
    for k in range(60):
        side = k % 3
        if side == 0:
            x, y = int(rng.integers(-FX + 3, FX - 3)), FY + int(rng.integers(2, 4)) * (1 if hsh(k, 3) < 0.5 else -1)
        else:
            x, y = (-FX if side == 1 else FX) + int(rng.integers(2, 4)) * (1 if hsh(k, 4) < 0.5 else -1), int(rng.integers(FY + 4, 20))
        if abs(x) < GX + 7 and y < FY + 5:
            continue
        if not v.solid(x, y, 1):
            v.set(x, y, 1, "leaves", leaf(k, 9))
            if hsh(k, 5) < 0.4 and not v.solid(x, y, 2):
                v.set(x, y, 2, "leaves", leaf(k, 8))

    # wherever the fine grid has something on the ground inside the yard, the coarse dirt cell gives way to fine dirt,
    # so no two faces lie in the same plane at the floor's top (z = 0.125)
    for i in range(-38, 38):
        for j in range(-34, 12):
            if not d.solid(i, j, 0):
                continue
            cells = [(2 * i + a, 2 * j + b) for a in (0, 1) for b in (0, 1)]
            if any(v.solid(x, y, 0) for (x, y) in cells):
                mat, col = d.get(i, j, 0), tuple(int(c) for c in d.c[i + d.sx, j + d.sy, 0])
                d.clear(i, j, 0, i + 1, j + 1, 1)
                for (x, y) in cells:
                    if not v.solid(x, y, 0):
                        v.set(x, y, 0, mat, col)

    ob = V.join([v, f, g, d] + extra, "SM_BarracksYard")
    drop_bottom(ob)
    return ob


# ---------------------------------------------------------------------------------------------------- props, cleanup

DUMMIES = [((3.75, -1.75), -15.0), ((5.75, -3.5), -20.0), ((7.0, -5.75), -28.0)]


def props():
    return [{"mesh": "SM_TrainingDummy", "pos": [x, y, 0.125], "yaw": yaw} for ((x, y), yaw) in DUMMIES]


def drop_bottom(ob):
    """Delete the faces that look straight down from the ground plane (nobody ever sees them)."""
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.normal_update()
    kill = [fc for fc in bm.faces if fc.normal.z < -0.9 and max(p.co.z for p in fc.verts) <= 1e-4]
    bmesh.ops.delete(bm, geom=kill, context="FACES")
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()
    ob["voxel_faces"] = len(ob.data.polygons) // 2


def report(ob):
    co = np.zeros(len(ob.data.vertices) * 3, np.float32)
    ob.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    lo, hi = co.min(axis=0), co.max(axis=0)
    print("ASSET %s faces=%d size=%.3f x %.3f x %.3f  min=(%.3f, %.3f, %.3f) max=(%.3f, %.3f, %.3f)" % (
        ob.name, ob["voxel_faces"], hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2], lo[0], lo[1], lo[2], hi[0], hi[1], hi[2]))


# ---------------------------------------------------------------------------------------------------- previews

def import_gltf(name):
    import bpy
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(V.MESHES, name + ".gltf"))
    obs = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    for ob in obs:
        if ob.data.color_attributes and ob.data.color_attributes[0].name != "Col":
            ob.data.color_attributes[0].name = "Col"            # the preview materials read "Col" (shared with the yard)
        for i, mt in enumerate(ob.data.materials):
            if mt is None:
                continue
            slot = mt.name.split(".")[0]
            slot = slot[4:] if slot.startswith("Vox_") else slot
            if not mt.get("vox_preview"):
                mt.name = "imported_" + mt.name
            pm = V.material(slot)
            pm["vox_preview"] = True
            ob.data.materials[i] = pm
    return obs


def add_dummies():
    from mathutils import Matrix
    for p in props():
        for ob in import_gltf(p["mesh"]):
            ob.matrix_world = Matrix.Translation(p["pos"]) @ Matrix.Rotation(math.radians(p["yaw"]), 4, "Z") @ ob.matrix_world


VIEWS = {
    "ref": dict(target=(0.4, 0.2, 1.6), az=-35, el=35, dist=46, lens=60, res=(1280, 853)),
    "front": dict(target=(0.0, 0.0, 2.2), az=0, el=18, dist=50, lens=55, res=(1280, 800)),
    "hall": dict(target=(0.0, 4.0, 2.8), az=-20, el=22, dist=30, lens=55, res=(1280, 800)),
    "gate": dict(target=(0.0, -8.0, 1.6), az=-25, el=14, dist=16, lens=50, res=(1280, 800)),
    "right": dict(target=(0.0, 0.0, 2.0), az=60, el=32, dist=46, lens=60, res=(1280, 800)),
    "back": dict(target=(0.0, 0.0, 2.5), az=200, el=30, dist=46, lens=60, res=(1280, 800)),
}


def safe_render(path, **kw):
    import time
    import bpy
    for attempt in range(2):
        try:
            return V.render(path, **kw)
        except RuntimeError as e:
            print("render failed (%s), attempt %d" % (str(e).splitlines()[0][:80], attempt + 1))
            time.sleep(15)
    bpy.context.scene.cycles.device = "CPU"
    bpy.ops.render.render(write_still=True)
    print("rendered (CPU)", path)
    return path


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    no_render = "--no-render" in argv
    views = argv[argv.index("--views") + 1].split(",") if "--views" in argv else list(VIEWS)
    samples = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 32
    V.reset_scene()
    ob = build_yard()
    report(ob)
    V.export_gltf(ob, collision="complex", extra=dict(props=props()))
    if no_render:
        return
    add_dummies()
    for name in views:
        safe_render(os.path.join(V.PREVIEWS, "barracks_yard_%s.png" % name), samples=samples, **VIEWS[name])


main()
