"""Realm v2: the third battle map (L_RealmV2), an island 640 m square, after References/RealmV2/ (PLAN.md the brief;
layout_annotated.png and layout_island_suggestion.png the layout; visual_inspiration.png, scale_and_clouds.png,
terrain_pockets.png and port.png the look). Pure numpy (+ scipy for the balance report, when it is there); writes
SourceArt/realmv2.json and SourceArt/realmv2_terrain.npz (heights, surfaces, the hazard map, the water's levels).

    Blender -b --factory-startup --python Tools/blender/realmv2_layout.py             (or: import realmv2_layout as R; R.build())
    Tools/.venv/bin/python Tools/blender/realmv2_layout.py [--debug] [--balance]   (--debug: Saved/realmv2_plan.png, the
                                                                                        plan from above; --balance: the routes)

Built on town_layout.py and written after highland_layout.py (the same conventions: world metres, +X east, +Y north,
+Z up; the postcard camera, realmv2_cam.py, looks from the south-west). The level is fixed: this script is the
development tool that makes it, and everything in it is seeded.

  the island   sea all round (COAST): cliffs 6 m and more with ledges and rocks, a few coves with a beach, islets
  the channels two arms of the sea come in from the north coast and run down either side of the massif in ravines 6 m
               deep and 26 m wide; they meet south of the ruins and reach the south coast; a third arm comes in from
               the west. Nobody crosses them but by the nine bridges
  the massif   the land between the arms: the MOUNTAIN (eleven peaks, the summit 184 m over the land; nobody climbs
               it), on its south shoulder the UPPER TERRACE (22 m, the old arch) and under that the RUINS PLATEAU (12 m,
               pillars round a flat court: the contested high ground), climbed by three gentle ramps (south, west,
               east) and a stair between the two terraces. A creek falls from the mountain onto the plateau, crosses
               it and falls into the east arm. Round the mountain's feet: the west foot's pocket, the NORTH CROSSING
               (the saddle between the west arm and the mountain's north-west buttress), the ground behind the
               mountain, the east shelf with the centre-east mine in the mountain's wall
  south-west   the player's: the castle; the home mine in the west bluff's face, a tower on the level ground by the mine
               road; the hill tower on its knoll in the north-west of its land; the port on the west coast
  north-east   the enemy's: the castle (facing west); the home mine in the north bluff's face, its tower beside it; the
               hill tower on its knoll in the south of its land; the port on the east coast
  the rest     pockets of level, open ground to build in, ringed by forest; low rounded hills; rock plateaus with trees
               on top; the north-west and the south-east countries (a neutral mine in its tor each); the SOUTH CROSSING
               (the double bridge over the joined arm, on a rock in midstream)

Terrain maths (written for this map; the ideas, not the code, are Luanti's Carpathian mapgen's and FastNoiseLite's):
  fbm / ridged   layered value noise; the ridged sum weights each octave by the one before (sharp crests, smooth feet)
  warp           domain warping: the mountain's outline and its peaks are looked up at places pushed about by noise
  steps          Carpathian's stepped mountains: a height cut into treads and risers, blended in by a slow noise
  the lowland    one slow noise, flattened to a level at every place of the plan, cut into quarter-block shelves
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import realmv2_cam as C
import minehill
import softground
import wildwoods
import town_layout as T
from town_layout import hash2, noise2, seg_dist, dist_polyline, in_poly, in_rect, meta, rot

ROOT = T.ROOT
OUT = T.OUT
MESHES = T.MESHES
NAME = "realmv2"

CELL = 0.25
HALF = 320.0                      # the world is 640 m square
N = int(2 * HALF / CELL)
ZMIN = -10.0
TOP = 250.0
WAT = -6.0                        # the sea, and every channel of it through the island (the ravines: 6 m under the banks)
SEA = WAT
SEABED = -8.0
DOCK_Z = SEA + 1.0                 # the ports' quays and piers
UPN = 7.0                         # the rivers above their falls, on the north rim
POND = 41.75                      # the creek's pond in the mountain's wall
BROOK = 11.5                      # the creek on the ruins plateau
RUINS_Z = 12.0
UPPER_Z = 22.0
BLUFF_Z = 7.0
HILL_Z = 4.0                      # the two hill towers: on knolls that roll off in quarter-block shelves (KNOLLS)
MOUND_Z = 0.0                     # the towers by the home mines stand on the level ground

SURF = T.SURF + ["snow"]
GRASS, COBBLE, DIRT, GRAVEL, STONE, MOSSY, PLANK, SNOW = range(8)

# ---------------------------------------------------------------------------------------------------- the plan

# ---- the rivers: (points, half width). Narrow where a bridge crosses.
RIVER_LOW = [
    # the west river
    ([(-70, 330), (-76, 296), (-80, 262), (-84, 228), (-70, 196), (-78, 172), (-90, 160)], 7.0),
    ([(-90, 160), (-90, 144)], 2.6),
    ([(-90, 144), (-104, 128), (-136, 112), (-166, 100), (-182, 84), (-186, 64), (-178, 53)], 7.5),
    ([(-178, 53), (-178, 37)], 2.6),
    ([(-178, 37), (-166, 14), (-140, -10), (-112, -32), (-74, -60), (-34, -80), (-8, -87)], 7.5),
    ([(-8, -87), (8, -87)], 2.6),
    ([(8, -87), (24, -100), (42, -110), (56, -119)], 8.0),
    # round the rock of the south crossing
    ([(56, -119), (48.5, -127), (48.5, -143), (56, -151)], 2.6),
    ([(56, -119), (63.5, -127), (63.5, -143), (56, -151)], 2.6),
    ([(56, -151), (64, -168), (82, -200), (92, -250), (100, -292), (104, -330)], 8.5),
    # the tributary from the west
    ([(-330, 112), (-270, 110), (-224, 104)], 5.5),
    ([(-224, 104), (-208, 104)], 2.6),
    ([(-208, 104), (-196, 98), (-182, 84)], 5.5),
    # the east river
    ([(128, 330), (128, 296), (124, 262), (112, 226), (108, 201)], 7.0),
    ([(108, 201), (108, 185)], 2.6),
    ([(108, 185), (118, 160), (140, 128), (166, 108), (178, 101)], 7.5),
    ([(178, 101), (178, 85)], 2.6),
    ([(178, 85), (196, 62), (220, 36), (226, 14), (220, -2), (204, -14), (184, -28), (171, -33)], 7.5),
    ([(171, -33), (155, -33)], 2.6),
    ([(155, -33), (128, -50), (96, -66), (60, -84), (24, -100)], 7.5),
    # the creek's last stretch, from under its fall off the plateau
    ([(68, -47), (70, -58), (66, -76), (60, -84)], 2.0),
]
RIVER_UP = []                     # (no upper reaches: the channels are the sea's)
FALL_Y = 1e9
BROOK_LINE = ([(38, 41), (48, 30), (60, 14), (64, -8), (66, -30), (68, -44.5)], 1.3)
POND_AT = (38.0, 49.5, 4.0)       # in the mountain's south wall
POOL_AT = (38.0, 41.0, 4.0)       # on the plateau under it
# stone slabs over the creek (x, y, half x, half y, level): the ground runs on over the water there
SLABS = [(64.6, -14.0, 3.0, 2.5, RUINS_Z), (69.0, -62.0, 9.5, 2.5, 0.0)]
# the bridges (SM_Bridge, 7 m): name -> (x, y, yaw). yaw 90 runs east-west, 0 north-south. All at level 0.
BRIDGES = dict(nw=(-90.0, 152.0, 90.0), w=(-178.0, 45.0, 90.0), s=(0.0, -87.0, 0.0), big_w=(48.5, -135.0, 90.0), big_e=(63.5, -135.0, 90.0),
               trib=(-216.0, 104.0, 0.0), n=(108.0, 193.0, 90.0), e=(178.0, 93.0, 90.0), se=(163.0, -33.0, 0.0))

# ---- the mountain: the massif's outline, and its peaks (x, y, how high over its shoulders, how far it reaches)
M_POLY = [(-70, 56), (-84, 96), (-66, 134), (-46, 172), (-42, 204), (-28, 234), (18, 246), (58, 244), (76, 226), (82, 200), (104, 176),
          (125, 150), (126, 104), (126, 36), (112, 22), (88, 24), (62, 36), (22, 42), (-6, 64), (-40, 54)]
SHOULDER = 18.0
# (eleven peaks: the summit in the middle, a crown of lesser ones round it; the massif is one mountain, 200 x 240 m)
PEAKS = [(28.0, 146.0, 172.0, 118.0), (-34.0, 116.0, 112.0, 66.0), (84.0, 152.0, 128.0, 68.0), (92.0, 78.0, 88.0, 56.0), (22.0, 76.0, 66.0, 50.0),
         (-12.0, 190.0, 104.0, 62.0), (54.0, 204.0, 96.0, 56.0), (-46.0, 162.0, 76.0, 46.0), (84.0, 194.0, 66.0, 40.0), (-42.0, 78.0, 54.0, 38.0),
         (8.0, 224.0, 56.0, 36.0)]
# the way round the mountain's north (the north crossing to the north bridge): the mountain keeps off it
NORTH_WAY = [(-74.0, 146.0), (-62.0, 176.0), (-58.0, 208.0), (-46.0, 240.0), (-14.0, 262.0), (40.0, 264.0), (80.0, 252.0), (92.0, 228.0), (95.0, 204.0)]
SNOW_LINE = 150.0
RUINS = [(-48, 8), (-34, 26), (-4, 32), (14, 44), (40, 46), (64, 38), (94, 22), (96, -22), (74, -44), (30, -50), (-14, -46), (-44, -30)]
UPPER = [(-52, 34), (-40, 62), (-12, 66), (6, 48), (0, 32), (-28, 28)]


def _oval(x, y, rx, ry, n=20):
    return [(x + rx * math.cos(2 * math.pi * k / n), y + ry * math.sin(2 * math.pi * k / n)) for k in range(n)]


# ---- the flat-topped hills: name, outline of the top, its level; what it is (top: "build" = open ground to build on,
# "tower" = a watch tower's hill, "wild" = nobody gets up there)
MESAS = [
    dict(name="ruins", poly=RUINS, z=RUINS_Z, top="build", team="Neutral"),
    dict(name="upper", poly=UPPER, z=UPPER_Z, top="build", team="Neutral"),
    dict(name="wbluff", poly=[(-324, -128), (-262, -124), (-250, -104), (-247, -78), (-247, -46), (-256, -22), (-276, -6), (-324, -2)], z=BLUFF_Z, top="build", team=0),
    dict(name="nbluff", poly=[(196, 324), (200, 262), (214, 250), (236, 246.5), (266, 246.5), (286, 252), (300, 266), (324, 270), (324, 324)], z=BLUFF_Z, top="build", team=1),
    dict(name="knoll_s", poly=_oval(-56, -226, 24, 15), z=5.0, top="wild"),
    dict(name="knoll_se", poly=_oval(168, -122, 18, 13), z=5.0, top="wild"),
    dict(name="knoll_nw", poly=_oval(-128, 262, 20, 14), z=6.0, top="wild"),
    dict(name="knoll_w", poly=_oval(-268, -196, 16, 22), z=5.0, top="wild"),
    dict(name="knoll_e", poly=_oval(196, -238, 20, 12), z=4.0, top="wild"),
]
# ---- the ways up: (name, from (x, y, z), to (x, y, z), half width, surface). The floor rises evenly from one end to the
# other in quarter-block shelves (a ramp: a shelf every metre and more; STONE: a stair), and the hillside beside it
# steps up and down from it in one-metre terraces: a road along the slope, never a slot or a wall.
RAMPS = [
    ("ruins_s", (-62.0, -51.0, 0.0), (4.0, -40.0, RUINS_Z), 4.5, DIRT),
    ("ruins_w", (-100.0, 24.0, 1.0), (-42.0, 0.0, RUINS_Z), 4.5, DIRT),
    ("ruins_e", (140.0, 8.0, 0.0), (84.0, -8.0, RUINS_Z), 4.5, DIRT),
    ("upper", (-8.0, 22.0, RUINS_Z), (-22.0, 38.5, UPPER_Z), 2.25, STONE),
    ("wbluff", (-238.0, -18.0, 0.0), (-277.0, -32.0, BLUFF_Z), 4.0, DIRT),
    ("nbluff", (190.0, 238.0, 0.0), (212.0, 276.0, BLUFF_Z), 4.0, DIRT),
    ("port0", (-274.0, -176.0, 0.0), (-292.0, -176.0, DOCK_Z), 2.25, STONE),
    ("port1", (274.0, 150.0, 0.0), (292.0, 150.0, DOCK_Z), 2.25, STONE),
]
# ---- the neutral mines' rocks (x, y, radius), the towers' mounds by the home mines (x, y, radius)
TOR_NW = (-196.0, 222.0, 18.0)
TOR_SE = (264.0, -214.0, 18.0)
# A watch tower never stands on a drum of rock with sheer walls and a stair (owner's rule, 2026-11-22: References/Remake/
# tower_cylinder_bad.png). The towers by the home mines stand on the level ground; the two hill towers on KNOLLS:
# (x, y, the level top's radius, how high, how far the slope runs, seed): natural hills that anyone walks up from any
# side, their foot wandering, rising in shelves of a quarter block.
KNOLLS = [(-252.0, 48.0, 10.0, HILL_Z, 22.0, 3), (266.0, 6.0, 10.0, HILL_Z, 22.0, 7)]
# low rounded hills between the pockets, wooded (the same shape: walked over from any side)
HILLOCKS = [(-96.0, -176.0, 8.0, 4.0, 26.0, 11), (-226.0, -238.0, 6.0, 3.5, 22.0, 12), (-150.0, 2.0, 7.0, 4.5, 24.0, 13), (-266.0, 150.0, 8.0, 5.0, 24.0, 14),
            (-150.0, 262.0, 8.0, 4.0, 22.0, 15), (196.0, 60.0, 6.0, 3.5, 18.0, 16), (150.0, -92.0, 8.0, 4.5, 24.0, 17), (60.0, -236.0, 9.0, 5.0, 26.0, 18),
            (236.0, -148.0, 7.0, 4.0, 22.0, 19), (176.0, 262.0, 7.0, 4.0, 20.0, 20), (-40.0, -128.0, 6.0, 3.0, 18.0, 21), (212.0, -20.0, 6.0, 3.5, 18.0, 22)]

# ---- the island. Its coast (a rounded square, wobbling; straight at the two ports), the islets off it (x, y, half size:
# rocks with a tree, nobody reaches them), and the ports: one per side, on its own coast near its castle.
def _coast():
    pts = []
    for k in range(72):
        a = 2 * math.pi * k / 72
        c, sn = math.cos(a), math.sin(a)
        r = 297.0 / (abs(c) ** 8 + abs(sn) ** 8) ** 0.125
        r *= 0.975 + 0.022 * math.sin(3 * a + 1.0) + 0.018 * math.sin(7 * a + 0.4) + 0.012 * math.sin(13 * a + 2.0)
        x, y = max(-309.0, min(309.0, r * c)), max(-309.0, min(309.0, r * sn))
        if x < -250 and -214 < y < -140:
            x = -292.0
        if x > 250 and 112 < y < 188:
            x = 292.0
        pts.append((round(x, 1), round(y, 1)))
    return pts


COAST = _coast()
ISLETS = [(-150.0, -313.0, 5.0), (40.0, 313.0, 5.5), (313.0, -60.0, 5.0), (-313.0, 220.0, 5.0), (228.0, -312.0, 6.0)]
# a port: the quay (a shelf of the cliff's foot at DOCK_Z: x0, y0, x1, y1), the stair down to it (a RAMPS entry), the
# pier (SM_Dock: its land end, its yaw), and what stands there (mesh, x, y, z, yaw)
PORTS = (
    dict(team=0, quay=(-305.0, -197.0, -292.0, -157.0), sign=-1.0, dock=((-305.0, -166.0), -90.0),
         things=[("SM_Port_Warehouse", -298.5, -189.0, DOCK_Z, -90.0), ("SM_Port_Crane", -301.5, -159.5, DOCK_Z, -90.0), ("SM_Port_Arch", -292.5, -182.0, DOCK_Z, -90.0),
                 ("SM_Port_Tower", -283.0, -202.0, 0.0, -90.0)]),
    dict(team=1, quay=(292.0, 130.0, 305.0, 170.0), sign=1.0, dock=((305.0, 161.0), 90.0),
         things=[("SM_Port_Warehouse", 298.5, 138.0, DOCK_Z, 90.0), ("SM_Port_Crane", 301.5, 167.5, DOCK_Z, 90.0), ("SM_Port_Arch", 292.5, 145.0, DOCK_Z, 90.0),
                 ("SM_Port_Tower", 283.0, 124.0, 0.0, 90.0)]),
)

# ---- the sky (AVLSky): clouds (x, y, z, half sizes x, y, z; metres) and flocks of birds (x, y, z, the loop's radius).
# The clouds wreathe the mountain's flanks at mid-height, lie in banks beyond the map's edges and in a few wisps over
# the valleys; the game puffs a cloud away when the camera comes near it or rises to its height, so none ever hides the
# ground from the overview. The birds: some at the clouds' height, some lower, some higher.
def _sky():
    clouds = []
    cx, cy = PEAKS[0][0], PEAKS[0][1] - 10.0
    for k in range(14):                                                     # small puffs low round the mountain
        a = 2 * math.pi * (k + 0.3) / 14
        r = 100.0 + 34.0 * float(hash2(np.array(k), np.array(1), 61))
        z = 58.0 + 62.0 * float(hash2(np.array(k), np.array(2), 61))
        clouds.append((round(cx + r * math.cos(a) * 0.95, 1), round(cy + r * math.sin(a) * 1.15, 1), round(z, 1), 9.0 + 3.0 * (k % 3), 7.0 + 2.0 * (k % 2), 5.0))
    for k in range(12):                                                     # banks beyond the edges
        a = 2 * math.pi * (k + 0.5) / 12
        r = 372.0 + 40.0 * float(hash2(np.array(k), np.array(3), 61))
        clouds.append((round(r * math.cos(a), 1), round(r * math.sin(a), 1), round(58.0 + 34.0 * float(hash2(np.array(k), np.array(4), 61)), 1), 30.0, 20.0, 9.0))
    for (x, y, z) in ((-150.0, 104.0, 66.0), (64.0, -156.0, 72.0), (206.0, 44.0, 64.0), (-118.0, -36.0, 76.0), (112.0, 256.0, 70.0), (-250.0, 180.0, 82.0)):
        clouds.append((x, y, z, 9.0, 7.0, 3.5))                            # wisps over the valleys
    flocks = [(cx, cy, 128.0, 150.0), (cx + 10.0, cy + 20.0, 96.0, 118.0), (cx - 10.0, cy, 226.0, 90.0), (-150.0, -110.0, 62.0, 95.0),
              (210.0, 120.0, 70.0, 100.0), (40.0, -170.0, 104.0, 120.0), (-190.0, 190.0, 150.0, 110.0)]
    return dict(clouds=clouds, flocks=flocks, birds_per_flock=6)


# ---- the level places of the plan: (name, x, y, rx, ry, level, team, kind). The lowland is flattened to `level` inside
# each; kind "build": a buildable area of the annotated map (open, level ground); "zone": a contested zone;
# "apron": level ground something needs (a bridge's end, a mine's mouth, a stair's foot).
FLATS = [
    ("home0", -176.0, -124.0, 62.0, 50.0, 0.0, 0, "build"),
    ("south0", -138.0, -226.0, 44.0, 34.0, 1.0, 0, "build"),
    ("east0", -112.0, -92.0, 36.0, 26.0, 0.0, 0, "build"),
    ("north0", -222.0, 64.0, 24.0, 28.0, 1.0, 0, "build"),
    ("mine0", -234.0, -66.0, 18.0, 22.0, 0.0, 0, "apron"),
    ("home1", 240.0, 152.0, 58.0, 50.0, 0.0, 1, "build"),
    ("north1", 164.0, 196.0, 30.0, 26.0, 1.0, 1, "build"),
    ("south1", 274.0, 84.0, 28.0, 28.0, 1.0, 1, "build"),
    ("mine1", 250.0, 232.0, 26.0, 14.0, 0.0, 1, "apron"),
    ("northwest", -206.0, 166.0, 38.0, 30.0, 2.0, "Neutral", "build"),
    ("mine_nw", -196.0, 198.0, 18.0, 12.0, 2.0, "Neutral", "apron"),
    ("westfoot", -122.0, 74.0, 34.0, 30.0, 1.0, "Neutral", "build"),
    ("northvale", 14.0, 276.0, 48.0, 15.0, 1.0, "Neutral", "build"),
    ("port0", -268.0, -176.0, 14.0, 16.0, 0.0, 0, "apron"),
    ("port1", 268.0, 150.0, 14.0, 16.0, 0.0, 1, "apron"),
    ("eastshelf", 152.0, 48.0, 22.0, 30.0, 0.0, "Neutral", "build"),
    ("southeast", 124.0, -188.0, 44.0, 34.0, 1.0, "Neutral", "build"),
    ("east", 236.0, -86.0, 34.0, 34.0, 0.0, "Neutral", "build"),
    ("mine_se", 238.0, -214.0, 14.0, 18.0, 1.0, "Neutral", "apron"),
    ("north_crossing", -70.0, 148.0, 17.0, 24.0, 0.0, "Neutral", "zone"),
    ("south_crossing", 6.0, -160.0, 34.0, 22.0, 0.0, "Neutral", "zone"),
    ("southtip", -2.0, -70.0, 22.0, 9.0, 0.0, "Neutral", "apron"),
    ("ford", 69.0, -62.0, 12.0, 8.0, 0.0, "Neutral", "apron"),
]
FLATS += [("bridge_" + k, v[0], v[1], 13.0, 13.0, 0.0, "Neutral", "apron") for k, v in BRIDGES.items()]

# ---- buildings: name -> (mesh, x, y, z, yaw, team). Fronts face -Y at yaw 0, -X (west) at yaw -90, +X (east) at yaw 90.
KIND = {"SM_Dock": "Dock", "SM_Castle": "Castle", "SM_MineCliff": "Gold Mine", "SM_WatchTower": "Watch Tower", "SM_Bridge": "Bridge", "SM_PlazaBanner": "Village Banner"}
# Each side starts with its castle, its home mine, the watch tower beside that mine and the watch tower on its hill.
# No farm, no cottages, no barracks: Builders raise them. A mine is set into the face it stands by: its middle 3 m
# inside the face (2.5 m of it stand proud).
BUILD = dict(
    castle0=("SM_Castle", -176.0, -118.0, 0.0, 0.0, 0),
    mine0=("SM_MineCliff", -250.0, -62.0, 0.0, 90.0, 0),                # in the west bluff's east face
    tower0=("SM_WatchTower", -221.0, -80.0, MOUND_Z, -90.0, 0),
    tower0b=("SM_WatchTower", -252.0, 48.0, HILL_Z, 0.0, 0),            # the player's hill tower (W)
    castle1=("SM_Castle", 246.0, 152.0, 0.0, -90.0, 1),                 # (faces west, towards the mountain)
    mine1=("SM_MineCliff", 250.0, 249.5, 0.0, 0.0, 1),                  # in the north bluff's south face
    tower1=("SM_WatchTower", 273.0, 224.0, MOUND_Z, -90.0, 1),
    tower1b=("SM_WatchTower", 266.0, 6.0, HILL_Z, -90.0, 1),            # the enemy's hill tower (E)
    mine_nw=("SM_MineCliff", TOR_NW[0], TOR_NW[1] - TOR_NW[2] + 3.0, 2.0, 0.0, "Neutral"),        # faces south, in its tor
    mine_se=("SM_MineCliff", TOR_SE[0] - TOR_SE[2] + 3.0, TOR_SE[1], 1.0, -90.0, "Neutral"),      # faces west, in its tor
    mine_c=("SM_MineCliff", 123.0, 60.0, 0.0, 90.0, "Neutral"),         # centre-east: in the mountain's east wall
)
HILLS = dict(mine_nw=(7.0, (6.0, 10.0), 5), mine_se=(7.0, (6.0, 10.0), 9))      # minehill.hill: crest, reach, seed
NEUTRAL_MINES = ("mine_nw", "mine_c", "mine_se")


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

PLAZA0 = (-176.0, -132.0)
PLAZA1 = (round(G_["castle1"][0] - 8.3, 3), G_["castle1"][1])     # (west of its door)
PLAZA = (PLAZA0, PLAZA1)
SPAWN = (-176.0, -128.0, -120.0)  # x, y, facing (degrees from +X): in front of the player's castle, facing the viewer
START1 = (round(G_["castle1"][0] - 2.3, 3), G_["castle1"][1], 180.0)
RALLY0 = (-154.0, -136.0)         # where each side's troops gather: by its main road
RALLY1 = (216.0, 140.0)
# the contested zones: tagged points of the level (terrain only: nothing captures them yet)
ZONES = dict(NorthCrossing=(-70.0, 148.0), SouthCrossing=(6.0, -160.0), Ruins=(24.0, -12.0))


def bridge_ends(name):
    bx, by, yaw = BRIDGES[name]
    return ((bx - 3.5, by), (bx + 3.5, by)) if yaw else ((bx, by - 3.5), (bx, by + 3.5))


def _roads():
    """The roads: (points [(x, y)], half width, surface). They lie on the ground as it is (the ramps and stairs are
    RAMPS). Cobbles from each castle to its mine and its nearest bridges; dirt tracks elsewhere."""
    P0, P1 = PLAZA0, PLAZA1
    be = bridge_ends
    out = [
        # ---- the player's
        ([G_["castle0"], P0], 1.8, COBBLE),
        ([P0, (-200.0, -130.0), (-224.0, -104.0), (-238.0, -82.0), G_["mine0"]], 1.4, COBBLE),                        # the mine road
        ([(-238.0, -80.0), G_["tower0"]], 1.3, COBBLE),                                                            # to the tower's steps
        ([P0, (-144.0, -128.0), (-96.0, -110.0), (-48.0, -100.0), (-12.0, -98.0), be("s")[0]], 2.0, COBBLE),           # to the south bridge (the ruins)
        ([(-96.0, -110.0), (-52.0, -138.0), (-4.0, -146.0), (30.0, -137.0), be("big_w")[0]], 2.0, COBBLE),             # to the south crossing
        ([(-200.0, -130.0), (-206.0, -60.0), (-212.0, 10.0), (-200.0, 40.0), be("w")[0]], 1.2, DIRT),                  # north: the west bridge
        ([(-212.0, 10.0), (-240.0, 14.0), (-256.0, 28.0), G_["tower0b"]], 1.2, DIRT),                                                # the hill tower's stair
        ([(-200.0, 40.0), (-214.0, 76.0), (-216.0, 94.0), be("trib")[0]], 1.2, DIRT),                                  # the tributary's bridge
        ([(-238.0, -18.0), (-222.0, -30.0), (-207.0, -44.0)], 1.2, DIRT),                                             # the bluff's ramp
        ([P0, (-212.0, -150.0), (-246.0, -172.0), (-274.0, -176.0)], 1.4, COBBLE),                                    # the port
        # ---- the enemy's
        ([G_["castle1"], P1], 1.8, COBBLE),
        ([P1, (226.0, 172.0), (236.0, 204.0), (247.0, 228.0), G_["mine1"]], 1.4, COBBLE),                             # the mine road
        ([(247.0, 228.0), (254.0, 224.0), G_["tower1"]], 1.3, COBBLE),
        ([P1, (212.0, 136.0), (196.0, 104.0), be("e")[1]], 2.0, COBBLE),                                              # to the east bridge (the mountain)
        ([(226.0, 172.0), (190.0, 196.0), (150.0, 200.0), be("n")[1]], 1.2, DIRT),                                    # to the north bridge
        ([(212.0, 136.0), (236.0, 100.0), (250.0, 56.0), (248.0, 20.0), (246.0, 6.0), (244.0, -30.0), (232.0, -64.0)], 1.2, DIRT),     # south, under the hill tower
        ([(246.0, 6.0), G_["tower1b"]], 1.2, DIRT),
        ([(190.0, 238.0), (206.0, 216.0), (226.0, 190.0)], 1.2, DIRT),                                                # the bluff's ramp
        ([G_["castle1"], (240.0, 136.0), (258.0, 140.0), (274.0, 150.0)], 1.4, COBBLE),                               # the port
        # ---- the massif
        ([be("s")[1], (0.0, -72.0), (-30.0, -58.0), (-62.0, -51.0)], 1.4, DIRT),                                      # up the south ramp
        ([be("w")[1], (-150.0, 52.0), (-122.0, 50.0), (-100.0, 24.0)], 1.2, DIRT),                                    # the west foot, the west ramp
        ([(-122.0, 50.0), (-112.0, 96.0), (-86.0, 128.0), (-74.0, 146.0), be("nw")[1]], 1.2, DIRT),                   # to the north crossing
        ([p for p in NORTH_WAY] + [be("n")[0]], 1.2, DIRT),                                                          # round the mountain's north
        ([be("e")[0], (160.0, 78.0), (146.0, 62.0), G_["mine_c"]], 1.4, DIRT),                                        # the east shelf, the mine
        ([(146.0, 62.0), (148.0, 30.0), (140.0, 8.0)], 1.2, DIRT),                                                    # the east ramp
        ([(148.0, 30.0), (160.0, -6.0), be("se")[1]], 1.2, DIRT),
        # on the ruins plateau: old paving between the ramps' heads, the slab over the creek and the stair
        ([(4.0, -40.0), (20.0, -24.0), (40.0, -14.0), (61.0, -14.0)], 1.6, STONE),
        ([(68.0, -14.0), (76.0, -12.0), (84.0, -8.0)], 1.6, STONE),
        ([(-42.0, 0.0), (-20.0, -10.0), (20.0, -24.0)], 1.6, STONE),
        ([(-20.0, -10.0), (-10.0, 10.0), (-8.0, 22.0)], 1.6, STONE),
        # ---- the north-west and the south-east countries
        ([be("nw")[0], (-120.0, 168.0), (-160.0, 190.0), G_["mine_nw"]], 1.2, DIRT),
        ([be("trib")[1], (-214.0, 134.0), (-204.0, 168.0), (-198.0, 190.0), G_["mine_nw"]], 1.2, DIRT),
        ([be("big_e")[1], (96.0, -146.0), (150.0, -176.0), (206.0, -206.0), G_["mine_se"]], 1.2, DIRT),
        ([be("se")[0], (176.0, -62.0), (206.0, -84.0), (232.0, -64.0)], 1.2, DIRT),
        ([(206.0, -84.0), (190.0, -130.0), (150.0, -176.0)], 1.2, DIRT),
        ([be("big_w")[1], be("big_e")[0]], 2.0, COBBLE),                                                               # over the rock in midstream
    ]
    return out


PATHS = _roads()
APRONS = [G_[k] for k in G_] + [e for b in BRIDGES for e in bridge_ends(b)]
PLAZAS = [PLAZA0, PLAZA1]

# How many trees (the budget; the wild woods on the rim, the mountain's feet and the knolls come on top: WILD_SHARE).
# Faces each, near / far: A 101k / 9k, B 94k / 8k, C 37k / 3k, D 10k / 1k.
TREES = dict(A=12, B=12, C=200, D=3300)
WILD_SHARE = (0.2, 0.6)          # the chance a wild-wood candidate is kept, thinnest to thickest stand
TREE_GAP = {"A": 12.0, "B": 11.0, "C": 8.0, "D": 4.8}
TREE_CLEAR = {"A": 3.6, "B": 3.4, "C": 2.2, "D": 1.3}
BUILD_MARGIN = 1.5
THIN = 0.01


# ---------------------------------------------------------------------------------------------------- noise

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
    """A ridged sum, 0 .. 1: each octave is a field of sharp crests (1 - |n|, squared), weighted by the octave before,
    so the detail gathers on the ridges and the valleys stay smooth."""
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
    """Domain warping: every place is looked up a little way off, by a slow noise."""
    return X + amp * fbm(X, Y, scale, seed, 2), Y + amp * fbm(X, Y, scale, seed + 53, 2)


def steps(v):
    """A height in units of one step, cut into a riser (the first half) and a tread (the second)."""
    k = np.floor(v)
    return k + np.clip((v - k) * 2.0, 0.0, 1.0)


# ---------------------------------------------------------------------------------------------------- the ground

def grid():
    a = -HALF + (np.arange(N) + 0.5) * CELL
    return np.meshgrid(a, a, indexing="ij")


def box(x0, y0, x1, y1, pad=0.0):
    """The grid's slices over a rectangle of the map."""
    i0, i1 = max(0, int((x0 - pad + HALF) / CELL)), min(N, int((x1 + pad + HALF) / CELL) + 1)
    j0, j1 = max(0, int((y0 - pad + HALF) / CELL)), min(N, int((y1 + pad + HALF) / CELL) + 1)
    return (slice(i0, i1), slice(j0, j1))


