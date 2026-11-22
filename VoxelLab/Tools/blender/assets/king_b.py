"""King David (version B): a stocky king built from INDIVIDUAL bevelled cubes and slabs of several sizes, as seven
rigid parts (a wooden toy), each exported on its own with its mesh origin at its joint.

    Blender -b --factory-startup --python Tools/blender/assets/king_b.py -- [--no-render] [--views hero,sides,...] [--fast]

Units: everything is sculpted in "u" = 1.25 cm (he is 136 u tall). World axes: +X is his LEFT (he faces -Y), z = 0 is
the ground between his feet.

How it is made
  * Shapes are sculpted in small grids (Grid) of 2 u cells (4 u for cape and fur, 1 u for the face), often in a tilted
    frame (forearms, sword, head, torso), and emit() MERGES them: every region of one colour is covered by the fewest,
    largest boxes (bars, slabs, strips of mixed size), each a real box with a micro-bevel on every edge; some take the
    next lighter or darker shade, some stand a little proud. Small cubes are kept for accents only: fur, studs, gems,
    the medallion's rays, the ragged hem. Fist, sword, buckle, tabard strips and clasps are direct blocks.
  * A dark "core" sits just under the blocks so the hairline seams between them are closed.
  * Faces that are buried under a neighbouring block are removed (cull); bevels keep the neighbouring faces' normals,
    so each face shades flat and each bevel catches a highlight.
  * The colour attribute "Col" holds each block's colour (linear) times a baked proximity shading (ao_field), with the
    seam bevels darkened, so seams and overlaps read in the engine.
  * Slots: Vox_paint (cloth, skin, hair, leather), Vox_gold, Vox_metal, Vox_wool (fur).
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import json
import math
import time

import bpy
import numpy as np
import voxlib as V
import voxkit as K
from voxlib import Vox

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
NO_RENDER = "--no-render" in ARGS
DIAG = "--diag" in ARGS
FAST = "--fast" in ARGS
VIEWS = set(ARGS[ARGS.index("--views") + 1].split(",")) if "--views" in ARGS else None

U = 0.0125
PREFIX = "SM_KingB_"
REF = os.path.join(V.ROOT, "References", "king.png")
# The figure is a tree of rigid parts (PARENT; no entry = the figure's root). Body is the pelvis, Chest turns on it at
# the waist; each arm is an upper arm and a forearm (with the hand), each leg a thigh (with its half of the skirt) and a
# shin (with the boot); the cape is a yoke on the shoulders and CAPE_COLS chains of CAPE_ROWS panels hanging from it
# ("Cape<col><row>", col 0 on his right), which the engine swings as cloth.
ORDER = ["Body", "Chest", "Head", "ArmL", "ForeL", "ArmR", "ForeR", "HandR", "LegL", "ShinL", "LegR", "ShinR", "Cape", "Sword", "Sheath"]
PARENT = {"Chest": "Body", "Head": "Chest", "ArmL": "Chest", "ArmR": "Chest", "ForeL": "ArmL", "ForeR": "ArmR", "HandR": "ForeR",
          "ShinL": "LegL", "ShinR": "LegR", "Cape": "Chest", "Sheath": "Body"}
CAPE_COLS, CAPE_ROWS = 5, 4
CAPE_U = (-0.72, -0.25, 0.25, 0.72)           # the columns' borders, as a share of the cape's half width
CAPE_L = ((16, 36, 56, 76), (20, 40, 60, 80)) # where the rows start, u below the collar (even / odd columns: staggered)
ELBOW = {"L": 14.0, "R": 33.0}                # the bend the forearms are modelled with (degrees)
KNEE_Z = 28.0
TOP = 138.0                                   # the tip of the crown
JOINTS = {                                    # u, world
    "Body": (0, 0, 56), "Chest": (0, 0, 73), "Head": (0, 0, 104),
    "ArmL": (25, 0, 100), "ArmR": (-25, 0, 100),
    "LegL": (12, 0, 54), "LegR": (-12, 0, 54),
    "ShinL": (12, 0, KNEE_Z), "ShinR": (-12, 0, KNEE_Z),
    "Cape": (0, 16, 104),
    "Sheath": (0, 0, 56),                     # rides on the body
    "Sword": (0, 0, 0),                       # the middle of the grip in his right fist: set by build_sword()
}

MATN = ["paint", "gold", "metal", "wool"]
KINDS = ["cloth", "skin", "hair", "leather", "gold", "metal", "fur", "gem", "core", "blade"]
_PAL = [
    # name        colour     slot     preview kind
    ("gold",     "#FFB616", "gold", "gold"), ("gold_l", "#FFD63E", "gold", "gold"), ("gold_d", "#E39510", "gold", "gold"),
    ("gold_dd",  "#A2640C", "gold", "gold"),
    ("steel",    "#A19EA2", "metal", "metal"), ("steel_l", "#B6B2B3", "metal", "metal"), ("steel_ll", "#CFCAC8", "metal", "metal"),
    ("steel_d",  "#8A888E", "metal", "metal"), ("steel_dd", "#69676F", "metal", "metal"),
    ("blade",    "#D2CCC8", "metal", "blade"), ("blade_l", "#ECE7E1", "metal", "blade"), ("blade_d", "#B3ADAD", "metal", "blade"),
    ("blade_dd", "#979397", "metal", "blade"),
    ("skin",     "#B5622B", "paint", "skin"), ("skin_l", "#C87439", "paint", "skin"), ("skin_d", "#98501F", "paint", "skin"),
    ("skin_dd",  "#7D3F1B", "paint", "skin"), ("lip", "#93472B", "paint", "skin"),
    ("mouth", "#4E2014", "paint", "skin"), ("lip_l", "#C9744A", "paint", "skin"),
    ("hair",     "#2A1E18", "paint", "hair"), ("hair_l", "#3E2B20", "paint", "hair"), ("hair_d", "#1C1410", "paint", "hair"),
    ("hair_h",   "#553A2A", "paint", "hair"),
    ("fur",      "#F7D6A4", "wool", "fur"), ("fur_l", "#FFE9C4", "wool", "fur"), ("fur_d", "#E6B982", "wool", "fur"),
    ("fur_dd",   "#C79864", "wool", "fur"),
    ("green",    "#4F6E1F", "paint", "cloth"), ("green_l", "#61822A", "paint", "cloth"), ("green_d", "#405B1B", "paint", "cloth"),
    ("green_dd", "#2F4516", "paint", "cloth"),
    ("cream",    "#E5CFA0", "paint", "cloth"), ("cream_l", "#F1E0B8", "paint", "cloth"), ("cream_d", "#CBB183", "paint", "cloth"),
    ("cream_dd", "#B49C72", "paint", "cloth"),
    ("belt",     "#7B4A24", "paint", "leather"), ("belt_l", "#96602F", "paint", "leather"), ("belt_d", "#5A3418", "paint", "leather"),
    ("belt_dd",  "#40240F", "paint", "leather"),
    ("sleeve",   "#A46C3E", "paint", "cloth"), ("sleeve_l", "#BB8452", "paint", "cloth"), ("sleeve_d", "#7E4E2B", "paint", "cloth"),
    ("bracer",   "#4B372D", "paint", "leather"), ("bracer_l", "#634B3D", "paint", "leather"), ("bracer_d", "#33251E", "paint", "leather"),
    ("sole",     "#6B4426", "paint", "leather"), ("sole_d", "#4C2E18", "paint", "leather"),
    ("white",    "#F4EFE4", "paint", "gem"), ("pupil", "#15100E", "paint", "hair"),
    ("gem",      "#D8551C", "paint", "gem"), ("gem_l", "#FF9A4A", "paint", "gem"), ("gem_w", "#FFF4DA", "paint", "gem"),
    ("core",     "#17120F", "paint", "core"),
]
PN = [None] + [p[0] for p in _PAL]
PI = {n: i for i, n in enumerate(PN)}
PRGB = np.array([[0, 0, 0]] + [[int(p[1][i:i + 2], 16) / 255.0 for i in (1, 3, 5)] for p in _PAL], np.float32)
PMAT = np.array([0] + [MATN.index(p[2]) for p in _PAL], np.int32)
PKIND = np.array([0] + [KINDS.index(p[3]) for p in _PAL], np.int32)


# ---------------------------------------------------------------------------------------------------- small maths

def RX(deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], np.float64)


def RY(deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], np.float64)


def RZ(deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], np.float64)


class Frame:
    """world = R @ local + t (u)."""

    def __init__(self, R=None, t=None):
        self.R = np.eye(3) if R is None else np.array(R, np.float64)
        self.t = np.zeros(3) if t is None else np.array(t, np.float64)

    def sub(self, Rl, pivot):
        """A child frame: this frame's local space turned by Rl about a pivot given in local coordinates."""
        pivot = np.array(pivot, np.float64)
        return Frame(self.R @ Rl, self.R @ (pivot - Rl @ pivot) + self.t)

    def place(self, Rl, at):
        """A child frame whose origin sits at local point `at`, turned by Rl."""
        return Frame(self.R @ Rl, self.R @ np.array(at, np.float64) + self.t)

    def w(self, p):
        return np.asarray(p, np.float64) @ self.R.T + self.t

    def inv(self, P):
        return (np.asarray(P, np.float64) - self.t) @ self.R


IDENT = Frame()


def hash3(a, b, c, seed=0):
    h = (a.astype(np.int64) * 73856093) ^ (b.astype(np.int64) * 19349663) ^ (c.astype(np.int64) * 83492791) ^ (seed * 2654435761)
    h = (h ^ (h >> 13)) * 1274126177
    h = h ^ (h >> 16)
    return (h & 0xFFFFFF).astype(np.float32) / float(0xFFFFFF)


def shift(a, axis, n, fill=0):
    """b[p + n along axis] = a[p]."""
    b = np.roll(a, n, axis=axis)
    sl = [slice(None)] * a.ndim
    sl[axis] = slice(0, n) if n > 0 else slice(n, None)
    b[tuple(sl)] = fill
    return b


# ---------------------------------------------------------------------------------------------------- parts and blocks

class Part:
    def __init__(self, key):
        self.key = key
        self.joint = np.array(JOINTS[key], np.float64)
        self._ch = []
        self._gid = {}
        self._frames = []
        self.bias = 0                         # counts as this many earlier chunks for emit()'s random stream

    def gid(self, frame):
        k = id(frame)
        if k not in self._gid:
            self._gid[k] = len(self._gid) + 1
            self._frames.append(frame)
        return self._gid[k]

    def add(self, frame, lo, hi, pi, w, keep=None, rgb=None, cull=True):
        lo = np.atleast_2d(np.asarray(lo, np.float64))
        hi = np.atleast_2d(np.asarray(hi, np.float64))
        n = len(lo)
        pi = np.broadcast_to(np.asarray(pi, np.int32), (n,)).copy()
        if rgb is None:
            rgb = PRGB[pi]
        if keep is None:
            keep = np.full((n, 6), -1 if cull else 1, np.int8)
        self._ch.append(dict(
            c=(lo + hi) / 2, h=(hi - lo) / 2, R=np.broadcast_to(frame.R, (n, 3, 3)).copy(), t=np.broadcast_to(frame.t, (n, 3)).copy(),
            pi=pi, rgb=np.asarray(rgb, np.float32).reshape(n, 3), w=np.broadcast_to(np.asarray(w, np.float64), (n,)).copy(),
            keep=np.asarray(keep, np.int8).reshape(n, 6), gid=np.full(n, self.gid(frame) if cull else 0, np.int32)))

    def blk(self, frame, x0, x1, y0, y1, z0, z1, name, bevel=0.09, cull=True, tint=1.0, sx=1):
        """One block, bounds in the frame's local u (x mirrored when sx < 0)."""
        if sx < 0:
            x0, x1 = -x1, -x0
        size = sorted((abs(x1 - x0), abs(y1 - y0), abs(z1 - z0)))
        w = min(bevel * size[1], 0.3 * size[0], 0.34)
        rgb = np.clip(PRGB[PI[name]] * tint, 0, 1)
        self.add(frame, [min(x0, x1), min(y0, y1), min(z0, z1)], [max(x0, x1), max(y0, y1), max(z0, z1)], PI[name], w, rgb=rgb, cull=cull)

    def finalize(self):
        for k in ("c", "h", "R", "t", "pi", "rgb", "w", "keep", "gid"):
            setattr(self, k, np.concatenate([c[k] for c in self._ch]))
        self.core = PKIND[self.pi] == KINDS.index("core")
        flat = np.abs(self.R - np.eye(3)).max(axis=(1, 2)) < 1e-9
        for sg, lim in ((-1, 0.0), (1, TOP)):
            edge = self.c[:, 2] + self.t[:, 2] + sg * self.h[:, 2]
            over = np.where(flat, np.maximum(0.0, sg * (edge - lim)), 0.0)
            over = np.minimum(over, 2 * self.h[:, 2] - 0.05)
            self.c[:, 2] -= sg * over / 2
            self.h[:, 2] -= over / 2
        return self

    def world_boxes(self):
        return self.c, self.h, self.R, self.t


class Combo:
    """Several finalized parts taken as one rigid piece about the first one's joint (for the clearance searches)."""

    def __init__(self, *parts):
        self.key = parts[0].key
        self.joint = parts[0].joint
        for k in ("c", "h", "R", "t", "w", "core"):
            setattr(self, k, np.concatenate([getattr(q, k) for q in parts]))


