"""The barracks and its yard props.

    SM_Barracks            the hall: stone footing, timber walls, green gable roof (ridge left-right) with a front gable
                           over the open door, awning on the left, a lean-to weapon porch on the right
    SM_TrainingDummy       a wooden practice dummy
    SM_WeaponRack          a rack of spears and swords
    SM_BannerPost_Swords   a post with a small hanging banner (crossed swords)
    SM_BannerPost_Tree     the same with the tree

Run:  Blender -b --factory-startup --python Tools/blender/assets/barracks.py -- [--no-render] [--only a,b] [--views a,b]
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import voxlib as V
import voxkit as K
from voxlib import Vox

VOX = 0.125
FINE = 0.0625

# ---- the building's grid (12.5 cm voxels). Footprint 86 x 64 voxels = 10.75 x 8 m, the door centre is x = 0.
NX, NY, NZ = 86, 64, 70
OX, OY = 43, 32
FLOOR, EAVE = 8, 26                       # floor 1.0 m above the ground (4 rises of 25 cm), eaves at 3.25 m
MX0, MX1, MY0, MY1 = 4, 62, 18, 60        # hall walls (core)
BX0, BX1, BY0 = 27, 59, 12                # door bay (core), it joins the hall at MY0
DX0, DX1, DZ1 = 37, 49, 23                # door opening
AX0, AX1, AY0 = 2, 20, 3                  # awning
WX0, WX1, WY0, WY1 = 62, 86, 21, 57       # side wing (roof extents)

WOODS = ["#ffffff", "#f4dcc0", "#ffe9cc", "#e8ccaa", "#fff2d8", "#eed2b0"]
BARGE = ["#f2d2ae", "#e4be96", "#f8dcb8", "#dab48c", "#eccaa2", "#e8c49c"]
LEAFS = ["#ffffff", "#e6f2a6", "#cfe690", "#f2f6b4", "#b8dc7c"]
DARK = "#8c7458"                          # the shadowed timber between the proud courses
FRAME = "#d8b890"
STEEL = "#c3c7cf"
STEEL_DARK = "#8a8e98"
SHAFT = "#ffdcae"
CANVAS = ["#efe0b2", "#e6d5a2", "#f3e6bc"]


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


# ---------------------------------------------------------------------------------------------------- helpers

def gable(v, a0, a1, b0, b1, z, ridge="x", run=4, rise=3, bw0=4, bw1=4, seed=0):
    """A solid stepped gable roof. `a` runs along the ridge, `b` across it. The first bw0 / last bw1 voxels along the
    ridge are the barge boards: big wooden blocks that step up the gable end, standing clear of the gable wall and one
    voxel above the tiles (0 = that end is buried in another roof). Returns the z of the top of the ridge beam."""
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
            put(t0, t1, lo, hi, zl, zl + 1, "beam")                      # wooden soffit
            put(t0, t1, lo, lo + 1, zl, zl + 2, "beam")                  # eave boards
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
        put(c0, c1, mid - 1, mid + 1, top - 2 * rise, top - 1, "plank", barge(seed, end, 98))      # the block under the peak
        put(c0, c1, mid - 2, mid + 2, top - 1, top + 3, "plank", barge(seed, end, 99))
    return top + 2


def gable_face(v, layer, b0, b1, z, ridge, run, rise, mat, color=None):
    """Dress the gable wall (the one voxel layer just inside the barge boards) with a wall material."""
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


def logs(v, axis, layer, a0, a1, z0, z1, seed=0):
    """Heavy horizontal timbers: courses 3 voxels high standing one voxel proud, a dark gap between them."""
    k, z = 0, z0
    while z < z1:
        zt = min(z + 3, z1)
        if axis == "y":
            v.box(a0, layer, z, a1, layer + 1, zt, "beam", wood(seed, k))
        else:
            v.box(layer, a0, z, layer + 1, a1, zt, "beam", wood(seed, k))
        z += 4
        k += 1


def window(v, axis, core, out, a0, z0, w=5, h=7, bars=True):
    """A glowing window in a timber wall. core: the wall's core layer on `axis`, out: +1/-1 the way it faces. The panes
    sit in the core, the frame is level with the proud timbers, sill and lintel stand out one more."""
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
        put(core, a0, a0 + w, z0 + h // 2, z0 + h // 2 + 1, "beam", FRAME)
    put(s, a0 - 2, a0 + w + 2, z0 - 1, z0, "beam")                       # sill
    put(s, a0 - 1, a0 + w + 1, z0 + h, z0 + h + 1, "beam")               # lintel


def paint_rows(g, rows, pal, x0, y, ztop, depth=1, mat="paint"):
    """Pixel art straight into a grid: rows (top first) in the XZ plane, x0 = left edge, at layer(s) y .. y+depth."""
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
    """A spear standing up in a 6.25 cm grid: shaft z0..z1, a gold collar and a steel leaf blade above (5 px)."""
    g.box(x, y, z0, x + 1, y + 1, z1, "post", SHAFT)
    g.box(x, y, z1, x + 1, y + 1, z1 + 1, "gold")
    if axis == "x":
        g.box(x - 1, y, z1 + 1, x + 2, y + 1, z1 + 3, "paint", STEEL)
    else:
        g.box(x, y - 1, z1 + 1, x + 1, y + 2, z1 + 3, "paint", STEEL)
    g.box(x, y, z1 + 3, x + 1, y + 1, z1 + 5, "paint", STEEL)


def sword(g, x, y, z0, blade=13):
    """A sword standing on its point in a 6.25 cm grid (blade 2 px wide at x, x+1). About blade + 7 px tall."""
    g.box(x, y, z0, x + 1, y + 1, z0 + 1, "paint", STEEL)
    g.box(x, y, z0 + 1, x + 2, y + 1, z0 + blade, "paint", STEEL)
    g.box(x + 1, y, z0 + 2, x + 2, y + 1, z0 + blade, "paint", STEEL_DARK)
    g.box(x - 2, y, z0 + blade, x + 4, y + 1, z0 + blade + 1, "gold")
    g.box(x, y, z0 + blade + 1, x + 2, y + 1, z0 + blade + 5, "paint", "wood_dark")
    g.box(x - 1, y, z0 + blade + 5, x + 3, y + 1, z0 + blade + 7, "gold")


def arrows(g, x0, y0, z, n=5, seed=0):
    """A sheaf of arrows standing in a crate (6.25 cm grid): shafts with white or red feathers."""
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


# ---------------------------------------------------------------------------------------------------- banners

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
            P(r, r + 1, "S") if r < n - 5 else None
        k = n - 4
        for d in (-2, -1, 0, 1, 2):
            P(k - d, k + d, "G")
        P(k + 1, k + 1, "G")
        P(k + 2, k + 2, "G")
        P(k + 3, k + 3, "G")
        P(k + 2, k + 3, "G")
        P(k + 3, k + 2, "G")
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
TREE_SMALL = [
    ".TTTT.",
    "TTTTTT",
    "TTtTTT",
    "TTTTTT",
    ".TTTT.",
    "..TT..",
    "..TT..",
    ".TTTT.",
]
EMBLEM_PAL = {"S": "#f1f1ea", "s": "#bfc3c8", "G": "gold", "T": "gold", "t": "gold_light"}


def make_banner(pattern, pal=EMBLEM_PAL, w=16, h=26, notch=5, rod=True, ey0=4, name="banner"):
    """Like voxkit.banner but with any emblem (rows of palette characters) and size. 6.25 cm voxels, green field,
    gold border, swallow-tail foot; stands in the XZ plane facing -Y; origin = middle of the top."""
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


# ---------------------------------------------------------------------------------------------------- props

def dummy_parts():
    """The training dummy, 1.5 m tall, 1 m across the arms. Origin: centre of its cross foot; it faces -Y."""
    b = Vox(8, 8, 9, VOX, origin=(4, 4, 0), name="dummy")
    b.box(0, 3, 0, 8, 5, 1, "beam")                                      # cross foot
    b.box(3, 0, 0, 5, 8, 1, "beam")
    b.box(2, 3, 1, 6, 5, 2, "beam", WOODS[3])                            # the braces that hold the post
    b.box(3, 2, 1, 5, 6, 2, "beam", WOODS[3])
    b.box(3, 3, 1, 5, 5, 4, "post")
    b.box(0, 3, 5, 8, 5, 7, "plank", BARGE[1])                           # the crossbar (arms)
    b.box(0, 3, 5, 1, 5, 7, "plank", BARGE[3])
    b.box(7, 3, 5, 8, 5, 7, "plank", BARGE[3])
    b.box(2, 2, 4, 6, 6, 8, "plank")                                     # chest block
    b.box(2, 2, 4, 6, 6, 5, "plank", "#c89c70")
    b.box(2, 2, 7, 6, 6, 8, "plank", "#c89c70")
    b.box(3, 3, 8, 5, 5, 9, "post")                                      # neck
    head = Vox(8, 8, 8, FINE, origin=(4, 4, 0), name="dummy_head").at(0, 0, 9 * VOX)
    head.box(1, 1, 0, 7, 7, 6, "plank", WOODS[2])
    head.box(1, 1, 0, 7, 7, 1, "plank", "#c89c70")
    head.box(1, 1, 5, 7, 7, 6, "plank", "#c89c70")
    head.set(2, 0, 3, "metal")                                           # two bolts for eyes
    head.set(5, 0, 3, "metal")
    head.box(3, 3, 6, 5, 5, 7, "beam")
    boss = Vox(6, 2, 6, FINE, origin=(3, 2, 0), name="dummy_boss").at(0, -2 * VOX, 5 * VOX)
    paint_rows(boss, [".SS.", "SSSS", "SSSS", ".SS."], {"S": STEEL}, 1, 1, 4)
    boss.box(2, 0, 1, 4, 1, 3, "paint", STEEL_DARK)
    return [b, head, boss]


def rack_parts(n=5):
    """The weapon rack: 1.5 m wide, spears to 1.65 m. Origin: centre of its base; the weapons face -Y."""
    b = Vox(12, 6, 12, VOX, origin=(6, 3, 0), name="rack")
    for x in (0, 10):
        b.box(x, 0, 0, x + 2, 6, 1, "beam")                              # feet
        b.box(x, 1, 1, x + 2, 5, 2, "beam", WOODS[3])
        b.box(x, 2, 1, x + 2, 4, 11, "post")
        b.box(x, 2, 11, x + 2, 4, 12, "beam", WOODS[2])
    b.box(1, 1, 2, 11, 2, 4, "beam", WOODS[1])                           # lower rail in front of the weapons
    b.box(1, 3, 9, 11, 4, 11, "beam", WOODS[1])                          # upper rail behind them
    b.box(2, 2, 0, 10, 3, 1, "plank")                                    # the board the butts stand on
    f = Vox(24, 12, 32, FINE, origin=(12, 6, 0), name="rack_fine")
    xs = [5, 9, 12, 15, 19][:n] if n == 5 else list(np.linspace(5, 19, n).round().astype(int))
    for k, x in enumerate(xs):
        if k % 2 == 0:
            spear(f, x, 5, 2, 22 + (k % 3))
        else:
            sword(f, x - 1, 5, 2, blade=12)
    return [b, f]


def banner_post_parts(pattern):
    """A post with a crossbar and a small hanging banner (0.6 x 1 m). Origin: centre of its base; it faces -Y."""
    b = Vox(8, 6, 18, VOX, origin=(4, 3, 0), name="banner_post", seed=4)
    b.box(2, 1, 0, 6, 5, 2, "stone")
    b.chunky("stone", cell=2, p=0.3, seed=3)
    b.box(3, 2, 2, 5, 4, 16, "post")
    b.box(3, 2, 16, 5, 4, 17, "gold")
    b.box(1, 1, 14, 7, 2, 15, "beam", WOODS[2])                          # crossbar in front of the post
    b.set(0, 1, 14, "gold")
    b.set(7, 1, 14, "gold")
    bn = make_banner(pattern, w=10, h=16, notch=3, rod=False, ey0=3).at(0, -1 * VOX, 14 * VOX)
    return [b, bn]


def build_dummy():
    return V.join(dummy_parts(), "SM_TrainingDummy")


def build_rack():
    return V.join(rack_parts(), "SM_WeaponRack")


def build_banner_post_swords():
    return V.join(banner_post_parts(SWORDS_SMALL), "SM_BannerPost_Swords")


def build_banner_post_tree():
    return V.join(banner_post_parts(TREE_SMALL), "SM_BannerPost_Tree")


# ---------------------------------------------------------------------------------------------------- the barracks

def build_barracks(dummies=True):
    rng = np.random.default_rng(12)
    v = Vox(NX, NY, NZ, VOX, origin=(OX, OY, 0), name="barracks", seed=7)
    f = Vox(NX * 2, NY * 2, NZ * 2, FINE, origin=(OX * 2, OY * 2, 0), name="barracks_fine", seed=3)   # small things
    extra = []

    def mx(x):
        return (x - OX) * VOX

    def my(y):
        return (y - OY) * VOX

    # ---- footing of big stone blocks, and the blocks beside the steps
    v.box(1, 15, 0, 65, 63, FLOOR, "stone")
    v.box(24, 9, 0, 62, 16, FLOOR, "stone")
    v.box(28, 4, 0, 35, 9, FLOOR, "stone")
    v.box(51, 4, 0, 58, 9, FLOOR, "stone")
    v.box(29, 1, 0, 35, 4, 4, "stone")
    v.box(51, 1, 0, 57, 4, 4, "stone")

    # ---- walls: a dark core with proud timber courses, stone piers at the corners
    v.box(MX0, MY0, FLOOR, MX1, MY1, EAVE, "beam", DARK)
    v.box(BX0, BY0, FLOOR, BX1, MY0, EAVE, "beam", DARK)
    logs(v, "y", MY0 - 1, MX0, BX0, FLOOR, EAVE, 1)
    logs(v, "y", MY1, MX0, MX1, FLOOR, EAVE, 2)
    logs(v, "x", MX0 - 1, MY0, MY1, FLOOR, EAVE, 3)
    logs(v, "x", MX1, MY0, MY1, FLOOR, EAVE, 4)
    logs(v, "y", BY0 - 1, BX0, BX1, FLOOR, EAVE, 5)
    logs(v, "x", BX0 - 1, BY0, MY0, FLOOR, EAVE, 6)
    logs(v, "x", BX1, BY0, MY0, FLOOR, EAVE, 7)
    for (px, py) in ((2, 16), (2, 56), (58, 56), (58, 16)):
        v.box(px, py, FLOOR, px + 6, py + 6, EAVE, "stone")
    v.box(30, 11, FLOOR, 35, 12, DZ1, "stone")                           # stone panels either side of the door
    v.box(51, 11, FLOOR, 56, 12, DZ1, "stone")
    v.chunky("stone", p=0.3, seed=2)
    v.tint("stone", "#e9e2d6", p=0.3, seed=4, cell=4)
    v.tint("stone", "#fff4e2", p=0.2, seed=9, cell=4)

    # ---- steps: three treads up to the footing, 25 cm rises, 37.5 cm treads; their foot is at y = -4.0 m
    v.clear(35, 0, 0, 51, 9, 12)
    K.stairs(v, 35, 0, 0, 16, 3, "-y", run=3, rise=2, mat="stone")
    v.clear(35, 9, FLOOR, 51, 12, FLOOR + 3)                             # a clean landing

    # ---- posts and windows
    v.box(16, 16, FLOOR, 19, 18, EAVE, "post")                           # front, under the awning
    for a0 in (10, 21):
        window(v, "y", MY0, -1, a0, 14)
    for x in (20, 33, 46):                                               # back
        v.box(x, MY1, FLOOR, x + 3, MY1 + 2, EAVE, "post")
    for a0 in (12, 26, 39, 51):
        window(v, "y", MY1 - 1, 1, a0, 14)
    for y in (31, 44):                                                   # west, east
        v.box(MX0 - 2, y, FLOOR, MX0, y + 3, EAVE, "post")
        v.box(MX1, y, FLOOR, MX1 + 2, y + 3, EAVE, "post")
    for a0 in (24, 37, 49):
        window(v, "x", MX0, -1, a0, 14)
    window(v, "x", MX1 - 1, 1, 37, 14)

    # ---- roofs: the hall's (ridge along X), then the gable over the door (ridge along Y) cut into it
    gable(v, 0, 66, 12, 64, EAVE, "x", 4, 3, 4, 4, seed=1)
    top = gable(v, 8, 38, 24, 62, EAVE, "y", 3, 3, 4, 0, seed=2)
    gable_face(v, 4, 12, 64, EAVE, "x", 4, 3, "brick")
    gable_face(v, 61, 12, 64, EAVE, "x", 4, 3, "brick")
    gable_face(v, 12, 24, 62, EAVE, "y", 3, 3, "brick")
    v.box(2, 17, 25, 4, 61, 27, "beam")                                  # tie beams under the gables
    v.box(62, 17, 25, 64, 61, 27, "beam")
    v.box(28, 10, 26, 58, 12, 28, "beam")
    window(v, "x", 4, -1, 36, 31, w=4, h=5)
    window(v, "x", 61, 1, 36, 31, w=4, h=5)
    window(v, "y", 12, -1, 35, 30, w=3, h=4, bars=False)
    window(v, "y", 12, -1, 48, 30, w=3, h=4, bars=False)
    for x in (9, 17, 24):                                                # rafter ends under the front eave
        v.box(x, 13, 24, x + 2, 17, 26, "beam", WOODS[3])
        v.box(x, 15, 22, x + 2, 17, 24, "beam", WOODS[3])
    for x in (12, 26, 39, 52):                                           # and the back one
        v.box(x, 61, 24, x + 2, 63, 26, "beam", WOODS[3])

    for i in range(6):                                                   # iron studs on the front gable's blocks
        zf = 2 * (EAVE + 3 * i) + 1
        for xf in (2 * (24 + 3 * i) + 1, 2 * (62 - 3 * i) - 3):
            f.box(xf, 15, zf, xf + 2, 16, zf + 2, "metal")

    # ---- chimney
    v.box(8, 23, EAVE, 15, 30, 48, "brick")
    v.box(7, 22, 48, 16, 31, 51, "brick", "#f0e6d8")
    v.box(9, 24, 50, 14, 29, 51, "paint", "#1c1816")
    v.chunky("brick", cell=2, p=0.22, seed=6, region=(6, 21, 34, 17, 32, 48))

    # ---- the open door: a lit room about 1 m deep
    v.clear(DX0, 9, FLOOR, DX1, 14, DZ1)
    v.clear(34, 14, FLOOR, 52, 21, 24)
    v.box(34, 12, FLOOR - 1, 52, 21, FLOOR, "plank")                     # plank floor and threshold
    v.box(DX0, 9, FLOOR - 1, DX1, 12, FLOOR, "plank", WOODS[3])
    v.box(34, 21, FLOOR, 52, 22, 24, "plank", "#ffe6b8")                 # back wall
    v.box(33, 14, FLOOR, 34, 21, 24, "plank", "#f0d0a0")
    v.box(52, 14, FLOOR, 53, 21, 24, "plank", "#f0d0a0")
    v.box(34, 14, 24, 52, 21, 25, "beam")
    v.box(46, 16, 12, 52, 21, 13, "plank")                               # table (right) with a helmet
    v.box(46, 16, FLOOR, 47, 17, 12, "post")
    v.box(51, 16, FLOOR, 52, 17, 12, "post")
    v.box(47, 17, FLOOR, 52, 21, 12, "beam", DARK)
    f.box(95, 35, 26, 100, 40, 29, "paint", STEEL)
    f.box(96, 36, 29, 99, 39, 31, "paint", STEEL)
    f.box(95, 35, 26, 100, 36, 27, "paint", STEEL_DARK)
    f.box(97, 34, 27, 98, 36, 30, "paint", STEEL_DARK)                   # nose guard
    f.box(97, 36, 31, 98, 39, 33, "paint", "red")                        # crest
    f.box(102, 37, 26, 104, 39, 29, "paint", STEEL_DARK)                 # a mug
    v.box(35, 19, 11, 41, 20, 12, "beam", WOODS[1])                      # spear rack on the back wall (left)
    v.box(35, 19, 17, 41, 20, 18, "beam", WOODS[1])
    for k, x in enumerate((72, 75, 78, 81)):
        spear(f, x, 37, 16, 38 + (k % 2))
    paint_rows(f, [                                                      # the round green shield with the gold tree
        "...GGGG...",
        "..GggggG..",
        ".GggTTggG.",
        "GggTTTTggG",
        "GgTTTTTTgG",
        "GggTTTTggG",
        "GgggTTgggG",
        ".GgTTTTgG.",
        "..GggggG..",
        "...GGGG...",
    ], {"G": "gold", "g": "banner", "T": "gold_light"}, 89, 41, 45)
    flantern(f, 88, 38, 33, chain=1)                                     # the lamp that lights the room, on the chest                                              # the lamp that lights the room
    v.box(42, 18, FLOOR, 46, 21, 11, "plank", WOODS[3])                  # a small chest under the shield
    v.box(42, 18, 10, 46, 21, 11, "beam")
    f.box(87, 35, 19, 89, 36, 21, "gold")

    # ---- door front: posts, lintel with gold plates, brackets
    for x in (27, 56):
        v.box(x, 10, FLOOR, x + 3, 12, EAVE, "post")
        v.box(x, 9, 23, x + 3, 10, EAVE, "beam", WOODS[3])
    for x in (35, 49):
        v.box(x, 10, FLOOR, x + 2, 12, DZ1, "post")
    v.box(34, 9, DZ1, 52, 12, EAVE, "beam", WOODS[2])
    for cx in (74, 86, 98):
        f.box(cx - 2, 17, 47, cx + 2, 18, 51, "gold")
    v.box(37, 10, DZ1 - 2, 38, 12, DZ1, "beam", WOODS[3])                # little brackets in the door's top corners
    v.box(48, 10, DZ1 - 2, 49, 12, DZ1, "beam", WOODS[3])
    for (xa, xb) in ((25, 27), (59, 61)):                                # corbels under the gable's lowest blocks
        v.box(xa, 10, 22, xb, 12, 25, "beam", WOODS[3])
    for cx in (65, 107):                                                 # the two wall lanterns on iron arms
        f.box(cx - 1, 14, 44, cx + 1, 22, 46, "metal")
        f.box(cx - 1, 20, 40, cx + 1, 22, 44, "metal")
        flantern(f, cx, 16, 44)

    # ---- crates of arrows on the blocks beside the steps
    for (x0, s) in ((29, 1), (52, 2)):
        v.box(x0, 4, FLOOR, x0 + 5, 9, FLOOR + 4, "plank")
        v.frame(x0, 4, FLOOR, x0 + 5, 9, FLOOR + 4, "beam")
        v.clear(x0 + 1, 5, FLOOR + 3, x0 + 4, 8, FLOOR + 4)
        arrows(f, x0 * 2 + 2, 10, FLOOR * 2 + 6, n=6, seed=s)
    v.box(52, 1, 4, 56, 4, 7, "plank", WOODS[1])                         # a small box on the lower block
    v.frame(52, 1, 4, 56, 4, 7, "beam")

    # ---- the awning: cream canvas on posts, with a table, a bench, sacks and a spear rack under it
    v.clear(AX0, AY0, 0, AX1 + 4, 15, 12)                                # (the footing's swollen stones stay behind y = 15)
    v.box(AX0, 16, 23, AX1, 17, 25, "beam", WOODS[3])                    # wall rail
    for k, (ya, yb) in enumerate(((13, 16), (10, 13), (7, 10), (4, 7))):
        v.box(AX0, ya, 23 - k, AX1, yb, 24 - k, "wool", CANVAS[k % 3])
    for x in (AX0, AX1 - 2):
        v.box(x, 4, 0, x + 2, 6, 20, "post")
        v.box(x - (1 if x > AX0 else 0), 3, 0, x + 3, 7, 2, "stone")
    v.box(AX0, 4, 19, AX1, 5, 20, "beam")                                # front beam
    for x in (AX0, AX1 - 1):                                             # side rails up to the wall
        for k, (ya, yb) in enumerate(((13, 16), (10, 13), (7, 10), (5, 7))):
            v.box(x, ya, 22 - k, x + 1, yb, 23 - k, "beam", WOODS[2])
    scallop = [0, 2, 3, 3, 2, 0]                                         # the valance, in 6.25 cm pixels
    for i in range(AX0 * 2, AX1 * 2):
        d = scallop[(i - AX0 * 2) % 6]
        z1 = 42
        z0 = 37 - d
        f.box(i, 6, z0 + 1, i + 1, 8, z1, "wool", CANVAS[0])
        f.box(i, 6, z0, i + 1, 8, z0 + 1, "paint", "gold")
    v.box(5, 7, 5, 14, 11, 6, "plank")                                   # table
    for (x, y) in ((5, 7), (13, 7), (5, 10), (13, 10)):
        v.box(x, y, 0, x + 1, y + 1, 5, "post")
    v.box(6, 9, 2, 13, 10, 3, "beam", WOODS[3])
    for (x, y) in ((13, 17), (21, 15), (17, 19)):                        # mugs and a plate
        f.box(x, y, 12, x + 2, y + 2, 15, "paint", STEEL)
        f.box(x, y, 14, x + 2, y + 2, 15, "paint", STEEL_DARK)
        f.box(x + 2, y, 13, x + 3, y + 1, 14, "paint", STEEL_DARK)
    f.box(22, 18, 12, 26, 21, 13, "plank", WOODS[1])
    f.box(23, 19, 13, 25, 20, 14, "paint", "#d8a850")
    v.box(6, 4, 3, 13, 6, 4, "plank", WOODS[1])                          # bench
    v.box(6, 4, 0, 7, 6, 3, "post")
    v.box(12, 4, 0, 13, 6, 3, "post")
    v.box(15, 7, 0, 18, 10, 3, "plank", WOODS[4])                        # stool
    v.box(15, 7, 0, 18, 10, 2, "post")
    v.box(15, 7, 2, 18, 10, 3, "plank", WOODS[4])
    sack = "#d2b888"
    v.ellipsoid(4.5, 12.5, 1.6, 2.4, 2.2, 2.2, "wool", sack)             # sacks
    v.ellipsoid(8.0, 13.0, 1.2, 1.9, 1.9, 1.7, "wool", "#c4a878")
    v.set(4, 12, 3, "wool", "#a88c5c")
    v.set(8, 13, 2, "wool", "#a88c5c")
    v.box(12, 13, 0, 13, 15, 11, "post")                                 # spear rack against the footing
    v.box(19, 13, 0, 20, 15, 11, "post")
    v.box(12, 13, 4, 20, 14, 5, "beam", WOODS[1])
    v.box(12, 13, 9, 20, 14, 10, "beam", WOODS[1])
    for k, x in enumerate((27, 30, 33, 36)):
        spear(f, x, 28, 0, 24 + (k % 2))

    # ---- the side wing: an open lean-to porch for the weapons, on posts
    v.box(WX0, WY0 + 1, 0, 83, WY1 - 1, 1, "cobble")
    v.box(WX0, 53, 0, 82, 55, 4, "stone")                                # back wall: stone foot, upright planks
    for k in range(8):
        x0 = WX0 + 3 * k
        v.box(x0, WY0, 24 - k, x0 + 3, WY1, 25 - k, "plank", WOODS[k % 6])       # boarded underside
        v.box(x0, WY0, 25 - k, x0 + 3, WY1, 26 - k, "roof")
        for (ya, yb) in ((WY0, WY0 + 2), (WY1 - 2, WY1)):                        # side boards
            v.box(x0, ya, 24 - k, x0 + 3, yb, 27 - k, "plank", barge(31, k, ya))
        if x0 < 80:
            v.box(x0, 53, 4, x0 + 3, 55, 24 - k, "plank", wood(32, k))
    v.box(85, WY0, 17, 86, WY1, 19, "beam")                              # eave board
    for y in (23, 52):
        v.box(79, y, 0, 82, y + 3, 19, "post")
        v.box(78, y - 1, 0, 83, y + 4, 3, "stone")
    v.box(79, 37, 0, 81, 39, 18, "post")
    v.box(79, 23, 17, 82, 55, 19, "beam", WOODS[3])                      # the plate the roof sits on
    for z in (3, 7):
        v.box(80, 26, z, 81, 52, z + 1, "beam", WOODS[1])                # rail on the east side
    for k in range(3):                                                   # braces on the front post
        v.box(78 - k, 23, 16 + k, 79 - k, 25, 17 + k, "beam", WOODS[3])
    v.stamp(K.barrel(), 76, 49, 1)
    v.stamp(K.barrel(), 70, 50, 1)
    v.stamp(K.crate(6), 74, 43, 1)
    v.box(67, 27, 1, 72, 32, 5, "plank", WOODS[2])                       # arrow crate at the front
    v.frame(67, 27, 1, 72, 32, 5, "beam")
    v.clear(68, 28, 4, 71, 31, 5)
    arrows(f, 137, 57, 8, n=7, seed=5)
    v.box(72, 26, 1, 76, 30, 4, "hay")
    extra += place(rack_parts(), mx(67.5), my(40), VOX, rot=1)           # the weapon rack against the hall wall
    flantern(f, 2 * 67, 2 * 28, 46)                                      # a lantern under the porch roof, by the wall

    # ---- flag pole on the gable's peak, big banner over the door
    v.box(42, 10, top, 44, 12, 65, "post")
    v.box(41, 9, top, 45, 13, top + 2, "beam", WOODS[3])
    v.box(41, 9, 63, 45, 13, 64, "gold")
    f.ellipsoid(86, 22, 133, 3.3, 3.3, 3.3, "gold")
    extra.append(K.flag("swords", w=24, h=14).at(mx(44), my(11), 55.5 * VOX))
    v.box(40, 7, 41, 41, 8, 43, "beam")                                  # the banner's two brackets
    v.box(45, 7, 41, 46, 8, 43, "beam")
    extra.append(make_banner(swords_rows(14), w=20, h=30, notch=6, ey0=5).at(mx(43), my(7.5), 43 * VOX))

    # ---- moss, flowers and vines
    roof_top = v.exposed("+z") & v.mask("roof")
    n = V.noise3(v.n, 7, 5)
    X, Y, Z = v.grid()
    front_left = (X < 27) & (Y < 34)
    v.where(roof_top & (n > 0.60), "moss")
    v.where(roof_top & front_left & (n > 0.49), "moss")
    v.where(roof_top & (Y < 16) & (X < 24) & (n > 0.36), "moss")
    v.scatter("roof", "moss", p=0.04, seed=4, direction="+z")
    v.scatter("stone", "mossy_stone", p=0.10, seed=8, direction="+z")
    v.scatter("stone", "mossy_stone", p=0.05, seed=9, region=(0, 0, 0, NX, NY, 5))

    def hang(x, y, z, n_max, p=0.7):
        if rng.random() > p:
            return
        for k in range(int(rng.integers(1, n_max + 1))):
            if v.m[x, y, z - k] == 0:
                v.set(x, y, z - k, "leaves", LEAFS[int(rng.integers(len(LEAFS)))])

    for x in range(4, 25):                                               # hanging from the front eave
        lush = 5 if (x < 9 or 12 < x < 20) else 2
        hang(x, 11, 28, lush, 0.85 if lush == 5 else 0.5)
        if rng.random() < 0.5:
            v.set(x, 12, 29, "leaves", LEAFS[int(rng.integers(len(LEAFS)))])
    for x in range(40, 62):                                              # the back eave
        hang(x, 63, 28, 4, 0.45)
    for z in range(FLOOR, EAVE):                                         # ivy up the north-east pier and the back wall
        for x in range(56, 65):
            if rng.random() < 0.55 - 0.012 * (z - FLOOR) and v.m[x, 62, z] == 0 and v.m[x, 61, z] > 0:
                v.set(x, 62, z, "leaves", LEAFS[int(rng.integers(len(LEAFS)))])
    for z in range(0, 20):                                               # ivy on the south-west pier
        for y in range(15, 23):
            if rng.random() < 0.5 - 0.02 * z and v.m[1, y, z] == 0 and v.m[2, y, z] > 0:
                v.set(1, y, z, "leaves", LEAFS[int(rng.integers(len(LEAFS)))])
    for x in range(66, 86):                                              # a few off the porch roof's front edge
        hang(x, WY0 - 1, 25 - (x - WX0) // 3, 3, 0.3)
    for z in range(33, 44):                                              # and up the chimney
        for x in range(8, 15):
            if rng.random() < 0.45 - 0.035 * (z - 33) and v.m[x, 22, z] == 0 and v.m[x, 23, z] > 0:
                v.set(x, 22, z, "leaves", LEAFS[int(rng.integers(len(LEAFS)))])

    def flower_box(axis, layer, out, a0, w, z, seed):
        """A planter under a window: layer = the sill's layer, it hangs one voxel further out."""
        cols = ["flower_white", "flower_yellow", "flower_pink", "flower_orange"]
        for a in range(a0 - 1, a0 + w + 1):
            for d in (0, out):
                x, y = (a, layer + d) if axis == "y" else (layer + d, a)
                v.box(x, y, z - 2, x + 1, y + 1, z, "plank", WOODS[3])
                if d == out:
                    v.set(x, y, z, "leaves", LEAFS[int(hsh(seed, a) * len(LEAFS))])
                    if hsh(seed, a, 7) < 0.75:
                        fx, fy = 2 * x + int(hsh(seed, a, 1) * 2), 2 * y + int(hsh(seed, a, 2) * 2)
                        f.box(fx, fy, 2 * z + 2, fx + 1, fy + 1, 2 * z + 4, "paint", cols[int(hsh(seed, a, 3) * 4)])
                        f.box(fx - (1 if axis == "y" else 0), fy - (1 if axis == "x" else 0), 2 * z + 3,
                              fx + (2 if axis == "y" else 1), fy + (2 if axis == "x" else 1), 2 * z + 4,
                              "paint", cols[int(hsh(seed, a, 3) * 4)])

    flower_box("x", MX0 - 2, -1, 24, 5, 13, 1)                           # west wall
    flower_box("x", MX0 - 2, -1, 49, 5, 13, 2)
    flower_box("y", MY1 + 1, 1, 26, 5, 13, 3)                            # back wall
    flower_box("y", MY1 + 1, 1, 39, 5, 13, 4)

    flowers = np.argwhere(v.mask("moss") & v.exposed("+z"))              # little white flowers on the mossy eave
    for (x, y, z) in flowers:
        if y < 18 and x < 26 and rng.random() < 0.16:
            fx, fy = 2 * x + int(rng.integers(2)), 2 * y + int(rng.integers(2))
            f.box(fx, fy, 2 * z + 2, fx + 1, fy + 1, 2 * z + 3, "leaves")
            f.box(fx - 1, fy, 2 * z + 3, fx + 2, fy + 1, 2 * z + 4, "paint", "flower_white")
            f.box(fx, fy - 1, 2 * z + 3, fx + 1, fy + 2, 2 * z + 4, "paint", "flower_white")
            f.box(fx, fy, 2 * z + 3, fx + 1, fy + 1, 2 * z + 5, "paint", "flower_yellow")

    # ---- two dummies beside the steps, as in the close-up
    if dummies:
        extra += place(dummy_parts(), mx(24), my(4), 0)
        extra += place(dummy_parts(), mx(63), my(4), 0)

    return V.join([v, f] + extra, "SM_Barracks")


