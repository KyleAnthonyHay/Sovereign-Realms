"""The FARMER MAN (References/Remake/farmer_man.png): a stocky bearded farmer under a wide straw hat, in a cream shirt
with rolled sleeves and a green apron (a gold wheat emblem in a gold frame, a gold hem), a pitchfork in his left fist
and a woven basket of wheat, carrots and apples on his back with a small lit lantern hanging from its side. Built like
King David (king_b.py) and the troops (troop_archer.py, troop_builder.py, troop_swordsman.py) from individual bevelled
cubes and slabs of several sizes, as rigid parts (a wooden toy) that the game swings about their joints. Each part is
exported on its own with its mesh origin at its joint.

    Blender -b --factory-startup --python Tools/blender/assets/troop_farmer_man.py -- [--no-render] [--views hero,sides,...] [--fast] [--gpu]

Units: "u" = 1.25 cm. World axes: +X is his LEFT (he faces -Y), z = 0 is the ground between his feet.

THE HEAD is put together from two other troops, on purpose:
  the FACE is the ARCHER's (troop_archer.py, build_head): her skull (24 u wide, 20 deep, 22 high, starting 2 u above
      the neck joint), ONE smooth skin plate in front of it, her nose (one small block with a shadow under it), her
      mouth (one thin lip bar) and her ears (a 2 u block each side with a dark hollow), all at her heights above the
      skull's base. His jaw is broadened (2 u wider each side, below the ears) and carries the beard.
  the EYES are the SWORDSMAN's (troop_swordsman.py, build_head): on a grid of 1 u cells in front of the plate, a white
      6 u wide and 3 u high each side with a 3 x 3 u dark pupil set one cell in from its inner end, a brow that is one
      thick rectangle (8 x 3 u) resting on the eye and standing one cell proud of it, and a small glint block high on
      the pupil's inner side. No lids (he has none either).

THE RIG (the block "THE RIG" below) is King David's, as the troops use it: the same part names, parents and joints, so
the same C++ can swing him. He has no cape. Extra parts next to the King's, as the archer has her Bow, Quiver and Arrow:
  Pitchfork   in the left fist (rides on ForeL, as the archer's Bow); origin at the middle of the grip; it stands
              upright with its butt on the ground while the arm is at rest
  BackBasket  the woven basket on his back with the wheat, carrots and apples (rides on Chest, as the Quiver)
  Lantern     hanging from the basket's right side (rides on BackBasket; origin at its ring, so it can swing); its
              light is the "glow" slot (the emissive voxel material, as the Builder's lantern)
  Hat         the straw hat (rides on Head; origin on the crown of the skull)
  Pouch       the leather pouch on his right hip (rides on Body; origin where its loops hang from the belt)
SM_FarmerMan.json carries "pitchfork", "basket", "lantern", "hat" and "pouch" entries for them.

The block engine (Part, Grid, emit, cull, the baked shading, the mesh) and the preview stage are copies of
troop_builder.py's (which are king_b.py's), kept in this file so that nothing here depends on those scripts.
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
CPU_ONLY = "--gpu" not in ARGS                # Cycles on the Metal GPU can crash here: the CPU unless asked
VIEWS = set(ARGS[ARGS.index("--views") + 1].split(",")) if "--views" in ARGS else None

U = 0.0125
NAME = "SM_FarmerMan"
PREFIX = NAME + "_"
SHOT_PREFIX = "farmer_man_"
REF = os.path.join(V.ROOT, "References", "Remake", "farmer_man.png")

# ================================================================================================== THE RIG
# King David's rig (king_b.py / SM_KingB.json) as the troops use it, without the scabbard and the cape. A tree of
# rigid parts (PARENT; no entry = the figure's root). Body is the pelvis, Chest turns on it at the waist; each arm is
# an upper arm and a forearm (the left with its hand, which holds the pitchfork; the right hand is its own part,
# "HandR", turning at the wrist); each leg a thigh (with its half of the shirt's skirt and of the apron) and a shin
# (with the boot).
ORDER = ["Body", "Chest", "Head", "ArmL", "ForeL", "ArmR", "ForeR", "HandR", "LegL", "ShinL", "LegR", "ShinR",
         "Hat", "Pouch", "BackBasket", "Lantern", "Pitchfork"]
PARENT = {"Chest": "Body", "Head": "Chest", "ArmL": "Chest", "ArmR": "Chest", "ForeL": "ArmL", "ForeR": "ArmR", "HandR": "ForeR",
          "ShinL": "LegL", "ShinR": "LegR",
          "Hat": "Head", "Pouch": "Body", "BackBasket": "Chest", "Lantern": "BackBasket", "Pitchfork": "ForeL"}
CAPE_COLS, CAPE_ROWS = 0, 0                   # no cape
ELBOW = {"L": 65.0, "R": 22.0}                # the bend the forearms are modelled with (degrees): the left holds the pitchfork up
WRIST_L = 25.0                                # the left fist is modelled turned up this much more: with the elbow, the shaft stands upright
ARM_OUT = {"L": 7.0, "R": 6.0}                # how far the arms hang out from the shoulders (degrees)
KNEE_Z = 28.0
SKULL_Z = 106.0                               # the base of the skull (the archer's is 2 u above her neck joint, as here)
TOP = 152.0                                   # nothing stands higher (the wheat in the basket)
HEIGHT, RADIUS, STRIDE = 1.75, 0.42, 1.8      # metres, for the character's capsule and gait (the troops' own)
LAN_X, LAN_Y, LAN_Z = -25.5, 31.0, 92.0       # the ring the lantern hangs by
JOINTS = {                                    # u, world
    "Body": (0, 0, 56), "Chest": (0, 0, 73), "Head": (0, 0, 104),
    "ArmL": (25, 0, 100), "ArmR": (-25, 0, 100),
    "LegL": (12, 0, 54), "LegR": (-12, 0, 54),
    "ShinL": (12, 0, KNEE_Z), "ShinR": (-12, 0, KNEE_Z),
    "Hat": (0, 0, 128),                       # the crown of the skull
    "Pouch": (-14, -13, 66),                  # where its loops leave the belt
    "BackBasket": (0, 24, 82),                # the middle of the basket on his back
    "Lantern": (LAN_X, LAN_Y, LAN_Z),
    # set while building: ForeL / ForeR (the elbows, build_arm), HandR (the wrist), Pitchfork (the middle of the grip
    # in the left fist, build_pitchfork)
}
ELBOW_AT = (25, 0, 76)                        # the elbow, in the upper arm's own frame (x mirrored for the right arm)
WRIST_AT = (25, -0.5, 52.0)                   # the wrist, in the forearm's frame
GRIP = (24.8, -3.5, 45.8)                     # the middle of what a fist holds, in the hand's frame
# ==================================================================================================

MATN = ["paint", "gold", "metal", "wool", "glow"]
KINDS = ["cloth", "skin", "hair", "leather", "gold", "metal", "fur", "gem", "core", "blade", "stone", "wood", "paper", "glow"]
_PAL = [
    # name        colour     slot     preview kind
    ("gold",     "#FFB616", "gold", "gold"), ("gold_l", "#FFD63E", "gold", "gold"), ("gold_d", "#E39510", "gold", "gold"),
    ("gold_dd",  "#A2640C", "gold", "gold"),
    ("steel",    "#9A9496", "metal", "metal"), ("steel_l", "#B4ADAB", "metal", "metal"), ("steel_ll", "#CAC3BE", "metal", "metal"),
    ("steel_d",  "#77737A", "metal", "metal"), ("steel_dd", "#45434A", "metal", "metal"),
    ("skin",     "#D38B4E", "paint", "skin"), ("skin_l", "#E39D5E", "paint", "skin"), ("skin_d", "#B6733B", "paint", "skin"),
    ("skin_dd",  "#96592B", "paint", "skin"), ("lip", "#8E4A2C", "paint", "skin"),
    ("hair",     "#5A3A22", "paint", "hair"), ("hair_l", "#6C472A", "paint", "hair"), ("hair_ll", "#7E5532", "paint", "hair"),
    ("hair_d",   "#472C18", "paint", "hair"),
    ("beard",    "#5E3C21", "paint", "hair"), ("beard_l", "#72492A", "paint", "hair"), ("beard_d", "#4A2E18", "paint", "hair"),
    ("brow",     "#3A2414", "paint", "hair"),
    ("green",    "#41602B", "paint", "cloth"), ("green_l", "#517335", "paint", "cloth"), ("green_d", "#334E21", "paint", "cloth"),
    ("green_dd", "#263B18", "paint", "cloth"),
    ("cream",    "#DCC69C", "paint", "cloth"), ("cream_l", "#ECDAB6", "paint", "cloth"), ("cream_d", "#C2AA7C", "paint", "cloth"),
    ("cream_dd", "#A1895C", "paint", "cloth"),
    ("belt",     "#7B4A24", "paint", "leather"), ("belt_l", "#96602F", "paint", "leather"), ("belt_d", "#5A3418", "paint", "leather"),
    ("belt_dd",  "#40240F", "paint", "leather"),
    ("bracer",   "#6A4226", "paint", "leather"), ("bracer_l", "#82532F", "paint", "leather"), ("bracer_d", "#4E2F1A", "paint", "leather"),
    ("pouch",    "#C4A06A", "paint", "leather"), ("pouch_l", "#D6B680", "paint", "leather"), ("pouch_d", "#A88652", "paint", "leather"),
    ("trouser",  "#5C3C26", "paint", "cloth"), ("trouser_l", "#6F4A30", "paint", "cloth"), ("trouser_d", "#462C1B", "paint", "cloth"),
    ("boot",     "#77492A", "paint", "leather"), ("boot_l", "#935E34", "paint", "leather"), ("boot_d", "#5A361D", "paint", "leather"),
    ("sole",     "#4A2E1B", "paint", "leather"), ("sole_d", "#33200F", "paint", "leather"),
    ("wood",     "#8A5630", "paint", "wood"), ("wood_l", "#A0693C", "paint", "wood"), ("wood_d", "#6E4224", "paint", "wood"),
    ("wood_dd",  "#4E2D17", "paint", "wood"),
    ("straw",    "#E2A93A", "paint", "paper"), ("straw_l", "#F2C254", "paint", "paper"), ("straw_d", "#C48C2A", "paint", "paper"),
    ("straw_dd", "#9E6C20", "paint", "paper"),
    ("hatband",  "#8A5A2C", "paint", "leather"),
    ("wick",     "#8C5A2E", "paint", "wood"), ("wick_l", "#A8733C", "paint", "wood"), ("wick_d", "#6C4321", "paint", "wood"),
    ("wick_dd",  "#3E2511", "paint", "wood"),
    ("rope",     "#C8954C", "paint", "paper"), ("rope_l", "#DBAB60", "paint", "paper"), ("rope_d", "#A8793B", "paint", "paper"),
    ("wheat",    "#EDB93A", "paint", "paper"), ("wheat_l", "#F8D262", "paint", "paper"), ("wheat_d", "#CC9628", "paint", "paper"),
    ("carrot",   "#EA7A1C", "paint", "cloth"), ("carrot_l", "#F6943A", "paint", "cloth"), ("carrot_d", "#C96210", "paint", "cloth"),
    ("leaf",     "#6F9C2C", "paint", "cloth"), ("leaf_l", "#8EBA3A", "paint", "cloth"), ("leaf_d", "#55791F", "paint", "cloth"),
    ("apple",    "#B92A1F", "paint", "cloth"), ("apple_l", "#D8432F", "paint", "cloth"), ("apple_d", "#8F1D17", "paint", "cloth"),
    ("white",    "#F4EFE4", "paint", "gem"), ("pupil", "#15100E", "paint", "hair"), ("gem_w", "#FFF4DA", "paint", "gem"),
    ("glow",     "#FFA62E", "glow", "glow"), ("glow_l", "#FFC85A", "glow", "glow"),
    ("core",     "#17120F", "paint", "core"),
]
PN = [None] + [p[0] for p in _PAL]
PI = {n: i for i, n in enumerate(PN)}
PRGB = np.array([[0, 0, 0]] + [[int(p[1][i:i + 2], 16) / 255.0 for i in (1, 3, 5)] for p in _PAL], np.float32)
PMAT = np.array([0] + [MATN.index(p[2]) for p in _PAL], np.int32)
PKIND = np.array([0] + [KINDS.index(p[3]) for p in _PAL], np.int32)


# ##################################################################################################################
# The block engine: a copy of troop_builder.py's, which is king_b.py's (small maths, Part, Grid, emit, the chamfered box, cull, the baked shading,
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
NOSHADE = ("white", "pupil", "lip", "gem_w", "core", "glow", "glow_l", "brow")


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
AO_LO = np.array([-72.0, -52.0, -4.0])
AO_N = (288, 224, 320)


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
# The farmer
# ##################################################################################################################
# Shapes are sculpted on 2 u cells (1 u for the eyes and the beard) and MERGED into the fewest, largest boxes by
# emit(); buckles, studs, the fists, the face's features, the pitchfork, the lantern and the produce are direct blocks.

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


def gold_square(put, x0, x1, z0, z1, yf, t=2.0, inner="belt_dd", stud=True):
    """A hollow gold square buckle facing -y, its front at yf: a plate, four bars standing proud of it, a dark middle."""
    put(x0, x1, yf + 1.0, yf + 2.4, z0, z1, "gold")
    put(x0, x0 + t, yf, yf + 1.2, z0, z1, "gold_l")
    put(x1 - t, x1, yf, yf + 1.2, z0, z1, "gold_l")
    put(x0 + t, x1 - t, yf, yf + 1.2, z1 - t, z1, "gold_l")
    put(x0 + t, x1 - t, yf, yf + 1.2, z0, z0 + t, "gold_l")
    put(x0 + t, x1 - t, yf + 0.6, yf + 1.2, z0 + t, z1 - t, inner)
    if stud:
        xm, zm = (x0 + x1) / 2, (z0 + z1) / 2
        put(xm - 0.9, xm + 0.9, yf - 0.3, yf + 0.8, zm - 0.9, zm + 0.9, "gold_d", bevel=0.15)


APRON_HEM = 28.0                              # the apron's gold hem (u above the ground): it hangs to the knees
SKIRT_HEM = 40.0                              # the shirt's skirt ends at mid thigh


def build_leg(s):
    """-> (thigh, shin). The thigh carries its half of the shirt's skirt and its half of the apron (the gold frame, the
    emblem's ears of wheat, the gold hem); the shin the boot, its straps and gold buckle, and the drum the knee turns on."""
    side = "L" if s > 0 else "R"
    P, Q = Part("Leg" + side), Part("Shin" + side)
    g = Grid(IDENT, 1, 27, -19, 15, 20, 68, cs=2, sx=s)
    XS, Y, Z = g.XS, g.Y, g.Z
    g.box(5, 19, -7, 7, 24, 54, "trouser")                    # the thigh, in brown trousers
    sk = g.bm(1, 21, -9, 9, SKIRT_HEM, 54)                    # the half of the shirt's skirt that swings with this leg ...
    drum = (XS > 1) & (XS < 21) & (Y ** 2 + (Z - 54) ** 2 < 9.7 ** 2) & (Z > 54)        # ... ending in a drum about the hip axis
    g.fill(sk | drum, "cream")
    g.paint(sk & ((g.ix % 3) == 0), "cream_d")                # pleats
    g.paint(sk & (Z < SKIRT_HEM + 2), "cream_dd")             # hem
    ap = (XS > 1) & (XS < 13) & (Y > -11) & (Y < -9) & (Z > APRON_HEM) & (Z < 54)       # this leg's half of the apron
    g.fill(ap, "green")
    hh = g.hash(2, 5 + s)
    g.paint(ap & (hh < 0.2), "green_l")
    g.paint(ap & (hh > 0.85), "green_d")
    hem = ap & (Z < APRON_HEM + 4)
    g.paint(hem, "gold")                                      # the gold hem, a few blocks of it hanging lower
    g.grow(hem & (Z < APRON_HEM + 2) & (g.hash(2, 9 + s, ax=(1, 0, 0)) < 0.4), "-z")
    emit(P, g, lim=((4, 8), (4, 8), (8, 16)), pref="z", lims={"gold": ((4, 6), (2, 2), (2, 4)), "cream_dd": ((4, 8), (4, 8), (2, 2)),
                                                             "trouser": (8, 16), "green": ((4, 6), (2, 2), (6, 12))}, seed=20 + s)
    b = lambda *a, **k: P.blk(IDENT, *a, sx=s, **k)
    b(1.0, 9.8, -11.9, -11.0, 34.0, 35.8, "gold")             # the gold frame round the emblem: its foot ...
    b(8.0, 9.8, -11.9, -11.0, 35.8, 54.0, "gold_d")           # ... and its side (it closes on the pelvis)
    for i, z in enumerate((38.4, 42.0, 45.6)):                # the ears of the wheat emblem, stepping up and out from the stem
        b(1.3, 3.7, -12.0, -11.0, z, z + 2.6, "gold_l" if i % 2 else "gold", bevel=0.12)
        b(3.5, 5.6, -11.9, -11.0, z + 1.5, z + 3.7, "gold", bevel=0.12)
    b(1.2, 4.6, -11.8, -11.0, 36.4, 37.6, "gold_d", bevel=0.12)                          # the leaf at its foot
    # ---- the shin and the boot
    g = Grid(IDENT, 1, 27, -21, 13, 0, 66, cs=2, sx=s)
    XS, Y, Z = g.XS, g.Y, g.Z
    g.fill((XS > 7) & (XS < 17) & (Y ** 2 + (Z - KNEE_Z) ** 2 < 37.0) & (Z > 22), "trouser_d")    # the knee's drum
    g.box(5, 19, -7, 7, 16, 24, "trouser")                    # the leg
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
    for z in (8.6, 13.8):                                     # two straps
        b(2.3, 21.7, -9.7, 9.7, z, z + 3.0, "belt_d" if z < 10 else "belt")
        b(21.4, 22.8, -3.0, 2.0, z - 0.4, z + 3.4, "gold")
        b(22.6, 23.3, -1.5, 0.5, z + 0.5, z + 2.5, "gold_l", bevel=0.15)
    b(9.5, 14.5, -11.0, -9.4, 8.0, 12.2, "gold")              # a stud on the lower strap
    gold_square(b, 7.6, 16.4, 11.4, 19.6, -12.0, t=2.2, inner="boot_d")                  # the big gold buckle on the upper one
    return P, Q


