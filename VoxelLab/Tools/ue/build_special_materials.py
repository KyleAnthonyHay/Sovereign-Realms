"""The two materials that move (run inside the editor, after import_assets.py made the plain ones):

    python3 Tools/ue_py.py Tools/ue/build_special_materials.py

  M_VoxWater   the river: the pixel water texture drifting in whole-texel steps (so it stays pixel art), glints that
               come and go, white streaks running down the vertical faces (the fall), glossy enough to mirror the sky.
  M_VoxLeaves  M_Voxel plus a small wind: every leaf cube bobs on its own and the crown leans a little.
MI_Vox_water and MI_Vox_leaves are re-parented to them, so every mesh picks them up.
"""
import unreal

MAT_DIR = "/Game/Voxel/Materials"
TEX_DIR = "/Game/Voxel/Textures"
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
MP = unreal.MaterialProperty
CT = unreal.CustomMaterialOutputType


def get_material(name):
    path = MAT_DIR + "/" + name
    if eal.does_asset_exist(path):
        mat = eal.load_asset(path)
        mel.delete_all_material_expressions(mat)
    else:
        mat = tools.create_asset(name, MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
    return mat


class G:
    def __init__(self, mat):
        self.mat = mat
        self.n = 0

    def node(self, cls, **props):
        self.n += 1
        e = mel.create_material_expression(self.mat, cls, -1400 + (self.n % 5) * 260, -500 + (self.n // 5) * 180)
        for k, v in props.items():
            e.set_editor_property(k, v)
        return e

    def scalar(self, name, default):
        return self.node(unreal.MaterialExpressionScalarParameter, parameter_name=name, default_value=default)

    def link(self, src, dst, dst_in, src_out=""):
        if not mel.connect_material_expressions(src, src_out, dst, dst_in):
            raise RuntimeError("connect failed: %s -> %s.%s" % (src.get_name(), dst.get_name(), dst_in))

    def custom(self, code, out_type, inputs, desc, outputs=None):
        c = self.node(unreal.MaterialExpressionCustom, code=code, output_type=out_type, description=desc)
        if outputs:
            outs = []
            for name, typ in outputs:
                co = unreal.CustomOutput()
                co.set_editor_property("output_name", name)
                co.set_editor_property("output_type", typ)
                outs.append(co)
            c.set_editor_property("additional_outputs", outs)
        ins = []
        for item in inputs:
            ci = unreal.CustomInput()
            ci.set_editor_property("input_name", item[0])
            ins.append(ci)
        c.set_editor_property("inputs", ins)
        for item in inputs:
            self.link(item[1], c, item[0], item[2] if len(item) > 2 else "")
        return c

    def out(self, src, prop, src_out=""):
        if not mel.connect_material_property(src, src_out, prop):
            raise RuntimeError("output connect failed: %s" % prop)

    def finish(self):
        mel.layout_material_expressions(self.mat)
        mel.recompile_material(self.mat)
        eal.save_loaded_asset(self.mat, False)


def reparent(instance, mat):
    mi = eal.load_asset(MAT_DIR + "/" + instance)
    if mi:
        mel.set_material_instance_parent(mi, mat)
        mel.update_material_instance(mi)
        eal.save_loaded_asset(mi, False)


WATER = """
// UV0 is in texture repeats (64 texels = 4 m). Everything moves in whole texels.
float2 texel = float2(1.0 / 64.0, 1.0 / 64.0);
float up = abs(N.z);
float3 col;
if (up > 0.5)
{
    float2 a = UV + floor(T * Speed) * texel * float2(1.0, 0.0) + floor(T * Speed * 0.5) * texel * float2(0.0, 1.0);
    float2 b = UV * 0.5 - floor(T * Speed * 0.7) * texel * float2(0.0, 1.0) + float2(0.37, 0.11);
    float3 ca = Texture2DSample(Tex, TexSampler, a).rgb;
    float3 cb = Texture2DSample(Tex, TexSampler, b).rgb;
    col = lerp(ca, cb, 0.45);
    // glints: the brightest texels of the two layers flare when they meet
    float g = saturate((max(ca.b, cb.b) - 0.72) * 6.0) * saturate((ca.g + cb.g) - 1.05) * 3.0;
    col = lerp(col, float3(0.86, 0.95, 1.0), saturate(g));
    Glint = saturate(g);
}
else
{
    // a fall: streaks running down, mostly white
    float2 f = UV + float2(0.0, -floor(T * FallSpeed) * texel.y);
    float3 cf = Texture2DSample(Tex, TexSampler, float2(f.x, f.y * 0.25)).rgb;
    float streak = step(0.5, frac(UV.x * 32.0 + 0.25)) * 0.25 + cf.b;
    col = lerp(cf, float3(0.66, 0.84, 0.96), saturate(streak * 0.62));
    Glint = 0.05;
}
Rough = up > 0.5 ? TopRough : 0.5;
return col;
"""


def water():
    mat = get_material("M_VoxWater")
    g = G(mat)
    tex = g.node(unreal.MaterialExpressionTextureObjectParameter, parameter_name="Tex", texture=eal.load_asset(TEX_DIR + "/T_Vox_water"))
    uv = g.node(unreal.MaterialExpressionTextureCoordinate)
    t = g.node(unreal.MaterialExpressionTime)
    n = g.node(unreal.MaterialExpressionVertexNormalWS)
    c = g.custom(WATER, CT.CMOT_FLOAT3,
                 [("UV", uv), ("T", t), ("N", n), ("Tex", tex), ("Speed", g.scalar("Speed", 5.0)), ("FallSpeed", g.scalar("FallSpeed", 46.0)),
                  ("TopRough", g.scalar("Roughness", 0.16))],
                 "pixel water", outputs=[("Glint", CT.CMOT_FLOAT1), ("Rough", CT.CMOT_FLOAT1)])
    vc = g.node(unreal.MaterialExpressionVertexColor)
    tint = g.node(unreal.MaterialExpressionVectorParameter, parameter_name="Tint", default_value=unreal.LinearColor(0.82, 0.95, 1.0, 1))
    m1 = g.node(unreal.MaterialExpressionMultiply)
    g.link(c, m1, "A")
    g.link(vc, m1, "B")
    m2 = g.node(unreal.MaterialExpressionMultiply)
    g.link(m1, m2, "A")
    g.link(tint, m2, "B")
    g.out(m2, MP.MP_BASE_COLOR)
    g.out(c, MP.MP_ROUGHNESS, "Rough")
    em = g.node(unreal.MaterialExpressionMultiply)
    g.link(c, em, "A", "Glint")
    g.link(g.scalar("GlintGlow", 0.35), em, "B")
    g.out(em, MP.MP_EMISSIVE_COLOR)
    g.out(g.scalar("Specular", 0.6), MP.MP_SPECULAR)
    g.finish()
    reparent("MI_Vox_water", mat)
    print("M_VoxWater built")


LEAF_WIND = """
// every leaf cube (25 cm) bobs on its own phase; the whole crown leans with a slow gust
float3 cell = floor((P - N * 3.0) / 25.0);
float ph = frac(sin(dot(cell, float3(12.9898, 78.233, 37.719))) * 43758.5453) * 6.2832;
float bob = sin(T * 1.7 + ph) * Bob;
float gust = sin(T * 0.6 + (Pivot.x + Pivot.y) * 0.004) * 0.5 + sin(T * 1.13 + Pivot.y * 0.006) * 0.5;
float h = saturate((P.z - Pivot.z - 200.0) / 900.0);
return float3(1.0, 0.45, 0.0) * gust * h * Sway + float3(0.3, 0.2, 1.0) * bob;
"""


def leaves():
    mat = get_material("M_VoxLeaves")
    g = G(mat)
    tex = g.node(unreal.MaterialExpressionTextureSampleParameter2D, parameter_name="Tex", texture=eal.load_asset(TEX_DIR + "/T_Vox_leaves"))
    vc = g.node(unreal.MaterialExpressionVertexColor)
    tint = g.node(unreal.MaterialExpressionVectorParameter, parameter_name="Tint", default_value=unreal.LinearColor(1, 1, 1, 1))
    m1 = g.node(unreal.MaterialExpressionMultiply)
    g.link(tex, m1, "A", "RGB")
    g.link(vc, m1, "B")
    m2 = g.node(unreal.MaterialExpressionMultiply)
    g.link(m1, m2, "A")
    g.link(tint, m2, "B")
    g.out(m2, MP.MP_BASE_COLOR)
    g.out(g.scalar("Roughness", 0.9), MP.MP_ROUGHNESS)
    g.out(g.scalar("Specular", 0.2), MP.MP_SPECULAR)
    g.out(g.scalar("Metallic", 0.0), MP.MP_METALLIC)
    em = g.node(unreal.MaterialExpressionMultiply)
    g.link(m2, em, "A")
    g.link(g.scalar("Emissive", 0.0), em, "B")
    g.out(em, MP.MP_EMISSIVE_COLOR)
    wind = g.custom(LEAF_WIND, CT.CMOT_FLOAT3,
                    [("P", g.node(unreal.MaterialExpressionWorldPosition)), ("N", g.node(unreal.MaterialExpressionVertexNormalWS)),
                     ("T", g.node(unreal.MaterialExpressionTime)), ("Pivot", g.node(unreal.MaterialExpressionObjectPositionWS)),
                     ("Bob", g.scalar("Bob", 1.2)), ("Sway", g.scalar("Sway", 4.0))], "leaf wind")
    g.out(wind, MP.MP_WORLD_POSITION_OFFSET)
    g.finish()
    reparent("MI_Vox_leaves", mat)
    print("M_VoxLeaves built")


SWAY = """
// How much this corner moves: banners and flags carry it in the vertex colour's alpha (0 along the rod, 1 at the foot);
// plants sway more the higher they stand above their own root.
float3 rel = P - Pivot;
float plant = saturate(rel.z / max(Height, 1.0));
float w = lerp(plant * plant, Alpha, UseAlpha);
// a gust that travels across the village, and a faster flutter running through the cloth / along the stalks
float gust = sin(T * 1.1 + P.x * 0.0031 + P.y * 0.0043) * 0.6 + sin(T * 0.47 + P.y * 0.0019) * 0.4;
float flutter = sin(T * 3.4 + P.z * 0.045 + P.x * 0.03 + P.y * 0.021);
float push = (0.35 + 0.65 * (gust * 0.5 + 0.5)) * (0.55 + 0.45 * flutter) + 0.25 * gust;
return float3(Dir.x, Dir.y, 0.0) * push * w * Amp + float3(0.0, 0.0, -abs(push) * w * w * Amp * 0.18);
"""


def sway():
    """M_VoxSway: M_Voxel plus wind. MI_Vox_cloth (banners, flags) uses the vertex alpha; the plant instances
    MI_Sway_<slot> (grass, flowers, wheat: Tools/ue/import_assets.py assigns them) use height above the root."""
    mat = get_material("M_VoxSway")
    g = G(mat)
    tex = g.node(unreal.MaterialExpressionTextureSampleParameter2D, parameter_name="Tex", texture=eal.load_asset(TEX_DIR + "/T_Vox_paint"))
    vc = g.node(unreal.MaterialExpressionVertexColor)
    tint = g.node(unreal.MaterialExpressionVectorParameter, parameter_name="Tint", default_value=unreal.LinearColor(1, 1, 1, 1))
    m1 = g.node(unreal.MaterialExpressionMultiply)
    g.link(tex, m1, "A", "RGB")
    vrgb = g.node(unreal.MaterialExpressionComponentMask, r=True, g=True, b=True, a=False)   # the alpha is the sway weight
    g.link(vc, vrgb, "")
    g.link(vrgb, m1, "B")
    m2 = g.node(unreal.MaterialExpressionMultiply)
    g.link(m1, m2, "A")
    g.link(tint, m2, "B")
    g.out(m2, MP.MP_BASE_COLOR)
    g.out(g.scalar("Roughness", 0.9), MP.MP_ROUGHNESS)
    g.out(g.scalar("Specular", 0.2), MP.MP_SPECULAR)
    g.out(g.scalar("Metallic", 0.0), MP.MP_METALLIC)
    em = g.node(unreal.MaterialExpressionMultiply)
    g.link(m2, em, "A")
    g.link(g.scalar("Emissive", 0.0), em, "B")
    g.out(em, MP.MP_EMISSIVE_COLOR)
    wind = g.custom(SWAY, CT.CMOT_FLOAT3,
                    [("P", g.node(unreal.MaterialExpressionWorldPosition)), ("T", g.node(unreal.MaterialExpressionTime)),
                     ("Pivot", g.node(unreal.MaterialExpressionObjectPositionWS)), ("Alpha", vc, "A"),
                     ("UseAlpha", g.scalar("UseAlpha", 0.0)), ("Height", g.scalar("Height", 60.0)), ("Amp", g.scalar("Amp", 6.0)),
                     ("Dir", g.node(unreal.MaterialExpressionVectorParameter, parameter_name="WindDir", default_value=unreal.LinearColor(0.55, 0.83, 0, 0)))],
                    "wind sway")
    g.out(wind, MP.MP_WORLD_POSITION_OFFSET)
    mat.set_editor_property("two_sided", True)
    g.finish()

    def instance(name, tex_name, use_alpha, height, amp):
        path = MAT_DIR + "/" + name
        mi = eal.load_asset(path) if eal.does_asset_exist(path) else tools.create_asset(
            name, MAT_DIR, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        mel.set_material_instance_parent(mi, mat)
        t = eal.load_asset(TEX_DIR + "/" + tex_name)
        if t:
            mel.set_material_instance_texture_parameter_value(mi, "Tex", t)
        mel.set_material_instance_scalar_parameter_value(mi, "UseAlpha", use_alpha)
        mel.set_material_instance_scalar_parameter_value(mi, "Height", height)
        mel.set_material_instance_scalar_parameter_value(mi, "Amp", amp)
        mel.update_material_instance(mi)
        eal.save_loaded_asset(mi, False)

    instance("MI_Vox_cloth", "T_Vox_cloth", 1.0, 60.0, 9.0)
    # (height over which the sway builds up, amplitude in cm). Wheat leans well over in the gusts: it is tall and
    # thin and stands in fields, where the wind should be seen.
    WIND = {"wheat": (95.0, 17.0), "wheat_top": (95.0, 17.0)}
    for slot in ("leaves", "paint", "wheat", "wheat_top", "moss", "dirt", "grass"):
        height, amp = WIND.get(slot, (70.0, 5.0))
        instance("MI_Sway_" + slot, "T_Vox_" + slot, 0.0, height, amp)
    print("M_VoxSway built")


SILHOUETTE = """
float3 c = Scene.rgb;
float cd = CD.r, sd = SD.r;
if (cd > 1.0e6 || cd < sd + 30.0) return c;               // the hero is not here, or nothing stands in front of him
float2 p = floor(Pix.xy / 2.0);                             // a 2x2-pixel checker: reads as 'behind', not painted on
float chk = fmod(p.x + p.y, 2.0);
return lerp(c, Col.rgb * (0.72 + 0.4 * chk), A);
"""


def silhouette():
    """M_Silhouette (post-process): where the hero (custom depth) is hidden behind a tree or a building, his shape shows
    through as a dithered gold silhouette. Tools/ue/build_level.py adds it to the level's post-process volume."""
    mat = get_material("M_Silhouette")
    mat.set_editor_property("material_domain", unreal.MaterialDomain.MD_POST_PROCESS)
    mat.set_editor_property("blendable_location", unreal.BlendableLocation.BL_SCENE_COLOR_AFTER_TONEMAPPING)
    g = G(mat)
    ST = unreal.SceneTextureId
    c = g.custom(SILHOUETTE, CT.CMOT_FLOAT3,
                 [("Scene", g.node(unreal.MaterialExpressionSceneTexture, scene_texture_id=ST.PPI_POST_PROCESS_INPUT0)),
                  ("SD", g.node(unreal.MaterialExpressionSceneTexture, scene_texture_id=ST.PPI_SCENE_DEPTH)),
                  ("CD", g.node(unreal.MaterialExpressionSceneTexture, scene_texture_id=ST.PPI_CUSTOM_DEPTH)),
                  ("Pix", g.node(unreal.MaterialExpressionScreenPosition), "PixelPosition"),
                  ("Col", g.node(unreal.MaterialExpressionVectorParameter, parameter_name="Color", default_value=unreal.LinearColor(1.0, 0.78, 0.30, 1.0)), "RGBA"),
                  ("A", g.scalar("Amount", 0.62))], "hero silhouette")
    g.out(c, MP.MP_EMISSIVE_COLOR)
    g.finish()
    print("M_Silhouette built")


# The leaf wind is built but NOT switched on by default: moving every crown makes the shadow maps redraw all the trees
# each frame (about 4 ms). PARTS=["water", "leaves"] turns it on.
PARTS = globals().get("PARTS") or ["water", "sway", "silhouette"]
if "water" in PARTS:
    water()
if "leaves" in PARTS:
    leaves()
if "sway" in PARTS:
    sway()
if "silhouette" in PARTS:
    silhouette()
