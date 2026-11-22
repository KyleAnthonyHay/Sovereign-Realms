"""Gives the tall trees their further levels of detail (run inside the editor, not during PIE):

    python3 Tools/ue_py.py Tools/ue/tree_lods.py

From Tools/blender/assets/tree_lods.py (import those first: PARTS=['meshes'], ONLY=[...the twelve names below]):
    SM_Tree2_<k>_Leaves   LOD 1 = _Leaves_L1 (the crown at its own 0.25 m scale, without the lace) from SWITCH1,
                          LOD 2 = _Leaves_L2 (half-metre cubes) from SWITCH2
    SM_Tree2_<k>_Trunk    LOD 1 = _Trunk_L2 (0.25 m voxels) from SWITCH2
A switch is where a tree is that many metres from the hero camera (40 degrees wide); the overview (30 degrees, the
engine's LODDistanceFactor 3 against the hero view's 2.25) switches at 4/3 of it. The engine measures it as the share
of the screen the mesh's bounding sphere takes.
Owner's rule (2026-11-21, References/Remake/lod_coarse_bad.png): no coarse version where the player normally looks.
SWITCH2 is where a half-metre cube is some 4 px of a 1600 px wide overview (373 m away, for a D): only
the overview pulled most of the way back draws it. SWITCH1 only drops the crown's 0.125 m lace, which is a pixel or
two from there.
Importing a tree again (import_assets.py) drops its LODs: run this again afterwards.
"""
import math

import unreal

MESH = "/Game/Voxel/Meshes/"
SWITCH1 = globals().get("SWITCH1") or {"A": 95.0, "B": 95.0, "C": 75.0, "D": 60.0}       # metres from the hero camera
SWITCH2 = globals().get("SWITCH2") or {"A": 320.0, "B": 320.0, "C": 280.0, "D": 280.0}
FOV = 40.0

eal = unreal.EditorAssetLibrary
sms = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
out = []


def size_at(mesh, metres):
    radius = mesh.get_bounds().sphere_radius / 100.0
    return min(0.9, radius / (metres * math.tan(math.radians(FOV / 2.0))))


for kind in "ABCD":
    for part, chain in (("Leaves", [("_L1", SWITCH1), ("_L2", SWITCH2)]), ("Trunk", [("_L2", SWITCH2)])):
        name = "SM_Tree2_%s_%s" % (kind, part)
        dst = eal.load_asset(MESH + name)
        srcs = [eal.load_asset(MESH + name + suffix) for (suffix, _sw) in chain]
        if not dst or not all(srcs):
            out.append("%s: missing%s" % (name, "" if dst else " (the tree)") + ("" if all(srcs) else " (a level: import it first)"))
            continue
        if sms.get_lod_count(dst) > 1:
            sms.remove_lods(dst)
        sizes = [1.0]
        for i, (src, (suffix, sw)) in enumerate(zip(srcs, chain)):
            sms.set_lod_from_static_mesh(dst, i + 1, src, 0, True)
            sizes.append(min(size_at(dst, sw[kind]), sizes[-1] * 0.95))
        sms.set_lod_screen_sizes(dst, sizes)
        eal.save_loaded_asset(dst, False)
        out.append("%s: %s triangles, from screen sizes %s (%s m)" % (
            name, " / ".join(str(dst.get_num_triangles(i)) for i in range(sms.get_lod_count(dst))),
            " / ".join("%.3f" % s for s in sizes[1:]), " / ".join("%.0f" % sw[kind] for (_s, sw) in chain)))
print("tree LODs:\n" + "\n".join(out))