def fist(part, frame, s):
    """A closed fist (the King's sword hand): wrist, palm, four finger bars side by side along the grip, thumb.
    -> the middle of what it holds (world u)."""
    h = lambda *q, **k: part.blk(frame, *q, sx=s, **k)
    GX, GY, GZ = GRIP                                         # the grip's axis: along y, through (x GX, z GZ); its middle at y GY
    h(21.5, 28.5, -4.6, 3.2, 49.4, 53.6, "skin_d")            # wrist
    h(20.4, 30.2, GY - 5.1, GY + 5.5, 43.6, 51.0, "skin")     # the back of the hand and the palm
    for i, (nm, dz) in enumerate((("skin_l", 0.3), ("skin", 0.0), ("skin_d", 0.2), ("skin", 0.6))):
        y0 = GY - 5.3 + i * 2.75                              # four fingers side by side along the grip, curled under it
        h(19.6, 31.0, y0, y0 + 2.75, 40.4 + dz, 46.4, nm)
    h(18.2, 21.6, GY - 6.0, GY + 1.6, 45.6, 49.4, "skin_l")   # the thumb, lying along the grip on the inside
    return frame.w((s * GX, GY, GZ))


def build_arm(s):
    """-> (upper arm, forearm). The elbow is where the forearm's frame is bent. Cream sleeves, puffed at the shoulder
    and rolled up to a thick cuff at the elbow; bare forearms with a leather bracer; bare fists. The left forearm
    carries its fist, closed round the pitchfork (as the archer's bow hand); the right hand is its own part (HandR)."""
    side = "L" if s > 0 else "R"
    P = Part("Arm" + side)
    A = Frame().sub(RY(-s * ARM_OUT[side]), P.joint)
    ex, ey, ez = ELBOW_AT
    Fo = A.sub(RX(-ELBOW[side]), (s * ex, ey, ez))
    JOINTS["Fore" + side] = tuple(float(v) for v in A.w((s * ex, ey, ez)))
    Q = Part("Fore" + side)
    # ---- upper arm: shoulder drum, puffed sleeve, rolled cuff
    g = Grid(A, 15, 37, -12, 12, 68, 112, cs=2, sx=s)
    XS, Y, Z = g.XS, g.Y, g.Z
    g.box(19, 31, -6, 6, 70, 76, "cream_dd")                  # the inside of the cuff, round the elbow
    g.fill((XS > 19) & (XS < 31) & (Y ** 2 + (Z - 100) ** 2 < 7.0 ** 2), "cream")       # the drum the arm turns on
    g.box(19, 33, -8, 8, 80, 98, "cream")                     # the sleeve
    g.box(19, 31, -8, 8, 98, 104, "cream")                    # the shoulder
    g.box(19, 35, -10, 10, 86, 98, "cream")                   # ... puffed out
    puff = g.bm(19, 35, -10, 10, 86, 98)
    g.paint(puff & (Z > 96), "cream_l")
    g.paint(g.isn("cream") & (Z < 96) & ((g.ix + g.iy) % 4 == 0), "cream_d")            # folds
    g.box(17, 35, -10, 10, 74, 80, "cream_l")                 # the sleeve rolled up: a thick roll at the elbow
    g.pbox(17, 35, -10, 10, 74, 76, "cream")
    emit(P, g, lim=((5, 9), (5, 9), (6, 12)), pref="z", lims=dict(cream_l=((6, 10), (6, 10), (2, 4)), cream_dd=(8, 16)),
         shade=0.3, proud_p=0.4, proud=(0.12, 0.4), seed=31 + s)
    # ---- forearm (bent frame)
    g = Grid(Fo, 14, 36, -13, 13, 38, 82, cs=2, sx=s)
    XS, Y, Z = g.XS, g.Y, g.Z
    g.box(20, 30, -5, 5, 52, 80, "skin")                      # the bare forearm
    g.pbox(20, 30, -5, 5, 52, 54, "skin_d")
    g.box(18, 32, -7, 7, 58, 68, "bracer")                    # the leather bracer
    g.pbox(18, 32, -7, 7, 58, 60, "bracer_d")
    Q.bias = len(P._ch)
    emit(Q, g, lim=(8, 16), lims={"skin": ((5, 10), (5, 10), (8, 14))}, shade=0.3, seed=41 + s)
    f = lambda *q, **k: Q.blk(Fo, *q, sx=s, **k)
    f(17.5, 32.5, -7.5, 7.5, 66.4, 68.0, "bracer_l")          # its upper lip
    f(32.0, 32.8, -1.2, 1.2, 61.6, 64.0, "gold", bevel=0.15)  # studs
    f(23.8, 26.2, -7.8, -7.0, 61.6, 64.0, "gold", bevel=0.15)
    wx, wy, wz = WRIST_AT
    if s > 0:
        # the pitchfork hand: the fist is modelled turned up at the wrist, so that the shaft stands upright in it
        Hf = Fo.sub(RX(-WRIST_L), (s * wx, wy, wz))
        f(21.5, 28.5, -4.4, 3.4, 49.6, 53.4, "skin_d")
        grip = fist(Q, Hf, s)
        P.fork_part = build_pitchfork(grip)
    else:
        JOINTS["HandR"] = tuple(float(v) for v in Fo.w((s * wx, wy, wz)))
        H = Part("HandR")
        fist(H, Fo, s)
        P.hand_part = H
    return P, Q


