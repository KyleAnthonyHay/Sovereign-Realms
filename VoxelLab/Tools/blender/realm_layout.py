"""The realm: the battle map after References/Remake/battlefield.png, at twice its size each way. Pure numpy (+ scipy
for the balance report, when it is there); writes SourceArt/realm.json and SourceArt/realm_terrain.npz (heights,
surfaces, the hazard map).

    Blender -b --factory-startup --python Tools/blender/realm_layout.py                (or: import realm_layout as R; R.build())
    ../Tools/.venv/bin/python Tools/blender/realm_layout.py [--debug] [--balance]      (--debug: Saved/realm_plan.png, the
                                                                                         plan from above; --balance: the routes)

Built on town_layout.py (its helpers and its Scene are used as they are). World metres, +X east, +Y north, +Z up; the
postcard camera (realm_cam.py) looks from the south-west as the town's does, so the picture's bottom-left is the
south-west and its top-right the north-east.

The map is 416 m square (four times the area of the first one: the same buildings, twice as far apart, the room
between them open ground to build on). The sea lies to the west and the south; to the north and the east the land
runs on into the backdrop (assets/realm_terrain.py), which nobody can reach.

  south-west   the player's town on the plain (0): the castle and its plaza, the dock under the west cliff. Its one gold
               mine is set into the mountain's foot at the north end of the west terrace (+1), its watch tower on a
               mound before the mine's mouth (as the map first had them). Nothing else: no farm, no barracks, no
               archery range (Builders raise them); meadows (MEADOWS0) round the town
  north-west   the mountain (terraces from +5 to +33): a neutral mine
               in its east face
  middle       the river, north to south-east: the upper river on the highland (UP), the first fall, the gorge (MID)
               that splits round the divider island, the two bridges over the island (the only crossing), the second
               fall, the lower gorge (LOW), the third fall into the sea
  north-east   the enemy's base on its plateau (+1): the same, laid out differently (the castle faces west; its mine set
               into the east ridge to the south-east, its tower on a mound before the mine's mouth); meadows (MEADOWS1)
  roads        only these: each castle to the bridge, each castle to its mine (and the steps to the tower beside it),
               the player's castle to the dock. Everything else is grass, to build on
  south-east   the crag with the second neutral mine (on the enemy's bank, as far from the bridge as the first)

  realm.json   camera, terrain, spawn, places, gates, instances [{mesh, pos, yaw, scale, group, tags?, team?, scale3?}],
               teams (the contract with the game code: every building's kind, team, position, yaw, footprint; each
               side's start and rally point), markers (tagged points the level gets), balance (measured routes, and
               the ground each side has to build on), trees (the budget: how many of each kind, their faces)
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import realm_cam as C
import minehill
import town_layout as T
from town_layout import hash2, noise2, seg_dist, dist_polyline, in_poly, in_rect, meta, rot

ROOT = T.ROOT
OUT = T.OUT
MESHES = T.MESHES

CELL = 0.25
HALF = 208.0                      # the world is 416 m square
N = int(2 * HALF / CELL)
ZMIN = -8.5
TOP = 34.0
SEA = -6.25                       # the sea's surface; its bed is SEABED
SEABED = -7.75
UP = 1.75                         # the upper river, on the highland
MID = -2.25                       # the gorge, under the bridges
LOW = -4.0                        # the lower gorge, after the second fall

SURF = T.SURF
GRASS, COBBLE, DIRT, GRAVEL, STONE, MOSSY, PLANK = range(7)

# ---------------------------------------------------------------------------------------------------- the plan

# the coast: the land's outline (it runs off the map to the north and the east)
COAST = [(-184, 280), (280, 280), (280, -116), (200, -120), (168, -132), (140, -136), (120, -148), (96, -154), (72, -144), (48, -152),
         (20, -168), (-16, -176), (-56, -172), (-88, -176), (-116, -168), (-140, -152), (-160, -136), (-170, -116), (-172, -100), (-180, -84),
         (-184, -56), (-180, -24), (-186, 0), (-182, 40), (-188, 80), (-180, 124), (-186, 168), (-180, 208)]
ISLETS = [(-196, -148, 6.0), (-195, -36, 4.0), (-120, -194, 5.5), (-24, -196, 6.5), (80, -184, 7.0), (156, -168, 6.0), (192, -148, 5.0)]

# the mountain in the north-west corner (its edge: cliffs), the enemy's plateau
MOUNTAIN = [(-280, 280), (-60, 280), (-60, 56), (-128, 56), (-140, 34), (-280, 34)]
PLATEAU = [(36, 92), (52, 56), (68, 28), (92, 4), (116, -16), (132, -48), (172, -64), (280, -64), (280, 280), (20, 280), (16, 192), (18, 140)]
# The watch towers guard the gold mines: each stands on a mound 3 m over its side's ground, some 18 m from its mine's
# mouth and beside the last stretch of the mine road, which is the way a raid from the bridge comes. Each side has one
# mine, set into the wall at the edge of its land: the player's into the mountain's foot, the enemy's into the east
# ridge (References/Remake/mine_in_wall.png; no hills of their own).
SHELF = (-152.0, 14.0, 9.0)       # the player's tower: a mound south-east of its mine's mouth, at +4 (3 m over the terrace)
KNOLL = (152.5, -2.0, 9.0)        # the enemy's tower: a mound north-west of its mine's mouth, at +4 (3 m over its plateau)
HOME_CRAGS = []                   # (no drums of rock for the home mines)
CRAG = (77.0, -63.0, 14.0)        # the neutral mine of the east bank is set into this rock (its back and both sides)
FALL1_Y = 187.0                   # the highland's edge at the river: the first fall
FALL1_X = -20.0                   # where the river crosses it
RIDGE_X = 180.0                   # the foot of the east ridge (it wanders)
TERRACE_W = (-116.0, -76.0)       # the player's west terrace (+1): west of this x, north of this y

# buildings: name -> (mesh, x, y, z, yaw, team). Fronts face -Y at yaw 0, -X (west) at yaw -90, +X (east) at yaw 90.
BUILD = dict(
    castle0=("SM_Castle", -104.0, -56.0, 0.0, 0.0, 0),
    mine0=("SM_MineCliff", -158.0, 39.5, 1.0, 0.0, 0),                 # (set into the mountain's foot, at the north end of the west terrace)
    tower0=("SM_WatchTower", SHELF[0], SHELF[1], 4.0, 180.0, 0),
    castle1=("SM_Castle", 118.0, 98.0, 1.0, -90.0, 1),
    mine1=("SM_MineCliff", 179.0, -8.0, 1.0, -90.0, 1),                # (set into the east ridge, south-east of the castle)
    tower1=("SM_WatchTower", KNOLL[0], KNOLL[1], 4.0, 90.0, 1),
    mine_w=("SM_MineCliff", -66.5, 88.0, 0.0, 90.0, "Neutral"),
    mine_e=("SM_MineCliff", 67.0, -62.0, 0.0, -90.0, "Neutral"),
)
KIND = {"SM_Castle": "Castle", "SM_BarracksYard": "Barracks", "SM_ArcheryHall": "Archery Range", "SM_MineCliff": "Gold Mine",
        "SM_WatchTower": "Watch Tower", "SM_FarmCottage_A": "Farm", "SM_FarmCottage_B": "Farm", "SM_Farmstead": "Farm",
        "SM_Bridge": "Bridge", "SM_PlazaBanner": "Village Banner", "SM_Dock": "Dock"}

PLAZA0, PLAZA1 = (-104.0, -70.0), (104.0, 98.0)
# the crossing: two footbridges (7 m each, running east-west) over the two channels, the divider island between them
BRIDGE_Y = 10.0
BRIDGE_W, BRIDGE_E = (-6.5, BRIDGE_Y), (6.5, BRIDGE_Y)
BRIDGE_WEST_END, BRIDGE_EAST_END = (-10.0, BRIDGE_Y), (10.0, BRIDGE_Y)
ISLAND_WALK = 11.0                # the island can be walked this far north and south of the crossing; beyond: bare rock
DOCK = (-171.0, -112.0)           # its land end; it runs out west (yaw -90), deck 1 m above the sea
DOCK_Z = SEA + 1.0
SPAWN = (-104.0, -66.0, -120.0)   # x, y, facing (degrees from +X): in front of the player's castle, facing the viewer
START1 = (107.0, 98.0, 180.0)    # where the enemy's units gather: in front of its castle
RALLY0, RALLY1 = (-66.0, -49.35), (84.65, 40.0)      # each side's first troops stand here (open ground by its road to the bridge)

# The open ground to build on: meadows (x, y, radius) round each side's buildings. Flat (none of the woods' half-block
# terraces), and all but bare of trees. What lies between them is forest, which a building clears where it is put
# (AVLForest::ClearTrees in the game).
MEADOWS0 = [(-104, -64, 60), (-62, -32, 34), (-146, -46, 30), (-76, -116, 40), (-100, 6, 36), (-44, -100, 30)]
MEADOWS1 = [(114, 98, 60), (104, 42, 34), (124, 160, 28), (152, 76, 36), (72, 138, 32), (150, 14, 30)]

# Nobody builds a mine in the game: every mine is placed here, set into the ground it stands by, and the game adds
# nothing round it (a Builder claims a neutral or fallen mine where it stands). In a wall: minehill.embed, see heights().
# In a hill: HILLS. MOUNDED lists mines that get the mesh of that hill, SM_MineMound (Tools/blender/assets/
# mine_mound.py), at their own place and turn: none here. Every mine actor is tagged Mounded: it is reached, worked and
# struck at its front.
# A mine in a hill (not in a wall) has the hill's shoulders round it: minehill.hill, the terraced hill of References/
# Remake/mine_mound.png, highest behind the mine, rolling off on both its sides, open before its mouth; laid over the
# rock that stands there. key -> (crest over the mine's floor, how far its foot reaches (from, to), seed)
HILLS = dict(mine_e=(6.5, (6.0, 10.0), 5))
MOUNDED = ()                      # (none here: every mine of this map is set into a wall, see heights())


def mound_rects():
    return [minehill.mound_rect(BUILD[k][1], BUILD[k][2], BUILD[k][4]) for k in MOUNDED]


def footprint(key, pad=0.0):
    mesh, x, y, z, yaw = BUILD[key][:5]
    (x0, y0, _), (x1, y1, _) = meta(mesh).get("bounds", [[-5, -5, 0], [5, 5, 5]])
    cs = [rot(a, b, yaw) for a in (x0, x1) for b in (y0, y1)]
    return (x + min(c[0] for c in cs) - pad, y + min(c[1] for c in cs) - pad, x + max(c[0] for c in cs) + pad, y + max(c[1] for c in cs) + pad, z)


def front(key, out=0.0, along=0.0):
    """A point `out` metres in front of a building's front edge (its own -Y), `along` metres to its right."""
    mesh, x, y, z, yaw = BUILD[key][:5]
    y0 = meta(mesh).get("bounds", [[-5, -5, 0], [5, 5, 5]])[0][1]
    dx, dy = rot(along, y0 - out, yaw)
    return (round(x + dx, 2), round(y + dy, 2))


