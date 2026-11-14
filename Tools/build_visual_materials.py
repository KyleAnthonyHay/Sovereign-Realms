"""Builds (or rebuilds in place) the materials under /Game/SR/Materials.

Run inside the editor:  Tools/ue_py.py Tools/build_visual_materials.py
(after Tools/import_world_assets.py, which brings in the pixel-art textures they sample).
Re-running keeps asset references intact: graphs are cleared and rebuilt.
See Docs/VISUAL_CONTRACT.md for the parameter contract.

World materials share three ideas:
  * one texel density: every mesh carries UV0 in centimetres (or the material uses world XY), and
    the material divides by TexelSize (4 cm), so a texel is the same size on every surface;
  * crisp texels without crawl: textures are sampled through SRPix.S, which snaps to the texel
    grid but anti-aliases the texel edge over one screen pixel (and falls back to the mip chain
    once texels are smaller than a pixel), so panning the camera does not make the art shimmer;
  * real light on the pixels: the art is albedo only. Lumen, the sun and the shadow maps do the rest.
"""
import unreal

DIR = "/Game/SR/Materials"
TEX = "/Game/SR/Textures/"
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

    def tex(self, name, asset, linear=False, group="Textures"):
        """Texture object parameter, for sampling inside a Custom node."""
        t = unreal.EditorAssetLibrary.load_asset(TEX + asset)
        if t is None:
            raise RuntimeError("missing texture " + TEX + asset + " (run Tools/import_world_assets.py first)")
        st = unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR if linear else unreal.MaterialSamplerType.SAMPLERTYPE_COLOR
        return self.node(unreal.MaterialExpressionTextureObjectParameter, parameter_name=name, texture=t, sampler_type=st, group=group)

    def custom(self, code, out_type, inputs, desc, outputs=None):
        """inputs: list of (name, expression) or (name, expression, output_name).
        outputs: extra named outputs [(name, type)], assigned in the code as plain variables."""
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
        print("built", self.mat.get_path_name())


F1 = unreal.CustomMaterialOutputType.CMOT_FLOAT1
F2 = unreal.CustomMaterialOutputType.CMOT_FLOAT2
F3 = unreal.CustomMaterialOutputType.CMOT_FLOAT3
F4 = unreal.CustomMaterialOutputType.CMOT_FLOAT4