def poly_box(poly, pad):
    return box(min(p[0] for p in poly), min(p[1] for p in poly), max(p[0] for p in poly), max(p[1] for p in poly), pad)


def sdist(X, Y, poly):
    """Signed distance to a polygon: > 0 inside."""
    d = dist_polyline(X, Y, list(poly) + [poly[0]])
    return np.where(in_poly(X, Y, poly), d, -d)


def river_dist(X, Y, stretches, sl=None):
    """Metres to the water's edge (< 0 in the water). Each stretch is only looked at near itself."""
    d = np.full(X.shape, 1e9)
    for pts, hw in stretches:
        for a, b in zip(pts[:-1], pts[1:]):
            s = box(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]), hw + 30.0)
            d[s] = np.minimum(d[s], seg_dist(X[s], Y[s], a, b)[0] - hw)
    return d


def rect_mask(X, Y, cx, cy, hx, hy):
    return (np.abs(X - cx) <= hx) & (np.abs(Y - cy) <= hy)


def bridge_rect(X, Y, name, half_len, half_w):
    bx, by, yaw = BRIDGES[name]
    return rect_mask(X, Y, bx, by, half_len, half_w) if yaw else rect_mask(X, Y, bx, by, half_w, half_len)


def min_near(h, k):
    """The lowest ground within k cells (a square)."""
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


