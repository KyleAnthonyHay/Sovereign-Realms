"""Builds /Game/SR/Materials/M_Occlusion, the troops' see-through silhouette (run inside the editor):

    python3 Tools/ue_py.py Tools/build_occlusion_material.py

Troop sprite cards render custom depth with the team in the stencil (1 player, 2 enemy; ASRUnit::BuildVisuals,
r.CustomDepth=3). Where a troop is hidden behind something nearer the camera (its custom depth lies well behind the scene
depth), this post-process tints the pixel toward the team colour with a fine 2x2 dither so the troop reads as
a silhouette through the wall. Added to the camera's blendables by USRFogSubsystem.
"""
import unreal

DIR = "/Game/SR/Materials"
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
MP = unreal.MaterialProperty

path = DIR + "/M_Occlusion"
if eal.does_asset_exist(path):
    mat = eal.load_asset(path)
    mel.delete_all_material_expressions(mat)
else:
    mat = unreal.AssetToolsHelpers.get_asset_tools().create_asset("M_Occlusion", DIR, unreal.Material, unreal.MaterialFactoryNew())
mat.set_editor_property("material_domain", unreal.MaterialDomain.MD_POST_PROCESS)
mat.set_editor_property("blendable_location", unreal.BlendableLocation.BL_SCENE_COLOR_AFTER_TONEMAPPING)
mat.set_editor_property("blendable_priority", 1)
n = [0]


def node(cls, **props):
    n[0] += 1
    e = mel.create_material_expression(mat, cls, -1400 + (n[0] % 5) * 280, -500 + (n[0] // 5) * 180)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


ST = unreal.SceneTextureId
scene = node(unreal.MaterialExpressionSceneTexture, scene_texture_id=ST.PPI_POST_PROCESS_INPUT0)
sdepth = node(unreal.MaterialExpressionSceneTexture, scene_texture_id=ST.PPI_SCENE_DEPTH)
cdepth = node(unreal.MaterialExpressionSceneTexture, scene_texture_id=ST.PPI_CUSTOM_DEPTH)
stencil = node(unreal.MaterialExpressionSceneTexture, scene_texture_id=ST.PPI_CUSTOM_STENCIL)
pix = node(unreal.MaterialExpressionScreenPosition)
pcol = node(unreal.MaterialExpressionVectorParameter, parameter_name="PlayerColor", default_value=unreal.LinearColor(0.35, 0.62, 1.0, 1.0))
ecol = node(unreal.MaterialExpressionVectorParameter, parameter_name="EnemyColor", default_value=unreal.LinearColor(1.0, 0.38, 0.3, 1.0))
amount = node(unreal.MaterialExpressionScalarParameter, parameter_name="Amount", default_value=0.6)

code = r"""
float3 c = Scene.rgb;
float cd = CD.r, sd = SD.r;
if (cd > 1.0e6 || cd < sd + 40.0) return c;              // no troop here, or nothing stands in front of it
float s = round(St.r);
float3 team = s > 1.5 ? E.rgb : P.rgb;
float2 p = floor(Pix.xy / 2.0);                            // a 2x2-pixel checker: reads as 'behind', not painted on
float chk = fmod(p.x + p.y, 2.0);
return lerp(c, team * (0.75 + 0.35 * chk), A);
"""
custom = node(unreal.MaterialExpressionCustom, code=code, output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3, description="Troop silhouette")
names = ("Scene", "SD", "CD", "St", "Pix", "P", "E", "A")
ins = []
for name in names:
    ci = unreal.CustomInput()
    ci.set_editor_property("input_name", name)
    ins.append(ci)
custom.set_editor_property("inputs", ins)
for name, src, out in (("Scene", scene, ""), ("SD", sdepth, ""), ("CD", cdepth, ""), ("St", stencil, ""), ("Pix", pix, "PixelPosition"),
                       ("P", pcol, "RGBA"), ("E", ecol, "RGBA"), ("A", amount, "")):
    if not mel.connect_material_expressions(src, out, custom, name):
        raise RuntimeError("connect failed " + name)
if not mel.connect_material_property(custom, "", MP.MP_EMISSIVE_COLOR):
    raise RuntimeError("output connect failed")
mel.layout_material_expressions(mat)
mel.recompile_material(mat)
eal.save_loaded_asset(mat, False)
print("built", mat.get_path_name())
