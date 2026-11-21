"""The highlands: the second battle map (L_Highlands), 540 m square (the realm's 416 m and 30% more each way). Pure
numpy (+ scipy for the balance report, when it is there); writes SourceArt/highland.json and
SourceArt/highland_terrain.npz (heights, surfaces, the hazard map).

    Blender -b --factory-startup --python Tools/blender/highland_layout.py             (or: import highland_layout as R; R.build())
    ../Tools/.venv/bin/python Tools/blender/highland_layout.py [--debug] [--balance]   (--debug: Saved/highland_plan.png, the
                                                                                         plan from above; --balance: the routes)

Built on town_layout.py and written after realm_layout.py (the same conventions: world metres, +X east, +Y north,
+Z up; the postcard camera, highland_cam.py, looks from the south-west).

The two sides are balanced but NOT each other's mirror: each has the same kinds of things, laid out its own way
(GROUND, HOMES, side_paths, MEADOWS, GROVES), and the plan is tuned until the walks from the two castles agree within a
few per cent (--balance). Only the middle is the same from both sides: the river and the Crown are symmetric.
Beyond the edge: the sea to the west, the south and the south-east; the highland to the north and the ridge to the
north-east, which run on into the backdrop (assets/highland_terrain.py).

  south-west   the player's home on the plain: the castle (facing south) and its plaza, the dock under the west cliff.
               In the map's corner the BLUFF: a flat-topped hill 6 m up over the sea (about 6000 m2 to build on),
               climbed by one stair that turns on a landing; a peak on its corner (26 m over it; nobody climbs that).
               The one gold mine is cut into the bluff's east foot, 94 m from the castle's door, the watch tower on a
               mound before its mouth. Nothing else: no farm, no barracks (Builders raise them).
               North of the home a spur of rock runs in from the west coast, its pass near the coast; behind it the
               north vale: the neutral mine in its tor (facing south), the track to the north bridge
  north-east   the enemy's home: the castle faces west; the dock under the east cliff. Its bluff is a long SHELF under
               the highland's wall (as much ground on top), climbed straight from the south by two flights in a line;
               the one mine is cut into the shelf's south foot, 91 m from the castle's door, its tower on a mound east
               of it. South of the home the HORN, a lone rock (24 m), stands over the pass of a spur that runs in from
               the east coast at a slant, the pass in its middle; behind it the south-east: the neutral mine in its
               tor (facing west), the track to the south bridge
  middle       the river in its gorge (water 4 m under the banks, palisades of rock up to 8 m over them along both
               sides), from the great fall off the highland (12 m) to the sea. In the middle of the map it parts round
               the CROWN: a mesa 5 m over the banks (9 m over the water), 73 x 110 m, ringed with standing stones, a
               rock in its middle with two neutral gold mines back to back (the twin lode: a Builder raises a Gold
               Mine on either and takes it). One bridge from each bank and a stair up; the top is flat and open: room
               for towers and buildings, to hold it. Two more bridges far up and far down the river are the long way
               round.

  highland.json   camera, terrain, spawn, places, gates, instances [{mesh, pos, yaw, scale, group, tags?, team?, scale3?}],
               teams (the contract with the game code: every building's kind, team, position, yaw, footprint; each
               side's start and rally point), markers (tagged points the level gets), balance (measured routes, and
               the ground each side has to build on), meadows, buildable (the named flat grounds), trees (the budget)
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import highland_cam as C
import minehill
import town_layout as T
from town_layout import hash2, noise2, seg_dist, dist_polyline, in_poly, in_rect, meta, rot

ROOT = T.ROOT
OUT = T.OUT
MESHES = T.MESHES
NAME = "highland"

CELL = 0.25
HALF = 270.0                      # the world is 540 m square
N = int(2 * HALF / CELL)
ZMIN = -10.0
TOP = 46.0
SEA = -7.5                        # the sea's surface; its bed is SEABED
SEABED = -9.0
UP = 7.75                         # the upper river, on the highland
MID = -4.0                        # the gorge
LOW = -6.0                        # the last reach, after the second fall

SURF = T.SURF
GRASS, COBBLE, DIRT, GRAVEL, STONE, MOSSY, PLANK = range(7)


def M(p):
    """The other side's point: half a turn about the middle of the map (a height, if there is one, stays)."""
    return (-p[0], -p[1]) + tuple(p[2:])


def MR(r):
    """The other side's rectangle (x0, y0, x1, y1)."""
    return (-r[2], -r[3], -r[0], -r[1])


# ---------------------------------------------------------------------------------------------------- the plan

# the coast: the land's outline (it runs off the map to the north and, north of y = 100, to the east)
COAST = [(-244, 300), (300, 300), (300, 104), (246, 100), (242, 80), (241, 64), (241, 40), (245, 10), (240, -30), (246, -70), (238, -110),
         (244, -150), (236, -190), (222, -214), (196, -228), (160, -236), (120, -232), (80, -238), (40, -234), (0, -238), (-40, -234),
         (-80, -238), (-120, -234), (-160, -238), (-200, -234), (-226, -222), (-240, -196), (-244, -160), (-240, -120), (-242, -80),
         (-241, -60), (-241, -44), (-246, -10), (-240, 30), (-246, 70), (-240, 110), (-246, 150), (-240, 190), (-244, 230), (-240, 262)]
ISLETS = [(-258, -150, 5.0), (-257, 20, 4.0), (-140, -257, 5.5), (-20, -258, 6.0), (100, -256, 6.5), (200, -250, 5.0), (258, -130, 5.0),
          (257, -20, 4.5), (-258, 180, 4.5)]

# ---- each side's ground. The two sides are NOT each other's mirror: each has the same kinds of things (a bluff to build
# on with one stair and the second mine on top, a first mine with its tower, a spur with a pass, a far country with a
# neutral mine) laid out its own way, and the plan is tuned until the walks from the two castles agree (balance()).
BLUFF_Z = 6.0
MOUND_Z = 3.0
GROUND = (
    dict(   # ---- the player's (south-west): the bluff fills the map's corner over the sea, a peak on its corner
        bluff=[(-262, -262), (-146, -262), (-136, -200), (-131, -191), (-131, -165), (-138, -160), (-158, -136), (-262, -136)],     # (it comes out to the mine set into its east face)
        peaks=[(-218.0, -208.0, 30.0, BLUFF_Z, 26.0)],        # rocks nobody climbs: x, y, radius, the ground they stand on, how high
        landing=(-176.0, -131.0, 8.0),                        # the shelf half way up the bluff's stair (at BLUFF_Z / 2)
        mound=(-106.0, -176.0, 10.0),                         # the watch tower's mound
        spur=([(-266.0, 52.0), (-96.0, 52.0)], 13.0),         # the wall of rock: its crest, its half width
        gap=((-171.0, 20.0), (-171.0, 84.0), 11.0),           # the pass through it: from, to, half width
        tor=(-150.0, 162.0, 18.0),                            # the rock of its bank's neutral mine
        crags=[(-70.0, 92.0, 12.0), (-204.0, -8.0, 11.0), (-58.0, -206.0, 9.0), (-214.0, 196.0, 14.0)]),
    dict(   # ---- the enemy's (north-east): the bluff is a long shelf under the highland's wall, a buttress of that wall on
            # it; the Horn, a rock that stands alone south-east of the castle, over the pass
        bluff=[(96, 262), (96, 192), (112, 172), (136, 163), (174, 164), (175, 158), (196, 158), (198, 168), (212, 182), (222, 200), (222, 262)],     # (and to the mine in its south face)
        peaks=[(152.0, 229.0, 17.0, BLUFF_Z, 30.0), (190.0, -8.0, 21.0, 0.0, 24.0)],
        landing=(136.0, 157.0, 8.0),
        mound=(207.0, 148.0, 10.0),
        spur=([(266.0, -86.0), (204.0, -70.0), (150.0, -48.0), (114.0, -52.0)], 12.0),
        gap=((170.0, -92.0), (183.0, -26.0), 11.0),
        tor=(172.0, -130.0, 18.0),
        crags=[(60.0, -104.0, 12.0), (214.0, -160.0, 11.0), (66.0, 204.0, 9.0), (110.0, -212.0, 13.0)]),
)
BLUFF, PEAK, LANDING = GROUND[0]["bluff"], GROUND[0]["peaks"][0], GROUND[0]["landing"]
TOR0, TOR1 = GROUND[0]["tor"], GROUND[1]["tor"]

