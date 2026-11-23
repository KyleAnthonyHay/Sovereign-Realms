"""Gives Realm v2's ground tiles their further levels of detail (run inside the editor, not during PIE):

    python3 Tools/ue_py.py Tools/ue/realmv2_lods.py

From Tools/blender/assets/realmv2_terrain.py (import SM_RealmV2Ground_<i>_<j>_L1 and _L2 first: sh Tools/mac/realmv2_rebuild.sh
does): LOD 1 = _L1 (the same ground, its flat faces joined into quads of up to 1 m) from SWITCH[0] metres from the hero
camera, LOD 2 = _L2 (up to 4 m) from SWITCH[1]; the overview switches at 4/3 of these (as the trees: tree_lods.py).
The shape does not change at all (no coarse ground anywhere: the owner's rule); what goes is the block-to-block tint and
the corner shading. The _L1 / _L2 assets are deleted once they are inside the tiles (everything in /Game/Voxel is cooked).
Importing the tiles again drops their LODs: run this again afterwards.
"""
import json
import math
import os

import unreal

ROOT = os.path.abspath(unreal.Paths.project_dir())
MESH = "/Game/Voxel/Meshes/"
SWITCH = globals().get("SWITCH") or (110.0, 280.0)
FOV = 40.0
eal = unreal.EditorAssetLibrary
sms = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)


def size_at(mesh, metres):
    radius = mesh.get_bounds().sphere_radius / 100.0
    return min(0.95, radius / (metres * math.tan(math.radians(FOV / 2.0))))


tiles = json.load(open(os.path.join(ROOT, "SourceArt", "Meshes", "realmv2_tiles.json")))
done, missing, tri = 0, 0, [0, 0, 0]
with unreal.ScopedSlowTask(len(tiles), "Realm v2: the ground's levels of detail") as task:
    task.make_dialog(False)
    for name in tiles:
        task.enter_progress_frame(1)
        dst = eal.load_asset(MESH + name)
        srcs = [eal.load_asset(MESH + name + s) if eal.does_asset_exist(MESH + name + s) else None for s in ("_L1", "_L2")]
        if not dst or not all(srcs):
            missing += 1
            continue
        if sms.get_lod_count(dst) > 1:
            sms.remove_lods(dst)
        sizes = [1.0]
        for i, src in enumerate(srcs):
            sms.set_lod_from_static_mesh(dst, i + 1, src, 0, True)
            sizes.append(min(size_at(dst, SWITCH[i]), sizes[-1] * 0.9))
        sms.set_lod_screen_sizes(dst, sizes)
        eal.save_loaded_asset(dst, False)
        for i in range(3):
            tri[i] += dst.get_num_triangles(i)
        done += 1
gone = 0
for name in tiles:
    for s in ("_L1", "_L2"):
        if eal.does_asset_exist(MESH + name + s) and eal.delete_asset(MESH + name + s):
            gone += 1
print("realm v2 ground LODs: %d tiles (%d without their far meshes), triangles %.2f / %.2f / %.2f M, from %s m; %d far meshes deleted" % (
    done, missing, tri[0] / 1e6, tri[1] / 1e6, tri[2] / 1e6, " / ".join("%.0f" % v for v in SWITCH), gone))