class Grid:
    """A sculpting grid of cubic cells (cs u each) in a frame. Coordinates passed in are the frame's local u; with
    sx = -1 the x you pass is mirrored (so both arms/legs are written once, x growing outward)."""

    def __init__(self, frame, x0, x1, y0, y1, z0, z1, cs=1.0, sx=1):
        self.frame, self.cs, self.sx = frame, float(cs), sx
        if sx < 0:
            x0, x1 = -x1, -x0
        self.lo = np.array([x0, y0, z0], np.float64)
        self.n = tuple(int(round((b - a) / cs)) for a, b in ((x0, x1), (y0, y1), (z0, z1)))
        self.p = np.zeros(self.n, np.uint8)
        self.ix, self.iy, self.iz = np.meshgrid(*[np.arange(k) for k in self.n], indexing="ij")
        self.X = (self.ix + 0.5) * cs + x0
        self.Y = (self.iy + 0.5) * cs + y0
        self.Z = (self.iz + 0.5) * cs + z0
        self.XS = self.X * sx
        self.dout = "+x" if sx > 0 else "-x"
        self.din = "-x" if sx > 0 else "+x"

    def bm(self, x0, x1, y0, y1, z0, z1):
        return (self.XS > x0) & (self.XS < x1) & (self.Y > y0) & (self.Y < y1) & (self.Z > z0) & (self.Z < z1)

    def fill(self, mask, name):
        self.p[mask] = PI[name]
        return self

    def paint(self, mask, name):
        self.p[mask & (self.p > 0)] = PI[name]
        return self

    def carve(self, mask):
        self.p[mask] = 0
        return self

    def box(self, x0, x1, y0, y1, z0, z1, name):
        return self.fill(self.bm(x0, x1, y0, y1, z0, z1), name)

    def pbox(self, x0, x1, y0, y1, z0, z1, name):
        return self.paint(self.bm(x0, x1, y0, y1, z0, z1), name)

    def isn(self, *names):
        return np.isin(self.p, [PI[n] for n in names])

    def solid(self):
        return self.p > 0

    def exposed(self, d):
        axis = "xyz".index(d[1])
        s = self.p > 0
        nb = shift(s, axis, -1 if d[0] == "+" else 1, False)
        return s & ~nb

    def surface(self):
        m = np.zeros(self.n, bool)
        for d in ("+x", "-x", "+y", "-y", "+z", "-z"):
            m |= self.exposed(d)
        return m

    def hash(self, cell=2, seed=0, ax=(1, 1, 1)):
        return hash3((self.ix // cell) * ax[0], (self.iy // cell) * ax[1], (self.iz // cell) * ax[2], seed)

    def grow(self, mask, d, n=1, name=None):
        """Copy the masked solid cells n steps outward in direction d (into air only)."""
        axis = "xyz".index(d[1])
        sg = 1 if d[0] == "+" else -1
        src = np.where(mask & (self.p > 0), self.p, 0)
        for i in range(1, n + 1):
            sh = shift(src, axis, sg * i, 0)
            take = (sh > 0) & (self.p == 0)
            self.p[take] = PI[name] if name else sh[take]
        return self

    def local(self, frame):
        """The cell centres expressed in another frame's local coordinates -> (lx, ly, lz)."""
        P = np.stack([self.X, self.Y, self.Z], axis=-1).reshape(-1, 3)
        L = frame.inv(self.frame.w(P)).reshape(self.n + (3,))
        return L[..., 0], L[..., 1], L[..., 2]


def greedy(sub):
    """Maximal boxes of equal non-zero value in a small array -> [(x0, y0, z0, x1, y1, z1, value)]."""
    out = []
    a = sub.copy()
    nx, ny, nz = a.shape
    for x in range(nx):
        for y in range(ny):
            for z in range(nz):
                v = a[x, y, z]
                if not v:
                    continue
                z1 = z + 1
                while z1 < nz and a[x, y, z1] == v:
                    z1 += 1
                y1 = y + 1
                while y1 < ny and (a[x, y1, z:z1] == v).all():
                    y1 += 1
                x1 = x + 1
                while x1 < nx and (a[x1, y:y1, z:z1] == v).all():
                    x1 += 1
                a[x:x1, y:y1, z:z1] = 0
                out.append((x, y, z, x1, y1, z1, int(v)))
    return out


LEVELS = ["dd", "d", "", "l", "ll"]


def _ladder():
    """For every colour, the next lighter and next darker shade of its family (itself where there is none)."""
    fam = {}
    for nme in PN[1:]:
        base, _, suf = nme.partition("_")
        if suf in LEVELS:
            fam.setdefault(base, {})[LEVELS.index(suf)] = PI[nme]
    up, dn = np.arange(len(PN)), np.arange(len(PN))
    for d in fam.values():
        for lv, i in d.items():
            up[i] = d.get(lv + 1, i)
            dn[i] = d.get(lv - 1, i)
    return up, dn


PUP, PDN = _ladder()
NOSHADE = ("white", "pupil", "lip", "mouth", "lip_l", "gem", "gem_l", "gem_w", "core")


def emit(part, g, lim=(8, 16), pref=None, lims=None, shade=0.35, proud_p=0.3, proud=(0.1, 0.35), bevel=1.0, cjit=0.03,
         seed=0, core=True, tilt=0.0, core_rgb=None):
    """Turn a grid into blocks by MERGING: every region of one colour is covered by a few large boxes. A box starts
    at the first free cell and grows along the three axes (pref first, the others in random order) while the cells
    are the same colour, up to a length drawn at random from lim (u; one range, or one per axis; lims gives other
    ranges for single colours), so neighbours come out as bars, slabs and strips of different sizes. A share
    `shade` of the boxes take the next lighter or darker shade of their colour, a share proud_p stand proud by
    `proud` u. Boxes that never reach the surface are dropped; a dark core closes the seams behind the rest.
    tilt > 0 turns every box by up to that many degrees about its own centre (fur)."""
    p = g.p
    n = np.array(p.shape)
    solid = p > 0
    if not solid.any():
        return 0
    cs = g.cs
    lims = lims or {}
    pad = np.pad(solid, 1)
    exp = [~pad[2:, 1:-1, 1:-1], ~pad[:-2, 1:-1, 1:-1], ~pad[1:-1, 2:, 1:-1], ~pad[1:-1, :-2, 1:-1], ~pad[1:-1, 1:-1, 2:], ~pad[1:-1, 1:-1, :-2]]
    exp = [e & solid for e in exp]                          # +x -x +y -y +z -z
    surf = exp[0] | exp[1] | exp[2] | exp[3] | exp[4] | exp[5]
    taken = ~solid
    rng = np.random.default_rng(seed + 1000 * (len(part._ch) + part.bias))
    pa = "xyz".index(pref) if pref else None
    blocks = []
    for (x, y, z) in np.argwhere(solid):
        if taken[x, y, z]:
            continue
        v = p[x, y, z]
        spec = lims.get(PN[v], lims.get(PN[v].partition("_")[0], lim))
        L = []
        for a in range(3):
            r = spec[a] if isinstance(spec[0], (tuple, list)) else spec
            L.append(max(1, int(round(rng.uniform(r[0], r[1]) / cs))))
        axes = [a for a in rng.permutation(3) if a != pa]
        if pa is not None:
            axes = [pa] + axes
        lo, hi = [x, y, z], [x + 1, y + 1, z + 1]

        def free(a, at):
            sl = [slice(lo[i], hi[i]) for i in range(3)]
            sl[a] = at
            sl = tuple(sl)
            return at < n[a] and bool((p[sl] == v).all()) and not taken[sl].any()

        for a in axes:
            while free(a, hi[a]):
                if hi[a] - lo[a] >= L[a] and free(a, hi[a] + 1):      # at its length, and more than a sliver is left
                    break
                hi[a] += 1
        sl = tuple(slice(lo[i], hi[i]) for i in range(3))
        taken[sl] = True
        if surf[sl].any():
            blocks.append((lo[0], lo[1], lo[2], hi[0], hi[1], hi[2], int(v)))
    if not blocks:
        return 0
    B = np.array(blocks, np.int64)
    lo = B[:, 0:3].astype(np.float64)
    hi = B[:, 3:6].astype(np.float64)
    pi = B[:, 6].astype(np.int32)
    # shade: some blocks a step lighter or darker than their neighbours
    r = rng.random(len(B))
    ok = ~np.isin(pi, [PI[nm] for nm in NOSHADE])
    pi = np.where(ok & (r < shade * 0.5), PUP[pi], np.where(ok & (r > 1 - shade * 0.5), PDN[pi], pi)).astype(np.int32)
    # proud: grow outward on faces whose every cell is open
    amount = np.where(rng.random(len(B)) < proud_p, rng.uniform(proud[0], proud[1], len(B)), 0.0) / cs
    for i in np.nonzero(amount > 0)[0]:
        x0, y0, z0, x1, y1, z1 = B[i, :6]
        if exp[0][x1 - 1, y0:y1, z0:z1].all():
            hi[i, 0] += amount[i]
        if exp[1][x0, y0:y1, z0:z1].all():
            lo[i, 0] -= amount[i]
        if exp[2][x0:x1, y1 - 1, z0:z1].all():
            hi[i, 1] += amount[i]
        if exp[3][x0:x1, y0, z0:z1].all():
            lo[i, 1] -= amount[i]
        if exp[4][x0:x1, y0:y1, z1 - 1].all():
            hi[i, 2] += amount[i]
        if exp[5][x0:x1, y0:y1, z0].all():
            lo[i, 2] -= amount[i]
    size = np.sort((B[:, 3:6] - B[:, 0:3]) * cs, axis=1)
    w = np.minimum(np.clip(0.03 * size[:, 1], 0.15, 0.30) * bevel, 0.3 * size[:, 0])     # micro-bevel, a little wider on big blocks
    rgb = PRGB[pi] * (1.0 + np.clip(rng.normal(0, cjit, (len(B), 1)), -2.2 * cjit, 2.2 * cjit))
    if tilt > 0:
        for i in range(len(B)):
            cen = (lo[i] + hi[i]) / 2 * cs + g.lo
            half = (hi[i] - lo[i]) / 2 * cs
            Rm = RZ(rng.uniform(-tilt, tilt)) @ RY(rng.uniform(-tilt, tilt)) @ RX(rng.uniform(-tilt, tilt))
            part.add(g.frame.place(Rm, cen), -half, half, pi[i], w[i], rgb=np.clip(rgb[i], 0, 1), cull=False)
    else:
        part.add(g.frame, lo * cs + g.lo, hi * cs + g.lo, pi, w, rgb=np.clip(rgb, 0, 1))
    if core:
        m = 0.1 * bevel / cs                                 # cells: just under the shallowest bevel
        CC = max(2, int(round(8 / cs)))
        lo_l, hi_l, keep_l = [], [], []
        for cx in range(0, n[0], CC):
            for cy in range(0, n[1], CC):
                for cz in range(0, n[2], CC):
                    sub = solid[cx:cx + CC, cy:cy + CC, cz:cz + CC]
                    if not sub.any():
                        continue
                    boxes = [(0, 0, 0) + sub.shape + (1,)] if sub.all() else greedy(sub.astype(np.uint8))
                    for (x0, y0, z0, x1, y1, z1, _) in boxes:
                        x0, y0, z0, x1, y1, z1 = x0 + cx, y0 + cy, z0 + cz, x1 + cx, y1 + cy, z1 + cz
                        ps = pad                               # index + 1
                        fl = [ps[x1 + 1, y0 + 1:y1 + 1, z0 + 1:z1 + 1].all(), ps[x0, y0 + 1:y1 + 1, z0 + 1:z1 + 1].all(),
                              ps[x0 + 1:x1 + 1, y1 + 1, z0 + 1:z1 + 1].all(), ps[x0 + 1:x1 + 1, y0, z0 + 1:z1 + 1].all(),
                              ps[x0 + 1:x1 + 1, y0 + 1:y1 + 1, z1 + 1].all(), ps[x0 + 1:x1 + 1, y0 + 1:y1 + 1, z0].all()]
                        if all(fl):
                            continue
                        l = [x0 + (0 if fl[1] else m), y0 + (0 if fl[3] else m), z0 + (0 if fl[5] else m)]
                        h = [x1 - (0 if fl[0] else m), y1 - (0 if fl[2] else m), z1 - (0 if fl[4] else m)]
                        if min(h[0] - l[0], h[1] - l[1], h[2] - l[2]) <= 0.05:
                            continue
                        lo_l.append(l)
                        hi_l.append(h)
                        keep_l.append([0 if fl[1] else 1, 0 if fl[0] else 1, 0 if fl[3] else 1, 0 if fl[2] else 1, 0 if fl[5] else 1, 0 if fl[4] else 1])
        if lo_l:
            crgb = np.tile(PRGB[p[solid]].mean(axis=0) * 0.28 if core_rgb is None else np.array(core_rgb), (len(lo_l), 1))
            part.add(g.frame, np.array(lo_l) * cs + g.lo, np.array(hi_l) * cs + g.lo, PI["core"], 0.0, keep=np.array(keep_l, np.int8), rgb=crgb)
    return len(B)


# ---- the chamfered box: 24 vertices (3 per corner, one on each face that meets there)

SG = np.array([[(1 if ci & 1 else -1), (1 if ci & 2 else -1), (1 if ci & 4 else -1)] for ci in range(8)], np.float64)
VS = np.repeat(SG, 3, axis=0)
VA = np.tile(np.arange(3), 8)
VM = (np.arange(3)[None, :] != VA[:, None]).astype(np.float64)
VN = np.zeros((24, 3))
VN[np.arange(24), VA] = VS[np.arange(24), VA]


def _templates():
    pos = VS * (1.0 - 0.2 * VM)

    def cid(s):
        return (1 if s[0] > 0 else 0) + (2 if s[1] > 0 else 0) + (4 if s[2] > 0 else 0)

    main = []
    for a in range(3):
        b, c = (a + 1) % 3, (a + 2) % 3
        for sg in (-1, 1):                                    # face f = a * 2 + (sg > 0)
            quad = []
            for (sb, sc) in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                s = [0, 0, 0]
                s[a], s[b], s[c] = sg, sb, sc
                quad.append(cid(s) * 3 + a)
            nrm = np.cross(pos[quad[1]] - pos[quad[0]], pos[quad[2]] - pos[quad[0]])
            if nrm[a] * sg < 0:
                quad = quad[::-1]
            main.append(quad)
    edges, edge_faces = [], []
    for a in range(3):
        for b in range(a + 1, 3):
            c = 3 - a - b
            for sa in (-1, 1):
                for sb in (-1, 1):
                    def vid(sc, ax):
                        s = [0, 0, 0]
                        s[a], s[b], s[c] = sa, sb, sc
                        return cid(s) * 3 + ax
                    quad = [vid(-1, a), vid(1, a), vid(1, b), vid(-1, b)]
                    nrm = np.cross(pos[quad[1]] - pos[quad[0]], pos[quad[2]] - pos[quad[0]])
                    d = np.zeros(3)
                    d[a], d[b] = sa, sb
                    if nrm.dot(d) < 0:
                        quad = quad[::-1]
                    edges.append(quad)
                    edge_faces.append((a * 2 + (1 if sa > 0 else 0), b * 2 + (1 if sb > 0 else 0)))
    corners, corner_faces = [], []
    for ci in range(8):
        tri = [ci * 3, ci * 3 + 1, ci * 3 + 2]
        nrm = np.cross(pos[tri[1]] - pos[tri[0]], pos[tri[2]] - pos[tri[0]])
        if nrm.dot(SG[ci]) < 0:
            tri = tri[::-1]
        corners.append(tri)
        corner_faces.append(tuple(a * 2 + (1 if SG[ci][a] > 0 else 0) for a in range(3)))
    return np.array(main), np.array(edges), np.array(edge_faces), np.array(corners), np.array(corner_faces)


T_MAIN, T_EDGE, T_EDGE_F, T_CORN, T_CORN_F = _templates()


def cull(part):
    """Decide which main faces of each block are buried under other blocks of the same frame."""
    eps = 0.02
    for g in np.unique(part.gid):
        if g == 0:
            continue
        I = np.nonzero(part.gid == g)[0]
        lo = part.c[I] - part.h[I]
        hi = part.c[I] + part.h[I]
        w = part.w[I]
        keep = part.keep[I].copy()
        for li in np.nonzero((keep < 0).any(axis=1))[0]:
            wi = w[li]
            for f in range(6):
                if keep[li, f] >= 0:
                    continue
                a = f // 2
                sg = 1 if f % 2 else -1
                b, c = (a + 1) % 3, (a + 2) % 3
                pos = (hi[li, a] if sg > 0 else lo[li, a]) + sg * eps
                b0, b1 = lo[li, b] + wi + eps, hi[li, b] - wi - eps
                c0, c1 = lo[li, c] + wi + eps, hi[li, c] - wi - eps
                cand = (lo[:, a] < pos) & (hi[:, a] > pos) & (lo[:, b] < b1) & (hi[:, b] > b0) & (lo[:, c] < c1) & (hi[:, c] > c0)
                cand[li] = False
                J = np.nonzero(cand)[0]
                if len(J) == 0:
                    keep[li, f] = 1
                    continue
                nb = max(2, int(math.ceil((b1 - b0) / 0.55)) + 1)
                nc = max(2, int(math.ceil((c1 - c0) / 0.55)) + 1)
                P = np.empty((nb * nc, 3))
                P[:, a] = pos
                P[:, b] = np.repeat(np.linspace(b0, b1, nb), nc)
                P[:, c] = np.tile(np.linspace(c0, c1, nc), nb)
                d = np.minimum(P[:, None, :] - lo[J][None], hi[J][None] - P[:, None, :])
                wj = w[J][None]
                ins = (d.min(axis=2) >= 0) & (d[:, :, 0] + d[:, :, 1] >= wj) & (d[:, :, 0] + d[:, :, 2] >= wj) & (d[:, :, 1] + d[:, :, 2] >= wj)
                keep[li, f] = 0 if ins.any(axis=1).all() else 1
        part.keep[I] = keep


# ---- baked proximity shading

AO_CELL = 0.5
AO_LO = np.array([-72.0, -48.0, -4.0])
AO_N = (288, 200, 290)


def part_points(part, step=0.45, shrink=0.0, cores=True):
    """Lattice points inside every block of a part, world u."""
    out = []
    sel = np.ones(len(part.c), bool) if cores else ~part.core
    h = np.maximum(part.h - shrink, 0.02)
    counts = np.maximum(2, np.ceil(2 * h / step).astype(np.int64) + 1)
    key = counts[:, 0] * 1000000 + counts[:, 1] * 1000 + counts[:, 2]
    for kv in np.unique(key[sel]):
        I = np.nonzero(sel & (key == kv))[0]
        kx, ky, kz = counts[I[0]]
        L = np.stack(np.meshgrid(np.linspace(-1, 1, kx), np.linspace(-1, 1, ky), np.linspace(-1, 1, kz), indexing="ij"), axis=-1).reshape(-1, 3)
        chunk = max(1, int(1500000 // len(L)))
        for s in range(0, len(I), chunk):
            J = I[s:s + chunk]
            loc = part.c[J][:, None, :] + L[None] * h[J][:, None, :]
            out.append((np.einsum("nij,nkj->nki", part.R[J], loc) + part.t[J][:, None, :]).reshape(-1, 3))
    return np.concatenate(out) if out else np.zeros((0, 3))


def box_blur(a, r):
    for axis in range(3):
        c = np.cumsum(a, axis=axis, dtype=np.float32)
        hi = np.minimum(np.arange(a.shape[axis]) + r, a.shape[axis] - 1)
        lo = np.arange(a.shape[axis]) - r - 1
        top = np.take(c, hi, axis=axis)
        bot = np.take(c, np.maximum(lo, 0), axis=axis)
        shape = [1, 1, 1]
        shape[axis] = -1
        bot = bot * (lo >= 0).reshape(shape)
        a = (top - bot) / float(2 * r + 1)
    return a


AO = {}


def ao_field(parts):
    occ = np.zeros(AO_N, np.float32)
    for part in parts.values():
        P = part_points(part, step=0.4)
        q = np.floor((P - AO_LO) / AO_CELL).astype(np.int64)
        ok = np.all((q >= 0) & (q < np.array(AO_N)), axis=1)
        q = q[ok]
        occ[q[:, 0], q[:, 1], q[:, 2]] = 1.0
    AO["o1"] = box_blur(box_blur(occ, 2), 2)
    AO["o2"] = box_blur(box_blur(occ, 6), 6)
    # what a flat wall gives, for the two sample distances
    line = np.zeros((1, 1, 400), np.float32)
    line[0, 0, :200] = 1.0
    l1 = box_blur(box_blur(np.repeat(np.repeat(line, 1, 0), 1, 1), 2), 2)[0, 0]
    l2 = box_blur(box_blur(line, 6), 6)[0, 0]
    AO["b1"] = float(l1[200 + int(round(AO_D1 / AO_CELL))])
    AO["b2"] = float(l2[200 + int(round(AO_D2 / AO_CELL))])


AO_D1, AO_D2 = 1.0, 3.0


def ao_at(P, N):
    """Brightness 0.3..1 at world points P (u) with outward normals N."""
    def sample(field, d):
        q = np.floor((P + N * d - AO_LO) / AO_CELL).astype(np.int64)
        q = np.clip(q, 0, np.array(AO_N) - 1)
        return field[q[:, 0], q[:, 1], q[:, 2]]
    a1 = np.clip((sample(AO["o1"], AO_D1) - AO["b1"]) / (1 - AO["b1"]), 0, 1)
    a2 = np.clip((sample(AO["o2"], AO_D2) - AO["b2"]) / (1 - AO["b2"]), 0, 1)
    return np.clip(1.0 - 0.42 * a1 - 0.45 * a2, 0.35, 1.0)


def mesh_arrays(part):
    """-> verts (metres, relative to the joint), normals, tris, per-corner colour (linear) and uv, per-tri slot/kind."""
    N = len(part.c)
    h, w = part.h, part.w
    loc = part.c[:, None, :] + VS[None] * (h[:, None, :] - w[:, None, None] * VM[None])
    wv = np.einsum("nij,nkj->nki", part.R, loc) + part.t[:, None, :]           # (N, 24, 3) world u
    wn = np.einsum("nij,kj->nki", part.R, VN)
    keep = part.keep == 1
    base = np.arange(N) * 24
    els = []                                                 # (vertex ids (M, k), block index (M,), shade (M,), lerp)
    for f in range(6):
        I = np.nonzero(keep[:, f])[0]
        if len(I):
            els.append((base[I][:, None] + T_MAIN[f][None], I, np.ones(len(I)), 0.2))
    bev = w > 1e-6
    for e in range(12):
        f1, f2 = T_EDGE_F[e]
        k1, k2 = keep[:, f1], keep[:, f2]
        I = np.nonzero((k1 | k2) & bev)[0]
        if len(I):
            shade = np.where(k1[I] & k2[I], 1.0, SEAM)
            els.append((base[I][:, None] + T_EDGE[e][None], I, shade, 0.5))
    for ci in range(8):
        f1, f2, f3 = T_CORN_F[ci]
        k1, k2, k3 = keep[:, f1], keep[:, f2], keep[:, f3]
        I = np.nonzero((k1 | k2 | k3) & bev)[0]
        if len(I):
            shade = np.where(k1[I] & k2[I] & k3[I], 1.0, SEAM * 0.9)
            els.append((base[I][:, None] + T_CORN[ci][None], I, shade, 0.5))
    V_ = wv.reshape(-1, 3)
    Nn = wn.reshape(-1, 3)
    tris, cols, uvs, tblk = [], [], [], []
    for (vid, I, shade, lerp) in els:
        P = V_[vid]                                           # (M, k, 3)
        nrm = Nn[vid].mean(axis=1)
        nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
        cen = P.mean(axis=1, keepdims=True)
        S = P + (cen - P) * lerp
        kk = vid.shape[1]
        ao = ao_at(S.reshape(-1, 3), np.repeat(nrm, kk, axis=0)).reshape(-1, kk)
        col = V.srgb_to_linear(part.rgb[I])[:, None, :] * (ao * shade[:, None])[:, :, None]
        ax = np.abs(nrm).argmax(axis=1)                       # box projection
        ua = np.where(ax == 0, 1, 0)
        va = np.where(ax == 2, 1, 2)
        uv = np.stack([np.take_along_axis(P, ua[:, None, None].repeat(kk, 1), axis=2)[..., 0],
                       np.take_along_axis(P, va[:, None, None].repeat(kk, 1), axis=2)[..., 0]], axis=-1) * (U / 4.0)
        order = [[0, 1, 2], [0, 2, 3]] if kk == 4 else [[0, 1, 2]]
        for o in order:
            tris.append(vid[:, o])
            cols.append(col[:, o])
            uvs.append(uv[:, o])
            tblk.append(I)
    tris = np.concatenate(tris)
    cols = np.concatenate(cols)
    uvs = np.concatenate(uvs)
    tblk = np.concatenate(tblk)
    used, inv = np.unique(tris.reshape(-1), return_inverse=True)
    return dict(verts=(V_[used] - part.joint) * U, normals=Nn[used], tris=inv.reshape(-1, 3), cols=cols, uvs=uvs,
                slot=PMAT[part.pi][tblk], kind=PKIND[part.pi][tblk])


SEAM = 0.4


def make_object(part):
    a = mesh_arrays(part)
    name = PREFIX + part.key
    T = len(a["tris"])
    mesh = bpy.data.meshes.new(name)
    mesh.vertices.add(len(a["verts"]))
    mesh.vertices.foreach_set("co", a["verts"].astype(np.float32).reshape(-1))
    mesh.loops.add(T * 3)
    mesh.loops.foreach_set("vertex_index", a["tris"].astype(np.int32).reshape(-1))
    mesh.polygons.add(T)
    mesh.polygons.foreach_set("loop_start", np.arange(0, T * 3, 3, dtype=np.int32))
    try:
        mesh.polygons.foreach_set("loop_total", np.full(T, 3, dtype=np.int32))
    except Exception:
        pass
    used = sorted(set(a["slot"].tolist()))
    lut = np.zeros(len(MATN), np.int32)
    for i, s in enumerate(used):
        lut[s] = i
        mesh.materials.append(V.material(MATN[s]))
    mesh.polygons.foreach_set("material_index", lut[a["slot"]].astype(np.int32))
    mesh.polygons.foreach_set("use_smooth", np.ones(T, bool))
    uv = mesh.uv_layers.new(name="UVMap")
    uv.data.foreach_set("uv", a["uvs"].astype(np.float32).reshape(-1))
    attr = mesh.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="CORNER")
    rgba = np.ones((T * 3, 4), np.float32)
    rgba[:, :3] = np.clip(a["cols"].reshape(-1, 3), 0.0, 4.0)
    attr.data.foreach_set("color", rgba.reshape(-1))
    mesh.color_attributes.active_color = attr
    mesh.color_attributes.render_color_index = 0
    mesh.update()
    if mesh.validate():
        print("WARNING: validate() changed", name)
    mesh.normals_split_custom_set_from_vertices(a["normals"].astype(np.float32).tolist())
    ob = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(ob)
    ob["voxel_faces"] = int(T // 2)
    ob["lights"] = "[]"
    ob["triangles"] = int(T)
    part.kind_per_tri = a["kind"]
    return ob


# ---------------------------------------------------------------------------------------------------- swept volumes

SW_LO = np.array([-80.0, -80.0, -20.0])
SW_N = (160, 180, 180)


def rotated(P, joint, axis, deg):
    R = RX(deg) if axis == "x" else RZ(deg)
    return (P - joint) @ R.T + joint


def occ_grid(P, cell=1.0):
    g = np.zeros(tuple(int(n / cell) for n in SW_N), bool)
    q = np.floor((P - SW_LO) / cell).astype(np.int64)
    ok = np.all((q >= 0) & (q < np.array(g.shape)), axis=1)
    q = q[ok]
    g[q[:, 0], q[:, 1], q[:, 2]] = True
    return g


def dilate(g, n=1):
    for _ in range(n):
        o = g.copy()
        for axis in range(3):
            o |= shift(g, axis, 1, False) | shift(g, axis, -1, False)
        g = o
    return g


def swept(part, axis, lo, hi, step=2.0, grow=1):
    P = part_points(part, step=0.7, cores=False)
    g = np.zeros(SW_N, bool)
    for ang in np.arange(lo, hi + 1e-6, step):
        g |= occ_grid(rotated(P, part.joint, axis, float(ang)))
    return dilate(g, grow) if grow else g


def in_grid(g, P, cell=1.0):
    q = np.floor((np.asarray(P) - SW_LO) / cell).astype(np.int64)
    ok = np.all((q >= 0) & (q < np.array(g.shape)), axis=1)
    out = np.zeros(len(q), bool)
    out[ok] = g[q[ok, 0], q[ok, 1], q[ok, 2]]
    return out


# ---------------------------------------------------------------------------------------------------- the king
# Shapes are sculpted on 2 u cells (4 u for cape and fur, 1 u for the face) and MERGED into the fewest, largest
# boxes by emit(); studs, gems, clasps, the buckle, the medallion, the fist and the sword are direct blocks.

WING_W0, WING_K = 37.0, 0.20                  # half width of the cape = WING_W0 + WING_K * (104 - z)
GOLD_BARS = {"gold": (5, 10)}


def build_leg(s):
    """-> (thigh, shin). The thigh carries the knee plate and its half of the skirt; the shin the boot and, hidden
    inside the knee plate while the leg is straight, the drum the knee turns on."""
    side = "L" if s > 0 else "R"
    P, Q = Part("Leg" + side), Part("Shin" + side)
    g = Grid(IDENT, 3, 27, -19, 13, 0, 66, cs=2, sx=s)
    XS, Y, Z = g.XS, g.Y, g.Z
    g.box(5, 19, -7, 7, 24, 54, "steel_d")                    # thigh (under the skirt)
    g.box(5, 19, -7, 7, 32, 34, "steel_dd")
    g.box(5, 21, -9, 7, 24, 32, "steel_l")                    # knee: a wide lighter plate
    # the half of the skirt that swings with this leg, ending in a drum about the hip axis
    sk = g.bm(5, 21, -9, 9, 34, 54)
    drum = (XS > 5) & (XS < 21) & (Y ** 2 + (Z - 54) ** 2 < 9.7 ** 2) & (Z > 54)
    g.fill(sk | drum, "green")
    g.box(5, 23, -11, 11, 34, 38, "gold")                     # hem
    g.paint(sk & (XS < 7) & (Y < -7) & (Z > 38), "gold")      # gold border beside the tabard
    emit(P, g, lim=(8, 16), lims={"gold": (6, 11), "sole": (10, 22)}, seed=20 + s)
    g = Grid(IDENT, 3, 27, -19, 13, 0, 66, cs=2, sx=s)
    XS, Y, Z = g.XS, g.Y, g.Z
    g.fill((XS > 7) & (XS < 17) & (Y ** 2 + (Z - KNEE_Z) ** 2 < 37.0) & (Z > 22), "steel_dd")     # the knee's drum
    g.box(5, 19, -7, 7, 8, 12, "steel_d")
    g.box(5, 19, -7, 7, 12, 24, "steel")                      # shin
    g.box(5, 21, -9, 7, 8, 12, "steel_l")                     # ankle cuff
    g.box(3, 21, -15, 7, 0, 8, "steel")                       # boot
    foot = g.bm(3, 21, -15, 7, 0, 8)
    g.carve(foot & (Y < -11) & (Z > 6))
    g.carve(foot & (Y < -13) & (Z > 4))
    g.paint(foot & (Y < -9), "steel_l")                       # toe cap
    g.paint(foot & (Z < 2), "sole")
    emit(Q, g, lim=(8, 16), lims={"gold": (6, 11), "sole": (10, 22)}, seed=24 + s)
    b = lambda *a, **k: Q.blk(IDENT, *a, sx=s, **k)
    b(2.3, 21.7, -15.8, 7.8, 0.0, 1.5, "sole_d")              # the welt of the sole
    b(6, 9, -16.6, -15.4, 0.2, 2.8, "gold")                   # two gold squares on the toe
    b(15, 18, -16.6, -15.4, 0.2, 2.8, "gold")
    b(17.5, 22.4, -10.4, -4.0, 8.4, 11.8, "gold")             # gold block on the outer corner of the cuff
    b(8.0, 11.0, -10.0, -8.8, 8.8, 11.2, "steel")
    b(7.5, 16.5, -8.2, -6.8, 13.5, 22.5, "steel_l")           # greave plate
    b = lambda *a, **k: P.blk(IDENT, *a, sx=s, **k)
    b(9.0, 15.0, -10.4, -8.8, 25.5, 30.5, "steel_ll")         # knee cap
    b(10.8, 13.2, -11.2, -10.2, 26.8, 29.2, "gold")
    b(17.5, 22.4, -10.4, -4.5, 24.8, 30.2, "gold")            # gold block on the outer corner of the knee
    for (x, z) in ((12.0, 44.0), (15.5, 49.5)) if s < 0 else ((13.0, 46.0),):
        b(x, x + 2.2, -10.0, -8.8, z, z + 2.2, "gold")        # studs on the cloth
    b(11.5, 16.5, 8.8, 9.9, 42.5, 47.5, "gold_d")             # a square on the back
    b(13.0, 15.0, 9.7, 10.4, 44.0, 46.0, "green_d")
    b(20.8, 21.9, -2.5, 2.5, 43.0, 48.0, "gold")              # hollow square on the hip side
    b(21.7, 22.3, -1.2, 1.2, 44.3, 46.7, "green_d")
    return P, Q


ARM_L_OUT = 0.0                               # extra outward angle of the left arm, to make room for the scabbard (place_sheath)


def build_arm(s, extra=0.0):
    """-> (upper arm, forearm with the hand). The elbow is where the forearm's frame is bent."""
    side = "L" if s > 0 else "R"
    P = Part("Arm" + side)
    A = Frame().sub(RY(-s * ((7.0 + extra) if s > 0 else 6.0)), P.joint)
    bend = ELBOW[side]
    Fo = A.sub(RX(-bend), (s * 25, 0, 76))
    JOINTS["Fore" + side] = tuple(float(v) for v in A.w((s * 25, 0, 76)))
    Q = Part("Fore" + side)
    # ---- upper arm: shoulder drum, pauldron, sleeve
    g = Grid(A, 15, 35, -12, 12, 70, 112, cs=2, sx=s)
    XS, Y, Z = g.XS, g.Y, g.Z
    g.box(19, 31, -6, 6, 70, 88, "sleeve")
    g.pbox(19, 31, -6, 6, 70, 76, "sleeve_d")
    g.fill((XS > 19) & (XS < 31) & (Y ** 2 + (Z - 100) ** 2 < 7.0 ** 2), "steel")       # the drum the arm turns on
    g.box(19, 33, -8, 8, 88, 98, "steel_l")                   # pauldron plate
    g.box(19, 31, -8, 8, 84, 88, "steel")                     # the lame under it
    g.pbox(19, 33, -8, 8, 88, 90, "gold")                     # gold edging
    emit(P, g, lim=(8, 16), lims=GOLD_BARS, seed=31 + s)
    a = lambda *q, **k: P.blk(A, *q, sx=s, **k)
    a(29.5, 34.8, -9.8, -3.5, 90.0, 96.2, "gold")             # the gold corner block of the picture
    a(31.0, 33.8, -10.6, -9.6, 91.4, 94.6, "gold_l")
    a(21.0, 27.0, -9.0, -8.0, 84.4, 86.0, "gold_d")           # trim on the lame
    # ---- forearm and hand (bent frame)
    g = Grid(Fo, 14, 36, -13, 13, 38, 82, cs=2, sx=s)
    XS, Y, Z = g.XS, g.Y, g.Z
    g.box(20, 30, -5, 5, 70, 80, "sleeve_d")
    g.box(20, 30, -5, 5, 52, 56, "belt_d")                    # cuff
    if s < 0:
        g.box(18, 32, -7, 7, 54, 72, "steel_l")               # the big vambrace, gold bands at both ends
        vb = g.bm(18, 32, -7, 7, 54, 72)
        g.paint(vb & ((Z > 68) | (Z < 58)), "gold")
    else:
        g.box(18, 32, -7, 7, 56, 70, "bracer")
        g.box(18, 32, -7, 7, 70, 74, "gold")
    Q.bias = len(P._ch)
    emit(Q, g, lim=(8, 16), lims={"gold": (6, 12)}, seed=41 + s)
    f = lambda *q, **k: Q.blk(Fo, *q, sx=s, **k)
    if s < 0:
        f(32.0, 33.2, -2.4, 2.4, 60.5, 65.5, "gold")          # a stud and a boss on the vambrace
        f(22.5, 27.5, -8.2, -7.0, 60.5, 65.5, "steel_ll")
        f(24.0, 26.0, -9.0, -8.0, 62.0, 64.0, "gold")
        f(17.4, 32.6, -7.6, 7.6, 71.2, 72.6, "gold_l")        # lips of the two gold bands
        f(17.4, 32.6, -7.6, 7.6, 53.4, 54.8, "gold_d")
    else:
        f(32.0, 33.0, -3.0, 3.0, 59.5, 66.5, "bracer_l")
        f(32.8, 33.6, -1.2, 1.2, 61.8, 64.2, "gold")
        f(17.5, 32.5, -7.5, 7.5, 55.4, 57.0, "bracer_d")
        f(22.0, 28.0, -8.0, -7.0, 59.0, 67.0, "bracer_l")
    if s > 0:
        # the free fist: one block, four finger bars, a thumb
        f(19.2, 31.0, -3.0, 6.4, 41.6, 52.0, "skin")
        for (z0, z1, nm, dy) in ((42.0, 44.6, "skin_d", 0.0), (44.6, 47.1, "skin", 0.5), (47.1, 49.6, "skin_l", 0.6), (49.6, 52.0, "skin", 0.2)):
            f(19.4, 30.8, -7.4 - dy, -3.0, z0, z1, nm)
        f(18.0, 24.5, -9.0, -6.6, 47.6, 51.2, "skin_l")       # thumb
        f(30.6, 32.2, -6.8, 5.6, 45.5, 52.4, "steel_l")       # plate on the back of the hand
        f(22.0, 31.0, -8.4, -7.0, 49.4, 52.4, "steel")
    else:
        # The sword hand, its own part turning at the wrist, closed round the hilt in a hammer grip: the grip runs
        # through the fist from back to front (across the forearm), the guard sits just beyond the thumb and the
        # forefinger, the blade carries on in line with the grip and the pommel shows behind the little finger.
        # The sword is modelled in this fist and never turns in it: the engine aims the blade with the wrist.
        JOINTS["HandR"] = tuple(float(v) for v in Fo.w((s * 25, -0.5, 52.0)))
        H = Part("HandR")
        h = lambda *q, **k: H.blk(Fo, *q, sx=s, **k)
        GY, GZ = -3.5, 45.8                                   # the grip's axis: along y, through (x 24.8, z GZ); its middle at y GY
        h(21.5, 28.5, -4.6, 3.2, 49.4, 53.6, "skin_d")        # wrist
        h(20.4, 30.2, GY - 5.1, GY + 5.5, 43.6, 51.0, "skin") # the back of the hand and the palm
        for i, (nm, dz) in enumerate((("skin_l", 0.3), ("skin", 0.0), ("skin_d", 0.2), ("skin", 0.6))):
            y0 = GY - 5.3 + i * 2.75                          # four fingers side by side along the grip, curled under it
            h(19.6, 31.0, y0, y0 + 2.75, 40.4 + dz, 46.4, nm)
        h(18.2, 21.6, GY - 6.0, GY + 1.6, 45.6, 49.4, "skin_l")    # the thumb, lying along the grip on the inside
        P.hand_part = H
        P.sword_part = build_sword(Fo, (s * 24.8, GY, GZ))
    return P, Q


def build_sword(Fo, at):
    """The sword as its own part, origin at the middle of the grip, modelled as it sits in his right fist (the fist
    occupies -5.3 .. 5.7 u along the grip: guard in front of it, pommel behind). Its frame: -z down the blade (forward,
    across the forearm), x the width of the blade (along the forearm, so the edges lead when the forearm swings), y
    through the flats. The engine carries it with the hand, and moves it between the fist and the scabbard."""
    hand = Fo.w(at)
    JOINTS["Sword"] = tuple(float(v) for v in hand)
    P = Part("Sword")
    S = Frame(Fo.R @ np.array([[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 0.0, 0.0]]), hand)
    P.frame = S
    tip = -55.0
    # grip, wrapped
    for i, z in enumerate(np.arange(-5.5, 9.5, 5.0)):
        P.blk(S, -1.4, 1.4, -1.4, 1.4, z, z + 5.0, ("belt", "gold_d", "belt")[i], bevel=0.12)
    # pommel: two cubes, one turned 45 degrees, and a cap
    P.blk(S, -3.4, 3.4, -3.4, 3.4, 9.6, 16.4, "gold")
    S2 = S.sub(RZ(45.0), (0, 0, 0))
    P.blk(S2, -3.0, 3.0, -3.0, 3.0, 10.4, 15.6, "gold_l")
    P.blk(S, -2.0, 2.0, -2.0, 2.0, 16.4, 17.6, "gold_d")
    P.blk(S, -1.1, 1.1, -3.9, -3.4, 11.9, 14.1, "gem_w", bevel=0.2)
    P.blk(S, -1.1, 1.1, 3.4, 3.9, 11.9, 14.1, "gem_w", bevel=0.2)
    # cross-guard: bar, flared ends, boss with a stone
    P.blk(S, -8.0, 8.0, -1.7, 1.7, -9.5, -5.5, "gold")
    P.blk(S, -10.4, -6.8, -2.4, 2.4, -10.8, -4.2, "gold_l")
    P.blk(S, 6.8, 10.4, -2.4, 2.4, -10.8, -4.2, "gold_l")
    P.blk(S, -2.8, 2.8, -2.6, 2.6, -10.8, -4.2, "gold_d")
    P.blk(S, -1.3, 1.3, -3.2, 3.2, -8.8, -6.2, "steel_ll", bevel=0.2)
    # blade: five long pieces stepping in to the point, and a one-piece fuller
    top, ln = -10.8, abs(tip) - 10.8
    cuts = (0.0, 0.30, 0.56, 0.77, 0.91, 1.0)
    widths = (5.2, 4.9, 4.2, 3.2, 2.0)
    names = ("blade", "blade_l", "blade", "blade_l", "blade_ll" if "blade_ll" in PI else "blade_l")
    for i in range(5):
        P.blk(S, -widths[i], widths[i], -1.0, 1.0, top - cuts[i + 1] * ln, top - cuts[i] * ln, names[i], bevel=0.035)
    P.blk(S, -1.2, 1.2, -1.55, 1.55, top - 0.62 * ln, top - 0.5, "blade_d", bevel=0.1)
    P.blk(S.sub(RY(45.0), (0, 0, tip + 2.0)), -1.9, 1.9, -0.9, 0.9, tip + 0.1, tip + 3.9, "blade_l", bevel=0.05)        # the point
    for i in (1, 2, 3):                                       # a tooth at each step of the outer edge
        P.blk(S, -widths[i - 1] - 0.1, -widths[i] + 0.2, -0.8, 0.8, top - cuts[i] * ln - 1.6, top - cuts[i] * ln + 0.0, "blade_d", bevel=0.1)
    P.blade_tip = S.w((0, 0, tip))
    P.tip_local = tip
    return P


def archer_face(P, F, z0, front=-11.0, hw=12.0, top=None, skin="skin", shade="skin_d", lip="lip", brow="brow",
                nose=(1.3, 2.6, 0.6), brow_t=1.6, brow_x=(2.6, 9.6), brow_dip=0.0, mouth=3.0, mouth_dz=0.0, glint="gem_w",
                plate=True, eyes_only=False):
    """THE ARCHER'S FACE (troop_archer.py, build_head): the one every figure's face is built on. ONE smooth skin plate
    in front of the skull (a single block, so no seams between blocks read as features); eyes of a 6 x 4 u white with
    a 3 x 4 u dark pupil centred in it (a level gaze, straight ahead) and a glint; a level rectangle brow a little above
    each eye; a small nose with a shadow under it; a short mouth line. Her heights above the foot of her face (100) are
    kept above z0, and her depths in front of her plate (front: -11) in front of this one.
    Each figure's own touches: nose = (half width, height, how far proud), brow_t (how thick), brow_x (its inner and
    outer ends), brow_dip (its inner end coming down toward the nose: a sterner look), mouth (half width).
    eyes_only: just the eyes, brows and glints (a face whose plate, nose and mouth are already the archer's)."""
    b = lambda *a, **k: P.blk(F, *a, **k)
    d = front + 11.0                              # the archer's y + d
    K = z0 - 100.0                                # the archer's z + K
    if plate and not eyes_only:
        b(-hw, hw, front, front + 1.0, z0, top if top is not None else z0 + 22.0, skin, bevel=0.03)
    if not eyes_only:
        b(-mouth, mouth, -11.2 + d, -10.9 + d, 103.6 + K + mouth_dz, 104.6 + K + mouth_dz, lip, bevel=0.1)   # mouth: one thin bar
        nw, nh, npr = nose
        b(-nw, nw, -10.9 - npr + d, -10.9 + d, 106.8 + K, 106.8 + nh + K, skin, bevel=0.12, tint=1.05)      # nose: one block
        b(-nw, nw, -11.2 + d, -10.9 + d, 106.1 + K, 106.8 + K, shade, bevel=0.1)                           # ... the shadow under it
    for sx in (1, -1):
        b(3.0, 9.0, -11.25 + d, -10.9 + d, 110.0 + K, 114.0 + K, "white", sx=sx, bevel=0.05)          # eyes
        b(4.5, 7.5, -11.4 + d, -10.9 + d, 110.0 + K, 114.0 + K, "pupil", sx=sx, bevel=0.05)           # the pupil, centred
        b(brow_x[0], brow_x[1], -11.7 + d, -10.9 + d, 114.6 + K, 114.6 + brow_t + K, brow, sx=sx, bevel=0.08)   # brows
        if brow_dip > 0:
            b(brow_x[0], brow_x[0] + 2.6, -11.75 + d, -10.9 + d, 114.6 - brow_dip + K, 114.6 + K, brow, sx=sx, bevel=0.08)
        b(4.8, 5.7, -11.55 + d, -11.35 + d, 112.6 + K, 113.5 + K, glint, sx=sx, bevel=0.2)            # the glint in each eye


def build_head():
    """King David's head: the ARCHER's face (archer_face: one smooth skin plate, her eyes with their centred pupils
    and glints, a short mouth line) made a man's and a king's: heavy brows that dip toward a bolder, prouder nose, and
    a short, square black beard (References/crops/king_head.png): the jaw and the chin under it, up the cheeks to the
    sideburns, a moustache over the mouth. Hair, skin, crown and its stones as before."""
    P = Part("Head")
    F = Frame().sub(RZ(9.0) @ RY(-2.5), P.joint)
    g = Grid(F, -18, 18, -19, 19, 100, 140, cs=2)
    X, Y, Z = g.X, g.Y, g.Z
    AX = np.abs(X)
    g.box(-12, 12, -11, 11, 106, 130, "skin")
    sk = g.solid()
    g.paint(sk & (AX > 10) & (Y < -1) & (Z < 112), "hair")     # the beard along the jaw, seen from the side ...
    g.paint(sk & (AX > 10) & (Y < -5) & (Z < 120), "hair")     # ... rising to the sideburns
    g.paint(sk & (Z < 108) & (Y < 1), "hair")                  # ... and under the chin
    g.box(-12, 12, -11, -3, 104, 106, "hair")                  # the beard under the jaw
    # hair: back (down to the nape), sides behind the ears, a strip above the ears under the crown, top
    g.box(-14, 14, 11, 13, 104, 132, "hair")
    g.fill((AX > 12) & (AX < 14) & (Y > 3) & (Y < 13) & (Z > 106) & (Z < 132), "hair")
    g.fill((AX > 12) & (AX < 14) & (Y > -11) & (Y < 3) & (Z > 122) & (Z < 132), "hair")
    g.box(-12, 12, -11, 13, 130, 132, "hair")
    hair = g.isn("hair") & ~((Z < 120) & (Y < 3))
    g.grow(hair & (Y > 11) & (g.hash(2, 7) < 0.3), "+y")     # locks standing out, two cells at a time
    g.grow(hair & (X > 12) & (Y > 3) & (Z < 126) & (g.hash(2, 8) < 0.3), "+x")
    g.grow(hair & (X < -12) & (Y > 3) & (Z < 126) & (g.hash(2, 9) < 0.3), "-x")
    g.fill((AX > 12) & (AX < 14) & (Y > -9) & (Y < -3) & (Z > 112) & (Z < 122), "hair_d")    # the sideburns, down into the beard
    g.fill((AX > 12) & (AX < 14) & (Y > -11) & (Y < -1) & (Z > 106) & (Z < 112), "hair")     # the beard over the jaw's corner
    # ears
    g.fill((AX > 12) & (AX < 14) & (Y > -3) & (Y < 3) & (Z > 114) & (Z < 122), "skin_l")
    # the crown takes the place of the hair at its own height
    ringm = (((AX > 12) & (AX < 14)) | ((np.abs(Y) > 11) & (np.abs(Y) < 13))) & (AX < 14) & (np.abs(Y) < 13) & (Z > 128) & (Z < 132)
    g.carve(ringm)
    g.carve((AX > 14) & (Z > 126))
    g.carve((Y > 13) & (Z > 126))
    emit(P, g, lim=(8, 14), lims={"hair": (4, 9), "hair_d": (5, 10), "skin_l": (8, 9)}, shade=0.3, seed=61)
    b = lambda *a, **k: P.blk(F, *a, **k)
    for sx in (1, -1):
        b(13.6, 14.8, -1.6, 1.8, 115.6, 119.4, "skin_d", sx=sx)    # the hollow of the ear
    # ---- THE FACE: the archer's, on a plate in front of the skull (its front at -12), her heights + 6: a bolder,
    # prouder nose, brows thicker and dipping toward it, the mouth a little shorter (it shows in the beard's gap)
    archer_face(P, F, 106.0, front=-12.0, hw=12.0, top=128.0, brow="hair_d", nose=(1.7, 3.4, 1.1), brow_t=2.2,
                brow_x=(2.3, 9.8), brow_dip=0.5, mouth=2.4)
    b(-12.0, 12.0, -13.0, -11.9, 126.0, 128.0, "hair")         # the fringe under the crown
    for sx in (1, -1):
        b(9.0, 12.0, -12.8, -11.9, 123.0, 126.0, "hair_d", sx=sx)                    # the hair coming down at the temples
    # ---- the beard, one layer proud of the face: big plain blocks as in the picture. The chin and jaw, a square
    # goatee hanging below the chin, round the mouth, stepping up the cheeks to the sideburns; a moustache.
    bd = lambda x0, x1, z0, z1, nm="hair", y0=-13.0: b(x0, x1, y0, -11.9, z0, z1, nm, bevel=0.12)
    bd(-12.0, 12.0, 106.0, 109.2)                              # chin and jaw
    bd(-7.0, 7.0, 103.6, 107.0, "hair", -13.6)                 # the goatee, hanging below the chin
    bd(-4.6, 4.6, 103.0, 104.0, "hair_l", -13.4)
    for sx in (1, -1):
        b(3.2, 12.0, -13.0, -11.9, 109.2, 111.0, "hair", sx=sx, bevel=0.12)          # round the mouth
        b(8.0, 12.0, -13.0, -11.9, 111.0, 113.6, "hair_l", sx=sx, bevel=0.12)        # up the cheeks ...
        b(10.0, 12.0, -12.8, -11.9, 113.6, 116.4, "hair", sx=sx, bevel=0.12)         # ... to the sideburns
        b(10.6, 12.0, -12.5, -11.9, 116.4, 119.0, "hair_d", sx=sx, bevel=0.12)
        b(3.6, 5.8, -13.5, -11.9, 109.0, 111.6, "hair_d", sx=sx, bevel=0.12)         # the moustache's ends
    b(-5.8, 5.8, -13.6, -11.9, 110.8, 112.3, "hair_d", bevel=0.12)                  # the moustache
    # ---- the crown, on top of the head: a band of large blocks, points all round, a tall front piece with its stone
    c = Grid(F, -18, 18, -19, 19, 126, 140, cs=2)
    X, Y, Z = c.X, c.Y, c.Z
    AX, AY = np.abs(X), np.abs(Y)
    ring = (((AX > 12) & (AX < 14)) | ((AY > 11) & (AY < 13))) & (AX < 14) & (AY < 13)
    c.fill(ring & (Z > 128) & (Z < 132), "gold")
    along = np.where(AX > 12, c.iy, c.ix)
    c.fill(ring & (Z > 132) & (Z < 136) & ((along % 4) < 2), "gold_l")                   # points
    c.fill(ring & (AX > 12) & (AY > 11) & (Z > 132) & (Z < 136), "gold")                 # corner points
    c.fill((Y < -13) & (Y > -15) & (AX < 4) & (Z > 128) & (Z < 136), "gold")             # tall front piece
    c.fill((Y < -11) & (Y > -13) & (AX < 4) & (Z > 132) & (Z < 136), "gold_d")
    emit(P, c, lim=((4, 7), (4, 7), (4, 8)), shade=0.6, proud_p=0.35, proud=(0.1, 0.3), seed=62)
    b(-2.0, 2.0, -15.0, -13.0, 136.0, 138.0, "gold_l")        # the spike of the front piece
    for sx in (1, -1):
        for sy in (1, -1):
            b(12.2, 13.8, min(11.2 * sy, 12.8 * sy), max(11.2 * sy, 12.8 * sy), 136.0, 137.0, "gold_l", sx=sx)     # tips of the corner points
    b(-2.6, 2.6, -16.2, -15.0, 128.8, 135.2, "gold_l")        # the setting and the stone
    b(-1.6, 1.6, -17.0, -16.0, 129.8, 134.2, "gem")
    b(-0.6, 0.6, -17.5, -16.8, 132.2, 133.4, "gem_w", bevel=0.2)
    for sx in (1, -1):
        b(13.8, 14.8, -1.6, 1.6, 128.8, 131.4, "white", sx=sx, bevel=0.15)              # stones round the band
        b(7.0, 9.6, -13.9, -13.0, 129.0, 131.2, "white", sx=sx, bevel=0.15)
    b(-1.6, 1.6, 13.0, 14.0, 128.8, 131.4, "gem", bevel=0.15)
    return P


def cape_piece(x, L):
    """Which part of the cape a point belongs to: x (u), L (u below the collar) -> (key, column, row); row -1 = yoke."""
    W = WING_W0 + WING_K * max(L, 0.0)
    col = int(np.searchsorted(CAPE_U, x / W))
    row = int(np.searchsorted(CAPE_L[col % 2], L, side="right")) - 1
    return ("Cape" if row < 0 else "Cape%d%d" % (col, row)), col, row


def build_cape():
    """-> {key: part}: the yoke under the collar ("Cape") and the hanging panels "Cape<col><row>", each hinged at the
    middle of its top edge to the panel above it."""
    cs = 4.0
    g = Grid(IDENT, -68, 68, -12, 52, 4, 108, cs=cs)
    nx, ny, nz = g.n
    xs = (np.arange(nx) + 0.5) * cs - 68
    zs = (np.arange(nz) + 0.5) * cs + 4
    Xc, Zc = np.meshgrid(xs, zs, indexing="ij")
    L = 104 - Zc
    W = WING_W0 + WING_K * L
    u = Xc / W
    amp = 0.3 + 3.8 * np.clip(L / 95, 0, 1)
    side = np.clip((np.abs(u) - 0.7) / 0.3, 0, 1)
    yb = 17 + 0.17 * L + amp * np.cos(u * np.pi * 5.0) * (1 - side) - 8.0 * side ** 2
    j0 = np.floor((yb + 12) / cs).astype(int)
    hemz = 8 + 4 * (hash3(np.arange(nx) // 2, np.zeros(nx, int), np.zeros(nx, int), 5) > 0.6)
    inside = (np.abs(Xc) < W) & (L >= 0) & (Zc > hemz[:, None]) & (Zc < 104 - np.maximum(0, np.abs(Xc) - 24) * 0.55)
    big = 10 ** 6
    jn = np.where(inside, j0, -big)
    nbmax = np.maximum.reduce([shift(jn, 0, 1, -big), shift(jn, 0, -1, -big), shift(jn, 1, 1, -big), shift(jn, 1, -1, -big)])
    j1 = np.maximum(j0, np.minimum(nbmax, j0 + 2))
    back = inside[:, None, :] & (g.iy >= j0[:, None, :]) & (g.iy <= j1[:, None, :])
    # wings: the sides that come forward past the arms
    Lz = 104 - zs
    Wz = WING_W0 + WING_K * Lz
    iw = np.floor((Wz - 0.5 + 68) / cs).astype(int)           # the cell the edge falls in, on +x
    yf = 10 - 0.125 * Lz
    wing = np.zeros(g.n, bool)
    for k in range(nz):
        if Lz[k] < 13 or zs[k] < 8:
            continue
        i_lo = iw[k]
        i_hi = max(i_lo, iw[k - 1] if k > 0 and zs[k - 1] > 8 else i_lo)
        for (a, b) in ((i_lo, i_hi), (nx - 1 - i_hi, nx - 1 - i_lo)):
            for i in range(a, b + 1):
                jb = j1[i, k] if inside[i, k] else 0
                wing[i, :, k] = (g.Y[i, :, k] > yf[k]) & (np.arange(ny) <= max(jb, j0[i, k]))
    solid = back | wing
    g.fill(solid, "green")
    X, Y, Z = g.X, g.Y, g.Z
    Lc = 104 - Z
    Wc = WING_W0 + WING_K * Lc
    ridge = np.cos(X / Wc * np.pi * 5.0)
    g.paint(solid & (ridge > 0.4) & (np.abs(X) < Wc * 0.75), "green_d")        # the folds: valleys dark, ridges light
    g.paint(solid & (ridge < -0.6) & (np.abs(X) < Wc * 0.75), "green_l")
    # hem: a band of gold blocks, a broken gold-and-cream row above it, a few strays hanging low
    hz = hemz[:, None, None]
    row0 = solid & (Z < hz + 4)
    row1 = solid & (Z > hz + 4) & (Z < hz + 8)
    pair = hash3(g.ix // 2, g.iy * 0, g.iz * 0, 8)
    g.paint(row0, "gold")
    g.paint(row1 & (pair < 0.4), "gold_d")
    g.paint(row1 & (pair > 0.78), "cream")
    g.grow(row0 & (hash3(g.ix // 2, g.iy * 0, g.iz * 0, 11) < 0.25), "-z")
    lead = wing & ~shift(wing, 1, 1, False) & (Y < 14)        # gold blocks at intervals up the leading edges
    g.paint(lead & ((g.iz % 7) == 3) & (Z > hz + 8), "gold")
    # cut into the yoke and the panels
    Ucell = X / Wc
    colc = np.searchsorted(np.array(CAPE_U), Ucell)
    starts = np.array(CAPE_L)[colc % 2]                       # (..., rows)
    rowc = (Lc[..., None] >= starts).sum(axis=-1) - 1
    full = g.p.copy()
    out = {}
    keys = ["Cape"] + ["Cape%d%d" % (c, r) for c in range(CAPE_COLS) for r in range(CAPE_ROWS)]
    for idx, key in enumerate(keys):
        if key == "Cape":
            m = (rowc < 0) & (full > 0)
        else:
            c, r = int(key[4]), int(key[5])
            m = (colc == c) & (rowc == r) & (full > 0)
            top = m & (Lc < CAPE_L[c % 2][r] + cs)            # its top row of cells: the hinge is at their middle
            JOINTS[key] = (float(X[top].mean()), float(Y[top].mean()), 104.0 - CAPE_L[c % 2][r])
            PARENT[key] = "Cape" if r == 0 else "Cape%d%d" % (c, r - 1)
        g.p = np.where(m, full, 0).astype(np.uint8)
        Pk = Part(key)
        emit(Pk, g, lim=((4, 4), (4, 8), (12, 30)), pref="z", lims={"gold": ((8, 12), (4, 8), (4, 4)), "gold_d": ((8, 12), (4, 8), (4, 4)),
                                                                    "cream": ((4, 8), (4, 8), (4, 4))},
             shade=0.6, proud_p=0.45, proud=(0.15, 0.6), seed=71 + idx, cjit=0.04)
        out[key] = Pk
    g.p = full
    ORDER[ORDER.index("Cape") + 1:ORDER.index("Cape") + 1] = keys[1:]
    # hollow gold squares, the clasps of the picture: thin plates on the wings and across the back
    surf_x = {}
    for k in range(nz):
        col = np.nonzero(solid[:, :, k].any(axis=1))[0]
        if len(col):
            surf_x[k] = (col.max() + 1) * cs - 68

    def square(put, size=7.0):
        h = size / 2
        for (a0, a1, b0, b1, nm) in ((-h, h, -h, -h + 1.8, "gold"), (-h, h, h - 1.8, h, "gold_l"), (-h, -h + 1.8, -h + 1.8, h - 1.8, "gold"),
                                     (h - 1.8, h, -h + 1.8, h - 1.8, "gold_d")):
            put(a0, a1, b0, b1, nm)

    for sx_ in (1, -1):
        for (yc, zc) in ((11.0, 84.0), (15.0, 56.0), (18.0, 30.0)):
            xo = surf_x.get(int((zc - 4) // cs), 50.0) + 0.7
            Pk = out[cape_piece(sx_ * xo, 104.0 - zc)[0]]
            square(lambda a0, a1, b0, b1, nm: Pk.blk(IDENT, xo - 0.9, xo + 0.9, yc + a0, yc + a1, zc + b0, zc + b1, nm, sx=sx_, bevel=0.2))
    for xc in (-30.0, 0.0, 30.0):
        zc = 36.0
        i, k = int((xc + 68) // cs), int((zc - 4) // cs)
        yo = (j1[i, k] + 1) * cs - 12 + 0.7
        Pk = out[cape_piece(xc, 104.0 - zc)[0]]
        square(lambda a0, a1, b0, b1, nm: Pk.blk(IDENT, xc + a0, xc + a1, yo - 0.9, yo + 0.9, zc + b0, zc + b1, nm, bevel=0.2), 8.0)
    return out


def torso_tiers(Z):
    """Half width and half depth of the torso at height Z (2 u steps): waist, two lames, chest, shoulders."""
    hw = np.where(Z < 80, 14, np.where(Z < 84, 16, np.where(Z < 100, 18, 16)))
    hd = np.where(Z < 84, 9, np.where(Z < 100, 11, 9))
    return hw, hd


def build_body(arms, head, cape):
    P = Part("Body")
    blk = lambda *a, **k: P.blk(IDENT, *a, **k)
    # ---- pelvis: the top of the skirt, the belt
    g = Grid(IDENT, -26, 26, -19, 15, 30, 78, cs=2)
    X, Y, Z = g.X, g.Y, g.Z
    AX = np.abs(X)
    g.fill((AX < np.where(Z < 56, 22, 20)) & (np.abs(Y) < 11) & (Z > 52) & (Z < 66), "green")
    g.box(-4, 4, -7, 7, 38, 54, "green_dd")                   # between the legs
    g.box(-16, 16, -11, 11, 66, 74, "belt")
    emit(P, g, lim=(10, 18), lims={"belt": ((10, 18), (8, 12), (4, 4))}, seed=81)
    for sx in (1, -1):
        blk(5.0, 7.0, -12.1, -11.0, 52.0, 66.0, "gold", sx=sx)               # gold borders beside the tabard
        blk(19.6, 20.9, -2.5, 2.5, 57.0, 62.0, "gold", sx=sx)                # hip squares
        blk(20.7, 21.3, -1.2, 1.2, 58.3, 60.7, "green_d", sx=sx)
        blk(10.5, 12.7, -12.2, -11.0, 69.0, 71.2, "gold", sx=sx, bevel=0.15) # belt studs
        blk(-1.2, 1.2, 11.0, 12.2, 68.8, 71.2, "gold_d")
    # the strap down his left hip, with gold studs
    for i in range(3):
        x = 9.5 + i * 4.0
        z = 64.5 - i * 3.4
        blk(x, x + 4.1, -12.3, -11.0, z - 4.4, z, ("belt_l", "belt", "belt_l")[i])
        blk(x + 1.1, x + 3.0, -12.9, -12.2, z - 3.2, z - 1.3, "gold", bevel=0.15)
    blk(-14.0, -11.0, -12.0, -11.0, 56.0, 59.0, "gold")
    # tabard: one full-length strip per pleat
    for i in range(5):
        x0 = -5.0 + 2.0 * i
        pr = 1 - i % 2
        blk(x0, x0 + 2.0, -13.0 - 1.1 * pr, -11.0, (33.0, 32.0, 34.0, 32.0, 33.0)[i], 66.0, ("cream_l", "cream_d", "cream", "cream_d", "cream_l")[i],
            bevel=0.1)
    # buckle: plates on plates
    blk(-5.6, 5.6, -14.8, -11.2, 64.3, 75.7, "gold")
    blk(-5.6, -3.4, -15.8, -14.6, 64.3, 75.7, "gold_l")
    blk(3.4, 5.6, -15.8, -14.6, 64.3, 75.7, "gold_l")
    blk(-3.4, 3.4, -15.8, -14.6, 73.5, 75.7, "gold_l")
    blk(-3.4, 3.4, -15.8, -14.6, 64.3, 66.5, "gold_l")
    blk(-3.4, 3.4, -15.2, -14.6, 66.5, 73.5, "gold_d")
    blk(-1.8, 1.8, -16.6, -15.0, 68.2, 71.8, "steel_ll", bevel=0.14)
    blk(-7.2, -5.6, -13.4, -11.2, 67.5, 72.5, "gold_d")
    blk(5.6, 7.2, -13.4, -11.2, 67.5, 72.5, "gold_d")

    # ---- torso (tilted a little: contrapposto): its own part, turning on the pelvis at the waist
    B = P
    P = Part("Chest")
    P.bias = len(B._ch)
    FT = Frame().sub(RY(1.0), (0, 0, 73))
    P.torso = FT
    tb = lambda *a, **k: P.blk(FT, *a, **k)
    g = Grid(FT, -24, 24, -19, 15, 72, 112, cs=2)
    X, Y, Z = g.X, g.Y, g.Z
    AX = np.abs(X)
    hw, hd = torso_tiers(Z)
    body = (AX < hw) & (np.abs(Y) < hd) & (Z > 72) & (Z < 104)
    g.fill(body, "steel_d")
    g.paint(body & (Z < 76), "belt_d")
    g.paint(body & (Z >= 76) & (Z < 80), "steel_dd")          # two lames
    g.paint(body & (Z >= 80) & (Z < 84), "steel")
    g.fill((AX < 12) & (Y > -13) & (Y < -11) & (Z > 84) & (Z < 100), "steel_l")          # breastplate, proud of the chest
    g.paint(body & (Z > 100), "green")                        # the cloak over the shoulders, under the fur
    g.paint(body & (Z > 96) & (AX > 12) & (Y < -7), "green")
    g.fill((X ** 2 + Y ** 2 < 6.2 ** 2) & (Z > 104) & (Z < 112), "skin_d")                # neck
    emit(P, g, lim=((9, 16), (8, 12), (6, 10)), lims={"steel_l": ((8, 12), (2, 2), (8, 16)), "skin_d": (12, 12)}, seed=82)
    # the sun medallion: plates on plates, petals and rays turned about its centre, a pale stone set as a diamond
    zc = 93.0

    def turned(deg):
        return FT.sub(RY(deg), (0, 0, zc))

    for deg, nm in ((0.0, "gold_d"), (45.0, "gold_d")):
        P.blk(turned(deg), -6.2, 6.2, -14.3, -13.0, zc - 6.2, zc + 6.2, nm)
    for kk in range(8):
        P.blk(turned(kk * 45.0), -1.7, 1.7, -15.2, -13.8, zc + 5.0, zc + 8.6, "gold" if kk % 2 else "gold_l")
        if kk in (0, 1, 7):
            continue
        P.blk(turned(kk * 45.0 + 22.5), -0.8, 0.8, -14.2, -13.0, zc + 9.4, zc + 11.0, "gold_l", bevel=0.15)
    for deg, nm in ((0.0, "gold"), (45.0, "gold_l")):
        P.blk(turned(deg), -4.1, 4.1, -15.5, -14.2, zc - 4.1, zc + 4.1, nm)
    P.blk(turned(0.0), -2.9, 2.9, -16.0, -15.3, zc - 2.9, zc + 2.9, "gold_d")
    P.blk(turned(45.0), -1.9, 1.9, -16.9, -15.8, zc - 1.9, zc + 1.9, "gem_w", bevel=0.12)
    # pendant: a four-pointed star on the lames below the breastplate
    tb(-1.0, 1.0, -10.2, -9.0, 76.5, 84.0, "gold")
    tb(-3.6, 3.6, -10.2, -9.0, 80.2, 82.2, "gold")
    tb(-2.0, 2.0, -10.8, -9.6, 79.2, 83.2, "gold_l")
    tb(-1.0, 1.0, -11.4, -10.4, 80.2, 82.2, "gem_w", bevel=0.2)
    for sx in (1, -1):
        # gold bars from the medallion to the shoulders, and the clasps of the cloak
        tb(7.6, 12.0, -14.2, -13.0, 94.0, 97.0, "gold", sx=sx)
        tb(12.0, 17.6, -12.3, -11.0, 94.0, 97.0, "gold", sx=sx)
        tb(12.6, 16.2, -12.3, -11.0, 97.6, 101.2, "gold_l", sx=sx)
        tb(13.6, 15.2, -12.8, -12.2, 98.6, 100.2, "green_d", sx=sx, bevel=0.15)
        tb(12.0, 18.2, -12.0, -11.0, 84.0, 85.6, "gold_d", sx=sx)             # edging under the chest plate
        tb(18.0, 19.0, -9.0, 9.0, 84.0, 85.6, "gold_d", sx=sx)
    tb(-12.2, 12.2, -14.0, -13.0, 84.0, 85.4, "gold")         # edging under the breastplate
    for a in range(4):                                        # gorget: four bars round the neck
        Fg = FT.sub(RZ(a * 90.0), (0, 0, 0))
        P.blk(Fg, -7.6, 7.6, -8.6, -6.2, 104.0, 106.4, "gold" if a % 2 else "gold_l")

    # ---- the fur collar: lumps of 4 u cubes, some merged into 8 u ones, with loose tufts turned at random
    keep_out = np.zeros(SW_N, bool)
    for a in arms:
        keep_out |= swept(a, "x", -48, 48, step=2.0, grow=1)
    keep_out |= swept(head, "z", -22, 22, step=2.0, grow=1)
    cs = 4.0
    f = Grid(IDENT, -52, 52, -28, 32, 82, 118, cs=cs)
    X, Y, Z = f.X, f.Y, f.Z
    AX = np.abs(X)
    blobs = [(27.0, 1.0, 102.5, 16.5, 17.5, 11.5), (0.0, 17.0, 104.0, 30.0, 10.5, 9.5), (18.0, -11.0, 100.5, 8.5, 7.0, 7.5),
             (39.0, 4.0, 95.0, 7.0, 15.0, 11.5), (27.0, -15.0, 99.5, 13.5, 7.5, 8.5)]
    d = np.full(f.n, 9.0, np.float32)
    for (cx, cy, cz, rx, ry, rz) in blobs:
        d = np.minimum(d, ((AX - cx) / rx) ** 2 + ((Y - cy) / ry) ** 2 + ((Z - cz) / rz) ** 2)
    d = d + (f.hash(1, 41) - 0.5) * 0.35
    fur = d < 1.0
    hw, hd = torso_tiers(Z)
    fur &= ~((AX < hw - 2) & (np.abs(Y) < hd - 2) & (Z < 103))
    sub = np.stack(np.meshgrid([-1.6, 0, 1.6], [-1.6, 0, 1.6], [-1.6, 0, 1.6], indexing="ij"), axis=-1).reshape(-1, 3)
    cen = np.stack([X, Y, Z], axis=-1).reshape(-1, 3)
    blocked = np.zeros(len(cen), bool)
    for o in sub:
        blocked |= in_grid(keep_out, cen + o)
    fur &= ~blocked.reshape(f.n)
    cur = fur & (AX < 6) & (Y > 8)                            # no crumbs: keep what hangs together with the back of the neck
    while True:
        nxt = dilate(cur) & fur
        if nxt.sum() == cur.sum():
            break
        cur = nxt
    fur = cur
    f.fill(fur, "fur")
    nb = emit(P, f, lim=(4, 7), shade=0.7, proud_p=0.5, proud=(0.2, 0.8), seed=83, cjit=0.03, tilt=9.0, core_rgb=PRGB[PI["fur_d"]] * 0.85)
    rng = np.random.default_rng(7)
    tufts = 0
    for (i, j, k) in np.argwhere(fur & f.surface()):
        if rng.random() > 0.5:
            continue
        nrm = np.zeros(3)
        for ax, (di, dj, dk) in enumerate(((1, 0, 0), (0, 1, 0), (0, 0, 1))):
            for sg in (1, -1):
                q = (i + sg * di, j + sg * dj, k + sg * dk)
                if not (0 <= q[0] < f.n[0] and 0 <= q[1] < f.n[1] and 0 <= q[2] < f.n[2]) or not fur[q]:
                    nrm[ax] += sg
        ln = np.linalg.norm(nrm)
        if ln == 0 or (nrm[2] < 0 and abs(nrm[0]) + abs(nrm[1]) == 0):
            continue
        nrm /= ln
        size = rng.uniform(3.0, 5.0)
        c = np.array([X[i, j, k], Y[i, j, k], Z[i, j, k]]) + nrm * rng.uniform(0.8, 1.8) + rng.uniform(-1.0, 1.0, 3)
        if abs(c[0]) < 10.5 and c[1] < -9 and c[2] < 103:
            continue                                         # leave the medallion in view
        Rm = RZ(rng.uniform(-35, 35)) @ RY(rng.uniform(-28, 28)) @ RX(rng.uniform(-28, 28))
        pts = c + (sub / 1.6 * size * 0.62) @ Rm.T
        if in_grid(keep_out, pts).any():
            continue
        name = ("fur", "fur_l", "fur_l", "fur_d")[int(rng.integers(0, 4))]
        P.add(Frame(Rm, c), [-size / 2] * 3, [size / 2] * 3, PI[name], 0.06 * size, cull=False,
              rgb=np.clip(PRGB[PI[name]] * rng.uniform(0.96, 1.04), 0, 1))
        tufts += 1
    print("fur: %d blocks, %d tufts" % (nb, tufts))
    return B, P


def frame_along(a, b, up=(0.0, 0.0, 1.0)):
    """A frame at a whose local -z points at b (local x across, local y through)."""
    a, b = np.asarray(a, np.float64), np.asarray(b, np.float64)
    zax = a - b
    zax /= np.linalg.norm(zax)
    xax = np.cross(np.asarray(up, np.float64), zax)
    if np.linalg.norm(xax) < 1e-6:
        xax = np.array([1.0, 0.0, 0.0])
    xax /= np.linalg.norm(xax)
    yax = np.cross(zax, xax)
    return Frame(np.stack([xax, yax, zax], axis=1), a)


def rot_between(a, b):
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    v = np.cross(a, b)
    c = float(np.dot(a, b))
    if np.linalg.norm(v) < 1e-9:
        return np.eye(3) if c > 0 else RX(180.0)
    K_ = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + K_ + K_ @ K_ * (1.0 / (1.0 + c))


def rot_axis(axis, ang):
    axis = axis / np.linalg.norm(axis)
    K_ = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return np.eye(3) + math.sin(ang) * K_ + (1 - math.cos(ang)) * (K_ @ K_)


SHEATH_HALF = (6.6, 2.5)                      # half width and half thickness of the scabbard (u)


def sheath_pose(S, mouth, D):
    """For a scabbard whose mouth is at `mouth` and which points along D: the turn Delta that takes the sword from the
    fist into it (about the grip), the sheathed sword's frame and grip position. The blade's flats face out (+-x)."""
    d_hand = S.R @ np.array([0.0, 0.0, -1.0])
    Q = rot_between(d_hand, D)
    w = Q @ S.R @ np.array([1.0, 0.0, 0.0])
    r = math.atan2(-w[0], np.cross(D, w)[0])
    if math.cos(r) < 0:
        r += math.pi
    Delta = rot_axis(D, r) @ Q
    R_sh = Delta @ S.R
    G = np.asarray(mouth, np.float64) - 10.8 * D            # the guard's lower face sits on the mouth
    return Delta, Frame(R_sh, G)


def sheath_points(F, tip, step=1.2):
    hx, hy = SHEATH_HALF
    xs = np.arange(-hx, hx + 1e-6, step)
    ys = np.arange(-hy, hy + 1e-6, step)
    zs = np.arange(tip - 1.5, -10.8 + 1e-6, step)
    L = np.stack(np.meshgrid(xs, ys, zs, indexing="ij"), axis=-1).reshape(-1, 3)
    return F.w(L)


# The hang the search found and the user approved (mouth u, degrees from vertical, degrees out, left arm out). The
# search is touchy (a block standing 0.2 u prouder can tip it), so it only runs again with --search-sheath.
SHEATH_PIN = ((24.0, -16.0, 60.0), 35.0, 16.0, 9.0)


def place_sheath(parts):
    """Search for where the scabbard hangs AT HIS LEFT HIP: mouth at the side of the belt, against the skirt, hilt
    forward and up, tip down and back past the outside of the thigh. The left arm hangs over the hip, so the search
    may also turn that arm out a few degrees at the shoulder to make room. Hard: clear of the left leg through its
    whole swing and of the ground. Soft: clear of the left arm through a walking swing, of the cape, not sunk into the
    skirt, close to the classic hang, and as little arm change as possible. Returns (mouth, direction, arm angle)."""
    if SHEATH_PIN and "--search-sheath" not in ARGS:
        mouth, th, ph, e = SHEATH_PIN
        t, f = math.radians(th), math.radians(ph)
        D = np.array([math.sin(f), math.sin(t) * math.cos(f), -math.cos(t) * math.cos(f)])
        print("SHEATH pinned: mouth (%.1f, %.1f, %.1f) u, %.0f deg from vertical, %.0f out, left arm out +%.0f deg" % (mouth + (th, ph, e)))
        return np.array(mouth, np.float64), D / np.linalg.norm(D), e
    sw = parts["Sword"]
    S, tip = sw.frame, sw.tip_local
    Psw = part_points(sw, step=1.4, cores=False)[::2]
    hand = np.array(JOINTS["Sword"], np.float64)
    whole = wholes(parts)
    leg = swept(whole["LegL"], "x", -46, 46, step=4.0, grow=1)
    cape = swept(whole["Cape"], "x", 0, 32, step=4.0, grow=0)
    body = occ_grid(part_points(whole["Body"], step=0.8, cores=False))
    arm_pts = part_points(whole["ArmL"], step=0.9, cores=False)
    sj = np.array(JOINTS["ArmL"], np.float64)
    arms = {}
    for e in (0.0, 3.0, 6.0, 9.0, 12.0):
        P0 = (arm_pts - sj) @ RY(-e).T + sj                    # the arm turned out a further e degrees
        g = np.zeros(SW_N, bool)
        for ang in np.arange(-30, 31, 5.0):
            g |= occ_grid(rotated(P0, sj, "x", float(ang)))
        arms[e] = dilate(g, 1)
    best = None
    for th in np.arange(20, 61, 5.0):
        for ph in (0.0, 8.0, 16.0, 24.0):
            t, f = math.radians(th), math.radians(ph)
            D = np.array([math.sin(f), math.sin(t) * math.cos(f), -math.cos(t) * math.cos(f)])
            D /= np.linalg.norm(D)
            for mz in np.arange(50, 67, 2.0):
                for mx in np.arange(14, 31, 2.0):
                    for my in np.arange(-16, 3, 3.0):
                        Delta, F = sheath_pose(S, (mx, my, mz), D)
                        pts = np.concatenate([sheath_points(F, tip, 2.0), F.t + (Psw - hand) @ Delta.T])
                        if pts[:, 2].min() < 2.0:
                            continue
                        n_leg = int(in_grid(leg, pts).sum())
                        if n_leg > 2:
                            continue
                        n_body = int(in_grid(body, pts).sum())
                        n_cape = int(in_grid(cape, pts).sum())
                        base = (3.0 * n_body + 2.0 * n_cape + 0.5 * (mz - 60) ** 2 + 0.6 * (mx - 20) ** 2 + 0.2 * (my + 8) ** 2
                                + 0.05 * (th - 35) ** 2 + 0.04 * ph ** 2 + 60 * n_leg)
                        if best is not None and base >= best[0]:
                            continue
                        for e, ga in arms.items():
                            n_arm = int(in_grid(ga, pts).sum())
                            cost = base + 25.0 * n_arm + 6.0 * e * e
                            if best is None or cost < best[0]:
                                best = (cost, (mx, my, mz), D, th, ph, e, n_leg, n_arm, n_cape, n_body)
    if best is None:
        raise RuntimeError("no place for the scabbard at the hip")
    cost, mouth, D, th, ph, e, nl, na, nc, nb = best
    print("SHEATH at the hip: mouth (%.1f, %.1f, %.1f) u, %.0f deg from vertical, %.0f out, left arm out +%.0f deg | touches: "
          "leg %d, arm %d (walking swing), cape %d, skirt %d" % (mouth[0], mouth[1], mouth[2], th, ph, e, nl, na, nc, nb))
    return np.array(mouth, np.float64), D, e


def build_sheath(parts):
    """The scabbard at his left hip and the strap that hangs it from the belt."""
    sw = parts["Sword"]
    mouth, D, e = place_sheath(parts)
    if e > 0:                                                  # turn the left arm out to make room
        global ARM_L_OUT
        ARM_L_OUT = e
        parts["ArmL"], parts["ForeL"] = [q.finalize() for q in build_arm(1, extra=e)]
    Delta, F = sheath_pose(sw.frame, mouth, D)
    P = Part("Sheath")
    tip = sw.tip_local
    hx, hy = SHEATH_HALF
    b = lambda *q, **k: P.blk(F, *q, **k)
    z_top, z_end = -10.8, tip - 1.5
    ln = z_top - z_end
    # the leather body: three long planks of slightly different browns, a raised spine down the middle
    b(-hx, -hx * 0.33, -hy, hy, z_end + 3.5, z_top - 4.0, "belt_d")
    b(-hx * 0.33, hx * 0.33, -hy - 0.4, hy + 0.4, z_end + 3.5, z_top - 4.0, "belt")
    b(hx * 0.33, hx, -hy, hy, z_end + 3.5, z_top - 4.0, "belt_d", tint=0.92)
    # gold throat at the mouth, a locket band, the chape at the tip with its point
    b(-hx - 0.6, hx + 0.6, -hy - 0.6, hy + 0.6, z_top - 4.6, z_top, "gold")
    b(-hx - 0.2, hx + 0.2, -hy - 0.8, hy + 0.8, z_top - 4.6, z_top - 3.4, "gold_d")
    b(-1.4, 1.4, -hy - 1.2, -hy - 0.6, z_top - 3.6, z_top - 1.0, "gem", bevel=0.2)
    zl = z_top - 0.42 * ln
    b(-hx - 0.4, hx + 0.4, -hy - 0.4, hy + 0.4, zl - 2.4, zl, "gold_d")
    b(-hx + 0.4, hx - 0.4, -hy - 0.5, hy + 0.5, z_end + 0.8, z_end + 4.2, "gold")
    b(-hx * 0.55, hx * 0.55, -hy - 0.2, hy + 0.2, z_end - 1.2, z_end + 1.0, "gold_d")
    b(-1.6, 1.6, -1.6, 1.6, z_end - 2.8, z_end - 0.8, "gold_l")
    # the strap from the side of the belt down to the throat, with a gold buckle where it leaves the belt
    anchor = np.array([15.5, min(-2.0, mouth[1] + 4.0), 68.0])
    c = F.w((0.0, 0.0, z_top - 3.0))
    st = frame_along(anchor, c, up=(1.0, 0.0, 0.0))
    L = float(np.linalg.norm(c - anchor))
    P.blk(st, -1.4, 1.4, -0.7, 0.7, -L, 0.0, "belt_d", bevel=0.15)
    P.blk(Frame(np.eye(3), anchor), -2.0, 2.0, -2.0, 2.0, -2.2, 2.2, "gold", bevel=0.18)
    # the frog: a leather loop round the throat with a gold ring
    b(-hx - 1.2, hx + 1.2, -hy - 1.2, hy + 1.2, z_top - 9.0, z_top - 6.0, "belt_dd")
    ring = F.w((0.0, -hy - 1.6, z_top - 7.5))
    P.blk(Frame(np.eye(3), ring), -1.6, 1.6, -1.6, 1.6, -1.6, 1.6, "gold", bevel=0.18)
    P.sword_delta = Delta
    P.sword_frame = F
    P.mouth, P.dir = mouth, D
    return P


def sheathed_points(parts, P):
    """Sword points (world u, in-hand pose) moved into the scabbard."""
    hand = np.array(JOINTS["Sword"], np.float64)
    sh = parts["Sheath"]
    return sh.sword_frame.t + (P - hand) @ sh.sword_delta.T


WHOLE = ["Body", "Head", "ArmL", "ArmR", "LegL", "LegR", "Cape", "Sword", "Sheath"]


def wholes(parts):
    """The limbs as the single rigid pieces they are while every elbow, knee, wrist and cape hinge is at rest."""
    w = {"Body": Combo(parts["Body"], parts["Chest"]), "Head": parts["Head"], "ArmL": Combo(parts["ArmL"], parts["ForeL"]),
         "ArmR": Combo(parts["ArmR"], parts["ForeR"], parts["HandR"]), "LegL": Combo(parts["LegL"], parts["ShinL"]),
         "LegR": Combo(parts["LegR"], parts["ShinR"]), "Cape": Combo(*[parts[k] for k in ORDER if k.startswith("Cape")]),
         "Sword": parts["Sword"]}
    if "Sheath" in parts:
        w["Sheath"] = parts["Sheath"]
    return w


def build_king():
    t0 = time.time()
    parts = {}
    for s_, side in ((1, "L"), (-1, "R")):
        parts["Leg" + side], parts["Shin" + side] = build_leg(s_)
        parts["Arm" + side], parts["Fore" + side] = build_arm(s_)
    parts["HandR"] = parts["ArmR"].hand_part
    parts["Head"] = build_head()
    parts.update(build_cape())
    for q in parts.values():
        q.finalize()
    parts["Sword"] = parts["ArmR"].sword_part.finalize()
    parts["Body"], parts["Chest"] = [q.finalize() for q in build_body(
        [Combo(parts["ArmL"], parts["ForeL"]), Combo(parts["ArmR"], parts["ForeR"], parts["HandR"])], parts["Head"], None)]
    parts["Sheath"] = build_sheath(parts).finalize()
    print("sculpted in %.1f s" % (time.time() - t0))
    return parts


# ---------------------------------------------------------------------------------------------------- checks

def pivot(key):
    return [round(c * U, 5) for c in JOINTS[key]]


def check_pose(parts, pts, label, sheathed=False, **ang):
    axes = dict(LegL=("x", ang.get("legl", 0)), LegR=("x", ang.get("legr", 0)), ArmL=("x", ang.get("arml", 0)),
                ArmR=("x", ang.get("armr", 0)), Cape=("x", ang.get("cape", 0)), Head=("z", ang.get("head", 0)), Body=("x", 0),
                Sheath=("x", 0))
    posed = {}
    for k in WHOLE:
        if k == "Sword":
            posed[k] = pts["SwordSheathed"] if sheathed else rotated(pts[k], parts["ArmR"].joint, "x", axes["ArmR"][1])
        else:
            posed[k] = rotated(pts[k], parts[k].joint, axes[k][0], axes[k][1])
    occ = {k: occ_grid(posed[k], 0.5) for k in WHOLE}
    bad = []
    for i, a in enumerate(WHOLE):
        for b in WHOLE[i + 1:]:
            if {a, b} in ({"Body", "LegL"}, {"Body", "LegR"}, {"Body", "Head"}, {"Sword", "ArmR"}, {"Sheath", "Body"}) \
                    or (sheathed and {a, b} == {"Sword", "Sheath"}):
                continue
            both = occ[a] & occ[b]
            n = int(both.sum())
            if n:
                idx = np.argwhere(both)
                lo = idx.min(axis=0) * 0.5 + SW_LO
                hi = idx.max(axis=0) * 0.5 + SW_LO
                bad.append("%s-%s:%d [x %.0f..%.0f y %.0f..%.0f z %.0f..%.0f]" % (a, b, n, lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]))
                if DIAG and n > 20 and {a, b} != {"Body", "Cape"}:
                    wz = idx[:, 2] * 0.5 + SW_LO[2]
                    for z0 in range(0, 140, 10):
                        m = (wz >= z0) & (wz < z0 + 10)
                        if m.any():
                            q = idx[m] * 0.5 + SW_LO
                            print("      %s-%s z %3d..%3d: %5d cells, x %.0f..%.0f y %.0f..%.0f" % (a, b, z0, z0 + 10, int(m.sum()), q[:, 0].min(), q[:, 0].max(), q[:, 1].min(), q[:, 1].max()))
    low = min(float(p[:, 2].min()) for p in posed.values())
    print("CHECK %-14s lowest z %.1f u | overlaps: %s" % (label, low, "; ".join(bad) if bad else "none"))


# ---------------------------------------------------------------------------------------------------- previews

def preview_material(kind):
    name = "Prev_" + kind
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes["Principled BSDF"]
    col = nt.nodes.new("ShaderNodeVertexColor")
    col.layer_name = "Col"
    nt.links.new(col.outputs["Color"], b.inputs["Base Color"])

    def setv(key, v):
        if key in b.inputs:
            b.inputs[key].default_value = v

    rough, metal = dict(cloth=(0.85, 0), skin=(0.55, 0), hair=(0.6, 0), leather=(0.55, 0), gold=(0.42, 1.0), metal=(0.5, 1.0),
                        blade=(0.38, 1.0), fur=(0.95, 0), gem=(0.15, 0), core=(1.0, 0))[kind]
    setv("Roughness", rough)
    setv("Metallic", metal)
    if kind in ("skin", "fur"):
        setv("Subsurface Weight", 0.2 if kind == "skin" else 0.12)
        setv("Subsurface Radius", (1.0, 0.45, 0.25) if kind == "skin" else (1.0, 0.9, 0.7))
        setv("Subsurface Scale", 0.012 if kind == "skin" else 0.02)
    if kind == "fur":
        setv("Sheen Weight", 0.15)
    if kind in ("gem",):
        nt.links.new(col.outputs["Color"], b.inputs["Emission Color"])
        setv("Emission Strength", 0.25)
    if kind in ("cloth", "leather", "hair", "fur", "gold", "metal", "blade"):
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = dict(cloth=900.0, leather=500.0, hair=700.0, fur=1200.0).get(kind, 260.0)
        noise.inputs["Detail"].default_value = 3.0
        bump = nt.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = dict(cloth=0.22, leather=0.15, hair=0.25, fur=0.3).get(kind, 0.05)
        bump.inputs["Distance"].default_value = 0.002
        nt.links.new(noise.outputs[0], bump.inputs["Height"])
        nt.links.new(bump.outputs[0], b.inputs["Normal"])
    return mat


def to_preview(obs, parts):
    for key, ob in obs.items():
        mesh = ob.data
        kinds = parts[key].kind_per_tri
        mesh.materials.clear()
        used = sorted(set(kinds.tolist()))
        lut = np.zeros(len(KINDS), np.int32)
        for i, k in enumerate(used):
            lut[k] = i
            mesh.materials.append(preview_material(KINDS[k]))
        mesh.polygons.foreach_set("material_index", lut[kinds].astype(np.int32))
        mesh.update()


def look_at(ob, target):
    from mathutils import Vector
    d = Vector(target) - ob.location
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def stage():
    if os.environ.get("KING_CPU"):
        bpy.context.scene.cycles.device = "CPU"
    scene = bpy.context.scene
    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    bg = nt.nodes["Background"]
    out = nt.nodes["World Output"]
    lp = nt.nodes.new("ShaderNodeLightPath")
    cam_bg = nt.nodes.new("ShaderNodeBackground")
    cam_bg.inputs[0].default_value = (0.082, 0.082, 0.085, 1)
    cam_bg.inputs[1].default_value = 1.0
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.25
    ramp.color_ramp.elements[0].color = (0.92, 0.9, 0.88, 1)
    ramp.color_ramp.elements[1].position = 0.85
    ramp.color_ramp.elements[1].color = (1.25, 1.2, 1.12, 1)
    mapr = nt.nodes.new("ShaderNodeMapRange")
    mapr.inputs[1].default_value = -1.0
    mapr.inputs[2].default_value = 1.0
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], mapr.inputs[0])
    nt.links.new(mapr.outputs[0], ramp.inputs[0])
    nt.links.new(ramp.outputs[0], bg.inputs[0])
    bg.inputs[1].default_value = 1.0
    amb = nt.nodes.new("ShaderNodeBackground")               # what diffuse surfaces get: a soft cool ambient
    amb.inputs[0].default_value = (0.72, 0.7, 0.7, 1)
    amb.inputs[1].default_value = 0.65
    mixg = nt.nodes.new("ShaderNodeMixShader")               # glossy rays see the bright studio gradient
    nt.links.new(lp.outputs["Is Glossy Ray"], mixg.inputs[0])
    nt.links.new(amb.outputs[0], mixg.inputs[1])
    nt.links.new(bg.outputs[0], mixg.inputs[2])
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
    nt.links.new(mixg.outputs[0], mix.inputs[1])
    nt.links.new(cam_bg.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])
    bpy.ops.mesh.primitive_plane_add(size=400, location=(0, 0, -0.001))
    gnd = bpy.context.active_object
    gnd.name = "PreviewGround"
    gm = bpy.data.materials.new("PreviewGround")
    gm.use_nodes = True
    gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.05, 0.05, 0.052, 1)
    gm.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 1.0
    gm.node_tree.nodes["Principled BSDF"].inputs["Specular IOR Level"].default_value = 0.0
    gnd.data.materials.append(gm)
    rig = bpy.data.objects.new("Rig", None)
    scene.collection.objects.link(rig)

    def lamp(name, kind, energy, color, pos, size=None):
        l = bpy.data.lights.new(name, kind)
        l.energy = energy
        l.color = color
        if kind == "SUN":
            l.angle = math.radians(size or 3.0)
        else:
            l.size = size or 2.0
        o = bpy.data.objects.new(name, l)
        scene.collection.objects.link(o)
        o.location = pos
        look_at(o, (0, 0, 0.9))
        o.parent = rig
        return o

    # positions for a camera straight in front (-Y); the rig is turned with the camera
    lamp("Key", "SUN", 4.4, (1.0, 0.91, 0.78), (-3.0, -8.0, 6.0), 5.0)
    lamp("Rim", "SUN", 4.5, (0.95, 0.97, 1.0), (4.5, 7.0, 5.5), 3.0)
    lamp("Fill", "AREA", 520.0, (1.0, 0.97, 0.94), (4.0, -7.0, 2.0), 6.0)
    return rig


def shot(name, az, el, dist=6.2, target=(0, 0, 0.86), res=(900, 1200), lens=105, samples=None):
    scene = bpy.context.scene
    path = os.path.join(V.PREVIEWS, "king_b_%s.png" % name)
    cam = bpy.data.objects.get("PreviewCam")
    if cam is None:
        cam = bpy.data.objects.new("PreviewCam", bpy.data.cameras.new("PreviewCam"))
        scene.collection.objects.link(cam)
    a, e = math.radians(az), math.radians(el)
    cam.location = (target[0] + math.sin(a) * math.cos(e) * dist, target[1] - math.cos(a) * math.cos(e) * dist, target[2] + math.sin(e) * dist)
    look_at(cam, target)
    cam.data.lens = lens
    scene.camera = cam
    bpy.data.objects["Rig"].rotation_euler = (0, 0, math.radians(az))
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.filepath = path
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples or (24 if FAST else 72)
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 6
    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - High Contrast"
    except Exception:
        pass
    scene.view_settings.exposure = 0.0
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "METAL"
        prefs.get_devices()
        for dev in prefs.devices:
            dev.use = True
        scene.cycles.device = "CPU" if os.environ.get("KING_CPU") else "GPU"
    except Exception:
        pass
    try:
        bpy.ops.render.render(write_still=True)
    except RuntimeError as ex:
        print("GPU render failed (%s): CPU" % str(ex).strip().splitlines()[0][:80])
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
    return a.reshape(h, w, 4)[::-1].copy()


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


def montage(paths, out, H=1000, crops=None):
    tiles = []
    for i, p in enumerate(paths):
        a = load_px(p)
        if crops and crops[i]:
            x0, y0, x1, y1 = crops[i]
            a = a[y0:y1, x0:x1]
        tiles.append(fit_h(a, H))
    save_px(np.concatenate(tiles, axis=1), out)
    print("montage", out)


SHEATH = {}


CARRY = dict(armr=10.0, forer=25.0, handr=45.0)      # how the previews hold the drawn sword: arm down, blade forward and down


def rig(obs):
    """Parent the objects as the engine does (after the export, which wants them loose)."""
    for key, ob in obs.items():
        if key in PARENT:
            ob.parent = obs[PARENT[key]]


def pose(obs, sheathed=False, **ang):
    """Turn joints by degrees about x (Head: about z): legl, legr, shinl, shinr, arml, armr, forel, forer, handr, chest,
    cape (every panel of the top row), head. Positive swings a hanging limb backwards. The drawn sword sits in the
    fist and moves with the hand."""
    from mathutils import Matrix
    for key, ob in obs.items():
        base = np.array(JOINTS[PARENT[key]], np.float64) if key in PARENT else np.zeros(3)
        if key == "Sword":
            ob.rotation_mode = "QUATERNION"
            if sheathed:
                ob.parent = None
                ob.location = [float(v) * U for v in SHEATH["grip"]]
                ob.rotation_quaternion = Matrix(SHEATH["delta"].tolist()).to_quaternion()
            else:
                ob.parent = obs["HandR"]
                ob.location = [float(v) * U for v in np.array(JOINTS["Sword"]) - np.array(JOINTS["HandR"])]
                ob.rotation_quaternion = (1, 0, 0, 0)
            continue
        ob.location = [float(v) * U for v in np.array(JOINTS[key], np.float64) - base]
        a = ang.get(key.lower(), ang.get("cape", 0.0) if key.startswith("Cape") and key.endswith("0") and len(key) == 6 else 0.0)
        ob.rotation_euler = (0, 0, math.radians(a)) if key == "Head" else (math.radians(a), 0, 0)


def want(name):
    return VIEWS is None or name in VIEWS


def main():
    t0 = time.time()
    V.reset_scene()
    parts = build_king()
    for k in ORDER:
        cull(parts[k])
    print("culled in %.1f s" % (time.time() - t0))
    ao_field(parts)
    print("shading field in %.1f s" % (time.time() - t0))

    lo = np.array([1e9] * 3)
    hi = -lo
    for k in ORDER:
        P = part_points(parts[k], step=1.0, cores=False)
        lo, hi = np.minimum(lo, P.min(axis=0)), np.maximum(hi, P.max(axis=0))
    print("KING size: x %.3f m (%.2f..%.2f), y %.3f m (%.2f..%.2f), height %.4f m (lowest %.4f)" % (
        (hi[0] - lo[0]) * U, lo[0] * U, hi[0] * U, (hi[1] - lo[1]) * U, lo[1] * U, hi[1] * U, hi[2] * U, lo[2] * U))
    W = wholes(parts)
    pts = {k: part_points(W[k], step=0.6, shrink=0.4, cores=False) for k in WHOLE}
    check_pose(W, pts, "rest")
    check_pose(W, pts, "walk A", legl=35, legr=-35, arml=-35, armr=35, cape=20)
    check_pose(W, pts, "walk B", legl=-35, legr=35, arml=35, armr=-35, cape=20)
    pts["SwordSheathed"] = sheathed_points(parts, pts["Sword"])
    check_pose(W, pts, "sheathed rest", sheathed=True)
    check_pose(W, pts, "sheathed walk A", sheathed=True, legl=35, legr=-35, arml=-35, armr=35, cape=20)
    check_pose(W, pts, "sheathed walk B", sheathed=True, legl=-35, legr=35, arml=35, armr=-35, cape=20)

    obs = {}
    total = 0
    for key in ORDER:
        ob = make_object(parts[key])
        obs[key] = ob
        V.export_gltf(ob, collision="none", extra=dict(pivot=pivot(key), part=key, triangles=int(ob["triangles"]),
                                                       blocks=int(len(parts[key].c))))
        total += int(ob["triangles"])
        kd = parts[key].kind_per_tri
        print("  %-5s %6d blocks (%d core)  %7d triangles (%d core)" % (key, len(parts[key].c), int(parts[key].core.sum()), ob["triangles"],
                                                                      int((kd == KINDS.index("core")).sum())))
    print("KING triangles in all: %d  (%.1f s)" % (total, time.time() - t0))
    sh = parts["Sheath"]
    sw = parts["Sword"]
    meta = dict(height=1.7, radius=0.42, voxel=U, elbow_l=ELBOW["L"], elbow_r=ELBOW["R"],
                cape=dict(cols=CAPE_COLS, rows=CAPE_ROWS),
                parts={key: dict(mesh=PREFIX + key, pivot=pivot(key), parent=PARENT.get(key, "")) for key in ORDER},
                sword=dict(blade_dir=[round(float(v), 5) for v in sw.frame.R @ np.array([0.0, 0.0, -1.0])],
                           sheath_dir=[round(float(v), 5) for v in sh.dir],
                           sheath_pos=[round(float(v) * U, 5) for v in sh.sword_frame.t],
                           delta=[[round(float(v), 6) for v in row] for row in sh.sword_delta]))
    with open(os.path.join(V.MESHES, "SM_KingB.json"), "w") as f:
        json.dump(meta, f, indent=1)
    print("wrote SM_KingB.json")
    if NO_RENDER:
        return

    SHEATH["grip"] = parts["Sheath"].sword_frame.t
    SHEATH["delta"] = parts["Sheath"].sword_delta
    to_preview(obs, parts)
    stage()
    rig(obs)
    Pv = V.PREVIEWS
    pose(obs, **CARRY)
    if want("hero"):
        hero = shot("hero", az=-29, el=-5, dist=6.3, target=(-0.07, 0, 0.845), res=(900, 1200), lens=104)
        montage([REF, hero], os.path.join(Pv, "king_b_compare.png"), H=1200, crops=[(0, 30, 1005, 1370), None])
    if want("sides"):
        tiles = [shot("front", 0, 2, res=(720, 960)), shot("right", -90, 2, res=(720, 960)),
                 shot("back", 180, 4, res=(720, 960)), shot("left", 90, 2, res=(720, 960))]
        montage(tiles, os.path.join(Pv, "king_b_sides.png"), H=960)
    if want("head"):
        head = shot("head", az=-33, el=-12, dist=6.0, target=(-0.02, 0, 1.43), res=(1000, 1000), lens=250)
        montage([os.path.join(V.ROOT, "References", "crops", "king_head.png"), head], os.path.join(Pv, "king_b_head_compare.png"), H=1000)
    if want("face"):
        tiles = [shot("face_front", 0, 0, dist=6.0, target=(0, 0, 1.47), res=(800, 800), lens=250),
                 shot("face_34", -33, -6, dist=6.0, target=(0, 0, 1.47), res=(800, 800), lens=250),
                 shot("face_side", -90, 0, dist=6.0, target=(0, 0, 1.47), res=(800, 800), lens=250)]
        montage(tiles, os.path.join(Pv, "king_b_face.png"), H=800)
    if want("grip"):
        gx, gy, gz = [float(v) * U for v in JOINTS["HandR"]]
        tiles = []
        for nm, kw in (("carry", CARRY), ("level", dict(armr=-40.0, forer=-40.0, handr=20.0)), ("raised", dict(armr=-140.0, forer=-50.0, handr=-10.0))):
            pose(obs, **kw)
            bpy.context.view_layer.update()
            c = obs["Sword"].matrix_world.translation
            for vi, (az, el) in enumerate(((-90, 5), (-35, 10), (-140, 20))):
                tiles.append(shot("grip_%s_%d" % (nm, vi), az, el, dist=6.0, target=(c.x, c.y, c.z), res=(640, 640), lens=260))
        for r in range(3):
            montage(tiles[r * 3:r * 3 + 3], os.path.join(Pv, "king_b_grip_%d.png" % r), H=640)
        pose(obs, **CARRY)
    if want("game"):
        tiles = [shot("game_front", 25, 40, dist=7.0, res=(720, 960)), shot("game_back", 205, 40, dist=7.0, res=(720, 960))]
        montage(tiles, os.path.join(Pv, "king_b_game.png"), H=960)
    if want("sheathed"):
        pose(obs, sheathed=True)
        tiles = [shot("sheathed_front", -29, -2, dist=6.6, res=(720, 960)), shot("sheathed_left", 90, 2, dist=6.6, res=(720, 960)),
                 shot("sheathed_game", 25, 40, dist=7.0, res=(720, 960)), shot("sheathed_back", 150, 8, dist=6.6, res=(720, 960))]
        montage(tiles, os.path.join(Pv, "king_b_sheathed.png"), H=960)
        pose(obs, legl=35, legr=-35, arml=-35, armr=35, cape=20, sheathed=True)
        tiles = [shot("sheathed_walk_left", 90, 2, dist=7.0, res=(720, 960)), shot("sheathed_walk_front", -29, 0, dist=7.0, res=(720, 960))]
        montage(tiles, os.path.join(Pv, "king_b_sheathed_walk.png"), H=960)
        pose(obs, **CARRY)
    if want("walk"):
        pose(obs, legl=30, shinl=-10, legr=-25, shinr=35, arml=-30, forel=-25, armr=35, forer=10, handr=45, chest=-6, cape=20)
        tiles = [shot("walk_front", -29, 0, dist=7.0, res=(720, 960)), shot("walk_left", 90, 2, dist=7.0, res=(720, 960)),
                 shot("walk_back", 150, 8, dist=7.0, res=(720, 960)), shot("walk_right", -90, 2, dist=7.0, res=(720, 960))]
        montage(tiles, os.path.join(Pv, "king_b_walk.png"), H=960)
        pose(obs, **CARRY)
    print("done in %.1f s" % (time.time() - t0))


main()