def flat_weight(X, Y, f, skirt=14.0):
    """1 inside a level place, falling to 0 over `skirt` metres outside it."""
    _n, x, y, rx, ry = f[:5]
    e = np.hypot((X - x) / rx, (Y - y) / ry)
    return np.clip(1.0 - (e - 1.0) * min(rx, ry) / skirt, 0.0, 1.0)


def lowland(X, Y):
    """The valley floor: a slow roll of 0 to 3.5 m, level at every place of the plan."""
    b = 3.6 * np.clip((noise2(X, Y, 170.0, 901, octaves=2) - 0.28) / 0.5, 0.0, 1.0) ** 1.2
    keep = np.zeros(X.shape)
    for f in FLATS:
        s = box(f[1] - f[3], f[2] - f[4], f[1] + f[3], f[2] + f[4], 16.0)
        w = flat_weight(X[s], Y[s], f)
        w = w * w * (3.0 - 2.0 * w)
        b[s] = b[s] * (1.0 - w) + f[5] * w
        if f[7] in ("zone", "build") or f[0].startswith("bridge"):
            keep[s] = np.maximum(keep[s], flat_weight(X[s], Y[s], f, 5.0))
    return b, keep


def mountain(X, Y, keep):
    """The massif, metres (0 outside it). Carpathian's recipe in spirit: a base that rises quickly from the foot, peaks
    joined by ridges (a ridged sum over warped ground), and a share of it cut into steps by a slow noise."""
    s = poly_box(M_POLY, 34.0)
    x, y = X[s], Y[s]
    calm = np.clip((np.hypot(x - 126.0, y - 60.0) - 14.0) / 22.0, 0.0, 1.0)           # (the wall stands where the plan says at the mine)
    xw, yw = warp(x, y, 16.0, 90.0, 700)
    xw, yw = warp(xw, yw, 5.0, 26.0, 720)
    xw, yw = x + (xw - x) * calm, y + (yw - y) * calm
    d_in = sdist(xw, yw, M_POLY)
    foot = np.clip(d_in / 11.0, 0.0, 1.0) ** 0.75
    env = np.zeros(x.shape)
    for (px, py, ph, pr) in PEAKS:                                          # (hollow flanks: steep at the top, broad at the foot)
        env += (ph * np.clip(1.0 - np.hypot(xw - px, yw - py) / pr, 0.0, 1.0) ** 1.5) ** 4
    env = env ** 0.25
    rd = ridged(xw, yw, 62.0, 740)
    rd2 = ridged(x, y, 21.0, 750, 3)
    var = noise2(x, y, 80.0, 780)
    h = SHOULDER * foot + env * (0.56 + 0.56 * rd) * foot + (9.0 * (rd2 - 0.35) * np.clip(env / 40.0, 0.25, 1.0) + 5.0 * fbm(x, y, 30.0, 760, 3)) * foot
    # the shoulders: below 100 m the mountain is cut into benches 10 m apart (grass and forest on the treads, cliffs
    # between them), nearly everywhere; higher up only where the slow noise says
    hs = steps(h / 10.0 + 0.25 * fbm(x, y, 40.0, 770, 2)) * 10.0
    low = np.clip((105.0 - h) / 40.0, 0.0, 1.0)
    h = h + (hs - h) * np.clip(0.9 * low + np.clip((var - 0.25) / 0.4, 0.0, 1.0) * 0.6, 0.0, 0.95)
    # crags: in bands the rock breaks off in cliffs of two and four metres instead of one-metre terraces
    crag = noise2(x, y, 34.0, 790, octaves=2) + 0.3 * np.clip((h - 40.0) / 90.0, 0.0, 1.0)
    q = np.where(crag > 0.74, 8.0, np.where(crag > 0.6, 4.0, np.where(crag > 0.46, 2.0, 1.0)))
    h = np.floor(h / q + 0.5 * hash2(np.floor(x / 3.0), np.floor(y / 3.0), 795)) * q
    way = np.clip((dist_polyline(x, y, NORTH_WAY) - 7.0) / 5.0, 0.0, 1.0)
    h = np.where(d_in > 0, np.maximum(h, 3.0), 0.0) * np.where((1.0 - keep[s]) * way >= 0.999, 1.0, 0.0)
    out = np.zeros(X.shape)
    out[s] = np.where(h >= 1.5, np.maximum(np.round(h), 3.0), 0.0)
    return out


