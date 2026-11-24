"""Realm v3: the fourth battle map (L_RealmV3), an island 512 m square, after References/RealmV3/ (PLAN.md the design;
concept_plan.png the layout, concept_threequarter.png the look). Pure numpy (+ scipy for the balance report, when it
is there); writes SourceArt/realmv3.json and SourceArt/realmv3_terrain.npz (heights, surfaces, the hazard map).

    Blender -b --factory-startup --python Tools/blender/realmv3_layout.py             (or: import realmv3_layout as R; R.build())
    Tools/.venv/Scripts/python Tools/blender/realmv3_layout.py [--debug] [--balance]   (--debug: Saved/realmv3_plan.png, the
                                                                                        plan from above; --balance: the routes)

Written from realmv2_layout.py (the same conventions: world metres, +X east, +Y north, +Z up; the postcard camera,
realmv3_cam.py, looks from the south-west). The level is fixed: this script is the development tool that makes it, and
everything in it is seeded.

The owner's verdict on Realm v2 was "not enough forest and too much space": this map is the gameplay and nothing else.
  the plateaus  two raised tables (14 m, cliffs all round; 164 x 148 m), A in the north-west (the player's) and B in the
                south-east (the enemy's): the castle, a home mine in a crag at either side of it, two towers. Two ways
                off: the base ramp, a broad smooth spur of the hillside down to the pass; and a stone stair down a
                cleft in the sea cliff to the side's own port (Realm v2's set: quay, warehouse, crane, arch, harbour
                tower, pier, ship), which joins nothing else
  the ridges    rock from the north-east corner to the south-west corner, coast to coast (sea cliffs at both ends): two
                long sharp crests either side of the basin, joined beyond its ends into one spine that runs on to each
                corner. Nobody climbs them. ONE way through each: a pass 12 m wide, cut where a base ramp comes down
  the basin     the contested ground between the crests (4 m, a lens 132 x 60 m): the lane runs straight across it from
                pass to pass; a neutral mine in the rock at its north-east end and one at its south-west end; level
                ground to build on either side of the lane
  the forest    everything else, to the shore: thick wood on a rolling floor nobody walks on (the hidden walls stand
                along the ramps and round the plateaus, and a hidden lid lies over the ground behind them: see
                assets/realmv3_terrain.py), so there is no way round the passes
The plan is point-symmetric about the middle of the map: (x, y) of the player's side is (-x, -y) of the enemy's, turned
half round, and so is every noise the ground is made from (noise2 / shash below), every tree and every rock. Travel
times, plateau sizes and ramp widths are therefore the same for both sides by construction; balance() measures them.

Terrain maths: as realmv2_layout.py's (fbm / ridged / warp), with the crests as tents along lines in the island's
diagonal frame (u north-east, v north-west).
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import realmv3_cam as C
import minehill
import softground
import town_layout as T
from town_layout import seg_dist, dist_polyline, in_poly, in_rect, meta, rot

ROOT = T.ROOT
OUT = T.OUT
MESHES = T.MESHES
NAME = "realmv3"

CELL = 0.25
HALF = 256.0                      # the world is 512 m square
N = int(2 * HALF / CELL)
ZMIN = -10.0
TOP = 120.0
WAT = -6.0                        # the sea
SEA = WAT
SEABED = -8.0
PLATEAU_Z = 14.0                  # the two bases
BASIN_Z = 4.0                     # the basin, the passes and the ramps' feet
DOCK_Z = SEA + 1.0                 # the ports' quays and piers
R2 = 1.0 / math.sqrt(2.0)

SURF = T.SURF + ["snow"]
GRASS, COBBLE, DIRT, GRAVEL, STONE, MOSSY, PLANK, SNOW = range(8)


# ---------------------------------------------------------------------------------------------------- symmetric noise

def hash2(ix, iy, seed=0):
    return T.hash2(ix, iy, seed)


def noise2(X, Y, scale, seed=0, octaves=3):
    """town_layout.noise2 made point-symmetric about the map's middle: the mean of the noise here and at (-x, -y),
    stretched back to the spread one noise has. 0 .. 1."""
    X, Y = np.asarray(X, np.float64), np.asarray(Y, np.float64)
    a = T.noise2(X, Y, scale, seed, octaves) + T.noise2(-X, -Y, scale, seed, octaves)
    return np.clip(0.5 + (a - 1.0) * R2, 0.0, 1.0)


def shash(X, Y, size, seed, shear=0.0):
    """A random number 0 .. 1 per block of `size` metres (the rows pushed along by `shear` blocks each), the same at
    (x, y) and (-x, -y)."""
    def g(x, y):
        j = np.floor(y / size)
        return T.hash2(np.floor((x + shear * size * j) / size), j, seed)
    return (g(X, Y) + g(-X, -Y)) % 1.0


def fbm(X, Y, scale, seed, octaves=4, gain=0.5):
    """Layered value noise, -1 .. 1."""
    out = np.zeros(np.shape(X))
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        out += (noise2(X, Y, scale / (2 ** o), seed + 13 * o, octaves=1) * 2.0 - 1.0) * amp
        tot += amp
        amp *= gain
    return out / tot


def ridged(X, Y, scale, seed, octaves=4, gain=0.5):
    """A ridged sum, 0 .. 1 (sharp crests, smooth feet): see realmv2_layout.ridged."""
    out = np.zeros(np.shape(X))
    amp, tot, w = 1.0, 0.0, 1.0
    for o in range(octaves):
        r = 1.0 - np.abs(noise2(X, Y, scale / (2 ** o), seed + 17 * o, octaves=1) * 2.0 - 1.0)
        r = r * r * w
        w = np.clip(r * 2.0, 0.0, 1.0)
        out += r * amp
        tot += amp
        amp *= gain
    return out / tot


def warp(X, Y, amp, scale, seed):
    """Domain warping: every place is looked up a little way off. The push at (-x, -y) is the opposite of the push at
    (x, y) (an odd noise), so that the warped ground keeps the map's symmetry."""
    def raw(x, y, sd):
        return (T.noise2(x, y, scale, sd, 1) * 2.0 - 1.0) * (2.0 / 3.0) + (T.noise2(x, y, scale / 2.0, sd + 13, 1) * 2.0 - 1.0) / 3.0
    X, Y = np.asarray(X, np.float64), np.asarray(Y, np.float64)
    return X + amp * (raw(X, Y, seed) - raw(-X, -Y, seed)) * R2, Y + amp * (raw(X, Y, seed + 53) - raw(-X, -Y, seed + 53)) * R2


# ---------------------------------------------------------------------------------------------------- the plan

def mir(p):
    """The enemy's twin of a point of the player's side."""
    return (-p[0], -p[1]) + tuple(p[2:])


def uv(x, y):
    return ((x + y) * R2, (y - x) * R2)


def xy(u, v):
    return ((u - v) * R2, (u + v) * R2)


def _oval(x, y, rx, ry, n=44, p=2.5):
    out = []
    for k in range(n):
        a = 2 * math.pi * k / n
        c, s = math.cos(a), math.sin(a)
        r = 1.0 / ((abs(c) / rx) ** p + (abs(s) / ry) ** p) ** (1.0 / p)
        out.append((round(x + r * c, 2), round(y + r * s, 2)))
    return out


# ---- the plateaus: a rounded table 164 x 148 m each (owner, 2026-11-23: "make the platform area twice as big"; it was
# 120 x 108 m, and 112 x 80 before that), squarer in the corners (PP), 132 m deep from the ramp's top to its back rim.
# The castle is 14 x 11 m, a mine 16 x 11, a barracks yard 19 x 18, an archery hall 20 x 14, a farmstead 23 x 19: room
# for the castle, the two mines, the two towers and some thirty buildings with lanes between them.
PA = (-130.0, 130.0, 82.0, 74.0)
PP = 3.0
PLATEAU0 = _oval(*PA, p=PP)
PLATEAU1 = [mir(p) for p in PLATEAU0]
MESAS = [
    dict(name="plateau0", poly=PLATEAU0, z=PLATEAU_Z, top="build", team=0),
    dict(name="plateau1", poly=PLATEAU1, z=PLATEAU_Z, top="build", team=1),
]

# ---- the basin: a lens in the diagonal frame, BU along the ridges (north-east), BV across them
BU, BV, BP = 66.0, 30.0, 2.4


def lens_v(u):
    """How far the basin reaches across (v) at u along it."""
    a = abs(u) / BU
    return BV * (1.0 - a ** BP) ** (1.0 / BP) if a < 1.0 else 0.0


# ---- the ridges: rock RIDGE_W wide along either side of the basin, joined beyond its ends into one spine 2 x RIDGE_W
# wide that runs on to the corner's sea cliffs; the two crests (u, v): 13 m outside the basin's edge, then down the
# middle of the spine
RIDGE_W = 22.0
SHOULDER = 6.0


def _crest():
    pts = []
    for u in (-330.0, -245.0, -200.0, -160.0, -125.0, -100.0, -84.0, -72.0, -60.0, -48.0, -32.0, -16.0, 0.0, 16.0, 32.0, 48.0, 60.0, 72.0, 84.0, 100.0, 125.0, 160.0, 200.0, 245.0, 330.0):
        k = BU - 6.0
        v = lens_v(u) + 13.0 if abs(u) <= k else 2.0 + (lens_v(k) + 11.0) * max(0.0, 1.0 - (abs(u) - k) / 34.0)
        pts.append((u, round(v, 2)))
    return pts


CREST_NW = _crest()
CRESTS = [CREST_NW, [(-u, -v) for (u, v) in CREST_NW]]

