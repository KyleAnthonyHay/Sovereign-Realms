"""The town: an island on cliffs above the sea, after References/Remake/town.png. Pure numpy; writes SourceArt/town.json
and SourceArt/town_terrain.npz (the height and surface maps, for assets/town_terrain.py).

    Blender -b --factory-startup --python Tools/blender/town_layout.py [-- --debug]     (or: import town_layout as T; T.build())
    ../Tools/.venv/bin/python Tools/blender/town_layout.py --debug                     (also writes Saved/town_plan.png: the plan
                                                                                         seen through the postcard camera, over the picture)

The plan is in WORLD metres (+X east, +Y north, +Z up), read off the picture through the postcard camera (town_cam.py:
from the south-west, so +X runs right and a little up the picture, +Y up and to the left). Everything is axis-aligned
and at scale 1, so the voxels of buildings and ground line up.

Heights: the sea lies at SEA, the town plateau at 0, the west terrace (archery range, mine) and the east terrace (farms,
windmill) at +1, the watch tower's knoll at +2.5, the forest behind rising in 1 m steps. A river runs off the east terrace:
the pond and the upper river (surface UPPER), the first fall into the gorge pool (POOL) under the bridge, the second fall
into the sea. Paths carry a height at every point: where two points differ, the path is a flight of quarter-block
steps (walkable by everyone: a step is at most 50 cm).

  town.json   camera, terrain (grid, water levels), spawn, places, instances [{mesh, pos, yaw, scale, group, tags?, scale3?}]
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import town_cam as C

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ROOT, "SourceArt")
MESHES = os.path.join(OUT, "Meshes")

CELL = 0.25
HALF = 72.0                       # the world is 144 m square
N = int(2 * HALF / CELL)
ZMIN = -7.0
SEA = -5.0                        # the sea's surface; its bed is SEABED
SEABED = -6.5
POOL = -2.25                      # the gorge pool and the river under the bridge
UPPER = 0.5                       # the pond and the upper river, on the east terrace
LILY = 1.0                        # the lily pond by the plots

SURF = ["grass", "cobble", "dirt", "gravel", "stone", "mossy_stone", "plank"]
GRASS, COBBLE, DIRT, GRAVEL, STONE, MOSSY, PLANK = range(7)


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


def seg_dist(X, Y, a, b):
    """Distance to the segment a-b and the position along it (0..1)."""
    vx, vy = b[0] - a[0], b[1] - a[1]
    L = vx * vx + vy * vy
    t = np.clip(((X - a[0]) * vx + (Y - a[1]) * vy) / max(L, 1e-9), 0, 1)
    return np.hypot(X - (a[0] + t * vx), Y - (a[1] + t * vy)), t


def dist_polyline(X, Y, pts):
    d = np.full(X.shape, 1e9)
    for a, b in zip(pts[:-1], pts[1:]):
        d = np.minimum(d, seg_dist(X, Y, a, b)[0])
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


def in_rect(X, Y, r, pad=0.0):
    return (X > r[0] - pad) & (X < r[2] + pad) & (Y > r[1] - pad) & (Y < r[3] + pad)


def meta(mesh):
    p = os.path.join(MESHES, mesh + ".json")
    return json.load(open(p)) if os.path.exists(p) else {}


def rot(x, y, yaw):
    a = math.radians(yaw)
    return x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)


# ---------------------------------------------------------------------------------------------------- the plan

# The coast (clockwise from the west). The river's gorge cuts the south-east part off; the bridge and the east end join them.
ISLAND = [(-55.5, 29), (-51, 42), (-41, 55), (-22, 63), (8, 64), (38, 59), (56, 44), (64, 14), (64, -20), (56, -32), (47, -38),
          (31, -48.5), (21, -54.5), (11, -58.5), (2, -60.5), (-8.5, -61.5), (-22, -56.5), (-28.5, -51), (-32, -47), (-39.5, -42.5),
          (-45.5, -37), (-48.7, -29.5), (-49.6, -24), (-51.2, -17.5), (-53.5, -8), (-59, 1), (-60.4, 16.5)]
ISLETS = [(-60, -47, 5.0), (44, -56, 4.5)]     # x, y, radius: rocks with a tree off the coast (0: skipped)

# buildings: name -> (mesh, x, y, z, yaw). Fronts face -Y at yaw 0.
BUILD = dict(
    castle=("SM_Castle", -8.5, -0.5, 0.0, 0.0),
    barracks=("SM_BarracksYard", 11.0, -17.5, 0.0, 0.0),
    archery=("SM_ArcheryHall", -28.5, 4.75, 1.0, 0.0),
    mine=("SM_MineCliff", -21.0, 20.5, 1.0, 0.0),
    tower=("SM_WatchTower", -37.0, 30.0, 2.5, 0.0),
    cottage_a=("SM_FarmCottage_A", -26.5, -12.5, 0.0, 0.0),
    cottage_b=("SM_FarmCottage_B", -6.0, -21.0, 0.0, 0.0),
    farm=("SM_Farmstead", 36.0, -19.0, 1.0, 0.0),
    windmill=("SM_Windmill", 53.5, -10.5, 2.0, -90.0),          # its door and sails face west: towards the viewer's left
)
PLAZA = (-14.5, -12.0)
BRIDGE = (-13.75, -34.5)          # runs north-south (the asset's own Y), 7 m long
BRIDGE_N, BRIDGE_S = (BRIDGE[0], BRIDGE[1] + 3.5), (BRIDGE[0], BRIDGE[1] - 3.5)
DOCK = (-50.5, -24.0)             # its land end; it runs out west (yaw -90), deck 1 m above the sea
DOCK_Z = SEA + 1.0
SPAWN = (-14.5, -15.25, -120.0)     # x, y, facing (degrees from +X): by the plaza, facing the viewer


def footprint(key, pad=0.0):
    mesh, x, y, z, yaw = BUILD[key]
    (x0, y0, _), (x1, y1, _) = meta(mesh).get("bounds", [[-5, -5, 0], [5, 5, 5]])
    cs = [rot(a, b, yaw) for a in (x0, x1) for b in (y0, y1)]
    return (x + min(c[0] for c in cs) - pad, y + min(c[1] for c in cs) - pad, x + max(c[0] for c in cs) + pad, y + max(c[1] for c in cs) + pad, z)


def front(key, out=0.0, along=0.0):
    """A point `out` metres in front of a building's front edge (its own -Y), `along` metres to its right."""
    mesh, x, y, z, yaw = BUILD[key]
    y0 = meta(mesh).get("bounds", [[-5, -5, 0], [5, 5, 5]])[0][1]
    dx, dy = rot(along, y0 - out, yaw)
    return (round(x + dx, 2), round(y + dy, 2))


