"""Gives Realm v3's ground tiles their further levels of detail (run inside the editor, not during PIE):

    python3 Tools/ue_py.py Tools/ue/realmv3_lods.py

From Tools/blender/assets/realmv3_terrain.py (import SM_RealmV3Ground_<i>_<j>_L1 and _L2 first: sh Tools/mac/realmv3_rebuild.sh
does): LOD 1 = _L1 (the same ground, its flat faces joined into quads of up to 1 m) from SWITCH[0] metres from the hero
camera, LOD 2 = _L2 (up to 4 m) from SWITCH[1]; the overview switches at 4/3 of these (as the trees: tree_lods.py).
The shape does not change at all (no coarse ground anywhere: the owner's rule); what goes is the block-to-block tint and
the corner shading. The _L1 / _L2 assets are deleted once they are inside the tiles (everything in /Game/Voxel is cooked).
Importing the tiles again drops their LODs: run this again afterwards.
ONLY_COLLISION = True runs only the last step (which level of detail the tiles collide with: see there).
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


tiles = json.load(open(os.path.join(ROOT, "SourceArt", "Meshes", "realmv3_tiles.json")))
# ONLY_COLLISION = True: just the last step (the tiles have their levels of detail already, and the _L1 / _L2 meshes
# they were made from are gone).
if not globals().get("ONLY_COLLISION"):
    done, missing, tri = 0, 0, [0, 0, 0]
    with unreal.ScopedSlowTask(len(tiles), "Realm v3: the ground's levels of detail") as task:
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
    print("realm v3 ground LODs: %d tiles (%d without their far meshes), triangles %.2f / %.2f / %.2f M, from %s m; %d far meshes deleted" % (
        done, missing, tri[0] / 1e6, tri[1] / 1e6, tri[2] / 1e6, " / ".join("%.0f" % v for v in SWITCH), gone))

# ---- what the tiles collide with (Windows pass, batch 3: tried, measured, NOT taken; COLLISION_LOD stays 0).
# A tile collides with its own triangles (the footsteps read the material of the triangle hit, the path grid and the
# arrows trace against them). COLLISION_LOD = 2 makes it collide with those of its coarsest level of detail instead,
# the same shape in a third of the triangles (5.40 M faces -> 1.64 M). On Windows (387 tiles, packaged Development,
# 313 units) the units' movement cost the same within the noise (CharacterMovement 6.1 / 7.6 / 6.9 ms before, 5.8 /
# 7.4 / 8.0 after, at the three views), and the path grid was not the same grid: 1,096,156 nodes for 1,096,134 (21
# cells fewer "too tight", one fewer under water), every checksum different. So the tiles keep their own triangles.
COLLISION_LOD = globals().get("COLLISION_LOD", 0)
changed = 0
with unreal.ScopedSlowTask(len(tiles), "Realm v3: the ground's collision") as task:
    task.make_dialog(False)
    for name in tiles:
        task.enter_progress_frame(1)
        dst = eal.load_asset(MESH + name)
        if not dst:
            continue
        want = max(0, min(int(COLLISION_LOD), sms.get_lod_count(dst) - 1))
        if dst.get_editor_property("lod_for_collision") == want:
            continue
        dst.set_editor_property("lod_for_collision", want)
        body = dst.get_editor_property("body_setup")
        if body:
            # (set to what it is: the body's own change notice throws its cooked collision away, so that it is made
            # again from the level of detail now chosen)
            body.set_editor_property("collision_trace_flag", body.get_editor_property("collision_trace_flag"))
        eal.save_loaded_asset(dst, False)
        changed += 1
print("realm v3 ground collision: level of detail %d on %d tile(s) (%d in all)" % (COLLISION_LOD, changed, len(tiles)))
