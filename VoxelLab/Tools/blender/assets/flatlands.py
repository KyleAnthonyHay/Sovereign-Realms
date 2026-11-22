"""The Flatlands: a flat field with every building side by side, for reviewing them and checking the look.

    Blender -b --factory-startup --python Tools/blender/assets/flatlands.py

Writes
  SourceArt/flatlands.json      the plan (same instance format as layout.json, plus name labels, the spawn, the camera,
                                the figures of the line-up)
  SM_Flat_<i>_<j>               the ground: quarter-block grass, a cobbled road sunk one step along the fronts,
                                a spur of it to every door, the harbour's pond with shelved banks, the line-up's
                                cobbled patch (SourceArt/Meshes/flat_tiles.json lists the tiles)
  SM_FlatPond                   the pond's water (slot "water": M_VoxWater)
Tools/ue/build_flatlands.py turns it into /Game/Maps/L_Flatlands.

The buildings stand at the size they have in the village (SourceArt/layout.json), fronts (-Y) on one line facing
the road, in the order of BUILDINGS. Across the road (south, toward the camera): King David and every troop in a line
(FIGURES: each figure's parts in the pose they were modelled in, static), the harbour (SM_Dock running out into a
pond, the grain ship SM_Boat moored at the dock's "moor"), and the props of Realm v2 (PROPS: the ruins, the port).
The farm's two hands (the farmer woman and man) are not placed: the game gives every finished farm its pair
(UVLConstruction::TickFarmhands) once the match runs, so they work the Flatlands farm too; they also stand in the line.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import numpy as np
import minehill

ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SRC = os.path.join(ROOT, "SourceArt")
MESHES = os.path.join(SRC, "Meshes")

# meshes (the first one that has been built is used), label, door offset along x in the asset (metres, before scaling).
# The barracks, archery range and farm are the remakes with their yards (References/Remake/*.png); the village keeps
# the old SM_Barracks / SM_ArcheryRange / SM_FarmCottage_* until it is rebuilt.
BUILDINGS = [
    (("SM_Castle",), "Castle", 0.0),
    (("SM_TownHall",), "Town Hall", 1.0),
    (("SM_BarracksYard", "SM_Barracks"), "Barracks", 0.0),
    (("SM_ArcheryHall", "SM_ArcheryRange"), "Archery Range", 0.0),
    (("SM_WatchTower",), "Watch Tower", 0.0),
    (("SM_MineCliff",), "Gold Mine", 2.5),
    (("SM_Farmstead", "SM_FarmCottage_A"), "Farm", 0.0),
    (("SM_Treasury",), "Treasury", 1.75),
    (("SM_Granary",), "Granary", 1.75),
    (("SM_Bridge",), "Bridge", 0.0),
]
# the line-up, left to right as seen from the road: (figure json in SourceArt/Meshes, its parts' folder, its name)
FIGURES = [
    ("SM_KingB", "/Game/Voxel/King", "King David"),
    ("SM_Swordsman", "/Game/Voxel/Troops/Swordsman", "Swordsman"),
    ("SM_Archer", "/Game/Voxel/Troops/Archer", "Archer"),
    ("SM_Spy", "/Game/Voxel/Troops/Spy", "Spy"),
    ("SM_Builder", "/Game/Voxel/Troops/Builder", "Builder"),
    ("SM_FarmerWoman", "/Game/Voxel/Troops/FarmerWoman", "Farmer"),
    ("SM_FarmerMan", "/Game/Voxel/Troops/FarmerMan", "Farmer"),
]
LINE = (0.0, -20.0)       # the line-up's middle
LINE_GAP = 2.2            # metres between figures
HARBOUR_X = 78.0          # the dock's land end (x), on the road's south side (across from the treasury and the granary)
DOCK_Y = -15.5
WATER_Z = -1.0            # the pond's water: a metre under the dock's deck, as at sea
POND = (HARBOUR_X - 13.0, -39.0, HARBOUR_X + 13.0, -16.5)          # x0, y0, x1, y1 of the pond's water edge (rounded)
# the newest props, in a row west of the line-up (left to right): (mesh, gap after it); the port's pieces only once built
PROPS = [("SM_Port_Tower", 3.0), ("SM_Port_Warehouse", 3.0), ("SM_Port_Arch", 3.0), ("SM_Port_Crane", 5.0),
         ("SM_Ruin_Arch", 2.0), ("SM_Ruin_Pillar_A", 1.5), ("SM_Ruin_Pillar_B", 1.5), ("SM_Ruin_Pillar_C", 2.0), ("SM_Ruin_Block", 0.0)]
PROPS_X1 = -14.0          # where the props' row ends (east)
PROPS_Y = -26.0           # the line their fronts stand on
GAP = 7.0                 # metres between buildings
FRONT = -6.0              # the line the fronts stand on
ROAD = (-11.0, -8.0)      # the road along the fronts (y from, to)
CELL = 0.25
W, D = 196.0, 104.0       # the field (at least: it grows to hold the row)
CY = 6.0                  # its middle in y
DEPTH = 3.0               # metres of ground (the pond is 2.5 m deep)
# A mine never stands alone on flat ground: the Gold Mine stands in SM_MineMound, the terraced hill of References/Remake/
# mine_mound.png (assets/mine_mound.py), placed at the mine's own place and turn; the row leaves room for its wings.
MOUND = "SM_MineMound"


def meta(mesh):
    return json.load(open(os.path.join(MESHES, mesh + ".json")))


def bounds(mesh):
    return meta(mesh)["bounds"]


def built(meshes):
    for m in meshes:
        if os.path.exists(os.path.join(MESHES, m + ".json")):
            return m
    raise FileNotFoundError(meshes)


def village_scale(layout, mesh):
    for it in layout["instances"]:
        if it["mesh"] == mesh:
            return it.get("scale", 1.0)
    return 1.0


def plan():
    layout = json.load(open(os.path.join(SRC, "layout.json")))
    items, labels, foot = [], [], []
    widths, wings = [], []
    chosen = [(built(meshes), title, door) for meshes, title, door in BUILDINGS]
    for mesh, title, door in chosen:
        (x0, y0, _), (x1, y1, _) = bounds(mesh)
        s = village_scale(layout, mesh)
        wing = 0.0
        if mesh == "SM_MineCliff" and os.path.exists(os.path.join(MESHES, MOUND + ".json")):
            mb = minehill.mound_bounds()
            wing = max(x0 - mb[0], mb[2] - x1, 0.0) * s - GAP + 2.0      # the hill's wings reach beyond the mine: 2 m clear of the neighbours
        wings.append(max(wing, 0.0))
        widths.append((x1 - x0) * s + 2 * wings[-1])
    total = sum(widths) + GAP * (len(widths) - 1)
    x = -total / 2.0
    for (mesh, title, door), w, wing in zip(chosen, widths, wings):
        (x0, y0, _), (x1, y1, z1) = bounds(mesh)
        s = village_scale(layout, mesh)
        cx = x + wing - x0 * s
        cy = FRONT - y0 * s
        z = 0.04 if mesh == "SM_Bridge" else -0.01         # the underside of a floor just under the grass, not on it
        items.append(dict(mesh=mesh, pos=[round(cx, 3), round(cy, 3), z], yaw=0.0, scale=round(s, 3), group="buildings"))
        foot.append((x0 * s + cx, y0 * s + cy, x1 * s + cx, y1 * s + cy))
        if mesh == "SM_MineCliff" and os.path.exists(os.path.join(MESHES, MOUND + ".json")):
            items.append(dict(mesh=MOUND, pos=[round(cx, 3), round(cy, 3), 0.0], yaw=0.0, scale=round(s, 3), group="rocks", tags=["MineMound"]))
            foot.append(minehill.mound_rect(cx, cy, 0.0, s))             # (nothing is strewn in its hill)
        # what the asset asks to have placed with it (dummies, wheat, sheep...): its own space, yaw 0 here
        for pr in meta(mesh).get("props", []):
            px, py, pz = pr["pos"]
            items.append(dict(mesh=pr["mesh"], pos=[round(cx + px * s, 3), round(cy + py * s, 3), round(pz * s, 3)],
                              yaw=float(pr.get("yaw", 0.0)), scale=round(float(pr.get("scale", 1.0)) * s, 3), group="props"))
        dx = cx + door * s
        labels.append(dict(text=title, pos=[round(dx, 2), ROAD[0] - 3.2, 0.0], door=round(dx, 2)))
        x += w + GAP
    figures, extra_labels = extras(items, foot)
    labels += extra_labels
    if not any(it["mesh"] == "SM_TrainingDummy" for it in items):
        # the old barracks has no yard: dummies by the road in front of it, for the sword
        bx = [it for it in items if it["mesh"] == "SM_Barracks"][0]["pos"][0]
        for k, (ox, oy) in enumerate(((-3.0, -13.5), (0.0, -14.5), (3.0, -13.5))):
            items.append(dict(mesh="SM_TrainingDummy", pos=[bx + ox, oy, 0.0], yaw=float(180 + 15 * (k - 1)), scale=1.0, group="props"))
            foot.append((bx + ox - 0.8, oy - 0.8, bx + ox + 0.8, oy + 0.8))
    return layout, items, labels, foot, total, figures


def extras(items, foot):
    """The line-up of figures, the harbour (dock, ship, pond) and the row of the newest props, south of the road."""
    figures, labels = [], []
    n = len(FIGURES)
    for i, (key, folder, title) in enumerate(FIGURES):
        if not os.path.exists(os.path.join(MESHES, key + ".json")):
            continue
        x = LINE[0] + (i - (n - 1) / 2.0) * LINE_GAP
        parts = meta(key)["parts"]
        figures.append(dict(name=title, folder=folder, pos=[round(x, 3), LINE[1], 0.0],
                            parts=[dict(mesh=d["mesh"], pivot=d["pivot"]) for d in parts.values()]))
    hx = (n - 1) / 2.0 * LINE_GAP + 1.4
    foot.append((LINE[0] - hx, LINE[1] - 2.6, LINE[0] + hx, LINE[1] + 1.6))
    labels.append(dict(text="King and troops", pos=[LINE[0], LINE[1] - 4.2, 0.0], door=None))
    # the harbour: the dock runs out (-Y) from the road's edge into the pond, the ship lies at its mooring
    if os.path.exists(os.path.join(MESHES, "SM_Dock.json")):
        dm = meta("SM_Dock")
        items.append(dict(mesh="SM_Dock", pos=[HARBOUR_X, DOCK_Y, 0.0], yaw=0.0, scale=1.0, group="buildings"))
        for pr in dm.get("props", []):
            px, py, pz = pr["pos"]
            items.append(dict(mesh=pr["mesh"], pos=[round(HARBOUR_X + px, 3), round(DOCK_Y + py, 3), pz], yaw=float(pr.get("yaw", 0.0)),
                              scale=float(pr.get("scale", 1.0)), group="props"))
        mx, my, _mz, myaw = dm.get("moor", [0.0, -14.8, -1.0, 0.0])
        items.append(dict(mesh="SM_Boat", pos=[HARBOUR_X + mx, DOCK_Y + my, WATER_Z + 0.02], yaw=myaw, scale=1.0, group="props"))
        labels.append(dict(text="Harbour", pos=[HARBOUR_X - 3.6, ROAD[0] - 3.2, 0.0], door=None))
    x0, y0, x1, y1 = POND
    foot.append((x0 - 2.0, y0 - 2.0, x1 + 2.0, y1 + 2.0))
    # the newest props, right to left from PROPS_X1, fronts on PROPS_Y
    x = PROPS_X1
    built_props = [(mesh, gap) for mesh, gap in PROPS if os.path.exists(os.path.join(MESHES, mesh + ".json"))]
    for k, (mesh, _gap) in enumerate(reversed(built_props)):
        (bx0, by0, _), (bx1, by1, _) = bounds(mesh)
        x -= bx1
        items.append(dict(mesh=mesh, pos=[round(x, 3), round(PROPS_Y - by0, 3), 0.0], yaw=0.0, scale=1.0, group="props"))
        foot.append((x + bx0, PROPS_Y, x + bx1, PROPS_Y + (by1 - by0)))
        left = len(built_props) - 2 - k                       # the gap after the piece to its left
        x += bx0 - (built_props[left][1] if left >= 0 else 0.0)
    if x < PROPS_X1:
        labels.append(dict(text="Ruins and port", pos=[round((x + PROPS_X1) / 2.0, 2), PROPS_Y - 2.6, 0.0], door=None))
    return figures, labels


def pond_depth(X, Y, rag):
    """How far inside the pond's edge each cell is (metres; < 0 outside): a rectangle with rounded corners."""
    x0, y0, x1, y1 = POND
    r = 4.0
    cx, cy = np.clip(X, x0 + r, x1 - r), np.clip(Y, y0 + r, y1 - r)
    return r - np.hypot(X - cx, Y - cy) + rag * 1.5


