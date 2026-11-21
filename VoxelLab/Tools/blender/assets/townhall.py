"""Town hall of the voxel village: SM_TownHall.

A two-storey half-timbered hall on a 1 m platform of stone blocks. Front faces -Y. The staircase comes down the front,
centred on x = +1.0 m, and its foot ends exactly at y = -5.0 m. Footprint 11 m (X) by 10 m (Y), origin = its centre
at plaza level.

    Blender -b --factory-startup --python Tools/blender/assets/townhall.py -- [--no-render] [--views a,b] [--no-export]
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import voxlib as V
import voxkit as K
from voxlib import Vox

IDS = V.IDS
NX, NY, NZ = 88, 80, 100          # 11 m x 10 m x 12.5 m at 12.5 cm
OX, OY = 44, 40                   # voxel that becomes x = 0, y = 0
PZ = 8                            # top of the platform (1 m)
SX = 52                           # centre line of the stairs and the door (x = +1.0 m)

PLASTER = "#efe2c4"
BARGE = ("#eecca6", "#e0b68c")         # alternate tints of the barge board blocks
LEAF = (None, "#d8e8a0", "#b6d47a", "#c6e08a", "#9cc468")
FLOWERS = ("flower_white", "flower_yellow", "flower_orange", "flower_pink", "#a678d8", "#e25a6a")


def mx(x):
    """voxel x -> metres"""
    return (x - OX) * 0.125


def my(y):
    return (y - OY) * 0.125


# ---------------------------------------------------------------------------------------------------- helpers

def gable(v, a0, a1, b0, b1, z, ridge="x", run=4, rise=4, barge=(True, True), board=4):
    """A stepped gable roof as a shell (so the gable walls stay visible under the overhang): each course is a strip of
    tiles along both slopes, thick barge-board blocks step up the two gable ends, one voxel proud of the tiles.
    ridge='x': the ridge runs along X between a0 and a1, the slopes fall to b0 (-Y) and b1 (+Y). Returns the top z."""
    def put(al, ah, bl, bh, zl, zh, mat, col=None):
        if ridge == "y":
            v.box(bl, al, zl, bh, ah, zh, mat, col)
        else:
            v.box(al, bl, zl, ah, bh, zh, mat, col)

    steps = int(np.ceil((b1 - b0) / 2.0 / run))
    top = z
    for i in range(steps):
        lo, hi = b0 + i * run, b1 - i * run
        if hi <= lo:
            break
        zl, zh = z + i * rise, z + (i + 1) * rise
        w = min(run + 2, hi - lo)
        put(a0, a1, lo, lo + w, zl, zh, "roof")
        put(a0, a1, hi - w, hi, zl, zh, "roof")
        if i == 0:                                           # wooden boards along the eaves
            put(a0, a1, lo, lo + 1, zl, zl + 2, "plank", "#dcae82")
            put(a0, a1, hi - 1, hi, zl, zl + 2, "plank", "#dcae82")
        for k, (on, al, ah) in enumerate(((barge[0], a0, a0 + board), (barge[1], a1 - board, a1))):
            if not on:
                continue
            col = BARGE[(i + k) % 2]
            drop = 1 if i == 0 else 0
            bw = min(run, hi - lo)                                # one block per course, a voxel proud all round
            put(al, ah, lo - 1, lo + bw, zl - drop, zh + 1, "plank", col)
            put(al, ah, hi - bw, hi + 1, zl - drop, zh + 1, "plank", col)
        top = zh
    mid = (b0 + b1) // 2
    put(a0, a1, mid - 2, mid + 2, top, top + 2, "plank", "#d9a878")      # ridge board
    if barge[0]:
        put(a0, a0 + board, mid - 3, mid + 3, top - 1, top + 3, "plank", BARGE[0])
    if barge[1]:
        put(a1 - board, a1, mid - 3, mid + 3, top - 1, top + 3, "plank", BARGE[0])
    return top + 2


def fill_under(v, x0, y0, x1, y1, z0, mat="plaster", color=PLASTER):
    """Make the inside solid: in every column of the rectangle, fill the air between z0 and its highest voxel."""
    m = v.m[x0:x1, y0:y1, :]
    solid = m > 0
    nz = v.n[2]
    top = np.where(solid.any(axis=2), nz - 1 - np.argmax(solid[:, :, ::-1], axis=2), -1)
    zz = np.arange(nz)[None, None, :]
    mask = (~solid) & (zz >= z0) & (zz < top[:, :, None])
    m[mask] = IDS[mat]
    v.c[x0:x1, y0:y1, :][mask] = V.rgb(color) if color else 255


class Face:
    """One wall face. axis: 'y' (the wall runs along X, `a` is x) or 'x' (`a` is y). plane: the wall's outer voxel
    layer on that axis; out: +1 / -1, the way it faces. Layer p = p voxels outside the wall (0 = the wall itself)."""

    def __init__(self, v, axis, plane, out):
        self.v, self.axis, self.plane, self.out = v, axis, plane, out

    def idx(self, p, al, ah, zl, zh):
        L = self.plane + self.out * p
        al, zl = max(0, al), max(0, zl)
        if self.axis == "y":
            return (slice(al, ah), slice(L, L + 1), slice(zl, zh))
        return (slice(L, L + 1), slice(al, ah), slice(zl, zh))

    def put(self, p0, p1, al, ah, zl, zh, mat, col=None):
        l0, l1 = sorted((self.plane + self.out * p0, self.plane + self.out * p1))
        if self.axis == "y":
            self.v.box(al, l0, zl, ah, l1 + 1, zh, mat, col)
        else:
            self.v.box(l0, al, zl, l1 + 1, ah, zh, mat, col)

    def xyz(self, p, a, z):
        L = self.plane + self.out * p
        return (a, L, z) if self.axis == "y" else (L, a, z)

    def timber(self, al, ah, zl, zh, mat="beam", proud=1, col=None):
        """Timber standing proud of the wall, only where there is wall behind it and air to put it in (so it follows
        gable triangles and never eats roofs)."""
        back = self.v.m[self.idx(0, al, ah, zl, zh)] > 0
        for p in range(1, proud + 1):
            i = self.idx(p, al, ah, zl, zh)
            ok = back & (self.v.m[i] == 0)
            self.v.m[i][ok] = IDS[mat]
            self.v.c[i][ok] = V.rgb(col) if col else 255

    def brace(self, a, z, n, da, dz=1, mat="beam"):
        for k in range(n):
            self.timber(a + k * da, a + k * da + 1, z + k * dz, z + k * dz + 2, mat)

    def win(self, a0, z0, w=6, h=6, sill=True, mullion=True):
        self.put(1, 2, a0 - 1, a0 + w + 1, z0 - 1, z0 + h + 1, None)       # no stone bulging in front of it
        K.window(self.v, self.axis, self.plane, a0, z0, w=w, h=h, out=self.out, sill=sill, mullion=mullion)

    def flowerbox(self, a0, a1, z, rng, depth=3):
        """A planter under a window: its top is at z + 2, plants on top and trailing over the front."""
        self.put(1, depth, a0, a1, z, z + 2, "plank", "#c9a476")
        self.put(1, depth, a0, a0 + 1, z, z + 2, "beam")
        self.put(1, depth, a1 - 1, a1, z, z + 2, "beam")
        self.put(depth, depth, a0, a1, z + 1, z + 2, "beam")
        self.put(1, 1, a0 + 1, a0 + 2, z - 2, z, "beam")                    # brackets
        self.put(1, 1, a1 - 2, a1 - 1, z - 2, z, "beam")
        for a in range(a0, a1):
            for p in range(1, depth + 1):
                r = rng.random()
                if r < 0.85:
                    self.v.set(*self.xyz(p, a, z + 2), "leaves", LEAF[rng.integers(0, len(LEAF))])
                    if rng.random() < 0.45:
                        self.v.set(*self.xyz(p, a, z + 3), "paint", FLOWERS[rng.integers(0, len(FLOWERS))])
                    elif rng.random() < 0.3:
                        self.v.set(*self.xyz(p, a, z + 3), "leaves", LEAF[rng.integers(0, len(LEAF))])
            if rng.random() < 0.55:                                          # trailing over the front
                for dz in range(int(rng.integers(1, 4))):
                    x, y, zz = self.xyz(depth + 1, a, z + 1 - dz)
                    if self.v.get(x, y, zz) is None:
                        self.v.set(x, y, zz, "leaves", LEAF[rng.integers(0, len(LEAF))])

    def leaf(self, a, z, rng, extra=0.0):
        """One vine leaf on the outermost surface of the wall at (a, z)."""
        for p in range(1, 5):
            x, y, zz = self.xyz(p, a, z)
            if self.v.get(x, y, zz) is None:
                bx, by, bz = self.xyz(p - 1, a, z)
                if self.v.get(bx, by, bz) in (None, "window", "glow"):
                    return
                self.v.set(x, y, zz, "leaves", LEAF[rng.integers(0, len(LEAF))])
                if rng.random() < extra:
                    x2, y2, z2 = self.xyz(p + 1, a, z)
                    if self.v.get(x2, y2, z2) is None:
                        self.v.set(x2, y2, z2, "leaves", LEAF[rng.integers(0, len(LEAF))])
                return

    def vine(self, a, z0, z1, rng, width=3, wander=2, extra=0.3):
        """A vine creeping up the wall from z0 to z1 around column a."""
        c = a
        for z in range(z0, z1):
            c = int(np.clip(c + rng.integers(-1, 2), a - wander, a + wander))
            w = int(rng.integers(1, width + 1))
            t = (z - z0) / max(1.0, float(z1 - z0))
            if t > 0.8 and w > 1:
                w -= 1
            for i in range(w):
                self.leaf(c + i - w // 2, z, rng, extra)


def hang(v, cells, rng, lo=1, hi=5, p=0.6):
    """Vines hanging down from under an eave: cells = [(x, y, ztop)], each gets a strand of lo..hi leaves below ztop."""
    for (x, y, zt) in cells:
        if rng.random() > p:
            continue
        for k in range(int(rng.integers(lo, hi + 1))):
            if v.get(x, y, zt - 1 - k) is None:
                v.set(x, y, zt - 1 - k, "leaves", LEAF[rng.integers(0, len(LEAF))])
            else:
                break


def corner(v, x, y, sx, sy, z0, z1, mat="post"):
    """A corner post standing one voxel proud on both faces. (x, y): the wall box corner (x0 or x1, y0 or y1)."""
    xa, xb = (x - 1, x + 2) if sx < 0 else (x - 2, x + 1)
    ya, yb = (y - 1, y + 2) if sy < 0 else (y - 2, y + 1)
    v.box(xa, ya, z0, xb, yb, z1, mat)


def plants(v, x0, y0, x1, y1, z, rng, p=0.5, flowers=0.4, tall=0.25):
    """A flower bed: low leaf clumps with flowers on the ground at height z."""
    for x in range(x0, x1):
        for y in range(y0, y1):
            if rng.random() > p or v.get(x, y, z) is not None or v.get(x, y, z - 1) is None:
                continue
            v.set(x, y, z, "leaves", LEAF[rng.integers(0, len(LEAF))])
            r = rng.random()
            if r < flowers:
                v.set(x, y, z + 1, "paint", FLOWERS[rng.integers(0, len(FLOWERS))])
            elif r < flowers + tall:
                v.set(x, y, z + 1, "leaves", LEAF[rng.integers(0, len(LEAF))])


def pot(v, x, y, z, rng, big=False):
    """A clay pot with a plant: its low corner at (x, y, z)."""
    s = 4 if big else 3
    v.box(x, y, z, x + s, y + s, z + (3 if big else 2), "paint", "#b4623a")
    v.box(x, y, z + (3 if big else 2), x + s, y + s, z + (4 if big else 3), "paint", "#c8744a")
    for i in range(s):
        for j in range(s):
            zt = z + (4 if big else 3)
            if 0 < i < s - 1 or 0 < j < s - 1 or rng.random() < 0.6:
                v.set(x + i, y + j, zt, "leaves", LEAF[rng.integers(0, len(LEAF))])
                if rng.random() < 0.5:
                    v.set(x + i, y + j, zt + 1, "paint" if rng.random() < 0.6 else "leaves",
                          FLOWERS[rng.integers(0, len(FLOWERS))] if rng.random() < 0.7 else "#b6d47a")


# ---------------------------------------------------------------------------------------------------- cloth

TREE = [
    "....TTT..TTT....",
    "..TTTTTTTTTTTT..",
    ".TTTTTTTTTTTTTT.",
    ".TTTTTTTTTTTTTT.",
    "TTTTTTTTTTTTTTTT",
    "TTTTTTTTTTTTTTTT",
    ".TTTTTTTTTTTTTT.",
    "TTTTTTTTTTTTTTTT",
    "TTTTTTTTTTTTTTTT",
    ".TTTTT.TT.TTTTT.",
    "..TTT..TT..TTT..",
    ".......TT.......",
    ".......TT.......",
    ".......TT.......",
    "......TTTT......",
    "....TTTTTTTT....",
    "..TTTT.TT.TTTT..",
]

SMALL_TREE = [
    ".TTTT.",
    "TTTTTT",
    "TT.TTT",
    "TTTTTT",
    ".TTTT.",
    "..TT..",
    "..TT..",
    ".TTTT.",
]


def big_banner(w=24, h=42, notch=7, border=2, name="banner"):
    """The hall's banner (1 voxel = 6.25 cm): 1.4 m wide, 2.5 m long, green with a gold border, a gold tree, a
    swallow tail and a rod across the top. Stands in the XZ plane; origin = middle of the top of the rod."""
    inside = np.zeros((h, w), bool)
    for j in range(h):
        for i in range(w):
            k = j - (h - notch)
            cut = k >= 0 and abs(i - (w - 1) / 2.0) < (k + 1) * (w / 2.0 - border - 1) / notch
            inside[j, i] = not cut
    field = inside.copy()
    for _ in range(border):                                   # wear the edge away: what is left is the green field
        pad = np.pad(field, 1)
        field = field & pad[:-2, 1:-1] & pad[2:, 1:-1] & pad[1:-1, :-2] & pad[1:-1, 2:]
    field[:border, :] = inside[:border, :] & field[border:border + 1, :]      # no gold band under the rod
    ex0, ey0 = (w - len(TREE[0])) // 2, 6
    v = Vox(w + 2, 2, h + 2, V.TEXEL, origin=((w + 2) / 2.0, 1, h + 2), name=name)
    for j in range(h):
        for i in range(w):
            if not inside[j, i]:
                continue
            col = "banner" if field[j, i] else ("gold_light" if (i + j) % 6 == 0 else "gold")
            pj, pi = j - ey0, i - ex0
            if field[j, i] and 0 <= pj < len(TREE) and 0 <= pi < len(TREE[pj]) and TREE[pj][pi] == "T":
                col = "gold_light" if (pj * 3 + pi) % 7 == 0 else "gold"
            elif field[j, i] and (i * 7 + j * 3) % 11 == 0:
                col = "banner_dark"
            elif field[j, i] and (i * 5 + j * 9) % 17 == 0:
                col = "banner_light"
            z = h - 1 - j
            v.box(i + 1, 0, z, i + 2, 1, z + 1, "paint", col)
    v.box(0, 0, h, w + 2, 2, h + 2, "plank")
    v.box(0, 0, h, 1, 2, h + 2, "gold")
    v.box(w + 1, 0, h, w + 2, 2, h + 2, "gold")
    v.hang()
    return v


def pennant(w=26, h=12, name="pennant"):
    """The tower's flag, flying to +X (6.25 cm voxels). Origin: bottom of the hoist."""
    v = Vox(w, 1, h, V.TEXEL, origin=(0, 0.5, 0), name=name)
    for i in range(w):
        for j in range(h):
            taper = (i / float(w)) * 2.0
            notch = i >= w - 6 and abs(j - (h - 1) / 2.0) < (i - (w - 7)) * 0.75
            if j < taper or j > h - 1 - taper or notch:
                continue
            border = j - 1 < taper or j + 1 > h - 1 - taper or i == w - 1 \
                or (i >= w - 7 and abs(j - (h - 1) / 2.0) < (i - (w - 8)) * 0.75 + 0.8)
            col = "gold" if border else ("banner_dark" if (i * 7 + j * 3) % 11 == 0 else "banner")
            pi, pj = i - 4, (h - 1 - j) - (h - len(SMALL_TREE)) // 2
            if not border and 0 <= pj < len(SMALL_TREE) and 0 <= pi < len(SMALL_TREE[pj]) and SMALL_TREE[pj][pi] == "T":
                col = "gold"
            if not border and 13 <= i <= 16 and abs(j - (h - 1) / 2.0) < 1.6:      # a gold roundel on the fly
                col = "gold"
            v.box(i, 0, j, i + 1, 1, j + 1, "paint", col)
    v.fly()
    return v


