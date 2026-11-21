"""Gives the tall trees their second level of detail (run inside the editor, not during PIE):

    python3 Tools/ue_py.py Tools/ue/tree_lods.py

SM_Tree2_<A..D>_Trunk / _Leaves get LOD 1 from SM_Tree2_<..>_L1 (Tools/blender/assets/tree_lods.py; import those
first: PARTS=['meshes'], ONLY=[...the eight _L1 names]). The switch is where a tree is some SWITCH metres from the
hero camera (40 degrees wide): the engine measures it as the share of the screen the mesh's bounding sphere takes.
Importing a tree again (import_assets.py) drops its LOD 1: run this again afterwards.
"""
import math

import unreal

MESH = "/Game/Voxel/Meshes/"
SWITCH = globals().get("SWITCH") or {"A": 75.0, "B": 75.0, "C": 58.0, "D": 46.0}       # metres from the hero camera
FOV = 40.0

eal = unreal.EditorAssetLibrary
sms = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
out = []
for kind in "ABCD":
    for part in ("Trunk", "Leaves"):
        name = "SM_Tree2_%s_%s" % (kind, part)
        dst, src = eal.load_asset(MESH + name), eal.load_asset(MESH + name + "_L1")
        if not dst or not src:
            out.append("%s: missing%s" % (name, "" if dst else " (the tree)") + ("" if src else " (its _L1: import it first)"))
            continue
        if sms.get_lod_count(dst) > 1:
            sms.remove_lods(dst)
        index = sms.set_lod_from_static_mesh(dst, 1, src, 0, True)
        radius = dst.get_bounds().sphere_radius / 100.0
        size = min(0.9, radius / (SWITCH[kind] * math.tan(math.radians(FOV / 2.0))))
        sms.set_lod_screen_sizes(dst, [1.0, size])
        eal.save_loaded_asset(dst, False)
        out.append("%s: LOD %d, %d -> %d triangles, from screen size %.3f (%.0f m), %d material slots" % (
            name, index, dst.get_num_triangles(0), dst.get_num_triangles(1), size, SWITCH[kind], len(dst.get_editor_property("static_materials"))))
print("tree LODs:\n" + "\n".join(out))