# ---------------------------------------------------------------------------------------------------- main

def report(ob):
    co = np.zeros(len(ob.data.vertices) * 3, np.float32)
    ob.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    lo, hi = co.min(axis=0), co.max(axis=0)
    print("ASSET %s faces=%d size=%.3f x %.3f x %.3f  min=(%.3f, %.3f, %.3f) max=(%.3f, %.3f, %.3f)" % (
        ob.name, ob["voxel_faces"], hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2], lo[0], lo[1], lo[2], hi[0], hi[1], hi[2]))


BUILDERS = {
    "barracks": (build_barracks, "complex"),
    "dummy": (build_dummy, "complex"),
    "rack": (build_rack, "complex"),
    "post_swords": (build_banner_post_swords, "complex"),
    "post_tree": (build_banner_post_tree, "complex"),
}

VIEWS = {   # name: (asset or 'props', render keywords)
    "ref": ("barracks", dict(target=(-0.2, 0, 3.6), az=-33, el=9, dist=30, lens=62, res=(1000, 1100))),
    "village": ("barracks", dict(target=(0, 0, 2.8), az=28, el=32, dist=30, lens=70)),
    "front": ("barracks", dict(target=(0, 0, 3.2), az=0, el=14, dist=30, lens=70)),
    "door": ("barracks", dict(target=(0, -2.5, 2.2), az=-8, el=10, dist=12, lens=60)),
    "left": ("barracks", dict(target=(0, 0, 2.6), az=-105, el=20, dist=32, lens=70)),
    "back": ("barracks", dict(target=(0, 0, 3.0), az=205, el=26, dist=30, lens=70)),
    "right": ("barracks", dict(target=(0, 0, 3.0), az=105, el=22, dist=30, lens=70)),
    "props": ("props", dict(target=(0, 0, 1.0), az=-22, el=16, dist=11, lens=60)),
    "props_back": ("props", dict(target=(0, 0, 1.0), az=160, el=24, dist=11, lens=60)),
}