# The river: the pond and the upper river on the east terrace, the fall, the pool and the gorge, the fall into the sea.
POND = (19.5, -35.0, 3.6)
RIVER_UP = [(19.5, -35.0), (13.0, -36.5), (8.0, -37.5), (5.0, -38.0)]
FALL1 = (4.6, -38.0)
POOL_AT = (0.5, -38.25, 3.6)
RIVER_MID = [(3.5, -38.2), (-5.0, -36.0), (-13.75, -34.5), (-20.0, -36.5), (-24.5, -40.5), (-28.0, -45.5), (-31.0, -50.0)]
FALL2 = (-28.2, -45.8)
LILY_POND = (53.5, 7.5, 4.2)      # by the plots, with lily pads (References/Remake/farmland.png)

# the east terrace (+1): everything east of this line
EAST = [(22.0, 90), (22.0, -29.0), (7.0, -31.0), (5.0, -35.0), (5.0, -41.0), (23.0, -42.5), (28.0, -47.0), (38.0, -90), (90, -90), (90, 90)]

# paths: (points [(x, y, z)], half width, surface). A change of z between two points is a flight of steps.
MINE_APRON = (-18.5, 13.5)
FARM_GATE = front("farm", 1.2)
BARRACKS_GATE = front("barracks", 0.6)
ARCHERY_GATE = front("archery", 0.3)
TOWER_DOOR = front("tower", 0.3)
PATHS = [
    ([front("castle", 0.2) + (0,), (-10.5, -9.5, 0), PLAZA + (0,)], 1.5, COBBLE),
    ([PLAZA + (0,), (-21.0, -8.0, 0), (ARCHERY_GATE[0], -7.5, 0), (ARCHERY_GATE[0], -4.75, 1), ARCHERY_GATE + (1,)], 1.3, COBBLE),
    ([(-16.0, -9.5, 0), (-17.1, -6.5, 0), (-17.1, 7.0, 0), (-17.4, 10.0, 1), MINE_APRON + (1,)], 0.95, COBBLE),
    ([MINE_APRON + (1,), (-31.0, 13.25, 1), (TOWER_DOOR[0], 15.5, 1), (TOWER_DOOR[0], 19.5, 2.5), TOWER_DOOR + (2.5,)], 1.1, COBBLE),
    ([PLAZA + (0,), (-19.5, -20.5, 0), (-31.0, -23.0, 0), (-40.0, -24.0, 0), (-48.5, -24.0, DOCK_Z), (DOCK[0] + 0.25, DOCK[1], DOCK_Z)], 1.3, COBBLE),
    ([PLAZA + (0,), (-13.75, -22.0, 0), BRIDGE_N + (0,)], 1.4, COBBLE),
    ([BRIDGE_S + (0,), (-10.0, -43.5, 0), (0.0, -47.0, 0), (12.0, -48.0, 0), (21.5, -46.5, 0), (25.5, -44.0, 1), (31.0, -36.0, 1), FARM_GATE + (1,)], 1.25, COBBLE),
    ([BARRACKS_GATE + (0,), (11.0, -29.5, 0), (-3.0, -29.5, 0), (-13.75, -28.5, 0)], 1.3, COBBLE),
    ([(11.0, -29.5, 0), (19.5, -30.0, 0), (23.5, -30.0, 1), FARM_GATE + (1,)], 1.2, COBBLE),
    ([FARM_GATE + (1,), (49.0, -30.5, 1), (49.0, -18.0, 1), (49.0, -15.0, 2), (49.9, -10.5, 2)], 1.1, DIRT),   # up to the windmill
    ([(49.0, -18.0, 1), (47.6, -13.5, 1), (46.5, -9.0, 1), (35.0, -9.0, 1), (24.5, -9.0, 1)], 0.8, PLANK),      # along the front of the plots
    ([(35.0, -9.0, 1), (35.0, 0.0, 1), (35.0, 1.5, 1.5), (35.0, 8.0, 1.5)], 0.75, PLANK),   # between the plots, up the terrace
    ([(24.5, 0.0, 1), (46.0, 0.0, 1), (49.3, 4.0, 1)], 0.75, PLANK),                        # the cross path, on to the pond
]
# where a path meets something at its own level (steps, gates, bridge ends, the plaza): it is not sunk there
APRONS = [front("castle", 0.2), BRIDGE_N, BRIDGE_S, BARRACKS_GATE, ARCHERY_GATE, TOWER_DOOR, FARM_GATE, MINE_APRON, DOCK]

# the farm plots (References/Remake/farmland.png): fenced, terraced, plank paths between them
#          x0     y0    x1    y1   z    what          gate side
PLOTS = [(25.0, -7.5, 33.5, -1.0, 1.0, "wheat", "s"),
         (36.5, -7.5, 45.5, -1.0, 1.0, "greens", "s"),
         (25.0, 1.5, 33.5, 8.0, 1.5, "sheep", "e"),
         (36.5, 1.5, 45.5, 8.0, 1.5, "wheat", "w")]
