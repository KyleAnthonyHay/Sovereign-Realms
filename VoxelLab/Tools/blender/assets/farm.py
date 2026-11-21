"""The farms of the voxel village: two cottages, the paddock fence set, wheat, hay, a sheep and a trough.

    Blender -b --factory-startup --python Tools/blender/assets/farm.py -- [--no-render] [--no-export] [--only a,b,props,scene]

Fronts face -Y. Buildings and the lantern pier are on the 12.5 cm grid; the small pieces (fence, wheat, hay, sheep,
trough) are on the 6.25 cm grid so that rails, straps and faces can be finer than a wall block.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import math
import numpy as np
import bpy
import voxlib as V
import voxkit as K
from voxlib import Vox

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
NO_RENDER = "--no-render" in ARGS
NO_EXPORT = "--no-export" in ARGS
ONLY = None
for _i, _a in enumerate(ARGS):
    if _a == "--only" and _i + 1 < len(ARGS):
        ONLY = set(ARGS[_i + 1].split(","))

T = 0.0625                                                     # the fine grid
WOODS = ("#f6d2ac", "#dcae82", "#ecc097", "#cb9a6c")           # tints that make neighbouring timbers read as separate blocks
TILE = "#7cb6a4"                                               # roof tiles: a little darker and bluer than the raw texture
TILE_LIGHT = "#d8f0a8"
LEAF_TINTS = (None, "#d8e8a0", "#b0c890", None)
FLOWERS = ("flower_white", "flower_yellow", "flower_orange", "flower_pink")


# ---------------------------------------------------------------------------------------------------- helpers

def roof_steps(b0, b1, z, run, rise):
    out = []
    i = 0
    while b1 - b0 - 2 * i * run > 0:
        out.append((b0 + i * run, b1 - i * run, z + i * rise))
        i += 1
    return out


def roof_under(b0, b1, z, run, rise):
    """-> f(b): the height of the underside of the stepped roof above across-coordinate b."""
    n = len(roof_steps(b0, b1, z, run, rise))

    def under(b):
        i = min((b - b0) // run, (b1 - 1 - b) // run)
        return z + max(0, min(i, n - 1)) * rise
    return under


def gable(v, a0, a1, b0, b1, z, ridge="y", run=4, rise=3, thick=3, cube=4, ends=(True, True), tile=TILE, ridge_w=4,
          seed=0, eave=True):
    """A stepped gable roof as a SHELL (so the gable wall stays visible under the overhang), with chunky wooden blocks
    stepping up the gable ends and a ridge of wooden blocks. along = the ridge direction (a0..a1), across = b0..b1."""
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
    """A small glowing window. The wall's outer face is the voxel layer `plane` on `axis`, facing `out`. The panes
    replace that layer; the frame stands one voxel proud, the sill `sill` voxels."""
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
    """Leaf voxels creeping over a list of (x, y, z) anchor cells: each grows a run of leaves down (hang) or up, only
    into air."""
    rng = np.random.default_rng(seed)
    for (x, y, z) in cells:
        if rng.random() > density:
            continue
        n = int(rng.integers(hmin, hmax + 1))
        for k in range(n):
            zz = z - k if hang else z + k
            if v.get(x, y, zz) is None and 0 <= zz < v.n[2] and 0 <= x < v.n[0] and 0 <= y < v.n[1]:
                c = LEAF_TINTS[int(rng.integers(0, len(LEAF_TINTS)))]
                v.set(x, y, zz, "leaves", c)


def flower_box(v, x0, x1, y0, y1, z, seed=0):
    rng = np.random.default_rng(seed)
    v.box(x0, y0, z, x1, y1, z + 2, "plank", WOODS[1])
    for x in range(x0, x1):
        for y in range(y0, y1):
            r = rng.random()
            if r < 0.45:
                v.set(x, y, z + 2, "paint", FLOWERS[int(rng.integers(0, 4))])
            elif r < 0.9:
                v.set(x, y, z + 2, "leaves", LEAF_TINTS[int(rng.integers(0, 4))])


def centre_origin(v):
    lo, hi = v.bounds()
    v.origin = ((lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0, 0.0)
    return lo, hi


# ---------------------------------------------------------------------------------------------------- cottages

def cottage_vox(variant):
    A = variant == "A"
    v = Vox(72, 60, 48, 0.125, name="cottage" + variant, seed=3 if A else 8)
    W = 36 if A else 32                    # width of the gable front (X)
    D = 32                                 # depth (Y)
    X0, Y0 = 14, 12
    X1, Y1 = X0 + W, Y0 + D
    ZF, ZE = 4, 17                         # top of the stone footing; the eaves
    cx = X0 + W // 2
    RUN, RISE = 4, 3
    b0, b1 = X0 - 3, X1 + 3                # the roof across X, 3 voxels of eave
    a0, a1 = Y0 - 3, Y1 + 3                # and along Y, 3 voxels of gable overhang (the barge blocks touch the wall)
    steps = roof_steps(b0, b1, ZE, RUN, RISE)
    under = roof_under(b0, b1, ZE, RUN, RISE)

    # ---- stone footing (chunky) and the solid body under the roof
    v.box(X0 - 2, Y0 - 2, 0, X1 + 2, Y1 + 2, ZF, "stone")
    v.chunky("stone", p=0.4, seed=2 if A else 6)
    for (lo, hi, zl) in steps:
        v.box(max(lo, X0), Y0, ZF, min(hi, X1), Y1, zl, "plaster")
    v.tint("plaster", "#e9e2d0", p=0.35, cell=4, seed=4)
    v.tint("plaster", "#d9d2c2", p=0.12, cell=4, seed=9)

    # ---- timber frame, one voxel proud of the walls
    for (px, py) in ((X0 - 1, Y0 - 1), (X1 - 2, Y0 - 1), (X0 - 1, Y1 - 2), (X1 - 2, Y1 - 2)):
        v.box(px, py, ZF, px + 3, py + 3, ZE + 3, "post")
    for sx in (cx - 6, cx + 4):                                                 # studs beside the door, up into the gable
        top = min(under(sx), under(sx + 1))
        v.box(sx, Y0 - 1, ZF, sx + 2, Y0, top, "post")
        v.box(sx, Y1, ZF, sx + 2, Y1 + 1, top, "post")
    v.box(X0, Y1, 8, X1, Y1 + 1, 9, "beam")                                     # back wall rail
    # side walls: plate under the eaves, a rail at sill height, posts
    for px in (X0 - 1, X1):
        v.box(px, Y0, ZE - 2, px + 1, Y1, ZE, "beam")
        v.box(px, Y0, 8, px + 1, Y1, 9, "beam")
    if A:
        side_posts = {X0 - 1: (Y0 + 15,), X1: (Y0 + 15,)}
    else:
        side_posts = {X0 - 1: (Y0 + 9, Y0 + 20), X1: (Y0 + 13,)}
    for px, ys in side_posts.items():
        for py in ys:
            v.box(px, py, ZF, px + 1, py + 2, ZE, "post")

    # ---- door and windows
    K.door(v, "y", Y0, cx - 4, 2, w=8, h=15, out=-1)
    v.box(cx - 4, Y0, 2, cx + 4, Y0 + 1, 17, "plank", "#c79668")
    for zz in (5, 13):
        v.box(cx - 4, Y0, zz, cx + 4, Y0 + 1, zz + 1, "metal")
    v.clear(cx - 4, Y0 - 3, 2, cx + 4, Y0, ZF + 1)                              # the footing gives way to the door
    v.box(cx - 5, Y0 - 4, 0, cx + 5, Y0, 2, "stone")                            # threshold and step
    if A:
        win(v, "y", Y0, X0 + 5, 9)
        win(v, "y", Y0, X1 - 10, 9)
        win(v, "y", Y0, cx - 2, 21)                                             # the little gable window
        win(v, "x", X0, Y0 + 6, 9, out=-1)
        win(v, "x", X0, Y0 + 21, 9, out=-1)
        win(v, "x", X1 - 1, Y0 + 21, 9, out=1)
        win(v, "y", Y1 - 1, cx - 2, 9, out=1)
    else:
        win(v, "y", Y0, X0 + 4, 9)
        win(v, "y", Y0, X1 - 7, 9, w=3, vbar=False)
        win(v, "y", Y0, cx - 2, 21)
        win(v, "x", X0, Y0 + 13, 9, out=-1)
        win(v, "x", X1 - 1, Y0 + 5, 9, out=1)
        win(v, "y", Y1 - 1, cx + 3, 9, out=1)
    for k in range(3):                                                          # louvred vent in the back gable
        v.box(cx - 3, Y1, 22 + 2 * k, cx + 3, Y1 + 1, 23 + 2 * k, "beam")
    # plate beams across the gable fronts: two voxels proud, the door's lintel
    for k, bx in enumerate(range(X0 - 1, X1 + 1, 6)):
        v.box(bx, Y0 - 2, ZE, min(bx + 6, X1 + 1), Y0, ZE + 3, "plank", WOODS[1 + 2 * (k % 2)])
        v.box(bx, Y1, ZE, min(bx + 6, X1 + 1), Y1 + 2, ZE + 3, "plank", WOODS[1 + 2 * (k % 2)])
    for bx in (X0 + 2, cx - 7, cx + 6, X1 - 3):                                 # little brackets under the front plate
        v.box(bx, Y0 - 2, ZE - 2, bx + 1, Y0 - 1, ZE, "beam")

    # ---- roof
    top = gable(v, a0, a1, b0, b1, ZE, ridge="y", run=RUN, rise=RISE, seed=0 if A else 1)

    if A:
        # a little stone chimney on the left slope, towards the back
        qx, qy = X0 + 5, Y1 - 12
        v.box(qx, qy, 20, qx + 5, qy + 5, 33, "stone")
        v.box(qx - 1, qy - 1, 33, qx + 6, qy + 6, 35, "stone")
        v.box(qx + 1, qy + 1, 35, qx + 4, qy + 4, 36, "paint", "#3a3430")
        v.chunky("stone", p=0.2, seed=5, region=(qx - 2, qy - 2, 24, qx + 7, qy + 7, 33))
        # a creep of moss climbing the left slope, as in the picture
        for i, (lo, hi, zl) in enumerate(steps[:5]):
            yb = a0 + 3 + i * 4
            v.box(lo + (1 if i == 0 else 0), yb, zl + 2, lo + 4, yb + 5, zl + 3, "moss")
        # barrel, crate and a sack by the right wall near the front corner
        v.stamp(K.barrel(), X1 + 4, Y0 + 5, 0)
        v.stamp(K.crate(5), X1 + 4, Y0 + 13, 0, overwrite=False)
        v.box(X1 + 2, Y0 + 12, 5, X1 + 5, Y0 + 15, 7, "paint", "canvas")
        v.box(X1 + 3, Y0 + 13, 7, X1 + 4, Y0 + 14, 8, "paint", "cream_dark")
    else:
        # ---- a cross gable (wall dormer) on the left side
        d = Vox(*v.n, voxel=0.125, seed=v.seed)
        dy0, dy1 = Y0 + 9, Y0 + 22                                              # 13 wide
        r0, r1, rz = dy0 - 2, dy1 + 2, 24
        dunder = roof_under(r0, r1, rz, 3, 2)
        for (lo, hi, zl) in roof_steps(r0, r1, rz, 3, 2):
            d.box(X0, max(lo, dy0), ZE, cx, min(hi, dy1), zl, "plaster")
        for py in (dy0, dy1 - 2):
            d.box(X0 - 1, py, ZE, X0, py + 2, min(dunder(py), dunder(py + 1)), "post")
        win(d, "x", X0, dy0 + 4, 19, out=-1)
        gable(d, X0 - 3, cx, r0, r1, rz, ridge="x", run=3, rise=2, thick=2, cube=3, ends=(True, False), ridge_w=3, seed=2)
        dm = d.m > 0
        zone = np.zeros_like(dm)
        zone[:X0 + 2, r0:r1, ZE:] = True
        v.clear(X0 - 4, dy0, ZE, X0, dy1, ZE + 4)                               # the eave stops at the dormer
        take = dm & ((v.m == 0) | zone)
        v.m[take] = d.m[take]
        v.c[take] = d.c[take]
        # ---- chimney on the right slope, near the back
        v.box(cx + 3, Y0 + 22, 20, cx + 8, Y0 + 27, 36, "stone")
        v.box(cx + 2, Y0 + 21, 36, cx + 9, Y0 + 28, 38, "stone")
        v.box(cx + 4, Y0 + 23, 38, cx + 7, Y0 + 26, 39, "paint", "#3a3430")
        v.chunky("stone", p=0.22, seed=5, region=(cx, Y0 + 19, 22, cx + 11, Y0 + 30, 36))
        # ---- firewood lean-to on the right wall, back half
        ly0, ly1 = Y0 + 17, Y1 + 1
        for k in range(3):
            for j, yy in enumerate(range(ly0, ly1, 4)):
                v.box(X1 + 4 * k, yy, 15 - k, X1 + 4 * k + (4 if k < 2 else 3), min(yy + 4, ly1), 17 - k, "plank",
                      WOODS[(j + k) % 4])
        for py in (ly0 + 1, ly1 - 3):
            v.box(X1 + 8, py, 0, X1 + 10, py + 2, 13, "post")
        v.box(X1 + 8, ly0, 12, X1 + 10, ly1, 13, "beam")
        rng = np.random.default_rng(4)
        for row in range(4):
            for col in range(4):
                yy = ly0 + 4 + col * 2 + (row % 2)
                if yy + 2 > ly1 - 3 or (row == 3 and col in (0, 3)):
                    continue
                ln = int(rng.integers(5, 7))
                v.box(X1, yy, row * 2, X1 + ln, yy + 2, row * 2 + 2, "log", WOODS[int(rng.integers(0, 4))])
                v.box(X1 + ln - 1, yy, row * 2, X1 + ln, yy + 2, row * 2 + 2, "paint",
                      ("#d9a565", "#c98f4e", "#e2b377")[int(rng.integers(0, 3))])
        flower_box(v, X0 + 3, X0 + 10, Y0 - 3, Y0 - 1, 7, seed=3)

    K.wall_lantern(v, cx + 5, Y0 - 1, 16)

    # ---- life: lighter tiles, moss, ivy
    v.tint("roof", TILE_LIGHT, p=0.13, cell=2, seed=7)
    v.scatter("roof", "moss", p=0.05, seed=4, direction="+z")
    v.scatter("plank", "moss", p=0.07, seed=6, direction="+z", region=(0, 0, ZE - 1, v.n[0], v.n[1], v.n[2]))
    v.scatter("stone", "mossy_stone", p=0.10, seed=8, direction="+z")
    if A:
        cells = [(x, Y0 - 1, under(x) - 1) for x in range(X0 + 2, X0 + 5)]
        cells += [(X0 - 1, y, ZE - 3) for y in range(Y0 + 2, Y0 + 5)]
        ivy(v, cells, seed=2, hmin=3, hmax=9)
        ivy(v, [(X0 - 2, Y0 - 2, ZF), (X0 - 2, Y0 - 1, ZF), (X0 - 1, Y0 - 2, ZF)], seed=3, hmin=5, hmax=13, hang=False, density=1.0)
        ivy(v, [(x, Y1 + 1, ZE - 1) for x in range(X1 - 9, X1 - 2)], seed=5, hmin=2, hmax=8)
    else:
        ivy(v, [(X0 - 1, y, ZE - 3) for y in range(Y1 - 8, Y1 - 2)], seed=2, hmin=2, hmax=8)
        ivy(v, [(X1 - 3 - k, Y0 - 1, ZE - 1) for k in range(4)], seed=6, hmin=2, hmax=6)
        ivy(v, [(x, Y1 + 1, ZE - 1) for x in range(X0 + 1, X0 + 9)], seed=5, hmin=2, hmax=8)
    lo, hi = centre_origin(v)
    v.info = dict(door=((cx - v.origin[0]) * 0.125, (Y0 - v.origin[1]) * 0.125), top=top * 0.125,
                  size=tuple(float(s) * 0.125 for s in (hi - lo)))
    return v


def build_cottage_a():
    v = cottage_vox("A")
    ob = v.to_object("SM_FarmCottage_A")
    ob["info"] = str(v.info)
    return ob


def build_cottage_b():
    v = cottage_vox("B")
    ob = v.to_object("SM_FarmCottage_B")
    ob["info"] = str(v.info)
    return ob


# ---------------------------------------------------------------------------------------------------- fence

def _fence_post(v, x, y, w=4, h=17, tint=WOODS[1]):
    v.box(x, y, 0, x + w, y + w, h, "post", tint)
    v.box(x, y, h - 2, x + w, y + w, h, "post")                                 # a paler head
    v.box(x, y, h - 4, x + w, y + w, h - 3, None)                               # with a groove under it
    v.box(x + 1, y + 1, h - 4, x + w - 1, y + w - 1, h - 3, "post", WOODS[3])


def _fence_rails(v, x0, x1, y):
    v.box(x0, y, 5, x1, y + 2, 8, "plank", "#d2bc9c")
    v.box(x0, y, 11, x1, y + 2, 14, "plank", "#e2ccac")


def build_fence_straight():
    v = Vox(34, 4, 18, T, origin=(2, 2, 0), name="fence")
    _fence_rails(v, 2, 34, 1)
    _fence_post(v, 0, 0)
    _fence_post(v, 16, 0)
    return v.to_object("SM_Fence_Straight")


def build_fence_post():
    v = Vox(4, 4, 18, T, origin=(2, 2, 0), name="fence_post")
    _fence_post(v, 0, 0)
    return v.to_object("SM_Fence_Post")


def build_fence_post_lantern():
    v = Vox(10, 10, 18, 0.125, origin=(5, 5, 0), name="fence_lantern", seed=2)
    v.box(2, 2, 0, 8, 8, 2, "stone")
    v.box(3, 3, 2, 7, 7, 8, "brick", "#e2b07c")                                # a warm brown pier
    v.chunky(["stone", "brick"], cell=2, p=0.22, seed=3)
    v.box(2, 2, 8, 8, 8, 9, "beam")
    K.lantern(v, 5, 5, 9, 4)
    v.scatter("stone", "mossy_stone", p=0.3, seed=1, direction="+z")
    v.scatter("brick", "moss", p=0.06, seed=4)
    return v.to_object("SM_Fence_Post_Lantern")


def build_fence_gate():
    v = Vox(38, 8, 22, T, origin=(3, 4, 0), name="gate")
    for px in (0, 32):                                                          # two stout posts, 2.0 m apart
        v.box(px, 1, 0, px + 6, 7, 20, "post", WOODS[1])
        v.box(px, 1, 17, px + 6, 7, 20, "post")
        v.box(px, 1, 15, px + 6, 7, 16, None)
        v.box(px + 1, 2, 15, px + 5, 6, 16, "post", WOODS[3])
        v.box(px + 1, 2, 20, px + 5, 6, 21, "post")
    heights = (15, 16, 17, 17, 16, 15)
    for i in range(6):                                                          # the leaf: six upright planks
        v.box(7 + i * 4, 3, 3, 11 + i * 4, 5, heights[i], "post", ("#fff0dc", "#ecd4b4", "#ffffff")[i % 3])
    for yy in (2, 5):                                                           # ledges and a brace, both faces
        v.box(7, yy, 5, 31, yy + 1, 7, "beam")
        v.box(7, yy, 12, 31, yy + 1, 14, "beam")
        for x in range(9, 29):
            zb = 7 + int((x - 9) * 3 / 19.0 + 0.5)
            v.box(x, yy, zb, x + 1, yy + 1, zb + 2, "beam")
    for zz in (5, 12):                                                          # strap hinges
        v.box(5, 1, zz, 12, 2, zz + 2, "metal")
        v.box(5, 6, zz, 12, 7, zz + 2, "metal")
    v.box(27, 1, 9, 33, 2, 10, "metal")                                         # latch
    v.box(27, 0, 8, 28, 1, 11, "metal")
    return v.to_object("SM_Fence_Gate")


# ---------------------------------------------------------------------------------------------------- wheat

def build_wheat():
    """16 x 16 texels. Tufts sit on a 4-texel pitch that carries on across neighbouring patches, so a field of
    patches on a 1 m grid has no seams."""
    v = Vox(16, 16, 16, T, origin=(8, 8, 0), name="wheat", seed=1)
    rng = np.random.default_rng(7)
    LOW = ("#e2ae58", "#d9a44c", "#ebb964")
    MID = ("#fbd98c", "#f3cc78", "#ffe29c")
    EAR = (None, "#fff0c0", None)
    TIP = ("#ffd65e", "#ffcf4a", "#ffe07a")
    ring = [(-1, 0), (-1, 1), (2, 0), (2, 1), (0, -1), (1, -1), (0, 2), (1, 2)]

    def pick(seq):
        return seq[int(rng.integers(0, len(seq)))]

    for i in range(4):
        for j in range(4):
            # a tuft: a bundle of stalks, blades standing off it, a fat ear and a tip
            x = 4 * i + 1 + int(rng.integers(0, 2)) - (1 if i == 3 else 0)
            y = 4 * j + 1 + int(rng.integers(0, 2)) - (1 if j == 3 else 0)
            h0 = int(rng.integers(3, 6))
            h1 = h0 + int(rng.integers(3, 6))
            h2 = min(h1 + 3, 14)
            v.box(x, y, 0, x + 2, y + 2, h0, "wheat", pick(LOW))
            v.box(x, y, h0, x + 2, y + 2, h1, "wheat", pick(MID))
            for k in rng.permutation(8)[:3]:
                bx, by = x + ring[k][0], y + ring[k][1]
                if 0 <= bx < 16 and 0 <= by < 16:
                    b0 = int(rng.integers(1, h0))
                    v.box(bx, by, b0, bx + 1, by + 1, min(h1 + int(rng.integers(-2, 2)), 13), "wheat", pick(MID))
            v.box(x, y, h1, x + 2, y + 2, h2, "wheat", pick(EAR))
            tx, ty = x + int(rng.integers(0, 2)), y + int(rng.integers(0, 2))
            v.box(tx, ty, h2, tx + 1, ty + 1, min(h2 + int(rng.integers(1, 3)), 15), "paint", pick(TIP))
            # a thin one in the gap
            x2, y2 = 4 * i + 3 - int(rng.integers(0, 2)) * 3 * (i == 3), 4 * j + 3 - int(rng.integers(0, 2)) * 3 * (j == 3)
            if v.get(x2, y2, 0) is None:
                h = int(rng.integers(6, 10))
                v.box(x2, y2, 0, x2 + 1, y2 + 1, h, "wheat", pick(LOW))
                v.box(x2, y2, h, x2 + 1, y2 + 1, h + 2, "wheat", pick(EAR))
                v.set(x2, y2, h + 2, "paint", pick(TIP))
    return v.to_object("SM_Wheat")


# ---------------------------------------------------------------------------------------------------- hay

def bale_vox(seed=0):
    """A bale 1.0 x 0.625 x 0.625 m (16 x 10 x 10 texels), long along X, two twine straps sunk into it."""
    v = Vox(18, 12, 11, T, origin=(9, 6, 0), name="bale", seed=seed)
    v.box(1, 1, 0, 17, 11, 10, "hay")
    rng = np.random.default_rng(seed + 20)
    for sx in (5, 12):
        v.box(sx, 1, 0, sx + 1, 11, 10, None)
        v.box(sx, 2, 1, sx + 1, 10, 9, "paint", "#7a5226")
    v.tint("hay", "#f3dfa2", p=0.3, cell=2, seed=seed)
    v.tint("hay", "#e2c070", p=0.15, cell=2, seed=seed + 3)
    for _ in range(14):                                                         # loose straw standing out of it
        f = int(rng.integers(0, 5))
        a, b = int(rng.integers(1, 17)), int(rng.integers(1, 10))
        if a in (5, 12) and f in (0, 1, 2):
            continue
        if f == 0:
            v.set(a, min(b + 1, 10), 10, "hay", "#fff0b0")
        elif f == 1:
            v.set(a, 0, b, "hay", "#fff0b0")
        elif f == 2:
            v.set(a, 11, b, "hay", "#fff0b0")
        elif f == 3:
            v.set(0, min(b + 1, 10), int(rng.integers(0, 10)), "hay", "#fff0b0")
        else:
            v.set(17, min(b + 1, 10), int(rng.integers(0, 10)), "hay", "#fff0b0")
    return v


def build_hay_bale():
    return bale_vox(1).to_object("SM_HayBale")


def build_hay_stack():
    b = 0.625
    parts = [bale_vox(2).at(-0.33, -0.33, 0), bale_vox(3).at(-0.28, 0.33, 0),
             bale_vox(4).at(-0.42, 0.02, b, 1), bale_vox(5).at(0.56, 0.05, 0, 1)]
    return V.join(parts, "SM_HayStack")


# ---------------------------------------------------------------------------------------------------- sheep, trough

def build_sheep():
    """Faces -Y. 1.0 m long, about 0.9 m to the top of the head."""
    v = Vox(14, 18, 16, T, origin=(7, 9, 0), name="sheep", seed=4)
    for lx in (3, 9):
        for ly in (5, 13):
            v.box(lx, ly, 0, lx + 2, ly + 2, 5, "wool", "#e6dccb")
            v.box(lx, ly, 0, lx + 2, ly + 2, 1, "paint", "#4a4038")
    v.box(2, 4, 4, 12, 16, 12, "wool")                                          # body
    v.chunky("wool", cell=2, p=0.22, seed=3, region=(0, 4, 5, 14, 18, 16))      # tufts
    v.box(6, 16, 8, 8, 17, 10, "wool")                                          # tail
    v.box(3, 2, 8, 11, 6, 15, "wool")                                           # the woolly hood
    v.box(4, 1, 8, 10, 3, 13, "paint", "sheep_face")                            # face
    v.box(5, 0, 8, 9, 1, 10, "paint", "sheep_face")                             # muzzle
    v.box(6, 0, 9, 8, 1, 10, "paint", "#e2a79c")                                # nose
    v.set(4, 0, 11, "paint", "black")
    v.set(9, 0, 11, "paint", "black")
    v.box(4, 0, 11, 5, 1, 12, "paint", "black")
    v.box(9, 0, 11, 10, 1, 12, "paint", "black")
    v.box(2, 2, 11, 3, 4, 12, "paint", "sheep_face")                            # ears
    v.box(11, 2, 11, 12, 4, 12, "paint", "sheep_face")
    return v.to_object("SM_Sheep")


def build_trough():
    """1.5 m long along X, 0.5 m wide, on two trestle ends, water inside."""
    v = Vox(24, 10, 9, T, origin=(12, 5, 0), name="trough")
    for i, x in enumerate(range(0, 24, 4)):
        v.box(x, 1, 2, x + 4, 9, 8, "plank", WOODS[(i * 3) % 4])
    v.box(1, 2, 3, 23, 8, 8, None)
    v.box(1, 2, 3, 23, 8, 6, "water")
    for x in (2, 20):                                                           # trestle ends
        v.box(x, 0, 0, x + 2, 10, 3, "beam")
        v.box(x, 0, 3, x + 2, 1, 6, "beam")
        v.box(x, 9, 3, x + 2, 10, 6, "beam")
    for x in (7, 16):                                                           # iron bands
        v.box(x, 1, 2, x + 1, 9, 3, "metal")
        v.box(x, 1, 2, x + 1, 2, 8, "metal")
        v.box(x, 8, 2, x + 1, 9, 8, "metal")
    return v.to_object("SM_Trough")


# ---------------------------------------------------------------------------------------------------- scenes

ASSETS = [
    ("SM_FarmCottage_A", build_cottage_a, "complex"),
    ("SM_FarmCottage_B", build_cottage_b, "complex"),
    ("SM_Fence_Straight", build_fence_straight, "complex"),
    ("SM_Fence_Post", build_fence_post, "complex"),
    ("SM_Fence_Post_Lantern", build_fence_post_lantern, "complex"),
    ("SM_Fence_Gate", build_fence_gate, "complex"),
    ("SM_Wheat", build_wheat, "none"),
    ("SM_HayBale", build_hay_bale, "complex"),
    ("SM_HayStack", build_hay_stack, "complex"),
    ("SM_Sheep", build_sheep, "complex"),
    ("SM_Trough", build_trough, "complex"),
]


def render(path, **kw):
    """V.render, but the GPU is shared with other jobs: on an out-of-memory error wait and retry, then use the CPU."""
    import time
    for attempt in range(3):
        try:
            return V.render(path, **kw)
        except RuntimeError as e:
            print("render failed (%s), attempt %d" % (str(e)[:80], attempt))
            time.sleep(20)
    bpy.context.scene.cycles.device = "CPU"
    bpy.ops.render.render(write_still=True)
    print("rendered (CPU)", path)
    return path


def put(ob, x=0.0, y=0.0, rot=0.0, z=0.0, copy=True):
    o = ob.copy() if copy else ob
    if copy:
        bpy.context.scene.collection.objects.link(o)
    o.location = (x, y, z)
    o.hide_render = False
    o.rotation_euler = (0, 0, math.radians(rot))
    return o


def stash(ob):
    ob.location = (0, 0, -500)
    ob.hide_render = True
    return ob


def ground(w=28, d=26, dirt=None, seed=0):
    """A grass slab for previews (25 cm voxels), with a dirt patch: dirt = (x0, y0, x1, y1) in metres."""
    nx, ny = int(w / 0.25), int(d / 0.25)
    g = Vox(nx, ny, 2, 0.25, origin=(nx / 2.0, ny / 2.0, 2), name="ground", seed=seed)
    g.box(0, 0, 0, nx, ny, 2, "grass")
    if dirt:
        X, Y, Z = g.grid()
        n = V.noise3(g.n, 5, seed + 3)
        mx, my = (X - nx / 2.0) * 0.25, (Y - ny / 2.0) * 0.25
        inside = (mx > dirt[0] - 1 + n * 2) & (mx < dirt[2] + 1 - n * 2) & (my > dirt[1] - 1 + n * 2) & (my < dirt[3] + 1 - n * 2)
        g.where(inside & (Z == 1), "dirt")
    return g.to_object("PreviewTerrain")


def farm_scene(variant):
    """The paddock of the picture: 8 x 8 m of fence with lantern piers, the cottage's door to the east (+X)."""
    V.reset_scene()
    A = variant == "A"
    cot = build_cottage_a() if A else build_cottage_b()
    fence, post, pier, gate = stash(build_fence_straight()), stash(build_fence_post()), stash(build_fence_post_lantern()), stash(build_fence_gate())
    wheat, stack, bale, sheep, trough = stash(build_wheat()), stash(build_hay_stack()), stash(build_hay_bale()), stash(build_sheep()), stash(build_trough())
    ground(dirt=(-1.8, -4.3, 4.2, -1.7), seed=1 if A else 2)
    put(cot, -1.6, 1.6, 90, copy=False)
    x0, y0, nx, ny = -5.0, -5.0, 5, 5
    x1, y1 = x0 + 2 * nx, y0 + 2 * ny
    for k in range(nx):
        put(fence, x0 + 2 * k, y0, 0)                                          # south side
        put(fence, x1 - 2 * k, y1, 180)                                        # north
    for k in range(ny):
        put(gate if k == 2 else fence, x1, y0 + 2 * k, 90)                     # east, the gate before the door
        put(fence, x0, y1 - 2 * k, 270)                                        # west
    for (x, y) in ((x0, y0), (x1, y1), (x0, y1)):
        put(pier, x, y)
    rng = np.random.default_rng(5)
    for i in range(5):
        for j in range(2):
            put(wheat, -1.0 + i, -3.5 + j, 180 * int(rng.integers(0, 2)))
    put(sheep, -3.7, -3.1, 25)
    put(sheep, -2.8, -2.2, -70)
    put(trough, -4.3, -0.4, 90)
    put(stack, 3.7, 3.6, 90)
    put(bale, 3.6, 2.0, 20)
    render(os.path.join(V.PREVIEWS, "farm_scene_%s.png" % variant.lower()), target=(0.0, 0.0, 1.0), az=40, el=32, dist=36, lens=85,
           samples=64, sun_az=80, sun_el=30)


