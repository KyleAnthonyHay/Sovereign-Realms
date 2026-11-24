"""/Game/Voxel/Fog/M_FogOfWar: the fog of war's layer, a post-process material (run inside the editor):

    python Tools/ue_py.py Tools/ue/build_fog_material.py

UVLFog (VLFog.cpp) makes a dynamic instance of it on a post-process volume of its own and feeds it:
  Mask      the fog texture: R visible now, G explored (eased, one texel per fog cell)
  Heights   the terrain smoothed (R16F, cm): the fog's floor; its top is Layer over it
  Grid      (origin X, origin Y, 1 / size, 0): world XY to the textures' UV
  Layer, Density, ExploredDensity, Wisps, Bright, Desaturate, On, Steep, TopFeather, UnexploredDim (vl.Fog.* cvars)
The view ray is marched (10 steps, jittered per pixel) through the part of the layer in front of the pixel: the fog's
density there is Density where unexplored, ExploredDensity where explored, none where visible, ramping in over the top
5 m; the top rises and falls by Wisps in drifting noise. What stands above the layer (a watch tower's roof, the
mountain's peaks) is seen clear. Explored ground out of sight is greyed (Desaturate). Scene Color After DOF: at the
render resolution, before the upscaler.
"""
import unreal

PATH, NAME = "/Game/Voxel/Fog", "M_FogOfWar"
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
full = PATH + "/" + NAME
if not eal.does_directory_exist(PATH):
    eal.make_directory(PATH)
if eal.does_asset_exist(full):
    eal.delete_asset(full)
m = unreal.AssetToolsHelpers.get_asset_tools().create_asset(NAME, PATH, unreal.Material, unreal.MaterialFactoryNew())
m.set_editor_property("material_domain", unreal.MaterialDomain.MD_POST_PROCESS)
BL = unreal.BlendableLocation
loc = None
for n in ("BL_SCENE_COLOR_AFTER_DOF", "BL_AFTER_DOF", "BL_SCENE_COLOR_BEFORE_BLOOM"):
    if hasattr(BL, n):
        loc = getattr(BL, n)
        break
print("blendable location:", loc)
m.set_editor_property("blendable_location", loc)

CODE = r"""
float3 col = Scene.rgb;
if (On < 0.5) { return col; }
float3 V = WP - Cam;
float L = length(V);
if (L > 600000.0) { return col; }
float3 D = V / max(L, 1.0);
float2 org = Grid.xy;
float inv = Grid.z;
float2 uvP = (WP.xy - org) * inv;
float4 mP = Mask.SampleLevel(MaskSampler, uvP, 0);
float hP = Heights.SampleLevel(HeightsSampler, uvP, 0).r;
// drifting wisps: two octaves of value noise on the ground plane
float2 q = WP.xy * 0.0009 + float2(Time * 0.011, Time * 0.007);
float n = 0.0;
float amp = 0.65;
for (int o = 0; o < 2; o++)
{
    float2 i = floor(q);
    float2 f = frac(q);
    f = f * f * (3.0 - 2.0 * f);
    float a = frac(sin(dot(i, float2(127.1, 311.7))) * 43758.5453);
    float b = frac(sin(dot(i + float2(1.0, 0.0), float2(127.1, 311.7))) * 43758.5453);
    float c = frac(sin(dot(i + float2(0.0, 1.0), float2(127.1, 311.7))) * 43758.5453);
    float d = frac(sin(dot(i + float2(1.0, 1.0), float2(127.1, 311.7))) * 43758.5453);
    n += amp * lerp(lerp(a, b, f.x), lerp(c, d, f.x), f.y);
    q = q * 2.7 + float2(17.3, 9.1);
    amp *= 0.55;
}
float wob = Wisps * (n * 2.0 - 1.0);
// the stretch of the ray that can be in the layer: up to 150 m before the pixel, from where it comes down under the top
float topRef = hP + Layer + Wisps + 800.0;
float t0 = max(0.0, L - 15000.0);
if (D.z < -0.01) { t0 = max(t0, L - (topRef - WP.z) / (-D.z)); }
if (D.z < 0.0 && WP.z > topRef) { t0 = L; }
float tau = 0.0;
float lit = 0.0;
float ex = 0.0;
// the path through the layer already makes a grazing look denser than a look straight down; on top of that the
// density falls to Steep of itself from a look GrazeSin (sine of the angle below the horizontal) to one SteepSin:
// the hero's low look keeps the full bank, the overview's look down sees dim shapes through it. Wisps vary it.
float steepK = lerp(1.0, Steep, smoothstep(GrazeSin, SteepSin, abs(D.z))) * (0.6 + 0.8 * n);
if (t0 < L)
{
    const int N = 10;
    float dt = (L - t0) / N;
    float jit = frac(52.9829189 * frac(dot(Parameters.SvPosition.xy, float2(0.06711056, 0.00583715))) + Time * 0.61803);   // (interleaved gradient noise, a new phase each frame: the upscaler averages it)
    for (int s = 0; s < N; s++)
    {
        float t = t0 + (s + jit) * dt;
        float3 X = Cam + D * t;
        float2 uv = (X.xy - org) * inv;
        float4 m = Mask.SampleLevel(MaskSampler, uv, 0);
        float h = Heights.SampleLevel(HeightsSampler, uv, 0).r;
        float inside = h + Layer + wob - X.z;
        float dens = lerp(Density, ExploredDensity, m.g) * (1.0 - m.r) * smoothstep(0.0, 1.0, inside / TopFeather) * steepK;
        tau += dens * dt;
        lit += dens * dt * saturate(1.0 - inside / max(Layer, 1.0));
        ex += dens * dt * m.g;
    }
}
float T = exp(-tau);
float litF = tau > 1e-5 ? lit / tau : 0.0;
float exF = tau > 1e-5 ? ex / tau : 0.0;
// unexplored fog a deeper blue-grey, explored a lighter one; lit toward its top, shaded with the wisps
float3 fogC = lerp(DeepCol, FogCol, exF) * Bright * (0.62 + 0.38 * litF) * (0.84 + 0.32 * n);
// the ground under it: greyed where explored, greyed and dimmed where unexplored
float u = saturate(1.0 - max(mP.g, mP.r));
float g = saturate(max(saturate(mP.g - mP.r) * Desaturate, u * 0.7));
float lum = dot(col, float3(0.3, 0.59, 0.11));
col = lerp(col, lum * float3(0.86, 0.91, 1.0), g) * lerp(1.0, UnexploredDim, u);
return col * T + fogC * (1.0 - T);
"""

