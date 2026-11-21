"""The BUILDER: a sturdy bearded craftsman in a long navy robe with gold-yellow bands, a tool belt, a stone-headed
hammer in his right fist and a wooden frame pack on his back (blueprint panels, rolled plans, a coil of rope, a lit
lantern), built like King David (king_b.py) and the troops (troop_swordsman.py) from individual bevelled cubes and
slabs of several sizes, as rigid parts (a wooden toy) that the game swings about their joints. Each part is exported on
its own with its mesh origin at its joint. Reference: References/Remake/builder.png.

    Blender -b --factory-startup --python Tools/blender/assets/troop_builder.py -- [--no-render] [--views hero,sides,...] [--fast] [--gpu]

Units: "u" = 1.25 cm (he is 138 u = 1.725 m to the top of his hair; the plans in his pack stand a little higher). World
axes: +X is his LEFT (he faces -Y), z = 0 is the ground between his feet.

The reference shows the hammer in his LEFT hand; the rig's weapon hand is the right one, so the model is the mirror
image of the picture (hammer right, lantern / emblem / free fist on his left). builder_compare.png mirrors the render
back so that it reads like the picture.

THE RIG (the block "THE RIG" below) is King David's, as the troops use it: the same part names, parents and joints, so
the same C++ swings him. He has no cape (the pack is on his back): the robe's long skirt swings with the thighs.
Extra parts next to the King's: Hammer (in the right fist, where the swordsman's sword is: origin at the middle of the
grip; "sword" in SM_Builder.json describes it for the engine) and Pack (on the back; rides on Chest).

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
NAME = "SM_Builder"
PREFIX = NAME + "_"
REF = os.path.join(V.ROOT, "References", "Remake", "builder.png")

# ================================================================================================== THE RIG
# King David's rig (king_b.py / SM_KingB.json) as the troops use it, without the scabbard and the cape. A tree of
# rigid parts (PARENT; no entry = the figure's root). Body is the pelvis, Chest turns on it at the waist; each arm is
# an upper arm and a forearm (the left with its hand, the right with the hammer hand "HandR" turning at the wrist);
# each leg a thigh (with its half of the robe's skirt) and a shin (with the boot). The hammer is its own part,
# modelled in the right fist, its origin at the middle of the grip (the swordsman's "Sword"); the pack rides on Chest.
ORDER = ["Body", "Chest", "Head", "ArmL", "ForeL", "ArmR", "ForeR", "HandR", "LegL", "ShinL", "LegR", "ShinR", "Pack", "Hammer"]
PARENT = {"Chest": "Body", "Head": "Chest", "ArmL": "Chest", "ArmR": "Chest", "ForeL": "ArmL", "ForeR": "ArmR", "HandR": "ForeR",
          "ShinL": "LegL", "ShinR": "LegR", "Pack": "Chest", "Hammer": "HandR"}
CAPE_COLS, CAPE_ROWS = 0, 0                   # no cape
ELBOW = {"L": 14.0, "R": 33.0}                # the bend the forearms are modelled with (degrees)
ARM_OUT = {"L": 7.0, "R": 6.0}                # how far the arms hang out from the shoulders (degrees)
KNEE_Z = 28.0
HAIR_TOP = 138.0                              # the top of his hair
TOP = 150.0                                   # nothing stands higher (the plans in the pack)
HEIGHT, RADIUS = 1.75, 0.42                   # metres, for the character's capsule (the troops' own)
JOINTS = {                                    # u, world
    "Body": (0, 0, 56), "Chest": (0, 0, 73), "Head": (0, 0, 104),
    "ArmL": (25, 0, 100), "ArmR": (-25, 0, 100),
    "LegL": (12, 0, 54), "LegR": (-12, 0, 54),
    "ShinL": (12, 0, KNEE_Z), "ShinR": (-12, 0, KNEE_Z),
    "Pack": (0, 26, 90),                      # the middle of the pack on his back
    # set while building: ForeL / ForeR (the elbows, build_arm), HandR (the wrist), Hammer (the middle of the grip in
    # the right fist, build_hammer)
}
ELBOW_AT = (25, 0, 76)                        # the elbow, in the upper arm's own frame (x mirrored for the right arm)
WRIST_AT = (25, -0.5, 52.0)                   # the wrist, in the forearm's frame
GRIP = (24.8, -3.5, 45.8)                     # the middle of the hammer's grip in the fist, in the forearm's frame
# ==================================================================================================

MATN = ["paint", "gold", "metal", "wool", "glow"]
KINDS = ["cloth", "skin", "hair", "leather", "gold", "metal", "fur", "gem", "core", "blade", "stone", "wood", "paper", "glow"]
_PAL = [
    # name        colour     slot     preview kind
    ("gold",     "#FFB616", "gold", "gold"), ("gold_l", "#FFD63E", "gold", "gold"), ("gold_d", "#E39510", "gold", "gold"),
    ("gold_dd",  "#A2640C", "gold", "gold"),
    ("steel",    "#A19EA2", "metal", "metal"), ("steel_l", "#B6B2B3", "metal", "metal"), ("steel_ll", "#CFCAC8", "metal", "metal"),
    ("steel_d",  "#6E6C72", "metal", "metal"), ("steel_dd", "#45434A", "metal", "metal"),
    ("stone",    "#8E8882", "paint", "stone"), ("stone_l", "#A49E96", "paint", "stone"), ("stone_ll", "#B8B2A9", "paint", "stone"),
    ("stone_d",  "#77726D", "paint", "stone"), ("stone_dd", "#5E5A57", "paint", "stone"),
    ("skin",     "#C8742E", "paint", "skin"), ("skin_l", "#DB893C", "paint", "skin"), ("skin_d", "#A95F23", "paint", "skin"),
    ("skin_dd",  "#884B1D", "paint", "skin"), ("lip", "#7E3D22", "paint", "skin"),
    ("hair",     "#2E1C14", "paint", "hair"), ("hair_l", "#3B251A", "paint", "hair"), ("hair_ll", "#492F21", "paint", "hair"),
    ("hair_d",   "#21130D", "paint", "hair"),
    ("beard",    "#2C1B13", "paint", "hair"), ("beard_l", "#3B261A", "paint", "hair"), ("beard_d", "#21140E", "paint", "hair"),
    ("navy",     "#2A3159", "paint", "cloth"), ("navy_l", "#363F6D", "paint", "cloth"), ("navy_ll", "#444E81", "paint", "cloth"),
    ("navy_d",   "#20264A", "paint", "cloth"), ("navy_dd", "#171C38", "paint", "cloth"),
    ("yellow",   "#E09A10", "paint", "cloth"), ("yellow_l", "#EFAE1E", "paint", "cloth"), ("yellow_d", "#BE7D0C", "paint", "cloth"),
    ("cream",    "#E3CB9A", "paint", "cloth"), ("cream_l", "#F0DCB2", "paint", "cloth"), ("cream_d", "#CBB07E", "paint", "cloth"),
    ("cream_dd", "#AC915C", "paint", "cloth"),
    ("belt",     "#7B4A24", "paint", "leather"), ("belt_l", "#96602F", "paint", "leather"), ("belt_d", "#5A3418", "paint", "leather"),
    ("belt_dd",  "#40240F", "paint", "leather"),
    ("bracer",   "#6A4226", "paint", "leather"), ("bracer_l", "#82532F", "paint", "leather"), ("bracer_d", "#4E2F1A", "paint", "leather"),
    ("trouser",  "#3B2A22", "paint", "cloth"), ("trouser_d", "#2A1D17", "paint", "cloth"),
    ("boot",     "#77492A", "paint", "leather"), ("boot_l", "#935E34", "paint", "leather"), ("boot_d", "#5A361D", "paint", "leather"),
    ("sole",     "#4A2E1B", "paint", "leather"), ("sole_d", "#33200F", "paint", "leather"),
    ("wood",     "#70442A", "paint", "wood"), ("wood_l", "#875633", "paint", "wood"), ("wood_d", "#59341E", "paint", "wood"),
    ("wood_dd",  "#412514", "paint", "wood"),
    ("paper",    "#E4CD9C", "paint", "paper"), ("paper_l", "#F1DEB4", "paint", "paper"), ("paper_d", "#C8AD79", "paint", "paper"),
    ("paper_dd", "#A1855A", "paint", "paper"),
    ("rope",     "#C8954C", "paint", "paper"), ("rope_l", "#DBAB60", "paint", "paper"), ("rope_d", "#A8793B", "paint", "paper"),
    ("bp",       "#232C5C", "paint", "cloth"), ("bp_l", "#2C3870", "paint", "cloth"), ("bp_d", "#1A2148", "paint", "cloth"),
    ("line",     "#F3BE3A", "paint", "gem"),
    ("white",    "#F4EFE4", "paint", "gem"), ("pupil", "#15100E", "paint", "hair"), ("lip_d", "#6E3320", "paint", "skin"),
    ("gem_w",    "#FFF4DA", "paint", "gem"),
    ("glow",     "#FFA62E", "glow", "glow"), ("glow_l", "#FFC85A", "glow", "glow"),
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
NOSHADE = ("white", "pupil", "lip", "gem_w", "core", "glow", "glow_l", "line")


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
AO_N = (288, 200, 312)


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
# The builder
# ##################################################################################################################
# Shapes are sculpted on 2 u cells (1 u for the face) and MERGED into the fewest, largest boxes by emit(); studs,
# buckles, fittings, the fists, the hammer and the things on the pack are direct blocks.

ROBE = ((5, 9), (5, 9), (10, 20))             # the robe: tall slabs, so that it hangs in folds
SKIRT_HEM = 20.0                              # the hem's height above the ground (u): the boots show under it


def skirt_tiers(Z):
    """The robe's skirt at height Z: how far out it reaches from the middle (x) and its half depth (y). It flares."""
    out = np.where(Z > 46, 21, np.where(Z > 38, 23, np.where(Z > 30, 25, 27)))
    dep = np.where(Z > 46, 9, np.where(Z > 38, 11, np.where(Z > 30, 13, 15)))
    return out, dep