# ---- the middle
MESA_Z = 5.0
FALL1_Y = 232.0                   # the highland's edge at the river: the great fall
FALL1_X = 30.0
FALL2_Y = -200.0                  # the second fall (the river runs south there): beyond it the water lies at LOW
RIDGE_X = 242.0                   # the foot of the east ridge (it wanders), north of RIDGE_Y
RIDGE_Y = 102.0
# the bridges (7 m, running east-west): two onto the Crown, one far up the river, one far down
BRIDGES = dict(crown_w=(-40.0, 0.0), crown_e=(40.0, 0.0), north=(28.0, 170.0), south=(-28.0, -170.0))
SPIRE = (15.0, 13.0)              # the rock in the middle of the Crown: half axes (its two mines are set into it, back and sides)
PALISADE = 13.0                   # how far the gorge's rock walls reach back from the banks, at most
STONES = (30.0, 44.0, 16)         # the standing stones: the ring's half axes, how many

# The river. Each stretch: (points, half width). Narrow where a bridge crosses.
RIVER_UP = [([(46, 290), (38, 252), (FALL1_X, FALL1_Y - 0.5)], 6.0)]
_N = [(FALL1_X, FALL1_Y + 0.5), (27, 204), (28, 177), (28, 163), (24, 138), (10, 98), (0, 66)]
CHANNEL_W = [(0, 64), (-22, 57), (-37, 41), (-41, 22), (-40, 7), (-40, -7), (-41, -22), (-37, -41), (-22, -57), (0, -64)]
CHANNEL_E = [(-x, y) for (x, y) in CHANNEL_W]
_S = [M(p) for p in _N[::-1]]                            # (0, -66) ... (-28, -177), (-27, -204), (-30, -232.5)
RIVER_MID = [(_N[:3], 6.0), (_N[2:4], 2.6), (_N[3:], 6.0),
             (CHANNEL_W[:5], 4.2), (CHANNEL_W[4:6], 2.6), (CHANNEL_W[5:], 4.2),
             (CHANNEL_E[:5], 4.2), (CHANNEL_E[4:6], 2.6), (CHANNEL_E[5:], 4.2),
             (_S[:4], 6.0), (_S[3:5], 2.6), ([_S[4], (-27.2, FALL2_Y - 0.5)], 6.0)]
RIVER_LOW = [([(-27.2, FALL2_Y + 0.5), (-27, -204), (-30, -232.5), (-34, -270)], 6.0)]

# ---- buildings: name -> (mesh, x, y, z, yaw, team). Fronts face -Y at yaw 0, -X (west) at yaw -90, +X (east) at yaw 90.
KIND = {"SM_Castle": "Castle", "SM_BarracksYard": "Barracks", "SM_ArcheryHall": "Archery Range", "SM_MineCliff": "Gold Mine",
        "SM_WatchTower": "Watch Tower", "SM_FarmCottage_A": "Farm", "SM_FarmCottage_B": "Farm", "SM_Farmstead": "Farm",
        "SM_Bridge": "Bridge", "SM_PlazaBanner": "Village Banner", "SM_Dock": "Dock"}
GATE_OUT = dict(castle=0.2, mine=1.5, tower=0.3)
# (the camera looks from the south-west: every castle, farm and cottage fronts south or west, to be seen)
# Each side starts with its castle, one gold mine and the watch tower beside it; farms, barracks and the rest are raised
# by Builders. The mine is cut into the foot of the side's bluff (no hill of its own).
HOMES = (
    dict(
        castle=("SM_Castle", -128.0, -78.0, 0.0, 0.0),
        mine=("SM_MineCliff", -134.0, -178.0, 0.0, 90.0),              # in the bluff's east foot
        tower=("SM_WatchTower", -105.0, -176.0, MOUND_Z, -90.0)),
    dict(
        castle=("SM_Castle", 135.0, 86.0, 0.0, -90.0),                 # (faces west, towards the Crown)
        mine=("SM_MineCliff", 186.0, 160.5, 0.0, 0.0),                 # in the shelf's south foot
        tower=("SM_WatchTower", 208.0, 148.0, MOUND_Z, -90.0)),
)


def _bounds(mesh):
    return meta(mesh).get("bounds", [[-5, -5, 0], [5, 5, 5]])


def _front(mesh, x, y, yaw, out=0.0, along=0.0):
    dx, dy = rot(along, _bounds(mesh)[0][1] - out, yaw)
    return (round(x + dx, 3), round(y + dy, 3))


def _build():
    b = {}
    for t, home in enumerate(HOMES):
        for k, (mesh, x, y, z, yaw) in home.items():
            b[(k + str(t)) if not k.endswith("b") else (k[:-1] + str(t) + "b")] = (mesh, x, y, z, yaw, t)
    # neutral: the twin lode in the Crown's rock, a mine in each bank's far country
    b["crown_n"] = ("SM_MineCliff", 0.0, 10.0, MESA_Z, 180.0, "Neutral")
    b["crown_s"] = ("SM_MineCliff", 0.0, -10.0, MESA_Z, 0.0, "Neutral")
    b["mine_nw"] = ("SM_MineCliff", TOR0[0], TOR0[1] - TOR0[2] + 3.0, 0.0, 0.0, "Neutral")          # faces south, set into the tor (its back and both sides)
    b["mine_se"] = ("SM_MineCliff", TOR1[0] - TOR1[2] + 3.0, TOR1[1], 0.0, -90.0, "Neutral")        # faces west, set into the tor
    return b


BUILD = _build()

# Nobody builds a mine in the game: every mine is placed here, set into the ground it stands by, and the game adds
# nothing round it (a Builder claims a neutral or fallen mine where it stands). In a wall: minehill.embed, see heights().
# In a hill: HILLS. MOUNDED lists mines that get the mesh of that hill, SM_MineMound (Tools/blender/assets/
# mine_mound.py), at their own place and turn: none here. Every mine actor is tagged Mounded: it is reached, worked and
# struck at its front.
# A mine in a hill (not in a wall) has the hill's shoulders round it: minehill.hill, the terraced hill of References/
# Remake/mine_mound.png, highest behind the mine, rolling off on both its sides, open before its mouth; laid over the
# rock that stands there. key -> (crest over the mine's floor, how far its foot reaches (from, to), seed)
HILLS = dict(mine_nw=(7.0, (6.0, 10.0), 5), mine_se=(7.0, (6.0, 10.0), 9), crown_n=(6.0, (3.0, 6.0), 2), crown_s=(6.0, (3.0, 6.0), 3))
MOUNDED = ()                      # (none here: every mine of this map is set into a wall, see heights())


def mound_rects():
    return [minehill.mound_rect(BUILD[k][1], BUILD[k][2], BUILD[k][4]) for k in MOUNDED]


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
for _t in "01":
    for _k, _o in GATE_OUT.items():
        _n = (_k + _t) if not _k.endswith("b") else (_k[:-1] + _t + "b")
        GATE[_n] = front(_n, _o)
for _k in ("crown_n", "crown_s", "mine_nw", "mine_se"):
    GATE[_k] = front(_k, 2.0)
G_ = GATE

PLAZA0 = (-128.0, -92.0)
PLAZA1 = (round(G_["castle1"][0] - 8.3, 3), G_["castle1"][1])     # (west of its door)
PLAZA = (PLAZA0, PLAZA1)
SPAWN = (-128.0, -88.0, -120.0)   # x, y, facing (degrees from +X): in front of the player's castle, facing the viewer
START1 = (round(G_["castle1"][0] - 2.3, 3), G_["castle1"][1], 180.0)
RALLY0 = (-106.0, -90.0)          # where each side's troops gather: by its main road, towards the Crown (beyond its farms)
RALLY1 = (100.0, 77.0)
DOCK0 = (-241.0, -60.0)           # its land end; it runs out west (yaw -90), deck 1 m above the sea. The enemy's: east
DOCK_Z = SEA + 1.0
DOCK1 = (241.0, 60.0)
DOCKS = ((DOCK0, -90.0, 1.0), (DOCK1, 90.0, -1.0))             # land end, yaw, which way x grows towards the land


def bridge_ends(name):
    bx, by = BRIDGES[name]
    return (bx - 3.5, by), (bx + 3.5, by)


