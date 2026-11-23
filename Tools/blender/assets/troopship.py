"""troopship: the troop ship, a war cog that carries a platoon and the heroes across the water (no reference picture:
designed from the grain ship's own art language, References/Remake/boat_grain.png, and the port of
References/RealmV2/port.png).

  SM_TroopShip   a voxel war cog, 22.5 m of hull (25 m with the bowsprit and the rudder), 6 m in the beam (6.6 m over
                 the shields), 16.9 m from the waterline to the masthead pennant. The grain ship (SM_Boat) is 12.75 m of
                 hull, 3.25 m in the beam and 9.1 m high: this one has 1.8 times its length, 1.85 times its beam and
                 3.3 times its deck. Sized from the units: a soldier's capsule is 0.8 m across and 1.7 m tall, and a
                 formation keeps them 1.25 m apart; aboard they stand 1.2 m by 1 m apart.
                 * the hull: the grain ship's two courses of mossy stone at the waterline, timber strakes above them,
                   wales, iron straps with rivets, riveted plates, a capped gunwale; a row of round shields hung
                   outside the bulwark each side;
                 * the MAIN DECK, 1.5 m above the water, 13 m long and 5.5 m wide inside the bulwark, 0.875 m high (chest
                   high on a soldier): open aft of the mast for twenty soldiers in four rows of five; a hatch, crates,
                   barrels, sacks, rope and a rack of spears before the mast;
                 * an ENTRY PORT in the bulwark each side, 1.75 m wide, between two posts with a lantern: the gangplank
                   lands there (SM_TroopShip_Gangplank, a mesh of its own that the game lays from the port to the
                   quay or the shore);
                 * the STERN CASTLE, a raised deck 2.25 m above the main deck with a battlement of timber merlons: lit
                   windows in its sides, its front and the transom, a door from the main deck, steep stairs up to it,
                   the helm, two stern lanterns, the rudder, a flagpole with the realm's flag. The heroes stand here;
                 * the FORECASTLE, 1.6 m above the main deck, a battlement round it rising to the stem: four archers
                   stand here. A door and stairs from the main deck; the stem with an iron-banded head, a lantern
                   hung from it, a bowsprit;
                 * one mast, 15.75 m above the water, with iron bands and a crow's nest; a yard and a cream square sail
                   8 m wide and 7 m deep in patched panels, a green banner down its middle with the realm's gold
                   tree; its foot is 2.9 m above the main deck, over the soldiers' heads; rope rigging: forestay,
                   backstays, shrouds with ratlines, braces, sheets; a pennant at the masthead;
                 * green banners with gold crossed swords on the castles' sides.
  SM_TroopShip_Gangplank   the gangplank: 4 m long, 1.25 m wide, boards on two stringers with cleats across them.
                 Pivot: the middle of its ship end, on the walking surface; it runs toward +X.

Pivot: the middle of the hull's length and beam on the WATERLINE (z = 0 is the water; it draws 1.125 m: the sea of the
Realm maps is 2 m deep). Long axis X, bow +X, as the grain ship's. No collision (the game moves it and stands the
units on its decks itself). The sail, the banners and the flags are cloth (slot "cloth": they sway, and the enemy's
are red).

Where units stand, where the entry ports are and how big the hull is go to the mesh's sidecar (SM_TroopShip.json:
"deck") and, for the game, to Source/SovereignRealms/VLTroopShipDeck.inl (written here: do not edit it by hand).

Run:  blender -b --factory-startup --python Tools/blender/assets/troopship.py -- [--no-render] [--views=a,b] [--samples N] [--lod] [--compare]
--lod also makes the far level of detail SourceArt/Meshes/LOD/SM_TroopShip_L1.gltf (the hull's own 12.5 cm voxel, faces
merged: as the grain ship's, not the buildings' 25 cm, which loses the sail and the rigging) and lists it in lods.json.
--compare: the "compare" preview has the grain ship beside it (built from boat.py).
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
import numpy as np
import voxlib as V
import voxkit as K
from voxlib import Vox
import boat as GB           # the grain ship's pieces: crates, barrels, sacks, rope coils, turned(), the preview render

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
NO_RENDER = "--no-render" in ARGS
VIEWS = [n for a in ARGS if a.startswith("--views=") for n in a.split("=", 1)[1].split(",")]
SAMPLES = int(ARGS[ARGS.index("--samples") + 1]) if "--samples" in ARGS else 16
TASK = "troopship"
NAME = "SM_TroopShip"
PLANK = "SM_TroopShip_Gangplank"

VX = 0.125
TX = V.TEXEL

# colours (the grain ship's)
WOOD_T = GB.WOOD_T
IRON = GB.IRON
STUD = GB.STUD
PLATE = GB.PLATE
RIG = GB.RIG
STRAKES = GB.STRAKES
DECK = GB.DECK
STONES = GB.STONES
DARKWOOD = GB.DARKWOOD
SACKS = GB.SACKS

# the plan, in voxels of 12.5 cm about the pivot (x along the ship, bow +x; z up from the waterline)
X0, X1 = -88, 92               # the transom .. the bow's tip
HW = 24.0                      # the half beam
KEEL = -9                      # the bottom (1.125 m under the water)
DECK_Z = 12                    # the main deck's top (1.5 m above the water)
RAIL_Z = 19                    # the bulwark's top amidships (exclusive)
CASTLE_X = -46                 # the stern castle's front wall (it covers x < this)
CASTLE_Z = 30                  # its raised deck's top
FORE_X = 58                    # the forecastle's aft wall (it covers x >= this)
FORE_Z = 25                    # its deck's top
PARAPET = 6                    # the castles' battlement: this high, its merlons 3 more
GATE = (-22, -8)               # the entry ports in the bulwark, both sides (x0, x1)
MAST_X = 4                     # the mast: x 4..10, y -3..3 (75 cm square; a metre square below the yard's height)
MAST_TOP = 126
NEST_Z = 101                   # the crow's nest's floor
YARD_Z = 90                    # the yard's underside
YARD_HW = 40
BRACE = -18.0                  # the yard and sail braced round this far (degrees about Z)
STEM_Z = 44                    # the top of the stem's head
OX, OY, OZ = 98, 34, 10        # the hull grid's voxel that is the pivot
NX, NY, NZ = 214, 68, 150

# where the units stand (metres about the pivot, Blender axes; z the deck they stand on)
m = lambda q: q * VX
MAIN_ROWS = [-0.7, -1.9, -3.1, -4.3]                       # x of each row on the main deck, the foremost first
MAIN_COLS = [0.0, 1.0, -1.0, 2.0, -2.0]                    # y, the middle first
SLOTS_MAIN = [(x, y, m(DECK_Z)) for x in MAIN_ROWS for y in MAIN_COLS]
SLOTS_FORE = [(7.95, 1.05, m(FORE_Z)), (7.95, -1.05, m(FORE_Z)), (9.1, 0.65, m(FORE_Z)), (9.1, -0.65, m(FORE_Z))]
SLOTS_STERN = [(-7.3, 0.9, m(CASTLE_Z)), (-7.3, -0.9, m(CASTLE_Z)), (-8.6, 1.9, m(CASTLE_Z)), (-8.6, -1.9, m(CASTLE_Z))]


def B(v, x0, y0, z0, x1, y1, z1, mat, color=None):
    """A box in the hull grid, in voxels about the pivot."""
    v.box(OX + x0, OY + y0, OZ + z0, OX + x1, OY + y1, OZ + z1, mat, color)


def half(x, z):
    """The hull's half beam (voxels) at x (a voxel's middle) and height z: drawn in a little at the transom with rounded
    quarters, full amidships, fining to the stem from the mast forward; narrower at the bottom (the flare)."""
    x = np.asarray(x, float)
    st = np.clip((X0 + 14.0 - x) / 14.0, 0, 1)
    hw = HW - 5.0 * st ** 2
    bw = np.clip((x - 26.0) / (X1 - 26.0), 0, 1)
    hw = np.where(x > 26, HW * np.clip(1 - bw ** 2.0, 0, 1) ** 0.75, hw)
    return hw * (0.64 + 0.36 * np.clip((np.asarray(z, float) + 9.0) / 15.0, 0, 1))


def keel(x):
    """The bottom: it rises into the forefoot at the bow and a little under the transom."""
    return KEEL + np.clip((x - (X1 - 34.0)) / 34.0, 0, 1) ** 1.6 * 15.0 + np.clip((X0 + 8.0 - x) / 8.0, 0, 1) * 3.0


def deck_z(x):
    """The top of the deck along the ship."""
    return np.where(x < CASTLE_X, CASTLE_Z, np.where(x >= FORE_X, FORE_Z, DECK_Z))


def sheer(x):
    """The forecastle's battlement rises to the stem."""
    return np.round(np.clip((x - 66.0) / 26.0, 0, 1) ** 1.5 * 6.0)