def behind(key, X, Y, side=3.0, depth=7.0):
    """The cells behind a building (a mine: the rock it is set in)."""
    mesh, x, y, z, yaw = BUILD[key][:5]
    (x0, y0, _), (x1, y1, _) = meta(mesh).get("bounds", [[-5, -5, 0], [5, 5, 5]])
    a = math.radians(-yaw)
    lx = (X - x) * math.cos(a) - (Y - y) * math.sin(a)
    ly = (X - x) * math.sin(a) + (Y - y) * math.cos(a)
    return (lx > x0 - side) & (lx < x1 + side) & (ly > y1 - 1.0) & (ly < y1 + depth)


# The river. Each stretch: (points, half width). The two channels are narrow where the bridges cross them.
RIVER_UP = [([(-8, 280), (-16, 224), (FALL1_X, FALL1_Y - 0.5)], 5.0)]
CHANNEL_W = [(0, 76), (-9, 58), (-10, 34), (-6.5, 22), (-6.5, -2), (-10, -14), (-9, -32), (0, -48)]
CHANNEL_E = [(-x, y) for (x, y) in CHANNEL_W]
RIVER_MID = [([(FALL1_X, FALL1_Y + 0.5), (-18, 156), (-10, 124), (-2, 96), (0, 76)], 5.5),
             (CHANNEL_W[:4], 3.2), (CHANNEL_W[3:5], 2.6), (CHANNEL_W[4:], 3.2),            # the west channel
             (CHANNEL_E[:4], 3.2), (CHANNEL_E[3:5], 2.6), (CHANNEL_E[4:], 3.2),            # the east channel
             ([(0, -48), (6, -60), (16, -74)], 5.5)]
FALL2 = (16.5, -74.5)
FALL2_DIR = (0.68, -0.735)        # the river's direction there: beyond this line the water lies at LOW
RIVER_LOW = [([(17, -75), (40, -100), (76, -120), (108, -138), (128, -156)], 6.0)]

# gates and aprons
GATE = dict(
    castle0=front("castle0", 0.2), tower0=front("tower0", 0.3), mine0=front("mine0", 1.5), mine_w=front("mine_w", 2.0),
    castle1=front("castle1", 0.2), tower1=front("tower1", 0.3), mine1=front("mine1", 2.0), mine_e=front("mine_e", 2.0),
)
G_ = GATE
ROAD_M0, ROAD_M1 = (-80.0, -66.0), (80.0, 80.0)          # where each side's mine road leaves its main road
BEND_W, BEND_E = (-28.0, -16.0), (36.0, 20.0)            # a bend of each main road on its way to the bridge
TOWER_RD0 = (-152.0, 30.0)                               # where the steps to the player's tower leave its mine road
TOWER_RD1 = (168.5, -2.0)                                # and the enemy's

# paths: (points [(x, y, z)], half width, surface). A change of z between two points is a flight of steps.
# Only these roads: each castle to the bridge, to its mine (with the steps to the tower beside it), the player's to the
# dock. The rest of the ground is grass to build on.
PATHS = [
    # ---- the player's side (the plain: 0)
    ([G_["castle0"] + (0,), PLAZA0 + (0,)], 1.8, COBBLE),
    ([PLAZA0 + (0,), ROAD_M0 + (0,), (-60.0, -52.0, 0), (-34.0, -46.0, 0), BEND_W + (0,), (-30.0, 2.0, 0), BRIDGE_WEST_END + (0,)], 2.0, COBBLE),     # to the bridge
    ([PLAZA0 + (0,), (-118.0, -105.0, 0), (-144.0, -112.0, 0), (-157.25, -112.0, 0), (-168.75, -112.0, DOCK_Z), (DOCK[0] + 0.25, DOCK[1], DOCK_Z)], 1.4, COBBLE),   # to the dock
    ([ROAD_M0 + (0,), (-83.0, -48.0, 0), (-90.0, -16.0, 0), (-100.0, 12.0, 0), (-111.0, 18.0, 0), (-121.0, 16.0, 1), (-136.0, 27.0, 1),
      TOWER_RD0 + (1,), G_["mine0"] + (1,)], 1.3, COBBLE),                                                                                              # to the mine
    ([TOWER_RD0 + (1,), (G_["tower0"][0], 24.0, 4), G_["tower0"] + (4,)], 1.3, COBBLE),
    # ---- the crossing
    ([(-3.0, BRIDGE_Y, 0), (3.0, BRIDGE_Y, 0)], 1.4, COBBLE),
    # ---- the enemy's side (its plateau: +1)
    ([G_["castle1"] + (1,), PLAZA1 + (1,)], 1.8, COBBLE),
    ([PLAZA1 + (1,), ROAD_M1 + (1,), (62.0, 54.0, 1), (56.0, 45.0, 0), BEND_E + (0,), (28.0, 12.0, 0), BRIDGE_EAST_END + (0,)], 2.0, COBBLE),          # to the bridge
    ([ROAD_M1 + (1,), (104.0, 72.0, 1), (136.0, 68.0, 1), (160.0, 44.0, 1), (166.0, 20.0, 1), TOWER_RD1 + (1,), G_["mine1"] + (1,)], 1.3, COBBLE),     # to the mine
    ([TOWER_RD1 + (1,), (TOWER_RD1[0] - 6.0, TOWER_RD1[1], 4), G_["tower1"] + (4,)], 1.3, COBBLE),
]
# where a path meets something at its own level: it is not sunk there
APRONS = [G_[k] for k in G_] + [BRIDGE_WEST_END, BRIDGE_EAST_END, (-3.0, BRIDGE_Y), (3.0, BRIDGE_Y), DOCK]
PLAZAS = [(PLAZA0, 0.0), (PLAZA1, 1.0)]

# No farms stand here at the start (Builders raise them): no plots, no paddocks. (The code that fences and plants
# them is kept: put entries back to have them again.)
#          x0     y0     x1     y1    z    what      gate side
PLOTS = []
# the cottages' paddocks: (key, (x0, y0, x1, y1), z, the gap in the fence (side, from, to), what grows)
PADDOCKS = []

# How many trees (the budget). Faces each, near / far (assets/tree_lods.py gives each a second level of detail of
# half-metre blocks, which the level's instanced forest draws beyond some 40 m): A 101k / 9k, B 94k / 8k, C 37k / 3k,
# D 10k / 1k. The giants are landmarks; the forest is D, with C among them. Where nobody can go (the mountain, the
# highland, the ridge) there are no tree meshes at all: assets/realm_terrain.py bakes blocks of leaves into SM_RealmWoods.
TREES = dict(A=8, B=8, C=110, D=1350)
TREE_GAP = {"A": 12.0, "B": 11.0, "C": 8.0, "D": 4.8}     # the room each kind keeps (half of it towards each neighbour)
TREE_CLEAR = {"A": 3.6, "B": 3.4, "C": 2.2, "D": 1.3}     # how far a tree reaches for a building's purposes (scale 1)
BUILD_MARGIN = 1.5                                       # no tree stands within this of a building's footprint


# ---------------------------------------------------------------------------------------------------- the ground

def grid():
    a = -HALF + (np.arange(N) + 0.5) * CELL
    return np.meshgrid(a, a, indexing="ij")


