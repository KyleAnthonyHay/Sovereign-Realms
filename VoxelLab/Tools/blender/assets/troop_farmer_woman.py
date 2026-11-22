"""The FARMER WOMAN (References/Remake/farmer_woman.png), built the same way as the other troops (troop_archer.py,
troop_builder.py ...) and King David (king_b.py): rigid parts of INDIVIDUAL bevelled blocks of mixed sizes, each
exported on its own with its mesh origin at its joint, and swung about those joints by the engine. Part names,
hierarchy and joint conventions are King David's (see RIG below).

    Blender -b --factory-startup --python Tools/blender/assets/troop_farmer_woman.py -- [--no-render] [--views hero,sides,...] [--fast]
    (FARMER_CPU=1 or KING_CPU=1 renders on the CPU; Cycles on the Metal GPU can crash here)

Units: "u" = 1.25 cm. World axes: +X is her LEFT (she faces -Y), z = 0 is the ground between her feet.
Extra parts next to the King's (the archer's pattern for Bow, Quiver and Arrow): Sickle (in the left fist; rides on
ForeL), Basket (a woven basket of carrots hanging from the right forearm; rides on ForeR) and Pouch (the leather pouch
on her left hip; rides on Body). SM_FarmerWoman.json carries "sickle", "basket" and "pouch" entries for them. She has
no cape; the long skirt (with its half of the apron) rides on the thighs, as the archer's does.

THE HEAD is put together from two other troops, on purpose:
    the FACE STRUCTURE is the archer's (troop_archer.py): the 24 x 20 x 22 u skull on the Head joint at z 98, one smooth
        skin plate in front of it, a short one-bar mouth, a small low nose with the shadow under it, the ears with their
        hollows, square gold earrings;
    the EYE STRUCTURE is the swordsman's (troop_swordsman.py): a 1 u grid in front of the face, a 6 x 3 u white with a
        3 x 3 u pupil one u in from its inner end, one thick 8 x 3 u brow resting on each eye and standing a layer
        proud of it, a glint in the pupil's upper inner corner; emitted with the swordsman's block sizes.

The block engine (Part, Grid, emit, cull, shading, mesh building, preview stage) is a copy of troop_archer.py's (itself
king_b.py's), kept in this file so that nothing here depends on those scripts while they are being reworked.
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
FAST = "--fast" in ARGS
VIEWS = set(ARGS[ARGS.index("--views") + 1].split(",")) if "--views" in ARGS else None
if os.environ.get("FARMER_CPU"):
    os.environ["KING_CPU"] = "1"

U = 0.0125
NAME = "SM_FarmerWoman"
PREFIX = NAME + "_"
SHOT_PREFIX = "farmer_woman_"
REF = os.path.join(V.ROOT, "References", "Remake", "farmer_woman.png")

# ---------------------------------------------------------------------------------------------------- RIG
# THE PART / JOINT TABLE (one place; mirrors king_b.py's ORDER / PARENT / JOINTS, without the scabbard and the cape).
# The figure is a tree of rigid parts (PARENT; no entry = the figure's root). Body is the pelvis, Chest turns on it at
# the waist; each arm is an upper arm and a forearm (the left with its hand; the right hand is its own part, HandR,
# turning at the wrist); each leg is a thigh (with its half of the skirt and the apron) and a shin (with the boot).
# Joints marked None are set while the parts are built (they depend on the arm frames).
ORDER = ["Body", "Chest", "Head", "ArmL", "ForeL", "ArmR", "ForeR", "HandR", "LegL", "ShinL", "LegR", "ShinR",
         "Sickle", "Basket", "Pouch"]
PARENT = {"Chest": "Body", "Head": "Chest", "ArmL": "Chest", "ArmR": "Chest", "ForeL": "ArmL", "ForeR": "ArmR", "HandR": "ForeR",
          "ShinL": "LegL", "ShinR": "LegR",
          "Sickle": "ForeL", "Basket": "ForeR", "Pouch": "Body"}
CAPE_COLS, CAPE_ROWS = 0, 0                   # no cape
ELBOW = {"L": 55.0, "R": 75.0}                # the bend the forearms are modelled with (degrees): the right one carries the basket
WRIST_L = 20.0                                # the left fist is modelled turned up this much more (it holds the sickle upright)
KNEE_Z = 28.0
HIP_X, HIP_Z = 9.0, 56.0
LIFT = HIP_Z - 52.0                           # the pelvis, belt and waist were first sculpted with the hips at 52
SHOULDER_X, SHOULDER_Z = 23.0, 94.0
ELBOW_Z = 72.0                                # in the arm's own frame
WRIST_Z = 52.0
TOP = 140.0                                   # nothing stands above this (the top of the piled locs)
HEIGHT, RADIUS, STRIDE = 1.66, 0.40, 1.7      # metres, for the character JSON
JOINTS = {                                    # u, world
    "Body": (0, 0, 54 + LIFT), "Chest": (0, 0, 70 + LIFT), "Head": (0, 0, 98),
    "ArmL": (SHOULDER_X, 0, SHOULDER_Z), "ArmR": (-SHOULDER_X, 0, SHOULDER_Z),
    "ForeL": None, "ForeR": None, "HandR": None,
    "LegL": (HIP_X, 0, HIP_Z), "LegR": (-HIP_X, 0, HIP_Z),
    "ShinL": (HIP_X, 0, KNEE_Z), "ShinR": (-HIP_X, 0, KNEE_Z),
    "Sickle": None,                           # the middle of the grip, in her left fist
    "Basket": None,                           # the top of the handle, where it hangs on the right forearm
    "Pouch": (17.0, -2.0, 69.0),              # where its straps hang from the belt, on her left hip
}

MATN = ["paint", "gold", "metal", "wool"]
KINDS = ["cloth", "skin", "hair", "leather", "gold", "metal", "fur", "gem", "core", "blade"]
_PAL = [
    # name        colour     slot     preview kind
    ("gold",     "#FFB616", "gold", "gold"), ("gold_l", "#FFD63E", "gold", "gold"), ("gold_d", "#E39510", "gold", "gold"),
    ("gold_dd",  "#A2640C", "gold", "gold"),
    ("blade",    "#D2CCC8", "metal", "blade"), ("blade_l", "#ECE7E1", "metal", "blade"), ("blade_d", "#B3ADAD", "metal", "blade"),
    ("skin",     "#8E4A20", "paint", "skin"), ("skin_l", "#A25826", "paint", "skin"), ("skin_d", "#763B18", "paint", "skin"),
    ("skin_dd",  "#663216", "paint", "skin"), ("lip", "#642818", "paint", "skin"),
    ("loc",      "#4A2D1B", "paint", "hair"), ("loc_l", "#613C24", "paint", "hair"), ("loc_d", "#382112", "paint", "hair"),
    ("loc_dd",   "#27170C", "paint", "hair"),
    ("brow",     "#22140C", "paint", "hair"),
    ("green",    "#4E6622", "paint", "cloth"), ("green_l", "#5F7A29", "paint", "cloth"), ("green_d", "#3F531A", "paint", "cloth"),
    ("green_dd", "#2F3E15", "paint", "cloth"),
    ("apron",    "#587226", "paint", "cloth"), ("apron_l", "#66832C", "paint", "cloth"), ("apron_d", "#4B6220", "paint", "cloth"),
    ("cream",    "#E2C68C", "paint", "cloth"), ("cream_l", "#F0DAA6", "paint", "cloth"), ("cream_d", "#C8AA74", "paint", "cloth"),
    ("cream_dd", "#AC8F5E", "paint", "cloth"),
    ("belt",     "#7B4A24", "paint", "leather"), ("belt_l", "#96602F", "paint", "leather"), ("belt_d", "#5A3418", "paint", "leather"),
    ("belt_dd",  "#40240F", "paint", "leather"),
    ("boot",     "#6E4425", "paint", "leather"), ("boot_l", "#8E5C30", "paint", "leather"), ("boot_d", "#523019", "paint", "leather"),
    ("wood",     "#80502A", "paint", "leather"), ("wood_l", "#9A6535", "paint", "leather"), ("wood_d", "#63391B", "paint", "leather"),
    ("wick",     "#D29430", "paint", "leather"), ("wick_l", "#E8B048", "paint", "leather"), ("wick_d", "#B27820", "paint", "leather"),
    ("wick_dd",  "#7C5012", "paint", "leather"),
    ("carrot",   "#E8721A", "paint", "cloth"), ("carrot_l", "#F58C2E", "paint", "cloth"), ("carrot_d", "#C85A10", "paint", "cloth"),
    ("leaf",     "#6C9C2A", "paint", "cloth"), ("leaf_l", "#8ABA3A", "paint", "cloth"), ("leaf_d", "#527C1E", "paint", "cloth"),
    ("sole",     "#4C2E18", "paint", "leather"),
    ("white",    "#F4EFE4", "paint", "gem"), ("pupil", "#15100E", "paint", "hair"), ("gem_w", "#FFF4DA", "paint", "gem"),
    ("core",     "#17120F", "paint", "core"),
]
PN = [None] + [p[0] for p in _PAL]
PI = {n: i for i, n in enumerate(PN)}
PRGB = np.array([[0, 0, 0]] + [[int(p[1][i:i + 2], 16) / 255.0 for i in (1, 3, 5)] for p in _PAL], np.float32)
PMAT = np.array([0] + [MATN.index(p[2]) for p in _PAL], np.int32)
PKIND = np.array([0] + [KINDS.index(p[3]) for p in _PAL], np.int32)


# ==================================================================================================== ENGINE
# (copied from king_b.py: small maths, parts and blocks, chamfered boxes, culling, baked shading, mesh, swept volumes)

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
NOSHADE = ("white", "pupil", "lip", "gem_w", "core", "brow", "sole")


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
AO_LO = np.array([-80.0, -68.0, -4.0])
AO_N = (320, 248, 290)


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



# ==================================================================================================== THE FARMER WOMAN
# Shapes are sculpted on 2 u cells (1 u for the eyes) and MERGED into the fewest, largest boxes by emit(); the apron,
# its wheat emblem, buckles, earrings, hair cuffs, fists, the carrots and the sickle's handle are direct blocks.

GY, GZ = -3.5, 45.8                           # the axis a fist closes round: along the forearm frame's y, at z GZ; its middle at y GY
DX = SHOULDER_X - 25.0                        # the King's hand blocks are written about x 25
SKIN_HAND = ("skin_d", "skin", "skin_l")
GLOVE = ("belt_d", "belt", "belt_l")          # her leather work gloves
SKIRT = ((40, HIP_Z, 17, 10), (30, 40, 19, 12), (24, 30, 21, 14))        # the skirt's tiers: z0, z1, outer x, half depth (u)
APRON_TILT = 11.5                             # the apron leans forward over the flaring skirt (degrees)


def build_leg(s):
    """-> (thigh, shin). The thigh carries its half of the long green skirt (three flaring tiers and the cream
    underskirt showing below), its half of the apron (gold border, half of the wheat emblem) and, on her right, the
    cream cloth tucked in at the belt; the shin the boot with its buckled strap and, hidden inside the skirt, the
    drum the knee turns on."""
    side = "L" if s > 0 else "R"
    P, Q = Part("Leg" + side), Part("Shin" + side)
    g = Grid(IDENT, 0, 26, -18, 18, 0, 68, cs=2, sx=s)
    XS, Y, Z = g.XS, g.Y, g.Z
    g.box(3, 15, -6, 6, 24, HIP_Z, "green_dd")                # thigh (never seen: the skirt is solid round it)
    sk = np.zeros(g.n, bool)
    for (z0, z1, xo, hy) in SKIRT:                            # the half of the skirt that swings with this leg ...
        sk |= g.bm(0, xo, -hy, hy, z0, z1)
    drum = (XS > 0) & (XS < 17) & (Y ** 2 + (Z - HIP_Z) ** 2 < 10.7 ** 2) & (Z > HIP_Z)      # ... ending in a drum about the hip axis
    g.fill(sk | drum, "green")
    g.paint(sk & (((g.ix + 2 * (g.iy // 3)) % 4) == 0) & (Z < 46), "green_d")               # pleats
    g.paint(sk & (hash3(g.ix // 2, g.iy // 2, g.iz * 0, 7) > 0.8) & (Z < 40), "green_l")
    for (z0, z1, xo, hy) in SKIRT[1:]:
        g.paint(g.bm(0, xo, -hy, hy, z1 - 2, z1) & ~g.bm(0, xo - 2, -hy + 2, hy - 2, z1 - 2, z1), "green_l")     # the lip of each tier
    g.box(0, 21, -14, 14, 20, 24, "cream")                    # the cream underskirt below the hem
    ru = g.bm(0, 21, -14, 14, 20, 24)
    g.paint(ru & (((g.ix + g.iy) % 3) == 0), "cream_d")
    g.paint(ru & (Z < 22) & (((g.ix + g.iy) % 3) == 1), "cream_l")
    emit(P, g, lim=((2, 6), (4, 10), (6, 12)), pref="z", lims={"green_dd": (8, 16), "cream": ((4, 6), (4, 6), (2, 4)),
                                                                "cream_d": ((2, 2), (2, 2), (4, 4)), "cream_l": ((2, 4), (2, 4), (2, 2))}, seed=20 + s)
    # ---- the apron: a flat panel hanging from the belt in front of the skirt, leaning forward with it; this half's
    # share of it (the two halves meet at x 0), the gold border down its side and along its foot, half the wheat ear
    Af = IDENT.sub(RX(-APRON_TILT), (0.0, -10.0, 58.0))
    a = lambda *q, **k: P.blk(Af, *q, sx=s, **k)
    a(0.0, 8.2, -11.4, -10.2, 43.0, 58.0, "apron", bevel=0.03)
    a(0.0, 8.2, -11.4, -10.2, 27.0, 43.0, "apron", bevel=0.03, tint=0.96 if s > 0 else 1.03)
    for (z0, z1, nm) in ((27.0, 37.0, "gold"), (37.0, 48.0, "gold_l"), (48.0, 58.0, "gold")):     # the border down the side
        a(8.0, 10.4, -11.9, -10.2, z0, z1, nm if s > 0 else {"gold": "gold_l", "gold_l": "gold"}[nm])
    a(0.0, 5.0, -11.9, -10.2, 24.4, 27.2, "gold")                                        # ... and along the foot
    a(5.0, 10.4, -11.9, -10.2, 24.4, 27.2, "gold_d")
    a(0.0, 6.4, -11.75, -11.3, 29.4, 30.4, "gold_d", bevel=0.1)                          # the thin second line inside it
    a(5.6, 6.4, -11.75, -11.3, 30.4, 56.0, "gold_d", bevel=0.1)
    a(0.0, 0.75, -12.0, -11.3, 33.0, 47.0, "gold_d", bevel=0.1)                          # the wheat ear: the stalk ...
    a(0.0, 2.2, -12.1, -11.3, 31.6, 33.2, "gold")                                        # ... its foot ...
    for i, z in enumerate((35.4, 39.2, 43.0)):                                           # ... three pairs of grains, each rising outward ...
        a(0.9, 2.5, -12.3, -11.3, z, z + 2.6, "gold_l" if i % 2 else "gold", bevel=0.15)
        a(2.1, 3.9, -12.3, -11.3, z + 1.3, z + 3.9, "gold" if i % 2 else "gold_l", bevel=0.15)
    a(0.0, 1.2, -12.3, -11.3, 47.0, 51.0, "gold_l", bevel=0.15)                          # ... and the one on top
    if s < 0:
        # the cream cloth tucked in at the belt on her right, hanging in three folds over the apron's edge
        a(8.8, 11.2, -13.3, -11.8, 40.0, 60.0, "cream_l")
        a(11.2, 13.4, -13.6, -11.8, 44.0, 60.0, "cream")
        a(13.4, 15.6, -13.1, -11.6, 37.0, 60.0, "cream_d")
        a(8.8, 11.2, -13.5, -13.1, 40.0, 42.0, "cream_d", bevel=0.1)                     # the stitched ends
        a(13.4, 15.6, -13.3, -12.9, 37.0, 39.0, "cream_dd", bevel=0.1)
    # ---- the shin
    g = Grid(IDENT, 0, 26, -18, 18, 0, 68, cs=2, sx=s)
    XS, Y, Z = g.XS, g.Y, g.Z
    g.fill((XS > 5) & (XS < 13) & (Y ** 2 + (Z - KNEE_Z) ** 2 < 26.0) & (Z > 22), "boot_d")     # the knee's drum
    g.box(3, 15, -6, 6, 6, 26, "boot")                        # boot shaft (its top is under the skirt)
    g.box(1, 17, -8, 8, 12, 18, "belt_d")                     # the strap round the shaft
    g.box(3, 17, -12, 6, 0, 6, "boot")                        # foot
    foot = g.bm(3, 17, -12, 6, 0, 6)
    g.carve(foot & (Y < -10) & (Z > 4))
    g.paint(foot & (Y < -8), "boot_l")                        # toe cap
    g.paint(foot & (Z < 2), "sole")
    emit(Q, g, lim=(8, 16), lims={"sole": (10, 22), "belt_d": ((6, 10), (6, 10), (6, 6))}, seed=24 + s)
    b = lambda *q, **k: Q.blk(IDENT, *q, sx=s, **k)
    b(2.3, 17.7, -12.8, 6.8, 0.0, 1.5, "sole")                # the welt of the sole
    b(0.4, 17.6, -8.6, 8.6, 17.0, 18.8, "belt")               # the lips of the strap
    b(0.4, 17.6, -8.6, 8.6, 11.2, 13.0, "belt_dd")
    b(5.4, 12.6, -9.8, -8.0, 16.6, 18.8, "gold_l")            # its buckle: a hollow gold square on the front
    b(5.4, 12.6, -9.8, -8.0, 11.2, 13.4, "gold")
    b(5.4, 7.6, -9.8, -8.0, 13.4, 16.6, "gold")
    b(10.4, 12.6, -9.8, -8.0, 13.4, 16.6, "gold_d")
    b(7.6, 10.4, -8.9, -8.0, 13.4, 16.6, "belt_dd")
    return P, Q


def fist(part, frame, s, pal=SKIN_HAND):
    """A closed fist (the King's sword hand): wrist, palm, four finger bars side by side along the grip, thumb.
    pal = (dark, middle, light) colours: skin, or a glove's leather."""
    d, m, l = pal
    h = lambda *q, **k: part.blk(frame, *q, sx=s, **k)
    h(21.5 + DX, 28.5 + DX, -4.6, 3.2, 49.4, 53.6, d)
    h(20.4 + DX, 30.2 + DX, GY - 5.1, GY + 5.5, 43.6, 51.0, m)
    for i, (nm, dz) in enumerate(((l, 0.3), (m, 0.0), (d, 0.2), (m, 0.6))):
        y0 = GY - 5.3 + i * 2.75
        h(19.6 + DX, 31.0 + DX, y0, y0 + 2.75, 40.4 + dz, 46.4, nm)
    h(18.2 + DX, 21.6 + DX, GY - 6.0, GY + 1.6, 45.6, 49.4, l)
    return frame.w((s * (24.8 + DX), GY, GZ))                  # the middle of what it holds


def build_arm(s):
    """-> (upper arm, forearm). The elbow is where the forearm's frame is bent. The left forearm carries its fist (which
    holds the sickle); the right hand is its own part (HandR), and the basket hangs on the right forearm."""
    side = "L" if s > 0 else "R"
    P = Part("Arm" + side)
    A = Frame().sub(RY(-s * 6.0), P.joint)
    cx = SHOULDER_X
    Fo = A.sub(RX(-ELBOW[side]), (s * cx, 0, ELBOW_Z))
    JOINTS["Fore" + side] = tuple(float(v) for v in A.w((s * cx, 0, ELBOW_Z)))
    Q = Part("Fore" + side)
    # ---- upper arm: the blouse's big puffed sleeve, gathered into a cuff above the elbow, the bare arm below it
    g = Grid(A, cx - 10, cx + 12, -12, 12, 66, 102, cs=2, sx=s)
    XS, Y, Z = g.XS, g.Y, g.Z
    g.box(cx - 6, cx + 6, -6, 6, 72, 80, "skin")
    g.box(cx - 8, cx + 8, -8, 8, 78, 82, "cream_d")           # the gathered cuff
    g.box(cx - 8, cx + 10, -10, 10, 82, 92, "cream")          # the puff: a wide lower tier ...
    g.box(cx - 8, cx + 8, -8, 8, 92, 98, "cream_l")           # ... stepping in to the top
    g.fill((XS > cx - 6) & (XS < cx + 6) & (Y ** 2 + (Z - SHOULDER_Z) ** 2 < 36.0), "cream")       # the drum the arm turns on
    g.carve(g.bm(cx + 8, cx + 10, -10, 10, 82, 92) & (np.abs(Y) > 8))                              # rounded outer corners
    puff = g.isn("cream")
    g.paint(puff & (((g.ix + g.iy) % 4) == 0) & (Z > 84), "cream_d")                               # gathers
    g.paint(puff & (Z < 84), "cream_l")
    emit(P, g, lim=(6, 14), lims={"cream_d": ((2, 4), (2, 4), (4, 8)), "cream_l": (6, 12), "skin": (8, 12)}, seed=31 + s)
    # ---- forearm (bent frame): elbow drum, bare skin, a leather bracer banded at both ends
    g = Grid(Fo, cx - 10, cx + 10, -12, 12, 36, 80, cs=2, sx=s)
    XS, Y, Z = g.XS, g.Y, g.Z
    g.fill((XS > cx - 6) & (XS < cx + 6) & (Y ** 2 + (Z - ELBOW_Z) ** 2 < 36.0), "skin_d")         # the drum the elbow turns on
    g.box(cx - 6, cx + 6, -6, 6, 64, 72, "skin")
    g.box(cx - 6, cx + 6, -6, 6, 54, 64, "belt")
    Q.bias = len(P._ch)
    emit(Q, g, lim=(8, 14), seed=41 + s)
    f = lambda *q, **k: Q.blk(Fo, *q, sx=s, **k)
    f(cx - 7.2, cx + 7.2, -7.2, 7.2, 61.6, 64.6, "belt_l")    # the bracer's upper band ...
    f(cx - 7.2, cx + 7.2, -7.2, 7.2, 53.6, 56.6, "gold")      # ... and the gold band at the wrist
    f(cx - 7.6, cx + 7.6, -7.6, 7.6, 53.4, 54.6, "gold_d")
    f(cx + 6.0, cx + 7.0, -2.0, 2.0, 57.4, 60.8, "belt_d")    # a strap and a stud on the outside
    f(cx + 6.8, cx + 7.5, -1.0, 1.0, 58.1, 60.1, "gold")
    if s > 0:
        # the sickle hand: the fist is modelled turned up a little more at the wrist, so the sickle stands upright
        Hf = Fo.sub(RX(-WRIST_L), (s * cx, 0.0, WRIST_Z))
        f(cx - 3.5, cx + 3.5, -4.4, 3.4, 49.0, 53.0, "belt_d")
        grip = fist(Q, Hf, s, GLOVE)
        P.sickle_part = build_sickle(Hf, grip, s)
    else:
        JOINTS["HandR"] = tuple(float(v) for v in Fo.w((s * cx, -0.5, WRIST_Z)))
        H = Part("HandR")
        fist(H, Fo, s, GLOVE)
        P.hand_part = H
        P.basket_part = build_basket(Fo, s)
    return P, Q


SICKLE_FOOT, SICKLE_NECK = -10.0, 16.0        # along the handle from the fist: its foot, where the blade starts (u)
SICKLE_R = 13.0                               # the radius of the blade's outer edge


def build_sickle(Hf, grip, s):
    """The sickle as its own part, origin at the middle of the grip, modelled as it stands in her left fist. Its frame:
    +z up the handle (the axis the fist closes round), +x the way the blade curves (outward, to her left), y through
    the flat of the blade."""
    JOINTS["Sickle"] = tuple(float(v) for v in grip)
    P = Part("Sickle")
    bz = Hf.R @ np.array([0.0, -1.0, 0.0])
    bx = Hf.R @ np.array([float(s), 0.0, 0.0])
    S = Frame(np.stack([bx, np.cross(bz, bx), bz], axis=1), grip)
    P.frame = S
    b = lambda *q, **k: P.blk(S, *q, **k)
    cuts = (SICKLE_FOOT + 2.0, -5.0, 1.0, 7.0, SICKLE_NECK - 2.4)
    for i in range(4):                                        # the wooden handle
        b(-1.7, 1.7, -1.7, 1.7, cuts[i], cuts[i + 1], ("wood", "wood_d", "wood", "wood_l")[i], bevel=0.12)
    b(-2.4, 2.4, -2.4, 2.4, SICKLE_FOOT, SICKLE_FOOT + 2.6, "gold")                      # the gold cap at its foot ...
    b(-2.3, 2.3, -2.3, 2.3, 7.0, 9.6, "gold_l")                                          # ... a band above the fist ...
    b(-2.4, 2.4, -2.4, 2.4, SICKLE_NECK - 2.6, SICKLE_NECK + 0.4, "gold_d")              # ... and the ferrule the blade sits in
    # the blade: a crescent in the x-z plane, one 2 u cell thick: what lies inside the outer circle and outside an
    # inner one set off toward the open side, so it is broad where it leaves the handle and runs to a point
    R0 = SICKLE_R
    cx0, cz0 = R0 - 1.0, SICKLE_NECK + 1.0
    g = Grid(S, -4, 30, -1, 1, 8, 36, cs=2)
    X, Z = g.X, g.Z
    out = (X - cx0) ** 2 + (Z - cz0) ** 2 < R0 ** 2
    inn = (X - cx0 - 1.3) ** 2 + (Z - cz0 + 2.7) ** 2 < (R0 - 2.1) ** 2
    blade = out & ~inn & ~((X < 8) & (Z < SICKLE_NECK))
    g.fill(blade, "blade_l")
    edge = blade & (shift(inn, 0, -1, False) | shift(inn, 2, 1, False))                  # the cutting edge, on the inside of the curve
    g.paint(edge, "blade")
    emit(P, g, lim=(2, 6), shade=0.3, proud_p=0.0, seed=91)
    P.tip = S.w((float(X[blade].max()), 0.0, float(Z[blade & (X >= X[blade].max() - 0.1)].min())))
    return P


BASKET_DROP = 9.0                             # the handle's top stands this far above the middle of the forearm (u)
BASKET_RIM = -28.0                            # the rim, below the handle's top


def build_basket(Fo, s):
    """The woven basket of carrots as its own part: it hangs by its hoop handle on her right forearm, clear of the
    skirt. Modelled upright (it hangs plumb); origin at the top of the handle, over the middle of the forearm."""
    mid = Fo.w((s * SHOULDER_X, 0.0, (ELBOW_Z + WRIST_Z) / 2 + 1.0))
    joint = mid + np.array([s * 1.0, 0.0, BASKET_DROP])
    JOINTS["Basket"] = tuple(float(v) for v in joint)
    P = Part("Basket")
    Bf = Frame(np.eye(3), joint)
    P.frame = Bf
    zr = BASKET_RIM
    g = Grid(Bf, -10, 10, -10, 10, zr - 14, zr, cs=2)
    X, Y, Z = g.X, g.Y, g.Z
    AX, AY = np.abs(X), np.abs(Y)
    g.fill((AX < 8) & (AY < 8) & (Z < zr - 8), "wick")        # the narrower foot ...
    g.fill((Z > zr - 8) & ~((AX > 8) & (AY > 8)), "wick")     # ... and the wider body, its corners cut
    body = g.solid()
    g.paint(body & (((g.ix + g.iy + g.iz) % 2) == 0), "wick_d")                          # the weave: a chequer of light and dark
    g.paint(body & (Z < zr - 12), "wick_dd")
    g.paint(body & (Z > zr - 2) & (AX < 8) & (AY < 8), "wick_dd")                        # the dark inside, under the carrots
    emit(P, g, lim=(2, 4), lims={"wick_dd": (6, 12)}, shade=0.25, proud_p=0.5, proud=(0.1, 0.4), seed=95)
    b = lambda *q, **k: P.blk(Bf, *q, **k)
    for sg in (1, -1):                                        # the rim: four thick bars standing proud
        b(-10.8, 10.8, sg * 8.6, sg * 10.8, zr - 1.0, zr + 1.6, "wick_l" if sg < 0 else "wick")
        b(sg * 8.6, sg * 10.8, -8.6, 8.6, zr - 1.0, zr + 1.6, "wick" if sg < 0 else "wick_l")
        b(sg * 9.2, sg * 11.0, -1.3, 1.3, zr + 1.6, 1.4, "wick_d")                        # the handle's two posts ...
    b(-11.0, 11.0, -1.3, 1.3, -0.9, 1.4, "wick")                                         # ... and the bar that lies on the forearm
    b(-8.2, 8.2, -8.2, 8.2, zr - 16.2, zr - 14.0, "wick_dd")                             # the foot ring
    # the carrots: each a fat orange root (two steps to the point, which is down in the basket) with a tuft of leaves,
    # leaning this way and that; kept under the forearm, which passes over the middle of the basket
    spots = ((-5.2, -5.6, -24.0, 20.0), (-0.6, -6.2, 16.0, 26.0), (4.6, -5.4, 30.0, 14.0), (-5.6, -0.4, -30.0, -6.0),
             (0.0, -1.0, 6.0, 10.0), (5.2, 0.4, 28.0, -10.0), (-4.4, 5.0, -22.0, -24.0), (1.4, 5.6, 12.0, -28.0), (5.6, 5.4, 32.0, -20.0))
    for i, (px, py, ay, ax) in enumerate(spots):
        Cf = Bf.sub(RX(ax) @ RY(ay), (px, py, zr - 2.0))
        c = lambda *q, **k: P.blk(Cf, *q, cull=False, **k)
        nm = ("carrot", "carrot_l", "carrot_d")[i % 3]
        c(px - 1.3, px + 1.3, py - 1.3, py + 1.3, zr - 5.0, zr - 0.5, PN[PDN[PI[nm]]], bevel=0.15)
        c(px - 2.0, px + 2.0, py - 2.0, py + 2.0, zr - 0.5, zr + 4.6, nm, bevel=0.15)
        c(px - 1.5, px + 1.5, py - 1.5, py + 1.5, zr + 4.6, zr + 6.0, PN[PDN[PI[nm]]], bevel=0.15)
        for j, (lx, ly, lh) in enumerate(((-1.1, -0.9, 3.4), (1.0, -0.2, 4.2), (-0.2, 1.1, 2.8))):
            c(px + lx - 0.8, px + lx + 0.8, py + ly - 0.8, py + ly + 0.8, zr + 6.0, zr + 6.0 + lh, ("leaf", "leaf_l", "leaf_d")[(i + j) % 3], bevel=0.2)
    for i, (lx, ly, top) in enumerate(((-7.6, -6.0, -15.0), (-7.7, -3.4, -12.5), (-7.6, 3.2, -14.0), (-7.7, 5.6, -16.5), (-5.4, 7.6, -17.5),
                                       (-5.6, -7.6, -18.0))):
        b(s * -lx - 0.9, s * -lx + 0.9, ly - 0.9, ly + 0.9, zr + 1.0, top, ("leaf_l", "leaf", "leaf_d")[i % 3], bevel=0.2, cull=False)     # tall leaves on the outer side
    P.rim = Bf.w((0.0, 0.0, zr + 1.6))
    return P


def build_pouch():
    """The leather pouch on her left hip as its own part: two straps from the belt, the bag, its flap and gold clasp.
    It hangs outside the skirt's hip, so the swinging thigh passes inside it. Origin where the straps leave the belt."""
    P = Part("Pouch")
    P.frame = Frame(np.eye(3), P.joint)
    b = lambda *q, **k: P.blk(IDENT, *q, **k)
    b(14.6, 18.6, -6.0, 3.0, 68.6, 70.6, "belt_d")            # the loop over the belt
    for y in (-5.8, 1.0):
        b(17.2, 18.6, y, y + 1.8, 55.0, 69.0, "belt_d")       # the two straps
    b(17.4, 24.0, -7.4, 3.4, 43.6, 55.0, "belt_l")            # the bag
    b(17.8, 23.6, -6.8, 2.8, 42.4, 43.8, "belt")              # its rounded foot
    b(17.2, 24.7, -8.0, 4.0, 50.6, 57.6, "belt")              # the flap
    b(24.5, 25.0, -8.0, 4.0, 50.6, 51.6, "belt_d", bevel=0.1) # ... and its stitched edge
    b(24.5, 25.5, -3.4, -0.6, 48.6, 52.8, "gold")             # the clasp
    b(25.3, 25.8, -2.6, -1.4, 49.8, 51.4, "gold_d", bevel=0.2)
    return P


def build_locs(P, F):
    """The mass of locs behind the head wrap: INDIVIDUAL locs, each a chain of chunky cubes turned a little against
    each other, some with a gold cuff. They rise behind the wrap, pile up into a big knot on top (highest toward the
    back), sweep back and cascade down behind the shoulders; a few come off the sides behind the ears. Kept out of:
    the face, the wrap, the shoulders' swing."""
    rng = np.random.default_rng(11)
    up = np.array([0.0, 0.0, 1.0])
    names = ("loc", "loc", "loc_l", "loc_d")

    def norm(v):
        return v / np.linalg.norm(v)

    def chain(root, d0, n, bend, zmin, size=4.8):
        p, d = np.array(root, np.float64), norm(np.array(d0, np.float64))
        nm = names[int(rng.integers(0, 4))]
        for i in range(n):
            L = float(rng.uniform(4.6, 7.4))
            if (p + d * L)[2] + 3.4 > TOP:                    # at the ceiling: turn over, back and down
                d = norm(np.array([d[0], 0.8, -0.5]))
            c = p + d * L / 2
            R = rot_between(up, d) @ RZ(float(rng.uniform(0, 90)))
            h = size * float(rng.uniform(0.86, 1.1)) / 2
            P.add(Frame(F.R @ R, F.w(c)), [-h, -h, -L / 2 - 0.5], [h, h, L / 2 + 0.5], PI[nm], 0.26, cull=False,
                  rgb=np.clip(PRGB[PI[nm]] * rng.uniform(0.9, 1.1), 0, 1))
            if i >= 1 and rng.random() < 0.22:                # a gold cuff round this length of the loc
                gn = ("gold", "gold_l", "gold_d")[int(rng.integers(0, 3))]
                P.add(Frame(F.R @ R, F.w(c)), [-h - 0.7, -h - 0.7, -1.5], [h + 0.7, h + 0.7, 1.5], PI[gn], 0.26, cull=False)
            p = p + d * L
            d = norm(d + np.array(bend) + rng.normal(0, 0.07, 3))
            if p[2] < 134 and abs(p[0]) < 17 and -13 < p[1] < 14:           # not into the skull or the wrap: out behind them
                p[1] = 14.5
            if p[2] < 104 and abs(p[0]) > 12 and p[1] < 13:   # behind the shoulders, not through them
                p[1] = 13.0
            if p[2] < 100:
                p[1] = max(p[1], 12.0 + (100 - p[2]) * 0.12)  # lying on her back
            p[0] = float(np.clip(p[0], -20.0, 20.0))          # the mass stays close to the head: no stray spikes
            if p[1] > 31.0 - max(0.0, p[2] - 110.0) * 0.5:
                p[1] = 31.0 - max(0.0, p[2] - 110.0) * 0.5
                d = norm(np.array([d[0] * 0.5, 0.15, -1.0]))  # at the back of the mass: hang straight down
            if p[2] < zmin:
                break

    for x in (-10.5, -5.2, 0.0, 5.2, 10.5):                   # the knot: locs gathered up behind the wrap, longer toward the back
        for j, y in enumerate((14.5, 18.0, 21.5)):
            root = (x + rng.uniform(-1, 1), y + rng.uniform(-1, 1), 124.0)
            chain(root, (x * 0.04, -0.1 + j * 0.2, 1.0), 4 + j + int(rng.integers(0, 2)), (0.0, 0.24, -0.4), 100.0 - 6 * j)
    for x in (-8.0, -2.7, 2.7, 8.0):                          # short ones between them: the knot piled high
        for y in (15.0, 19.0, 23.0):
            chain((x + rng.uniform(-1, 1), y + rng.uniform(-1, 1), 128.0), (x * 0.03, 0.0, 1.0), 2, (rng.uniform(-0.2, 0.2), 0.3, -0.3), 112.0, size=5.4)
    for x in (-10.0, 0.0, 10.0):                              # the back of the head: straight into the cascade
        for z in (119.0, 111.0):
            chain((x + rng.uniform(-2, 2), 14.0, z), (x * 0.02, 0.9, 0.15), int(rng.integers(6, 9)), (0.0, -0.05, -0.45), float(rng.uniform(72, 86)))
    for sx in (1, -1):                                        # off the sides, behind the ears
        for y in (8.0, 12.0):
            chain((sx * 15.0, y, 119.0), (sx * 0.6, 0.3, 0.5), int(rng.integers(5, 8)), (-sx * 0.1, 0.22, -0.75), float(rng.uniform(96, 102)))


EYE_Z = 111.0                                 # the foot of the eyes (the archer's skull stands on z 100)


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
    """Dark brown skin, the archer's face (its skull, one smooth plate, a short mouth, a small nose, ears with square
    gold earrings) with her eyes (archer_face), a cream
    head wrap over the crown, a fringe of locs under it, brown locs with gold cuffs knotted up behind it and falling
    behind and in front of the shoulders."""
    P = Part("Head")
    F = Frame()
    g = Grid(F, -24, 24, -20, 24, 80, 140, cs=2)
    X, Y, Z = g.X, g.Y, g.Z
    AX = np.abs(X)
    g.box(-12, 12, -10, 10, 100, 122, "skin")                 # the archer's skull
    g.box(-14, 14, 10, 14, 102, 124, "loc")                   # back of the head
    g.fill((AX > 12) & (AX < 14) & (Y > 4) & (Y < 10) & (Z > 102) & (Z < 122), "loc")            # behind the ears
    g.fill((AX > 12) & (AX < 14) & (Y > -10) & (Y < 4) & (Z > 116) & (Z < 122), "loc")           # above the ears
    g.fill((AX > 14) & (AX < 18) & (Y > 4) & (Y < 8) & (Z > 102) & (Z < 120), "loc_d")           # locs hanging behind each ear
    g.fill((AX > 14) & (AX < 18) & (Y > 8) & (Y < 12) & (Z > 100) & (Z < 122), "loc")
    g.fill((AX > 14) & (AX < 16) & (Y > -8) & (Y < 12) & (Z > 116) & (Z < 122), "loc")           # the volume over the ears
    g.fill((AX < 12) & (Y > 14) & (Y < 18) & (Z > 108) & (Z < 128), "loc")                       # ... and at the back, gathered up
    # a thick loc each side coming from behind the ear over the top of the shoulder and down the front of the blouse,
    # inside the puffed sleeve so the swinging arm clears it (longer on her right, as in the picture)
    for sx_, zb in ((-1, 84), (1, 88)):
        XS_ = X * sx_
        g.fill((XS_ > 16) & (XS_ < 18) & (Y > -16) & (Y < 6) & (Z > 100) & (Z < 104), "loc_d")
        g.fill((XS_ > 12) & (XS_ < 18) & (Y > -16) & (Y < -12) & (Z > 100) & (Z < 104), "loc_d")
        g.fill((XS_ > 12) & (XS_ < 16) & (Y > -16) & (Y < -12) & (Z > zb) & (Z < 102), "loc")
    hair = g.isn("loc")
    hh = g.hash(2, 3)
    g.paint(hair & (hh < 0.28), "loc_l")
    g.paint(hair & (hh > 0.78), "loc_d")
    # the cream head wrap: a broad band wound over the crown, wider than the skull, a narrower turn on top
    g.fill((AX < 16) & (Y > -14) & (Y < 12) & (Z > 122) & (Z < 130) & ~((AX > 14) & ((Y < -12) | (Y > 10))), "cream")
    g.fill((AX < 14) & (Y > -12) & (Y < 12) & (Z > 130) & (Z < 134) & ~((AX > 12) & ((Y < -10) | (Y > 10))), "cream_l")
    wrap = g.isn("cream", "cream_l")
    g.paint(wrap & (((g.ix + g.iz * 2 + g.iy) % 5) == 0), "cream_d")                             # its folds, winding round
    g.paint(wrap & (Z < 124) & (((g.ix + g.iy) % 3) == 0), "cream_dd")                           # the shadowed lower edge
    g.fill((AX > 12) & (AX < 14) & (Y > -2) & (Y < 2) & (Z > 108) & (Z < 114), "skin_l")         # ears
    emit(P, g, lim=(8, 14), lims={"loc": (6, 11), "skin_l": (8, 9), "cream": ((4, 10), (4, 10), (2, 4)), "cream_l": ((4, 10), (4, 10), (2, 4)),
                                  "cream_d": ((2, 6), (2, 6), (2, 2)), "cream_dd": ((2, 4), (2, 4), (2, 2))},
         shade=0.3, proud_p=0.4, proud=(0.15, 0.5), seed=61)
    b = lambda *a, **k: P.blk(F, *a, **k)
    # ---- THE FACE STRUCTURE: the archer's. ONE smooth skin plate in front of the skull (a single block), so no seams
    # between blocks read as features; a short mouth line, a small low-relief nose with a slight shadow under it.
    b(-12.0, 12.0, -11.0, -10.0, 100.0, 122.0, "skin", bevel=0.03)
    b(-3.0, 3.0, -11.2, -10.9, 103.6, 104.6, "lip", bevel=0.1)                           # mouth: one thin bar
    b(-1.3, 1.3, -11.5, -10.9, 106.8, 109.4, "skin", bevel=0.12, tint=1.06)              # nose: one small block, barely proud
    b(-1.3, 1.3, -11.2, -10.9, 106.1, 106.8, "skin_d", bevel=0.1)                        # ... and the shadow under it
    # ---- THE EYES: the archer's too (archer_face): a 6 x 4 u white, a 3 x 4 u pupil centred in it, a glint, her brow.
    archer_face(P, F, 100.0, front=-11.0, brow="brow", eyes_only=True)
    for sx in (1, -1):
        b(10.0, 12.0, -12.0, -10.9, 117.0, 120.0, "loc_d", sx=sx)                        # the hair coming down at the temples
    b(-12.0, 12.0, -12.0, -10.9, 120.0, 122.0, "loc")         # the fringe of locs under the wrap
    for i, x in enumerate((-10.5, -6.0, -1.5, 3.0, 7.5)):
        b(x, x + 3.0, -12.6, -11.4, 119.2 + (i % 2) * 0.6, 122.0, ("loc_l", "loc_d", "loc", "loc_l", "loc_d")[i])
    for sx in (1, -1):
        b(13.6, 14.5, -1.0, 1.0, 109.6, 112.4, "skin_d", sx=sx)                          # the hollow of the ear
        # earrings: a link and a hollow gold square hanging from each ear (the archer's, a size larger)
        b(13.7, 14.9, 0.4, 1.6, 105.3, 108.6, "gold_d", sx=sx, bevel=0.2)
        b(13.6, 15.0, -2.4, 4.4, 104.0, 105.6, "gold", sx=sx)
        b(13.6, 15.0, -2.4, 4.4, 99.2, 100.8, "gold", sx=sx)
        b(13.6, 15.0, -2.4, -0.8, 100.8, 104.0, "gold_l", sx=sx)
        b(13.6, 15.0, 2.8, 4.4, 100.8, 104.0, "gold_d", sx=sx)
    # gold cuffs on the front locs
    for (sx, z) in ((-1, 87.0), (1, 91.0), (-1, 96.0)):
        b(11.2, 16.8, -16.8, -11.2, z, z + 3.4, "gold" if z < 95 else "gold_l", sx=sx)
    build_locs(P, F)
    # ---- the long locs behind the shoulders: separate columns hanging down her back
    FL = F.sub(RX(5.0), (0.0, 13.0, 114.0))
    gl = Grid(FL, -20, 20, 10, 24, 60, 116, cs=2)
    locs = ((-18, 12, 99, "loc_l"), (14, 12, 90, "loc"),
            (-14, 12, 88, "loc"), (-10, 14, 82, "loc_l"), (-6, 12, 76, "loc_d"), (-2, 14, 68, "loc"), (2, 12, 64, "loc_l"),
            (6, 14, 70, "loc"), (10, 12, 78, "loc_d"))
    for (x0, y0, zb, nm) in locs:
        gl.box(x0, x0 + 4, y0, y0 + 4, zb, 114, nm)
    emit(P, gl, lim=((4, 4), (4, 4), (5, 11)), pref="z", shade=0.5, proud_p=0.4, proud=(0.15, 0.5), seed=65)
    for (x0, y0, z) in ((-6, 12, 80.0), (2, 12, 68.0), (6, 14, 76.0), (-10, 14, 88.0), (10, 12, 84.0), (-2, 14, 74.0), (-18, 12, 102.0), (14, 12, 94.0),
                        (-14, 12, 96.0), (2, 12, 86.0), (-6, 12, 94.0)):
        P.blk(FL, x0 - 0.9, x0 + 4.9, y0 - 0.9, y0 + 4.9, z, z + 3.6, "gold" if (x0 // 4) % 2 else "gold_l")       # gold cuffs
    return P


def build_body():
    """-> (Body, Chest). Body: the pelvis inside the skirt, the belt with its big gold buckle, the knot of the cream
    cloth. Chest: the cream blouse under the green bodice with its gold trim and straps, the open neck."""
    P = Part("Body")
    FB = Frame(np.eye(3), (0.0, 0.0, LIFT))
    blk = lambda *a, **k: P.blk(FB, *a, **k)
    g = Grid(FB, -21, 21, -18, 14, 30, 74, cs=2)
    X, Y, Z = g.X, g.Y, g.Z
    AX = np.abs(X)
    # the pelvis sits INSIDE the two skirt halves (their hip drums are the outside), so nothing is coplanar with them
    g.fill((AX < 15) & (np.abs(Y) < np.where((AX < 3) | (Z > 60), 8, 6)) & (Z > 50) & (Z < 62), "green_d")
    g.box(-15, 15, -10, 10, 62, 68, "belt")
    emit(P, g, lim=(8, 16), lims={"belt": ((8, 14), (8, 12), (6, 6))}, seed=81)
    # buckle: a hollow gold square, plates on plates
    blk(-4.8, 4.8, -11.4, -10.0, 60.4, 69.6, "gold")
    blk(-4.8, -2.6, -12.4, -11.2, 60.4, 69.6, "gold_l")
    blk(2.6, 4.8, -12.4, -11.2, 60.4, 69.6, "gold_l")
    blk(-2.6, 2.6, -12.4, -11.2, 67.4, 69.6, "gold_l")
    blk(-2.6, 2.6, -12.4, -11.2, 60.4, 62.6, "gold_l")
    blk(-2.6, 2.6, -11.9, -11.2, 62.6, 67.4, "belt_dd")
    blk(-1.0, 1.0, -12.6, -11.6, 64.0, 66.0, "gold_d", bevel=0.15)
    blk(9.0, 11.0, -11.0, -10.0, 64.0, 66.0, "gold", bevel=0.15)                         # a belt stud on her left
    blk(-16.0, -15.0, -2.0, 2.0, 63.0, 67.0, "gold_d")
    blk(-1.5, 1.5, 10.0, 11.0, 63.5, 66.5, "gold_d")
    blk(-15.0, 15.0, -10.3, 10.3, 67.0, 67.9, "belt_l", bevel=0.05)                      # the belt's lighter upper edge
    # the knot of the cream cloth tucked in over the belt on her right (the cloth itself hangs on the right thigh)
    blk(-15.4, -8.6, -11.9, -10.0, 61.6, 68.6, "cream_l")
    blk(-14.2, -9.8, -12.5, -11.7, 63.4, 66.8, "cream")
    # ---- chest: its own part, turning on the pelvis at the waist
    B = P
    P = Part("Chest")
    P.bias = len(B._ch)
    FT = Frame()
    tb = lambda *a, **k: P.blk(FT, *a, **k)
    g = Grid(FT, -21, 21, -18, 14, 68, 104, cs=2)
    X, Y, Z = g.X, g.Y, g.Z
    AX = np.abs(X)
    body = (AX < 13) & (np.abs(Y) < 8) & (Z > 68 + LIFT) & (Z < 94)
    g.fill(body, "cream")
    g.paint(body & (Z < 70 + LIFT), "belt_d")
    bodice = body & (Z > 70 + LIFT) & (Z < 88)
    g.paint(bodice, "green")
    g.paint(bodice & (AX > 8) & (AX < 10), "green_d")                                    # its side seams
    g.paint(bodice & (Z > 86), "gold")                                                   # the gold trim along its top ...
    straps = body & (AX > 8) & (AX < 12) & (Z > 88)
    g.paint(straps, "green_l")                                                           # ... and the straps over the shoulders
    g.paint(body & (AX < 8) & (Y < -6) & (Z > 90), "skin")                               # the blouse's open neck
    g.paint(body & (AX < 8) & (Y > 6) & (Z > 92), "skin_d")
    g.fill((X ** 2 + Y ** 2 < 30.0) & (Z > 92) & (Z < 102), "skin_d")                    # neck
    emit(P, g, lim=((6, 14), (6, 12), (4, 10)), lims={"gold": ((4, 8), (4, 8), (2, 2)), "green_l": ((4, 4), (4, 6), (4, 6)), "skin_d": (10, 10),
                                                      "skin": (10, 16)}, seed=82)
    for sx in (1, -1):                                        # the straps' gold edges and the lacing down the bodice's front
        tb(7.7, 8.5, -8.5, -7.9, 88.0, 94.0, "gold_d", sx=sx, bevel=0.1)
        tb(1.2, 2.4, -8.6, -8.0, 75.0, 86.0, "gold_d", sx=sx, bevel=0.1)
    for z in (76.5, 79.5, 82.5):
        tb(-2.4, 2.4, -8.7, -8.1, z, z + 1.0, "cream_d", bevel=0.1)
    return B, P


WHOLE = ["Body", "Head", "ArmL", "ArmR", "LegL", "LegR"]


def wholes(parts):
    """The limbs as the single rigid pieces they are while every elbow, knee and wrist is at rest."""
    return {"Body": Combo(parts["Body"], parts["Chest"], parts["Pouch"]), "Head": parts["Head"],
            "ArmL": Combo(parts["ArmL"], parts["ForeL"], parts["Sickle"]),
            "ArmR": Combo(parts["ArmR"], parts["ForeR"], parts["HandR"], parts["Basket"]),
            "LegL": Combo(parts["LegL"], parts["ShinL"]), "LegR": Combo(parts["LegR"], parts["ShinR"])}


def build_farmer():
    t0 = time.time()
    parts = {}
    for s_, side in ((1, "L"), (-1, "R")):
        parts["Leg" + side], parts["Shin" + side] = build_leg(s_)
        parts["Arm" + side], parts["Fore" + side] = build_arm(s_)
    parts["HandR"] = parts["ArmR"].hand_part
    parts["Basket"] = parts["ArmR"].basket_part
    parts["Sickle"] = parts["ArmL"].sickle_part
    parts["Pouch"] = build_pouch()
    parts["Head"] = build_head()
    parts["Body"], parts["Chest"] = build_body()
    for q in parts.values():
        q.finalize()
    missing = [k for k in ORDER if JOINTS.get(k) is None or k not in parts]
    assert not missing, missing
    print("sculpted in %.1f s" % (time.time() - t0))
    return parts


# ---------------------------------------------------------------------------------------------------- checks

def pivot(key):
    return [round(c * U, 5) for c in JOINTS[key]]


def check_pose(parts, pts, label, **ang):
    axes = dict(LegL=("x", ang.get("legl", 0)), LegR=("x", ang.get("legr", 0)), ArmL=("x", ang.get("arml", 0)),
                ArmR=("x", ang.get("armr", 0)), Head=("z", ang.get("head", 0)), Body=("x", 0))
    posed = {k: rotated(pts[k], parts[k].joint, axes[k][0], axes[k][1]) for k in WHOLE}
    occ = {k: occ_grid(posed[k], 0.5) for k in WHOLE}
    bad = []
    for i, a in enumerate(WHOLE):
        for b in WHOLE[i + 1:]:
            if {a, b} in ({"Body", "LegL"}, {"Body", "LegR"}, {"Body", "Head"}):
                continue
            both = occ[a] & occ[b]
            n = int(both.sum())
            if n:
                idx = np.argwhere(both)
                lo = idx.min(axis=0) * 0.5 + SW_LO
                hi = idx.max(axis=0) * 0.5 + SW_LO
                bad.append("%s-%s:%d [x %.0f..%.0f y %.0f..%.0f z %.0f..%.0f]" % (a, b, n, lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]))
    low = min(float(p[:, 2].min()) for p in posed.values())
    print("CHECK %-8s lowest z %.1f u | overlaps: %s" % (label, low, "; ".join(bad) if bad else "none"))



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
    path = os.path.join(V.PREVIEWS, SHOT_PREFIX + "%s.png" % name)
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



# ---------------------------------------------------------------------------------------------------- pose and main

def rig(obs):
    """Parent the objects as the engine does (after the export, which wants them loose)."""
    for key, ob in obs.items():
        if key in PARENT:
            ob.parent = obs[PARENT[key]]


def pose(obs, **ang):
    """Turn joints by degrees about x (Head: about z), keyed by the part's name in lower case: legl, shinl, arml, forel,
    handr, chest, head ...; a tuple (x, y, z) turns about all three axes. Positive swings a hanging limb backwards.
    Sickle, Basket and Pouch ride on their parents (ForeL, ForeR, Body)."""
    for key, ob in obs.items():
        base = np.array(JOINTS[PARENT[key]], np.float64) if key in PARENT else np.zeros(3)
        ob.location = [float(v) * U for v in np.array(JOINTS[key], np.float64) - base]
        a = ang.get(key.lower(), 0.0)
        if isinstance(a, (tuple, list)):
            ob.rotation_euler = tuple(math.radians(v) for v in a)
        else:
            ob.rotation_euler = (0, 0, math.radians(a)) if key == "Head" else (math.radians(a), 0, 0)


def want(name):
    return VIEWS is None or name in VIEWS


# the picture's pose (previews only): the sickle raised at her left, the basket on her right arm, the head turned a little
HERO = dict(head=16.0, arml=(-28.0, 0.0, -30.0), forel=-38.0, armr=(4.0, 0.0, 8.0), legl=-4.0, legr=3.0)
WALK = dict(legl=30, shinl=-10, legr=-25, shinr=35, arml=-30, forel=-15, armr=22, forer=6, chest=-6)


def main():
    t0 = time.time()
    V.reset_scene()
    parts = build_farmer()
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
        print("  %-7s x %6.1f..%6.1f  y %6.1f..%6.1f  z %6.1f..%6.1f u" % ((k,) + tuple(v for pair in zip(P.min(axis=0), P.max(axis=0)) for v in pair)))
    print("FARMER WOMAN size: x %.3f m (%.2f..%.2f), y %.3f m (%.2f..%.2f), height %.4f m (lowest %.4f)" % (
        (hi[0] - lo[0]) * U, lo[0] * U, hi[0] * U, (hi[1] - lo[1]) * U, lo[1] * U, hi[1] * U, hi[2] * U, lo[2] * U))
    figure_top = max(float(part_points(parts[k], step=1.0, cores=False)[:, 2].max()) for k in ORDER if k not in ("Sickle", "Basket", "Pouch"))
    print("top of the figure (hair): %.4f m" % (figure_top * U))
    W = wholes(parts)
    pts = {k: part_points(W[k], step=0.6, shrink=0.4, cores=False) for k in WHOLE}
    check_pose(W, pts, "rest")
    check_pose(W, pts, "walk A", legl=35, legr=-35, arml=-35, armr=35)
    check_pose(W, pts, "walk B", legl=-35, legr=35, arml=35, armr=-35)

    obs = {}
    total = 0
    for key in ORDER:
        ob = make_object(parts[key])
        obs[key] = ob
        V.export_gltf(ob, collision="none", extra=dict(pivot=pivot(key), part=key, parent=PARENT.get(key, ""), triangles=int(ob["triangles"]),
                                                       blocks=int(len(parts[key].c))))
        total += int(ob["triangles"])
        print("  %-7s %6d blocks (%d core)  %7d triangles  %6d faces" % (key, len(parts[key].c), int(parts[key].core.sum()), ob["triangles"], int(ob["voxel_faces"])))
    print("FARMER WOMAN triangles in all: %d  (%.1f s)" % (total, time.time() - t0))
    r5 = lambda v: [round(float(c), 5) for c in v]
    sickle, basket, pouch = parts["Sickle"], parts["Basket"], parts["Pouch"]
    meta = dict(height=HEIGHT, radius=RADIUS, voxel=U, mesh_yaw=-90.0, stride=STRIDE,
                elbow_l=ELBOW["L"], elbow_r=ELBOW["R"], wrist_l=WRIST_L,
                cape=dict(cols=CAPE_COLS, rows=CAPE_ROWS), has_sheath=False,
                parts={key: dict(mesh=PREFIX + key, pivot=pivot(key), parent=PARENT.get(key, "")) for key in ORDER},
                # metres and unit vectors in Blender axes (+x her left, -y forward, z up), in the modelled rest pose
                sickle=dict(part="Sickle", hand="L", parent=PARENT["Sickle"], grip=pivot("Sickle"),
                            axis=r5(sickle.frame.R[:, 2]),                # up the handle, from the fist toward the blade
                            blade_dir=r5(sickle.frame.R[:, 0]),           # the way the blade curves (away from her)
                            flat=r5(sickle.frame.R[:, 1]),                # through the flat of the blade
                            foot_offset=round(-SICKLE_FOOT * U, 5), neck_offset=round(SICKLE_NECK * U, 5),
                            radius=round(SICKLE_R * U, 5), tip=r5(sickle.tip * U)),
                basket=dict(part="Basket", arm="R", parent=PARENT["Basket"], pivot=pivot("Basket"),
                            axis=r5(basket.frame.R[:, 2]),                # from its foot to its handle
                            rim=r5(basket.rim * U), drop=round(BASKET_DROP * U, 5)),
                pouch=dict(part="Pouch", side="L", parent=PARENT["Pouch"], pivot=pivot("Pouch")))
    with open(os.path.join(V.MESHES, NAME + ".json"), "w") as f:
        json.dump(meta, f, indent=1)
    print("wrote %s.json" % NAME)
    if NO_RENDER:
        return

    to_preview(obs, parts)
    stage()
    rig(obs)
    Pv = V.PREVIEWS
    pv = lambda n: os.path.join(Pv, SHOT_PREFIX + n + ".png")
    if want("hero"):
        pose(obs, **HERO)
        hero = shot("hero", az=-30, el=-10, dist=3.2, target=(0.06, 0, 0.87), res=(900, 1250), lens=50)
        montage([REF, hero], pv("compare"), H=1250)
    pose(obs)
    if want("sides"):
        tiles = [shot("front", 0, 2, dist=6.6, res=(720, 960)), shot("right", -90, 2, dist=6.6, res=(720, 960)),
                 shot("back", 180, 4, dist=6.6, res=(720, 960)), shot("left", 90, 2, dist=6.6, res=(720, 960))]
        montage(tiles, pv("sides"), H=960)
    if want("34"):
        shot("three_quarter", -32, 8, dist=6.6, res=(900, 1200))
    if want("face"):
        fc = shot("face_ref_angle", -30, -8, dist=6.0, target=(0, 0, 1.42), res=(800, 800), lens=230)
        montage([REF, fc], pv("face_compare"), H=800, crops=[(440, 120, 820, 500), None])
        tiles = [shot("face_front", 0, 0, dist=6.0, target=(0, 0, 1.42), res=(800, 800), lens=230),
                 shot("face_34", -33, -6, dist=6.0, target=(0, 0, 1.42), res=(800, 800), lens=230),
                 shot("face_side", 90, 0, dist=6.0, target=(0, 0, 1.42), res=(800, 800), lens=230)]
        montage(tiles, pv("face"), H=800)
    if want("game"):
        tiles = [shot("game_front", 25, 40, dist=7.0, res=(720, 960)), shot("game_back", 205, 40, dist=7.0, res=(720, 960))]
        montage(tiles, pv("game"), H=960)
    if want("walk"):
        pose(obs, **WALK)
        tiles = [shot("walk_front", -29, 0, dist=7.2, res=(720, 960)), shot("walk_left", 90, 2, dist=7.2, res=(720, 960)),
                 shot("walk_back", 150, 8, dist=7.2, res=(720, 960)), shot("walk_right", -90, 2, dist=7.2, res=(720, 960))]
        montage(tiles, pv("walk"), H=960)
    pose(obs)
    print("done in %.1f s" % (time.time() - t0))


main()