def cottage_views(variant):
    V.reset_scene()
    ob = build_cottage_a() if variant == "A" else build_cottage_b()
    print("cottage", variant, ob["info"])
    n = "farm_cottage_%s" % variant.lower()
    render(os.path.join(V.PREVIEWS, n + ".png"), target=(0, 0, 2.1), az=28, el=30, dist=27, lens=85, sun_az=120, sun_el=32)
    render(os.path.join(V.PREVIEWS, n + "_left.png"), target=(0, 0, 2.1), az=-50, el=30, dist=27, lens=85)
    render(os.path.join(V.PREVIEWS, n + "_back.png"), target=(0, 0, 2.1), az=205, el=30, dist=27, lens=85)


def props_view():
    V.reset_scene()
    fence, post, pier, gate = build_fence_straight(), build_fence_post(), build_fence_post_lantern(), build_fence_gate()
    wheat, stack, bale, sheep, trough = build_wheat(), build_hay_stack(), build_hay_bale(), build_sheep(), build_trough()
    put(fence, -5.0, 1.5, copy=False)
    put(fence, -3.0, 1.5)
    put(gate, -1.0, 1.5, copy=False)
    put(fence, 1.0, 1.5)
    put(pier, 3.0, 1.5, copy=False)
    put(post, 4.2, 1.5, copy=False)
    put(wheat, -4.5, -1.0, copy=False)
    put(wheat, -3.5, -1.0, 180)
    put(wheat, -4.5, -2.0, 180)
    put(wheat, -3.5, -2.0)
    put(sheep, -1.8, -1.3, -30, copy=False)
    put(sheep, -0.6, -1.6, 200)
    put(bale, 0.9, -1.4, copy=False)
    put(stack, 2.8, -1.3, copy=False)
    put(trough, 4.6, -1.0, 90, copy=False)
    render(os.path.join(V.PREVIEWS, "farm_props.png"), target=(0.0, -0.2, 0.6), az=28, el=30, dist=24, lens=85, res=(1600, 800))
    render(os.path.join(V.PREVIEWS, "farm_props_back.png"), target=(0.0, -0.2, 0.6), az=200, el=30, dist=24, lens=85, res=(1600, 800))


def want(key):
    return ONLY is None or key in ONLY


if not NO_EXPORT:
    for name, fn, collision in ASSETS:
        key = {"SM_FarmCottage_A": "a", "SM_FarmCottage_B": "b"}.get(name, "props")
        if not want(key):
            continue
        V.reset_scene()
        ob = fn()
        V.export_gltf(ob, collision=collision)
        co = np.zeros(len(ob.data.vertices) * 3, np.float32)
        ob.data.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        print("ASSET %-24s faces %6d  min %s  max %s  %s" % (name, ob["voxel_faces"], np.round(co.min(axis=0), 3),
                                                            np.round(co.max(axis=0), 3), ob.get("info", "")))

if not NO_RENDER:
    if want("a"):
        cottage_views("A")
    if want("b"):
        cottage_views("B")
    if want("props"):
        props_view()
    if want("scene"):
        farm_scene("A")
    if want("sceneb"):
        farm_scene("B")