def rim_hills(X, Y):
    """The wooded hills that close the valley: metres (0 inside it). They rise from a wandering foot 20 to 40 m inside
    the edge in one-metre terraces; higher along the north (the far range stands behind it)."""
    d_edge = HALF - np.maximum(np.abs(X), np.abs(Y))
    wide = 22.0 + noise2(X, Y, 64.0, 811) * 20.0 + (noise2(X, Y, 17.0, 813) - 0.5) * 6.0
    u = np.clip((wide - d_edge) / wide, 0.0, 1.0)
    north = np.clip((Y - 200.0) / 100.0, 0.0, 1.0)
    h = u ** 0.85 * (10.0 + noise2(X, Y, 40.0, 815) * 9.0 + 7.0 * north) + (noise2(X, Y, 9.0, 817) - 0.5) * 3.0 * u
    return np.where(u > 0, np.maximum(np.round(h + 1.5), 2.0), 0.0)


def mesa_field(X, Y, m, n1, n2, calm):
    """A flat-topped hill: (heights, top mask) on the cells of its box. Its sides are rock: steps of two metres, a
    metre or so deep each."""
    d = sdist(X, Y, m["poly"]) + (n2 - 0.5) * 3.0 * calm
    z = m["z"]
    wf = np.maximum(2.5, 0.55 * z) + (n1 - 0.5) * 2.0
    prof = np.clip(1.0 + d / wf, 0.0, 1.0)
    h = np.where(d >= 0, z, np.minimum(z, np.ceil(prof * z / 2.0) * 2.0))
    return np.where(prof > 0, h, 0.0), d >= 0


def ramp_fields(X, Y, h):
    """Cuts the ways up into the ground: -> (h, floor mask, surface (-1: none), stair mask)."""
    floor = np.zeros(X.shape, bool)
    sides = np.zeros(X.shape, bool)
    surf = np.full(X.shape, -1, np.int8)
    stair = np.zeros(X.shape, bool)
    for (_name, a, b, hw, sf) in RAMPS:
        reach = hw + abs(b[2] - a[2]) + 3.0
        s = box(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]), reach)
        e, t = seg_dist(X[s], Y[s], a, b)
        zr = a[2] + np.round(t * (b[2] - a[2]) / 0.25) * 0.25
        side = np.ceil(np.clip(e - hw, 0.0, None))                       # one-metre terraces beside the floor
        hh = np.clip(h[s], zr - side, zr + side)
        fl = e <= hw
        sides[s] |= ~fl & (hh != h[s])
        hh = np.where(fl, zr, hh)
        h[s] = hh
        floor[s] |= fl
        if sf == STONE:
            surf[s] = np.where(fl, STONE, surf[s])
            stair[s] |= fl & (t > 0.0) & (t < 1.0)
        else:
            surf[s] = np.where(fl & (e < 1.3 + (noise2(X[s], Y[s], 2.2, 5) - 0.5) * 0.7), sf, surf[s])
    return h, floor, surf, stair, sides & ~floor


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
        surf[s] = np.where(plaza & (surf[s] < 0), COBBLE, surf[s])
        best[s] = np.minimum(best[s], np.hypot(X[s] - p[0], Y[s] - p[1]) - 4.2)
    return surf, best


