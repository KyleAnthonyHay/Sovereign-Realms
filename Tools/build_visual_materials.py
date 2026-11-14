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
import os
import unreal


def _splat_rect():
    """World origin and size of the ground splat map, from the generator's layout (falls back to the old small map)."""
    import json as _json
    try:
        with open(os.path.join(os.path.abspath(unreal.Paths.project_dir()), "SourceArt", "World", "layout.json")) as f:
            sp = _json.load(f)["splat"]
        return (float(sp["origin"][0]), float(sp["origin"][1]), float(sp["size"]), 0.0)
    except Exception:
        return (-5600.0, -6144.0, 12288.0, 0.0)

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

    def scalar(self, name, default, group="SR", cpd=None):
        """cpd: custom primitive data index. The value then comes from the component (one float per primitive),
        so every unit shares one material instance; the default is used where the component sets nothing."""
        e = self.node(unreal.MaterialExpressionScalarParameter, parameter_name=name, default_value=default, group=group)
        if cpd is not None:
            e.set_editor_property("use_custom_primitive_data", True)
            e.set_editor_property("primitive_data_index", cpd)
        return e

    def vector(self, name, default, group="SR", cpd=None):
        e = self.node(unreal.MaterialExpressionVectorParameter, parameter_name=name, default_value=default, group=group)
        if cpd is not None:                       # occupies cpd .. cpd + 3
            e.set_editor_property("use_custom_primitive_data", True)
            e.set_editor_property("primitive_data_index", cpd)
        return e

    def const(self, v):
        return self.node(unreal.MaterialExpressionConstant, r=v)

    def const3(self, r, g, b):
        return self.node(unreal.MaterialExpressionConstant3Vector, constant=lin(r, g, b))

    def link(self, src, dst, dst_in, src_out=""):
        ok = mel.connect_material_expressions(src, src_out, dst, dst_in)
        if not ok:
            raise RuntimeError("connect failed: %s -> %s.%s" % (src.get_name(), dst.get_name(), dst_in))

    def tex(self, name, asset, linear=False, group="Textures", sampler=None):
        """Texture object parameter, for sampling inside a Custom node. `asset` is a name under /Game/SR/Textures or a full path."""
        path = asset if asset.startswith("/") else TEX + asset
        t = unreal.EditorAssetLibrary.load_asset(path)
        if t is None:
            raise RuntimeError("missing texture " + path + " (run Tools/import_world_assets.py / import_character_sprites.py first)")
        st = sampler or (unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR if linear else unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
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


# ----------------------------------------------------------------------------- grey test blocks
# M_UnitGreybox was the troops' material while they were primitives. Only the optional obstacle blocks use it now
# (Sovereign Feel > Scenario > Spawn Greybox Obstacles); the troops are build_sprite() below.
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
        ("SplatRect", g.vector("SplatRect", lin(*_splat_rect()), "Splat"), "RGBA"),
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


# ----------------------------------------------------------------------------- troop sprites
# Custom primitive data layout shared by M_UnitSprite and M_UnitSpriteShadow (set by ASRUnit / ASRProjectile):
#   0 FrameCol   1 FrameRow   2 HitFlash   3 Fade   4..7 TeamColor
CHAR = "/Game/SR/Characters/"

SPRITE_CODE = r"""
float2 cell = CellPx.xy;
float2 size = SheetCells.xy * cell;
float2 origin = float2(FrameCol, FrameRow) * cell;
float2 uv = UV * cell;                                          // texels inside this frame's cell
// crisp texels, each edge anti-aliased over EdgeSoftness screen pixels (SRPix.S uses one; a sprite texel is only about
// two pixels wide at the default zoom and temporal AA already integrates the edge, so less keeps the pixels harder).
// No mips: the sheets are never minified far.
float2 fw = max(fwidth(uv) * EdgeSoftness, 1e-5);
float2 seam = floor(uv + 0.5);
float2 p = clamp(seam + clamp((uv - seam) / fw, -0.5, 0.5), 0.5, cell - 0.5);
float4 c = Sheet.SampleLevel(View.SharedBilinearClampedSampler, (origin + p) / size, 0);
float2 tc = (origin + clamp(floor(uv) + 0.5, 0.5, cell - 0.5)) / size;      // this texel's centre: mask and normal are never blended
float m = Mask.SampleLevel(View.SharedPointClampedSampler, tc, 0).r;
float3 n = Nrm.SampleLevel(View.SharedPointClampedSampler, tc, 0).xyz * 2.0 - 1.0;
float3 rgb = lerp(c.rgb, c.rgb * Team.rgb * 2.0, m);           // SPRITE_SPEC.md, Team colour
float f = saturate(Flash);
rgb = lerp(rgb, FlashCol.rgb, f * FlashMix);
// Normal: sheet space (x screen right, y screen down, z toward the viewer) -> world, through the view axes (the card
// is parallel to the view plane). NormalStrength 0 = one even normal for the whole figure, halfway between up and the viewer.
float3 even = normalize(float3(0.0, -0.45, 0.9));
n = normalize(lerp(even, n, NormalStrength));
OutNormal = normalize(n.x * View.ViewRight - n.y * View.ViewUp - n.z * View.ViewForward);
// Relight splits the baked look between an emissive share (always there) and a share the scene lights and shadows.
OutEmissive = rgb * (1.0 - Relight) * Baked + FlashCol.rgb * f * Glow;
float dn = InterleavedGradientNoise(Parameters.SvPosition.xy, View.StateFrameIndexMod8);
OutMask = c.a * ((Fade > dn * 0.98 + 0.01) ? 1.0 : 0.0);        // dithered death fade; stays in the opaque pass
return rgb * Relight;
"""

# The card is parallel to the view plane, so it leans back with the camera: its head would sink into a wall behind
# the unit and its feet into the ground. Each vertex slides along its own view ray, which does not move it on screen:
# the top row onto an upright plane through the feet, the pivot and bottom rows onto the ground. The card then has the
# depth of a standing figure (sorting, shadows received, depth of field) and still looks exactly like the flat sprite.
SPRITE_WPO = r"""
float3 F = normalize(float3(View.ViewForward.xy, 0.0));
float3 R = P - C;
float s;
if (UV.y < PivotV - 0.001) s = dot(O - C, F) / max(dot(R, F), 1.0);
else s = (O.z + Lift - C.z) / min(R.z, -1.0);
return R * (clamp(s, 0.25, 4.0) - 1.0) * Billboard;
"""

SPRITE_SHADOW_CODE = r"""
float2 cell = CellPx.xy;
float2 size = SheetCells.xy * cell;
float2 t = clamp(floor(UV * cell) + 0.5, 0.5, cell - 0.5);
float a = Sheet.SampleLevel(View.SharedPointClampedSampler, (float2(FrameCol, FrameRow) * cell + t) / size, 0).a;
// the corpse's shadow dissolves texel by texel (a temporal dither would boil in the shadow map)
float h = frac(sin(dot(floor(t), float2(12.9898, 78.233))) * 43758.5453);
return a * ((Fade > h * 0.98 + 0.01) ? 1.0 : 0.0);
"""

BLOB_CODE = r"""
float2 d = (UV - 0.5) * 2.0;
float2 q = (floor(d * Cells) + 0.5) / Cells;                   // chunky cells that travel with the unit
float r = length(q);
float a = r < 0.5 ? 1.0 : (r < 0.76 ? 0.72 : (r < 0.98 ? 0.4 : 0.0));     // three flat bands
return a * saturate(Strength) * saturate(Fade);
"""


def build_sprite():
    """M_UnitSprite (troops and arrows), M_UnitSpriteShadow (their hidden shadow cards), M_UnitBlob (contact shadow decal)."""
    G1 = unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_GRAYSCALE
    mat = get_material("M_UnitSprite")
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
    mat.set_editor_property("two_sided", True)
    mat.set_editor_property("tangent_space_normal", False)
    mat.set_editor_property("opacity_mask_clip_value", 0.5)
    mat.set_editor_property("dithered_lod_transition", False)
    g = G(mat)
    uv = g.node(unreal.MaterialExpressionTextureCoordinate)
    col = g.scalar("FrameCol", 8.0, "Per unit (custom primitive data)", cpd=0)
    row = g.scalar("FrameRow", 0.0, "Per unit (custom primitive data)", cpd=1)
    flash = g.scalar("HitFlash", 0.0, "Per unit (custom primitive data)", cpd=2)
    fade = g.scalar("Fade", 1.0, "Per unit (custom primitive data)", cpd=3)
    team = g.vector("TeamColor", lin(0.05, 0.22, 0.8), "Per unit (custom primitive data)", cpd=4)
    cells = g.vector("SheetCells", lin(24.0, 16.0, 0.0, 0.0), "Sheet")
    cellpx = g.vector("CellPx", lin(160.0, 160.0, 0.0, 0.0), "Sheet")
    colour = g.custom(SPRITE_CODE, F3, [
        ("UV", uv), ("FrameCol", col), ("FrameRow", row), ("Flash", flash), ("Fade", fade), ("Team", team),
        ("SheetCells", cells, "RGBA"), ("CellPx", cellpx, "RGBA"),
        ("Sheet", g.tex("SpriteSheet", CHAR + "T_Shieldbearer_Color", group="Sheet")),
        ("Mask", g.tex("TeamMask", CHAR + "T_Shieldbearer_TeamMask", group="Sheet", sampler=G1)),
        ("Nrm", g.tex("NormalSheet", CHAR + "T_Shieldbearer_Normal", linear=True, group="Sheet")),
        ("Relight", g.scalar("Relight", 0.6, "Look")),
        ("Baked", g.scalar("BakedLight", 3.0, "Look")),
        ("NormalStrength", g.scalar("NormalStrength", 0.7, "Look")),
        ("EdgeSoftness", g.scalar("EdgeSoftness", 0.5, "Look")),
        ("FlashCol", g.vector("HitFlashColor", lin(1.0, 0.92, 0.85), "Look")),
        ("FlashMix", g.scalar("HitFlashMix", 0.65, "Look")),
        ("Glow", g.scalar("HitFlashGlow", 0.9, "Look")),
    ], "Sprite frame: colour, team tint, flash, relight split", outputs=[("OutEmissive", F3), ("OutNormal", F3), ("OutMask", F1)])
    origin = g.node(unreal.MaterialExpressionTransformPosition,
                    transform_source_type=unreal.MaterialPositionTransformSource.TRANSFORMPOSSOURCE_LOCAL,
                    transform_type=unreal.MaterialPositionTransformSource.TRANSFORMPOSSOURCE_WORLD)
    g.link(g.const3(0.0, 0.0, 0.0), origin, "")
    wpo = g.custom(SPRITE_WPO, F3, [
        ("P", g.node(unreal.MaterialExpressionWorldPosition, world_position_shader_offset=unreal.WorldPositionIncludedOffsets.WPT_EXCLUDE_ALL_SHADER_OFFSETS)),
        ("C", g.node(unreal.MaterialExpressionCameraPositionWS)), ("O", origin), ("UV", uv),
        ("PivotV", g.scalar("PivotV", 0.7375, "Sheet")),
        ("Lift", g.scalar("GroundLift", 4.0, "Billboard")),
        ("Billboard", g.scalar("Billboard", 1.0, "Billboard")),
    ], "Billboard: upright depth, feet on the ground")
    g.out(colour, MP.MP_BASE_COLOR)
    g.out(colour, MP.MP_EMISSIVE_COLOR, "OutEmissive")
    g.out(colour, MP.MP_NORMAL, "OutNormal")
    g.out(colour, MP.MP_OPACITY_MASK, "OutMask")
    g.out(wpo, MP.MP_WORLD_POSITION_OFFSET)
    g.out(g.const(1.0), MP.MP_ROUGHNESS)
    g.out(g.const(0.0), MP.MP_SPECULAR)
    g.finish()

    sh = get_material("M_UnitSpriteShadow")
    sh.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
    sh.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    sh.set_editor_property("two_sided", True)
    sh.set_editor_property("opacity_mask_clip_value", 0.5)
    g = G(sh)
    alpha = g.custom(SPRITE_SHADOW_CODE, F1, [
        ("UV", g.node(unreal.MaterialExpressionTextureCoordinate)),
        ("FrameCol", g.scalar("FrameCol", 8.0, "Per unit (custom primitive data)", cpd=0)),
        ("FrameRow", g.scalar("FrameRow", 0.0, "Per unit (custom primitive data)", cpd=1)),
        ("Fade", g.scalar("Fade", 1.0, "Per unit (custom primitive data)", cpd=3)),
        ("SheetCells", g.vector("SheetCells", lin(24.0, 16.0, 0.0, 0.0), "Sheet"), "RGBA"),
        ("CellPx", g.vector("CellPx", lin(160.0, 160.0, 0.0, 0.0), "Sheet"), "RGBA"),
        ("Sheet", g.tex("SpriteSheet", CHAR + "T_Shieldbearer_Color", group="Sheet")),
    ], "Sprite silhouette for the shadow pass")
    g.out(alpha, MP.MP_OPACITY_MASK)
    g.out(g.const3(0.0, 0.0, 0.0), MP.MP_EMISSIVE_COLOR)
    g.finish()

    blob = get_material("M_UnitBlob")
    blob.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)        # before the domain: decals reject opaque
    blob.set_editor_property("material_domain", unreal.MaterialDomain.MD_DEFERRED_DECAL)
    g = G(blob)
    dcol = g.node(unreal.MaterialExpressionDecalColor)
    a = g.custom(BLOB_CODE, F1, [
        ("UV", g.node(unreal.MaterialExpressionTextureCoordinate)),
        ("Cells", g.scalar("Cells", 9.0, "Look")),
        ("Strength", g.scalar("Strength", 1.0, "Look")),          # the per-unit strength arrives in the decal colour's alpha
        ("Fade", dcol, "A"),
    ], "Stepped contact shadow")
    g.out(g.vector("Color", lin(0.012, 0.014, 0.03), "Look"), MP.MP_BASE_COLOR)
    g.out(a, MP.MP_OPACITY)
    g.finish()
    return mat, sh