# the cottages' paddocks: (x0, y0, x1, y1), the gap in the fence (side, from, to)
PADDOCK_A = (-34.5, -19.0, -22.25, -9.0)
PADDOCK_B = (-11.0, -27.25, 0.25, -17.0)
GAP_A = ("e", -17.5, -15.5)
GAP_B = ("w", -21.5, -19.5)

TREES = dict(A=7, B=7, C=26, D=36)        # how many of each tall tree (A and B are about 100k faces each)


# ---------------------------------------------------------------------------------------------------- the ground

def path_fields(X, Y):
    """For every cell: the path it lies on (height, surface, how far inside, whether on steps)."""
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
    plaza = (np.hypot(X - PLAZA[0], Y - PLAZA[1]) + rag) < 4.2
    z = np.where(plaza & np.isnan(z), 0.0, z)
    surf = np.where(plaza & (surf < 0), COBBLE, surf)
    return z, surf, steps


def heights():
    X, Y = grid()
    rag = (noise2(X, Y, 6.0, 11) - 0.5) * 3.0
    poly = ISLAND + [ISLAND[0]]
    dc = dist_polyline(X, Y, poly)
    dc = np.where(in_poly(X, Y, ISLAND), dc, -dc) + rag                    # > 0 on the island, metres from the coast
    for (ix, iy, r) in ISLETS:
        if r > 0:
            dc = np.maximum(dc, r - np.hypot(X - ix, Y - iy) + rag * 0.5)
    land = dc > 0

    # ---- levels
    n1 = noise2(X, Y, 14.0, 3)
    east = in_poly(X, Y, EAST)
    west = (X < -17.6) & (Y > -5.0 + (noise2(X, Y, 5.0, 23) - 0.5) * 0.0)
    h = np.zeros(X.shape)
    yy = Y + (n1 - 0.5) * 9.0
    mid = ~east & ~west
    h = np.where(mid & (yy > 9.5), 1.0, h)
    h = np.where(mid & (yy > 18.0), 2.0, h)
    h = np.where(west, 1.0, h)
    h = np.where(west & ((yy > 27.0) | (X < -46.0 + (n1 - 0.5) * 6)), 2.0, h)
    h = np.where(east, 1.0, h)
    h = np.where(east & (yy > 11.0), 2.0, h)
    h = np.where(yy > 30.0, np.maximum(h, 3.0), h)
    h = np.where(yy > 43.0, 4.0, h)
    # the tower's knoll, the windmill's mound
    tx, ty = BUILD["tower"][1], BUILD["tower"][2]
    h = np.where(np.hypot(X - tx, Y - (ty - 0.8)) < 9.5 + (n1 - 0.5) * 2, 2.5, h)
    wx, wy = BUILD["windmill"][1], BUILD["windmill"][2]
    h = np.where(np.hypot(X - wx, Y - wy) < 5.6, 2.0, h)
    h = np.where((np.hypot(X - wx, Y - wy) >= 5.6) & (np.hypot(X - wx, Y - wy) < 6.6), 1.5, h)
    # the islets
    for (ix, iy, r) in ISLETS:
        if r > 0:
            h = np.where(np.hypot(X - ix, Y - iy) < r + 2.5, -2.0 + np.round(n1 * 2) * 0.5, h)
    # the lawns are not one flat sheet: low grass platforms a quarter block high
    lawn = (noise2(X, Y, 4.5, 77) > 0.58)
    h = np.where(lawn, h + 0.25, h)

    # ---- the plots' terraces and the buildings' pads
    for (x0, y0, x1, y1, z, _k, _g) in PLOTS:
        h = np.where(in_rect(X, Y, (x0, y0, x1, y1), 0.9), z, h)
    h = np.where(in_rect(X, Y, (24.0, 0.9, 47.0, 9.0)), 1.5, h)
    pads = [footprint(k, 1.0) for k in BUILD]
    for (x0, y0, x1, y1, z) in pads:
        h = np.where(in_rect(X, Y, (x0, y0, x1, y1)), z, h)
    for pk in (PADDOCK_A, PADDOCK_B):
        h = np.where(in_rect(X, Y, pk, 0.5), 0.0, h)
    # behind the mine the ground stands as high as its cliff (the asset is a cliff face with the portal in it)
    m = footprint("mine")
    h = np.where(in_rect(X, Y, (m[0] - 3, m[3] - 1.0, m[2] + 3, m[3] + 7)), np.maximum(h, 3.0), h)

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
    # (blocks of 1.5 m here, 0.75 m there: broken rock, not a comb of single columns)
    blk = hash2(np.floor((X + 0.4 * np.floor(Y / 1.5)) / 1.5), np.floor(Y / 1.5), 7)
    blk2 = hash2(np.floor(X / 0.75), np.floor(Y / 0.75), 9)
    keep = path | apron
    for k in BUILD:
        keep |= in_rect(X, Y, footprint(k, 1.5))
    cut1 = land & (dc < 1.3) & ~keep & (blk > 0.62)
    cut2 = land & (dc < 2.6) & (dc >= 1.3) & ~keep & (blk > 0.8)
    h = np.where(cut1, h - 1.0 - np.round(blk2 * 3.0) * 0.5, h)
    h = np.where(cut2, h - 0.5 - np.round(blk2) * 0.5, h)
    h = np.where(~land, SEABED, h)
    rocks = ~land & (dc > -3.2) & (blk > 0.52)
    h = np.where(rocks, SEA - 0.5 + np.round(blk2 * 5.0) * 0.5 * (1.0 + dc / 3.2), h)

    # ---- the river
    wrag = (noise2(X, Y, 3.0, 21) - 0.5) * 0.8
    d_up = np.minimum(dist_polyline(X, Y, RIVER_UP) - 1.5, np.hypot(X - POND[0], Y - POND[1]) - POND[2]) + wrag
    d_mid = np.minimum(dist_polyline(X, Y, RIVER_MID) - 2.0, np.hypot(X - POOL_AT[0], Y - POOL_AT[1]) - POOL_AT[2]) + wrag * 0.6
    water_up = (d_up < 0) & east & land & ~path
    gorge = (d_mid < 0) & ~east & land
    water_mid = gorge
    h = np.where(water_up, UPPER - 0.75, h)
    h = np.where(water_up & (d_up < -0.9), UPPER - 1.0, h)
    h = np.where(gorge, POOL - 0.75, h)
    h = np.where(gorge & (d_mid < -0.9), POOL - 1.25, h)
    # rock shelves a little way down the gorge's sides (not under the bridge)
    shelf = (d_mid >= 0) & (d_mid < 0.75) & ~east & land & ~keep & (blk > 0.55)
    h = np.where(shelf, np.minimum(h, -0.75 - np.round(blk2) * 0.5), h)
    d_lily = np.hypot(X - LILY_POND[0], Y - LILY_POND[1]) - LILY_POND[2] + wrag
    water_lily = (d_lily < 0) & land & ~path
    h = np.where(water_lily, LILY - 0.75, h)
    h = np.where(water_lily & (d_lily < -1.0), LILY - 1.0, h)
    bank = (d_lily >= 0) & (d_lily < 1.2) & ~path
    h = np.where(bank, np.maximum(np.minimum(h, 1.5), 1.25), h)
    bank_up = (d_up >= 0) & (d_up < 1.0) & east & land & ~path
    h = np.where(bank_up, 1.0, h)

    sea = ~land & ~rocks
    return dict(X=X, Y=Y, h=h, land=land, dc=dc, sea=sea, rocks=rocks, east=east, path=path, psurf=psurf, psteps=psteps,
                water_up=water_up, water_mid=water_mid, water_lily=water_lily, pads=pads, cut=(cut1 | cut2) & ~water_up & ~water_mid)