def heights():
    X, Y = grid()
    n1, n2, n3 = noise2(X, Y, 14.0, 3), noise2(X, Y, 7.0, 17), noise2(X, Y, 26.0, 131)

    # ---- the valley floor, in quarter-block shelves that wander
    b, keep = lowland(X, Y)
    h = np.round((b + (noise2(X, Y, 5.0, 903) - 0.5) * 0.22) / 0.25) * 0.25
    R = {}

    # ---- the hills that close the valley, the mountain
    rim = np.zeros(X.shape)                                                 # (no hills round the edge: the island ends in sea cliffs)
    mt = mountain(X, Y, keep)
    h = np.maximum(h, np.maximum(rim, mt))
    R["rim"], R["mountain"] = rim > 0, mt > 0

    # ---- the flat-topped hills (not at a mine set in their face, not at a way up: their edge is the plan's there)
    calm = np.ones(X.shape)
    for k in ("mine0", "mine1"):
        calm *= np.clip((np.hypot(X - BUILD[k][1], Y - BUILD[k][2]) - 12.0) / 10.0, 0.0, 1.0)
    for (_n, a, bb, hw, _s) in RAMPS:
        calm *= np.clip((seg_dist(X, Y, a, bb)[0] - hw - 2.0) / 8.0, 0.0, 1.0)
    tops = {}
    flank = np.zeros(X.shape, bool)
    for m in MESAS:
        s = poly_box(m["poly"], 12.0)
        mh, top = mesa_field(X[s], Y[s], m, n1[s], n2[s], calm[s])
        hh = h[s]
        if m["name"] in ("ruins", "upper"):                                 # cut level out of the mountain's shoulder
            hh = np.where(top, m["z"], np.maximum(hh, mh))
        else:
            hh = np.maximum(hh, mh)
        flank[s] |= (mh > 0) & ~top
        t = np.zeros(X.shape, bool)
        t[s] = top & (hh == m["z"])
        tops[m["name"]] = t
        h[s] = hh
    R["flank"] = flank

    # ---- the rocks of the two far neutral mines (hills that roll off in one-metre shelves), the towers' mounds
    tor = np.zeros(X.shape, bool)
    for key, (tx, ty, tr) in (("mine_nw", TOR_NW), ("mine_se", TOR_SE)):
        s = box(tx - tr, ty - tr, tx + tr, ty + tr, 16.0)
        x, y = X[s], Y[s]
        base = BUILD[key][3]
        ang = np.arctan2(y - ty, x - tx)
        dt = np.hypot(x - tx, y - ty) - (n2[s] - 0.5) * 3.0 + 1.8 * np.sin(ang * 2 + 0.7 + tx) + 1.2 * np.sin(ang * 3 + 2.1) + 0.8 * np.sin(ang * 5 + 4.0)
        m = dt < tr
        up = np.clip(tr - dt, 0.0, None)
        hh = np.where(m, np.maximum(h[s], base + np.clip(np.ceil(up / 1.5 + np.clip(up - 9.0, 0.0, None) * 0.9), 1.0, 17.0)), h[s])
        crest, reach, seed = HILLS[key]
        mh = minehill.hill(x, y, BUILD[key][1], BUILD[key][2], BUILD[key][4], crest, reach, seed, noise2(x, y, 7.0, 400 + seed))
        hh = np.where(mh > 0, np.maximum(hh, base + mh), hh)
        h[s] = hh
        tor[s] |= m | (mh > 0)
    R["tor"] = tor
    # the hill towers' knolls: up from every side in quarter-block shelves, the foot wandering
    for (kx, ky, kr, kz, run, seed) in KNOLLS + HILLOCKS:
        s = box(kx - kr - run, ky - kr - run, kx + kr + run, ky + kr + run, 8.0)
        x, y = X[s], Y[s]
        ang = np.arctan2(y - ky, x - kx)
        d = np.hypot(x - kx, y - ky) + 3.0 * np.sin(ang * 2 + seed) + 2.0 * np.sin(ang * 3 + 1.3 * seed) + (noise2(x, y, 9.0, 500 + seed) - 0.5) * 5.0
        t = np.clip(1.0 - (d - kr) / run, 0.0, 1.0)
        kh = np.round((kz * t * t * (3.0 - 2.0 * t) + (noise2(x, y, 5.0, 510 + seed) - 0.5) * 0.2) / 0.25) * 0.25
        h[s] = np.maximum(h[s], np.where(t > 0, kh, 0.0))
    R["mound"] = np.zeros(X.shape, bool)

    # ---- the creek's pond in the mountain's wall and its pool on the plateau
    px, py, pr = POND_AT
    qx, qy, qr = POOL_AT
    dpond, dpool = np.hypot(X - px, Y - py), np.hypot(X - qx, Y - qy)
    h = np.where((dpond < pr + 2.5) & (Y >= py - pr + 0.5), np.maximum(h, POND + 0.5), h)
    h = np.where((dpool < qr + 2.0) & (dpond >= pr) & (Y < py - pr + 0.5), RUINS_Z, h)

    # ---- the ways up
    h, rfloor, rsurf, rstair, rsides = ramp_fields(X, Y, h)
    R["rside"] = rsides

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
    quay = np.zeros(X.shape, bool)
    for pt in PORTS:
        q = pt["quay"]
        m = in_rect(X, Y, q)
        quay |= m
        dc = np.where(m, np.maximum(dc, 3.0), dc)
    h = np.where(isle > -2.5, 1.0, h)
    h = np.where(quay & ~rfloor, DOCK_Z, h)

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

    # ---- the water. Where it lies (wz: its surface, NaN on dry ground), the beds, the banks
    near = np.full(X.shape, 1e9)
    for (bx, by, _yaw) in BRIDGES.values():
        near = np.minimum(near, np.hypot(X - bx, Y - by))
    calm_w = np.clip((near - 15.0) / 6.0, 0, 1)                             # the banks are straight at the bridges, ragged elsewhere
    wrag = (noise2(X, Y, 3.0, 21) - 0.5) * 0.9 * calm_w
    d_low = river_dist(X, Y, RIVER_LOW) + wrag
    d_up = river_dist(X, Y, RIVER_UP) + wrag
    d_brook = river_dist(X, Y, [BROOK_LINE]) + wrag * 0.4
    slab = np.zeros(X.shape, bool)
    for (sx, sy, hx, hy, _z) in SLABS:
        slab |= rect_mask(X, Y, sx, sy, hx, hy)
    north = Y > FALL_Y
    water_up = (d_up < 0) & north
    land = (dc > 0) & ~((d_low < 0) & (dc < 6.0))                           # (a channel's mouth is the sea's)
    # (each bridge stands on a neck of land 6 m wide that comes out through the broad water to the narrow channel)
    neck = np.zeros(X.shape, bool)
    for name, (bx, by, yaw) in BRIDGES.items():
        neck |= bridge_rect(X, Y, name, 12.0, 3.0) & ((np.abs(X - bx) if yaw else np.abs(Y - by)) > 2.6)
    water_low = (d_low < 0) & ~north & ~slab & land & ~neck
    water_brook = ((d_brook < 0) | (dpool < qr)) & ~slab & ~water_low & (h <= RUINS_Z + 0.01) & (Y > -45.5)
    water_pond = dpond < pr
    wz = np.full(X.shape, np.nan, np.float32)
    wz[water_low] = WAT
    wz[water_up] = UPN
    wz[water_brook] = BROOK
    wz[water_pond] = POND
    wet = ~np.isnan(wz)
    corridor = np.zeros(X.shape, bool)
    keep_bank = np.zeros(X.shape, bool)
    abut = np.zeros(X.shape, bool)
    for name, (bx, by, yaw) in BRIDGES.items():
        corridor |= bridge_rect(X, Y, name, 4.25, 1.5)
        keep_bank |= bridge_rect(X, Y, name, 12.0, 3.0)
        across = np.abs(X - bx) if yaw else np.abs(Y - by)
        abut |= wet & bridge_rect(X, Y, name, 2.7, 2.0) & (across > 1.25)
    for (sx, sy, hx, hy, _z) in SLABS:
        keep_bank |= rect_mask(X, Y, sx, sy, hx + 0.5, hy + 0.5)
    # the banks: rock that steps down to the water, a metre a step (the land's own height where it is lower)
    h0 = h.copy()
    # (the ravines' walls: terraces a metre and a half high, 1.2 m deep each: 6 m up over 5 m)
    cap = WAT + 0.5 + 1.5 * np.ceil(np.clip(d_low - 0.6, 0.0, None) / 1.2)
    bank = (d_low >= 0) & (d_low < 14.0) & ~north & (cap < h) & ~keep_bank & ~rfloor & ~dilate(water_brook, 6) & land & ~quay
    h = np.where(bank, cap, h)
    bank_up = (d_up >= 0) & (d_up < 6.0) & north
    h = np.where(bank_up, np.maximum(h, UPN + 0.75 + np.ceil(np.clip(d_up - 0.5, 0, None) / 0.8)), h)
    for (wm, d, lvl, deep) in ((water_low, d_low, WAT, 1.5), (water_up, d_up, UPN, 1.0), (water_brook, d_brook, BROOK, 0.5), (water_pond, dpond - pr, POND, 0.75)):
        h = np.where(wm, lvl - min(deep, 0.75), h)
        h = np.where(wm & (d < -0.9), lvl - deep, h)
    h = np.where(abut, -2.5, h)
    for (sx, sy, hx, hy, z) in SLABS:
        h = np.where(rect_mask(X, Y, sx, sy, hx, hy), z, h)
    R["bank"] = bank | bank_up

    # ---- the sea: ragged rock ledges on the cliff's edge, rocks standing in the water at its foot, the bed
    blk = hash2(np.floor((X + 0.4 * np.floor(Y / 1.5)) / 1.5), np.floor(Y / 1.5), 7)
    blk2 = hash2(np.floor(X / 0.75), np.floor(Y / 0.75), 9)
    keep_c = rfloor | quay | dilate(quay, 8)
    for k in BUILD:
        keep_c |= in_rect(X, Y, footprint(k, 1.5))
    cut1 = land & ~wet & (dc < 1.3) & ~keep_c & (blk > 0.62)
    cut2 = land & ~wet & (dc < 2.6) & (dc >= 1.3) & ~keep_c & (blk > 0.8)
    h = np.where(cut1, h - 1.0 - np.round(blk2 * 3.0) * 0.5, h)
    h = np.where(cut2, h - 0.5 - np.round(blk2) * 0.5, h)
    # beaches: in a few coves the land comes down to the water in shelves instead of a cliff
    beach = np.zeros(X.shape, bool)
    for (bx, by, br) in BEACHES:
        db = np.hypot(X - bx, Y - by)
        m = (db < br) & land & ~wet & (dc < 16.0)
        hb = SEA + 0.25 + np.round(np.clip(dc - 1.0, 0.0, None) * 0.42 / 0.25) * 0.25
        h = np.where(m, np.minimum(h, hb), h)
        beach |= m & (hb <= h + 1e-6)
    h = np.where(~land, SEABED, h)
    rocks = ~land & (dc > -3.2) & (blk > 0.52) & ~dilate(quay, 10) & ~dilate(beach, 6)
    h = np.where(rocks, SEA - 0.5 + np.round(blk2 * 5.0) * 0.5 * (1.0 + dc / 3.2), h)
    sea = ~land
    deck = np.zeros(X.shape, bool)
    for pt in PORTS:                                                        # the piers' planks (SM_Dock: 3 m wide, 9 m long, a head 8 x 3.5 m)
        (dx, dy), _yaw = pt["dock"]
        ly = (X - dx) * -pt["sign"]
        lx = Y - dy
        deck |= ((np.abs(lx) <= 1.5) & (ly <= 0.25) & (ly >= -9.0)) | ((np.abs(lx) <= 4.0) & (ly <= -9.0) & (ly >= -12.5))
    R["cut"] = (cut1 | cut2) & ~wet
    R["beach"] = beach

    # ---- what is what
    for m in MESAS:                                                         # (a top is what is left of it at its level)
        tops[m["name"]] &= (h == m["z"])
    roads, road_d = path_fields(X, Y)
    path = (roads >= 0) | rfloor
    steep = (h - min_near(h, 2)) >= 0.75
    wild = R["rim"] | R["mountain"] | R["flank"] | R["tor"] | R["bank"] | R["rside"] | sea
    for m in MESAS:
        if m["top"] == "wild":
            wild |= tops[m["name"]]
    wild &= ~rfloor & ~wet
    wild |= sea
    for m in MESAS:
        if m["top"] != "wild":
            wild &= ~tops[m["name"]]
    for f in FLATS:                                                         # (a level place of the plan is never wild)
        if f[7] != "apron":
            s = box(f[1] - f[3], f[2] - f[4], f[1] + f[3], f[2] + f[4])
            wild[s] &= ~(np.hypot((X[s] - f[1]) / f[3], (Y[s] - f[2]) / f[4]) < 0.9) | (h[s] != f[5])
    open_ = np.zeros(X.shape, bool)
    for f in FLATS:
        if f[7] in ("build", "zone"):
            s = box(f[1] - f[3], f[2] - f[4], f[1] + f[3], f[2] + f[4])
            open_[s] |= (np.hypot((X[s] - f[1]) / f[3], (Y[s] - f[2]) / f[4]) < 1.0) & (h[s] == f[5])
    for m in MESAS:
        if m["top"] == "build":
            open_ |= tops[m["name"]]
    open_ &= ~wild & ~wet & ~sea

    # ---- where nobody may go (the barriers stand on its edge): the water and its banks, and the rim of every drop
    # where people walk (ground with something more than a metre and a half lower within a metre). Not the roads, the
    # ramps, the bridges or the slabs.
    rimdrop = (h - min_near(h, 4) > 1.5) & ~path & ~wild & ~wet & ~quay
    hazard = wet | dilate(R["bank"], 2) | rimdrop | sea | (land & (dc < 2.6) & ~path & ~quay & ~R["beach"])
    hazard &= ~corridor & ~slab & ~rfloor & ~deck
    R.update(tops=tops, n1=n1, n2=n2)
    return dict(X=X, Y=Y, h=h, land=land & ~wet, dc=dc, sea=sea & ~rocks, rocks=rocks, deck=deck, quay=quay, wet=wet, wz=wz, path=path, roads=roads, road_d=road_d, rfloor=rfloor, rsurf=rsurf, rstair=rstair,
                pads=pads, hazard=hazard, corridor=corridor, slab=slab, abut=abut, d_river=np.minimum(d_low, d_up), R=R, wild=wild, open=open_,
                rim=rimdrop, steep=steep, water_low=water_low, water_up=water_up, water_brook=water_brook, water_pond=water_pond)