def field(labels):
    """Heights (top of the ground) and surfaces on the quarter-block grid: 0 grass, 1 cobble road."""
    nx, ny = int(W / CELL), int(D / CELL)
    xs = -W / 2 + (np.arange(nx) + 0.5) * CELL
    ys = CY - D / 2 + (np.arange(ny) + 0.5) * CELL
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    rng = np.random.default_rng(7)
    rag = rng.uniform(-0.35, 0.35, X.shape)
    rag = (rag + np.roll(rag, 1, 0) + np.roll(rag, 1, 1) + np.roll(rag, -1, 0)) / 4.0       # ragged, not noisy
    road = (Y + rag > ROAD[0]) & (Y + rag < ROAD[1]) & (np.abs(X) < W / 2 - 6)
    for lb in labels:                                                                       # a spur to every door
        if lb.get("door") is not None:
            road |= (np.abs(X - lb["door"]) + rag < 1.2) & (Y > ROAD[0]) & (Y < FRONT + 0.2)
    road |= (np.abs(X - HARBOUR_X) + rag < 1.6) & (Y > DOCK_Y - 0.5) & (Y < ROAD[0] + 0.5)       # ... and to the dock
    h = np.where(road, -CELL, 0.0)
    # the line-up's cobbled patch (level with the grass: the figures stand at z = 0)
    hx = (len(FIGURES) - 1) / 2.0 * LINE_GAP + 1.3
    plaza = (np.abs(X - LINE[0]) + rag < hx) & (np.abs(Y - (LINE[1] - 0.4)) + rag < 1.7)
    # the pond: banks of quarter-block shelves (0.6 m each) down to the water, then the bed falls away under it
    d = pond_depth(X, Y, rag)
    shelf = np.where(d < 0, 0.0, -CELL * np.minimum(np.ceil(d / 0.6), 4))
    deep = np.where(d > 3.0, -2.5, np.where(d > 2.4, -1.5, shelf))
    h = np.where(d > 0, np.minimum(h, deep), h)
    surf = np.where(road | plaza, 1, 0)
    surf = np.where(d > 0, np.where(h < WATER_Z - 0.01, 3, 2), surf)                       # 2 gravel shore, 3 stone bed
    return X, Y, h, surf