def make_sprite_instances(sprite, shadow):
    for troop in ("Shieldbearer", "Archer", "Miner", "Farmer"):
        make_instance("MI_UnitSprite_" + troop, sprite, textures={
            "SpriteSheet": CHAR + "T_%s_Color" % troop, "TeamMask": CHAR + "T_%s_TeamMask" % troop, "NormalSheet": CHAR + "T_%s_Normal" % troop})
        make_instance("MI_UnitSpriteShadow_" + troop, shadow, textures={"SpriteSheet": CHAR + "T_%s_Color" % troop})
    # the arrow: one 44 x 9 frame, no normal sheet (one even normal), no billboard correction (the code orients its card)
    arrow = {"SheetCells": lin(1, 1, 0, 0), "CellPx": lin(44, 9, 0, 0)}
    make_instance("MI_ArrowSprite", sprite, scalars={"NormalStrength": 0.0, "Billboard": 0.0}, vectors=arrow,
                  textures={"SpriteSheet": CHAR + "T_Arrow_Color", "TeamMask": CHAR + "T_Arrow_TeamMask"})
    make_instance("MI_ArrowShadow", shadow, vectors=arrow, textures={"SpriteSheet": CHAR + "T_Arrow_Color"})


# ----------------------------------------------------------------------------- buildings (castle, farm, mine)
# One opaque and one masked material serve every surface of the buildings; each mesh slot is an instance
# (MI_Bld_<slot>, table BUILDING_SLOTS below, mirrored in Tools/blender/bldkit.py MATERIALS).
# Vertex contract (bldkit.py): UV0 in cm; UV1.x = cm below the head of the wall (opaque) or sway weight (cards);
# vertex colour R = baked shade. Custom primitive data 0..2 = the owning team's colour.
# Texture alpha is a mask on the opaque slots: 0.6 = team-coloured (TeamMask 1) or glinting (GlowMask 1) texel.
BUILDING_CODE = PIX + r"""
float T = max(Texel, 0.5);
float2 uv = WorldTop > 0.5 ? float2(P.y, -P.x) / T : UV0 / T;
float4 c = px.S(Tex, uv, Size.xy);
float4 ct = px.Texel(Tex, uv, Size.xy);
float mask = abs(ct.a - 0.6) < 0.12 ? 1.0 : 0.0;
float3 col = lerp(c.rgb, c.rgb * Team.rgb * TeamBoost, mask * TeamMask);
// Weathering is drawn in whole texels: a hash per texel dithers three or four flat steps, a slow blotch moves the
// boundaries so they never run level along a wall.
float2 tc = floor(uv);
float hx = px.h(tc);
float2 q = tc / 26.0;
float2 qi = floor(q);
float2 qf = q - qi;
qf = qf * qf * (3.0 - 2.0 * qf);
float bl = lerp(lerp(px.h(qi), px.h(qi + float2(1, 0)), qf.x), lerp(px.h(qi + float2(0, 1)), px.h(qi + float2(1, 1)), qf.x), qf.y);
float h = LocalZ;                                                  // height above the building's ground line (its origin)
// damp, dirty foot
float d = saturate(1.0 - h / max(DampHeight * (0.55 + 0.9 * bl), 1.0));
d = floor(d * 3.0 + 0.5 + (hx - 0.5) * 0.4) / 3.0;                  // three flat steps, a narrow dithered seam between them
col *= lerp(float3(1, 1, 1), DampTint.rgb, d * Damp);
// sun-bleached heads (UV1.x = cm below the top of the wall this face belongs to)
float b = saturate(1.0 - UV1.x / max(BleachDepth * (0.5 + bl), 1.0));
b = floor(b * 2.0 + 0.5 + (hx - 0.5) * 0.4) / 2.0;
col = lerp(col, col * BleachTint.rgb, b * Bleach);
// moss creeping up from the turf, joints first
if (Moss > 0.0)
{
	float joint = 1.0 - saturate((px.lum(ct.rgb) - 0.05) / 0.22);
	float mh = MossHeight * (0.2 + 1.6 * bl * bl);
	if (h < mh && hx < Moss * (1.0 - h / mh) * (0.5 + joint * 0.9)) col = px.Texel(MossTex, uv, 128).rgb * 0.85;
}
// turf settling on up-facing facets of rock, a whole facet at a time
if (MossTop > 0.0 && N.z > MossSlope) col = px.S(MossTex, float2(P.y, -P.x) / T, 128).rgb;
col *= VCr;
// normal map through the face's own UV frame (flat-shaded pieces: no tangents needed)
float3 nrm = N;
float3 tn = px.S(NormalTex, uv, Size.xy).xyz * 2.0 - 1.0;
float3 dpx = ddx(P); float3 dpy = ddy(P);
float2 dux = ddx(UV0); float2 duy = ddy(UV0);
float det = dux.x * duy.y - dux.y * duy.x;
if (abs(det) > 1e-10 && NormalStrength > 0.0 && WorldTop < 0.5)
{
	float sgn = det < 0.0 ? -1.0 : 1.0;
	float3 Tu = (dpx * duy.y - dpy * dux.y) * sgn;
	float3 Tv = (dpy * dux.x - dpx * duy.x) * sgn;
	Tu = normalize(Tu - N * dot(Tu, N));
	Tv = normalize(Tv - N * dot(Tv, N));
	nrm = normalize(Tu * tn.x * NormalStrength + Tv * tn.y * NormalStrength + N * max(tn.z, 0.2));
}
OutNormal = nrm;
OutEmissive = c.rgb * mask * GlowMask * Glow;
return col * Tint.rgb;
"""