def surface(G):
    X, Y, h = G["X"], G["Y"], G["h"]
    s = np.zeros(X.shape, np.int8)
    s[G["path"]] = G["psurf"][G["path"]]
    # the plots' soil, the paddocks' trodden earth
    for (x0, y0, x1, y1, z, kind, _g) in PLOTS:
        inside = in_rect(X, Y, (x0, y0, x1, y1), -0.4)
        s[inside & (s == 0) & ((kind != "sheep") | (noise2(X, Y, 3.0, 31) > 0.52))] = DIRT
    for pk in (PADDOCK_A, PADDOCK_B):
        s[in_rect(X, Y, pk, -0.3) & (s == 0) & (noise2(X, Y, 3.5, 31) > 0.6)] = DIRT
    s[(noise2(X, Y, 5.0, 41) > 0.82) & (s == 0) & G["land"]] = DIRT
    s[(noise2(X, Y, 3.0, 61) > 0.84) & (s == 0) & G["land"]] = MOSSY
    # the coast's ledges and rocks, the gorge's shelves
    cut = G["cut"]
    s[cut] = np.where(hash2(np.floor(X / 0.5), np.floor(Y / 0.5), 13)[cut] > 0.5, STONE, MOSSY)
    s[G["rocks"]] = np.where(hash2(np.floor(X / 0.5), np.floor(Y / 0.5), 13)[G["rocks"]] > 0.6, MOSSY, STONE)
    s[G["sea"]] = GRAVEL
    s[G["water_up"] | G["water_mid"] | G["water_lily"]] = GRAVEL
    return s


def ground(h, x, y):
    i = int(np.clip((x + HALF) / CELL, 0, N - 1))
    j = int(np.clip((y + HALF) / CELL, 0, N - 1))
    return float(h[i, j])


# ---------------------------------------------------------------------------------------------------- things

class Scene:
    def __init__(self, G, s):
        self.G, self.h, self.s = G, G["h"], s
        self.items = []
        self.missing = set()
        self.solid = []                    # (x, y, r): things that stand there, for the scatter to keep clear of

    def add(self, mesh, x, y, yaw=0.0, scale=1.0, z=None, dz=0.0, group="village", tags=None, r=None):
        if not os.path.exists(os.path.join(MESHES, mesh + ".gltf")):
            self.missing.add(mesh)
        zz = ground(self.h, x, y) if z is None else z
        it = dict(mesh=mesh, pos=[round(x, 3), round(y, 3), round(zz + dz, 3)], yaw=round(yaw, 2), scale=round(scale, 3), group=group)
        if tags:
            it["tags"] = list(tags)
        self.items.append(it)
        if r:
            self.solid.append((x, y, r))
        return it

    def with_props(self, mesh, x, y, z, yaw=0.0, group="buildings", tags=None):
        self.add(mesh, x, y, yaw, z=z, group=group, tags=tags)
        for pr in meta(mesh).get("props", []):
            px, py = rot(pr["pos"][0], pr["pos"][1], yaw)
            self.add(pr["mesh"], x + px, y + py, yaw + float(pr.get("yaw", 0.0)), float(pr.get("scale", 1.0)), z=z + pr["pos"][2], group="props")

    def tree(self, kind, x, y, yaw=0.0, scale=1.0, group="forest"):
        self.add("SM_Tree2_%s_Trunk" % kind, x, y, yaw, scale, dz=-0.15, group=group, r={"A": 1.6, "B": 1.5, "C": 1.1, "D": 0.7}[kind] * scale)
        self.add("SM_Tree2_%s_Leaves" % kind, x, y, yaw, scale, dz=-0.15, group=group)

    def fence(self, rect, z, gap=None, lanterns=False, skip=()):
        """A rail fence round a rectangle, 2 m pieces; gap = (side 'n'|'s'|'e'|'w', from, to): an opening, with a lantern
        on one of its posts (the other a plain post). Corners get plain posts unless lanterns=True (the user asked
        for fewer lights). skip: rectangles (buildings) it does not run through."""
        x0, y0, x1, y1 = rect
        sides = dict(s=((x0, y0), (x1, y0)), e=((x1, y0), (x1, y1)), n=((x1, y1), (x0, y1)), w=((x0, y1), (x0, y0)))
        for name, ((ax, ay), (bx, by)) in sides.items():
            L = math.hypot(bx - ax, by - ay)
            runs = [(0.0, L)]
            if gap and gap[0] == name:
                horiz = name in "sn"
                g0, g1 = sorted((abs(gap[1] - (ax if horiz else ay)), abs(gap[2] - (ax if horiz else ay))))
                runs = [(0.0, g0), (g1, L)]
                for k, g in enumerate((g0, g1)):
                    t = g / L
                    self.add("SM_Fence_Post_Lantern" if k == 0 else "SM_Fence_Post", ax + (bx - ax) * t, ay + (by - ay) * t, 0.0, z=z, group="farm", r=0.3)
            yaw = math.degrees(math.atan2(by - ay, bx - ax))
            for (r0, r1) in runs:
                if r1 - r0 < 0.4:
                    continue
                k = max(1, int(round((r1 - r0) / 2.0)))
                sc = (r1 - r0) / (k * 2.0)
                for j in range(k):
                    t = (r0 + (r1 - r0) * j / float(k)) / L
                    x, y = ax + (bx - ax) * t, ay + (by - ay) * t
                    mx, my = x + (bx - ax) / L * sc, y + (by - ay) / L * sc
                    if any(r[0] - 0.2 < mx < r[2] + 0.2 and r[1] - 0.2 < my < r[3] + 0.2 for r in skip):
                        continue
                    it = self.add("SM_Fence_Straight", x, y, yaw, z=z, group="farm")
                    it["scale3"] = [round(sc, 3), 1.0, 1.0]
            self.add("SM_Fence_Post_Lantern" if lanterns else "SM_Fence_Post", ax, ay, yaw, z=z, group="farm", r=0.3)


