"""The Flatlands: a flat field with every building side by side, for reviewing them and checking the look.

    Blender -b --factory-startup --python Tools/blender/assets/flatlands.py

Writes
  SourceArt/flatlands.json      the plan (same instance format as layout.json, plus name labels, the spawn, the camera)
  SM_Flat_<i>_<j>               the ground: quarter-block grass, a cobbled road sunk one step along the fronts,
                                a spur of it to every door (SourceArt/Meshes/flat_tiles.json lists the tiles)
Tools/ue/build_flatlands.py turns it into /Game/Maps/L_Flatlands.

The buildings stand at the size they have in the village (SourceArt/layout.json), fronts (-Y) on one line facing
the road, in the order of BUILDINGS.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import numpy as np

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
    (("SM_Bridge",), "Bridge", 0.0),
]
GAP = 7.0                 # metres between buildings
FRONT = -6.0              # the line the fronts stand on
ROAD = (-11.0, -8.0)      # the road along the fronts (y from, to)
CELL = 0.25
W, D = 196.0, 96.0        # the field
CY = 10.0                 # its middle in y
DEPTH = 1.0               # metres of ground


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
    widths = []
    chosen = [(built(meshes), title, door) for meshes, title, door in BUILDINGS]
    for mesh, title, door in chosen:
        (x0, y0, _), (x1, y1, _) = bounds(mesh)
        s = village_scale(layout, mesh)
        widths.append((x1 - x0) * s)
    total = sum(widths) + GAP * (len(widths) - 1)
    x = -total / 2.0
    for (mesh, title, door), w in zip(chosen, widths):
        (x0, y0, _), (x1, y1, z1) = bounds(mesh)
        s = village_scale(layout, mesh)
        cx = x - x0 * s
        cy = FRONT - y0 * s
        z = 0.04 if mesh == "SM_Bridge" else -0.01         # the underside of a floor just under the grass, not on it
        items.append(dict(mesh=mesh, pos=[round(cx, 3), round(cy, 3), z], yaw=0.0, scale=round(s, 3), group="buildings"))
        foot.append((x0 * s + cx, y0 * s + cy, x1 * s + cx, y1 * s + cy))
        # what the asset asks to have placed with it (dummies, wheat, sheep...): its own space, yaw 0 here
        for pr in meta(mesh).get("props", []):
            px, py, pz = pr["pos"]
            items.append(dict(mesh=pr["mesh"], pos=[round(cx + px * s, 3), round(cy + py * s, 3), round(pz * s, 3)],
                              yaw=float(pr.get("yaw", 0.0)), scale=round(float(pr.get("scale", 1.0)) * s, 3), group="props"))
        dx = cx + door * s
        labels.append(dict(text=title, pos=[round(dx, 2), ROAD[0] - 3.2, 0.0], door=round(dx, 2)))
        x += w + GAP
    if not any(it["mesh"] == "SM_TrainingDummy" for it in items):
        # the old barracks has no yard: dummies by the road in front of it, for the sword
        bx = [it for it in items if it["mesh"] == "SM_Barracks"][0]["pos"][0]
        for k, (ox, oy) in enumerate(((-3.0, -13.5), (0.0, -14.5), (3.0, -13.5))):
            items.append(dict(mesh="SM_TrainingDummy", pos=[bx + ox, oy, 0.0], yaw=float(180 + 15 * (k - 1)), scale=1.0, group="props"))
            foot.append((bx + ox - 0.8, oy - 0.8, bx + ox + 0.8, oy + 0.8))
    return layout, items, labels, foot, total


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
        road |= (np.abs(X - lb["door"]) + rag < 1.2) & (Y > ROAD[0]) & (Y < FRONT + 0.2)
    h = np.where(road, -CELL, 0.0)
    return X, Y, h, road


def scatter(items, foot, labels, road_xy):
    rng = np.random.default_rng(20261120)
    X, Y, road = road_xy

    def free(x, y, pad):
        if any(x0 - pad < x < x1 + pad and y0 - pad < y < y1 + pad for (x0, y0, x1, y1) in foot):
            return False
        if ROAD[0] - 1.0 - pad < y < ROAD[1] + 1.0 + pad:
            return False
        if any(abs(x - lb["door"]) < 2.5 + pad and y < FRONT + 0.5 for lb in labels):
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
    for i, lb in enumerate(labels[:-1]):
        x = (lb["door"] + labels[i + 1]["door"]) / 2.0
        items.append(dict(mesh="SM_LanternPost", pos=[round(x, 2), ROAD[1] + 0.9, 0.0], yaw=0.0, scale=1.0, group="village"))


def build_ground(X, Y, h, road):
    import voxlib as V
    from voxlib import Vox, IDS
    V.reset_scene()
    nx, ny = X.shape
    nz = int(DEPTH / CELL)
    v = Vox(nx, ny, nz, CELL, origin=(nx / 2.0, ny / 2.0 - CY / CELL, nz), name="flat", seed=5)
    top = np.round((h + DEPTH) / CELL).astype(np.int32)
    K = np.arange(nz, dtype=np.int32)[None, None, :]
    solid = K < top[:, :, None]
    depth = top[:, :, None] - 1 - K
    surf = np.where(road, IDS["cobble"], IDS["grass"]).astype(np.uint8)
    v.m[:] = np.where(solid, np.where(depth == 0, surf[:, :, None], IDS["dirt"]), 0).astype(np.uint8)
    tiles = V.split(v, "SM_Flat", 28.0)
    for ob in tiles:
        V.export_gltf(ob)
    with open(os.path.join(MESHES, "flat_tiles.json"), "w") as f:
        json.dump([o.name for o in tiles], f)
    return tiles


def main():
    layout, items, labels, foot, total = plan()
    X, Y, h, road = field(labels)
    scatter(items, foot, labels, (X, Y, road))
    mid = 0.0
    out = dict(
        instances=items,
        labels=labels,
        spawn=dict(pos=[mid, (ROAD[0] + ROAD[1]) / 2.0, 0.0], yaw=90.0),
        camera=dict(target=[mid, 4.0, 2.0], az=-8.0, el=30.0, dist=max(60.0, total * 0.98), hfov=60.0, width=1600, height=900),
        ground=dict(w=W, d=D, cy=CY),
    )
    with open(os.path.join(SRC, "flatlands.json"), "w") as f:
        json.dump(out, f, indent=1)
    print("flatlands: %d buildings over %.0f m, %d instances" % (len(BUILDINGS), total, len(items)))
    if "--plan-only" not in sys.argv:
        tiles = build_ground(X, Y, h, road)
        print("flatlands ground: %d tiles" % len(tiles))


main()