BUILDING_CARD_CODE = PIX + r"""
float T = max(Texel, 0.5);
float2 uv = UV0 / T;
float4 c = px.S(Tex, uv, Size.xy);
float4 ct = px.Texel(Tex, uv, Size.xy);
float mask = abs(ct.a - 0.6) < 0.12 ? 1.0 : 0.0;
float3 col = lerp(c.rgb, c.rgb * Team.rgb * TeamBoost, mask * TeamMask);
col *= lerp(RootShade, 1.0, saturate(UV1.x * 1.6)) * VCr;          // crops sink into shade at the root
OutAlpha = c.a;
float3 n = N * Side;
OutNormal = normalize(lerp(n, float3(0, 0, 1), UpNormal));
float flick = 0.85 + 0.15 * sin(Time * 17.0 + P.x * 0.05) * sin(Time * 11.0 + P.y * 0.07);
OutEmissive = c.rgb * Glow * flick;
return col * Tint.rgb * (Glow > 0.0 ? 0.0 : 1.0);
"""

BUILDING_SWAY = r"""
float t = Time * Speed;
float w = Weight * Weight;
return float3(sin(t + P.y * 0.011 + P.x * 0.004), cos(t * 0.83 + P.x * 0.009), 0.0) * Amount * w;
"""

# slot -> (kind, texture, (w, h), normal map or None, scalar overrides, vector overrides)
_STONE = {"Damp": 0.55, "Bleach": 0.3, "Moss": 0.35}
BUILDING_SLOTS = {
    "Ashlar": ("opaque", "T_Bld_Ashlar", (128, 128), "T_Bld_Ashlar_N", dict(_STONE), {}),
    "AshlarLarge": ("opaque", "T_Bld_AshlarLarge", (128, 128), "T_Bld_AshlarLarge_N", dict(_STONE, Moss=0.42), {}),
    "Trim": ("opaque", "T_Bld_Trim", (64, 16), "T_Bld_Trim_N", {"Damp": 0.3, "Bleach": 0.0, "Moss": 0.0}, {}),
    "Mudbrick": ("opaque", "T_Bld_Mudbrick", (128, 128), "T_Bld_Mudbrick_N", {"Damp": 0.5, "Bleach": 0.2, "Moss": 0.3}, {}),
    "Plaster": ("opaque", "T_Bld_Plaster", (128, 128), "T_Bld_Plaster_N", {"Damp": 0.45, "Bleach": 0.2, "Moss": 0.15}, {}),
    "RoofClay": ("opaque", "T_Bld_RoofClay", (128, 128), "T_Bld_RoofClay_N", {"Damp": 0.0, "Bleach": 0.0}, {}),
    "Beam": ("opaque", "T_Bld_Beam", (64, 16), None, {"Damp": 0.35, "Bleach": 0.0, "Roughness": 0.8}, {}),
    "Planks": ("opaque", "T_Bld_Planks", (64, 64), None, {"Damp": 0.35, "Bleach": 0.0, "Roughness": 0.8}, {}),
    "Door": ("opaque", "T_Bld_Door", (64, 64), None, {"Damp": 0.0, "Bleach": 0.0, "Roughness": 0.7}, {}),
    "Shutter": ("opaque", "T_Bld_Shutter", (16, 16), None, {"Damp": 0.0, "Bleach": 0.0}, {}),
    "Thatch": ("opaque", "T_Bld_Thatch", (64, 64), "T_Bld_Thatch_N", {"Damp": 0.3, "Bleach": 0.0, "Roughness": 0.95}, {}),
    "Soil": ("opaque", "T_Bld_Soil", (64, 64), "T_Bld_Soil_N", {"Damp": 0.0, "Bleach": 0.0, "Roughness": 0.95}, {}),
    "Frieze": ("opaque", "T_Bld_Frieze", (64, 16), None, {"Damp": 0.0, "Bleach": 0.0, "TeamMask": 1.0, "Roughness": 0.45, "Specular": 0.5}, {}),
    "Bronze": ("opaque", "T_Bld_Bronze", (32, 32), None, {"Damp": 0.0, "Bleach": 0.0, "Roughness": 0.38, "Specular": 0.7}, {}),
    "Ore": ("opaque", "T_Bld_Ore", (64, 64), None, {"Damp": 0.0, "Bleach": 0.0, "GlowMask": 1.0, "Glow": 2.5, "Roughness": 0.6}, {}),
    "Gold": ("opaque", "T_Bld_Gold", (32, 32), None, {"Damp": 0.0, "Bleach": 0.0, "GlowMask": 1.0, "Glow": 3.0, "Roughness": 0.35, "Specular": 0.8}, {}),
    "Pot": ("opaque", "T_Bld_Pot", (32, 32), None, {"Damp": 0.25, "Bleach": 0.0, "Roughness": 0.6}, {}),
    "Dark": ("opaque", "T_Bld_Dark", (16, 16), None, {"Damp": 0.0, "Bleach": 0.0, "Roughness": 1.0, "Specular": 0.0}, {}),
    "Dirt": ("opaque", "T_Dirt", (128, 128), "T_Dirt_N", {"Damp": 0.0, "Bleach": 0.0, "Roughness": 0.95}, {}),
    "Cobble": ("opaque", "T_Cobble", (128, 128), "T_Cobble_N", {"Damp": 0.0, "Bleach": 0.0}, {}),
    "Bark": ("opaque", "T_Bark", (32, 64), None, {"Damp": 0.3, "Bleach": 0.0, "Roughness": 0.9}, {}),
    "LeafCore": ("opaque", "T_Bld_Leaves", (64, 64), None, {"Damp": 0.0, "Bleach": 0.0, "Roughness": 0.9, "Specular": 0.1}, {"Tint": lin(0.8, 0.8, 0.8)}),
    "Rock": ("opaque", "T_Rock", (64, 64), "T_Rock_N", {"Damp": 0.4, "Bleach": 0.0, "MossTop": 1.0, "MossSlope": 0.84, "Roughness": 0.86},
             {"Tint": lin(0.8, 0.78, 0.72)}),
    "Cliff": ("opaque", "T_Cliff", (128, 128), "T_Cliff_N", {"Damp": 0.3, "Bleach": 0.0, "Roughness": 0.82}, {}),
    "Turf": ("opaque", "T_Grass", (128, 128), None, {"Damp": 0.0, "Bleach": 0.0, "WorldTop": 1.0, "Roughness": 0.95}, {"Tint": lin(0.9, 0.9, 0.86)}),
    "Leaves": ("card", "T_Bld_Leaves", (64, 64), None, {"UpNormal": 0.6, "SwayAmount": 1.2, "SwaySpeed": 1.4}, {}),
    "Wheat": ("card", "T_Bld_Wheat", (64, 32), None, {"UpNormal": 1.0, "RootShade": 0.5, "SwayAmount": 5.0, "SwaySpeed": 1.5}, {}),
    "Banner": ("card", "T_Bld_Banner", (16, 64), None, {"TeamMask": 1.0, "UpNormal": 0.35, "SwayAmount": 5.0, "SwaySpeed": 2.2}, {}),
    "Awning": ("card", "T_Bld_Awning", (32, 32), None, {"TeamMask": 1.0, "UpNormal": 0.0, "SwayAmount": 1.5, "SwaySpeed": 1.8}, {}),
    "Flame": ("card", "T_Bld_Flame", (16, 16), None, {"Glow": 9.0, "UpNormal": 1.0, "SwayAmount": 2.5, "SwaySpeed": 9.0}, {}),
}


