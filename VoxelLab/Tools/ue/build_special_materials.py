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


# A side's colour on a unit: with Mix 1 the GREEN cloth (hue about 50..170 degrees: the capes, cowls, hoods and tunic
# panels, olive to leaf green) turns to a rich red of like brightness, keeping its shading and its lighter and darker
# pieces. Everything else (skin, hair, leather, cream, the builder's navy and yellow, greys) is left as it is: gold
# and cream stop at hue 47. Expects `C` (float3) and `Mix`; leaves the result in `Sw`.
TEAM_SWAP = """
float3 Sw = C;
float mx = max(C.r, max(C.g, C.b)), mn = min(C.r, min(C.g, C.b)), dl = mx - mn;
if (Mix > 0.0 && dl > 1.0e-4)
{
    float h = (mx == C.g) ? 2.0 + (C.b - C.r) / dl : ((mx == C.r) ? (C.g - C.b) / dl : 4.0 + (C.r - C.g) / dl);
    h = frac(h / 6.0 + 1.0) * 360.0;
    float s = dl / mx;
    float w = smoothstep(48.0, 53.0, h) * (1.0 - smoothstep(160.0, 175.0, h)) * smoothstep(0.18, 0.32, s) * Mix;
    float h2 = frac((4.0 - (h - 80.0) * 0.15) / 360.0 + 1.0);          // the olive a touch warmer than the greens
    float3 k = saturate(abs(frac(h2 + float3(0.0, 2.0 / 3.0, 1.0 / 3.0)) * 6.0 - 3.0) - 1.0);
    float3 red = min(mx * TEAM_GAIN, 1.0) * lerp(float3(1.0, 1.0, 1.0), k, saturate(s * 1.1 + 0.08));
    Sw = lerp(C, red, w);
}
""".replace("TEAM_GAIN", "1.5")