# ---- the one way: (name, from (x, y, z), to (x, y, z), half width, surface, how steep the ground beside it may be:
# metres up or down per metre away). The base ramp comes off the plateau's south rim (the castle's door, the plaza, the
# road and the ramp's head in one line) and runs down to the pass's mouth; the pass is level, cut through the crest.
# The base ramp (owner, 2026-11-23: "it should feel like the terrain is naturally going up, not a bare pathway"; it was
# a cut 12 m wide with terraced banks) is a spur of the hillside: 18 m of walking ground (24 m where it meets the
# plateau and the pass), 73 m long for its 10 m (1 in 7.3; eased at both ends); its shoulders fall away 1 in 2 to the
# forest's floor and rise 1 in 2 to the plateau's top (the cliff tapers into them), grass, with the forest up to its
# edges and a worn track up its middle. And it is SMOOTH: the voxel ground can only rise in quarter-block shelves,
# which is what read as a stair, so the spur and its shoulders are covered by a sloping sheet (SM_RealmV3Ramps:
# the ground's own top faces, same texture and tint, laid on the true slope; assets/realmv3_terrain.py build_sheet);
# the plan keeps that slope in G["sheet"] and the voxels just under it.
RAMP_HW = 9.0
PASS_HW = 6.0
PASS_U = -45.0                    # where the pass crosses the north-west ridge, along it (u)
_IN = tuple(round(c, 1) for c in xy(PASS_U, lens_v(PASS_U) - 1.5))
_FOOT = tuple(round(c, 1) for c in xy(PASS_U, lens_v(PASS_U) + RIDGE_W + 4.0))
_HEAD = (PA[0] + 52.0, PA[1] - 58.0)
# ---- the ports: one per side, on the far side of its plateau from the middle of the map (the player's on the west
# coast, the enemy's on the east), Realm v2's set. The coast is straight there (PORT_X); the quay lies at its foot;
# a stone stair comes down to it from the plateau through a cleft in the sea cliff. It joins nothing but the plateau.
PORT_X = PA[0] - PA[2] - 4.0
PORT_Y = PA[1] - 8.0
_STAIR = ((PORT_X + 44.0, PORT_Y + 1.0, PLATEAU_Z), (PORT_X - 2.0, PORT_Y + 1.0, DOCK_Z))
RAMPS = [
    ("base0", _HEAD + (PLATEAU_Z,), _FOOT + (BASIN_Z,), RAMP_HW, DIRT, 0.5),
    ("pass0", _FOOT + (BASIN_Z,), _IN + (BASIN_Z,), PASS_HW, DIRT, 3.0),
    ("port0", _STAIR[0], _STAIR[1], 2.25, STONE, 3.0),
]
RAMPS += [(n[:-1] + "1", mir(a), mir(b), hw, sf, k) for (n, a, b, hw, sf, k) in RAMPS]
PORTS = [dict(team=0, quay=(PORT_X - 13.0, PORT_Y - 20.0, PORT_X, PORT_Y + 20.0), sign=-1.0, dock=((PORT_X - 13.0, PORT_Y + 11.0), -90.0),
              things=[("SM_Port_Warehouse", PORT_X - 6.5, PORT_Y - 12.0, DOCK_Z, -90.0), ("SM_Port_Crane", PORT_X - 9.5, PORT_Y + 17.5, DOCK_Z, -90.0),
                      ("SM_Port_Arch", PORT_X - 0.5, PORT_Y - 5.0, DOCK_Z, -90.0), ("SM_Port_Tower", PORT_X + 16.0, PORT_Y - 25.0, PLATEAU_Z, -90.0)])]
PORTS.append(dict(team=1, quay=(-PORTS[0]["quay"][2], -PORTS[0]["quay"][3], -PORTS[0]["quay"][0], -PORTS[0]["quay"][1]), sign=1.0,
                  dock=((-PORTS[0]["dock"][0][0], -PORTS[0]["dock"][0][1]), 90.0),
                  things=[(m, -x, -y, z, yaw + 180.0) for (m, x, y, z, yaw) in PORTS[0]["things"]]))
SHIP = "SM_Boat"

# ---- the home mines' crags: (x, y, radius, seed, +1 the player's / -1 its twin turned half round)
TORS = dict(mine0=(PA[0] - 68.0, PA[1] + 20.0, 14.0, 5, 1.0), mine0b=(PA[0] + 68.0, PA[1] + 20.0, 14.0, 9, 1.0))
TORS.update({k.replace("0", "1"): (-v[0], -v[1], v[2], v[3], -1.0) for k, v in list(TORS.items())})


def _coast():
    """A rounded square, wobbling (even waves only: the same coast at (x, y) and (-x, -y)); straight at the two ports."""
    pts = []
    for k in range(120):
        a = 2 * math.pi * k / 120
        c, sn = math.cos(a), math.sin(a)
        r = 219.0 / (abs(c) ** 8 + abs(sn) ** 8) ** 0.125
        r *= 0.985 + 0.02 * math.sin(2 * a + 1.0) + 0.016 * math.sin(6 * a + 0.4) + 0.012 * math.sin(10 * a + 2.0) + 0.008 * math.sin(16 * a + 0.9)
        x, y = max(-230.0, min(230.0, r * c)), max(-230.0, min(230.0, r * sn))
        if x < -185.0 and abs(y - PORT_Y) < 37.0:
            x = PORT_X
        if x > 185.0 and abs(y + PORT_Y) < 37.0:
            x = -PORT_X
        pts.append((round(x, 1), round(y, 1)))
    return pts


COAST = _coast()
ISLETS = [(-70.0, -238.0, 4.5), (240.0, -36.0, 4.0), (-240.0, -116.0, 3.5)]
ISLETS += [mir(p) for p in ISLETS]

# ---- buildings: name -> (mesh, x, y, z, yaw, team). Fronts face -Y at yaw 0, -X (west) at yaw -90, +X (east) at yaw 90.
KIND = {"SM_Dock": "Dock", "SM_Castle": "Castle", "SM_MineCliff": "Gold Mine", "SM_WatchTower": "Watch Tower", "SM_PlazaBanner": "Village Banner"}
# Each side starts with its castle, its two home mines (one in a crag at either end of the plateau) and a watch tower
# beside each of them (Realm v2's rule, "a tower beside its home mine", for two home mines; both stand on the level
# ground, either side of the road to the ramp, so the ramp's head lies between them). No farm, no cottages.
_B0 = dict(
    castle0=("SM_Castle", PA[0], PA[1] + 18.0, PLATEAU_Z, 0.0, 0),
    mine0=("SM_MineCliff", PA[0] - 57.0, PA[1] + 20.0, PLATEAU_Z, 90.0, 0),          # Home 1: in the west crag, facing east
    mine0b=("SM_MineCliff", PA[0] + 57.0, PA[1] + 20.0, PLATEAU_Z, -90.0, 0),         # Home 2: in the east crag, facing west
    tower0=("SM_WatchTower", PA[0] - 38.0, PA[1] - 30.0, PLATEAU_Z, 0.0, 0),         # (over the port's stair)
    tower0b=("SM_WatchTower", PA[0] + 46.0, PA[1] - 30.0, PLATEAU_Z, 0.0, 0),        # (over the ramp's head)
)


def _north_end():
    """The basin's northernmost point (x, y): Neutral 1 stands with its back to the rock there."""
    best = (0.0, -1e9)
    for k in range(2000):
        t = 0.5 * math.pi * k / 1999.0
        p = xy(BU * math.cos(t) ** (2.0 / BP), BV * math.sin(t) ** (2.0 / BP))
        if p[1] > best[1]:
            best = p
    return best


_NE = _north_end()
_N1 = (round(_NE[0] * 2.0) / 2.0, round((_NE[1] - 5.0) * 2.0) / 2.0)
BUILD = dict(_B0)
for _k, (_m, _x, _y, _z, _yaw, _t) in _B0.items():
    BUILD[_k.replace("0", "1")] = (_m, -_x, -_y, _z, ((_yaw + 360.0) % 360.0) - 180.0, 1)
BUILD["mine_n1"] = ("SM_MineCliff", _N1[0], _N1[1], BASIN_Z, 0.0, "Neutral")         # Neutral 1: the basin's north-east end
BUILD["mine_n2"] = ("SM_MineCliff", -_N1[0], -_N1[1], BASIN_Z, 180.0, "Neutral")     # Neutral 2: its south-west end
HILLS = dict(mine0=(6.0, (5.0, 8.0), 5), mine0b=(6.0, (5.0, 8.0), 9))
HILLS.update({k.replace("0", "1"): v for k, v in list(HILLS.items())})
NEUTRAL_MINES = ("mine_n1", "mine_n2")
HOME_MINES = ("mine0", "mine0b", "mine1", "mine1b")


def _bounds(mesh):
    return meta(mesh).get("bounds", [[-5, -5, 0], [5, 5, 5]])


def _front(mesh, x, y, yaw, out=0.0, along=0.0):
    dx, dy = rot(along, _bounds(mesh)[0][1] - out, yaw)
    return (round(x + dx, 3), round(y + dy, 3))


def footprint(key, pad=0.0):
    mesh, x, y, z, yaw = BUILD[key][:5]
    (x0, y0, _), (x1, y1, _) = _bounds(mesh)
    cs = [rot(a, b, yaw) for a in (x0, x1) for b in (y0, y1)]
    return (x + min(c[0] for c in cs) - pad, y + min(c[1] for c in cs) - pad, x + max(c[0] for c in cs) + pad, y + max(c[1] for c in cs) + pad, z)


def front(key, out=0.0, along=0.0):
    """A point `out` metres in front of a building's front edge (its own -Y), `along` metres to its right."""
    mesh, x, y, z, yaw = BUILD[key][:5]
    return _front(mesh, x, y, yaw, out, along)


def behind(key, X, Y, side=3.0, depth=7.0):
    """The cells behind a building (a mine: the rock it is set in)."""
    mesh, x, y, z, yaw = BUILD[key][:5]
    (x0, y0, _), (x1, y1, _) = _bounds(mesh)
    a = math.radians(-yaw)
    lx = (X - x) * math.cos(a) - (Y - y) * math.sin(a)
    ly = (X - x) * math.sin(a) + (Y - y) * math.cos(a)
    return (lx > x0 - side) & (lx < x1 + side) & (ly > y1 - 1.0) & (ly < y1 + depth)


GATE = {}
for _k in BUILD:
    GATE[_k] = front(_k, 1.5 if _k.startswith("mine") else (0.2 if _k.startswith("castle") else 0.3))
G_ = GATE

PLAZA0 = (PA[0], PA[1] + 4.0)
PLAZA1 = mir(PLAZA0)
PLAZA = (PLAZA0, PLAZA1)
SPAWN = (PA[0], PA[1] + 8.0, -90.0)     # x, y, facing (degrees from +X): in front of the player's castle, facing the ramp
START1 = (-PA[0], -PA[1] - 8.0, 90.0)
RALLY0 = (PA[0] + 22.0, PA[1] - 22.0)            # where each side's troops gather: by the road to the ramp
RALLY1 = mir(RALLY0)
# the contested ground: tagged points of the level (terrain only: nothing captures them)
ZONES = dict(Basin=(0.0, 0.0), PassNW=((_FOOT[0] + _IN[0]) / 2.0, (_FOOT[1] + _IN[1]) / 2.0), PassSE=(-(_FOOT[0] + _IN[0]) / 2.0, -(_FOOT[1] + _IN[1]) / 2.0))
# the level ground to build on in the basin, either side of the lane: (name, x, y, rx, ry)
PADS = [("basin_north", -2.0, 25.0, 22.0, 10.0), ("basin_south", 2.0, -25.0, 22.0, 10.0)]


def _roads():
    """The roads: (points [(x, y)], half width, surface). Cobbles on the plateaus (castle, plaza, mines, towers, the
    ramp's head); a dirt road down the ramps, through the passes and across the basin, with a track to each neutral
    mine."""
    P0 = PLAZA0
    mine = [
        ([G_["castle0"], P0], 1.8, COBBLE),
        ([P0, G_["mine0"]], 1.4, COBBLE),
        ([P0, G_["mine0b"]], 1.4, COBBLE),
        ([P0, (PA[0] + 26.0, PA[1] - 28.0), (_HEAD[0] - 1.0, _HEAD[1] + 6.0)], 2.0, COBBLE),         # to the ramp's head
        ([P0, (PA[0] - 20.0, PA[1] - 2.0), _STAIR[0][:2]], 1.4, COBBLE),                             # to the port's stair
        ([(PA[0] - 20.0, PA[1] - 2.0), (PA[0] - 30.0, PA[1] - 24.0), (PA[0] - 38.0, PA[1] - 39.5), G_["tower0"]], 1.2, COBBLE),
        ([(PA[0] + 26.0, PA[1] - 28.0), (PA[0] + 38.0, PA[1] - 40.0), G_["tower0b"]], 1.2, COBBLE),
        ([_FOOT, _IN, (0.0, 0.0)], 1.6, DIRT),
        ([(_IN[0] * 0.3, _IN[1] * 0.3), (-23.0, -24.0), G_["mine_n2"]], 1.2, DIRT),
    ]
    return mine + [([mir(p) for p in pts], w, sf) for (pts, w, sf) in mine]