def build_building():
    """M_Building (opaque) and M_BuildingCard (masked, two-sided), then one instance per mesh slot."""
    mat = get_material("M_Building")
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE)
    mat.set_editor_property("tangent_space_normal", False)
    g = G(mat)
    P = g.node(unreal.MaterialExpressionWorldPosition, world_position_shader_offset=unreal.WorldPositionIncludedOffsets.WPT_EXCLUDE_ALL_SHADER_OFFSETS)
    # height above the building's own origin (ObjectPositionWS is the bounds centre, no use for a ground line)
    local = g.node(unreal.MaterialExpressionTransformPosition,
                   transform_source_type=unreal.MaterialPositionTransformSource.TRANSFORMPOSSOURCE_WORLD,
                   transform_type=unreal.MaterialPositionTransformSource.TRANSFORMPOSSOURCE_LOCAL)
    g.link(P, local, "")
    pivot_z = g.node(unreal.MaterialExpressionComponentMask, r=False, g=False, b=True, a=False)
    g.link(local, pivot_z, "")
    team = g.vector("TeamColor", lin(0.05, 0.22, 0.8), "Per building (custom primitive data)", cpd=0)
    colour = g.custom(BUILDING_CODE, F3, [
        ("P", P), ("N", g.node(unreal.MaterialExpressionVertexNormalWS)),
        ("UV0", g.node(unreal.MaterialExpressionTextureCoordinate, coordinate_index=0)),
        ("UV1", g.node(unreal.MaterialExpressionTextureCoordinate, coordinate_index=1)),
        ("VCr", g.node(unreal.MaterialExpressionVertexColor), "R"), ("LocalZ", pivot_z), ("Team", team),
        ("Tex", g.tex("Tex", "T_Bld_Ashlar")), ("NormalTex", g.tex("NormalTex", "T_Bld_Flat_N", True)), ("MossTex", g.tex("MossTex", "T_GrassMoss")),
        ("Size", g.vector("Size", lin(128.0, 128.0, 0.0, 0.0), "Textures"), "RGBA"),
        ("Texel", g.scalar("TexelSize", 4.0, "Crunch")),
        ("WorldTop", g.scalar("WorldTop", 0.0, "Textures")),
        ("TeamMask", g.scalar("TeamMask", 0.0, "Team")), ("TeamBoost", g.scalar("TeamBoost", 2.0, "Team")),
        ("GlowMask", g.scalar("GlowMask", 0.0, "Glow")), ("Glow", g.scalar("Glow", 0.0, "Glow")),
        ("Damp", g.scalar("Damp", 0.5, "Weathering")), ("DampHeight", g.scalar("DampHeight", 150.0, "Weathering")),
        ("DampTint", g.vector("DampTint", lin(0.52, 0.5, 0.5), "Weathering"), "RGBA"),
        ("Bleach", g.scalar("Bleach", 0.3, "Weathering")), ("BleachDepth", g.scalar("BleachDepth", 110.0, "Weathering")),
        ("BleachTint", g.vector("BleachTint", lin(1.3, 1.26, 1.16), "Weathering"), "RGBA"),
        ("Moss", g.scalar("Moss", 0.0, "Weathering")), ("MossHeight", g.scalar("MossHeight", 90.0, "Weathering")),
        ("MossTop", g.scalar("MossTop", 0.0, "Weathering")), ("MossSlope", g.scalar("MossSlope", 0.84, "Weathering")),
        ("NormalStrength", g.scalar("NormalStrength", 1.0, "Surface")),
        ("Tint", g.vector("Tint", lin(1.0, 1.0, 1.0), "Surface"), "RGBA"),
    ], "Building surface: cm UVs, team / glow mask, texel-stepped weathering, normal map in the face's UV frame",
        outputs=[("OutNormal", F3), ("OutEmissive", F3)])
    g.out(colour, MP.MP_BASE_COLOR)
    g.out(colour, MP.MP_NORMAL, "OutNormal")
    g.out(colour, MP.MP_EMISSIVE_COLOR, "OutEmissive")
    g.out(g.scalar("Roughness", 0.84, "Surface"), MP.MP_ROUGHNESS)
    g.out(g.scalar("Specular", 0.3, "Surface"), MP.MP_SPECULAR)
    g.finish()

    card = get_material("M_BuildingCard")
    card.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
    card.set_editor_property("two_sided", True)
    card.set_editor_property("tangent_space_normal", False)
    card.set_editor_property("opacity_mask_clip_value", 0.3)
    g = G(card)
    P = g.node(unreal.MaterialExpressionWorldPosition, world_position_shader_offset=unreal.WorldPositionIncludedOffsets.WPT_EXCLUDE_ALL_SHADER_OFFSETS)
    uv1 = g.node(unreal.MaterialExpressionTextureCoordinate, coordinate_index=1)
    team = g.vector("TeamColor", lin(0.05, 0.22, 0.8), "Per building (custom primitive data)", cpd=0)
    time = g.node(unreal.MaterialExpressionTime)
    colour = g.custom(BUILDING_CARD_CODE, F3, [
        ("P", P), ("N", g.node(unreal.MaterialExpressionVertexNormalWS)), ("Side", g.node(unreal.MaterialExpressionTwoSidedSign)),
        ("UV0", g.node(unreal.MaterialExpressionTextureCoordinate, coordinate_index=0)), ("UV1", uv1),
        ("VCr", g.node(unreal.MaterialExpressionVertexColor), "R"), ("Team", team), ("Time", time),
        ("Tex", g.tex("Tex", "T_Bld_Wheat")),
        ("Size", g.vector("Size", lin(64.0, 32.0, 0.0, 0.0), "Textures"), "RGBA"),
        ("Texel", g.scalar("TexelSize", 4.0, "Crunch")),
        ("TeamMask", g.scalar("TeamMask", 0.0, "Team")), ("TeamBoost", g.scalar("TeamBoost", 2.0, "Team")),
        ("Glow", g.scalar("Glow", 0.0, "Glow")),
        ("RootShade", g.scalar("RootShade", 1.0, "Colour")), ("UpNormal", g.scalar("UpNormal", 0.0, "Colour")),
        ("Tint", g.vector("Tint", lin(1.0, 1.0, 1.0), "Colour"), "RGBA"),
    ], "Building card: cloth, crops, leaves, flame", outputs=[("OutAlpha", F1), ("OutNormal", F3), ("OutEmissive", F3)])
    weight = g.node(unreal.MaterialExpressionComponentMask, r=True, g=False, b=False, a=False)
    g.link(uv1, weight, "")
    sway = g.custom(BUILDING_SWAY, F3, [("P", P), ("Time", time), ("Weight", weight),
                                        ("Speed", g.scalar("SwaySpeed", 1.6, "Sway")), ("Amount", g.scalar("SwayAmount", 3.0, "Sway"))], "Wind sway")
    g.out(colour, MP.MP_BASE_COLOR)
    g.out(colour, MP.MP_OPACITY_MASK, "OutAlpha")
    g.out(colour, MP.MP_NORMAL, "OutNormal")
    g.out(colour, MP.MP_EMISSIVE_COLOR, "OutEmissive")
    g.out(sway, MP.MP_WORLD_POSITION_OFFSET)
    g.out(g.scalar("Roughness", 0.9, "Surface"), MP.MP_ROUGHNESS)
    g.out(g.const(0.12), MP.MP_SPECULAR)
    g.finish()

    for slot, (kind, tex, size, nrm, scalars, vectors) in BUILDING_SLOTS.items():
        textures = {"Tex": tex}
        if nrm:
            textures["NormalTex"] = nrm
        v = {"Size": lin(size[0], size[1], 0, 0)}
        v.update(vectors)
        make_instance("MI_Bld_" + slot, mat if kind == "opaque" else card, scalars=scalars, vectors=v, textures=textures)


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
        mel.set_material_instance_texture_parameter_value(mi, k, eal.load_asset(v if v.startswith("/") else TEX + v))
    mel.update_material_instance(mi)
    eal.save_loaded_asset(mi, False)
    print("built", path)