def side_paths(t):
    """One side's roads: (points [(x, y, z)], half width, surface). A change of z between two points is a flight of steps."""
    P = PLAZA[t] + (0.0,)
    B2, B1 = BLUFF_Z / 2, BLUFF_Z

    def g(k, z=0.0):
        return G_[k % t] + (z,)

    if t == 0:
        return [
            ([g("castle%d"), P], 1.8, COBBLE),
            # the main road, to the Crown's bridge
            ([P, (-104.0, -90.0, 0), (-80.0, -62.0, 0), (-62.0, -24.0, 0), (-52.0, -2.0, 0), bridge_ends("crown_w")[0] + (0,)], 2.0, COBBLE),
            # the mine road along the bluff's foot; the steps up the tower's mound
            ([P, (-122.0, -110.0, 0), (-122.0, -170.0, 0), g("mine%d")], 1.4, COBBLE),
            ([(-122.0, -176.0, 0), (-120.5, -176.0, 0), (-114.0, -176.0, MOUND_Z), g("tower%d", MOUND_Z)], 1.3, COBBLE),
            # up the bluff: a flight west along its north face to the landing, a turn, a flight south onto the top
            ([(-122.0, -110.0, 0), (-140.0, -116.0, 0), (-156.0, -127.0, 0), (-171.0, -130.0, B2), (-177.0, -133.0, B2),
              (-177.0, -147.0, B1), (-181.0, -152.0, B1)], 1.4, COBBLE),
            # the dock: down the cliff
            ([(-122.0, -110.0, 0), (-156.0, -96.0, 0), (-196.0, -64.0, 0), (-224.75, -60.0, 0), (-238.75, -60.0, DOCK_Z), (-240.75, -60.0, DOCK_Z)], 1.4, COBBLE),
            # tracks: through the spur's pass to the neutral mine, on to the far bridge; from the mine road to the near one
            ([(-80.0, -62.0, 0), (-112.0, -12.0, 0), (-150.0, 28.0, 0), (-171.0, 52.0, 0), (-166.0, 100.0, 0), G_["mine_nw"] + (0,)], 1.2, DIRT),
            ([(-166.0, 100.0, 0), (-100.0, 150.0, 0), (-30.0, 170.0, 0), bridge_ends("north")[0] + (0,)], 1.2, DIRT),
            ([(-122.0, -140.0, 0), (-96.0, -160.0, 0), (-70.0, -176.0, 0), bridge_ends("south")[0] + (0,)], 1.2, DIRT),
        ]
    return [
        ([g("castle%d"), P], 1.8, COBBLE),
        # the main road, to the Crown's bridge
        ([P, (100.0, 77.0, 0), (74.0, 50.0, 0), (58.0, 18.0, 0), (51.0, 2.0, 0), bridge_ends("crown_e")[1] + (0,)], 2.0, COBBLE),
        # up the shelf: straight north, two flights in a line with the landing between them
        ([P, (120.0, 104.0, 0), (131.0, 128.0, 0), (136.0, 141.0, 0), (136.0, 150.5, B2), (136.0, 156.0, B2), (136.0, 170.0, B1),
          (138.0, 176.0, B1)], 1.4, COBBLE),
        # the mine road north-east along the shelf's foot; the steps up the tower's mound
        ([(120.0, 104.0, 0), (152.0, 130.0, 0), (178.0, 146.0, 0), g("mine%d")], 1.4, COBBLE),
        ([g("mine%d"), (192.0, 148.0, 0), (198.6, 148.0, MOUND_Z), g("tower%d", MOUND_Z)], 1.3, COBBLE),
        # the dock: east, down the cliff
        ([P, (126.0, 73.0, 0), (160.0, 62.0, 0), (200.0, 60.0, 0), (224.75, 60.0, 0), (238.75, 60.0, DOCK_Z), (240.75, 60.0, DOCK_Z)], 1.4, COBBLE),
        # tracks: under the Horn and through the pass to the neutral mine, on to the far bridge; from the shelf road to the near one
        ([(160.0, 62.0, 0), (160.0, 4.0, 0), (164.0, -34.0, 0), (176.5, -59.0, 0), (166.0, -104.0, 0), G_["mine_se"] + (0,)], 1.2, DIRT),
        ([(166.0, -104.0, 0), (100.0, -152.0, 0), (30.0, -172.0, 0), bridge_ends("south")[1] + (0,)], 1.2, DIRT),
        ([(120.0, 104.0, 0), (96.0, 118.0, 0), (74.0, 126.0, 0), (48.0, 158.0, 0), bridge_ends("north")[1] + (0,)], 1.2, DIRT),
    ]


_cw, _ce = bridge_ends("crown_w"), bridge_ends("crown_e")
PATHS = side_paths(0) + side_paths(1) + [
    # ---- the Crown: from each bridge a landing, a stair of ten metres up through the rim, a few paces of paving
    ([_cw[1] + (0,), (-33.0, 0.0, 0), (-23.0, 0.0, MESA_Z), (-19.0, 0.0, MESA_Z)], 2.0, COBBLE),
    ([_ce[0] + (0,), (33.0, 0.0, 0), (23.0, 0.0, MESA_Z), (19.0, 0.0, MESA_Z)], 2.0, COBBLE),
]
# where a path meets something at its own level: it is not sunk there
APRONS = [G_[k] for k in G_] + [e for b in BRIDGES for e in bridge_ends(b)] + [d[0] for d in DOCKS]
PLAZAS = [(PLAZA0, 0.0), (PLAZA1, 0.0)]

# No farms stand here at the start (Builders raise them): no plots, no paddocks. (The code that fences and plants
# them is kept: put entries back to have them again.)
#          x0     y0     x1     y1    z    what      gate side
PLOTS = []
# the cottages' paddocks: (key, (x0, y0, x1, y1), z, the gap in the fence (side, from, to), what grows)
PADDOCKS = []

# The open ground to build on: meadows (x, y, radius), flat and all but bare of trees, round each side's buildings and
# at the places worth holding. The bluffs' tops and the Crown's are open too. Between them: light woodland and the
# groves below, which a building clears where it is put (AVLForest::ClearTrees in the game).
MEADOWS0 = [(-128, -82, 60), (-80, -112, 36), (-116, -170, 32), (-190, -80, 34), (-70, -12, 30), (-176, 0, 36), (-140, 112, 42),
            (-20, 172, 20), (-52, -172, 22)]
MEADOWS1 = [(128, 90, 60), (106, 134, 34), (192, 144, 30), (176, 104, 40), (72, 14, 30), (120, 0, 42), (132, -128, 42),
            (52, 172, 20), (-2, -174, 22)]
# The woods: groves (x0, y0, x1, y1, how thick 0..1), each bank its own. Elsewhere: a tree here and there.
GROVES0 = [(-78, -150, -14, -28, 1.0), (-78, 26, -8, 150, 1.0), (-238, 72, -192, 228, 0.9), (-238, 62, -100, 86, 0.8), (-238, 20, -100, 42, 0.7),
           (-112, -232, -44, -182, 0.9), (-120, 184, 4, 228, 0.8)]
GROVES1 = [(16, 30, 64, 150, 1.0), (10, -160, 96, -76, 1.0), (196, -232, 238, -96, 0.9), (104, -40, 156, -18, 0.8), (40, -232, 104, -186, 0.8),
           (216, 178, 240, 230, 0.9), (4, 184, 92, 228, 0.9), (214, 100, 240, 172, 0.7), (150, 14, 236, 34, 0.6)]
THIN = 0.012

# How many trees (the budget). Faces each, near / far: A 101k / 9k, B 94k / 8k, C 37k / 3k, D 10k / 1k (the second
# level of detail of assets/tree_lods.py). The realm has 1380 on 416 m; this map is 1.7 times its area and has about
# as many: groves, not one forest. Where nobody can go there are no tree meshes at all:
# assets/highland_terrain.py bakes blocks of leaves into SM_HighlandWoods.
TREES = dict(A=8, B=8, C=110, D=1300)
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


def snoise(X, Y, scale, seed):
    """Noise that is the same for both sides: the west half's, and its half turn on the east half."""
    west = (X < 0) | ((X == 0) & (Y < 0))
    return np.where(west, noise2(X, Y, scale, seed), noise2(-X, -Y, scale, seed))