FORK_TOP = 138.0                              # the tips of the tines above the ground (u), while the arm is at rest
FORK_HEAD = 104.0                             # where the shaft ends in the iron head


def build_pitchfork(grip):
    """The pitchfork as its own part, origin at the middle of the grip in his left fist, standing upright with its
    butt on the ground: an iron-shod butt, a wooden shaft with two gold bands, an iron head with three tines side by
    side (across him, so that they read from the front). Its frame: +z up the shaft, z = 0 at the ground."""
    JOINTS["Pitchfork"] = tuple(float(v) for v in grip)
    P = Part("Pitchfork")
    S = Frame(np.eye(3), (float(grip[0]), float(grip[1]), 0.0))
    P.frame = S
    b = lambda *q, **k: P.blk(S, *q, **k)
    b(-2.1, 2.1, -2.1, 2.1, 0.0, 11.0, "steel_d")             # the iron shoe on the butt
    b(-2.6, 2.6, -2.6, 2.6, 9.6, 12.6, "steel")
    cuts = np.linspace(12.6, FORK_HEAD, 11)
    for i in range(10):                                       # the shaft, in lengths of two woods
        b(-1.7, 1.7, -1.7, 1.7, cuts[i], cuts[i + 1], ("wood", "wood_l", "wood", "wood_d")[i % 4], bevel=0.12)
    for z in (27.0, 96.0):                                    # the two gold bands, each with a lip
        b(-2.5, 2.5, -2.5, 2.5, z, z + 5.0, "gold")
        b(-2.9, 2.9, -2.9, 2.9, z + 3.6, z + 5.0, "gold_l")
    b(-3.1, 3.1, -2.7, 2.7, FORK_HEAD - 1.0, FORK_HEAD + 4.6, "steel_d")                 # the socket
    b(-11.0, 11.0, -1.9, 1.9, FORK_HEAD + 2.6, FORK_HEAD + 7.2, "steel")                 # the bar the tines stand on
    b(-1.3, 1.3, -2.7, -1.7, FORK_HEAD + 3.6, FORK_HEAD + 6.2, "steel_ll", bevel=0.15)   # a rivet
    for x in (-9.3, 0.0, 9.3):
        b(x - 1.7, x + 1.7, -1.7, 1.7, FORK_HEAD + 7.2, FORK_HEAD + 19.0, "steel" if x else "steel_l")
        b(x - 1.5, x + 1.5, -1.5, 1.5, FORK_HEAD + 19.0, FORK_TOP - 5.0, "steel_l" if x else "steel")
        b(x - 1.1, x + 1.1, -1.1, 1.1, FORK_TOP - 5.0, FORK_TOP, "steel_ll")             # the point
    P.tip = S.w((0.0, 0.0, FORK_TOP))
    P.butt = S.w((0.0, 0.0, 0.0))
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
    """The head, put together from two other troops (see the top of this file).
    FACE: the ARCHER's. Her skull (24 x 20 x 22 u), one smooth skin plate in front of it, her nose, mouth and ears at
    her heights above the skull's base (hers is at 100, his at SKULL_Z); his jaw is 2 u broader each side and carries
    the beard. EYES: the ARCHER's too (archer_face).
    His own: warm tan skin, brown hair down to the collar, a full brown beard and a moustache."""
    P = Part("Head")
    F = Frame()
    K = SKULL_Z - 100.0                                       # the archer's heights + K
    g = Grid(F, -18, 18, -18, 18, 100, 134, cs=2)
    X, Y, Z = g.X, g.Y, g.Z
    AX = np.abs(X)
    g.box(-12, 12, -10, 10, 100 + K, 122 + K, "skin")         # ARCHER: the skull
    g.fill((AX < 14) & (Y > -10) & (Y < 4) & (Z > SKULL_Z) & (Z < SKULL_Z + 8), "beard")        # his: the jaw, broadened, under the beard
    g.fill((AX < 10) & (Y > -10) & (Y < 2) & (Z > SKULL_Z - 2) & (Z < SKULL_Z), "beard")        # ... and the beard under the chin
    g.fill((AX > 12) & (AX < 14) & (Y > -10) & (Y < -4) & (Z > SKULL_Z + 8) & (Z < SKULL_Z + 14), "beard")      # sideburns
    g.box(-14, 14, 10, 14, SKULL_Z, 128, "hair")              # the back of the head, down to the collar
    g.fill((AX > 12) & (AX < 14) & (Y > 4) & (Y < 10) & (Z > SKULL_Z + 2) & (Z < 128), "hair")  # behind the ears
    g.fill((AX > 12) & (AX < 14) & (Y > -10) & (Y < 4) & (Z > SKULL_Z + 14) & (Z < 128), "hair")                # above the ears
    g.box(-14, 14, -12, 14, 128, 130, "hair")                 # the cap (under the hat)
    g.fill((AX > 14) & (AX < 16) & (Y > 4) & (Y < 12) & (Z > SKULL_Z + 2) & (Z < 124), "hair")  # shaggy behind each ear
    g.fill((AX < 12) & (Y > 14) & (Y < 16) & (Z > SKULL_Z + 2) & (Z < 126), "hair")             # ... and at the back
    hair = g.isn("hair")
    hh = g.hash(2, 3)
    g.paint(hair & (hh < 0.28), "hair_l")
    g.paint(hair & (hh > 0.78), "hair_d")
    g.fill((AX > 12) & (AX < 16) & (Y > -2) & (Y < 2) & (Z > 108 + K) & (Z < 114 + K), "skin_l")                # ARCHER: the ears
    emit(P, g, lim=(8, 14), lims={"hair": (5, 9), "beard": (5, 9), "skin_l": (8, 9)}, shade=0.3, proud_p=0.4, proud=(0.15, 0.5), seed=61)
    b = lambda *a, **k: P.blk(F, *a, **k)
    # ---- ARCHER: the face. ONE smooth skin plate in front of the skull (a single block), so that no seams between
    # blocks read as features; the nose is one small block with a slight shadow under it, the mouth one thin bar.
    b(-12.0, 12.0, -10.6, -10.0, 100.0 + K, 122.0 + K, "skin", bevel=0.03)
    b(-3.0, 3.0, -10.9, -10.5, 103.6 + K, 104.6 + K, "lip", bevel=0.1)                   # mouth (in the gap the beard leaves)
    b(-1.5, 1.5, -12.2, -10.5, 106.8 + K, 109.6 + K, "skin", bevel=0.12, tint=1.05)      # nose (a little prouder: it stands over a moustache)
    b(-1.5, 1.5, -11.0, -10.5, 106.2 + K, 106.9 + K, "skin_d", bevel=0.1)                # ... and the shadow under it
    for sx in (1, -1):
        b(15.6, 16.5, -1.0, 1.0, 109.6 + K, 112.4 + K, "skin_d", sx=sx)                  # the hollow of the ear
        b(9.6, 12.0, -11.3, -10.5, 122.6, 126.0, "hair_d", sx=sx)                        # the hair coming down at the temples
    b(-12.0, 12.0, -11.4, -10.5, 125.0, 128.0, "hair")        # the hairline (under the hat's brim)
    # ---- his own: a full brown beard, one layer proud of the face in big plain blocks (as the swordsman's and the
    # builder's), carried by his broad jaw: chin and jaw, thicker on the chin, round the mouth, up the cheeks to the
    # sideburns; a moustache proud of it with drooping ends
    bd = lambda x0, x1, z0, z1, nm, y0=-11.6, sx=1: b(x0, x1, y0, -10.5, z0 + K - 6.0, z1 + K - 6.0, nm, sx=sx, bevel=0.12)
    bd(-14.0, 14.0, 105.6, 109.2, "beard")
    bd(-10.0, 10.0, 104.4, 108.0, "beard", -12.4)
    bd(-6.0, 6.0, 103.6, 104.8, "beard_d", -12.2)
    for sx in (1, -1):
        bd(3.4, 14.0, 109.2, 111.0, "beard", sx=sx)
        bd(9.0, 14.0, 111.0, 113.6, "beard", sx=sx)
        bd(11.2, 14.0, 113.6, 116.4, "beard_d", -11.4, sx=sx)
        bd(12.0, 14.0, 116.4, 120.4, "beard_l", -11.2, sx=sx)
        bd(4.0, 6.4, 108.8, 111.4, "beard_l", -12.2, sx=sx)
    bd(-6.2, 6.2, 110.8, 112.3, "beard_l", -12.3)
    # ---- ARCHER: the eyes too (a 6 x 4 u white with a 3 x 4 u pupil centred in it, a glint); his brows a little heavier
    archer_face(P, F, 100.0 + K, front=-10.6, brow="brow", brow_t=2.0, brow_x=(2.4, 9.8), eyes_only=True)
    return P