# ----------------------------------------------------------------------------- building placement overlay
def build_grid_cell():
    """One 1 m grid cell of the build overlay (an ISM of /Engine/BasicShapes/Plane). Colour and alpha per instance
    (PerInstanceCustomData 0..3), so free / blocked / footprint cells all share one draw call."""
    mat = get_material("M_GridCell")
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    mat.set_editor_property("two_sided", True)
    mat.set_editor_property("used_with_instanced_static_meshes", True)
    g = G(mat)
    chans = []
    for i, d in enumerate((0.3, 1.0, 0.4, 0.5)):
        e = g.node(unreal.MaterialExpressionPerInstanceCustomData, data_index=i)
        e.set_editor_property("const_default_value", d)
        chans.append(e)
    uv = g.node(unreal.MaterialExpressionTextureCoordinate)
    glow = g.scalar("Glow", 1.6, "Look")
    rgb = g.custom("return float3(R, G, B) * Glow;", F3, [("R", chans[0]), ("G", chans[1]), ("B", chans[2]), ("Glow", glow)], "Cell colour")
    a = g.custom(
        "float2 d = min(UV, 1.0 - UV);\n"
        "float e = min(d.x, d.y);\n"
        "float aa = max(fwidth(e), 0.002);\n"
        "float border = 1.0 - saturate((e - 0.045) / aa);\n"       # a thin bright frame round every cell
        "float inset = saturate((e - 0.0) / aa);\n"
        "return saturate(A) * inset * lerp(0.32, 1.0, border);",
        F1, [("UV", uv), ("A", chans[3])], "Cell alpha")
    g.out(rgb, MP.MP_EMISSIVE_COLOR)
    g.out(a, MP.MP_OPACITY)
    g.finish()