x = -1400


def node(cls, y, **props):
    global x
    e = mel.create_material_expression(m, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def scalar(name, value, y):
    return node(unreal.MaterialExpressionScalarParameter, y, parameter_name=name, default_value=value)


def lwc_free(src, y):
    """The LWC position as a plain float3 (a Custom node takes floats)."""
    cls = getattr(unreal, "MaterialExpressionTruncateLWC", None)
    if cls is None:
        return src
    t = mel.create_material_expression(m, cls, -1100, y)
    mel.connect_material_expressions(src, "", t, "")
    return t


custom = mel.create_material_expression(m, unreal.MaterialExpressionCustom, -400, 0)
custom.set_editor_property("code", CODE)
custom.set_editor_property("output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT3)
custom.set_editor_property("description", "FogOfWar")
names = ["Scene", "WP", "Cam", "Mask", "Heights", "Grid", "Layer", "Density", "ExploredDensity", "Wisps", "Bright", "Desaturate", "On", "Steep", "TopFeather",
         "UnexploredDim", "GrazeSin", "SteepSin", "Time", "FogCol", "DeepCol"]
ins = []
for nm in names:
    ci = unreal.CustomInput()
    ci.set_editor_property("input_name", nm)
    ins.append(ci)
custom.set_editor_property("inputs", ins)

scene = node(unreal.MaterialExpressionSceneTexture, -600, scene_texture_id=unreal.SceneTextureId.PPI_POST_PROCESS_INPUT0)
wp = node(unreal.MaterialExpressionWorldPosition, -500)
cam = node(unreal.MaterialExpressionCameraPositionWS, -400)
white = unreal.load_asset("/Engine/EngineResources/WhiteSquareTexture")
mask = node(unreal.MaterialExpressionTextureObjectParameter, -300, parameter_name="Mask", texture=white)
heights = node(unreal.MaterialExpressionTextureObjectParameter, -150, parameter_name="Heights", texture=white)
grid = node(unreal.MaterialExpressionVectorParameter, 0, parameter_name="Grid", default_value=unreal.LinearColor(-32000.0, -32000.0, 1.0 / 64000.0, 0.0))
fogcol = node(unreal.MaterialExpressionVectorParameter, 700, parameter_name="FogColor", default_value=unreal.LinearColor(0.66, 0.70, 0.76, 1.0))
deepcol = node(unreal.MaterialExpressionVectorParameter, 900, parameter_name="DeepColor", default_value=unreal.LinearColor(0.40, 0.45, 0.54, 1.0))
tm = node(unreal.MaterialExpressionTime, 800)
mel.connect_material_expressions(scene, "Color", custom, "Scene")
mel.connect_material_expressions(lwc_free(wp, -500), "", custom, "WP")
mel.connect_material_expressions(lwc_free(cam, -400), "", custom, "Cam")
mel.connect_material_expressions(mask, "", custom, "Mask")
mel.connect_material_expressions(heights, "", custom, "Heights")
mel.connect_material_expressions(grid, "", custom, "Grid")
y = 100
for nm, v in (("Layer", 1750.0), ("Density", 0.0016), ("ExploredDensity", 0.00035), ("Wisps", 350.0), ("Bright", 0.72), ("Desaturate", 0.45), ("On", 1.0),
              ("Steep", 0.12), ("TopFeather", 800.0), ("UnexploredDim", 0.6), ("GrazeSin", 0.1), ("SteepSin", 0.55)):
    mel.connect_material_expressions(scalar(nm, v, y), "", custom, nm)
    y += 80
mel.connect_material_expressions(tm, "", custom, "Time")
# the fog's colour made independent of the exposure where the engine has the node for it
ea = getattr(unreal, "MaterialExpressionEyeAdaptationInverse", None)
for src, pin, yy in ((fogcol, "FogCol", 700), (deepcol, "DeepCol", 900)):
    if ea is not None:
        inv = mel.create_material_expression(m, ea, -1100, yy)
        mel.connect_material_expressions(src, "", inv, "LightValue")
        mel.connect_material_expressions(inv, "", custom, pin)
    else:
        mel.connect_material_expressions(src, "", custom, pin)
print("fog colours through EyeAdaptationInverse" if ea is not None else "fog colours as they are")
mel.connect_material_property(custom, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
mel.recompile_material(m)
eal.save_loaded_asset(m, False)
try:
    print("compile errors:", [str(e) for e in m.get_editor_property("compile_errors")] if hasattr(m, "compile_errors") else "n/a")
except Exception as ex:
    print("compile errors: (not readable)", ex)
print("built", full)