def sdist(X, Y, poly, closed=True):
    """Signed distance to a polygon: > 0 inside."""
    d = dist_polyline(X, Y, poly + [poly[0]] if closed else poly)
    return np.where(in_poly(X, Y, poly), d, -d)


def river_dist(X, Y, stretches):
    d = np.full(X.shape, 1e9)
    for pts, hw in stretches:
        d = np.minimum(d, dist_polyline(X, Y, pts) - hw)
    return d


def relief(X, Y):
    """The big shapes: the plain, the terraces, the mountain, the highland, the ridge. Also used for the backdrop's edge."""
    n1 = noise2(X, Y, 14.0, 3)
    n2 = noise2(X, Y, 7.0, 17)
    h = np.zeros(X.shape)
    dm = sdist(X, Y, MOUNTAIN) + (n2 - 0.5) * 3.0
    mountain = dm > 0
    # the west terrace (the player's mine stands on it, against the sea cliff)
    h = np.where((X < TERRACE_W[0] + (n1 - 0.5) * 4.0) & (Y > TERRACE_W[1]) & ~mountain, 1.0, h)
    # the enemy's plateau
    de = sdist(X, Y, PLATEAU) + (n2 - 0.5) * 3.0
    h = np.where(de > 0, 1.0, h)
    # (its north terrace, a metre higher, is gone with the archery range that stood on it and the steps of its road: it
    # could not be reached any more. That ground is the plateau's now, level with the rest, to build on.)
    # the highland north of the first fall (its edge is straight where the river crosses it)
    dax = np.abs(X - FALL1_X)
    dh = Y - (FALL1_Y + (n1 - 0.5) * 5.0 * np.clip((dax - 5.0) / 10.0, 0, 1))
    high = (dh > 0) & ~mountain
    n3 = noise2(X, Y, 26.0, 131)
    # (the wild ground rises in one-metre blocks, each too high to step up: a cliff at its edge, then broken slopes)
    h = np.where(high, np.clip(np.round(3.0 + dh * 0.45 + (n2 - 0.5) * 3.0 + (n3 - 0.5) * 4.0), 3.0, 13.0), h)
    # the east ridge (its foot wanders)
    dr = X - (RIDGE_X + (n3 - 0.5) * 13.0 + (n1 - 0.5) * 4.0)
    # (the ridge's wall comes out to the enemy's mine, which is set into it: its front stands 2.5 m proud of the face)
    dr = np.where(np.abs(Y - BUILD["mine1"][2]) < 11.0 + (n2 - 0.5) * 2.0, np.maximum(dr, X - (BUILD["mine1"][1] - 3.0)), dr)
    h = np.where(dr > 0, np.maximum(h, np.clip(np.round(5.0 + dr * 0.6 + (n2 - 0.5) * 3.0), 5.0, 15.0)), h)
    # the mountain: a cliff of five metres all round its foot, then up to its tops in the corner
    h = np.where(mountain, np.clip(np.round(4.5 + dm * 0.27 + (n3 - 0.5) * 9.0 + (n2 - 0.5) * 3.0), 5.0, TOP - 1.0), h)
    # the shelf of the player's tower, the spur of the enemy's
    sx, sy, sr = SHELF
    shelf = np.hypot(X - sx, Y - sy) < sr + (n1 - 0.5) * 1.5
    h = np.where(shelf, BUILD["tower0"][3], h)
    kx, ky, kr = KNOLL
    h = np.where(np.hypot(X - kx, Y - ky) < kr + (n1 - 0.5) * 1.5, BUILD["tower1"][3], h)
    # the crag of the east bank
    cx, cy, cr = CRAG
    dcr = np.hypot(X - cx, Y - cy) - (n2 - 0.5) * 3.0
    # (a hill, not a drum: it rolls off in shelves of a metre, each a metre and a half deep, from a wandering foot;
    # References/Remake/mine_mound.png. Its lowest step is a metre: nobody walks up it)
    ang = np.arctan2(Y - cy, X - cx)
    dcr = dcr + 1.6 * np.sin(ang * 2 + 0.7) + 1.1 * np.sin(ang * 3 + 2.1) + 0.7 * np.sin(ang * 5 + 4.0)
    h = np.where(dcr < cr, np.clip(np.ceil((cr - dcr) / 1.5), 1.0, 9.0), h)
    crag = dcr < cr
    # the rocks of the two home mines
    for (cx, cy, cr) in HOME_CRAGS:
        dcr = np.hypot(X - cx, Y - cy) - (n2 - 0.5) * 3.0
        crag |= dcr < cr
        h = np.where(dcr < cr, 5.0, h)
        h = np.where(dcr < cr - 5.0, 7.0, h)
        h = np.where(dcr < cr - 9.0, 9.0, h)
    return h, dict(n1=n1, n2=n2, mountain=mountain, dm=dm, de=de, high=high, ridge=dr > 0, crag=crag, shelf=shelf)


def path_fields(X, Y):
    """For every cell: the path it lies on (height, surface, whether on steps). As town_layout.path_fields."""
    z = np.full(X.shape, np.nan)
    surf = np.full(X.shape, -1, np.int8)
    steps = np.zeros(X.shape, bool)
    best = np.full(X.shape, 1e9)
    rag = (noise2(X, Y, 2.2, 5) - 0.5) * 0.7
    for pts, w, s in PATHS:
        for a, b in zip(pts[:-1], pts[1:]):
            d, t = seg_dist(X, Y, a, b)
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            dz = b[2] - a[2]
            if abs(dz) > 1e-6:
                run = min(L, abs(dz) / 0.25 * 0.5)                       # quarter-block risers, half-metre treads
                u = np.clip((t * L - (L - run) / 2.0) / run, 0, 1)
                zz = a[2] + np.sign(dz) * np.floor(u * abs(dz) / 0.25 + 0.5) * 0.25
                zz = np.clip(zz, min(a[2], b[2]), max(a[2], b[2]))
                inside = d < w + 0.1
                st = inside & (u > 0) & (u < 1)
            else:
                zz = np.full(X.shape, a[2])
                inside = (d + rag) < w
                st = np.zeros(X.shape, bool)
            take = inside & (d < best)
            z = np.where(take, zz, z)
            surf = np.where(take, STONE if abs(dz) > 1e-6 and s == COBBLE else s, surf)
            steps = np.where(take, st, steps)
            best = np.where(take, d, best)
    for (p, pz_) in PLAZAS:
        plaza = (np.hypot(X - p[0], Y - p[1]) + rag) < 4.2
        z = np.where(plaza & np.isnan(z), pz_, z)
        surf = np.where(plaza & (surf < 0), COBBLE, surf)
    return z, surf, steps


def meadow(X, Y):
    """The open ground to build on round each side's buildings: 0 outside, 1 well inside (ragged edges)."""
    rag = (noise2(X, Y, 9.0, 151) - 0.5) * 10.0
    m = np.zeros(np.shape(X))
    for (cx, cy, r) in MEADOWS0 + MEADOWS1:
        m = np.maximum(m, np.clip((r - np.hypot(X - cx, Y - cy) + rag) / 4.0, 0.0, 1.0))
    return m


def rect_mask(X, Y, cx, cy, hx, hy):
    return (np.abs(X - cx) <= hx) & (np.abs(Y - cy) <= hy)


def dock_deck(X, Y):
    """The dock's planks (SM_Dock at yaw -90: its own -Y runs west): the walkway 3 m wide and 9 m long, the head 8 x 3.5 m."""
    lx, ly = -(Y - DOCK[1]), X - DOCK[0]              # the asset's own x, y
    return ((np.abs(lx) <= 1.5) & (ly <= 0.25) & (ly >= -9.0)) | ((np.abs(lx) <= 4.0) & (ly <= -9.0) & (ly >= -12.5))


