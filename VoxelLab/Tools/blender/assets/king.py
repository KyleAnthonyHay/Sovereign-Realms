"""King David, the player's avatar: a stocky voxel king built as seven rigid parts (a wooden toy), each exported on
its own with its mesh origin at its joint.

    Blender -b --factory-startup --python Tools/blender/assets/king.py -- [--no-render] [--views hero,front,...] [--fast]

All coordinates below are WORLD voxels (3.125 cm): x = 0 is the middle of the figure (+X is his LEFT, he faces -Y),
y = 0 runs through the hips and shoulders, z = 0 is the ground. Every part lives in the same grid, so parts can be
checked against each other (swept volumes, posed overlaps) with plain array operations.

How the parts keep clear of each other
  * legs  : x 2..8 each side; the tabard hangs in the 4-voxel gap between them, the green skirt below the hip is part
            of each leg (so it swings with it), and the leg ends in a drum about the hip axis inside the pelvis.
  * arms  : x 9..15; the torso/belt/pelvis stop at x = 8, the cape wings start at x = 16 (17 below the elbow), and the
            sword stays inside the same corridor (x -16..-9). The shoulder is a drum about the shoulder axis and the
            fur collar is carved by the arms' swept volume.
  * cape  : hangs from under the fur and flares backwards so arms and heels miss it once it lifts.
  * head  : the fur is carved by the head's swept volume (it turns about Z); the beard ends above the chest.
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

VOX = 0.03125
X0, Y0 = 28, 22                      # grid index of world x = 0 / y = 0
NX, NY, NZ = 56, 52, 58
REF = os.path.join(V.ROOT, "References", "king.png")

_ix, _iy, _iz = np.meshgrid(np.arange(NX), np.arange(NY), np.arange(NZ), indexing="ij")
XW, YW, ZW = _ix - X0 + 0.5, _iy - Y0 + 0.5, _iz + 0.5            # world voxel centres

JOINTS = {                           # world voxels
    "Body": (0, 0, 22),
    "Head": (0, 0, 43),
    "ArmL": (12, 0, 36), "ArmR": (-12, 0, 36),
    "LegL": (5, 0, 20), "LegR": (-5, 0, 20),
    "Cape": (0, 5, 40),
}

C = dict(
    gold="#e9a013", gold_d="#b8760f", gold_l="#f8c532",
    steel="#8f9198", steel_l="#b1b3b9", steel_d="#6c6e77", steel_dd="#50525b",
    skin="#a85a2c", skin_d="#874523", skin_l="#bb6b38", lip="#7e3d2a",
    hair="#231a15", hair_l="#342720",
    fur="#ecdcb8", fur_l="#f8edd2", fur_d="#d3bb8c",
    green="#4f7220", green_l="#668a2b", green_d="#3b591b", green_dd="#2b4316",
    cream="#e8d6aa", cream_d="#cdb786",
    belt="#72421f", belt_d="#4f2d16", leather="#3e2a1e",
    sole="#633c20", sole_d="#472a17",
    blade="#cfcdc9", blade_d="#a9a8ac", blade_l="#e9e6e0",
    white="#f1ede2", pupil="#17120f", gem="#d04a1e", gem_d="#7c2614",
)


# ---------------------------------------------------------------------------------------------------- helpers

def part(key, seed=0):
    j = JOINTS[key]
    v = Vox(NX, NY, NZ, VOX, origin=(j[0] + X0, j[1] + Y0, j[2]), name="SM_King_" + key, seed=seed)
    v.key = key
    return v


def box(v, x0, x1, y0, y1, z0, z1, color=None, mat="paint"):
    v.box(x0 + X0, y0 + Y0, z0, x1 + X0, y1 + Y0, z1, mat, C.get(color, color) if color else None)


def mbox(v, s, x0, x1, y0, y1, z0, z1, color=None, mat="paint"):
    """box() mirrored to the -X side when s < 0."""
    if s < 0:
        x0, x1 = -x1, -x0
    box(v, x0, x1, y0, y1, z0, z1, color, mat)


def put(v, x, y, z, color, mat="paint"):
    box(v, x, x + 1, y, y + 1, z, z + 1, color, mat)


def mput(v, s, x, y, z, color, mat="paint"):
    mbox(v, s, x, x + 1, y, y + 1, z, z + 1, color, mat)


def fill(v, mask, color, mat="paint"):
    v.where(mask, mat, C.get(color, color) if color else None)


def rng_box(x0, x1, y0, y1, z0, z1):
    return (XW > x0) & (XW < x1) & (YW > y0) & (YW < y1) & (ZW > z0) & (ZW < z1)


def hash3(a, b, c, seed=0):
    h = (a.astype(np.int64) * 73856093) ^ (b.astype(np.int64) * 19349663) ^ (c.astype(np.int64) * 83492791) ^ (seed * 2654435761)
    h = (h ^ (h >> 13)) * 1274126177
    h = h ^ (h >> 16)
    return (h & 0xFFFFFF).astype(np.float32) / float(0xFFFFFF)


def cellhash(cell=2, seed=0, ax=(1, 1, 1)):
    """0..1 noise that is constant inside cells of `cell` voxels (per axis: 0 in `ax` = ignore that axis)."""
    return hash3((_ix // cell) * ax[0], (_iy // cell) * ax[1], (_iz // cell) * ax[2], seed)


def mottle(v, mask, colors, cell=2, seed=0, ax=(1, 1, 1)):
    """Recolour the masked voxels cell by cell from a list of (colour, share)."""
    h = cellhash(cell, seed, ax)
    lo = 0.0
    for col, share in colors:
        sel = mask & (h >= lo) & (h < lo + share)
        v.c[sel] = V.rgb(C.get(col, col))
        lo += share


def colour_mask(v, color):
    return (v.m > 0) & np.all(v.c == V.rgb(C.get(color, color)), axis=-1)


def dilate(mask, n=1):
    for _ in range(n):
        out = mask.copy()
        for axis in range(3):
            for sh in (1, -1):
                out |= np.roll(mask, sh, axis=axis)
        mask = out
    return mask


def bump(v, src, direction, p, cell=2, seed=0):
    """Copy a random share p of the cells of `src` one voxel outward in `direction` ('+x', '-y', ...), into air only."""
    axis = "xyz".index(direction[1])
    sh = 1 if direction[0] == "+" else -1
    pick = src & (cellhash(cell, seed) < p)
    m = np.roll(np.where(pick, v.m, 0), sh, axis=axis)
    c = np.roll(v.c, sh, axis=axis)
    take = (m > 0) & (v.m == 0)
    v.m[take] = m[take]
    v.c[take] = c[take]
    return take


def stamp(v, rows, x_left, z_top, y, palette, proud=None):
    """Pixel art on a front face: rows of characters, top row first, one voxel each, in the layer y..y+1.
    palette: char -> colour. proud: char -> how many extra layers it sticks out towards -Y."""
    proud = proud or {}
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch in ". ":
                continue
            d = proud.get(ch, 0)
            box(v, x_left + i, x_left + i + 1, y - d, y + 1, z_top - j, z_top - j + 1, palette[ch])


# ---- posed geometry (for carving the fur and for checking that nothing cuts through anything)

def centres(v):
    p = np.argwhere(v.m > 0).astype(np.float32) + 0.5
    p[:, 0] -= X0
    p[:, 1] -= Y0
    return p


def rotated(p, joint, axis, deg):
    """Rotate world voxel points about an axis through the joint (same sense as Blender's rotation_euler)."""
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    q = p - np.array(joint, np.float32)
    out = q.copy()
    if axis == "x":
        out[:, 1] = q[:, 1] * ca - q[:, 2] * sa
        out[:, 2] = q[:, 1] * sa + q[:, 2] * ca
    else:
        out[:, 0] = q[:, 0] * ca - q[:, 1] * sa
        out[:, 1] = q[:, 0] * sa + q[:, 1] * ca
    return out + np.array(joint, np.float32)


BIG = (120, 160, 90)
BIG_OFF = np.array([60, 60, 10], np.float32)
_FAT = [(0, 0, 0)] + [(dx, dy, dz) for dx in (-0.42, 0.42) for dy in (-0.42, 0.42) for dz in (-0.42, 0.42)]


def occupancy(p, fat=True):
    g = np.zeros(BIG, bool)
    for off in (_FAT if fat else _FAT[:1]):
        q = np.floor(p + BIG_OFF + np.array(off, np.float32)).astype(np.int64)
        ok = np.all((q >= 0) & (q < np.array(BIG)), axis=1)
        q = q[ok]
        g[q[:, 0], q[:, 1], q[:, 2]] = True
    return g


def inside(p, grid):
    q = np.floor(p + BIG_OFF).astype(np.int64)
    ok = np.all((q >= 0) & (q < np.array(BIG)), axis=1)
    out = np.zeros(len(p), bool)
    out[ok] = grid[q[ok, 0], q[ok, 1], q[ok, 2]]
    return out


def swept(v, axis, lo, hi, step=1.0, grow=1):
    """Boolean array over the part grid: every cell the part passes through while turning lo..hi degrees."""
    p = centres(v)
    g = np.zeros(BIG, bool)
    for ang in np.arange(lo, hi + 1e-6, step):
        g |= occupancy(rotated(p, JOINTS[v.key], axis, float(ang)))
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
    v = part("LegL" if s > 0 else "LegR", seed=3 if s > 0 else 4)
    # boot: brown sole, grey armoured foot with a lighter toe cap, gold ankle band
    mbox(v, s, 1, 9, -7, 4, 0, 2, "sole")
    mbox(v, s, 1, 9, -7, 4, 0, 1, "sole_d")
    mput(v, s, 3, -7, 1, "gold")
    mput(v, s, 6, -7, 1, "gold")
    mbox(v, s, 1, 9, -6, 4, 2, 5, "steel")
    mbox(v, s, 1, 9, -7, -4, 2, 4, "steel_l")                      # toe cap, a step lower than the instep
    mbox(v, s, 2, 8, -7, -6, 2, 3, "steel")
    mbox(v, s, 1, 9, 3, 4, 2, 4, "steel_d")                        # heel
    mbox(v, s, 1, 9, -4, 4, 5, 7, "gold")
    mbox(v, s, 1, 9, -4, 4, 5, 6, "gold_d")
    mbox(v, s, 4, 6, -5, -4, 5, 7, "gold_l")                       # buckle on the band
    # shin, greave plate and knee
    mbox(v, s, 2, 8, -3, 3, 7, 14, "steel")
    mbox(v, s, 3, 7, -4, -3, 7, 10, "steel_l")
    mbox(v, s, 2, 8, 3, 4, 7, 9, "steel_d")
    mbox(v, s, 2, 9, -4, 4, 9, 12, "steel_l")
    mbox(v, s, 2, 9, -4, 4, 9, 10, "steel")
    mbox(v, s, 4, 6, -5, -4, 10, 11, "gold")                       # knee stud
    mbox(v, s, 2, 8, -3, 3, 12, 14, "steel_d")
    # the skirt half that swings with this leg: gold hem, green cloth, and a drum about the hip axis
    mbox(v, s, 2, 8, -5, 5, 14, 16, "gold")
    mbox(v, s, 2, 8, -5, 5, 14, 15, "gold_d")
    mbox(v, s, 2, 7, -4, 4, 16, 20, "green")
    xr = (XW > 2) & (XW < 7) if s > 0 else (XW > -7) & (XW < -2)
    fill(v, xr & (YW ** 2 + (ZW - 20) ** 2 <= 16.3), "green")
    cloth = colour_mask(v, "green")
    mottle(v, cloth, [("green", 0.5), ("green_d", 0.3), ("green_l", 0.2)], cell=2, seed=11 + s, ax=(1, 1, 0))
    mbox(v, s, 2, 3, -4, -3, 16, 20, "gold")                       # gold border beside the tabard
    mput(v, s, 2, -4, 17, "gold_l")
    mput(v, s, 5, -4, 18, "gold")                                  # studs on the cloth
    mput(v, s, 4, -5, 15, "gold_l")
    mput(v, s, 6, -5, 15, "gold_l")
    for (x0, x1, col) in ((2, 8, "steel"),):                       # a little plate variation
        m = colour_mask(v, col) & (ZW > 7)
        mottle(v, m, [("steel", 0.7), ("steel_l", 0.15), ("steel_d", 0.15)], cell=2, seed=21 + s)
    return v


# ---------------------------------------------------------------------------------------------------- arms

def build_arm(s):
    v = part("ArmL" if s > 0 else "ArmR", seed=5 if s > 0 else 6)
    xr = (XW > 9) & (XW < 15) if s > 0 else (XW > -15) & (XW < -9)
    # pauldron: a drum about the shoulder axis (so it looks the same at any swing) with a plate hanging below it
    fill(v, xr & (YW ** 2 + (ZW - 36) ** 2 <= 16.3), "steel")
    mbox(v, s, 9, 15, -4, 4, 31, 36, "steel")
    mbox(v, s, 9, 15, -4, 4, 34, 35, "steel_l")
    mbox(v, s, 9, 15, -4, 4, 31, 32, "gold")
    mbox(v, s, 13, 15, -4, 4, 32, 34, "gold")                      # gold corner block, as in the picture
    mbox(v, s, 13, 15, -4, 4, 33, 34, "gold_l")
    # bare upper arm, gold band, big vambrace, leather cuff
    mbox(v, s, 9, 15, -3, 3, 29, 31, "skin")
    mbox(v, s, 9, 15, -3, 3, 30, 31, "skin_d")
    mbox(v, s, 9, 15, -4, 4, 28, 29, "gold")
    mbox(v, s, 9, 15, -4, 4, 22, 28, "steel_l")
    mbox(v, s, 9, 15, -4, 4, 22, 23, "steel")
    mbox(v, s, 9, 15, -4, 4, 27, 28, "steel")
    mbox(v, s, 14, 15, -1, 1, 24, 26, "gold")                      # studs
    mbox(v, s, 11, 13, -4, -3, 25, 26, "gold")
    plates = colour_mask(v, "steel_l") & (ZW > 22) & (ZW < 28)
    mottle(v, plates, [("steel_l", 0.7), ("steel", 0.3)], cell=2, seed=31 + s)
    mbox(v, s, 9, 15, -3, 3, 21, 22, "leather")
    # hand: a big fist
    mbox(v, s, 9, 15, -3, 3, 17, 21, "skin")
    mbox(v, s, 9, 15, -3, 3, 17, 18, "skin_d")
    if s > 0:
        mbox(v, s, 9, 15, -4, -3, 17, 20, "skin")                  # knuckles of a closed fist
        mbox(v, s, 9, 15, -4, -3, 17, 18, "skin_d")
        mbox(v, s, 12, 15, -4, 3, 19, 21, "steel")                 # gauntlet plate on the back of the hand
        mbox(v, s, 12, 15, -4, 3, 20, 21, "steel_l")
    else:
        build_sword(v)
    return v


def build_sword(v):
    """The sword in his right fist, point down, in front of the forearm. It stays inside x -16..-9 so that the arm can
    swing without it touching the hip, the leg or the cape wing."""
    # fingers closed round the grip
    box(v, -15, -9, -7, -3, 17, 21, "skin")
    box(v, -15, -9, -7, -3, 17, 18, "skin_d")
    box(v, -15, -9, -7, -6, 19, 20, "skin_d")
    box(v, -10, -9, -7, -3, 18, 21, "skin_l")                      # thumb side
    # grip above the fist and the pommel
    box(v, -14, -11, -6, -4, 21, 24, "gold_d")
    box(v, -14, -11, -6, -4, 22, 23, "gold")
    box(v, -14, -11, -7, -4, 24, 28, "gold")
    box(v, -15, -10, -8, -4, 25, 27, "gold")
    box(v, -14, -11, -8, -7, 25, 27, "gold_l")
    box(v, -14, -11, -7, -4, 27, 28, "gold_l")
    box(v, -13, -12, -9, -8, 25, 27, "steel_l")                    # the pommel's stone
    # cross-guard
    box(v, -16, -9, -7, -4, 15, 17, "gold")
    box(v, -16, -9, -7, -4, 15, 16, "gold_d")
    box(v, -16, -14, -7, -4, 14, 18, "gold")                       # the ends flare
    box(v, -11, -9, -7, -4, 14, 18, "gold")
    box(v, -16, -14, -7, -4, 17, 18, "gold_l")
    box(v, -11, -9, -7, -4, 17, 18, "gold_l")
    box(v, -14, -11, -8, -4, 14, 17, "gold")                       # boss
    box(v, -13, -12, -9, -8, 15, 16, "steel_l")
    # blade
    box(v, -14, -11, -6, -4, 5, 15, "blade")
    box(v, -13, -12, -7, -4, 6, 14, "blade_l")                     # the ridge down the middle
    box(v, -14, -13, -6, -4, 5, 15, "blade_d")                     # outer edge a shade darker
    box(v, -14, -12, -6, -4, 3, 5, "blade")
    box(v, -14, -13, -6, -4, 2, 3, "blade_d")
    box(v, -13, -12, -6, -4, 2, 3, "blade")
    box(v, -14, -13, -6, -4, 1, 2, "blade")


# ---------------------------------------------------------------------------------------------------- head

FACE = [               # x = -5 .. 4, top row is z = 48
    "sBBBssBBBs",      # brows, right under the crown
    "ssWPssPWss",      # eyes
    "ssssnnssss",      # cheeks and nose
    "bsMMMMMMsb",      # moustache
    "bbbbllbbbb",      # mouth
    "bbbbbbbbbb",      # chin
]
CROWN_FRONT = [        # 12 wide (x = -6 .. 5), top row is z = 53
    ".....LL.....",
    "LL..GGGG..LL",
    "GGG.GGGG.GGG",
]
CROWN_SIDE = [         # top row is z = 52
    "LL...LL...LL",
    "GGG.GGGG.GGG",
]


def build_head():
    v = part("Head", seed=7)
    box(v, -5, 5, -5, 5, 43, 51, "skin")
    # hair: a one-voxel shell on the sides and back, and the top of the head
    box(v, -5, 5, -5, 6, 51, 52, "hair")
    box(v, -6, 6, 5, 6, 44, 52, "hair")
    for sx in (1, -1):
        mbox(v, sx, 5, 6, 1, 6, 44, 52, "hair")
        mbox(v, sx, 5, 6, -5, 1, 48, 52, "hair")                   # above the ear
        mbox(v, sx, 5, 6, -2, 1, 45, 48, "skin_l")                 # the ear
        mbox(v, sx, 5, 6, -1, 0, 46, 47, "skin_d")
        mbox(v, sx, 5, 6, -6, -2, 42, 46, "hair")                  # beard along the jaw
        mbox(v, sx, 5, 6, -3, -2, 46, 48, "hair")                  # sideburn up to the hair
    # the face
    pal = dict(B="hair", W="white", P="pupil", n="skin_l", M="hair", l="lip", b="hair", s="skin")
    stamp(v, FACE, -5, 48, -5, pal, proud=dict(B=1, M=1, b=1, n=1))
    box(v, -5, 5, -6, -2, 42, 43, "hair")                          # the beard under the chin
    box(v, -3, 3, -7, -6, 42, 45, "hair")                          # and its bulk on the chin
    box(v, -1, 1, -7, -6, 44, 45, None, None)                      # keep the mouth open
    hair = colour_mask(v, "hair")
    # lumps of curls on the sides and back, below the crown
    low = hair & (ZW < 49)
    bump(v, low & (YW > 5), "+y", 0.5, cell=2, seed=3)
    bump(v, low & (XW > 5) & (YW > 0), "+x", 0.5, cell=2, seed=5)
    bump(v, low & (XW < -5) & (YW > 0), "-x", 0.5, cell=2, seed=6)
    bump(v, hair & (ZW > 51) & (np.abs(XW) < 4) & (YW > -4) & (YW < 5), "+z", 0.45, cell=2, seed=8)
    hair = colour_mask(v, "hair")
    mottle(v, hair, [("hair", 0.7), ("hair_l", 0.3)], cell=2, seed=9)
    # crown: a band round the head with merlons, a tall front piece and a gem
    ring = (np.abs(XW) < 6) & (np.abs(YW) < 6) & ~((np.abs(XW) < 5) & (np.abs(YW) < 5))
    fill(v, ring & (ZW > 49) & (ZW < 51), "gold")
    fill(v, ring & (ZW > 49) & (ZW < 50), "gold_d")
    cpal = dict(G="gold", L="gold_l")
    stamp(v, CROWN_FRONT, -6, 53, -6, cpal)
    for j, row in enumerate(CROWN_SIDE):
        z = 52 - j
        for i, ch in enumerate(row):
            if ch == ".":
                continue
            col = cpal[ch]
            put(v, -6 + i, 5, z, col)                              # back
            put(v, -6, -6 + i, z, col)                             # his right
            put(v, 5, -6 + i, z, col)                              # his left
    box(v, -1, 1, -7, -6, 50, 52, "gem")                           # the front gem
    box(v, -1, 1, -7, -6, 50, 51, "gem_d")
    for x in (-4, 3):
        put(v, x, -6, 50, "white")
    for y in (-4, 3):
        put(v, -6, y, 50, "white")
        put(v, 5, y, 50, "white")
    put(v, -1, 5, 50, "gem")
    put(v, 0, 5, 50, "gem")
    return v


# ---------------------------------------------------------------------------------------------------- cape

def cape_back(z):
    """y of the front face of the cape's back sheet at height z: it flares backwards as it falls."""
    d = 40 - z
    return 5 + int(round(d * 0.2 + (d / 37.0) ** 2 * 2.5))


def cape_half(z):
    """Half width of the cape at height z: it widens towards the hem."""
    return 18 if z >= 30 else (19 if z >= 7 else 20)


def cape_front(z):
    """y of the front edge of the wings (the sides of the cape that come forward past the arms)."""
    return 1 if z >= 30 else (0 if z >= 14 else -1)


def build_cape():
    v = part("Cape", seed=8)
    for z in range(3, 40):
        yb = cape_back(z)
        hw = cape_half(z)
        for x in range(-hw, hw):
            ax = x + 0.5
            if z + 0.5 > 40 - max(0.0, abs(ax) - 8) * 0.5:          # the top edge slopes down over the shoulders
                continue
            fold = 1 if (x + 60) % 6 in (2, 3, 4) else 0
            if abs(ax) > hw - 3:
                fold = 0
            y0 = yb + fold
            col = "green" if fold == 0 else "green_d"
            if (x + 60) % 6 == 0:
                col = "green_l"
            box(v, x, x + 1, y0, y0 + 2, z, z + 1, col)
        # wings: outside the arms (|x| >= 16, 17 below the elbow), so the arms can never be trapped
        if z < 35:
            for sx in (1, -1):
                mbox(v, sx, hw - 2, hw, cape_front(z), yb + 2, z, z + 1, "green")
                mbox(v, sx, hw - 1, hw, yb + 1, yb + 3, z, z + 1, None, None)      # take the square corner off
    cloth = v.m > 0
    wing = cloth & (np.abs(XW) > 16) & (YW < 5 + (40 - ZW) * 0.2)
    mottle(v, wing, [("green", 0.55), ("green_d", 0.25), ("green_l", 0.2)], cell=3, seed=4, ax=(0, 1, 1))
    # hem: gold blocks with a cream line above, some blocks standing proud
    hem = cloth & (ZW < 6)
    fill(v, hem, "gold")
    fill(v, cloth & (ZW > 6) & (ZW < 7), "cream")
    mottle(v, hem, [("gold", 0.6), ("gold_d", 0.25), ("gold_l", 0.15)], cell=3, seed=2, ax=(1, 1, 0))
    bump(v, v.exposed("+y") & hem, "+y", 0.45, cell=3, seed=12)
    # front edges of the wings: gold with cream bands, all the way down
    for sx in (1, -1):
        for z in range(3, 35):
            hw, yf = cape_half(z), cape_front(z)
            k = (z - 3) % 8
            if z < 7 or k in (5, 6, 7):                             # gold blocks, each with a cream one above it
                col = "cream" if (k == 7 and z >= 7) else "gold"
                mbox(v, sx, hw - 2, hw, yf - 1, yf + 2, z, z + 1, col)
            else:
                mbox(v, sx, hw - 2, hw, yf, yf + 1, z, z + 1, "green_d")
        # square ornaments on the outside of the wing
        for (zc, yc) in ((20, 5), (10, 5)):
            mbox(v, sx, 18, 19, yc, yc + 4, zc, zc + 4, "gold")
            mbox(v, sx, 18, 19, yc + 1, yc + 3, zc + 1, zc + 3, "green_d")
        # square clasp at the top of the wing, where the cape comes out from under the fur
        mbox(v, sx, 17, 18, 2, 6, 30, 34, "gold")
        mbox(v, sx, 17, 18, 3, 5, 31, 33, "green_d")
        mbox(v, sx, 16, 18, 0, 1, 30, 34, "gold")
        mbox(v, sx, 16, 18, 0, 1, 31, 33, "gold_l")
    return v


# ---------------------------------------------------------------------------------------------------- body

MEDAL = [              # 7 x 7, x = -3.5 .. 3.5 -> columns x = -4 .. 2 are shifted by half: we use 8 x 7 instead
    "..gggg..",        # z = 40
    ".gGGGGg.",
    "gGGllGGg",
    "gGlwwlGg",
    "gGGllGGg",
    ".gGGGGg.",
    "..gggg..",        # z = 34
]


def build_body(arms, head, cape):
    v = part("Body", seed=2)
    # pelvis: the top of the skirt, with the cream tabard down the middle
    box(v, -8, 8, -5, 5, 20, 27, "green")
    for sx in (1, -1):                                             # let the leg's skirt turn under the edge
        mbox(v, sx, 2, 8, -5, -4, 20, 21, None, None)
        mbox(v, sx, 2, 8, 4, 5, 20, 21, None, None)
    cloth = colour_mask(v, "green")
    mottle(v, cloth, [("green", 0.5), ("green_d", 0.3), ("green_l", 0.2)], cell=2, seed=11, ax=(1, 1, 0))
    box(v, -2, 2, -4, 4, 16, 20, "green_dd")                       # between the legs
    for sx in (1, -1):
        mbox(v, sx, 2, 3, -5, -4, 21, 27, "gold")
        mput(v, sx, 2, -5, 23, "gold_l")
        mput(v, sx, 5, -5, 24, "gold")
        mput(v, sx, 8 - 1, -1, 23, "gold")                         # studs on the hips
        mput(v, sx, 8 - 1, 0, 23, "gold")
    box(v, -2, 2, -6, -5, 20, 27, "cream")
    box(v, -2, 2, -6, -4, 14, 20, "cream")
    box(v, -1, 1, -6, -4, 13, 14, "cream")
    for x in (-2, 1):                                              # pleats
        box(v, x, x + 1, -6, -5, 14, 27, "cream_d")
    box(v, -2, 2, -6, -5, 14, 15, "cream_d")
    # torso: grey plate
    box(v, -8, 8, -4, 4, 27, 41, "steel_d")
    box(v, -7, 7, -5, -4, 30, 41, "steel")
    box(v, -7, 7, -5, -4, 30, 33, "steel_dd")                      # darker belly plates
    box(v, -7, 7, -5, -4, 33, 34, "steel_d")
    chest = colour_mask(v, "steel") & (YW < -4)
    mottle(v, chest, [("steel", 0.6), ("steel_l", 0.15), ("steel_d", 0.25)], cell=2, seed=17)
    box(v, -8, 8, 4, 5, 30, 39, "steel_d")                         # back plate (seen when the cape lifts)
    box(v, -8, 8, 4, 5, 34, 35, "steel_dd")
    # belt and buckle
    box(v, -8, 8, -6, 5, 27, 30, "belt")
    box(v, -8, 8, -6, 5, 27, 28, "belt_d")
    box(v, -8, 8, -6, 5, 29, 30, "belt_d")
    for x in (-7, -5, 4, 6):
        put(v, x, -6, 28, "gold")
    box(v, -3, 3, -7, -6, 26, 31, "gold")
    box(v, -2, 2, -7, -6, 27, 30, "gold_d")
    box(v, -1, 1, -8, -6, 28, 29, "gold_l")
    box(v, -1, 1, -8, -6, 27, 28, "gold")
    # sun medallion, its chains and the pendant under it
    pal = dict(g="gold_d", G="gold", l="gold_l", w="white")
    stamp(v, MEDAL, -4, 39, -6, pal, proud=dict(G=1, l=1, w=1))
    for (x, z) in ((-5, 36), (4, 36), (-5, 39), (4, 39), (-5, 33), (4, 33)):      # rays
        put(v, x, -6, z, "gold")
    for sx in (1, -1):
        pass
    stamp(v, [".gg.", "gwwg", ".gg."], -2, 32, -6, pal)
    put(v, -3, -6, 31, "gold_d")
    put(v, 2, -6, 31, "gold_d")
    # the green of the cloak on the chest beside the medallion
    for sx in (1, -1):
        mbox(v, sx, 5, 8, -5, -4, 36, 41, "green")
        mbox(v, sx, 6, 8, -5, -4, 34, 36, "green_d")
        for k in range(3):
            mput(v, sx, 5 + k, -5, 38 + k, "gold")
    # neck
    fill(v, (XW ** 2 + YW ** 2 <= 12.3) & (ZW > 41) & (ZW < 45), "skin_d")

    # ---- the fur collar: lumpy 2-voxel cubes over the shoulders and round the back of the neck
    hard = v.m > 0
    blobs = [(12.0, 0.0, 39.0, 7.0, 10.0, 5.6), (-12.0, 0.0, 39.0, 7.0, 10.0, 5.6),    # shoulder mounds
             (0.0, 7.0, 39.0, 16.0, 5.0, 4.6),                                          # round the back
             (9.5, -5.0, 39.5, 3.8, 3.4, 3.4), (-9.5, -5.0, 39.5, 3.8, 3.4, 3.4),      # lobes on the collar bones
             (16.5, 0.0, 37.5, 2.4, 9.0, 4.8), (-16.5, 0.0, 37.5, 2.4, 9.0, 4.8)]      # flaps outside the arms
    Xc, Yc, Zc = np.floor(XW / 2) * 2 + 1, np.floor(YW / 2) * 2 + 1, np.floor(ZW / 2) * 2 + 1
    d = np.full(v.n, 9.0, np.float32)
    for (cx, cy, cz, rx, ry, rz) in blobs:
        d = np.minimum(d, ((Xc - cx) / rx) ** 2 + ((Yc - cy) / ry) ** 2 + ((Zc - cz) / rz) ** 2)
    d = d + (cellhash(2, 41) - 0.5) * 0.45
    roof = 44.2 - np.maximum(0.0, np.abs(XW) - 8.0) * 0.36          # the shoulders slope down from the neck
    fur = (d <= 1.0) & (np.abs(XW) < 18) & (ZW < roof)
    # keep clear of everything that moves
    keep_out = np.zeros(v.n, bool)
    for a in arms:
        keep_out |= swept(a, "x", -47, 47, grow=1)
    keep_out |= swept(head, "z", -30, 30, step=2.0, grow=1)
    keep_out |= cape.m > 0
    fur &= ~keep_out & ~hard
    for k, (axis, sh) in enumerate(((0, 1), (0, -1), (1, 1), (1, -1), (2, 1), (2, -1))):       # jumbled cubes
        pick = fur & (hash3(_ix // 2, _iy // 2, _iz // 2, 50 + k) < (0.22 if axis < 2 else 0.3))
        fur |= np.roll(pick, sh, axis=axis) & ~keep_out & ~hard & (np.abs(XW) < 19) & (ZW < roof + 1) & (ZW > 32)
    fill(v, fur, "fur", "wool")
    fur = connected(v.m > 0, hard) & fur                           # no crumbs left floating by the carving
    v.m[(v.m == V.IDS["wool"]) & ~fur] = 0
    mottle(v, fur, [("fur", 0.5), ("fur_l", 0.28), ("fur_d", 0.22)], cell=2, seed=43)
    return v


# ---------------------------------------------------------------------------------------------------- build / export

def build_king():
    """-> {key: Vox} for the seven parts (all in the shared world grid)."""
    parts = {}
    parts["LegL"], parts["LegR"] = build_leg(1), build_leg(-1)
    parts["ArmL"], parts["ArmR"] = build_arm(1), build_arm(-1)
    parts["Head"] = build_head()
    parts["Cape"] = build_cape()
    parts["Body"] = build_body([parts["ArmL"], parts["ArmR"]], parts["Head"], parts["Cape"])
    return parts


ORDER = ["Body", "Head", "ArmL", "ArmR", "LegL", "LegR", "Cape"]


def pivot(key):
    return [round(c * VOX, 5) for c in JOINTS[key]]


def make_objects(parts):
    obs = {}
    for key in ORDER:
        ob = parts[key].to_object("SM_King_" + key)
        obs[key] = ob
    return obs


def pose(obs, legl=0.0, legr=0.0, arml=0.0, armr=0.0, cape=0.0, head=0.0):
    ang = dict(LegL=("x", legl), LegR=("x", legr), ArmL=("x", arml), ArmR=("x", armr), Cape=("x", cape), Head=("z", head), Body=("x", 0.0))
    for key, ob in obs.items():
        ob.location = pivot(key)
        axis, a = ang[key]
        ob.rotation_euler = (math.radians(a), 0, 0) if axis == "x" else (0, 0, math.radians(a))


def check_pose(parts, label, **angles):
    """Count voxels of one part that end up inside another in a pose. Legs/Head inside the Body are meant to be there
    (hip drum in the pelvis, neck in the head), every other pair must be clear."""
    ang = dict(LegL=("x", angles.get("legl", 0)), LegR=("x", angles.get("legr", 0)), ArmL=("x", angles.get("arml", 0)),
               ArmR=("x", angles.get("armr", 0)), Cape=("x", angles.get("cape", 0)), Head=("z", angles.get("head", 0)), Body=("x", 0))
    pts = {k: rotated(centres(parts[k]), JOINTS[k], ang[k][0], ang[k][1]) for k in ORDER}
    occ = {k: occupancy(pts[k], fat=False) for k in ORDER}
    bad = []
    for i, a in enumerate(ORDER):
        for b in ORDER[i + 1:]:
            n = int(inside(pts[a], occ[b]).sum()) + int(inside(pts[b], occ[a]).sum())
            if n:
                bad.append("%s-%s:%d" % (a, b, n))
    low = min(float(p[:, 2].min()) for p in pts.values()) - 0.5
    print("CHECK %-12s overlaps: %s | lowest point z = %.2f vox" % (label, ", ".join(bad) if bad else "none", low))
    return bad


# ---------------------------------------------------------------------------------------------------- previews

def grey_stage():
    """A neutral floor like the reference picture's backdrop (voxlib would otherwise add a grass-green one)."""
    bpy.ops.mesh.primitive_plane_add(size=400, location=(0, 0, -0.001))
    g = bpy.context.active_object
    g.name = "PreviewGround"
    gm = bpy.data.materials.new("PreviewGround")
    gm.use_nodes = True
    gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.11, 0.11, 0.115, 1)
    gm.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 1.0
    g.data.materials.append(gm)


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


def montage(paths, out, H=800, crops=None):
    tiles = []
    for i, p in enumerate(paths):
        a = load_px(p)
        if crops and crops[i]:
            x0, y0, x1, y1 = crops[i]
            a = a[y0:y1, x0:x1]
        tiles.append(fit_h(a, H))
    save_px(np.concatenate(tiles, axis=1), out)
    print("montage", out)


def shot(name, az, el, dist=5.4, target=(0, 0, 0.86), res=(720, 900), lens=85):
    path = os.path.join(V.PREVIEWS, "king_%s.png" % name)
    try:
        V.render(path, target=target, az=az, el=el, dist=dist, lens=lens, res=res, samples=16 if FAST else 40,
                 sun_az=228.0, sun_el=38.0, exposure=-0.9)
    except RuntimeError as e:                 # other jobs share the GPU: fall back to the CPU for this tiny scene
        print("GPU render failed (%s): rendering %s on the CPU" % (str(e).strip().splitlines()[0][:80], name))
        bpy.context.scene.cycles.device = "CPU"
        bpy.ops.render.render(write_still=True)
    return path


def want(name):
    return VIEWS is None or name in VIEWS


def main():
    V.reset_scene()
    parts = build_king()

    # ---- numbers
    allm = np.zeros((NX, NY, NZ), bool)
    for k in ORDER:
        allm |= parts[k].m > 0
    idx = np.argwhere(allm)
    lo, hi = idx.min(axis=0), idx.max(axis=0) + 1
    print("KING size: x %.3f m, y %.3f m (from %.3f to %.3f), height %.4f m" % (
        (hi[0] - lo[0]) * VOX, (hi[1] - lo[1]) * VOX, (lo[1] - Y0) * VOX, (hi[1] - Y0) * VOX, hi[2] * VOX))
    check_pose(parts, "rest")
    check_pose(parts, "walk A", legl=35, legr=-35, arml=-35, armr=35, cape=20)
    check_pose(parts, "walk B", legl=-35, legr=35, arml=35, armr=-35, cape=20)
    check_pose(parts, "run A", legl=45, legr=-45, arml=-45, armr=45, cape=30)
    check_pose(parts, "run B", legl=-45, legr=45, arml=45, armr=-45, cape=30)
    check_pose(parts, "arms, no cape", arml=45, armr=-45)
    check_pose(parts, "head turn", head=25)

    # ---- export: every part on its own, origin at its joint
    obs = make_objects(parts)
    total = 0
    for key in ORDER:
        ob = obs[key]
        ob.location = (0, 0, 0)
        V.export_gltf(ob, collision="none", extra=dict(pivot=pivot(key), part=key))
        total += int(ob["voxel_faces"])
    print("KING faces in all:", total)
    meta = dict(height=1.7, radius=0.42, voxel=VOX,
                parts={key: dict(mesh="SM_King_" + key, pivot=pivot(key)) for key in ORDER})
    with open(os.path.join(V.MESHES, "SM_King.json"), "w") as f:
        json.dump(meta, f, indent=1)
    print("wrote SM_King.json")
    if NO_RENDER:
        return

    # ---- previews
    grey_stage()
    P = V.PREVIEWS
    pose(obs)
    if want("hero"):
        hero = shot("hero", az=-32, el=-4, res=(800, 1000))
        montage([REF, hero], os.path.join(P, "king_compare.png"), H=1000, crops=[(0, 30, 1005, 1370), None])
    if want("level"):
        shot("level", az=27, el=6, res=(800, 1000))
    if want("sides"):
        tiles = [shot("front", 0, 3), shot("left", 90, 3), shot("back", 180, 3), shot("right", -90, 3)]
        montage(tiles, os.path.join(P, "king_sides.png"), H=800)
    if want("game"):
        tiles = [shot("game_front", 25, 42, dist=6.0), shot("game_back", 205, 42, dist=6.0)]
        montage(tiles, os.path.join(P, "king_game.png"), H=800)
    if want("walk"):
        pose(obs, legl=35, legr=-35, arml=-35, armr=35, cape=20)
        tiles = [shot("walkA_front", -27, 3, dist=6.0), shot("walkA_left", 90, 3, dist=6.0),
                 shot("walkA_back", 155, 8, dist=6.0), shot("walkA_right", -90, 3, dist=6.0)]
        montage(tiles, os.path.join(P, "king_walkA.png"), H=800)
        pose(obs, legl=-35, legr=35, arml=35, armr=-35, cape=20)
        tiles = [shot("walkB_front", 27, 3, dist=6.0), shot("walkB_left", 90, 3, dist=6.0),
                 shot("walkB_back", 205, 8, dist=6.0), shot("walkB_right", -90, 3, dist=6.0)]
        montage(tiles, os.path.join(P, "king_walkB.png"), H=800)
        pose(obs)
    if want("face"):
        shot("face", az=-20, el=2, dist=2.6, target=(0, 0, 1.36), res=(800, 800))


main()