PATHS = _roads()
APRONS = [G_[k] for k in G_]
PLAZAS = [PLAZA0, PLAZA1]

# The forest: one tree in every FOREST_GRID x FOREST_GRID metres of the wild ground (jittered), FOREST_KEEP of them
# kept; the crowns of the small tree (SM_Tree2_D) are 4.4 to 5 m across, so they close over the ground. (3.75 m was
# measured too: 12 % more trees, the view over the forest a millisecond of GPU dearer than Realm v2's dearest.)
# Faces each, near / far: A 101k / 9k, B 94k / 8k, C 37k / 3k, D 10k / 1k.
FOREST_GRID = 4.0
FOREST_KEEP = 0.94
RIDGE_KEEP = 0.4                 # on the ridges' grassy ledges
TREE_GAP = {"A": 12.0, "B": 11.0, "C": 8.0, "D": 4.8}
TREE_CLEAR = {"A": 3.6, "B": 3.4, "C": 2.2, "D": 1.3}
BUILD_MARGIN = 1.5


# ---------------------------------------------------------------------------------------------------- the ground

def grid():
    a = -HALF + (np.arange(N) + 0.5) * CELL
    return np.meshgrid(a, a, indexing="ij")


def box(x0, y0, x1, y1, pad=0.0):
    i0, i1 = max(0, int((x0 - pad + HALF) / CELL)), min(N, int((x1 + pad + HALF) / CELL) + 1)
    j0, j1 = max(0, int((y0 - pad + HALF) / CELL)), min(N, int((y1 + pad + HALF) / CELL) + 1)
    return (slice(i0, i1), slice(j0, j1))


def poly_box(poly, pad):
    return box(min(p[0] for p in poly), min(p[1] for p in poly), max(p[0] for p in poly), max(p[1] for p in poly), pad)


def sdist(X, Y, poly):
    """Signed distance to a polygon: > 0 inside."""
    d = dist_polyline(X, Y, list(poly) + [poly[0]])
    return np.where(in_poly(X, Y, poly), d, -d)


def min_near(h, k):
    out = h.copy()
    for ax in (0, 1):
        acc = out.copy()
        for sh in range(1, k + 1):
            acc = np.minimum(acc, np.minimum(np.roll(out, sh, axis=ax), np.roll(out, -sh, axis=ax)))
        out = acc
    return out


def max_near(h, k):
    return -min_near(-h, k)


def dilate(mask, k):
    out = mask.copy()
    for ax in (0, 1):
        acc = out.copy()
        for sh in range(1, k + 1):
            acc |= np.roll(out, sh, axis=ax) | np.roll(out, -sh, axis=ax)
        out = acc
    return out


def lens(U, V):
    """1 on the basin's edge, less inside it."""
    return ((np.abs(U) / BU) ** BP + (np.abs(V) / BV) ** BP) ** (1.0 / BP)


def ridges(X, Y, U, V, eb):
    """The band of rock, metres above the sea (0 outside it and in the basin). A base that rises quickly from the
    foot; the crests, tents along their lines, higher towards the corners; spurs from a ridged sum stretched along the
    band; cliffs of one to six metres (crags)."""
    uw, vw = warp(U, V, 7.0, 60.0, 700)
    uw, vw = warp(uw, vw, 2.5, 18.0, 720)
    a = np.clip(np.abs(uw) / BU, 0.0, 1.0)
    wb = RIDGE_W + BV * (1.0 - a ** BP) ** (1.0 / BP)
    d_in = np.minimum(wb - np.abs(vw), (eb - 1.0) * 40.0)
    foot = np.clip(d_in / 4.5, 0.0, 1.0) ** 0.7
    # (the crest's height along its line: peaks and saddles every 30 to 60 m, higher towards the corners)
    peak = np.clip((noise2(X, Y, 30.0, 731, 2) - 0.22) / 0.56, 0.0, 1.0) ** 1.25
    # (owner, 2026-11-23: "make the rock walls less tall, they are blocking my view": they were 25 to 50 m over the
    # basin, 66 m at the corners; now 14 to 22 m and under 30)
    hc = 5.0 + 8.0 * peak + 4.0 * np.clip((np.abs(U) - 70.0) / 100.0, 0.0, 1.0)
    dcr = np.full(X.shape, 1e9)
    for crest in CRESTS:
        dcr = np.minimum(dcr, dist_polyline(uw, vw, crest))
    env = hc * np.clip(1.0 - dcr / 24.0, 0.0, 1.0) ** 1.05               # (a tent: a knife's edge along the crest)
    rd = ridged(uw / 1.8, vw, 34.0, 740)
    rd2 = ridged(X, Y, 13.0, 750, 3)
    # (lower still by each pass, a saddle: the overview pulled right in stands 10 m up and 22 m back from what it looks
    # at, and in the pass that was inside the rock)
    dp = np.full(X.shape, 1e9)
    for (name, a, b, _hw, _sf, _k) in RAMPS:
        if name.startswith("pass"):
            dp = np.minimum(dp, seg_dist(X, Y, a, b)[0])
    sad = np.clip((dp - 10.0) / 38.0, 0.0, 1.0)
    sad = 0.42 + 0.58 * sad * sad * (3.0 - 2.0 * sad)
    h = (SHOULDER * foot + env * (0.62 + 0.5 * rd) * foot) * sad + (3.0 * (rd2 - 0.35) + 2.0 * fbm(X, Y, 24.0, 760, 3)) * foot
    h = h + 3.5 * (rd2 - 0.3) * np.clip(1.0 - dcr / 10.0, 0.0, 1.0) * foot      # teeth on the crest
    # Broken rock, not banded rock. The faces were cut into shelves of one to six metres at the same levels all along
    # (contour lines: they read as terraces). Now the rock stands in columns: blocks 2 m and 4.5 m across, each pushed
    # up or down by a metre or so, and cut into steps of half a metre to two metres that start at a different height
    # in every 3 m block, so no ledge runs on along a face.
    h = h + ((shash(X, Y, 2.0, 796) - 0.5) * 2.4 + (shash(X, Y, 4.5, 797, shear=0.37) - 0.5) * 3.0) * foot
    crag = noise2(X, Y, 30.0, 790, octaves=2)
    q = np.where(crag > 0.66, 2.0, np.where(crag > 0.45, 1.0, 0.5))
    h = np.floor(h / q + shash(X, Y, 3.0, 795)) * q
    h = np.where(d_in > 0, np.maximum(h, 3.0), 0.0)
    return np.where(h >= 1.5, BASIN_Z + np.round(h * 2.0) / 2.0, 0.0)


def mesa_field(X, Y, m, n1, n2, calm):
    """A flat-topped hill: (heights, top mask). Its sides are rock: steps of two metres, a metre or so deep each."""
    d = sdist(X, Y, m["poly"]) + (n2 - 0.5) * 3.0 * calm
    z = m["z"]
    wf = np.maximum(2.5, 0.5 * z) + (n1 - 0.5) * 2.0
    prof = np.clip(1.0 + d / wf, 0.0, 1.0)
    h = np.where(d >= 0, z, np.minimum(z, np.ceil(prof * z / 2.0) * 2.0))
    return np.where(prof > 0, h, 0.0), d >= 0


def ramp_fields(X, Y, h, mtn):
    """Shapes the ways into the ground: -> (h, floor mask, surface (-1: none), the passes' and stairs' cut sides, the
    base ramps' shoulders).
    A base ramp is a spur: its height runs evenly from the plateau to the pass (eased at both ends), in quarter-block
    shelves whose lines wander with a noise (never straight across: not a stair); the ground beside its walking width
    may differ from it by 1 m in every 2 m away (steeper further out), so its shoulders slope, the plateau's cliff
    tapers into them and the forest's floor rises to them. A pass and a port's stair are cuts with stepped rock sides."""
    floor = np.zeros(X.shape, bool)
    sides = np.zeros(X.shape, bool)
    shoulder = np.zeros(X.shape, bool)
    sheet = np.full(X.shape, np.nan)
    surf = np.full(X.shape, -1, np.int8)
    rag = (noise2(X, Y, 2.2, 5) - 0.5) * 0.7
    for (_name, a, b, hw, sf, k) in RAMPS:
        s = box(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]), hw + 40.0)
        e, t = seg_dist(X[s], Y[s], a, b)
        if _name.startswith("base"):
            ts = 0.5 * t + 0.5 * t * t * (3.0 - 2.0 * t)
            zs = a[2] + ts * (b[2] - a[2])
            hwv = hw + 3.0 * np.abs(2.0 * t - 1.0) ** 3                   # (wider where it meets the plateau and the pass)
            d = np.clip(e - hwv, 0.0, None)
            lim = k * d + 1.5 * np.clip(d - 12.0, 0.0, None)
            h0 = h[s]
            rock = mtn[s]                                                 # (the ridge by the ramp's foot stays rock, in steps)
            cut = np.clip(h0, zs - 3.0 * np.ceil(d), zs + 3.0 * np.ceil(d))
            bound = np.where(rock, cut, np.clip(h0, zs - lim, zs + lim))
            fl = e <= hwv
            mask = fl | ((bound != h0) & ~rock)
            top = np.where(fl, zs, bound)                                 # the true slope
            h[s] = np.where(mask, np.floor((top - 0.03) / 0.25) * 0.25, bound)
            sheet[s] = np.where(mask, top, sheet[s])
            shoulder[s] |= mask & ~fl
            sides[s] |= rock & ~fl & (cut != h0)
            floor[s] |= fl
            # a worn track up its middle, broken by grass
            worn = fl & (e < 1.5 + rag[s] * 1.4) & (noise2(X[s], Y[s], 7.0, 909) > 0.34)
            surf[s] = np.where(worn, sf, surf[s])
            continue
        zr = a[2] + np.round(t * (b[2] - a[2]) / 0.25) * 0.25
        side = np.ceil(np.clip(e - hw, 0.0, None)) * k                   # terraces beside the floor
        # (a pass begins square at the ramp's foot: its floor's round end would cut a step across the ramp's last metres)
        act = (t > 0.0) if _name.startswith("pass") else np.ones(e.shape, bool)
        hh = np.where(act, np.clip(h[s], zr - side, zr + side), h[s])
        fl = (e <= hw) & act
        sides[s] |= ~fl & (hh != h[s])
        hh = np.where(fl, zr, hh)
        h[s] = hh
        floor[s] |= fl
        surf[s] = np.where(fl & ((e < 2.0 + rag[s]) | (sf == STONE)), sf, surf[s])
    # (where a pass or a stair was cut afterwards, there is no sheet: the voxels are the ground again)
    sheet = np.where(np.isfinite(sheet) & (h != np.floor((sheet - 0.03) / 0.25) * 0.25), np.nan, sheet)
    shoulder &= np.isfinite(sheet)
    return h, floor, surf, sides & ~floor, shoulder & ~floor, sheet