def surface(G):
    X, Y, h, R = G["X"], G["Y"], G["h"], G["R"]
    s = np.zeros(X.shape, np.int8)
    hs = hash2(np.floor(X / 0.5), np.floor(Y / 0.5), 13)
    # rock where it is steep, more and more of it higher up, snow on the heights' treads
    drop = h - min_near(h, 2)
    rise = max_near(h, 2) - h
    rocky = G["wild"]
    bare = noise2(X, Y, 6.0, 91) + np.clip((h - 80.0) / 50.0, 0, 1) * 0.9 + np.clip(drop - 1.0, 0, 3) * 0.12
    s[rocky & (bare > 0.72)] = MOSSY
    s[rocky & (bare > 0.9)] = STONE
    s[R["bank"]] = np.where(hs[R["bank"]] > 0.45, STONE, MOSSY)
    snow = R["mountain"] & (h > SNOW_LINE + (noise2(X, Y, 18.0, 93) - 0.5) * 16.0) & ((drop < 2.5) | (h > SNOW_LINE + 14.0))
    s[snow] = SNOW
    # the mountain: grass only on the treads' inner ground (its terraces' edges and its cliffs are rock)
    mrock = R["mountain"] & ((drop >= 1.0) | (h > 112.0 + (noise2(X, Y, 22.0, 97) - 0.5) * 30.0)) & ~snow
    s[mrock & (s == GRASS)] = np.where(hs[mrock & (s == GRASS)] > 0.5, STONE, MOSSY)
    s[mrock & (h > 46.0) & (s == MOSSY) & (hs > 0.3)] = STONE
    # the ruins' court: old paving, moss among the grass
    court = R["tops"]["ruins"] & (np.hypot((X - 24.0) / 40.0, (Y + 12.0) / 22.0) < 1.0 + (noise2(X, Y, 5.0, 95) - 0.5) * 0.5)
    s[court & (hs > 0.5)] = MOSSY
    s[court & (hs > 0.84)] = STONE
    up = R["tops"]["upper"] & (np.hypot((X + 22.0) / 16.0, (Y - 46.0) / 12.0) < 1.0)
    s[up & (hs > 0.45)] = MOSSY
    s[up & (hs > 0.8)] = STONE
    s[(noise2(X, Y, 5.0, 41) > 0.82) & (s == 0) & G["land"] & ~rocky] = DIRT
    s[(noise2(X, Y, 3.0, 61) > 0.84) & (s == 0) & G["land"]] = MOSSY
    rd = G["roads"] >= 0
    s[rd & ~rocky] = G["roads"][rd & ~rocky]
    rs = G["rsurf"] >= 0
    s[rs] = G["rsurf"][rs]
    s[G["slab"]] = STONE
    cut = R["cut"]
    s[cut] = np.where(hs[cut] > 0.5, STONE, MOSSY)
    s[R["beach"]] = np.where(hs[R["beach"]] > 0.25, GRAVEL, DIRT)
    s[G["quay"]] = np.where(hs[G["quay"]] > 0.3, COBBLE, STONE)
    s[rs] = G["rsurf"][rs]
    s[G["rocks"]] = np.where(hs[G["rocks"]] > 0.6, MOSSY, STONE)
    s[G["sea"]] = GRAVEL
    s[G["wet"]] = GRAVEL
    s[G["abut"]] = np.where(hs[G["abut"]] > 0.6, MOSSY, STONE)
    s[(rise >= 2.0) & (s == GRASS) & rocky & (hs > 0.5)] = MOSSY          # the foot of a cliff
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
        self.G, self.h, self.s = G, G["h"], s
        self.items = []
        self.missing = set()
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

    def tree(self, kind, x, y, yaw=0.0, scale=1.0, group="forest", z=None):
        r = {"A": 1.6, "B": 1.5, "C": 1.1, "D": 0.7}[kind] * scale
        self.add("SM_Tree2_%s_Trunk" % kind, x, y, yaw, scale, z=z, dz=-0.15, group=group, r=r)
        self.add("SM_Tree2_%s_Leaves" % kind, x, y, yaw, scale, z=z, dz=-0.15, group=group)
        self.trees.append((x, y, kind, scale))


def rect_gap(x, y, f):
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


# the ship at each pier (SM_Boat: the grain ship since 2026-11-22; it was a rowing boat)
SHIP = "SM_Boat"
# coves with a beach: (x, y, radius)
BEACHES = [(-60.0, -300.0, 26.0), (300.0, -110.0, 24.0), (-300.0, 250.0, 24.0), (180.0, 304.0, 22.0), (150.0, -300.0, 22.0)]


def ruins():
    """The ruins: (mesh, x, y, yaw, z). Pillars round the plateau's court, an arch at its west and its east gate, the
    old arch and its pillars on the upper terrace, fallen blocks."""
    out = []
    cx, cy, rx, ry, n = 24.0, -12.0, 36.0, 19.0, 14
    for k in range(n):
        a = 2 * math.pi * (k + 0.5) / n
        x, y = cx + rx * math.cos(a), cy + ry * math.sin(a)
        r = float(hash2(np.array(k), np.array(3), 77))
        mesh = "SM_Ruin_Pillar_A" if r < 0.45 else ("SM_Ruin_Pillar_B" if r < 0.8 else "SM_Ruin_Pillar_C")
        out.append((mesh, round(x * 2) / 2.0, round(y * 2) / 2.0, 90.0 * (k % 4), RUINS_Z))
    out += [("SM_Ruin_Arch", -32.0, -6.0, 90.0, RUINS_Z), ("SM_Ruin_Arch", 24.0, -12.0, 0.0, RUINS_Z), ("SM_Ruin_Block", 30.0, -6.0, 20.0, RUINS_Z),
            ("SM_Ruin_Block", 14.0, -19.0, 70.0, RUINS_Z), ("SM_Ruin_Block", 44.0, -22.0, 0.0, RUINS_Z), ("SM_Ruin_Pillar_C", 8.0, 6.0, 0.0, RUINS_Z),
            ("SM_Ruin_Arch", -24.0, 48.0, 20.0, UPPER_Z), ("SM_Ruin_Pillar_A", -36.0, 46.0, 0.0, UPPER_Z), ("SM_Ruin_Pillar_B", -14.0, 54.0, 90.0, UPPER_Z),
            ("SM_Ruin_Pillar_C", -32.0, 56.0, 0.0, UPPER_Z), ("SM_Ruin_Block", -18.0, 42.0, 40.0, UPPER_Z),
            # the crossings: a pair of old pillars at each
            ("SM_Ruin_Pillar_B", -60.0, 160.0, 0.0, 0.0), ("SM_Ruin_Pillar_C", -80.0, 136.0, 90.0, 0.0),
            ("SM_Ruin_Pillar_B", 20.0, -150.0, 0.0, 0.0), ("SM_Ruin_Pillar_C", -8.0, -172.0, 90.0, 0.0)]
    return out


_WOOD = None


def wood(x, y):
    """How wooded a place is, 0..1: stands and clearings by a slow noise, a tree here and there between them."""
    global _WOOD
    if _WOOD is None:
        a = -HALF + (np.arange(int(HALF)) + 0.5) * 2.0
        wx, wy = np.meshgrid(a, a, indexing="ij")
        # (forest nearly everywhere outside the pockets: only one place in five is a glade)
        _WOOD = np.clip((noise2(wx, wy, 62.0, 951, octaves=2) - 0.36) / 0.06, THIN, 1.0)
    n = _WOOD.shape[0]
    return float(_WOOD[min(n - 1, max(0, int((x + HALF) / 2.0))), min(n - 1, max(0, int((y + HALF) / 2.0)))])


