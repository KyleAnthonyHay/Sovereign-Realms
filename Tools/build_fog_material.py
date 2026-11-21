"""Builds /Game/SR/Materials/M_FogOfWar, the fog-of-war post-process (run inside the editor):

    python3 Tools/ue_py.py Tools/build_fog_material.py

USRFogSubsystem writes the fog grid into a transient texture (grey: 0 unexplored, 0.5 explored, 1 in sight) and sets
it as FogTex, with MapRect = (origin X, origin Y, size X, size Y) in cm. The material reconstructs each pixel's world
position from depth, samples the grid there and darkens: unexplored ground near black with a cold tint, explored
ground dimmed and greyed, ground in sight untouched. A slow drifting noise breaks the edges up so they read as mist
rather than a grid. Applied after tone mapping (on the final image).
"""
import unreal

DIR = "/Game/SR/Materials"
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
MP = unreal.MaterialProperty


def get_material(name):
    path = DIR + "/" + name
    if eal.does_asset_exist(path):
        mat = eal.load_asset(path)
        mel.delete_all_material_expressions(mat)
    else:
        mat = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, DIR, unreal.Material, unreal.MaterialFactoryNew())
    return mat


mat = get_material("M_FogOfWar")
mat.set_editor_property("material_domain", unreal.MaterialDomain.MD_POST_PROCESS)
mat.set_editor_property("blendable_location", unreal.BlendableLocation.BL_SCENE_COLOR_AFTER_TONEMAPPING)
n = [0]


def node(cls, **props):
    n[0] += 1
    e = mel.create_material_expression(mat, cls, -1400 + (n[0] % 5) * 280, -500 + (n[0] // 5) * 180)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


scene = node(unreal.MaterialExpressionSceneTexture, scene_texture_id=unreal.SceneTextureId.PPI_POST_PROCESS_INPUT0)
depth = node(unreal.MaterialExpressionSceneTexture, scene_texture_id=unreal.SceneTextureId.PPI_SCENE_DEPTH)
wp = node(unreal.MaterialExpressionWorldPosition)
white = eal.load_asset("/Engine/EngineResources/WhiteSquareTexture")
tex = node(unreal.MaterialExpressionTextureObjectParameter, parameter_name="FogTex", texture=white,
           sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
rect = node(unreal.MaterialExpressionVectorParameter, parameter_name="MapRect", default_value=unreal.LinearColor(-13500, -13500, 27000, 27000))
strength = node(unreal.MaterialExpressionScalarParameter, parameter_name="Strength", default_value=1.0)
time = node(unreal.MaterialExpressionTime)
# x, y: the distance (cm) over which the fog thins into the haze; z: how much of it goes; w: how much of it the sky takes
fade = node(unreal.MaterialExpressionVectorParameter, parameter_name="DistanceFade", default_value=unreal.LinearColor(26000, 90000, 0.7, 0.85))

code = r"""
float3 c = Scene.rgb;
bool sky = Depth.r > 2.0e6;      // the sky takes the fog of the map's edge under it (Fade.w of it), or it would stand pale over black land
float2 uv = (WP.xy - Rect.xy) / Rect.zw;
float2 drift = float2(sin(WP.y * 0.0021 + T * 0.13), cos(WP.x * 0.0017 - T * 0.11)) * 0.0022;  // mist, not a grid
// a small blur of the grid (bilinear taps a cell apart) so the edge is a soft mist, not stair-steps
float2 cell = 1.0 / 216.0;
float f = 0.0;
f += pow(saturate(Fog.SampleLevel(View.SharedBilinearClampedSampler, uv + drift, 0).r), 0.4545) * 0.36;
f += pow(saturate(Fog.SampleLevel(View.SharedBilinearClampedSampler, uv + drift + float2(cell.x, 0), 0).r), 0.4545) * 0.16;
f += pow(saturate(Fog.SampleLevel(View.SharedBilinearClampedSampler, uv + drift - float2(cell.x, 0), 0).r), 0.4545) * 0.16;
f += pow(saturate(Fog.SampleLevel(View.SharedBilinearClampedSampler, uv + drift + float2(0, cell.y), 0).r), 0.4545) * 0.16;
f += pow(saturate(Fog.SampleLevel(View.SharedBilinearClampedSampler, uv + drift - float2(0, cell.y), 0).r), 0.4545) * 0.16;   // stored sRGB
// (no edge to the fog: past the grid the nearest cell's state carries on, because the sampler clamps. It used to turn
// to "explored" there, which showed as a pale band and a grey wedge at the map's border from the shallow camera angles.)
float seen = smoothstep(0.0, 0.5, f);                            // 0 unexplored .. 1 explored
float lit = smoothstep(0.5, 1.0, f);                             // 0 out of sight .. 1 in sight
float l = dot(c, float3(0.3, 0.59, 0.11));
float3 grey = lerp(c, l.xxx * float3(0.85, 0.9, 1.0), 0.55);
float3 explored = grey * 0.55;
float3 unknown = l.xxx * float3(0.15, 0.16, 0.2) + float3(0.008, 0.009, 0.014);   // the land shows faintly
float3 o = lerp(unknown, explored, seen);
o = lerp(o, c, lit);
// and it thins into the haze with distance, so dark unexplored land never stands as a black cut-out against the sky
float far = smoothstep(Fade.x, Fade.y, Depth.r);
return lerp(c, o, saturate(S) * (sky ? Fade.w : 1.0 - Fade.z * far));
"""
custom = node(unreal.MaterialExpressionCustom, code=code, output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3, description="Fog of war")
ins = []
for name in ("Scene", "Depth", "WP", "Fog", "Rect", "S", "T", "Fade"):
    ci = unreal.CustomInput()
    ci.set_editor_property("input_name", name)
    ins.append(ci)
custom.set_editor_property("inputs", ins)
for name, src in (("Scene", scene), ("Depth", depth), ("WP", wp), ("Fog", tex), ("Rect", rect), ("S", strength), ("T", time), ("Fade", fade)):
    if not mel.connect_material_expressions(src, "RGBA" if src in (rect, fade) else "", custom, name):
        raise RuntimeError("connect failed " + name)
if not mel.connect_material_property(custom, "", MP.MP_EMISSIVE_COLOR):
    raise RuntimeError("output connect failed")
mel.layout_material_expressions(mat)
mel.recompile_material(mat)
eal.save_loaded_asset(mat, False)
print("built", mat.get_path_name())