HAT_TILT = 7.0                                # the hat is pushed back this far (degrees): the brim rises over the face


def build_hat():
    """The straw hat as its own part on the head: a wide ragged brim of straw blocks in three yellows, drooping in
    places, a low round crown with a leather band."""
    P = Part("Hat")
    F = Frame().sub(RX(-HAT_TILT), (0.0, 0.0, 126.0))
    P.frame = F
    g = Grid(F, -34, 34, -32, 28, 120, 144, cs=2)
    X, Y, Z = g.X, g.Y, g.Z
    rr = (X / 29.0) ** 2 + np.where(Y < 0, Y / 27.0, Y / 21.0) ** 2
    sector = np.floor((np.arctan2(Y, X) + np.pi) / (2 * np.pi) * 26).astype(np.int64)
    rag = (hash3(sector, sector * 0, sector * 0, 7) - 0.5) * 0.26                        # a ragged edge
    brim = (rr + rag < 1.0) & (Z > 124) & (Z < 126)
    brim |= (rr < 0.55) & (Z > 126) & (Z < 128)               # thicker toward the crown
    brim |= (rr + rag < 1.0) & (rr > 0.6) & (Z > 122) & (Z < 124) & (hash3(sector, sector * 0, sector * 0, 13) < 0.45)      # drooping in places
    crown = ((X / 16.0) ** 2 + (Y / 15.0) ** 2 < 1.0) & (Z > 126) & (Z < 138)
    crown |= ((X / 12.0) ** 2 + (Y / 11.0) ** 2 < 1.0) & (Z > 138) & (Z < 140)
    g.fill(brim | crown, "straw")
    hh = g.hash(2, 9)
    g.paint(g.solid() & (hh < 0.3), "straw_l")
    g.paint(g.solid() & (hh > 0.74), "straw_d")
    g.paint(crown & (Z > 128) & (Z < 132), "hatband")
    emit(P, g, lim=(4, 8), lims={"hatband": ((6, 10), (6, 10), (4, 4))}, shade=0.5, proud_p=0.55, proud=(0.2, 0.7), seed=66, cjit=0.05,
         core_rgb=PRGB[PI["straw_dd"]] * 0.6)
    P.top = F.w((0.0, 0.0, 140.0))
    return P