def path_fields(X, Y):
    """For every cell: the surface of the road it lies on (-1: none), and how far it is from the nearest road's edge."""
    surf = np.full(X.shape, -1, np.int8)
    best = np.full(X.shape, 1e9, np.float32)
    rag = (noise2(X, Y, 2.2, 5) - 0.5) * 0.7
    for pts, w, sf in PATHS:
        for a, b in zip(pts[:-1], pts[1:]):
            s = box(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]), w + 9.0)
            d, _t = seg_dist(X[s], Y[s], a, b)
            take = ((d + rag[s]) < w) & (d - w < best[s])
            surf[s] = np.where(take, sf, surf[s])
            best[s] = np.minimum(best[s], d - w)
    for p in PLAZAS:
        s = box(p[0], p[1], p[0], p[1], 6.0)
        plaza = (np.hypot(X[s] - p[0], Y[s] - p[1]) + rag[s]) < 4.2
        surf[s] = np.where(plaza, COBBLE, surf[s])
        best[s] = np.minimum(best[s], np.hypot(X[s] - p[0], Y[s] - p[1]) - 4.2)
    return surf, best


def heights():
    X, Y = grid()
    U, V = (X + Y) * R2, (Y - X) * R2
    n1, n2 = noise2(X, Y, 14.0, 3), noise2(X, Y, 7.0, 17)
    R = {}

    # ---- the forest's floor: a slow roll of 1 to 4.5 m in half-block shelves (nobody walks on it)
    roll = np.clip((noise2(X, Y, 64.0, 901, octaves=2) - 0.3) / 0.45, 0.0, 1.0) ** 1.2
    h = np.round((1.0 + 3.5 * roll + (noise2(X, Y, 5.0, 903) - 0.5) * 0.3) / 0.5) * 0.5

    # ---- the ridges and the basin between them
    eb = lens(U, V) + (n2 - 0.5) * 0.06
    mt = ridges(X, Y, U, V, eb)
    h = np.where(mt > 0, mt, h)
    basin = eb < 1.0
    h = np.where(basin, BASIN_Z, h)
    R["mountain"] = (mt > 0) & ~basin

    # ---- the plateaus (their edge is the plan's at a mine and at the ramp)
    calm = np.ones(X.shape)
    for k in HOME_MINES:
        calm *= np.clip((np.hypot(X - BUILD[k][1], Y - BUILD[k][2]) - 12.0) / 10.0, 0.0, 1.0)
    for (_n, a, bb, hw, _s, _k) in RAMPS:
        calm *= np.clip((seg_dist(X, Y, a, bb)[0] - hw - 2.0) / 8.0, 0.0, 1.0)
    tops = {}
    inner = np.zeros(X.shape, bool)
    flank = np.zeros(X.shape, bool)
    for m in MESAS:
        s = poly_box(m["poly"], 16.0)
        mh, top = mesa_field(X[s], Y[s], m, n1[s], n2[s], calm[s])
        hh = np.maximum(h[s], mh)
        flank[s] |= (mh > 0) & ~top
        t = np.zeros(X.shape, bool)
        t[s] = top & (hh == m["z"])
        tops[m["name"]] = t
        inner[s] |= sdist(X[s], Y[s], m["poly"]) > 2.0
        h[s] = hh
    R["flank"] = flank

    # ---- the home mines' crags: rock that rises from the plateau's rim in shelves, the mine in its face
    tor = np.zeros(X.shape, bool)
    for key, (tx, ty, tr, seed, sg) in TORS.items():
        s = box(tx - tr, ty - tr, tx + tr, ty + tr, 14.0)
        x, y = X[s], Y[s]
        base = BUILD[key][3]
        ang = np.arctan2((y - ty) * sg, (x - tx) * sg)
        dt = np.hypot(x - tx, y - ty) - (n2[s] - 0.5) * 3.0 + 1.8 * np.sin(ang * 2 + 0.7 + seed) + 1.2 * np.sin(ang * 3 + 2.1) + 0.8 * np.sin(ang * 5 + 4.0)
        m = dt < tr
        up = np.clip(tr - dt, 0.0, None)
        # (shelves of one, two and three metres, by the block: a crag, not a stair)
        tq = 1.0 + np.floor(shash(x, y, 2.5, 430 + seed) * 2.6)
        th = up / 1.5 + np.clip(up - 8.0, 0.0, None) * 0.9
        hh = np.where(m, np.maximum(h[s], base + np.clip(np.ceil(th / tq) * tq, 1.0, 9.0)), h[s])
        crest, reach, hseed = HILLS[key]
        mh = minehill.hill(x, y, BUILD[key][1], BUILD[key][2], BUILD[key][4], crest, reach, hseed, noise2(x, y, 7.0, 400 + hseed))
        hh = np.where(mh > 0, np.maximum(hh, base + mh), hh)
        h[s] = hh
        tor[s] |= m | (mh > 0)
    R["tor"] = tor

    # ---- the ramps, the passes and the ports' stairs
    h, rfloor, rsurf, rsides, rshoulder, sheet = ramp_fields(X, Y, h, R["mountain"])
    R["rside"] = rsides
    R["shoulder"] = rshoulder
    R["flank"] = flank = flank & ~rshoulder                                 # (the cliff tapers into a ramp's shoulder: grass, not rock)

    # ---- the island's coast: where the land ends (dc: metres inside it), the islets, the ports' quays
    crag = (noise2(X, Y, 6.0, 11) - 0.5) * 3.0 + (noise2(X, Y, 24.0, 12) - 0.5) * 6.0
    for pt in PORTS:
        q = pt["quay"]
        crag = crag * np.clip((np.hypot(X - (q[0] + q[2]) / 2, Y - (q[1] + q[3]) / 2) - 26.0) / 12.0, 0.0, 1.0)
    dc = sdist(X, Y, COAST) + crag
    isle = np.full(X.shape, -1e9)
    for (ix, iy, r) in ISLETS:
        isle = np.maximum(isle, softground.islet(X, Y, ix, iy, r, crag * 0.25))
    dc = np.maximum(dc, isle)
    h = np.where(isle > -2.5, 1.0, h)
    quay = np.zeros(X.shape, bool)
    for pt in PORTS:
        quay |= in_rect(X, Y, pt["quay"])
    dc = np.where(quay | rfloor, np.maximum(dc, 3.0), dc)
    h = np.where(quay & ~rfloor, DOCK_Z, h)
    R["rside"] = rsides = rsides & ~quay

    # ---- the rock the mines are set in, the buildings' pads
    for k in BUILD:
        if BUILD[k][0] == "SM_MineCliff":
            h = np.where(behind(k, X, Y), np.maximum(h, BUILD[k][3] + 5.0), h)
    pads = [footprint(k, 1.0) for k in BUILD]
    for k, (x0, y0, x1, y1, z) in zip(BUILD, pads):
        if BUILD[k][0] == "SM_MineCliff":
            h, _bay = minehill.embed(X, Y, h, BUILD[k][1], BUILD[k][2], BUILD[k][3], BUILD[k][4])
        else:
            h = np.where(in_rect(X, Y, (x0, y0, x1, y1)), z, h)

    # ---- the sea: ragged rock ledges on the cliff's edge, rocks standing in the water at its foot, the bed
    land = dc > 0
    blk = shash(X, Y, 1.5, 7, shear=0.4)
    blk2 = shash(X, Y, 0.75, 9)
    keep_c = rfloor | dilate(quay, 8)
    cut1 = land & (dc < 1.3) & (blk > 0.62) & ~keep_c
    cut2 = land & (dc < 2.6) & (dc >= 1.3) & (blk > 0.8) & ~keep_c
    h = np.where(cut1, h - 1.0 - np.round(blk2 * 3.0) * 0.5, h)
    h = np.where(cut2, h - 0.5 - np.round(blk2) * 0.5, h)
    h = np.where(~land, SEABED, h)
    rocks = ~land & (dc > -3.2) & (blk > 0.52) & ~dilate(quay, 10)
    h = np.where(rocks, SEA - 0.5 + np.round(blk2 * 5.0) * 0.5 * (1.0 + dc / 3.2), h)
    sea = ~land
    R["cut"] = cut1 | cut2
    deck = np.zeros(X.shape, bool)
    for pt in PORTS:                                                        # the piers' planks (SM_Dock: 3 m wide, 9 m long, a head 8 x 3.5 m)
        (dx, dy), _yaw = pt["dock"]
        ly = (X - dx) * -pt["sign"]
        lx = Y - dy
        deck |= ((np.abs(lx) <= 1.5) & (ly <= 0.25) & (ly >= -9.0)) | ((np.abs(lx) <= 4.0) & (ly <= -9.0) & (ly >= -12.5))

    # ---- the same ground at (x, y) and (-x, -y), to the last cell
    asym = int((h != h[::-1, ::-1]).sum())
    h = np.where(V > 0, h, h[::-1, ::-1])
    sheet = np.where(V > 0, sheet, sheet[::-1, ::-1])
    R["asym_cells"] = asym

    # ---- what is what
    for m in MESAS:
        tops[m["name"]] &= (h == m["z"])
    floor_b = basin & (h == BASIN_Z)
    roads, road_d = path_fields(X, Y)
    path = (roads >= 0) | rfloor
    steep = (h - min_near(h, 2)) >= 0.75
    # where people go: the plateaus (with their crags), the ramps, the passes, the basin (with the mines in its ends)
    region = inner | basin | rfloor | quay
    for m in MESAS:
        region |= tops[m["name"]]
    for k in BUILD:
        region |= in_rect(X, Y, footprint(k, 0.5)[:4])
    region &= ~R["shoulder"] & ~(R["rside"] & ~inner)                       # (a ramp's shoulder is not ground to walk on)
    region &= land
    region |= deck
    wild = (land & ~region) | (tor & ~rfloor) | sea
    open_ = (floor_b | tops["plateau0"] | tops["plateau1"]) & ~wild

    # ---- where nobody may go (the hidden walls stand on its edge): everything outside that region (the forest, the
    # ridges, the cliffs, the sea) and the rim of every drop inside it. Not the roads or the ramps.
    rimdrop = (h - min_near(h, 4) > 1.5) & region & ~path & ~tor & ~quay & ~deck
    hazard = (~region) | rimdrop
    hazard &= ~rfloor
    R.update(tops=tops, n1=n1, n2=n2, bank=np.zeros(X.shape, bool), mound=np.zeros(X.shape, bool), basin=floor_b)
    none = np.zeros(X.shape, bool)
    return dict(X=X, Y=Y, U=U, V=V, h=h, land=land, dc=dc, sea=sea & ~rocks, rocks=rocks, deck=deck, quay=quay, wet=none, wz=np.full(X.shape, np.nan, np.float32),
                path=path, roads=roads, road_d=road_d, rfloor=rfloor, rsurf=rsurf, pads=pads, hazard=hazard, corridor=none, R=R, wild=wild, open=open_,
                region=region, rim=rimdrop, steep=steep, sheet=sheet, top=np.where(np.isfinite(sheet), sheet + 0.03, h))


