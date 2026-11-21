"""SM_Castle: the small stone keep of References/castle.png.

Layout (12.5 cm voxels, grid 112 x 88 = 14 x 11 m, mesh origin = centre of the footprint at ground level):
  front (-Y)   steps y 0..12 (foot at y = -5.5 m, centred on x = 0), porch with the gate, gatehouse tower behind it
  corners      four turrets; low crenellated curtain walls between the front turrets and the porch
  behind       the hall, green gable roof with its ridge along X
  left (-X)    canvas awning over crates, sacks and barrels;  right front: a work table with a barrel

Run:  Blender -b --factory-startup --python Tools/blender/assets/castle.py -- [--no-render] [--views front,back]
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import voxlib as V
import voxkit as K
from voxlib import Vox

import math
import time

import bpy
from voxmats import IDS

VOX = 0.125
NX, NY, NZ = 112, 88, 96
OX, OY = 56, 44                      # the voxel that becomes the mesh origin
ROOF_LO, ROOF_HI, ROOF_Z, ROOF_STEPS = 20, 86, 35, 11

WALL = "brick"
BLOCK = "stone"
WOOD = "plank"                       # the orange timber of the picture
DARK = "beam"                        # darker accents
POST = "plank"
ROOF_TINT = "#f4ccb4"
DOOR_TINT = "#b89878"
CANVAS = "#efe2b4"
IVY_TINTS = (None, "#e4f29a", "#c4e08a", "#f0f6b0", None)

K.EMBLEMS["tree_big"] = [
    "....TTTTTT....",
    "..TTTTTTTTTT..",
    ".TTTTTTTTTTTT.",
    "TTTT.TTTT.TTTT",
    "TTTTTTTTTTTTTT",
    "TT.TTTTTTTT.TT",
    "TTTTTT.TTTTTTT",
    ".TTTTTTTTTTTT.",
    "..TTT.TT.TTT..",
    "......TT......",
    "......TT......",
    "......TT......",
    ".....TTTT.....",
    "....TTTTTT....",
]
K.EMBLEMS["tree_small"] = [
    ".TTTT.",
    "TTTTTT",
    "TTTTTT",
    "TTTTTT",
    ".TTTT.",
    "..TT..",
    "..TT..",
    ".TTTT.",
]


# ---------------------------------------------------------------------------------------------------- helpers

class Face:
    """Paint on a wall face. axis 'y': the wall runs along X and its outer voxel layer is y = plane; axis 'x' likewise.
    out: +1 / -1, the way the face looks. Boxes are given along the wall (a), in height (z) and in LAYERS (d):
    0 = the wall's surface layer, 1 = one voxel proud of it, -1 = one voxel into the wall. d0 <= d < d1."""

    def __init__(self, v, axis, plane, out):
        self.v, self.axis, self.plane, self.out = v, axis, plane, out

    def box(self, a0, a1, z0, z1, d0, d1, mat, color=None):
        p0, p1 = self.plane + self.out * d0, self.plane + self.out * (d1 - 1)
        lo, hi = min(p0, p1), max(p0, p1) + 1
        if self.axis == "y":
            self.v.box(a0, lo, z0, a1, hi, z1, mat, color)
        else:
            self.v.box(lo, a0, z0, hi, a1, z1, mat, color)


def arch_h(w, hs):
    """Column heights of a round arch w voxels wide whose straight sides are hs high."""
    r = w / 2.0
    return [hs + int(round(math.sqrt(max(0.0, r * r - (i + 0.5 - r) ** 2)))) for i in range(w)]


