"""The SPY troop (the old game's Scout): a hooded runner with a spyglass. Brown skin and dark curls under a green hood
with a gold rim and gold studs, a thick green scarf with a square gold clasp, a cream tunic with puffed sleeves and
leather straps crossed over the chest, a belt with pouches and a pair of binoculars hanging at the front, a bedroll and
a small glowing lantern on the back, a short green scout's cloak split into two tails with a thin gold edge (its own
shape, not the King's mantle), banded leather leggings and chunky boots. The head is in large plain pieces.
Built like the swordsman and the archer (troop_swordsman.py) from bevelled cubes and slabs of several sizes, as rigid
parts that the game swings about their joints; each part is exported on its own with its mesh origin at its joint.
Reference: References/Remake/spy.png.

    Blender -b --factory-startup --python Tools/blender/assets/troop_spy.py -- [--no-render] [--views hero,sides,...] [--fast] [--gpu]

Units: "u" = 1.25 cm (140 u = 1.75 m to the top of the hood, 128 u to the top of the skull). World axes: +X is the
figure's LEFT (it faces -Y), z = 0 is the ground between the feet.

THE RIG (the block "THE RIG" below) is King David's: the same part names, parents and joints, so the same C++ swings
it. If the King's rig changes, change that block (and the few places marked RIG) and run again. Three parts are the
spy's own and ride on the King's: "Spyglass" (in the right fist, on HandR: the game raises it to the eye, UVLSpy),
and "HoodA" > "HoodB" (the hood's loose tail down the back, on Head: swung as cloth by UVLSpy, and its vertices carry
a sway weight in their colour's alpha for the wind material, slot "sway").
ITS WEAK BOW (the owner's call, 2026-11-23: "scout should have a weak bow"): the archer's parts and joints, so the
archer's code (UVLArcherCombat) carries it, draws it and shoots it: "Bow" in the left fist (rides on ForeL; a short
plain hunting bow, 1.1 m against her 1.4 m recurve, no gold), "BowStringU" / "BowStringL" (its string's halves), "Arrow"
(in the right fist, on HandR, where the spyglass is: the game puts the glass away while it shoots) and "Quiver" (a small
leather one low on the back, left of the bedroll, its mouth leaning to the left shoulder; rides on Chest).

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
NAME = "SM_Spy"
PREFIX = NAME + "_"
REF = os.path.join(V.ROOT, "References", "Remake", "spy.png")

# ================================================================================================== THE RIG
# King David's rig (king_b.py / SM_KingB.json), without the scabbard and the sword. A tree of rigid parts (PARENT; no
# entry = the figure's root). Body is the pelvis, Chest turns on it at the waist; each arm is an upper arm and a
# forearm (the left with its hand, the right with the hand "HandR" turning at the wrist); each leg a thigh (with its
# half of the skirt) and a shin (with the boot); the cape is a yoke on the shoulders ("Cape") and CAPE_COLS chains of
# CAPE_ROWS panels hanging from it ("Cape<col><row>", col 0 on the right (-x) as in the King's files), which the
# engine swings as cloth. The spy's own: "Spyglass" rides on HandR (origin at the middle of its grip in the fist);
# "HoodA" > "HoodB" hang from the Head.
ORDER = ["Body", "Chest", "Head", "HoodA", "HoodB", "ArmL", "ForeL", "ArmR", "ForeR", "HandR", "LegL", "ShinL", "LegR", "ShinR", "Cape",
         "Spyglass", "Bow", "BowStringU", "BowStringL", "Quiver", "Arrow"]
PARENT = {"Bow": "ForeL", "BowStringU": "Bow", "BowStringL": "Bow", "Quiver": "Chest", "Arrow": "HandR", "Chest": "Body", "Head": "Chest", "ArmL": "Chest", "ArmR": "Chest", "ForeL": "ArmL", "ForeR": "ArmR", "HandR": "ForeR",
          "ShinL": "LegL", "ShinR": "LegR", "Cape": "Chest", "Spyglass": "HandR", "HoodA": "Head", "HoodB": "HoodA"}
CAPE_COLS, CAPE_ROWS = 5, 4
CAPE_U = (-0.72, -0.25, 0.25, 0.72)           # the columns' borders, as a share of the cape's half width
CAPE_L = ((10, 24, 38, 52), (13, 27, 41, 55)) # where the rows start, u below the collar (even / odd columns: staggered)
CAPE_HEM = 30.0                               # the height of the two tails' tips above the ground (u): a short cloak, to the knees
CAPE_RISE = 14.0                              # the hem rises this much to the middle split and to the edges: two swallow tails
CAPE_SPLIT = 34.0                             # the split up the middle starts this far below the collar
ELBOW = {"L": 14.0, "R": 33.0}                # the bend the forearms are modelled with (degrees)
ARM_OUT = {"L": 7.0, "R": 6.0}                # how far the arms hang out from the shoulders (degrees)
KNEE_Z = 28.0
TOP = 140.0                                   # the top of the hood
HEIGHT, RADIUS = 1.75, 0.42                    # metres, for the character's capsule
STRIDE = 2.6                                  # metres to a full walk cycle: a runner's long stride (the others: 1.8)
JOINTS = {                                    # u, world
    "Body": (0, 0, 56), "Chest": (0, 0, 73), "Head": (0, 0, 104),
    "ArmL": (25, 0, 100), "ArmR": (-25, 0, 100),
    "LegL": (12, 0, 54), "LegR": (-12, 0, 54),
    "ShinL": (12, 0, KNEE_Z), "ShinR": (-12, 0, KNEE_Z),
    "Cape": (0, 16, 104),
    "HoodA": (0, 19, 131), "HoodB": (0, 23, 118),             # the hinges of the hood's tail
    "Quiver": (17, 27, 74),                                   # the middle of the quiver: low on the back, left of the bedroll
    "Bow": None, "BowStringU": None, "BowStringL": None, "Arrow": None,    # (set while building)
    # set while building: ForeL / ForeR (the elbows, build_arm), HandR (the wrist), Spyglass (the middle of its grip
    # in the right fist, build_spyglass), Cape<col><row> (the middle of each panel's top edge, build_cape)
}
ELBOW_AT = (25, 0, 76)                        # the elbow, in the upper arm's own frame (x mirrored for the right arm)
WRIST_AT = (25, -0.5, 52.0)                   # the wrist, in the forearm's frame
GRIP = (24.8, -3.5, 45.8)                     # the middle of the spyglass's grip in the fist, in the forearm's frame
HOOD_SWAY = (133.0, 103.0)                    # the tail's sway weight: 0 at this height, 1 at that (u)
EYE = (-6.0, -13.0, 120.0)                    # the pupil of the right eye (the spyglass is raised to it)
WRIST_L = 25.0                                # the bow fist is modelled turned up this much more at the wrist (the archer's)
# ==================================================================================================

MATN = ["paint", "gold", "metal", "wool", "glow", "sway"]
KINDS = ["cloth", "skin", "hair", "leather", "gold", "metal", "fur", "gem", "core", "blade", "glow"]
_PAL = [
    # name        colour     slot     preview kind
    ("gold",     "#FFB616", "gold", "gold"), ("gold_l", "#FFD63E", "gold", "gold"), ("gold_d", "#E39510", "gold", "gold"),
    ("gold_dd",  "#A2640C", "gold", "gold"),
    ("steel",    "#A19EA2", "metal", "metal"), ("steel_l", "#B6B2B3", "metal", "metal"), ("steel_ll", "#CFCAC8", "metal", "metal"),
    ("steel_d",  "#8A888E", "metal", "metal"), ("steel_dd", "#69676F", "metal", "metal"),
    ("lens",     "#35505F", "metal", "gem"), ("lens_l", "#8FBFD2", "metal", "gem"),
    ("skin",     "#C06A22", "paint", "skin"), ("skin_l", "#D47C2E", "paint", "skin"), ("skin_d", "#A2571C", "paint", "skin"),
    ("skin_dd",  "#7E421A", "paint", "skin"), ("lip", "#8A4226", "paint", "skin"),
    ("hair",     "#3E2A20", "paint", "hair"), ("hair_l", "#54382A", "paint", "hair"), ("hair_ll", "#684634", "paint", "hair"),
    ("hair_d",   "#241812", "paint", "hair"), ("brow", "#211610", "paint", "hair"),
    ("green",    "#566E20", "paint", "cloth"), ("green_l", "#6A842C", "paint", "cloth"), ("green_d", "#445A19", "paint", "cloth"),
    ("green_dd", "#324310", "paint", "cloth"),
    ("hood",     "#566E20", "sway", "cloth"), ("hood_l", "#6A842C", "sway", "cloth"), ("hood_d", "#445A19", "sway", "cloth"),
    ("hoodgold", "#FFB616", "sway", "gold"),
    ("cream",    "#DCBC80", "paint", "cloth"), ("cream_l", "#EBD09A", "paint", "cloth"), ("cream_d", "#C2A066", "paint", "cloth"),
    ("cream_dd", "#A6854E", "paint", "cloth"),
    ("roll",     "#B08A58", "wool", "cloth"), ("roll_l", "#C8A674", "wool", "cloth"), ("roll_d", "#7E5E3A", "wool", "cloth"),
    ("belt",     "#7B4A24", "paint", "leather"), ("belt_l", "#96602F", "paint", "leather"), ("belt_d", "#5A3418", "paint", "leather"),
    ("belt_dd",  "#40240F", "paint", "leather"),
    ("bracer",   "#6A4226", "paint", "leather"), ("bracer_l", "#82532F", "paint", "leather"), ("bracer_d", "#4E2F1A", "paint", "leather"),
    ("glove",    "#96592A", "paint", "leather"), ("glove_l", "#B06C34", "paint", "leather"), ("glove_d", "#78441E", "paint", "leather"),
    ("tube",     "#4A3024", "paint", "leather"), ("tube_l", "#8A4C2A", "paint", "leather"), ("tube_d", "#2E1E18", "paint", "leather"),
    ("trouser",  "#5A3B26", "paint", "cloth"), ("trouser_l", "#6D4930", "paint", "cloth"), ("trouser_d", "#452C1B", "paint", "cloth"),
    ("boot",     "#77492A", "paint", "leather"), ("boot_l", "#8F5B33", "paint", "leather"), ("boot_d", "#5A361D", "paint", "leather"),
    ("sole",     "#4A2E1B", "paint", "leather"), ("sole_d", "#33200F", "paint", "leather"),
    ("white",    "#F4EFE4", "paint", "gem"), ("pupil", "#15100E", "paint", "hair"),
    ("gem_w",    "#FFF4DA", "paint", "gem"),
    ("glow",     "#FFAE30", "glow", "glow"), ("glow_l", "#FFD470", "glow", "glow"),
    ("core",     "#17120F", "paint", "core"),
    # the bow, its string and its arrows (the archer's colours, a plainer wood)
    ("wood",     "#7A5432", "paint", "leather"), ("wood_l", "#946A40", "paint", "leather"), ("wood_d", "#5C3C20", "paint", "leather"),
    ("shaft",    "#6A452A", "paint", "leather"), ("shaft_l", "#C9A56E", "paint", "leather"),
    ("fletch",   "#E0D6B8", "paint", "cloth"), ("fletch_d", "#8A9A5A", "paint", "cloth"),
    ("string",   "#E6DABE", "paint", "cloth"),
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
NOSHADE = ("white", "pupil", "lip", "gem_w", "core", "brow", "glow", "glow_l", "lens", "lens_l", "string")


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
    if getattr(part, "sway", None):                           # cloth for the wind material: the alpha is how far it moves
        z0, z1 = part.sway
        z = a["verts"][a["tris"].reshape(-1), 2] / U + part.joint[2]
        rgba[:, 3] = np.clip((z0 - z) / (z0 - z1), 0.0, 1.0)
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
# The spy
# ##################################################################################################################
# Shapes are sculpted on 2 u cells (4 u for the cape, 1 u for the face) and MERGED into the fewest, largest boxes by
# emit(); studs, the clasp, the buckles, the fists, the spyglass, the binoculars, the lantern are direct blocks.

WING_W0, WING_K = 24.0, 0.12                  # half width of the cloak = WING_W0 + WING_K * (104 - z): narrow and light, not the King's mantle
GOLD_BARS = {"gold": (5, 10)}
QUILT = ((5, 7), (8, 12), (5, 7))             # the tunic: squarish pads


def build_leg(s):
    """-> (thigh, shin). The thigh: dark leather leggings banded with a strap and its gold buckle, a knee pad, and its
    half of the tunic's short skirt; the shin: more straps and a chunky boot, and (hidden inside the knee pad while
    the leg is straight) the drum the knee turns on."""
    side = "L" if s > 0 else "R"
    P, Q = Part("Leg" + side), Part("Shin" + side)
    g = Grid(IDENT, 3, 27, -19, 13, 0, 66, cs=2, sx=s)
    XS, Y, Z = g.XS, g.Y, g.Z
    g.box(5, 19, -7, 7, 24, 54, "trouser")                    # thigh
    g.box(5, 21, -9, 9, 36, 40, "belt_l")                     # a broad strap round it
    g.box(5, 21, -9, 7, 24, 32, "boot_l")                     # knee: a wide leather pad
    g.pbox(5, 21, -9, 7, 30, 32, "boot_d")
    # the half of the skirt that swings with this leg, ending in a drum about the hip axis
    sk = g.bm(5, 21, -9, 9, 44, 54)
    drum = (XS > 5) & (XS < 21) & (Y ** 2 + (Z - 54) ** 2 < 9.7 ** 2) & (Z > 54)
    g.fill(sk | drum, "cream")
    g.paint(sk & (Z < 46) & (g.hash(2, 3 + s, ax=(1, 1, 0)) < 0.5), "cream_d")     # a ragged hem
    g.paint(sk & (Y < -7) & (XS > 13) & (XS < 17), "cream_d") # a fold down the front
    emit(P, g, lim=(8, 16), lims={"trouser": (10, 20), "cream": ((5, 8), (8, 12), (5, 9)), "cream_d": ((4, 6), (4, 6), (4, 10)),
                                  "belt_l": ((8, 16), (8, 16), (4, 4))}, shade=0.5, seed=20 + s)
    g = Grid(IDENT, 3, 27, -19, 13, 0, 66, cs=2, sx=s)
    XS, Y, Z = g.XS, g.Y, g.Z
    g.fill((XS > 7) & (XS < 17) & (Y ** 2 + (Z - KNEE_Z) ** 2 < 37.0) & (Z > 22), "trouser_d")    # the knee's drum
    g.box(5, 19, -7, 7, 8, 24, "trouser")                     # the shin, wrapped
    g.box(5, 21, -9, 9, 16, 20, "belt_l")                     # a strap below the knee
    g.box(3, 23, -9, 9, 6, 12, "boot_l")                      # the boot's thick cuff
    g.box(3, 23, -17, 9, 0, 8, "boot")                        # a chunky foot
    foot = g.bm(3, 23, -17, 9, 0, 8)
    g.carve(foot & (Y < -13) & (Z > 6))
    g.carve(foot & (Y < -15) & (Z > 4))
    g.paint(foot & (Y < -9), "boot_l")                        # toe cap
    g.paint(foot & (Z < 2), "sole")
    emit(Q, g, lim=(8, 16), lims={"sole": (10, 22), "belt_l": ((8, 16), (8, 16), (4, 4))}, seed=24 + s)
    b = lambda *a, **k: Q.blk(IDENT, *a, sx=s, **k)
    b(2.3, 23.7, -17.8, 9.8, 0.0, 1.5, "sole_d")              # the welt of the sole
    b(9.5, 14.5, -10.2, -8.8, 15.6, 20.4, "gold")             # the strap's buckle: a hollow gold square
    b(11.0, 13.0, -10.7, -10.0, 17.0, 19.0, "belt_dd", bevel=0.15)
    b(22.8, 23.9, -3.0, 3.0, 7.0, 11.0, "gold_d")             # a gold plate on the outside of the cuff
    b = lambda *a, **k: P.blk(IDENT, *a, sx=s, **k)
    b(9.0, 15.0, -10.2, -8.8, 25.0, 29.5, "boot")             # knee cap
    b(10.8, 13.2, -10.9, -10.0, 26.2, 28.6, "gold")
    b(9.0, 15.0, -10.3, -8.8, 35.4, 40.6, "gold")             # the thigh strap's buckle
    b(10.6, 13.4, -10.9, -10.1, 36.8, 39.2, "belt_dd", bevel=0.15)
    b(20.8, 21.9, -2.0, 2.0, 36.6, 39.4, "gold_d")            # a stud on its outside
    return P, Q


def build_arm(s):
    """-> (upper arm, forearm with the hand). The elbow is where the forearm's frame is bent. A short green capelet
    with a gold border lies on each upper arm, over a big puffed cream sleeve; the forearm has a banded leather bracer."""
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
    g.box(19, 33, -8, 8, 76, 88, "cream")                     # the big puff
    g.pbox(19, 33, -8, 8, 76, 78, "cream_l")
    g.box(19, 31, -8, 8, 94, 98, "green")                     # capelet: draped in tiers, wider toward its edge
    g.box(19, 33, -8, 8, 90, 94, "green")
    g.box(19, 33, -10, 10, 86, 90, "gold")                    # its gold border, standing out
    cap = g.isn("green")
    fold = (g.iy + (g.ix // 3)) % 4                           # folds running down the capelet
    g.paint(cap & (fold == 0), "green_d")
    g.paint(cap & (fold == 2), "green_l")
    emit(P, g, lim=((4, 8), (2, 4), (6, 12)), pref="z", lims=dict(gold=((5, 10), (5, 10), (4, 4)), cream=QUILT, cream_l=QUILT, cream_d=(8, 16)),
         shade=0.3, proud_p=0.45, proud=(0.15, 0.5), seed=31 + s)
    a = lambda *q, **k: P.blk(A, *q, sx=s, **k)
    for y in (-6.0, 0.0, 6.0):                                # studs on the border
        a(32.8, 33.7, y - 1.1, y + 1.1, 86.9, 89.1, "gold_l", bevel=0.15)
    for x in (22.0, 28.0):
        a(x - 1.1, x + 1.1, -10.9, -9.9, 86.9, 89.1, "gold_l", bevel=0.15)
    # ---- forearm and hand (bent frame)
    g = Grid(Fo, 14, 36, -13, 13, 38, 82, cs=2, sx=s)
    XS, Y, Z = g.XS, g.Y, g.Z
    g.box(20, 30, -5, 5, 70, 80, "cream_d")
    g.box(18, 32, -7, 7, 70, 74, "cream_l")                   # the sleeve's cuff, turned back over the bracer
    g.box(20, 30, -5, 5, 52, 56, "glove_d")                   # the glove's wrist
    g.box(18, 32, -7, 7, 56, 70, "bracer")                    # leather bracer, banded with two straps
    g.pbox(18, 32, -7, 7, 56, 58, "bracer_d")
    g.pbox(18, 32, -7, 7, 62, 66, "belt_l")
    Q.bias = len(P._ch)
    emit(Q, g, lim=(8, 16), lims={"belt_l": ((8, 14), (8, 14), (4, 4))}, seed=41 + s)
    f = lambda *q, **k: Q.blk(Fo, *q, sx=s, **k)
    f(32.0, 32.9, -2.0, 2.0, 62.2, 65.8, "gold")              # the strap's buckles, outside and front
    f(23.0, 27.0, -7.9, -7.0, 62.2, 65.8, "gold")
    f(24.2, 25.8, -8.4, -7.7, 63.2, 64.8, "belt_dd", bevel=0.15)
    f(17.5, 32.5, -7.5, 7.5, 68.0, 69.4, "bracer_l")          # its upper lip
    if s > 0:
        # the bow hand (the archer's): the gloved fist, modelled turned up a little more at the wrist, closed round the
        # bow's grip, so the bow stands nearly upright while the forearm is held level
        wx, wy, wz = WRIST_AT
        Hf = Fo.sub(RX(-WRIST_L), (s * wx, 0.0, wz))
        GX, GY, GZ = GRIP
        f(21.5, 28.5, -4.4, 3.4, 49.0, 53.0, "glove_d")       # wrist
        h = lambda *q, **k: Q.blk(Hf, *q, sx=s, **k)
        h(20.4, 30.2, GY - 5.1, GY + 5.5, 43.6, 51.0, "glove")
        for i, (nm, dz) in enumerate((("glove_l", 0.3), ("glove", 0.0), ("glove_d", 0.2), ("glove", 0.6))):
            y0 = GY - 5.3 + i * 2.75
            h(19.6, 31.0, y0, y0 + 2.75, 40.4 + dz, 46.4, nm)
        h(18.2, 21.6, GY - 6.0, GY + 1.6, 45.6, 49.4, "glove_l")   # thumb
        P.bow_part = build_bow(Hf, Hf.w((s * GX, GY, GZ)), s)
    else:
        # RIG: the right hand, its own part turning at the wrist, closed round the spyglass in a hammer grip: the tube
        # runs through the fist from back to front (across the forearm), the eyepiece behind the little finger, the
        # big lens ahead of the thumb. The spyglass is modelled in this fist and never turns in it.
        wx, wy, wz = WRIST_AT
        JOINTS["HandR"] = tuple(float(v) for v in Fo.w((s * wx, wy, wz)))
        H = Part("HandR")
        h = lambda *q, **k: H.blk(Fo, *q, sx=s, **k)
        GX, GY, GZ = GRIP                                     # the grip's axis: along y, through (x GX, z GZ); its middle at y GY
        h(21.5, 28.5, -4.6, 3.2, 49.4, 53.6, "glove_d")       # wrist
        h(20.4, 30.2, GY - 5.1, GY + 5.5, 43.6, 51.0, "glove")     # the back of the hand and the palm
        for i, (nm, dz) in enumerate((("glove_l", 0.3), ("glove", 0.0), ("glove_d", 0.2), ("glove", 0.6))):
            y0 = GY - 5.3 + i * 2.75                          # four fingers side by side along the tube, curled under it
            h(19.6, 31.0, y0, y0 + 2.75, 40.4 + dz, 46.4, nm)
        h(18.2, 21.6, GY - 6.0, GY + 1.6, 45.6, 49.4, "glove_l")   # the thumb, lying along the tube on the inside
        P.hand_part = H
        P.glass_part = build_spyglass(Fo, (s * GX, GY, GZ))
        P.arrow_part = build_arrow(Fo, Fo.w((s * GX, GY, GZ)))      # (in the same fist: shown only while it shoots)
    return P, Q


# ---------------------------------------------------------------------------------------------------- the weak bow
# The archer's bow, arrow and quiver (troop_archer.py build_bow / build_arrow / build_quiver), smaller and plainer: a
# short hunting bow with no gold, a small quiver of seven. Frames and joints as hers, so UVLArcherCombat poses them.

BOW_H, BOW_D = 44.0, 16.0                     # half length (u; hers 57), how far the limbs come back toward the string (hers 21)
BOW_NOCK = 0.82
BOW_CANT = 82.0


def bow_curve(z):
    t = np.minimum(np.abs(z) / BOW_H, 1.0)
    a = BOW_D * (t / BOW_NOCK) ** 1.55
    b = BOW_D * (1.0 - 0.5 * (np.maximum(t - BOW_NOCK, 0.0) / (1.0 - BOW_NOCK)) ** 1.2)
    return np.where(t <= BOW_NOCK, a, b)


def build_bow(Hf, grip, s):
    """The bow as its own part, origin at the middle of the grip, modelled as it sits in the left fist. Its frame: +z up
    the upper limb, +y from the grip toward the string, x through its thickness."""
    JOINTS["Bow"] = tuple(float(v) for v in grip)
    P = Part("Bow")
    c, sn = math.cos(math.radians(BOW_CANT)), math.sin(math.radians(BOW_CANT))
    bz = Hf.R @ np.array([0.0, -1.0, 0.0])
    by = Hf.R @ np.array([s * sn, 0.0, c])
    bx = np.cross(by, bz)
    B = Frame(np.stack([bx, by, bz], axis=1), grip)
    P.frame = B
    g = Grid(B, -3, 3, -9, 27, -48, 48, cs=3)
    Y, Z = g.Y, g.Z
    y0, y1 = bow_curve(Z - 1.5), bow_curve(Z + 1.5)
    limb = (Y > np.minimum(y0, y1) - 3.6) & (Y < np.maximum(y0, y1) + 3.6) & (np.abs(Z) < BOW_H) & (np.abs(Z) > 6)
    g.fill(limb, "wood")
    AZ = np.abs(Z)
    g.paint(limb & (AZ > 40), "wood_d")                                                  # dark horn tips
    g.paint(limb & (AZ > 18) & (AZ < 21), "wood_l")
    emit(P, g, lim=((6, 6), (6, 9), (6, 15)), pref="z", shade=0.5, proud_p=0.3, seed=191)
    b = lambda *q, **k: P.blk(B, *q, **k)
    for i, z in enumerate((-7.0, -2.4, 2.4)):                 # the grip, wrapped in leather
        b(-2.6, 2.6, -3.2, 3.2, z, z + (4.6 if i != 1 else 4.8), ("belt_d", "belt", "belt_d")[i], bevel=0.12)
    ys = BOW_D + 0.4
    zn = BOW_H * BOW_NOCK
    P.string_parts = {}
    for key, sg in (("BowStringU", 1.0), ("BowStringL", -1.0)):
        JOINTS[key] = tuple(float(v) for v in B.w((0.0, ys, sg * zn)))
        S = Part(key)
        cuts = np.linspace(0.0, sg * zn, 5)
        for i in range(4):
            S.blk(B, -0.45, 0.45, ys - 0.45, ys + 0.45, cuts[i], cuts[i + 1], "string", bevel=0.2, tint=(1.0, 0.93)[i % 2], cull=False)
        S.blk(B, -0.8, 0.8, ys - 0.8, ys + 0.8, 0.0, sg * 2.5, "belt_l", bevel=0.2, cull=False)
        P.string_parts[key] = S
    P.string_y = ys
    return P


ARROW_TIP, ARROW_NOCK = -34.0, 18.0           # along the arrow from the fist: the point, the nock (u; hers -40, 20)


def build_arrow(Fo, grip):
    """The loose arrow, origin where the right fist holds it; -z runs to the point (forward, across the forearm)."""
    JOINTS["Arrow"] = tuple(float(v) for v in grip)
    P = Part("Arrow")
    S = Frame(Fo.R @ np.array([[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 0.0, 0.0]]), grip)
    P.frame = S
    b = lambda *q, **k: P.blk(S, *q, cull=False, **k)
    cuts = (ARROW_NOCK - 1.0, 6.0, -10.0, -22.0, ARROW_TIP + 3.6)
    for i in range(4):
        b(-0.65, 0.65, -0.65, 0.65, cuts[i + 1], cuts[i], "shaft_l", bevel=0.2, tint=(1.0, 0.93, 1.0, 0.95)[i])
    b(-1.4, 1.4, -0.55, 0.55, ARROW_TIP + 1.4, ARROW_TIP + 4.0, "steel_d", bevel=0.15)
    b(-0.8, 0.8, -0.55, 0.55, ARROW_TIP, ARROW_TIP + 1.6, "steel", bevel=0.15)
    b(-2.4, 2.4, -0.4, 0.4, 9.0, 16.0, "fletch_d", bevel=0.1)                            # green-grey fletching
    b(-0.4, 0.4, -2.4, 2.4, 9.5, 15.5, "fletch", bevel=0.1)
    b(-0.85, 0.85, -0.85, 0.85, ARROW_NOCK - 1.2, ARROW_NOCK, "shaft", bevel=0.2)
    return P


QUIVER_ARROWS = 7
QUIVER_TILT = 22.0                            # its mouth leans toward the left shoulder (hers: -19, the right)


def build_quiver():
    """A small leather quiver low on the back, left of the bedroll, with seven arrows."""
    P = Part("Quiver")
    Qf = Frame(RY(QUIVER_TILT), P.joint)
    P.frame = Qf
    g = Grid(Qf, -6, 6, -6, 6, -16, 14, cs=2)
    Z = g.Z
    g.box(-5, 5, -4, 4, -14, 10, "belt")
    body = g.bm(-5, 5, -4, 4, -14, 10)
    g.paint(body & (Z < -10), "belt_dd")
    g.paint(body & (Z > -4) & (Z < -2), "belt_l")
    g.box(-6, 6, -5, 5, 10, 13, "belt_d")                     # a thick leather rim
    emit(P, g, lim=((4, 8), (4, 8), (6, 12)), lims={"belt_d": ((4, 6), (4, 6), (3, 3)), "belt_l": ((4, 8), (4, 8), (2, 2))}, shade=0.5, seed=195)
    b = lambda *q, **k: P.blk(Qf, *q, **k)
    b(-5.4, 5.4, -4.4, 4.4, -15.5, -13.5, "belt_dd")
    b(-4.0, 4.0, -3.0, 3.0, 10.0, 12.5, "belt_dd", cull=False)
    spots = ((-2.6, -1.6, 32.0), (0.0, -1.8, 29.0), (2.6, -1.6, 33.0), (-2.6, 1.4, 28.0), (0.0, 1.6, 34.0), (2.6, 1.4, 30.0), (-1.2, 0.0, 31.0))[:QUIVER_ARROWS]
    for i, (ax, ay, top) in enumerate(spots):
        Qa = Qf.sub(RX(-ay * 2.4 + (1.5 if i % 2 else -1.5)) @ RY(ax * 2.2) @ RZ(i * 37.0 % 90.0), (ax, ay, 8.0))
        a = lambda *q, **k: P.blk(Qa, *q, cull=False, **k)
        a(ax - 0.7, ax + 0.7, ay - 0.7, ay + 0.7, 8.0, top - 1.0, "shaft", bevel=0.2, tint=(1.0, 0.88, 1.1)[i % 3])
        a(ax - 2.3, ax + 2.3, ay - 0.4, ay + 0.4, top - 8.5, top - 2.0, ("fletch_d", "fletch")[i % 2], bevel=0.1)
        a(ax - 0.4, ax + 0.4, ay - 2.3, ay + 2.3, top - 8.0, top - 2.5, ("fletch", "fletch_d")[i % 2], bevel=0.1)
        a(ax - 0.9, ax + 0.9, ay - 0.9, ay + 0.9, top - 1.2, top, "shaft_l", bevel=0.2)
    P.mouth = Qf.w((0.0, 0.0, 13.0))
    return P


GLASS_EYE, GLASS_LENS = 11.0, -28.0           # the ends of the spyglass along its axis (u from the middle of the grip)


def build_spyglass(Fo, at):
    """The spyglass as its own part, origin at the middle of its grip, modelled as it sits in the right fist (the fist
    occupies -5.3 .. 5.7 u along it). Its frame: -z towards the big lens (forward, across the forearm), +z the
    eyepiece. Three drawn-out sections of dark leather, each wider than the last, gold rings between them, a broad
    gold rim round the lens. About 49 cm long."""
    hand = Fo.w(at)
    JOINTS["Spyglass"] = tuple(float(v) for v in hand)
    P = Part("Spyglass")
    S = Frame(Fo.R @ np.array([[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 0.0, 0.0]]), hand)
    P.frame = S

    def tube(r, z0, z1, name, **k):
        P.blk(S, -r, r, -r, r, z0, z1, name, **k)

    tube(2.0, 9.6, GLASS_EYE, "tube_d")                       # the eye cup
    tube(2.7, 6.4, 9.6, "gold")                               # the eyepiece's ring
    tube(1.9, -6.2, 6.4, "tube")                              # the narrow draw, in the fist
    tube(2.9, -8.2, -6.2, "gold_d")
    tube(2.6, -13.0, -8.2, "tube_l")                          # the middle draw, in two blocks
    tube(2.6, -17.4, -13.0, "tube")
    tube(3.3, -19.0, -17.4, "gold")
    tube(3.2, -24.0, -19.0, "tube_l")                         # the barrel
    tube(4.1, -27.2, -24.0, "gold")                           # the rim of the lens
    tube(4.4, -26.4, -25.0, "gold_l")
    tube(3.0, GLASS_LENS, -27.0, "lens", bevel=0.2)           # the glass
    P.blk(S, -2.4, -0.6, 0.6, 2.4, GLASS_LENS - 0.3, -27.6, "lens_l", bevel=0.2)       # a glint on it
    P.eye_end = S.w((0, 0, GLASS_EYE))
    P.lens_end = S.w((0, 0, GLASS_LENS))
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
    """A broad young face (straight rectangle brows, white eyes with dark pupils, a block nose, a small mouth) framed
    by dark hair in a few big pieces: a fringe and a lock down each cheek with a gold bead, under a deep green hood of
    large plain planes whose rim is a gold band with a few studs. -> (Head, HoodA, HoodB): the hood's shell on the head is rigid; its loose tail down the back is
    two hinged pieces the game swings as cloth."""
    P = Part("Head")
    F = Frame().sub(RZ(0.0), P.joint)
    g = Grid(F, -18, 18, -19, 19, 100, 140, cs=2)
    X, Y, Z = g.X, g.Y, g.Z
    AX = np.abs(X)
    g.box(-12, 12, -11, 11, 106, 128, "skin")
    sk = g.solid()
    g.paint(sk & (Y > 3), "hair_d")                           # the hair, in the shadow of the hood
    g.paint(sk & (Z > 124) & (Y > -9), "hair_d")
    g.paint(sk & (Z < 108) & (Y > -5), "skin_d")              # under the jaw
    emit(P, g, lim=(8, 14), lims={"hair_d": (6, 12)}, shade=0.3, seed=61)
    b = lambda *a, **k: P.blk(F, *a, **k)
    # ---- THE FACE: the archer's (archer_face), her heights + 6 on a plate in front of the skull (its front at -12).
    # His own: young and clean-shaven, a little more nose than hers, a slightly wider mouth.
    archer_face(P, F, 106.0, front=-12.0, hw=12.0, top=128.0, brow="brow", nose=(1.5, 3.0, 0.8), brow_t=1.8,
                brow_x=(2.6, 9.6), mouth=2.8)
    # ---- the hair: a few big pieces standing out from under the hood, as on the swordsman and the archer: a fringe
    # in three slabs over the brows and one long lock down each cheek with a gold bead
    b(-13.0, -4.0, -15.0, -11.0, 125.0, 132.0, "hair")
    b(-4.0, 5.0, -15.6, -11.0, 126.0, 132.0, "hair_l")
    b(5.0, 13.0, -15.0, -11.0, 124.0, 132.0, "hair")
    for sx in (1, -1):
        b(12.0, 16.0, -15.0, -5.0, 116.0, 128.0, "hair", sx=sx)
        b(12.0, 16.0, -14.4, -5.0, 106.0, 116.0, "hair_d" if sx > 0 else "hair_l", sx=sx)
        b(11.6, 16.4, -15.6, -11.4, 112.0, 115.0, "gold", sx=sx)             # the bead
    # ---- the hood: a deep shell round the head in large plain pieces: upright sides, a flat-topped dome in three
    # tiers, its rim one gold band
    m = Grid(F, -24, 24, -22, 26, 102, 142, cs=2)
    X, Y, Z = m.X, m.Y, m.Z
    AX = np.abs(X)
    AY = np.abs(Y - 3.0)
    tier = np.where(Z > 136, 6.0, np.where(Z > 132, 3.0, np.where(Z < 108, 4.0, 0.0)))      # how far each tier steps in
    hood = (AX < 22 - tier) & (AY < 20 - tier)
    hood &= ~((AX > 18 - tier) & (AY > 16 - tier) & (Y > 0))  # the back corners taken off; the front stays square for the rim
    hood &= ~((AX < 12) & (np.abs(Y) < 11) & (Z < 128))       # the skull
    hood &= ~((AX < 16) & (Y < -5) & (Z < 132))               # its opening: the face and the hair
    hood &= (Z > 104) & (Z < TOP)
    m.fill(hood, "green")
    m.paint(hood & (Z < 108), "green_d")                      # its lower edge, on the scarf
    m.paint(hood & (Z > 132), "green_l")                      # the crown, in the light
    m.paint(hood & (Y < -13), "gold")                         # the rim
    emit(P, m, lim=((10, 20), (10, 20), (10, 24)), lims={"gold": ((4, 12), (4, 4), (10, 24))},
         shade=0.25, proud_p=0.15, proud=(0.1, 0.3), seed=65, cjit=0.02)
    for sx in (1, -1):                                        # a gold stud on each side, two on each side of the rim
        b(21.4, 23.0, -1.4, 1.4, 119.6, 122.4, "gold", sx=sx, bevel=0.15)
        for z in (112.0, 124.0):
            b(17.4, 20.6, -17.9, -16.6, z - 1.4, z + 1.4, "gold_l", sx=sx, bevel=0.15)
    # ---- the hood's tail (RIG: HoodA > HoodB, hinged on the head; slot "sway": their alpha is the wind's weight)
    A, B = Part("HoodA"), Part("HoodB")
    A.sway = B.sway = HOOD_SWAY
    A.blk(F, -9.0, 9.0, 15.0, 25.0, 126.0, 134.0, "hood")
    A.blk(F, -6.0, 6.0, 13.0, 21.0, 133.0, 137.0, "hood_l")
    A.blk(F, -8.0, 0.0, 18.0, 27.0, 118.0, 126.0, "hood_d")
    A.blk(F, 0.0, 8.0, 18.0, 26.4, 118.0, 126.0, "hood")
    A.blk(F, -9.4, -7.6, 19.0, 21.4, 127.0, 129.4, "hoodgold", bevel=0.15)
    A.blk(F, 7.6, 9.4, 19.0, 21.4, 127.0, 129.4, "hoodgold", bevel=0.15)
    B.blk(F, -7.0, 1.0, 20.0, 28.0, 111.0, 118.0, "hood_l")
    B.blk(F, 1.0, 7.0, 20.0, 27.4, 111.0, 118.0, "hood_d")
    B.blk(F, -5.0, 5.0, 21.0, 27.0, 106.0, 111.0, "hood")
    B.blk(F, -3.0, 3.0, 22.0, 26.0, 103.0, 106.0, "hoodgold")
    return P, A, B


def cape_piece(x, L):
    """Which part of the cape a point belongs to: x (u), L (u below the collar) -> (key, column, row); row -1 = yoke."""
    W = WING_W0 + WING_K * max(L, 0.0)
    col = int(np.searchsorted(CAPE_U, x / W))
    row = int(np.searchsorted(CAPE_L[col % 2], L, side="right")) - 1
    return ("Cape" if row < 0 else "Cape%d%d" % (col, row)), col, row


def build_cape():
    """-> {key: part}: the yoke under the scarf ("Cape") and the hanging panels "Cape<col><row>", each hinged at the
    middle of its top edge to the panel above it (RIG: the King's cape panels, so the same C++ swings it). The shape is
    the spy's own: a short, narrow scout's cloak, flat on the back (no wings round the arms), split up the middle
    into two swallow tails with ragged tips, a thin gold edge along the hem."""
    cs = 4.0
    g = Grid(IDENT, -68, 68, -12, 52, 4, 108, cs=cs)
    nx, ny, nz = g.n
    xs = (np.arange(nx) + 0.5) * cs - 68
    zs = (np.arange(nz) + 0.5) * cs + 4
    Xc, Zc = np.meshgrid(xs, zs, indexing="ij")
    L = 104 - Zc
    W = WING_W0 + WING_K * L
    u = Xc / W
    amp = 0.2 + 1.6 * np.clip(L / 70, 0, 1)                   # shallow folds: a light cloth
    side = np.clip((np.abs(u) - 0.7) / 0.3, 0, 1)
    yb = 17 + 0.17 * L + amp * np.cos(u * np.pi * 5.0) * (1 - side) - 8.0 * side ** 2
    j0 = np.floor((yb + 12) / cs).astype(int)
    # the hem: lowest at the middle of each half (the tails' tips), rising to the split and to the edges; ragged
    Wh = WING_W0 + WING_K * (104 - CAPE_HEM - CAPE_RISE)
    hemz = CAPE_HEM + CAPE_RISE * np.abs(2.0 * np.clip(np.abs(xs) / Wh, 0, 1) - 1.0) - 4 * (hash3(np.arange(nx), np.zeros(nx, int), np.zeros(nx, int), 5) > 0.55)
    inside = (np.abs(Xc) < W) & (L >= 0) & (Zc > hemz[:, None]) & (Zc < 104 - np.maximum(0, np.abs(Xc) - 20) * 0.55)
    inside &= ~((np.abs(Xc) < 4) & (L > CAPE_SPLIT))          # the split
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
        if True:                                              # (no wings: the spy's cloak hangs flat on the back)
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
    g.paint(solid & (ridge > 0.75), "green_d")                # a few folds
    # hem: a band of gold blocks, a broken second row above it, a few strays hanging low
    hz = hemz[:, None, None]
    row0 = solid & (Z < hz + 4)
    row1 = solid & (Z > hz + 4) & (Z < hz + 8)
    pair = hash3(g.ix // 2, g.iy * 0, g.iz * 0, 8)
    g.paint(row0, "gold")                                     # a thin gold edge, nothing more
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
        assert m.any(), "the cloak's panel %s is empty" % key
        g.p = np.where(m, full, 0).astype(np.uint8)
        Pk = Part(key)
        emit(Pk, g, lim=((4, 8), (4, 8), (10, 16)), pref="z", lims={"gold": ((8, 12), (4, 8), (4, 4)), "gold_d": ((8, 12), (4, 8), (4, 4))},
             shade=0.3, proud_p=0.2, proud=(0.1, 0.3), seed=71 + idx, cjit=0.03)
        out[key] = Pk
    g.p = full
    ORDER[ORDER.index("Cape") + 1:ORDER.index("Cape") + 1] = keys[1:]
    return out


def torso_tiers(Z):
    """Half width and half depth of the torso at height Z (2 u steps): waist, ribs, chest, shoulders."""
    hw = np.where(Z < 80, 14, np.where(Z < 84, 16, np.where(Z < 100, 18, 16)))
    hd = np.where(Z < 84, 9, np.where(Z < 100, 11, 9))
    return hw, hd


ROLL = (-9.0, 31.0, 94.0, 8.2, 25.0)          # the bedroll: centre x, y, z, radius, half length (u)
LANTERN = (-43.0, 31.0, 79.0)                 # the middle of the lantern's light (u)


def build_body(arms, head):
    """-> (Body, Chest): the pelvis with the belt, its buckle, the pouches, the tunic's front and the binoculars; the
    torso with the crossed straps, the scarf and its clasp (carved clear of the swinging arms and the turning head),
    and on the back the bedroll with the lantern hung from its end."""
    P = Part("Body")
    blk = lambda *a, **k: P.blk(IDENT, *a, **k)
    # ---- pelvis: the top of the skirt, the belt
    g = Grid(IDENT, -26, 26, -19, 15, 30, 78, cs=2)
    X, Y, Z = g.X, g.Y, g.Z
    AX = np.abs(X)
    g.fill((AX < np.where(Z < 56, 22, 20)) & (np.abs(Y) < 11) & (Z > 52) & (Z < 66), "cream_d")
    g.box(-4, 4, -7, 7, 38, 54, "trouser_d")                  # between the legs
    g.box(-16, 16, -11, 11, 66, 74, "belt")
    emit(P, g, lim=(10, 18), lims={"belt": ((10, 18), (8, 12), (4, 4))}, seed=81)
    for sx in (1, -1):
        blk(10.5, 12.7, -12.2, -11.0, 69.0, 71.2, "gold", sx=sx, bevel=0.15) # belt studs
        blk(-1.2, 1.2, 11.0, 12.2, 68.8, 71.2, "gold_d")
        # a pouch on each hip, and one on each side
        blk(10.0, 19.0, -15.6, -11.0, 53.0, 64.0, "boot", sx=sx)
        blk(9.6, 19.4, -16.2, -11.0, 59.5, 64.6, "boot_l", sx=sx)
        blk(13.4, 15.6, -16.9, -16.0, 59.0, 61.4, "gold", sx=sx, bevel=0.15)
        blk(19.6, 22.0, -5.0, 5.0, 54.0, 64.0, "belt", sx=sx)
        blk(19.8, 22.4, -5.4, 5.4, 60.0, 64.6, "belt_l", sx=sx)
        blk(22.2, 23.0, -1.1, 1.1, 59.4, 61.6, "gold", sx=sx, bevel=0.15)
    # the tunic's front: one full-length strip per pleat, hanging between the legs
    xs = (-7.0, -5.0, -1.7, 1.7, 5.0, 7.0)
    for i in range(5):
        pr = (0.0, 0.6, 1.4, 0.6, 0.0)[i]
        blk(xs[i], xs[i + 1], -13.0 - pr, -11.0, (39.0, 36.0, 34.0, 37.0, 40.0)[i], 66.0, ("cream_d", "cream", "cream_l", "cream", "cream_d")[i],
            bevel=0.1)
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
    # the binoculars, hung from the belt on two straps, their big lenses down and forward
    Bn = IDENT.sub(RX(-28.0), (0.0, -15.0, 63.5))
    bn = lambda *a, **k: P.blk(Bn, *a, **k)
    for sx in (1, -1):
        blk(2.6, 4.6, -15.4, -13.6, 61.0, 66.0, "belt_d", sx=sx)             # straps
        bn(1.0, 6.6, -20.4, -15.0, 53.0, 61.0, "tube", sx=sx)               # barrels
        bn(0.7, 6.9, -20.7, -14.7, 60.4, 62.6, "gold", sx=sx)               # eyepiece rings
        bn(1.8, 5.8, -19.6, -15.8, 62.6, 63.6, "tube_d", sx=sx)
        bn(0.4, 7.2, -21.0, -14.4, 50.0, 53.4, "gold", sx=sx)               # the rims of the lenses
        bn(1.4, 6.2, -20.0, -15.4, 49.3, 50.2, "lens", sx=sx, bevel=0.2)
        bn(3.9, 5.6, -19.4, -17.8, 49.0, 49.6, "lens_l", sx=sx, bevel=0.2)
    bn(-1.2, 1.2, -19.0, -16.4, 54.5, 59.5, "tube_d")         # the bridge between them
    bn(-0.9, 0.9, -19.6, -18.8, 56.0, 58.0, "gold_d", bevel=0.15)

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
    g.paint(body & (Z > 100), "green")                        # the scarf over the shoulders
    panel = (AX < 12) & (Y > -13) & (Y < -11) & (Z > 80) & (Z < 98)          # the tunic's front, proud of the chest
    g.fill(panel, "cream")
    g.paint(panel & (AX < 4), "cream_l")                      # the placket down the middle
    g.fill((X ** 2 + Y ** 2 < 6.2 ** 2) & (Z > 104) & (Z < 112), "skin_d")   # neck
    emit(P, g, lim=QUILT, lims={"skin_d": (12, 12), "belt_d": ((10, 18), (8, 12), (4, 4)), "cream_l": ((8, 8), (2, 2), (5, 7)),
                                "green": (8, 14)}, shade=0.55, seed=82)
    for sx in (1, -1):                                        # two straps crossed over the chest, shoulder to waist
        for i in range(13):
            x = -15.0 + i * 2.3
            z = 97.0 - i * 1.7
            tb(x, x + 3.0, -14.5 if abs(x + 1.5) < 12 else -12.5, -11.0, z - 4.4, z, ("belt", "belt", "belt_l", "belt_l")[(i + 2 * (sx > 0)) % 4], sx=sx)
            if i in (2, 10):
                y = -14.5 if abs(x + 1.5) < 12 else -12.5
                tb(x + 0.5, x + 2.5, y - 0.6, y + 0.2, z - 3.2, z - 1.2, "gold", sx=sx, bevel=0.15)
    tb(-2.6, 2.6, -15.6, -14.2, 83.6, 88.8, "gold_d")         # where they cross: a gold plate
    tb(-1.3, 1.3, -16.1, -15.4, 84.9, 87.5, "belt_dd", bevel=0.15)

    # ---- the scarf: a thick green roll round the neck, a drape down the front to the clasp
    keep_out = np.zeros(SW_N, bool)
    for a in arms:
        keep_out |= swept(a, "x", -48, 48, step=2.0, grow=1)
    keep_out |= swept(head, "z", -22, 22, step=2.0, grow=1)
    m = Grid(IDENT, -28, 28, -21, 27, 86, 112, cs=2)
    X, Y, Z = m.X, m.Y, m.Z
    AX = np.abs(X)
    hw, hd = torso_tiers(Z)
    torso = ((AX < hw) & (np.abs(Y) < hd) & (Z < 104)) | ((AX < 12) & (Y > -13) & (Y < -11) & (Z > 80) & (Z < 98))
    zl = 90.0 + 0.4 * AX                                      # the lower edge of the drape: a V sweeping down to the clasp
    oval = (X / 23.0) ** 2 + (Y / 17.5) ** 2 < 1.0            # round in plan, not a box
    cowl = (Y < -9) & (Y > -15) & (AX < 22) & (Z > zl) & (Z < 106)
    cowl |= (Y < -9) & (Y > -19) & (AX < 20) & (Z > zl + 4) & (Z < 106)      # a second, thicker swag above it
    cowl |= (Y < -9) & (Y > -21) & (AX < 16) & (Z > zl + 8) & (Z < 104)      # ... and a third
    cowl |= oval & (Z > 100) & (Z < 106)                      # over the shoulders and round the neck
    cowl |= oval & (np.abs(Y) > 9) & (Z > 98) & (Z < 106)
    cowl &= oval | (Y < -9)
    rr = (X / 21.0) ** 2 + (Y / 16.0) ** 2
    cowl |= (rr < 1.25) & (rr > 0.5) & (Z > 104) & (Z < 110)                  # the roll standing up round the neck
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
    edge = cowl & (Y < -9) & (Z < zl + 2) & (AX > 6)          # the drape's lower edge: gold
    m.paint(edge, "gold")
    emit(P, m, lim=((6, 14), (4, 8), (2, 4)), pref="x", lims={"gold": ((4, 8), (4, 4), (2, 2))}, shade=0.35, proud_p=0.5, proud=(0.2, 0.7), seed=83, cjit=0.04)
    # the clasp: a hollow gold square with a dark stone
    cy = -17.0
    cy = -19.0
    tb(-5.0, 5.0, cy - 2.2, cy + 4.0, 91.0, 101.0, "gold")
    tb(-5.0, -2.8, cy - 3.2, cy - 2.0, 91.0, 101.0, "gold_l")
    tb(2.8, 5.0, cy - 3.2, cy - 2.0, 91.0, 101.0, "gold_l")
    tb(-2.8, 2.8, cy - 3.2, cy - 2.0, 98.8, 101.0, "gold_l")
    tb(-2.8, 2.8, cy - 3.2, cy - 2.0, 91.0, 93.2, "gold_l")
    tb(-2.8, 2.8, cy - 2.6, cy - 2.0, 93.2, 98.8, "gold_d")
    tb(-1.7, 1.7, cy - 3.6, cy - 2.4, 94.3, 97.7, "belt_dd", bevel=0.14)

    # ---- the bedroll across the back, strapped, a little to the right: its end shows past the shoulder
    rx, ry, rz, rr_, rl = ROLL
    r = Grid(IDENT, -36, 18, 20, 42, 84, 104, cs=2)
    X, Y, Z = r.X, r.Y, r.Z
    rad2 = (Y - ry) ** 2 + (Z - rz) ** 2
    cyl = (rad2 < rr_ ** 2) & (np.abs(X - rx) < rl)
    r.fill(cyl, "roll")
    end = cyl & (np.abs(X - rx) > rl - 2)                     # the ends: the blanket's spiral
    r.paint(end & (rad2 > 3.0 ** 2) & (rad2 < 5.2 ** 2), "roll_d")
    r.paint(end & (rad2 < 1.6 ** 2), "roll_d")
    r.paint(cyl & ~end & (r.hash(2, 3, ax=(1, 0, 0)) < 0.3), "roll_l")
    for xc in (rx - 12.0, rx + 12.0):                         # two straps
        r.paint(cyl & (np.abs(X - xc) < 2), "belt")
    emit(P, r, lim=((4, 10), (4, 8), (4, 8)), lims={"belt": ((4, 4), (4, 8), (4, 8))}, shade=0.4, seed=84)
    for xc in (rx - 12.0, rx + 12.0):
        tb(xc - 1.4, xc + 1.4, ry + rr_ - 0.6, ry + rr_ + 0.7, rz - 1.6, rz + 1.6, "gold", bevel=0.15)       # their buckles
        tb(xc - 2.0, xc + 2.0, 12.0, ry - 5.0, rz + 4.0, rz + 6.6, "belt_d")                                 # ... and the straps to the shoulders
    # ---- the lantern: hung on a hook from the roll's end, a small iron frame round its light
    lx, ly, lz = LANTERN
    x0 = rx - rl
    tb(lx - 1.0, x0 + 2.0, ly - 1.0, ly + 1.0, rz - 1.0, rz + 1.0, "belt_dd")           # the hook's arm
    tb(lx - 0.8, lx + 0.8, ly - 0.8, ly + 0.8, lz + 8.0, rz - 1.0, "steel_dd")          # the chain
    tb(lx - 2.0, lx + 2.0, ly - 2.0, ly + 2.0, lz + 7.0, lz + 9.0, "belt_dd")           # the cap's knob
    tb(lx - 5.6, lx + 5.6, ly - 5.6, ly + 5.6, lz + 5.0, lz + 7.2, "belt_dd")           # the cap
    tb(lx - 5.2, lx + 5.2, ly - 5.2, ly + 5.2, lz - 7.0, lz - 5.0, "belt_dd")           # the base
    tb(lx - 4.0, lx + 4.0, ly - 4.0, ly + 4.0, lz - 5.0, lz + 5.0, "glow")              # the light
    tb(lx - 2.4, lx + 2.4, ly - 4.3, ly + 4.3, lz - 2.0, lz + 3.0, "glow_l")
    tb(lx - 4.3, lx + 4.3, ly - 2.4, ly + 2.4, lz - 2.0, lz + 3.0, "glow_l")
    for sx in (1, -1):
        for sy in (1, -1):                                    # the frame's four posts
            tb(lx + sx * 4.6 - 0.8, lx + sx * 4.6 + 0.8, ly + sy * 4.6 - 0.8, ly + sy * 4.6 + 0.8, lz - 5.0, lz + 5.0, "belt_dd", bevel=0.15)
    return B, P


WHOLE = ["Body", "Head", "ArmL", "ArmR", "LegL", "LegR", "Cape", "Spyglass", "Quiver"]


def wholes(parts):
    """The limbs as the single rigid pieces they are while every elbow, knee, wrist and cloth hinge is at rest."""
    return {"Body": Combo(parts["Body"], parts["Chest"]), "Head": Combo(parts["Head"], parts["HoodA"], parts["HoodB"]),
            "ArmL": Combo(parts["ArmL"], parts["ForeL"], parts["Bow"], parts["BowStringU"], parts["BowStringL"]),
            "ArmR": Combo(parts["ArmR"], parts["ForeR"], parts["HandR"]), "Quiver": parts["Quiver"], "LegL": Combo(parts["LegL"], parts["ShinL"]),
            "LegR": Combo(parts["LegR"], parts["ShinR"]), "Cape": Combo(*[parts[k] for k in ORDER if k.startswith("Cape")]),
            "Spyglass": parts["Spyglass"]}


def build_spy():
    t0 = time.time()
    parts = {}
    for s_, side in ((1, "L"), (-1, "R")):
        parts["Leg" + side], parts["Shin" + side] = build_leg(s_)
        parts["Arm" + side], parts["Fore" + side] = build_arm(s_)
    parts["HandR"] = parts["ArmR"].hand_part
    parts["Head"], parts["HoodA"], parts["HoodB"] = build_head()
    parts.update(build_cape())
    for q in parts.values():
        q.finalize()
    parts["Spyglass"] = parts["ArmR"].glass_part.finalize()
    parts["Arrow"] = parts["ArmR"].arrow_part.finalize()
    parts["Bow"] = parts["ArmL"].bow_part.finalize()
    for k, q in parts["Bow"].string_parts.items():
        parts[k] = q.finalize()
    parts["Quiver"] = build_quiver().finalize()
    parts["Body"], parts["Chest"] = [q.finalize() for q in build_body(
        [Combo(parts["ArmL"], parts["ForeL"]), Combo(parts["ArmR"], parts["ForeR"], parts["HandR"])],
        Combo(parts["Head"], parts["HoodA"], parts["HoodB"]))]
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
        if k == "Spyglass":
            posed[k] = rotated(pts[k], parts["ArmR"].joint, "x", axes["ArmR"][1])
        elif k == "Quiver":
            posed[k] = pts[k]                                 # (on the Chest, which stands still in these checks)
        else:
            posed[k] = rotated(pts[k], parts[k].joint, axes[k][0], axes[k][1])
    occ = {k: occ_grid(posed[k], 0.5) for k in WHOLE}
    bad = []
    for i, a in enumerate(WHOLE):
        for b in WHOLE[i + 1:]:
            if {a, b} in ({"Body", "LegL"}, {"Body", "LegR"}, {"Body", "Head"}, {"Spyglass", "ArmR"}, {"Quiver", "Body"}):
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
                        blade=(0.38, 1.0), fur=(0.95, 0), gem=(0.15, 0), core=(1.0, 0), glow=(0.5, 0))[kind]
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
    if kind == "glow":
        nt.links.new(col.outputs["Color"], b.inputs["Emission Color"])
        setv("Emission Strength", 1.4)
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
    path = os.path.join(V.PREVIEWS, "spy_%s.png" % name)
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



# how the previews hold the spyglass: (carried) the arm down, the tube forward; (the comparison) held out a little, to be seen
CARRY = dict(armr=6.0, forer=20.0, handr=20.0)
SHOW = dict(armr=-15.0, armr_z=-22.0, forer=15.0, handr=20.0)


def rig(obs):
    """Parent the objects as the engine does (after the export, which wants them loose)."""
    for key, ob in obs.items():
        if key in PARENT:
            ob.parent = obs[PARENT[key]]


def pose(obs, **ang):
    """Turn joints by degrees about x (Head: about z): legl, legr, shinl, shinr, arml, armr, forel, forer, handr, chest,
    body, head, hooda, hoodb; cape (every panel of the top row), cape1 .. cape3 (the rows below, each relative to the
    one above). Positive swings a hanging limb backwards. <key>_z turns it about z as well."""
    for key, ob in obs.items():
        parent = PARENT.get(key)
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
    parts = build_spy()
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
    print("SPY size: x %.3f m (%.2f..%.2f), y %.3f m (%.2f..%.2f), height %.4f m (lowest %.4f)" % (
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
        print("  %-8s %6d blocks (%d core)  %7d triangles (%d core)  %6d faces" % (
            key, len(parts[key].c), int(parts[key].core.sum()), ob["triangles"], int((kd == KINDS.index("core")).sum()), ob["voxel_faces"]))
    print("SPY triangles in all: %d  (%.1f s)" % (total, time.time() - t0))
    sg = parts["Spyglass"]
    m = lambda v: [round(float(c) * U, 5) for c in v]
    # The character file, in SM_KingB.json's format (no sword, no scabbard). "spyglass": the grip (the part's origin,
    # in the right fist), the direction the big lens points as modelled, and its two ends; "eye": the pupil it is
    # raised to; "hood": the tail's hinges; "lantern": the middle of its light (on the Chest). Metres, Blender axes.
    meta = dict(height=HEIGHT, radius=RADIUS, voxel=U, elbow_l=ELBOW["L"], elbow_r=ELBOW["R"], stride=STRIDE,
                cape=dict(cols=CAPE_COLS, rows=CAPE_ROWS), has_sheath=False,
                parts={key: dict(mesh=PREFIX + key, pivot=pivot(key), parent=PARENT.get(key, "")) for key in ORDER},
                spyglass=dict(part="Spyglass", parent="HandR", grip=pivot("Spyglass"),
                              dir=[round(float(v), 5) for v in sg.frame.R @ np.array([0.0, 0.0, -1.0])],
                              eye_end=m(sg.eye_end), lens_end=m(sg.lens_end), length=round((GLASS_EYE - GLASS_LENS) * U, 5)),
                eye=m(EYE), hood=dict(parts=["HoodA", "HoodB"], parent="Head", sway=[HOOD_SWAY[0] * U, HOOD_SWAY[1] * U]),
                lantern=dict(part="Chest", pos=m(LANTERN)), wrist_l=WRIST_L,
                # its weak bow, in the archer's format (SM_Archer.json): metres and unit vectors in Blender axes
                bow=dict(part="Bow", hand="L", parent=PARENT["Bow"], grip=pivot("Bow"),
                         axis=[round(float(v), 5) for v in parts["Bow"].frame.R[:, 2]],
                         string_dir=[round(float(v), 5) for v in parts["Bow"].frame.R[:, 1]],
                         length=round(2 * BOW_H * U, 5), string_offset=round(parts["Bow"].string_y * U, 5),
                         string_parts=["BowStringU", "BowStringL"]),
                arrow=dict(part="Arrow", hand="R", parent=PARENT["Arrow"], grip=pivot("Arrow"),
                           length=round((ARROW_NOCK - ARROW_TIP) * U, 5), tip_offset=round(-ARROW_TIP * U, 5)),
                quiver=dict(part="Quiver", parent=PARENT["Quiver"], pivot=pivot("Quiver"),
                            axis=[round(float(v), 5) for v in parts["Quiver"].frame.R[:, 2]],
                            mouth=m(parts["Quiver"].mouth), arrows=QUIVER_ARROWS))
    with open(os.path.join(V.MESHES, NAME + ".json"), "w") as f:
        json.dump(meta, f, indent=1)
    print("wrote %s.json" % NAME)
    if NO_RENDER:
        return

    to_preview(obs, parts)
    stage()
    rig(obs)
    Pv = V.PREVIEWS
    p = lambda n: os.path.join(Pv, "spy_%s.png" % n)
    pose(obs, **CARRY)
    if want("hero"):
        pose(obs, head=-12.0, arml=-6.0, forel=-12.0, **SHOW)
        hero = shot("hero", az=-32, el=-9, dist=3.6, target=(-0.05, 0, 0.86), res=(900, 1250), lens=62)
        montage([REF, hero], p("compare"), H=1250)
        pose(obs, **CARRY)
    if want("sides"):
        tiles = [shot("front", 0, 2, res=(720, 960)), shot("side", -90, 2, res=(720, 960)),
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
        pose(obs, legl=30, shinl=-10, legr=-25, shinr=35, arml=-30, forel=-25, armr=35, forer=10, handr=20, chest=-6, cape=20, cape1=8, cape2=6,
             hooda=14, hoodb=10)
        tiles = [shot("walk_front", -29, 0, dist=7.0, res=(720, 960)), shot("walk_left", 90, 2, dist=7.0, res=(720, 960)),
                 shot("walk_back", 150, 8, dist=7.0, res=(720, 960)), shot("walk_right", -90, 2, dist=7.0, res=(720, 960))]
        montage(tiles, p("walk"), H=960)
        pose(obs, **CARRY)
    print("done in %.1f s" % (time.time() - t0))


main()