# ---------------------------------------------------------------------------------------------------- the hall

def check(v):
    """The things the scene builder relies on: the stairs are walkable and the way to the door is clear."""
    solid = v.m[SX - 8:SX + 8, :, :PZ + 20] > 0                 # the middle 2 m of the stairs, up to 2.5 m above the platform
    top = np.where(solid.any(axis=2), solid.shape[2] - np.argmax(solid[:, :, ::-1], axis=2), 0)
    rows = [int(top[:, y].max()) for y in range(0, 20)]
    flat = [int(top[:, y].min()) == int(top[:, y].max()) for y in range(0, 20)]
    want = [2] * 4 + [4] * 4 + [6] * 4 + [PZ] * 8               # 3 treads, then 1 m of clear landing, 2 m wide
    print("stairs profile (z of the walking surface per voxel row from y = -5.0 m):", rows)
    assert rows == want and all(flat), "the stairs or the landing are blocked"
    door = v.m[SX - 4:SX + 4, 20:25, PZ:24] > 0                # the doorway itself: 1 m wide, 2 m high, up to the leaves
    assert not door.any() and (v.m[SX - 4:SX + 4, 20:25, PZ - 1] > 0).all(), "the doorway is blocked"
    assert (v.m[SX - 10:SX + 10, 0, :2] > 0).all(), "the foot of the stairs must be at the front edge"

