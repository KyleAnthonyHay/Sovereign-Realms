"""Builds (or rebuilds in place) the procedural materials under /Game/SR/Materials.

Run inside the editor:  Tools/ue_py.py Tools/build_visual_materials.py
Everything is procedural (world-aligned hashes in Custom nodes), so there are no textures.
Re-running keeps asset references intact: graphs are cleared and rebuilt.
See Docs/VISUAL_CONTRACT.md for the parameter contract.
"""
import unreal

DIR = "/Game/SR/Materials"
mel = unreal.MaterialEditingLibrary
eal = unreal.EditorAssetLibrary
MP = unreal.MaterialProperty


def lin(r, g, b, a=1.0):
    return unreal.LinearColor(r, g, b, a)


def srgb(hex_str):
    """'#rrggbb' as painted on screen -> linear."""
    h = hex_str.lstrip("#")
    def f(i):
        c = int(h[i:i + 2], 16) / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return lin(f(0), f(2), f(4))


def get_material(name):
    path = DIR + "/" + name
    if eal.does_asset_exist(path):
        mat = eal.load_asset(path)
        mel.delete_all_material_expressions(mat)
    else:
        mat = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, DIR, unreal.Material, unreal.MaterialFactoryNew())
    return mat


class G:
    """Tiny graph builder."""

    def __init__(self, mat):
        self.mat = mat
        self.n = 0

    def node(self, cls, **props):
        self.n += 1
        e = mel.create_material_expression(self.mat, cls, -1600 + (self.n % 6) * 260, -600 + (self.n // 6) * 170)
        for k, v in props.items():
            e.set_editor_property(k, v)
        return e

    def scalar(self, name, default, group="SR"):
        return self.node(unreal.MaterialExpressionScalarParameter, parameter_name=name, default_value=default, group=group)

    def vector(self, name, default, group="SR"):
        return self.node(unreal.MaterialExpressionVectorParameter, parameter_name=name, default_value=default, group=group)

    def const(self, v):
        return self.node(unreal.MaterialExpressionConstant, r=v)

    def const3(self, r, g, b):
        return self.node(unreal.MaterialExpressionConstant3Vector, constant=lin(r, g, b))

    def link(self, src, dst, dst_in, src_out=""):
        ok = mel.connect_material_expressions(src, src_out, dst, dst_in)
        if not ok:
            raise RuntimeError("connect failed: %s -> %s.%s" % (src.get_name(), dst.get_name(), dst_in))

    def custom(self, code, out_type, inputs, desc):
        """inputs: list of (name, expression) or (name, expression, output_name)."""
        c = self.node(unreal.MaterialExpressionCustom, code=code, output_type=out_type, description=desc)
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
        print("built", self.mat.get_path_name())


F1 = unreal.CustomMaterialOutputType.CMOT_FLOAT1
F3 = unreal.CustomMaterialOutputType.CMOT_FLOAT3


# ----------------------------------------------------------------------------- units
def build_unit():
    mat = get_material("M_UnitGreybox")
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
    mat.set_editor_property("two_sided", False)
    mat.set_editor_property("dithered_lod_transition", False)
    g = G(mat)
    color = g.vector("Color", lin(0.5, 0.5, 0.5), "Contract")
    team = g.vector("TeamColor", lin(0.05, 0.22, 0.8), "Contract")
    flash = g.scalar("HitFlash", 0.0, "Contract")
    fade = g.scalar("Fade", 1.0, "Contract")
    flash_col = g.vector("HitFlashColor", lin(1.0, 0.9, 0.75), "Look")
    flash_glow = g.scalar("HitFlashGlow", 2.2, "Look")
    rim = g.scalar("RimStrength", 0.55, "Look")
    rim_exp = g.scalar("RimExponent", 2.6, "Look")
    lift = g.scalar("ShadowLift", 0.07, "Look")
    sat = g.scalar("PaintSaturation", 1.15, "Look")
    rough = g.scalar("Roughness", 0.62, "Look")
    fres = g.node(unreal.MaterialExpressionFresnel, base_reflect_fraction=0.0)
    g.link(rim_exp, fres, "ExponentIn")

    base = g.custom(
        "float3 c = Color;\n"
        "float l = dot(c, float3(0.3, 0.59, 0.11));\n"
        "c = max(lerp(float3(l, l, l), c, Sat), 0.0);\n"   # slightly over-saturated, like model paint
        "return lerp(c, FlashCol, saturate(Flash) * 0.85);",
        F3, [("Color", color), ("Sat", sat), ("FlashCol", flash_col), ("Flash", flash)], "Unit base colour")

    emis = g.custom(
        "float3 rimCol = lerp(Color, Team, 0.55) + 0.04;\n"          # team-tinted rim so the faction reads on every part
        "float3 e = rimCol * Fres * Rim + Color * Lift;\n"           # ShadowLift keeps units readable inside cast shadows
        "return e + FlashCol * saturate(Flash) * Glow;",              # the hit flash itself: must be obvious for 0.16 s
        F3, [("Color", color), ("Team", team), ("Fres", fres), ("Rim", rim), ("Lift", lift),
             ("FlashCol", flash_col), ("Flash", flash), ("Glow", flash_glow)], "Unit rim + flash")

    mask = g.custom(
        "float n = InterleavedGradientNoise(Parameters.SvPosition.xy, View.StateFrameIndexMod8);\n"
        "return (Fade > n * 0.98 + 0.01) ? 1.0 : 0.0;",              # dithered death fade; stays in the opaque pass
        F1, [("Fade", fade)], "Dither fade")

    g.out(base, MP.MP_BASE_COLOR)
    g.out(emis, MP.MP_EMISSIVE_COLOR)
    g.out(mask, MP.MP_OPACITY_MASK)
    g.out(rough, MP.MP_ROUGHNESS)
    g.out(g.const(0.3), MP.MP_SPECULAR)
    g.finish()


# ----------------------------------------------------------------------------- rings
def build_ring():
    mat = get_material("M_SelectionRing")
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    mat.set_editor_property("two_sided", True)
    g = G(mat)
    color = g.vector("Color", lin(0.25, 1.0, 0.35), "Contract")
    opacity = g.scalar("Opacity", 1.0, "Contract")
    glow = g.scalar("Glow", 2.2, "Look")
    edge = g.scalar("DarkEdge", 0.55, "Look")
    uv = g.node(unreal.MaterialExpressionTextureCoordinate)

    # r = 1 at the ring's outer edge. A bright core with a thin dark outer lip reads on grass, dirt and stone.
    rgb = g.custom(
        "float r = length(UV - 0.5) * 2.0;\n"
        "float lip = smoothstep(0.90, 0.97, r);\n"
        "return lerp(Color * Glow, Color * 0.06, lip * Edge);",
        F3, [("UV", uv), ("Color", color), ("Glow", glow), ("Edge", edge)], "Ring colour")
    a = g.custom(
        "float r = length(UV - 0.5) * 2.0;\n"
        "float aa = max(fwidth(r), 0.002);\n"
        "return saturate(Opacity) * saturate((1.0 - r) / aa);",       # anti-aliased outer edge
        F1, [("UV", uv), ("Opacity", opacity)], "Ring alpha")
    g.out(rgb, MP.MP_EMISSIVE_COLOR)
    g.out(a, MP.MP_OPACITY)
    g.finish()


# ----------------------------------------------------------------------------- terrain
TERRAIN_CODE = r"""
struct SRT
{
	float h(float2 p) { float3 p3 = frac(float3(p.xyx) * 0.1031); p3 += dot(p3, p3.yzx + 33.33); return frac((p3.x + p3.y) * p3.z); }
	float vn(float2 p) { float2 i = floor(p); float2 f = frac(p); f = f * f * (3.0 - 2.0 * f);
		return lerp(lerp(h(i), h(i + float2(1, 0)), f.x), lerp(h(i + float2(0, 1)), h(i + float2(1, 1)), f.x), f.y); }
};
SRT f;
float T = max(Texel, 0.5);
float3 c = floor(P / T + 0.001);                 // texel coordinates: everything below is constant per texel
float hx = f.h(c.xy + c.z * 17.0);
float2 w = c.xy * T;
float nBig = f.vn(w / 520.0) * 0.65 + f.vn(w / 170.0 + 31.7) * 0.35;
float nMid = f.vn(w / 60.0 + 7.3);

// ---- grass: three posterised greens in soft clumps, plus sparse dry blades (2 texels tall)
float nSmall = f.vn(w / 13.0 + 3.1);
float gv = nBig * 0.50 + nMid * 0.26 + nSmall * 0.30 + hx * 0.10 - 0.08;
float3 grass = gv < 0.36 ? GrassDark : (gv < 0.63 ? GrassMid : GrassLight);
float blade = f.h(float2(c.x, floor(c.y * 0.5)) + 91.0);
if (blade > 0.91 && nBig > 0.42) grass = lerp(grass, GrassDry, 0.75);

// ---- dirt: a meandering track along X plus worn patches; ragged, dithered edges
float ph = w.x / max(Path.y, 1.0) * 6.2832;
float centre = Path.w + Path.x * sin(ph) + Path.x * 0.3 * sin(ph * 2.7 + 1.3);
float d = abs(w.y - centre) + (nMid - 0.5) * Path.z * 1.1 + (hx - 0.5) * Path.z * 0.45;
float pathM = (d < Path.z && P.z < PathMaxZ) ? 1.0 : 0.0;
float worn = f.vn(w / 300.0 + 77.1) * 0.6 + nMid * 0.3 + hx * 0.12;
float patchM = (worn > DirtPatches && P.z < PathMaxZ) ? 1.0 : 0.0;
float3 dirt = (f.vn(w / 11.0 + 9.4) * 0.8 + hx * 0.2 + nMid * 0.3) > 0.68 ? DirtLight : DirtDark;
if (f.h(floor(c.xy * 0.5) + 5.5) > 0.945) dirt = Pebble;
if (d > Path.z * 0.72 && pathM > 0.5 && hx > 0.4) dirt = DirtDark * 0.8;
float3 top = lerp(grass, dirt, max(pathM, patchM));

// ---- stone courses for the sides: offset blocks, dark joints, the odd earthy block
float ua = abs(N.x) > abs(N.y) ? c.y : c.x;
float R = max(Course, 2.0);
float zj = c.z + floor(f.h(float2(floor(ua / 9.0), 1.3)) * 3.0);   // courses step up and down: rock, not masonry
float row = floor(zj / R);
float rh = f.h(float2(row, 3.7));
float W = floor(lerp(R * 1.5, R * 3.6, rh));
float uo = ua + floor(rh * 37.0);
float col = floor(uo / W);
float bid = f.h(float2(col, row * 1.37 + 11.0));
float3 stone = bid < 0.34 ? StoneDark : (bid < 0.76 ? StoneMid : StoneLight);
if (bid > 0.9) stone = lerp(stone, Earth, 0.65);
stone *= 0.9 + 0.2 * hx;
if ((zj - row * R) < 1.0 || (uo - col * W) < 1.0) stone = StoneDark * Joint;

float3 side;
if (RockTop > 0.5)
{
	// boulders: bare stone with moss creeping over the top and down the upper courses
	float moss = nMid * 0.7 + hx * 0.45;
	top = moss < Moss ? grass : (hx > 0.5 ? StoneLight : StoneMid) * (0.92 + 0.16 * hx);
	float td = TopDist / T;
	side = (td < 2.0 + 5.0 * f.h(float2(ua, 7.7)) * Moss && moss < Moss + 0.15) ? GrassDark : stone;
}
else
{
	// terraces: turf hanging over the lip, then a ragged band of earth, then stone
	float td = TopDist / T;
	float c1 = f.h(float2(ua, 7.7));
	float c2 = f.h(float2(floor(ua / 3.0), 2.2));
	float turf = 1.0 + floor(c1 * 2.6) + floor(c2 * 2.0);
	float soil = turf + SoilDepth + floor(c2 * 4.0) + floor(c1 * 1.5);
	side = td < turf ? (hx > 0.45 ? GrassDark : GrassMid * 0.8) : (td < soil ? Earth * (0.8 + 0.4 * hx) : stone);
}
return N.z > 0.6 ? top : side;
"""


def build_terrain():
    mat = get_material("M_Terrain")
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE)
    g = G(mat)
    P = g.node(unreal.MaterialExpressionWorldPosition)
    N = g.node(unreal.MaterialExpressionVertexNormalWS)

    # World distance from this pixel down from the top of the mesh. Engine basic shapes span local Z -50..50.
    up_ws = g.node(unreal.MaterialExpressionTransform,
                   transform_source_type=unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_LOCAL,
                   transform_type=unreal.MaterialVectorCoordTransform.TRANSFORM_WORLD)
    g.link(g.const3(0.0, 0.0, 1.0), up_ws, "")
    top_dist_v = g.custom("return (50.0 - LP.z) * length(Up);", F1,
                          [("LP", g.node(unreal.MaterialExpressionPreSkinnedPosition)), ("Up", up_ws)], "Depth below top")
    top_dist = g.node(unreal.MaterialExpressionVertexInterpolator)
    g.link(top_dist_v, top_dist, "VS")

    params = [
        ("P", P), ("N", N), ("TopDist", top_dist),
        ("Texel", g.scalar("TexelSize", 3.5, "Crunch")),
        ("Course", g.scalar("StoneCourseTexels", 6.0, "Crunch")),
        ("GrassDark", g.vector("GrassDark", srgb("#4a5a2a"), "Grass")),
        ("GrassMid", g.vector("GrassMid", srgb("#667a33"), "Grass")),
        ("GrassLight", g.vector("GrassLight", srgb("#86923f"), "Grass")),
        ("GrassDry", g.vector("GrassDry", srgb("#b9a857"), "Grass")),
        ("DirtDark", g.vector("DirtDark", srgb("#6e5639"), "Dirt")),
        ("DirtLight", g.vector("DirtLight", srgb("#927550"), "Dirt")),
        ("Pebble", g.vector("Pebble", srgb("#93876f"), "Dirt")),
        ("Earth", g.vector("Earth", srgb("#5c4630"), "Dirt")),
        ("StoneDark", g.vector("StoneDark", srgb("#5d584c"), "Stone")),
        ("StoneMid", g.vector("StoneMid", srgb("#857d6a"), "Stone")),
        ("StoneLight", g.vector("StoneLight", srgb("#9a8f78"), "Stone")),
        # Path: X = meander amplitude, Y = wavelength, Z = half width, W = centre Y (all cm)
        ("Path", g.vector("Path", lin(380.0, 5200.0, 150.0, 60.0), "Dirt"), "RGBA"),
        ("PathMaxZ", g.scalar("PathMaxZ", 20.0, "Dirt")),
        ("DirtPatches", g.scalar("DirtPatchThreshold", 0.80, "Dirt")),
        ("SoilDepth", g.scalar("SoilDepthTexels", 5.0, "Dirt")),
        ("Joint", g.scalar("JointBrightness", 0.76, "Stone")),
        ("RockTop", g.scalar("RockTop", 0.0, "Rock")),
        ("Moss", g.scalar("Moss", 0.45, "Rock")),
    ]
    colour = g.custom(TERRAIN_CODE, F3, params, "Terrain colour (top / side by normal)")
    g.out(colour, MP.MP_BASE_COLOR)
    g.out(g.scalar("Roughness", 0.92, "Surface"), MP.MP_ROUGHNESS)
    g.out(g.scalar("Specular", 0.18, "Surface"), MP.MP_SPECULAR)
    g.finish()
    return mat


# ----------------------------------------------------------------------------- foliage
FOLIAGE_CODE = r"""
struct SRF { float h(float3 p) { p = frac(p * 0.1031); p += dot(p, p.zyx + 31.32); return frac((p.x + p.y) * p.z); } };
SRF f;
float T = max(Texel, 0.5);
float3 c = floor(P / T + 0.001);
float hx = f.h(c);
float needle = fmod(abs(c.z), 2.0) < 1.0 ? 0.0 : 1.0;          // alternating rows read as layered boughs
float v = (1.0 - saturate(LZ)) * 0.62 + hx * 0.42 + needle * 0.10 + (Rand - 0.5) * 0.22;
float3 col = v < 0.40 ? Dark : (v < 0.74 ? Mid : Light);       // skirt of each tier catches light, the top sits in shade
if (hx > 0.95) col = Tip;
return col * (0.88 + 0.24 * Rand);
"""


def build_foliage():
    mat = get_material("M_Foliage")
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE)
    mel.set_base_material_usage(mat, unreal.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES)
    g = G(mat)
    P = g.node(unreal.MaterialExpressionWorldPosition, world_position_shader_offset=unreal.WorldPositionIncludedOffsets.WPT_EXCLUDE_ALL_SHADER_OFFSETS)
    rand = g.node(unreal.MaterialExpressionPerInstanceRandom)
    # Height within the mesh, 0 at the base and 1 at the tip (basic shapes span local Z -50..50).
    lz_v = g.custom("return LP.z / 100.0 + 0.5;", F1, [("LP", g.node(unreal.MaterialExpressionPreSkinnedPosition))], "Local height 0..1")
    lz = g.node(unreal.MaterialExpressionVertexInterpolator)
    g.link(lz_v, lz, "VS")
    colour = g.custom(FOLIAGE_CODE, F3, [
        ("P", P), ("LZ", lz), ("Rand", rand),
        ("Texel", g.scalar("TexelSize", 3.5, "Crunch")),
        ("Dark", g.vector("Dark", srgb("#1f3326"), "Colour")),
        ("Mid", g.vector("Mid", srgb("#2f4a2f"), "Colour")),
        ("Light", g.vector("Light", srgb("#4a6336"), "Colour")),
        ("Tip", g.vector("Tip", srgb("#74833f"), "Colour")),
    ], "Foliage colour")
    sway = g.custom(
        "float k = saturate(P.z / 900.0);\n"
        "float t = Time * Speed + Rand * 6.2832;\n"
        "return float3(sin(t + P.y * 0.004), cos(t * 0.83 + P.x * 0.004), 0.0) * Amount * k * k;",
        F3, [("P", g.node(unreal.MaterialExpressionWorldPosition, world_position_shader_offset=unreal.WorldPositionIncludedOffsets.WPT_EXCLUDE_ALL_SHADER_OFFSETS)),
             ("Time", g.node(unreal.MaterialExpressionTime)), ("Rand", rand),
             ("Speed", g.scalar("SwaySpeed", 1.1, "Sway")), ("Amount", g.scalar("SwayAmount", 3.0, "Sway"))], "Wind sway")
    g.out(colour, MP.MP_BASE_COLOR)
    g.out(sway, MP.MP_WORLD_POSITION_OFFSET)
    g.out(g.scalar("Roughness", 0.85, "Surface"), MP.MP_ROUGHNESS)
    g.out(g.const(0.15), MP.MP_SPECULAR)
    g.finish()
    return mat