def build_ghost():
    """Placement ghost: the building's own mesh drawn as glowing glass, tinted green (fits) or red (blocked).
    Colour comes from custom primitive data 0..2, opacity from 3."""
    # (named M_PlacementGhost: an older M_Ghost asset failed to compile on Metal and cannot be rebuilt in place)
    mat = get_material("M_PlacementGhost")
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    mat.set_editor_property("two_sided", False)
    mat.set_editor_property("used_with_static_lighting", False)
    g = G(mat)
    color = g.vector("Color", lin(0.3, 1.0, 0.45), "Contract", cpd=0)
    opacity = g.scalar("Opacity", 0.42, "Contract", cpd=3)
    fres = g.node(unreal.MaterialExpressionFresnel)
    wp = g.node(unreal.MaterialExpressionWorldPosition)
    rgb = g.custom(
        "float band = frac(P.z / 24.0 - Time * 0.6);\n"            # slow rising scanlines read as 'not built yet'
        "float scan = smoothstep(0.0, 0.08, band) * (1.0 - smoothstep(0.12, 0.2, band));\n"
        "return Color * (0.55 + Fr * 1.4 + scan * 0.5);",
        F3, [("Color", color), ("Fr", fres), ("P", wp), ("Time", g.node(unreal.MaterialExpressionTime))], "Ghost colour")
    a = g.custom("return saturate(Opacity * (0.6 + Fr * 0.9));", F1, [("Opacity", opacity), ("Fr", fres)], "Ghost alpha")
    g.out(rgb, MP.MP_EMISSIVE_COLOR)
    g.out(a, MP.MP_OPACITY)
    g.finish()

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
if not ONLY or "building" in ONLY:
    build_building()
if not ONLY or "placement" in ONLY or "gridcell" in ONLY:
    build_grid_cell()
if not ONLY or "placement" in ONLY or "ghost" in ONLY:
    build_ghost()
if not ONLY or "sprite" in ONLY:
    sprite_m, sprite_shadow_m = build_sprite()
    make_sprite_instances(sprite_m, sprite_shadow_m)