def build_townhall():
    rng = np.random.default_rng(1207)
    v = Vox(NX, NY, NZ, 0.125, origin=(OX, OY, 0), name="townhall", seed=7)

    # ------------------------------------------------------------------ 1. platform, stairs, posts
    v.box(1, 12, 0, 87, 79, PZ, "stone")
    for (x0, y0, x1, y1) in ((5, 17, 37, 36), (5, 36, 22, 40), (67, 17, 83, 36), (72, 36, 83, 56)):
        v.box(x0, y0, PZ - 1, x1, y1, PZ, "grass")                              # lawn
    K.stairs(v, SX - 10, 0, 0, 20, 3, "-y", run=4, rise=2)                      # 3 treads, the platform is the 4th
    for sx in (SX - 16, SX + 10):
        v.box(sx, 0, 0, sx + 6, 6, 10, "stone")                                 # end posts (lanterns go on top)
    for sx in (SX - 14, SX + 10):
        v.box(sx, 6, 0, sx + 4, 9, 8, "stone")                                  # stepped cheek walls
        v.box(sx, 9, 0, sx + 4, 14, 11, "stone")
    for cx in (1, 81):
        v.box(cx, 12, 0, cx + 6, 18, 13, "stone")                               # front corner posts (lanterns)
    for (x0, y0, x1, y1, h) in ((1, 28, 5, 32, 10), (1, 46, 5, 50, 11), (1, 60, 5, 64, 10), (1, 74, 6, 79, 12),
                                (28, 75, 32, 79, 10), (44, 75, 48, 79, 11), (82, 74, 87, 79, 12),
                                (83, 30, 87, 34, 10), (83, 48, 87, 52, 11), (83, 62, 87, 66, 10),
                                (14, 12, 18, 16, 10), (26, 12, 30, 16, 11), (72, 12, 76, 16, 10)):
        v.box(x0, y0, PZ, x1, y1, h, "stone")                                   # raised rim blocks

    # ------------------------------------------------------------------ 2. ground floor of stone
    GF = 26                                                                     # top of the ground floor
    v.box(6, 40, PZ, 22, 64, GF, "stone")                                       # left wing
    v.box(22, 36, PZ, 72, 68, GF, "stone")                                      # main block
    v.box(38, 24, PZ, 66, 36, GF, "stone")                                      # front cross wing (door)
    v.box(56, 56, PZ, 76, 76, GF, "stone")                                      # tower
    v.box(12, 62, PZ, 22, 71, 20, "stone")                                      # chimney breast
    v.box(13, 62, 20, 21, 70, GF, "stone")
    for (x0, y0, x1, y1) in ((6, 40, 22, 64), (22, 36, 72, 68), (38, 24, 66, 36), (56, 56, 76, 76), (12, 62, 22, 71)):
        v.box(x0 - 1, y0 - 1, PZ, x1 + 1, y1 + 1, PZ + 3, "stone")              # footing, wider than the walls

    before = v.m.copy()
    v.chunky("stone", p=0.32, seed=3)
    added = (v.m > 0) & (before == 0)
    bump = added[:, :, PZ] & (v.m[:, :, PZ + 1] == 0)                           # keep the platform top flat to walk on
    v.m[:, :, PZ][bump] = 0
    v.clear(SX - 10, 0, 0, SX + 10, 12, 40)                                     # the stairs stay clean and walkable
    K.stairs(v, SX - 10, 0, 0, 20, 3, "-y", run=4, rise=2)
    v.clear(SX - 10, 12, PZ, SX + 10, 24, 40)
    for i in range(4):                                                          # darker risers so every step reads
        v.box(SX - 10, i * 4, max(0, i * 2 - 2), SX + 10, i * 4 + 1, i * 2 + 1, "stone", "#c4bcb2")

    # ------------------------------------------------------------------ 3. upper floor, roofs
    v.box(6, 40, GF, 22, 64, 40, "plaster", PLASTER)
    v.box(22, 36, GF, 72, 68, 41, "plaster", PLASTER)
    v.box(38, 24, GF, 66, 36, 37, "plaster", PLASTER)

    gable(v, 2, 22, 36, 68, 36, ridge="x", barge=(True, False))                 # wing: ridge top 54
    fill_under(v, 6, 40, 22, 64, 40)
    main_top = gable(v, 18, 76, 32, 72, 37, ridge="x")                          # main: ridge top 59
    fill_under(v, 22, 36, 72, 68, 41)
    gable(v, 20, 52, 34, 70, 33, ridge="y", barge=(True, False))                # cross gable over the door: 55
    fill_under(v, 38, 24, 66, 36, 37)

    # ------------------------------------------------------------------ 4. tower shaft and chimney (through the roofs)
    TR = 70                                                                     # underside of the tower's rim
    v.box(56, 56, GF, 76, 76, 52, "stone")
    v.box(55, 55, 45, 77, 77, 47, "stone")                                      # string course
    v.box(13, 62, GF, 21, 70, 66, "stone")
    v.box(12, 61, 66, 22, 71, 70, "stone")                                      # chimney crown
    v.box(11, 60, 67, 23, 72, 69, "stone")
    v.box(15, 64, 70, 19, 68, 73, "stone", "#b8b0a8")                           # flue
    v.chunky("stone", p=0.32, seed=5, region=(0, 0, GF, NX, NY, NZ))
    v.box(16, 65, 72, 18, 67, 73, "paint", "black")
    v.box(56, 56, 52, 76, 76, TR, "plaster", PLASTER)                           # the tower's timber storey

    # tower: rim, stepped pyramid, cap, pole
    v.box(52, 52, TR, 80, 80, TR + 3, "plank", BARGE[1])
    for k in range(7):                                                          # the rim reads as separate blocks
        for (x0, y0, x1, y1) in ((52 + 4 * k, 52, 56 + 4 * k, 53), (52 + 4 * k, 79, 56 + 4 * k, 80),
                                 (52, 52 + 4 * k, 53, 56 + 4 * k), (79, 52 + 4 * k, 80, 56 + 4 * k)):
            if k % 2 == 0:
                v.box(x0, y0, TR, x1, y1, TR + 4, "plank", BARGE[0])
    for (cx, cy) in ((54, 54), (76, 54), (54, 76), (76, 76), (65, 54), (65, 76), (54, 65), (76, 65)):
        v.box(cx, cy, TR - 2, cx + 2, cy + 2, TR, "beam")                       # corbels under the rim
    for (i, (a, zl, zh)) in enumerate(((55, TR + 3, TR + 7), (58, TR + 7, TR + 11), (61, TR + 11, TR + 14))):
        v.box(a, a, zl, 132 - a, 132 - a, zh, "roof")                           # steep stepped pyramid
    v.box(63, 63, TR + 14, 69, 69, TR + 16, "plank", BARGE[0])
    v.box(64, 64, TR + 16, 68, 68, TR + 17, "plank", BARGE[1])
    v.box(65, 65, TR + 17, 67, 67, TR + 25, "post", "#f0c890")
    v.box(65, 65, TR + 24, 67, 67, TR + 26, "gold")                             # top of the pole: 12.0 m

    # ------------------------------------------------------------------ 5. timber frames
    f_wing_s = Face(v, "y", 40, -1)
    f_wing_w = Face(v, "x", 6, -1)
    f_wing_n = Face(v, "y", 63, 1)
    f_main_s = Face(v, "y", 36, -1)
    f_main_n = Face(v, "y", 67, 1)
    f_main_e = Face(v, "x", 71, 1)
    f_main_w = Face(v, "x", 22, -1)
    f_cross_s = Face(v, "y", 24, -1)
    f_cross_w = Face(v, "x", 38, -1)
    f_cross_e = Face(v, "x", 65, 1)
    f_tow_s = Face(v, "y", 56, -1)
    f_tow_n = Face(v, "y", 75, 1)
    f_tow_w = Face(v, "x", 56, -1)
    f_tow_e = Face(v, "x", 75, 1)

    def storey(f, a0, a1, z0, z1, posts=(), plate=True, belt=True):
        if belt:
            f.timber(a0, a1, z0, z0 + 2, "beam", proud=2)                       # the beam the upper floor sits on
        if plate:
            f.timber(a0, a1, z1 - 2, z1, "beam")
        for a in posts:
            f.timber(a, a + 2, z0, z1, "post")

    # wing
    storey(f_wing_s, 6, 22, GF, 40)
    storey(f_wing_n, 6, 13, GF, 40, posts=(9,))
    storey(f_wing_w, 40, 64, GF, 40, posts=(46, 56))
    f_wing_w.timber(40, 64, 40, 42, "beam", proud=2)                            # tie beam of the gable
    f_wing_w.timber(51, 53, 42, 54, "post")
    f_wing_w.brace(45, 42, 5, 1)
    f_wing_w.brace(58, 42, 5, -1)
    # main
    storey(f_main_s, 22, 38, GF, 41, posts=(33,))
    storey(f_main_s, 66, 72, GF, 41)
    storey(f_main_n, 22, 56, GF, 41, posts=(25, 36, 38, 51))
    storey(f_main_e, 36, 56, GF, 41, posts=(41, 50))
    f_main_e.timber(36, 56, 41, 43, "beam", proud=2)
    f_main_e.timber(47, 49, 43, 58, "post")
    f_main_e.timber(55, 57, 43, 58, "post")
    f_main_e.brace(41, 43, 5, 1)
    storey(f_main_w, 36, 40, GF, 41)
    storey(f_main_w, 64, 68, GF, 41)
    f_main_w.timber(36, 68, 41, 60, "post")                                     # the gable above the wing roof: boarded
    # cross wing
    storey(f_cross_s, 38, 66, GF, 37, posts=(45, 57), plate=False)
    f_cross_s.timber(38, 66, 37, 39, "beam", proud=2)
    f_cross_s.timber(51, 53, 39, 54, "post")
    f_cross_s.brace(42, 39, 5, 1)
    f_cross_s.brace(61, 39, 5, -1)
    storey(f_cross_w, 24, 36, GF, 37, posts=(29,))
    storey(f_cross_e, 24, 36, GF, 37, posts=(29,))
    # tower
    for f in (f_tow_s, f_tow_n, f_tow_w, f_tow_e):
        storey(f, 56, 76, 52, TR)
        f.brace(58, 54, 4, 1)
        f.brace(73, 54, 4, -1)
    # corner posts: stone plinth below, post above
    for (x, y, sx, sy, zt) in ((6, 40, -1, -1, 40), (6, 64, -1, 1, 40), (22, 36, -1, -1, 41), (22, 68, -1, 1, 41),
                               (72, 36, 1, -1, 41), (38, 24, -1, -1, 37), (66, 24, 1, -1, 37)):
        corner(v, x, y, sx, sy, GF, zt)
        for k, z in enumerate(range(PZ, GF, 3)):                                # quoins: big corner stones
            if k % 2 == 0:
                corner(v, x, y, sx, sy, z, min(GF, z + 3), "stone")
    for (x, y, sx, sy) in ((56, 56, -1, -1), (76, 56, 1, -1), (56, 76, -1, 1), (76, 76, 1, 1)):
        corner(v, x, y, sx, sy, 52, TR)

    # ------------------------------------------------------------------ 6. the door at the top of the stairs
    v.clear(SX - 8, 21, PZ, SX + 8, 26, 27)
    v.box(SX - 8, 22, PZ, SX - 5, 26, 26, "post")                               # heavy door posts
    v.box(SX + 5, 22, PZ, SX + 8, 26, 26, "post")
    v.box(SX - 9, 21, PZ, SX - 4, 26, PZ + 2, "stone")
    v.box(SX + 4, 21, PZ, SX + 9, 26, PZ + 2, "stone")
    v.box(SX - 9, 21, 24, SX + 9, 26, 27, "beam")                               # lintel
    v.box(SX - 8, 21, 27, SX + 8, 23, 28, "plank")
    v.box(SX - 5, 25, PZ, SX + 5, 26, 24, "plank")                              # the leaves
    v.box(SX - 5, 24, 24, SX + 5, 26, 24, "beam")
    for z in (PZ + 2, 21):
        v.box(SX - 5, 25, z, SX + 5, 26, z + 1, "metal")
    v.box(SX - 4, 25, 17, SX - 1, 26, 20, "window")
    v.box(SX + 1, 25, 17, SX + 4, 26, 20, "window")
    v.box(SX - 3, 25, 17, SX - 2, 26, 20, "beam")
    v.box(SX + 2, 25, 17, SX + 3, 26, 20, "beam")
    v.box(SX - 2, 24, 14, SX - 1, 25, 16, "gold")
    v.box(SX + 1, 24, 14, SX + 2, 25, 16, "gold")
    for sx in (SX - 13, SX + 9):                                                # stone blocks beside the door
        v.box(sx, 20, PZ, sx + 4, 24, PZ + 6, "stone")
        v.box(sx, 21, PZ + 6, sx + 4, 24, PZ + 9, "stone")
    v.chunky("stone", p=0.5, seed=9, region=(SX - 13, 20, PZ, SX + 13, 24, PZ + 9))
    v.clear(SX - 4, 12, PZ, SX + 4, 25, 24)                                     # the way in stays clear

    # ------------------------------------------------------------------ 7. windows and flower boxes
    f_wing_s.win(11, 14, 6, 8)
    f_wing_s.win(11, 29, 6, 6)
    f_wing_s.flowerbox(9, 19, 26, rng)
    f_main_s.win(25, 14, 6, 8)
    f_main_s.win(25, 29, 6, 6)
    f_main_s.flowerbox(23, 33, 26, rng, depth=4)
    f_cross_s.win(40, 29, 4, 6, mullion=False)
    f_cross_s.win(60, 29, 4, 6, mullion=False)
    f_cross_w.win(28, 15, 4, 6, mullion=False)
    f_cross_e.win(28, 15, 4, 6, mullion=False)
    f_cross_e.win(28, 29, 4, 5, mullion=False)
    f_main_e.win(43, 14, 6, 8)
    f_main_e.win(43, 29, 6, 6)
    f_main_e.flowerbox(41, 51, 26, rng)
    f_main_e.win(50, 46, 4, 5, mullion=False)
    f_main_n.win(28, 14, 6, 8)
    f_main_n.win(42, 14, 6, 8)
    f_main_n.win(28, 29, 6, 6)
    f_main_n.win(42, 29, 6, 6)
    f_main_n.flowerbox(40, 50, 26, rng)
    f_wing_w.win(49, 14, 6, 8)
    f_wing_w.win(49, 30, 6, 6)
    f_wing_w.flowerbox(47, 57, 27, rng)
    f_wing_w.win(50, 45, 4, 4, mullion=False)
    for f in (f_tow_s, f_tow_n, f_tow_w, f_tow_e):
        f.win(64, 60, 4, 7, mullion=False)
    f_tow_e.win(65, 16, 2, 7, sill=False, mullion=False)                        # slits in the stone shaft
    f_tow_e.win(65, 36, 2, 7, sill=False, mullion=False)
    f_tow_n.win(65, 16, 2, 7, sill=False, mullion=False)
    f_tow_n.win(65, 36, 2, 7, sill=False, mullion=False)

    # ------------------------------------------------------------------ 8. lanterns
    for sx in (SX - 13, SX + 13):
        K.lantern(v, sx, 3, 10, 4)                                              # on the stair end posts
    K.lantern(v, 4, 15, 13, 4)                                                  # on the platform's front corners
    K.lantern(v, 84, 15, 13, 4)
    for x in (SX - 11, SX + 10):
        v.clear(x - 1, 21, 21, x + 3, 24, 28)
        K.wall_lantern(v, x, 24, 27)                                            # beside the door
    K.wall_lantern(v, 71, 53, 24, out=(1, 0))                                   # east wall
    K.wall_lantern(v, 36, 67, 24, out=(0, 1))                                   # back wall
    K.wall_lantern(v, 6, 44, 24, out=(-1, 0))                                   # wing's end

    # ------------------------------------------------------------------ 9. banner brackets (the banner itself is joined on)
    for x in (SX - 9, SX + 7):
        v.box(x, 17, 47, x + 2, 24, 49, "beam")
        v.box(x, 17, 49, x + 2, 19, 50, "gold")

    # ------------------------------------------------------------------ 10. vines, moss, flowers
    f_main_s.vine(35, PZ, 37, rng, width=4, wander=2, extra=0.45)               # the big one in the corner by the door wing
    f_cross_w.vine(34, PZ, 34, rng, width=3, wander=1, extra=0.3)
    f_cross_s.vine(64, PZ, 36, rng, width=3, wander=1, extra=0.35)              # right of the door
    f_cross_e.vine(26, PZ, 30, rng, width=3, wander=1)
    f_wing_s.vine(20, PZ, 30, rng, width=2, wander=1)
    f_wing_w.vine(42, PZ, 26, rng, width=3, wander=1)
    f_main_n.vine(53, PZ, 34, rng, width=3, wander=2, extra=0.3)
    f_main_n.vine(24, PZ, 24, rng, width=2, wander=1)
    f_tow_e.vine(59, PZ, 46, rng, width=4, wander=2, extra=0.35)
    f_tow_n.vine(72, PZ, 30, rng, width=3, wander=2)
    f_main_e.vine(38, PZ, 22, rng, width=2, wander=1)
    Face(v, "y", 12, -1).vine(22, 1, PZ + 1, rng, width=4, wander=3)            # on the platform's front
    Face(v, "y", 12, -1).vine(70, 0, PZ + 1, rng, width=3, wander=2)
    Face(v, "x", 1, -1).vine(38, 1, PZ + 1, rng, width=4, wander=3)
    Face(v, "x", 86, 1).vine(42, 1, PZ + 1, rng, width=4, wander=3)
    Face(v, "y", 78, 1).vine(38, 1, PZ + 1, rng, width=4, wander=3)
    # hanging from the eaves
    hang(v, [(x, 31, 37) for x in range(31, 35)], rng, 1, 4, 0.6)
    hang(v, [(x, 31, 37) for x in range(70, 76)], rng, 1, 5, 0.6)
    hang(v, [(x, 35, 36) for x in range(3, 10)], rng, 1, 3, 0.5)
    hang(v, [(69, y, 33) for y in range(21, 32)], rng, 1, 5, 0.5)
    hang(v, [(34, y, 33) for y in range(21, 30)], rng, 1, 4, 0.4)
    hang(v, [(x, 72, 37) for x in range(22, 54)], rng, 1, 4, 0.3)
    hang(v, [(76, y, 37) for y in range(33, 40)], rng, 1, 4, 0.5)
    hang(v, [(x, 51, TR) for x in range(53, 62)], rng, 1, 3, 0.4)
    hang(v, [(80, y, TR) for y in range(66, 80)], rng, 1, 4, 0.4)
    # moss and paler tiles on the roofs, moss on the stone tops
    v.tint("roof", "#dfeaa6", p=0.16, seed=4, cell=2)
    v.tint("roof", "#b9c98e", p=0.12, seed=8, cell=2)
    top = v.exposed("+z")
    v.where(top & v.mask("roof") & (V.noise3(v.n, 6, 21) > 0.655), "moss")
    walk = np.zeros(v.n, bool)
    walk[SX - 10:SX + 10, 0:24, :] = True                                       # the stairs and the way in stay bare stone
    v.where(top & v.mask("stone") & ~walk & (V.noise3(v.n, 6, 5) > 0.58), "mossy_stone")
    # flower beds along the walls and the rim
    plants(v, 7, 38, 22, 40, PZ, rng, 0.6)
    plants(v, 23, 33, 34, 36, PZ, rng, 0.65)
    plants(v, 67, 26, 71, 35, PZ, rng, 0.5)
    plants(v, 73, 37, 76, 55, PZ, rng, 0.5)
    plants(v, 6, 18, 12, 20, PZ, rng, 0.5)
    plants(v, 31, 17, 37, 19, PZ, rng, 0.45)
    plants(v, 78, 19, 83, 26, PZ, rng, 0.4)
    plants(v, 23, 69, 54, 70, PZ, rng, 0.35)

    # ------------------------------------------------------------------ 11. props on the platform
    pot(v, 40, 21, PZ + 9, rng)                                                 # pots on the stone blocks by the door
    v.stamp(K.crate(6), 35, 21, PZ)
    v.stamp(K.barrel(), 33, 28, PZ)
    v.stamp(K.crate(7), 28, 21, PZ)
    v.stamp(K.crate(5), 28, 21, PZ + 7, rot=1)
    v.stamp(K.barrel(), 20, 21, PZ)
    pot(v, 62, 21, PZ + 9, rng)
    pot(v, 69, 21, PZ, rng, big=True)
    v.stamp(K.crate(6), 78, 31, PZ)
    v.stamp(K.barrel(), 79, 40, PZ)
    pot(v, 74, 30, PZ, rng)
    v.stamp(K.barrel(), 80, 70, PZ)                                             # behind the tower
    v.stamp(K.crate(6), 51, 74, PZ)
    v.stamp(K.crate(5), 44, 72, PZ)
    v.stamp(K.barrel(), 26, 73, PZ)
    pot(v, 2, 52, PZ, rng)
    v.stamp(K.crate(6), 4, 69, PZ)

    check(v)
    cloth = big_banner().at(mx(SX), my(19.5), 49 * 0.125)
    flag = pennant().at(mx(67), my(66), 88.5 * 0.125)   # hoist on the pole
    return V.join([v, cloth, flag], "SM_TownHall")