def side_shapes(X, Y, S):
    """One side's hills (S: its entry of GROUND): heights and what is what."""
    n1 = noise2(X, Y, 14.0, 3)
    n2 = noise2(X, Y, 7.0, 17)
    n3 = noise2(X, Y, 26.0, 131)
    h = np.zeros(X.shape)
    # the bluff, flat on top
    bluff = sdist(X, Y, S["bluff"]) + (n2 - 0.5) * 3.0 > 0
    h = np.where(bluff, BLUFF_Z, h)
    # the peaks: a cliff of four metres all round, then up in one-metre blocks
    peak = np.zeros(X.shape, bool)
    for (px, py, pr, base, high) in S["peaks"]:
        dk = pr - np.hypot(X - px, Y - py) + (n2 - 0.5) * 5.0
        m = (dk > 0) & (bluff if base > 0 else ~bluff)
        peak |= m
        h = np.where(m, base + np.clip(np.round(3.0 + dk * 0.8 + (n3 - 0.5) * 7.0), 4.0, high), h)
    # the landing of the stair, against the bluff's face
    lx, ly, lr = S["landing"]
    landing = (np.hypot(X - lx, Y - ly) < lr + (n1 - 0.5) * 1.0) & ~bluff
    h = np.where(landing, BLUFF_Z / 2.0, h)
    # the tower's mound
    mx, my, mr = S["mound"]
    mound = np.hypot(X - mx, Y - my) < mr + (n1 - 0.5) * 1.5
    h = np.where(mound, MOUND_Z, h)
    # the spur: its crest wanders; the pass cuts straight through
    pts, sw = S["spur"]
    wob = (n3 - 0.5) * 16.0
    vx, vy = pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1]
    vl = math.hypot(vx, vy)
    ds = sw - dist_polyline(X + wob * vy / vl, Y - wob * vx / vl, pts) + (n2 - 0.5) * 4.0
    ga, gb, gw = S["gap"]
    spur = (ds > 0) & (seg_dist(X, Y, ga, gb)[0] > gw + (n1 - 0.5) * 2.0) & ~bluff
    h = np.where(spur, np.clip(np.round(3.0 + ds * 1.5 + (n3 - 0.5) * 7.0), 4.0, 24.0), h)
    # the tor of the neutral mine, the lone crags
    tx, ty, tr = S["tor"]
    dt = np.hypot(X - tx, Y - ty) - (n2 - 0.5) * 3.0
    tor = dt < tr
    # (a hill, not a drum of rock: it rolls off in shelves of a metre from a wandering foot, References/Remake/
    # mine_mound.png; steeper towards its top. Its lowest step is a metre: nobody walks up it)
    ang = np.arctan2(Y - ty, X - tx)
    dt = dt + 1.8 * np.sin(ang * 2 + 0.7 + tx) + 1.2 * np.sin(ang * 3 + 2.1) + 0.8 * np.sin(ang * 5 + 4.0)
    tor = dt < tr
    up = np.clip(tr - dt, 0.0, None)
    h = np.where(tor, np.clip(np.ceil(up / 1.5 + np.clip(up - 9.0, 0.0, None) * 0.9), 1.0, 17.0), h)
    crag = np.zeros(X.shape, bool)
    for (cx, cy, cr) in S["crags"]:
        dc = np.hypot(X - cx, Y - cy) - (n2 - 0.5) * 3.0
        crag |= dc < cr
        h = np.where(dc < cr, 4.0, h)
        h = np.where(dc < cr - 3.5, 7.0, h)
        h = np.where(dc < cr - 6.5, 10.0, h)
        h = np.where(dc < cr - 9.5, 14.0, h)
    return dict(h=h, bluff=bluff & ~peak, peak=peak, shelf=landing | mound, spur=spur, tor=tor | crag)


def river_fields(X, Y, land):
    """Where the water lies, from the plan alone."""
    near = np.full(X.shape, 1e9)
    for (bx, by) in BRIDGES.values():
        near = np.minimum(near, np.hypot(X - bx, Y - by))
    calm = np.clip((near - 15.0) / 6.0, 0, 1)                             # the banks are straight at the bridges, ragged elsewhere
    wrag = (snoise(X, Y, 3.0, 21) - 0.5) * 0.9 * calm
    d_up = river_dist(X, Y, RIVER_UP) + wrag
    d_mid = river_dist(X, Y, RIVER_MID) + wrag
    d_low = river_dist(X, Y, RIVER_LOW) + wrag
    north = Y > FALL1_Y
    beyond2 = Y < FALL2_Y
    water_up = (d_up < 0) & north
    water_low = (d_low < 0) & beyond2 & land
    water_mid = (d_mid < 0) & ~north & ~beyond2 & land
    d_any = np.minimum(np.where(north, d_up, 1e9), np.minimum(np.where(beyond2, 1e9, d_mid), np.where(beyond2, d_low, 1e9)))
    wet = water_up | water_mid | water_low
    island = in_poly(X, Y, CHANNEL_W + CHANNEL_E[::-1]) & ~wet
    return dict(d_up=d_up, d_mid=d_mid, d_low=d_low, north=north, beyond2=beyond2, water_up=water_up, water_mid=water_mid, water_low=water_low,
                d_any=d_any, wet=wet, island=island)


def path_fields(X, Y):
    """For every cell: the path it lies on (height, surface, whether on steps). As town_layout.path_fields."""
    z = np.full(X.shape, np.nan)
    surf = np.full(X.shape, -1, np.int8)
    steps = np.zeros(X.shape, bool)
    best = np.full(X.shape, 1e9)
    rag = (snoise(X, Y, 2.2, 5) - 0.5) * 0.7
    for pts, w, s in PATHS:
        for a, b in zip(pts[:-1], pts[1:]):
            # (only the cells near the segment: the map is big)
            x0, x1 = min(a[0], b[0]) - w - 2.0, max(a[0], b[0]) + w + 2.0
            y0, y1 = min(a[1], b[1]) - w - 2.0, max(a[1], b[1]) + w + 2.0
            i0, i1 = max(0, int((x0 + HALF) / CELL)), min(N, int((x1 + HALF) / CELL) + 1)
            j0, j1 = max(0, int((y0 + HALF) / CELL)), min(N, int((y1 + HALF) / CELL) + 1)
            sl = (slice(i0, i1), slice(j0, j1))
            d, t = seg_dist(X[sl], Y[sl], a, b)
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
                zz = np.full(d.shape, a[2])
                inside = (d + rag[sl]) < w
                st = np.zeros(d.shape, bool)
            take = inside & (d < best[sl])
            z[sl] = np.where(take, zz, z[sl])
            surf[sl] = np.where(take, STONE if abs(dz) > 1e-6 and s == COBBLE else s, surf[sl])
            steps[sl] = np.where(take, st, steps[sl])
            best[sl] = np.where(take, d, best[sl])
    for (p, pz_) in PLAZAS:
        plaza = (np.hypot(X - p[0], Y - p[1]) + rag) < 4.2
        z = np.where(plaza & np.isnan(z), pz_, z)
        surf = np.where(plaza & (surf < 0), COBBLE, surf)
    return z, surf, steps


def path_distance(X, Y):
    """How far every cell is from the nearest path's edge (as path_fields: only near each segment; 1e9 elsewhere)."""
    out = np.full(X.shape, 1e9, np.float32)
    for pts, w, _s in PATHS:
        for a, b in zip(pts[:-1], pts[1:]):
            pad = w + 8.0
            i0, i1 = max(0, int((min(a[0], b[0]) - pad + HALF) / CELL)), min(N, int((max(a[0], b[0]) + pad + HALF) / CELL) + 1)
            j0, j1 = max(0, int((min(a[1], b[1]) - pad + HALF) / CELL)), min(N, int((max(a[1], b[1]) + pad + HALF) / CELL) + 1)
            sl = (slice(i0, i1), slice(j0, j1))
            out[sl] = np.minimum(out[sl], seg_dist(X[sl], Y[sl], a, b)[0] - w)
    return out


def meadow(X, Y):
    """The open ground to build on round each side's buildings: 0 outside, 1 well inside (ragged edges)."""
    rag = (snoise(X, Y, 9.0, 151) - 0.5) * 10.0
    m = np.zeros(np.shape(X))
    for (cx, cy, r) in MEADOWS0 + MEADOWS1:
        m = np.maximum(m, np.clip((r - np.hypot(X - cx, Y - cy) + rag) / 4.0, 0.0, 1.0))
    return m


def rect_mask(X, Y, cx, cy, hx, hy):
    return (np.abs(X - cx) <= hx) & (np.abs(Y - cy) <= hy)


def dock_deck(X, Y):
    """The docks' planks (SM_Dock, its own -Y running out to sea): the walkway 3 m wide and 9 m long, the head 8 x 3.5 m."""
    out = np.zeros(X.shape, bool)
    for (d, _yaw, sign) in DOCKS:
        lx, ly = Y - d[1], (X - d[0]) * sign                  # across the walkway; along it (0 at the land end, negative out to sea)
        out |= ((np.abs(lx) <= 1.5) & (ly <= 0.25) & (ly >= -9.0)) | ((np.abs(lx) <= 4.0) & (ly <= -9.0) & (ly >= -12.5))
    return out