def build_leg(s):
    """-> (thigh, shin). The thigh carries its half of the robe's long skirt (solid, from the hip to the hem, with
    half of the cream front panel); the shin the boot and the drum the knee turns on, inside the skirt."""
    side = "L" if s > 0 else "R"
    P, Q = Part("Leg" + side), Part("Shin" + side)
    g = Grid(IDENT, 1, 31, -19, 19, 16, 68, cs=2, sx=s)
    XS, Y, Z = g.XS, g.Y, g.Z
    out, dep = skirt_tiers(Z)
    sk = (XS > 1) & (XS < out) & (np.abs(Y) < dep) & (Z > SKIRT_HEM) & (Z < 54)
    drum = (XS > 1) & (XS < 21) & (Y ** 2 + (Z - 54) ** 2 < 9.7 ** 2) & (Z > 54)
    g.fill(sk | drum, "navy")
    front = sk & (Y < -dep + 2)
    g.paint(sk & (XS > 9) & ((g.ix + g.iy) % 5 == 0), "navy_d")       # folds
    g.paint(sk & (XS > 9) & ((g.ix + g.iy) % 5 == 2), "navy_l")
    g.paint(sk & (Z > 28) & (Z < 30), "yellow_d")             # the thin band above the hem
    hem = (XS > 1) & (XS < out + 2) & (np.abs(Y) < dep + 2) & (Z > SKIRT_HEM) & (Z < SKIRT_HEM + 4)
    g.fill(hem, "yellow")                                     # the hem: a thick gold-yellow band, standing out
    g.paint(hem & (g.hash(2, 3 + s, ax=(1, 1, 0)) < 0.25), "yellow_l")
    panel = (XS < 7) & (Y < 0) & (Z > SKIRT_HEM) & (Z < 54)   # the cream panel down the front: this leg's half
    g.paint((sk | hem) & panel, "cream")
    g.carve(hem & ~sk & panel)                                # ... flat at the hem, between the gold bands
    g.paint(sk & panel & (XS < 3), "cream_d")                 # the pleat down the middle
    g.paint(sk & panel & (Z < 26) & (XS > 3), "cream_l")
    emit(P, g, lim=ROBE, pref="z", lims={"yellow": ((6, 12), (6, 12), (4, 4)), "yellow_l": ((4, 8), (4, 8), (4, 4)), "yellow_d": ((6, 12), (6, 12), (2, 2)),
                                        "cream": ((3, 4), (2, 4), (12, 22)), "cream_d": ((2, 2), (2, 4), (14, 26)), "cream_l": ((4, 4), (2, 4), (6, 6))},
         shade=0.45, proud_p=0.35, proud=(0.1, 0.4), seed=20 + s)
    b = lambda *a, **k: P.blk(IDENT, *a, sx=s, **k)
    b(7.0, 8.6, -12.0, -9.0, 46.0, 54.0, "yellow_d", bevel=0.1)
    b(7.0, 8.6, -14.0, -11.0, 38.0, 46.0, "yellow_d", bevel=0.1)
    b(7.0, 8.6, -16.0, -13.0, 30.0, 38.0, "yellow_d", bevel=0.1)      # a gold border beside the cream panel
    if s > 0:
        # the house emblem embroidered on the skirt: an outline with a stepped roof and a door
        e = lambda x0, x1, z0, z1, nm="yellow_l": b(x0, x1, -14.0 if z0 < 38 else -12.0, -11.0, z0, z1, nm, bevel=0.12)
        e(10.5, 22.5, 31.5, 33.5)                             # the sill
        e(10.5, 12.5, 33.5, 39.5)                             # walls
        e(20.5, 22.5, 33.5, 39.5)
        e(10.5, 14.5, 39.5, 41.5, "yellow")                   # the roof, stepping up to the ridge
        e(18.5, 22.5, 39.5, 41.5, "yellow")
        e(12.5, 16.0, 41.5, 43.5)
        e(17.0, 20.5, 41.5, 43.5)
        e(14.5, 18.5, 43.5, 45.5, "yellow")
        e(15.5, 17.5, 33.5, 37.5, "yellow")                   # the door
        e(14.5, 18.5, 37.5, 38.6)
    else:
        for (x, z) in ((12.0, 40.0), (17.0, 33.0)):
            b(x, x + 2.2, -14.0 if z < 38 else -12.0, -11.0, z, z + 2.2, "yellow_l", bevel=0.15)   # two stray stitches
    # ---- the shin and the boot
    g = Grid(IDENT, 1, 27, -21, 13, 0, 66, cs=2, sx=s)
    XS, Y, Z = g.XS, g.Y, g.Z
    g.fill((XS > 7) & (XS < 17) & (Y ** 2 + (Z - KNEE_Z) ** 2 < 37.0) & (Z > 22), "trouser_d")    # the knee's drum
    g.box(5, 19, -7, 7, 16, 26, "trouser")                    # the leg, inside the skirt
    g.box(3, 21, -9, 9, 6, 20, "boot")                        # the boot's shaft: chunky
    g.box(3, 23, -17, 9, 0, 8, "boot")                        # the foot
    foot = g.bm(3, 23, -17, 9, 0, 8)
    g.carve(foot & (Y < -13) & (Z > 6))
    g.carve(foot & (Y < -15) & (Z > 4))
    g.paint(foot & (Y < -9), "boot_l")                        # toe cap
    g.paint(foot & (Z < 2), "sole")
    g.pbox(3, 21, -9, 9, 18, 20, "boot_l")                    # the shaft's rolled top
    emit(Q, g, lim=(8, 16), lims={"sole": (10, 22), "boot_l": (6, 12)}, seed=24 + s)
    b = lambda *a, **k: Q.blk(IDENT, *a, sx=s, **k)
    b(2.3, 23.7, -17.8, 9.8, 0.0, 1.5, "sole_d")              # the welt of the sole
    for z in (8.6, 13.8):                                     # two straps, each with gold studs
        b(2.3, 21.7, -9.7, 9.7, z, z + 3.0, "belt_d" if z < 10 else "belt")
        b(9.5, 14.5, -11.0, -9.4, z - 0.6, z + 3.6, "gold")
        b(11.0, 13.0, -11.6, -10.8, z + 0.5, z + 2.5, "gold_l", bevel=0.15)
        b(21.4, 22.8, -3.0, 2.0, z - 0.4, z + 3.4, "gold")
        b(22.6, 23.3, -1.5, 0.5, z + 0.5, z + 2.5, "gold_l", bevel=0.15)
    return P, Q