def safe_render(path, **kw):
    """V.render, but when the GPU is out of memory (other renders are running) wait and try again, then use the CPU."""
    import time
    import bpy
    for attempt in range(3):
        try:
            return V.render(path, **kw)
        except RuntimeError as e:
            print("render failed (%s), attempt %d" % (str(e).splitlines()[0][:80], attempt + 1))
            time.sleep(20)
    bpy.context.scene.cycles.device = "CPU"
    bpy.ops.render.render(write_still=True)
    print("rendered (CPU)", path)
    return path


def main():
    argv =sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    no_render = "--no-render" in argv
    only = argv[argv.index("--only") + 1].split(",") if "--only" in argv else list(BUILDERS)
    views = argv[argv.index("--views") + 1].split(",") if "--views" in argv else list(VIEWS)
    samples = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 48

    for key in only:
        V.reset_scene()
        build, collision = BUILDERS[key]
        ob = build()
        report(ob)
        V.export_gltf(ob, collision=collision)
    if no_render:
        return
    for name in views:
        what, kw = VIEWS[name]
        if what != "props" and what not in only:
            continue
        if what == "props" and not any(k in only for k in ("dummy", "rack", "post_swords", "post_tree")):
            continue
        V.reset_scene()
        if what == "props":
            for key, x in (("post_swords", -2.7), ("dummy", -1.2), ("rack", 0.6), ("post_tree", 2.4)):
                ob = BUILDERS[key][0]()
                ob.location = (x, 0, 0)
        else:
            BUILDERS[what][0]()
        safe_render(os.path.join(V.PREVIEWS, "barracks_%s.png" % name), samples=samples, **kw)


main()