def heights():
    X, Y = grid()
    rag = (noise2(X, Y, 6.0, 11) - 0.5) * 3.0 + (noise2(X, Y, 24.0, 12) - 0.5) * 7.0
    rag = rag * np.clip((np.hypot(X - DOCK[0], Y - DOCK[1]) - 9.0) / 10.0, 0.0, 1.0)      # (the dock's cliff is where the plan says)
    dc = sdist(X, Y, COAST) + rag                                           # > 0 on the land, metres from the coast
    for (ix, iy, r) in ISLETS:
        dc = np.maximum(dc, r - np.hypot(X - ix, Y - iy) + rag * 0.5)
    for mr in mound_rects():                                                # (ground under the whole of a mine's hill, where the coast is near)
        dc = np.where(in_rect(X, Y, mr, 1.0), np.maximum(dc, 3.0), dc)
    land = dc > 0

    h, R = relief(X, Y)
    n1 = R["n1"]
    for k, (crest, reach, seed) in HILLS.items():
        mh = minehill.hill(X, Y, BUILD[k][1], BUILD[k][2], BUILD[k][4], crest, reach, seed, noise2(X, Y, 7.0, 400 + seed))
        h = np.where(mh > 0, np.maximum(h, BUILD[k][3] + mh), h)
        R["crag"] = R["crag"] | (mh > 0)
    wild = R["mountain"] | R["high"] | R["ridge"] | R["crag"]
    # the woods are not flat: half-block terraces (a unit steps up them); the lawns: low platforms a quarter block high
    # (not the meadows: they are flat, to build on)
    open_ = meadow(X, Y) > 0.5
    h = np.where((noise2(X, Y, 11.0, 51) > 0.6) & ~wild & ~open_, h + 0.5, h)
    h = np.where((noise2(X, Y, 4.5, 77) > 0.58) & ~(open_ & ~wild), h + 0.25, h)
    for (ix, iy, r) in ISLETS:
        h = np.where(np.hypot(X - ix, Y - iy) < r + 2.5, -3.0 + np.round(n1 * 2) * 0.5, h)

    # ---- the plots' terraces, the buildings' pads, the rock the mines are set in
    for (x0, y0, x1, y1, z, _k, _g) in PLOTS:
        h = np.where(in_rect(X, Y, (x0, y0, x1, y1), 0.9), z, h)
    for k in BUILD:
        if BUILD[k][0] == "SM_MineCliff":
            h = np.where(behind(k, X, Y), np.maximum(h, BUILD[k][3] + 5.0), h)
    pads = [footprint(k, 1.0) for k in BUILD]
    for k, (x0, y0, x1, y1, z) in zip(BUILD, pads):
        if BUILD[k][0] == "SM_MineCliff":
            # a mine is set INTO its wall (References/Remake/mine_in_wall.png): no level pad round it, the cliff stands as
            # it is beside it and over it; only the portal's bay is cut out of the rock (minehill.embed)
            h, _bay = minehill.embed(X, Y, h, BUILD[k][1], BUILD[k][2], BUILD[k][3], BUILD[k][4])
        else:
            h = np.where(in_rect(X, Y, (x0, y0, x1, y1)), z, h)
    for (_k, pk, z, _g, _w) in PADDOCKS:
        h = np.where(in_rect(X, Y, pk, 0.5), z, h)

    # ---- paths
    pz, psurf, psteps = path_fields(X, Y)
    path = ~np.isnan(pz)
    apron = np.zeros(X.shape, bool)
    for (ax, ay) in APRONS:
        apron |= np.hypot(X - ax, Y - ay) < 1.6
    for pts, w, s in PATHS:                                               # no sinking next to a flight of steps either
        for a, b in zip(pts[:-1], pts[1:]):
            if abs(a[2] - b[2]) > 1e-6:
                apron |= seg_dist(X, Y, a, b)[0] < w + 1.2
    sunk = path & ~psteps & ~apron & (psurf == COBBLE)
    h = np.where(path, pz - np.where(sunk, 0.25, 0.0), h)

    # ---- the coast: ragged rock ledges on the cliff's edge, rocks standing in the sea at its foot
    blk = hash2(np.floor((X + 0.4 * np.floor(Y / 1.5)) / 1.5), np.floor(Y / 1.5), 7)
    blk2 = hash2(np.floor(X / 0.75), np.floor(Y / 0.75), 9)
    keep = path | apron
    for k in BUILD:
        keep |= in_rect(X, Y, footprint(k, 1.5))
    for mr in mound_rects():
        keep |= in_rect(X, Y, mr, 1.0)
    cut1 = land & (dc < 1.3) & ~keep & (blk > 0.62)
    cut2 = land & (dc < 2.6) & (dc >= 1.3) & ~keep & (blk > 0.8)
    h = np.where(cut1, h - 1.0 - np.round(blk2 * 3.0) * 0.5, h)
    h = np.where(cut2, h - 0.5 - np.round(blk2) * 0.5, h)
    h = np.where(~land, SEABED, h)
    rocks = ~land & (dc > -3.2) & (blk > 0.52)
    h = np.where(rocks, SEA - 0.5 + np.round(blk2 * 5.0) * 0.5 * (1.0 + dc / 3.2), h)

    # ---- the river (its banks are straight at the bridges, ragged elsewhere)
    calm = np.clip((np.hypot(X, Y - BRIDGE_Y) - 15.0) / 6.0, 0, 1)
    wrag = (noise2(X, Y, 3.0, 21) - 0.5) * 0.9 * calm
    d_up = river_dist(X, Y, RIVER_UP) + wrag
    d_mid = river_dist(X, Y, RIVER_MID) + wrag
    d_low = river_dist(X, Y, RIVER_LOW) + wrag
    north = Y > FALL1_Y
    beyond2 = (X - FALL2[0]) * FALL2_DIR[0] + (Y - FALL2[1]) * FALL2_DIR[1] > 0
    water_up = (d_up < 0) & north
    water_low = (d_low < 0) & beyond2 & land
    water_mid = (d_mid < 0) & ~north & ~(beyond2 & (d_low < 0)) & land & ~water_low
    d_any = np.minimum(np.where(north, d_up, 1e9), np.minimum(d_mid, np.where(beyond2, d_low, 1e9)))
    for (wm, d, lvl, deep) in ((water_up, d_up, UP, 1.25), (water_mid, d_mid, MID, 1.5), (water_low, d_low, LOW, 1.5)):
        h = np.where(wm, lvl - 0.75, h)
        h = np.where(wm & (d < -0.9), lvl - deep, h)
    # the bridges' feet stand on rock sills
    for (bx, by) in (BRIDGE_W, BRIDGE_E):
        h = np.where(water_mid & rect_mask(X, Y, bx, by, 2.6, 1.9), MID - 0.75, h)
    corridor = rect_mask(X, Y, BRIDGE_W[0], BRIDGE_Y, 4.25, 1.5) | rect_mask(X, Y, BRIDGE_E[0], BRIDGE_Y, 4.25, 1.5)
    # rock shelves a little way down the gorge's sides (not at the bridges)
    shelf = (d_any >= 0) & (d_any < 0.75) & land & ~keep & ~corridor & (blk > 0.55) & (Y < FALL1_Y - 1.0)
    h = np.where(shelf, np.minimum(h, np.where(beyond2 & (d_low < 0.75), -1.5, -0.75) - np.round(blk2) * 0.5), h)
    bank_up = (d_up >= 0) & (d_up < 1.2) & north
    h = np.where(bank_up, np.minimum(h, UP + 0.75), h)

    # ---- the divider island: flat where the crossing is, bare broken rock towards its two points
    wet = water_up | water_mid | water_low
    island = in_poly(X, Y, CHANNEL_W + CHANNEL_E[::-1]) & ~wet
    isl_rock = island & (np.abs(Y - BRIDGE_Y) > ISLAND_WALK)
    h = np.where(island & ~isl_rock & ~path, 0.0, h)
    h = np.where(isl_rock, 0.75 + np.round(blk2 * 3.0) * 0.5 + np.where(np.abs(Y - BRIDGE_Y) > 20.0, 0.5, 0.0), h)

    # ---- where nobody may go (the barriers stand on its edge): the sea and the cliff's rim over it, the river and its
    # banks, the island's rocks. Not the bridges, not the dock.
    sea = ~land & ~rocks
    deck = dock_deck(X, Y)
    hazard = ~land | (land & (dc < 2.6) & ~path) | (d_any < 0.9) | isl_rock
    hazard &= ~corridor & ~deck

    return dict(X=X, Y=Y, h=h, land=land, dc=dc, sea=sea, rocks=rocks, path=path, psurf=psurf, psteps=psteps,
                water_up=water_up, water_mid=water_mid, water_low=water_low, wet=wet, pads=pads, island=island, isl_rock=isl_rock,
                cut=(cut1 | cut2 | shelf) & ~wet, hazard=hazard, corridor=corridor, deck=deck, d_river=d_any, R=R, wild=wild, open=open_ & ~wild)


def surface(G):
    X, Y, h, R = G["X"], G["Y"], G["h"], G["R"]
    s = np.zeros(X.shape, np.int8)
    hs = hash2(np.floor(X / 0.5), np.floor(Y / 0.5), 13)
    # the mountain, the ridge, the highland, the crag: grass on the low terraces, more and more bare rock higher up
    rocky = (R["mountain"] | R["ridge"] | R["crag"] | R["high"]) & ~R["shelf"]
    bare = noise2(X, Y, 6.0, 91) + np.clip((h - 6.0) / 14.0, 0, 1) * 0.8
    s[rocky & (bare > 0.72)] = MOSSY
    s[rocky & (bare > 0.9)] = STONE
    s[G["path"]] = G["psurf"][G["path"]]
    # the plots' soil, the paddocks' trodden earth
    for (x0, y0, x1, y1, z, kind, _g) in PLOTS:
        inside = in_rect(X, Y, (x0, y0, x1, y1), -0.4)
        s[inside & (s == 0) & ((kind != "sheep") | (noise2(X, Y, 3.0, 31) > 0.52))] = DIRT
    for (_k, pk, _z, _g, _w) in PADDOCKS:
        s[in_rect(X, Y, pk, -0.3) & (s == 0) & (noise2(X, Y, 3.5, 31) > 0.6)] = DIRT
    s[(noise2(X, Y, 5.0, 41) > 0.82) & (s == 0) & G["land"]] = DIRT
    s[(noise2(X, Y, 3.0, 61) > 0.84) & (s == 0) & G["land"]] = MOSSY
    # the island
    isl = G["island"] & ~G["path"]
    s[isl] = np.where(hs[isl] > 0.55, MOSSY, np.where(hs[isl] > 0.25, STONE, GRASS))
    s[G["isl_rock"]] = np.where(hs[G["isl_rock"]] > 0.5, STONE, MOSSY)
    # the coast's ledges and rocks, the gorge's shelves
    cut = G["cut"]
    s[cut] = np.where(hs[cut] > 0.5, STONE, MOSSY)
    s[G["rocks"]] = np.where(hs[G["rocks"]] > 0.6, MOSSY, STONE)
    s[G["sea"]] = GRAVEL
    s[G["wet"]] = GRAVEL
    return s