# ---------------------------------------------------------------------------------------------------- main

VIEWS = {
    #  name       az    el  sun_az
    "village": (28.0, 32.0, -60.0),
    "ref": (-32.0, 30.0, -120.0),
    "front": (0.0, 22.0, -140.0),
    "back": (152.0, 30.0, 110.0),
    "backleft": (-140.0, 30.0, -60.0),
    "top": (20.0, 62.0, -120.0),
    "east": (96.0, 14.0, 150.0),
    "west": (-96.0, 14.0, -150.0),
    "eye": (14.0, 6.0, -140.0),
}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    views = list(VIEWS)
    if "--views" in argv:
        views = argv[argv.index("--views") + 1].split(",")
    V.reset_scene()
    ob = build_townhall()
    print("SM_TownHall: %d voxel faces" % ob["voxel_faces"])
    if "--no-export" not in argv:
        V.export_gltf(ob)
    if "--no-render" in argv:
        return
    for name in views:
        az, el, sun = VIEWS[name]
        V.reset_scene()
        build_townhall()
        path = os.path.join(V.PREVIEWS, "townhall_%s.png" % name)
        try:
            V.render(path, target=(0.3, 0.0, 4.9), az=az, el=el, dist=36, lens=70, res=(1100, 1100), samples=40,
                     sun_az=sun)
        except RuntimeError as e:                             # the GPU is shared with other jobs: fall back to the CPU
            import bpy
            print("GPU render failed (%s), rendering on the CPU" % str(e).splitlines()[0])
            bpy.context.scene.cycles.device = "CPU"
            bpy.ops.render.render(write_still=True)
            print("rendered", path)


if __name__ == "__main__":
    main()