def things(G, s):
    X, Y, h, R = G["X"], G["Y"], G["h"], G["R"]
    sc = Scene(G, s)
    rng = np.random.default_rng(20261122)
    wild = G["wild"]
    open_ = G["open"]

    # ---- the buildings (with what their sidecars ask to have placed with them), the bridges, the ruins
    for key, (mesh, x, y, z, yaw, team) in BUILD.items():
        sc.building(mesh, x, y, z - 0.01, yaw, team, tags=(["Mounded"] if mesh == "SM_MineCliff" else None))
    for (bx, by, yaw) in BRIDGES.values():
        sc.add("SM_Bridge", bx, by, yaw, z=0.04, group="buildings", team="Neutral")
    sc.add("SM_PlazaBanner", PLAZA0[0], PLAZA0[1], z=0.0, r=1.3, team=0)
    sc.add("SM_PlazaBanner", PLAZA1[0], PLAZA1[1], z=0.0, r=1.3, team=1)
    for pt in PORTS:                                                      # the ports: the pier and its boat, what stands on the quay
        (dx, dy), dyaw = pt["dock"]
        sc.building("SM_Dock", dx, dy, DOCK_Z, dyaw, pt["team"])
        moor = meta("SM_Dock").get("moor", [2.9, -5.9, -1.0, 90.0])
        mx, my = rot(moor[0], moor[1], dyaw)
        # (the ship: SM_Boat is the grain ship now, 13.5 m, its pivot on the waterline; it lies across the pier's head, at
        # the dock's own mooring. cloth: whose colours its sail and banners take, without making it anyone's building)
        ship = sc.add(SHIP, dx + mx, dy + my, moor[3] + dyaw, z=SEA, group="props", tags=["Moored"])
        ship["cloth"] = pt["team"]
        for (mesh, x, y, z, yaw) in pt["things"]:
            sc.add(mesh, x, y, yaw, z=z, group="port", r=3.0, team=pt["team"])
    for (mesh, x, y, yaw, z) in ruins():
        sc.add(mesh, x, y, yaw, z=z, group="ruins", r=2.6 if mesh.endswith("Arch") else 1.2)

    clutter = []
    for t in "01":
        clutter += [("SM_FlowerPlanter", front("castle" + t, 1.0, -3.6), 0), ("SM_FlowerPlanter", front("castle" + t, 1.0, 3.6), 0),
                    ("SM_MineCart", front("mine" + t, 1.0, 3.0), 90), ("SM_Barrel", front("mine" + t, 0.6, -3.0), 0), ("SM_Crate", front("mine" + t, 1.2, -4.0), 30)]
    for k in NEUTRAL_MINES:
        clutter += [("SM_MineCart", front(k, 1.0, 3.2), 0), ("SM_Crate", front(k, 0.8, -3.4), 30), ("SM_Barrel", front(k, 0.6, -4.4), 0)]
    clutter += [("SM_Signpost", (-99.0, -115.0), 200), ("SM_Signpost", (-209.0, 13.0), 100), ("SM_Signpost", (209.0, 133.0), 20), ("SM_Signpost", (149.0, 33.0), 280),
                ("SM_Signpost", (-119.0, 53.0), 60)]
    for (mesh, (x, y), yaw) in clutter:
        sc.add(mesh, x, y, yaw, r=0.9)

    def cell(x, y):
        return int(np.clip((x + HALF) / CELL, 2, N - 3)), int(np.clip((y + HALF) / CELL, 2, N - 3))

    def level(x, y, r=2):
        i, j = cell(x, y)
        i0, i1, j0, j1 = max(i - r, 0), min(i + r, N - 1), max(j - r, 0), min(j + r, N - 1)
        return h[i0, j] == h[i, j] == h[i1, j] == h[i, j0] == h[i, j1]

    rects = [p[:4] for p in G["pads"]]
    bridge_at = [b[:2] for b in BRIDGES.values()]

    def on_pad(x, y, pad=0.6):
        for (x0, y0, x1, y1) in rects:
            if x0 - pad < x < x1 + pad and y0 - pad < y < y1 + pad:
                return True
        if any(math.hypot(x - bx, y - by) < 12.0 for (bx, by) in bridge_at):
            return True
        return math.hypot(x - PLAZA0[0], y - PLAZA0[1]) < 5.5 or math.hypot(x - PLAZA1[0], y - PLAZA1[1]) < 5.5

    path_d = G["road_d"]

    def free(x, y, r, path_gap=0.5, allow_pad=False):
        i, j = cell(x, y)
        if G["wet"][i, j] or s[i, j] in (COBBLE, PLANK, GRAVEL) or G["hazard"][i, j] or G["rfloor"][i, j] or not G["land"][i, j] or G["quay"][i, j]:
            return False
        if path_d[i, j] < path_gap + r or not level(x, y, max(1, int(r / CELL))):
            return False
        if not allow_pad and on_pad(x, y, 0.4 + r):
            return False
        return not sc.solid.hits(x, y, r)

    # ---- lantern posts along the cobbled roads, alternating sides
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
                    if free(x, y, 0.45, 0.25):
                        sc.add("SM_LanternPost", x, y, r=1.0)
                        run, side = 0.0, -side
                d += 0.5
                run += 0.5
    for p in PLAZAS:
        for (dx, dy) in ((-4.6, 2.6), (4.4, -3.0), (3.2, 4.0), (-3.4, -4.4)):
            x, y = p[0] + dx, p[1] + dy
            if free(x, y, 0.4, 0.2, allow_pad=True):
                sc.add("SM_LanternPost_Tall", x, y, yaw=math.degrees(math.atan2(p[1] - y, p[0] - x)) + 90.0, r=1.0)
    for name, (bx, by, yaw) in BRIDGES.items():                           # a lantern at each end of every bridge
        for k, (ex, ey) in enumerate(bridge_ends(name)):
            o = -1.6 if k == 0 else 1.6
            x, y = (ex + o, ey + 2.9) if yaw else (ex + 2.9, ey + o)
            if free(x, y, 0.4, 0.2, allow_pad=True):
                sc.add("SM_LanternPost", x, y, r=1.0)

    # ---- trees: the forest where people can walk. All but none on the open ground; none in or against a building.
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

    for kind, x, y in (("B", -44.0, 12.0), ("B", 86.0, 4.0), ("A", -14.0, 58.0)):      # old trees among the ruins
        if free(x, y, 1.6, 1.0):
            plant(kind, x, y, float(rng.uniform(0.85, 1.0)), "frame")
    tries, lone = 0, 0
    zone_cells = [f for f in FLATS if f[7] == "zone"]
    for kind in "ABCD":
        while count[kind] < TREES[kind] and tries < 2500000:
            tries += 1
            x, y = rng.uniform(-HALF + 5, HALF - 5, 2)
            i, j = cell(x, y)
            if wild[i, j]:
                continue
            w = wood(x, y) * (1.0 if kind in "CD" else 0.8)
            if open_[i, j]:                                # a lone tree here and there on the open ground, no more
                on_top = any(R["tops"][m["name"]][i, j] for m in MESAS if m["top"] == "build")
                in_zone = any(math.hypot((x - f[1]) / f[3], (y - f[2]) / f[4]) < 1.0 for f in zone_cells)
                w = 0.01 if kind == "D" and lone < 60 and not on_top and not in_zone else 0.0
            if rng.random() > w:
                continue
            if kind in "AB" and wood(x, y) < 0.5:          # the giants stand in the woods
                continue
            if crowded(x, y, kind) or not free(x, y, radius[kind] + 0.6, 2.6):
                continue
            scale = float(rng.uniform(0.85, 1.1))
            if tree_blocked(x, y, kind, scale) or any(math.hypot(x - ax, y - ay) < 7.5 for (ax, ay) in APRONS):
                continue
            plant(kind, x, y, scale)
            lone += 1 if open_[i, j] else 0
    against = [(x, y, k, tree_blocked(x, y, k, sc_)) for (x, y, k, sc_) in sc.trees if tree_blocked(x, y, k, sc_)]
    if against:
        gone = {(round(x, 3), round(y, 3)) for (x, y, _k, _w) in against}
        sc.items = [it for it in sc.items if not (it["mesh"].startswith("SM_Tree") and (it["pos"][0], it["pos"][1]) in gone)]
        sc.trees = [t for t in sc.trees if (round(t[0], 3), round(t[1], 3)) not in gone]
        for (_x, _y, k, _w) in against:
            count[k] -= 1
    sc.cleared = len(against)

    # ---- the wild woods (the rim, the mountain's lower terraces, the knolls: where nobody can go): the same trees,
    # instances of the level's AVLForest with their levels of detail (wildwoods.py)
    bare = np.zeros(h.shape, bool)
    for key in BUILD:
        bare[box(*footprint(key, 5.0)[:4])] = True
    bare |= R["mound"] | R["bank"]
    sc.wild_trees = 0
    for (x, y, z, kind, scale) in wildwoods.spots(G, s, CELL, (GRASS, MOSSY), 96.0, bare, share=WILD_SHARE):
        if tree_blocked(x, y, kind, scale):
            continue
        sc.tree(kind, x, y, yaw=float(rng.integers(0, 4)) * 90.0, scale=scale, group="wild", z=z)
        count[kind] += 1
        sc.wild_trees += 1

    # ---- undergrowth
    def scatter(n, meshes, r, group, gap, scale=(0.9, 1.15), where=None, solid=False):
        placed, t = [], 0
        while len(placed) < n and t < n * 80:
            t += 1
            x, y = rng.uniform(-HALF + 3, HALF - 3, 2)
            if where and not where(x, y):
                continue
            if not free(x, y, r, 0.3) or any(math.hypot(x - a, y - b) < gap for a, b in placed[-300:]):
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

    scatter(210, ["SM_Rock_A", "SM_Rock_B", "SM_Rock_B", "SM_Rock_C", "SM_Rock_C", "SM_Rock_D", "SM_Rock_E"], 1.5, "rocks", 5.0, scale=(0.7, 1.0), solid=True, where=rough)
    scatter(1150, ["SM_Bush_A", "SM_Bush_A", "SM_Bush_B", "SM_Bush_B", "SM_Bush_C"], 0.8, "plants", 2.2, scale=(0.8, 1.25), where=rough)
    scatter(4000, ["SM_Flowers_A", "SM_Flowers_B", "SM_Flowers_C", "SM_Flowers_D"], 0.3, "plants", 1.0, where=tame)
    scatter(9500, ["SM_GrassTuft_A", "SM_GrassTuft_B", "SM_GrassTuft_C", "SM_GrassTuft_C"], 0.3, "plants", 0.6, scale=(0.9, 1.5), where=tame)
    # lily pads in the rivers' quiet reaches
    k = 0
    for _ in range(60000):
        if k >= 110:
            break
        x, y = rng.uniform(-HALF + 3, HALF - 3, 2)
        i, j = cell(x, y)
        if G["water_low"][i, j] and G["d_river"][i, j] < -1.4 and all(math.hypot(x - bx, y - by) > 16.0 for (bx, by) in bridge_at):
            sc.add(str(rng.choice(["SM_LilyPad_A", "SM_LilyPad_B"])), x, y, float(rng.uniform(0, 360)), z=WAT + 0.02, group="plants")
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
    co = G["corridor"][0::2, 0::2] | G["corridor"][1::2, 1::2]                # the bridges' decks
    hh = np.where(co, 0.0, hh)
    dk = G["deck"][0::2, 0::2] | G["deck"][1::2, 1::2]                        # the piers' planks
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
    for (di, dj) in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
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

    pts = dict(G_)
    for name in BRIDGES:
        e0, e1 = bridge_ends(name)
        bx, by, yaw = BRIDGES[name]
        pts["b_" + name + "_a"] = (e0[0] - 1.0, e0[1]) if yaw else (e0[0], e0[1] - 1.0)
        pts["b_" + name + "_b"] = (e1[0] + 1.0, e1[1]) if yaw else (e1[0], e1[1] + 1.0)
    pts.update(ruins=ZONES["Ruins"], upper=(-24.0, 44.0), north_crossing=ZONES["NorthCrossing"], south_crossing=ZONES["SouthCrossing"],
               wbluff=(-272.0, -60.0), nbluff=(226.0, 282.0))
    for f in FLATS:
        if f[7] == "build":
            pts["flat_" + f[0]] = (f[1], f[2])
    nodes = {k: node(v) for k, v in pts.items()}
    D = dijkstra(g, directed=False, indices=[nodes["castle0"], nodes["castle1"]])

    def d(src, k):
        if nodes[k] is None:
            return None
        v = float(D[src, nodes[k]])
        return None if not math.isfinite(v) else round(v, 1)

    def side(t):
        s, o = str(t), str(1 - t)
        return dict(own_mine=d(t, "mine" + s), mine_tower=d(t, "tower" + s), hill_tower=d(t, "tower" + s + "b"), own_bluff=d(t, "wbluff" if t == 0 else "nbluff"),
                    mine_nw=d(t, "mine_nw"), mine_centre_east=d(t, "mine_c"), mine_se=d(t, "mine_se"),
                    ruins=d(t, "ruins"), upper_terrace=d(t, "upper"), north_crossing=d(t, "north_crossing"), south_crossing=d(t, "south_crossing"),
                    enemy_castle=d(t, "castle" + o), enemy_mine=d(t, "mine" + o), enemy_hill_tower=d(t, "tower" + o + "b"))

    rep = dict(player=side(0), enemy=side(1),
               bridges={name: [d(0, "b_" + name + "_a"), d(1, "b_" + name + "_b")] for name in BRIDGES},
               flats={f[0]: [d(0, "flat_" + f[0]), d(1, "flat_" + f[0])] for f in FLATS if f[7] == "build"},
               heights=dict(ruins=RUINS_Z, upper_terrace=UPPER_Z, bluff=BLUFF_Z, hill_tower=HILL_Z, rivers=WAT, summit=float(G["h"].max())),
               note="metres walked from the castle's door by the shortest route over the ground (50 cm cells, steps of at most 50 cm, "
                    "no water, no building; trees not counted). bridges: [from the player's castle to its nearer end, from the enemy's]")

    # ---- the ground to build on: level ground a side can walk to and is nearer to than its foe, less roads and
    # buildings (and 2 m round them)
    d0, d1 = D[0].reshape(n, n), D[1].reshape(n, n)
    taken = G["path"][0::2, 0::2] | G["path"][1::2, 1::2] | G["corridor"][0::2, 0::2]
    for k in BUILD:
        taken |= in_rect(X, Y, footprint(k, 2.0)[:4])
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
    for side_, mine_, other in (("player", d0, d1), ("enemy", d1, d0)):
        own = ok & np.isfinite(mine_) & (mine_ < other) & ~taken & flat
        area[side_] = dict(total=int(own.sum() * 0.25), marked=int((own & mdw).sum() * 0.25), open=int((own & ~treed).sum() * 0.25),
                           wooded=int((own & treed).sum() * 0.25))
    reach = ok & np.isfinite(d0) & ~taken & flat
    for m in MESAS:
        if m["top"] == "build":
            area[m["name"]] = int((reach & G["R"]["tops"][m["name"]][0::2, 0::2]).sum() * 0.25)
    for f in FLATS:
        if f[7] in ("build", "zone"):
            area[f[0]] = int((reach & mdw & (np.hypot((X - f[1]) / f[3], (Y - f[2]) / f[4]) < 1.0)).sum() * 0.25)
    rep["buildable_m2"] = dict(area, note="square metres of level ground that can be walked to, less roads and buildings. player / enemy: what is nearer "
                                          "(on foot) to its castle than to the other (marked: in the plan's buildable areas and on the hills' tops; open: no "
                                          "tree within 4 m; wooded: under trees, which a building clears). The named entries: each buildable area of the plan.")
    rep["unreachable"] = sorted(k for k in pts if nodes[k] is None or not math.isfinite(float(D[0, nodes[k]])))
    if verbose:
        print("%-24s %8s %8s" % ("from the castle door to", "player", "enemy"))
        for k in rep["player"]:
            print("%-24s %8s %8s" % (k, rep["player"][k], rep["enemy"][k]))
        for k, v in rep["bridges"].items():
            print("%-24s %8s %8s" % ("bridge " + k, v[0], v[1]))
        for k, v in rep["flats"].items():
            print("%-24s %8s %8s   %6s m2" % ("area " + k, v[0], v[1], area.get(k)))
        print("%-24s %8s %8s" % ("ground to build on, m2", "player", "enemy"))
        for k in ("total", "marked", "open", "wooded"):
            print("%-24s %8s %8s" % (k, area["player"][k], area["enemy"][k]))
        print("tops: " + ", ".join("%s %s" % (m["name"], area[m["name"]]) for m in MESAS if m["top"] == "build"))
        print("zones: " + ", ".join("%s %s" % (f[0], area[f[0]]) for f in FLATS if f[7] == "zone"))
        print("unreachable: %s" % (rep["unreachable"] or "none"))
    return rep


