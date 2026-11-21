"""Chimney tops for the smoke (writes SourceArt/extras.json): for each listed building, the highest lump of stone/brick
that is narrow (a chimney, not a tower): Blender -b --factory-startup --python Tools/blender/find_chimneys.py"""
import json, os, sys
import bpy
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
MESHES = os.path.join(ROOT, "..", "SourceArt", "Meshes")
OUT = os.path.join(ROOT, "..", "SourceArt", "extras.json")
BUILDINGS = ["SM_TownHall", "SM_Barracks", "SM_FarmCottage_A", "SM_FarmCottage_B"]
extras = {}
for name in BUILDINGS:
    path = os.path.join(MESHES, name + ".gltf")
    if not os.path.exists(path):
        continue
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=path)
    ob = [o for o in bpy.data.objects if o.type == "MESH"][0]
    me = ob.data
    mw = np.array(ob.matrix_world)
    co = np.zeros(len(me.vertices) * 3, np.float32); me.vertices.foreach_get("co", co); co = co.reshape(-1, 3)
    co = co @ mw[:3, :3].T + mw[:3, 3]
    mat = np.zeros(len(me.polygons), np.int32); me.polygons.foreach_get("material_index", mat)
    stone = [i for i, m in enumerate(me.materials) if m and any(k in m.name for k in ("stone", "brick"))]
    tri = np.zeros(len(me.polygons) * 3, np.int32); me.polygons.foreach_get("vertices", tri); tri = tri.reshape(-1, 3)
    pts = co[tri[np.isin(mat, stone)].reshape(-1)]
    if len(pts) == 0:
        continue
    # 0.5 m columns of stone: top height and how tall the column of stone stands above the roofs around it
    cell = np.floor(pts[:, :2] / 0.5).astype(np.int64)
    tops = {}
    for (cx, cy), z in zip(map(tuple, cell), pts[:, 2]):
        tops[(cx, cy)] = max(tops.get((cx, cy), -1e9), z)
    allcell = np.floor(co[:, :2] / 0.5).astype(np.int64)
    alltop = {}
    for (cx, cy), z in zip(map(tuple, allcell), co[:, 2]):
        alltop[(cx, cy)] = max(alltop.get((cx, cy), -1e9), z)
    found = []
    for (cx, cy), z in sorted(tops.items(), key=lambda kv: -kv[1]):
        if z < alltop[(cx, cy)] - 0.05:
            continue                                       # something else is on top (a tower roof): not a chimney
        ring = [alltop.get((cx + dx, cy + dy), 0.0) for dx in (-3, 0, 3) for dy in (-3, 0, 3) if (dx, dy) != (0, 0)]
        if z - max(ring) > 0.6 and all(abs(cx - fx) + abs(cy - fy) > 4 for fx, fy, _ in found):
            found.append((cx, cy, z))
    smoke = [[round((cx + 0.5) * 0.5, 2), round((cy + 0.5) * 0.5, 2), round(float(z), 2)] for cx, cy, z in found[:2]]
    extras[name] = {"smoke": smoke}
    print(name, smoke)
with open(OUT, "w") as f:
    json.dump(extras, f, indent=1)