def unit():
    """M_VoxUnit: M_Voxel for the units (the MI_King_<slot> instances, Tools/ue/import_king.py) plus the side's colour:
    "TeamMix" 1 turns the green cloth red (TEAM_SWAP). The enemy's units wear the twins MI_King_paint_Enemy and
    MI_King_sway_Enemy (AVLKing swaps them in by name). A parent of its own, so the world's M_Voxel pays nothing."""
    mat = get_material("M_VoxUnit")
    g = G(mat)
    tex = g.node(unreal.MaterialExpressionTextureSampleParameter2D, parameter_name="Tex", texture=eal.load_asset(TEX_DIR + "/T_Vox_paint"))
    vc = g.node(unreal.MaterialExpressionVertexColor)
    vrgb = g.node(unreal.MaterialExpressionComponentMask, r=True, g=True, b=True, a=False)
    g.link(vc, vrgb, "")
    team = g.custom(TEAM_SWAP + "return Sw;", CT.CMOT_FLOAT3, [("C", vrgb), ("Mix", g.scalar("TeamMix", 0.0))], "team colour")
    m1 = g.node(unreal.MaterialExpressionMultiply)
    g.link(tex, m1, "A", "RGB")
    g.link(team, m1, "B")
    m2 = g.node(unreal.MaterialExpressionMultiply)
    g.link(m1, m2, "A")
    g.link(g.node(unreal.MaterialExpressionVectorParameter, parameter_name="Tint", default_value=unreal.LinearColor(1, 1, 1, 1)), m2, "B")
    g.out(m2, MP.MP_BASE_COLOR)
    g.out(g.scalar("Roughness", 0.9), MP.MP_ROUGHNESS)
    g.out(g.scalar("Metallic", 0.0), MP.MP_METALLIC)
    g.out(g.scalar("Specular", 0.25), MP.MP_SPECULAR)
    em = g.node(unreal.MaterialExpressionMultiply)
    g.link(m2, em, "A")
    g.link(g.scalar("Emissive", 0.0), em, "B")
    g.out(em, MP.MP_EMISSIVE_COLOR)
    g.finish()
    # the units' instances that exist already move over to it (import_king.py parents new ones to it), and the two
    # with cloth get their enemy twin: a child instance, so it follows every other setting of its parent
    voxel = eal.load_asset(MAT_DIR + "/M_Voxel")
    n = 0
    for path in eal.list_assets(MAT_DIR, recursive=False):
        name = path.split("/")[-1].split(".")[0]
        if not name.startswith("MI_King_") or name.endswith("_Enemy") or name == "MI_KingDust":
            continue
        mi = eal.load_asset(MAT_DIR + "/" + name)
        if isinstance(mi, unreal.MaterialInstanceConstant) and mi.get_editor_property("parent") == voxel:
            mel.set_material_instance_parent(mi, mat)
            mel.update_material_instance(mi)
            eal.save_loaded_asset(mi, False)
            n += 1
    for key in ("paint", "sway"):
        base = eal.load_asset(MAT_DIR + "/MI_King_" + key) if eal.does_asset_exist(MAT_DIR + "/MI_King_" + key) else None
        if not base:
            continue
        name = "MI_King_" + key + "_Enemy"
        twin = eal.load_asset(MAT_DIR + "/" + name) if eal.does_asset_exist(MAT_DIR + "/" + name) else tools.create_asset(
            name, MAT_DIR, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        mel.set_material_instance_parent(twin, base)
        mel.set_material_instance_scalar_parameter_value(twin, "TeamMix", 1.0)
        if key == "sway":
            mel.set_material_instance_scalar_parameter_value(twin, "TeamHue", 1.0)
        mel.update_material_instance(twin)
        eal.save_loaded_asset(twin, False)
    print("M_VoxUnit built (%d unit instance(s) moved to it)" % n)


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
    # a side's colour: TeamMix 1 repaints the cloth in TeamTint, keeping its light and dark (MI_Vox_cloth_Enemy: red)
    base = m2
    # (TeamHue 1, the units' cloth, MI_King_sway_Enemy: only the green turns red, as in M_VoxUnit; the gold trim stays)
    m2 = g.custom("float3 C = Base;\n" + TEAM_SWAP + "if (Hue > 0.5) return Sw;\n"
                  "float l = saturate(dot(Base, float3(0.3, 0.59, 0.11)) * 3.0 + 0.12);\nreturn lerp(Base, l * Team.rgb, Mix);", CT.CMOT_FLOAT3,
                  [("Base", base), ("Team", g.node(unreal.MaterialExpressionVectorParameter, parameter_name="TeamTint", default_value=unreal.LinearColor(0.8, 0.06, 0.05, 1))),
                   ("Mix", g.scalar("TeamMix", 0.0)), ("Hue", g.scalar("TeamHue", 0.0))], "team colour")
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

    def instance(name, tex_name, use_alpha, height, amp, team=0.0, one_sided=False):
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
        mel.set_material_instance_scalar_parameter_value(mi, "TeamMix", team)
        # M_VoxSway is two-sided for the cloth (banners, flags, capes: thin sheets seen from both sides). The plants are
        # closed voxel blocks whose back faces are never seen: their instances draw one side only.
        bpo = mi.get_editor_property("base_property_overrides")
        bpo.set_editor_property("override_two_sided", one_sided)
        bpo.set_editor_property("two_sided", not one_sided)
        mi.set_editor_property("base_property_overrides", bpo)
        mel.update_material_instance(mi)
        eal.save_loaded_asset(mi, False)

    instance("MI_Vox_cloth", "T_Vox_cloth", 1.0, 60.0, 9.0)
    instance("MI_Vox_cloth_Enemy", "T_Vox_cloth", 1.0, 60.0, 9.0, team=1.0)        # the enemy's banners and flags (build_realm.py)
    # (height over which the sway builds up, amplitude in cm). Wheat leans well over in the gusts: it is tall and
    # thin and stands in fields, where the wind should be seen.
    WIND = {"wheat": (95.0, 17.0), "wheat_top": (95.0, 17.0)}
    for slot in ("leaves", "paint", "wheat", "wheat_top", "moss", "dirt", "grass"):
        height, amp = WIND.get(slot, (70.0, 5.0))
        instance("MI_Sway_" + slot, "T_Vox_" + slot, 0.0, height, amp, one_sided=True)
    print("M_VoxSway built")


SILHOUETTE = """
float3 c = Scene.rgb;
float cd = CD.r, sd = SD.r;
// Every unit writes custom depth, its side in the stencil (1 the player's, 2 the enemy's: AVLKing, VLTeamLook). The
// custom depth keeps the NEAREST unit, so: no unit here, or the nearest one is the enemy's (never shown through
// walls), or the nearest one is what is seen (nothing in front of it; a unit behind ANOTHER UNIT is behind this
// one, so troops do not bring the silhouette out, only trees, buildings and the ground do)
if (cd > 1.0e6 || abs(ST.r - 1.0) > 0.5 || cd < sd + 30.0) return c;
float2 p = floor(Pix.xy / 2.0);                             // a 2x2-pixel checker: reads as 'behind', not painted on
float chk = fmod(p.x + p.y, 2.0);
return lerp(c, Col.rgb * (0.72 + 0.4 * chk), A);
"""


def silhouette():
    """M_Silhouette (post-process): where one of the player's units (custom depth, stencil 1) is hidden behind a tree or
    a building, its shape shows through as a dithered gold silhouette; not behind another unit, and never the enemy's
    (stencil 2). Tools/ue/build_level.py adds it to the level's post-process volume."""
    mat = get_material("M_Silhouette")
    mat.set_editor_property("material_domain", unreal.MaterialDomain.MD_POST_PROCESS)
    mat.set_editor_property("blendable_location", unreal.BlendableLocation.BL_SCENE_COLOR_AFTER_TONEMAPPING)
    g = G(mat)
    ST = unreal.SceneTextureId
    c = g.custom(SILHOUETTE, CT.CMOT_FLOAT3,
                 [("Scene", g.node(unreal.MaterialExpressionSceneTexture, scene_texture_id=ST.PPI_POST_PROCESS_INPUT0)),
                  ("SD", g.node(unreal.MaterialExpressionSceneTexture, scene_texture_id=ST.PPI_SCENE_DEPTH)),
                  ("CD", g.node(unreal.MaterialExpressionSceneTexture, scene_texture_id=ST.PPI_CUSTOM_DEPTH)),
                  ("ST", g.node(unreal.MaterialExpressionSceneTexture, scene_texture_id=ST.PPI_CUSTOM_STENCIL)),
                  ("Pix", g.node(unreal.MaterialExpressionScreenPosition), "PixelPosition"),
                  ("Col", g.node(unreal.MaterialExpressionVectorParameter, parameter_name="Color", default_value=unreal.LinearColor(1.0, 0.78, 0.30, 1.0)), "RGBA"),
                  ("A", g.scalar("Amount", 0.62))], "hero silhouette")
    g.out(c, MP.MP_EMISSIVE_COLOR)
    g.finish()
    print("M_Silhouette built")


# The leaf wind is built but NOT switched on by default: moving every crown makes the shadow maps redraw all the trees
# each frame (about 4 ms). PARTS=["water", "leaves"] turns it on.
PARTS = globals().get("PARTS") or ["water", "sway", "unit", "silhouette"]
if "water" in PARTS:
    water()
if "leaves" in PARTS:
    leaves()
if "sway" in PARTS:
    sway()
if "unit" in PARTS:
    unit()                              # (after the sway: MI_King_sway_Enemy needs M_VoxSway's TeamHue)
if "silhouette" in PARTS:
    silhouette()