def hard_edges(G):
    """The owner's terrain rule, measured: cells of open ground (not wild, water, hazard, a road or a ramp) with a drop
    of a metre or more to a neighbour that is open ground too."""
    h = G["h"]
    openg = ~(G["wild"] | G["wet"] | G["hazard"] | G["path"] | G["R"]["mound"])
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
                  "Rally:0, Rally:1, and the contested zones NorthCrossing, SouthCrossing, Ruins."
    return out


def buildable_areas():
    """The named level grounds, for whoever places buildings."""
    out = []
    for f in FLATS:
        if f[7] in ("build", "zone"):
            out.append(dict(name=f[0], team=f[6], z=f[5], centre=[f[1], f[2]], radii=[f[3], f[4]], kind=f[7]))
    for m in MESAS:
        if m["top"] == "build":
            out.append(dict(name=m["name"], team=m["team"], z=m["z"], polygon=[list(p) for p in m["poly"]], kind="top"))
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
    for tag, (zx, zy) in ZONES.items():
        markers.append(dict(tag=tag, pos=[zx, zy, round(ground(h, zx, zy), 3)], yaw=0.0))
    bal = balance(G, verbose, sc.trees)
    edges = hard_edges(G)
    layout = dict(
        name="Realm v2", map="/Game/Maps/L_RealmV2",
        camera=dict(pos=list(C.POS), target=list(C.TARGET), hfov=C.HFOV, az=C.AZ, el=C.EL, width=C.W, height=C.H),
        terrain=dict(cell=CELL, half=HALF, zmin=ZMIN, top=TOP, sea=SEA, seabed=SEABED, water=WAT, upper_water=UPN, pond=POND, brook=BROOK, surfaces=SURF, hard_edge_cells=edges),
        spawn=dict(pos=[SPAWN[0], SPAWN[1], ground(h, SPAWN[0], SPAWN[1])], yaw=SPAWN[2]),
        places=dict(plaza=PLAZA0, plaza1=PLAZA1, glade=(-122.0, 74.0), summit=PEAKS[0][:2], peaks=[p[:2] for p in PEAKS], ruins=ZONES["Ruins"], upper_terrace=(-24.0, 46.0),
                    north_crossing=ZONES["NorthCrossing"], south_crossing=ZONES["SouthCrossing"],
                    bridges={k: dict(centre=v[:2], yaw=v[2], ends=bridge_ends(k)) for k, v in BRIDGES.items()},
                    ramps={r[0]: dict(foot=r[1], head=r[2], half_width=r[3]) for r in RAMPS},
                    **{k: (v[1], v[2]) for k, v in BUILD.items()}),
        gates=GATE,
        teams=tm,
        markers=markers,
        balance=bal,
        buildable=buildable_areas(),
        sky=_sky(),
        trees=dict(count=sc.tree_counts, clear=TREE_CLEAR, margin=BUILD_MARGIN, cleared_at_build=sc.cleared, wild=sc.wild_trees,
                   lod_faces_m=wildwoods.budget(sc.tree_counts, meta),
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
        np.savez_compressed(os.path.join(OUT, NAME + "_terrain.npz"), h=h.astype(np.float32), s=s, hazard=G["hazard"], wz=G["wz"])
        counts = {}
        for it in sc.items:
            counts[it["mesh"]] = counts.get(it["mesh"], 0) + 1
        faces = sum(meta(m).get("faces", 0) * n for m, n in counts.items())
        print("realmv2: %d instances, %d kinds, %.2f M faces; trees %s (%d of them wild) = %.2f M faces (all at LOD 0 / 1 / 2: %s M), %d taken away from buildings; "
              "summit %.0f m; hard edges on open ground: %d cells; not built yet: %s" % (
                  len(sc.items), len(counts), faces / 1e6, sc.tree_counts, sc.wild_trees, layout["trees"]["faces"] / 1e6,
                  " / ".join("%.2f" % v for v in layout["trees"]["lod_faces_m"]), sc.cleared, float(h.max()), edges, ", ".join(sorted(sc.missing)) or "none"))
    return layout, G, s


def debug(layout, G, s, path=None):
    """The plan from above (north up), 2 px per metre: surfaces, heights, water, hazard edge, open ground (paler), buildings, trees."""
    from PIL import Image, ImageDraw
    h = G["h"]
    cols = np.array([(96, 150, 50), (190, 160, 110), (140, 100, 60), (120, 120, 120), (150, 150, 150), (110, 140, 100), (200, 140, 70), (240, 244, 250)], np.uint8)
    shade = 0.62 + 0.035 * np.clip(h, -3, 12) + 0.004 * np.clip(h - 12, 0, 100)
    # a little relief: lit from the south-east
    shade = shade + np.clip((np.roll(h, 2, 0) - np.roll(h, -2, 0)) * -0.05 + (np.roll(h, 2, 1) - np.roll(h, -2, 1)) * 0.05, -0.25, 0.25)
    rgb = cols[s].astype(np.float32) * shade[:, :, None]
    rgb[G["open"] & (s == 0)] *= 1.18
    rgb[G["water_low"] & ~G["abut"]] = (70, 140, 210)
    rgb[G["sea"]] = (40, 90, 160)
    rgb[G["water_brook"] | G["water_pond"]] = (130, 200, 250)
    hz = G["hazard"]
    edge = hz & ~(np.roll(hz, 1, 0) & np.roll(hz, -1, 0) & np.roll(hz, 1, 1) & np.roll(hz, -1, 1))
    rgb[edge] = (255, 40, 40)
    if "hard" in G:
        rgb[dilate(G["hard"], 2)] = (255, 0, 255)
    img = np.clip(rgb, 0, 255).astype(np.uint8).transpose(1, 0, 2)[::-1]
    im = Image.fromarray(img[::2, ::2])
    K = CELL * 2
    dr = ImageDraw.Draw(im)

    def px(x, y):
        return ((x + HALF) / K, (HALF - y) / K)

    for it in layout["instances"]:
        x, y, _z = it["pos"]
        if it["mesh"].endswith("_Trunk"):
            r = {"A": 6, "B": 6, "C": 4, "D": 2.4}.get(it["mesh"].split("_")[-2], 2) / K
            c = px(x, y)
            dr.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], outline=(20, 70, 20), width=1)
        elif it["mesh"].startswith("SM_Ruin"):
            c = px(x, y)
            dr.rectangle([c[0] - 2, c[1] - 2, c[0] + 2, c[1] + 2], fill=(250, 250, 250))
    for k, v in BUILD.items():
        f = footprint(k)
        a, b = px(f[0], f[3]), px(f[2], f[1])
        dr.rectangle([a[0], a[1], b[0], b[1]], outline=(255, 230, 80) if v[5] == 0 else ((255, 80, 80) if v[5] == 1 else (255, 255, 255)), width=3)
        g = px(*GATE[k])
        dr.ellipse([g[0] - 4, g[1] - 4, g[0] + 4, g[1] + 4], fill=(255, 0, 255))
        dr.text((a[0] + 4, a[1] + 4), k, fill=(255, 255, 255))
    for name, (bx, by, yaw) in BRIDGES.items():
        e0, e1 = bridge_ends(name)
        a, b = px(min(e0[0], e1[0]) - (0 if yaw else 2), max(e0[1], e1[1]) + (2 if yaw else 0)), px(max(e0[0], e1[0]) + (0 if yaw else 2), min(e0[1], e1[1]) - (2 if yaw else 0))
        dr.rectangle([a[0], a[1], b[0], b[1]], outline=(255, 255, 255), width=2)
    for f in FLATS:
        if f[7] in ("build", "zone"):
            a, b = px(f[1] - f[3], f[2] + f[4]), px(f[1] + f[3], f[2] - f[4])
            dr.ellipse([a[0], a[1], b[0], b[1]], outline=(255, 255, 255) if f[7] == "build" else (200, 120, 255), width=1)
            dr.text((a[0] + 6, (a[1] + b[1]) / 2), f[0], fill=(255, 255, 255))
    path = path or os.path.join(ROOT, "Saved", "realmv2_plan.png")
    im.save(path)
    print(path)


if __name__ == "__main__":
    L, G_all, S = build(verbose="--balance" in sys.argv or "--debug" in sys.argv)
    if "--debug" in sys.argv:
        debug(L, G_all, S)
