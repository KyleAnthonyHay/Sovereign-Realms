"""King David (version A), the player's avatar: seven rigid parts (a wooden toy), each exported on its own with its mesh
origin at its joint, built from INDIVIDUAL BEVELLED BLOCKS of several sizes.

    Blender -b --factory-startup --python Tools/blender/assets/king_a.py -- [--no-render] [--views compare,sides,face,walk] [--fast]

How it is made
  1. Each part is sculpted on a 1.25 cm design grid (world voxels): every cell holds a BASE (a named colour family with
     2-4 shades and a material: paint / gold / metal / wool) and a BLOCK SHAPE (how big the cubes there may be:
     4-voxel plates on the armour, 3-voxel cubes in the fur, 2 x 6 pleats on the tabard, single voxels in the eyes...).
  2. The grid is cut into blocks: the biggest aligned (and, on cloth and armour, brick-staggered) cells of one base
     become one block, what is left falls back to smaller blocks. Each block takes one shade of its base.
  3. Every visible block becomes a chamfered box (micro-bevel 8 % of its smallest side), so neighbouring blocks show a
     hairline seam and each edge catches a thin highlight; cape, fur, hair and some plates are pushed out by a little
     so no surface is perfectly flat. Faces hidden inside the part are dropped.
  4. Colour goes into a CORNER FLOAT_COLOR attribute "Col" (linear) multiplied by a baked proximity occlusion, so the
     seams and overlaps read in the engine; UVs are box-projected; material slots Vox_paint / Vox_gold / Vox_metal /
     Vox_wool; smooth shading with Weighted Normals (the bevels are soft, the faces flat).

World voxel coordinates: x = 0 is the middle of the figure (+X is his LEFT, he faces -Y), y = 0 runs through the hips
and shoulders, z = 0 is the ground. Corridors that keep the moving parts apart (|x| in voxels): tabard 0..8 (body),
legs 8..32 (skirt panel 8..25), waist 0..19.5, chest 0..25, arms 26..43, cape wings beyond 44.
A slight contrapposto (torso +2.5 deg, head -5 deg about Y) is applied to the finished meshes and to their joints.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import json
import math

import bpy
import numpy as np
import voxlib as V
import voxkit as K
from voxlib import Vox

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
NO_RENDER = "--no-render" in ARGS
FAST = "--fast" in ARGS
VIEWS = None
if "--views" in ARGS:
    VIEWS = set(ARGS[ARGS.index("--views") + 1].split(","))

PREFIX = "SM_KingA_"
VOX = 0.0125
X0, Y0 = 72, 50                      # grid index of world x = 0 / y = 0
NX, NY, NZ = 144, 104, 140
REF = os.path.join(V.ROOT, "References", "king.png")
BG = (0x53 / 255.0, 0x52 / 255.0, 0x53 / 255.0)

_ix, _iy, _iz = np.meshgrid(np.arange(NX), np.arange(NY), np.arange(NZ), indexing="ij")
XW = (_ix - X0 + 0.5).astype(np.float32)
YW = (_iy - Y0 + 0.5).astype(np.float32)
ZW = (_iz + 0.5).astype(np.float32)

HIP = 68.0
ARM_IN, ARM_OUT = 22.0, 36.0          # the arms' corridor (|x|)
CHEST, WAIST = 21.0, 17.0             # half widths of the chest and the cinched belt
CAPE_W0, CAPE_W1 = 40.5, 57.0         # outer half width of the cape at the shoulders and at the hem
JOINTS = {                           # world voxels, before the contrapposto
    "Body": (0.0, 0.0, HIP),
    "Head": (0.0, -1.0, 106.0),
    "ArmL": ((ARM_IN + ARM_OUT) / 2, 0.0, 105.0), "ArmR": (-(ARM_IN + ARM_OUT) / 2, 0.0, 105.0),
    "LegL": (17.0, 0.0, HIP), "LegR": (-17.0, 0.0, HIP),
    "Cape": (0.0, 17.0, 107.0),
}
ORDER = ["Body", "Head", "ArmL", "ArmR", "LegL", "LegR", "Cape"]
TORSO_TILT = 2.5                     # degrees about Y through the pelvis: Body, Head, arms, cape
HEAD_TILT = -4.0                     # degrees about Y through the neck, on top of the torso tilt
HEAD_TURN = 12.0                     # degrees about Z: towards his left, as in the picture

# ---------------------------------------------------------------------------------------------------- bases & shapes

SHAPES = {                           # name: (kx, ky, kz, staggered like bricks)
    "s1": (1, 1, 1, False), "s2": (2, 2, 2, False), "s3": (3, 3, 3, False), "s4": (4, 4, 4, True),
    "plate": (4, 4, 4, True), "tile": (3, 3, 3, True), "cloth": (4, 4, 5, False), "pleat": (2, 4, 6, False),
    "fur": (4, 4, 4, False), "band": (4, 3, 3, True), "blade": (2, 2, 2, False),
}
SHAPE_FILL = {"cloth": 0.5, "fur": 0.45, "plate": 0.6, "s4": 0.6, "band": 0.6, "tile": 0.65, "s3": 0.7, "pleat": 0.7}
SHAPE_NAMES = list(SHAPES)
SHAPE_ID = {n: i + 1 for i, n in enumerate(SHAPE_NAMES)}      # 0 = none

#      name        material  shades (sRGB, as seen on screen)                         shape    jitter (voxels)
_BASES = [
    ("gold",      "gold",  ["#e89a08", "#eea812", "#de8c06"],                          "s2",    0.15),
    ("gold_d",    "gold",  ["#b86504", "#aa5a02"],                                     "s2",    0.10),
    ("gold_l",    "gold",  ["#f4b81c", "#f8c62c"],                                     "s2",    0.15),
    ("steel",     "metal", ["#86838c", "#918e96", "#7b7880"],                          "plate", 0.10),
    ("steel_l",   "metal", ["#9f9ca4", "#aaa7ae", "#96939a"],                          "plate", 0.10),
    ("steel_d",   "metal", ["#6c6971", "#625f67"],                                     "plate", 0.08),
    ("steel_dd",  "metal", ["#5f5d66"],                                                "s1",    0.0),
    ("skin",      "paint", ["#c9733a", "#d07a3e", "#c06c34"],                          "s3",    0.0),
    ("skin_l",    "paint", ["#de8a4a", "#d88444"],                                     "s2",    0.0),
    ("skin_d",    "paint", ["#a85a2a", "#a05428"],                                     "s2",    0.0),
    ("skin_dd",   "paint", ["#7a3e1c"],                                                "s1",    0.0),
    ("lip",       "paint", ["#6a2c1c"],                                                "s1",    0.0),
    ("hair",      "paint", ["#2a201b", "#231a16", "#33281f"],                          "s3",    0.35),
    ("beard",     "paint", ["#2a201b", "#1f1813", "#362a22"],                          "s2",    0.3),
    ("brow",      "paint", ["#251c17", "#2e231d"],                                     "s1",    0.0),
    ("white",     "paint", ["#f4ebe0"],                                                "s1",    0.0),
    ("pupil",     "paint", ["#3f2616"],                                                "s1",    0.0),
    ("glint",     "paint", ["#a07a60"],                                                "s1",    0.0),
    ("fur",       "wool",  ["#efd6aa", "#f8e6c4", "#e3c696", "#f4dfb8"],               "fur",   0.55),
    ("fur_d",     "wool",  ["#d4b282", "#c9a472"],                                     "fur",   0.5),
    ("green",     "paint", ["#55682a", "#4a5c23", "#617630", "#43541e"],               "cloth", 0.15),
    ("green_d",   "paint", ["#43541d", "#3b4a1a"],                                     "cloth", 0.12),
    ("cream",     "paint", ["#efd2a6", "#f6dfba", "#e6c899"],                          "pleat", 0.0),
    ("cream_d",   "paint", ["#d8b688", "#cfab7c"],                                     "pleat", 0.0),
    ("belt",      "paint", ["#7a4020", "#6c381b", "#87492a"],                          "band",  0.12),
    ("belt_d",    "paint", ["#5c2e15", "#653318"],                                     "band",  0.1),
    ("leather",   "paint", ["#4a2a18", "#422515"],                               "s2",    0.0),
    ("sole",      "paint", ["#3d2414", "#34200f"],                                     "s3",    0.0),
    ("blade",     "metal", ["#c4c3c4", "#bbbabc", "#cbcacb"],                          "blade", 0.0),
    ("blade_l",   "metal", ["#e2e1df", "#dad9d7"],                                     "s1",    0.0),
    ("blade_d",   "metal", ["#9d9c9f", "#959497"],                                     "s1",    0.0),
    ("grip",      "paint", ["#5e4c3e", "#54443a"],                                     "s1",    0.0),
    ("gem",       "paint", ["#d8521c"],                                                "s1",    0.0),
    ("gem_l",     "paint", ["#f59a48"],                                                "s1",    0.0),
    ("gem_dark",  "paint", ["#2a1d18", "#33241d"],                                     "s1",    0.0),
    ("stone",     "paint", ["#f6efe0"],                                                "s1",    0.0),
]
BASES = [None]
BASE_ID = {}
for _n, _m, _sh, _shape, _j in _BASES:
    BASE_ID[_n] = len(BASES)
    BASES.append(dict(name=_n, mat=_m, shades=_sh, shape=_shape, jit=_j))
MAT_SLOTS = ["paint", "gold", "metal", "wool"]


def base_id(name):
    return BASE_ID[name]


# ---------------------------------------------------------------------------------------------------- the design grid

class Part:
    def __init__(self, key, seed=0):
        self.key = key
        self.seed = seed
        self.b = np.zeros((NX, NY, NZ), np.uint16)         # base id, 0 = air
        self.k = np.zeros((NX, NY, NZ), np.uint8)          # block shape id
        self.xf = None                                     # world voxels -> world voxels (a turned sub-grid)
        self.subs = []                                     # more grids that belong to the same part
        self.free = []                                     # free cubes (x0 y0 z0 x1 y1 z1 base, grid units, may overlap)

    @property
    def solid(self):
        return self.b > 0


def part(key, seed=0):
    return Part(key, seed)


def B(x0, x1, y0, y1, z0, z1, X=None):
    """Box mask between voxel boundaries (world voxels). X: an alternative x coordinate (mirrored LX)."""
    X = XW if X is None else X
    return (X > x0) & (X < x1) & (YW > y0) & (YW < y1) & (ZW > z0) & (ZW < z1)


def RB(x0, x1, y0, y1, z0, z1, r, X=None, axis="z"):
    """Box with rounded edges along `axis` (radius r voxels)."""
    X = XW if X is None else X
    m = B(x0, x1, y0, y1, z0, z1, X)
    if r <= 0:
        return m
    cx, cy, cz = (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2
    hx, hy, hz = (x1 - x0) / 2, (y1 - y0) / 2, (z1 - z0) / 2
    if axis == "z":
        a, ha, b, hb = X - cx, hx, YW - cy, hy
    elif axis == "x":
        a, ha, b, hb = YW - cy, hy, ZW - cz, hz
    else:
        a, ha, b, hb = X - cx, hx, ZW - cz, hz
    da = np.maximum(0, np.abs(a) - (ha - r))
    db = np.maximum(0, np.abs(b) - (hb - r))
    return m & (da * da + db * db <= r * r + 0.25)


def ell(cx, cy, cz, rx, ry, rz, X=None):
    X = XW if X is None else X
    return ((X - cx) / rx) ** 2 + ((YW - cy) / ry) ** 2 + ((ZW - cz) / rz) ** 2 <= 1.0


def paint(p, mask, base, shape=None):
    bi = base_id(base)
    p.b[mask] = bi
    p.k[mask] = SHAPE_ID[shape or BASES[bi]["shape"]]


def recolor(p, mask, base, shape=None):
    paint(p, mask & p.solid, base, shape)


def reshape(p, mask, shape):
    p.k[mask & p.solid] = SHAPE_ID[shape]


def is_base(p, *names):
    return np.isin(p.b, [base_id(n) for n in names])


def hash3(a, b, c, seed=0):
    h = (np.asarray(a).astype(np.int64) * 73856093) ^ (np.asarray(b).astype(np.int64) * 19349663) ^ \
        (np.asarray(c).astype(np.int64) * 83492791) ^ (seed * 2654435761)
    h = (h ^ (h >> 13)) * 1274126177
    h = h ^ (h >> 16)
    return (h & 0xFFFFFF).astype(np.float32) / float(0xFFFFFF)


def cellhash(cell=2, seed=0):
    cx, cy, cz = (cell, cell, cell) if np.isscalar(cell) else cell
    return hash3(_ix // cx, _iy // cy, _iz // cz, seed)


def dilate(mask, n=1):
    for _ in range(n):
        out = mask.copy()
        for axis in range(3):
            for sh in (1, -1):
                out |= np.roll(mask, sh, axis=axis)
        mask = out
    return mask


def surface(p):
    s = p.solid
    out = np.zeros_like(s)
    for axis in range(3):
        for sh in (1, -1):
            out |= s & ~np.roll(s, sh, axis=axis)
    return out


def relief(p, src, prob=0.3, cell=3, seed=0, dirs=("+x", "-x", "+y", "-y", "+z", "-z"), allow=None):
    """A share of the cells of the masked voxels swell one voxel outward into air (stray cubes, raised tiles)."""
    solid = p.solid
    pick = src & solid & (cellhash(cell, seed) < prob)
    took = np.zeros_like(solid)
    for d in dirs:
        axis = "xyz".index(d[1])
        sh = 1 if d[0] == "+" else -1
        b = np.roll(np.where(pick, p.b, 0), sh, axis=axis)
        k = np.roll(p.k, sh, axis=axis)
        take = (b > 0) & ~solid & ~took
        if allow is not None:
            take &= allow
        p.b[take] = b[take]
        p.k[take] = k[take]
        took |= take
    return took


# ---- posed geometry (for carving and for checking that nothing cuts through anything)

def centres(p):
    out = []
    for g in [p] + p.subs:
        q = np.argwhere(g.solid).astype(np.float32) + 0.5
        q[:, 0] -= X0
        q[:, 1] -= Y0
        out.append(g.xf(q) if g.xf else q)
    return np.concatenate(out)


def rotated(q, joint, axis, deg):
    """Rotate world voxel points about an axis through the joint (same sense as Blender's rotation_euler)."""
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    r = q - np.array(joint, np.float32)
    out = r.copy()
    if axis == "x":
        out[:, 1] = r[:, 1] * ca - r[:, 2] * sa
        out[:, 2] = r[:, 1] * sa + r[:, 2] * ca
    elif axis == "y":
        out[:, 0] = r[:, 0] * ca + r[:, 2] * sa
        out[:, 2] = -r[:, 0] * sa + r[:, 2] * ca
    else:
        out[:, 0] = r[:, 0] * ca - r[:, 1] * sa
        out[:, 1] = r[:, 0] * sa + r[:, 1] * ca
    return out + np.array(joint, np.float32)


BIG = (200, 300, 200)
BIG_OFF = np.array([100, 140, 30], np.float32)
_FAT = [(0, 0, 0)] + [(dx, dy, dz) for dx in (-0.45, 0.45) for dy in (-0.45, 0.45) for dz in (-0.45, 0.45)]


def occupancy(q, fat=True):
    g = np.zeros(BIG, bool)
    for off in (_FAT if fat else _FAT[:1]):
        r = np.floor(q + BIG_OFF + np.array(off, np.float32)).astype(np.int64)
        ok = np.all((r >= 0) & (r < np.array(BIG)), axis=1)
        r = r[ok]
        g[r[:, 0], r[:, 1], r[:, 2]] = True
    return g


def inside(q, grid):
    r = np.floor(q + BIG_OFF).astype(np.int64)
    ok = np.all((r >= 0) & (r < np.array(BIG)), axis=1)
    out = np.zeros(len(q), bool)
    out[ok] = grid[r[ok, 0], r[ok, 1], r[ok, 2]]
    return out


def swept(p, axis, lo, hi, step=1.5, grow=1):
    q = centres(p)
    g = np.zeros(BIG, bool)
    for ang in np.arange(lo, hi + 1e-6, step):
        g |= occupancy(rotated(q, JOINTS[p.key], axis, float(ang)))
    ox, oy, oz = int(BIG_OFF[0]) - X0, int(BIG_OFF[1]) - Y0, int(BIG_OFF[2])
    out = g[ox:ox + NX, oy:oy + NY, oz:oz + NZ]
    return dilate(out, grow) if grow else out


def connected(solid, seed):
    cur = seed & solid
    while True:
        nxt = dilate(cur) & solid
        if nxt.sum() == cur.sum():
            return cur
        cur = nxt


# ---------------------------------------------------------------------------------------------------- legs

def build_leg(s):
    """Boot, banded greave, knee cop, thigh and the half of the green skirt that swings with it. s = +1 left leg."""
    p = part("LegL" if s > 0 else "LegR", seed=3 if s > 0 else 4)
    LX = XW * s
    # sole: dark leather with gold squares on the toe
    paint(p, B(8, 26, -21, 10, 0, 4, LX), "sole")
    for gx in (11, 19):
        paint(p, B(gx, gx + 3, -22, -20, 0, 3, LX), "gold", "s1")
    paint(p, B(25, 27, -6, -2, 0, 3, LX), "gold", "s1")
    # armoured foot: a toe cap that steps down, a sloping instep
    paint(p, RB(8.5, 25.5, -20, 9, 4, 8, 2, LX), "steel")
    paint(p, RB(9, 25, -16, 9, 8, 10, 2, LX), "steel")
    paint(p, RB(9.5, 24.5, -12, 9, 10, 12, 2, LX), "steel")
    paint(p, B(9, 25, -20, -16, 7, 8, LX), "steel_l", "s2")
    # ankle band: wider, gold corner blocks and a stud
    paint(p, RB(8, 26, -14, 11, 12, 18, 2, LX), "steel_l")
    paint(p, B(8, 26, -14, 11, 12, 13, LX), "steel_d", "s2")
    paint(p, B(22, 26.5, -15, -10, 12, 18, LX), "gold")
    paint(p, B(7.5, 12, -15, -10, 12, 18, LX), "gold")
    paint(p, B(16, 18, -15.5, -13, 14, 16, LX), "gold_l", "s1")
    # shin and greave plate
    paint(p, RB(9.5, 24.5, -11, 9, 18, 29, 3, LX), "steel")
    paint(p, RB(11, 23, -12, -7, 19, 28, 1, LX), "steel_l")
    # knee cop: a wide band with gold squares
    paint(p, RB(8, 25.5, -14, 10, 28, 35, 3, LX), "steel_l")
    paint(p, B(8, 25.5, -14, 10, 28, 29, LX), "steel_d", "s2")
    paint(p, B(10, 14, -15, -12, 30, 34, LX), "gold")
    paint(p, B(11, 13, -16, -14, 31, 33, LX), "steel_dd")
    paint(p, B(20, 24, -15, -12, 30, 34, LX), "gold")
    paint(p, B(21, 23, -16, -14, 31, 33, LX), "gold_l", "s1")
    # thigh
    paint(p, RB(9, 21.5, -11.5, 9.5, 34, 56, 3, LX), "steel")
    paint(p, B(9, 21.5, -12, 9.5, 38, 39, LX) & surface(p), "steel_d", "s1")
    # the skirt half: green cloth from the hip down; on top a drum about the hip axis that hides inside the belt
    cloth = RB(8, 21, -16, 14, 42, HIP + 1, 3, LX)
    cloth &= ~((LX > 17.5) & (ZW > HIP - 1) & ((YW ** 2) / 196 + ((ZW - HIP + 1) ** 2) / 4 > 1))
    flare = RB(8, 21.5, -17, 15, 42, 54, 3, LX)
    drum = (LX > 8) & (LX < 17.5) & (YW ** 2 + (ZW - HIP) ** 2 <= 15.2 ** 2) & (ZW >= HIP)
    paint(p, cloth | flare | drum, "green")
    # gold hem of chunky blocks
    recolor(p, B(6, 23, -19, 17, 42, 46, LX), "gold", "s2")
    drop = (cellhash((2, 2, 999), 23 + s) < 0.45) & B(8, 21, -18, 16, 40, 42, LX) & ~B(10, 20, -10, 10, 0, 99, LX)
    paint(p, drop, "gold_d", "s2")
    # gold border beside the tabard, small studs, and two gold squares on the panel
    paint(p, B(8, 10, -18, -16, 46, 68, LX), "gold", "s2")
    for z in (50, 56, 62):
        paint(p, B(10, 11, -18, -17, z, z + 1, LX), "gold_l", "s1")
    for z in (49, 57):
        paint(p, B(13, 17, -18.5, -16, z, z + 4, LX), "gold")
        paint(p, B(14, 16, -19.5, -18, z + 1, z + 3, LX), "gold_l", "s1")
    return p


# ---------------------------------------------------------------------------------------------------- arms

def arm_upper(p, s):
    """Pauldron (drum about the shoulder axis + two lames) and the sleeve."""
    LX = XW * s
    jz = JOINTS["ArmL"][2]
    drum = (LX > ARM_IN) & (LX < ARM_OUT) & (YW ** 2 + (ZW - jz) ** 2 <= 10.2 ** 2)
    paint(p, drum, "steel")
    paint(p, RB(ARM_IN, ARM_OUT, -10.5, 10.5, 96, jz, 3, LX, axis="y"), "steel")
    paint(p, RB(ARM_IN - 0.5, ARM_OUT + 0.5, -11, 11, 88, 97, 3, LX, axis="y"), "steel_l")
    paint(p, B(ARM_IN - 0.5, ARM_OUT + 0.5, -11, 11, 88, 89, LX), "steel_d", "s2")
    paint(p, B(ARM_IN, ARM_OUT, -10.5, 10.5, 96, 97, LX), "steel_d", "s2")
    for gx in (ARM_IN, ARM_IN + 6, ARM_IN + 12):
        paint(p, B(gx, gx + 4, -12, -10, 88, 92, LX), "gold")
        paint(p, B(gx + 1, gx + 3, -13, -12, 89, 91, LX), "gold_l", "s1")
    paint(p, RB(ARM_IN + 2, ARM_OUT - 2, -7.5, 7.5, 74, 89, 2, LX), "belt")
    paint(p, B(ARM_IN + 2, ARM_OUT - 2, -7.5, 7.5, 82, 84, LX) & surface(p), "belt_d", "s2")


def arm_lower(p, s, lean=0.0):
    """Gold band, vambrace and cuff. lean: forward drift (voxels of -Y per voxel down)."""
    LX = XW * s
    cy = lambda z: -max(0.0, (78 - z) * lean)
    for z in range(56, 80):
        c = cy(z)
        if z >= 76:
            paint(p, RB(ARM_IN + 1, ARM_OUT - 1, c - 8.5, c + 8.5, z, z + 1, 2, LX), "gold" if z >= 77 else "gold_d", "s2")
        elif z >= 58:
            paint(p, RB(ARM_IN, ARM_OUT, c - 9.5, c + 9.5, z, z + 1, 3, LX), "steel_l" if z >= 60 else "steel_d")
        else:
            paint(p, RB(ARM_IN + 1.5, ARM_OUT - 1.5, c - 8, c + 8, z, z + 1, 2, LX), "leather")
    c = cy(67)
    paint(p, B(ARM_OUT, ARM_OUT + 1.5, c - 1, c + 1, 66, 68, LX), "gold", "s1")
    paint(p, B(28, 30, c - 11, c - 9.5, 64, 66, LX), "gold", "s1")
    return cy


def fist(p, s, cx, cy, z0, z1, wx=12, wy=13):
    """A closed fist: knuckles forward (-Y), finger rows, thumb on the inner side."""
    LX = XW * s
    x0, x1, y0, y1 = cx - wx / 2, cx + wx / 2, cy - wy / 2, cy + wy / 2
    paint(p, RB(x0, x1, y0, y1, z0, z1, 2, LX, axis="y"), "skin", "s2")
    for z in np.arange(z0 + 3, z1 - 2, 3):
        recolor(p, B(x0, x1, y0 - 1, y0 + 1, z, z + 1, LX), "skin_d", "s1")
    paint(p, B(x0 + 1, x1 - 1, y0 - 1, y0, z0 + 1, z1 - 3, LX) & (((LX + 0.5).astype(int) % 3) != 0), "skin_l", "s1")
    recolor(p, B(x0, x1, y0, y1, z0, z0 + 1, LX), "skin_dd", "s1")
    paint(p, RB(x0 - 1, x0 + 4, y0 - 1, y0 + 5, z1 - 5, z1, 1, LX), "skin_l", "s1")


ELBOW = (0.0, 80.0)                   # (y, z) of the right elbow axis
FOREARM_PITCH = -22.0                 # degrees about X: the right forearm comes forward to hold the sword
FIST_R_DESIGN = np.array([-(ARM_IN + ARM_OUT) / 2, -12.0, 52.5])


def xf_rot_x(yz, deg):
    def f(q):
        return rotated(q, (0.0, yz[0], yz[1]), "x", deg)
    return f


FIST_R = xf_rot_x(ELBOW, FOREARM_PITCH)(FIST_R_DESIGN[None].astype(np.float32))[0].astype(np.float64)
SWORD_DIR = np.array([-30.0, -12.0, -46.0]) / np.linalg.norm([-30.0, -12.0, -46.0])
SWORD_G = FIST_R + SWORD_DIR * 7.5                                 # centre of the cross-guard
SWORD_L = float((SWORD_G[2] - 2.5) / -SWORD_DIR[2])               # blade length (voxels)
_cam = np.array([-0.62, -0.79, 0.0])                               # the flat faces the picture's camera
SWORD_N = _cam - SWORD_DIR * np.dot(_cam, SWORD_DIR)
SWORD_N /= np.linalg.norm(SWORD_N)
SWORD_U = np.cross(SWORD_N, SWORD_DIR)
SWORD_U /= np.linalg.norm(SWORD_U)
SW_O = np.array([0.0, 0.0, 70.0])     # where the guard centre sits in the sword's own grid


def build_arm(s):
    p = part("ArmL" if s > 0 else "ArmR", seed=5 if s > 0 else 6)
    LX = XW * s
    arm_upper(p, s)
    if s > 0:
        cy = arm_lower(p, s, lean=0.12)
        fist(p, s, 29.75, -2.0 + cy(50), 44, 56.5)
        paint(p, RB(ARM_OUT - 4, ARM_OUT, -10 + cy(50), 5 + cy(50), 45, 57, 1, LX), "steel_l", "s2")
        paint(p, B(ARM_OUT - 4, ARM_OUT, -10 + cy(50), 5 + cy(50), 45, 46, LX), "steel_d", "s1")
    else:
        # the forearm is its own grid, pitched forward about the elbow
        fa = part("ArmR", seed=16)
        arm_lower(fa, s, lean=0.0)
        fist(fa, s, -FIST_R_DESIGN[0], FIST_R_DESIGN[1], FIST_R_DESIGN[2] - 6, FIST_R_DESIGN[2] + 5.5, wx=12, wy=12)
        paint(fa, B(ARM_IN + 1.5, ARM_OUT - 1.5, -10, 2, 56, 59, XW * s), "leather")      # the wrist bends forward
        fa.xf = xf_rot_x(ELBOW, FOREARM_PITCH)
        p.subs.append(fa)
        p.subs.append(build_sword())
    return p


def build_sword():
    """The long sword, built straight in its own grid (blade down -Z, flat facing -Y, guard centre at SW_O) and then
    turned into his right fist: pommel up by the belt, point down past his right foot."""
    p = part("ArmR", seed=17)
    L = SWORD_L
    X, Y, Z = XW - SW_O[0], YW - SW_O[1], ZW - SW_O[2]
    zb = -Z                                                    # distance down the blade from the guard
    tooth = ((np.floor(zb / 4.0) % 2) * 0.8)                   # the stepped edge of the picture
    half = np.where(zb < L - 16, 6.6 - zb * 0.012 - tooth, np.maximum(0.0, (L - zb) * 0.40))
    blade = (zb > 1.5) & (zb < L) & (np.abs(X) <= half) & (np.abs(Y) <= 1.5)
    paint(p, blade, "blade", "blade")
    edge = blade & (np.abs(X) > half - 1.6)
    recolor(p, edge & (X < 0), "blade_l", "s1")
    recolor(p, edge & (X > 0), "blade_d", "s1")
    fuller = blade & (np.abs(X) < 1.0) & (zb < L - 15) & (zb > 3)
    p.b[fuller & (np.abs(Y) > 0.5) & (Y < 0)] = 0
    recolor(p, fuller, "blade_d", "s1")
    # cross-guard: a bar with cube knobs at the ends and a centre block with a grey stone
    paint(p, (np.abs(Z) <= 2) & (np.abs(X) <= 11) & (np.abs(Y) <= 2), "gold", "s2")
    for e in (-1, 1):
        paint(p, (np.abs(Z) <= 3) & (np.abs(X - e * 12) <= 3) & (np.abs(Y) <= 3), "gold_l", "s3")
    paint(p, (np.abs(Z) <= 3.5) & (np.abs(X) <= 3.5) & (np.abs(Y) <= 3), "gold", "s3")
    paint(p, (np.abs(Z) <= 1.5) & (np.abs(X) <= 1.5) & (Y < -2.5) & (Y > -4.5), "steel_l", "s1")
    # grip with gold wire bands, an octagonal pommel
    grip = (Z > 2) & (Z < 17) & (X ** 2 + Y ** 2 <= 2.2 ** 2)
    paint(p, grip, "grip", "s1")
    for zz in (11, 14):
        recolor(p, grip & (np.abs(Z - zz) < 0.8), "gold", "s1")
    pm = (Z >= 16) & (Z < 24) & (np.abs(X) + np.abs(Y) <= 6) & (np.abs(X) <= 4) & (np.abs(Y) <= 4)
    paint(p, pm, "gold", "s2")
    recolor(p, pm & (Z < 18), "gold_d", "s2")
    recolor(p, pm & (Z > 22), "gold_l", "s2")
    paint(p, (np.abs(Z - 20) <= 1.5) & (np.abs(X) <= 1.5) & (Y < -3.5) & (Y > -5.5), "steel_l", "s1")

    def xf(q):
        r = q - SW_O.astype(np.float32)
        out = SWORD_G[None] + r[:, :1] * SWORD_U[None] + r[:, 1:2] * SWORD_N[None] + r[:, 2:3] * (-SWORD_DIR[None])
        return out.astype(np.float32)
    p.xf = xf
    return p


# ---------------------------------------------------------------------------------------------------- head

def build_head():
    p = part("Head", seed=7)
    # neck, long enough to read between the beard and the collar
    paint(p, (XW ** 2 + (YW + 1) ** 2 <= 7.4 ** 2) & (ZW > 97) & (ZW < 114), "skin_d", "s2")
    # skull / face block
    paint(p, RB(-12, 12, -12, 10, 110, 132, 2), "skin")
    # brow ridge and nose
    paint(p, B(-10, 10, -13, -12, 125, 127), "skin_l", "s2")
    paint(p, B(-2, 2, -13, -12, 115, 123), "skin", "s2")
    paint(p, B(-2, 2, -14, -13, 115, 121), "skin_l", "s2")
    paint(p, B(-1, 1, -15, -14, 116, 120), "skin_l", "s1")
    recolor(p, B(-2, -1, -14, -12, 115, 116) | B(1, 2, -14, -12, 115, 116), "skin_dd", "s1")
    # eyes: sclera both sides of a dark pupil (looking at the viewer), a glint, a shaded lid line
    for sx in (-1, 1):
        LX = XW * sx
        paint(p, B(3, 10, -12.5, -11, 118, 122, LX), "white")
        paint(p, B(4, 7, -12.7, -11, 118, 121, LX), "pupil")
        paint(p, B(5, 6, -12.7, -11, 120, 121, LX), "glint")
        recolor(p, B(3, 10, -13, -11, 117, 118, LX), "skin_d", "s1")
        # brows: thick, dark, proud, the inner end lower (a stern look)
        paint(p, B(2, 11, -13.5, -11, 122, 124.5, LX), "brow")
        paint(p, B(2, 4, -13.5, -11, 121.5, 122, LX) & False, "brow")
    # beard and moustache: a thick frame round the mouth in small cubes
    beard = (B(-12.5, 12.5, -15, -5, 106, 112) | B(-13, -10, -14, 5, 106, 121) | B(10, 13, -14, 5, 106, 121)
             | B(-8, 8, -16, -9, 104.5, 107))
    beard &= ~B(-4, 4, -18, -11, 110, 112)
    beard &= ~(B(-9, 9, -18, -11, 103, 106) & (np.abs(XW) > 6))
    mous = B(-8, 8, -15.5, -11, 112, 115) | B(-9, -5, -15.5, -11, 109, 113) | B(5, 9, -15.5, -11, 109, 113)
    paint(p, beard | mous, "beard")
    jum = (cellhash(2, 63) < 0.4) & surface(p) & is_base(p, "beard") & (ZW < 112)
    relief(p, jum, prob=1.0, cell=2, seed=64, dirs=("-y", "-z", "+x", "-x"))
    paint(p, B(-4, 4, -13, -11, 110, 112), "lip", "s2")
    paint(p, B(-3, 3, -13, -12, 110, 111), "skin_dd", "s1")
    # ears
    for sx in (-1, 1):
        LX = XW * sx
        paint(p, B(12, 14.5, -4, 2, 115, 122, LX), "skin_l", "s2")
        paint(p, B(14, 14.5, -3, 1, 117, 120, LX), "skin_d", "s1")
    # hair: a dark curly mass over the back and sides
    hair = (ell(0, 2, 122, 15.5, 13, 13.5) & (ZW > 107) & (YW > -4)) | B(-13, 13, -8, 11, 127, 135)
    hair &= ~B(-12, 12, -13, -6, 100, 135) | (ZW > 130)
    hair &= ~B(11.9, 15, -5, 3, 114, 123) & ~B(-15, -11.9, -5, 3, 114, 123)
    paint(p, hair & ~p.solid | (hair & is_base(p, "skin") & (YW > -6)), "hair")
    hsurf = is_base(p, "hair") & surface(p) & (YW > -8) & (ZW < 127)
    relief(p, hsurf, prob=0.45, cell=3, seed=66, dirs=("+y", "+x", "-x", "-z"))
    reshape(p, is_base(p, "hair") & surface(p), "s2")
    paint(p, B(-12, 12, -12, 10, 131, 135), "hair")
    # the crown: a gold band with tall points, dark stones between them and a red stone at the front
    rim = RB(-14, 14, -14, 12, 127, 140, 3) & ~RB(-12.2, 12.2, -12.2, 10.2, 100, 140, 2)
    rim &= ZW > 128
    ring = rim & (ZW < 132)
    paint(p, ring, "gold", "s2")
    recolor(p, ring & (ZW < 129), "gold_d", "s1")
    recolor(p, ring & (ZW > 131), "gold_l", "s1")
    ang = np.degrees(np.arctan2(XW, -(YW + 1.0)))
    for a in (0, 45, -45, 90, -90, 135, -135, 180):
        da = np.abs((ang - a + 180) % 360 - 180)
        big = a == 0
        w = 9.0 if big else 7.5
        paint(p, rim & (da < w) & (ZW >= 132) & (ZW < 134), "gold", "s2")
        paint(p, rim & (da < w * 0.55) & (ZW >= 134) & (ZW < (136 if big else 135.5)), "gold", "s2")
        dm = np.abs((ang - (a + 22.5) + 180) % 360 - 180)
        paint(p, rim & (dm < 5) & (ZW > 129) & (ZW < 131), "gem_dark", "s1")
    # front stone in a raised gold setting
    paint(p, B(-3, 3, -16.5, -14, 128, 134), "gold_l", "s2")
    paint(p, B(-2, 2, -17, -14, 129, 133), "gem", "s2")
    paint(p, B(-1, 1, -17.5, -17, 130, 132), "gem_l", "s1")
    return p


# ---------------------------------------------------------------------------------------------------- cape

CAPE_CELL = (4, 4, 5)


def cape_t(z):
    return np.clip((107.0 - z) / 102.0, 0.0, 1.0)


def cape_W(t):
    return CAPE_W0 + (CAPE_W1 - CAPE_W0) * t ** 2.2


def cape_yf(t):
    return 2.0 - 14.0 * t ** 1.2


def quantise(mask, cell, thresh=0.4):
    """Fill whole aligned cells that are at least `thresh` full (coarse masses, one block each)."""
    cx, cy, cz = cell
    a = mask.reshape(NX // cx, cx, NY // cy, cy, NZ // cz, cz).mean(axis=(1, 3, 5))
    full = a >= thresh
    return np.repeat(np.repeat(np.repeat(full, cx, 0), cy, 1), cz, 2)


def build_cape():
    """A C of cloth round the back and sides, flaring into a wide A-line towards the hem, made of big cloth blocks
    (one 4 x 4 x 5 cell thick) with fold columns standing a cell proud."""
    p = part("Cape", seed=9)
    cx, cy, cz = CAPE_CELL
    t = cape_t(ZW)
    W = cape_W(t)
    yb = 20.0 + 14.0 * t
    yf = cape_yf(t)
    thick = 4.0
    R = 12.0
    col_x = hash3(_ix // cx, 0, 0, 72)                         # fold ridges: whole columns a cell further out
    col_y = hash3(0, _iy // cy, 0, 73)
    ridge_b = ((col_x < 0.35) & (t > 0.18)) * 4.0
    ridge_w = ((col_y < 0.35) & (t > 0.18)) * 4.0
    ax = np.abs(XW)
    wi = W - thick
    dx = np.maximum(0.0, ax - (wi - R))
    dy = np.maximum(0.0, YW - (yb - R))
    inner_ok = np.where((dx > 0) & (dy > 0), np.sqrt(dx * dx + dy * dy) >= R, (ax >= wi) | (YW >= yb))
    dxo = np.maximum(0.0, ax - (W - R))
    dyo = np.maximum(0.0, YW - (yb + thick - R))
    outer_ok = np.where((dxo > 0) & (dyo > 0), np.sqrt(dxo * dxo + dyo * dyo) <= R,
                        (ax <= W + ridge_w) & (YW <= yb + thick + ridge_b))
    cloth = inner_ok & outer_ok & (YW >= yf) & (ZW > 5) & (ZW < 108)
    top = (ZW >= 98) & (ZW < 108) & (YW >= 4) & (YW <= 23) & (ax <= CAPE_W0) & ~((ax < ARM_OUT + 1.5) & (YW < 18))
    cloth = quantise(cloth | top, CAPE_CELL, 0.4)
    cloth &= ~((ax < ARM_OUT + 1.0) & (YW < 18) & (ZW > 80))  # keep the shoulders' corridor clear
    paint(p, cloth, "green", "cloth")
    solid = p.solid
    # the hem: the lowest cell of every column is gold, the next one cream (some gold), stray gold cells below
    zc = _iz // cz
    lz = 1
    paint(p, solid & (zc == lz), "gold", "s4")
    paint(p, solid & (zc == lz + 1) & (cellhash((cx, cy, 999), 75) < 0.6), "cream", "s4")
    paint(p, solid & (zc == lz + 1) & (cellhash((cx, cy, 999), 75) >= 0.6), "gold", "s4")
    stray = (zc == 0) & np.roll(solid, cz, axis=2) & (cellhash((cx, cy, 999), 76) < 0.3)
    paint(p, stray & (zc >= 0), "gold_d", "s4")
    # gold squares on the outer faces of the wings, near the front edge: a gold frame, a dark-green middle
    for sx in (-1, 1):
        for zc in (90, 70, 50, 31):
            tt = float(cape_t(zc))
            yc = float(cape_yf(tt)) + 7.0
            colm = solid & (np.abs(YW - yc) < 3.0) & (np.abs(ZW - zc) < 3.0) & (XW * sx > 0)
            if not colm.any():
                continue
            xo = np.abs(XW[colm]).max()                          # the outer face there
            plate = (np.abs(YW - yc) < 3.0) & (np.abs(ZW - zc) < 3.0) & (XW * sx > xo - 0.5) & (XW * sx < xo + 1.5)
            paint(p, plate, "gold", "s2")
            mid = (np.abs(YW - yc) < 1.0) & (np.abs(ZW - zc) < 1.0) & (XW * sx > xo + 0.5) & (XW * sx < xo + 1.5)
            paint(p, mid, "green_d", "s1")
    return p


# ---------------------------------------------------------------------------------------------------- body

def build_body(arms, head, cape):
    p = part("Body", seed=8)
    # pelvis core between the legs (hidden) and the pleated tabard
    paint(p, RB(-8, 8, -14, 12, 44, 74, 2), "leather")
    tab = B(-8, 8, -18, -14, 42, 72)
    paint(p, tab, "cream")
    pleat = (((XW + 8) // 2).astype(int) % 2) == 0
    recolor(p, tab & ~pleat, "cream_d")
    paint(p, B(-8, 8, -19, -18, 42, 70) & pleat, "cream")
    rag = cellhash((2, 2, 999), 83)
    p.b[tab & (ZW < 40 + np.floor(rag * 3) * 2)] = 0

    # torso: cinched belt, layered chest plates widening to the shoulders (a V-taper)
    bands = [  # z0, z1, half width, front y, base
        (72, 76, WAIST, -19.0, "belt_d"),
        (76, 80, WAIST, -18.5, "belt"),
        (80, 84, WAIST + 1.5, -18.5, "steel_d"),
        (84, 90, CHEST - 1.5, -19.5, "steel"),
        (90, 96, CHEST - 0.5, -20.5, "steel"),
        (96, 104, CHEST, -20.0, "steel_l"),
    ]
    edge = {"steel_l": "steel", "steel": "steel_d", "steel_d": "steel_dd", "belt": "belt_d", "belt_d": "leather"}
    for (z0, z1, hx, yf, c) in bands:
        paint(p, RB(-hx, hx, yf, 12, z0, z1, 6), c)
        paint(p, RB(-hx - 0.5, hx + 0.5, yf - 1, 12.5, z0, z0 + 1, 6), edge[c], "s1" if c.startswith("steel") else "band")
    paint(p, RB(-CHEST - 1, CHEST + 1, -17, 12, 104, 106, 7), "steel_l")
    paint(p, RB(-15, 15, -12, 10, 106, 107, 6), "steel")
    # belt buckle: big gold square with a frame, darker inside and a raised centre
    paint(p, B(-6, 6, -22, -18, 70, 82), "gold", "s2")
    paint(p, B(-4, 4, -23, -21, 72, 80), "gold_d", "s2")
    paint(p, B(-2, 2, -24, -22, 74, 78), "gold_l", "s2")
    paint(p, B(-1, 1, -25, -24, 75, 77), "stone", "s1")
    for (gx, gz) in ((-6, 70), (4, 70), (-6, 80), (4, 80)):
        paint(p, B(gx, gx + 2, -23, -21, gz, gz + 2), "gold_l", "s2")
    for gx in (-13, -9, 9, 13):
        paint(p, B(gx - 1, gx + 1, -20.5, -19, 72, 74), "gold", "s1")

    # lapels: the green front edges of the robe with gold squares, down the chest sides
    for sx in (-1, 1):
        LX = XW * sx
        lap = np.zeros(p.b.shape, bool)
        for z in range(80, 108, 2):
            x_in = 12.0 + (108 - z) * 0.08
            lap |= B(x_in, x_in + 6, -30, 0, z, z + 2, LX)
        shell = lap & ~p.solid & np.roll(p.solid, -1, axis=1) & (YW < -10)
        paint(p, shell, "green", "s2")
        for zc in (86, 98):
            x_in = 12.0 + (108 - zc) * 0.08 + 1
            sq = B(x_in, x_in + 4, -26, -14, zc - 2, zc + 2, LX) & dilate(is_base(p, "green"), 1) & ~p.solid
            sq |= B(x_in, x_in + 4, -26, -14, zc - 2, zc + 2, LX) & is_base(p, "green")
            paint(p, sq, "gold", "s2")
            recolor(p, sq & B(x_in + 1, x_in + 3, -30, 0, zc - 1, zc + 1, LX), "green_d", "s1")

    # the sun medallion: gold cubes in a disc with rays, a raised ring and a pale stone, a chain to the shoulders
    mz = 94.0
    r = np.sqrt(XW ** 2 + (ZW - mz) ** 2)
    a = np.degrees(np.arctan2(ZW - mz, XW))
    rays = (np.abs(((a + 22.5) % 45) - 22.5) < 9.0) & (r < 10.5)
    disc = (r < 7.0) | rays
    paint(p, disc & (YW > -23) & (YW < -17), "gold", "s2")
    recolor(p, disc & (r > 8.0), "gold_d", "s2")
    paint(p, (r < 6.0) & (r > 3.5) & (YW > -25) & (YW < -23), "gold_l", "s2")
    paint(p, (r <= 4.0) & (YW > -24) & (YW < -23), "gold_d", "s2")
    paint(p, (np.abs(XW) < 2) & (np.abs(ZW - mz) < 2) & (YW > -26) & (YW < -23), "gold_l", "s2")
    paint(p, (np.abs(XW) < 1) & (np.abs(ZW - mz) < 1) & (YW > -27) & (YW < -26), "stone", "s1")
    for sx in (-1, 1):
        for k in range(5):
            x = sx * (11 + k * 2.4)
            z = 97 + k * 1.6
            paint(p, B(x - 1.2, x + 1.2, -21, -17, z - 1, z + 1.2), "gold" if k % 2 == 0 else "gold_d", "s1")
    # pendant: a gold star below the medallion with a pale stone
    pz = 84.0
    pr = np.abs(XW) + np.abs(ZW - pz) * 0.75
    pend = (pr < 5.0) | ((np.abs(ZW - pz - 2) < 1.0) & (np.abs(XW) < 7.0)) | ((ZW < pz) & (ZW > pz - 8) & (np.abs(XW) < 1.0))
    paint(p, pend & (YW > -23) & (YW < -19), "gold", "s2")
    paint(p, (np.abs(XW) < 1) & (np.abs(ZW - pz) < 1) & (YW > -24) & (YW < -23), "stone", "s1")
    paint(p, (np.abs(XW) < 1) & (ZW > pz + 4) & (ZW < 89) & (YW > -21) & (YW < -19), "gold_d", "s1")

    # shoulders under the fur
    paint(p, RB(-CHEST - 1, CHEST + 1, -12, 12, 98, 106, 6), "steel")

    # the fur collar: jumbled 4-voxel cubes, wide and high round the shoulders, carved clear of moving parts
    keep_out = np.zeros(p.b.shape, bool)
    for a_ in arms:
        keep_out |= swept(a_, "x", -47, 47, grow=1)
    keep_out |= swept(head, "z", -28, 28, step=2.0, grow=1)
    keep_out |= cape.solid
    hard = p.solid
    blobs = [(29.0, 1.0, 107.0, 14.5, 15.0, 8.0), (-29.0, 1.0, 107.0, 14.5, 15.0, 8.0),      # shoulder mounds
             (33.0, -3.0, 111.0, 8.0, 9.0, 6.0), (-33.0, -3.0, 111.0, 8.0, 9.0, 6.0),         # puffs on top, outboard
             (36.0, 7.0, 112.0, 7.0, 7.0, 5.5), (-36.0, 7.0, 112.0, 7.0, 7.0, 5.5),
             (0.0, 13.0, 109.0, 25.0, 9.0, 8.0),                                              # round the back of the neck
             (16.5, -12.0, 104.0, 8.0, 6.5, 5.0), (-16.5, -12.0, 104.0, 8.0, 6.5, 5.0),       # front lobes
             (39.5, 0.0, 101.0, 5.5, 13.5, 11.5), (-39.5, 0.0, 101.0, 5.5, 13.5, 11.5),       # flaps over the cape tops
             (35.0, -8.0, 106.0, 7.5, 7.5, 7.5), (-35.0, -8.0, 106.0, 7.5, 7.5, 7.5)]
    cs = 4
    Xc, Yc, Zc = (np.floor(XW / cs) + 0.5) * cs, (np.floor(YW / cs) + 0.5) * cs, (np.floor(ZW / cs) + 0.5) * cs
    d = np.full(p.b.shape, 9.0, np.float32)
    for (cx, cy, cz, rx, ry, rz) in blobs:
        d = np.minimum(d, ((Xc - cx) / rx) ** 2 + ((Yc - cy) / ry) ** 2 + ((Zc - cz) / rz) ** 2)
    d = d + (cellhash(cs, 92) - 0.5) * 0.7
    fur = d <= 1.0
    out = fur.copy()
    for k, (axis, sh) in enumerate(((0, 1), (0, -1), (1, 1), (1, -1), (2, 1), (2, -1))):
        out |= np.roll(fur & (cellhash(cs, 93 + k) < 0.3), sh * 2, axis=axis)
    fur = out & ~keep_out & ~hard & (ZW < 119) & (ZW > 86)
    paint(p, fur, "fur")
    fur = connected(p.solid, hard) & fur
    p.b[is_base(p, "fur") & ~fur] = 0
    # the visible fur: free cubes of 3.5-5.5 voxels, jittered, overlapping, on the surface of the fur volume;
    # under them a shrunken core so no hole shows through
    shell = fur & ~(np.roll(fur, 1, 0) & np.roll(fur, -1, 0) & np.roll(fur, 1, 1) & np.roll(fur, -1, 1)
                    & np.roll(fur, 1, 2) & np.roll(fur, -1, 2))
    core = fur.copy()
    for _ in range(2):
        core &= np.roll(core, 1, 0) & np.roll(core, -1, 0) & np.roll(core, 1, 1) & np.roll(core, -1, 1) & np.roll(core, 1, 2) & np.roll(core, -1, 2)
    p.b[fur & ~core] = 0
    recolor(p, core, "fur_d")
    idx = np.argwhere(shell)
    cell = 4
    key = (idx[:, 0] // cell * 4096 + idx[:, 1] // cell) * 4096 + idx[:, 2] // cell
    h = hash3(idx[:, 0], idx[:, 1], idx[:, 2], 201)
    o = np.lexsort((h, key))
    _, first = np.unique(key[o], return_index=True)
    pick = idx[o][first]
    fb, fd = base_id("fur"), base_id("fur_d")
    for (i, j, k) in pick.tolist():
        r = hash3(np.array([i]), np.array([j]), np.array([k]), 202)[0]
        r2 = hash3(np.array([i]), np.array([j]), np.array([k]), 203)[0]
        r3 = hash3(np.array([i]), np.array([j]), np.array([k]), 204)[0]
        sz = 3.6 + 2.0 * r
        cx_ = i + 0.5 + (r2 - 0.5) * 2.0
        cy_ = j + 0.5 + (r3 - 0.5) * 2.0
        cz_ = k + 0.5 + (r - 0.5) * 1.5
        hz = sz * (0.8 + 0.35 * r3)
        base_ = fd if (k < 96 - 0 and r2 < 0.7) or r2 < 0.12 else fb
        p.free.append((cx_ - sz / 2, cy_ - sz / 2, cz_ - hz / 2, cx_ + sz / 2, cy_ + sz / 2, cz_ + hz / 2, base_))
    return p


# ---------------------------------------------------------------------------------------------------- blocks -> mesh

def integral(a):
    """Summed volume table with a zero border: S[i, j, k] = sum of a[:i, :j, :k]."""
    S = np.zeros((a.shape[0] + 1, a.shape[1] + 1, a.shape[2] + 1), np.int32)
    S[1:, 1:, 1:] = a.astype(np.int32).cumsum(0).cumsum(1).cumsum(2)
    return S


def box_sum(S, x0, y0, z0, x1, y1, z1):
    """Vectorised sum over [x0, x1) x [y0, y1) x [z0, z1) (clipped to the grid)."""
    n = np.array(S.shape) - 1
    x0, x1 = np.clip(x0, 0, n[0]), np.clip(x1, 0, n[0])
    y0, y1 = np.clip(y0, 0, n[1]), np.clip(y1, 0, n[1])
    z0, z1 = np.clip(z0, 0, n[2]), np.clip(z1, 0, n[2])
    x1, y1, z1 = np.maximum(x1, x0), np.maximum(y1, y0), np.maximum(z1, z0)
    return (S[x1, y1, z1] - S[x0, y1, z1] - S[x1, y0, z1] - S[x1, y1, z0]
            + S[x0, y0, z1] + S[x0, y1, z0] + S[x1, y0, z0] - S[x0, y0, z0])


def decompose(p):
    """Cut the part into blocks -> (blocks (N, 7): x0 y0 z0 sx sy sz base, occupancy grid of the blocks).
    Per block shape, the biggest aligned (brick-staggered where asked) cells come first. A cell becomes ONE block when
    it is filled enough (SHAPE_FILL: coarse masses), holds nothing of another shape and one base dominates it; the
    rest falls back to halved cells and finally single voxels."""
    solid = p.solid
    claimed = np.zeros_like(solid)
    out = []
    order = sorted(range(1, len(SHAPE_NAMES) + 1), key=lambda i: -np.prod(SHAPES[SHAPE_NAMES[i - 1]][:3]))
    for si in order:
        name = SHAPE_NAMES[si - 1]
        kx, ky, kz, stag = SHAPES[name]
        cls = solid & (p.k == si)
        if not cls.any():
            continue
        tries = []
        a, b, c = kx, ky, kz
        h = lambda q: max(1, (q + 1) // 2) if q > 1 else 1
        first = True
        while True:
            tries.append((a, b, c, stag and first, SHAPE_FILL.get(name, 0.75) if first else 0.8))
            # thin plates of the same footprint: what a raised layer or a thin sheet leaves over
            for sl in ((a, b, 1), (a, 1, c), (1, b, c), (a, 1, 1), (1, b, 1), (1, 1, c)):
                if sl != (a, b, c) and sl != (1, 1, 1) and np.prod(sl) >= 2:
                    tries.append(sl + (stag and first, 1.0))
            if (a, b, c) == (1, 1, 1):
                break
            a, b, c = h(a), h(b), h(c)
            first = False
        seen = set()
        tries = [t for t in tries if not (t[:3] in seen or seen.add(t[:3]))] + [(1, 1, 1, False, 1.0)]
        for (a, b, c, st, fill) in tries:
            rem = cls & ~claimed
            if not rem.any():
                break
            forbid = integral((solid & ~cls) | claimed)
            idx = np.argwhere(rem)
            ox = ((idx[:, 2] // c) % 2) * (a // 2) if st else np.zeros(len(idx), np.int64)
            oy = ((idx[:, 2] // c) % 2) * (b // 2) if st else np.zeros(len(idx), np.int64)
            cx, cy, cz = (idx[:, 0] + ox) // a, (idx[:, 1] + oy) // b, idx[:, 2] // c
            key = (cx * 4096 + cy) * 4096 + cz
            bv = p.b[idx[:, 0], idx[:, 1], idx[:, 2]].astype(np.int64)
            o = np.lexsort((bv, key))
            ks, bs = key[o], bv[o]
            uk, start, cnt = np.unique(ks, return_index=True, return_counts=True)
            # majority base per cell
            kb = ks * 65536 + bs
            ukb, kb_start, kb_cnt = np.unique(kb, return_index=True, return_counts=True)
            kb_key = ukb // 65536
            cell_of_kb = np.searchsorted(uk, kb_key)
            best = np.zeros(len(uk), np.int64)
            np.maximum.at(best, cell_of_kb, kb_cnt)
            is_best = kb_cnt == best[cell_of_kb]
            maj = np.zeros(len(uk), np.int64)
            maj[cell_of_kb[is_best]] = ukb[is_best] % 65536
            first = idx[o][start]
            fox = ((first[:, 2] // c) % 2) * (a // 2) if st else 0
            foy = ((first[:, 2] // c) % 2) * (b // 2) if st else 0
            bx0 = ((first[:, 0] + fox) // a) * a - fox
            by0 = ((first[:, 1] + foy) // b) * b - foy
            bz0 = (first[:, 2] // c) * c
            nf = box_sum(forbid, bx0, by0, bz0, bx0 + a, by0 + b, bz0 + c)
            inside_grid = (bx0 >= 0) & (by0 >= 0) & (bz0 >= 0) & (bx0 + a <= NX) & (by0 + b <= NY) & (bz0 + c <= NZ)
            ok = (cnt >= fill * a * b * c - 1e-6) & (best >= 0.65 * cnt) & (nf == 0) & inside_grid
            if (a, b, c) == (1, 1, 1):
                ok = np.ones(len(uk), bool)
            if not ok.any():
                continue
            sel = np.nonzero(ok)[0]
            X0_, Y0_, Z0_ = bx0[sel], by0[sel], bz0[sel]
            for dx in range(a):
                for dy in range(b):
                    for dz in range(c):
                        claimed[X0_ + dx, Y0_ + dy, Z0_ + dz] = True
            n = len(sel)
            out.append(np.stack([X0_, Y0_, Z0_, np.full(n, a), np.full(n, b), np.full(n, c), maj[sel]], axis=1))
    return np.concatenate(out).astype(np.int64), claimed


def _template():
    """Chamfered box topology: 24 vertices (8 corners x the 3 faces they sit on), 6 main faces, 12 edge chamfers,
    8 corner triangles, each with the (axis, side) faces that decide whether it is drawn."""
    vid = lambda sx, sy, sz, a: ((sx * 2 + sy) * 2 + sz) * 3 + a
    faces = []
    for a in range(3):
        for s in (0, 1):
            b, c = [i for i in range(3) if i != a]
            cyc = [(0, 0), (1, 0), (1, 1), (0, 1)]
            vs = []
            for (u, w) in cyc:
                cs = [0, 0, 0]
                cs[a], cs[b], cs[c] = s, u, w
                vs.append(vid(*cs, a))
            faces.append((vs, [(a, s)], "main", a))
    for a in range(3):
        for b in range(a + 1, 3):
            c = 3 - a - b
            for sa in (0, 1):
                for sb in (0, 1):
                    c0 = [0, 0, 0]
                    c0[a], c0[b], c0[c] = sa, sb, 0
                    c1 = list(c0)
                    c1[c] = 1
                    vs = [vid(*c0, a), vid(*c1, a), vid(*c1, b), vid(*c0, b)]
                    faces.append((vs, [(a, sa), (b, sb)], "edge", a))
    for sx in (0, 1):
        for sy in (0, 1):
            for sz in (0, 1):
                faces.append(([vid(sx, sy, sz, 0), vid(sx, sy, sz, 1), vid(sx, sy, sz, 2)], [(0, sx), (1, sy), (2, sz)], "corner", 0))
    # winding: outward normals for a unit cube with a bevel of 0.2
    P = _verts(np.array([[0, 0, 0, 1, 1, 1]], np.float64), np.array([0.2]))[0]
    fixed = []
    for (vs, conds, kind, ax) in faces:
        pts = P[vs]
        nrm = np.zeros(3)
        for i in range(len(pts)):
            q, r = pts[i], pts[(i + 1) % len(pts)]
            nrm += np.cross(q, r)
        if np.dot(nrm, pts.mean(axis=0) - 0.5) < 0:
            vs = vs[::-1]
        fixed.append((vs, conds, kind, ax))
    return fixed


def _verts(boxes, w):
    """boxes (N, 6): x0 y0 z0 x1 y1 z1 ; w (N,) bevel -> (N, 24, 3)."""
    N = len(boxes)
    out = np.zeros((N, 24, 3))
    lo, hi = boxes[:, :3], boxes[:, 3:]
    for sx in (0, 1):
        for sy in (0, 1):
            for sz in (0, 1):
                s = (sx, sy, sz)
                corner = np.stack([hi[:, i] if s[i] else lo[:, i] for i in range(3)], axis=1)
                for a in range(3):
                    v = corner.copy()
                    for i in range(3):
                        if i != a:
                            v[:, i] += (-w if s[i] else w)
                    out[:, ((sx * 2 + sy) * 2 + sz) * 3 + a] = v
    return out


TEMPLATE = None


def block_mesh(p, name, xform):
    """Blocks of part p (and its sub-grids) -> one Blender mesh object (world metres, then xform(points) -> local)."""
    geo = [grid_geometry(g, name) for g in [p] + p.subs]
    off = 0
    verts, faces, cols, fmat = [], [], [], []
    for (v_, f_, c_, m_) in geo:
        verts.append(v_)
        faces.extend([tuple(i + off for i in fc) for fc in f_])
        cols.append(c_)
        fmat.append(m_)
        off += len(v_)
    world = np.concatenate(verts)
    vcol = np.concatenate(cols)
    fmat = np.concatenate(fmat)
    local = xform(world)
    return make_object(name, local, faces, vcol, fmat, sum(1 for _ in faces))


def grid_geometry(p, name):
    """-> (vertices in world metres, faces, vertex colours, face material slots) of one grid's blocks."""
    global TEMPLATE
    if TEMPLATE is None:
        TEMPLATE = _template()
    blk, solid = decompose(p)
    vols = blk[:, 3] * blk[:, 4] * blk[:, 5]
    print("BLOCKS %s: %s" % (name, dict(zip(*[x.tolist() for x in np.unique(vols, return_counts=True)]))))
    S_air = integral(~solid)
    solid_ao = solid.copy()
    for (a0, b0, c0, a1, b1, c1, _) in p.free:
        solid_ao[int(round(a0)):int(round(a1)), int(round(b0)):int(round(b1)), int(round(c0)):int(round(c1))] = True
    S_sol = integral(solid_ao)
    x0, y0, z0, sx, sy, sz, base = [blk[:, i] for i in range(7)]
    x1, y1, z1 = x0 + sx, y0 + sy, z0 + sz
    # which faces see air
    exp = np.zeros((len(blk), 3, 2), bool)
    exp[:, 0, 0] = box_sum(S_air, x0 - 1, y0, z0, x0, y1, z1) > 0
    exp[:, 0, 1] = box_sum(S_air, x1, y0, z0, x1 + 1, y1, z1) > 0
    exp[:, 1, 0] = box_sum(S_air, x0, y0 - 1, z0, x1, y0, z1) > 0
    exp[:, 1, 1] = box_sum(S_air, x0, y1, z0, x1, y1 + 1, z1) > 0
    exp[:, 2, 0] = box_sum(S_air, x0, y0, z0 - 1, x1, y1, z0) > 0
    exp[:, 2, 1] = box_sum(S_air, x0, y0, z1, x1, y1, z1 + 1) > 0
    # faces on the grid border count as open
    exp[:, 0, 0] |= x0 == 0
    exp[:, 0, 1] |= x1 == NX
    exp[:, 1, 0] |= y0 == 0
    exp[:, 1, 1] |= y1 == NY
    exp[:, 2, 0] |= z0 == 0
    exp[:, 2, 1] |= z1 == NZ
    vis = exp.any(axis=(1, 2))
    blk, exp = blk[vis], exp[vis]
    x0, y0, z0, sx, sy, sz, base = [blk[:, i] for i in range(7)]
    N = len(blk)
    # no flat surfaces: every block sits a random fraction of its bevel proud of its neighbours, and a share of the
    # cloth / fur / armour blocks stands a whole voxel proud (their side faces then open)
    w = 0.08 * np.minimum(np.minimum(sx, sy), sz).astype(np.float64)
    w = np.maximum(w, 0.07)
    jit = np.array([BASES[b]["jit"] for b in base])
    pri = [(1, 0), (1, 1), (0, 0), (0, 1), (2, 1), (2, 0)]
    off = np.zeros((N, 3))
    grow = np.zeros((N, 6))
    chosen = np.full(N, -1)
    h = hash3(x0, y0 * 3 + 1, z0 * 7 + 2, p.seed + 101)
    raise_ = hash3(x0, y0, z0, p.seed + 103) < jit * 0.6
    S_s = integral(solid)
    for k, (a, s) in enumerate(pri):
        m = (chosen < 0) & exp[:, a, s]
        chosen[m] = k
        off[m, a] = h[m] * 0.8 * w[m] * (1 if s else -1)
    for k, (a, s) in enumerate(pri):
        m = raise_ & (chosen == k)
        lo_ = [x0.copy(), y0.copy(), z0.copy()]
        hi_ = [x0 + sx, y0 + sy, z0 + sz]
        if s:
            lo_[a], hi_[a] = hi_[a], hi_[a] + 1
        else:
            lo_[a], hi_[a] = lo_[a] - 1, lo_[a]
        free = box_sum(S_s, lo_[0], lo_[1], lo_[2], hi_[0], hi_[1], hi_[2]) == 0
        m &= free
        grow[m, a * 2 + s] = 1.0
        for a2 in range(3):
            if a2 != a:
                exp[m, a2, 0] = True
                exp[m, a2, 1] = True
        off[m, a] = 0.0
    boxes = np.stack([x0, y0, z0, x0 + sx, y0 + sy, z0 + sz], axis=1).astype(np.float64)
    boxes[:, :3] += off - grow[:, 0::2]
    boxes[:, 3:] += off + grow[:, 1::2]
    if p.free:
        F = np.array(p.free, np.float64)
        fs = F[:, 3:6] - F[:, :3]
        boxes = np.concatenate([boxes, F[:, :6]])
        w = np.concatenate([w, np.maximum(0.08 * fs.min(axis=1), 0.07)])
        exp = np.concatenate([exp, np.ones((len(F), 3, 2), bool)])
        base = np.concatenate([base, F[:, 6].astype(np.int64)])
        x0 = np.concatenate([x0, np.floor(F[:, 0]).astype(np.int64)])
        y0 = np.concatenate([y0, np.floor(F[:, 1]).astype(np.int64)])
        z0 = np.concatenate([z0, np.floor(F[:, 2]).astype(np.int64)])
        N = len(boxes)
    P = _verts(boxes, w)                                        # grid units
    # occlusion per vertex: how much of this part is in front of it (two scales)
    Pf = P.reshape(-1, 3)
    vaxis = np.tile(np.arange(24) % 3, N)
    corner = np.tile(np.arange(24) // 3, N)
    sgn = np.zeros(len(Pf))
    for c8 in range(8):
        s = ((c8 >> 2) & 1, (c8 >> 1) & 1, c8 & 1)
        for a in range(3):
            sel = (corner == c8) & (vaxis == a)
            sgn[sel] = 1 if s[a] else -1
    nrm = np.zeros_like(Pf)
    nrm[np.arange(len(Pf)), vaxis] = sgn
    ao = np.ones(len(Pf))
    for (dist, hs, k) in ((1.2, 1.2, 0.55), (3.0, 3.0, 0.55)):
        c = Pf + nrm * dist
        lo_ = np.floor(c - hs + 0.5).astype(np.int64)
        hi_ = np.floor(c + hs + 0.5).astype(np.int64)
        vol = np.maximum(1, np.prod(hi_ - lo_, axis=1))
        f = box_sum(S_sol, lo_[:, 0], lo_[:, 1], lo_[:, 2], hi_[:, 0], hi_[:, 1], hi_[:, 2]) / vol
        ao *= 1.0 - k * np.clip(f, 0, 1) ** 0.9
    ao = np.clip(ao, 0.32, 1.0)
    # colour: one shade of the base per block, a touch of brightness noise
    cols = np.zeros((N, 3))
    hb = hash3(x0 * 5 + 3, y0, z0 // np.where(np.isin(base, [base_id("green"), base_id("cream")]), 10, 1), p.seed + 107)
    hb2 = hash3(x0, y0 * 5 + 1, z0, p.seed + 109)
    for bi in np.unique(base):
        m = base == bi
        sh = [V.srgb_to_linear(V.rgb(c).astype(np.float32) / 255.0) for c in BASES[bi]["shades"]]
        pick = np.minimum((hb[m] * len(sh)).astype(int), len(sh) - 1)
        cols[m] = np.array(sh)[pick]
    cols *= (0.95 + 0.1 * hb2)[:, None]
    vcol = np.repeat(cols, 24, axis=0) * ao[:, None]
    # faces
    polys, pmat = [], []
    matidx = np.array([MAT_SLOTS.index(BASES[b]["mat"]) for b in base])
    basev = np.arange(N) * 24
    for (vs, conds, kind, ax) in TEMPLATE:
        if kind == "main":
            m = exp[:, conds[0][0], conds[0][1]]
        elif kind == "corner":
            m = (exp[:, conds[0][0], conds[0][1]].astype(int) + exp[:, conds[1][0], conds[1][1]] + exp[:, conds[2][0], conds[2][1]]) >= 2
        else:
            m = np.zeros(N, bool)
            for (a, s) in conds:
                m |= exp[:, a, s]
        ids = np.nonzero(m)[0]
        if len(ids) == 0:
            continue
        polys.append((basev[ids][:, None] + np.array(vs)[None, :], ids))
    # compact the vertex list
    used = np.zeros(len(Pf), bool)
    for (pv, ids) in polys:
        used[pv.reshape(-1)] = True
    remap = np.full(len(Pf), -1, np.int64)
    remap[used] = np.arange(used.sum())
    world = Pf[used].copy()
    world[:, 0] -= X0
    world[:, 1] -= Y0
    if p.xf is not None:
        world = p.xf(world.astype(np.float32)).astype(np.float64)
    world *= VOX
    faces, fmat = [], []
    for (pv, ids) in polys:
        r = remap[pv]
        faces.extend(map(tuple, r.tolist()))
        fmat.append(matidx[ids])
    return world, faces, vcol[used], np.concatenate(fmat)


def make_object(name, local, faces, vcol, fmat, nblocks):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(local.tolist(), [], faces)
    used_slots = sorted(set(fmat.tolist()))
    lut = {s: i for i, s in enumerate(used_slots)}
    for s in used_slots:
        mesh.materials.append(V.material(MAT_SLOTS[s]))
    mesh.polygons.foreach_set("material_index", np.array([lut[s] for s in fmat.tolist()], np.int32))
    mesh.polygons.foreach_set("use_smooth", np.ones(len(faces), bool))
    nl = len(mesh.loops)
    lv = np.zeros(nl, np.int64)
    mesh.loops.foreach_get("vertex_index", lv)
    attr = mesh.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="CORNER")
    rgba = np.ones((nl, 4), np.float32)
    rgba[:, :3] = vcol[lv]
    attr.data.foreach_set("color", rgba.reshape(-1))
    mesh.color_attributes.active_color = attr
    mesh.color_attributes.render_color_index = 0
    # box-projected UVs (4 m per texture repeat, like the voxel meshes)
    pn = np.zeros(len(faces) * 3, np.float32)
    mesh.polygons.foreach_get("normal", pn)
    dom = np.abs(pn.reshape(-1, 3)).argmax(axis=1)
    lt = np.zeros(len(faces), np.int32)
    mesh.polygons.foreach_get("loop_total", lt)
    ldom = np.repeat(dom, lt)
    co = local[lv]
    ua = np.where(ldom == 0, co[:, 1], co[:, 0])
    va = np.where(ldom == 2, co[:, 1], co[:, 2])
    uvl = mesh.uv_layers.new(name="UVMap")
    uvl.data.foreach_set("uv", (np.stack([ua, va], axis=1) / 4.0).astype(np.float32).reshape(-1))
    mesh.update()
    mesh.validate()
    ob = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(ob)
    wn = ob.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL")
    wn.mode = "FACE_AREA"
    wn.weight = 100
    wn.keep_sharp = False
    ob["voxel_faces"] = int(sum(len(f) - 2 for f in faces))
    ob["blocks"] = int(nblocks)
    ob["lights"] = "[]"
    return ob


# ---------------------------------------------------------------------------------------------------- contrapposto

def rot_matrix(axis, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    if axis == "y":
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    if axis == "z":
        return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def m(v):
    return np.array(v, np.float64) * VOX


PELVIS = m(JOINTS["Body"])
R_TORSO = rot_matrix("y", TORSO_TILT)


def torso_apply(pts):
    return (pts - PELVIS) @ R_TORSO.T + PELVIS


def joint_world(key):
    """Joint position (metres, Blender axes) after the contrapposto."""
    j = m(JOINTS[key])
    if key in ("LegL", "LegR", "Body"):
        return j
    return torso_apply(j[None])[0]


def part_xform(key):
    """world metres (design) -> local mesh coordinates (origin at the posed joint)."""
    jw = joint_world(key)
    if key in ("LegL", "LegR"):
        return lambda pts: pts - jw
    if key == "Head":
        R = rot_matrix("z", HEAD_TURN) @ rot_matrix("y", HEAD_TILT)
        return lambda pts: (torso_apply(pts) - jw) @ R.T
    return lambda pts: torso_apply(pts) - jw


def pivot(key):
    return [round(float(c), 5) for c in joint_world(key)]


# ---------------------------------------------------------------------------------------------------- build / checks

def build_king():
    parts = {}
    parts["LegL"], parts["LegR"] = build_leg(1), build_leg(-1)
    parts["ArmL"], parts["ArmR"] = build_arm(1), build_arm(-1)
    parts["Head"] = build_head()
    parts["Cape"] = build_cape()
    parts["Body"] = build_body([parts["ArmL"], parts["ArmR"]], parts["Head"], parts["Cape"])
    return parts


ANG_AXES = dict(LegL="x", LegR="x", ArmL="x", ArmR="x", Cape="x", Head="z", Body="x")


def check_pose(parts, label, **ang):
    pts = {k: rotated(centres(parts[k]), JOINTS[k], ANG_AXES[k], ang.get(k, 0.0)) for k in ORDER}
    occ = {k: occupancy(pts[k], fat=False) for k in ORDER}
    bad = []
    for i, a in enumerate(ORDER):
        for b in ORDER[i + 1:]:
            n = int(inside(pts[a], occ[b]).sum()) + int(inside(pts[b], occ[a]).sum())
            if n:
                bad.append("%s-%s:%d" % (a, b, n))
    low = min(float(q[:, 2].min()) for q in pts.values()) - 0.5
    print("CHECK %-14s overlaps: %s | lowest z = %.1f vox" % (label, ", ".join(bad) if bad else "none", low))
    return bad


# ---------------------------------------------------------------------------------------------------- previews

def preview_material(slot):
    """Preview-only look (the engine has its own shaders): colour from Col, true metals, cloth with a little bump."""
    name = "Prev_" + slot
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    col = nt.nodes.new("ShaderNodeVertexColor")
    col.layer_name = "Col"
    nt.links.new(col.outputs["Color"], bsdf.inputs["Base Color"])
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 180.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Distance"].default_value = 0.0006
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    if slot == "gold":
        bsdf.inputs["Metallic"].default_value = 1.0
        bsdf.inputs["Roughness"].default_value = 0.4
        bump.inputs["Strength"].default_value = 0.08
    elif slot == "metal":
        bsdf.inputs["Metallic"].default_value = 1.0
        bsdf.inputs["Roughness"].default_value = 0.42
        bump.inputs["Strength"].default_value = 0.1
    elif slot == "wool":
        bsdf.inputs["Roughness"].default_value = 0.95
        bump.inputs["Strength"].default_value = 0.35
        try:
            bsdf.inputs["Subsurface Weight"].default_value = 0.25
            bsdf.inputs["Subsurface Radius"].default_value = (0.02, 0.012, 0.008)
            nt.links.new(col.outputs["Color"], bsdf.inputs["Subsurface Color"]) if "Subsurface Color" in bsdf.inputs else None
        except KeyError:
            pass
    else:
        bsdf.inputs["Roughness"].default_value = 0.78
        bump.inputs["Strength"].default_value = 0.25
        try:
            bsdf.inputs["Subsurface Weight"].default_value = 0.06
            bsdf.inputs["Subsurface Radius"].default_value = (0.01, 0.004, 0.003)
        except KeyError:
            pass
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    return mat


def use_preview_materials(obs):
    for ob in obs.values():
        for i, mt in enumerate(ob.data.materials):
            ob.data.materials[i] = preview_material(mt.name.replace("Vox_", ""))


def setup_stage():
    scene = bpy.context.scene
    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.30, 0.27, 0.23, 1.0)
    bg.inputs[1].default_value = 0.28
    # shadow-catching floor (the montage lays the render over the reference's grey)
    bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, 0))
    g = bpy.context.active_object
    g.name = "PreviewGround"
    g.is_shadow_catcher = True
    # key: strong warm sun from the front-left of the picture's camera
    sun = bpy.data.lights.new("Key", "SUN")
    sun.energy = 4.2
    sun.color = (1.0, 0.82, 0.62)
    sun.angle = math.radians(3.0)
    so = bpy.data.objects.new("Key", sun)
    scene.collection.objects.link(so)
    a, e = math.radians(-52.0), math.radians(40.0)
    so.location = (math.sin(a) * math.cos(e) * 10, -math.cos(a) * math.cos(e) * 10, math.sin(e) * 10)
    V.look_at(so, (0, 0, 0.9))
    # rim: a bright light behind him, a little to his left, carving the silhouette
    for nm, loc, en, sz in (("Rim", (1.4, 3.2, 2.6), 900.0, 1.6), ("Rim2", (-1.6, 3.0, 2.8), 260.0, 1.4)):
        rl = bpy.data.lights.new(nm, "AREA")
        rl.energy = en
        rl.size = sz
        rl.color = (1.0, 0.93, 0.85)
        ro = bpy.data.objects.new(nm, rl)
        scene.collection.objects.link(ro)
        ro.location = loc
        V.look_at(ro, (0, 0, 1.0))
    # a soft cool fill from the right, low
    fl = bpy.data.lights.new("Fill", "AREA")
    fl.energy = 120.0
    fl.size = 3.0
    fl.color = (0.85, 0.9, 1.0)
    fo = bpy.data.objects.new("Fill", fl)
    scene.collection.objects.link(fo)
    fo.location = (3.0, -3.5, 1.2)
    V.look_at(fo, (0, 0, 0.9))
    cam = bpy.data.objects.new("PreviewCam", bpy.data.cameras.new("PreviewCam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 24 if FAST else 96
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 6
    scene.render.film_transparent = True
    for look in ("AgX - Punchy", "AgX - High Contrast", "AgX - Medium High Contrast"):
        try:
            scene.view_settings.view_transform = "AgX"
            scene.view_settings.look = look
            break
        except Exception:
            continue
    scene.view_settings.exposure = -0.25
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "METAL"
        prefs.get_devices()
        for dev in prefs.devices:
            dev.use = True
        scene.cycles.device = "GPU"
    except Exception:
        pass


def shot(name, az, el, dist=6.4, target=(0, 0, 0.86), res=(720, 900), lens=95):
    scene = bpy.context.scene
    cam = scene.camera
    a, e = math.radians(az), math.radians(el)
    cam.location = (target[0] + math.sin(a) * math.cos(e) * dist, target[1] - math.cos(a) * math.cos(e) * dist,
                    target[2] + math.sin(e) * dist)
    V.look_at(cam, target)
    cam.data.lens = lens
    scene.render.resolution_x, scene.render.resolution_y = res
    path = os.path.join(V.PREVIEWS, "king_a_%s.png" % name)
    scene.render.filepath = path
    try:
        bpy.ops.render.render(write_still=True)
    except RuntimeError as e:
        print("GPU render failed (%s): CPU" % str(e).strip().splitlines()[0][:80])
        scene.cycles.device = "CPU"
        bpy.ops.render.render(write_still=True)
    print("rendered", path)
    return path


def load_px(path):
    im = bpy.data.images.load(path)
    w, h = im.size
    a = np.empty(w * h * 4, np.float32)
    im.pixels.foreach_get(a)
    bpy.data.images.remove(im)
    a = a.reshape(h, w, 4)[::-1].copy()
    # lay transparent renders over the reference's grey
    al = a[..., 3:4]
    a[..., :3] = a[..., :3] * al + np.array(BG, np.float32) * (1 - al)
    a[..., 3] = 1.0
    return a


def save_px(a, path):
    h, w = a.shape[:2]
    im = bpy.data.images.new("montage", w, h, alpha=False)
    im.pixels.foreach_set(np.ascontiguousarray(a[::-1]).ravel())
    im.filepath_raw = path
    im.file_format = "PNG"
    im.save()
    bpy.data.images.remove(im)


def fit_h(a, H):
    h, w = a.shape[:2]
    W = max(1, int(round(w * H / h)))
    yi = np.clip(((np.arange(H) + 0.5) * h / H).astype(int), 0, h - 1)
    xi = np.clip(((np.arange(W) + 0.5) * w / W).astype(int), 0, w - 1)
    return a[yi][:, xi]


def montage(paths, out, H=800, crops=None):
    tiles = []
    for i, path in enumerate(paths):
        a = load_px(path)
        if crops and crops[i]:
            x0, y0, x1, y1 = crops[i]
            a = a[y0:y1, x0:x1]
        tiles.append(fit_h(a, H))
    save_px(np.concatenate(tiles, axis=1), out)
    print("montage", out)


def pose(obs, **ang):
    for key, ob in obs.items():
        ob.location = pivot(key)
        a = ang.get(key, 0.0)
        ob.rotation_euler = (math.radians(a), 0, 0) if ANG_AXES[key] == "x" else (0, 0, math.radians(a))


def want(name):
    return VIEWS is None or name in VIEWS


def main():
    V.reset_scene()
    parts = build_king()

    allc = np.concatenate([centres(parts[k]) for k in ORDER])
    lo, hi = allc.min(axis=0) - 0.5, allc.max(axis=0) + 0.5
    print("KING size: x %.3f..%.3f m, y %.3f..%.3f m, height %.4f m" % (
        lo[0] * VOX, hi[0] * VOX, lo[1] * VOX, hi[1] * VOX, hi[2] * VOX))
    check_pose(parts, "rest")
    check_pose(parts, "walk A", LegL=35, LegR=-35, ArmL=-35, ArmR=35, Cape=20)
    check_pose(parts, "walk B", LegL=-35, LegR=35, ArmL=35, ArmR=-35, Cape=20)
    check_pose(parts, "run A", LegL=45, LegR=-45, ArmL=-45, ArmR=45, Cape=30)
    check_pose(parts, "run B", LegL=-45, LegR=45, ArmL=45, ArmR=-45, Cape=30)
    check_pose(parts, "head turn", Head=25)

    obs = {}
    total = 0
    for key in ORDER:
        ob = block_mesh(parts[key], PREFIX + key, part_xform(key))
        obs[key] = ob
        V.export_gltf(ob, collision="none", extra=dict(pivot=pivot(key), part=key, blocks=int(ob["blocks"])))
        total += int(ob["voxel_faces"])
        print("FACES %-5s tris %6d" % (key, int(ob["voxel_faces"])))
    print("KING triangles in all:", total)
    meta = dict(height=1.7, radius=0.42, voxel=VOX,
                parts={key: dict(mesh=PREFIX + key, pivot=pivot(key)) for key in ORDER})
    with open(os.path.join(V.MESHES, "SM_KingA.json"), "w") as f:
        json.dump(meta, f, indent=1)
    print("wrote SM_KingA.json", json.dumps(meta["parts"]))
    if NO_RENDER:
        return

    use_preview_materials(obs)
    setup_stage()
    P = V.PREVIEWS
    pose(obs)
    if want("compare"):
        hero = shot("hero", az=-30, el=3.0, dist=6.4, target=(0, 0, 0.87), res=(800, 1050), lens=118)
        montage([REF, hero], os.path.join(P, "king_a_compare.png"), H=1050, crops=[(0, 40, 1005, 1360), None])
    if want("sides"):
        tiles = [shot("front", 0, 4), shot("left", 90, 4), shot("back", 180, 4), shot("right", -90, 4)]
        montage(tiles, os.path.join(P, "king_a_sides.png"), H=800)
    if want("face"):
        shot("face", az=-22, el=4, dist=1.9, target=(0, 0, 1.47), res=(800, 800))
    if want("walk"):
        pose(obs, LegL=35, LegR=-35, ArmL=-35, ArmR=35, Cape=20)
        tiles = [shot("walk_front", -30, 4), shot("walk_right", -90, 4), shot("walk_left", 90, 4), shot("walk_back", 160, 8)]
        montage(tiles, os.path.join(P, "king_a_walk.png"), H=800)
        pose(obs)


main()
