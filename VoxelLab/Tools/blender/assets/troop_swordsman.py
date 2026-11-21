"""The SWORDSMAN troop: a sturdy soldier with an afro, a short beard, a green cowl and cape, a padded cream tunic and a
shortsword, built like King David (king_b.py) from individual bevelled cubes and slabs of several sizes, as rigid parts
(a wooden toy) that the game swings about their joints. Each part is exported on its own with its mesh origin at its
joint. Reference: References/Remake/swordsman.png.

    Blender -b --factory-startup --python Tools/blender/assets/troop_swordsman.py -- [--no-render] [--views hero,sides,...] [--fast] [--gpu]

Units: "u" = 1.25 cm (he is 140 u = 1.75 m to the top of his afro, 128 u = 1.6 m to the top of his skull; the King is 138 u to the tip of his crown). World axes: +X is his LEFT (he faces -Y), z = 0 is
the ground between his feet.

THE RIG (the block "THE RIG" below) is King David's: the same part names, parents and joints, so the same C++ swings
him. If the King's rig changes, change that block (and the few places marked RIG) and run again.

The block engine (Part, Grid, emit, cull, the baked shading, the mesh) and the preview stage are copies of king_b.py's
(marked below), so this script does not depend on that file while it is being worked on.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import json
import math
import time

import bpy
import numpy as np
import voxlib as V
from voxlib import Vox

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
NO_RENDER = "--no-render" in ARGS
DIAG = "--diag" in ARGS
FAST = "--fast" in ARGS
CPU_ONLY = "--gpu" not in ARGS                # Cycles on the Metal GPU can crash here: the CPU unless asked
VIEWS = set(ARGS[ARGS.index("--views") + 1].split(",")) if "--views" in ARGS else None

U = 0.0125
NAME = "SM_Swordsman"
PREFIX = NAME + "_"
REF = os.path.join(V.ROOT, "References", "Remake", "swordsman.png")

# ================================================================================================== THE RIG
# King David's rig (king_b.py / SM_KingB.json), without the scabbard. A tree of rigid parts (PARENT; no entry = the
# figure's root). Body is the pelvis, Chest turns on it at the waist; each arm is an upper arm and a forearm (the left
# with its hand, the right with the sword hand "HandR" turning at the wrist); each leg a thigh (with its half of the
# skirt) and a shin (with the boot); the cape is a yoke on the shoulders ("Cape") and CAPE_COLS chains of CAPE_ROWS
# panels hanging from it ("Cape<col><row>", col 0 on his right (-x) as in the King's files), which the engine swings
# as cloth. The sword is its own part, modelled in the right fist, its origin at the middle of the grip.
ORDER = ["Body", "Chest", "Head", "ArmL", "ForeL", "ArmR", "ForeR", "HandR", "LegL", "ShinL", "LegR", "ShinR", "Cape", "Sword"]
PARENT = {"Chest": "Body", "Head": "Chest", "ArmL": "Chest", "ArmR": "Chest", "ForeL": "ArmL", "ForeR": "ArmR", "HandR": "ForeR",
          "ShinL": "LegL", "ShinR": "LegR", "Cape": "Chest"}
CAPE_COLS, CAPE_ROWS = 5, 4
CAPE_U = (-0.72, -0.25, 0.25, 0.72)           # the columns' borders, as a share of the cape's half width
CAPE_L = ((16, 36, 56, 76), (20, 40, 60, 80)) # where the rows start, u below the collar (even / odd columns: staggered)
CAPE_HEM = 16.0                               # the hem's height above the ground (u): the cape falls to the calves
ELBOW = {"L": 14.0, "R": 33.0}                # the bend the forearms are modelled with (degrees)
ARM_OUT = {"L": 7.0, "R": 6.0}                # how far the arms hang out from the shoulders (degrees)
KNEE_Z = 28.0
TOP = 140.0                                   # the top of his hair
HEIGHT, RADIUS = 1.75, 0.42                    # metres, for the character's capsule (the height includes the afro)
JOINTS = {                                    # u, world
    "Body": (0, 0, 56), "Chest": (0, 0, 73), "Head": (0, 0, 104),
    "ArmL": (25, 0, 100), "ArmR": (-25, 0, 100),
    "LegL": (12, 0, 54), "LegR": (-12, 0, 54),
    "ShinL": (12, 0, KNEE_Z), "ShinR": (-12, 0, KNEE_Z),
    "Cape": (0, 16, 104),
    # set while building: ForeL / ForeR (the elbows, build_arm), HandR (the wrist), Sword (the middle of the grip in
    # the right fist, build_sword), Cape<col><row> (the middle of each panel's top edge, build_cape)
}
ELBOW_AT = (25, 0, 76)                        # the elbow, in the upper arm's own frame (x mirrored for the right arm)
WRIST_AT = (25, -0.5, 52.0)                   # the wrist, in the forearm's frame
GRIP = (24.8, -3.5, 45.8)                     # the middle of the sword's grip in the fist, in the forearm's frame
# ==================================================================================================

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
    ("skin",     "#C4691F", "paint", "skin"), ("skin_l", "#D87C2C", "paint", "skin"), ("skin_d", "#A4561A", "paint", "skin"),
    ("skin_dd",  "#84451B", "paint", "skin"), ("lip", "#8E4426", "paint", "skin"),
    ("hair",     "#35241B", "paint", "hair"), ("hair_l", "#453023", "paint", "hair"), ("hair_ll", "#573B2B", "paint", "hair"),
    ("hair_d",   "#261913", "paint", "hair"),
    ("beard",    "#1E1613", "paint", "hair"), ("beard_l", "#2C201A", "paint", "hair"),
    ("green",    "#566E20", "paint", "cloth"), ("green_l", "#6A842C", "paint", "cloth"), ("green_d", "#445A19", "paint", "cloth"),
    ("green_dd", "#324310", "paint", "cloth"),
    ("olive",    "#7C7832", "paint", "cloth"), ("olive_l", "#928C40", "paint", "cloth"), ("olive_d", "#666228", "paint", "cloth"),
    ("cream",    "#DCBC80", "paint", "cloth"), ("cream_l", "#EBD09A", "paint", "cloth"), ("cream_d", "#C2A066", "paint", "cloth"),
    ("cream_dd", "#A6854E", "paint", "cloth"),
    ("belt",     "#7B4A24", "paint", "leather"), ("belt_l", "#96602F", "paint", "leather"), ("belt_d", "#5A3418", "paint", "leather"),
    ("belt_dd",  "#40240F", "paint", "leather"),
    ("bracer",   "#6A4226", "paint", "leather"), ("bracer_l", "#82532F", "paint", "leather"), ("bracer_d", "#4E2F1A", "paint", "leather"),
    ("glove",    "#96592A", "paint", "leather"), ("glove_l", "#B06C34", "paint", "leather"), ("glove_d", "#78441E", "paint", "leather"),
    ("trouser",  "#5A3B26", "paint", "cloth"), ("trouser_l", "#6D4930", "paint", "cloth"), ("trouser_d", "#452C1B", "paint", "cloth"),
    ("boot",     "#77492A", "paint", "leather"), ("boot_l", "#8F5B33", "paint", "leather"), ("boot_d", "#5A361D", "paint", "leather"),
    ("sole",     "#4A2E1B", "paint", "leather"), ("sole_d", "#33200F", "paint", "leather"),
    ("white",    "#F4EFE4", "paint", "gem"), ("pupil", "#15100E", "paint", "hair"), ("lip_d", "#6E3320", "paint", "skin"),
    ("gem",      "#C8281E", "paint", "gem"), ("gem_l", "#FF6A50", "paint", "gem"), ("gem_w", "#FFF4DA", "paint", "gem"),
    ("core",     "#17120F", "paint", "core"),
]
PN = [None] + [p[0] for p in _PAL]
PI = {n: i for i, n in enumerate(PN)}
PRGB = np.array([[0, 0, 0]] + [[int(p[1][i:i + 2], 16) / 255.0 for i in (1, 3, 5)] for p in _PAL], np.float32)
PMAT = np.array([0] + [MATN.index(p[2]) for p in _PAL], np.int32)
PKIND = np.array([0] + [KINDS.index(p[3]) for p in _PAL], np.int32)


# ##################################################################################################################
# The block engine: a copy of king_b.py's (small maths, Part, Grid, emit, the chamfered box, cull, the baked shading,
# the mesh, the swept volumes).
# ##################################################################################################################

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
NOSHADE = ("white", "pupil", "lip", "gem", "gem_l", "gem_w", "core")


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


# ##################################################################################################################
# The swordsman
# ##################################################################################################################
# Shapes are sculpted on 2 u cells (4 u for cape and hair, 1 u for the face) and MERGED into the fewest, largest
# boxes by emit(); studs, gems, the clasp, the buckles, the fists and the sword are direct blocks.

WING_W0, WING_K = 37.0, 0.20                  # half width of the cape = WING_W0 + WING_K * (104 - z)
GOLD_BARS = {"gold": (5, 10)}
QUILT = ((5, 7), (8, 12), (5, 7))             # the padded tunic: squarish pads


def build_leg(s):
    """-> (thigh, shin). The thigh carries the knee pad and its half of the tunic's skirt; the shin the boot and,
    hidden inside the knee pad while the leg is straight, the drum the knee turns on."""
    side = "L" if s > 0 else "R"
    P, Q = Part("Leg" + side), Part("Shin" + side)
    g = Grid(IDENT, 3, 27, -19, 13, 0, 66, cs=2, sx=s)
    XS, Y, Z = g.XS, g.Y, g.Z
    g.box(5, 19, -7, 7, 24, 54, "trouser")                    # thigh (under the skirt)
    g.box(5, 21, -9, 7, 24, 32, "boot_l")                     # knee: a wide leather pad
    g.pbox(5, 21, -9, 7, 30, 32, "boot_d")
    # the half of the skirt that swings with this leg, ending in a drum about the hip axis
    sk = g.bm(5, 21, -9, 9, 34, 54)
    drum = (XS > 5) & (XS < 21) & (Y ** 2 + (Z - 54) ** 2 < 9.7 ** 2) & (Z > 54)
    g.fill(sk | drum, "green")
    g.paint(sk & (Y < -7) & (XS > 13) & (XS < 17), "green_d") # a fold down the front
    g.box(5, 23, -11, 11, 34, 38, "gold")                     # hem: a gold band, broken by green
    hem = g.bm(5, 23, -11, 11, 34, 38)
    g.paint(hem & (g.hash(2, 3 + s, ax=(1, 1, 0)) < 0.22) & (XS > 9), "green_d")
    g.paint(sk & (XS < 9) & (Y < -7) & (Z > 38), "gold")      # gold border beside the tabard
    emit(P, g, lim=(8, 16), lims={"gold": (6, 11), "trouser": (10, 20), "green": ((5, 8), (8, 12), (5, 9)), "green_d": ((2, 4), (2, 4), (10, 16))},
         shade=0.5, seed=20 + s)
    g = Grid(IDENT, 3, 27, -19, 13, 0, 66, cs=2, sx=s)
    XS, Y, Z = g.XS, g.Y, g.Z
    g.fill((XS > 7) & (XS < 17) & (Y ** 2 + (Z - KNEE_Z) ** 2 < 37.0) & (Z > 22), "trouser_d")    # the knee's drum
    g.box(5, 19, -7, 7, 8, 24, "boot")                        # the boot's shaft
    g.box(5, 21, -9, 9, 16, 22, "boot_l")                     # its turned-down cuff
    g.box(3, 21, -15, 7, 0, 8, "boot")                        # foot
    foot = g.bm(3, 21, -15, 7, 0, 8)
    g.carve(foot & (Y < -11) & (Z > 6))
    g.carve(foot & (Y < -13) & (Z > 4))
    g.paint(foot & (Y < -9), "boot_l")                        # toe cap
    g.paint(foot & (Z < 2), "sole")
    emit(Q, g, lim=(8, 16), lims={"gold": (6, 11), "sole": (10, 22)}, seed=24 + s)
    b = lambda *a, **k: Q.blk(IDENT, *a, sx=s, **k)
    b(2.3, 21.7, -15.8, 7.8, 0.0, 1.5, "sole_d")              # the welt of the sole
    b(4.4, 19.6, -7.7, 7.7, 9.0, 12.0, "belt_d")              # ankle strap and its gold buckle
    b(9.5, 14.5, -9.0, -7.5, 8.2, 12.8, "gold")
    b(11.0, 13.0, -9.5, -8.8, 9.6, 11.4, "belt_dd", bevel=0.15)
    b(20.6, 22.2, -4.0, 2.0, 16.2, 21.8, "gold")              # gold buckle on the outside of the cuff
    b(21.9, 22.6, -2.2, 0.2, 17.8, 20.2, "boot_d", bevel=0.15)
    b(8.0, 12.0, -10.2, -8.8, 16.6, 20.6, "gold_d")           # and a small one on its front
    b = lambda *a, **k: P.blk(IDENT, *a, sx=s, **k)
    b(9.0, 15.0, -10.2, -8.8, 25.0, 29.5, "boot")             # knee cap
    b(10.8, 13.2, -10.9, -10.0, 26.2, 28.6, "gold")
    for (x, z) in ((11.5, 44.0), (16.0, 49.0)) if s < 0 else ((13.0, 46.0), (10.5, 41.0)):
        b(x, x + 2.2, -10.0, -8.8, z, z + 2.2, "gold")        # studs on the cloth
    b(20.8, 21.9, -2.5, 2.5, 43.0, 48.0, "gold")              # hollow square on the hip side
    b(21.7, 22.3, -1.2, 1.2, 44.3, 46.7, "green_d")
    return P, Q


def build_arm(s):
    """-> (upper arm, forearm with the hand). The elbow is where the forearm's frame is bent. The green capelet of
    the cowl lies on the upper arm and swings with it."""
    side = "L" if s > 0 else "R"
    P = Part("Arm" + side)
    A = Frame().sub(RY(-s * ARM_OUT[side]), P.joint)
    bend = ELBOW[side]
    ex, ey, ez = ELBOW_AT
    Fo = A.sub(RX(-bend), (s * ex, ey, ez))
    JOINTS["Fore" + side] = tuple(float(v) for v in A.w((s * ex, ey, ez)))
    Q = Part("Fore" + side)
    # ---- upper arm: shoulder drum, capelet, puffed sleeve
    g = Grid(A, 15, 37, -12, 12, 70, 112, cs=2, sx=s)
    XS, Y, Z = g.XS, g.Y, g.Z
    g.box(19, 31, -6, 6, 70, 76, "cream_d")                   # the sleeve gathered above the elbow
    g.fill((XS > 19) & (XS < 31) & (Y ** 2 + (Z - 100) ** 2 < 7.0 ** 2), "green")       # the drum the arm turns on
    if s < 0:
        g.box(19, 33, -8, 8, 76, 88, "cream")                 # the big puff of the sword arm
        g.pbox(19, 33, -8, 8, 76, 78, "cream_l")
        g.box(19, 31, -8, 8, 94, 98, "green")                 # capelet: draped in tiers, wider toward its edge
        g.box(19, 33, -8, 8, 90, 94, "green")
        g.box(19, 33, -10, 10, 86, 90, "gold")                # its gold border, standing out
    else:
        g.box(19, 33, -8, 8, 76, 80, "cream")                 # a short puff under the long capelet
        g.box(19, 31, -8, 8, 94, 98, "green")                 # the long capelet, draped in tiers
        g.box(19, 33, -8, 8, 84, 94, "green")
        g.box(19, 33, -10, 10, 80, 84, "gold")                # gold band
        g.pbox(19, 33, -8, 8, 84, 88, "green_d")
    cap = g.isn("green")
    fold = (g.iy + (g.ix // 3)) % 4                           # folds running down the capelet
    g.paint(cap & (fold == 0), "green_d")
    g.paint(cap & (fold == 2), "green_l")
    emit(P, g, lim=((4, 8), (2, 4), (6, 12)), pref="z", lims=dict(gold=((5, 10), (5, 10), (4, 4)), cream=QUILT, cream_l=QUILT, cream_d=(8, 16)),
         shade=0.3, proud_p=0.45, proud=(0.15, 0.5), seed=31 + s)
    a = lambda *q, **k: P.blk(A, *q, sx=s, **k)
    if s < 0:
        for y in (-6.0, 0.0, 6.0):                            # studs on the border
            a(32.8, 33.7, y - 1.1, y + 1.1, 86.9, 89.1, "gold_l", bevel=0.15)
        for x in (22.0, 28.0):
            a(x - 1.1, x + 1.1, -10.9, -9.9, 86.9, 89.1, "gold_l", bevel=0.15)
    else:
        a(32.8, 33.8, -2.2, 2.2, 80.4, 83.6, "gold_l")
        a(24.0, 28.0, -11.0, -9.9, 80.4, 83.6, "gold_l")
    # ---- forearm and hand (bent frame)
    g = Grid(Fo, 14, 36, -13, 13, 38, 82, cs=2, sx=s)
    XS, Y, Z = g.XS, g.Y, g.Z
    g.box(20, 30, -5, 5, 70, 80, "cream_d")
    g.box(18, 32, -7, 7, 70, 74, "cream_l")                   # the sleeve's cuff, turned back over the bracer
    g.box(20, 30, -5, 5, 52, 56, "glove_d")                   # the glove's wrist
    if s < 0:
        g.box(18, 32, -7, 7, 56, 70, "bracer")                # leather bracer
        g.pbox(18, 32, -7, 7, 56, 58, "bracer_d")
    else:
        g.box(18, 32, -7, 7, 56, 70, "steel")                 # the steel vambrace, a gold band at the wrist
        g.pbox(18, 32, -7, 7, 56, 60, "gold")
    Q.bias = len(P._ch)
    emit(Q, g, lim=(8, 16), lims={"gold": (6, 12)}, seed=41 + s)
    f = lambda *q, **k: Q.blk(Fo, *q, sx=s, **k)
    if s < 0:
        for z in (61.0, 66.0):                                # studs
            f(32.0, 32.8, -1.1, 1.1, z - 1.1, z + 1.1, "steel_ll", bevel=0.15)
            f(23.9, 26.1, -7.8, -7.0, z - 1.1, z + 1.1, "steel_ll", bevel=0.15)
        f(17.5, 32.5, -7.5, 7.5, 68.0, 69.4, "bracer_l")      # its upper lip
    else:
        f(17.4, 32.6, -7.6, 7.6, 59.0, 60.4, "gold_l")        # lip of the gold band
        f(32.0, 33.0, -3.0, 3.0, 61.5, 68.5, "steel_l")       # plates on the vambrace
        f(22.0, 28.0, -8.0, -7.0, 61.5, 68.5, "steel_l")
        f(24.0, 26.0, -8.6, -7.8, 56.8, 59.2, "steel_ll", bevel=0.15)
    if s > 0:
        # the free fist in its glove: one block, four finger bars, a thumb
        f(19.2, 31.0, -3.0, 6.4, 41.6, 52.0, "glove")
        for (z0, z1, nm, dy) in ((42.0, 44.6, "glove_d", 0.0), (44.6, 47.1, "glove", 0.5), (47.1, 49.6, "glove_l", 0.6), (49.6, 52.0, "glove", 0.2)):
            f(19.4, 30.8, -7.4 - dy, -3.0, z0, z1, nm)
        f(18.0, 24.5, -9.0, -6.6, 47.6, 51.2, "glove_l")      # thumb
    else:
        # RIG: the sword hand, its own part turning at the wrist, closed round the hilt in a hammer grip: the grip
        # runs through the fist from back to front (across the forearm), the guard sits just beyond the thumb and the
        # forefinger, the blade carries on in line with the grip and the pommel shows behind the little finger.
        # The sword is modelled in this fist and never turns in it: the engine aims the blade with the wrist.
        wx, wy, wz = WRIST_AT
        JOINTS["HandR"] = tuple(float(v) for v in Fo.w((s * wx, wy, wz)))
        H = Part("HandR")
        h = lambda *q, **k: H.blk(Fo, *q, sx=s, **k)
        GX, GY, GZ = GRIP                                     # the grip's axis: along y, through (x GX, z GZ); its middle at y GY
        h(21.5, 28.5, -4.6, 3.2, 49.4, 53.6, "glove_d")       # wrist
        h(20.4, 30.2, GY - 5.1, GY + 5.5, 43.6, 51.0, "glove")     # the back of the hand and the palm
        for i, (nm, dz) in enumerate((("glove_l", 0.3), ("glove", 0.0), ("glove_d", 0.2), ("glove", 0.6))):
            y0 = GY - 5.3 + i * 2.75                          # four fingers side by side along the grip, curled under it
            h(19.6, 31.0, y0, y0 + 2.75, 40.4 + dz, 46.4, nm)
        h(18.2, 21.6, GY - 6.0, GY + 1.6, 45.6, 49.4, "glove_l")   # the thumb, lying along the grip on the inside
        P.hand_part = H
        P.sword_part = build_sword(Fo, (s * GX, GY, GZ))
    return P, Q


def build_sword(Fo, at):
    """The shortsword as its own part, origin at the middle of the grip, modelled as it sits in his right fist (the
    fist occupies -5.3 .. 5.7 u along the grip: guard in front of it, pommel behind). Its frame: -z down the blade
    (forward, across the forearm), x the width of the blade (along the forearm, so the edges lead when the forearm
    swings), y through the flats. The engine carries it with the hand. A broad blade about 45 cm long, a gold guard
    with a red stone, a leather grip, a gold pommel."""
    hand = Fo.w(at)
    JOINTS["Sword"] = tuple(float(v) for v in hand)
    P = Part("Sword")
    S = Frame(Fo.R @ np.array([[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 0.0, 0.0]]), hand)
    P.frame = S
    tip = -48.0
    # grip, wrapped
    for i, z in enumerate(np.arange(-5.5, 8.0, 4.5)):
        P.blk(S, -1.4, 1.4, -1.4, 1.4, z, z + 4.5, ("belt_d", "belt", "belt_d")[i], bevel=0.12)
    # pommel: a gold cube and a cap
    P.blk(S, -3.0, 3.0, -3.0, 3.0, 8.0, 13.4, "gold")
    P.blk(S, -1.9, 1.9, -1.9, 1.9, 13.4, 14.6, "gold_d")
    P.blk(S, -3.4, 3.4, -3.4, 3.4, 9.6, 11.8, "gold_l")
    # cross-guard: bar, flared ends with a pale stone each, a boss with the red stone on both faces
    P.blk(S, -8.6, 8.6, -1.8, 1.8, -9.6, -5.6, "gold")
    P.blk(S, -11.4, -7.6, -2.5, 2.5, -10.8, -4.4, "gold_l")
    P.blk(S, 7.6, 11.4, -2.5, 2.5, -10.8, -4.4, "gold_l")
    P.blk(S, -3.4, 3.4, -2.8, 2.8, -11.4, -4.0, "gold_d")
    P.blk(S, -1.8, 1.8, -3.5, 3.5, -9.5, -5.9, "gem", bevel=0.2)
    for sx in (1, -1):
        P.blk(S, 8.6, 10.4, -3.0, 3.0, -8.5, -6.7, "gem_w", bevel=0.2, sx=sx)
    # blade: broad, four long pieces stepping in to the point, a one-piece fuller
    top, ln = -11.4, abs(tip) - 11.4
    cuts = (0.0, 0.34, 0.62, 0.82, 0.93, 1.0)
    widths = (5.2, 5.0, 4.4, 3.2, 1.9)
    names = ("blade", "blade_l", "blade", "blade_l", "blade_l")
    for i in range(5):
        P.blk(S, -widths[i], widths[i], -1.0, 1.0, top - cuts[i + 1] * ln, top - cuts[i] * ln, names[i], bevel=0.035)
    P.blk(S, -1.3, 1.3, -1.5, 1.5, top - 0.6 * ln, top - 0.5, "blade_d", bevel=0.1)
    P.blk(S.sub(RY(45.0), (0, 0, tip + 1.8)), -1.7, 1.7, -0.9, 0.9, tip + 0.1, tip + 3.5, "blade_l", bevel=0.05)       # the point
    P.blade_tip = S.w((0, 0, tip))
    P.tip_local = tip
    return P


# the clumps heaped on the afro: (x, y, z, radius) u, in the head's frame. They make the top an uneven mound.
AFRO_CLUMPS = ((-6, -4, 132, 7.0), (7, 2, 133, 7.0), (-1, 9, 132, 7.0), (-13, 5, 128, 6.5), (14, -3, 128, 6.5), (2, -9, 131, 6.0),
               (-15, -4, 123, 6.0), (16, 6, 122, 6.0), (0, 16, 124, 7.0), (-10, 13, 126, 6.0), (11, 12, 127, 6.0))


def build_head():
    """A broad face under a big afro of 4 u and 8 u cubes: thick straight brows, white eyes with dark pupils, a block
    nose, a moustache and a short beard round the jaw, big ears. The head faces straight ahead (a troop in a rank)."""
    P = Part("Head")
    F = Frame().sub(RZ(0.0), P.joint)
    g = Grid(F, -18, 18, -19, 19, 100, 140, cs=2)
    X, Y, Z = g.X, g.Y, g.Z
    AX = np.abs(X)
    g.box(-12, 12, -11, 11, 106, 128, "skin")
    sk = g.solid()
    g.paint(sk & (AX > 10) & (Y < -1) & (Z < 112), "beard")   # the beard along the jaw, seen from the side
    g.paint(sk & (AX > 10) & (Y < -7) & (Z < 120), "beard")   # ... rising to the sideburns
    g.paint(sk & (Z < 108) & (Y < 1), "beard")                # ... and under the chin
    g.paint(sk & (Y > 9), "hair_d")                           # the nape, under the afro
    g.fill((AX > 12) & (AX < 14) & (Y > -3) & (Y < 3) & (Z > 112) & (Z < 120), "skin_l")      # ears
    emit(P, g, lim=(8, 14), lims={"beard": (6, 12), "skin_l": (8, 9), "hair_d": (6, 12)}, shade=0.3, seed=61)
    b = lambda *a, **k: P.blk(F, *a, **k)
    for sx in (1, -1):
        b(13.6, 14.8, -1.6, 1.8, 113.6, 118.0, "skin_d", sx=sx)    # the hollow of the ear
    # ---- the face: a 1 u plate in front of the skull; every feature is one or two boxes standing proud of it
    f = Grid(F, -14, 14, -17, -11, 100, 132)
    X, Y, Z = f.X, f.Y, f.Z
    AX = np.abs(X)
    L0, L1, L2 = (Y > -12), (Y > -13), (Y > -14)
    f.fill(L0 & (AX < 12) & (Z > 106) & (Z < 128), "skin")
    f.fill(L1 & (AX < 12) & (Z > 106) & (Z < 110), "beard")   # a full short beard: chin and jaw ...
    f.fill(L1 & (AX > 4) & (AX < 12) & (Z > 110) & (Z < 112), "beard")       # ... round the mouth ...
    f.fill(L1 & (AX > 8) & (AX < 12) & (Z > 112) & (Z < 115), "beard")       # ... stepping up the cheeks ...
    f.fill(L1 & (AX > 10) & (AX < 12) & (Z > 115) & (Z < 117), "beard")
    f.fill(L0 & (AX > 10) & (AX < 12) & (Z > 117) & (Z < 120), "beard_l")    # ... to the sideburns
    f.fill(L1 & (AX < 7) & (Z > 112) & (Z < 114), "beard")    # moustache, joined to the beard
    f.fill(L0 & (AX < 3) & (Z > 110) & (Z < 111), "lip")      # the mouth, in the small patch of skin the beard leaves
    f.fill(L2 & (AX < 2) & (Z > 114) & (Z < 119), "skin_l")   # nose: one block
    f.fill(L1 & (AX > 2) & (AX < 4) & (Z > 114) & (Z < 116), "skin_d")       # nostrils' wings
    f.fill(L0 & (AX > 3) & (AX < 9) & (Z > 119) & (Z < 122), "white")        # eyes: a white and a pupil each
    f.fill(L0 & (AX > 4) & (AX < 7) & (Z > 119) & (Z < 122), "pupil")
    f.fill(L1 & (AX > 2) & (AX < 10) & (Z > 122) & (Z < 125), "beard")       # brows: one thick rectangle each
    emit(P, f, lim=(9, 15), lims={"beard": (10, 14), "beard_l": (4, 4), "white": (3, 3), "pupil": (3, 3), "skin_l": (8, 8), "skin_d": (2, 2),
                                  "lip": (8, 8)},
         shade=0.14, proud_p=0.25, proud=(0.08, 0.2), bevel=0.8, seed=63, core=False)
    for sx in (1, -1):
        b(4.3, 5.2, -12.35, -11.9, 120.8, 121.7, "gem_w", sx=sx, bevel=0.2)             # the glint in each eye
    # ---- the afro: a big lumpy dome. A round mass with clumps heaped on it (2 u cells, merged into 4 - 6 u cubes,
    # each turned a little), then loose curls of several sizes standing out of it, the biggest on top.
    cs = 2.0
    h = Grid(F, -24, 24, -22, 24, 104, 142, cs=cs)
    X, Y, Z = h.X, h.Y, h.Z
    AX = np.abs(X)
    d = (X / 21.0) ** 2 + ((Y - 2.0) / 19.5) ** 2 + np.where(Z > 124, ((Z - 124) / 13.0) ** 2, ((Z - 124) / 14.0) ** 2)
    for (cx, cy, cz, r) in AFRO_CLUMPS:
        d = np.minimum(d, ((X - cx) ** 2 + (Y - cy) ** 2 + (Z - cz) ** 2) / r ** 2)
    d = d + (h.hash(2, 41) - 0.5) * 0.22
    hair = d < 1.0
    hair &= ~((AX < 12) & (np.abs(Y) < 12) & (Z < 128))       # the skull
    hair &= ~((Y < -12) & (Z < 128))                          # nothing in front of the face: the fringe stops above the brows
    hair &= ~((AX > 12) & (Y < 4) & (Z < 120))                # the ears stay in view
    hair &= ~((Y < 12) & (Z < 112))
    hair &= ~(Z < 108)
    hair &= Z < TOP
    hair |= (AX < 12) & (np.abs(Y) < 12) & (Z > 128) & (Z < 132)             # always a layer on the crown of the skull
    h.fill(hair, "hair")
    nb = emit(P, h, lim=(4.0, 7.6), shade=0.75, proud_p=0.4, proud=(0.15, 0.5), seed=64, cjit=0.05, tilt=7.0, core_rgb=PRGB[PI["hair_d"]] * 0.8)
    rng = np.random.default_rng(11)
    curls = 0
    for (i, j, k) in np.argwhere(hair & h.surface()):
        if rng.random() > 0.13:
            continue
        nrm = np.zeros(3)
        for ax, (di, dj, dk) in enumerate(((1, 0, 0), (0, 1, 0), (0, 0, 1))):
            for sg in (1, -1):
                q = (i + sg * di, j + sg * dj, k + sg * dk)
                if not (0 <= q[0] < h.n[0] and 0 <= q[1] < h.n[1] and 0 <= q[2] < h.n[2]) or not hair[q]:
                    nrm[ax] += sg
        ln = np.linalg.norm(nrm)
        if ln == 0 or nrm[2] < 0:
            continue
        nrm /= ln
        size = rng.uniform(3.0, 4.2) + (1.0 if nrm[2] > 0.5 and rng.random() < 0.4 else 0.0)      # bigger ones on top
        c = np.array([X[i, j, k], Y[i, j, k], Z[i, j, k]]) + nrm * rng.uniform(0.2, 1.0) + rng.uniform(-0.6, 0.6, 3)         # tight to the mass
        if c[2] + size * 0.75 > TOP + 0.5 or (c[1] < -11 and c[2] - size * 0.75 < 127.5) or (abs(c[0]) > 11 and c[1] < 5 and c[2] - size * 0.75 < 120.5):
            continue                                          # not above his height, not over the face or the ears
        Rm = RZ(rng.uniform(-35, 35)) @ RY(rng.uniform(-25, 25)) @ RX(rng.uniform(-25, 25))
        name = ("hair", "hair_l", "hair_ll", "hair_d", "hair_l")[int(rng.integers(0, 5))]
        P.add(F.place(Rm, c), [-size / 2] * 3, [size / 2] * 3, PI[name], 0.06 * size, cull=False,
              rgb=np.clip(PRGB[PI[name]] * rng.uniform(0.94, 1.06), 0, 1))
        curls += 1
    print("afro: %d blocks, %d curls" % (nb, curls))
    return P


def cape_piece(x, L):
    """Which part of the cape a point belongs to: x (u), L (u below the collar) -> (key, column, row); row -1 = yoke."""
    W = WING_W0 + WING_K * max(L, 0.0)
    col = int(np.searchsorted(CAPE_U, x / W))
    row = int(np.searchsorted(CAPE_L[col % 2], L, side="right")) - 1
    return ("Cape" if row < 0 else "Cape%d%d" % (col, row)), col, row


def build_cape():
    """-> {key: part}: the yoke under the cowl ("Cape") and the hanging panels "Cape<col><row>", each hinged at the
    middle of its top edge to the panel above it (RIG: the King's cape, cut the same way; this one ends at the calves)."""
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
    hemz = CAPE_HEM + 4 * (hash3(np.arange(nx) // 2, np.zeros(nx, int), np.zeros(nx, int), 5) > 0.6)
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
        if Lz[k] < 13 or zs[k] < CAPE_HEM:
            continue
        i_lo = iw[k]
        i_hi = max(i_lo, iw[k - 1] if k > 0 and zs[k - 1] > CAPE_HEM else i_lo)
        for (a, b) in ((i_lo, i_hi), (nx - 1 - i_hi, nx - 1 - i_lo)):
            for i in range(a, b + 1):
                jb = j1[i, k] if inside[i, k] else 0
                wing[i, :, k] = (g.Y[i, :, k] > yf[k]) & (np.arange(ny) <= max(jb, j0[i, k])) & (zs[k] > hemz[i])
    solid = back | wing
    g.fill(solid, "green")
    X, Y, Z = g.X, g.Y, g.Z
    Lc = 104 - Z
    Wc = WING_W0 + WING_K * Lc
    ridge = np.cos(X / Wc * np.pi * 5.0)
    g.paint(solid & (ridge > 0.4) & (np.abs(X) < Wc * 0.75), "green_d")        # the folds: valleys dark, ridges light
    g.paint(solid & (ridge < -0.6) & (np.abs(X) < Wc * 0.75), "green_l")
    # hem: a broken band of gold blocks, a few gold and cream ones above it, a few strays hanging low
    hz = hemz[:, None, None]
    row0 = solid & (Z < hz + 4)
    row1 = solid & (Z > hz + 4) & (Z < hz + 8)
    pair = hash3(g.ix // 2, g.iy * 0, g.iz * 0, 8)
    g.paint(row0, "gold")                                      # the gold band along the whole hem ...
    g.paint(row1 & (pair < 0.45), "gold_d")                   # ... with a battlemented second row
    g.paint(row1 & (pair > 0.9), "cream")
    g.grow(row0 & (hash3(g.ix // 2, g.iy * 0, g.iz * 0, 11) < 0.2), "-z")
    lead = wing & ~shift(wing, 1, 1, False) & (Y < 14)        # gold blocks at intervals up the leading edges
    g.paint(lead & ((g.iz % 6) == 3) & (Z > hz + 8), "gold")
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
    return out


def torso_tiers(Z):
    """Half width and half depth of the torso at height Z (2 u steps): waist, ribs, chest, shoulders."""
    hw = np.where(Z < 80, 14, np.where(Z < 84, 16, np.where(Z < 100, 18, 16)))
    hd = np.where(Z < 84, 9, np.where(Z < 100, 11, 9))
    return hw, hd


def build_body(arms, head):
    """-> (Body, Chest): the pelvis with the belt, the buckle, the tabard and the sword belt; the padded torso with
    the cowl round the neck, its clasp and the hood lying on the back (carved clear of the swinging arms and the
    turning head)."""
    P = Part("Body")
    blk = lambda *a, **k: P.blk(IDENT, *a, **k)
    # ---- pelvis: the top of the skirt, the belt
    g = Grid(IDENT, -26, 26, -19, 15, 30, 78, cs=2)
    X, Y, Z = g.X, g.Y, g.Z
    AX = np.abs(X)
    g.fill((AX < np.where(Z < 56, 22, 20)) & (np.abs(Y) < 11) & (Z > 52) & (Z < 66), "green")
    g.box(-4, 4, -7, 7, 38, 54, "trouser_d")                  # between the legs
    g.box(-16, 16, -11, 11, 66, 74, "belt")
    emit(P, g, lim=(10, 18), lims={"belt": ((10, 18), (8, 12), (4, 4))}, seed=81)
    for sx in (1, -1):
        blk(7.0, 9.0, -12.1, -11.0, 52.0, 66.0, "gold", sx=sx)               # gold borders beside the tabard
        blk(19.6, 20.9, -2.5, 2.5, 57.0, 62.0, "gold", sx=sx)                # hip squares
        blk(20.7, 21.3, -1.2, 1.2, 58.3, 60.7, "green_d", sx=sx)
        blk(10.5, 12.7, -12.2, -11.0, 69.0, 71.2, "gold", sx=sx, bevel=0.15) # belt studs
        blk(-1.2, 1.2, 11.0, 12.2, 68.8, 71.2, "gold_d")
    # tabard: one full-length strip per pleat, cream between two leather straps with gold studs
    xs = (-7.0, -5.0, -1.7, 1.7, 5.0, 7.0)
    for i in range(5):
        pr = (0.0, 0.6, 1.4, 0.6, 0.0)[i]
        blk(xs[i], xs[i + 1], -13.0 - pr, -11.0, (33.0, 31.0, 30.0, 31.0, 33.0)[i], 66.0, ("belt", "cream_d", "cream_l", "cream", "belt_l")[i],
            bevel=0.1)
    for sx in (1, -1):
        for z in (38.0, 46.0, 54.0):
            blk(5.2, 6.8, -13.7, -12.9, z, z + 1.6, "gold", sx=sx, bevel=0.15)
    blk(-1.7, 1.7, -14.6, -14.2, 31.0, 34.0, "gold_d")        # a gold tip on the middle pleat
    # the sword belt: sagging across the hips from his right (low) to his left, with studs
    for i in range(7):
        x = -20.0 + i * 5.8
        z = 55.5 + 9.5 * (i / 6.0) ** 1.4
        blk(x, x + 5.9, -15.3 if 2 <= i <= 4 else -12.4, -11.0, z, z + 4.2, ("belt_l", "belt", "belt_l", "belt", "belt_l", "belt", "belt_l")[i])
        blk(x + 2.2, x + 3.6, (-15.3 if 2 <= i <= 4 else -12.4) - 0.5, -11.0, z + 1.4, z + 2.8, "gold" if i % 2 == 0 else "steel_ll", bevel=0.15)
    # buckle: a hollow gold square, plates on plates, a dark stone
    blk(-5.6, 5.6, -14.8, -11.2, 64.3, 75.7, "gold")
    blk(-5.6, -3.4, -15.8, -14.6, 64.3, 75.7, "gold_l")
    blk(3.4, 5.6, -15.8, -14.6, 64.3, 75.7, "gold_l")
    blk(-3.4, 3.4, -15.8, -14.6, 73.5, 75.7, "gold_l")
    blk(-3.4, 3.4, -15.8, -14.6, 64.3, 66.5, "gold_l")
    blk(-3.4, 3.4, -15.2, -14.6, 66.5, 73.5, "gold_d")
    blk(-1.8, 1.8, -16.4, -15.0, 68.2, 71.8, "belt_dd", bevel=0.14)
    blk(-7.2, -5.6, -13.4, -11.2, 67.5, 72.5, "gold_d")
    blk(5.6, 7.2, -13.4, -11.2, 67.5, 72.5, "gold_d")

    # ---- torso: its own part, turning on the pelvis at the waist
    B = P
    P = Part("Chest")
    P.bias = len(B._ch)
    tb = lambda *a, **k: P.blk(IDENT, *a, **k)
    g = Grid(IDENT, -24, 24, -19, 15, 72, 112, cs=2)
    X, Y, Z = g.X, g.Y, g.Z
    AX = np.abs(X)
    hw, hd = torso_tiers(Z)
    body = (AX < hw) & (np.abs(Y) < hd) & (Z > 72) & (Z < 104)
    g.fill(body, "cream")
    g.paint(body & (Z < 76), "belt_d")
    g.paint(body & (Y > 0), "cream_d")                        # the back, under the cape
    g.paint(body & (X > 4) & (Y < 0) & (Z > 76) & (Z < 100), "olive")        # the green panel over his left side
    g.paint(body & (Z > 100), "green")                        # the cowl over the shoulders
    panel = (AX < 12) & (Y > -13) & (Y < -11) & (Z > 80) & (Z < 98)          # the padded front, proud of the chest
    g.fill(panel, "cream")
    g.paint(panel & (X > 4), "olive")
    g.paint(panel & (AX < 4), "cream_l")                      # the placket down the middle
    g.fill((X ** 2 + Y ** 2 < 6.2 ** 2) & (Z > 104) & (Z < 112), "skin_d")   # neck
    emit(P, g, lim=QUILT, lims={"skin_d": (12, 12), "belt_d": ((10, 18), (8, 12), (4, 4)), "cream_l": ((8, 8), (2, 2), (5, 7)),
                                "green": (8, 14)}, shade=0.55, seed=82)
    for z in (78.4, 84.2, 89.0):                              # gold studs down the placket
        tb(-1.1, 1.1, -13.9 if z > 80 else -11.9, -11.0, z, z + 2.2, "gold", bevel=0.15)
    for (x, z) in ((8.0, 86.0), (14.2, 80.5)):
        tb(x, x + 2.0, -13.8 if x < 12 else -11.8, -11.0, z, z + 2.0, "gold", bevel=0.15)
    for (x, z) in ((-9.5, 90.0), (-9.5, 83.0)):
        tb(x, x + 2.0, -13.8, -11.0, z, z + 2.0, "gold_d", bevel=0.15)
    for i in range(5):                                        # the strap from the cowl down to his left side
        x = 3.0 + i * 2.6
        z = 96.0 - i * 4.2
        tb(x, x + 3.6, -14.4, -11.0, z - 5.0, z, ("belt", "belt_l", "belt", "belt_l", "belt")[i])
        if i % 2 == 1:
            tb(x + 0.9, x + 2.7, -15.0, -14.2, z - 3.4, z - 1.6, "gold", bevel=0.15)

    # ---- the cowl: a thick green collar round the neck, a drape down the front to the clasp, the hood on the back
    keep_out = np.zeros(SW_N, bool)
    for a in arms:
        keep_out |= swept(a, "x", -48, 48, step=2.0, grow=1)
    keep_out |= swept(head, "z", -22, 22, step=2.0, grow=1)
    m = Grid(IDENT, -28, 28, -21, 27, 86, 112, cs=2)
    X, Y, Z = m.X, m.Y, m.Z
    AX = np.abs(X)
    hw, hd = torso_tiers(Z)
    torso = ((AX < hw) & (np.abs(Y) < hd) & (Z < 104)) | ((AX < 12) & (Y > -13) & (Y < -11) & (Z > 80) & (Z < 98))
    zl = 91.0 + 0.45 * AX                                     # the lower edge of the drape: a V sweeping down to the clasp
    oval = (X / 23.0) ** 2 + (Y / 17.5) ** 2 < 1.0            # round in plan, not a box
    cowl = (Y < -9) & (Y > -15) & (AX < 22) & (Z > zl) & (Z < 106)
    cowl |= (Y < -9) & (Y > -17) & (AX < 20) & (AX > 5) & (Z > zl + 5) & (Z < 104)       # a second, thicker swag above it
    cowl |= oval & (Z > 100) & (Z < 106)                      # over the shoulders and round the neck
    cowl |= oval & (np.abs(Y) > 9) & (Z > 98) & (Z < 106)
    cowl &= oval | (Y < -9)
    rr = (X / 21.0) ** 2 + (Y / 16.0) ** 2
    cowl |= (rr < 1.0) & (rr > 0.55) & (Y > -10) & (Z > 104) & (Z < 110)                 # the roll standing up round the neck
    hood = ((X / 19.0) ** 2 + ((Y - 15.0) / 9.0) ** 2 + ((Z - 99.0) / 10.5) ** 2 < 1.0) & (Y > 9)
    cowl |= hood
    cowl &= ~torso
    cowl &= ~((X ** 2 + Y ** 2 < 7.5 ** 2) & (Z > 104))       # the neck's hole
    sub = np.stack(np.meshgrid([-0.8, 0.8], [-0.8, 0.8], [-0.8, 0.8], indexing="ij"), axis=-1).reshape(-1, 3)
    cen = np.stack([X, Y, Z], axis=-1).reshape(-1, 3)
    blocked = np.zeros(len(cen), bool)
    for o in sub:
        blocked |= in_grid(keep_out, cen + o)
    cowl &= ~blocked.reshape(m.n)
    m.fill(cowl, "green")
    fold = np.floor((Z - 0.45 * AX) / 2.9) % 3                # folds sweeping from the shoulders down to the clasp
    m.paint(cowl & (fold == 0), "green_d")
    m.paint(cowl & (fold == 2), "green_l")
    m.paint(cowl & (Z > 108), "green_l")
    m.paint(cowl & hood & (Y > 19), "green_d")
    emit(P, m, lim=((6, 14), (4, 8), (2, 4)), pref="x", shade=0.35, proud_p=0.5, proud=(0.2, 0.7), seed=83, cjit=0.04)
    # the clasp at the throat: a hollow gold square with a green stone
    cy = -15.0
    tb(-5.0, 5.0, cy - 2.2, cy, 92.0, 102.0, "gold")
    tb(-5.0, -2.8, cy - 3.2, cy - 2.0, 92.0, 102.0, "gold_l")
    tb(2.8, 5.0, cy - 3.2, cy - 2.0, 92.0, 102.0, "gold_l")
    tb(-2.8, 2.8, cy - 3.2, cy - 2.0, 99.8, 102.0, "gold_l")
    tb(-2.8, 2.8, cy - 3.2, cy - 2.0, 92.0, 94.2, "gold_l")
    tb(-2.8, 2.8, cy - 2.6, cy - 2.0, 94.2, 99.8, "gold_d")
    tb(-1.7, 1.7, cy - 3.6, cy - 2.4, 95.3, 98.7, "olive_l", bevel=0.14)
    return B, P


WHOLE = ["Body", "Head", "ArmL", "ArmR", "LegL", "LegR", "Cape", "Sword"]


def wholes(parts):
    """The limbs as the single rigid pieces they are while every elbow, knee, wrist and cape hinge is at rest."""
    return {"Body": Combo(parts["Body"], parts["Chest"]), "Head": parts["Head"], "ArmL": Combo(parts["ArmL"], parts["ForeL"]),
            "ArmR": Combo(parts["ArmR"], parts["ForeR"], parts["HandR"]), "LegL": Combo(parts["LegL"], parts["ShinL"]),
            "LegR": Combo(parts["LegR"], parts["ShinR"]), "Cape": Combo(*[parts[k] for k in ORDER if k.startswith("Cape")]),
            "Sword": parts["Sword"]}


def build_swordsman():
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
        [Combo(parts["ArmL"], parts["ForeL"]), Combo(parts["ArmR"], parts["ForeR"], parts["HandR"])], parts["Head"])]
    print("sculpted in %.1f s" % (time.time() - t0))
    return parts


# ---------------------------------------------------------------------------------------------------- checks

def pivot(key):
    return [round(c * U, 5) for c in JOINTS[key]]


def check_pose(parts, pts, label, **ang):
    axes = dict(LegL=("x", ang.get("legl", 0)), LegR=("x", ang.get("legr", 0)), ArmL=("x", ang.get("arml", 0)),
                ArmR=("x", ang.get("armr", 0)), Cape=("x", ang.get("cape", 0)), Head=("z", ang.get("head", 0)), Body=("x", 0))
    posed = {}
    for k in WHOLE:
        if k == "Sword":
            posed[k] = rotated(pts[k], parts["ArmR"].joint, "x", axes["ArmR"][1])
        else:
            posed[k] = rotated(pts[k], parts[k].joint, axes[k][0], axes[k][1])
    occ = {k: occ_grid(posed[k], 0.5) for k in WHOLE}
    bad = []
    for i, a in enumerate(WHOLE):
        for b in WHOLE[i + 1:]:
            if {a, b} in ({"Body", "LegL"}, {"Body", "LegR"}, {"Body", "Head"}, {"Sword", "ArmR"}):
                continue
            both = occ[a] & occ[b]
            n = int(both.sum())
            if n:
                idx = np.argwhere(both)
                lo = idx.min(axis=0) * 0.5 + SW_LO
                hi = idx.max(axis=0) * 0.5 + SW_LO
                bad.append("%s-%s:%d [x %.0f..%.0f y %.0f..%.0f z %.0f..%.0f]" % (a, b, n, lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]))
    low = min(float(p[:, 2].min()) for p in posed.values())
    print("CHECK %-14s lowest z %.1f u | overlaps: %s" % (label, low, "; ".join(bad) if bad else "none"))


# ##################################################################################################################
# Previews: a copy of king_b.py's stage (materials, lights, camera, montage).
# ##################################################################################################################

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
    if CPU_ONLY:
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
    path = os.path.join(V.PREVIEWS, "swordsman_%s.png" % name)
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
        scene.cycles.device = "CPU" if CPU_ONLY else "GPU"
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


CARRY = dict(armr=10.0, forer=25.0, handr=45.0)      # how the previews hold the sword: arm down, blade forward and down


def rig(obs):
    """Parent the objects as the engine does (after the export, which wants them loose)."""
    for key, ob in obs.items():
        if key in PARENT:
            ob.parent = obs[PARENT[key]]
    obs["Sword"].parent = obs["HandR"]


def pose(obs, **ang):
    """Turn joints by degrees about x (Head: about z): legl, legr, shinl, shinr, arml, armr, forel, forer, handr, chest,
    body, head; cape (every panel of the top row), cape1 .. cape3 (the rows below, each relative to the one above).
    Positive swings a hanging limb backwards. The sword sits in the fist and moves with the hand."""
    for key, ob in obs.items():
        parent = "HandR" if key == "Sword" else PARENT.get(key)
        base = np.array(JOINTS[parent], np.float64) if parent else np.zeros(3)
        ob.location = [float(v) * U for v in np.array(JOINTS[key], np.float64) - base]
        if key.startswith("Cape") and len(key) == 6:
            a = ang.get("cape" if key[5] == "0" else "cape" + key[5], 0.0)
        else:
            a = ang.get(key.lower(), 0.0)
        ob.rotation_euler = (0, 0, math.radians(a)) if key == "Head" else (math.radians(a), 0, math.radians(ang.get(key.lower() + "_z", 0.0)))


def want(name):
    return VIEWS is None or name in VIEWS


def main():
    t0 = time.time()
    V.reset_scene()
    parts = build_swordsman()
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
    print("SWORDSMAN size: x %.3f m (%.2f..%.2f), y %.3f m (%.2f..%.2f), height %.4f m (lowest %.4f)" % (
        (hi[0] - lo[0]) * U, lo[0] * U, hi[0] * U, (hi[1] - lo[1]) * U, lo[1] * U, hi[1] * U, hi[2] * U, lo[2] * U))
    W = wholes(parts)
    pts = {k: part_points(W[k], step=0.6, shrink=0.4, cores=False) for k in WHOLE}
    check_pose(W, pts, "rest")
    check_pose(W, pts, "walk A", legl=35, legr=-35, arml=-35, armr=35, cape=20)
    check_pose(W, pts, "walk B", legl=-35, legr=35, arml=35, armr=-35, cape=20)

    obs = {}
    total = 0
    for key in ORDER:
        ob = make_object(parts[key])
        obs[key] = ob
        V.export_gltf(ob, collision="none", extra=dict(pivot=pivot(key), part=key, triangles=int(ob["triangles"]),
                                                       blocks=int(len(parts[key].c))))
        total += int(ob["triangles"])
        kd = parts[key].kind_per_tri
        print("  %-6s %6d blocks (%d core)  %7d triangles (%d core)  %6d faces" % (
            key, len(parts[key].c), int(parts[key].core.sum()), ob["triangles"], int((kd == KINDS.index("core")).sum()), ob["voxel_faces"]))
    print("SWORDSMAN triangles in all: %d  (%.1f s)" % (total, time.time() - t0))
    sw = parts["Sword"]
    blade_dir = [round(float(v), 5) for v in sw.frame.R @ np.array([0.0, 0.0, -1.0])]
    # The character file, in SM_KingB.json's format. He has no scabbard: "has_sheath" says so, and the scabbard fields
    # the King's importer reads are filled with "stay in the fist" (no turn, the grip's own position) so that it runs.
    meta = dict(height=HEIGHT, radius=RADIUS, voxel=U, elbow_l=ELBOW["L"], elbow_r=ELBOW["R"],
                cape=dict(cols=CAPE_COLS, rows=CAPE_ROWS), has_sheath=False,
                parts={key: dict(mesh=PREFIX + key, pivot=pivot(key), parent=PARENT.get(key, "")) for key in ORDER},
                sword=dict(blade_dir=blade_dir, has_sheath=False, length=round(abs(sw.tip_local) * U, 5),
                           grip=pivot("Sword"), tip=[round(float(v) * U, 5) for v in sw.blade_tip],
                           sheath_dir=blade_dir, sheath_pos=pivot("Sword"),
                           delta=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]))
    with open(os.path.join(V.MESHES, NAME + ".json"), "w") as f:
        json.dump(meta, f, indent=1)
    print("wrote %s.json" % NAME)
    if NO_RENDER:
        return

    to_preview(obs, parts)
    stage()
    rig(obs)
    Pv = V.PREVIEWS
    p = lambda n: os.path.join(Pv, "swordsman_%s.png" % n)
    pose(obs, **CARRY)
    if want("hero"):
        pose(obs, head=10.0, arml=-8.0, forel=-18.0, armr_z=40.0, **CARRY)       # the arm turned in: the blade's flat to the camera
        hero = shot("hero", az=-14, el=-9, dist=3.6, target=(-0.03, 0, 0.86), res=(900, 1250), lens=66)
        montage([REF, hero], p("compare"), H=1250)
        pose(obs, **CARRY)
    if want("sides"):
        tiles = [shot("front", 0, 2, res=(720, 960)), shot("right", -90, 2, res=(720, 960)),
                 shot("back", 180, 4, res=(720, 960)), shot("left", 90, 2, res=(720, 960))]
        montage(tiles, p("sides"), H=960)
    if want("face"):
        tiles = [shot("face_front", 0, 0, dist=6.0, target=(0, 0, 1.47), res=(800, 800), lens=230),
                 shot("face", -30, -8, dist=6.0, target=(0, 0, 1.47), res=(800, 800), lens=230),
                 shot("face_side", -90, 0, dist=6.0, target=(0, 0, 1.47), res=(800, 800), lens=230)]
        montage(tiles, p("faces"), H=800)
    if want("game"):
        tiles = [shot("game_front", 25, 40, dist=7.0, res=(720, 960)), shot("game_back", 205, 40, dist=7.0, res=(720, 960))]
        montage(tiles, p("game"), H=960)
    if want("rest"):
        pose(obs)                                             # exactly as exported: every joint at zero
        tiles = [shot("rest_front", -29, 0, dist=7.0, res=(720, 960)), shot("rest_right", -90, 2, dist=7.0, res=(720, 960))]
        montage(tiles, p("rest"), H=960)
        pose(obs, **CARRY)
    if want("walk"):
        pose(obs, legl=30, shinl=-10, legr=-25, shinr=35, arml=-30, forel=-25, armr=35, forer=10, handr=45, chest=-6, cape=20, cape1=8, cape2=6)
        tiles = [shot("walk_front", -29, 0, dist=7.0, res=(720, 960)), shot("walk_left", 90, 2, dist=7.0, res=(720, 960)),
                 shot("walk_back", 150, 8, dist=7.0, res=(720, 960)), shot("walk_right", -90, 2, dist=7.0, res=(720, 960))]
        montage(tiles, p("walk"), H=960)
        pose(obs, **CARRY)
    if want("jump"):
        pose(obs, legl=-70, shinl=95, legr=-45, shinr=105, arml=-70, forel=-40, armr=-55, forer=-30, handr=20, chest=-8, head=0,
             cape=38, cape1=12, cape2=8, cape3=6)
        obs["Body"].location.z += 0.35
        for k in ("LegL", "LegR", "Sword"):
            if obs[k].parent is None:
                obs[k].location.z += 0.35
        tiles = [shot("jump_front", -29, 0, dist=7.6, target=(0, 0, 1.1), res=(720, 960)), shot("jump_left", 90, 2, dist=7.6, target=(0, 0, 1.1), res=(720, 960)),
                 shot("jump_back", 150, 8, dist=7.6, target=(0, 0, 1.1), res=(720, 960)), shot("jump_right", -90, 2, dist=7.6, target=(0, 0, 1.1), res=(720, 960))]
        montage(tiles, p("jump"), H=960)
        pose(obs, **CARRY)
    print("done in %.1f s" % (time.time() - t0))


main()