# Shared HLSL: crisp, anti-aliased texel sampling. `uv` is in texels, `size` is the texture size in texels.
PIX = r"""
struct SRPix
{
	float4 S(Texture2D T, float2 uv, float2 size)
	{
		float2 fw = max(fwidth(uv), 1e-5);
		float2 seam = floor(uv + 0.5);
		float2 p = seam + clamp((uv - seam) / fw, -0.5, 0.5);
		return T.SampleGrad(View.SharedTrilinearWrappedSampler, p / size, ddx(uv) / size, ddy(uv) / size);
	}
	float4 Texel(Texture2D T, float2 texel, float2 size) { return T.SampleLevel(View.SharedPointWrappedSampler, (floor(texel) + 0.5) / size, 0); }
	float h(float2 p) { float3 p3 = frac(float3(p.xyx) * 0.1031); p3 += dot(p3, p3.yzx + 33.33); return frac((p3.x + p3.y) * p3.z); }
	float lum(float3 c) { return dot(c, float3(0.3, 0.59, 0.11)); }
};
SRPix px;
"""


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
TERRAIN_CODE = PIX + r"""
float T = max(Texel, 0.5);
float3 col;
float3 nrm = float3(0, 0, 1);
float rough = 0.95;
if (N.z > 0.5)
{
	// ---- top: world-aligned. Texture 'up' is world +X (up the screen), so blades stand toward the horizon.
	float2 uv = float2(P.y, -P.x) / T;
	float2 tc = floor(uv) + 0.5;                                   // this texel
	float2 wc = float2(-tc.y, tc.x) * T;                            // its world XY
	float4 sp = Splat.SampleLevel(View.SharedBilinearClampedSampler, (wc - SplatRect.xy) / SplatRect.z, 0);
	float hx = px.h(tc);
	float3 g0 = px.S(Grass, uv, 128).rgb;
	float tip = saturate((px.lum(px.Texel(Grass, uv, 128).rgb) - 0.045) / 0.16);     // 0 thatch .. 1 blade tip, per texel
	col = g0;
	// moss and straw take over tuft by tuft (blade tips hold out longest), never as a soft blend
	if (sp.g > 0.5 + (hx - 0.5) * 0.35 + (tip - 0.5) * 0.2) col = px.S(GrassMoss, uv, 128).rgb;
	if (sp.b > 0.5 + (hx - 0.5) * 0.35 - (tip - 0.5) * 0.2) col = px.S(GrassDry, uv, 128).rgb;
	// road: bare earth first, with grass tips poking into its edge; then stones, joints dissolving first
	float r = sp.r;
	if (r > 0.2 + tip * 0.22 + (hx - 0.5) * 0.1)
	{
		col = px.S(Dirt, uv, 128).rgb;
		nrm = px.S(DirtN, uv, 128).xyz * 2.0 - 1.0;
		rough = 0.9;
		float3 cb = px.Texel(Cobble, uv, 128).rgb;
		float body = saturate((px.lum(cb) - 0.05) / 0.2);          // 0 in the joints .. 1 on a stone's face
		if (r > 0.9 - body * 0.32)
		{
			col = px.S(Cobble, uv, 128).rgb;
			nrm = px.S(CobbleN, uv, 128).xyz * 2.0 - 1.0;
			rough = StoneRoughness;
		}
		nrm = normalize(float3(-nrm.y * NormalStrength, nrm.x * NormalStrength, nrm.z));
	}
	col *= lerp(1.0, sp.a, FootShade);                             // shade baked at cliff feet
	col *= 1.0 + (sp.b - sp.g) * TintRange;                        // dry ground a little lighter, mossy a little deeper
}
else
{
	// ---- side: UV0 = (distance along the outline, depth below the turf) in cm; UV1.x = wall height
	float2 uv = UV0 / T;
	float wallH = UV1.x;
	col = px.S(Cliff, uv, 128).rgb;
	float3 tn = px.S(CliffN, uv, 128).xyz * 2.0 - 1.0;
	float3 Tw = normalize(float3(-N.y, N.x, 0.0));
	nrm = normalize(Tw * tn.x * NormalStrength + float3(0, 0, -1) * tn.y * NormalStrength + N * tn.z);
	rough = StoneRoughness + 0.1;
	// turf hanging over the edge, never more than about half the wall
	float lipMax = min(23.0, wallH / T * LipFraction);
	if (uv.y < lipMax)
	{
		float4 lp = px.S(Lip, float2(uv.x, min(uv.y, 23.4)), float2(128, 24));
		float grassW = saturate((lp.a - 0.6) / 0.3);
		float shadow = saturate(lp.a / 0.43) * (1.0 - grassW);
		col = lerp(col * (1.0 - shadow * LipShadow), lp.rgb, grassW);
		nrm = normalize(lerp(nrm, normalize(N + float3(0, 0, 0.6)), grassW));
		rough = lerp(rough, 0.95, grassW);
	}
	float above = wallH - UV0.y;                                    // cm above the wall's foot
	col *= lerp(1.0 - FootShade * 0.35, 1.0, saturate(above / 30.0));
}
OutNormal = nrm;
OutRough = rough;
return col * Tint;
"""