def top(x):
    """The top (exclusive) of the bulwark, or of a castle's battlement between its merlons."""
    return np.where(x < CASTLE_X, CASTLE_Z + PARAPET, np.where(x >= FORE_X, FORE_Z + PARAPET + sheer(x), RAIL_Z))


STRAPS = [X0 + 2, CASTLE_X - 3, -34, GATE[0] - 3, GATE[1] + 1, 14, 28, 42, FORE_X - 3, 72]      # the iron straps (their aft edge)


def hull():
    v = Vox(NX, NY, NZ, VX, origin=(OX, OY, OZ), name="hull", seed=2)
    X, Y, Z = v.grid()
    xs, ys, zs = X - OX + 0.5, np.abs(Y - OY + 0.5), Z - OZ
    yi = Y - OY
    hw = half(xs, zs)
    inx = (xs > X0) & (xs < X1)
    kb = keel(xs)
    tp = top(xs)
    dk = deck_z(xs)
    castle = (xs < CASTLE_X) | (xs >= FORE_X)
    # the merlons: along the sides by x, across the transom by y
    side_merlon = castle & (((X - OX - X0) // 5) % 2 == 0)
    transom = xs < X0 + 2
    tr_merlon = transom & (((yi + 40) // 5) % 2 == 0)
    tpm = tp + 3 * (np.where(transom, tr_merlon, side_merlon)).astype(int)
    body = inx & (ys <= hw) & (zs >= kb)
    solid = body & (zs < dk)
    wall = body & (zs >= dk) & (zs < tpm) & ((ys > hw - 2.0) | transom)
    wall &= ~((xs > GATE[0]) & (xs < GATE[1]) & (zs >= DECK_Z))                      # the entry ports
    shell = solid | wall
    # ---- timber strakes: two voxels high, planks about a metre long with staggered butts, each its own shade
    v.where(shell, "plank")
    strake = np.array([V.rgb(c) for c in STRAKES], np.uint8)
    k = ((zs // 2) * 3 + (X + (zs // 2) * 5) // 9) % len(STRAKES)
    v.c[shell] = strake[k[shell]]
    # ---- the stone courses: from the keel to 60 cm above the water, chunky and mossy at the waterline
    st = shell & (zs < 5)
    v.where(st, "stone")
    stc = np.array([V.rgb(c) for c in STONES], np.uint8)
    ks = ((X + (zs // 3) * 2) // 4 + zs // 3) % len(STONES)
    v.c[st] = stc[ks[st]]
    # ---- the decks: boards along the ship, two voxels wide, each its own shade
    dkm = solid & (zs == dk - 1) & (ys <= hw - 2.0)
    dc = np.array([V.rgb(c) for c in DECK], np.uint8)
    kd = ((Y // 2) * 3 + (X + (Y // 2) * 7) // 12) % len(DECK)
    v.where(dkm, "plank")
    v.c[dkm] = dc[kd[dkm]]
    # ---- one voxel outside the planking: the wales, the straps, the plates
    out1 = inx & (ys > hw) & (ys <= hw + 1.0) & (zs >= kb) & (zs < tp)
    out2 = inx & (ys > hw + 1.0) & (ys <= hw + 2.0) & (zs >= kb) & (zs < tp)
    v.where(out1 & ((zs == 5) | (zs == 6)), "beam", DARKWOOD)                       # the wale over the stone
    v.where(out1 & ((zs == DECK_Z - 1) | (zs == DECK_Z)), "beam", DARKWOOD)         # the wale at the deck
    v.where(out1 & (xs < CASTLE_X) & ((zs == CASTLE_Z - 2) | (zs == CASTLE_Z - 1)), "beam", DARKWOOD)   # ... at the raised decks
    v.where(out1 & (xs >= FORE_X) & ((zs == FORE_Z - 2) | (zs == FORE_Z - 1)), "beam", DARKWOOD)
    for xp in STRAPS:
        s = out1 & (xs >= xp) & (xs < xp + 2) & (zs >= -1)
        v.where(s, "paint", IRON)
        v.where(out2 & (xs >= xp) & (xs < xp + 1) & (zs >= 0) & (zs % 4 == 1), "paint", STUD)           # rivets
    # riveted plates on the castles' sides under their battlements
    for (a, b_, zp) in ((X0 + 4, CASTLE_X - 3, CASTLE_Z + 1), (FORE_X + 3, 72, FORE_Z + 1)):
        for xq in range(a + 4, b_ - 4, 10):
            s = out1 & (xs >= xq) & (xs < xq + 4) & (zs >= zp) & (zs < zp + 3)
            v.where(s, "paint", PLATE)
            v.where(out2 & (xs >= xq + 1) & (xs < xq + 3) & (zs == zp + 1), "paint", STUD)
    # the gunwale's cap rail amidships with chunky timber caps and a bolt on top; iron caps on the castles' merlons
    capz = RAIL_Z - 1
    mid = inx & (xs >= CASTLE_X) & (xs < FORE_X) & ~((xs > GATE[0]) & (xs < GATE[1]))
    v.where(mid & (ys > hw - 3.0) & (ys <= hw + 1.0) & (zs == capz), "beam", WOOD_T)
    for xc in list(range(CASTLE_X + 3, GATE[0] - 4, 8)) + list(range(GATE[1] + 6, FORE_X - 4, 8)):
        s = inx & (xs >= xc) & (xs < xc + 3) & (ys > hw - 3.0) & (ys <= hw + 1.0) & (zs >= capz) & (zs < capz + 2)
        v.where(s, "beam", "#e8b480")
        v.where(s & (zs == capz + 1) & (xs >= xc + 1) & (xs < xc + 2) & (ys > hw - 2.0) & (ys <= hw - 1.0), "paint", STUD)
    v.where(wall & castle & (zs == tpm - 1) & (side_merlon | tr_merlon), "paint", IRON)
    v.where(wall & castle & (zs == tp - 1) & ~(side_merlon | tr_merlon), "beam", DARKWOOD)
    v.chunky("stone", cell=4, depth=1, p=0.25, seed=9)
    v.scatter("stone", "mossy_stone", p=0.18, seed=4, region=(0, 0, OZ - 2, NX, NY, OZ + 2))
    v.scatter("stone", "mossy_stone", p=0.05, seed=5, region=(0, 0, OZ + 2, NX, NY, OZ + 5))

    # ---- the entry ports: a post each side of them (iron-capped), a lantern on the aft one; a sill plank
    for side in (1, -1):
        y0 = int(HW) - 3 if side > 0 else -int(HW) - 1
        for xg in (GATE[0] - 2, GATE[1]):
            B(v, xg, y0, DECK_Z, xg + 3, y0 + 4, RAIL_Z + 4, "post", "#e8b480")
            B(v, xg - 1, y0 - (0 if side > 0 else 1), RAIL_Z + 4, xg + 4, y0 + (5 if side > 0 else 4), RAIL_Z + 5, "paint", IRON)
        K.lantern(v, OX + GATE[0] - 1, OY + y0 + 2, OZ + RAIL_Z + 5, 4)
        ys0 = int(HW) - 2 if side > 0 else -int(HW) - 1
        B(v, GATE[0] + 1, ys0, DECK_Z - 1, GATE[1], ys0 + 3, DECK_Z, "beam", DARKWOOD)

    # ---- the stem: a heavy timber rising out of the bow and curving forward, iron-banded, a lantern hung from its head
    s0 = X1 - 4
    for z in range(int(keel(X1 - 1.0)), STEM_Z):
        off = int(round(5.0 * np.clip((z - 14) / float(STEM_Z - 14), 0, 1) ** 2))
        B(v, s0 + off, -2, z, s0 + 5 + off, 2, z + 1, "beam", "#e2a870")
        if z in (10, 20, 30, 38):
            B(v, s0 + off, -3, z, s0 + 6 + off, 3, z + 1, "paint", IRON)
    B(v, s0 + 4, -3, STEM_Z, s0 + 11, 3, STEM_Z + 3, "beam", "#e8b480")              # its head
    B(v, s0 + 5, -2, STEM_Z + 3, s0 + 10, 2, STEM_Z + 4, "gold", "#f0c040")
    B(v, s0 + 9, -1, STEM_Z - 3, s0 + 14, 1, STEM_Z - 2, "paint", IRON)              # the lantern's bracket
    B(v, s0 + 12, -1, STEM_Z - 5, s0 + 13, 1, STEM_Z - 3, "paint", IRON)
    K.lantern(v, OX + s0 + 13, OY, OZ + STEM_Z - 14, 4)
    # the bowsprit: a spar from the forecastle's deck out over the stem
    for i in range(34):
        x = 72 + i
        z = FORE_Z + 6 + int(round(i * 0.42))
        if x < s0 + 3 or z > STEM_Z + 3:
            B(v, x, -1, z, x + 1, 1, z + 2, "beam", "#e8b07a")
    hull.sprit = (72 + 33, 0, FORE_Z + 6 + 14 + 1)
    B(v, 72 + 31, -2, FORE_Z + 6 + 12, 72 + 33, 2, FORE_Z + 6 + 16, "paint", IRON)

    # ---- the stern castle: lit windows in its sides, its transom and its front, a door from the main deck
    for (plane, out) in ((OY + int(HW) - 1, 1), (OY - int(HW), -1)):
        for a0 in (X0 + 16, X0 + 27):
            K.window(v, "y", plane, OX + a0, OZ + DECK_Z + 6, w=5, h=7, out=out)
    for a0 in (-12, -3, 7):
        K.window(v, "x", OX + X0, OY + a0, OZ + DECK_Z + 6, w=5, h=7, out=-1)
    K.door(v, "x", OX + CASTLE_X - 1, OY - 4, OZ + DECK_Z, w=8, h=13, out=1)
    K.window(v, "x", OX + CASTLE_X - 1, OY - 16, OZ + DECK_Z + 6, w=5, h=7, out=1)
    K.window(v, "x", OX + CASTLE_X - 1, OY + 8, OZ + DECK_Z + 6, w=4, h=7, out=1)
    # the steep stairs up to it on the port side, with stringers and a hand rail
    n = (CASTLE_Z - DECK_Z) // 2
    for k_ in range(1, n + 1):
        x = CASTLE_X + n - k_
        B(v, x, 14, DECK_Z + 2 * k_ - 1, x + 1, 21, DECK_Z + 2 * k_, "beam", WOOD_T)
        for y in (13, 21):
            B(v, x, y, DECK_Z + 2 * k_ - 3, x + 1, y + 1, DECK_Z + 2 * k_ + 1, "beam", DARKWOOD)
        B(v, x, 13, DECK_Z + 2 * k_ + 5, x + 1, 14, DECK_Z + 2 * k_ + 6, "beam", WOOD_T)
    B(v, CASTLE_X + n - 1, 13, DECK_Z, CASTLE_X + n, 14, DECK_Z + 8, "post", WOOD_T)
    # the railing along its front (open at the stairs' head)
    RZ0 = CASTLE_Z
    xf = CASTLE_X - 1
    B(v, xf, -22, RZ0 + 4, xf + 1, 13, RZ0 + 5, "beam", WOOD_T)
    B(v, xf, -22, RZ0 + 1, xf + 1, 13, RZ0 + 2, "beam", DARKWOOD)
    for y in (-18, -12, -6, 0, 6, 12):
        B(v, xf, y, RZ0, xf + 1, y + 1, RZ0 + 6, "post", "#e8b480")
    # the two stern lanterns on posts at the transom's quarters
    for y in (-15, 15):
        B(v, X0 + 2, y - 1, RZ0, X0 + 4, y + 1, RZ0 + 17, "post", "#d8a070")
        K.lantern(v, OX + X0 + 3, OY + y, OZ + RZ0 + 17, 6)
    # the helm: a wheel on a pedestal, before the flagpole
    hx = X0 + 16
    B(v, hx, -2, RZ0, hx + 3, 2, RZ0 + 7, "post", "#d89a62")
    for dy in range(-6, 7):
        for dz in range(-6, 7):
            d = math.hypot(dy + 0.0, dz + 0.0)
            spoke = (dy == 0 or dz == 0 or abs(dy) == abs(dz)) and d <= 6.2
            if 3.6 < d <= 5.0 or spoke:
                B(v, hx + 3, dy, RZ0 + 8 + dz, hx + 4, dy + 1, RZ0 + 9 + dz, "beam", DARKWOOD if d > 1.5 else WOOD_T)
    B(v, hx + 3, 0, RZ0 + 8, hx + 5, 1, RZ0 + 9, "gold", "#f0c040")
    # the flagpole at the taffrail
    B(v, X0 + 6, -1, RZ0, X0 + 8, 1, RZ0 + 46, "post", "#e8b480")
    B(v, X0 + 5, -2, RZ0 + 46, X0 + 9, 2, RZ0 + 47, "gold", "#f0c040")
    B(v, X0 + 6, -1, RZ0 + 9, X0 + 8, 1, RZ0 + 10, "paint", IRON)
    hull.flag = (X0 + 8, 0, RZ0 + 31)
    # the rudder on the sternpost
    B(v, X0 - 3, -1, KEEL + 2, X0, 1, DECK_Z + 3, "beam", DARKWOOD)
    B(v, X0 - 4, -1, KEEL + 2, X0 - 3, 1, 4, "beam", DARKWOOD)
    for z in (-4, 3, 10):
        B(v, X0 - 3, -2, z, X0 + 1, 2, z + 1, "paint", IRON)

    # ---- the forecastle: a door and windows in its aft wall, stairs on the starboard side, a railing along its edge
    K.door(v, "x", OX + FORE_X, OY - 4, OZ + DECK_Z, w=8, h=10, out=-1)
    K.window(v, "x", OX + FORE_X, OY + 8, OZ + DECK_Z + 5, w=4, h=5, out=-1)
    nf = (FORE_Z - DECK_Z) // 2
    for k_ in range(1, nf + 1):
        x = FORE_X - nf - 1 + k_
        B(v, x, -18, DECK_Z + 2 * k_ - 1, x + 1, -11, DECK_Z + 2 * k_, "beam", WOOD_T)
        for y in (-19, -11):
            B(v, x, y, DECK_Z + 2 * k_ - 3, x + 1, y + 1, DECK_Z + 2 * k_ + 1, "beam", DARKWOOD)
        B(v, x, -11, DECK_Z + 2 * k_ + 5, x + 1, -10, DECK_Z + 2 * k_ + 6, "beam", WOOD_T)
    B(v, FORE_X - nf, -11, DECK_Z, FORE_X - nf + 1, -10, DECK_Z + 8, "post", WOOD_T)
    FZ0 = FORE_Z
    B(v, FORE_X, -10, FZ0 + 4, FORE_X + 1, 18, FZ0 + 5, "beam", WOOD_T)
    B(v, FORE_X, -10, FZ0 + 1, FORE_X + 1, 18, FZ0 + 2, "beam", DARKWOOD)
    for y in (-10, -4, 2, 8, 14):
        B(v, FORE_X, y, FZ0, FORE_X + 1, y + 1, FZ0 + 6, "post", "#e8b480")

    # ---- the mast, its step, its bands, the crow's nest and the cap
    B(v, MAST_X - 4, -7, DECK_Z, MAST_X + 10, 7, DECK_Z + 3, "beam", DARKWOOD)
    for (x, y) in ((MAST_X - 4, -7), (MAST_X + 9, -7), (MAST_X - 4, 6), (MAST_X + 9, 6)):
        B(v, x, y, DECK_Z + 2, x + 1, y + 1, DECK_Z + 3, "paint", STUD)
    B(v, MAST_X - 1, -4, DECK_Z, MAST_X + 7, 4, YARD_Z - 26, "post", "#e8b07a")      # the lower mast, a metre square
    B(v, MAST_X, -3, YARD_Z - 26, MAST_X + 6, 3, MAST_TOP, "post", "#e8b07a")
    for z in (DECK_Z + 8, 34, 48):
        B(v, MAST_X - 2, -5, z, MAST_X + 8, 5, z + 1, "paint", IRON)
        B(v, MAST_X + 2, -6, z, MAST_X + 4, -5, z + 1, "paint", STUD)
        B(v, MAST_X + 2, 5, z, MAST_X + 4, 6, z + 1, "paint", STUD)
    B(v, MAST_X - 2, -5, YARD_Z - 27, MAST_X + 8, 5, YARD_Z - 25, "beam", DARKWOOD)  # the hounds, where it steps in
    for z in (76, 112, 120):
        B(v, MAST_X - 1, -4, z, MAST_X + 7, 4, z + 1, "paint", IRON)
    B(v, MAST_X - 1, -4, YARD_Z - 1, MAST_X + 7, 4, YARD_Z, "paint", RIG[1])          # the parrel holding the yard
    B(v, MAST_X - 1, -4, YARD_Z + 4, MAST_X + 7, 4, YARD_Z + 5, "paint", RIG[1])
    # the crow's nest: a floor on brackets, a tub of boards with a rail, a lantern on its after corner
    nx0, nx1, ny = MAST_X - 7, MAST_X + 13, 10
    for k_ in range(3):
        B(v, MAST_X - 1 - k_ * 2, -4 - k_ * 2, NEST_Z - 3 + k_, MAST_X + 7 + k_ * 2, 4 + k_ * 2, NEST_Z - 2 + k_, "beam", DARKWOOD)
    B(v, nx0, -ny, NEST_Z, nx1, ny, NEST_Z + 1, "plank", "#e2b684")
    for (x0, x1, y0, y1) in ((nx0, nx1, -ny, -ny + 1), (nx0, nx1, ny - 1, ny), (nx0, nx0 + 1, -ny, ny), (nx1 - 1, nx1, -ny, ny)):
        B(v, x0, y0, NEST_Z + 1, x1, y1, NEST_Z + 5, "plank", "#d6a674")
        B(v, x0, y0, NEST_Z + 5, x1, y1, NEST_Z + 6, "beam", DARKWOOD)
    for (x, y) in ((nx0, -ny), (nx1 - 1, -ny), (nx0, ny - 1), (nx1 - 1, ny - 1)):
        B(v, x, y, NEST_Z, x + 1, y + 1, NEST_Z + 8, "post", "#e8b480")
        B(v, x, y, NEST_Z + 8, x + 1, y + 1, NEST_Z + 9, "paint", IRON)
    K.lantern(v, OX + nx0 + 2, OY + ny - 3, OZ + NEST_Z + 1, 4)
    B(v, MAST_X - 1, -4, MAST_TOP, MAST_X + 7, 4, MAST_TOP + 2, "beam", DARKWOOD)     # the cap
    B(v, MAST_X + 2, -1, MAST_TOP + 2, MAST_X + 4, 1, MAST_TOP + 12, "post", "#e8b07a")
    B(v, MAST_X + 1, -2, MAST_TOP + 12, MAST_X + 5, 2, MAST_TOP + 13, "gold", "#f0c040")
    return v


# ---------------------------------------------------------------------------------------------------- the cloth

def big(pattern, k):
    """A pixel emblem (rows of '.' and 'T') with every pixel k x k."""
    return ["".join(ch * k for ch in row) for row in pattern for _ in range(k)]


def sail():
    """The square sail (6.25 cm voxels): cream canvas in patched panels with seams and a bolt rope round it, billowing
    forward (+x), and down its middle a green banner with the realm's gold tree and a gold border that hangs below
    the sail's foot to a point. Origin: the middle of its head, on the yard's front face."""
    W2, H, TAIL = 76, 112, 16
    v = Vox(30, 2 * W2 + 8, H + TAIL + 10, TX, origin=(0, W2 + 4, H + TAIL), name="sail", seed=3)
    yy = np.arange(2 * W2) + 0.5 - W2
    bel = np.clip(1 - (yy / W2) ** 2, 0, 1) ** 0.7
    dep = np.zeros((2 * W2, H + TAIL), int)
    for j in range(H + TAIL):
        up = 0.55 + 0.45 * math.sin(math.pi * min(j, H - 1) / float(H - 1)) ** 0.6     # (fuller in the middle of its height)
        dep[:, j] = np.round(8.0 * bel * up)
    panel = ["#efe2c0", "#e9dab4", "#f3e8cc", "#e4d4aa", "#ece0bc"]
    emb = big(K.EMBLEMS["tree"], 3)
    BW = 22                                                    # the banner's half width
    ex0, ey0 = -len(emb[0]) / 2.0, 14
    for i in range(2 * W2):
        yc = yy[i]
        for j in range(H + TAIL):
            ab = abs(yc)
            if j >= H:                                         # the banner's tail below the foot
                k = j - H
                lim = BW * (1.0 - (k + 1) / float(TAIL + 1))
                if ab >= lim:
                    continue
                edge = ab >= lim - 1.5 or ab >= BW - 1.5
                col = ("gold" if (i + j) % 2 else "gold_dark") if edge else ("banner_dark" if (i * 7 + j * 3) % 11 == 0 else "banner")
            elif ab < BW and j >= 2:                           # the banner on the sail
                col = "banner_dark" if (i * 7 + j * 3) % 11 == 0 else "banner"
                if ab >= BW - 2.0:
                    col = "gold"
                pj, pi = j - ey0, int(math.floor(yc - ex0))
                if 0 <= pj < len(emb) and 0 <= pi < len(emb[pj]) and emb[pj][pi] != ".":
                    col = "gold_light" if (pj // 3 + pi // 3) % 5 == 0 else "gold"
            else:
                p_ = (int(yc + W2) // 19 + j // 16 + 3) % len(panel)
                col = panel[p_]
                if int(yc + W2) % 19 == 0 or j % 16 == 0:
                    col = "#cfbb90"                            # the seams
                elif (int(yc + W2) % 19 in (1, 18) or j % 16 in (1, 15)) and (i + j) % 3 == 0:
                    col = "#ddc99f"                            # stitching
                if i == 0 or i == 2 * W2 - 1 or j == 0 or j == H - 1:
                    col = "#c2a878"                            # the bolt rope round it
            z = H + TAIL - 1 - j
            d0 = dep[i, j]
            lo = min(d0, dep[max(i - 1, 0), j], dep[min(i + 1, 2 * W2 - 1), j], dep[i, max(j - 1, 0)], dep[i, min(j + 1, H + TAIL - 1)])
            for x in range(lo, d0 + 1):
                v.box(13 + x, i + 4, z, 14 + x, i + 5, z + 1, "paint", col)
    # the yard it hangs from: a squared spar with iron ends and rope lashings, on the mast's front face
    zy = H + TAIL
    v.box(6, 2, zy, 13, 2 * W2 + 6, zy + 7, "beam", "#e8b07a")
    for y in (2, 2 * W2 + 4):
        v.box(5, y, zy - 1, 14, y + 2, zy + 8, "metal", "#8a8890")
    for y in (14, 38, 62, 2 * W2 - 54, 2 * W2 - 30, 2 * W2 - 6):
        v.box(5, y, zy - 1, 14, y + 2, zy + 8, "wool", RIG[0])
    v.hang(region=(0, 0, 0, v.n[0], v.n[1], zy))               # (the cloth only, not the yard)
    t = GB.turned(v, BRACE, "sail")
    a = math.radians(BRACE)
    rot = lambda x, y: (x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a))
    # (in hull voxels about the mast's middle): the yard's ends and the foot's corners, turned with it
    sail.yard_ends = [rot(4.75, sy * (YARD_HW - 1.5)) for sy in (1, -1)]
    sail.corners = [rot((13 + dep[0, H - 1]) / 2.0, sy * (W2 - 1) / 2.0) + (H / 2.0,) for sy in (1, -1)]
    return t


def shield(kind, name):
    """A round shield 75 cm across hung on the bulwark (6.25 cm voxels), facing -Y: boards, an iron rim, a gold boss.
    Origin: its middle, on its back."""
    v = Vox(12, 3, 12, TX, origin=(6, 3, 6), name=name)
    field, cross = (("#e9dcc0", "#b98a5a"), ("#c9945c", "#e9dcc0"), ("#d8c8a8", "#8e8c94"))[kind % 3]
    for i in range(12):
        for k in range(12):
            d = math.hypot(i + 0.5 - 6, k + 0.5 - 6)
            if d > 6.1:
                continue
            if d > 4.9:
                v.box(i, 1, k, i + 1, 3, k + 1, "paint", IRON)
            else:
                c = cross if (kind % 3 == 0 and (i in (5, 6) or k in (5, 6))) or (kind % 3 == 1 and (i + k) % 6 < 2) or (kind % 3 == 2 and k < 6) else field
                v.box(i, 1, k, i + 1, 3, k + 1, "paint", c)
    v.box(4, 0, 4, 8, 1, 8, "paint", STUD)
    v.box(5, 0, 5, 7, 1, 7, "gold", "#f0c040")
    return v


# ---------------------------------------------------------------------------------------------------- rope

def rigging():
    """The rope (6.25 cm voxels, about 11 cm thick, two strands): forestay, backstays, shrouds with ratlines, the
    yard's lifts and braces, the sail's sheets. Ends in hull voxels (12.5 cm) about the pivot."""
    zmin = 14
    nx, ny, nz = 420, 172, (MAST_TOP + 6 - zmin) * 2
    org = (190, 86, -2 * zmin)
    v = Vox(nx, ny, nz, TX, origin=org, name="rigging", seed=8)
    cols = [V.rgb(c) for c in RIG]
    oi = np.array(org, float)
    off = np.array([(dx, dy, dz) for dx in range(4) for dy in range(4) for dz in range(4)])

    def rope(a, b, sag=0.0, r=0.95):
        a, b = np.array(a, float) * 2.0, np.array(b, float) * 2.0         # hull voxels -> fine voxels
        n = int(np.linalg.norm(b - a) / 0.35) + 2
        for s, t in enumerate(np.linspace(0.0, 1.0, n)):
            p = a + (b - a) * t
            p[2] -= sag * 2.0 * 4.0 * t * (1 - t)
            q = p + oi
            c = np.floor(q - 1.5).astype(int) + off
            ok = (np.linalg.norm(c + 0.5 - q, axis=1) <= r) & (c >= 0).all(axis=1) & (c[:, 0] < nx) & (c[:, 1] < ny) & (c[:, 2] < nz)
            c = c[ok]
            v.m[c[:, 0], c[:, 1], c[:, 2]] = V.IDS["paint"]
            v.c[c[:, 0], c[:, 1], c[:, 2]] = cols[(s // 4) % 2]

    mt = (MAST_X + 3, 0, MAST_TOP - 2)
    rope(mt, hull.sprit, 0.8)                                                           # forestay to the bowsprit
    rope((MAST_X + 3, 0, NEST_Z - 4), (X1 + 2.0, 0, STEM_Z + 1.5), 0.5)                 # inner stay to the stem's head
    for sy in (1, -1):
        rope(mt, (X0 + 3.0, sy * 15.0, CASTLE_Z + 12.0), 1.2)                            # backstays to the stern lanterns' posts
        top_ = (MAST_X + 3, sy * 4.5, NEST_Z - 2)
        feet = [(xs_, sy * (HW - 0.8), RAIL_Z - 0.5) for xs_ in (-4.0, 6.0, 16.0)]
        for f in feet:
            rope(top_, f, 0.2)                                                           # shrouds to the gunwale
        for kk in range(1, 9):                                                           # ratlines between them
            t = kk / 10.0
            pts = [tuple(np.array(f) + (np.array(top_) - np.array(f)) * t) for f in feet]
            rope(pts[0], pts[1], 0.0, r=0.62)
            rope(pts[1], pts[2], 0.0, r=0.62)
    for k_, sy in enumerate((1, -1)):
        ex, ey = sail.yard_ends[k_]
        ye = (MAST_X + 3 + ex, ey, YARD_Z + 2.0)
        rope(ye, (CASTLE_X - 2.0, sy * 12.0, CASTLE_Z + 5.0), 2.0)                       # braces aft to the castle's rail
        rope(ye, (MAST_X + 3, sy * 2.0, MAST_TOP - 6), 0.0, r=0.75)                      # the yard's lifts
        cx_, cy_, cz_ = sail.corners[k_]
        rope((MAST_X + 3 + cx_, cy_, YARD_Z - cz_ + 0.5), (GATE[0] - 6.0, sy * (HW - 0.8), RAIL_Z - 0.5), 1.0)     # sheets
    return v


# ---------------------------------------------------------------------------------------------------- the deck's gear

def gear():
    """Before the mast, on the main deck (6.25 cm voxels): a hatch with a grating, crates, barrels, sacks, rope and a
    rack of spears. Nothing aft of the mast, where the soldiers stand. Origin: the ship's middle line at x = 20 hull
    voxels, on the deck's top."""
    L, W = 76, 88
    v = Vox(L, W, 60, TX, origin=(0, W // 2, 0), name="gear", seed=6)
    o = lambda x, y: (x, y + W // 2)
    # the hatch: a coaming with a grating
    hx0, hy0, hx1, hy1 = 6, -13, 34, 13
    v.box(hx0, hy0 + W // 2, 0, hx1, hy1 + W // 2, 3, "beam", DARKWOOD)
    for i in range(hx0 + 2, hx1 - 2):
        for j in range(hy0 + 2, hy1 - 2):
            dark = (i % 4 < 2) and (j % 4 < 2)
            v.box(i, j + W // 2, 2, i + 1, j + W // 2 + 1, 3, "paint" if dark else "beam", "#3a2a1e" if dark else "#e2b684")
    for (x, y) in ((hx0, hy0), (hx1 - 2, hy0), (hx0, hy1 - 2), (hx1 - 2, hy1 - 2)):
        v.box(x, y + W // 2, 3, x + 2, y + W // 2 + 2, 4, "paint", IRON)
    # port side: crates stacked against the forecastle, sacks, a barrel
    for (x, y, z, s, fl) in ((62, 10, 0, 12, False), (62, 23, 0, 11, True), (49, 25, 0, 12, False), (62, 12, 12, 11, True), (50, 26, 12, 10, True),
                             (37, 30, 0, 10, False)):
        GB.crate(v, *o(x, y), z, s=s, seed=abs(x + y) % 5, flip=fl)
    GB.sack(v, *o(55, 17), 0, 4.4, 4.0, SACKS[2])
    GB.sack(v, *o(67, 18), 23, 4.0, 3.6, SACKS[0])
    GB.sack_lying(v, *o(42, 22), 0, "x", SACKS[1], length=5.5, fat=4.0, end=-1)
    GB.barrel(v, *o(28, 35), 0, seed=3)
    GB.barrel(v, *o(15, 35), 0, seed=5)
    GB.coil(v, *o(4, 32), 0, 5.0)
    # starboard side: barrels, a coil, and the rack of spears along the bulwark
    GB.barrel(v, *o(8, -35), 0, seed=7)
    GB.barrel(v, *o(44, -20), 0, seed=9)
    GB.sack(v, *o(36, -22), 0, 4.2, 3.8, SACKS[3])
    GB.coil(v, *o(46, -33), 0, 4.5)
    rx0, rx1, ry = 16, 40, -41
    for x in (rx0, rx1 - 2):
        v.box(x, ry + W // 2, 0, x + 2, ry + W // 2 + 3, 20, "post", "#d8a070")
    for z in (6, 17):
        v.box(rx0, ry + W // 2 + 1, z, rx1, ry + W // 2 + 3, z + 2, "beam", DARKWOOD)
    for x in range(rx0 + 3, rx1 - 3, 3):
        v.box(x, ry + W // 2 + 3, 0, x + 1, ry + W // 2 + 4, 34, "beam", "#e8b480")
        v.box(x, ry + W // 2 + 3, 34, x + 1, ry + W // 2 + 4, 38, "paint", "#a9adb4")
        v.box(x, ry + W // 2 + 3, 38, x + 1, ry + W // 2 + 4, 39, "paint", "#d8dce2")
    return v


def gangplank():
    """SM_TroopShip_Gangplank (6.25 cm voxels): boards across two stringers, a cleat every 37.5 cm, iron at both ends."""
    L, W = 64, 20
    v = Vox(L, W, 6, TX, origin=(0, W / 2.0, 4), name="gangplank", seed=4)
    cols = ["#f6d6aa", "#e2b684", "#eec696", "#d6a674"]
    for i in range(0, L, 4):
        v.box(i, 1, 2, i + 4, W - 1, 4, "plank", cols[(i // 4 * 3) % len(cols)])
    for y in (0, W - 2):
        v.box(0, y, 0, L, y + 2, 5, "beam", DARKWOOD)
    for i in range(5, L - 3, 6):
        v.box(i, 2, 4, i + 1, W - 2, 5, "beam", "#c89060")
    for i in (0, L - 2):
        v.box(i, 0, 3, i + 2, W, 5, "paint", IRON)
    return v


# ---------------------------------------------------------------------------------------------------- assembly

def build():
    v = hull()
    parts = [v]
    s = sail()
    parts.append(s.at(m(MAST_X + 3), 0.0, m(YARD_Z)))
    parts.append(rigging())
    parts.append(gear().at(m(20), 0.0, m(DECK_Z)))
    parts.append(K.flag("star", w=30, h=14, name="pennantMast").at(m(MAST_X + 4), 0.0, m(MAST_TOP + 4)))
    fx, fy, fz = hull.flag
    parts.append(K.flag("tree", w=40, h=24, name="flagStern").at(m(fx), 0.0, m(fz)))
    # banners with crossed swords on the castles' sides, both sides
    k = 0
    for (x, w, h) in ((CASTLE_X - 7.5, 14, 24), (FORE_X + 7.5, 14, 22)):
        ho = float(half(np.array([x]), 12)[0]) + 1.0
        zt = float(top(np.array([x]))[0]) - 1.0
        for side in (-1, 1):
            b_ = K.banner("swords", w=w, h=h, notch=4, name="banner%d" % k)
            parts.append(b_.at(m(x), side * (m(ho) + TX), m(zt), rot=0 if side < 0 else 2))
            k += 1
    # the shields along the bulwark, both sides
    for i, x in enumerate((-40, -31, -3, 6, 15, 24, 33, 42, 51)):
        ho = float(half(np.array([x + 0.5]), 12)[0]) + 1.0
        for side in (-1, 1):
            sh = shield(i + (side > 0), "shield%d%d" % (i, side > 0))
            parts.append(sh.at(m(x + 0.5), side * (m(ho) + 3 * TX), m(DECK_Z + 2.5), rot=0 if side < 0 else 2))
    for q in parts:
        a = q.mesh_arrays()
        print("  part %-12s %6d faces" % (q.name, 0 if a is None else len(a["verts"])))
    ob = V.join(parts, NAME)
    co = np.array([p.co[:] for p in ob.data.vertices])
    print("%s bounds %s .. %s" % (NAME, np.round(co.min(axis=0), 3), np.round(co.max(axis=0), 3)))
    return ob


def deck_meta():
    """What the game needs to know (metres, Blender axes; the game turns y round)."""
    return dict(
        capacity=dict(troops=len(SLOTS_MAIN) + len(SLOTS_FORE), heroes=len(SLOTS_STERN)),
        main=[[round(c, 3) for c in s] for s in SLOTS_MAIN], fore=[[round(c, 3) for c in s] for s in SLOTS_FORE],
        stern=[[round(c, 3) for c in s] for s in SLOTS_STERN],
        gate=dict(x=round(m((GATE[0] + GATE[1]) / 2.0), 3), y=round(m(HW), 3), z=round(m(DECK_Z), 3), width=round(m(GATE[1] - GATE[0] - 1), 3)),
        hull=dict(x0=m(X0 - 4), x1=m(X1 + 13), half_beam=round(m(HW + 2) + 3 * TX, 3), draught=round(-m(KEEL), 3), rail=m(RAIL_Z), mast=m(MAST_TOP + 13)),
        plank=dict(mesh=PLANK, length=4.0))


def write_inl(meta):
    """Source/SovereignRealms/VLTroopShipDeck.inl: the same numbers for the game, in Unreal's centimetres (y turned)."""
    def vec(s):
        return "FVector(%.1ff, %.1ff, %.1ff)" % (s[0] * 100.0, -s[1] * 100.0, s[2] * 100.0)
    lines = ["// Written by Tools/blender/assets/troopship.py from the model's own plan: do not edit by hand.",
             "// Where units stand on SM_TroopShip (cm, the ship's own space: +X the bow, Z up from the waterline), the entry",
             "// ports in its bulwark and the hull's size.", "#pragma once", "namespace VLTroopShipDeck", "{"]
    for (name, key, note) in (("Main", "main", "the main deck, aft of the mast: soldiers"), ("Fore", "fore", "the forecastle: archers first"),
                              ("Stern", "stern", "the stern castle: the heroes")):
        lines.append("\t// %s" % note)
        lines.append("\tstatic const FVector %s[] = { %s };" % (name, ", ".join(vec(s) for s in meta[key])))
    g, h = meta["gate"], meta["hull"]
    lines += ["\t// the entry ports: one each side, at +-GateY (the bulwark's line), their sill on the main deck",
              "\tstatic constexpr float GateX = %.1ff, GateY = %.1ff, GateZ = %.1ff, GateWidth = %.1ff;" % (g["x"] * 100, g["y"] * 100, g["z"] * 100, g["width"] * 100),
              "\t// the hull: from StemX to SternX along it, HalfBeam each side (over the shields), Draught under the water,",
              "\t// RailZ the bulwark's top, MastZ the masthead",
              "\tstatic constexpr float SternX = %.1ff, StemX = %.1ff, HalfBeam = %.1ff, Draught = %.1ff, RailZ = %.1ff, MastZ = %.1ff;"
              % (h["x0"] * 100, h["x1"] * 100, h["half_beam"] * 100, h["draught"] * 100, h["rail"] * 100, h["mast"] * 100),
              "\tstatic constexpr float PlankLength = %.1ff;      // SM_TroopShip_Gangplank, from its pivot along +X" % (meta["plank"]["length"] * 100),
              "}", ""]
    path = os.path.join(V.ROOT, "Source", "SovereignRealms", "VLTroopShipDeck.inl")
    with open(path, "w", newline="\n") as f:
        f.write("\n".join(lines))
    print("wrote", path)


# ---------------------------------------------------------------------------------------------------- previews

def crew():
    """Stand-ins for the units at every place (previews only): a block the size of a unit's capsule, 0.8 m across and
    1.7 m tall (the heroes 1.9 m, gold), so the deck's room can be judged."""
    import bpy
    obs = []
    for (slots, h, col) in ((SLOTS_MAIN, 1.7, (0.75, 0.68, 0.5, 1)), (SLOTS_FORE, 1.7, (0.2, 0.42, 0.14, 1)), (SLOTS_STERN[:2], 1.9, (0.85, 0.6, 0.1, 1))):
        mt = bpy.data.materials.new("Crew")
        mt.use_nodes = True
        mt.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = col
        for (x, y, z) in slots:
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=(x, y, z + h / 2.0))
            o = bpy.context.active_object
            o.scale = (0.6, 0.6, h)
            o.data.materials.append(mt)
            obs.append(o)
    return obs


def preview(tag, **kw):
    if NO_RENDER or (VIEWS and tag not in VIEWS):
        return
    path = os.path.join(V.PREVIEWS, "%s_%s.png" % (TASK, tag))
    kw.setdefault("samples", SAMPLES)
    GB.CPU = True                                              # (the GPU is the editor's)
    GB.render(path, **kw)


def make_lod(voxel=0.125):
    """LOD 1 at the hull's own voxel, with voxel_lods.py's rebuild (see the top of this file)."""
    p = os.path.join(HERE, "voxel_lods.py")
    ns = {"__file__": p, "__name__": "voxel_lods"}
    exec(compile(open(p).read().replace("\nmain()\n", "\n"), p, "exec"), ns)
    src = ns["read"](os.path.join(V.MESHES, NAME + ".gltf"))
    lob, tris = ns["rebuild"](NAME, voxel, 1, src, ns["TOL"]["buildings"])
    file = "%s_L1.gltf" % NAME
    V.export_gltf(lob, path=os.path.join(ns["OUT"], file), collision="none", extra=dict(lod_of=NAME, voxel=voxel, triangles=tris))
    bp = os.path.join(ns["OUT"], "lods.json")
    book = json.load(open(bp)) if os.path.exists(bp) else {}
    book[NAME] = dict(set="buildings", triangles=len(src[0]), levels=[dict(level=1, file=file, voxel=voxel, triangles=tris,
                      slots=[mt.name.replace("Vox_", "") for mt in lob.data.materials])])
    with open(bp, "w") as fh:
        json.dump(book, fh, indent=1)
    print("LOD %s: %d -> %d triangles" % (NAME, len(src[0]), tris))


def main():
    import bpy
    V.reset_scene()
    meta = deck_meta()
    gp = V.join([gangplank()], PLANK)
    V.export_gltf(gp, collision="none")
    bpy.data.objects.remove(gp)
    ob = build()
    print("faces", ob["voxel_faces"])
    V.export_gltf(ob, collision="none", extra=dict(deck=meta))
    write_inl(meta)
    if NO_RENDER:
        if "--lod" in ARGS:
            make_lod()
        return
    GB.sea()
    preview("three", target=(0.5, 0, 5.5), az=35, el=24, dist=60, lens=50, res=(1280, 860), sun_az=-130, sun_el=30)
    preview("side", target=(0.5, 0, 6.5), az=0, el=5, dist=58, lens=50, res=(1280, 860), sun_az=-150, sun_el=30)
    preview("front", target=(0, 0, 6.5), az=90, el=8, dist=52, lens=50, res=(1280, 860), sun_az=-150, sun_el=30)
    preview("back", target=(0, 0, 5.5), az=-140, el=24, dist=60, lens=50, res=(1280, 860), sun_az=-130, sun_el=30)
    preview("play", target=(0, 0, 2.0), az=28, el=48, dist=150, lens=50, res=(1280, 860), sun_az=-130, sun_el=35)
    men = crew()
    preview("deck", target=(-1.0, 0, 3.0), az=20, el=52, dist=30, lens=50, res=(1280, 860), sun_az=-130, sun_el=40)
    preview("crew", target=(0.5, 0, 4.5), az=-35, el=30, dist=52, lens=50, res=(1280, 860), sun_az=-130, sun_el=30)
    if "--compare" in ARGS:
        gb = GB.build()
        gb.location = (0.0, -9.0, 0.0)
        preview("compare", target=(0.5, -3.0, 4.5), az=25, el=30, dist=70, lens=50, res=(1280, 860), sun_az=-130, sun_el=30)
    if "--lod" in ARGS:
        make_lod()                                             # (last: it clears the scene)


if __name__ == "__main__":
    main()
