"""/Game/Voxel/Materials/M_PlacementGhost: the building being placed, drawn as glowing glass (run inside the editor):

    python3 Tools/ue_py.py Tools/ue/build_ghost_material.py

Translucent, unlit, emissive = Tint (a vector parameter: green where it fits, red where not), opacity = Opacity. The
game makes a dynamic instance of it and tints it each frame (UVLConstruction::UpdateGhost, VLConstruction.cpp); without
it the ghost keeps the building's own materials.
"""
import unreal

PATH, NAME = "/Game/Voxel/Materials", "M_PlacementGhost"
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
full = PATH + "/" + NAME
if eal.does_asset_exist(full):
    eal.delete_asset(full)
m = unreal.AssetToolsHelpers.get_asset_tools().create_asset(NAME, PATH, unreal.Material, unreal.MaterialFactoryNew())
m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
m.set_editor_property("two_sided", True)
tint = mel.create_material_expression(m, unreal.MaterialExpressionVectorParameter, -500, 0)
tint.set_editor_property("parameter_name", "Tint")
tint.set_editor_property("default_value", unreal.LinearColor(0.25, 1.0, 0.4, 1.0))
gain = mel.create_material_expression(m, unreal.MaterialExpressionMultiply, -250, 0)
gain.set_editor_property("const_b", 1.6)
mel.connect_material_expressions(tint, "", gain, "A")
mel.connect_material_property(gain, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
op = mel.create_material_expression(m, unreal.MaterialExpressionScalarParameter, -500, 200)
op.set_editor_property("parameter_name", "Opacity")
op.set_editor_property("default_value", 0.42)
mel.connect_material_property(op, "", unreal.MaterialProperty.MP_OPACITY)
mel.recompile_material(m)
eal.save_loaded_asset(m, False)
print("built", full)