def scatter(items, foot, labels, road_xy):
    rng = np.random.default_rng(20261120)
    X, Y, road = road_xy

    def free(x, y, pad):
        if any(x0 - pad < x < x1 + pad and y0 - pad < y < y1 + pad for (x0, y0, x1, y1) in foot):
            return False
        if ROAD[0] - 1.0 - pad < y < ROAD[1] + 1.0 + pad:
            return False
        if any(lb.get("door") is not None and abs(x - lb["door"]) < 2.5 + pad and y < FRONT + 0.5 for lb in labels):
            return False
        if any(abs(x - lb["pos"][0]) < 3.0 and abs(y - lb["pos"][1]) < 1.5 for lb in labels):
            return False
        return abs(x) < W / 2 - 3 and CY - D / 2 + 3 < y < CY + D / 2 - 3

    # a tree line behind the row and round its ends, like the forest edge round the village
    back = max(y1 for (_x0, _y0, _x1, y1) in foot) + 4.0
    k = 0
    for i in range(600):
        if k >= 52:
            break
        x = rng.uniform(-W / 2 + 6, W / 2 - 6)
        y = rng.uniform(back, CY + D / 2 - 8) if rng.random() < 0.8 else rng.uniform(-24, back)
        if abs(x) < W / 2 - 14 and y < back:
            continue
        if not free(x, y, 4.0) or any(math.hypot(x - it["pos"][0], y - it["pos"][1]) < 6.0 for it in items if it["mesh"].endswith("_Trunk")):
            continue
        kind = "ABCD"[int(rng.integers(0, 4))]
        s = float(rng.uniform(0.85, 1.15))
        yaw = float(rng.integers(0, 4)) * 90.0
        for part in ("Trunk", "Leaves"):
            items.append(dict(mesh="SM_Tree2_%s_%s" % (kind, part), pos=[round(x, 2), round(y, 2), -0.15], yaw=yaw, scale=s, group="forest"))
        k += 1

    def sprinkle(count, meshes, gap, group, scale=(0.9, 1.2), pad=0.6):
        pts = []
        for _ in range(count * 40):
            if len(pts) >= count:
                break
            x, y = rng.uniform(-W / 2 + 3, W / 2 - 3), rng.uniform(CY - D / 2 + 3, CY + D / 2 - 3)
            if not free(x, y, pad) or any(math.hypot(x - a, y - b) < gap for a, b in pts):
                continue
            pts.append((x, y))
            items.append(dict(mesh=str(rng.choice(meshes)), pos=[round(x, 2), round(y, 2), 0.0], yaw=float(rng.uniform(0, 360)),
                              scale=float(rng.uniform(*scale)), group=group))

    sprinkle(40, ["SM_Bush_A", "SM_Bush_B", "SM_Bush_C"], 3.0, "plants", (0.8, 1.2), pad=1.5)
    sprinkle(14, ["SM_Rock_A", "SM_Rock_B", "SM_Rock_C"], 6.0, "rocks", (0.8, 1.1), pad=1.5)
    sprinkle(260, ["SM_Flowers_A", "SM_Flowers_B", "SM_Flowers_C", "SM_Flowers_D"], 1.2, "plants")
    sprinkle(520, ["SM_GrassTuft_A", "SM_GrassTuft_B", "SM_GrassTuft_C"], 0.7, "plants", (0.9, 1.5))
    # lanterns along the road, between the buildings
    doors = [lb for lb in labels if lb.get("door") is not None]
    for i, lb in enumerate(doors[:-1]):
        x = (lb["door"] + doors[i + 1]["door"]) / 2.0
        items.append(dict(mesh="SM_LanternPost", pos=[round(x, 2), ROAD[1] + 0.9, 0.0], yaw=0.0, scale=1.0, group="village"))