def build_terrain():
    mat = get_material("M_Terrain")
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE)
    mat.set_editor_property("tangent_space_normal", False)
    g = G(mat)
    P = g.node(unreal.MaterialExpressionWorldPosition, world_position_shader_offset=unreal.WorldPositionIncludedOffsets.WPT_EXCLUDE_ALL_SHADER_OFFSETS)
    N = g.node(unreal.MaterialExpressionVertexNormalWS)
    uv0 = g.node(unreal.MaterialExpressionTextureCoordinate, coordinate_index=0)
    uv1 = g.node(unreal.MaterialExpressionTextureCoordinate, coordinate_index=1)
    params = [
        ("P", P), ("N", N), ("UV0", uv0), ("UV1", uv1),
        ("Grass", g.tex("Grass", "T_Grass")), ("GrassMoss", g.tex("GrassMoss", "T_GrassMoss")), ("GrassDry", g.tex("GrassDry", "T_GrassDry")),
        ("Dirt", g.tex("Dirt", "T_Dirt")), ("DirtN", g.tex("DirtNormal", "T_Dirt_N", True)),
        ("Cobble", g.tex("Cobble", "T_Cobble")), ("CobbleN", g.tex("CobbleNormal", "T_Cobble_N", True)),
        ("Cliff", g.tex("Cliff", "T_Cliff")), ("CliffN", g.tex("CliffNormal", "T_Cliff_N", True)),
        ("Lip", g.tex("Lip", "T_Lip")), ("Splat", g.tex("Splat", "T_Splat", True)),
        ("Texel", g.scalar("TexelSize", 4.0, "Crunch")),
        # SplatRect: XY = world origin of the splat map, Z = its world size (cm). Written by gen_battlefield.py's layout.
        ("SplatRect", g.vector("SplatRect", lin(-5600.0, -6144.0, 12288.0, 0.0), "Splat"), "RGBA"),
        ("NormalStrength", g.scalar("NormalStrength", 1.0, "Surface")),
        ("StoneRoughness", g.scalar("StoneRoughness", 0.72, "Surface")),
        ("FootShade", g.scalar("FootShade", 0.6, "Shading")),
        ("LipShadow", g.scalar("LipShadow", 0.4, "Shading")),
        ("LipFraction", g.scalar("LipFraction", 0.55, "Shading")),
        ("TintRange", g.scalar("TintRange", 0.08, "Shading")),
        ("Tint", g.vector("Tint", lin(1.0, 1.0, 1.0), "Shading")),
    ]
    colour = g.custom(TERRAIN_CODE, F3, params, "Terrain: turf / road on top, strata + turf lip on the sides", outputs=[("OutNormal", F3), ("OutRough", F1)])
    g.out(colour, MP.MP_BASE_COLOR)
    g.out(colour, MP.MP_NORMAL, "OutNormal")
    g.out(colour, MP.MP_ROUGHNESS, "OutRough")
    g.out(g.scalar("Specular", 0.25, "Surface"), MP.MP_SPECULAR)
    g.finish()
    return mat


# ----------------------------------------------------------------------------- props (rocks, masonry, timber)
PROP_CODE = PIX + r"""
float T = max(Texel, 0.5);
float2 uv = UV0 / T;
float3 col = VCb > 0.5 ? px.S(TexA, uv, SizeA.xy).rgb : px.S(TexB, uv, SizeB.xy).rgb;
// moss / turf settling on up-facing stone, texel by texel
// turf settles on up-facing facets, a whole facet at a time (no dither: a facet is either mossed over or bare)
if (Moss > 0.0 && N.z > lerp(1.02, MossSlope, Moss))
{
	col = px.S(MossTex, float2(P.y, -P.x) / T, 128).rgb;
}
// grounded: darker where the piece meets the turf
col *= lerp(1.0 - FootShade, 1.0, saturate((P.z - PivotZ + 4.0) / 36.0));
return col * Tint;
"""


def build_prop():
    mat = get_material("M_Prop")
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE)
    mel.set_base_material_usage(mat, unreal.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES)
    g = G(mat)
    P = g.node(unreal.MaterialExpressionWorldPosition, world_position_shader_offset=unreal.WorldPositionIncludedOffsets.WPT_EXCLUDE_ALL_SHADER_OFFSETS)
    obj = g.node(unreal.MaterialExpressionObjectPositionWS)
    pivot_z = g.node(unreal.MaterialExpressionComponentMask, r=False, g=False, b=True, a=False)
    g.link(obj, pivot_z, "")
    params = [
        ("P", P), ("N", g.node(unreal.MaterialExpressionVertexNormalWS)), ("UV0", g.node(unreal.MaterialExpressionTextureCoordinate, coordinate_index=0)),
        ("VCb", g.node(unreal.MaterialExpressionVertexColor), "B"), ("PivotZ", pivot_z),
        ("TexA", g.tex("TexA", "T_Rock")), ("TexB", g.tex("TexB", "T_Rock")), ("MossTex", g.tex("MossTex", "T_GrassMoss")),
        ("SizeA", g.vector("SizeA", lin(64.0, 64.0, 0.0, 0.0), "Textures"), "RGBA"),
        ("SizeB", g.vector("SizeB", lin(64.0, 64.0, 0.0, 0.0), "Textures"), "RGBA"),
        ("Texel", g.scalar("TexelSize", 4.0, "Crunch")),
        ("Moss", g.scalar("Moss", 0.0, "Moss")), ("MossSlope", g.scalar("MossSlope", 0.6, "Moss")),
        ("FootShade", g.scalar("FootShade", 0.35, "Shading")),
        ("Tint", g.vector("Tint", lin(1.0, 1.0, 1.0), "Shading")),
    ]
    colour = g.custom(PROP_CODE, F3, params, "Prop: UV0 in cm, texture A / B by vertex colour B, moss on top")
    g.out(colour, MP.MP_BASE_COLOR)
    g.out(g.scalar("Roughness", 0.82, "Surface"), MP.MP_ROUGHNESS)
    g.out(g.scalar("Specular", 0.3, "Surface"), MP.MP_SPECULAR)
    g.finish()
    return mat