def things(G, s):
    X, Y, h = G["X"], G["Y"], G["h"]
    sc = Scene(G, s)
    rng = np.random.default_rng(20261121)
    water = G["water_up"] | G["water_mid"] | G["water_lily"]

    # ---- the buildings (with what their sidecars ask to have placed with them)
    for key, (mesh, x, y, z, yaw) in BUILD.items():
        if key == "windmill":
            continue
        sc.with_props(mesh, x, y, z - 0.01, yaw)
    mesh, x, y, z, yaw = BUILD["windmill"]
    sc.add(mesh, x, y, yaw, z=z, group="buildings")
    hub = meta(mesh).get("hub", [0.0, -3.0, 7.5])
    hx, hy = rot(hub[0], hub[1], yaw)
    sc.add("SM_Windmill_Sails", x + hx, y + hy, yaw, z=z + hub[2], group="buildings", tags=["Spin"])
    sc.add("SM_Bridge", BRIDGE[0], BRIDGE[1], 0.0, z=0.04, group="buildings")
    sc.add("SM_PlazaBanner", PLAZA[0], PLAZA[1], z=0.0, r=1.3)
    sc.with_props("SM_Dock", DOCK[0], DOCK[1], DOCK_Z, -90.0)
    moor = meta("SM_Dock").get("moor", [2.9, -5.9, -1.0, 90.0])
    mx, my = rot(moor[0], moor[1], -90.0)
    sc.add("SM_Boat", DOCK[0] + mx, DOCK[1] + my, moor[3] - 90.0, z=SEA + 0.02, group="props")

    # ---- the cottages' paddocks: wheat, sheep, hay
    fa, fb = footprint("cottage_a"), footprint("cottage_b")
    sc.fence(PADDOCK_A, 0.0, GAP_A, skip=[fa])
    sc.fence(PADDOCK_B, 0.0, GAP_B, skip=[fb])

    def crops(x0, y0, x1, y1, z, mesh="SM_Wheat", step=1.0, scale=(0.92, 1.1), jitter=0.06):
        nx, ny = max(1, int(round((x1 - x0) / step))), max(1, int(round((y1 - y0) / step)))
        for i in range(nx):
            for j in range(ny):
                x = x0 + (i + 0.5) * (x1 - x0) / nx + rng.uniform(-jitter, jitter)
                y = y0 + (j + 0.5) * (y1 - y0) / ny + rng.uniform(-jitter, jitter)
                m = mesh if isinstance(mesh, str) else mesh[(i if len(mesh) < 4 else j) % len(mesh)]
                sc.add(m, x, y, float(rng.integers(0, 4)) * 90.0 + rng.uniform(-8, 8), float(rng.uniform(*scale)), z=z, group="farm")

    crops(-30.5, -18.3, -23.0, -15.6, 0.0)                                 # A: wheat in front of the cottage
    for (x, y, yaw) in ((-32.6, -11.0, 200), (-31.5, -13.2, 250), (-33.0, -15.0, 120)):
        sc.add("SM_Sheep", x, y, yaw, z=0.0, group="farm", r=0.6)
    sc.add("SM_Trough", -33.6, -12.5, 90.0, z=0.0, group="farm", r=0.8)
    sc.add("SM_HayStack", -23.2, -10.2, 20.0, z=0.0, group="farm", r=0.9)
    sc.add("SM_HayBale", -24.0, -14.4, 75.0, z=0.0, group="farm", r=0.6)
    crops(-10.3, -26.6, -0.5, -24.2, 0.0)                                  # B: wheat in front and to the east
    crops(-2.6, -23.6, -0.5, -18.0, 0.0)
    sc.add("SM_HayStack", -9.6, -18.2, -30.0, z=0.0, group="farm", r=0.9)
    sc.add("SM_HayBale", -10.0, -23.0, 10.0, z=0.0, group="farm", r=0.6)
    sc.add("SM_Barrel", -2.9, -17.8, 0.0, z=0.0, group="farm", r=0.5)

    # ---- the plots (farmland.png): fenced terraces, each with its gate on a plank path
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
    sc.add("SM_HayCart", 41.5, -32.6, 12.0, group="farm", r=1.9)
    sc.add("SM_HayBale", 44.5, -32.4, 40.0, group="farm", r=0.6)
    sc.add("SM_Sacks", 50.2, -7.6, -30.0, group="farm", r=0.8)
    sc.add("SM_Barrel", 50.4, -13.2, 0.0, group="farm", r=0.5)

    # ---- clutter in the town
    for (mesh, x, y, yaw) in (("SM_CrateStack", -39.0, -20.6, 20), ("SM_Barrel", -37.6, -20.4, 0), ("SM_Crate", -40.4, -25.4, 15),
                              ("SM_Barrel", -45.3, -20.9, 0), ("SM_Signpost", -16.6, -25.5, 200), ("SM_FlowerPlanter", -12.2, -6.6, 0),
                              ("SM_FlowerPlanter", -4.8, -6.6, 0), ("SM_Signpost", 21.0, -44.2, 160), ("SM_Barrel", -15.6, 14.6, 0),
                              ("SM_Crate", -14.9, 13.4, 30), ("SM_MineCart", -16.2, 16.3, 90), ("SM_Sacks", 1.2, -28.0, 40),
                              ("SM_ArrowBarrel", -24.0, -3.6, 0), ("SM_Signpost", 22.8, -27.8, 20)):
        sc.add(mesh, x, y, yaw, r=0.9)

    def cell(x, y):
        return int(np.clip((x + HALF) / CELL, 2, N - 3)), int(np.clip((y + HALF) / CELL, 2, N - 3))

    def level(x, y, r=2):
        i, j = cell(x, y)
        return h[i - r, j] == h[i, j] == h[i + r, j] == h[i, j - r] == h[i, j + r]

    def on_pad(x, y, pad=0.6):
        for (x0, y0, x1, y1, _z) in G["pads"]:
            if x0 - pad < x < x1 + pad and y0 - pad < y < y1 + pad:
                return True
        for (x0, y0, x1, y1) in (PADDOCK_A, PADDOCK_B) + tuple(p[:4] for p in PLOTS):
            if x0 - pad < x < x1 + pad and y0 - pad < y < y1 + pad:
                return True
        return math.hypot(x - BRIDGE[0], y - BRIDGE[1]) < 5.0 or math.hypot(x - PLAZA[0], y - PLAZA[1]) < 5.0

    path_d = np.full(X.shape, 1e9)
    for pts, w, _s in PATHS:
        path_d = np.minimum(path_d, dist_polyline(X, Y, [(p[0], p[1]) for p in pts]) - w)

    def free(x, y, r, path_gap=0.5, allow_pad=False):
        i, j = cell(x, y)
        if not G["land"][i, j] or water[i, j] or s[i, j] in (COBBLE, PLANK, GRAVEL) or G["dc"][i, j] < 1.2:
            return False
        if path_d[i, j] < path_gap + r or not level(x, y, max(1, int(r / CELL))):
            return False
        if not allow_pad and on_pad(x, y, 0.4 + r):
            return False
        return not any(math.hypot(x - a, y - b) < r + q for (a, b, q) in sc.solid)

    # ---- lantern posts along the paths, alternating sides
    for pts, w, surf in PATHS:
        if surf == PLANK:
            continue
        run, side = 4.0, 1
        for a, b in zip(pts[:-1], pts[1:]):
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            ux, uy = (b[0] - a[0]) / max(L, 1e-6), (b[1] - a[1]) / max(L, 1e-6)
            d = 0.0
            while d < L:
                if run >= 18.0:                  # (every 9 m was too many lights)
                    x, y = a[0] + ux * d - uy * side * (w + 1.0), a[1] + uy * d + ux * side * (w + 1.0)
                    if free(x, y, 0.45, 0.25) and abs(a[2] - b[2]) < 1e-6:
                        sc.add("SM_LanternPost", x, y, r=1.0)
                        run, side = 0.0, -side
                d += 0.5
                run += 0.5
    for (x, y) in ((PLAZA[0] - 4.6, PLAZA[1] + 2.6), (PLAZA[0] + 4.4, PLAZA[1] - 3.0), (PLAZA[0] + 3.2, PLAZA[1] + 4.0), (PLAZA[0] - 3.4, PLAZA[1] - 4.4)):
        if free(x, y, 0.4, 0.2, allow_pad=True):
            sc.add("SM_LanternPost_Tall", x, y, yaw=math.degrees(math.atan2(PLAZA[1] - y, PLAZA[0] - x)) + 90.0, r=1.0)

    # ---- trees: a few placed by hand where the picture has them, the rest in the forest behind and round the edges
    hand = [("B", -52.0, 26.0), ("A", -47.5, 9.0), ("C", -42.0, -8.0), ("A", -35.5, -33.5), ("C", -24.0, -28.0), ("D", -31.5, 0.0 - 26.5),
            ("B", -6.0, 12.5), ("A", 8.0, 9.5), ("C", 20.0, 6.0), ("A", -9.0, 27.0), ("B", 10.0, 24.0), ("C", 0.0, 17.0), ("D", 16.5, 14.0),
            ("C", 27.0, -38.5), ("B", 14.0, -55.0), ("C", -4.0, -55.0), ("D", -19.0, -45.5), ("A", 40.0, -44.0), ("D", 2.0, -43.0),
            ("C", 58.0, -24.0), ("D", 47.5, 12.0), ("C", -44.5, 17.5), ("D", -26.5, 30.5), ("D", 22.5, -4.5),
            ("C", 2.5, -3.0), ("D", 21.5, -34.0), ("D", -3.5, -33.5), ("C", -39.0, -10.5), ("C", -41.0, 2.5),
            ("D", -33.5, -28.5), ("D", 8.0, -43.5), ("D", -20.5, -5.5), ("C", 30.0, -42.0), ("D", 1.5, -8.0), ("D", -44.0, -13.0),
            ("D", 16.0, -34.0), ("C", -6.5, -48.5), ("D", 34.0, -33.5), ("D", 59.0, -1.0), ("C", 12.0, 3.5), ("C", -60.0, -47.0), ("D", 44.0, -56.0)]
    count = dict(A=0, B=0, C=0, D=0)
    for kind, x, y in hand:
        r = {"A": 1.6, "B": 1.5, "C": 1.1, "D": 0.7}[kind]
        if free(x, y, r, 1.2) or kind == "C" and min(math.hypot(x + 60, y + 47), math.hypot(x - 44, y + 56)) < 1:
            sc.tree(kind, x, y, yaw=float(rng.integers(0, 4)) * 90.0, scale=float(rng.uniform(0.9, 1.05)), group="frame")
            count[kind] += 1
    tries = 0
    gap = {"A": 11.0, "B": 10.0, "C": 7.0, "D": 4.5}
    trees = [(it["pos"][0], it["pos"][1], it["mesh"][9]) for it in sc.items if it["mesh"].endswith("_Trunk")]
    for kind in "ABCD":
        while count[kind] < TREES[kind] and tries < 60000:
            tries += 1
            x, y = rng.uniform(-HALF + 6, HALF - 6, 2)
            wood = (y > 8.0 and -17 < x < 22) or (y > 26) or (x < -42 and y > -4) or (y > 11 and x > 22) or (y < -42 and kind in "CD") \
                or (x > 50 and y < -12 and kind in "CD")
            if not wood or not free(x, y, {"A": 1.6, "B": 1.5, "C": 1.1, "D": 0.7}[kind] + 0.6, 2.4):
                continue
            if any(math.hypot(x - ax, y - ay) < 7.5 for (ax, ay) in APRONS):
                continue
            if any(math.hypot(x - a, y - b) < (gap[kind] + gap[k2]) / 2.0 for a, b, k2 in trees):
                continue
            trees.append((x, y, kind))
            sc.tree(kind, x, y, yaw=float(rng.integers(0, 4)) * 90.0, scale=float(rng.uniform(0.85, 1.1)))
            count[kind] += 1

    # ---- undergrowth
    def scatter(n, meshes, r, group, gap, scale=(0.9, 1.15), where=None, solid=False, allow_pad=False):
        placed, t = [], 0
        while len(placed) < n and t < n * 80:
            t += 1
            x, y = rng.uniform(-HALF + 3, HALF - 3, 2)
            if where and not where(x, y):
                continue
            if not free(x, y, r, 0.3, allow_pad) or any(math.hypot(x - a, y - b) < gap for a, b in placed):
                continue
            placed.append((x, y))
            sc.add(str(rng.choice(meshes)), x, y, yaw=float(rng.uniform(0, 360)) if group != "rocks" else float(rng.integers(0, 4)) * 90.0,
                   scale=float(rng.uniform(*scale)), group=group, r=r if solid else None)

    scatter(46, ["SM_Rock_A", "SM_Rock_B", "SM_Rock_B", "SM_Rock_C", "SM_Rock_C", "SM_Rock_D", "SM_Rock_E"], 1.5, "rocks", 5.0, scale=(0.7, 1.0), solid=True)
    scatter(200, ["SM_Bush_A", "SM_Bush_A", "SM_Bush_B", "SM_Bush_B", "SM_Bush_C"], 0.8, "plants", 2.2, scale=(0.8, 1.25))
    scatter(850, ["SM_Flowers_A", "SM_Flowers_B", "SM_Flowers_C", "SM_Flowers_D"], 0.3, "plants", 1.0)
    scatter(1400, ["SM_GrassTuft_A", "SM_GrassTuft_B", "SM_GrassTuft_C", "SM_GrassTuft_C"], 0.3, "plants", 0.6, scale=(0.9, 1.5))
    # rocks at the cliff's foot and on its ledges (nobody walks there)
    k = 0
    for _ in range(4000):
        if k >= 40:
            break
        x, y = rng.uniform(-HALF + 3, HALF - 3, 2)
        i, j = cell(x, y)
        if G["rocks"][i, j] and h[i, j] > SEA - 0.3 and not any(math.hypot(x - a, y - b) < 4.0 for a, b, _q in sc.solid) \
                and math.hypot(x - DOCK[0] + 6, y - DOCK[1]) > 11.0:
            sc.add(str(rng.choice(["SM_Rock_A", "SM_Rock_B", "SM_Rock_D", "SM_Rock_E"])), x, y, float(rng.integers(0, 4)) * 90.0,
                   float(rng.uniform(0.8, 1.2)), group="rocks", r=1.5)
            k += 1
    # lily pads: the lily pond, the spring pond, a few on the sea by the dock
    k = 0
    for _ in range(3000):
        if k >= 46:
            break
        x, y = rng.uniform(-HALF + 3, HALF - 3, 2)
        i, j = cell(x, y)
        if G["water_lily"][i, j] and h[i, j] <= LILY - 1.0:
            z = LILY
        elif G["water_up"][i, j] and math.hypot(x - POND[0], y - POND[1]) < POND[2] - 0.6:
            z = UPPER
        elif G["sea"][i, j] and -3.0 > G["dc"][i, j] > -9.0 and (x < -44 and -40 < y < -26 or 44 < x and y < -40) and rng.random() < 0.3:
            z = SEA
        else:
            continue
        sc.add(str(rng.choice(["SM_LilyPad_A", "SM_LilyPad_B"])), x, y, float(rng.uniform(0, 360)), z=z + 0.02, group="plants")
        k += 1
    return sc


