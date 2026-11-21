"""M_VoxArrow: the material of arrows in flight and stuck in things (UVLArrows; run inside the editor):

    python3 Tools/ue_py.py Tools/ue/build_arrow_material.py

The arrow's colours are its vertex colours (as the archer's). It is masked and dithered by "Fade" (1 = there, 0 = gone),
which each arrow sets for itself through custom primitive data 0: one material, no instance per arrow.
"""
import unreal

MAT_DIR = "/Game/Voxel/Materials"
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
MP = unreal.MaterialProperty

path = MAT_DIR + "/M_VoxArrow"
if eal.does_asset_exist(path):
    mat = eal.load_asset(path)
    mel.delete_all_material_expressions(mat)
else:
    mat = tools.create_asset("M_VoxArrow", MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
vc = mel.create_material_expression(mat, unreal.MaterialExpressionVertexColor, -700, 0)
rough = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -700, 250)
rough.set_editor_property("r", 0.85)
fade = mel.create_material_expression(mat, unreal.MaterialExpressionScalarParameter, -900, 450)
fade.set_editor_property("parameter_name", "Fade")
fade.set_editor_property("default_value", 1.0)
fade.set_editor_property("use_custom_primitive_data", True)
fade.set_editor_property("primitive_data_index", 0)
mel.connect_material_property(vc, "", MP.MP_BASE_COLOR)
mel.connect_material_property(rough, "", MP.MP_ROUGHNESS)
ok = False
try:
    fn = unreal.load_asset("/Engine/Functions/Engine_MaterialFunctions02/Utility/DitherTemporalAA")
    call = mel.create_material_expression(mat, unreal.MaterialExpressionMaterialFunctionCall, -500, 450)
    call.set_material_function(fn)
    ok = mel.connect_material_expressions(fade, "", call, "Alpha Threshold") and mel.connect_material_property(call, "", MP.MP_OPACITY_MASK)
except Exception as e:
    print("dither:", e)
if not ok:
    print("no dither: the arrow is cut off when Fade passes the clip value instead")
    mel.connect_material_property(fade, "", MP.MP_OPACITY_MASK)
mel.recompile_material(mat)
eal.save_loaded_asset(mat, False)
print("M_VoxArrow built, dithered fade:", bool(ok))