# ----------------------------------------------------------------------------- foliage
FOLIAGE_CODE = PIX + r"""
float T = max(Texel, 0.5);
float2 uv = UV0 / T;
float4 c;
if (VCb > 0.5) { c = float4(px.S(Bark, uv, float2(32, 64)).rgb, 1.0); }
else
{
	c = px.S(Needles, uv, float2(64, 48));
	c.rgb *= lerp(ShadeFloor, 1.0, UV1.x) * (0.9 + 0.2 * Rand);     // dark under each tier and at the base, lit toward the crown
	c.rgb = lerp(c.rgb, c.rgb * TipTint, saturate(UV1.x * UV1.x));
}
OutAlpha = c.a;
OutSub = c.rgb * Subsurface * (VCb > 0.5 ? 0.0 : 1.0);
return c.rgb * Tint;
"""

SWAY_CODE = r"""
float t = Time * Speed + Rand * 6.2832;
return float3(sin(t + P.y * 0.004), cos(t * 0.83 + P.x * 0.004), 0.0) * Amount * Weight * Weight;
"""

def build_foliage():
    mat = get_material("M_Foliage")
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
    mat.set_editor_property("two_sided", True)
    mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_TWO_SIDED_FOLIAGE)
    mat.set_editor_property("opacity_mask_clip_value", 0.5)
    mel.set_base_material_usage(mat, unreal.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES)
    g = G(mat)
    rand = g.node(unreal.MaterialExpressionPerInstanceRandom)
    uv1 = g.node(unreal.MaterialExpressionTextureCoordinate, coordinate_index=1)
    vc = g.node(unreal.MaterialExpressionVertexColor)
    colour = g.custom(FOLIAGE_CODE, F3, [
        ("UV0", g.node(unreal.MaterialExpressionTextureCoordinate, coordinate_index=0)), ("UV1", uv1), ("VCb", vc, "B"), ("Rand", rand),
        ("Needles", g.tex("Needles", "T_Needles")), ("Bark", g.tex("Bark", "T_Bark")),
        ("Texel", g.scalar("TexelSize", 4.0, "Crunch")),
        ("ShadeFloor", g.scalar("ShadeFloor", 0.2, "Colour")),
        ("TipTint", g.vector("TipTint", lin(1.12, 1.08, 0.86), "Colour")),
        ("Subsurface", g.scalar("Subsurface", 0.55, "Colour")),
        ("Tint", g.vector("Tint", lin(1.0, 1.0, 1.0), "Colour")),
    ], "Conifer: needles / bark by vertex colour B", outputs=[("OutAlpha", F1), ("OutSub", F3)])
    weight = g.node(unreal.MaterialExpressionComponentMask, r=False, g=True, b=False, a=False)
    g.link(uv1, weight, "")
    sway = g.custom(SWAY_CODE, F3, [
        ("P", g.node(unreal.MaterialExpressionWorldPosition, world_position_shader_offset=unreal.WorldPositionIncludedOffsets.WPT_EXCLUDE_ALL_SHADER_OFFSETS)),
        ("Time", g.node(unreal.MaterialExpressionTime)), ("Rand", rand), ("Weight", weight),
        ("Speed", g.scalar("SwaySpeed", 1.1, "Sway")), ("Amount", g.scalar("SwayAmount", 5.0, "Sway"))], "Wind sway")
    g.out(colour, MP.MP_BASE_COLOR)
    g.out(colour, MP.MP_OPACITY_MASK, "OutAlpha")
    g.out(colour, MP.MP_SUBSURFACE_COLOR, "OutSub")
    g.out(sway, MP.MP_WORLD_POSITION_OFFSET)
    g.out(g.scalar("Roughness", 0.85, "Surface"), MP.MP_ROUGHNESS)
    g.out(g.const(0.2), MP.MP_SPECULAR)
    g.finish()
    return mat


