"""The village: where everything stands. Pure numpy (run by Blender's Python or Tools/.venv), writes SourceArt/layout.json.

    Blender -b --factory-startup --python Tools/blender/village_layout.py        (or: import village_layout as L; L.build())

Positions were taken from References/village.png through the postcard camera (village_cam.py): a point of the picture
is unprojected onto the ground, so that from the postcard camera each thing lands where it is in the picture.
World: metres, +X east, +Y north, +Z up; (0, 0) is the ground under the middle of the picture.

  layout.json
    camera      the postcard camera (position, look-at, field of view)
    terrain     grid origin / cell size (the height and surface maps go to terrain.npz for terrain.py)
    instances   [{mesh, pos [x, y, z], yaw (degrees, counter-clockwise from above), scale}]
    spawn       where King David starts
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import village_cam as C

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ROOT, "SourceArt")
MESHES = os.path.join(OUT, "Meshes")

CELL = 0.25                       # quarter blocks: paths sit one step below the grass, as in the picture
HALF = 56.0                       # the world is 112 m square
N = int(2 * HALF / CELL)
ZMIN = -3.0
WATER_LOW = -0.75                 # the river and pond surface
WATER_HIGH = 1.0                  # the stream above the waterfall

U = C.unproject


# ---------------------------------------------------------------------------------------------------- helpers

def grid():
    a = -HALF + (np.arange(N) + 0.5) * CELL
    return np.meshgrid(a, a, indexing="ij")


def hash2(ix, iy, seed=0):
    h = (ix.astype(np.int64) * 73856093) ^ (iy.astype(np.int64) * 19349663) ^ (seed * 83492791)
    h = (h ^ (h >> 13)) * 1274126177
    h = h ^ (h >> 16)
    return (h & 0xFFFFFF).astype(np.float64) / float(0xFFFFFF)


def noise2(X, Y, scale, seed=0, octaves=3):
    out = np.zeros_like(X)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        s = scale / (2 ** o)
        gx, gy = X / s, Y / s
        x0, y0 = np.floor(gx).astype(np.int64), np.floor(gy).astype(np.int64)
        fx, fy = gx - x0, gy - y0
        fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
        v = (hash2(x0, y0, seed + o) * (1 - fx) + hash2(x0 + 1, y0, seed + o) * fx) * (1 - fy) + \
            (hash2(x0, y0 + 1, seed + o) * (1 - fx) + hash2(x0 + 1, y0 + 1, seed + o) * fx) * fy
        out += v * amp
        tot += amp
        amp *= 0.5
    return out / tot


def dist_polyline(X, Y, pts):
    d = np.full(X.shape, 1e9)
    for (ax, ay), (bx, by) in zip(pts[:-1], pts[1:]):
        vx, vy = bx - ax, by - ay
        L = vx * vx + vy * vy
        t = np.clip(((X - ax) * vx + (Y - ay) * vy) / max(L, 1e-9), 0, 1)
        d = np.minimum(d, np.hypot(X - (ax + t * vx), Y - (ay + t * vy)))
    return d


def in_poly(X, Y, poly):
    inside = np.zeros(X.shape, bool)
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        cond = ((y1 > Y) != (y2 > Y)) & (X < (x2 - x1) * (Y - y1) / (y2 - y1 + 1e-12) + x1)
        inside ^= cond
    return inside


def smooth(a, lo, hi):
    t = np.clip((a - lo) / (hi - lo), 0, 1)
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------------------------------------------- the plan

# Everything below is given as POINTS OF THE REFERENCE PICTURE (pixels) and unprojected through the postcard camera, so
# that it lands where it is in the picture. P(px, py[, z]) is the ground point seen at that pixel.
def P(px, py, z=0.0):
    x, y = U(px, py, z)
    return (round(x, 2), round(y, 2))


def PL(points, z=0.0):
    return [P(px, py, z) for (px, py) in points]


def _fit(name, default):
    """Position and scale of a building, solved against its box in the picture by Tools/blender/fit.py."""
    try:
        with open(os.path.join(OUT, "fit.json")) as f:
            r = json.load(f)[name]
        return (r["pos"][0], r["pos"][1]), r["scale"]
    except Exception:
        return default


HALL, HALL_S = _fit("SM_TownHall", ((1.42, 2.83), 0.81))
HALL_S = max(HALL_S, 0.85)
BARRACKS, BARRACKS_S = _fit("SM_Barracks", ((14.63, -3.59), 1.0))
RANGE, RANGE_S = _fit("SM_ArcheryRange", ((-12.06, 3.47), 1.03))
FARM_L, _s = _fit("SM_FarmCottage_A", ((-9.71, -3.79), 0.85))
FARM_R, _s = _fit("SM_FarmCottage_B", ((3.40, -9.16), 0.85))
COTTAGE_S = 0.85
PLAZA = P(778, 578)
_portal = P(315, 290, 2.0)                      # the mine portal's floor: 1 m above the terrace the cliff stands on
MINE = (_portal[0] - 2.5, _portal[1] + 1.56)    # (the portal is at x = +2.5, y = -1.56 in the asset)
# The bridge: its middle and heading from the four lantern piers of the picture (it runs nearly north-south, the river
# passing under it from the pond on the right), 7 m long.
BRIDGE = P(1081, 812)
BRIDGE_DIR = -72.0                              # heading of its far-bank end, degrees from +X
BRIDGE_YAW = BRIDGE_DIR + 90.0                  # the asset runs along its Y
_bd = (math.cos(math.radians(BRIDGE_DIR)), math.sin(math.radians(BRIDGE_DIR)))
BRIDGE_W = (round(BRIDGE[0] - 3.5 * _bd[0], 2), round(BRIDGE[1] - 3.5 * _bd[1], 2))      # the village end
BRIDGE_E = (round(BRIDGE[0] + 3.5 * _bd[0], 2), round(BRIDGE[1] + 3.5 * _bd[1], 2))      # the far end
STEPS_LOW, STEPS_HIGH = P(600, 455), P(520, 415, 1.0)          # the stone steps from the plaza up to the terrace
STEPS_YAW = math.degrees(math.atan2(STEPS_HIGH[1] - STEPS_LOW[1], STEPS_HIGH[0] - STEPS_LOW[0])) - 90.0
GLADE = (27.0, 30.0)              # the forest clearing of References/forest.png, north-east behind the barracks
CASTLE = (30.0, -30.0)            # across the river, down the road from the bridge
# The castle and the town hall have changed places: the castle now stands at the head of the plaza (HALL, the site the
# picture's town hall stood on) and the town hall across the river at the end of the road (CASTLE). SWAP = False puts
# them back.
SWAP = True
CASTLE_S = 0.8                    # the castle on the town hall's site: scaled to its pad (11.2 x 8.8 m)
SPAWN = P(815, 540) + (-60.0,)    # x, y, facing (degrees, 0 = +X east, counter-clockwise): on the plaza, facing the viewer
TREES = 210                       # the forest is dense: trunks about 5 m apart, crowns touching
TREE_GAP = 5.0

HALL_STEPS = (HALL[0], HALL[1] - 5.5 * CASTLE_S) if SWAP else (HALL[0] + 1.0 * HALL_S, HALL[1] - 5.0 * HALL_S)
# the far site: where the road from the bridge ends, and the building there faces back up the road
ROAD_END = (CASTLE[0] - 5.0, CASTLE[1] + 6.0)
_rd = (ROAD_END[0] - CASTLE[0], ROAD_END[1] - CASTLE[1])
_rl = math.hypot(*_rd)
FAR_YAW = math.degrees(math.atan2(_rd[0] / _rl, -_rd[1] / _rl)) if SWAP else 45.0     # front (-Y) turned to face the road
# the town hall there, its steps at the end of the road
FAR_HALL = (round(ROAD_END[0] - _rd[0] / _rl * 5.6 * HALL_S, 2), round(ROAD_END[1] - _rd[1] / _rl * 5.6 * HALL_S, 2))
BARRACKS_STEPS = (BARRACKS[0], BARRACKS[1] - 4.0 * BARRACKS_S)
MINE_RAMP = (MINE[0] + 3.0, MINE[1] - 5.6)

# The pond (its shore as drawn), the river leaving the bottom of the picture, the stream and fall on the right.
POND = PL([(850, 930), (850, 860), (900, 800), (1000, 790), (1250, 790), (1340, 772), (1440, 768), (1520, 760), (1600, 742), (1690, 760),
           (1690, 835), (1420, 850), (1250, 838), (1160, 842), (1115, 876), (1075, 930)])
RIVER_LOW = PL([(985, 900), (960, 1050), (880, 1350), (700, 1800), (300, 2400)])
RIVER_HIGH = PL([(1486, 756), (1570, 700), (1700, 620), (2000, 470), (2500, 300)])
FALL = P(1486, 758)
HIGHLAND = PL([(1440, 770), (1520, 760), (1600, 740), (1700, 762), (2600, 1000), (2600, 200), (1700, 470), (1500, 600), (1425, 690)])

PATHS = [                          # (points, half width)
    ([HALL_STEPS, P(862, 520), PLAZA], 1.5),                                           # hall steps -> plaza
    ([PLAZA, P(690, 520), STEPS_LOW], 1.2),                                            # plaza -> the steps up to the terrace
    ([STEPS_HIGH, P(470, 385, 1.0), MINE_RAMP], 1.0),                                  # terrace: steps -> mine ramp
    ([P(505, 428, 1.0), P(440, 475, 1.0), P(330, 525, 1.0), P(200, 540, 1.0)], 0.9),   # terrace: along the front of the range
    ([PLAZA, P(905, 560), P(1045, 505), BARRACKS_STEPS], 1.35),                        # plaza -> barracks door
    ([PLAZA, P(800, 645), P(900, 716), BRIDGE_W], 1.35),                               # plaza -> bridge
    ([BRIDGE_E, P(1250, 930), P(1480, 1040), ROAD_END], 1.25),                          # the road on across the river
    ([P(1420, 430), P(1560, 300), P(1760, 150), (GLADE[0] - 2.0, GLADE[1] - 3.0)], 1.0),  # barracks -> forest glade
    ([PLAZA, P(705, 612)], 0.9),                                                       # plaza -> left farm gate
]
DIRT_PATHS = [
    ([P(905, 600), P(935, 632)], 0.8),                                                 # right farm gate
]
# where a path must meet something at ground level (steps, bridge ends): it is not sunk there
APRONS = [HALL_STEPS, BARRACKS_STEPS, BRIDGE_W, BRIDGE_E, STEPS_LOW, STEPS_HIGH, MINE_RAMP]

# the terrace the range and the mine stand on: its edge as drawn (the low wall under the range, the steps, up past the mine)
TERRACE_WEST = PL([(-900, 520), (0, 575), (100, 585), (230, 600), (330, 612), (420, 585), (470, 550), (520, 520), (548, 470), (532, 430),
                   (560, 400), (585, 330), (640, 240), (700, 120), (760, -200), (-900, -200)], 1.0)
PADDOCK_L = PL([(240, 680), (410, 800), (755, 715), (640, 618)])
PADDOCK_R = PL([(885, 600), (1050, 730), (1385, 660), (1300, 572), (1205, 558)])

# footprints kept clear of trees and scatter: (x, y, radius)
CLEAR = [HALL + (8.0,), BARRACKS + (8.0,), RANGE + (7.0,), MINE + (10.5,), FARM_L + (7.0,), FARM_R + (7.0,), BRIDGE + (6.0,),
         PLAZA + (6.0,), GLADE + (6.5,), CASTLE + (11.0,)] + ([FAR_HALL + (15.5,), ROAD_END + (8.5,)] if SWAP else [])
# building footprints (x0, y0, x1, y1, ground height): the ground is levelled under them
_MAIN_HW, _MAIN_HD = (7.1 * CASTLE_S, 5.6 * CASTLE_S) if SWAP else (5.6 * HALL_S, 5.1 * HALL_S)
PADS = [(HALL[0] - _MAIN_HW, HALL[1] - _MAIN_HD, HALL[0] + _MAIN_HW, HALL[1] + _MAIN_HD, 0.0),
        (BARRACKS[0] - 5.6, BARRACKS[1] - 4.2, BARRACKS[0] + 5.6, BARRACKS[1] + 4.2, 0.0),
        (FARM_L[0] - 2.7, FARM_L[1] - 2.3, FARM_L[0] + 2.7, FARM_L[1] + 2.3, 0.0),
        (FARM_R[0] - 2.7, FARM_R[1] - 2.3, FARM_R[0] + 2.7, FARM_R[1] + 2.3, 0.0),
        (RANGE[0] - 4.8, RANGE[1] - 2.8, RANGE[0] + 4.8, RANGE[1] + 2.8, 1.0),
        (MINE[0] - 8.2, MINE[1] - 5.7, MINE[0] + 8.2, MINE[1] + 5.7, 1.0)]


def heights():
    X, Y = grid()
    n1 = noise2(X, Y, 18.0, 3)
    n2 = noise2(X, Y, 7.0, 9)
    centre = np.hypot(X - 1.6, Y - 3.0)
    out = smooth(centre, 23.0, 38.0)
    h = np.round(((n1 - 0.42) * 5.0 + (n2 - 0.5) * 1.2) * out * 2.0) / 2.0          # the forest floor rolls in half-block steps
    h = np.maximum(h, -0.5)
    # the lawns of the village are not one flat sheet: low grass platforms a quarter block high, as in the picture
    lawn = (noise2(X, Y, 4.5, 77) > 0.56) & (out < 0.5)
    h = np.where(lawn, h + 0.25, h)
    # the west terrace (archery range, mine) and the high ground behind it
    west = in_poly(X, Y, TERRACE_WEST)
    h = np.where(west, np.maximum(h, 1.0), h)
    h = np.maximum(h, np.round(smooth(centre, 27.0, 42.0) * 3.0 * 2.0) / 2.0 * west)        # the ground climbs behind the mine
    # the east highland the stream comes off
    east = in_poly(X, Y, HIGHLAND)
    h = np.where(east, np.maximum(h, 1.5), h)
    # flats for the far set pieces and under the buildings
    for (cx, cy, r, z) in ((GLADE[0], GLADE[1], 8.0, 0.5), (CASTLE[0], CASTLE[1], 11.5, 0.0)):
        h = np.where(np.hypot(X - cx, Y - cy) < r, z, h)
    for (x0, y0, x1, y1, z) in PADS:
        h = np.where((X > x0) & (X < x1) & (Y > y0) & (Y < y1), z, h)
    # paths lie a quarter block below the grass beside them (not where they meet steps or the bridge)
    rag = (noise2(X, Y, 2.2, 5) - 0.5) * 0.9
    path = np.zeros(X.shape, bool)
    for pts, w in PATHS + DIRT_PATHS:
        path |= (dist_polyline(X, Y, pts) + rag) < w
    path |= (np.hypot(X - PLAZA[0], Y - PLAZA[1]) + rag) < 3.3
    apron = np.zeros(X.shape, bool)
    for (ax, ay) in APRONS:
        apron |= np.hypot(X - ax, Y - ay) < 1.3
    flat0 = np.where(west, 1.0, np.where(east, 1.5, 0.0))
    near_village = out < 0.25
    h = np.where(path & near_village, flat0 - np.where(apron, 0.0, 0.25), h)
    h = np.where(path & ~near_village, h - 0.25, h)
    # the pond and river
    inside = in_poly(X, Y, POND)
    d_edge = np.full(X.shape, 1e9)
    d_edge = np.minimum(d_edge, dist_polyline(X, Y, POND + [POND[0]]))
    d_pond = np.where(inside, -d_edge, d_edge)                       # negative inside the pond
    d_low = np.minimum(d_pond, dist_polyline(X, Y, RIVER_LOW) - 2.9)
    wrag = (noise2(X, Y, 3.0, 21) - 0.5) * 0.7
    bank = d_low + wrag
    h = np.where((bank < 1.3) & ~path & ~east, np.minimum(h, 0.0), h)
    h = np.where((bank < 0.5) & ~path & ~east, np.minimum(h, -0.25), h)
    water_low = (bank < 0.0) & ~east                               # the highland stands over the pond as a cliff: the fall
    h = np.where(water_low, -1.25, h)
    h = np.where(bank < -0.7, -1.75, h)
    h = np.where(bank < -1.6, -2.0, h)
    # the stream above the fall
    sb = dist_polyline(X, Y, RIVER_HIGH) + wrag * 0.6
    water_high = (sb < 1.4) & east & ~water_low
    h = np.where(water_high, 0.5, h)
    h = np.where((sb < 2.4) & ~water_high & east, np.minimum(h, 1.5), h)
    lip = (np.hypot(X - FALL[0], Y - FALL[1]) < 2.6) & ~water_low
    return X, Y, h, water_low, water_high, east, lip, path


SURF = ["grass", "cobble", "dirt", "gravel", "stone", "mossy_stone"]


def surface(X, Y, h, water_low, water_high, east, lip, path):
    s = np.zeros(X.shape, np.int8)                                                    # grass
    rag = (noise2(X, Y, 2.2, 5) - 0.5) * 0.9
    s[path] = 1
    for pts, w in DIRT_PATHS:
        s[(dist_polyline(X, Y, pts) + rag) < w] = 2
    # farmyard earth inside the paddocks, here and there
    yard = (in_poly(X, Y, PADDOCK_L) | in_poly(X, Y, PADDOCK_R)) & (noise2(X, Y, 3.5, 31) > 0.6)
    s[yard & (s == 0)] = 2
    s[(noise2(X, Y, 5.0, 41) > 0.8) & (s == 0) & (np.hypot(X, Y) > 26)] = 2          # bare patches in the forest
    s[water_low | water_high] = 3
    # stone: the fall, the stream's banks, a few outcrops
    s[lip & ~water_high] = 4
    s[east & (dist_polyline(X, Y, RIVER_HIGH) < 2.6) & (s == 0) & (noise2(X, Y, 2.0, 51) > 0.45)] = 5
    s[(noise2(X, Y, 3.0, 61) > 0.84) & (s == 0) & (np.hypot(X - 1.6, Y - 3.0) > 20)] = 5
    return s


def ground(h, x, y):
    i = int(np.clip((x + HALF) / CELL, 0, N - 1))
    j = int(np.clip((y + HALF) / CELL, 0, N - 1))
    return float(h[i, j])


# ---------------------------------------------------------------------------------------------------- things

def have(mesh):
    return os.path.exists(os.path.join(MESHES, mesh + ".gltf"))


class Scene:
    def __init__(self, h):
        self.h = h
        self.items = []
        self.missing = set()

    def add(self, mesh, x, y, yaw=0.0, scale=1.0, z=None, dz=0.0, group="village"):
        if not have(mesh):
            self.missing.add(mesh)
        zz = ground(self.h, x, y) if z is None else z
        self.items.append(dict(mesh=mesh, pos=[round(x, 3), round(y, 3), round(zz + dz, 3)], yaw=round(yaw, 2), scale=round(scale, 3), group=group))

    def tree(self, kind, x, y, yaw=0.0, scale=1.0, group="forest"):
        self.add("SM_Tree_%s_Trunk" % kind, x, y, yaw, scale, dz=-0.15, group=group)
        self.add("SM_Tree_%s_Leaves" % kind, x, y, yaw, scale, dz=-0.15, group=group)

    def fence(self, pts, closed=True, lanterns=(), gate=None):
        """Chain 2 m fence pieces along a polyline; lantern posts at the listed corner indices; gate = (segment index, piece index)."""
        n = len(pts)
        for i in range(n if closed else n - 1):
            (ax, ay), (bx, by) = pts[i], pts[(i + 1) % n]
            L = math.hypot(bx - ax, by - ay)
            k = max(1, int(round(L / 2.0)))
            yaw = math.degrees(math.atan2(by - ay, bx - ax))
            sc = L / (k * 2.0)
            for j in range(k):
                t = j / float(k)
                x, y = ax + (bx - ax) * t, ay + (by - ay) * t
                mx, my = x + (bx - ax) * 0.5 / k, y + (by - ay) * 0.5 / k
                if any(x0 - 0.3 < mx < x1 + 0.3 and y0 - 0.3 < my < y1 + 0.3 for (x0, y0, x1, y1, _z) in PADS):
                    continue                                   # a building stands here
                piece = "SM_Fence_Gate" if gate == (i, j) else "SM_Fence_Straight"
                self.add(piece, x, y, yaw, 1.0, group="farm")
                self.items[-1]["scale3"] = [round(sc, 3), 1.0, 1.0]
            if i in lanterns:
                self.add("SM_Fence_Post_Lantern", ax, ay, yaw, group="farm")
        if not closed:
            self.add("SM_Fence_Post", pts[-1][0], pts[-1][1], 0.0, group="farm")


def things(X, Y, h, s, water_low, water_high):
    sc = Scene(h)
    rng = np.random.default_rng(20261120)

    # the buildings
    if SWAP:
        sc.add("SM_Castle", HALL[0], HALL[1], scale=CASTLE_S, z=0.0)
        sc.add("SM_TownHall", FAR_HALL[0], FAR_HALL[1], yaw=FAR_YAW, scale=HALL_S, z=0.0)
    else:
        sc.add("SM_TownHall", HALL[0], HALL[1], scale=HALL_S, z=0.0)
    sc.add("SM_Barracks", BARRACKS[0], BARRACKS[1], scale=BARRACKS_S, z=0.0)
    sc.add("SM_ArcheryRange", RANGE[0], RANGE[1], scale=RANGE_S, z=1.0)
    sc.add("SM_MineCliff", MINE[0], MINE[1], z=1.0)
    sc.add("SM_FarmCottage_A", FARM_L[0], FARM_L[1], scale=COTTAGE_S, z=0.0)
    sc.add("SM_FarmCottage_B", FARM_R[0], FARM_R[1], scale=COTTAGE_S, z=0.0)
    sc.add("SM_Bridge", BRIDGE[0], BRIDGE[1], yaw=BRIDGE_YAW, z=0.04)        # a little proud of the path: no flicker where its ends lie on it
    sc.add("SM_PlazaBanner", PLAZA[0], PLAZA[1], z=-0.25)
    if not SWAP:
        sc.add("SM_Castle", CASTLE[0], CASTLE[1], yaw=45.0, z=0.0)
    # the steps from the plaza up to the terrace (they rise towards +Y in the asset)
    sc.add("SM_StoneSteps", STEPS_LOW[0], STEPS_LOW[1], yaw=STEPS_YAW, z=0.0)

    # farms: paddocks (the fence stops where a cottage stands in it), wheat, animals
    sc.fence(PADDOCK_L, lanterns=(0, 1, 2), gate=(2, 1))
    sc.fence(PADDOCK_R, lanterns=(0, 1, 2), gate=(0, 1))
    for (px0, py0, px1, py1, rows) in ((392, 696, 590, 742, 4), (1082, 612, 1300, 664, 4)):      # wheat fields, from the picture
        for r in range(rows):
            for c in range(int((px1 - px0) / 34) + 1):
                x, y = U(px0 + c * 34 + (r % 2) * 8, py0 + (py1 - py0) * r / max(1, rows - 1))
                sc.add("SM_Wheat", x, y, yaw=float(rng.integers(0, 4)) * 90.0, group="farm")
    for (px, py, yaw) in ((338, 690, 200), (372, 676, 250), (992, 634, 215)):
        x, y = U(px, py)
        sc.add("SM_Sheep", x, y, yaw=yaw, group="farm")
    for (px, py, mesh) in ((662, 694, "SM_HayStack"), (928, 606, "SM_HayStack"), (1010, 590, "SM_HayBale"), (615, 716, "SM_HayBale"),
                           (300, 668, "SM_Trough"), (1180, 596, "SM_Barrel"), (880, 352, "SM_Barrel")):
        x, y = U(px, py)
        sc.add(mesh, x, y, yaw=float(rng.uniform(0, 360)), group="farm")

    # the barracks yard
    for i, (px, py) in enumerate(((1362, 468), (1408, 478), (1454, 488), (1500, 470))):
        x, y = U(px, py)
        sc.add("SM_TrainingDummy", x, y, yaw=float(rng.uniform(-25, 25)))
    for (px, py, mesh) in ((1150, 418, "SM_BannerPost_Tree"), (1238, 452, "SM_BannerPost_Tree"), (1560, 418, "SM_BannerPost_Swords"),
                           (1100, 470, "SM_WeaponRack")):
        x, y = U(px, py)
        sc.add(mesh, x, y)
    # the range's yard (on the terrace)
    for (px, py, mesh, yaw) in ((222, 548, "SM_ArrowBarrel", 0), (120, 470, "SM_Barrel", 30), (472, 522, "SM_Crate", 15)):
        x, y = U(px, py, 1.0)
        sc.add(mesh, x, y, yaw=yaw)

    def on_path(x, y, margin=0.7):
        """On a path or the plaza (or within `margin` of one), or in the water: no lantern post stands there."""
        r = int(round(margin / CELL))
        i, j = int((x + HALF) / CELL), int((y + HALF) / CELL)
        return bool(np.isin(s[max(0, i - r):i + r + 1, max(0, j - r):j + r + 1], (1, 3)).any())

    # lantern posts, from the picture
    for (px, py, z) in ((600, 492, 0.0), (500, 278, 1.0), (310, 420, 1.0), (1362, 602, 0.0), (1046, 716, 0.0), (700, 560, 0.0),
                        (860, 520, 0.0), (1010, 455, 0.0), (1232, 520, 0.0), (1330, 880, 0.0), (120, 560, 1.0)):
        x, y = U(px, py, z)
        if abs(ground(h, x, y) - z) < 0.3 and not on_path(x, y):
            sc.add("SM_LanternPost", x, y)
    far = [P(1380, 950), P(1560, 1040), (CASTLE[0] - 6.5, CASTLE[1] + 5.0), P(1500, 330), P(1700, 190), (GLADE[0] - 3.5, GLADE[1] - 4.0)]
    for (x, y) in far:                                                                                                 # along the far paths
        if not on_path(x, y):
            sc.add("SM_LanternPost", x, y)
    sc.add("SM_Signpost", *P(1262, 880), yaw=200.0)
    sc.add("SM_Rock_B", *P(1400, 742), yaw=90.0, group="rocks")
    sc.add("SM_Rock_C", *P(1560, 724), yaw=0.0, group="rocks")
    sc.add("SM_Rock_C", *P(1345, 760), yaw=180.0, group="rocks")
    sc.add("SM_Rock_A", *P(620, 860), yaw=0.0, group="rocks")
    sc.add("SM_Rock_C", *P(700, 880), yaw=90.0, group="rocks")
    sc.add("SM_CrateStack", *P(1075, 470), yaw=20.0)
    sc.add("SM_Sacks", *P(1545, 470), yaw=-30.0)
    sc.add("SM_FlowerPlanter", *P(735, 470), yaw=0.0)

    # the trees that frame the picture: given by where their CROWN should sit in the picture (its middle is about 7.5 m
    # above the foot, which is 230 px higher up the picture), so only the edges of the frame are leafy, as in the reference
    CROWN_UP = 230.0
    framed = [(-40, 40, 1.0, "A"), (-150, 300, 1.0, "B"), (-60, 1010, 0.0, "A"), (-260, 760, 0.0, "B"),
              (560, -10, 1.0, "B"), (300, -60, 1.0, "C"), (840, -70, 0.0, "C"), (1090, 10, 0.0, "A"), (1330, -40, 0.0, "C"), (1570, 70, 0.0, "B"),
              (1760, 300, 1.5, "A"), (1750, 540, 1.5, "C"), (1660, 980, 0.0, "B")]
    spots = []
    for (px, py, z, kind) in framed:
        up = CROWN_UP * {"A": 1.0, "B": 1.0, "C": 0.72, "D": 0.45}[kind]
        x, y = U(px, py + up, z)
        spots.append((x, y))
        sc.tree(kind, x, y, yaw=float(rng.integers(0, 4)) * 90.0, scale=float(rng.uniform(0.95, 1.08)), group="frame")

    def blocked(x, y, margin=0.0):
        i, j = int((x + HALF) / CELL), int((y + HALF) / CELL)
        if not (2 <= i < N - 2 and 2 <= j < N - 2):
            return True
        if s[i, j] in (1, 3) or water_low[i, j] or water_high[i, j]:
            return True
        for (cx, cy, r) in CLEAR:
            if math.hypot(x - cx, y - cy) < r + margin:
                return True
        for pts, w in PATHS:
            for (ax, ay), (bx, by) in zip(pts[:-1], pts[1:]):
                vx, vy = bx - ax, by - ay
                t = max(0.0, min(1.0, ((x - ax) * vx + (y - ay) * vy) / max(1e-9, vx * vx + vy * vy)))
                if math.hypot(x - ax - t * vx, y - ay - t * vy) < w + 1.6 + margin:
                    return True
        return False

    # inside the picture only the edges are wooded: keep the middle of the village open
    def in_view(x, y):
        px, py = C.project(x, y, 0.0)
        cy = py - CROWN_UP                                   # where the crown would show
        return -230 < px < 1830 and -170 < cy < 1120

    tries = 0
    while len(spots) < TREES and tries < 40000:
        tries += 1
        x, y = rng.uniform(-HALF + 3, HALF - 3, 2)
        if blocked(x, y, 1.5) or in_view(x, y):
            continue
        if any(math.hypot(x - a, y - b) < TREE_GAP for a, b in spots):
            continue
        spots.append((x, y))
        far = math.hypot(x - 1.6, y - 3.0) > 38
        kind = rng.choice(["A", "B", "C", "D"], p=[0.26, 0.26, 0.38, 0.10] if not far else [0.08, 0.08, 0.60, 0.24])
        sc.tree(str(kind), x, y, yaw=float(rng.integers(0, 4)) * 90.0, scale=float(rng.uniform(0.85, 1.15)))

    # undergrowth: bushes, rocks, flowers, grass
    def scatter(count, meshes, margin, group, min_gap, near_view=None, scale=(0.9, 1.15), only_grass=True, avoid=None):
        placed = []
        t = 0
        while len(placed) < count and t < count * 60:
            t += 1
            x, y = rng.uniform(-HALF + 2, HALF - 2, 2)
            if near_view is not None and (math.hypot(x - 1.6, y - 3.0) < near_view[0] or math.hypot(x - 1.6, y - 3.0) > near_view[1]):
                continue
            i, j = int((x + HALF) / CELL), int((y + HALF) / CELL)
            if only_grass and s[i, j] != 0:
                continue
            if water_low[i, j] or water_high[i, j] or s[i, j] in (1, 3):
                continue
            if avoid and avoid(x, y):
                continue
            # no scatter on a step edge: the four neighbours must be level
            if not (h[i - 2, j] == h[i, j] == h[i + 2, j] == h[i, j - 2] == h[i, j + 2]):
                continue
            if any(math.hypot(x - a, y - b) < min_gap for a, b in placed):
                continue
            placed.append((x, y))
            sc.add(str(rng.choice(meshes)), x, y, yaw=float(rng.uniform(0, 360)) if group != "rocks" else float(rng.integers(0, 4)) * 90.0,
                   scale=float(rng.uniform(*scale)), group=group)
        return placed

    def on_building(x, y):
        for (cx, cy, r) in ((HALL[0], HALL[1], 7.4 if SWAP else 6.6), (BARRACKS[0], BARRACKS[1], 6.4), (RANGE[0], RANGE[1], 5.4), (MINE[0], MINE[1], 9.0),
                            (FARM_L[0], FARM_L[1], 3.6), (FARM_R[0], FARM_R[1], 3.6), (CASTLE[0], CASTLE[1], 8.5), (BRIDGE[0], BRIDGE[1], 4.0)):
            if math.hypot(x - cx, y - cy) < r:
                return True
        if any(math.hypot(x - a, y - b) < 1.6 for a, b in spots):
            return True
        return False

    def in_paddock(x, y):
        pt = (np.array([[x]]), np.array([[y]]))
        return bool(in_poly(pt[0], pt[1], PADDOCK_L)[0, 0] or in_poly(pt[0], pt[1], PADDOCK_R)[0, 0])

    scatter(90, ["SM_Rock_A", "SM_Rock_B", "SM_Rock_B", "SM_Rock_C", "SM_Rock_C", "SM_Rock_D", "SM_Rock_E"], 0.0, "rocks", 4.2,
            avoid=lambda x, y: on_building(x, y) or in_paddock(x, y) or blocked(x, y, -0.6))
    # the understorey of the forest picture: big leafy bushes crowding the trunks, flowers and tall grass everywhere
    scatter(260, ["SM_Bush_A", "SM_Bush_A", "SM_Bush_B", "SM_Bush_B", "SM_Bush_C"], 0.0, "plants", 1.7, scale=(0.8, 1.25),
            avoid=lambda x, y: on_building(x, y) or in_paddock(x, y) or (math.hypot(x - 1.6, y - 3.0) < 21 and rng.random() < 0.75))
    scatter(900, ["SM_Flowers_A", "SM_Flowers_B", "SM_Flowers_C", "SM_Flowers_D"], 0.0, "plants", 1.0, avoid=lambda x, y: on_building(x, y) or in_paddock(x, y))
    scatter(1500, ["SM_GrassTuft_A", "SM_GrassTuft_B", "SM_GrassTuft_C", "SM_GrassTuft_C"], 0.0, "plants", 0.6, scale=(0.9, 1.5), avoid=on_building)
    # lily pads on the pond and the slow water
    k = 0
    for _ in range(400):
        x, y = rng.uniform(-12, 22), rng.uniform(-34, -6)
        i, j = int((x + HALF) / CELL), int((y + HALF) / CELL)
        if water_low[i, j] and h[i, j] <= -1.25 and math.hypot(x - BRIDGE[0], y - BRIDGE[1]) > 3.4 and math.hypot(x - FALL[0], y - FALL[1]) > 3.0:
            sc.add(str(rng.choice(["SM_LilyPad_A", "SM_LilyPad_B"])), x, y, yaw=float(rng.uniform(0, 360)), z=WATER_LOW + 0.02, group="plants")
            k += 1
            if k >= 16:
                break
    return sc


def build(write=True):
    X, Y, h, water_low, water_high, east, lip, path = heights()
    s = surface(X, Y, h, water_low, water_high, east, lip, path)
    sc = things(X, Y, h, s, water_low, water_high)
    layout = dict(
        camera=dict(pos=list(C.POS), target=list(C.TARGET), hfov=C.HFOV, az=C.AZ, el=C.EL, width=C.W, height=C.H),
        terrain=dict(cell=CELL, half=HALF, zmin=ZMIN, water_low=WATER_LOW, water_high=WATER_HIGH, surfaces=SURF, fall=list(FALL)),
        spawn=dict(pos=[SPAWN[0], SPAWN[1], ground(h, SPAWN[0], SPAWN[1])], yaw=SPAWN[2]),
        places=dict(plaza=PLAZA, hall=HALL, barracks=BARRACKS, range=RANGE, mine=MINE, farm_l=FARM_L, farm_r=FARM_R, bridge=BRIDGE,
                    glade=GLADE, castle=CASTLE),
        instances=sc.items,
    )
    if write:
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, "layout.json"), "w") as f:
            json.dump(layout, f)
        np.savez_compressed(os.path.join(OUT, "terrain.npz"), h=h, s=s, water_low=water_low, water_high=water_high)
        counts = {}
        for it in sc.items:
            counts[it["mesh"]] = counts.get(it["mesh"], 0) + 1
        print("layout: %d instances, %d kinds; not built yet: %s" % (len(sc.items), len(counts), ", ".join(sorted(sc.missing)) or "none"))
    return layout, (X, Y, h, s, water_low, water_high)


if __name__ == "__main__":
    build()
