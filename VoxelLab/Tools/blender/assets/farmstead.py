"""The farmstead (References/Remake/farm.png): a timber cottage with a steep green roof at the back, a hay stack and a
log pile beside it, a sheep pen to its left, a big raised wheat bed in front-left, a second wheat bed back-right,
carrot and tomato beds front-right, a cobble path in a T from the door out through the front gate, and a rail fence
round it all with stone lantern pillars at the corners and the gate.

    Blender -b --factory-startup --python Tools/blender/assets/farmstead.py -- [--no-render] [--no-export]
            [--views ref,front,...] [--samples N] [--cpu]

Exports SM_Farmstead (one static mesh). The wheat (it sways) and the sheep are NOT in the mesh: they are listed in the
sidecar JSON under "props" (SM_Wheat / SM_Sheep instances, metres in the asset's own space, yaw in degrees
counter-clockwise, z = the surface they stand on).

Pivot: the centre of the fenced rectangle (22 x 16 m) at ground level. The cottage is at the back (+Y), its door
faces -Y; the path leaves through the gate in the middle of the front (-Y) fence and runs about 1.3 m past it.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import json
import math
import time
import numpy as np
import bpy
import voxlib as V
import voxkit as K
from voxlib import Vox

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
NO_RENDER = "--no-render" in ARGS
NO_EXPORT = "--no-export" in ARGS
USE_CPU = "--cpu" in ARGS
VIEW_LIST = ARGS[ARGS.index("--views") + 1].split(",") if "--views" in ARGS else None
SAMPLES = int(ARGS[ARGS.index("--samples") + 1]) if "--samples" in ARGS else 32

VOX = 0.125
T = 0.0625
WOODS = ("#f6d2ac", "#dcae82", "#ecc097", "#cb9a6c")
TILE = "#7cb6a4"
TILE_LIGHT = "#d8f0a8"
LEAF_TINTS = (None, "#d8e8a0", "#b0c890", None)
FLOWERS = ("flower_white", "flower_yellow", "flower_orange", "flower_pink")

# ---- the plan (metres; +X east, +Y north/back, the front faces -Y)
FX, FY = 11.0, 8.5                       # the fence: x in [-FX, FX], y in [-FY, FY]
GATE_X = 1.4                             # the gate pillars' centres, x = +-GATE_X
COT_FRONT = 2.75                         # the cottage's front wall (y); the door is at x = 0
PATH_HW = 1.0                            # half width of the main path
BRANCH_Y = (-0.25, 1.5)                  # the path's east branch
WHEAT_BIG = (-10.25, -7.75, -1.75, 0.75)  # x0, y0, x1, y1 of the raised beds (outer edge of the boards)
WHEAT_BACK = (6.25, 2.0, 10.5, 7.5)
CARROTS = (1.75, -5.75, 5.75, -0.75)
TOMATOES = (6.5, -5.75, 10.5, -0.75)
PEN = (-FX, 1.75, -4.75, FY)               # the sheep pen (shares the outer fence on two sides)
SOIL_TOP = 0.25                          # top of the soil in the beds

# the ground-level grid (path, bed boards, vegetables): covers the plan with a margin
X_MIN, X_MAX = -11.75, 11.75
Y_MIN, Y_MAX = -10.25, 9.0


def gx(x):
    return int(round((x - X_MIN) / VOX))


def gy(y):
    return int(round((y - Y_MIN) / VOX))


# ---------------------------------------------------------------------------------------------------- helpers (from farm.py)

def roof_steps(b0, b1, z, run, rise):
    out = []
    i = 0
    while b1 - b0 - 2 * i * run > 0:
        out.append((b0 + i * run, b1 - i * run, z + i * rise))
        i += 1
    return out


def roof_under(b0, b1, z, run, rise):
    n = len(roof_steps(b0, b1, z, run, rise))

    def under(b):
        i = min((b - b0) // run, (b1 - 1 - b) // run)
        return z + max(0, min(i, n - 1)) * rise
    return under


def gable(v, a0, a1, b0, b1, z, ridge="y", run=4, rise=3, thick=3, cube=4, ends=(True, True), tile=TILE, ridge_w=4,
          seed=0, eave=True):
    """Stepped gable roof as a shell, chunky wooden blocks stepping up the gable ends, a ridge of wooden blocks."""
    def put(al, ah, bl, bh, zl, zh, mat, color=None):
        if ridge == "y":
            v.box(bl, al, zl, bh, ah, zh, mat, color)
        else:
            v.box(al, bl, zl, ah, bh, zh, mat, color)

    steps = roof_steps(b0, b1, z, run, rise)
    end_spans = ((a0 - 1, a0 - 1 + cube), (a1 + 1 - cube, a1 + 1))
    for i, (lo, hi, zl) in enumerate(steps):
        zh = zl + thick
        if hi - lo <= 2 * (run + 1):
            put(a0, a1, lo, hi, zl, zh, "roof", tile)
        else:
            put(a0, a1, lo, lo + run + 1, zl, zh, "roof", tile)
            put(a0, a1, hi - run - 1, hi, zl, zh, "roof", tile)
        if i == 0 and eave:
            put(a0, a1, lo, lo + 1, zl, zl + 2, "beam")
            put(a0, a1, hi - 1, hi, zl, zl + 2, "beam")
        w = min(cube, (hi - lo + 1) // 2)
        for e, (c0, c1) in enumerate(end_spans):
            if ends[e]:
                put(c0, c1, lo, lo + w, zl, zh + 1, "plank", WOODS[(i + e + seed) % 4])
                put(c0, c1, hi - w, hi, zl, zh + 1, "plank", WOODS[(i + e + seed + 2) % 4])
    lo, hi, zl = steps[-1]
    r0 = (b0 + b1 - ridge_w) // 2
    r1 = r0 + ridge_w
    rz = zl + thick if hi - lo >= ridge_w else zl + 1
    a, k = a0, 0
    while a < a1:
        put(a, min(a + 4, a1), r0, r1, rz, rz + 2, "plank", WOODS[(k + seed + 1) % 4])
        a += 4
        k += 1
    for e, (c0, c1) in enumerate(end_spans):
        if ends[e]:
            put(c0, c1, r0, r1, rz - 1, rz + 3, "plank", WOODS[(e + seed) % 4])
    return rz + 3


def win(v, axis, plane, a0, z0, w=5, h=5, out=-1, frame="beam", sill=2, vbar=True, hbar=True):
    """A small glowing window; the panes replace the wall's outer layer `plane`, the frame stands one voxel proud."""
    def put(al, ah, zl, zh, d0, d1, mat, color=None):
        p = sorted((plane + out * d0, plane + out * (d1 - 1)))
        if axis == "y":
            v.box(al, p[0], zl, ah, p[1] + 1, zh, mat, color)
        else:
            v.box(p[0], al, zl, p[1] + 1, ah, zh, mat, color)

    put(a0, a0 + w, z0, z0 + h, 0, 1, "window")
    put(a0 - 1, a0 + w + 1, z0 + h, z0 + h + 1, 1, 2, frame)
    put(a0 - 1, a0, z0, z0 + h, 1, 2, frame)
    put(a0 + w, a0 + w + 1, z0, z0 + h, 1, 2, frame)
    put(a0 - 1, a0 + w + 1, z0 - 1, z0, 1, 1 + sill, frame)
    if vbar:
        put(a0 + w // 2, a0 + w // 2 + 1, z0, z0 + h, 0, 1, frame)
    if hbar:
        put(a0, a0 + w, z0 + h // 2, z0 + h // 2 + 1, 0, 1, frame)


def ivy(v, cells, seed=0, density=0.8, hmin=2, hmax=7, hang=True):
    rng = np.random.default_rng(seed)
    for (x, y, z) in cells:
        if rng.random() > density:
            continue
        n = int(rng.integers(hmin, hmax + 1))
        for k in range(n):
            zz = z - k if hang else z + k
            if 0 <= zz < v.n[2] and 0 <= x < v.n[0] and 0 <= y < v.n[1] and v.get(x, y, zz) is None:
                v.set(x, y, zz, "leaves", LEAF_TINTS[int(rng.integers(0, len(LEAF_TINTS)))])


def drop_ground_faces(ob):
    """Remove the faces lying on the ground looking down (nobody ever sees them)."""
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


# ---------------------------------------------------------------------------------------------------- the cottage

def cottage():
    """The cottage on the 12.5 cm grid. Origin: the middle of the door at the front wall's outer face, ground level."""
    v = Vox(86, 66, 62, VOX, name="cottage", seed=5)
    W, D = 56, 40                            # 7 x 5 m walls
    X0, Y0 = 17, 15
    X1, Y1 = X0 + W, Y0 + D
    ZF, ZE = 4, 24                           # top of the stone footing (the door sill); the eaves (3 m)
    cx = X0 + W // 2
    RUN, RISE = 4, 4
    b0, b1 = X0 - 3, X1 + 3                  # roof across X with 3 voxels of eave
    a0, a1 = Y0 - 4, Y1 + 3                  # along Y: a deep overhang over the front gable
    steps = roof_steps(b0, b1, ZE, RUN, RISE)
    under = roof_under(b0, b1, ZE, RUN, RISE)

    # ---- stone footing, chunky
    v.box(X0 - 2, Y0 - 2, 0, X1 + 2, Y1 + 2, ZF, "stone")
    v.chunky("stone", p=0.4, seed=2)
    # ---- the body: plaster up to the eaves, boards in the gables
    for (lo, hi, zl) in steps:
        v.box(max(lo, X0), Y0, ZF, min(hi, X1), Y1, zl, "plaster")
    v.tint("plaster", "#efe2c4", p=0.35, cell=4, seed=4)
    v.tint("plaster", "#ddd0b4", p=0.15, cell=4, seed=9)
    X, Y, Z = v.grid()
    gab = v.mask("plaster") & (Z >= ZE + 3)
    v.where(gab, "beam")
    for z in range(ZE + 3, v.n[2]):
        sl = gab[:, :, z]
        if sl.any():
            v.c[:, :, z][sl] = V.rgb(WOODS[(z // 2) % 4])

    # ---- timber frame, one voxel proud
    for (px, py) in ((X0 - 1, Y0 - 1), (X1 - 2, Y0 - 1), (X0 - 1, Y1 - 2), (X1 - 2, Y1 - 2)):
        v.box(px, py, ZF, px + 3, py + 3, ZE + 3, "post")
    for sx in (cx - 9, cx + 7):                                                 # studs either side of the door
        v.box(sx, Y0 - 1, ZF, sx + 2, Y0, ZE, "post")
    for sx in (cx - 9, cx + 7):                                                 # and up the back
        v.box(sx, Y1, ZF, sx + 2, Y1 + 1, ZE, "post")
    v.box(X0, Y1, 9, X1, Y1 + 1, 10, "beam")
    for px in (X0 - 1, X1):
        v.box(px, Y0, ZE - 2, px + 1, Y1, ZE, "beam")
        v.box(px, Y0, 9, px + 1, Y1, 10, "beam")
        v.box(px, Y0 + 17, ZF, px + 1, Y0 + 19, ZE, "post")
    # front: a sill rail under the windows
    v.box(X0, Y0 - 1, 9, cx - 9, Y0, 10, "beam")
    v.box(cx + 9, Y0 - 1, 9, X1, Y0, 10, "beam")

    # ---- the door (2.25 m), recessed, vertical boards, iron bands, two stone steps
    dw, dh = 10, 18
    d0 = cx - dw // 2
    v.box(d0, Y0, ZF, d0 + dw, Y0 + 2, ZF + dh, None)
    for i in range(dw // 2):
        v.box(d0 + 2 * i, Y0 + 1, ZF, d0 + 2 * i + 2, Y0 + 2, ZF + dh, "post", ("#d49a64", "#c08654", "#dca872")[i % 3])
    for zz in (ZF + 3, ZF + dh - 4):
        v.box(d0, Y0 + 1, zz, d0 + dw, Y0 + 2, zz + 1, "metal")
    v.box(d0 + dw - 3, Y0, ZF + 8, d0 + dw - 2, Y0 + 1, ZF + 10, "gold")
    v.box(d0 - 2, Y0 - 1, ZF, d0, Y0 + 1, ZF + dh + 2, "post", WOODS[3])         # frame
    v.box(d0 + dw, Y0 - 1, ZF, d0 + dw + 2, Y0 + 1, ZF + dh + 2, "post", WOODS[3])
    v.box(d0 - 2, Y0 - 2, ZF + dh, d0 + dw + 2, Y0 + 1, ZF + dh + 2, "beam", WOODS[1])
    v.box(cx - 7, Y0 - 6, 0, cx + 7, Y0 - 2, 2, "stone", "#e4dccc")              # steps
    v.box(cx - 6, Y0 - 4, 2, cx + 6, Y0 - 2, 4, "stone", "#e4dccc")
    v.box(cx - 6, Y0 - 2, 0, cx + 6, Y0, ZF, "stone", "#e4dccc")
    for (sx, sy, sz) in ((cx - 7, Y0 - 6, 1), (cx + 3, Y0 - 6, 1), (cx - 6, Y0 - 4, 3), (cx + 2, Y0 - 3, 3)):
        v.box(sx, sy, sz, sx + 4, sy + 1, sz + 1, "stone", "#cfc6b4")             # joints between slabs read
    # ---- windows
    win(v, "y", Y0, X0 + 5, ZF + 7, w=7, h=7)                                    # left of the door
    win(v, "y", Y0, X1 - 12, ZF + 7, w=7, h=7)                                   # right of the door
    win(v, "y", Y0, cx - 4, ZE + 6, w=8, h=6)                                    # the gable window
    win(v, "x", X0, Y0 + 6, ZF + 7, w=6, h=7, out=-1)
    win(v, "x", X0, Y0 + 24, ZF + 7, w=6, h=7, out=-1)
    win(v, "x", X1 - 1, Y0 + 24, ZF + 7, w=6, h=7, out=1)
    win(v, "y", Y1 - 1, cx - 3, ZF + 7, w=6, h=7, out=1)
    win(v, "y", Y1 - 1, cx - 3, ZE + 6, w=6, h=5, out=1)
    # ---- plate beams across the gable fronts, brackets under the front one
    for k, bx in enumerate(range(X0 - 2, X1 + 2, 6)):
        v.box(bx, Y0 - 2, ZE, min(bx + 6, X1 + 2), Y0, ZE + 3, "plank", WOODS[1 + 2 * (k % 2)])
        v.box(bx, Y1, ZE, min(bx + 6, X1 + 2), Y1 + 2, ZE + 3, "plank", WOODS[1 + 2 * (k % 2)])
    for bx in (X0 + 2, cx - 12, cx + 11, X1 - 3):
        v.box(bx, Y0 - 2, ZE - 2, bx + 1, Y0 - 1, ZE, "beam")
    # ---- flower box under the left window, the lantern between the door and the right window
    fx0, fx1 = X0 + 3, X0 + 15
    v.box(fx0, Y0 - 4, 6, fx1, Y0 - 1, 9, "plank", WOODS[1])
    v.box(fx0, Y0 - 4, 6, fx0 + 1, Y0 - 1, 9, "beam")
    v.box(fx1 - 1, Y0 - 4, 6, fx1, Y0 - 1, 9, "beam")
    v.box(fx0 + 1, Y0 - 3, 8, fx1 - 1, Y0 - 1, 9, "dirt", "#8a6448")
    rng = np.random.default_rng(3)
    for x in range(fx0 + 1, fx1 - 1):
        for y in range(Y0 - 3, Y0 - 1):
            h = int(rng.integers(1, 3))
            v.box(x, y, 9, x + 1, y + 1, 9 + h, "leaves", LEAF_TINTS[int(rng.integers(0, 4))])
            if rng.random() < 0.55:
                v.set(x, y, 9 + h, "paint", FLOWERS[int(rng.integers(0, 4))])
    K.wall_lantern(v, X1 - 15, Y0 - 1, 21)

    # ---- roof
    top = gable(v, a0, a1, b0, b1, ZE, ridge="y", run=RUN, rise=RISE, thick=RISE, seed=0)
    # stone chimney on the left slope, in the front half
    qx, qy = X0 + 5, Y0 + 9
    v.box(qx, qy, ZE, qx + 6, qy + 6, 47, "stone")
    v.box(qx - 1, qy - 1, 47, qx + 7, qy + 7, 49, "stone")
    v.box(qx + 1, qy + 1, 48, qx + 5, qy + 5, 49, "paint", "#2e2824")
    v.chunky("stone", p=0.25, seed=5, region=(qx - 2, qy - 2, 34, qx + 8, qy + 8, 47))
    # moss creeping over both slopes, as in the picture
    rng = np.random.default_rng(11)
    for i, (lo, hi, zl) in enumerate(steps[:6]):
        for _ in range(3):
            yb = int(rng.integers(a0, a1 - 6))
            ln = int(rng.integers(3, 9))
            v.box(lo + (1 if i == 0 else 0), yb, zl + 2, lo + 4, yb + ln, zl + 3, "moss")
        for _ in range(2):
            yb = int(rng.integers(a0, a1 - 6))
            ln = int(rng.integers(3, 8))
            v.box(hi - 4, yb, zl + 2, hi - (1 if i == 0 else 0), yb + ln, zl + 3, "moss")

    # ---- log pile against the right wall, behind the hay
    lx0 = X1 + 2
    # logs lie along Y so their cut ends face the front
    ends = ("#d9a565", "#c98f4e", "#e2b377")
    for row in range(4):
        for k in range(4 - row):
            xx = lx0 + row + 2 * k
            ya = Y0 + 4 + int(rng.integers(0, 2))
            v.box(xx, ya, row * 2, xx + 2, Y0 + 17, row * 2 + 2, "log", WOODS[(row + k) % 4])
            v.box(xx, ya, row * 2, xx + 2, ya + 1, row * 2 + 2, "paint", ends[(row + k) % 3])
    for yy in (Y0 + 6, Y0 + 14):                                                # two stakes hold the pile
        v.box(lx0 + 8, yy, 0, lx0 + 9, yy + 1, 8, "post", WOODS[3])

    # ---- life: lighter tiles, moss, ivy
    v.tint("roof", TILE_LIGHT, p=0.16, cell=2, seed=7)
    v.scatter("roof", "moss", p=0.07, seed=4, direction="+z")
    v.scatter("plank", "moss", p=0.08, seed=6, direction="+z", region=(0, 0, ZE - 1, v.n[0], v.n[1], v.n[2]))
    v.scatter("stone", "mossy_stone", p=0.12, seed=8, direction="+z")
    cells = [(x, Y0 - 1, under(x) - 1) for x in range(X0 + 1, X0 + 5)]
    cells += [(X0 - 1, y, ZE - 3) for y in range(Y0 + 2, Y0 + 6)]
    ivy(v, cells, seed=2, hmin=3, hmax=9)
    ivy(v, [(X0 - 2, Y0 - 2, ZF), (X0 - 2, Y0 - 1, ZF), (X0 - 1, Y0 - 2, ZF)], seed=3, hmin=5, hmax=13, hang=False, density=1.0)
    ivy(v, [(x, Y1 + 1, ZE - 1) for x in range(X1 - 9, X1 - 2)], seed=5, hmin=2, hmax=8)
    v.origin = (cx, Y0, 0.0)
    v.info = dict(top=top * VOX)
    return v


# ---------------------------------------------------------------------------------------------------- fences and pillars

def fence_post(v, x, y, h=9, tint=WOODS[1]):
    """A 25 cm square post with a paler head."""
    v.box(x, y, 0, x + 2, y + 2, h - 1, "post", tint)
    v.box(x, y, h - 1, x + 2, y + 2, h, "post", "#f2d2a8")


def fence_run(L, every=2.0, start_post=False, end_post=False, h=9, seed=0):
    """A rail fence L metres long along +X on the 12.5 cm grid (1.1 m high, two chunky rails), origin at its start on
    the line. Posts about `every` metres; the end posts only when asked (the lantern pillars stand there otherwise)."""
    n = int(round(L / VOX))
    v = Vox(n + 2, 2, h, VOX, origin=(1, 1, 0), name="fence", seed=seed)
    k = max(1, int(round(L / every)))
    rng = np.random.default_rng(seed)
    for i in range(k):                                                           # rails in lengths, a slight shade each
        a, b = 1 + int(round(i * n / k)), 1 + int(round((i + 1) * n / k))
        v.box(a, 1, 3, b, 2, 5, "beam", ("#e0b88c", "#d4a87c", "#e8c49a")[int(rng.integers(0, 3))])
        v.box(a, 1, 6, b, 2, 8, "beam", ("#ecc8a0", "#dcb48a", "#f2d0a8")[int(rng.integers(0, 3))])
    for i in range(k + 1):
        if (i == 0 and not start_post) or (i == k and not end_post):
            continue
        px = 1 + int(round(i * n / k)) - 1
        fence_post(v, px, 0, h=h, tint=(WOODS[1], WOODS[3])[(i + seed) % 2])
    v.scatter("post", "moss", p=0.1, seed=seed + 3, direction="+z")
    return v


def lantern_pillar(seed=0):
    """A stone pillar with a glowing lantern on top (2.25 m). Origin: bottom centre."""
    v = Vox(8, 8, 18, VOX, origin=(4, 4, 0), name="pillar", seed=seed)
    v.box(0, 0, 0, 8, 8, 2, "stone")                                             # plinth
    v.box(1, 1, 2, 7, 7, 9, "stone")                                             # pillar, 1 m of stone
    v.chunky("stone", cell=2, p=0.25, seed=seed + 3, region=(0, 0, 2, 8, 8, 8))
    v.box(0, 0, 9, 8, 8, 10, "stone")                                            # collar
    v.tint("stone", "#d8d0c4", p=0.3, cell=2, seed=seed)
    v.scatter("stone", "mossy_stone", p=0.35, seed=seed + 1, direction="+z")
    v.box(1, 1, 10, 7, 7, 11, "plank", WOODS[3])                                 # wooden seat
    v.box(2, 2, 11, 6, 6, 16, "glow", "lantern_hot")                             # the lamp, 62 cm tall
    for dx in (1, 6):
        for dy in (1, 6):
            v.box(dx, dy, 11, dx + 1, dy + 1, 16, "post", "#8a6040")
    v.box(0, 0, 16, 8, 8, 17, "beam", WOODS[3])                                  # the cap: a wide board and a block
    v.box(2, 2, 17, 6, 6, 18, "beam", WOODS[1])
    return v


# ---------------------------------------------------------------------------------------------------- small things

def bale_vox(seed=0):
    """A hay bale 1.0 x 0.75 x 0.75 m on the 12.5 cm grid, long along X, two dark twine straps, a few loose straws."""
    v = Vox(10, 8, 7, VOX, origin=(5, 4, 0), name="bale", seed=seed)
    v.box(1, 1, 0, 9, 7, 6, "hay")
    v.tint("hay", "#f3dfa2", p=0.3, cell=1, seed=seed)
    v.tint("hay", "#e2c070", p=0.15, cell=1, seed=seed + 3)
    for sx in (3, 6):                                                           # straps round the bale
        v.box(sx, 1, 0, sx + 1, 7, 6, "paint", "#8a6232")
        v.box(sx, 2, 1, sx + 1, 6, 5, "hay")
    rng = np.random.default_rng(seed + 20)
    for _ in range(6):
        a, b = int(rng.integers(1, 9)), int(rng.integers(1, 7))
        if a in (3, 6):
            continue
        if rng.random() < 0.5:
            v.set(a, b, 6, "hay", "#fff0b0")
        else:
            v.set(a, 0 if rng.random() < 0.5 else 7, int(rng.integers(0, 6)), "hay", "#fff0b0")
    return v


def trough_vox():
    """1.5 m long along X, water inside (from farm.py)."""
    v = Vox(24, 10, 9, T, origin=(12, 5, 0), name="trough")
    for i, x in enumerate(range(0, 24, 4)):
        v.box(x, 1, 2, x + 4, 9, 8, "plank", WOODS[(i * 3) % 4])
    v.box(1, 2, 3, 23, 8, 8, None)
    v.box(1, 2, 3, 23, 8, 6, "water")
    for x in (2, 20):
        v.box(x, 0, 0, x + 2, 10, 3, "beam")
        v.box(x, 0, 3, x + 2, 1, 6, "beam")
        v.box(x, 9, 3, x + 2, 10, 6, "beam")
    for x in (7, 16):
        v.box(x, 1, 2, x + 1, 9, 3, "metal")
        v.box(x, 1, 2, x + 1, 2, 8, "metal")
        v.box(x, 8, 2, x + 1, 9, 8, "metal")
    return v


def bush_vox(rx=1.0, ry=0.9, rz=1.0, seed=0):
    """A puffy bush of 25 cm leaf cubes. Origin: bottom centre."""
    nx, ny, nz = int(2 * rx / 0.25) + 2, int(2 * ry / 0.25) + 2, int(2 * rz / 0.25) + 1
    v = Vox(nx, ny, nz, 0.25, origin=(nx / 2.0, ny / 2.0, 0), name="bush", seed=seed)
    v.ellipsoid(nx / 2.0, ny / 2.0, rz / 0.25 - 0.3, rx / 0.25, ry / 0.25, rz / 0.25, "leaves", noise=0.35,
                noise_scale=3, seed=seed)
    v.erode("leaves", p=0.2, seed=seed)
    v.tint("leaves", "#d8e8a0", p=0.35, seed=seed + 1)
    v.tint("leaves", "#b8d088", p=0.2, seed=seed + 2)
    return v


def barrel_vox():
    return K.barrel()


# ---------------------------------------------------------------------------------------------------- the ground layer

def path_layer(G, seed=1):
    """Flagstones one voxel thick (top at 12.5 cm): the main path from the steps out through the gate and the branch
    east along the front of the back-right wheat bed. Ragged edges, warm greys, sandy and mossy bits."""
    X, Y, Z = G.grid()
    mx = (X + 0.5) * VOX + X_MIN
    my = (Y + 0.5) * VOX + Y_MIN
    n = V.noise3(G.n, 3.0, seed + 5)
    jag = (n - 0.5) * 0.55
    main = (np.abs(mx) < PATH_HW + jag) & (my > -FY - 1.3 + jag) & (my < COT_FRONT - 0.6)
    branch = (mx > 0.0) & (mx < FX - 0.35 + jag) & (my > BRANCH_Y[0] + jag) & (my < BRANCH_Y[1] - jag)
    m = (main | branch) & (Z == 0)
    # edge cells: within ~0.2 m of the outline
    inner_main = (np.abs(mx) < PATH_HW + jag - 0.2) & (my > -FY - 1.1 + jag) & (my < COT_FRONT - 0.6)
    inner_branch = (mx > 0.0) & (mx < FX - 0.55 + jag) & (my > BRANCH_Y[0] + jag + 0.2) & (my < BRANCH_Y[1] - jag - 0.2)
    edge = m & ~((inner_main | inner_branch) & (Z == 0))
    G.where(m, "stone")
    # flagstones: 2 x 2 voxel cells (with some 3 x 2 run-ons) in a handful of warm greys
    h = V._hash3(X // 2 + (Y // 2) % 2, Y // 2, Z, seed + 31)
    greys = [V.rgb(c) for c in ("#f0e8da", "#e2d8c6", "#d6ccb8", "#ece0ca", "#cdc3b0", "#f6f0e4")]
    idx = (h * len(greys)).astype(int) % len(greys)
    for i, c in enumerate(greys):
        sel = m & (idx == i)
        G.c[sel] = c
    rng = np.random.default_rng(seed)
    r = rng.random(G.n)
    G.where(m & (r < 0.06), "cobble", "#d8c8a8")
    G.where(edge & (r > 0.55) & (r < 0.75), "cobble", "#c8b490")
    G.where(edge & (r >= 0.75) & (r < 0.8), "dirt", "#b89a76")
    G.where(edge & (r >= 0.8) & (r < 0.95), "moss")
    G.where(edge & (r >= 0.95), None)


def raised_bed(G, S, rect, soil="#8a6448", seed=0, post_every=2.2):
    """Boards round the bed (25 cm thick, 37.5 cm high) with square posts at the corners and along the sides, the
    soil inside on the 25 cm grid with its top at SOIL_TOP."""
    x0, y0, x1, y1 = rect
    i0, j0, i1, j1 = gx(x0), gy(y0), gx(x1), gy(y1)
    rng = np.random.default_rng(seed)
    boards = ("#b08860", "#9c7854", "#a88058")
    # long boards in pieces so neighbouring planks read
    for (a, b, along) in ((j0, j0 + 2, "x"), (j1 - 2, j1, "x"), (i0, i0 + 2, "y"), (i1 - 2, i1, "y")):
        lo, hi = (i0, i1) if along == "x" else (j0, j1)
        p = lo
        while p < hi:
            q = min(hi, p + int(rng.integers(8, 14)))
            col = boards[int(rng.integers(0, 3))]
            if along == "x":
                G.box(p, a, 0, q, b, 2, "beam", col)
                G.box(p, a, 2, q, b, 3, "beam", "#c09670")
            else:
                G.box(a, p, 0, b, q, 2, "beam", col)
                G.box(a, p, 2, b, q, 3, "beam", "#c09670")
            p = q
    # posts
    def post(px, py):
        G.box(px - 1, py - 1, 0, px + 2, py + 2, 4, "post", "#b48660")
        G.box(px - 1, py - 1, 4, px + 2, py + 2, 5, "plank", "#f0d4b0")
        G.set(px, py, 5, "beam", "#a07050")
    corners_x = [i0 + 1, i1 - 1 - 1]
    corners_y = [j0 + 1, j1 - 1 - 1]
    for px in corners_x:
        for py in corners_y:
            post(px, py)
    for (a, b, fixed, along) in ((i0 + 1, i1 - 2, (j0 + 1, j1 - 2), "x"), (j0 + 1, j1 - 2, (i0 + 1, i1 - 2), "y")):
        k = int(round((b - a) * VOX / post_every))
        for t in range(1, k):
            c = int(round(a + t * (b - a) / k))
            for f in fixed:
                post(c, f) if along == "x" else post(f, c)
    G.scatter("beam", "moss", p=0.05, seed=seed + 7, direction="+z", region=(i0 - 1, j0 - 1, 0, i1 + 1, j1 + 1, 6))
    # soil
    si0, sj0 = int(round((x0 + 0.25 - X_MIN) / 0.25)), int(round((y0 + 0.25 - Y_MIN) / 0.25))
    si1, sj1 = int(round((x1 - 0.25 - X_MIN) / 0.25)), int(round((y1 - 0.25 - Y_MIN) / 0.25))
    S.box(si0, sj0, 0, si1, sj1, 1, "dirt", soil)
    S.tint("dirt", "#7a5640", p=0.25, seed=seed + 2)
    S.tint("dirt", "#9a7452", p=0.12, seed=seed + 5)
    return (x0 + 0.25, y0 + 0.25, x1 - 0.25, y1 - 0.25)


def carrots(G, rect, seed=0):
    """Rows of carrots along X with soil between the rows: an orange crown standing out of the soil and a fan of
    light green leaves on it."""
    x0, y0, x1, y1 = rect
    rng = np.random.default_rng(seed)
    z = int(round(SOIL_TOP / VOX))
    nx = int((x1 - x0) / 0.5)
    ny = int(round((y1 - y0) / 0.75))
    for j in range(ny):
        for i in range(nx):
            px = gx(x0 + (i + 0.5) * (x1 - x0) / nx) - 1 + int(rng.integers(0, 2)) * (j % 2)
            py = gy(y0 + (j + 0.5) * (y1 - y0) / ny) - 1
            G.box(px, py, z, px + 2, py + 2, z + 1, "paint", ("#f08a24", "#e87a1c", "#f49a34")[int(rng.integers(0, 3))])
            leaf = ("#5aa42a", "#4e9626", "#66ae30")[int(rng.integers(0, 3))]
            # a leafy clump sitting just behind the crown, ragged at the corners
            for dx in (-1, 0, 1):
                for dy in (0, 1, 2):
                    corner = dx != 0 and dy != 1
                    if corner and rng.random() < 0.6:
                        continue
                    h = 1 + int(rng.integers(1, 3)) + (1 if (dx, dy) == (0, 1) else 0)
                    G.box(px + 1 + dx, py + dy, z, px + 2 + dx, py + dy + 1, z + h, "leaves", leaf)
            G.box(px, py, z, px + 2, py + 1, z + 1, "paint", ("#f08a24", "#e87a1c", "#f49a34")[int(rng.integers(0, 3))])
            if rng.random() < 0.6:
                G.set(px + int(rng.integers(0, 3)), py + 1 + int(rng.integers(0, 2)), z + 3 + int(rng.integers(0, 2)), "leaves", "#8cc840")


def tomatoes(G, rect, seed=0):
    """Tomato bushes: round leaf clumps with red fruit, a little orange squash at the foot of some."""
    x0, y0, x1, y1 = rect
    rng = np.random.default_rng(seed)
    z = int(round(SOIL_TOP / VOX))
    nx = int(round((x1 - x0) / 0.9))
    ny = int(round((y1 - y0) / 0.9))
    T_ = Vox(*G.n, voxel=VOX, seed=seed)
    for i in range(nx):
        for j in range(ny):
            cx = gx(x0 + (i + 0.5) * (x1 - x0) / nx) + rng.uniform(-0.4, 0.4)
            cy = gy(y0 + (j + 0.5) * (y1 - y0) / ny) + rng.uniform(-0.4, 0.4)
            r = rng.uniform(2.3, 2.7)
            sub = Vox(10, 10, 9, VOX, seed=seed + i * 7 + j)
            sub.ellipsoid(5, 5, 4.2, r, r, 3.6, "leaves", ("#5aa02a", "#4e9426", "#64aa2e")[int(rng.integers(0, 3))],
                          noise=0.3, noise_scale=2, seed=i * 5 + j)
            sub.erode("leaves", p=0.18, seed=i + j * 3)
            sub.scatter("leaves", "paint", p=0.22, seed=i * 3 + j, color="#d8302a")
            sub.scatter("paint", "paint", p=0.3, seed=i * 3 + j + 1, color="#f04a32")
            sub.box(4, 4, 0, 6, 6, 1, "post", "#7a5a30")
            ox, oy = int(round(cx)) - 5, int(round(cy)) - 5
            sub.origin = (0, 0, 0)
            G.stamp(sub, ox, oy, z, overwrite=False)
            if rng.random() < 0.55:
                sx, sy = int(round(cx)) + int(rng.choice([-3, 2])), int(round(cy)) - 3
                G.box(sx, sy, z, sx + 2, sy + 2, z + 2, "paint", ("#f08a24", "#e8901c")[int(rng.integers(0, 2))])
                G.set(sx, sy + 1, z + 2, "leaves", "#4a8c22")


def tufts(G, rng, n=40):
    """Clumps of tall grass, some with a flower, along the inside of the fence."""
    placed = tries = 0
    while placed < n and tries < n * 40:
        tries += 1
        side = int(rng.integers(0, 4))
        t = rng.uniform(-1, 1)
        x, y = [(t * FX, FY - 0.35), (t * FX, -FY + 0.35), (-FX + 0.35, t * FY), (FX - 0.35, t * FY)][side]
        x += rng.uniform(-0.12, 0.12)
        y += rng.uniform(-0.12, 0.12)
        i, j = gx(x), gy(y)
        if G.m[i - 2:i + 3, j - 2:j + 3, 0:3].any():
            continue
        tint = ("#a8d050", "#c8e48c", "#8cc040")[int(rng.integers(0, 3))]
        for (dx, dy) in ((0, 0), (1, 0), (0, 1), (-1, 0), (0, -1))[:int(rng.integers(2, 6))]:
            h = int(rng.integers(1, 4))
            G.box(i + dx, j + dy, 0, i + dx + 1, j + dy + 1, h, "leaves", tint)
            if rng.random() < 0.3:
                G.set(i + dx, j + dy, h, "paint", FLOWERS[int(rng.integers(0, 4))])
        placed += 1


# ---------------------------------------------------------------------------------------------------- the farmstead

def wheat_props(rect, seed):
    x0, y0, x1, y1 = rect
    rng = np.random.default_rng(seed)
    nx = max(1, int(round((x1 - x0) / 0.95)))
    ny = max(1, int(round((y1 - y0) / 0.95)))
    out = []
    for i in range(nx):
        for j in range(ny):
            px = x0 + (i + 0.5) * (x1 - x0) / nx + rng.uniform(-0.07, 0.07)
            py = y0 + (j + 0.5) * (y1 - y0) / ny + rng.uniform(-0.07, 0.07)
            out.append({"mesh": "SM_Wheat", "pos": [round(px, 3), round(py, 3), SOIL_TOP],
                        "yaw": float(int(rng.integers(0, 4)) * 90 + round(rng.uniform(-12, 12), 1)),
                        "scale": round(float(rng.uniform(0.9, 1.1)), 3)})
    return out


def build_farmstead():
    parts = []
    # ---- ground layer (path, beds, vegetables) on the 12.5 cm grid; soil on the 25 cm grid
    nx, ny = gx(X_MAX), gy(Y_MAX)
    G = Vox(nx, ny, 10, VOX, origin=(-X_MIN / VOX, -Y_MIN / VOX, 0), name="ground", seed=7)
    S = Vox(int((X_MAX - X_MIN) / 0.25), int((Y_MAX - Y_MIN) / 0.25), 1, 0.25,
            origin=(-X_MIN / 0.25, -Y_MIN / 0.25, 0), name="soil", seed=9)
    path_layer(G)
    big = raised_bed(G, S, WHEAT_BIG, seed=1)
    back = raised_bed(G, S, WHEAT_BACK, seed=2)
    car = raised_bed(G, S, CARROTS, seed=3)
    tom = raised_bed(G, S, TOMATOES, seed=4)
    carrots(G, car, seed=5)
    tomatoes(G, tom, seed=6)
    tufts(G, np.random.default_rng(12), n=40)
    parts += [G, S]

    # ---- the cottage
    cot = cottage()
    parts.append(cot.at(0.0, COT_FRONT, 0.0))
    # ---- hay stack and a barrel by the cottage's front right corner, a bush behind
    bales = [(4.55, 2.15, 0.0, 0), (5.6, 2.15, 0.0, 0), (5.1, 2.95, 0.0, 0), (4.7, 2.25, 0.75, 0), (5.55, 2.75, 0.75, 1)]
    for k, (x, y, z, r) in enumerate(bales):
        parts.append(bale_vox(k + 2).at(x, y, z, r))
    parts.append(barrel_vox().at(3.6, 1.8, 0.0))
    parts.append(bush_vox(1.25, 1.1, 1.4, seed=3).at(4.95, 6.6, 0.0))

    # ---- the outer fence and the lantern pillars
    runs = [
        ((-FX, FY), FX * 2, 0),                    # back, west to east
        ((-FX, -FY), FY * 2, 1),                   # west side, south to north
        ((FX, -FY), FY * 2, 1),                    # east side
        ((-FX, -FY), FX - GATE_X, 0),              # front, left of the gate
        ((GATE_X, -FY), FX - GATE_X, 0),           # front, right of the gate
    ]
    for k, ((x, y), L, rot) in enumerate(runs):
        parts.append(fence_run(L, every=2.2, seed=k).at(x, y, 0.0, rot))
    for k, (x, y) in enumerate(((-FX, FY), (FX, FY), (-FX, -FY), (FX, -FY), (-GATE_X, -FY), (GATE_X, -FY))):
        parts.append(lantern_pillar(seed=k).at(x, y, 0.0))
    # ---- the sheep pen inside the back-left corner, with a trough
    px0, py0, px1, py1 = PEN
    parts.append(fence_run(px1 - px0, every=2.2, end_post=True, seed=11).at(px0, py0, 0.0, 0))
    parts.append(fence_run(py1 - py0, every=2.2, seed=12).at(px1, py0, 0.0, 1))
    parts.append(trough_vox().at(-8.6, 7.4, 0.0))

    if "--faces" in ARGS:
        tally = {}
        for prt in parts:
            a = prt.mesh_arrays()
            tally[prt.name] = tally.get(prt.name, 0) + (0 if a is None else len(a["verts"]))
        print("FACES", tally)
    ob = V.join(parts, "SM_Farmstead")
    drop_ground_faces(ob)
    props = wheat_props(big, 21) + wheat_props(back, 22)
    props += [{"mesh": "SM_Sheep", "pos": [-7.4, 4.3, 0.0], "yaw": -35.0, "scale": 1.0},
              {"mesh": "SM_Sheep", "pos": [-6.1, 5.1, 0.0], "yaw": 10.0, "scale": 1.0}]
    ob["props"] = json.dumps(props)
    return ob


# ---------------------------------------------------------------------------------------------------- previews

def import_gltf(name):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(V.MESHES, name + ".gltf"))
    obs = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    for ob in obs:
        if ob.data.color_attributes:
            ob.data.color_attributes[0].name = "Col"
        for i, m in enumerate(ob.data.materials):
            if m is None:
                continue
            slot = m.name.split(".")[0]
            slot = slot[4:] if slot.startswith("Vox_") else slot
            if not m.get("vox_preview"):
                m.name = "imported_" + m.name                 # the importer's plain material must not shadow ours
            pm = V.material(slot)
            pm["vox_preview"] = True
            ob.data.materials[i] = pm
    return obs


def preview_ground(w=40, d=34):
    nx, ny = int(w / 0.5), int(d / 0.5)
    g = Vox(nx, ny, 2, 0.5, origin=(nx // 2, ny // 2, 2), name="ground", seed=4)
    g.box(0, 0, 0, nx, ny, 1, "dirt")
    g.box(0, 0, 1, nx, ny, 2, "grass")
    g.tint("grass", "#d8f0a0", p=0.25, seed=2)
    ob = g.to_object("PreviewGround")
    ob.location.z = -0.002
    return ob


def scene_with_props(ob):
    preview_ground()
    props = json.loads(ob["props"])
    src = {}
    for mesh in ("SM_Wheat", "SM_Sheep"):
        got = import_gltf(mesh)
        src[mesh] = got[0]
        got[0].location = (0, 0, -100)
        got[0].hide_render = True
    for k, p in enumerate(props):
        s = src[p["mesh"]]
        o = bpy.data.objects.new("%s_%d" % (p["mesh"], k), s.data)
        bpy.context.scene.collection.objects.link(o)
        o.location = p["pos"]
        o.rotation_euler = (0, 0, math.radians(p["yaw"]))
        o.scale = (p["scale"],) * 3


VIEWS = {
    #          target              az    el   dist  lens  sun_az sun_el
    "ref":   ((0.4, 0.0, 0.6),   -30,  38,  46.0,  50.0,  -60,  28),
    "front": ((0.0, -1.0, 1.8),     0,  14,  42.0,  50.0,  -60,  30),
    "back":  ((0.0, 0.0, 1.0),   200,  34,  58.0,  50.0,   60,  32),
    "right": ((0.0, 0.0, 1.0),    70,  30,  58.0,  50.0,  -40,  32),
    "close": ((0.0, 4.0, 2.4),   -24,  26,  30.0,  50.0,  -75,  28),
    "top":   ((0.0, 0.0, 0.0),     0,  89,  64.0,  50.0,  -60,  45),
}


def render(path, target, az, el, dist, lens, sun_az, sun_el, res=(1400, 800), samples=32, cpu=False):
    """voxlib.render with a choice of device (the Metal kernels can crash when the GPU is shared)."""
    scene = bpy.context.scene
    sun = V.setup_light(scene, sun_az, sun_el, strength=5.5, sky=0.55)
    sun.data.color = (1.0, 0.80, 0.58)                     # the picture's late golden light
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
    scene.view_settings.view_transform = "AgX"
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 4
    if cpu:
        scene.cycles.device = "CPU"
    else:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "METAL"
        prefs.get_devices()
        for dev in prefs.devices:
            dev.use = True
        scene.cycles.device = "GPU"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.render.render(write_still=True)
    print("rendered", path)


def render_view(name):
    target, az, el, dist, lens, sun_az, sun_el = VIEWS[name]
    path = os.path.join(V.PREVIEWS, "farmstead_%s.png" % name)
    V.reset_scene()
    ob = build_farmstead()
    scene_with_props(ob)
    try:
        render(path, target, az, el, dist, lens, sun_az, sun_el, samples=SAMPLES, cpu=USE_CPU)
    except RuntimeError as e:
        print("GPU render failed (%s), using the CPU" % str(e).splitlines()[0][:80])
        bpy.context.scene.cycles.device = "CPU"
        bpy.ops.render.render(write_still=True)


def main():
    V.reset_scene()
    t0 = time.time()
    ob = build_farmstead()
    co = np.zeros(len(ob.data.vertices) * 3, np.float32)
    ob.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    props = json.loads(ob["props"])
    print("SM_Farmstead bounds", np.round(co.min(axis=0), 3), np.round(co.max(axis=0), 3), "faces", ob["voxel_faces"],
          "props", {m: sum(1 for p in props if p["mesh"] == m) for m in ("SM_Wheat", "SM_Sheep")},
          "built in %.1f s" % (time.time() - t0))
    if not NO_EXPORT:
        V.export_gltf(ob, collision="complex", extra=dict(props=props))
    if NO_RENDER:
        return
    for name in (VIEW_LIST or ["ref", "front", "back", "close"]):
        render_view(name)


main()