def torso_tiers(Z):
    """Half width and half depth of the torso at height Z (2 u steps): waist, belly and chest, shoulders."""
    hw = np.where(Z < 78, 16, np.where(Z < 100, 18, 16))
    hd = np.where(Z < 100, 11, 9)
    return hw, hd


def build_body():
    """-> (Body, Chest). Body: the pelvis with the top of the shirt's skirt and of the apron, the belt and its gold
    square buckle, the strip of apron between the legs with the emblem's stem. Chest: the cream shirt, open at the
    collar, the green bib of the apron, the basket's two leather straps with their gold square buckles."""
    P = Part("Body")
    blk = lambda *a, **k: P.blk(IDENT, *a, **k)
    g = Grid(IDENT, -26, 26, -19, 15, 30, 78, cs=2)
    X, Y, Z = g.X, g.Y, g.Z
    AX = np.abs(X)
    g.fill((AX < np.where(Z < 56, 22, 20)) & (np.abs(Y) < 11) & (Z > 52) & (Z < 66), "cream")
    g.paint(g.solid() & (AX < 12) & (Y < -9), "green")        # the apron carries on up to the belt
    g.box(-18, 18, -13, 13, 66, 74, "belt")                   # the belt: broad, proud of the shirt
    emit(P, g, lim=(10, 18), lims={"belt": ((10, 18), (8, 12), (4, 4)), "green": ((6, 12), (2, 2), (6, 14))}, seed=81)
    for sx in (1, -1):
        blk(8.0, 9.8, -11.9, -11.0, 54.0, 56.6, "gold_d", sx=sx)                         # the emblem's frame: the tops of its sides ...
        blk(13.0, 15.2, -14.2, -13.0, 68.9, 71.1, "gold", sx=sx, bevel=0.15)             # belt studs
        blk(18.0, 19.2, -3.0, -0.8, 68.9, 71.1, "gold", sx=sx, bevel=0.15)
        blk(18.0, 19.2, 3.0, 5.2, 68.9, 71.1, "gold_d", sx=sx, bevel=0.15)
    blk(-9.8, 9.8, -11.9, -11.0, 56.6, 58.4, "gold")          # ... and its top bar
    # the strip of apron between the two halves that swing with the legs, with the stem of the wheat emblem
    blk(-1.0, 1.0, -11.0, -9.2, APRON_HEM - 1.5, 54.0, "green_d")
    blk(-1.2, 1.2, -11.3, -9.2, APRON_HEM - 1.5, APRON_HEM + 4.0, "gold")
    blk(-1.0, 1.0, -11.9, -11.0, 34.0, 35.8, "gold")
    blk(-0.8, 0.8, -11.9, -11.0, 35.8, 49.4, "gold_d", bevel=0.12)
    blk(-1.4, 1.4, -12.1, -11.0, 49.4, 53.0, "gold_l", bevel=0.12)                        # the ear at its top
    # the buckle: a big hollow gold square, plates on plates
    blk(-6.6, 6.6, -16.6, -13.0, 63.4, 76.6, "gold")
    blk(-6.6, -4.0, -17.8, -16.4, 63.4, 76.6, "gold_l")
    blk(4.0, 6.6, -17.8, -16.4, 63.4, 76.6, "gold_l")
    blk(-4.0, 4.0, -17.8, -16.4, 74.0, 76.6, "gold_l")
    blk(-4.0, 4.0, -17.8, -16.4, 63.4, 66.0, "gold_l")
    blk(-4.0, 4.0, -17.0, -16.4, 66.0, 74.0, "belt_dd")
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
    g.fill(body, "cream")
    g.paint(body & (Z < 76), "belt_d")
    g.paint(body & (AX > 10) & ((g.ix + g.iz // 3) % 4 == 0), "cream_d")                 # folds
    g.paint(body & (Z > 100) & (AX > 8), "cream_l")           # the yoke on the shoulders
    g.paint(body & (Y < -5) & (Z > 96) & (AX < np.where(Z > 100, 4, 2)), "skin")         # the open collar
    g.paint(body & (Y < -5) & (Z > 98) & (AX > 4) & (AX < 8), "cream_l")                 # ... and its flaps
    bib = (AX < 10) & (Y > -13) & (Y < -11) & (Z > 76) & (Z < 96)                        # the apron's bib, proud of the shirt
    g.fill(bib, "green")
    hh = g.hash(2, 4)
    g.paint(bib & (hh < 0.2), "green_l")
    g.paint(bib & (hh > 0.85), "green_d")
    g.fill((X ** 2 + Y ** 2 < 6.2 ** 2) & (Z > 104) & (Z < 112), "skin_d")               # neck
    emit(P, g, lim=((6, 12), (8, 12), (6, 12)), lims={"skin_d": (12, 12), "belt_d": ((10, 18), (8, 12), (4, 4)), "green": ((4, 8), (2, 2), (6, 10)),
                                                      "skin": ((2, 4), (2, 4), (2, 4))}, shade=0.4, seed=82)
    tb(-10.4, 10.4, -13.6, -12.8, 94.2, 96.2, "gold")         # the bib's gold border: along its top ...
    for sx in (1, -1):
        tb(8.8, 10.4, -13.6, -12.8, 76.0, 94.2, "gold_d", sx=sx)                         # ... and down its sides
        # the basket's shoulder straps: up the chest, over the shoulder, down the back; a gold square buckle on each
        tb(10.6, 15.2, -13.0, -11.0, 76.0, 101.0, "belt", sx=sx)
        tb(10.6, 15.2, -11.0, -9.0, 100.0, 105.6, "belt_l", sx=sx)
        tb(10.6, 15.2, -9.2, 9.2, 104.0, 105.6, "belt", sx=sx)
        tb(10.6, 15.2, 9.0, 10.8, 100.0, 105.6, "belt_d", sx=sx)
        tb(10.6, 15.2, 11.0, 12.6, 76.0, 101.0, "belt_d", sx=sx)
        gold_square(lambda *a, **k: tb(*a, sx=sx, **k), 8.6, 17.2, 85.4, 94.0, -15.4, t=2.2)
    return B, P


def build_pouch():
    """The leather pouch on his right hip, its own part hanging from the belt by two loops: a body, a pale flap, a stud."""
    P = Part("Pouch")
    b = lambda *a, **k: P.blk(IDENT, *a, **k)
    b(-18.6, -9.4, -17.8, -13.0, 53.0, 66.0, "belt")
    b(-18.0, -10.0, -18.4, -17.6, 54.0, 60.0, "belt_l")
    b(-19.0, -9.0, -18.8, -13.0, 60.0, 67.0, "pouch")         # the flap
    b(-19.0, -9.0, -19.2, -18.6, 60.0, 61.4, "pouch_d")
    b(-15.0, -13.0, -19.7, -18.6, 61.4, 63.6, "gold", bevel=0.15)
    for x in (-17.8, -12.0):
        b(x, x + 1.8, -14.8, -13.0, 66.0, 75.0, "belt_d")     # the loops over the belt
    return P


BK_Y0 = 13.0                                  # the basket: its front, against his back
BK_Z0, BK_Z1 = 62.0, 100.0                    # its foot and its rim


def basket_tiers(Z):
    """The basket at height Z: its half width and its back. It widens toward the rim."""
    hw = np.where(Z < 70, 14, np.where(Z < 80, 16, np.where(Z < 90, 18, 20)))
    y1 = np.where(Z < 70, 33, np.where(Z < 80, 35, np.where(Z < 90, 37, 39)))
    return hw, y1


def build_basket():
    """The woven basket on his back, its own part riding on the chest: a checker of two browns (the weave), a rope
    band round the middle and a thick rope rim; in it a sheaf of wheat standing up at the back, carrots lying over the
    rim at his right and a heap of apples; a bracket on its right side for the lantern."""
    P = Part("BackBasket")
    b = lambda *a, **k: P.blk(IDENT, *a, **k)
    g = Grid(IDENT, -26, 26, 11, 45, 58, 106, cs=2)
    X, Y, Z = g.X, g.Y, g.Z
    AX = np.abs(X)
    hw, y1 = basket_tiers(Z)
    body = (AX < hw) & (Y > BK_Y0) & (Y < y1) & (Z > BK_Z0) & (Z < BK_Z1)
    g.fill(body, "wick")
    g.paint(body & ((g.ix // 2 + g.iy // 2 + g.iz // 2) % 2 == 0), "wick_l")              # the weave
    g.paint(body & (Z < BK_Z0 + 2), "wick_d")
    g.paint(body & (Z > 78) & (Z < 82), "rope")
    rim = (AX < hw + 2) & (Y > BK_Y0 - 2) & (Y < y1 + 2) & (Z > BK_Z1 - 4) & (Z < BK_Z1)
    g.fill(rim, "rope_l")
    g.paint(rim & ((g.ix // 2 + g.iy // 2) % 2 == 0), "rope")
    inside = (AX < hw - 2) & (Y > BK_Y0 + 2) & (Y < y1 - 2)
    g.carve(inside & (Z > BK_Z1 - 6))                         # open: the produce lies in it
    g.paint(g.solid() & inside & (Z > BK_Z1 - 8), "wick_dd")
    emit(P, g, lim=(4, 4.4), lims={"rope": ((4, 8), (4, 8), (4, 4)), "wick_dd": (8, 16)}, shade=0.4, proud_p=0.5, proud=(0.15, 0.5), seed=91)
    for x in (-10.0, 0.0, 10.0):                              # knots on the rope band, at the back
        b(x - 1.6, x + 1.6, 35.0, 36.0, 78.4, 81.6, "rope_l", bevel=0.15)
    # the bracket the lantern hangs from, on his right
    b(LAN_X - 2.4, -19.0, LAN_Y - 1.1, LAN_Y + 1.1, LAN_Z + 1.0, LAN_Z + 3.2, "wood_d")
    b(LAN_X - 1.1, LAN_X + 1.1, LAN_Y - 1.1, LAN_Y + 1.1, LAN_Z - 0.6, LAN_Z + 1.2, "steel_d")
    rng = np.random.default_rng(5)
    # ---- the wheat: a sheaf standing up at the back, fanned out; each a stalk and an ear of three blocks
    tops = []
    for x in (-14.0, -9.5, -5.0, -0.5, 4.0, 8.5, 13.0):
        for y in (25.5, 30.0, 34.5):
            x_, y_ = x + rng.uniform(-1.2, 1.2), y + rng.uniform(-1.2, 1.2)
            L = rng.uniform(36.0, 52.0) - abs(x) * 0.5
            F = IDENT.place(RY(x_ * 1.2 + rng.uniform(-4, 4)) @ RX(-(y_ - 26.0) * 1.4 - 2.0 + rng.uniform(-3, 3)), (x_, y_, BK_Z1 - 5.0))
            a = lambda *q, **k: P.blk(F, *q, cull=False, **k)
            a(-0.8, 0.8, -0.8, 0.8, 0.0, L - 11.0, "wheat_d", bevel=0.2)
            a(-2.0, 2.0, -1.5, 1.5, L - 11.0, L - 7.0, "wheat", bevel=0.15)
            a(-1.5, 1.5, -2.0, 2.0, L - 7.3, L - 3.3, "wheat_l", bevel=0.15)
            a(-1.2, 1.2, -1.2, 1.2, L - 3.5, L, "wheat", bevel=0.15)
            tops.append(F.w((0.0, 0.0, L)))
    P.wheat_top = max(float(t[2]) for t in tops)
    # ---- the carrots: lying over the rim at his right, points out and down, their greens standing up inside
    for i, (base, d) in enumerate((((-12.0, 18.5, 105.5), (-0.86, -0.22, -0.26)), ((-12.5, 25.0, 106.0), (-0.9, 0.0, -0.22)),
                                   ((-11.0, 31.5, 105.0), (-0.84, 0.25, -0.3)))):
        base = np.array(base)
        Fc = frame_along(base, base + np.array(d))
        c = lambda *q, **k: P.blk(Fc, *q, cull=False, **k)
        c(-3.0, 3.0, -3.0, 3.0, -7.0, 0.0, "carrot")
        c(-2.4, 2.4, -2.4, 2.4, -13.0, -7.0, "carrot_l")
        c(-1.7, 1.7, -1.7, 1.7, -18.0, -13.0, "carrot")
        c(-1.0, 1.0, -1.0, 1.0, -21.0, -18.0, "carrot_d")
        for j, (ax, ay) in enumerate(((0.0, -30.0), (22.0, -48.0), (-20.0, -40.0), (6.0, -64.0))):
            Fg = Fc.place(RX(ax) @ RY(ay), (0.0, 0.0, 0.0))   # the greens: turned up from the carrot's line
            P.blk(Fg, -1.1, 1.1, -1.1, 1.1, 0.0, 8.0 + 2 * (j % 2), ("leaf_d", "leaf", "leaf_d", "leaf")[j], cull=False, bevel=0.15)
            P.blk(Fg, -2.0, 2.0, -0.9, 0.9, 6.0 + 2 * (j % 2), 13.0 + 2 * (j % 3), ("leaf", "leaf_l", "leaf_l", "leaf")[(i + j) % 4], cull=False, bevel=0.15)
    # ---- the apples: a heap of red blocks at his left
    for i, (x, y, z, r) in enumerate(((3.0, 20.5, 100.5, 2.9), (9.5, 20.0, 101.0, 2.7), (15.0, 21.0, 100.0, 2.6), (6.5, 24.5, 103.5, 2.8),
                                      (13.0, 25.5, 102.5, 2.6), (-2.5, 22.0, 100.0, 2.5), (10.0, 23.0, 105.5, 2.4))):
        Fa = IDENT.place(RZ(float(rng.uniform(0, 90))) @ RX(float(rng.uniform(-14, 14))), (x, y, z))
        P.blk(Fa, -r, r, -r, r, -r, r, ("apple", "apple_l", "apple", "apple_d", "apple_l", "apple", "apple_l")[i], cull=False, bevel=0.14)
        if i % 2 == 0:
            P.blk(Fa, -0.5, 0.5, -0.5, 0.5, r, r + 1.4, "wood_dd", cull=False, bevel=0.2)
    return P


def build_lantern():
    """The small lantern as its own part, hanging by its ring from the basket's bracket: an iron cage, a glowing core
    (the "glow" slot: the emissive voxel material)."""
    P = Part("Lantern")
    b = lambda *a, **k: P.blk(IDENT, *a, **k)
    lx, ly, z = LAN_X, LAN_Y, LAN_Z
    b(lx - 1.8, lx + 1.8, ly - 0.7, ly + 0.7, z - 3.4, z - 0.2, "steel")              # the ring
    b(lx - 2.6, lx + 2.6, ly - 2.6, ly + 2.6, z - 4.8, z - 3.2, "steel_dd")           # the cap, stepped
    b(lx - 4.4, lx + 4.4, ly - 4.4, ly + 4.4, z - 6.4, z - 4.6, "steel_dd")
    b(lx - 3.0, lx + 3.0, ly - 3.0, ly + 3.0, z - 14.4, z - 6.2, "glow", bevel=0.05)  # the light
    b(lx - 2.0, lx + 2.0, ly - 3.3, ly + 3.3, z - 13.0, z - 7.6, "glow_l", bevel=0.05)
    b(lx - 3.3, lx + 3.3, ly - 2.0, ly + 2.0, z - 13.0, z - 7.6, "glow_l", bevel=0.05)
    for sx in (1, -1):
        for sy in (1, -1):
            b(lx + sx * 3.9 - 0.7, lx + sx * 3.9 + 0.7, ly + sy * 3.9 - 0.7, ly + sy * 3.9 + 0.7, z - 14.6, z - 6.2, "steel_dd", bevel=0.15)
    b(lx - 4.4, lx + 4.4, ly - 4.4, ly + 4.4, z - 16.0, z - 14.2, "steel_dd")         # the base
    b(lx - 2.4, lx + 2.4, ly - 2.4, ly + 2.4, z - 17.0, z - 15.8, "steel_d")
    P.light = (lx, ly, z - 10.3)
    return P


WHOLE = ["Body", "Head", "ArmL", "ArmR", "LegL", "LegR"]


def wholes(parts):
    """The limbs as the single rigid pieces they are while every elbow, knee and wrist is at rest (the basket, its
    lantern and the pouch with the torso, the hat with the head, the pitchfork with its arm)."""
    return {"Body": Combo(parts["Body"], parts["Chest"], parts["BackBasket"], parts["Lantern"], parts["Pouch"]),
            "Head": Combo(parts["Head"], parts["Hat"]),
            "ArmL": Combo(parts["ArmL"], parts["ForeL"], parts["Pitchfork"]),
            "ArmR": Combo(parts["ArmR"], parts["ForeR"], parts["HandR"]), "LegL": Combo(parts["LegL"], parts["ShinL"]),
            "LegR": Combo(parts["LegR"], parts["ShinR"])}


def build_farmer():
    t0 = time.time()
    parts = {}
    for s_, side in ((1, "L"), (-1, "R")):
        parts["Leg" + side], parts["Shin" + side] = build_leg(s_)
        parts["Arm" + side], parts["Fore" + side] = build_arm(s_)
    parts["HandR"] = parts["ArmR"].hand_part
    parts["Pitchfork"] = parts["ArmL"].fork_part
    parts["Head"] = build_head()
    parts["Hat"] = build_hat()
    parts["Body"], parts["Chest"] = build_body()
    parts["Pouch"] = build_pouch()
    parts["BackBasket"] = build_basket()
    parts["Lantern"] = build_lantern()
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
    """Turn joints by degrees about x (Head: about z), keyed by the part's name in lower case: legl, legr, shinl, shinr,
    arml, armr, forel, forer, handr, chest, body, head, lantern ...; "<name>_z" adds a turn about z. Positive swings a
    hanging limb backwards. The pitchfork rides on the left forearm, the hat on the head, the basket (and the lantern
    on it) on the chest, the pouch on the pelvis."""
    for key, ob in obs.items():
        parent = PARENT.get(key)
        base = np.array(JOINTS[parent], np.float64) if parent else np.zeros(3)
        ob.location = [float(v) * U for v in np.array(JOINTS[key], np.float64) - base]
        a = ang.get(key.lower(), 0.0)
        ob.rotation_euler = (0, 0, math.radians(a)) if key == "Head" else (math.radians(a), 0, math.radians(ang.get(key.lower() + "_z", 0.0)))


def want(name):
    return VIEWS is None or name in VIEWS


HERO = dict(head=16.0)                        # the picture's pose: he looks toward the pitchfork
WALK = dict(legl=30, shinl=-10, legr=-25, shinr=35, arml=-22, armr=30, forer=-5, chest=-6, lantern=-10)


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
    top = 0.0
    for k in ORDER:
        P = part_points(parts[k], step=1.0, cores=False)
        lo, hi = np.minimum(lo, P.min(axis=0)), np.maximum(hi, P.max(axis=0))
        print("  %-10s x %6.1f..%6.1f  y %6.1f..%6.1f  z %6.1f..%6.1f u" % ((k,) + tuple(v for pair in zip(P.min(axis=0), P.max(axis=0)) for v in pair)))
        if k not in ("BackBasket", "Pitchfork"):
            top = max(top, float(P[:, 2].max()))
    print("FARMER MAN size: x %.3f m (%.2f..%.2f), y %.3f m (%.2f..%.2f), figure with his hat %.4f m, with the wheat %.4f m (lowest %.4f)" % (
        (hi[0] - lo[0]) * U, lo[0] * U, hi[0] * U, (hi[1] - lo[1]) * U, lo[1] * U, hi[1] * U, top * U, hi[2] * U, lo[2] * U))
    W = wholes(parts)
    pts = {k: part_points(W[k], step=0.6, shrink=0.4, cores=False) for k in WHOLE}
    check_pose(W, pts, "rest")
    check_pose(W, pts, "walk A", legl=35, legr=-35, arml=-35, armr=35)
    check_pose(W, pts, "walk B", legl=-35, legr=35, arml=35, armr=-35)
    check_pose(W, pts, "head turned", head=22)
    check_pose(W, pts, "head turned -", head=-22)

    obs = {}
    total = 0
    for key in ORDER:
        ob = make_object(parts[key])
        obs[key] = ob
        V.export_gltf(ob, collision="none", extra=dict(pivot=pivot(key), part=key, parent=PARENT.get(key, ""), triangles=int(ob["triangles"]),
                                                       blocks=int(len(parts[key].c))))
        total += int(ob["triangles"])
        print("  %-10s %6d blocks (%d core)  %7d triangles  %6d faces" % (key, len(parts[key].c), int(parts[key].core.sum()), ob["triangles"], ob["voxel_faces"]))
    print("FARMER MAN triangles in all: %d  (%.1f s)" % (total, time.time() - t0))
    r5 = lambda v: [round(float(c), 5) for c in v]
    fork, hat, lan, bk = parts["Pitchfork"], parts["Hat"], parts["Lantern"], parts["BackBasket"]
    # The character file, in the troops' format (SM_Archer.json). Metres and unit vectors in Blender axes (+x his
    # left, -y forward, z up), in the modelled rest pose.
    meta = dict(height=HEIGHT, radius=RADIUS, voxel=U, mesh_yaw=-90.0, stride=STRIDE,
                elbow_l=ELBOW["L"], elbow_r=ELBOW["R"], wrist_l=WRIST_L,
                cape=dict(cols=CAPE_COLS, rows=CAPE_ROWS), has_sheath=False,
                parts={key: dict(mesh=PREFIX + key, pivot=pivot(key), parent=PARENT.get(key, "")) for key in ORDER},
                pitchfork=dict(part="Pitchfork", hand="L", parent=PARENT["Pitchfork"], grip=pivot("Pitchfork"),
                               axis=r5(fork.frame.R[:, 2]),                # along the shaft, from the butt to the tines
                               tines_dir=r5(fork.frame.R[:, 0]),           # the line the three tines stand on
                               length=round(FORK_TOP * U, 5), tip=r5(fork.tip * U), butt=r5(fork.butt * U),
                               head=round(FORK_HEAD * U, 5)),              # where the iron head starts, from the butt
                basket=dict(part="BackBasket", parent=PARENT["BackBasket"], pivot=pivot("BackBasket"),
                            rim=round(BK_Z1 * U, 5), top=round(bk.wheat_top * U, 5), lantern="Lantern"),
                lantern=dict(part="Lantern", parent=PARENT["Lantern"], pivot=pivot("Lantern"), light=r5(np.array(lan.light) * U),
                             slot="glow"),
                hat=dict(part="Hat", parent=PARENT["Hat"], pivot=pivot("Hat"), top=r5(hat.top * U), tilt=HAT_TILT),
                pouch=dict(part="Pouch", parent=PARENT["Pouch"], pivot=pivot("Pouch")))
    with open(os.path.join(V.MESHES, NAME + ".json"), "w") as f:
        json.dump(meta, f, indent=1)
    print("wrote %s.json" % NAME)
    if NO_RENDER:
        return

    to_preview(obs, parts)
    stage()
    rig(obs)
    Pv = V.PREVIEWS
    p = lambda n: os.path.join(Pv, SHOT_PREFIX + "%s.png" % n)
    pose(obs)
    if want("hero"):
        pose(obs, **HERO)
        hero = shot("hero", az=-30, el=-7, dist=4.3, target=(0.02, 0.08, 0.93), res=(900, 1250), lens=62)
        tiles = [fit_h(load_px(REF), 1250), fit_h(load_px(hero), 1250)]
        save_px(np.ascontiguousarray(np.concatenate([t[..., :4] for t in tiles], axis=1)), p("compare"))
        print("montage", p("compare"))
        pose(obs)
    if want("threeq"):
        shot("threeq", az=-35, el=10, dist=7.4, target=(0.02, 0.08, 0.92), res=(900, 1200))
    if want("sides"):
        tiles = [shot("front", 0, 2, dist=7.4, target=(0.05, 0.08, 0.92), res=(720, 960)), shot("right", -90, 2, dist=7.4, target=(0, 0.08, 0.92), res=(720, 960)),
                 shot("back", 180, 4, dist=7.4, target=(-0.05, 0.08, 0.92), res=(720, 960)), shot("left", 90, 2, dist=7.4, target=(0, 0.08, 0.92), res=(720, 960))]
        montage(tiles, p("sides"), H=960)
    if want("face"):
        tiles = [shot("face_front", 0, 0, dist=6.0, target=(0, 0, 1.47), res=(800, 800), lens=230),
                 shot("face_34", -30, -8, dist=6.0, target=(0, 0, 1.47), res=(800, 800), lens=230),
                 shot("face_side", 90, 0, dist=6.0, target=(0, 0, 1.47), res=(800, 800), lens=230)]
        montage(tiles, p("faces"), H=800)
    if want("basket"):
        tiles = [shot("basket_back", 180, 12, dist=5.0, target=(0, 0.3, 1.2), res=(800, 900), lens=110),
                 shot("basket_right", -120, 12, dist=5.0, target=(0, 0.3, 1.2), res=(800, 900), lens=110)]
        montage(tiles, p("basket"), H=900)
    if want("game"):
        tiles = [shot("game_front", 25, 40, dist=7.6, res=(720, 960)), shot("game_back", 205, 40, dist=7.6, res=(720, 960))]
        montage(tiles, p("game"), H=960)
    if want("walk"):
        pose(obs, **WALK)
        tiles = [shot("walk_front", -29, 0, dist=7.6, res=(720, 960)), shot("walk_left", 90, 2, dist=7.6, res=(720, 960)),
                 shot("walk_back", 150, 8, dist=7.6, res=(720, 960)), shot("walk_right", -90, 2, dist=7.6, res=(720, 960))]
        montage(tiles, p("walk"), H=960)
        pose(obs)
    print("done in %.1f s" % (time.time() - t0))


main()