def build_arm(s):
    """-> (upper arm, forearm with the hand). The elbow is where the forearm's frame is bent. Navy sleeves to the
    elbow with a gold-yellow band and a thick cream cuff; bare forearms, a leather bracer at each wrist, bare fists."""
    side = "L" if s > 0 else "R"
    P = Part("Arm" + side)
    A = Frame().sub(RY(-s * ARM_OUT[side]), P.joint)
    bend = ELBOW[side]
    ex, ey, ez = ELBOW_AT
    Fo = A.sub(RX(-bend), (s * ex, ey, ez))
    JOINTS["Fore" + side] = tuple(float(v) for v in A.w((s * ex, ey, ez)))
    Q = Part("Fore" + side)
    # ---- upper arm: shoulder drum, sleeve, band, cuff
    g = Grid(A, 15, 37, -12, 12, 68, 112, cs=2, sx=s)
    XS, Y, Z = g.XS, g.Y, g.Z
    g.box(19, 31, -6, 6, 70, 76, "cream_dd")                  # the inside of the cuff, round the elbow
    g.fill((XS > 19) & (XS < 31) & (Y ** 2 + (Z - 100) ** 2 < 7.0 ** 2), "navy")        # the drum the arm turns on
    g.box(19, 33, -8, 8, 80, 98, "navy")                      # the sleeve
    g.box(19, 31, -8, 8, 98, 104, "navy")                     # the shoulder
    g.pbox(19, 33, -8, 8, 90, 92, "navy_l")                   # a paler stripe
    g.pbox(19, 33, -8, 8, 80, 84, "yellow")                   # the gold-yellow band
    g.box(17, 35, -10, 10, 74, 80, "cream")                   # the cuff: a thick cream roll at the elbow
    g.pbox(17, 35, -10, 10, 78, 80, "cream_l")
    emit(P, g, lim=((5, 9), (5, 9), (6, 12)), pref="z", lims=dict(yellow=((6, 10), (6, 10), (4, 4)), cream=((6, 10), (6, 10), (4, 4)),
                                                                   cream_l=((6, 12), (6, 12), (2, 2)), cream_dd=(8, 16), navy_l=((6, 10), (6, 10), (2, 2))),
         shade=0.35, proud_p=0.4, proud=(0.12, 0.4), seed=31 + s)
    # ---- forearm and hand (bent frame)
    g = Grid(Fo, 14, 36, -13, 13, 38, 82, cs=2, sx=s)
    XS, Y, Z = g.XS, g.Y, g.Z
    g.box(20, 30, -5, 5, 52, 80, "skin")                      # the bare forearm
    g.pbox(20, 30, -5, 5, 52, 54, "skin_d")
    g.box(18, 32, -7, 7, 54, 62, "bracer")                    # the leather bracer at the wrist
    g.pbox(18, 32, -7, 7, 54, 56, "bracer_d")
    Q.bias = len(P._ch)
    emit(Q, g, lim=(8, 16), lims={"skin": ((5, 10), (5, 10), (8, 14))}, shade=0.3, seed=41 + s)
    f = lambda *q, **k: Q.blk(Fo, *q, sx=s, **k)
    f(17.5, 32.5, -7.5, 7.5, 60.4, 62.0, "bracer_l")          # its upper lip
    f(32.0, 32.8, -1.2, 1.2, 56.6, 59.0, "gold", bevel=0.15)  # studs
    f(23.8, 26.2, -7.8, -7.0, 56.6, 59.0, "gold", bevel=0.15)
    if s > 0:
        # the free fist: one block, four finger bars, a thumb
        f(19.2, 31.0, -3.0, 6.4, 41.6, 52.0, "skin")
        for (z0, z1, nm, dy) in ((42.0, 44.6, "skin_d", 0.0), (44.6, 47.1, "skin", 0.5), (47.1, 49.6, "skin_l", 0.6), (49.6, 52.0, "skin", 0.2)):
            f(19.4, 30.8, -7.4 - dy, -3.0, z0, z1, nm)
        f(18.0, 24.5, -9.0, -6.6, 47.6, 51.2, "skin_l")       # thumb
    else:
        # RIG: the hammer hand, its own part turning at the wrist, closed round the handle in a hammer grip: the handle
        # runs through the fist from back to front (across the forearm), the head is beyond the thumb and the
        # forefinger and the pommel shows behind the little finger. The hammer is modelled in this fist and never
        # turns in it: the engine aims it with the wrist.
        wx, wy, wz = WRIST_AT
        JOINTS["HandR"] = tuple(float(v) for v in Fo.w((s * wx, wy, wz)))
        H = Part("HandR")
        h = lambda *q, **k: H.blk(Fo, *q, sx=s, **k)
        GX, GY, GZ = GRIP                                     # the grip's axis: along y, through (x GX, z GZ); its middle at y GY
        h(21.5, 28.5, -4.6, 3.2, 49.4, 53.6, "skin_d")        # wrist
        h(20.4, 30.2, GY - 5.1, GY + 5.5, 43.6, 51.0, "skin") # the back of the hand and the palm
        for i, (nm, dz) in enumerate((("skin_l", 0.3), ("skin", 0.0), ("skin_d", 0.2), ("skin", 0.6))):
            y0 = GY - 5.3 + i * 2.75                          # four fingers side by side along the grip, curled under it
            h(19.6, 31.0, y0, y0 + 2.75, 40.4 + dz, 46.4, nm)
        h(18.2, 21.6, GY - 6.0, GY + 1.6, 45.6, 49.4, "skin_l")    # the thumb, lying along the grip on the inside
        P.hand_part = H
        P.hammer_part = build_hammer(Fo, (s * GX, GY, GZ))
    return P, Q


HAMMER_TOP = -32.0                            # the top of the hammer's head, along its handle from the middle of the grip


def build_hammer(Fo, at):
    """The mallet as its own part, origin at the middle of the grip, modelled as it sits in his right fist (the fist
    occupies -5.3 .. 5.7 u along the handle: the head in front of it, the pommel behind). Its frame: -z up the handle
    to the head (forward, across the forearm), x along the head (along the forearm, so its faces lead when the forearm
    swings), y across it. The engine carries it with the hand. A big grey stone head bound with two gold bands, a
    gold cap and collar, a short wooden handle, a gold pommel."""
    hand = Fo.w(at)
    JOINTS["Hammer"] = tuple(float(v) for v in hand)
    P = Part("Hammer")
    S = Frame(Fo.R @ np.array([[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 0.0, 0.0]]), hand)
    P.frame = S
    b = lambda *a, **k: P.blk(S, *a, **k)
    # handle, wrapped
    for i, z in enumerate(np.arange(-9.5, 8.0, 4.5)):
        b(-1.7, 1.7, -1.7, 1.7, z, z + 4.5, ("wood_d", "wood", "wood_d", "wood")[i % 4], bevel=0.12)
    # pommel: a gold block and a cap
    b(-3.2, 3.2, -3.2, 3.2, 8.0, 13.0, "gold")
    b(-3.7, 3.7, -3.7, 3.7, 9.4, 11.6, "gold_l")
    b(-2.0, 2.0, -2.0, 2.0, 13.0, 14.2, "gold_d")
    # collar under the head, with a stud on each face
    b(-3.6, 3.6, -3.6, 3.6, -14.0, -9.5, "gold")
    b(-4.2, 4.2, -4.2, 4.2, -12.6, -10.8, "gold_d")
    # the head: a stone block, stepped in at each face, bound by two gold bands with studs, a gold cap on top
    z0, z1 = HAMMER_TOP + 1.6, -14.0                           # -30.4 .. -14.0
    b(-12.0, 12.0, -7.6, 7.6, z0, z1, "stone")
    b(-9.0, 9.0, -7.9, 7.9, z0 + 2.0, z1 - 2.0, "stone_d")     # the worn middle, proud of the block
    b(-3.0, 3.0, -8.2, 8.2, z0 + 4.0, z1 - 4.0, "stone_l")
    for sx in (1, -1):
        b(12.0, 14.4, -6.6, 6.6, z0 + 1.0, z1 - 1.0, "stone_l", sx=sx)       # the striking faces
        b(14.4, 15.6, -5.2, 5.2, z0 + 2.4, z1 - 2.4, "stone_ll", sx=sx)
        b(7.0, 10.6, -8.4, 8.4, z0 - 0.8, z1 + 0.8, "gold", sx=sx)           # a band round the head
        for sy in (1, -1):
            b(7.9, 9.7, sy * 8.3, sy * 9.0, (z0 + z1) / 2 - 0.9, (z0 + z1) / 2 + 0.9, "gold_l", sx=sx, bevel=0.15)
        b(7.9, 9.7, -0.9, 0.9, z0 - 1.4, z0 - 0.7, "gold_l", sx=sx, bevel=0.15)
    b(-4.4, 4.4, -5.0, 5.0, HAMMER_TOP, z0, "gold")           # the cap
    b(-1.6, 1.6, -1.6, 1.6, HAMMER_TOP - 0.9, HAMMER_TOP + 0.1, "gold_l", bevel=0.15)
    P.head_top = S.w((0, 0, HAMMER_TOP))
    P.tip_local = HAMMER_TOP
    return P


# the clumps heaped on his curls: (x, y, z, radius) u, in the head's frame
CURL_CLUMPS = ((-7, -5, 131, 6.5), (8, -2, 132, 6.5), (0, 7, 131, 7.0), (-14, 3, 128, 6.0), (14, 4, 128, 6.0), (2, -10, 130, 5.5),
               (-17, -5, 124, 5.5), (18, -4, 124, 5.5), (0, 12, 124, 6.5), (-11, 10, 126, 6.0), (12, 10, 126, 6.0))