# ---------------------------------------------------------------------------------------------------- output

def build(write=True):
    G = heights()
    s = surface(G)
    sc = things(G, s)
    h = G["h"]
    tower = BUILD["tower"]
    layout = dict(
        camera=dict(pos=list(C.POS), target=list(C.TARGET), hfov=C.HFOV, az=C.AZ, el=C.EL, width=C.W, height=C.H),
        terrain=dict(cell=CELL, half=HALF, zmin=ZMIN, sea=SEA, seabed=SEABED, pool=POOL, upper=UPPER, lily=LILY, surfaces=SURF),
        spawn=dict(pos=[SPAWN[0], SPAWN[1], ground(h, SPAWN[0], SPAWN[1])], yaw=SPAWN[2]),
        places=dict(plaza=PLAZA, bridge=BRIDGE, bridge_n=BRIDGE_N, bridge_s=BRIDGE_S, dock=DOCK, fall1=FALL1, fall2=FALL2,
                    glade=(3.0, 14.0), **{k: (v[1], v[2]) for k, v in BUILD.items()}),
        gates=dict(barracks=BARRACKS_GATE, archery=ARCHERY_GATE, farm=FARM_GATE, tower=TOWER_DOOR, mine=MINE_APRON),
        instances=sc.items,
    )
    if write:
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, "town.json"), "w") as f:
            json.dump(layout, f)
        np.savez_compressed(os.path.join(OUT, "town_terrain.npz"), h=h, s=s)
        counts = {}
        for it in sc.items:
            counts[it["mesh"]] = counts.get(it["mesh"], 0) + 1
        faces = sum(meta(m).get("faces", 0) * n for m, n in counts.items())
        print("town: %d instances, %d kinds, %.2f M faces; trees %s; not built yet: %s" % (
            len(sc.items), len(counts), faces / 1e6, {k: counts.get("SM_Tree2_%s_Trunk" % k, 0) for k in "ABCD"}, ", ".join(sorted(sc.missing)) or "none"))
    return layout, G, s