def surface(G):
    X, Y, h, R = G["X"], G["Y"], G["h"], G["R"]
    s = np.zeros(X.shape, np.int8)
    hs = shash(X, Y, 0.5, 13)
    drop = h - min_near(h, 2)
    rise = max_near(h, 2) - h
    mtn, wild = R["mountain"], G["wild"]
    # the forest's floor: grass, earth and moss in patches
    forest = wild & ~mtn & ~R["flank"] & ~R["tor"] & G["land"]
    s[forest & (noise2(X, Y, 5.0, 41) > 0.7)] = DIRT
    s[forest & (noise2(X, Y, 3.0, 61) > 0.78)] = MOSSY
    # the ridges: rock; grass only on the low ledges' inner ground
    ledge = mtn & (drop < 0.75) & (h < BASIN_Z + 8.0 + (noise2(X, Y, 22.0, 97) - 0.5) * 8.0) & (noise2(X, Y, 9.0, 98) > 0.35)
    rock = mtn & ~ledge
    high = np.clip((h - BASIN_Z - 5.0) / 14.0, 0.0, 1.0)
    s[rock] = np.where(hs[rock] > 0.55 - 0.3 * high[rock], STONE, MOSSY)
    # the plateaus' cliffs, the crags, the ramps' banks where they are cut into rock
    cliff = (R["flank"] | R["tor"]) & wild
    s[cliff] = np.where(hs[cliff] > 0.45, STONE, MOSSY)
    s[R["tor"] & wild & (drop < 0.5) & (rise < 0.5) & (hs > 0.55)] = GRASS
    edge = G["region"] & ~wild & (drop >= 2.0) & (hs > 0.5)              # the rim of a cliff: moss among the grass
    s[edge] = MOSSY
    # where people go: grass, a little earth and moss
    tame = G["region"] & ~wild
    s[tame & (noise2(X, Y, 5.0, 43) > 0.84)] = DIRT
    s[tame & (noise2(X, Y, 3.0, 63) > 0.86)] = MOSSY
    rd = G["roads"] >= 0
    s[rd & ~wild] = G["roads"][rd & ~wild]
    rs = G["rsurf"] >= 0
    s[rs] = G["rsurf"][rs]
    side = R["rside"] & (mtn | R["flank"] | (G["region"] & ~G["rfloor"]) | ~G["region"])
    s[side] = np.where(hs[side] > 0.5, STONE, MOSSY)
    s[G["quay"]] = np.where(hs[G["quay"]] > 0.3, COBBLE, STONE)
    s[rs] = G["rsurf"][rs]
    cut = R["cut"]
    s[cut] = np.where(hs[cut] > 0.5, STONE, MOSSY)
    s[G["rocks"]] = np.where(hs[G["rocks"]] > 0.6, MOSSY, STONE)
    s[G["sea"]] = GRAVEL
    s[(rise >= 2.0) & (s == GRASS) & wild & (hs > 0.5)] = MOSSY          # the foot of a cliff
    return s


def ground(h, x, y):
    i = int(np.clip((x + HALF) / CELL, 0, N - 1))
    j = int(np.clip((y + HALF) / CELL, 0, N - 1))
    return float(h[i, j])


# ---------------------------------------------------------------------------------------------------- things