def build_head():
    """A broad face under a head of dark curls: thick rectangle brows, white eyes with dark pupils, a block nose, a
    moustache and a full beard round the jaw and under the chin, ears showing among the curls. The head faces
    straight ahead (a troop in a rank)."""
    P = Part("Head")
    F = Frame().sub(RZ(0.0), P.joint)
    # the skull: 28 u wide, 22 deep, 22 high: with the curls the head is as broad as the swordsman's under his afro
    g = Grid(F, -20, 20, -19, 19, 100, 140, cs=2)
    X, Y, Z = g.X, g.Y, g.Z
    AX = np.abs(X)
    g.box(-14, 14, -11, 11, 106, 128, "skin")
    sk = g.solid()
    g.paint(sk & (AX > 12) & (Y < 1) & (Z < 114), "beard")    # the beard along the jaw, seen from the side
    g.paint(sk & (AX > 12) & (Y < -5) & (Z < 120), "beard")   # ... rising to the sideburns
    g.paint(sk & (Z < 108) & (Y < 3), "beard")                # ... and under the chin
    g.paint(sk & (Y > 9), "hair_d")                           # the nape, under the curls
    g.box(-12, 12, -11, -3, 104, 106, "beard")                # the beard under the jaw
    g.fill((AX > 14) & (AX < 16) & (Y > -3) & (Y < 3) & (Z > 112) & (Z < 120), "skin_l")      # ears
    emit(P, g, lim=(8, 14), lims={"beard": (5, 9), "skin_l": (8, 9), "hair_d": (6, 12)}, shade=0.3, seed=61)
    b = lambda *a, **k: P.blk(F, *a, **k)
    for sx in (1, -1):
        b(15.6, 16.8, -1.6, 1.8, 113.6, 118.0, "skin_d", sx=sx)    # the hollow of the ear
    # ---- the face: a 1 u plate in front of the skull; every feature is one or two boxes standing proud of it
    f = Grid(F, -16, 16, -17, -11, 100, 132)
    X, Y, Z = f.X, f.Y, f.Z
    AX = np.abs(X)
    L0, L1, L2, L3 = (Y > -12), (Y > -13), (Y > -14), (Y > -15)
    f.fill(L0 & (AX < 14) & (Z > 106) & (Z < 128), "skin")
    f.fill(L1 & (AX < 14) & (Z > 104) & (Z < 111), "beard")   # a full beard: the chin and the jaw ...
    f.fill(L2 & (AX < 10) & (Z > 104) & (Z < 109), "beard")   # ... thicker on the chin ...
    f.fill(L1 & (AX > 5) & (AX < 14) & (Z > 111) & (Z < 113), "beard")       # ... round the mouth ...
    f.fill(L1 & (AX > 10) & (AX < 14) & (Z > 113) & (Z < 116), "beard")      # ... stepping up the cheeks ...
    f.fill(L1 & (AX > 12) & (AX < 14) & (Z > 116) & (Z < 118), "beard")
    f.fill(L0 & (AX > 12) & (AX < 14) & (Z > 118) & (Z < 121), "beard_l")    # ... to the sideburns
    f.fill(L2 & (AX < 8) & (Z > 113) & (Z < 115), "beard")    # the moustache, joined to the beard and proud of it
    f.fill(L1 & (AX > 6) & (AX < 10) & (Z > 111) & (Z < 113), "beard")
    f.carve((AX < 4) & (Z > 110) & (Z < 113))                 # the mouth, in the gap the beard leaves: skin, a dark lip
    f.fill(L0 & (AX < 4) & (Z > 110) & (Z < 113), "skin_d")
    f.fill(L0 & (AX < 4) & (Z > 110) & (Z < 111), "lip")
    f.fill(L3 & (AX < 3) & (Z > 115) & (Z < 120), "skin_l")   # nose: one block
    f.fill(L1 & (AX > 3) & (AX < 5) & (Z > 115) & (Z < 117), "skin_d")       # nostrils' wings
    f.fill(L0 & (AX > 4) & (AX < 11) & (Z > 120) & (Z < 123), "white")       # eyes: a white and a pupil each
    f.fill(L0 & (AX > 5) & (AX < 8) & (Z > 120) & (Z < 123), "pupil")
    f.fill(L1 & (AX > 3) & (AX < 12) & (Z > 123) & (Z < 126), "beard")       # brows: one thick rectangle each
    emit(P, f, lim=(9, 15), lims={"beard": (8, 14), "beard_l": (5, 10), "white": (3, 3), "pupil": (3, 3), "skin_l": (8, 8), "skin_d": (2, 2),
                                  "lip": (8, 8)},
         shade=0.14, proud_p=0.25, proud=(0.08, 0.2), bevel=0.8, seed=63, core=False)
    for sx in (1, -1):
        b(5.3, 6.2, -12.35, -11.9, 121.8, 122.7, "gem_w", sx=sx, bevel=0.2)             # the glint in each eye
    # ---- the curls: a lumpy cap of 4 u cubes, each turned a little, with loose curls standing out of it
    cs = 2.0
    h = Grid(F, -26, 26, -20, 20, 104, 140, cs=cs)
    X, Y, Z = h.X, h.Y, h.Z
    AX = np.abs(X)
    d = (X / 20.5) ** 2 + ((Y - 0.5) / 15.5) ** 2 + np.where(Z > 124, ((Z - 124) / 12.0) ** 2, ((Z - 124) / 13.0) ** 2)
    for (cx, cy, cz, r) in CURL_CLUMPS:
        d = np.minimum(d, ((X - cx) ** 2 + (Y - cy) ** 2 + (Z - cz) ** 2) / r ** 2)
    d = d + (h.hash(2, 41) - 0.5) * 0.22
    hair = d < 1.0
    hair &= ~((AX < 14) & (np.abs(Y) < 12) & (Z < 128))       # the skull
    hair &= ~((Y < -12) & (Z < 127))                          # nothing in front of the face: the fringe stops above the brows
    hair &= ~((AX > 14) & (Y < 4) & (Y > -6) & (Z < 120))     # the ears stay in view
    hair &= ~((Y < 12) & (Y > -6) & (Z < 112))
    hair &= ~((Y < -6) & (Z < 118))                           # the sideburns are the beard's
    hair &= ~(Z < 110)
    hair &= (Z < HAIR_TOP) & (Y < 16)
    hair |= (AX < 14) & (np.abs(Y) < 12) & (Z > 128) & (Z < 132)             # always a layer on the crown of the skull
    h.fill(hair, "hair")
    nb = emit(P, h, lim=(3.6, 6.4), shade=0.75, proud_p=0.4, proud=(0.15, 0.5), seed=64, cjit=0.05, tilt=7.0, core_rgb=PRGB[PI["hair_d"]] * 0.8)
    rng = np.random.default_rng(11)
    curls = 0
    for (i, j, k) in np.argwhere(hair & h.surface()):
        if rng.random() > 0.2:
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
        size = rng.uniform(2.8, 3.8) + (0.8 if nrm[2] > 0.5 and rng.random() < 0.4 else 0.0)      # bigger ones on top
        c = np.array([X[i, j, k], Y[i, j, k], Z[i, j, k]]) + nrm * rng.uniform(0.2, 1.0) + rng.uniform(-0.6, 0.6, 3)         # tight to the mass
        if (c[2] + size * 0.75 > HAIR_TOP + 0.5 or c[1] + size * 0.75 > 16.5 or (c[1] < -11 and c[2] - size * 0.75 < 126.5)
                or (abs(c[0]) > 13 and c[1] < 5 and c[2] - size * 0.75 < 120.5)):
            continue                                          # not above his height, not into the pack, not over the face or the ears
        Rm = RZ(rng.uniform(-35, 35)) @ RY(rng.uniform(-25, 25)) @ RX(rng.uniform(-25, 25))
        name = ("hair", "hair_l", "hair_ll", "hair_d", "hair_l")[int(rng.integers(0, 5))]
        P.add(F.place(Rm, c), [-size / 2] * 3, [size / 2] * 3, PI[name], 0.06 * size, cull=False,
              rgb=np.clip(PRGB[PI[name]] * rng.uniform(0.94, 1.06), 0, 1))
        curls += 1
    print("hair: %d blocks, %d curls" % (nb, curls))
    return P


def torso_tiers(Z):
    """Half width and half depth of the torso at height Z (2 u steps): waist, belly and chest, shoulders."""
    hw = np.where(Z < 78, 16, np.where(Z < 100, 18, 16))
    hd = np.where(Z < 100, 11, 9)
    return hw, hd


