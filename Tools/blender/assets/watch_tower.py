"""watch_tower: the watch tower of the voxel village, made after References/Remake/watchtower.png.

  SM_WatchTower   a tall square stone tower that steps in twice on its way up (belt courses, corner quoins, stepped
                  stone piles round the corners, vines), a glowing window on two floors of every face, a timber-framed
                  door with a hood, a lantern, stone steps and a cobble path on the front, two tree banners beside it;
                  heavy timber brackets carry an overhanging lookout platform (timber rim and railing with iron studs,
                  stone corner piers, a telescope and crates), four posts hold a hipped roof of green tiles with
                  stacked timber hips, a dormer on every side and a lantern under every corner; a pennant on top.

Pivot: the centre of the tower's footprint, ground z = 0. The door faces -Y (the front). One mesh; the banners and the
flag are cloth (they sway in game). Every lantern is a lump of 'glow' voxels, so it becomes a lamp in the engine.

Run:  Blender -b --factory-startup --python Tools/blender/assets/watch_tower.py -- [--no-render] [--views=a,b] [--samples N] [--cpu]
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import math
import numpy as np
import voxlib as V
import voxkit as K
from voxlib import Vox
from voxmats import IDS

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
NO_RENDER = "--no-render" in ARGS
VIEWS = [n for a in ARGS if a.startswith("--views=") for n in a.split("=", 1)[1].split(",")]
SAMPLES = int(ARGS[ARGS.index("--samples") + 1]) if "--samples" in ARGS else 32
CPU = "--cpu" in ARGS
TASK = "watch_tower"

VX = 0.125
NX, NY, NZ = 96, 104, 168            # 12 x 13 x 21 m
OX, OY = 48, 58                      # the voxel that becomes (0, 0)

WALL = "brick"
BLOCK = "stone"
WOOD = "plank"                       # the orange timber of the picture
DARK = "beam"
STEEL = "#6e7279"
IVY_TINTS = (None, "#e4f29a", "#c4e08a", "#f0f6b0", None)
WOOD_A, WOOD_B = "#f4cfa4", "#dcae80"       # the two shades of the orange timber

# heights (voxels of 12.5 cm)
Z_BASE, Z_MID, Z_TOP = 36, 60, 80    # the shaft steps in at 4.5 m and 7.5 m and ends under the platform at 10 m
H_BASE, H_MID, H_UP = 24, 22, 20     # half widths of the three stages (6 / 5.5 / 5 m square)
FLOOR = 84                           # top of the platform floor (10.5 m)
PLAT = 28                            # half width of the floor slab; the rim reaches 32 (8 m across)
EAVE = 116                           # bottom of the roof tiles (14.5 m)
RAIL = 9                             # railing height above the floor (1.125 m): archers shoot over it
BEAM = FLOOR + 24                    # underside of the lowest roof timber (the tie beams): 3.0 m of headroom
FREE = 24                            # half width of the floor kept completely clear (6 x 6 m); posts stand outside it
ROOF_H, RUN, RISE, STEPS = 32, 6, 4, 5
SILL = 4                             # door sill / landing height

TREE_BIG = [
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


def half_at(z):
    return H_BASE if z < Z_BASE else (H_MID if z < Z_MID else H_UP)


# ====================================================================================================== helpers

class Side:
    """One of the four faces of the tower. Boxes are given as a (along the face, left to right seen from outside,
    0 = the middle), d (distance from the tower's axis, outwards) and z. r = 0 front (-Y), 1 east, 2 north, 3 west."""

    def __init__(self, v, r, coarse=False, dz=0):
        self.v, self.r, self.coarse, self.dz = v, r, coarse, dz

    def xy(self, a0, a1, d0, d1):
        r = self.r
        if r == 0:
            return OX + a0, OX + a1, OY - d1, OY - d0
        if r == 1:
            return OX + d0, OX + d1, OY + a0, OY + a1
        if r == 2:
            return OX - a1, OX - a0, OY + d0, OY + d1
        return OX - d1, OX - d0, OY - a1, OY - a0

    def box(self, a0, a1, d0, d1, z0, z1, mat, color=None):
        x0, x1, y0, y1 = self.xy(a0, a1, d0, d1)
        z0, z1 = z0 + self.dz, z1 + self.dz
        if self.coarse:                                    # the 25 cm grid: same coordinates, all of them even
            cbox(self.v, x0, y0, z0, x1, y1, z1, mat, color)
        else:
            self.v.box(x0, y0, z0, x1, y1, z1, mat, WOOD_A if (mat == WOOD and color is None) else color)

    def stud(self, a, d, z):
        self.box(a, a + 1, d, d + 1, z, z + 1, "paint", STEEL)


def cbox(c, x0, y0, z0, x1, y1, z1, mat, color=None):
    """Fill a box of the coarse (25 cm) grid given in main-grid (12.5 cm) voxel coordinates (all even)."""
    for q in (x0, y0, z0, x1, y1, z1):
        assert q % 2 == 0, (x0, y0, z0, x1, y1, z1)
    if mat == WOOD and color is None:
        color = WOOD_A
    c.box(x0 // 2, y0 // 2, z0 // 2, x1 // 2, y1 // 2, z1 // 2, mat, color)


def csquare(c, h, z0, z1, mat, color=None):
    cbox(c, OX - h, OY - h, z0, OX + h, OY + h, z1, mat, color)


def drop_bottom(ob, zs=(0.0,), hidden=()):
    """Delete the faces lying flat at one of the heights zs and facing down (never seen). hidden: (z, sign, half)
    = flat faces at height z looking up (+1) or down (-1) within +/- half metres of the axis, which are buried
    between the two voxel grids (the top of the shaft under the platform slab) and can go as well."""
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    doomed = [f for f in bm.faces if f.normal.z < -0.5 and any(all(abs(vt.co.z - z) < 1e-4 for vt in f.verts) for z in zs)]
    for (z, sign, half) in hidden:
        doomed += [f for f in bm.faces if f.normal.z * sign > 0.5 and
                   all(abs(vt.co.z - z) < 1e-4 and abs(vt.co.x) <= half + 1e-4 and abs(vt.co.y) <= half + 1e-4 for vt in f.verts)]
    doomed = list(set(doomed))
    n = len(doomed)
    bmesh.ops.delete(bm, geom=doomed, context="FACES")
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()
    ob["voxel_faces"] = int(ob.get("voxel_faces", 0)) - n // 2
    return ob


def vine(v, axis, a, z_top, z_bot, p_out, p_in, rng, spread=0.45, tints=IVY_TINTS):
    """A trailing strand of ivy on a face (after castle.py), from z_top down to z_bot. It hugs whatever is solid: for
    every height the leaf goes on the first empty voxel in front of the wall, searched from p_out (outside) to p_in."""
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
                if m in (glow, win, IDS["paint"]):
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
        if rng.random() < 0.09:                                    # a clump of leaves
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


def hanging_lantern(v, x, y, z, glow_h=5):
    """An iron-framed lantern hung from above: bottom centre at voxel (x, y, z) (it spans x-3 .. x+3)."""
    cap = "#8a6c54"
    v.box(x - 1, y - 1, z, x + 1, y + 1, z + 1, DARK, cap)
    v.box(x - 3, y - 3, z + 1, x + 3, y + 3, z + 2, DARK, cap)
    v.box(x - 2, y - 2, z + 2, x + 2, y + 2, z + 2 + glow_h, "glow", "lantern")
    for dx in (x - 3, x + 2):
        for dy in (y - 3, y + 2):
            v.box(dx, dy, z + 2, dx + 1, dy + 1, z + 2 + glow_h, DARK, cap)
    t = z + 2 + glow_h
    v.box(x - 3, y - 3, t, x + 3, y + 3, t + 1, DARK, cap)
    v.box(x - 2, y - 2, t + 1, x + 2, y + 2, t + 2, DARK, cap)
    return t + 2


def crate(size=7, name="crate"):
    """A plank crate with a timber frame and iron corner plates. Origin: bottom centre (low corner for odd sizes)."""
    v = Vox(size, size, size, VX, origin=(size // 2, size // 2, 0), name=name)
    v.box(0, 0, 0, size, size, size, WOOD, WOOD_A)
    v.frame(0, 0, 0, size, size, size, DARK)
    for x in (0, size - 1):
        for y in (0, size - 1):
            for z in (0, size - 1):
                v.set(x, y, z, "metal", "iron")
    return v


def hay_bale(v, x, y, z, sx=7, sy=6, sz=6):
    v.box(x, y, z, x + sx, y + sy, z + sz, "hay")
    for xx in (x + 1, x + sx - 2):
        v.box(xx, y, z, xx + 1, y + sy, z + sz, "hay", "#d8b060")


def make_flag(w=40, h=20):
    """The swallow-tailed pennant: green, gold edges, the gold tree. Flies to +X; a little wave in it (after castle.py)."""
    f = Vox(w, 9, h + 10, V.TEXEL, origin=(0, 4.5, 5), name="flag")
    pat = TREE_BIG
    ph, pw = len(pat), len(pat[0])
    for i in range(w):
        dy = int(round(1.7 * math.sin(i * 0.30 + 0.4) * min(1.0, i / 6.0)))
        dz = int(round(2.2 * math.sin(i / float(w) * math.pi * 1.5) * (i / float(w))))
        k = i - (w - 12)                                           # columns into the swallow tail
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


# ====================================================================================================== the stone shaft

def shaft(v):
    for (h, z0, z1) in ((H_BASE, 0, Z_BASE), (H_MID, Z_BASE, Z_MID), (H_UP, Z_MID, Z_TOP)):
        v.box(OX - h, OY - h, z0, OX + h, OY + h, z1, WALL)
    for r in range(4):
        S = Side(v, r)
        # corner quoins: alternating long and short stones, the corner itself two voxels proud
        for (h, z0, z1) in ((H_BASE, 0, Z_BASE), (H_MID, Z_BASE, Z_MID), (H_UP, Z_MID, Z_TOP)):
            k = 0
            for z in range(z0, z1, 4):
                la, ld = (11, 7) if k % 2 == 0 else (7, 11)
                col = (None, "#f2ece4", "#e6ded2")[(k + r) % 3]
                S.box(-(h + 1), -(h + 1) + la, h + 1 - ld, h + 1, z, min(z + 4, z1), BLOCK, col)
                S.box(-(h + 2), -(h + 2) + 7, h + 2 - 7, h + 2, z, min(z + 4, z1), BLOCK, col)
                k += 1
        # belt courses where the shaft steps in: a proud band with blocks standing out of it, a smaller course above
        for (h, zt) in ((H_BASE, Z_BASE), (H_MID, Z_MID)):
            S.box(-(h + 2), h + 2, h - 1, h + 1, zt - 3, zt, BLOCK)
            for a in range(-(h - 6), h - 6, 8):
                S.box(a, a + 4, h - 1, h + 2, zt - 4, zt, BLOCK, "#efe8dc")
            S.box(-(h + 2), -(h - 6), h - 6, h + 3, zt - 4, zt + 1, BLOCK)             # the corner block of the belt
            S.box(-(h - 1), h - 1, h - 3, h - 1, zt, zt + 2, BLOCK, "#e8e0d4")
        # a corbel course under the platform
        S.box(-(H_UP + 1), H_UP + 1, H_UP - 1, H_UP + 1, Z_TOP - 3, Z_TOP, BLOCK)
        # stepped piles of stone blocks round the foot of each corner (the left one of this face)
        c0 = H_BASE + 2
        heights = ((26, 19, 13, 7), (22, 16, 10, 5), (27, 20, 12, 6), (24, 17, 11, 6))[r]
        for k, hgt in enumerate(heights):
            ext = 3 * (k + 1)
            sz = ext + 9
            S.box(-(c0 + ext), -(c0 + ext) + sz, c0 + ext - sz, c0 + ext, 0, hgt, BLOCK, (None, "#efe8dc")[k % 2])


def stone_finish(v):
    v.tint(WALL, "#eadcc6", p=1.0)
    v.tint(WALL, "#f8ecd8", p=0.28, seed=41, cell=4)
    v.tint(WALL, "#d8c8b0", p=0.18, seed=42, cell=4)
    v.tint(BLOCK, "#f6ecdc", p=0.35, seed=43, cell=4)
    v.chunky(WALL, cell=4, depth=1, p=0.08, seed=5)
    v.chunky(BLOCK, cell=4, depth=1, p=0.13, seed=6)
    v.scatter(BLOCK, "mossy_stone", p=0.07, seed=7, direction="+z")
    v.scatter(WALL, "mossy_stone", p=0.008, seed=8)


def windows(v):
    for r in range(4):
        S = Side(v, r)
        for z0 in (41, 64):
            h = half_at(z0)
            S.box(-6, 6, h, h + 3, z0 - 3, z0 + 11, None)                   # clear swollen stones in front of it
            S.box(-3, 3, h - 2, h, z0, z0 + 8, None)                         # the recess
            S.box(-3, 3, h - 3, h - 2, z0, z0 + 8, "window")
            S.box(-1, 1, h - 3, h - 2, z0, z0 + 8, DARK)                     # mullion and transom
            S.box(-3, 3, h - 3, h - 2, z0 + 4, z0 + 5, DARK)
            S.box(-4, -3, h - 2, h + 1, z0, z0 + 8, WOOD)                    # jambs
            S.box(3, 4, h - 2, h + 1, z0, z0 + 8, WOOD)
            S.box(-5, 5, h - 2, h + 1, z0 + 8, z0 + 10, WOOD)                # lintel
            S.box(-5, 5, h - 2, h + 2, z0 - 2, z0, WOOD, WOOD_B)             # sill
            S.box(-6, 6, h - 1, h + 1, z0 + 10, z0 + 11, BLOCK)              # a stone hood over the lintel


# ====================================================================================================== the door (front)

def door(v):
    S = Side(v, 0)
    h = H_BASE
    z0, z1 = SILL, SILL + 20
    S.box(-14, 14, h, h + 12, 0, 32, None)                                   # clear swollen stones / pile blocks
    # the stone porch piers either side, stepped at the top
    for s in (-1, 1):
        a0, a1 = (-13, -8) if s < 0 else (8, 13)
        S.box(a0, a1, h, h + 4, 0, 18, BLOCK)
        S.box(a0 + (1 if s < 0 else 0), a1 - (0 if s < 0 else 1), h, h + 3, 18, 22, BLOCK, "#efe8dc")
        S.box(a0, a1, h + 4, h + 9, 0, SILL + 2, BLOCK, "#efe8dc")         # cheek blocks beside the steps
        S.box(a0, a1, h + 4, h + 7, SILL + 2, SILL + 5, BLOCK)
    # the opening
    S.box(-5, 5, h - 4, h + 4, z0, z1, None)
    S.box(-5, 5, h - 5, h - 4, z0, z1, WOOD, "#c8a078")                      # the leaf, deep in the wall
    for zz in (z0 + 4, z1 - 5):
        S.box(-5, 5, h - 4, h - 3, zz, zz + 1, "metal", "iron")
    S.box(2, 3, h - 4, h - 3, z0 + 9, z0 + 11, "gold")
    # timber frame: posts, an arched head, a lintel and a stepped hood
    for (a0, a1) in ((-8, -5), (5, 8)):
        S.box(a0, a1, h - 2, h + 3, z0, z1, WOOD, WOOD_B)
    S.box(-5, -3, h - 2, h + 2, z1 - 2, z1, DARK)
    S.box(3, 5, h - 2, h + 2, z1 - 2, z1, DARK)
    S.box(-5, -4, h - 2, h + 2, z1 - 4, z1 - 2, DARK)
    S.box(4, 5, h - 2, h + 2, z1 - 4, z1 - 2, DARK)
    S.box(-10, 10, h - 2, h + 5, z1, z1 + 3, WOOD)
    S.box(-7, 7, h - 2, h + 6, z1 + 3, z1 + 6, WOOD, WOOD_B)
    S.box(-4, 4, h - 2, h + 6, z1 + 6, z1 + 8, WOOD)
    for a in (-9, 8):
        S.stud(a, h + 5, z1 + 1)
    for a in (-6, 5):
        S.stud(a, h + 6, z1 + 4)
    # the lantern hanging in the doorway
    S.box(-1, 1, h + 1, h + 3, z1 - 1, z1, "metal", "iron")
    S.box(-3, 3, h - 1, h + 5, z1 - 2, z1 - 1, DARK, "#8a6c54")
    S.box(-2, 2, h, h + 4, z1 - 5, z1 - 2, "glow", "lantern")
    for a in (-3, 2):
        for d in (h - 1, h + 4):
            S.box(a, a + 1, d, d + 1, z1 - 5, z1 - 2, DARK, "#8a6c54")
    S.box(-3, 3, h - 1, h + 5, z1 - 6, z1 - 5, DARK, "#8a6c54")
    # landing and steps
    S.box(-8, 8, h - 4, h + 4, 0, SILL, BLOCK, "#efe8dc")
    S.box(-8, 8, h + 4, h + 7, 0, SILL - 1, BLOCK)
    S.box(-8, 8, h + 7, h + 10, 0, SILL - 2, BLOCK, "#efe8dc")
    # the cobble path
    rng = np.random.default_rng(12)
    for d in range(h + 10, OY):
        w0 = 7 + int(rng.integers(0, 2)) + (1 if d > h + 22 else 0)
        w1 = 7 + int(rng.integers(0, 2)) + (1 if d > h + 22 else 0)
        S.box(-w0, w1, d, d + 1, 0, 1, "cobble", "#e8b488")
    v.tint("cobble", "#d89a6c", p=0.3, seed=3, cell=2)
    # rod brackets for the banners
    for s in (-1, 1):
        for a in (s * 17 - 6, s * 17 + 5):
            S.box(a, a + 1, h + 1, h + 4, Z_BASE - 2, Z_BASE - 1, "metal", "iron")


# ====================================================================================================== brackets, platform

def brackets(v, c):
    h = H_UP
    for r in range(4):
        S, C = Side(v, r), Side(c, r, True)
        for a0 in (-14, 10):
            C.box(a0, a0 + 4, h, h + 2, 58, 76, "post")                               # the post on the wall
            C.box(a0, a0 + 4, h, 30, 74, 78, WOOD)                                    # the arm under the platform
            for k in range(4):                                                        # the stepped strut
                C.box(a0, a0 + 4, h + 2 + 2 * k, h + 4 + 2 * k, 62 + 2 * k, 68 + 2 * k, WOOD, WOOD_B)
            C.box(a0, a0 + 4, h + 2, h + 6, 58, 62, WOOD, WOOD_B)                     # a foot block (proud of the belt course)
            S.stud(a0 + 1, h + 6, 60)
            S.stud(a0 + 2, h + 4, 65)
            S.stud(a0 - 1 if a0 < 0 else a0 + 4, 26, 76)
        C.box(-30, -24, 24, 30, 74, 78, WOOD, WOOD_B)                                 # a block under each platform corner


def platform(v, c):
    csquare(c, PLAT, 78, FLOOR, WOOD, "#ecd8bc")
    for r in range(4):
        S, C = Side(v, r), Side(c, r, True)
        C.box(-32, 32, PLAT, 32, 78, FLOOR, WOOD)                                     # the rim beam
        for a in range(-20, 21, 8):
            S.stud(a, 32, 81)
        # stone corner pier (the left one of this face)
        S.box(-34, -27, 27, 34, 76, FLOOR + RAIL + 2, BLOCK)
        # railing: low enough to shoot over, nothing above it but the corner posts
        rt = FLOOR + RAIL
        S.box(-27, 27, 29, 31, rt - 2, rt, WOOD)
        S.box(-27, 27, 30, 31, rt - 6, rt - 4, WOOD, WOOD_B)
        for a in (-14, -1, 12):
            S.box(a, a + 2, 29, 32, FLOOR, rt + 1, WOOD, "#d8b48c")
            S.stud(a, 32, rt - 1)
        # roof post (the left one of this face) at the very corner of the floor, and a tie beam from post to post.
        # No knee braces and no foot blocks: the floor inside the posts is clear and so is the view over the rail.
        C.box(-(FREE + 4), -FREE, FREE, FREE + 4, FLOOR, BEAM, WOOD, "#d8b48c")
        C.box(-(FREE + 4), FREE + 4, FREE, FREE + 4, BEAM, BEAM + 4, WOOD)
        S.stud(-(FREE + 2), FREE + 4, BEAM + 2)
        S.stud(FREE + 1, FREE + 4, BEAM + 2)
        C.box(-30, 30, FREE - 2, 30, BEAM + 4, BEAM + 6, DARK)                        # the plate the roof sits on
    v.chunky(BLOCK, cell=4, depth=1, p=0.2, seed=9, region=(0, 0, 76, NX, NY, FLOOR + RAIL + 2))


def lookout_things(v):
    """A telescope and crates, tucked into the strip between the corner posts and the rail (outside the free floor)."""
    S = Side(v, 0)
    d0 = FREE + 1
    # telescope on a stand by the front right post, lying along the rail
    S.box(16, 18, d0, d0 + 2, FLOOR, FLOOR + 11, DARK)
    S.box(14, 20, d0, d0 + 2, FLOOR, FLOOR + 2, DARK)
    S.box(15, 19, d0, d0 + 2, FLOOR + 2, FLOOR + 4, DARK)
    S.box(16, 18, d0, d0 + 2, FLOOR + 10, FLOOR + 11, "metal", "iron")
    S.box(11, 22, d0, d0 + 2, FLOOR + 11, FLOOR + 13, "gold")
    S.box(10, 11, d0, d0 + 2, FLOOR + 11, FLOOR + 13, "metal", "iron")
    S.box(20, 23, d0 - 1, d0 + 3, FLOOR + 10, FLOOR + 14, "gold", "#f0c860")
    S.box(23, 24, d0, d0 + 2, FLOOR + 11, FLOOR + 13, "paint", "#3a3440")
    # crates by the front left post
    x0, x1, y0, y1 = S.xy(-23, -18, FREE, FREE + 5)
    v.stamp(crate(5), x0 + 2, y0 + 2, FLOOR)
    x0, x1, y0, y1 = S.xy(-17, -13, FREE + 1, FREE + 5)
    v.stamp(crate(4), x0 + 2, y0 + 2, FLOOR)


# ====================================================================================================== the roof

def roof(v, c):
    """Everything big is in the coarse grid (25 cm voxels: a quarter of the faces, and the tiles, hips and dormers
    cull each other); the studs, window panes and lanterns are fine voxels standing on it."""
    csquare(c, 30, EAVE - 2, EAVE, WOOD)                                                   # the boarded ceiling
    for i in range(STEPS):
        h = ROOF_H - RUN * i
        csquare(c, h, EAVE + RISE * i, EAVE + RISE * (i + 1), "roof")
    top = EAVE + RISE * STEPS
    dz = EAVE - 110                                         # the heights below were drawn for an eave at 110
    for r in range(4):
        S, C = Side(v, r, dz=dz), Side(c, r, True, dz=dz)
        C.box(-34, 34, 30, 34, 106, 112, WOOD)                                        # the eave: a deep timber fascia
        for a in range(-20, 21, 8):
            S.stud(a, 34, 109)
        # hips: one timber block per step, climbing the corner (the left corner of this face)
        for i in range(STEPS):
            h = ROOF_H - RUN * i
            zl = 110 + RISE * i
            C.box(-(h + 2), -(h - 6), h - 6, h + 2, zl - 2, zl + RISE + 2, WOOD, (WOOD_A, WOOD_B)[i % 2])
            if i < STEPS - 1:                                                         # a smaller block between two steps
                C.box(-(h - 2), -(h - 8), h - 8, h - 2, zl + 2, zl + RISE + 4, WOOD, (WOOD_B, WOOD_A)[i % 2])
        C.box(-36, -28, 28, 36, 104, 116, WOOD)                                       # the big block on the eave corner
        S.stud(-32, 36, 110)
        S.box(-37, -36, 31, 32, 110, 111, "paint", STEEL)                            # its stud on the side face
        # dormer: timber front with a glowing window, a stepped little gable
        C.box(-8, 8, 22, 30, 114, 122, WOOD, WOOD_B)
        S.box(-3, 3, 30, 31, 116, 121, "window")
        S.box(-1, 1, 30, 31, 116, 121, DARK)
        S.box(-3, 3, 30, 31, 118, 119, DARK)
        S.box(-5, -3, 30, 32, 115, 122, DARK)
        S.box(3, 5, 30, 32, 115, 122, DARK)
        S.box(-6, 6, 30, 33, 114, 116, WOOD)
        S.box(-5, 5, 30, 32, 121, 122, DARK)
        for (wa, zl, zh, back) in ((10, 122, 124, 16), (6, 124, 126, 16), (2, 126, 128, 10)):
            C.box(-wa, wa, back, 28, zl, zh, "roof")
            C.box(-wa, wa, 28, 32, zl, zh, WOOD)
        C.box(-12, -8, 28, 32, 118, 122, WOOD)                                        # the gable's foot blocks
        C.box(8, 12, 28, 32, 118, 122, WOOD)
        S.stud(-10, 32, 120)
        S.stud(9, 32, 120)
        S.stud(0, 32, 126)
    # the cap: a stone block, the pole
    v.box(OX - 4, OY - 4, top, OX + 4, OY + 4, top + 7, BLOCK)
    v.box(OX - 5, OY - 5, top, OX + 5, OY + 5, top + 3, BLOCK, "#efe8dc")
    v.box(OX - 1, OY - 1, top + 7, OX + 1, OY + 1, top + 27, "post")
    v.box(OX - 2, OY - 2, top + 7, OX + 2, OY + 2, top + 9, DARK)
    v.box(OX - 2, OY - 2, top + 26, OX + 2, OY + 2, top + 28, WOOD)
    v.box(OX - 1, OY - 1, top + 28, OX + 1, OY + 1, top + 29, "gold")
    # lanterns hanging under the eave corners, just outside the stone piers
    for (sx, sy) in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        x, y = OX + sx * 33, OY + sy * 33
        hanging_lantern(v, x, y, EAVE - 6 - 9, glow_h=5)       # top meets the corner block; bottom 2.1 m above the floor
    return top


# ====================================================================================================== clutter, vines

def top_of(v, x0, x1, y0, y1):
    """Height of the highest solid voxel in a footprint (so that props stand on the stone piles)."""
    col = v.m[x0:x1, y0:y1].any(axis=(0, 1))
    idx = np.nonzero(col)[0]
    return int(idx.max()) + 1 if len(idx) else 0


def clutter(v):
    S = Side(v, 0)

    def put(g, a, d, z=0):
        x0, x1, y0, y1 = S.xy(a, a + 1, d, d + 1)
        v.stamp(g, x0, y0, z)

    def hay(a, d, sa=7, sd=6, sz=6, z=None):
        x0, x1, y0, y1 = S.xy(a, a + sa, d, d + sd)
        hay_bale(v, x0, y0, top_of(v, x0, x1, y0, y1) if z is None else z, sa, sd, sz)

    # front left: stacked crates and a barrel
    put(crate(8), -30, 43)
    put(crate(7), -30, 43, 8)
    put(crate(7), -20, 44)
    put(K.barrel(), -39, 42)
    # front right: a crate by the steps, hay bales against the corner
    put(crate(7), 18, 40)
    hay(25, 39)
    hay(34, 38)
    hay(29, 39, z=6)
    hay(27, 46, 6, 7, 5)
    # loose stone blocks
    for (a, d, s, r) in ((-44, 30, 4, 0), (22, 47, 3, 0), (-12, 38, 3, 0), (-30, 40, 4, 2), (20, 40, 4, 2),
                         (36, 40, 3, 1), (-34, 40, 4, 3), (30, 41, 3, 3), (-40, 28, 3, 1)):
        Side(v, r).box(a, a + s, d, d + s, 0, s, BLOCK, (None, "#efe8dc")[s % 2])
    # barrels and a crate at the back
    N = Side(v, 2)
    for (g, a, d) in ((K.barrel(), -8, 29), (K.barrel(), 1, 30), (crate(7), 12, 30)):
        x0, x1, y0, y1 = N.xy(a, a + 1, d, d + 1)
        v.stamp(g, x0, y0, 0)


def vines(v):
    rng = np.random.default_rng(31)
    f_out, f_in = OY - 36, OY - 16
    # front: down the left quoin from under the platform, a second strand lower down, one right of the door
    vine(v, "y", OX - 19, 76, 46, f_out, f_in, rng, spread=0.7)
    vine(v, "y", OX - 12, 58, 34, f_out, f_in, rng, spread=0.7)
    vine(v, "y", OX + 15, 30, 4, f_out, f_in, rng, spread=0.7)
    vine(v, "y", OX - 26, 26, 2, f_out, f_in, rng, spread=0.8)
    vine(v, "y", OX - 28, 20, 2, f_out, f_in, rng, spread=0.8)
    # west
    w_out, w_in = OX - 36, OX - 16
    vine(v, "x", OY + 16, 76, 44, w_out, w_in, rng, spread=0.7)
    vine(v, "x", OY - 22, 28, 2, w_out, w_in, rng, spread=0.8)
    # east
    e_out, e_in = OX + 35, OX + 16
    vine(v, "x", OY - 15, 76, 50, e_out, e_in, rng, spread=0.7)
    vine(v, "x", OY + 18, 36, 2, e_out, e_in, rng, spread=0.8)
    # north
    n_out, n_in = OY + 35, OY + 16
    vine(v, "y", OX + 16, 76, 42, n_out, n_in, rng, spread=0.7)
    vine(v, "y", OX - 22, 30, 2, n_out, n_in, rng, spread=0.8)


# ====================================================================================================== build

def build():
    v = Vox(NX, NY, NZ, VX, origin=(OX, OY, 0), name="tower", seed=17)
    c = Vox(NX // 2, NY // 2, NZ // 2, 2 * VX, origin=(OX // 2, OY // 2, 0), name="coarse", seed=18)
    shaft(v)
    stone_finish(v)
    windows(v)
    door(v)
    brackets(v, c)
    platform(v, c)
    lookout_things(v)
    top = roof(v, c)
    clutter(v)
    vines(v)

    parts = [v, c]
    # banners either side of the door, hanging from rods on iron brackets just in front of the belt course
    by = -(H_BASE + 3) * VX - 0.0625
    for s in (-1, 1):
        parts.append(K.banner("tree", w=16, h=34, notch=6, name="banner%d" % s).at(s * 17 * VX, by, (Z_BASE - 1) * VX))
    # the pennant
    parts.append(make_flag().at(1 * VX, 0.0, (top + 13) * VX + 0.03125))
    if os.environ.get("WT_DEBUG"):
        for p_ in parts:
            a_ = p_.mesh_arrays()
            print("part", p_.name, 0 if a_ is None else len(a_["verts"]))
    ob = V.join(parts, "SM_WatchTower")
    drop_bottom(ob, zs=(0.0,), hidden=((Z_TOP * VX, 1, PLAT * VX), ((Z_TOP - 2) * VX, -1, H_UP * VX)))
    return ob


# ====================================================================================================== main

def render(path, target=(0, 0, 1.5), az=28.0, el=32.0, dist=22.0, lens=85.0, res=(900, 1300), samples=32,
           sun_az=-60.0, sun_el=32.0):
    """voxlib.render, with a choice of CPU (Cycles on Metal can crash while other jobs render)."""
    import bpy
    scene = bpy.context.scene
    if "Sun" not in bpy.data.objects:
        V.setup_light(scene, sun_az, sun_el)
    if "PreviewGround" not in bpy.data.objects:
        bpy.ops.mesh.primitive_plane_add(size=400, location=(0, 0, -0.001))
        g = bpy.context.active_object
        g.name = "PreviewGround"
        gm = bpy.data.materials.new("PreviewGround")
        gm.use_nodes = True
        gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.13, 0.25, 0.05, 1)
        gm.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 1.0
        g.data.materials.append(gm)
    cam = bpy.data.objects.get("PreviewCam")
    if cam is None:
        cam = bpy.data.objects.new("PreviewCam", bpy.data.cameras.new("PreviewCam"))
        scene.collection.objects.link(cam)
    a, e = math.radians(az), math.radians(el)
    cam.location = (target[0] + math.sin(a) * math.cos(e) * dist, target[1] - math.cos(a) * math.cos(e) * dist,
                    target[2] + math.sin(e) * dist)
    V.look_at(cam, target)
    cam.data.lens = lens
    cam.data.clip_end = 2000
    scene.camera = cam
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.filepath = path
    for transform, look in (("Filmic", "Medium High Contrast"), ("AgX", "AgX - Medium High Contrast")):
        try:
            scene.view_settings.view_transform = transform
            scene.view_settings.look = look
            break
        except Exception:
            continue
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 4
    scene.cycles.device = "CPU"
    if not CPU:
        try:
            prefs = bpy.context.preferences.addons["cycles"].preferences
            prefs.compute_device_type = "METAL"
            prefs.get_devices()
            for dev in prefs.devices:
                dev.use = True
            scene.cycles.device = "GPU"
        except Exception:
            pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.render.render(write_still=True)
    print("rendered", path)


def preview(tag, **kw):
    if NO_RENDER or (VIEWS and tag not in VIEWS):
        return
    import time
    path = os.path.join(V.PREVIEWS, "%s_%s.png" % (TASK, tag))
    kw.setdefault("samples", SAMPLES)
    for attempt in range(3):
        try:
            render(path, **kw)
            return
        except RuntimeError as e:
            print("render failed (%s), retrying" % str(e)[:80])
            time.sleep(20)


def main():
    V.reset_scene()
    ob = build()
    print("faces", ob["voxel_faces"])
    if "--no-export" not in ARGS:
        fr = FREE * VX
        V.export_gltf(ob, collision="complex", extra=dict(lookout=dict(
            floor_z=FLOOR * VX, headroom=(BEAM - FLOOR) * VX, free=[-fr, -fr, fr, fr], rail=RAIL * VX)))
    preview("ref", target=(0, 0, 9.8), az=-38, el=10, dist=61, lens=85, sun_az=-110, sun_el=34)
    preview("high", target=(0, 0, 9.0), az=-35, el=35, dist=61, lens=85, sun_az=-110, sun_el=34)
    preview("back", target=(0, 0, 9.8), az=150, el=14, dist=61, lens=85, sun_az=60, sun_el=34)
    preview("door", target=(0, -2.5, 2.6), az=-22, el=10, dist=17, lens=50, res=(1100, 900), sun_az=-110, sun_el=34)
    preview("top", target=(0, 0, 13.8), az=-30, el=6, dist=26, lens=50, res=(1100, 900), sun_az=-110, sun_el=34)
    # stand-ins (preview only, not exported): 1.7 m columns on the platform to show the headroom and the rail height
    if not NO_RENDER and (not VIEWS or "headroom" in VIEWS):
        import bpy
        mat = bpy.data.materials.new("StandIn")
        mat.use_nodes = True
        mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.8, 0.08, 0.06, 1)
        for (x, y) in ((-1.2, -3.2), (1.0, -3.2), (-3.2, 0.6), (0.0, 0.0), (2.6, -2.6)):
            bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, FLOOR * VX + 0.85))
            o = bpy.context.active_object
            o.scale = (0.5, 0.3, 1.7)
            o.data.materials.append(mat)
        preview("headroom", target=(0, 0, 12.4), az=-30, el=4, dist=20, lens=50, res=(1100, 900), sun_az=-110, sun_el=34)


if __name__ == "__main__":
    main()