# ----------------------------------------------------------------------------- water
WATER_CODE = r"""
struct SRW { float h(float2 p) { float3 p3 = frac(float3(p.xyx) * 0.1031); p3 += dot(p3, p3.yzx + 33.33); return frac((p3.x + p3.y) * p3.z); }
	float vn(float2 p) { float2 i = floor(p); float2 f = frac(p); f = f * f * (3.0 - 2.0 * f);
		return lerp(lerp(h(i), h(i + float2(1, 0)), f.x), lerp(h(i + float2(0, 1)), h(i + float2(1, 1)), f.x), f.y); } };
SRW f;
float T = max(Texel, 0.5);
float2 c = floor(P.xy / T + 0.001);
float2 w = c * T;
float a = f.vn(w / 260.0 + float2(Time * 0.06, Time * 0.045));
float b = f.vn(w / 95.0 - float2(Time * 0.09, -Time * 0.07));
float r = a * 0.6 + b * 0.4;
float3 col = lerp(Deep, Shallow, smoothstep(0.35, 0.75, r));
float glint = abs(r - 0.5) < 0.012 ? 1.0 : 0.0;                 // thin moving caustic lines, crunchy like the land
return col + Foam * glint * 0.07;
"""


def build_water():
    mat = get_material("M_Water")
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE)
    g = G(mat)
    colour = g.custom(WATER_CODE, F3, [
        ("P", g.node(unreal.MaterialExpressionWorldPosition)), ("Time", g.node(unreal.MaterialExpressionTime)),
        ("Texel", g.scalar("TexelSize", 3.5, "Crunch")),
        ("Deep", g.vector("Deep", srgb("#1c3f47"), "Colour")),
        ("Shallow", g.vector("Shallow", srgb("#2c5c5f"), "Colour")),
        ("Foam", g.vector("Foam", srgb("#cfe6dc"), "Colour")),
    ], "Water colour")
    g.out(colour, MP.MP_BASE_COLOR)
    g.out(g.scalar("Roughness", 0.12, "Surface"), MP.MP_ROUGHNESS)
    g.out(g.const(0.6), MP.MP_SPECULAR)
    g.finish()