def min_near(h, k):
    """The lowest ground within k cells (a square)."""
    out = h.copy()
    for ax in (0, 1):
        acc = out.copy()
        for sh in range(1, k + 1):
            acc = np.minimum(acc, np.minimum(np.roll(out, sh, axis=ax), np.roll(out, -sh, axis=ax)))
        out = acc
    return out


def stones():
    """The standing stones round the Crown's rim: (x, y, half size, height)."""
    rx, ry, n = STONES
    out = []
    for k in range(n):
        a = math.radians((k + 0.5) * 360.0 / n)
        r1 = float(hash2(np.array(k % (n // 2)), np.array(7), 5))           # (the same for a stone and the one opposite)
        r2 = float(hash2(np.array(k % (n // 2)), np.array(9), 6))
        out.append((round(rx * math.cos(a) * 4) / 4.0, round(ry * math.sin(a) * 4) / 4.0, 0.5 if r2 < 0.6 else 0.75, 1.0 if r1 < 0.2 else 2.5 + round(r1 * 5.0) * 0.5))
    return out


def heights():
    X, Y = grid()
    rag = (noise2(X, Y, 6.0, 11) - 0.5) * 3.0 + (noise2(X, Y, 24.0, 12) - 0.5) * 7.0
    for (d, _yaw, _s) in DOCKS:                                             # (the docks' cliffs are where the plan says)
        rag = rag * np.clip((np.hypot(X - d[0], Y - d[1]) - 9.0) / 10.0, 0.0, 1.0)
    dc = sdist(X, Y, COAST) + rag                                           # > 0 on the land, metres from the coast
    for (ix, iy, r) in ISLETS:
        dc = np.maximum(dc, r - np.hypot(X - ix, Y - iy) + rag * 0.5)
    for mr in mound_rects():                                                # (ground under the whole of a mine's hill, where the coast is near)
        dc = np.where(in_rect(X, Y, mr, 1.0), np.maximum(dc, 3.0), dc)
    land = dc > 0
    W = river_fields(X, Y, land)
    island, wet, d_any = W["island"], W["wet"], W["d_any"]

    # ---- the big shapes: each side's hills, the highland, the ridge, the Crown
    A, B = side_shapes(X, Y, GROUND[0]), side_shapes(X, Y, GROUND[1])
    h = np.maximum(A["h"], B["h"])
    R = {k: A[k] | B[k] for k in ("bluff", "peak", "shelf", "spur", "tor")}
    n1, n2, n3 = noise2(X, Y, 14.0, 3), noise2(X, Y, 7.0, 17), noise2(X, Y, 26.0, 131)
    dax = np.abs(X - FALL1_X)
    dh = Y - (FALL1_Y + (n1 - 0.5) * 5.0 * np.clip((dax - 6.0) / 10.0, 0, 1))          # (its edge is straight where the river crosses it)
    high = dh > 0
    h = np.where(high, np.maximum(h, np.clip(np.round(9.0 + dh * 0.85 + (n2 - 0.5) * 3.0 + (n3 - 0.5) * 7.0), 9.0, TOP - 2.0)), h)
    dr = X - (RIDGE_X + (n3 - 0.5) * 10.0 + (n1 - 0.5) * 4.0)
    ridge = (dr > 0) & (Y > RIDGE_Y)
    h = np.where(ridge, np.maximum(h, np.clip(np.round(7.0 + dr * 0.9 + (n2 - 0.5) * 3.0), 7.0, TOP - 2.0)), h)
    # the Crown: the whole island between the two channels, flat; the rock in its middle
    sn = 0.5 * (n2 + noise2(-X, -Y, 7.0, 17))
    es = np.hypot(X / SPIRE[0], Y / SPIRE[1]) + (sn - 0.5) * 0.3
    spire = island & (es < 1.0)
    h = np.where(island, MESA_Z, h)
    # (the rock rolls off to the mesa in shelves of a metre, not in three drums)
    h = np.where(spire, MESA_Z + np.clip(np.ceil((1.0 - es) * 13.0), 1.0, 12.0), h)
    # the gorge's walls: palisades of rock on both banks of the river above and below the Crown, in broken stretches
    # (none within 30 m of a bridge, none facing the Crown): highest over the water, stepping down away from it
    d_main = river_dist(X, Y, [(_N, 6.0), (_S, 6.0)] + RIVER_LOW)
    near_bridge = np.full(X.shape, 1e9)
    for (bx, by) in BRIDGES.values():
        near_bridge = np.minimum(near_bridge, np.hypot(X - bx, Y - by))
    deep = PALISADE * np.clip((snoise(X, Y, 30.0, 301) - 0.40) / 0.16, 0.0, 1.0) * np.clip((near_bridge - 30.0) / 10.0, 0.0, 1.0) * \
        np.clip((np.abs(Y) - 70.0) / 10.0, 0.0, 1.0)
    pal = (d_main > 1.5) & (d_main - 1.5 < deep - 1.0) & land & ~high & (dc > 8.0)
    h = np.where(pal, np.maximum(h, 3.0 + np.round(np.clip((deep - (d_main - 1.5)) * 0.42 + (snoise(X, Y, 7.0, 303) - 0.5) * 2.0, 0.0, 5.0))), h)
    for k, (crest, reach, seed) in HILLS.items():
        mh = minehill.hill(X, Y, BUILD[k][1], BUILD[k][2], BUILD[k][4], crest, reach, seed, noise2(X, Y, 7.0, 400 + seed))
        h = np.where(mh > 0, np.maximum(h, BUILD[k][3] + mh), h)
        if k.startswith("crown"):
            spire = spire | ((mh > 0) & island)
        else:
            R["tor"] = R["tor"] | (mh > 0)
    R.update(high=high, ridge=ridge, spire=spire, mesa=island & ~spire, pal=pal, n1=n1, n2=n2)
    wild = R["peak"] | R["spur"] | R["tor"] | high | ridge | spire | pal

    # the woods are not flat: half-block terraces (a unit steps up them); the lawns: low platforms a quarter block high
    # (not the meadows, the bluffs' tops or the Crown's: they are flat, to build on)
    open_ = ((meadow(X, Y) > 0.5) | R["bluff"] | R["mesa"] | R["shelf"]) & ~wild
    h = np.where((snoise(X, Y, 11.0, 51) > 0.6) & ~wild & ~open_, h + 0.5, h)
    h = np.where((snoise(X, Y, 4.5, 77) > 0.58) & ~(open_ & ~wild), h + 0.25, h)
    for (ix, iy, r) in ISLETS:
        h = np.where(np.hypot(X - ix, Y - iy) < r + 2.5, SEA + 3.25 + np.round(n1 * 2) * 0.5, h)

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
                apron |= rect_mask(X, Y, (a[0] + b[0]) / 2, (a[1] + b[1]) / 2, abs(a[0] - b[0]) / 2 + w + 1.5, abs(a[1] - b[1]) / 2 + w + 1.5) & \
                    (seg_dist(X, Y, a, b)[0] < w + 1.2)
    raised = R["bluff"] | R["shelf"] | island                             # (no sunk roads on the hills: their steps would not meet them)
    sunk = path & ~psteps & ~apron & (psurf == COBBLE) & ~raised
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

    # ---- the river's bed
    for (wm, d, lvl, deep) in ((W["water_up"], W["d_up"], UP, 1.25), (W["water_mid"], W["d_mid"], MID, 1.5), (W["water_low"], W["d_low"], LOW, 1.5)):
        h = np.where(wm, lvl - 0.75, h)
        h = np.where(wm & (d < -0.9), lvl - deep, h)
    # the bridges' feet stand on rock abutments built out from both banks (the stream runs between them)
    corridor = np.zeros(X.shape, bool)
    abut = np.zeros(X.shape, bool)
    for (bx, by) in BRIDGES.values():
        corridor |= rect_mask(X, Y, bx, by, 4.25, 1.5)
        abut |= wet & rect_mask(X, Y, bx, by, 2.7, 2.0) & (np.abs(X - bx) > 1.25)
    h = np.where(abut, -2.5, h)
    # rock shelves a little way down the gorge's sides (not at the bridges)
    shelf = (d_any >= 0) & (d_any < 0.75) & land & ~keep & ~corridor & (blk > 0.55) & (Y < FALL1_Y - 1.0)
    h = np.where(shelf, np.minimum(h, np.where(island, 1.5, -2.0) - np.round(blk2 * 2.0) * 0.5), h)
    bank_up = (W["d_up"] >= 0) & (W["d_up"] < 1.2) & W["north"]
    h = np.where(bank_up, np.minimum(h, UP + 0.75), h)

    # ---- where nobody may go (the barriers stand on its edge): the sea and the cliff's rim over it, the river and its
    # banks, and the rim of every drop where people walk (the bluffs, the landings, the mounds, the Crown): ground
    # with something more than a metre and a half lower within a metre. Not the roads and their steps, not the
    # bridges, not the docks.
    sea = ~land & ~rocks
    deck = dock_deck(X, Y)
    rim = (h - min_near(h, 4) > 1.5) & ~path & ~wild & land
    hazard = ~land | (land & (dc < 2.6) & ~path) | (d_any < 0.9) | rim
    hazard &= ~corridor & ~deck

    # ---- the standing stones (after the rims: they are things to walk round, not edges)
    stone = np.zeros(X.shape, bool)
    for (sx, sy, hs, sh) in stones():
        m = rect_mask(X, Y, sx, sy, hs, hs) & island & ~path & ~hazard
        stone |= m
        h = np.where(m, MESA_Z + sh, h)

    return dict(X=X, Y=Y, h=h, land=land, dc=dc, sea=sea, rocks=rocks, path=path, psurf=psurf, psteps=psteps,
                water_up=W["water_up"], water_mid=W["water_mid"], water_low=W["water_low"], wet=wet, pads=pads, island=island, isl_rock=stone,
                cut=(cut1 | cut2 | shelf) & ~wet, hazard=hazard, corridor=corridor, deck=deck, d_river=d_any, R=R, wild=wild, open=open_ & ~wild,
                abut=abut, rim=rim)


def surface(G):
    X, Y, h, R = G["X"], G["Y"], G["h"], G["R"]
    s = np.zeros(X.shape, np.int8)
    hs = hash2(np.floor(X / 0.5), np.floor(Y / 0.5), 13)
    # the peaks, the spurs, the tors, the highland, the ridge: grass on the low terraces, more and more bare rock higher up
    rocky = G["wild"]
    bare = noise2(X, Y, 6.0, 91) + np.clip((h - 13.0) / 18.0, 0, 1) * 0.8
    s[rocky & (bare > 0.72)] = MOSSY
    s[rocky & (bare > 0.9)] = STONE
    s[R["spire"]] = np.where(hs[R["spire"]] > 0.45, STONE, MOSSY)
    # the Crown: old paving round its rock, moss among the grass
    court = R["mesa"] & (np.hypot(X / 22.0, Y / 24.0) < 1.0 + (noise2(X, Y, 5.0, 93) - 0.5) * 0.5)
    s[court & (hs > 0.42)] = MOSSY
    s[court & (hs > 0.8)] = STONE
    s[G["path"]] = G["psurf"][G["path"]]
    # the plots' soil, the paddocks' trodden earth
    for (x0, y0, x1, y1, z, kind, _g) in PLOTS:
        inside = in_rect(X, Y, (x0, y0, x1, y1), -0.4)
        s[inside & (s == 0) & ((kind != "sheep") | (noise2(X, Y, 3.0, 31) > 0.52))] = DIRT
    for (_k, pk, _z, _g, _w) in PADDOCKS:
        s[in_rect(X, Y, pk, -0.3) & (s == 0) & (noise2(X, Y, 3.5, 31) > 0.6)] = DIRT
    s[(noise2(X, Y, 5.0, 41) > 0.82) & (s == 0) & G["land"]] = DIRT
    s[(noise2(X, Y, 3.0, 61) > 0.84) & (s == 0) & G["land"]] = MOSSY
    s[G["isl_rock"]] = np.where(hs[G["isl_rock"]] > 0.5, STONE, MOSSY)
    # the coast's ledges and rocks, the gorge's shelves
    cut = G["cut"]
    s[cut] = np.where(hs[cut] > 0.5, STONE, MOSSY)
    s[G["rocks"]] = np.where(hs[G["rocks"]] > 0.6, MOSSY, STONE)
    s[G["sea"]] = GRAVEL
    s[G["wet"]] = GRAVEL
    s[G["abut"]] = np.where(hs[G["abut"]] > 0.6, MOSSY, STONE)
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

    def building(self, mesh, x, y, z, yaw, team, group="buildings", tags=None):
        self.add(mesh, x, y, yaw, z=z, group=group, team=team, tags=tags)
        for pr in meta(mesh).get("props", []):
            px, py = rot(pr["pos"][0], pr["pos"][1], yaw)
            self.add(pr["mesh"], x + px, y + py, yaw + float(pr.get("yaw", 0.0)), float(pr.get("scale", 1.0)), z=z + pr["pos"][2], group="props")

    def tree(self, kind, x, y, yaw=0.0, scale=1.0, group="forest"):
        super().tree(kind, x, y, yaw, scale, group)
        self.trees.append((x, y, kind, scale))


def wood(x, y):
    """How wooded a place is, 0..1: the groves, and a tree here and there between them."""
    w = THIN
    for (x0, y0, x1, y1, t) in GROVES0 + GROVES1:
        if x0 < x < x1 and y0 < y < y1:
            w = max(w, t)
    return w


def rect_gap(x, y, f):
    """How far a point is from a rectangle (x0, y0, x1, y1, ...): 0 inside."""
    return math.hypot(max(f[0] - x, 0.0, x - f[2]), max(f[1] - y, 0.0, y - f[3]))


_FOOT = {k: footprint(k) for k in BUILD}


def tree_blocked(x, y, kind, scale=1.0, margin=BUILD_MARGIN):
    """Would this tree stand in or right against a building (its footprint and its gate)? The rule the game's
    AVLForest::ClearTrees applies when a building is put down, applied to the plan."""
    reach = TREE_CLEAR[kind] * scale + margin
    for k in BUILD:
        if rect_gap(x, y, _FOOT[k]) < reach:
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
        sc.building(mesh, x, y, z - 0.01, yaw, team, tags=(["Rich"] if key.startswith("crown") else []) + (["Mounded"] if mesh == "SM_MineCliff" else []) or None)
        if key in MOUNDED:
            sc.add("SM_MineMound", x, y, yaw, z=z, group="rocks", tags=["MineMound"])
    for (bx, by) in BRIDGES.values():
        sc.add("SM_Bridge", bx, by, 90.0, z=0.04, group="buildings", team="Neutral")
    sc.add("SM_PlazaBanner", PLAZA0[0], PLAZA0[1], z=0.0, r=1.3, team=0)
    sc.add("SM_PlazaBanner", PLAZA1[0], PLAZA1[1], z=0.0, r=1.3, team=1)
    moor = meta("SM_Dock").get("moor", [2.9, -5.9, -1.0, 90.0])
    for t, (d, yaw, _s) in enumerate(DOCKS):
        sc.building("SM_Dock", d[0], d[1], DOCK_Z, yaw, t)
        mx, my = rot(moor[0], moor[1], yaw)
        sc.add("SM_Boat", d[0] + mx, d[1] + my, moor[3] + yaw, z=SEA + 0.02, group="props")

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
            sc.add("SM_HayStack", (a[0] + a[2]) / 2.0, a[1] + 0.4, 20.0, z=z, group="farm", r=0.9)

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

    # ---- clutter (a few things at each side's gates and the mines' aprons; the same for both sides)
    def beside(key, out, along):
        return front(key, out, along)

    clutter = []
    for t in "01":
        clutter += [("SM_FlowerPlanter", beside("castle" + t, 1.0, -3.6), 0), ("SM_FlowerPlanter", beside("castle" + t, 1.0, 3.6), 0),
                    ("SM_MineCart", beside("mine" + t, 1.0, 3.0), 90), ("SM_Barrel", beside("mine" + t, 0.6, -3.0), 0), ("SM_Crate", beside("mine" + t, 1.2, -4.0), 30)]
        d, _yaw, sg = DOCKS[int(t)]
        clutter += [("SM_CrateStack", (d[0] + sg * 13.5, d[1] + 2.8), 20), ("SM_Barrel", (d[0] + sg * 15.0, d[1] + 3.0), 0), ("SM_Crate", (d[0] + sg * 12.0, d[1] - 2.8), 15)]
    clutter += [("SM_Signpost", (-77.0, -65.0), 200), ("SM_Signpost", (-119.0, -113.0), 100), ("SM_Signpost", (163.0, 58.0), 20), ("SM_Signpost", (123.0, 106.5), 280)]
    for k in ("crown_n", "crown_s", "mine_nw", "mine_se"):
        clutter += [("SM_MineCart", beside(k, 1.0, 3.2), 0), ("SM_Crate", beside(k, 0.8, -3.4), 30), ("SM_Barrel", beside(k, 0.6, -4.4), 0)]
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
        if any(math.hypot(x - bx, y - by) < 14.0 for (bx, by) in BRIDGES.values()):
            return True
        return math.hypot(x - PLAZA0[0], y - PLAZA0[1]) < 5.5 or math.hypot(x - PLAZA1[0], y - PLAZA1[1]) < 5.5

    path_d = path_distance(X, Y)

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

    # ---- lantern posts along the roads, alternating sides (not on the tracks)
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
    for name in BRIDGES:                                                  # a lantern at each bank's end of every bridge
        for k, (bx, by) in enumerate(bridge_ends(name)):
            if name.startswith("crown") and k == (1 if name == "crown_w" else 0):
                continue                                                  # (not in the stair's cutting)
            x, y = bx + (-1.6 if k == 0 else 1.6), by + 2.9
            if free(x, y, 0.4, 0.2, allow_pad=True):
                sc.add("SM_LanternPost", x, y, r=1.0)
    for sx in (-1, 1):                                                    # and at the head of each of the Crown's stairs
        for sy in (-1, 1):
            sc.add("SM_LanternPost", sx * 21.0, sy * 3.4, r=1.0)

    # ---- trees: only where people can walk (the peaks, the spurs, the highland and the ridge get SM_HighlandWoods:
    # blocks of leaves baked by assets/highland_terrain.py). All but none on the open ground; none in or against a building.
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

    hand = [("C" if r > 5.0 else "D", ix, iy) for (ix, iy, r) in ISLETS]                             # the islets'
    hand += [("B", 0.0, 41.0), ("B", 0.0, -41.0)]                                                   # an old tree at each end of the Crown
    for kind, x, y in hand:
        plant(kind, x, y, float(rng.uniform(0.85, 1.0)), "frame")
    tries, lone = 0, 0
    for kind in "ABCD":
        while count[kind] < TREES[kind] and tries < 1500000:
            tries += 1
            x, y = rng.uniform(-HALF + 5, HALF - 5, 2)
            i, j = cell(x, y)
            if wild[i, j]:
                continue
            w = wood(x, y) * (1.0 if kind in "CD" else 0.8)
            if open_[i, j]:                                # a lone tree here and there on the open ground, no more
                w = 0.012 if kind == "D" and lone < 40 and not (R["mesa"][i, j] or R["bluff"][i, j]) else 0.0
            if rng.random() > w:
                continue
            if kind in "AB" and wood(x, y) < 0.5:          # the giants stand in the groves
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
        return not wild[i, j]

    def rough(x, y):                                     # rocks and bushes keep off the open ground (mostly)
        i, j = cell(x, y)
        return not wild[i, j] and (not open_[i, j] or rng.random() < 0.08)

    scatter(150, ["SM_Rock_A", "SM_Rock_B", "SM_Rock_B", "SM_Rock_C", "SM_Rock_C", "SM_Rock_D", "SM_Rock_E"], 1.5, "rocks", 5.0, scale=(0.7, 1.0), solid=True, where=rough)
    scatter(850, ["SM_Bush_A", "SM_Bush_A", "SM_Bush_B", "SM_Bush_B", "SM_Bush_C"], 0.8, "plants", 2.2, scale=(0.8, 1.25), where=rough)
    scatter(3000, ["SM_Flowers_A", "SM_Flowers_B", "SM_Flowers_C", "SM_Flowers_D"], 0.3, "plants", 1.0, where=tame)
    scatter(7500, ["SM_GrassTuft_A", "SM_GrassTuft_B", "SM_GrassTuft_C", "SM_GrassTuft_C"], 0.3, "plants", 0.6, scale=(0.9, 1.5), where=tame)
    # rocks at the cliff's foot (nobody walks there)
    k = 0
    for _ in range(30000):
        if k >= 100:
            break
        x, y = rng.uniform(-HALF + 3, HALF - 3, 2)
        i, j = cell(x, y)
        if G["rocks"][i, j] and h[i, j] > SEA - 0.3 and not sc.solid.hits(x, y, 2.5) and all(math.hypot(x - d[0], y - d[1]) > 17.0 for (d, _a, _b) in DOCKS):
            sc.add(str(rng.choice(["SM_Rock_A", "SM_Rock_B", "SM_Rock_D", "SM_Rock_E"])), x, y, float(rng.integers(0, 4)) * 90.0,
                   float(rng.uniform(0.8, 1.2)), group="rocks", r=1.5)
            k += 1
    # lily pads on the sea by the docks and in the gorge's quiet reaches
    k = 0
    for _ in range(40000):
        if k >= 90:
            break
        x, y = rng.uniform(-HALF + 3, HALF - 3, 2)
        i, j = cell(x, y)
        if G["water_mid"][i, j] and G["d_river"][i, j] < -1.2 and abs(y) > 80 and rng.random() < 0.5:
            z = MID
        elif G["sea"][i, j] and -3.0 > G["dc"][i, j] > -9.0 and any(math.hypot(x - d[0], y - d[1]) < 45.0 for (d, _a, _b) in DOCKS) and not G["deck"][i, j] and rng.random() < 0.5:
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
    dk = G["deck"][0::2, 0::2] | G["deck"][1::2, 1::2]                        # the docks' planks
    hh = np.where(dk, DOCK_Z, hh)
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

    bluff_top, bluff_top1 = (-177.0, -150.0), (136.0, 173.0)
    pts = dict(G_)
    pts.update(bridge0=(bridge_ends("crown_w")[0][0] - 1.0, 0.0), bridge1=(bridge_ends("crown_e")[1][0] + 1.0, 0.0),
               crown_top0=(-19.0, 0.0), crown_top1=(19.0, 0.0),
               near0=(bridge_ends("south")[0][0] - 1.0, BRIDGES["south"][1]), near1=(bridge_ends("north")[1][0] + 1.0, BRIDGES["north"][1]),
               far0=(bridge_ends("north")[0][0] - 1.0, BRIDGES["north"][1]), far1=(bridge_ends("south")[1][0] + 1.0, BRIDGES["south"][1]),
               bluff0=bluff_top, bluff1=bluff_top1, dock0=(DOCK0[0] - 10.5, DOCK0[1]), dock1=(DOCK1[0] + 10.5, DOCK1[1]))
    nodes = {k: node(v) for k, v in pts.items()}
    D = dijkstra(g, directed=False, indices=[nodes["castle0"], nodes["castle1"], nodes["mine0"], nodes["mine1"]])

    def d(src, k):
        v = float(D[src, nodes[k]])
        return None if not math.isfinite(v) else round(v, 1)

    def side(t, own, foe):
        s = str(t)
        return dict(crown_bridge=d(t, "bridge" + s), crown_top=d(t, "crown_top" + s), crown_mine_north=d(t, "crown_n"), crown_mine_south=d(t, "crown_s"),
                    own_mine=d(t, "mine" + s), bluff_top=d(t, "bluff" + s),
                    tower=d(t, "tower" + s), dock=d(t, "dock" + s), neutral_mine_own_bank=d(t, own), neutral_mine_far_bank=d(t, foe),
                    near_flank_bridge=d(t, "near" + s), far_flank_bridge=d(t, "far" + s), enemy_castle=d(t, "castle" + str(1 - t)),
                    mine_to_tower=d(2 + t, "tower" + s), mine_to_crown_bridge=d(2 + t, "bridge" + s),
                    tower_to_mine_straight=round(math.hypot(BUILD["tower" + s][1] - G_["mine" + s][0], BUILD["tower" + s][2] - G_["mine" + s][1]), 1))

    rep = dict(player=side(0, "mine_nw", "mine_se"), enemy=side(1, "mine_se", "mine_nw"),
               heights=dict(bluff=BLUFF_Z, tower_mound=MOUND_Z, crown=MESA_Z, gorge=-MID, great_fall=UP - MID),
               note="metres walked from the castle's door by the shortest route over the ground (50 cm cells, steps of at most 50 cm, "
                    "no water, no building; trees and fences not counted)")

    # ---- the ground to build on: what can be walked to from the castle and is nearer (on foot) to it than to the
    # other one, less the roads, the buildings (and 2 m round them), the plots and the paddocks. "meadow": the flat
    # open ground; "open": no tree within 4 m; "wooded": the rest (a building clears its trees); "bluff": on top of
    # its hill; "crown": its half of the mesa in the middle.
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
    bluff, mesa = G["R"]["bluff"][0::2, 0::2], G["R"]["mesa"][0::2, 0::2]
    area = {}
    for side_, mine_, other in (("player", d0, d1), ("enemy", d1, d0)):
        own = ok & np.isfinite(mine_) & (mine_ < other) & ~taken & flat
        area[side_] = dict(total=int(own.sum() * 0.25), meadow=int((own & mdw).sum() * 0.25), open=int((own & ~treed).sum() * 0.25),
                           wooded=int((own & treed).sum() * 0.25), bluff=int((own & bluff).sum() * 0.25), crown=int((own & mesa).sum() * 0.25),
                           trees=int(sum(1 for (tx, ty, _k, _s) in trees
                                         if own[min(n - 1, int((tx + HALF) / 0.5)), min(n - 1, int((ty + HALF) / 0.5))])))
    area["crown_whole"] = int((ok & np.isfinite(d0) & ~taken & flat & mesa).sum() * 0.25)
    rep["buildable_m2"] = dict(area, note="square metres of level ground a side can walk to and is nearer to than its foe, less roads, buildings, "
                                          "plots and paddocks. meadow: the flat open ground (its meadows, its bluff's top, its half of the Crown); "
                                          "open: no tree within 4 m; wooded: under trees (a building clears them); bluff: on top of its hill; "
                                          "crown: its half of the mesa in the middle (crown_whole: all of it)")
    if verbose:
        print("%-24s %8s %8s" % ("from the castle door to", "player", "enemy"))
        for k in rep["player"]:
            print("%-24s %8s %8s" % (k, rep["player"][k], rep["enemy"][k]))
        print("%-24s %8s %8s" % ("ground to build on, m2", "player", "enemy"))
        for k in ("total", "meadow", "open", "wooded", "bluff", "crown", "trees"):
            print("%-24s %8s %8s" % (k, area["player"][k], area["enemy"][k]))
        print("%-24s %8s" % ("the Crown's top, whole", area["crown_whole"]))
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
        if key.startswith("crown"):
            e["rich"] = True
        return e

    def point(p):
        q = [p[0], p[1], round(ground(h, p[0], p[1]), 3)]
        return dict(pos=q, pos_ue=ue(q))

    out = {}
    for team, plaza, start, rally, bridge in ((0, PLAZA0, SPAWN, RALLY0, bridge_ends("crown_w")[0]), (1, PLAZA1, START1, RALLY1, bridge_ends("crown_e")[1])):
        b = [entry(k) for k in BUILD if BUILD[k][5] == team]
        out[str(team)] = dict(name="player" if team == 0 else "enemy", castle=next(e for e in b if e["kind"] == "Castle"),
                              buildings=b, start=dict(point(start), yaw=start[2], yaw_ue=-start[2]), rally=point(rally), plaza=point(plaza),
                              bridge_end=point(bridge), dock=point((DOCKS[team][0][0] + DOCKS[team][2] * 17.0, DOCKS[team][0][1])))
    out["neutral"] = dict(buildings=[entry(k) for k in BUILD if BUILD[k][5] == "Neutral"])
    out["axes"] = "pos: metres, +X east, +Y north, +Z up, yaw counter-clockwise from above (fronts face -Y at yaw 0). " \
                  "pos_ue / yaw_ue: Unreal centimetres (x, -y, z) and degrees (-yaw)."
    out["tags"] = "every building actor: Selectable, Name:<kind>, Team:0|1|Neutral (the Crown's two mines also: Rich). " \
                  "Markers (TargetPoint actors): TeamStart:0, TeamStart:1, Rally:0, Rally:1, Crown (the middle of the mesa)."
    return out


def buildable_areas():
    """The named flat grounds, for whoever places buildings: (name, team or Neutral, what, where)."""
    out = []
    for t in (0, 1):
        out.append(dict(name="bluff", team=t, z=BLUFF_Z, polygon=[list(p) for p in GROUND[t]["bluff"]],
                        note="the top of the side's hill, less the rock on it (%s)" % ", ".join("%.0f m round (%.0f, %.0f)" % (r, x, y) for (x, y, r, b, _h) in GROUND[t]["peaks"] if b > 0)))
        for (x, y, r) in (MEADOWS0, MEADOWS1)[t]:
            out.append(dict(name="meadow", team=t, z=0.0, centre=[x, y], radius=r))
    out.append(dict(name="crown", team="Neutral", z=MESA_Z, polygon=[list(p) for p in CHANNEL_W + CHANNEL_E[::-1]],
                    note="the mesa in the middle: all of it but the rock (%.0f x %.0f m round the middle) and the stairs' cuttings" % (2 * SPIRE[0], 2 * SPIRE[1] + 13.0)))
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
    markers.append(dict(tag="Crown", pos=[-19.0, 0.0, MESA_Z], yaw=0.0))
    bal = balance(G, verbose, sc.trees)
    layout = dict(
        name="Highlands", map="/Game/Maps/L_Highlands",
        camera=dict(pos=list(C.POS), target=list(C.TARGET), hfov=C.HFOV, az=C.AZ, el=C.EL, width=C.W, height=C.H),
        terrain=dict(cell=CELL, half=HALF, zmin=ZMIN, top=TOP, sea=SEA, seabed=SEABED, up=UP, mid=MID, low=LOW, surfaces=SURF),
        spawn=dict(pos=[SPAWN[0], SPAWN[1], ground(h, SPAWN[0], SPAWN[1])], yaw=SPAWN[2]),
        places=dict(plaza=PLAZA0, plaza1=PLAZA1, glade=MEADOWS0[6][:2], dock=DOCK0, dock1=DOCK1, fall1=(FALL1_X, FALL1_Y), fall2=(-27.2, FALL2_Y), crown=(0.0, 0.0),
                    landing0=GROUND[0]['landing'][:2], landing1=GROUND[1]['landing'][:2], pass0=(-171.0, 52.0), pass1=(176.5, -59.0),
                    bridges={k: dict(centre=v, west_end=bridge_ends(k)[0], east_end=bridge_ends(k)[1]) for k, v in BRIDGES.items()},
                    stones=[s_[:2] for s_ in stones()],
                    **{k: (v[1], v[2]) for k, v in BUILD.items()}),
        gates=GATE,
        teams=tm,
        markers=markers,
        balance=bal,
        meadows=dict(player=MEADOWS0, enemy=MEADOWS1),
        buildable=buildable_areas(),
        trees=dict(count=sc.tree_counts, clear=TREE_CLEAR, margin=BUILD_MARGIN, cleared_at_build=sc.cleared,
                   faces=int(sum(sc.tree_counts[k] * (meta("SM_Tree2_%s_Trunk" % k).get("faces", 0) + meta("SM_Tree2_%s_Leaves" % k).get("faces", 0)) for k in "ABCD"))),
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
        np.savez_compressed(os.path.join(OUT, NAME + "_terrain.npz"), h=h.astype(np.float32), s=s, hazard=G["hazard"])
        counts = {}
        for it in sc.items:
            counts[it["mesh"]] = counts.get(it["mesh"], 0) + 1
        faces = sum(meta(m).get("faces", 0) * n for m, n in counts.items())
        print("highland: %d instances, %d kinds, %.2f M faces; trees %s = %.2f M faces, %d taken away from buildings; not built yet: %s" % (
            len(sc.items), len(counts), faces / 1e6, sc.tree_counts, layout["trees"]["faces"] / 1e6, sc.cleared, ", ".join(sorted(sc.missing)) or "none"))
    return layout, G, s


def debug(layout, G, s, path=None):
    """The plan from above (north up), 2 px per metre: surfaces, heights, water, hazard edge, open ground (paler), buildings, trees."""
    from PIL import Image, ImageDraw
    h = G["h"]
    cols = np.array([(96, 150, 50), (190, 160, 110), (140, 100, 60), (120, 120, 120), (150, 150, 150), (110, 140, 100), (200, 140, 70)], np.uint8)
    rgb = cols[s].astype(np.float32) * (0.62 + 0.03 * np.clip(h, -3, 26))[:, :, None]
    rgb[G["open"] & (s == 0)] *= 1.18
    rgb[G["water_up"]] = (110, 180, 240)
    rgb[G["water_mid"] & ~G["abut"]] = (70, 140, 210)
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
    for (bx, by) in BRIDGES.values():
        a, b = px(bx - 3.5, by + 2), px(bx + 3.5, by - 2)
        dr.rectangle([a[0], a[1], b[0], b[1]], outline=(255, 255, 255), width=2)
    path = path or os.path.join(ROOT, "Saved", "highland_plan.png")
    im.save(path)
    print(path)


if __name__ == "__main__":
    L, G_all, S = build(verbose="--balance" in sys.argv or "--debug" in sys.argv)
    if "--debug" in sys.argv:
        debug(L, G_all, S)