# ----------------------------------------------------------------------------- sprite cards (grass, ferns, flowers, banner)
CARD_CODE = PIX + r"""
float4 c = px.S(Tex, UV0 * Size.xy, Size.xy);
c.rgb *= lerp(RootShade, 1.0, saturate(UV1.y * 2.2)) * (0.88 + 0.24 * Rand);     // sinks into the turf at the root
OutAlpha = c.a;
return c.rgb * Tint;
"""


def build_card():
    mat = get_material("M_Card")
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
    mat.set_editor_property("two_sided", True)
    mat.set_editor_property("tangent_space_normal", False)
    mat.set_editor_property("opacity_mask_clip_value", 0.5)
    mel.set_base_material_usage(mat, unreal.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES)
    g = G(mat)
    rand = g.node(unreal.MaterialExpressionPerInstanceRandom)
    uv1 = g.node(unreal.MaterialExpressionTextureCoordinate, coordinate_index=1)
    colour = g.custom(CARD_CODE, F3, [
        ("UV0", g.node(unreal.MaterialExpressionTextureCoordinate, coordinate_index=0)), ("UV1", uv1), ("Rand", rand),
        ("Tex", g.tex("Tex", "T_Tufts")),
        ("Size", g.vector("Size", lin(96.0, 24.0, 0.0, 0.0), "Textures"), "RGBA"),
        ("RootShade", g.scalar("RootShade", 0.6, "Colour")),
        ("Tint", g.vector("Tint", lin(0.86, 0.86, 0.86), "Colour")),
    ], "Sprite card (UV0 0..1)", outputs=[("OutAlpha", F1)])
    weight = g.node(unreal.MaterialExpressionComponentMask, r=False, g=True, b=False, a=False)
    g.link(uv1, weight, "")
    sway = g.custom(SWAY_CODE, F3, [
        ("P", g.node(unreal.MaterialExpressionWorldPosition, world_position_shader_offset=unreal.WorldPositionIncludedOffsets.WPT_EXCLUDE_ALL_SHADER_OFFSETS)),
        ("Time", g.node(unreal.MaterialExpressionTime)), ("Rand", rand), ("Weight", weight),
        ("Speed", g.scalar("SwaySpeed", 1.6, "Sway")), ("Amount", g.scalar("SwayAmount", 2.5, "Sway"))], "Wind sway")
    g.out(colour, MP.MP_BASE_COLOR)
    g.out(colour, MP.MP_OPACITY_MASK, "OutAlpha")
    g.out(g.const3(0.0, 0.0, 1.0), MP.MP_NORMAL)        # lit like the ground it stands in, from both sides
    g.out(sway, MP.MP_WORLD_POSITION_OFFSET)
    g.out(g.scalar("Roughness", 0.95, "Surface"), MP.MP_ROUGHNESS)
    g.out(g.const(0.1), MP.MP_SPECULAR)
    g.finish()
    return mat


# ----------------------------------------------------------------------------- water
WATER_CODE = PIX + r"""
float T = max(Texel, 0.5);
float2 uv = float2(P.y, -P.x) / T;
// two ripple layers sliding past each other, stepped a whole texel at a time so the pixels stay pixels
float2 a = uv + floor(float2(Time * Speed.x, Time * Speed.y));
float2 b = uv * 1.0 + float2(31.0, 17.0) - floor(float2(Time * Speed.z, -Time * Speed.w));
float3 ca = px.S(Tex, a, 64).rgb;
float3 cb = px.S(Tex, b, 64).rgb;
float3 col = max(ca, cb * 0.85);
float glint = saturate((px.lum(col) - GlintLevel) * 6.0);
OutEmissive = Glint.rgb * glint * Glint.a;
return lerp(col * Tint.rgb, Deep.rgb, DeepMix);
"""


