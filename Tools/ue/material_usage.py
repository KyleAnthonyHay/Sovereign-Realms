"""Usage flags the game's materials need for meshes the game makes at run time (run inside the editor, not during PIE):

    python3 Tools/ue_py.py Tools/ue/material_usage.py

M_Voxel and M_VoxSway are drawn on instanced static mesh components that only exist once a match runs: the chimney
smoke and the lantern motes (AVLAmbience: MI_Vox_smoke, MI_Vox_mote), a farm's wheat (UVLConstruction::SpawnProps:
MI_Sway_wheat, MI_Sway_wheat_top). The cook never sees those components, so nothing set "used with instanced static
meshes" for it, and a packaged build drew them with the default material ("missing usage flag InstancedStaticMeshes"
in its log). The level's own instanced meshes (the forest) get the flag while the cook loads the level; this makes it
part of the asset. Only the two materials are saved; their instances are not touched. The full builders
(import_assets.py, build_special_materials.py) set the same flag when they make the materials afresh.
"""
import unreal

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
done = []
for name in globals().get("MATERIALS") or ("M_Voxel", "M_VoxSway"):
    path = "/Game/Voxel/Materials/" + name
    if not eal.does_asset_exist(path):
        print("material_usage: no", path)
        continue
    mat = eal.load_asset(path)
    if mat.get_editor_property("used_with_instanced_static_meshes"):
        print("material_usage:", name, "has it already")
        continue
    mel.set_material_usage(mat, unreal.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES)
    mel.recompile_material(mat)
    eal.save_loaded_asset(mat, False)
    done.append(name)
print("material_usage: instanced static meshes on", ", ".join(done) if done else "nothing new")