def build_ground(X, Y, h, road):
    import voxlib as V
    from voxlib import Vox, IDS
    V.reset_scene()
    nx, ny = X.shape
    nz0 = int(DEPTH / CELL)                                 # the field's top
    nz = nz0 + int(max(0.0, float(h.max())) / CELL)         # (room for the mine's mound)
    v = Vox(nx, ny, nz, CELL, origin=(nx / 2.0, ny / 2.0 - CY / CELL, nz0), name="flat", seed=5)
    top = np.round((h + DEPTH) / CELL).astype(np.int32)
    K = np.arange(nz, dtype=np.int32)[None, None, :]
    solid = K < top[:, :, None]
    depth = top[:, :, None] - 1 - K
    surf = np.choose(road, [IDS["grass"], IDS["cobble"], IDS["gravel"], IDS["stone"]]).astype(np.uint8)
    v.m[:] = np.where(solid, np.where(depth == 0, surf[:, :, None], IDS["dirt"]), 0).astype(np.uint8)
    tiles = V.split(v, "SM_Flat", 28.0)
    for ob in tiles:
        V.export_gltf(ob)
    with open(os.path.join(MESHES, "flat_tiles.json"), "w") as f:
        json.dump([o.name for o in tiles], f)
    # the pond's water: one layer of water voxels whose top is the water line, over the cells deeper than it
    wet = (road == 3) | ((road == 2) & (h < WATER_Z - 0.01))
    if wet.any():
        V.reset_scene()
        w = Vox(nx, ny, 1, CELL, origin=(nx / 2.0, ny / 2.0 - CY / CELL, 1.0 - WATER_Z / CELL), name="pond")
        w.m[:, :, 0] = np.where(wet, IDS["water"], 0).astype(np.uint8)
        V.export_gltf(V.join([w], "SM_FlatPond"), collision="none")
    return tiles


def main():
    global W
    layout, items, labels, foot, total, figures = plan()
    W = max(W, round(total + 24.0))
    X, Y, h, surf = field(labels)
    scatter(items, foot, labels, (X, Y, surf == 1))
    mid = 0.0
    out = dict(
        instances=items,
        labels=labels,
        spawn=dict(pos=[mid, (ROAD[0] + ROAD[1]) / 2.0, 0.0], yaw=90.0),
        camera=dict(target=[mid, 4.0, 2.0], az=-8.0, el=30.0, dist=max(60.0, total * 0.98), hfov=60.0, width=1600, height=900),
        ground=dict(w=W, d=D, cy=CY),
        figures=figures,
        water=dict(mesh="SM_FlatPond", z=WATER_Z),
    )
    with open(os.path.join(SRC, "flatlands.json"), "w") as f:
        json.dump(out, f, indent=1)
    print("flatlands: %d buildings over %.0f m, %d instances" % (len(BUILDINGS), total, len(items)))
    if "--plan-only" not in sys.argv:
        tiles = build_ground(X, Y, h, surf)
        print("flatlands ground: %d tiles" % len(tiles))


main()