def make_instance(name, parent, scalars=None, vectors=None):
    path = DIR + "/" + name
    if eal.does_asset_exist(path):
        mi = eal.load_asset(path)
    else:
        mi = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, DIR, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(mi, parent)
    for k, v in (scalars or {}).items():
        mel.set_material_instance_scalar_parameter_value(mi, k, v)
    for k, v in (vectors or {}).items():
        mel.set_material_instance_vector_parameter_value(mi, k, v)
    mel.update_material_instance(mi)
    eal.save_loaded_asset(mi, False)
    print("built", path)


if not eal.does_directory_exist(DIR):
    eal.make_directory(DIR)
build_unit()
build_ring()
terrain = build_terrain()
foliage = build_foliage()
build_water()
make_instance("MI_Terrain_Rock", terrain, scalars={"RockTop": 1.0, "Moss": 0.42, "StoneCourseTexels": 11.0, "JointBrightness": 0.86})
make_instance("MI_Foliage_Tuft", foliage, scalars={"SwayAmount": 0.0},
              vectors={"Dark": srgb("#5a6a2c"), "Mid": srgb("#7b8436"), "Light": srgb("#9a9a45"), "Tip": srgb("#c4b660")})
make_instance("MI_Foliage_Trunk", foliage, scalars={"SwayAmount": 0.0},
              vectors={"Dark": srgb("#3a2a1c"), "Mid": srgb("#4d3823"), "Light": srgb("#63492d"), "Tip": srgb("#7a5c3a")})