def build_water():
    mat = get_material("M_Water")
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE)
    g = G(mat)
    colour = g.custom(WATER_CODE, F3, [
        ("P", g.node(unreal.MaterialExpressionWorldPosition)), ("Time", g.node(unreal.MaterialExpressionTime)),
        ("Tex", g.tex("Tex", "T_Water")),
        ("Texel", g.scalar("TexelSize", 4.0, "Crunch")),
        ("Speed", g.vector("ScrollTexelsPerSecond", lin(1.6, 0.5, 1.1, 0.8), "Motion"), "RGBA"),
        ("Tint", g.vector("Tint", lin(1.0, 1.0, 1.0), "Colour")),
        ("Deep", g.vector("Deep", srgb("#12303a"), "Colour")),
        ("DeepMix", g.scalar("DeepMix", 0.25, "Colour")),
        ("Glint", g.vector("Glint", lin(1.0, 0.92, 0.75, 0.6), "Colour"), "RGBA"),
        ("GlintLevel", g.scalar("GlintLevel", 0.32, "Colour")),
    ], "Water colour", outputs=[("OutEmissive", F3)])
    g.out(colour, MP.MP_BASE_COLOR)
    g.out(colour, MP.MP_EMISSIVE_COLOR, "OutEmissive")
    g.out(g.scalar("Roughness", 0.1, "Surface"), MP.MP_ROUGHNESS)
    g.out(g.scalar("Specular", 0.6, "Surface"), MP.MP_SPECULAR)
    g.finish()


def make_instance(name, parent, scalars=None, vectors=None, textures=None):
    path = DIR + "/" + name
    if eal.does_asset_exist(path):
        mi = eal.load_asset(path)
    else:
        mi = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, DIR, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(mi, parent)
    mel.clear_all_material_instance_parameters(mi)
    for k, v in (scalars or {}).items():
        mel.set_material_instance_scalar_parameter_value(mi, k, v)
    for k, v in (vectors or {}).items():
        mel.set_material_instance_vector_parameter_value(mi, k, v)
    for k, v in (textures or {}).items():
        mel.set_material_instance_texture_parameter_value(mi, k, eal.load_asset(TEX + v))
    mel.update_material_instance(mi)
    eal.save_loaded_asset(mi, False)
    print("built", path)


if not eal.does_directory_exist(DIR):
    eal.make_directory(DIR)
for stale in ("MI_Terrain_Rock", "MI_Foliage_Tuft", "MI_Foliage_Trunk"):      # instances from the first, texture-less pass
    if eal.does_asset_exist(DIR + "/" + stale):
        eal.delete_asset(DIR + "/" + stale)
ONLY = globals().get("ONLY")          # e.g. ONLY = ["terrain"] to rebuild one material while iterating
if not ONLY or "unit" in ONLY:
    build_unit()
    build_ring()
if not ONLY or "terrain" in ONLY:
    build_terrain()
if not ONLY or "water" in ONLY:
    build_water()
if not ONLY or "prop" in ONLY:
    prop = build_prop()
    make_instance("MI_Prop_Rock", prop, scalars={"Moss": 1.0, "MossSlope": 0.84, "Roughness": 0.86},
                  vectors={"SizeA": lin(64, 64, 0, 0), "Tint": lin(0.8, 0.78, 0.72)}, textures={"TexA": "T_Rock"})
    make_instance("MI_Prop_Sandstone", prop, scalars={"Moss": 0.0, "Roughness": 0.8},
                  vectors={"SizeA": lin(128, 64, 0, 0)}, textures={"TexA": "T_Sandstone"})
    make_instance("MI_Prop_Wood", prop, scalars={"Roughness": 0.8, "FootShade": 0.25},
                  vectors={"SizeA": lin(64, 32, 0, 0)}, textures={"TexA": "T_Wood"})
    make_instance("MI_Prop_Log", prop, scalars={"Moss": 0.0, "Roughness": 0.85},
                  vectors={"SizeA": lin(16, 16, 0, 0), "SizeB": lin(32, 64, 0, 0)}, textures={"TexA": "T_LogEnd", "TexB": "T_Bark"})
if not ONLY or "foliage" in ONLY:
    build_foliage()
if not ONLY or "card" in ONLY:
    cardm = build_card()
    make_instance("MI_Card_Banner", cardm, scalars={"RootShade": 1.0, "SwayAmount": 5.0, "SwaySpeed": 2.2},
                  vectors={"Size": lin(16, 40, 0, 0), "Tint": lin(1, 1, 1)}, textures={"Tex": "T_Banner"})
