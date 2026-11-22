"""Gives the small plants a cheap far version (run inside the editor, not during PIE):

    python3 Tools/ue_py.py Tools/ue/plant_lods.py

SM_GrassTuft_*, SM_Flowers_*, SM_Bush_* get a LOD 1 made by the engine's mesh reduction (KEEP of the triangles), drawn
from where a plant is some SWITCH metres from the hero camera (40 degrees wide). At that distance a tuft is a few
pixels: only its colour and its size count. It is what lets the realm's forest (build_realm.CULL) draw its undergrowth
far out in the overview. Importing a plant again (import_assets.py) drops its LOD 1: run this again afterwards.
"""
import math

import unreal

MESH = "/Game/Voxel/Meshes/"
# (owner's rule, 2026-11-21: no simplified version where the player normally looks. These were 110 / 120 / 170 m, which
# the overview, switching at 4/3 of these, passed at its usual zoom for the bushes' lumpy far version)
PLANTS = {"SM_GrassTuft_A": 170.0, "SM_GrassTuft_B": 170.0, "SM_GrassTuft_C": 170.0, "SM_Flowers_A": 180.0, "SM_Flowers_B": 180.0,
          "SM_Flowers_C": 180.0, "SM_Flowers_D": 180.0, "SM_Bush_A": 260.0, "SM_Bush_B": 260.0, "SM_Bush_C": 260.0}    # SWITCH, metres
KEEP = 0.12
FOV = 40.0

eal = unreal.EditorAssetLibrary
sms = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
out = []
for name, switch in PLANTS.items():
    sm = eal.load_asset(MESH + name) if eal.does_asset_exist(MESH + name) else None
    if not sm:
        out.append(name + ": missing")
        continue
    if sms.get_lod_count(sm) > 1:
        sms.remove_lods(sm)
    size = min(0.9, sm.get_bounds().sphere_radius / 100.0 / (switch * math.tan(math.radians(FOV / 2.0))))
    opt = unreal.StaticMeshReductionOptions()
    opt.set_editor_property("auto_compute_lod_screen_size", False)
    opt.set_editor_property("reduction_settings", [unreal.StaticMeshReductionSettings(percent_triangles=1.0, screen_size=1.0),
                                                   unreal.StaticMeshReductionSettings(percent_triangles=KEEP, screen_size=size)])
    n = sms.set_lods(sm, opt)
    eal.save_loaded_asset(sm, False)
    out.append("%s: %d LODs, %d -> %d triangles, from screen size %.4f (%.0f m)" % (name, n, sm.get_num_triangles(0), sm.get_num_triangles(1) if n > 1 else -1, size, switch))
print("plant LODs:\n" + "\n".join(out))