def debug(layout, G, s, path=None):
    """The plan through the postcard camera, beside and over the reference picture (PIL; not available inside Blender)."""
    from PIL import Image, ImageDraw
    X, Y, h = G["X"], G["Y"], G["h"]
    cols = np.array([(96, 150, 50), (190, 160, 110), (140, 100, 60), (120, 120, 120), (150, 150, 150), (110, 140, 100), (200, 140, 70)], np.uint8)
    rgb = cols[s].astype(np.float32)
    rgb *= (0.75 + 0.06 * np.clip(h, -3, 4))[:, :, None]
    wat = G["water_up"] | G["water_mid"] | G["water_lily"]
    rgb[wat] = (70, 140, 210)
    hh = np.where(wat, np.where(G["water_up"], UPPER, np.where(G["water_mid"], POOL, LILY)), h)
    rgb[G["sea"]] = (40, 90, 160)
    hh = np.where(G["sea"], SEA, hh)
    img = np.zeros((C.H, C.W, 3), np.uint8)
    img[:] = (30, 60, 110)
    # painter's order: far to near along the view direction
    depth = X * C.FWD[0] + Y * C.FWD[1]
    order = np.argsort(-depth, axis=None)
    xs, ys, zs = X.ravel()[order], Y.ravel()[order], hh.ravel()[order]
    cc = np.clip(rgb.reshape(-1, 3)[order], 0, 255).astype(np.uint8)
    for dz, shade in ((-1.5, 0.45), (-0.75, 0.55), (0.0, 1.0)):
        px, py = C.project(xs, ys, np.maximum(zs + dz, SEA))
        px, py = np.round(px).astype(int), np.round(py).astype(int)
        ok = (px >= 0) & (px < C.W - 1) & (py >= 0) & (py < C.H - 1)
        col = (cc[ok] * shade).astype(np.uint8)
        for ox in (0, 1):
            for oy in (0, 1):
                img[py[ok] + oy, px[ok] + ox] = col
    im = Image.fromarray(img)
    dr = ImageDraw.Draw(im)
    for it in layout["instances"]:
        m = meta(it["mesh"])
        if not m or it.get("group") not in ("buildings", "forest", "frame", "village"):
            continue
        (x0, y0, z0), (x1, y1, z1) = m["bounds"]
        x, y, z = it["pos"]
        sc_ = it["scale"]
        if it["mesh"].endswith("_Leaves"):
            continue
        if it["mesh"].endswith("_Trunk"):
            lm = meta(it["mesh"].replace("_Trunk", "_Leaves"))["bounds"]
            c = C.project(x, y, z + (lm[0][2] + lm[1][2]) / 2 * sc_)
            r = (lm[1][0] - lm[0][0]) / 2 * sc_ * 15 * 0.8
            dr.ellipse([c[0] - r, c[1] - r * 0.8, c[0] + r, c[1] + r * 0.8], outline=(20, 70, 20), width=2)
            f = C.project(x, y, z)
            dr.line([f, c], fill=(90, 60, 30), width=3)
            continue
        cs = [rot(a, b, it["yaw"]) for a, b in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
        lo = [C.project(x + a * sc_, y + b * sc_, z) for a, b in cs]
        hi = [C.project(x + a * sc_, y + b * sc_, z + z1 * sc_) for a, b in cs]
        colr = (255, 230, 80) if it.get("group") == "buildings" else (255, 255, 255)
        for k in range(4):
            dr.line([lo[k], lo[(k + 1) % 4]], fill=colr, width=2)
            dr.line([hi[k], hi[(k + 1) % 4]], fill=colr, width=1)
            dr.line([lo[k], hi[k]], fill=colr, width=1)
        dr.line([lo[0], lo[1]], fill=(255, 60, 60), width=3)               # the front
    ref = Image.open(os.path.join(ROOT, "References", "Remake", "town.png")).convert("RGB").resize((C.W, C.H))
    out = Image.new("RGB", (C.W, C.H * 2))
    out.paste(ref, (0, 0))
    out.paste(im, (0, C.H))
    path = path or os.path.join(ROOT, "Saved", "town_plan.png")
    out.save(path)
    Image.blend(ref, im, 0.55).save(path.replace(".png", "_blend.png"))
    print(path)


if __name__ == "__main__":
    L, G, S = build()
    if "--debug" in sys.argv:
        debug(L, G, S)