class Solids(list):
    """What stands where, (x, y, r): a list that can also be asked quickly."""
    B = 8.0

    def __init__(self):
        super().__init__()
        self.cells = {}

    def append(self, it):
        super().append(it)
        self.cells.setdefault((int(it[0] // self.B), int(it[1] // self.B)), []).append(it)

    def hits(self, x, y, r, reach=4.0):
        k = int((r + reach) // self.B) + 1
        ci, cj = int(x // self.B), int(y // self.B)
        for i in range(ci - k, ci + k + 1):
            for j in range(cj - k, cj + k + 1):
                for (a, b, q) in self.cells.get((i, j), ()):
                    if math.hypot(x - a, y - b) < r + q:
                        return True
        return False


class Scene:
    def __init__(self, G, s):
        self.G, self.h, self.s = G, G["top"], s
        self.items = []
        self.missing = set()
        self.solid = Solids()
        self.trees = []                    # (x, y, kind, scale)

    def add(self, mesh, x, y, yaw=0.0, scale=1.0, z=None, dz=0.0, group="village", tags=None, r=None, team=None):
        if not os.path.exists(os.path.join(MESHES, mesh + ".json")):
            self.missing.add(mesh)
        zz = ground(self.h, x, y) if z is None else z
        it = dict(mesh=mesh, pos=[round(x, 3), round(y, 3), round(zz + dz, 3)], yaw=round(yaw, 2), scale=round(scale, 3), group=group)
        if tags:
            it["tags"] = list(tags)
        if team is not None:
            it["team"] = team
        self.items.append(it)
        if r:
            self.solid.append((x, y, r))
        return it

    def both(self, mesh, x, y, yaw=0.0, scale=1.0, z=None, dz=0.0, group="village", r=None):
        """A thing of the player's half of the map and its twin in the enemy's."""
        self.add(mesh, x, y, yaw, scale, z, dz, group, r=r)
        self.add(mesh, -x, -y, yaw + 180.0, scale, z, dz, group, r=r)

    def building(self, mesh, x, y, z, yaw, team, group="buildings", tags=None):
        self.add(mesh, x, y, yaw, z=z, group=group, team=team, tags=tags)
        for pr in meta(mesh).get("props", []):
            px, py = rot(pr["pos"][0], pr["pos"][1], yaw)
            self.add(pr["mesh"], x + px, y + py, yaw + float(pr.get("yaw", 0.0)), float(pr.get("scale", 1.0)), z=z + pr["pos"][2], group="props")

    def tree(self, kind, x, y, yaw=0.0, scale=1.0, group="forest", z=None):
        r = {"A": 1.6, "B": 1.5, "C": 1.1, "D": 0.7}[kind] * scale
        self.add("SM_Tree2_%s_Trunk" % kind, x, y, yaw, scale, z=z, dz=-0.15, group=group, r=r)
        self.add("SM_Tree2_%s_Leaves" % kind, x, y, yaw, scale, z=z, dz=-0.15, group=group)
        self.trees.append((x, y, kind, scale))

    def trees2(self, kind, x, y, yaw, scale, group, z=None):
        self.tree(kind, x, y, yaw, scale, group, z)
        self.tree(kind, -x, -y, yaw + 180.0, scale, group, z)


def rect_gap(x, y, f):
    return math.hypot(max(f[0] - x, 0.0, x - f[2]), max(f[1] - y, 0.0, y - f[3]))


_FOOT_ = {k: footprint(k) for k in BUILD}


def tree_blocked(x, y, kind, scale=1.0, margin=BUILD_MARGIN):
    """Would this tree stand in or right against a building (its footprint and its gate)? The rule the game's
    AVLForest::ClearTrees applies when a building is put down, applied to the plan."""
    reach = TREE_CLEAR[kind] * scale + margin
    for k in BUILD:
        if rect_gap(x, y, _FOOT_[k]) < reach:
            return k
    for k, (gx, gy) in GATE.items():
        if math.hypot(x - gx, y - gy) < reach + 3.0:
            return k + " gate"
    return None


def forest_spots(G, s):
    """The forest and the ridges' few trees: [(x, y, z, kind, scale)] for the north-west half of the map (v > 0; the
    other half is its twin). One candidate in every FOREST_GRID metres, jittered; kept where the ground is wild land,
    not rock, level enough for a trunk, and far enough from where people go that the crown does not hang over it
    (2.5 m for the small tree, 5 m for the middle one, 8 m for the giants)."""
    X, Y, h, R = G["X"], G["Y"], G["h"], G["R"]
    mtn = R["mountain"]
    wood = G["wild"] & G["land"] & ~R["flank"] & ~R["tor"] & ~R["cut"] & (G["dc"] > 2.6) & ~G["path"] & ~dilate(G["quay"], 12)
    wood &= np.where(mtn, s == GRASS, np.isin(s, (GRASS, DIRT, MOSSY)))
    near = [~dilate(G["region"], k) for k in (10, 20, 32)]
    k = int(round(FOREST_GRID / CELL))
    nb = N // k
    I, J = np.meshgrid(np.arange(nb), np.arange(nb), indexing="ij")
    out = []
    for attempt in range(3):                                                # (a candidate on a shelf's edge: try again nearby)
        ci = (I * k + 1 + (hash2(I, J, 301 + 7 * attempt) * (k - 2)).astype(int)).ravel()
        cj = (J * k + 1 + (hash2(I, J, 303 + 7 * attempt) * (k - 2)).astype(int)).ravel()
        cell_id = (I * nb + J).ravel()
        keep = wood[ci, cj] & near[0][ci, cj] & (G["V"][ci, cj] > 0.3)
        ci, cj, cell_id = ci[keep], cj[keep], cell_id[keep]
        r = int(round(0.5 / CELL))
        lo = np.full(len(ci), 1e9)
        hi = np.full(len(ci), -1e9)
        for di in range(-r, r + 1):
            for dj in range(-r, r + 1):
                v = h[np.clip(ci + di, 0, N - 1), np.clip(cj + dj, 0, N - 1)]
                lo, hi = np.minimum(lo, v), np.maximum(hi, v)
        flat = (hi - lo) <= 0.51
        out.append((ci[flat], cj[flat], lo[flat], cell_id[flat]))
    seen = set()
    spots = []
    for (ci, cj, lo, cid) in out:
        x, y = X[ci, cj], Y[ci, cj]
        m = mtn[ci, cj]
        r0 = hash2(ci, cj, 305)
        r1 = hash2(ci, cj, 307)
        r2 = hash2(ci, cj, 309)
        n5, n8 = near[1][ci, cj], near[2][ci, cj]
        for q in range(len(ci)):
            if int(cid[q]) in seen:
                continue
            if r0[q] > (RIDGE_KEEP if m[q] else FOREST_KEEP):
                seen.add(int(cid[q]))
                continue
            kind = "D"
            if not m[q]:
                if r1[q] < 0.008 and n8[q]:
                    kind = "A" if r1[q] < 0.004 else "B"
                elif r1[q] < 0.07 and n5[q]:
                    kind = "C"
            seen.add(int(cid[q]))
            spots.append((float(x[q]), float(y[q]), float(max(lo[q], G["top"][ci[q], cj[q]] - 0.3)), kind, float(0.85 + r2[q] * 0.35)))
    return spots


def things(G, s):
    X, Y, h, R = G["X"], G["Y"], G["h"], G["R"]
    sc = Scene(G, s)
    rng = np.random.default_rng(20261123)
    wild = G["wild"]
    open_ = G["open"]

    # ---- the buildings (with what their sidecars ask to have placed with them), the banners
    for key, (mesh, x, y, z, yaw, team) in BUILD.items():
        sc.building(mesh, x, y, z - 0.01, yaw, team, tags=(["Mounded"] if mesh == "SM_MineCliff" else None))
    for pt in PORTS:                                                      # the ports: the pier and its ship, what stands on the quay
        (dx, dy), dyaw = pt["dock"]
        sc.building("SM_Dock", dx, dy, DOCK_Z, dyaw, pt["team"])
        moor = meta("SM_Dock").get("moor", [2.9, -5.9, -1.0, 90.0])
        mx, my = rot(moor[0], moor[1], dyaw)
        ship = sc.add(SHIP, dx + mx, dy + my, moor[3] + dyaw, z=SEA, group="props", tags=["Moored"])
        ship["cloth"] = pt["team"]
        for (mesh, x, y, z, yaw) in pt["things"]:
            sc.add(mesh, x, y, yaw, z=z, group="port", r=3.0, team=pt["team"])
    sc.add("SM_PlazaBanner", PLAZA0[0], PLAZA0[1], z=PLATEAU_Z, r=1.3, team=0)
    sc.add("SM_PlazaBanner", PLAZA1[0], PLAZA1[1], yaw=180.0, z=PLATEAU_Z, r=1.3, team=1)
    # old pillars where each pass comes out into the basin, a pair of them
    for (mesh, x, y, yaw) in (("SM_Ruin_Pillar_B", _IN[0] - 1.0, _IN[1] + 11.0, 0.0), ("SM_Ruin_Pillar_C", _IN[0] + 10.0, _IN[1] - 7.0, 90.0)):
        sc.both(mesh, x, y, yaw, z=BASIN_Z, group="ruins", r=1.2)

    clutter = [("SM_FlowerPlanter", front("castle0", 1.0, -3.6), 0), ("SM_FlowerPlanter", front("castle0", 1.0, 3.6), 0)]
    for k in ("mine0", "mine0b"):
        clutter += [("SM_MineCart", front(k, 1.0, 3.0), BUILD[k][4]), ("SM_Barrel", front(k, 0.6, -3.0), 0), ("SM_Crate", front(k, 1.2, -4.0), 30)]
    clutter += [("SM_MineCart", front("mine_n2", 1.0, 3.2), 180), ("SM_Crate", front("mine_n2", 0.8, -3.4), 30), ("SM_Barrel", front("mine_n2", 0.6, -4.4), 0),
                ("SM_Signpost", (_HEAD[0] + 4.5, _HEAD[1] + 7.0), 200), ("SM_Signpost", (_IN[0] + 6.0, _IN[1] + 6.0), 60),
                ("SM_Signpost", (_STAIR[0][0] + 3.0, _STAIR[0][1] + 3.6), 100)]
    for (mesh, (x, y), yaw) in clutter:
        sc.both(mesh, x, y, yaw, r=0.9)

    def cell(x, y):
        return int(np.clip((x + HALF) / CELL, 2, N - 3)), int(np.clip((y + HALF) / CELL, 2, N - 3))

    def level(x, y, r=2):
        i, j = cell(x, y)
        i0, i1, j0, j1 = max(i - r, 0), min(i + r, N - 1), max(j - r, 0), min(j + r, N - 1)
        v = (h[i0, j], h[i, j], h[i1, j], h[i, j0], h[i, j1])
        return max(v) - min(v) <= (0.25 if G["rfloor"][i, j] else 0.0)

    rects = [p[:4] for p in G["pads"]]

    def on_pad(x, y, pad=0.6):
        for (x0, y0, x1, y1) in rects:
            if x0 - pad < x < x1 + pad and y0 - pad < y < y1 + pad:
                return True
        return math.hypot(x - PLAZA0[0], y - PLAZA0[1]) < 5.5 or math.hypot(x - PLAZA1[0], y - PLAZA1[1]) < 5.5

    path_d = G["road_d"]

    def free(x, y, r, path_gap=0.5, allow_pad=False):
        i, j = cell(x, y)
        if s[i, j] in (COBBLE, PLANK, GRAVEL) or G["hazard"][i, j] or not G["land"][i, j] or wild[i, j] or G["quay"][i, j]:
            return False
        if G["rfloor"][i, j] and not on_spur(x, y):
            return False
        if path_d[i, j] < path_gap + r or not level(x, y, max(1, int(r / CELL))):
            return False
        if not allow_pad and on_pad(x, y, 0.4 + r):
            return False
        return not sc.solid.hits(x, y, r)

    def north_west(x, y):
        return (y - x) > 0.5

    def on_spur(x, y, lo=3.5):                          # the base ramp's grass, off its worn middle
        d, t = seg_dist(np.array(x), np.array(y), _HEAD, _FOOT)
        return lo < float(d) < RAMP_HW and 0.02 < float(t) < 0.98

    # ---- lantern posts along the player's cobbled roads, alternating sides (and their twins)
    for pts, w, surf in PATHS[:len(PATHS) // 2]:
        if surf != COBBLE:
            continue
        run, side = 12.0, 1
        for a, b in zip(pts[:-1], pts[1:]):
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            ux, uy = (b[0] - a[0]) / max(L, 1e-6), (b[1] - a[1]) / max(L, 1e-6)
            d = 0.0
            while d < L:
                if run >= 26.0:
                    x, y = a[0] + ux * d - uy * side * (w + 1.0), a[1] + uy * d + ux * side * (w + 1.0)
                    if free(x, y, 0.45, 0.25):
                        sc.both("SM_LanternPost", x, y, r=1.0)
                        run, side = 0.0, -side
                d += 0.5
                run += 0.5
    for (dx, dy) in ((-4.6, 2.6), (4.4, -3.0), (3.2, 4.0), (-3.4, -4.4)):
        x, y = PLAZA0[0] + dx, PLAZA0[1] + dy
        if free(x, y, 0.4, 0.2, allow_pad=True):
            sc.both("SM_LanternPost_Tall", x, y, yaw=math.degrees(math.atan2(PLAZA0[1] - y, PLAZA0[0] - x)) + 90.0, r=1.0)
    for (x, y) in ((_FOOT[0] + 9.0, _FOOT[1] + 1.0), (_IN[0] + 1.0, _IN[1] - 8.5)):      # a lantern at each mouth of the pass
        if free(x, y, 0.4, 0.2):
            sc.both("SM_LanternPost", x, y, r=1.0)

    # ---- the forest (and the ridges' few trees): where nobody goes. Instances of the level's AVLForest
    count = dict(A=0, B=0, C=0, D=0)
    sc.wild_trees = 0
    for (x, y, z, kind, scale) in forest_spots(G, s):
        if tree_blocked(x, y, kind, scale):
            continue
        sc.trees2(kind, x, y, float(rng.integers(0, 4)) * 90.0, scale, "wild", z)
        count[kind] += 2
        sc.wild_trees += 2

    # ---- a few trees where people go: by the plateaus' rims and the basin's walls, none on the ground to build on's
    # middle, none in or against a building, none by a road
    near_trees = []

    def lone(n, where, kinds):
        got, tries = 0, 0
        while got < n and tries < 40000:
            tries += 1
            x, y = rng.uniform(-HALF + 5, HALF - 5, 2)
            if not north_west(x, y) or not where(x, y):
                continue
            kind = str(rng.choice(kinds))
            rad = {"A": 1.6, "B": 1.5, "C": 1.1, "D": 0.7}[kind]
            scale = float(rng.uniform(0.85, 1.1))
            if not free(x, y, rad + 0.6, 3.0) or tree_blocked(x, y, kind, scale) or any(math.hypot(x - ax, y - ay) < 9.0 for (ax, ay) in APRONS):
                continue
            if any(math.hypot(x - a, y - b) < 7.0 for (a, b) in near_trees):
                continue
            sc.trees2(kind, x, y, float(rng.integers(0, 4)) * 90.0, scale, "forest")
            near_trees.append((x, y))
            count[kind] += 2
            got += 1

    def rim0(x, y):                                     # the plateau's outer ring
        e = (abs(x - PA[0]) / PA[2]) ** PP + (abs(y - PA[1]) / PA[3]) ** PP
        return 0.66 < e < 0.9

    def walls(x, y):                                    # the basin's edge
        u, v = uv(x, y)
        e = ((abs(u) / BU) ** BP + (abs(v) / BV) ** BP) ** (1.0 / BP)
        return 0.78 < e < 0.95

    lone(16, rim0, ["D", "D", "D", "C"])
    lone(6, walls, ["D", "D", "C"])
    sc.cleared = 0

    # ---- undergrowth and rocks where people go (and their twins)
    def scatter(n, meshes, r, group, gap, scale=(0.9, 1.15), where=None, solid=False):
        placed, t = [], 0
        while len(placed) < n and t < n * 200:
            t += 1
            x, y = rng.uniform(-HALF + 3, HALF - 3, 2)
            if not north_west(x, y) or (where and not where(x, y)):
                continue
            if not free(x, y, r, 0.3) or any(math.hypot(x - a, y - b) < gap for a, b in placed[-300:]):
                continue
            placed.append((x, y))
            yaw = float(rng.uniform(0, 360)) if group != "rocks" else float(rng.integers(0, 4)) * 90.0
            sc.both(str(rng.choice(meshes)), x, y, yaw, float(rng.uniform(*scale)), group=group, r=r if solid else None)

    def edge(x, y):                                     # rocks and bushes keep to the edges of the open ground
        return rim0(x, y) or walls(x, y)

    def spur_edge(x, y):                                # ... and to the ramp's edges: the hillside's own, not a lane's
        return on_spur(x, y, 5.5)

    scatter(9, ["SM_Rock_A", "SM_Rock_B", "SM_Rock_C", "SM_Rock_D", "SM_Rock_E"], 1.5, "rocks", 6.0, scale=(0.6, 0.95), solid=True, where=spur_edge)
    scatter(36, ["SM_Bush_A", "SM_Bush_B", "SM_Bush_B", "SM_Bush_C"], 0.8, "plants", 2.0, scale=(0.8, 1.25), where=spur_edge)

    scatter(14, ["SM_Rock_A", "SM_Rock_B", "SM_Rock_B", "SM_Rock_C", "SM_Rock_C", "SM_Rock_D", "SM_Rock_E"], 1.5, "rocks", 6.0, scale=(0.7, 1.0), solid=True, where=edge)
    scatter(110, ["SM_Bush_A", "SM_Bush_A", "SM_Bush_B", "SM_Bush_B", "SM_Bush_C"], 0.8, "plants", 2.2, scale=(0.8, 1.25), where=edge)
    scatter(650, ["SM_Flowers_A", "SM_Flowers_B", "SM_Flowers_C", "SM_Flowers_D"], 0.3, "plants", 1.0)
    scatter(1500, ["SM_GrassTuft_A", "SM_GrassTuft_B", "SM_GrassTuft_C", "SM_GrassTuft_C"], 0.3, "plants", 0.6, scale=(0.9, 1.5))

    # ---- bushes along the forest's edge, where it shows (beside the ramps and under the plateaus' cliffs)
    edge_band = dilate(G["region"], 28) & ~dilate(G["region"], 6) & wild & G["land"] & ~R["mountain"] & ~R["flank"] & ~R["tor"] & (s == GRASS)
    k = 0
    for _ in range(40000):
        if k >= 260:
            break
        x, y = rng.uniform(-HALF + 3, HALF - 3, 2)
        if not north_west(x, y):
            continue
        i, j = cell(x, y)
        if edge_band[i, j] and level(x, y, 3) and not sc.solid.hits(x, y, 0.8, 1.0):
            sc.both(str(rng.choice(["SM_Bush_A", "SM_Bush_B", "SM_Bush_C"])), x, y, float(rng.uniform(0, 360)), float(rng.uniform(0.9, 1.4)), group="plants")
            k += 1
    sc.tree_counts = dict(count)
    return sc


# ---------------------------------------------------------------------------------------------------- balance

def walk_map(G):
    """The ground on 50 cm cells, as the game's path grid sees it (without trees): where a unit can stand, and its
    height there."""
    hz = G["hazard"]
    H = hz[0::2, 0::2] | hz[1::2, 0::2] | hz[0::2, 1::2] | hz[1::2, 1::2]
    X, Y = G["X"][0::2, 0::2] + CELL / 2, G["Y"][0::2, 0::2] + CELL / 2
    blocked = H.copy()
    for k in BUILD:
        blocked |= in_rect(X, Y, footprint(k, 0.25)[:4])
    hh = np.maximum(np.maximum(G["h"][0::2, 0::2], G["h"][1::2, 0::2]), np.maximum(G["h"][0::2, 1::2], G["h"][1::2, 1::2]))
    dk = G["deck"][0::2, 0::2] | G["deck"][1::2, 1::2]                        # the piers' planks
    hh = np.where(dk, DOCK_Z, hh)
    return ~blocked, hh, X, Y


def balance(G, verbose=False, trees=()):
    """Walking distances (metres, shortest routes over the ground) from each side's castle door, the ground each side
    has to build on, and the proof that the passes are the only way: with either pass shut, no route joins the two
    castles. None without scipy."""
    try:
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import dijkstra
    except Exception:
        return None
    ok, hh, X, Y = walk_map(G)
    n = ok.shape[0]
    idx = np.arange(n * n).reshape(n, n)

    def graph(ok):
        rows, cols, wts = [], [], []

        def link(di, dj, w, extra=None):
            a = (slice(max(0, -di), n - max(0, di)), slice(max(0, -dj), n - max(0, dj)))
            b = (slice(max(0, di), n - max(0, -di)), slice(max(0, dj), n - max(0, -dj)))
            m = ok[a] & ok[b] & (np.abs(hh[a] - hh[b]) <= 0.5)
            if extra is not None:
                m &= extra[a]
            rows.append(idx[a][m]); cols.append(idx[b][m]); wts.append(np.full(int(m.sum()), w))
            return m

        step = {}
        for (di, dj) in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            m = np.zeros((n, n), bool)
            a = (slice(max(0, -di), n - max(0, di)), slice(max(0, -dj), n - max(0, dj)))
            m[a] = link(di, dj, 0.5)
            step[(di, dj)] = m
        for (di, dj) in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            link(di, dj, 0.5 * math.sqrt(2.0), step[(di, 0)] & step[(0, dj)])
        return coo_matrix((np.concatenate(wts), (np.concatenate(rows), np.concatenate(cols))), shape=(n * n, n * n)).tocsr()

    def node(p):
        i, j = int((p[0] + HALF) / 0.5), int((p[1] + HALF) / 0.5)
        best, bd = None, 1e9
        for a in range(max(0, i - 6), min(n, i + 7)):
            for b in range(max(0, j - 6), min(n, j + 7)):
                if ok[a, b]:
                    d = (a - i) ** 2 + (b - j) ** 2
                    if d < bd:
                        best, bd = idx[a, b], d
        return best

    pts = dict(G_)
    pts.update(dock0=(PORT_X - 15.0, PORT_Y + 11.0), dock1=(-PORT_X + 15.0, -PORT_Y - 11.0), quay0=(PORT_X - 6.0, PORT_Y + 8.0), quay1=(-PORT_X + 6.0, -PORT_Y - 8.0))
    pts.update(centre=(0.0, 0.0), ramp_head0=_HEAD, ramp_foot0=_FOOT, pass_in0=_IN, ramp_head1=mir(_HEAD), ramp_foot1=mir(_FOOT), pass_in1=mir(_IN))
    for (name, x, y, _rx, _ry) in PADS:
        pts[name] = (x, y)
    nodes = {k: node(v) for k, v in pts.items()}
    src = [nodes["castle0"], nodes["castle1"]]
    D = dijkstra(graph(ok), directed=False, indices=src)

    def d(t, k):
        if nodes[k] is None:
            return None
        v = float(D[t, nodes[k]])
        return None if not math.isfinite(v) else round(v, 1)

    def side(t):
        s, o = str(t), str(1 - t)
        return dict(home_mine_1=d(t, "mine" + s), home_mine_2=d(t, "mine" + s + "b"), tower_1=d(t, "tower" + s), tower_2=d(t, "tower" + s + "b"),
                    quay=d(t, "quay" + s), pier_head=d(t, "dock" + s), enemy_quay=d(t, "quay" + o),
                    ramp_head=d(t, "ramp_head" + s), ramp_foot=d(t, "ramp_foot" + s), basin_entry=d(t, "pass_in" + s), centre=d(t, "centre"),
                    neutral_1=d(t, "mine_n1"), neutral_2=d(t, "mine_n2"), basin_north=d(t, "basin_north"), basin_south=d(t, "basin_south"),
                    enemy_ramp_head=d(t, "ramp_head" + o), enemy_castle=d(t, "castle" + o))

    rep = dict(player=side(0), enemy=side(1),
               heights=dict(plateau=PLATEAU_Z, basin=BASIN_Z, sea=SEA, summit=float(G["h"].max())),
               note="metres walked from the castle's door by the shortest route over the ground (50 cm cells, steps of at most 50 cm, "
                    "no hazard, no building; trees not counted)")

    # ---- the only way: shut a pass (its floor) and ask again
    shut = {}
    for name, a, b in (("pass0", _FOOT, _IN), ("pass1", mir(_FOOT), mir(_IN))):
        mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        ok2 = ok & ~(seg_dist(X, Y, a, b)[0] < 30.0) | (ok & (np.hypot(X - mid[0], Y - mid[1]) > 60.0))
        ok2 = ok & ~((seg_dist(X, Y, a, b)[0] < 40.0) & (np.hypot(X - mid[0], Y - mid[1]) < 16.0))
        D2 = dijkstra(graph(ok2), directed=False, indices=[nodes["castle0"]])
        v = float(D2[0, nodes["castle1"]])
        shut[name] = None if not math.isfinite(v) else round(v, 1)
    rep["with_a_pass_shut"] = dict(shut, note="the route from the player's castle to the enemy's with a wall across that pass: None = there is none (no way round)")

    # ---- the ground to build on: level ground a side can walk to, less roads and buildings (and 2 m round them)
    d0, d1 = D[0].reshape(n, n), D[1].reshape(n, n)
    taken = G["path"][0::2, 0::2] | G["path"][1::2, 1::2]
    for k in BUILD:
        taken |= in_rect(X, Y, footprint(k, 2.0)[:4])
    flat = np.ones((n, n), bool)
    for (di, dj) in ((3, 0), (-3, 0), (0, 3), (0, -3)):
        flat &= np.roll(np.roll(hh, di, 0), dj, 1) == hh
    reach = ok & np.isfinite(d0) & ~taken & flat
    area = {}
    for m in MESAS:
        t = G["R"]["tops"][m["name"]][0::2, 0::2]
        area[m["name"]] = dict(top=int(t.sum() * 0.25), buildable=int((reach & t).sum() * 0.25))
    b = G["R"]["basin"][0::2, 0::2]
    area["basin"] = dict(floor=int(b.sum() * 0.25), buildable=int((reach & b).sum() * 0.25),
                         nearer_player=int((reach & b & (d0 < d1)).sum() * 0.25), nearer_enemy=int((reach & b & (d1 < d0)).sum() * 0.25))
    area["walkable_total"] = int((ok & np.isfinite(d0)).sum() * 0.25)
    rep["ground_m2"] = dict(area, note="square metres. top / floor: the level ground itself; buildable: what of it can be walked to, less roads and "
                                       "buildings (and 2 m round them) and anything not level over 1.5 m; walkable_total: all the ground a unit can reach")
    rep["ramps"] = {r[0]: dict(width=2 * r[3], length=round(math.hypot(r[2][0] - r[1][0], r[2][1] - r[1][1]), 1), rise=abs(r[2][2] - r[1][2])) for r in RAMPS}
    rep["unreachable"] = sorted(k for k in pts if nodes[k] is None or not math.isfinite(float(D[0, nodes[k]])))
    if verbose:
        print("%-24s %8s %8s" % ("from the castle door to", "player", "enemy"))
        for k in rep["player"]:
            print("%-24s %8s %8s" % (k, rep["player"][k], rep["enemy"][k]))
        print("with a pass shut: %s" % shut)
        for k, v in area.items():
            print("%-24s %s" % (k, v))
        print("ramps: %s" % rep["ramps"])
        print("unreachable: %s" % (rep["unreachable"] or "none"))
    return rep


def hard_edges(G):
    """The owner's terrain rule, measured: cells of open ground (not wild, hazard, a road or a ramp) with a drop of a
    metre or more to a neighbour that is open ground too."""
    h = G["h"]
    openg = ~(G["wild"] | G["hazard"] | G["path"])
    for k in BUILD:                                                         # (a mine's own rock, a building's pad)
        openg &= ~in_rect(G["X"], G["Y"], footprint(k, 1.5)[:4])
    bad = np.zeros(h.shape, bool)
    for ax in (0, 1):
        for sh in (1, -1):
            bad |= openg & np.roll(openg, sh, axis=ax) & (h - np.roll(h, sh, axis=ax) >= 1.0)
    G["hard"] = bad
    return int(bad.sum())


# ---------------------------------------------------------------------------------------------------- output

def ue(p):
    """Layout metres (+Y north) -> Unreal centimetres (+Y south)."""
    return [round(p[0] * 100.0, 1), round(-p[1] * 100.0, 1), round(p[2] * 100.0, 1)]


def teams(G):
    h = G["h"]

    def entry(key):
        mesh, x, y, z, yaw, team = BUILD[key]
        f = footprint(key)
        e = dict(key=key, kind=KIND[mesh], mesh=mesh, team=team, pos=[x, y, z], yaw=yaw, footprint=[round(v, 3) for v in f[:4]],
                 pos_ue=ue((x, y, z)), yaw_ue=-yaw)
        gx, gy = GATE[key]
        e["gate"] = [gx, gy, round(ground(h, gx, gy), 3)]
        e["gate_ue"] = ue(e["gate"])
        return e

    def point(p):
        q = [p[0], p[1], round(ground(h, p[0], p[1]), 3)]
        return dict(pos=q, pos_ue=ue(q))

    out = {}
    for team, plaza, start, rally in ((0, PLAZA0, SPAWN, RALLY0), (1, PLAZA1, START1, RALLY1)):
        b = [entry(k) for k in BUILD if BUILD[k][5] == team]
        out[str(team)] = dict(name="player" if team == 0 else "enemy", castle=next(e for e in b if e["kind"] == "Castle"),
                              buildings=b, start=dict(point(start), yaw=start[2], yaw_ue=-start[2]), rally=point(rally), plaza=point(plaza))
    out["neutral"] = dict(buildings=[entry(k) for k in BUILD if BUILD[k][5] == "Neutral"])
    out["axes"] = "pos: metres, +X east, +Y north, +Z up, yaw counter-clockwise from above (fronts face -Y at yaw 0). " \
                  "pos_ue / yaw_ue: Unreal centimetres (x, -y, z) and degrees (-yaw)."
    out["tags"] = "every building actor: Selectable, Name:<kind>, Team:0|1|Neutral. Markers (TargetPoint actors): TeamStart:0, TeamStart:1, " \
                  "Rally:0, Rally:1, and the contested ground Basin, PassNW, PassSE."
    return out


def buildable_areas():
    """The named level grounds, for whoever places buildings."""
    out = [dict(name=m["name"], team=m["team"], z=m["z"], polygon=[list(p) for p in m["poly"]], kind="top") for m in MESAS]
    out += [dict(name=n, team="Neutral", z=BASIN_Z, centre=[x, y], radii=[rx, ry], kind="build") for (n, x, y, rx, ry) in PADS]
    return out


def _sky():
    """Clouds (x, y, z, half sizes) and flocks of birds (x, y, z, the loop's radius): puffs along the two crests and over
    the corner massifs, banks beyond the edges, flocks over the basin, the bases and the corners. The same sky at
    (x, y) and (-x, -y)."""
    clouds = []
    for k, (u, v, z) in enumerate(((46.0, 44.0, 62.0), (100.0, 14.0, 66.0), (170.0, 16.0, 74.0), (140.0, -24.0, 68.0), (30.0, 110.0, 60.0))):
        x, y = xy(u, v)
        sz = (9.0 + 3.0 * (k % 3), 7.0 + 2.0 * (k % 2), 4.5)
        clouds += [(round(x, 1), round(y, 1), z) + sz, (round(-x, 1), round(-y, 1), z) + sz]
    for k in range(10):                                                     # banks beyond the edges
        a = 2 * math.pi * (k + 0.5) / 10
        r = 330.0 + 30.0 * (k % 5) / 4.0
        clouds.append((round(r * math.cos(a), 1), round(r * math.sin(a), 1), 56.0 + 7.0 * (k % 5), 26.0, 18.0, 8.0))
    flocks = [(0.0, 0.0, 60.0, 70.0), (-130.0, 130.0, 58.0, 70.0), (130.0, -130.0, 58.0, 70.0), (140.0, 140.0, 80.0, 70.0), (-140.0, -140.0, 80.0, 70.0)]
    return dict(clouds=clouds, flocks=flocks, birds_per_flock=6)


def build(write=True, verbose=False):
    G = heights()
    s = surface(G)
    sc = things(G, s)
    h = G["h"]
    tm = teams(G)
    h = G["top"]
    markers = []
    for t in ("0", "1"):
        markers.append(dict(tag="TeamStart:" + t, pos=tm[t]["start"]["pos"], yaw=tm[t]["start"]["yaw"]))
        markers.append(dict(tag="Rally:" + t, pos=tm[t]["rally"]["pos"], yaw=tm[t]["start"]["yaw"]))
    for tag, (zx, zy) in ZONES.items():
        markers.append(dict(tag=tag, pos=[zx, zy, round(ground(h, zx, zy), 3)], yaw=0.0))
    bal = balance(G, verbose, sc.trees)
    edges = hard_edges(G)
    counts = {}
    for it in sc.items:
        counts[it["mesh"]] = counts.get(it["mesh"], 0) + 1
    land_m2 = float(G["land"].sum()) * CELL * CELL
    wood_m2 = float((G["wild"] & G["land"] & ~G["R"]["mountain"] & ~G["R"]["flank"] & ~G["R"]["tor"]).sum()) * CELL * CELL
    layout = dict(
        name="Realm v3", map="/Game/Maps/L_RealmV3",
        camera=dict(pos=list(C.POS), target=list(C.TARGET), hfov=C.HFOV, az=C.AZ, el=C.EL, width=C.W, height=C.H),
        terrain=dict(cell=CELL, half=HALF, zmin=ZMIN, top=TOP, sea=SEA, seabed=SEABED, water=WAT, surfaces=SURF, hard_edge_cells=edges,
                     asymmetric_cells=G["R"]["asym_cells"], land_m2=round(land_m2), forest_m2=round(wood_m2),
                     ridge_m2=round(float(G["R"]["mountain"].sum()) * CELL * CELL), region_m2=round(float(G["region"].sum()) * CELL * CELL)),
        spawn=dict(pos=[SPAWN[0], SPAWN[1], ground(h, SPAWN[0], SPAWN[1])], yaw=SPAWN[2]),
        places=dict(plaza=PLAZA0, plaza1=PLAZA1, glade=(0.0, 0.0), basin=(0.0, 0.0), plateau0=PA[:2], plateau1=mir(PA[:2]),
                    ports=[dict(team=pt["team"], quay=pt["quay"], dock=pt["dock"][0], yaw=pt["dock"][1]) for pt in PORTS],
                    ramps={r[0]: dict(foot=r[2] if r[1][2] > r[2][2] else r[1], head=r[1] if r[1][2] > r[2][2] else r[2], half_width=r[3]) for r in RAMPS},
                    **{k: (v[1], v[2]) for k, v in BUILD.items()}),
        gates=GATE,
        teams=tm,
        markers=markers,
        balance=bal,
        buildable=buildable_areas(),
        sky=_sky(),
        trees=dict(count=sc.tree_counts, clear=TREE_CLEAR, margin=BUILD_MARGIN, cleared_at_build=sc.cleared, wild=sc.wild_trees,
                   per_hectare_of_forest=round(sc.wild_trees / max(wood_m2, 1.0) * 1e4),
                   faces=int(sum(sc.tree_counts[k] * (meta("SM_Tree2_%s_Trunk" % k).get("faces", 0) + meta("SM_Tree2_%s_Leaves" % k).get("faces", 0)) for k in "ABCD")),
                   lod_faces_m=[round(sum(sc.tree_counts[k] * (meta("SM_Tree2_%s_Trunk%s" % (k, a)).get("faces", 0) + meta("SM_Tree2_%s_Leaves%s" % (k, b)).get("faces", 0))
                                          for k in "ABCD") / 1e6, 3) for (a, b) in (("", ""), ("", "_L1"), ("_L2", "_L2"))]),
        instances=sc.items,
    )
    if write:
        os.makedirs(OUT, exist_ok=True)
        if bal is None and os.path.exists(os.path.join(OUT, NAME + ".json")):     # Blender has no scipy: keep the measured routes
            try:
                layout["balance"] = json.load(open(os.path.join(OUT, NAME + ".json"))).get("balance")
            except Exception:
                pass
        with open(os.path.join(OUT, NAME + ".json"), "w") as f:
            json.dump(layout, f)
        np.savez_compressed(os.path.join(OUT, NAME + "_terrain.npz"), h=G["top"].astype(np.float32), s=s, hazard=G["hazard"], wz=G["wz"], voxels=G["h"].astype(np.float32))
    faces = sum(meta(m).get("faces", 0) * n for m, n in counts.items())
    print("realmv3: %d instances, %d kinds, %.2f M faces; trees %s (%d of them in the forest: %d per hectare of it) = %.2f M faces (all at LOD 0 / 1 / 2: %s M); "
          "land %.0f m2: forest %.0f, ridges %.0f, where people go %.0f; summit %.0f m; hard edges on open ground: %d cells; cells not their twin's height: %d; no sidecar: %s" % (
              len(sc.items), len(counts), faces / 1e6, sc.tree_counts, sc.wild_trees, layout["trees"]["per_hectare_of_forest"], layout["trees"]["faces"] / 1e6,
              " / ".join("%.2f" % v for v in layout["trees"]["lod_faces_m"]), land_m2, wood_m2, layout["terrain"]["ridge_m2"], layout["terrain"]["region_m2"],
              float(G["h"].max()), edges, G["R"]["asym_cells"], ", ".join(sorted(sc.missing)) or "none"))
    return layout, G, s


def debug(layout, G, s, path=None):
    """The plan from above (north up), 2 px per metre: surfaces, heights, hazard edge, open ground (paler), buildings, trees."""
    from PIL import Image, ImageDraw
    h = G["h"]
    cols = np.array([(96, 150, 50), (190, 160, 110), (140, 100, 60), (120, 120, 120), (150, 150, 150), (110, 140, 100), (200, 140, 70), (240, 244, 250)], np.uint8)
    shade = 0.62 + 0.02 * np.clip(h, -3, 14) + 0.004 * np.clip(h - 14, 0, 100)
    shade = shade + np.clip((np.roll(h, 2, 0) - np.roll(h, -2, 0)) * -0.05 + (np.roll(h, 2, 1) - np.roll(h, -2, 1)) * 0.05, -0.25, 0.25)
    rgb = cols[s].astype(np.float32) * shade[:, :, None]
    rgb[G["open"] & (s == 0)] *= 1.18
    rgb[G["sea"]] = (40, 90, 160)
    hz = G["hazard"]
    edge = hz & ~(np.roll(hz, 1, 0) & np.roll(hz, -1, 0) & np.roll(hz, 1, 1) & np.roll(hz, -1, 1))
    rgb[edge] = (255, 40, 40)
    if "hard" in G:
        rgb[dilate(G["hard"], 2)] = (255, 0, 255)
    img = np.clip(rgb, 0, 255).astype(np.uint8).transpose(1, 0, 2)[::-1]
    K = CELL * 2
    im = Image.fromarray(img[::2, ::2])
    dr = ImageDraw.Draw(im)

    def px(x, y):
        return ((x + HALF) / K, (HALF - y) / K)

    if "--no-trees" not in sys.argv:
        for it in layout["instances"]:
            x, y, _z = it["pos"]
            if it["mesh"].endswith("_Leaves"):
                kind = it["mesh"].split("_")[-2]
                r = {"A": 6.5, "B": 6.5, "C": 4.2, "D": 2.4}.get(kind, 2) * it.get("scale", 1.0) / K
                c = px(x, y)
                g = {"A": (22, 78, 30), "B": (26, 84, 34), "C": (34, 98, 38), "D": (44, 112, 44)}[kind]
                dr.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], fill=g, outline=(18, 60, 22))
    for k, v in BUILD.items():
        f = footprint(k)
        a, b = px(f[0], f[3]), px(f[2], f[1])
        dr.rectangle([a[0], a[1], b[0], b[1]], outline=(255, 230, 80) if v[5] == 0 else ((255, 80, 80) if v[5] == 1 else (255, 255, 255)), width=3)
        g = px(*GATE[k])
        dr.ellipse([g[0] - 4, g[1] - 4, g[0] + 4, g[1] + 4], fill=(255, 0, 255))
        dr.text((a[0] + 4, a[1] + 4), k, fill=(255, 255, 255))
    for (n, x, y, rx, ry) in PADS:
        a, b = px(x - rx, y + ry), px(x + rx, y - ry)
        dr.ellipse([a[0], a[1], b[0], b[1]], outline=(255, 255, 255), width=1)
    path = path or os.path.join(ROOT, "Saved", "realmv3_plan.png")
    im.save(path)
    print(path)


if __name__ == "__main__":
    L, G_all, S = build(verbose="--balance" in sys.argv or "--debug" in sys.argv)
    if "--debug" in sys.argv:
        debug(L, G_all, S)