def ground(h, x, y):
    i = int(np.clip((x + HALF) / CELL, 0, N - 1))
    j = int(np.clip((y + HALF) / CELL, 0, N - 1))
    return float(h[i, j])


# ---------------------------------------------------------------------------------------------------- things

class Solids(list):
    """What stands where, (x, y, r): a list (town_layout's Scene appends to it) that can also be asked quickly."""
    B = 8.0

    def __init__(self):
        super().__init__()
        self.cells = {}

    def append(self, it):
        super().append(it)
        self.cells.setdefault((int(it[0] // self.B), int(it[1] // self.B)), []).append(it)

    def hits(self, x, y, r, reach=4.0):
        """Does a thing of radius r at (x, y) touch one of them? (reach: the biggest radius any of them has)"""
        k = int((r + reach) // self.B) + 1
        ci, cj = int(x // self.B), int(y // self.B)
        for i in range(ci - k, ci + k + 1):
            for j in range(cj - k, cj + k + 1):
                for (a, b, q) in self.cells.get((i, j), ()):
                    if math.hypot(x - a, y - b) < r + q:
                        return True
        return False


class Scene(T.Scene):
    """town_layout's Scene on this map's ground: fences, trees and buildings are placed the same way."""

    def __init__(self, G, s):
        super().__init__(G, s)
        self.solid = Solids()
        self.trees = []                    # (x, y, kind, scale)

    def add(self, mesh, x, y, yaw=0.0, scale=1.0, z=None, dz=0.0, group="village", tags=None, r=None, team=None):
        if not os.path.exists(os.path.join(MESHES, mesh + ".gltf")):
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

    def building(self, mesh, x, y, z, yaw, team, group="buildings"):
        self.add(mesh, x, y, yaw, z=z, group=group, team=team)
        for pr in meta(mesh).get("props", []):
            px, py = rot(pr["pos"][0], pr["pos"][1], yaw)
            self.add(pr["mesh"], x + px, y + py, yaw + float(pr.get("yaw", 0.0)), float(pr.get("scale", 1.0)), z=z + pr["pos"][2], group="props")

    def tree(self, kind, x, y, yaw=0.0, scale=1.0, group="forest"):
        super().tree(kind, x, y, yaw, scale, group)
        self.trees.append((x, y, kind, scale))


def wood(x, y):
    """How wooded a place is, 0..1 (the big woods lie between the bases and the river, and round the meadows)."""
    w = 0.3                                            # light woodland everywhere the meadows are not
    if -112 < x < -20 and -44 < y < 186:               # the west bank's forest
        w = 1.0
    elif 16 < x < 74 and -52 < y < 186:                # the east bank's
        w = 1.0
    elif 16 < x < 176 and y < -12 and not (x > 80 and y > -64 + (x - 80) * 0.55):    # the south-east lowland
        w = 0.8
    elif y < -138 or x < -158:                         # the player's coast
        w = 0.5
    elif x > 164 or y > 172:                           # the foot of the ridge and of the highland
        w = 0.7
    return w


def rect_gap(x, y, f):
    """How far a point is from a rectangle (x0, y0, x1, y1, ...): 0 inside."""
    return math.hypot(max(f[0] - x, 0.0, x - f[2]), max(f[1] - y, 0.0, y - f[3]))


def tree_blocked(x, y, kind, scale=1.0, margin=BUILD_MARGIN):
    """Would this tree stand in or right against a building (its footprint and its gate)? The rule the game's
    AVLForest::ClearTrees applies when a building is put down, applied to the plan."""
    reach = TREE_CLEAR[kind] * scale + margin
    for k in BUILD:
        if rect_gap(x, y, footprint(k)) < reach:
            return k
    for k, (gx, gy) in GATE.items():
        if math.hypot(x - gx, y - gy) < reach + 3.0:
            return k + " gate"
    return None


def things(G, s):
    X, Y, h, R = G["X"], G["Y"], G["h"], G["R"]
    sc = Scene(G, s)
    rng = np.random.default_rng(20261122)
    wild = G["wild"]
    open_ = G["open"]

    # ---- the buildings (with what their sidecars ask to have placed with them)
    for key, (mesh, x, y, z, yaw, team) in BUILD.items():
        n0 = len(sc.items)
        sc.building(mesh, x, y, z - 0.01, yaw, team)
        if mesh == "SM_MineCliff":
            sc.items[n0].setdefault("tags", []).append("Mounded")
        if key in MOUNDED:
            sc.add("SM_MineMound", x, y, yaw, z=z, group="rocks", tags=["MineMound"])
    sc.add("SM_Bridge", BRIDGE_W[0], BRIDGE_W[1], 90.0, z=0.04, group="buildings", team="Neutral")
    sc.add("SM_Bridge", BRIDGE_E[0], BRIDGE_E[1], 90.0, z=0.04, group="buildings", team="Neutral")
    sc.add("SM_PlazaBanner", PLAZA0[0], PLAZA0[1], z=0.0, r=1.3, team=0)
    sc.add("SM_PlazaBanner", PLAZA1[0], PLAZA1[1], z=1.0, r=1.3, team=1)
    sc.building("SM_Dock", DOCK[0], DOCK[1], DOCK_Z, -90.0, 0)
    moor = meta("SM_Dock").get("moor", [2.9, -5.9, -1.0, 90.0])
    mx, my = rot(moor[0], moor[1], -90.0)
    sc.add("SM_Boat", DOCK[0] + mx, DOCK[1] + my, moor[3] - 90.0, z=SEA + 0.02, group="props")

    def crops(x0, y0, x1, y1, z, mesh="SM_Wheat", step=1.0, scale=(0.92, 1.1), jitter=0.06):
        nx, ny = max(1, int(round((x1 - x0) / step))), max(1, int(round((y1 - y0) / step)))
        for i in range(nx):
            for j in range(ny):
                x = x0 + (i + 0.5) * (x1 - x0) / nx + rng.uniform(-jitter, jitter)
                y = y0 + (j + 0.5) * (y1 - y0) / ny + rng.uniform(-jitter, jitter)
                m = mesh if isinstance(mesh, str) else mesh[(i if len(mesh) < 4 else j) % len(mesh)]
                sc.add(m, x, y, float(rng.integers(0, 4)) * 90.0 + rng.uniform(-8, 8), float(rng.uniform(*scale)), z=z, group="farm")

    # ---- the cottages' paddocks: wheat or sheep, hay
    for (key, pk, z, gap, what) in PADDOCKS:
        f = footprint(key)
        sc.fence(pk, z, gap, skip=[f])
        x0, y0, x1, y1 = pk
        # the free strip of the paddock: beside the cottage, on its longer free side
        if (f[0] - x0) >= (x1 - f[2]):
            a = (x0 + 0.7, y0 + 0.7, f[0] - 0.9, y1 - 0.7)
        else:
            a = (f[2] + 0.9, y0 + 0.7, x1 - 0.7, y1 - 0.7)
        if what == "wheat":
            crops(a[0], a[1], a[2], a[3], z)
        else:
            for _ in range(3):
                sc.add("SM_Sheep", rng.uniform(a[0] + 0.5, a[2] - 0.5), rng.uniform(a[1] + 0.5, a[3] - 0.5), float(rng.uniform(0, 360)), z=z, group="farm", r=0.6)
            sc.add("SM_Trough", a[0] + 0.6, a[3] - 0.8, 90.0, z=z, group="farm", r=0.8)
        sc.add("SM_HayStack", (a[0] + a[2]) / 2.0, a[1] + 0.4, 20.0, z=z, group="farm", r=0.9) if what != "wheat" else None

    # ---- the plots: fenced, each with its gate on a plank path
    for (x0, y0, x1, y1, z, kind, gs) in PLOTS:
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        gap = (gs, cx - 1.0, cx + 1.0) if gs in "sn" else (gs, cy - 1.0, cy + 1.0)
        sc.fence((x0, y0, x1, y1), z, gap)
        if kind == "wheat":
            crops(x0 + 0.7, y0 + 0.7, x1 - 0.7, y1 - 0.7, z)
        elif kind == "greens":
            crops(x0 + 0.8, y0 + 0.8, x1 - 0.8, y1 - 0.8, z, mesh=["SM_Bush_C", "SM_Flowers_B", "SM_Bush_C", "SM_Flowers_D", "SM_GrassTuft_C"],
                  step=0.9, scale=(0.55, 0.7), jitter=0.03)
        else:
            for k in range(4):
                sc.add("SM_Sheep", cx + rng.uniform(-2.8, 2.8), cy + rng.uniform(-1.8, 1.8), float(rng.uniform(0, 360)), z=z, group="farm", r=0.6)
            sc.add("SM_Trough", x0 + 1.0, y1 - 0.9, 0.0, z=z, group="farm", r=0.8)
            sc.add("SM_HayStack", x0 + 1.2, y0 + 1.1, 15.0, z=z, group="farm", r=0.9)
            sc.add("SM_HayBale", x0 + 2.8, y0 + 0.9, 80.0, z=z, group="farm", r=0.6)

    # ---- clutter (by hand: a few things at each side's gates, the mines' aprons, the dock's stair head)
    def near(p, dx, dy):
        return (p[0] + dx, p[1] + dy)

    clutter = [("SM_CrateStack", near(DOCK, 12.5, 2.6), 20), ("SM_Barrel", near(DOCK, 13.8, 2.8), 0), ("SM_Crate", near(DOCK, 11.0, -2.8), 15),
               ("SM_Signpost", near(ROAD_M0, 3.0, -3.6), 200), ("SM_FlowerPlanter", near(G_["castle0"], -3.6, 1.0), 0), ("SM_FlowerPlanter", near(G_["castle0"], 3.6, 1.0), 0),
               ("SM_MineCart", front("mine0", 1.1, 2.6), 90), ("SM_Barrel", front("mine0", 1.3, -2.8), 0), ("SM_Crate", front("mine0", 2.3, -3.6), 30),
               ("SM_MineCart", near(G_["mine_w"], 0.6, 3.0), 0), ("SM_Crate", near(G_["mine_w"], 0.2, -3.2), 30),
               ("SM_MineCart", near(G_["mine_e"], -0.6, -3.0), 0), ("SM_Crate", near(G_["mine_e"], -0.2, 3.2), 30),
               ("SM_MineCart", front("mine1", 1.6, 3.0), 0), ("SM_Barrel", front("mine1", 2.2, -3.0), 0), ("SM_Crate", front("mine1", 1.2, -3.9), 30),
               ("SM_Signpost", near(ROAD_M1, 3.4, -2.6), 20),
               ("SM_Signpost", (-108.0, 21.0), 100),
               ("SM_FlowerPlanter", near(G_["castle1"], -1.0, 3.6), 90), ("SM_FlowerPlanter", near(G_["castle1"], -1.0, -3.6), 90)]
    for (mesh, (x, y), yaw) in clutter:
        sc.add(mesh, x, y, yaw, r=0.9)

    def cell(x, y):
        return int(np.clip((x + HALF) / CELL, 2, N - 3)), int(np.clip((y + HALF) / CELL, 2, N - 3))

    def level(x, y, r=2):
        i, j = cell(x, y)
        i0, i1, j0, j1 = max(i - r, 0), min(i + r, N - 1), max(j - r, 0), min(j + r, N - 1)
        return h[i0, j] == h[i, j] == h[i1, j] == h[i, j0] == h[i, j1]

    yards = [pk for (_k, pk, _z, _g, _w) in PADDOCKS] + [p[:4] for p in PLOTS]
    rects = [p[:4] for p in G["pads"]] + yards + mound_rects()

    def on_pad(x, y, pad=0.6):
        for (x0, y0, x1, y1) in rects:
            if x0 - pad < x < x1 + pad and y0 - pad < y < y1 + pad:
                return True
        return math.hypot(x, y - BRIDGE_Y) < 16.0 or math.hypot(x - PLAZA0[0], y - PLAZA0[1]) < 5.5 or math.hypot(x - PLAZA1[0], y - PLAZA1[1]) < 5.5

    path_d = np.full(X.shape, 1e9, np.float32)
    for pts, w, _s in PATHS:
        path_d = np.minimum(path_d, dist_polyline(X, Y, [(p[0], p[1]) for p in pts]) - w)

    def free(x, y, r, path_gap=0.5, allow_pad=False, allow_hazard=False):
        i, j = cell(x, y)
        if not G["land"][i, j] or G["wet"][i, j] or s[i, j] in (COBBLE, PLANK, GRAVEL) or G["dc"][i, j] < 1.2 or G["isl_rock"][i, j]:
            return False
        if G["hazard"][i, j] and not allow_hazard:
            return False
        if path_d[i, j] < path_gap + r or not level(x, y, max(1, int(r / CELL))):
            return False
        if not allow_pad and on_pad(x, y, 0.4 + r):
            return False
        return not sc.solid.hits(x, y, r)

    # ---- lantern posts along the roads, alternating sides (not on the tracks to the neutral mines)
    for pts, w, surf in PATHS:
        if surf != COBBLE:
            continue
        run, side = 12.0, 1
        for a, b in zip(pts[:-1], pts[1:]):
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            ux, uy = (b[0] - a[0]) / max(L, 1e-6), (b[1] - a[1]) / max(L, 1e-6)
            d = 0.0
            while d < L:
                if run >= 34.0:
                    x, y = a[0] + ux * d - uy * side * (w + 1.0), a[1] + uy * d + ux * side * (w + 1.0)
                    if free(x, y, 0.45, 0.25) and abs(a[2] - b[2]) < 1e-6:
                        sc.add("SM_LanternPost", x, y, r=1.0)
                        run, side = 0.0, -side
                d += 0.5
                run += 0.5
    for (p, _z) in PLAZAS:
        for (dx, dy) in ((-4.6, 2.6), (4.4, -3.0), (3.2, 4.0), (-3.4, -4.4)):
            x, y = p[0] + dx, p[1] + dy
            if free(x, y, 0.4, 0.2, allow_pad=True):
                sc.add("SM_LanternPost_Tall", x, y, yaw=math.degrees(math.atan2(p[1] - y, p[0] - x)) + 90.0, r=1.0)
    for (bx, by) in (BRIDGE_WEST_END, BRIDGE_EAST_END):                   # a lantern at each end of the crossing
        x, y = bx + math.copysign(1.6, bx), by + 2.9
        if free(x, y, 0.4, 0.2, allow_pad=True):
            sc.add("SM_LanternPost", x, y, r=1.0)

    # ---- trees: only where people can walk (the mountain, the highland and the ridge get SM_RealmWoods: blocks of
    # leaves baked by assets/realm_terrain.py). All but none on the meadows; none in or against a building.
    radius = {"A": 1.6, "B": 1.5, "C": 1.1, "D": 0.7}
    count = dict(A=0, B=0, C=0, D=0)
    near_trees = {}

    def crowded(x, y, kind):
        ci, cj = int(x // 12.0), int(y // 12.0)
        for i in (ci - 1, ci, ci + 1):
            for j in (cj - 1, cj, cj + 1):
                for (a, b, k2) in near_trees.get((i, j), ()):
                    if math.hypot(x - a, y - b) < (TREE_GAP[kind] + TREE_GAP[k2]) / 2.0:
                        return True
        return False

    def plant(kind, x, y, scale, group="forest"):
        sc.tree(kind, x, y, yaw=float(rng.integers(0, 4)) * 90.0, scale=scale, group=group)
        near_trees.setdefault((int(x // 12.0), int(y // 12.0)), []).append((x, y, kind))
        count[kind] += 1

    hand = [("D", 0.0, BRIDGE_Y + ISLAND_WALK + 2.0), ("D", 1.0, BRIDGE_Y - ISLAND_WALK - 2.5)]        # the island's two trees
    hand += [("C" if r > 5.0 else "D", ix, iy) for (ix, iy, r) in ISLETS]                           # the islets'
    for kind, x, y in hand:
        plant(kind, x, y, float(rng.uniform(0.85, 1.0)), "frame")
    tries, lone = 0, 0
    for kind in "ABCD":
        while count[kind] < TREES[kind] and tries < 900000:
            tries += 1
            x, y = rng.uniform(-HALF + 5, HALF - 5, 2)
            i, j = cell(x, y)
            if wild[i, j]:
                continue
            w = wood(x, y) * (1.0 if kind in "CD" else 0.8)
            if open_[i, j]:                                # a lone tree here and there on the meadows, no more
                w = 0.012 if kind == "D" and lone < 28 else 0.0
            if rng.random() > w:
                continue
            if kind in "AB" and not (abs(x) < 100 and -60 < y < 170):     # the giants stand in the middle woods
                continue
            if crowded(x, y, kind) or not free(x, y, radius[kind] + 0.6, 2.6):
                continue
            scale = float(rng.uniform(0.85, 1.1))
            if tree_blocked(x, y, kind, scale) or any(math.hypot(x - ax, y - ay) < 7.5 for (ax, ay) in APRONS):
                continue
            plant(kind, x, y, scale)
            lone += 1 if open_[i, j] else 0
    # the same rule once more over everything planted (by hand too): what the game's ClearTrees would take away
    against = [(x, y, k, tree_blocked(x, y, k, sc_)) for (x, y, k, sc_) in sc.trees if tree_blocked(x, y, k, sc_)]
    if against:
        gone = {(round(x, 3), round(y, 3)) for (x, y, _k, _w) in against}
        sc.items = [it for it in sc.items if not (it["mesh"].startswith("SM_Tree") and (it["pos"][0], it["pos"][1]) in gone)]
        sc.trees = [t for t in sc.trees if (round(t[0], 3), round(t[1], 3)) not in gone]
        for (_x, _y, k, _w) in against:
            count[k] -= 1
    sc.cleared = len(against)

    # ---- undergrowth
    def scatter(n, meshes, r, group, gap, scale=(0.9, 1.15), where=None, solid=False, allow_pad=False):
        placed, t = [], 0
        while len(placed) < n and t < n * 80:
            t += 1
            x, y = rng.uniform(-HALF + 3, HALF - 3, 2)
            if where and not where(x, y):
                continue
            if not free(x, y, r, 0.3, allow_pad) or any(math.hypot(x - a, y - b) < gap for a, b in placed[-300:]):
                continue
            placed.append((x, y))
            sc.add(str(rng.choice(meshes)), x, y, yaw=float(rng.uniform(0, 360)) if group != "rocks" else float(rng.integers(0, 4)) * 90.0,
                   scale=float(rng.uniform(*scale)), group=group, r=r if solid else None)

    def tame(x, y):
        i, j = cell(x, y)
        return not wild[i, j] or R["shelf"][i, j]

    def rough(x, y):                                     # rocks and bushes keep off the meadows (mostly)
        i, j = cell(x, y)
        return not wild[i, j] and (not open_[i, j] or rng.random() < 0.08)

    scatter(110, ["SM_Rock_A", "SM_Rock_B", "SM_Rock_B", "SM_Rock_C", "SM_Rock_C", "SM_Rock_D", "SM_Rock_E"], 1.5, "rocks", 5.0, scale=(0.7, 1.0), solid=True, where=rough)
    scatter(700, ["SM_Bush_A", "SM_Bush_A", "SM_Bush_B", "SM_Bush_B", "SM_Bush_C"], 0.8, "plants", 2.2, scale=(0.8, 1.25), where=rough)
    scatter(2400, ["SM_Flowers_A", "SM_Flowers_B", "SM_Flowers_C", "SM_Flowers_D"], 0.3, "plants", 1.0, where=tame)
    scatter(6000, ["SM_GrassTuft_A", "SM_GrassTuft_B", "SM_GrassTuft_C", "SM_GrassTuft_C"], 0.3, "plants", 0.6, scale=(0.9, 1.5), where=tame)
    # rocks at the cliff's foot (nobody walks there) and on the island's two points
    k = 0
    for _ in range(20000):
        if k >= 70:
            break
        x, y = rng.uniform(-HALF + 3, HALF - 3, 2)
        i, j = cell(x, y)
        if G["rocks"][i, j] and h[i, j] > SEA - 0.3 and not sc.solid.hits(x, y, 2.5) and math.hypot(x - DOCK[0] + 6, y - DOCK[1]) > 11.0:
            sc.add(str(rng.choice(["SM_Rock_A", "SM_Rock_B", "SM_Rock_D", "SM_Rock_E"])), x, y, float(rng.integers(0, 4)) * 90.0,
                   float(rng.uniform(0.8, 1.2)), group="rocks", r=1.5)
            k += 1
    for (x, y, m) in ((0.3, 34.0, "SM_Rock_A"), (-0.6, 52.0, "SM_Rock_D"), (0.4, -14.0, "SM_Rock_B"), (-0.2, -30.0, "SM_Rock_E")):
        sc.add(m, x, y, float(rng.integers(0, 4)) * 90.0, 1.0, group="rocks", r=1.5)
    # lily pads on the sea by the dock and in the river's quiet reaches
    k = 0
    for _ in range(20000):
        if k >= 70:
            break
        x, y = rng.uniform(-HALF + 3, HALF - 3, 2)
        i, j = cell(x, y)
        if G["water_mid"][i, j] and G["d_river"][i, j] < -1.2 and y > 80 and rng.random() < 0.5:
            z = MID
        elif G["sea"][i, j] and -3.0 > G["dc"][i, j] > -9.0 and x < -165 and -150 < y < -80 and not G["deck"][i, j] and rng.random() < 0.3:
            z = SEA
        else:
            continue
        sc.add(str(rng.choice(["SM_LilyPad_A", "SM_LilyPad_B"])), x, y, float(rng.uniform(0, 360)), z=z + 0.02, group="plants")
        k += 1
    sc.tree_counts = dict(count)
    return sc


# ---------------------------------------------------------------------------------------------------- balance

def walk_map(G):
    """The ground on 50 cm cells, as the game's path grid sees it (without trees and fences): where a unit can stand,
    and its height there."""
    hz = G["hazard"]
    H = hz[0::2, 0::2] | hz[1::2, 0::2] | hz[0::2, 1::2] | hz[1::2, 1::2]
    X, Y = G["X"][0::2, 0::2] + CELL / 2, G["Y"][0::2, 0::2] + CELL / 2
    blocked = H.copy()
    for k in BUILD:
        blocked |= in_rect(X, Y, footprint(k, 0.25)[:4])
    for mr in mound_rects():                                                  # (a mine's hill: nobody walks on it; the mound's own box, less its open front)
        blocked |= in_rect(X, Y, mr, -1.5)
    hh = np.maximum(np.maximum(G["h"][0::2, 0::2], G["h"][1::2, 0::2]), np.maximum(G["h"][0::2, 1::2], G["h"][1::2, 1::2]))
    co = G["corridor"][0::2, 0::2] | G["corridor"][1::2, 1::2]                # the bridges' decks
    hh = np.where(co, 0.0, hh)
    return ~blocked, hh, X, Y


def balance(G, verbose=False, trees=()):
    """Walking distances (metres, shortest routes over the ground) from each side's castle door, and the ground each
    side has to build on. None without scipy."""
    try:
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import dijkstra
    except Exception:
        return None
    ok, hh, X, Y = walk_map(G)
    n = ok.shape[0]
    idx = np.arange(n * n).reshape(n, n)
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
    for (di, dj) in ((1, 1), (1, -1), (-1, 1), (-1, -1)):                 # a diagonal only between joined sides
        link(di, dj, 0.5 * math.sqrt(2.0), step[(di, 0)] & step[(0, dj)])
    g = coo_matrix((np.concatenate(wts), (np.concatenate(rows), np.concatenate(cols))), shape=(n * n, n * n)).tocsr()

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

    pts = dict(castle0=G_["castle0"], castle1=G_["castle1"], bridge_w=(BRIDGE_WEST_END[0] - 1.0, BRIDGE_Y), bridge_e=(BRIDGE_EAST_END[0] + 1.0, BRIDGE_Y),
               mine0=G_["mine0"], mine1=G_["mine1"], mine_w=G_["mine_w"], mine_e=G_["mine_e"], tower0=G_["tower0"], tower1=G_["tower1"])
    nodes = {k: node(v) for k, v in pts.items()}
    D = dijkstra(g, directed=False, indices=[nodes["castle0"], nodes["castle1"], nodes["mine0"], nodes["mine1"]])

    def d(src, k):
        v = float(D[src, nodes[k]])
        return None if not math.isfinite(v) else round(v, 1)

    rep = dict(
        player=dict(bridge=d(0, "bridge_w"), own_mine=d(0, "mine0"), tower=d(0, "tower0"),
                    neutral_mine_own_bank=d(0, "mine_w"), neutral_mine_far_bank=d(0, "mine_e"),
                    enemy_castle=d(0, "castle1"), mine_to_tower=d(2, "tower0"), mine_to_bridge=d(2, "bridge_w"),
                    tower_to_mine_straight=round(math.hypot(BUILD["tower0"][1] - G_["mine0"][0], BUILD["tower0"][2] - G_["mine0"][1]), 1)),
        enemy=dict(bridge=d(1, "bridge_e"), own_mine=d(1, "mine1"), tower=d(1, "tower1"),
                   neutral_mine_own_bank=d(1, "mine_e"), neutral_mine_far_bank=d(1, "mine_w"),
                   enemy_castle=d(1, "castle0"), mine_to_tower=d(3, "tower1"), mine_to_bridge=d(3, "bridge_e"),
                   tower_to_mine_straight=round(math.hypot(BUILD["tower1"][1] - G_["mine1"][0], BUILD["tower1"][2] - G_["mine1"][1]), 1)),
        tower_height_over_base=dict(player=BUILD["tower0"][3] - BUILD["castle0"][3], enemy=BUILD["tower1"][3] - BUILD["castle1"][3]),
        note="metres walked from the castle's door by the shortest route over the ground (50 cm cells, steps of at most 50 cm, "
             "no water, no building; trees and fences not counted)")

    # ---- the ground to build on: what can be walked to from the castle and is nearer (on foot) to it than to the
    # other one, less the roads, the buildings (and 2 m round them), the plots and the paddocks. "meadow": the flat
    # open ground of MEADOWS; "open": no tree within 4 m; "wooded": the rest (a building clears its trees).
    d0, d1 = D[0].reshape(n, n), D[1].reshape(n, n)
    taken = G["path"][0::2, 0::2] | G["path"][1::2, 1::2] | G["corridor"][0::2, 0::2] | G["deck"][0::2, 0::2]
    for k in BUILD:
        taken |= in_rect(X, Y, footprint(k, 2.0)[:4])
    for (_k, pk, _z, _g, _w) in PADDOCKS:
        taken |= in_rect(X, Y, pk, 0.5)
    for pl in PLOTS:
        taken |= in_rect(X, Y, pl[:4], 0.5)
    # level ground: the same height 1.5 m either way (a building wants a flat floor)
    flat = np.ones((n, n), bool)
    for (di, dj) in ((3, 0), (-3, 0), (0, 3), (0, -3)):
        flat &= np.roll(np.roll(hh, di, 0), dj, 1) == hh
    treed = np.zeros((n, n), bool)
    for (tx, ty, _kind, _sc) in trees:
        i, j = int((tx + HALF) / 0.5), int((ty + HALF) / 0.5)
        i0, i1, j0, j1 = max(0, i - 8), min(n, i + 9), max(0, j - 8), min(n, j + 9)
        treed[i0:i1, j0:j1] |= np.hypot(X[i0:i1, j0:j1] - tx, Y[i0:i1, j0:j1] - ty) < 4.0
    mdw = G["open"][0::2, 0::2]
    area = {}
    for side, mine_, other in (("player", d0, d1), ("enemy", d1, d0)):
        own = ok & np.isfinite(mine_) & (mine_ < other) & ~taken & flat
        area[side] = dict(total=int(own.sum() * 0.25), meadow=int((own & mdw).sum() * 0.25), open=int((own & ~treed).sum() * 0.25),
                          wooded=int((own & treed).sum() * 0.25), trees=int(sum(1 for (tx, ty, _k, _s) in trees
                                                                                 if own[min(n - 1, int((tx + HALF) / 0.5)), min(n - 1, int((ty + HALF) / 0.5))])))
    rep["buildable_m2"] = dict(area, note="square metres of level ground a side can walk to and is nearer to than its foe, less roads, buildings, "
                                          "plots and paddocks. meadow: the flat open ground round its buildings; open: no tree within 4 m; "
                                          "wooded: under trees (a building clears them)")
    if verbose:
        print("%-24s %8s %8s" % ("from the castle door to", "player", "enemy"))
        for k in rep["player"]:
            print("%-24s %8s %8s" % (k, rep["player"][k], rep["enemy"][k]))
        print("%-24s %8s %8s" % ("ground to build on, m2", "player", "enemy"))
        for k in ("total", "meadow", "open", "wooded", "trees"):
            print("%-24s %8s %8s" % (k, area["player"][k], area["enemy"][k]))
    return rep


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
        if key in GATE:
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
                              buildings=b, start=dict(point(start), yaw=start[2], yaw_ue=-start[2]), rally=point(rally), plaza=point(plaza),
                              bridge_end=point(BRIDGE_WEST_END if team == 0 else BRIDGE_EAST_END))
    out["neutral"] = dict(buildings=[entry(k) for k in BUILD if BUILD[k][5] == "Neutral"])
    out["axes"] = "pos: metres, +X east, +Y north, +Z up, yaw counter-clockwise from above (fronts face -Y at yaw 0). " \
                  "pos_ue / yaw_ue: Unreal centimetres (x, -y, z) and degrees (-yaw)."
    out["tags"] = "every building actor: Selectable, Name:<kind>, Team:0|1|Neutral. Markers (TargetPoint actors): TeamStart:0, TeamStart:1, Rally:0, Rally:1."
    return out


def build(write=True, verbose=False):
    G = heights()
    s = surface(G)
    sc = things(G, s)
    h = G["h"]
    tm = teams(G)
    markers = []
    for t in ("0", "1"):
        markers.append(dict(tag="TeamStart:" + t, pos=tm[t]["start"]["pos"], yaw=tm[t]["start"]["yaw"]))
        markers.append(dict(tag="Rally:" + t, pos=tm[t]["rally"]["pos"], yaw=tm[t]["start"]["yaw"]))
    bal = balance(G, verbose, sc.trees)
    layout = dict(
        camera=dict(pos=list(C.POS), target=list(C.TARGET), hfov=C.HFOV, az=C.AZ, el=C.EL, width=C.W, height=C.H),
        terrain=dict(cell=CELL, half=HALF, zmin=ZMIN, top=TOP, sea=SEA, seabed=SEABED, up=UP, mid=MID, low=LOW, surfaces=SURF),
        spawn=dict(pos=[SPAWN[0], SPAWN[1], ground(h, SPAWN[0], SPAWN[1])], yaw=SPAWN[2]),
        places=dict(plaza=PLAZA0, plaza1=PLAZA1, glade=(-56.0, 40.0), bridge_w=BRIDGE_W, bridge_e=BRIDGE_E, bridge_west_end=BRIDGE_WEST_END,
                    bridge_east_end=BRIDGE_EAST_END, dock=DOCK, fall1=(FALL1_X, FALL1_Y), fall2=FALL2, fall3=(116.0, -145.0),
                    **{k: (v[1], v[2]) for k, v in BUILD.items()}),
        gates=GATE,
        teams=tm,
        markers=markers,
        balance=bal,
        meadows=dict(player=MEADOWS0, enemy=MEADOWS1),
        trees=dict(count=sc.tree_counts, clear=TREE_CLEAR, margin=BUILD_MARGIN, cleared_at_build=sc.cleared,
                   faces=int(sum(sc.tree_counts[k] * (meta("SM_Tree2_%s_Trunk" % k).get("faces", 0) + meta("SM_Tree2_%s_Leaves" % k).get("faces", 0)) for k in "ABCD"))),
        instances=sc.items,
    )
    if write:
        os.makedirs(OUT, exist_ok=True)
        if bal is None and os.path.exists(os.path.join(OUT, "realm.json")):       # Blender has no scipy: keep the measured routes
            try:
                layout["balance"] = json.load(open(os.path.join(OUT, "realm.json"))).get("balance")
            except Exception:
                pass
        with open(os.path.join(OUT, "realm.json"), "w") as f:
            json.dump(layout, f)
        np.savez_compressed(os.path.join(OUT, "realm_terrain.npz"), h=h.astype(np.float32), s=s, hazard=G["hazard"])
        counts = {}
        for it in sc.items:
            counts[it["mesh"]] = counts.get(it["mesh"], 0) + 1
        faces = sum(meta(m).get("faces", 0) * n for m, n in counts.items())
        print("realm: %d instances, %d kinds, %.2f M faces; trees %s = %.2f M faces, %d taken away from buildings; not built yet: %s" % (
            len(sc.items), len(counts), faces / 1e6, sc.tree_counts, layout["trees"]["faces"] / 1e6, sc.cleared, ", ".join(sorted(sc.missing)) or "none"))
    return layout, G, s


def debug(layout, G, s, path=None):
    """The plan from above (north up), 2 px per metre: surfaces, heights, water, hazard edge, meadows (paler), buildings, trees."""
    from PIL import Image, ImageDraw
    h = G["h"]
    cols = np.array([(96, 150, 50), (190, 160, 110), (140, 100, 60), (120, 120, 120), (150, 150, 150), (110, 140, 100), (200, 140, 70)], np.uint8)
    rgb = cols[s].astype(np.float32) * (0.7 + 0.03 * np.clip(h, -3, 22))[:, :, None]
    rgb[G["open"] & (s == 0)] *= 1.18
    rgb[G["water_up"]] = (110, 180, 240)
    rgb[G["water_mid"]] = (70, 140, 210)
    rgb[G["water_low"]] = (50, 110, 190)
    rgb[G["sea"]] = (40, 90, 160)
    hz = G["hazard"]
    edge = hz & ~(np.roll(hz, 1, 0) & np.roll(hz, -1, 0) & np.roll(hz, 1, 1) & np.roll(hz, -1, 1))
    rgb[edge] = (255, 40, 40)
    img = np.clip(rgb, 0, 255).astype(np.uint8).transpose(1, 0, 2)[::-1]
    im = Image.fromarray(img[::2, ::2])
    K = CELL * 2
    dr = ImageDraw.Draw(im)

    def px(x, y):
        return ((x + HALF) / K, (HALF - y) / K)

    for it in layout["instances"]:
        x, y, _z = it["pos"]
        if it["mesh"].endswith("_Trunk"):
            r = {"A": 6, "B": 6, "C": 4, "D": 2.4}.get(it["mesh"].split("_")[-2], 2) / K * (0.6 if "Tree2" not in it["mesh"] else 1.0)
            c = px(x, y)
            dr.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], outline=(20, 70, 20), width=1)
    for k, v in BUILD.items():
        f = footprint(k)
        a, b = px(f[0], f[3]), px(f[2], f[1])
        dr.rectangle([a[0], a[1], b[0], b[1]], outline=(255, 230, 80) if v[5] == 0 else ((255, 80, 80) if v[5] == 1 else (255, 255, 255)), width=3)
        if k in GATE:
            g = px(*GATE[k])
            dr.ellipse([g[0] - 4, g[1] - 4, g[0] + 4, g[1] + 4], fill=(255, 0, 255))
        dr.text((a[0] + 4, a[1] + 4), k, fill=(255, 255, 255))
    path = path or os.path.join(ROOT, "Saved", "realm_plan.png")
    im.save(path)
    print(path)


if __name__ == "__main__":
    L, G_all, S = build(verbose="--balance" in sys.argv or "--debug" in sys.argv)
    if "--debug" in sys.argv:
        debug(L, G_all, S)