def build_body():
    """-> (Body, Chest): the pelvis with the top of the skirt, the tool belt, its buckle, pouches and studs; the torso
    in the navy robe with the cream front panel, the pack's two shoulder straps and the sash across the chest."""
    P = Part("Body")
    blk = lambda *a, **k: P.blk(IDENT, *a, **k)
    # ---- pelvis: the top of the skirt, the belt
    g = Grid(IDENT, -26, 26, -19, 15, 30, 78, cs=2)
    X, Y, Z = g.X, g.Y, g.Z
    AX = np.abs(X)
    g.fill((AX < np.where(Z < 56, 22, 20)) & (np.abs(Y) < 11) & (Z > 52) & (Z < 66), "navy")
    g.paint(g.solid() & (AX < 6) & (Y < -9), "cream")         # the cream panel carries on up
    g.paint(g.solid() & (AX < 2) & (Y < -9), "cream_d")
    g.box(-18, 18, -13, 13, 66, 74, "belt")                   # the tool belt: broad, proud of the robe
    emit(P, g, lim=(10, 18), lims={"belt": ((10, 18), (8, 12), (4, 4)), "cream": ((4, 4), (2, 4), (8, 14)), "cream_d": ((4, 4), (2, 4), (8, 14))}, seed=81)
    for sx in (1, -1):
        blk(6.0, 7.6, -12.0, -11.0, 52.0, 66.0, "yellow_d", sx=sx, bevel=0.1)        # gold borders beside the cream panel
        blk(13.0, 15.2, -14.2, -13.0, 68.9, 71.1, "gold", sx=sx, bevel=0.15)         # belt studs
        blk(18.0, 19.2, -3.0, -0.8, 68.9, 71.1, "gold", sx=sx, bevel=0.15)
        blk(18.0, 19.2, 3.0, 5.2, 68.9, 71.1, "gold_d", sx=sx, bevel=0.15)
    # the big pouch on his left hip: a body, a flap, a gold stud; two loops hold it to the belt
    blk(8.6, 17.4, -17.6, -13.0, 54.0, 66.0, "belt")
    blk(8.2, 17.8, -18.4, -13.0, 60.5, 67.0, "belt_l")
    blk(12.0, 14.0, -19.1, -18.2, 61.6, 63.6, "gold", bevel=0.15)
    blk(9.4, 11.2, -14.6, -13.0, 66.0, 75.0, "belt_d")
    blk(14.8, 16.6, -14.6, -13.0, 66.0, 75.0, "belt_d")
    # a smaller one on his right, and a steel ring hanging from the belt beside it
    blk(-17.0, -10.6, -16.4, -13.0, 57.0, 66.0, "belt_l")
    blk(-17.4, -10.2, -17.0, -13.0, 62.0, 67.0, "belt")
    blk(-14.7, -12.9, -17.7, -16.8, 63.2, 65.0, "gold", bevel=0.15)
    blk(-14.7, -12.9, -14.6, -13.0, 66.0, 75.0, "belt_d")
    blk(-8.6, -7.2, -14.4, -13.0, 62.0, 66.0, "steel_l", bevel=0.15)
    blk(-9.8, -6.0, -14.6, -13.4, 60.0, 62.4, "steel", bevel=0.15)
    # buckle: a big hollow gold square, plates on plates
    blk(-6.6, 6.6, -16.6, -13.0, 63.4, 76.6, "gold")
    blk(-6.6, -4.0, -17.8, -16.4, 63.4, 76.6, "gold_l")
    blk(4.0, 6.6, -17.8, -16.4, 63.4, 76.6, "gold_l")
    blk(-4.0, 4.0, -17.8, -16.4, 74.0, 76.6, "gold_l")
    blk(-4.0, 4.0, -17.8, -16.4, 63.4, 66.0, "gold_l")
    blk(-4.0, 4.0, -17.0, -16.4, 66.0, 74.0, "gold_dd")
    blk(-2.0, 2.0, -18.2, -16.8, 68.0, 72.0, "gold_d", bevel=0.14)
    blk(-8.2, -6.6, -15.2, -13.0, 67.5, 72.5, "gold_d")
    blk(6.6, 8.2, -15.2, -13.0, 67.5, 72.5, "gold_d")

    # ---- torso: its own part, turning on the pelvis at the waist
    B = P
    P = Part("Chest")
    P.bias = len(B._ch)
    tb = lambda *a, **k: P.blk(IDENT, *a, **k)
    g = Grid(IDENT, -24, 24, -19, 15, 72, 114, cs=2)
    X, Y, Z = g.X, g.Y, g.Z
    AX = np.abs(X)
    hw, hd = torso_tiers(Z)
    body = (AX < hw) & (np.abs(Y) < hd) & (Z > 72) & (Z < 104)
    g.fill(body, "navy")
    g.paint(body & (Z < 76), "belt_d")
    g.paint(body & (Y < 0) & (AX > 12) & ((g.ix + g.iz // 3) % 4 == 0), "navy_d")        # folds
    g.paint(body & (AX < np.where(Z < 90, 6, np.where(Z < 98, 8, 10))) & (Y < 0) & (Z > 76), "cream")       # the cream front, opening to the collar
    g.paint(body & (AX < 2) & (Y < 0) & (Z > 76), "cream_d")                             # ... its placket
    g.paint(body & (Y < 0) & (Z > 76) & (AX > np.where(Z < 90, 6, np.where(Z < 98, 8, 10))) & (AX < np.where(Z < 90, 8, np.where(Z < 98, 10, 12))),
            "yellow")                                                                    # ... and the robe's gold-yellow edge beside it
    g.paint(body & (Z > 100) & (AX > 10), "navy_l")           # the yoke on the shoulders
    g.fill((X ** 2 + Y ** 2 < 6.2 ** 2) & (Z > 104) & (Z < 112), "skin_d")   # neck
    ring = (X / 11.0) ** 2 + (Y / 9.0) ** 2
    g.fill((ring < 1.0) & (ring > 0.4) & (Y > -6) & (Z > 104) & (Z < 106), "yellow")     # the collar: a gold-yellow roll behind the neck
    emit(P, g, lim=((6, 12), (8, 12), (6, 12)), lims={"skin_d": (12, 12), "belt_d": ((10, 18), (8, 12), (4, 4)), "cream": ((4, 6), (2, 4), (6, 10)),
                                                      "cream_d": ((4, 4), (2, 4), (6, 10)), "yellow": ((2, 2), (2, 6), (4, 8))}, shade=0.45, seed=82)
    for z in (79.0, 85.0, 91.0):                              # buttons down the placket
        tb(-1.0, 1.0, -11.9, -11.0, z, z + 2.0, "gold", bevel=0.15)
    for sx in (1, -1):
        # the pack's shoulder straps: up the chest, over the shoulder, down the back; a gold square fitting on each
        tb(9.0, 14.0, -12.6, -11.0, 76.0, 101.0, "belt", sx=sx)
        tb(9.0, 14.0, -10.8, -9.0, 100.0, 105.6, "belt_l", sx=sx)
        tb(9.0, 14.0, -9.2, 9.2, 104.0, 105.6, "belt", sx=sx)
        tb(9.0, 14.0, 9.0, 10.8, 100.0, 105.6, "belt_d", sx=sx)
        tb(9.0, 14.0, 11.0, 12.6, 76.0, 101.0, "belt_d", sx=sx)
        tb(8.2, 14.8, -14.0, -12.4, 91.0, 97.6, "gold", sx=sx)
        tb(10.4, 12.6, -14.7, -13.8, 93.2, 95.4, "gold_l", sx=sx, bevel=0.15)
        tb(10.4, 12.6, -13.3, -12.4, 80.0, 82.2, "gold_d", sx=sx, bevel=0.15)
    # the sash: from his left shoulder across the chest down to his right hip, over the straps (the picture, mirrored)
    n = 8
    for i in range(n):
        x = -17.5 + i * 4.2
        z = 100.5 - i * 3.3
        tb(x, x + 4.6, -14.4 if abs(x + 2.3) < 15 else -12.4, -11.0, z - 5.6, z, ("belt_l", "belt", "belt_l", "belt", "belt_l", "belt", "belt_l", "belt")[i], sx=-1)
        if i in (2, 5):
            tb(x + 1.4, x + 3.2, -15.1, -14.2, z - 3.7, z - 1.9, "gold", bevel=0.15, sx=-1)
    return B, P


def panel_frame(at, turn):
    """A frame on a face of the pack: its origin at `at`, x along the face, z up, -y out of it (turn: degrees about z)."""
    return IDENT.place(RZ(turn), at)


def blueprint(P, F, w, h, big=True):
    """A blueprint panel (half width w, half height h) in the face frame F: navy, a thin gold border, the drawing of a
    house in gold lines."""
    b = lambda *a, **k: P.blk(F, *a, cull=False, **k)
    b(-w, w, -0.9, 0.3, -h, h, "bp")
    b(-w + 1.6, w - 1.6, -1.1, -0.8, -h + 1.6, h - 1.6, "bp_l", bevel=0.05)
    t = 0.75                                                  # half of nothing: the lines' thickness
    line = lambda x0, x1, z0, z1: b(x0, x1, -1.6, -1.0, z0, z1, "line", bevel=0.05)
    for sx in (1, -1):                                        # the border
        line(sx * (w - 1.2) - t / 2, sx * (w - 1.2) + t / 2, -h + 0.9, h - 0.9)
    for sz in (1, -1):
        line(-w + 0.9, w - 0.9, sz * (h - 1.2) - t / 2, sz * (h - 1.2) + t / 2)
    hw = min(w * 0.5, h * 0.72)                               # the house: half width; walls, floor, roof, door, a window
    z0 = -h * 0.72
    wall = hw * 0.75
    line(-hw - 1.0, hw + 1.0, z0, z0 + t)
    for sx in (1, -1):
        line(sx * hw - t / 2, sx * hw + t / 2, z0, z0 + wall)
    line(-hw - 1.6, hw + 1.6, z0 + wall, z0 + wall + t)       # the eaves
    rise = min(hw * 0.8, h - 1.9 - (z0 + wall))               # the roof: two sloping lines
    ang = math.degrees(math.atan2(rise, hw + 1.2))
    ln = math.hypot(rise, hw + 1.2)
    for sx in (1, -1):
        R = RY(sx * ang)                                     # a bar along x, tilted up toward the ridge
        c = (sx * (hw + 1.2) / 2, -1.3, z0 + wall + t / 2 + rise / 2)
        P.blk(F.place(R, c), -ln / 2, ln / 2, -0.3, 0.3, -t / 2, t / 2, "line", bevel=0.05, cull=False)
    line(-hw * 0.25, hw * 0.25, z0 + wall * 0.55, z0 + wall * 0.55 + t)                  # the door
    for sx in (1, -1):
        line(sx * hw * 0.25 - t / 2, sx * hw * 0.25 + t / 2, z0, z0 + wall * 0.55)
    if big:
        for sx in (1, -1):                                    # a window each side of the door
            x = sx * hw * 0.62
            line(x - 1.4, x + 1.4, z0 + wall * 0.38, z0 + wall * 0.38 + t * 0.8)
            line(x - 1.4, x + 1.4, z0 + wall * 0.68, z0 + wall * 0.68 + t * 0.8)
            line(x - 1.4, x - 1.4 + t * 0.8, z0 + wall * 0.38, z0 + wall * 0.68)
            line(x + 1.4 - t * 0.8, x + 1.4, z0 + wall * 0.38, z0 + wall * 0.68 + t * 0.8)
        for (x, z) in ((-w + 3.2, h - 3.2), (w - 3.2, h - 3.2), (-w + 3.2, -h + 3.2), (w - 3.2, -h + 3.2)):
            line(x - 0.5, x + 0.5, z - 0.5, z + 0.5)          # the measuring marks in the corners


# the pack (u, world): a narrow frame behind the torso, between the swinging arms, and a wide crate on top of it at
# shoulder height (the arms swing under its wings)
PK_Y0, PK_Y1 = 14.0, 36.0                     # the frame: front (against his back) and back
PK_X = 16.0                                   # its half width
PK_Z0, PK_Z1 = 50.0, 98.0
CR_X, CR_Y0, CR_Y1 = 30.0, 18.0, 40.0         # the crate: half width, front, back
CR_Z0, CR_Z1 = 98.0, 128.0
# the rolled plans standing in the crate: (x, y, lean about x, lean about y (degrees), length u, half thickness u)
SCROLLS = ((-18.0, 29.0, -5.0, -15.0, 22.0, 4.2), (-7.0, 27.0, 6.0, -5.0, 28.0, 4.6), (4.5, 31.0, -7.0, 5.0, 25.0, 4.4),
           (16.0, 27.5, 4.0, 14.0, 21.0, 4.0), (23.0, 32.0, -3.0, 22.0, 15.0, 3.4))


def build_pack():
    """The frame pack on his back, its own part riding on the chest: planks in a frame of dark beams with gold corner
    fittings and studs, two leather belts round it; on top a wide crate, open, with rolled plans standing in it; a
    blueprint of a house on the crate's back and on its left side; a coil of rope hung on the back; a small glowing
    lantern hanging under the crate's left wing."""
    P = Part("Pack")
    b = lambda *a, **k: P.blk(IDENT, *a, **k)
    g = Grid(IDENT, -32, 32, 10, 44, 48, 130, cs=2)
    X, Y, Z = g.X, g.Y, g.Z
    AX = np.abs(X)
    g.box(-PK_X, PK_X, PK_Y0, PK_Y1, PK_Z0, PK_Z1, "wood")
    g.box(-12, 12, 10, PK_Y0, 78, 98, "belt_dd")              # the pad against his back
    g.box(-CR_X, CR_X, CR_Y0, CR_Y1, CR_Z0, CR_Z1, "wood")
    g.carve((AX < CR_X - 4) & (Y > CR_Y0 + 4) & (Y < CR_Y1 - 4) & (Z > CR_Z1 - 8))       # the crate is open: the plans stand in it
    g.paint(g.solid() & (AX < CR_X - 4) & (Y > CR_Y0 + 4) & (Y < CR_Y1 - 4) & (Z > CR_Z1 - 10), "wood_dd")
    wd = g.isn("wood")
    g.paint(wd & (g.hash(2, 7, ax=(1, 1, 0)) < 0.3), "wood_l")               # planks of two woods
    emit(P, g, lim=((4, 6), (4, 6), (12, 24)), pref="z", lims={"belt_dd": (8, 16), "wood_dd": (8, 16)}, shade=0.5, proud_p=0.3, proud=(0.1, 0.3), seed=91)
    # ---- the crate's frame: posts, rails, gold corner fittings with studs
    for sx in (1, -1):
        for (y0, y1) in ((CR_Y0 - 0.8, CR_Y0 + 3.4), (CR_Y1 - 3.4, CR_Y1 + 0.8)):
            b(CR_X - 3.4, CR_X + 0.8, y0, y1, CR_Z0, CR_Z1 + 0.8, "wood_d", sx=sx)       # posts
        for (z0, z1) in ((CR_Z0 - 0.8, CR_Z0 + 3.0), (CR_Z1 - 3.0, CR_Z1 + 0.8)):
            b(CR_X - 2.8, CR_X + 0.8, CR_Y0 + 3.4, CR_Y1 - 3.4, z0, z1, "wood_d", sx=sx) # side rails
        for (y0, y1) in ((CR_Y0 - 1.4, CR_Y0 + 4.2), (CR_Y1 - 4.2, CR_Y1 + 1.4)):
            for (z0, z1) in ((CR_Z0 - 1.4, CR_Z0 + 4.2), (CR_Z1 - 4.2, CR_Z1 + 1.4)):
                b(CR_X - 4.2, CR_X + 1.4, y0, y1, z0, z1, "gold", sx=sx)                 # a gold fitting on every corner
                ym, zm = (y0 + y1) / 2, (z0 + z1) / 2
                b(CR_X + 1.2, CR_X + 2.0, ym - 1.0, ym + 1.0, zm - 1.0, zm + 1.0, "gold_l", sx=sx, bevel=0.15)
                yo = y0 - 0.6 if y0 < 22 else y1 - 0.2
                b(CR_X - 2.4, CR_X - 0.4, yo, yo + 0.8, zm - 1.0, zm + 1.0, "gold_l", sx=sx, bevel=0.15)
    for (y0, y1) in ((CR_Y0 - 0.8, CR_Y0 + 2.8), (CR_Y1 - 2.8, CR_Y1 + 0.8)):
        for (z0, z1) in ((CR_Z0 - 0.8, CR_Z0 + 3.0), (CR_Z1 - 3.0, CR_Z1 + 0.8)):
            b(-CR_X + 3.4, CR_X - 3.4, y0, y1, z0, z1, "wood_d")                         # front and back rails
    for x in (-9.0, 9.0):                                     # gold plates on the back's top rail
        b(x - 2.4, x + 2.4, CR_Y1 + 0.6, CR_Y1 + 1.4, CR_Z1 - 3.4, CR_Z1 + 1.2, "gold")
        b(x - 1.0, x + 1.0, CR_Y1 + 1.2, CR_Y1 + 2.0, CR_Z1 - 2.1, CR_Z1 - 0.1, "gold_l", bevel=0.15)
    # ---- the frame below: posts, two leather belts with studs, gold feet
    for sx in (1, -1):
        b(PK_X - 3.0, PK_X + 0.8, PK_Y1 - 3.0, PK_Y1 + 0.8, PK_Z0 - 0.6, PK_Z1 - 0.8, "wood_d", sx=sx)
        b(PK_X - 3.0, PK_X + 0.8, PK_Y0, PK_Y0 + 3.2, PK_Z0 - 0.6, PK_Z1 - 0.8, "wood_d", sx=sx)
        b(PK_X - 3.8, PK_X + 1.4, PK_Y1 - 3.8, PK_Y1 + 1.4, PK_Z0 - 1.2, PK_Z0 + 4.2, "gold", sx=sx)
        b(PK_X - 2.2, PK_X - 0.2, PK_Y1 + 1.2, PK_Y1 + 2.0, PK_Z0 + 0.5, PK_Z0 + 2.5, "gold_l", sx=sx, bevel=0.15)
    b(-PK_X + 3.0, PK_X - 3.0, PK_Y1 - 2.6, PK_Y1 + 0.8, PK_Z0 - 0.6, PK_Z0 + 3.0, "wood_d")
    for (z, nm) in ((60.0, "belt"), (86.0, "belt_l")):
        b(-PK_X - 0.9, PK_X + 0.9, PK_Y0 + 0.4, PK_Y1 + 0.9, z, z + 4.0, nm)
        for x in (-11.0, 0.0, 11.0):
            b(x - 1.0, x + 1.0, PK_Y1 + 0.7, PK_Y1 + 1.5, z + 1.0, z + 3.0, "gold", bevel=0.15)
        for sx in (1, -1):
            b(PK_X + 0.7, PK_X + 1.5, 24.0, 26.0, z + 1.0, z + 3.0, "gold", sx=sx, bevel=0.15)
    # ---- the blueprints: a big one across the crate's back, a small one on its left side (the lantern's side)
    blueprint(P, panel_frame((0.0, CR_Y1 + 0.9, (CR_Z0 + CR_Z1) / 2), 180.0), 21.0, 11.4)
    blueprint(P, panel_frame((CR_X + 0.9, (CR_Y0 + CR_Y1) / 2, (CR_Z0 + CR_Z1) / 2), 90.0), 7.2, 11.0, big=False)
    # ---- the rolled plans: each two crossed slabs (an eight-sided roll), a darker end and the turn of the paper on it
    for i, (x, y, ax, ay, ln, r) in enumerate(SCROLLS):
        F = IDENT.place(RY(ay) @ RX(ax), (x, y, CR_Z1 - 9.0))
        nm = ("paper", "paper_l", "paper", "paper_l", "paper")[i]
        P.blk(F, -r, r, -r * 0.62, r * 0.62, 0.0, ln, nm, bevel=0.2)
        P.blk(F, -r * 0.62, r * 0.62, -r, r, 0.0, ln, nm, bevel=0.2)
        P.blk(F, -r * 0.8, r * 0.8, -r * 0.8, r * 0.8, 0.2, ln + 0.3, "paper_d", bevel=0.1)
        P.blk(F, -r * 0.42, r * 0.42, -r * 0.42, r * 0.42, ln, ln + 0.7, "paper_dd", bevel=0.1)
        P.blk(F, -r - 0.25, r + 0.25, -r * 0.62 - 0.25, r * 0.62 + 0.25, ln * 0.38, ln * 0.38 + 1.6, "belt", bevel=0.1)      # its tie
        P.blk(F, -r * 0.62 - 0.25, r * 0.62 + 0.25, -r - 0.25, r + 0.25, ln * 0.38, ln * 0.38 + 1.6, "belt", bevel=0.1)
    # ---- the coil of rope, hung from a gold hook on the back: two turns of short blocks
    cx, cy, cz = -1.0, PK_Y1 + 2.6, 72.0
    b(cx - 1.6, cx + 1.6, PK_Y1 + 0.8, PK_Y1 + 4.6, cz + 9.0, cz + 11.4, "gold")
    b(cx - 1.6, cx + 1.6, PK_Y1 + 3.4, PK_Y1 + 4.8, cz + 11.0, cz + 13.4, "gold_d")
    for turn, (rad, dy, n0) in enumerate(((9.0, 0.0, 12), (7.6, 2.0, 10))):
        for i in range(n0):
            a = 360.0 * (i + 0.5 * turn) / n0
            c = (cx + rad * math.sin(math.radians(a)), cy + dy, cz + rad * math.cos(math.radians(a)) - 1.2 * turn)
            seg = 2 * math.pi * rad / n0 * 0.56
            P.blk(IDENT.place(RY(a), c), -seg, seg, -1.7, 1.7, -1.8, 1.8, ("rope", "rope_l", "rope_d", "rope")[(i + turn) % 4], bevel=0.18, cull=False)
    # ---- the lantern, hanging by a ring under the crate's left wing: an iron cage, a glowing core
    lx, ly = 22.6, 33.0
    b(lx - 1.2, lx + 1.2, ly - 1.2, ly + 1.2, 94.4, CR_Z0 - 0.6, "steel_d")          # the hook
    b(lx - 1.8, lx + 1.8, ly - 0.7, ly + 0.7, 92.6, 95.2, "steel")                    # the ring
    b(lx - 2.6, lx + 2.6, ly - 2.6, ly + 2.6, 91.2, 92.8, "steel_dd")                 # the cap, stepped
    b(lx - 4.4, lx + 4.4, ly - 4.4, ly + 4.4, 89.6, 91.4, "steel_dd")
    b(lx - 3.0, lx + 3.0, ly - 3.0, ly + 3.0, 81.6, 89.8, "glow", bevel=0.05)         # the light
    b(lx - 2.0, lx + 2.0, ly - 3.3, ly + 3.3, 83.0, 88.4, "glow_l", bevel=0.05)
    b(lx - 3.3, lx + 3.3, ly - 2.0, ly + 2.0, 83.0, 88.4, "glow_l", bevel=0.05)
    for sx in (1, -1):
        for sy in (1, -1):
            b(lx + sx * 3.9 - 0.7, lx + sx * 3.9 + 0.7, ly + sy * 3.9 - 0.7, ly + sy * 3.9 + 0.7, 81.4, 89.8, "steel_dd", bevel=0.15)
    b(lx - 4.4, lx + 4.4, ly - 4.4, ly + 4.4, 80.0, 81.8, "steel_dd")                 # the base
    b(lx - 2.4, lx + 2.4, ly - 2.4, ly + 2.4, 79.0, 80.2, "steel_d")
    P.lantern = (lx, ly, 85.7)
    return P


WHOLE = ["Body", "Head", "ArmL", "ArmR", "LegL", "LegR"]


def wholes(parts):
    """The limbs as the single rigid pieces they are while every elbow, knee and wrist is at rest (the pack with the
    torso, the hammer with its arm)."""
    return {"Body": Combo(parts["Body"], parts["Chest"], parts["Pack"]), "Head": parts["Head"], "ArmL": Combo(parts["ArmL"], parts["ForeL"]),
            "ArmR": Combo(parts["ArmR"], parts["ForeR"], parts["HandR"], parts["Hammer"]), "LegL": Combo(parts["LegL"], parts["ShinL"]),
            "LegR": Combo(parts["LegR"], parts["ShinR"])}


def build_builder():
    t0 = time.time()
    parts = {}
    for s_, side in ((1, "L"), (-1, "R")):
        parts["Leg" + side], parts["Shin" + side] = build_leg(s_)
        parts["Arm" + side], parts["Fore" + side] = build_arm(s_)
    parts["HandR"] = parts["ArmR"].hand_part
    parts["Hammer"] = parts["ArmR"].hammer_part
    parts["Head"] = build_head()
    parts["Body"], parts["Chest"] = build_body()
    parts["Pack"] = build_pack()
    for q in parts.values():
        q.finalize()
    print("sculpted in %.1f s" % (time.time() - t0))
    return parts


# ---------------------------------------------------------------------------------------------------- checks

def pivot(key):
    return [round(c * U, 5) for c in JOINTS[key]]


def check_pose(parts, pts, label, **ang):
    """Where the rigid pieces run into each other in a pose (degrees about x at the hips and shoulders; Head about z)."""
    axes = dict(LegL=("x", ang.get("legl", 0)), LegR=("x", ang.get("legr", 0)), ArmL=("x", ang.get("arml", 0)),
                ArmR=("x", ang.get("armr", 0)), Head=("z", ang.get("head", 0)), Body=("x", 0))
    posed = {k: rotated(pts[k], parts[k].joint, axes[k][0], axes[k][1]) for k in WHOLE}
    occ = {k: occ_grid(posed[k], 0.5) for k in WHOLE}
    bad = []
    for i, a in enumerate(WHOLE):
        for b in WHOLE[i + 1:]:
            if {a, b} in ({"Body", "LegL"}, {"Body", "LegR"}, {"Body", "Head"}, {"LegL", "LegR"}):
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
                        blade=(0.38, 1.0), fur=(0.95, 0), gem=(0.15, 0), core=(1.0, 0), stone=(0.9, 0), wood=(0.7, 0), paper=(0.8, 0),
                        glow=(0.5, 0))[kind]
    setv("Roughness", rough)
    setv("Metallic", metal)
    if kind in ("skin", "fur"):
        setv("Subsurface Weight", 0.2 if kind == "skin" else 0.12)
        setv("Subsurface Radius", (1.0, 0.45, 0.25) if kind == "skin" else (1.0, 0.9, 0.7))
        setv("Subsurface Scale", 0.012 if kind == "skin" else 0.02)
    if kind == "fur":
        setv("Sheen Weight", 0.15)
    if kind in ("gem", "glow"):
        nt.links.new(col.outputs["Color"], b.inputs["Emission Color"])
        setv("Emission Strength", 0.25 if kind == "gem" else 4.0)
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
    path = os.path.join(V.PREVIEWS, "builder_%s.png" % name)
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


def rig(obs):
    """Parent the objects as the engine does (after the export, which wants them loose)."""
    for key, ob in obs.items():
        if key in PARENT:
            ob.parent = obs[PARENT[key]]


def pose(obs, **ang):
    """Turn joints by degrees about x (Head: about z): legl, legr, shinl, shinr, arml, armr, forel, forer, handr, chest,
    body, head. Positive swings a hanging limb backwards. The hammer sits in the fist and moves with the hand, the
    pack rides on the chest."""
    for key, ob in obs.items():
        parent = PARENT.get(key)
        base = np.array(JOINTS[parent], np.float64) if parent else np.zeros(3)
        ob.location = [float(v) * U for v in np.array(JOINTS[key], np.float64) - base]
        a = ang.get(key.lower(), 0.0)
        ob.rotation_euler = (0, 0, math.radians(a)) if key == "Head" else (math.radians(a), 0, math.radians(ang.get(key.lower() + "_z", 0.0)))



CARRY = dict(armr=4.0, forer=-12.0, handr=-25.0)     # how the previews hold the hammer: arm down, the head up and forward


def want(name):
    return VIEWS is None or name in VIEWS


def mirrored(path, out):
    a = load_px(path)
    save_px(np.ascontiguousarray(a[:, ::-1]), out)
    return out


def main():
    t0 = time.time()
    V.reset_scene()
    parts = build_builder()
    for k in ORDER:
        cull(parts[k])
    print("culled in %.1f s" % (time.time() - t0))
    ao_field(parts)
    print("shading field in %.1f s" % (time.time() - t0))

    lo = np.array([1e9] * 3)
    hi = -lo
    top = 0.0
    for k in ORDER:
        P = part_points(parts[k], step=1.0, cores=False)
        lo, hi = np.minimum(lo, P.min(axis=0)), np.maximum(hi, P.max(axis=0))
        if k not in ("Pack", "Hammer"):
            top = max(top, float(P[:, 2].max()))
    print("BUILDER size: x %.3f m (%.2f..%.2f), y %.3f m (%.2f..%.2f), figure %.4f m, with the pack %.4f m (lowest %.4f)" % (
        (hi[0] - lo[0]) * U, lo[0] * U, hi[0] * U, (hi[1] - lo[1]) * U, lo[1] * U, hi[1] * U, top * U, hi[2] * U, lo[2] * U))
    W = wholes(parts)
    pts = {k: part_points(W[k], step=0.6, shrink=0.4, cores=False) for k in WHOLE}
    check_pose(W, pts, "rest")
    check_pose(W, pts, "walk A", legl=35, legr=-35, arml=-35, armr=35)
    check_pose(W, pts, "walk B", legl=-35, legr=35, arml=35, armr=-35)
    check_pose(W, pts, "head turned", head=22)

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
    print("BUILDER triangles in all: %d  (%.1f s)" % (total, time.time() - t0))
    hm = parts["Hammer"]
    head_dir = [round(float(v), 5) for v in hm.frame.R @ np.array([0.0, 0.0, -1.0])]
    # The character file, in SM_KingB.json's format. "sword" is the hammer, described as the swordsman's sword is (the
    # direction of the head from the grip is the blade's): the engine swings it with the same poses. It never leaves
    # the fist ("has_sheath": false; the scabbard fields are "stay in the fist").
    grip = dict(part="Hammer", blade_dir=head_dir, has_sheath=False, length=round(abs(hm.tip_local) * U, 5),
                grip=pivot("Hammer"), tip=[round(float(v) * U, 5) for v in hm.head_top],
                sheath_dir=head_dir, sheath_pos=pivot("Hammer"),
                delta=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    meta = dict(height=HEIGHT, radius=RADIUS, voxel=U, elbow_l=ELBOW["L"], elbow_r=ELBOW["R"],
                cape=dict(cols=CAPE_COLS, rows=CAPE_ROWS), has_sheath=False,
                parts={key: dict(mesh=PREFIX + key, pivot=pivot(key), parent=PARENT.get(key, "")) for key in ORDER},
                sword=grip, hammer=grip,
                pack=dict(part="Pack", parent=PARENT["Pack"], pivot=pivot("Pack"), lantern=[round(float(v) * U, 5) for v in parts["Pack"].lantern]))
    with open(os.path.join(V.MESHES, NAME + ".json"), "w") as f:
        json.dump(meta, f, indent=1)
    print("wrote %s.json" % NAME)
    if NO_RENDER:
        return

    to_preview(obs, parts)
    stage()
    rig(obs)
    Pv = V.PREVIEWS
    p = lambda n: os.path.join(Pv, "builder_%s.png" % n)
    pose(obs, **CARRY)
    if want("hero"):
        # the picture's pose, mirrored: seen from his left, the free fist nearest, the hammer raised in the far hand
        pose(obs, head=12.0, arml=-4.0, forel=-12.0, armr=-30.0, armr_z=-55.0, forer=-56.0, handr=-6.0)
        hero = shot("hero", az=47, el=-9, dist=4.1, target=(0.0, 0.08, 0.92), res=(900, 1250), lens=66)
        back = shot("hero_back", az=150, el=4, dist=4.1, target=(0.0, 0.08, 0.92), res=(900, 1250), lens=66)
        tiles = [fit_h(load_px(REF), 1250), fit_h(load_px(hero)[:, ::-1], 1250), fit_h(load_px(back)[:, ::-1], 1250)]
        save_px(np.ascontiguousarray(np.concatenate([t[..., :4] for t in tiles], axis=1)), p("compare"))
        print("montage", p("compare"))
        pose(obs, **CARRY)
    if want("sides"):
        tiles = [shot("front", 0, 2, dist=7.0, target=(0, 0.08, 0.9), res=(720, 960)), shot("right", -90, 2, dist=7.0, target=(0, 0.08, 0.9), res=(720, 960)),
                 shot("back", 180, 4, dist=7.0, target=(0, 0.08, 0.9), res=(720, 960)), shot("left", 90, 2, dist=7.0, target=(0, 0.08, 0.9), res=(720, 960))]
        montage(tiles, p("sides"), H=960)
    if want("face"):
        tiles = [shot("face_front", 0, 0, dist=6.0, target=(0, 0, 1.47), res=(800, 800), lens=230),
                 shot("face_34", 30, -8, dist=6.0, target=(0, 0, 1.47), res=(800, 800), lens=230),
                 shot("face_side", 90, 0, dist=6.0, target=(0, 0, 1.47), res=(800, 800), lens=230)]
        montage(tiles, p("faces"), H=800)
    if want("pack"):
        tiles = [shot("pack_back", 180, 8, dist=5.0, target=(0, 0.3, 1.15), res=(800, 900), lens=120),
                 shot("pack_left", 115, 8, dist=5.0, target=(0, 0.3, 1.15), res=(800, 900), lens=120)]
        montage(tiles, p("pack"), H=900)
    if want("game"):
        tiles = [shot("game_front", 25, 40, dist=7.4, res=(720, 960)), shot("game_back", 205, 40, dist=7.4, res=(720, 960))]
        montage(tiles, p("game"), H=960)
    if want("rest"):
        pose(obs)                                             # exactly as exported: every joint at zero
        tiles = [shot("rest_front", -29, 0, dist=7.4, res=(720, 960)), shot("rest_right", -90, 2, dist=7.4, res=(720, 960))]
        montage(tiles, p("rest"), H=960)
        pose(obs, **CARRY)
    if want("walk"):
        pose(obs, legl=30, shinl=-10, legr=-25, shinr=35, arml=-30, forel=-25, armr=30, forer=-5, handr=-25, chest=-6)
        tiles = [shot("walk_front", -29, 0, dist=7.4, res=(720, 960)), shot("walk_left", 90, 2, dist=7.4, res=(720, 960)),
                 shot("walk_back", 150, 8, dist=7.4, res=(720, 960)), shot("walk_right", -90, 2, dist=7.4, res=(720, 960))]
        montage(tiles, p("walk"), H=960)
        pose(obs, **CARRY)
    print("done in %.1f s" % (time.time() - t0))


main()