def arch_window(F, a0, z0, w=4, hs=5, t=1, frame=BLOCK, transom=True, mullion=False, sill=True):
    """A glowing round-headed window: stone surround one voxel proud, panes one voxel back, a wooden bar across."""
    ho, hi = arch_h(w + 2 * t, hs), arch_h(w, hs)
    for i, h in enumerate(ho):
        F.box(a0 - t + i, a0 - t + i + 1, z0 - t, z0 + h, 0, 2, frame)
    for i, h in enumerate(hi):
        F.box(a0 + i, a0 + i + 1, z0, z0 + h, 0, 3, None)
        F.box(a0 + i, a0 + i + 1, z0, z0 + h, -1, 0, "window")
    if mullion:
        F.box(a0 + w // 2 - 1, a0 + w // 2 + 1, z0, z0 + max(hi), 0, 1, DARK)
    if transom:
        F.box(a0, a0 + w, z0 + hs - 1, z0 + hs, 0, 1, DARK)
    if sill:
        F.box(a0 - t - 1, a0 + w + t + 1, z0 - t - 1, z0 - t, 0, 3, frame)


def slit(F, a0, z0, w=2, h=6):
    """An arrow slit with a warm light behind it."""
    F.box(a0 - 1, a0 + w + 1, z0 - 1, z0 + h + 1, 0, 2, BLOCK)
    F.box(a0, a0 + w, z0, z0 + h, 0, 3, None)
    F.box(a0, a0 + w, z0, z0 + h, -1, 0, "window")


def stone_tints(v, seed):
    """Block-to-block colour variation, so that the walls read as separate stones."""
    v.tint(WALL, "#f6ead8", p=0.30, seed=seed + 1, cell=4)
    v.tint(WALL, "#e2dcd2", p=0.14, seed=seed + 2, cell=4)
    v.tint(BLOCK, "#f2ece4", p=0.25, seed=seed + 3, cell=4)


def merlons(v, x0, y0, x1, y1, z0, z1, xs, ys, t=3, mat=BLOCK, sides="fblr"):
    for (a, b) in xs:
        if "f" in sides:
            v.box(x0 + a, y0, z0, x0 + b, y0 + t, z1, mat)
        if "b" in sides:
            v.box(x0 + a, y1 - t, z0, x0 + b, y1, z1, mat)
    for (a, b) in ys:
        if "l" in sides:
            v.box(x0, y0 + a, z0, x0 + t, y0 + b, z1, mat)
        if "r" in sides:
            v.box(x1 - t, y0 + a, z0, x1, y0 + b, z1, mat)


def quoins(v, x, y, z0, z1, sx, sy, mat=BLOCK):
    """Corner stones standing one voxel proud, long and short sides alternating. (x, y) is the corner voxel just
    OUTSIDE the wall corner's two faces meet; sx, sy = the outward directions (+1 / -1)."""
    k = 0
    for z in range(z0, z1, 4):
        lx, ly = (7, 4) if k % 2 == 0 else (4, 7)
        xa, xb = (x - sx * lx, x + sx) if sx > 0 else (x - 1, x + lx)
        ya, yb = (y - sy * ly, y + sy) if sy > 0 else (y - 1, y + ly)
        v.box(min(xa, xb), min(ya, yb), z, max(xa, xb), max(ya, yb), min(z + 4, z1), mat)
        k += 1


def mirrored(t, mx=False, my=False):
    """A copy of a grid mirrored in X and / or Y (its footprint must sit symmetrically in the grid)."""
    c = Vox(t.n[0], t.n[1], t.n[2], t.voxel, origin=t.origin, name=t.name, seed=t.seed)
    m, col = t.m, t.c
    if mx:
        m, col = m[::-1], col[::-1]
    if my:
        m, col = m[:, ::-1], col[:, ::-1]
    c.m, c.c = m.copy(), col.copy()
    return c


def vine(v, axis, out, a, z_top, z_bot, p_out, p_in, rng, spread=0.45, tints=IVY_TINTS):
    """A trailing strand of ivy on a face, from z_top down to z_bot. It hugs whatever is solid: for every height the
    leaf goes on the first empty voxel in front of the wall, searched from p_out (outside) to p_in."""
    leaf, glow, win = IDS["leaves"], IDS["glow"], IDS["window"]
    step = 1 if p_in > p_out else -1

    def put(aa, zz):
        if not (0 <= zz < v.n[2]):
            return
        prev = None
        for p in range(p_out, p_in + step, step):
            x, y = (aa, p) if axis == "y" else (p, aa)
            if not (0 <= x < v.n[0] and 0 <= y < v.n[1]):
                continue
            m = v.m[x, y, zz]
            if m != 0 and m != leaf:
                if m in (glow, win):
                    return
                if prev is not None:
                    v.set(prev[0], prev[1], zz, "leaves", tints[rng.integers(len(tints))])
                return
            prev = (x, y)

    drift = 1 if rng.random() < 0.5 else -1
    for z in range(z_top, z_bot - 1, -1):
        put(a, z)
        if rng.random() < spread:
            put(a + (1 if rng.random() < 0.5 else -1), z)
        if rng.random() < 0.07:                                    # a clump of leaves
            s = 1 if rng.random() < 0.5 else -1
            for (da, dz) in ((s, 0), (s, 1), (2 * s, 0), (2 * s, 1), (s, -1), (3 * s, 0)):
                if rng.random() < 0.75:
                    put(a + da, z + dz)
        if rng.random() < 0.08:
            drift = -drift
        r = rng.random()
        if r < 0.30:
            a += drift
        elif r < 0.36:
            a -= drift


def hanging_lantern(v, x, y, z):
    """A tall iron lantern: its bottom centre at voxel (x, y, z), 10 voxels high, hung from above."""
    v.box(x - 1, y - 1, z, x + 1, y + 1, z + 1, DARK, "#9c8068")
    v.box(x - 3, y - 3, z + 1, x + 3, y + 3, z + 2, DARK, "#9c8068")
    v.box(x - 2, y - 2, z + 2, x + 2, y + 2, z + 7, "glow", "lantern")
    for dx in (x - 3, x + 2):
        for dy in (y - 3, y + 2):
            v.box(dx, dy, z + 2, dx + 1, dy + 1, z + 7, DARK, "#9c8068")
    v.box(x - 3, y - 3, z + 7, x + 3, y + 3, z + 8, DARK, "#9c8068")
    v.box(x - 2, y - 2, z + 8, x + 2, y + 2, z + 9, DARK, "#9c8068")
    v.box(x - 1, y - 1, z + 9, x + 1, y + 1, z + 10, DARK, "#9c8068")


def sack(v, x, y, z=0, color="#d0b888", rx=2.6, ry=2.3, rz=2.6):
    v.ellipsoid(x, y, z + rz - 0.4, rx, ry, rz, "wool", color)
    v.box(int(x) - 1, int(y) - 1, int(z + 2 * rz - 1), int(x) + 1, int(y) + 1, int(z + 2 * rz), "wool", "#b89c6c")


def tuft(v, x, y, rng, flower=None):
    if not (0 <= x < v.n[0] and 0 <= y < v.n[1]) or v.m[x, y, 0] != 0:
        return
    h = 1 + int(rng.random() < 0.5)
    tint = (None, "#e4f29a", "#c8e48c")[rng.integers(3)]
    v.box(x, y, 0, x + 1, y + 1, h, "leaves", tint)
    if flower:
        v.set(x, y, h, "paint", flower)


# ---------------------------------------------------------------------------------------------------- pieces

def build_turret(seed, with_banner_seat=True):
    """A corner turret, 18 x 18 voxels in plan, 50 high. Built as the FRONT-LEFT one: its outer faces are -X and -Y.
    Footprint = local 2..20 (a 2-voxel margin all round); origin at the footprint's low corner."""
    o = 2
    t = Vox(22, 22, 54, VOX, origin=(o, o, 0), name="turret", seed=seed)
    t.box(o, o, 0, o + 18, o + 18, 9, BLOCK)                       # wide footing of big blocks
    t.box(o + 1, o + 1, 9, o + 17, o + 17, 12, BLOCK)
    t.box(o + 2, o + 2, 12, o + 16, o + 16, 40, WALL)              # the shaft
    for (cx, cy, sx, sy) in ((o + 2, o + 2, 1, 1), (o + 15, o + 2, -1, 1), (o + 2, o + 15, 1, -1), (o + 15, o + 15, -1, -1)):
        for (dx, dy) in ((0, 0), (1, 0), (0, 1)):                  # round the shaft's corners off
            t.clear(cx + sx * dx, cy + sy * dy, 12, cx + sx * dx + 1, cy + sy * dy + 1, 40)
    for (cx, cy) in ((o, o), (o + 17, o), (o, o + 17), (o + 17, o + 17)):
        t.clear(cx, cy, 0, cx + 1, cy + 1, 9)
    t.box(o + 3, o + 3, 40, o + 15, o + 15, 44, WALL)
    t.chunky(BLOCK, p=0.4, seed=seed + 1)
    t.chunky(WALL, p=0.2, seed=seed + 2)
    stone_tints(t, seed)
    # the head: band on wooden corbels, crisp merlons, a sunk floor
    t.box(o, o, 40, o + 18, o + 18, 46, BLOCK)
    t.chunky(BLOCK, p=0.14, seed=seed + 3, region=(0, 0, 41, 22, 22, 45))
    iv = [(0, 4), (7, 11), (14, 18)]
    merlons(t, o, o, o + 18, o + 18, 46, 50, iv, iv, t=3)
    t.clear(o + 3, o + 3, 44, o + 15, o + 15, 54)
    t.box(o + 6, o + 8, 43, o + 11, o + 13, 44, "plank")          # trapdoor in the floor
    t.box(o + 6, o + 8, 43, o + 7, o + 13, 44, DARK)
    t.box(o + 10, o + 8, 43, o + 11, o + 13, 44, DARK)
    t.box(o + 8, o + 9, 43, o + 9, o + 10, 44, "metal", "iron")
    for a in (3, 12):                                              # corbels: two on every face
        for (x0, y0, x1, y1, ax) in ((o + a, o, o + a + 3, o + 2, "y-"), (o + a, o + 16, o + a + 3, o + 18, "y+"),
                                     (o, o + a, o + 2, o + a + 3, "x-"), (o + 16, o + a, o + 18, o + a + 3, "x+")):
            t.box(x0, y0, 38, x1, y1, 40, WOOD)
            if ax == "y-":
                t.box(x0, y0 + 1, 36, x1, y1, 38, WOOD)
            elif ax == "y+":
                t.box(x0, y0, 36, x1, y1 - 1, 38, WOOD)
            elif ax == "x-":
                t.box(x0 + 1, y0, 36, x1, y1, 38, WOOD)
            else:
                t.box(x0, y0, 36, x1 - 1, y1, 38, WOOD)
    if with_banner_seat:                                           # arms that carry the narrow banner's rod
        for a in (4, 12):
            t.box(o + a, o - 2, 38, o + a + 2, o, 40, WOOD)
            t.box(o + a, o - 2, 40, o + a + 2, o - 1, 41, DARK)
    slit(Face(t, "y", o + 2, -1), o + 8, 18, 2, 6)                 # front
    slit(Face(t, "x", o + 2, -1), o + 8, 24, 2, 6)                 # outer side
    return t


def build_roof():
    """The hall's stepped gable roof in a grid of its own (same size as the main one), stamped where there is air."""
    r = Vox(NX, NY, NZ, VOX, name="roof", seed=21)
    for i in range(ROOF_STEPS):
        lo, hi, z = ROOF_LO + 3 * i, ROOF_HI - 3 * i, ROOF_Z + 2 * i
        for (a, b) in ((lo, min(lo + 5, hi)), (max(hi - 5, lo), hi)):
            r.box(14, a, z, 98, b, z + 3, "roof", ROOF_TINT)
            r.box(11, a, z, 14, b, z + 4, "plank")                 # barge boards step up the gable ends
            r.box(98, a, z, 101, b, z + 4, "plank")
    r.box(14, ROOF_LO, ROOF_Z, 98, ROOF_LO + 1, ROOF_Z + 2, DARK)  # eave boards
    r.box(14, ROOF_HI - 1, ROOF_Z, 98, ROOF_HI, ROOF_Z + 2, DARK)
    top = ROOF_Z + 2 * (ROOF_STEPS - 1) + 3
    r.box(12, 51, top, 100, 55, top + 2, WOOD)
    r.box(14, 52, top + 2, 98, 54, top + 3, DARK)                     # ridge beam
    for x0 in (10, 98):                                            # king posts at the gable peaks
        r.box(x0, 51, top - 5, x0 + 4, 55, top + 6, POST)
        r.box(x0 - 0, 50, top + 6, x0 + 4, 56, top + 8, WOOD)
    r.scatter("roof", "moss", p=0.05, seed=4, direction="+z")
    for (x0, y0, x1, y1) in ((0, 0, 28, 31), (84, 0, NX, 31), (0, 69, 28, NY), (84, 69, NX, NY)):
        r.clear(x0, y0, 0, x1, y1, NZ)                             # the turrets stand in the corners
    return r


def make_flag(w=44, h=22):
    """The big swallow-tailed flag: green, gold edges, the gold tree. Flies to +X; a little wave in it."""
    f = Vox(w, 9, h + 10, V.TEXEL, origin=(0, 4.5, 5), name="flag")
    pat = K.EMBLEMS["tree_big"]
    ph, pw = len(pat), len(pat[0])
    for i in range(w):
        dy = int(round(1.7 * math.sin(i * 0.30 + 0.4) * min(1.0, i / 6.0)))
        dz = int(round(2.2 * math.sin(i / float(w) * math.pi * 1.5) * (i / float(w))))
        k = i - (w - 13)                                           # columns into the swallow tail
        for j in range(h):
            mid = abs(j - (h - 1) / 2.0)
            if k >= 0 and mid < (k + 1) * 0.62:
                continue
            edge = j <= 1 or j >= h - 2 or (k >= -1 and mid < (k + 3) * 0.62 + 0.8) or i == w - 1
            col = "gold" if edge else "banner"
            if edge and (i + j) % 4 == 0:
                col = "gold_dark"
            pi, pj = i - 5, (h - 1 - j) - (h - ph) // 2
            if not edge and 0 <= pj < ph and 0 <= pi < pw and pat[pj][pi] == "T":
                col = "gold_light" if (pi + pj) % 5 == 0 else "gold"
            elif not edge and (i * 7 + j * 3) % 11 == 0:
                col = "banner_dark"
            f.set(i, 4 + dy, 5 + j + dz, "paint", col)
    f.fly()
    return f


# ---------------------------------------------------------------------------------------------------- the castle

def build_castle():
    v = Vox(NX, NY, NZ, VOX, origin=(OX, OY, 0), name="castle", seed=7)
    rng = np.random.default_rng(12)

    # ---------------- 1. stone massing (everything that gets the dry-stone swelling)
    v.box(14, 22, 0, 98, 84, 35, WALL)                             # hall
    v.box(13, 21, 0, 99, 85, 5, BLOCK)
    for (a0, a1) in ((28, 40), (72, 84)):                          # curtain walls in front of the hall
        v.box(a0, 19, 0, a1, 22, 27, WALL)
        v.box(a0, 18, 0, a1, 22, 5, BLOCK)
        v.box(a0, 18, 27, a1, 22, 29, BLOCK)
    v.box(42, 12, 0, 70, 22, 37, WALL)                             # porch
    v.box(44, 22, 0, 68, 46, 59, WALL)                             # gatehouse tower
    quoins(v, 41, 11, 0, 36, -1, -1)
    quoins(v, 70, 11, 0, 36, 1, -1)
    v.box(41, 10, 37, 71, 22, 41, BLOCK)                           # porch band
    v.box(42, 20, 59, 70, 48, 66, BLOCK)                           # tower band
    for x0 in (42, 65):                                            # cheek blocks beside the steps
        v.box(x0, 6, 0, x0 + 5, 12, 11, BLOCK)
        v.box(x0, 1, 0, x0 + 5, 6, 6, BLOCK)
    for x0 in (36, 70):                                            # plinths of the timber posts
        v.box(x0, 13, 0, x0 + 6, 19, 9, BLOCK)
    for x0 in (44, 65):                                            # back buttresses
        v.box(x0, 84, 0, x0 + 4, 87, 18, BLOCK)
        v.box(x0, 84, 18, x0 + 4, 86, 22, BLOCK)
    # loose stone blocks at the foot of the walls
    for (x0, y0, sx, sy, sz) in ((32, 8, 5, 4, 4), (23, 6, 4, 4, 3), (36, 3, 4, 5, 3), (72, 3, 4, 4, 3), (104, 20, 4, 5, 3),
                                 (5, 20, 4, 4, 3), (104, 62, 5, 4, 4), (3, 70, 4, 4, 3), (96, 4, 5, 4, 3)):
        v.box(x0, y0, 0, x0 + sx, y0 + sy, sz, BLOCK)
    v.box(32, 8, 4, 36, 12, 8, BLOCK)

    v.chunky(BLOCK, p=0.36, seed=3, region=(0, 0, 0, NX, NY, 36))
    v.chunky(BLOCK, p=0.14, seed=3, region=(0, 0, 36, NX, NY, NZ))
    v.chunky(WALL, p=0.16, seed=5)
    stone_tints(v, 1)

    # crisp merlons on the curtain walls, the porch and the tower
    for (a, b) in ((28, 32), (80, 84)):
        v.box(a, 18, 29, b, 21, 33, BLOCK)
    merlons(v, 41, 10, 71, 22, 41, 46, [(0, 6), (12, 18), (24, 30)], [(0, 5), (8, 12)], t=3, sides="flr")
    t3 = [(0, 6), (11, 17), (22, 28)]
    merlons(v, 42, 20, 70, 48, 66, 72, t3, t3, t=4)

    v.clear(44, 13, 39, 68, 22, 47)                                # sunk floors behind the parapets
    v.clear(46, 24, 64, 66, 44, 74)

    # ---------------- 2. gable infill and roof
    for i in range(ROOF_STEPS):
        lo, hi, z = ROOF_LO + 3 * i, ROOF_HI - 3 * i, ROOF_Z + 2 * i
        if hi - 5 > lo + 5:
            v.box(14, lo + 5, z, 98, hi - 5, z + 2, WALL)
    for (x0, y0, x1, y1) in ((0, 0, 28, 31), (84, 0, NX, 31), (0, 69, 28, NY), (84, 69, NX, NY)):
        v.clear(x0, y0, 35, x1, y1, NZ)
    v.stamp(build_roof(), 0, 0, 0, overwrite=False)

    # ---------------- 3. steps and gate
    v.clear(47, 0, 0, 65, 12, 30)
    for i in range(4):
        v.box(47, 3 * i, 0, 65, 12, 2 * (i + 1), WALL)
    F = Face(v, "y", 12, -1)
    z0, w, hs, t, a0 = 8, 12, 12, 3, 50
    ho, hi_ = arch_h(w + 2 * t, hs), arch_h(w, hs)
    for i, h in enumerate(ho):                                     # voussoirs, one voxel proud
        a = a0 - t + i
        F.box(a, a + 1, z0, z0 + h, 0, 2, BLOCK, None if (i // 3) % 2 == 0 else "#e8e0d4")
    F.box(55, 57, z0 + max(hi_), z0 + max(ho) + 1, 0, 3, BLOCK)     # keystone
    for i, h in enumerate(hi_):
        a = a0 + i
        F.box(a, a + 1, z0, z0 + h, -2, 3, None)
        F.box(a, a + 1, z0, z0 + h, -3, -2, "post", DOOR_TINT if i % 2 == 0 else "#a88868")
    F.box(55, 57, z0, z0 + max(hi_), -3, -2, "post", "#7a6048")    # where the two leaves meet
    for zz in (z0 + 3, z0 + 11):                                   # strap hinges
        F.box(a0, a0 + 4, zz, zz + 1, -2, -1, "metal", "iron")
        F.box(a0 + w - 4, a0 + w, zz, zz + 1, -2, -1, "metal", "iron")
    for ra in (52, 57):                                            # ring handles
        F.box(ra, ra + 3, z0 + 6, z0 + 9, -2, -1, "metal", "iron")
        F.box(ra + 1, ra + 2, z0 + 7, z0 + 8, -2, -1, None)
        F.box(ra + 1, ra + 2, z0 + 9, z0 + 10, -2, -1, "metal", "iron")

    # lanterns either side of the gate, hanging from iron brackets
    for lx in (44, 68):
        hanging_lantern(v, lx, 8, 16)
        v.box(lx - 1, 7, 26, lx + 1, 12, 27, "metal", "iron")
        v.box(lx - 1, 10, 24, lx + 1, 12, 26, "metal", "iron")

    # ---------------- 4. porch woodwork, posts, banner seat
    for a in (43, 49, 60, 66):                                     # corbels under the porch parapet
        v.box(a, 10, 35, a + 3, 12, 37, WOOD)
        v.box(a, 11, 33, a + 3, 12, 35, WOOD)
    for y0 in (14, 18):
        v.box(40, y0, 35, 42, y0 + 3, 37, WOOD)
        v.box(70, y0, 35, 72, y0 + 3, 37, WOOD)
    for xp in (37, 71):                                            # the thick timber posts flanking the porch
        v.box(xp, 13, 9, xp + 4, 18, 31, POST)
        v.box(xp - 1, 12, 9, xp + 5, 19, 11, DARK)
        v.box(xp - 1, 12, 28, xp + 5, 19, 31, WOOD)
        v.box(xp - 3, 11, 31, xp + 7, 19, 35, WOOD)
        v.box(xp - 3, 11, 31, xp - 2, 19, 35, DARK)
        v.box(xp + 6, 11, 31, xp + 7, 19, 35, DARK)
        v.box(xp + 1, 19, 32, xp + 3, 22, 35, WOOD)
    for a in (48, 62):                                             # arms the big banner's rod rests on
        v.box(a, 8, 41, a + 2, 10, 43, WOOD)

    # ---------------- 5. tower: corner posts, corbel ring, window, flag pole
    for x0 in (43, 66):
        v.box(x0, 21, 41, x0 + 3, 24, 57, POST)
    v.box(43, 21, 57, 69, 47, 59, WOOD)
    for (x0, y0) in ((42, 20), (66, 20), (42, 44), (66, 44)):
        v.box(x0, y0, 54, x0 + 4, y0 + 4, 57, WOOD)
    for a in (54,):
        v.box(42, 32, 55, 44, 36, 57, WOOD)
        v.box(68, 32, 55, 70, 36, 57, WOOD)
        v.box(a, 46, 55, a + 4, 48, 57, WOOD)
    arch_window(Face(v, "y", 22, -1), 53, 47, w=6, hs=5, t=2, mullion=True)
    slit(Face(v, "x", 44, -1), 27, 46, 2, 6)
    slit(Face(v, "x", 67, 1), 27, 46, 2, 6)
    v.box(48, 37, 63, 54, 43, 64, "plank")                         # trapdoor on the tower top
    v.box(48, 37, 63, 49, 43, 64, DARK)
    v.box(53, 37, 63, 54, 43, 64, DARK)
    v.box(50, 39, 63, 52, 40, 64, "metal", "iron")
    v.box(54, 32, 64, 58, 36, 67, WOOD)                            # pole foot
    v.box(55, 33, 64, 57, 35, 93, POST)
    v.box(54, 32, 93, 58, 36, 95, WOOD)

    # ---------------- 6. windows
    Fc = Face(v, "y", 19, -1)
    arch_window(Fc, 30, 14, w=4, hs=5, t=1)
    arch_window(Fc, 78, 14, w=4, hs=5, t=1)
    Fr = Face(v, "x", 97, 1)                                       # right side
    arch_window(Fr, 40, 14, w=4, hs=5, t=1)
    arch_window(Fr, 60, 14, w=4, hs=5, t=1)
    K.window(v, "x", 97, 50, 41, w=6, h=7, out=1)
    Fl = Face(v, "x", 14, -1)                                      # left side (one under the awning) and its gable
    arch_window(Fl, 45, 13, w=4, hs=5, t=1)
    arch_window(Fl, 64, 14, w=4, hs=5, t=1)
    K.window(v, "x", 14, 50, 41, w=6, h=7, out=-1)
    Fb = Face(v, "y", 83, 1)                                       # back: a postern door between two windows
    arch_window(Fb, 34, 14, w=4, hs=5, t=1)
    arch_window(Fb, 74, 14, w=4, hs=5, t=1)
    bw, bhs = 8, 10
    bho, bhi = arch_h(bw + 4, bhs), arch_h(bw, bhs)
    for i, h in enumerate(bho):
        Fb.box(50 + i, 51 + i, 0, 2 + h, 0, 2, BLOCK)
    for i, h in enumerate(bhi):
        Fb.box(52 + i, 53 + i, 2, 2 + h, 0, 3, None)
        Fb.box(52 + i, 53 + i, 2, 2 + h, -1, 0, "post", DOOR_TINT if (i // 2) % 2 == 0 else "#a88868")
    Fb.box(52, 60, 5, 6, 0, 1, "metal", "iron")
    Fb.box(52, 60, 11, 12, 0, 1, "metal", "iron")
    Fb.box(58, 59, 8, 10, 0, 1, "metal", "iron")
    v.box(50, 85, 0, 62, 88, 2, BLOCK)                             # its doorstep
    K.wall_lantern(v, 64, 84, 20, out=(0, 1))
    for a in (30, 40, 70, 80):                                     # rafter ends under the back eave
        v.box(a, 84, 33, a + 2, 86, 35, WOOD)

    # ---------------- 7. turrets
    for (sx, sy, mx, my, seed) in ((10, 13, False, False, 31), (84, 13, True, False, 47), (10, 69, False, True, 59), (84, 69, True, True, 71)):
        v.stamp(mirrored(build_turret(seed, with_banner_seat=not my), mx, my), sx, sy, 0)

    # ---------------- 8. the awning on the left side
    v.box(12, 32, 26, 14, 62, 28, WOOD)                            # ledger on the wall
    for y0 in (32, 60):
        v.box(1, y0, 0, 3, y0 + 2, 21, POST)
        v.box(0, y0 - 1, 0, 4, y0 + 3, 2, BLOCK)
        for x in range(3, 12):                                     # rafters
            zz = 21 + ((x - 1) * 6) // 12
            v.box(x, y0, zz - 1, x + 1, y0 + 2, zz + 1, WOOD)
    v.box(1, 31, 20, 3, 63, 22, WOOD)
    for x in range(0, 14):
        for y in range(31, 63):
            zz = 22 + (x * 6) // 13
            if 3 <= x <= 10 and 37 <= y < 57:
                zz -= 1
            v.box(x, y, zz, x + 1, y + 1, zz + 1, "wool", CANVAS if (x + y // 3) % 5 else "#e2d29c")
    for y in range(31, 63):                                        # scalloped valance
        v.box(0, y, 20 if (y // 2) % 2 == 0 else 21, 1, y + 1, 22, "wool", "#e2d29c")
    # the stores under it
    v.stamp(K.crate(6), 9, 37, 0)
    v.stamp(K.crate(6), 9, 44, 0)
    v.stamp(K.crate(5), 9, 40, 6)
    v.stamp(K.crate(6), 4, 56, 0)
    v.stamp(K.barrel(), 9, 56, 0)
    v.stamp(K.barrel(), 5, 36, 0)
    sack(v, 5.5, 43.5)
    sack(v, 4.5, 48.5, color="#c8ac78")
    sack(v, 9.5, 50.0, color="#d8c090")
    sack(v, 6.5, 46.0, z=4, color="#d0b888", rx=2.4, ry=2.2, rz=2.2)

    # ---------------- 9. clutter at the front and the right
    v.stamp(K.barrel(), 30, 13, 0)                                 # by the left curtain
    v.box(30, 12, 8, 31, 14, 9, "leaves")
    v.stamp(K.crate(6), 38, 8, 0)
    v.stamp(K.crate(5), 38, 8, 6)
    v.stamp(K.crate(5), 27, 8, 0)
    # work table with a barrel and a crate, right of the gate
    for (tx, ty) in ((79, 4), (91, 4), (79, 9), (91, 9)):
        v.box(tx, ty, 0, tx + 2, ty + 2, 6, DARK)
    v.box(78, 3, 6, 94, 12, 8, "plank")
    v.box(79, 5, 3, 93, 6, 4, WOOD)
    v.stamp(K.barrel(), 83, 8, 8)
    v.stamp(K.crate(5), 90, 8, 8)
    v.stamp(K.crate(6), 86, 7, 0)
    v.stamp(K.barrel(), 104, 36, 0)                                # right side
    v.stamp(K.crate(6), 104, 44, 0)
    v.stamp(K.barrel(), 38, 86, 0) if False else None

    # ---------------- 10. ivy
    for (a, zt, zb) in ((33, 36, 0), (31, 34, 20), (34, 30, 0), (29, 27, 0), (36, 33, 22)):   # left of the porch
        vine(v, "y", -1, a, zt, zb, 0, 30, rng)
    for (a, zt, zb) in ((80, 36, 24), (77, 36, 30)):                          # right post and eave
        vine(v, "y", -1, a, zt, zb, 0, 30, rng)
    for (a, zt, zb) in ((47, 66, 56), (62, 64, 58), (15, 45, 34), (21, 30, 12), (95, 44, 36)):   # tower and turrets
        vine(v, "y", -1, a, zt, zb, 0, 40, rng, spread=0.35)
    for (a, zt, zb) in ((36, 33, 0), (38, 30, 4), (66, 34, 10), (45, 40, 20)):               # right side wall
        vine(v, "x", 1, a, zt, zb, NX - 1, 80, rng)
    for (a, zt, zb) in ((66, 33, 0), (68, 28, 0)):                                           # left side wall
        vine(v, "x", -1, a, zt, zb, 0, 30, rng)
    for (a, zt, zb) in ((30, 34, 6), (32, 30, 0), (68, 34, 12), (80, 33, 0), (82, 28, 0), (20, 40, 22), (92, 44, 30)):   # back
        vine(v, "y", 1, a, zt, zb, NY - 1, 60, rng)

    # ---------------- 11. flowers and grass at the foot
    flowers = ("flower_yellow", "flower_yellow", "flower_yellow", "flower_white", "flower_orange", "flower_pink", None, None, None)
    zones = [(9, 0, 42, 12, 40), (70, 0, 104, 12, 40), (103, 12, 112, 86, 34), (0, 12, 9, 30, 12), (0, 67, 9, 88, 12),
             (0, 0, 9, 12, 8), (104, 0, 112, 12, 8)]
    for (x0, y0, x1, y1, n) in zones:
        for _ in range(n):
            x, y = int(rng.integers(x0, x1)), int(rng.integers(y0, y1))
            tuft(v, x, y, rng, flowers[rng.integers(len(flowers))])
    for (bx, by) in ((14, 6), (98, 5), (107, 28), (107, 52), (4, 26), (75, 2)):      # little flowering bushes
        v.ellipsoid(bx, by, 1.2, 2.6, 2.4, 2.2, "leaves", noise=0.4, noise_scale=3, seed=bx)
        for _ in range(5):
            x, y = bx + int(rng.integers(-2, 3)), by + int(rng.integers(-2, 3))
            if 0 <= x < NX and 0 <= y < NY:
                col = np.argwhere(v.m[x, y, :8] == IDS["leaves"])
                if len(col):
                    v.set(x, y, int(col.max()) + 1, "paint", flowers[rng.integers(5)])

    # ---------------- banners and the flag (6.25 cm pixel-art grids)
    def w2m(x, y, z):
        return ((x - OX) * VOX, (y - OY) * VOX, z * VOX)

    parts = [v]
    parts.append(K.banner("tree_big", w=22, h=28, notch=6, name="banner_gate").at(*w2m(56, 9.5, 43)))
    parts.append(K.banner("tree_small", w=10, h=24, notch=4, name="banner_l").at(*w2m(19, 11.5, 40)))
    parts.append(K.banner("tree_small", w=10, h=24, notch=4, name="banner_r").at(*w2m(93, 11.5, 40)))
    parts.append(make_flag().at(*w2m(57, 34, 82)))
    ob = V.join(parts, "SM_Castle")
    drop_ground_faces(ob)
    return ob


def drop_ground_faces(ob):
    """Remove the faces that lie on the ground looking down (nobody can ever see them)."""
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    dead = [f for f in bm.faces if f.normal.z < -0.9 and all(abs(vt.co.z) < 1e-4 for vt in f.verts)]
    n = len(dead)
    bmesh.ops.delete(bm, geom=dead, context="FACES")
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()
    ob["voxel_faces"] = int(ob.get("voxel_faces", 0)) - n // 2
    return n


VIEWS = {
    #            target            az    el   dist  lens  sun_az sun_el
    "front":   ((0.0, 0.0, 5.2),  -14,  14,  50.0, 70.0, -150, 34),
    "village": ((0.0, 0.0, 4.2),   28,  32,  50.0, 70.0, -150, 34),
    "left":    ((0.0, 0.0, 4.2),  -70,  24,  50.0, 70.0, -120, 34),
    "back":    ((0.0, 0.0, 4.2),  205,  28,  50.0, 70.0,   40, 34),
    "right":   ((0.0, 0.0, 4.2),  105,  22,  50.0, 70.0,  120, 34),
    "gate":    ((0.0, -3.5, 3.0),  -8,  10,  20.0, 70.0, -150, 34),
    "top":     ((0.0, 0.0, 4.0),    0,  80,  44.0, 70.0, -150, 40),
}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    render = "--no-render" not in argv
    views = list(VIEWS)
    if "--views" in argv:
        views = argv[argv.index("--views") + 1].split(",")
    samples = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 48
    V.reset_scene()
    ob = build_castle()
    co = np.zeros(len(ob.data.vertices) * 3, np.float32)
    ob.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    print("SM_Castle bounds", co.min(axis=0), co.max(axis=0), "faces", ob["voxel_faces"])
    V.export_gltf(ob)
    if not render:
        return
    for name in views:
        target, az, el, dist, lens, sun_az, sun_el = VIEWS[name]
        for attempt in range(6):                                   # the GPU is shared: wait and try again if it is full
            V.reset_scene()
            build_castle()
            try:
                V.render(os.path.join(V.PREVIEWS, "castle_%s.png" % name), target=target, az=az, el=el, dist=dist,
                         lens=lens, sun_az=sun_az, sun_el=sun_el, samples=samples)
                break
            except RuntimeError as e:
                print("render failed (%s), attempt %d" % (str(e).splitlines()[0][:80], attempt + 1))
                time.sleep(25)


main()
