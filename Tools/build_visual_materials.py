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


MAP_SFX = {"two": "", "four": "4"}       # the maps (Tools/world/gen_battlefield.py --map): suffix of their layout, textures, mesh folder


def _layout(sfx=""):
    import json as _json
    with open(os.path.join(os.path.abspath(unreal.Paths.project_dir()), "SourceArt", "World", "layout%s.json" % sfx)) as f:
        return _json.load(f)


def _splat_rect(sfx=""):
    """World origin and size of a map's ground splat map, from the generator's layout (falls back to the old small map)."""
    try:
        sp = _layout(sfx)["splat"]
        return (float(sp["origin"][0]), float(sp["origin"][1]), float(sp["size"]), 0.0)
    except Exception:
        return (-5600.0, -6144.0, 12288.0, 0.0)

def _relief(sfx=""):
    """(rock line, snow line) in cm, from the generator's layout: where M_Terrain's bare rock and snow start."""
    try:
        r = _layout(sfx)["relief"]
        return float(r["rock_line"]), float(r["snow_line"])
    except Exception:
        return 3300.0, 6200.0


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
# Shared HLSL for the natural-world materials: value noise, and sampling a photographic texture on the world's texel
# grid. Q() is SRPix.S's seam without the sample: texel coordinates that stay constant inside a texel and blend across
# its edge over one screen pixel, so a texture of any scale laid through it comes out in the same crisp 4 cm texels
# as the pixel art, and does not crawl.
NAT = r"""
struct SRNat
{
	float h(float2 p) { float3 p3 = frac(float3(p.xyx) * 0.1031); p3 += dot(p3, p3.yzx + 33.33); return frac((p3.x + p3.y) * p3.z); }
	float v(float2 p)
	{
		float2 i = floor(p), f = frac(p);
		f = f * f * (3.0 - 2.0 * f);
		return lerp(lerp(h(i), h(i + float2(1, 0)), f.x), lerp(h(i + float2(0, 1)), h(i + float2(1, 1)), f.x), f.y);
	}
	float fbm(float2 p) { return v(p) * 0.55 + v(p * 2.13 + 17.0) * 0.3 + v(p * 4.7 + 41.0) * 0.15; }
	float2 Q(float2 uv) { float2 fw = max(fwidth(uv), 1e-5); float2 seam = floor(uv + 0.5); return seam + clamp((uv - seam) / fw, -0.5, 0.5); }
	float Q1(float u) { float fw = max(fwidth(u), 1e-5); float seam = floor(u + 0.5); return seam + clamp((u - seam) / fw, -0.5, 0.5); }
	float4 T2(Texture2D T, float2 uv, float2 dx, float2 dy) { return T.SampleGrad(View.SharedTrilinearWrappedSampler, uv, dx, dy); }
	float3 nrm(float4 s) { float2 xy = s.xy * 2.0 - 1.0; return float3(xy, sqrt(saturate(1.0 - dot(xy, xy)))); }
	float lum(float3 c) { return dot(c, float3(0.3, 0.59, 0.11)); }
};
SRNat nt;
"""

TERRAIN_CODE = PIX + NAT + r"""
float T = max(Texel, 0.5);
float3 col;
float land = step(1.5, UV1.y);                                   // the smooth land (gen_battlefield.py's heightfield): UV1.y = 2
float3 up = lerp(float3(0, 0, 1), normalize(N), land);           // the surface's own normal: straight up on a deck's top, the slope's on the land
float3 nrm = up;
float rough = 0.95;
float spec = 0.25;
if (N.z > 0.5 || land > 0.5)
{
	// ---- top: world-aligned. Texture 'up' is world +X (up the screen), so blades stand toward the horizon.
	float2 uv = float2(P.y, -P.x) / T;
	float2 tc = floor(uv) + 0.5;                                   // this texel
	float2 wc = float2(-tc.y, tc.x) * T;                            // its world XY
	float2 q = nt.Q(uv);                                           // the texel grid, for the photographic layers
	float2 gx = ddx(uv), gy = ddy(uv);
	float2 muv = (wc - SplatRect.xy) / SplatRect.z;
	float4 sp = Splat.SampleLevel(View.SharedBilinearClampedSampler, muv, 0);
	float damp = FlowMap.SampleLevel(View.SharedBilinearClampedSampler, muv, 0).a;      // 1 at the water's edge .. 0 three metres back
	float hx = px.h(tc);
	// three sizes of drifting difference in the turf: whole meadows, patches, tussocks
	float n1 = nt.fbm(wc / 5200.0), n2 = nt.fbm(wc / 1300.0 + 7.3), n3 = nt.v(wc / 230.0 + 3.1);
	float highflat = saturate((P.z - 500.0) / 900.0) * saturate((up.z - 0.975) / 0.02);
	float3 g0 = px.S(Grass, uv, 128).rgb;
	float tip = saturate((px.lum(px.Texel(Grass, uv, 128).rgb) - 0.06) / 0.12);      // 0 thatch .. 1 blade tip, per texel (T_Grass spans 0.062 .. 0.185)
	col = g0;
	// moss and straw take over tuft by tuft (blade tips hold out longest), never as a soft blend. Moss also creeps
	// over level high ground and damp banks; straw into the parched patches.
	if (sp.g + highflat * (n2 - 0.25) * 0.9 + damp * 0.3 > 0.5 + (hx - 0.5) * 0.35 + (tip - 0.5) * 0.2) col = px.S(GrassMoss, uv, 128).rgb;
	if (sp.b + saturate(0.34 - n1) * 1.6 * (1.0 - damp) > 0.5 + (hx - 0.5) * 0.35 - (tip - 0.5) * 0.2) col = px.S(GrassDry, uv, 128).rgb;
	// photographic layers on the same texels: real turf's light and dark, an aerial photograph's wide blotches
	float kg = T / GrassTile, km = T / MacroTile;
	float3 gd = nt.T2(GrassD, q * kg, gx * kg, gy * kg).rgb;
	col *= lerp(1.0, clamp(nt.lum(gd) / 0.235, 0.55, 1.6), GrassDetail);
	float3 mg = nt.T2(MacroD, q * km, gx * km, gy * km).rgb / float3(0.168, 0.119, 0.03);
	col *= lerp(float3(1, 1, 1), clamp(mg, 0.55, 1.7), MacroStrength * float3(1.0, 1.0, 0.35));
	col *= 1.0 + ((n2 - 0.5) * 0.34 + (n3 - 0.5) * 0.14) * Variation;
	col = lerp(col, col * LushTint.rgb, saturate((n1 - 0.5) * 3.2) * Variation);
	col = lerp(col, col * ParchedTint.rgb, saturate((0.46 - n1) * 3.2 + (n2 - 0.62) * 1.5) * Variation);
	// clover in drifts (deeper, bluer green), and flowers scattered through it: white, butter yellow, violet
	float pm = smoothstep(0.56, 0.72, nt.fbm(wc / 900.0 + 31.0)) * (1.0 - saturate(sp.r * 5.0)) * (1.0 - sp.b);
	col = lerp(col, col * CloverTint.rgb, pm * 0.55);
	float2 fc = floor(tc / 2.0);
	if (px.h(fc + 91.0) > 1.0 - Flowers * (0.12 + pm) && tip > 0.25)
	{
		float k = px.h(fc + 13.0);
		col = (k < 0.45 ? float3(0.62, 0.6, 0.5) : (k < 0.8 ? float3(0.7, 0.5, 0.09) : float3(0.3, 0.2, 0.52))) * FlowerBright;
	}
	float3 gn = nt.nrm(nt.T2(GrassN, q * kg, gx * kg, gy * kg));
	nrm = normalize(up + float3(-gn.y, gn.x, 0.0) * GrassNormal);
	// the forest floor: under a closed canopy leaf litter takes the turf over texel by texel (blade tips hold out
	// longest, so the wood's edge is ragged grass, never a line); the ground under and round a wood lies in its shade
	float4 fo = ForestMap.SampleLevel(View.SharedBilinearClampedSampler, muv, 0);
	if (fo.r * 1.3 + (n3 - 0.5) * 0.4 > 0.46 + (hx - 0.5) * 0.42 + tip * 0.2)
	{
		float kf = T / ForestTile;
		col = nt.T2(ForestD, q * kf, gx * kf, gy * kf).rgb * ForestTint.rgb * (1.0 + (n2 - 0.5) * 0.36 + (hx - 0.5) * 0.12);
		float3 fn = nt.nrm(nt.T2(ForestN, q * kf, gx * kf, gy * kf));
		nrm = normalize(up + float3(-fn.y, fn.x, 0.0) * 0.8);
		rough = 0.92;
	}
	col *= lerp(1.0, ForestShade, fo.g);
	// road: the verge yellows and thins; then bare earth, with grass tips poking into its edge; then stones, joints dissolving first
	float r = sp.r;
	float rt = 0.2 + tip * 0.22 + (hx - 0.5) * 0.1;
	col = lerp(col, col * float3(1.16, 1.0, 0.7), saturate(r / 0.22) * 0.45);
	float kp = T / PebbleTile;
	float3 pb = nt.T2(PebblesD, q * kp, gx * kp, gy * kp).rgb;
	float3 pn = nt.nrm(nt.T2(PebblesN, q * kp, gx * kp, gy * kp));
	if (r > rt)
	{
		col = px.S(Dirt, uv, 128).rgb * clamp(nt.lum(pb) / 0.16, 0.6, 1.5) * (1.0 + (n2 - 0.5) * 0.3 + (n3 - 0.5) * 0.18);
		col = lerp(col, col * float3(0.86, 0.9, 1.0), saturate((n1 - 0.5) * 2.5));         // cooler, greyer earth in places
		nrm = px.S(DirtN, uv, 128).xyz * 2.0 - 1.0;
		nrm.xy += pn.xy * 0.8;
		rough = 0.9;
		float3 cb = px.Texel(Cobble, uv, 128).rgb;
		float body = saturate((px.lum(cb) - 0.05) / 0.2);          // 0 in the joints .. 1 on a stone's face
		if (r > 0.9 - body * 0.32)
		{
			col = px.S(Cobble, uv, 128).rgb * (1.0 + (n3 - 0.5) * 0.2);
			nrm = px.S(CobbleN, uv, 128).xyz * 2.0 - 1.0;
			rough = StoneRoughness;
		}
		nrm = normalize(up * nrm.z + float3(-nrm.y * NormalStrength, nrm.x * NormalStrength, 0.0));
	}
	// wet ground by the water: dark, sheened soil, mud and leaf litter right at the edge (texel by texel)
	float wet = saturate(damp * 1.3 - 0.12 + (hx - 0.5) * 0.14);
	if (damp > 0.66 + (hx - 0.5) * 0.3 + tip * 0.1 && r <= 0.9)
	{
		float ku = T / MudTile;
		col = nt.T2(MudD, q * ku, gx * ku, gy * ku).rgb * MudTint.rgb;
		nrm = normalize(up + float3(-pn.y, pn.x, 0.0) * 0.5);
	}
	col *= lerp(1.0, WetDark, wet);
	rough = lerp(rough, WetRough, wet * wet);
	spec = lerp(spec, 0.5, wet * wet);
	// The land's slopes: turf holds on what troops can walk; a mountainside is living rock, and where one turns into
	// the other the turf breaks: a worn, darker lip of stony earth and scree above the rock's edge. The rock is an
	// aerial photograph of crags laid on from above, strata from the side where the face stands up, on the world's
	// own texels in all three axes (never drawn out down the slope); ledges and beds follow the contours.
	if (land > 0.5)
	{
		float edge = RockSlope + (n3 - 0.5) * 0.06 + (hx - 0.5) * 0.05 - tip * 0.02;
		float lipw = saturate((edge + LipWidth - N.z) / LipWidth);                        // 0 on sound turf .. 1 at the rock's edge
		if (r <= rt && lipw > 0.0)
		{
			col *= lerp(1.0, LipDark, lipw);
			if (lipw > px.h(tc + 7.0) * 0.85 + 0.1)
			{
				col = pb * ScreeTint.rgb * (0.75 + 0.5 * hx);
				nrm = normalize(up + float3(-pn.y, pn.x, 0.0) * 0.9);
				rough = 0.88;
			}
		}
		float bare = step(RockLine + (hx - 0.5) * 300.0 + tip * 90.0, P.z);               // above the tree line: all rock
		if (N.z < edge || bare > 0.5)
		{
			float3 Pq = float3(nt.Q(P.xy / T), nt.Q1(P.z / T)) * T;                         // this texel in all three axes
			float3 dPx = ddx(P), dPy = ddy(P);
			float2 tuv = Pq.xy / RockTile.x;
			float3 rtop = nt.T2(RockTopD, tuv, dPx.xy / RockTile.x, dPy.xy / RockTile.x).rgb;
			float3 ntop = nt.nrm(nt.T2(RockTopN, tuv, dPx.xy / RockTile.x, dPy.xy / RockTile.x));
			// The side view runs along one of the two diagonals (x + y or x - y), whichever the face is not edge-on to:
			// a coordinate that never stalls on any wall, and only changes over where the smooth normal crosses an axis.
			float dg = step(0.0, N.x * N.y) * 2.0 - 1.0;
			float2 suv = float2((Pq.x - dg * Pq.y) * 0.75, -Pq.z) / RockTile.y;
			float2 sdx = float2((dPx.x - dg * dPx.y) * 0.75, -dPx.z) / RockTile.y, sdy = float2((dPy.x - dg * dPy.y) * 0.75, -dPy.z) / RockTile.y;
			float3 Ng = normalize(cross(dPy, dPx));                                        // the triangle's own lean: a cliff's vertices lean back, its face does not
			Ng *= sign(Ng.z + 1e-6);
			float3 rside = nt.T2(RockSideD, suv, sdx, sdy).rgb;
			float3 nside = nt.nrm(nt.T2(RockSideN, suv, sdx, sdy));
			rside = lerp(rside, nt.lum(rside) * SideTint.rgb, SideTint.a);
			float sw = 1.0 - smoothstep(0.58, 0.8, min(N.z, Ng.z));                                   // 0 leaning back .. 1 standing up (never smoothstep(hi, lo): Metal leaves that undefined)
			rtop = lerp(rtop, nt.lum(rtop) * float3(1.0, 0.98, 0.94), 0.4) * RockTopGain;     // the photograph's moss, held back: the lichen layer does that here
			col = lerp(rtop, rside, sw) * RockFaceTint;
			float side = step(0.5, sw);                                                    // the fine grain: from above, or from the side once the face stands up
			float2 duv = lerp(Pq.xy, suv * RockTile.y, side) / RockTile.z;
			float3 rdet = nt.T2(RockDetailD, duv, lerp(dPx.xy, sdx * RockTile.y, side) / RockTile.z, lerp(dPy.xy, sdy * RockTile.y, side) / RockTile.z).rgb;
			col *= lerp(1.0, clamp(nt.lum(rdet) / 0.17, 0.45, 1.7), 0.85);
			// beds and ledges along the contours, warped so they are never ruled lines
			float zz = Pq.z + nt.fbm(Pq.xy / 1100.0) * 300.0 + nt.v(Pq.xy / 170.0) * 30.0;
			float bed = nt.v(float2(zz / 85.0, 3.7));
			col *= 1.0 + (bed - 0.5) * Strata * (0.35 + 0.65 * sw);
			float ledge = smoothstep(0.0, 0.09, frac(zz / LedgeCm)) * (1.0 - smoothstep(0.94, 1.0, frac(zz / LedgeCm)));
			col *= lerp(1.0 - LedgeDark * (0.3 + 0.7 * sw), 1.0, ledge);
			float3 bump = lerp(float3(ntop.x, ntop.y, 0.0), float3(0.707, -0.707 * dg, 0.0) * nside.x + float3(0, 0, -1) * nside.y, sw);
			nrm = normalize(up + bump * RockNormal);
			rough = StoneRoughness + 0.14;
			spec = 0.3;
			// lichen and moss where the rock looks at the sky and the air is damp
			float mossy = saturate((N.z - MossSlope) / 0.1) * saturate(nt.fbm(wc / 620.0 + 5.0) * 2.6 - 0.75 + sp.g * 0.8) * (1.0 - bare);
			if (mossy > hx * 0.7 + 0.12)
			{
				float kl = 1.0 / RockTile.w;
				col = lerp(col, nt.T2(LichenD, Pq.xy * kl, dPx.xy * kl, dPy.xy * kl).rgb * LichenTint.rgb, 0.8);
				if (mossy > hx * 0.5 + 0.5) col = px.S(GrassMoss, uv, 128).rgb * 0.85;
				rough = 0.93;
			}
			float high = saturate((P.z - RockLine * 0.6) / (RockLine * 1.4));              // high rock is colder and greyer
			col = lerp(col, px.lum(col) * float3(1.02, 1.04, 1.1) * 1.08, high * 0.7);
		}
	}
	if (P.z > SnowLine + (hx - 0.5) * 420.0 && (land < 0.5 || N.z > 0.62 + (hx - 0.5) * 0.1))
	{
		col = px.S(Snow, uv, 128).rgb;                              // snow lies where the rock is not too steep to hold it
		nrm = normalize(lerp(up, nrm, 0.35));
		rough = 0.55;
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
	float topZ = P.z + UV0.y;
	float lipMax = min(23.0, wallH / T * LipFraction);
	if (topZ > RockLine + 150.0 && topZ <= SnowLine) lipMax = 0.0;
	if (uv.y < lipMax)
	{
		float4 lp = px.S(Lip, float2(uv.x, min(uv.y, 23.4)), float2(128, 24));
		if (topZ > SnowLine) lp.rgb = px.S(Snow, uv, 128).rgb;
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
OutSpec = spec;
return col * Tint;
"""

NTEX = TEX + "Nature/"
NORMAL = unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL


def build_terrain():
    _data_map("T_WaterFlow")
    _data_map("T_Forest")
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
        ("Lip", g.tex("Lip", "T_Lip")), ("Splat", g.tex("Splat", "T_Splat", True)), ("FlowMap", g.tex("FlowMap", "T_WaterFlow", True)),
        ("Snow", g.tex("Snow", "T_Snow")),
        # the photographic layers (CC0, Docs/ASSET_CREDITS.md), laid on the world's texel grid
        ("GrassD", g.tex("NatureGrass", NTEX + "T_N_Grass_D", group="Nature")), ("GrassN", g.tex("NatureGrassNormal", NTEX + "T_N_Grass_N", group="Nature", sampler=NORMAL)),
        ("MacroD", g.tex("NatureMacro", NTEX + "T_N_AerialGrass_D", group="Nature")),
        ("PebblesD", g.tex("NaturePebbles", NTEX + "T_N_Pebbles_D", group="Nature")), ("PebblesN", g.tex("NaturePebblesNormal", NTEX + "T_N_Pebbles_N", group="Nature", sampler=NORMAL)),
        ("MudD", g.tex("NatureMud", NTEX + "T_N_Mud_D", group="Nature")),
        # the forest floor: T_Forest (gen_battlefield.py > build_forest_map: R = how closed the canopy is, G = its shade)
        ("ForestMap", g.tex("ForestMap", "T_Forest", True)),
        ("ForestD", g.tex("NatureForest", NTEX + "T_N_Forest_D", group="Nature")), ("ForestN", g.tex("NatureForestNormal", NTEX + "T_N_Forest_N", group="Nature", sampler=NORMAL)),
        ("ForestTile", g.scalar("ForestTile", 4096.0, "Forest")), ("ForestTint", g.vector("ForestTint", lin(0.82, 0.74, 0.6), "Forest"), "RGB"),
        ("ForestShade", g.scalar("ForestShade", 0.8, "Forest")),
        ("RockTopD", g.tex("RockTop", NTEX + "T_N_AerialRock_D", group="Nature")), ("RockTopN", g.tex("RockTopNormal", NTEX + "T_N_AerialRock_N", group="Nature", sampler=NORMAL)),
        ("RockSideD", g.tex("RockSide", NTEX + "T_N_Cliff_D", group="Nature")), ("RockSideN", g.tex("RockSideNormal", NTEX + "T_N_Cliff_N", group="Nature", sampler=NORMAL)),
        ("RockDetailD", g.tex("RockDetail", NTEX + "T_N_RockFace_D", group="Nature")), ("LichenD", g.tex("Lichen", NTEX + "T_N_MossRock_D", group="Nature")),
        # cm a texture spans. Texel density (one texture pixel per 4 cm texel) is its size x 4: 4096 for a 1k, 8192 for a 2k.
        ("GrassTile", g.scalar("GrassTile", 4096.0, "Nature")), ("MacroTile", g.scalar("MacroTile", 19000.0, "Nature")),
        ("PebbleTile", g.scalar("PebbleTile", 4096.0, "Nature")), ("MudTile", g.scalar("MudTile", 4096.0, "Nature")),
        # RockTile: X = the crags from above, Y = the strata from the side, Z = the fine detail, W = the lichen
        ("RockTile", g.vector("RockTile", lin(5200.0, 2400.0, 1100.0, 4096.0), "Rock"), "RGBA"),
        ("GrassDetail", g.scalar("GrassDetail", 0.6, "Turf")), ("GrassNormal", g.scalar("GrassNormal", 0.55, "Turf")),
        ("MacroStrength", g.scalar("MacroStrength", 0.5, "Turf")), ("Variation", g.scalar("Variation", 0.85, "Turf")),
        ("LushTint", g.vector("LushTint", lin(0.8, 1.04, 0.82), "Turf"), "RGB"), ("ParchedTint", g.vector("ParchedTint", lin(1.14, 1.05, 0.8), "Turf"), "RGB"),
        ("CloverTint", g.vector("CloverTint", lin(0.7, 1.1, 0.8), "Turf"), "RGB"),
        ("Flowers", g.scalar("Flowers", 0.012, "Turf")), ("FlowerBright", g.scalar("FlowerBright", 0.9, "Turf")),
        ("MudTint", g.vector("MudTint", lin(0.55, 0.5, 0.42), "Wet"), "RGB"), ("WetDark", g.scalar("WetDark", 0.58, "Wet")), ("WetRough", g.scalar("WetRough", 0.3, "Wet")),
        # where bare rock and snow start (cm above the field), from gen_battlefield.py's layout
        ("RockLine", g.scalar("RockLine", _relief()[0], "Relief")), ("SnowLine", g.scalar("SnowLine", _relief()[1], "Relief")),
        ("RockFaceTint", g.vector("RockFaceTint", lin(1.04, 1.02, 0.98), "Rock"), "RGB"),         # warms the rock toward the masonry's sandstone
        ("RockTopGain", g.scalar("RockTopGain", 1.5, "Rock")),
        ("SideTint", g.vector("SideTint", unreal.LinearColor(0.74, 0.7, 0.64, 0.86), "Rock"), "RGBA"),   # the strata, pulled from orange to this (A = how far)
        ("RockNormal", g.scalar("RockNormal", 2.0, "Rock")), ("Strata", g.scalar("Strata", 0.42, "Rock")),
        ("LedgeCm", g.scalar("LedgeCm", 230.0, "Rock")), ("LedgeDark", g.scalar("LedgeDark", 0.42, "Rock")),
        ("MossSlope", g.scalar("MossSlope", 0.7, "Rock")), ("LichenTint", g.vector("LichenTint", lin(0.9, 0.95, 0.7), "Rock"), "RGB"),
        ("ScreeTint", g.vector("ScreeTint", lin(0.6, 0.56, 0.48), "Rock"), "RGB"),
        ("LipWidth", g.scalar("LipWidth", 0.07, "Rock")), ("LipDark", g.scalar("LipDark", 0.62, "Rock")),
        # the land's rock: where the surface normal's Z falls under this (0.86 = a slope of 0.6), turf gives way to rock
        ("RockSlope", g.scalar("RockSlope", 0.86, "Relief")),
        ("Texel", g.scalar("TexelSize", 4.0, "Crunch")),
        # SplatRect: XY = world origin of the splat map (and of T_WaterFlow), Z = its world size (cm). Written by gen_battlefield.py's layout.
        ("SplatRect", g.vector("SplatRect", lin(*_splat_rect()), "Splat"), "RGBA"),
        ("NormalStrength", g.scalar("NormalStrength", 1.0, "Surface")),
        ("StoneRoughness", g.scalar("StoneRoughness", 0.72, "Surface")),
        ("FootShade", g.scalar("FootShade", 0.6, "Shading")),
        ("LipShadow", g.scalar("LipShadow", 0.4, "Shading")),
        ("LipFraction", g.scalar("LipFraction", 0.55, "Shading")),
        ("TintRange", g.scalar("TintRange", 0.08, "Shading")),
        ("Tint", g.vector("Tint", lin(1.0, 1.0, 1.0), "Shading")),
    ]
    colour = g.custom(TERRAIN_CODE, F3, params, "Terrain: turf, road, wet banks, rock and its broken lip, snow; deck sides",
                      outputs=[("OutNormal", F3), ("OutRough", F1), ("OutSpec", F1)])
    g.out(colour, MP.MP_BASE_COLOR)
    g.out(colour, MP.MP_NORMAL, "OutNormal")
    g.out(colour, MP.MP_ROUGHNESS, "OutRough")
    g.out(colour, MP.MP_SPECULAR, "OutSpec")
    g.finish()
    return mat


# M_Rock: boulders, scree, standing stones. The mountains' rock again (photographic, on the world's texels, from
# three sides), so a stone lying on a mountainside is the same stuff as the face under it; lichen and moss on top.
ROCK_CODE = PIX + NAT + r"""
float T = max(Texel, 0.5);
float3 n = normalize(N);
float3 Pq = float3(nt.Q(P.xy / T), nt.Q1(P.z / T)) * T;
float3 dPx = ddx(P), dPy = ddy(P);
float3 w = pow(abs(n), 4.0);
w /= (w.x + w.y + w.z);
float k = 1.0 / Tile;
float3 cx = nt.T2(RockD, Pq.yz * k, dPx.yz * k, dPy.yz * k).rgb;
float3 cy = nt.T2(RockD, Pq.xz * k, dPx.xz * k, dPy.xz * k).rgb;
float3 cz = nt.T2(RockD, Pq.xy * k, dPx.xy * k, dPy.xy * k).rgb;
float3 col = (cx * w.x + cy * w.y + cz * w.z) * Tint.rgb;
float3 tx = nt.nrm(nt.T2(RockN, Pq.yz * k, dPx.yz * k, dPy.yz * k));
float3 ty = nt.nrm(nt.T2(RockN, Pq.xz * k, dPx.xz * k, dPy.xz * k));
float3 tz = nt.nrm(nt.T2(RockN, Pq.xy * k, dPx.xy * k, dPy.xy * k));
float3 bump = float3(0.0, tx.x, tx.y) * w.x + float3(ty.x, 0.0, ty.y) * w.y + float3(tz.x, tz.y, 0.0) * w.z;
float3 nrm = normalize(n + bump * NormalStrength);
float rough = Rough;
float2 tc = floor(float2(P.y, -P.x) / T) + 0.5;
float hx = px.h(tc);
float mossy = saturate((n.z - lerp(1.02, MossSlope, Moss)) / 0.12) * saturate(nt.fbm(P.xy / 300.0 + 5.0) * 2.2 - 0.35);
if (mossy > hx * 0.6 + 0.1)
{
	float kl = 1.0 / 4096.0;
	col = lerp(col, nt.T2(LichenD, Pq.xy * kl, dPx.xy * kl, dPy.xy * kl).rgb * LichenTint.rgb, 0.85);
	if (mossy > hx * 0.5 + 0.45) col = px.S(MossTex, float2(P.y, -P.x) / T, 128).rgb * 0.9;
	rough = 0.93;
}
col *= lerp(1.0 - FootShade, 1.0, saturate((P.z - PivotZ + 4.0) / 36.0));        // grounded: darker where the piece meets the turf
OutNormal = nrm;
OutRough = rough;
return col;
"""


def build_rock():
    mat = get_material("M_Rock")
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE)
    mat.set_editor_property("tangent_space_normal", False)
    mel.set_base_material_usage(mat, unreal.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES)
    g = G(mat)
    P = g.node(unreal.MaterialExpressionWorldPosition, world_position_shader_offset=unreal.WorldPositionIncludedOffsets.WPT_EXCLUDE_ALL_SHADER_OFFSETS)
    obj = g.node(unreal.MaterialExpressionObjectPositionWS)
    pivot_z = g.node(unreal.MaterialExpressionComponentMask, r=False, g=False, b=True, a=False)
    g.link(obj, pivot_z, "")
    params = [
        ("P", P), ("N", g.node(unreal.MaterialExpressionVertexNormalWS)), ("PivotZ", pivot_z),
        ("RockD", g.tex("Rock", NTEX + "T_N_RockFace_D")), ("RockN", g.tex("RockNormal", NTEX + "T_N_RockFace_N", sampler=NORMAL)),
        ("LichenD", g.tex("Lichen", NTEX + "T_N_MossRock_D")), ("MossTex", g.tex("MossTex", "T_GrassMoss")),
        ("Tile", g.scalar("Tile", 1500.0, "Rock")), ("Texel", g.scalar("TexelSize", 4.0, "Crunch")),
        ("NormalStrength", g.scalar("NormalStrength", 1.2, "Rock")), ("Rough", g.scalar("Roughness", 0.86, "Surface")),
        ("Moss", g.scalar("Moss", 1.0, "Moss")), ("MossSlope", g.scalar("MossSlope", 0.62, "Moss")),
        ("LichenTint", g.vector("LichenTint", lin(0.9, 0.95, 0.7), "Moss"), "RGB"),
        ("FootShade", g.scalar("FootShade", 0.4, "Shading")),
        ("Tint", g.vector("Tint", lin(0.95, 0.9, 0.82), "Shading"), "RGB"),
    ]
    colour = g.custom(ROCK_CODE, F3, params, "Rock: the mountains' stone from three sides, lichen and moss on top", outputs=[("OutNormal", F3), ("OutRough", F1)])
    g.out(colour, MP.MP_BASE_COLOR)
    g.out(colour, MP.MP_NORMAL, "OutNormal")
    g.out(colour, MP.MP_ROUGHNESS, "OutRough")
    g.out(g.scalar("Specular", 0.3, "Surface"), MP.MP_SPECULAR)
    g.finish()
    return mat


# ----------------------------------------------------------------------------- props (rocks, masonry, timber)
# ----------------------------------------------------------------------------- fade near the camera
def near_fade(g, P, near=450.0, far=800.0):
    """1 where the surface is whole, 0 where it is dithered away: masonry and timber the camera has come right up to
    (nearer than `near` cm it is gone, beyond `far` whole) thin out like the tree crowns do, so the closest zooms at the
    shallow camera angles look past a wall that stands between the camera and its focus instead of into it. The camera
    is 9.5 m from its focus at its closest, so nothing at the focus, and nothing at all from the ordinary zooms, fades."""
    return g.custom(
        "float d = length(P - Cam);\n"
        "float f = saturate((d - Fade.x) / max(Fade.y - Fade.x, 1.0));\n"
        "float2 sp = Parameters.SvPosition.xy + float(View.StateFrameIndexMod8) * float2(5.588, 3.167);\n"
        "float ign = frac(52.9829189 * frac(dot(sp, float2(0.06711056, 0.00583715))));\n"
        "return f >= 0.999 ? 1.0 : step(ign, f);", F1, [
            ("P", P), ("Cam", g.node(unreal.MaterialExpressionCameraPositionWS)),
            ("Fade", g.vector("CameraFade", lin(near, far, 0.0, 0.0), "Fade"), "RGBA")], "Fade near the camera (dithered)")


PROP_CODE = PIX + r"""
float T = max(Texel, 0.5);
float2 uv = UV0 / T;
float3 col = VCb > 0.5 ? px.S(TexA, uv, SizeA.xy).rgb : px.S(TexB, uv, SizeB.xy).rgb;
// moss / turf settling on up-facing stone, texel by texel
// turf settles on up-facing facets, a whole facet at a time (no dither: a facet is either mossed over or bare)
float3 nrm = N;
if (Moss > 0.0 && N.z > lerp(1.02, MossSlope, Moss))
{
	col = px.S(MossTex, float2(P.y, -P.x) / T, 128).rgb;
}
else
{
	// Relief: the pixel art's own light and dark read as height (joints and cracks sunk, faces proud), one flat tilt a
	// texel, through the face's own UV frame (flat-shaded pieces: no tangents needed). The low sun then picks the
	// courses and the grain out instead of lying flat on them.
	float hl, hr, hd, hu;
	if (VCb > 0.5)
	{
		hl = px.lum(px.Texel(TexA, uv + float2(-1, 0), SizeA.xy).rgb); hr = px.lum(px.Texel(TexA, uv + float2(1, 0), SizeA.xy).rgb);
		hd = px.lum(px.Texel(TexA, uv + float2(0, -1), SizeA.xy).rgb); hu = px.lum(px.Texel(TexA, uv + float2(0, 1), SizeA.xy).rgb);
	}
	else
	{
		hl = px.lum(px.Texel(TexB, uv + float2(-1, 0), SizeB.xy).rgb); hr = px.lum(px.Texel(TexB, uv + float2(1, 0), SizeB.xy).rgb);
		hd = px.lum(px.Texel(TexB, uv + float2(0, -1), SizeB.xy).rgb); hu = px.lum(px.Texel(TexB, uv + float2(0, 1), SizeB.xy).rgb);
	}
	float2 grad = clamp(float2(hr - hl, hu - hd) * Relief, -0.9, 0.9);
	float3 dpx = ddx(P); float3 dpy = ddy(P);
	float2 dux = ddx(UV0); float2 duy = ddy(UV0);
	float det = dux.x * duy.y - dux.y * duy.x;
	if (abs(det) > 1e-10 && Relief > 0.0)
	{
		float sgn = det < 0.0 ? -1.0 : 1.0;
		float3 Tu = (dpx * duy.y - dpy * dux.y) * sgn;
		float3 Tv = (dpy * dux.x - dpx * duy.x) * sgn;
		Tu = normalize(Tu - N * dot(Tu, N));
		Tv = normalize(Tv - N * dot(Tv, N));
		nrm = normalize(N - Tu * grad.x - Tv * grad.y);
	}
	// Weathering in whole texels, like the buildings': a slow blotch so no boundary runs level, a hash to dither the seam.
	float2 tc = floor(uv);
	float hx = px.h(tc);
	float2 q = tc / 22.0;
	float2 qi = floor(q);
	float2 qf = q - qi;
	qf = qf * qf * (3.0 - 2.0 * qf);
	float bl = lerp(lerp(px.h(qi), px.h(qi + float2(1, 0)), qf.x), lerp(px.h(qi + float2(0, 1)), px.h(qi + float2(1, 1)), qf.x), qf.y);
	col *= 1.0 + (bl - 0.5) * Blotch;                                        // stone and timber are never one tone
	float hgt = P.z - PivotZ;
	float d = saturate(1.0 - hgt / max(DampHeight * (0.5 + bl), 1.0));        // damp and dirt climbing from the turf
	d = floor(d * 3.0 + 0.5 + (hx - 0.5) * 0.4) / 3.0;
	col *= lerp(float3(1, 1, 1), DampTint.rgb, d * Damp);
	float up = saturate((N.z - 0.35) / 0.5);                                 // faces that look at the sky bleach
	col = lerp(col, col * BleachTint.rgb, floor(up * 2.0 + 0.5 + (hx - 0.5) * 0.4) / 2.0 * Bleach);
	// lichen and moss take the joints (the dark texels) near the ground first
	float joint = 1.0 - saturate((px.lum(col) - 0.04) / 0.2);
	if (Lichen > 0.0 && hx < Lichen * (0.25 + 0.75 * bl) * (0.35 + joint) * saturate(1.3 - hgt / 260.0))
	{
		col = lerp(col, px.Texel(MossTex, uv, 128).rgb * 0.8, 0.85);
	}
}
// grounded: darker where the piece meets the turf
col *= lerp(1.0 - FootShade, 1.0, saturate((P.z - PivotZ + 4.0) / 36.0));
OutNormal = nrm;
return col * Tint;
"""


def build_prop():
    mat = get_material("M_Prop")
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)      # (masked only for the fade near the camera)
    mat.set_editor_property("opacity_mask_clip_value", 0.5)
    mat.set_editor_property("tangent_space_normal", False)
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
        ("Relief", g.scalar("Relief", 2.2, "Surface")),
        ("Blotch", g.scalar("Blotch", 0.22, "Weathering")),
        ("Damp", g.scalar("Damp", 0.5, "Weathering")), ("DampHeight", g.scalar("DampHeight", 70.0, "Weathering")),
        ("DampTint", g.vector("DampTint", lin(0.55, 0.53, 0.5), "Weathering"), "RGBA"),
        ("Bleach", g.scalar("Bleach", 0.25, "Weathering")),
        ("BleachTint", g.vector("BleachTint", lin(1.25, 1.22, 1.12), "Weathering"), "RGBA"),
        ("Lichen", g.scalar("Lichen", 0.0, "Weathering")),
    ]
    colour = g.custom(PROP_CODE, F3, params, "Prop: UV0 in cm, texture A / B by vertex colour B, relief from the texture, texel-stepped weathering, moss on top",
                      outputs=[("OutNormal", F3)])
    g.out(colour, MP.MP_BASE_COLOR)
    g.out(colour, MP.MP_NORMAL, "OutNormal")
    g.out(near_fade(g, P), MP.MP_OPACITY_MASK)
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
    # A crown the camera has come right up to thins away in a dither, so a close view looks in under the trees
    # instead of into a wall of leaves (gone within 9 m of the camera, whole beyond 23 m; the camera stands 9.5 m from
    # its focus at its closest, 32 m at the default zoom and 140 m at its furthest, so nothing fades from the ordinary views). Leaves only: the trunks stay.
    fade = g.custom(
        "float d = length(P - Cam);\n"
        "float f = (VCb > 0.5) ? 1.0 : saturate((d - Fade.x) / max(Fade.y - Fade.x, 1.0));\n"
        "float2 sp = Parameters.SvPosition.xy + float(View.StateFrameIndexMod8) * float2(5.588, 3.167);\n"
        "float ign = frac(52.9829189 * frac(dot(sp, float2(0.06711056, 0.00583715))));\n"
        "return f >= 0.999 ? 1.0 : step(ign, f);", F1, [
        ("P", g.node(unreal.MaterialExpressionWorldPosition, world_position_shader_offset=unreal.WorldPositionIncludedOffsets.WPT_EXCLUDE_ALL_SHADER_OFFSETS)),
        ("Cam", g.node(unreal.MaterialExpressionCameraPositionWS)), ("VCb", vc, "B"),
        ("Fade", g.vector("CameraFade", lin(900.0, 2300.0, 0.0, 0.0), "Fade"), "RGBA")], "Fade near the camera (dithered)")
    mask = g.node(unreal.MaterialExpressionMultiply)
    g.link(colour, mask, "A", "OutAlpha")
    g.link(fade, mask, "B")
    g.out(colour, MP.MP_BASE_COLOR)
    g.out(mask, MP.MP_OPACITY_MASK)
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
# The river, its channels and the far lake are one sheet (SM_Water). Everything that varies across it comes from
# T_WaterMap, a world-aligned data map the world generator bakes over the splat map's square:
#   R = distance in from the bank (0 at the bank .. 1 at 256 cm and beyond)   G = ford   B = current (0 in the still lake)
# so the water has shallows and a foam line along every bank, and a ford shows its gravel bed. All of it is evaluated per
# world texel (4 cm), like the ground: edges are stepped and dithered, never soft gradients.
def _water_info(sfx=""):
    """(MapRect, flow in texel space) from the generator's layout. MapRect: XY = world origin of T_WaterMap, Z = its world size."""
    rect, flow = (-16000.0, -20480.0, 40960.0, 0.0), (-0.816, 0.578)
    try:
        w = _layout(sfx)["water"]
        rect = (float(w["map"]["origin"][0]), float(w["map"]["origin"][1]), float(w["map"]["size"]), 0.0)
        flow = (float(w["flow"][0]), float(w["flow"][1]))
    except Exception:
        pass
    # texel space is (world Y, -world X): texture 'down' is toward the camera
    return rect, (flow[1], -flow[0], 0.0, 0.0)


def _data_map(name):
    """A world-space data map (not pixel art): linear, uncompressed, bilinear, clamped, no mips. The importer brings every
    new PNG in as point-filtered sRGB pixel art, so it is put right here before a material samples it."""
    t = eal.load_asset(TEX + name)
    if t is None:
        raise RuntimeError("missing texture " + TEX + name + " (run Tools/world/gen_battlefield.py, then Tools/import_world_assets.py)")
    t.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP)
    t.set_editor_property("srgb", False)
    t.set_editor_property("filter", unreal.TextureFilter.TF_BILINEAR)
    t.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
    t.set_editor_property("address_x", unreal.TextureAddress.TA_CLAMP)
    t.set_editor_property("address_y", unreal.TextureAddress.TA_CLAMP)
    t.set_editor_property("never_stream", True)
    eal.save_loaded_asset(t, False)
    return t


def _falls(sfx=""):
    """The feet of a map's waterfalls for M_Water (up to four): XY, Z = how far the churned water reaches (cm)."""
    out = []
    try:
        for f in _layout(sfx)["water"].get("falls", [])[:4]:
            out.append(lin(float(f["foot"][0]), float(f["foot"][1]), float(f.get("width", 240.0)) * 2.7, 0.0))
    except Exception:
        pass
    return out + [lin(0.0, 0.0, 0.0, 0.0)] * (4 - len(out))


# M_Water. Opaque and lit, so Lumen gives it the sky and the banks to reflect and nothing sorts wrong over it; the
# depth is not read from the screen but from the generator's maps, so the bed shows through exactly where the water is
# shallow, on any hardware:
#   T_WaterMap   R = cm in from the bank / 256, G = ford, A = (the mist's)
#   T_WaterFlow  RG = the current (world XY, 0.5 = still), B = depth / 200 cm
# Reflections ride smooth ripple normals carried down each river by its own current (two phases of a flow map, so the
# pattern never stretches) under a cross-chop of wind ripples; the colour, the foam and the glints stay on the
# world's 4 cm texels like everything else.
WATER_CODE = PIX + NAT + r"""
float T = max(Texel, 0.5);
float2 uv = float2(P.y, -P.x) / T;
float2 tc = floor(uv) + 0.5;                                    // this texel
float2 wc = float2(-tc.y, tc.x) * T;                            // its world XY
float2 gx = ddx(P.xy), gy = ddy(P.xy);
float4 m = Map.SampleLevel(View.SharedBilinearClampedSampler, (wc - MapRect.xy) / MapRect.z, 0);
float4 fl = FlowMap.SampleLevel(View.SharedBilinearClampedSampler, (P.xy - MapRect.xy) / MapRect.z, 0);
float bank = m.r * 256.0;                                       // cm in from the bank
float depth = fl.b * 200.0;                                     // cm of water over the bed
float hx = px.h(tc);
float2 flow = fl.rg * 2.0 - 1.0;                                // downstream, world XY; its length is the current's strength
float cur = saturate(length(flow) * 1.15);
float2 fdir = normalize(flow + float2(1e-3, 1e-3));

// ---- churned water at the foot of a fall
float churn = 0.0, ringD = 0.0;
float4 F[4] = { Fall0, Fall1, Fall2, Fall3 };
for (int i = 0; i < 4; ++i)
{
	float d = length(wc - F[i].xy);
	float k = saturate(1.0 - d / max(F[i].z, 1.0));
	if (k > churn) { churn = k; ringD = d; }
}

// ---- ripples: two phases of the same normals, each sliding down the current and fading out as the other fades in
float off = nt.v(P.xy / 900.0);
float ph = Time * FlowRate + off;
float p0 = frac(ph), p1 = frac(ph + 0.5);
float2 adv = flow * FlowSpeed / max(FlowRate, 1e-3);
float kw = 1.0 / WaveTile.x;
float2 nA = nt.nrm(nt.T2(Waves, (P.xy - adv * p0) * kw, gx * kw, gy * kw)).xy;
float2 nB = nt.nrm(nt.T2(Waves, (P.xy - adv * p1) * kw + 0.37, gx * kw, gy * kw)).xy;
float2 nflow = lerp(nA, nB, abs(1.0 - 2.0 * p0));
float k1 = 1.0 / WaveTile.y, k2 = 1.0 / WaveTile.z;
float2 nw = nt.nrm(nt.T2(Waves, P.xy * k1 + Time * Wind.xy, gx * k1, gy * k1)).xy
          + nt.nrm(nt.T2(Waves, float2(P.y, -P.x) * k2 - Time * Wind.zw, gx * k2, gy * k2)).xy;
float2 nxy = nflow * lerp(0.3, 1.25, cur) + nw * lerp(0.55, 0.3, cur);
nxy *= NormalStrength * lerp(0.45, 1.0, saturate(depth / 45.0)) * (1.0 + m.g * FordChop + churn * 2.5);
float3 nrm = normalize(float3(nxy, 1.0));

// ---- the bed through the water: clear over the shallows, turquoise as it deepens, dark in the channel
float kb = 1.0 / BedTile;
float2 bw = wc + nxy * min(depth, 60.0) * Refraction;
float3 bed = nt.T2(BedD, bw * kb, gx * kb, gy * kb).rgb * BedTint.rgb;
bed = lerp(bed, px.S(Gravel, uv, 128).rgb * FordTint.rgb, saturate(m.g * 1.5));       // a ford: pale gravel
bed *= 1.0 + (nt.v(wc / 55.0 + nxy * 1.5 + Time * 0.35) - 0.5) * Caustics * saturate(depth / 12.0);   // light playing on the bed
float clear = exp(-depth / max(ClearDepth, 1.0));
float deep = 1.0 - exp(-max(depth - 8.0, 0.0) / max(DeepDepth, 1.0));
float3 col = lerp(Shallow.rgb, bed, clear);
col = lerp(col, Deep.rgb * (0.85 + 0.3 * nt.fbm(wc / 2600.0)), deep);
col *= 1.0 + (nxy.x * 0.55 - nxy.y * 0.45) * WaveShade;                                  // the ripples' lit and shaded sides (the sky they mirror is one even blue)

// shallow water close in under a bank over a ford's bed (a marsh pool is all of that; a ford only at its two ends):
// murky and peat-stained, not pale gravel
float streakless = 0.0;
col = lerp(col, col * MarshTint.rgb, saturate(m.g * 1.5) * saturate(1.0 - bank / 420.0) * saturate(1.0 - streakless));

// ---- foam, on the texel grid
float kf = 1.0 / FoamTile;
float4 nz = nt.T2(Noise, (wc - flow * Time * 26.0) * kf, gx * kf, gy * kf);
float foam = 0.0;
// the bank: a ragged white edge, and lines that lap in to it and die
if (bank < EdgeFoam * (0.35 + 1.3 * nz.r) && nz.g > 0.3) foam = 1.0;
float lap = frac(bank / LapSpacing + Time * LapSpeed + nz.g * 0.8);
float lapLine = smoothstep(0.0, 0.12, lap) * (1.0 - smoothstep(0.14, 0.42, lap));
float reach = saturate(1.0 - bank / LapReach);
if (lapLine * reach * lerp(1.0, 0.6, cur) > 0.38 + nz.r * 0.55) foam = max(foam, 0.45 * reach + 0.1);
// the current: white streaks drawn out downstream over the fords and the fast shallows, faint lines of it everywhere it runs
float2 fl2 = float2(dot(wc, fdir), dot(wc, float2(-fdir.y, fdir.x)));
float ks = 1.0 / StreakTile;
float streak = nt.T2(Noise, float2(fl2.x - Time * StreakSpeed, fl2.y * 1.7) * ks, gx * ks, gy * ks).a;
float fast = saturate(m.g * cur * 1.5 + cur * saturate(1.0 - depth / 55.0) * 0.7);                // a still marsh pool has none
// (a riffle, not a rapid: thin broken threads of white where the water runs over the stones, most of the bed left clear)
if (streak + nz.b * 0.2 > 1.09 - fast * 0.17 && nz.r > 0.42) foam = max(foam, 0.26 + 0.34 * nz.g);
foam = max(foam, cur * smoothstep(0.66, 0.8, streak) * 0.16);
// under a fall: boiling white at the foot, rings running out from it
float ring = frac(ringD / 130.0 - Time * 0.55 + nz.g * 0.8);
float ringLine = smoothstep(0.0, 0.2, ring) * (1.0 - smoothstep(0.25, 0.7, ring));
if (nz.r * 0.75 + ringLine * 0.45 + nz.b * 0.2 > 1.28 - churn * 1.05) foam = max(foam, saturate(0.35 + churn));
foam = saturate(foam);
col = lerp(col, Foam.rgb, foam * Foam.a);
// shallow water lying level with its bank (a marsh pool, the ends of a ford; anywhere still): the edge silts up texel by texel into the same wet mud the
// land draws there, so the sheet's own outline is lost
float silt = 0.0;
if (bank < SiltWidth * (0.25 + 1.5 * nz.r) * (0.6 + 0.8 * hx) * saturate(m.g * 2.0 + (1.0 - saturate(cur * 4.0))) && depth < 30.0 && churn <= 0.0)
{
	float ku = T / MudTile;
	float2 mq = nt.Q(uv);
	col = nt.T2(MudD, mq * ku, ddx(uv) * ku, ddy(uv) * ku).rgb * MudTint.rgb;
	silt = 1.0;
	foam = 0.0;
}

// ---- glints: a few sun sparkles winking on the crests
float crest = saturate((nxy.x - nxy.y) * 2.2);
float sparkle = step(1.0 - Sparkle * (1.0 + cur * 2.0), px.h(tc + floor(Time * 4.0) * 13.7)) * crest;
OutEmissive = Glint.rgb * sparkle * Glint.a * (1.0 - foam);
OutRough = lerp(lerp(lerp(Rough, FordRough, saturate(m.g * 1.5)), 0.7, foam), 0.5, silt);        // a ford: wet gravel under a film of water, too rough for Lumen to trace (0.4)
OutSpec = lerp(Spec, 0.2, foam);
OutNormal = normalize(lerp(nrm, float3(0, 0, 1), saturate(foam * 0.6 + silt)));
return col;
"""


def build_water():
    rect, _ = _water_info()
    _data_map("T_WaterMap")
    _data_map("T_WaterFlow")
    mat = get_material("M_Water")
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE)
    mat.set_editor_property("tangent_space_normal", False)
    g = G(mat)
    falls = _falls()
    colour = g.custom(WATER_CODE, F3, [
        ("P", g.node(unreal.MaterialExpressionWorldPosition)), ("Time", g.node(unreal.MaterialExpressionTime)),
        ("Gravel", g.tex("Gravel", "T_Gravel")), ("Map", g.tex("WaterMap", "T_WaterMap", True)), ("FlowMap", g.tex("FlowMap", "T_WaterFlow", True)),
        ("Waves", g.tex("Waves", NTEX + "T_N_WaterWaves_N", sampler=NORMAL)), ("Noise", g.tex("Noise", NTEX + "T_N_WaterNoise", sampler=unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)),
        ("BedD", g.tex("Bed", NTEX + "T_N_Pebbles_D")),
        ("MudD", g.tex("Mud", NTEX + "T_N_Mud_D")), ("MudTile", g.scalar("MudTile", 4096.0, "Colour")),
        ("MudTint", g.vector("MudTint", lin(0.32, 0.29, 0.245), "Colour"), "RGB"),           # M_Terrain's MudTint x its WetDark: the bank's own wet mud
        ("SiltWidth", g.scalar("SiltWidth", 85.0, "Foam")), ("MarshTint", g.vector("MarshTint", lin(0.5, 0.56, 0.44), "Colour"), "RGB"),
        ("Texel", g.scalar("TexelSize", 4.0, "Crunch")),
        # MapRect: XY = world origin of T_WaterMap / T_WaterFlow, Z = their world size (cm). From layout.json.
        ("MapRect", g.vector("MapRect", lin(*rect), "Map"), "RGBA"),
        ("Fall0", g.vector("Fall0", falls[0], "Map"), "RGBA"), ("Fall1", g.vector("Fall1", falls[1], "Map"), "RGBA"),
        ("Fall2", g.vector("Fall2", falls[2], "Map"), "RGBA"), ("Fall3", g.vector("Fall3", falls[3], "Map"), "RGBA"),
        # motion. FlowSpeed: cm per second the ripples ride a full current; FlowRate: how often a phase is renewed
        ("FlowSpeed", g.scalar("FlowSpeed", 85.0, "Motion")), ("FlowRate", g.scalar("FlowRate", 0.3, "Motion")),
        ("Wind", g.vector("WindScroll", lin(0.021, 0.012, 0.014, 0.026), "Motion"), "RGBA"),       # tiles per second, the two wind layers
        ("WaveTile", g.vector("WaveTile", lin(520.0, 760.0, 330.0, 0.0), "Motion"), "RGBA"),       # cm: current ripples, wind chop A, B
        ("NormalStrength", g.scalar("NormalStrength", 0.55, "Surface")), ("WaveShade", g.scalar("WaveShade", 0.9, "Surface")), ("FordChop", g.scalar("FordChop", 0.9, "Surface")),
        ("Rough", g.scalar("Roughness", 0.07, "Surface")), ("FordRough", g.scalar("FordRoughness", 0.45, "Surface")), ("Spec", g.scalar("Specular", 0.5, "Surface")),
        # colour by depth
        ("Shallow", g.vector("Shallow", srgb("#2f8f86"), "Colour"), "RGB"),                        # turquoise
        ("Deep", g.vector("Deep", srgb("#0d2a36"), "Colour"), "RGB"),
        ("ClearDepth", g.scalar("ClearDepth", 26.0, "Colour")), ("DeepDepth", g.scalar("DeepDepth", 80.0, "Colour")),
        ("BedTint", g.vector("BedTint", lin(0.62, 0.66, 0.6), "Colour"), "RGB"), ("BedTile", g.scalar("BedTile", 4096.0, "Colour")),
        ("FordTint", g.vector("FordTint", lin(0.62, 0.74, 0.7), "Colour"), "RGB"),
        ("Refraction", g.scalar("Refraction", 0.5, "Colour")), ("Caustics", g.scalar("Caustics", 0.5, "Colour")),
        # foam
        ("Foam", g.vector("Foam", unreal.LinearColor(0.78, 0.86, 0.84, 0.92), "Foam"), "RGBA"),
        ("FoamTile", g.scalar("FoamTile", 620.0, "Foam")), ("EdgeFoam", g.scalar("EdgeFoam", 7.0, "Foam")),
        ("LapSpacing", g.scalar("LapSpacing", 64.0, "Foam")), ("LapSpeed", g.scalar("LapSpeed", 0.22, "Foam")), ("LapReach", g.scalar("LapReach", 150.0, "Foam")),
        ("StreakTile", g.scalar("StreakTile", 900.0, "Foam")), ("StreakSpeed", g.scalar("StreakSpeed", 150.0, "Foam")),
        ("Glint", g.vector("Glint", lin(1.0, 0.92, 0.75, 1.6), "Colour"), "RGBA"),
        ("Sparkle", g.scalar("Sparkle", 0.01, "Colour")),
    ], "Water: depth colour, the bed, flow-mapped ripples, bank foam, current streaks, churn under the falls, glints",
        outputs=[("OutEmissive", F3), ("OutRough", F1), ("OutSpec", F1), ("OutNormal", F3)])
    g.out(colour, MP.MP_BASE_COLOR)
    g.out(colour, MP.MP_EMISSIVE_COLOR, "OutEmissive")
    g.out(colour, MP.MP_ROUGHNESS, "OutRough")
    g.out(colour, MP.MP_SPECULAR, "OutSpec")
    g.out(colour, MP.MP_NORMAL, "OutNormal")
    g.finish()


# ----------------------------------------------------------------------------- atmosphere: cloud shadows, birds
# M_CloudShadow is a light function on the sun: broad soft shadows of clouds that are never seen, drifting across the
# field with the wind. World-aligned value noise, so it costs a few instructions per lit pixel and no texture.
CLOUD_CODE = r"""
struct SRNoise
{
	float h(float2 p) { float3 p3 = frac(float3(p.xyx) * 0.1031); p3 += dot(p3, p3.yzx + 33.33); return frac((p3.x + p3.y) * p3.z); }
	float v(float2 p)
	{
		float2 i = floor(p), f = frac(p);
		f = f * f * (3.0 - 2.0 * f);
		return lerp(lerp(h(i), h(i + float2(1, 0)), f.x), lerp(h(i + float2(0, 1)), h(i + float2(1, 1)), f.x), f.y);
	}
};
SRNoise nz;
float2 p = (P.xy + Time * Wind.xy) / max(Scale, 1.0);
float n = nz.v(p) * 0.6 + nz.v(p * 2.13 + 17.0) * 0.28 + nz.v(p * 4.7 + 41.0) * 0.12;
float c = smoothstep(Cover - Soft, Cover + Soft, n);
return 1.0 - c * Strength;
"""


def build_cloud_shadow():
    mat = get_material("M_CloudShadow")
    mat.set_editor_property("material_domain", unreal.MaterialDomain.MD_LIGHT_FUNCTION)
    g = G(mat)
    P = g.node(unreal.MaterialExpressionWorldPosition)
    params = [
        ("P", P), ("Time", g.node(unreal.MaterialExpressionTime)),
        ("Wind", g.vector("Wind", lin(55.0, 130.0, 0.0, 0.0), "Clouds"), "RGBA"),      # cm per second: toward screen right, a little up
        ("Scale", g.scalar("Scale", 5200.0, "Clouds")),                               # size of a cloud, cm
        ("Cover", g.scalar("Cover", 0.56, "Clouds")),                                 # higher = fewer clouds
        ("Soft", g.scalar("Soft", 0.11, "Clouds")),
        ("Strength", g.scalar("Strength", 0.5, "Clouds")),                            # how much sun a cloud takes
    ]
    c = g.custom(CLOUD_CODE, F1, params, "Cloud shadows: drifting world-aligned noise, 1 = sun, lower under a cloud")
    g.out(c, MP.MP_EMISSIVE_COLOR)
    g.finish()
    return mat


# M_Mist: low mist, never the fog of war (that is the game's own, M_FogOfWar). Unlit, translucent, soft against whatever
# it meets (depth fade), built of slow drifting wisps. Three ways of being laid, chosen by an instance:
#   UseMap 1            over the rivers: the water mesh again, a hand above the surface, thinning to nothing at the banks
#                       (T_WaterMap.r: distance in from the bank)
#   Ground 1            ground mist: the land's own meshes again, lifted `Lift` cm, showing only where mist pools
#                       (T_WaterMap.a: the hollows and the water's margins), so it lies in the dips and follows every slope
#   neither             a level sheet fading toward its own rim: the valley sheets under the far mountains, the spray
#                       at a waterfall's foot (MI_Mist_Valley, MI_Mist_Spray, on the engine's plane)
MIST_CODE = NAT + r"""
float2 p = (P.xy + Time * Wind.xy) / max(Scale, 1.0);
p += (float2(nt.v(p * 0.6 + Time * 0.021), nt.v(p * 0.6 + 31.0 - Time * 0.017)) - 0.5) * 1.3;        // the wisps curl as they drift
float n = nt.v(p) * 0.5 + nt.v(p * 2.3 + 11.0 - Time * 0.013) * 0.32 + nt.v(p * 5.1 + 3.0 + Time * 0.031) * 0.18;
float wisps = smoothstep(Cover, Cover + Soft, n);
float4 m = Map.SampleLevel(View.SharedBilinearClampedSampler, (P.xy - MapRect.xy) / MapRect.z, 0);
float rim = saturate(1.0 - length(UV - 0.5) * 2.0);
float edge = lerp(smoothstep(0.0, 0.55, rim), saturate(m.r * 1.5), UseMap);
float pool = smoothstep(0.12, 0.75, m.a) * (1.0 - saturate(m.r * 6.0));
edge = lerp(edge, pool * smoothstep(0.86, 0.97, normalize(N).z), Ground);          // none on the steeps: the lifted land would stand off them
return wisps * edge * Strength;
"""


def build_mist():
    mat = get_material("M_Mist")
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    mat.set_editor_property("two_sided", True)
    g = G(mat)
    rect, _ = _water_info()
    P = g.node(unreal.MaterialExpressionWorldPosition, world_position_shader_offset=unreal.WorldPositionIncludedOffsets.WPT_EXCLUDE_ALL_SHADER_OFFSETS)
    _data_map("T_WaterMap")
    ground = g.scalar("Ground", 0.0, "Mist")
    params = [
        ("P", P), ("N", g.node(unreal.MaterialExpressionVertexNormalWS)), ("UV", g.node(unreal.MaterialExpressionTextureCoordinate, coordinate_index=0)), ("Time", g.node(unreal.MaterialExpressionTime)),
        ("Map", g.tex("Map", "T_WaterMap", True)), ("MapRect", g.vector("MapRect", lin(*rect), "Map"), "RGBA"),
        ("UseMap", g.scalar("UseMap", 1.0, "Mist")), ("Ground", ground),
        ("Wind", g.vector("Wind", lin(22.0, 48.0, 0.0, 0.0), "Mist"), "RGBA"),       # cm per second, with the clouds but slower
        ("Scale", g.scalar("Scale", 620.0, "Mist")), ("Cover", g.scalar("Cover", 0.34, "Mist")), ("Soft", g.scalar("Soft", 0.42, "Mist")),
        ("Strength", g.scalar("Strength", 0.27, "Mist")),
    ]
    a = g.custom(MIST_CODE, F1, params, "Mist: drifting wisps; thinning at the bank / pooling in the hollows / fading to the sheet's rim")
    fade = g.node(unreal.MaterialExpressionDepthFade, fade_distance_default=170.0)      # no hard line where a sheet meets a cliff or a troop
    g.link(a, fade, "Opacity")
    g.link(g.scalar("FadeDistance", 170.0, "Mist"), fade, "FadeDistance")
    g.out(fade, MP.MP_OPACITY)
    g.out(g.vector("Colour", lin(0.66, 0.69, 0.71), "Mist"), MP.MP_EMISSIVE_COLOR)
    # ground mist rides above the land it is drawn from
    lift = g.custom("return float3(0.0, 0.0, Lift * Ground);", F3, [("Lift", g.scalar("Lift", 75.0, "Mist")), ("Ground", ground)], "Ground mist: lifted off the land")
    g.out(lift, MP.MP_WORLD_POSITION_OFFSET)
    g.finish()
    return mat


# M_Waterfall: the falls off the highlands' rims (SM_Waterfall_<n>, gen_battlefield.fall_mesh: UV0 = (0..1 across, cm
# fallen), UV1.x = 0 at the lip .. 1 at the pool). Unlit, translucent, in chunky cells like everything else: glassy
# green water sliding over the lip, breaking into three speeds of white streak as it falls, solid white at the foot;
# ragged, thinner sides. The pool's churn and rings are M_Water's (Fall0..3), the spray MI_Mist_Spray's.
WATERFALL_CODE = NAT + r"""
float2 cell = float2(floor(UV.x * Columns), floor(UV.y / CellCm));          // texel-sized cells
float fallen = UV.y;
float v = Speed * (0.55 + 0.45 * saturate(fallen / 500.0));                // it gathers speed
float y1 = cell.y - floor(Time * v / CellCm);
float y2 = cell.y - floor(Time * v * 1.45 / CellCm);
float y3 = cell.y - floor(Time * v * 0.7 / CellCm);
float s1 = nt.v(float2(cell.x * 1.9 + 3.0, y1 * 0.06));
float s2 = nt.v(float2(cell.x * 0.83 + 17.0, y2 * 0.17 + 9.0));
float s3 = nt.v(float2(cell.x * 3.7 + 5.0, y3 * 0.028 + 4.0));
float streak = s1 * 0.5 + s2 * 0.3 + s3 * 0.2;
float broken = smoothstep(0.02, 0.45, T);                                   // glassy at the lip, white lower down
float foot = saturate((T - 0.82) / 0.18);
float white = saturate(smoothstep(0.62 - broken * 0.3, 0.8 - broken * 0.25, streak) + foot * 1.2);
float side = saturate((0.5 - abs(UV.x - 0.5)) * 5.0 + (s2 - 0.5) * 0.8);     // ragged edges
float a = saturate(lerp(0.62, 1.0, smoothstep(0.3, 0.7, streak)) + foot * 0.6) * smoothstep(0.0, 0.5, side);
a = floor(a * 5.0 + 0.5) / 5.0;                                             // flat steps
OutOpacity = a * Strength;
float3 col = lerp(Deep.rgb, Foam.rgb, white);
col *= 0.86 + 0.14 * s2;
return col * Bright;
"""


def build_waterfall():
    mat = get_material("M_Waterfall")
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    mat.set_editor_property("two_sided", True)
    g = G(mat)
    params = [
        ("UV", g.node(unreal.MaterialExpressionTextureCoordinate, coordinate_index=0)),
        ("T", _fall_t(g)),
        ("Time", g.node(unreal.MaterialExpressionTime)),
        ("Columns", g.scalar("Columns", 60.0, "Fall")), ("CellCm", g.scalar("CellCm", 4.0, "Fall")), ("Speed", g.scalar("Speed", 520.0, "Fall")),
        ("Strength", g.scalar("Strength", 0.95, "Fall")), ("Bright", g.scalar("Bright", 0.82, "Fall")),
        ("Deep", g.vector("Deep", lin(0.2, 0.42, 0.44), "Fall"), "RGBA"), ("Foam", g.vector("Foam", lin(0.9, 0.95, 0.96), "Fall"), "RGBA"),
    ]
    rgb = g.custom(WATERFALL_CODE, F3, params, "Waterfall: glassy lip, three speeds of streak, white foot", outputs=[("OutOpacity", F1)])
    g.out(rgb, MP.MP_EMISSIVE_COLOR)
    g.out(rgb, MP.MP_OPACITY, "OutOpacity")
    g.finish()
    return mat


def _fall_t(g):
    """UV1.x as a scalar."""
    uv1 = g.node(unreal.MaterialExpressionTextureCoordinate, coordinate_index=1)
    m = g.node(unreal.MaterialExpressionComponentMask, r=True, g=False, b=False, a=False)
    g.link(uv1, m, "")
    return m


# M_Birds: the birds (ASRBirds, a procedural mesh rebuilt each frame: it moves and beats the wings itself). Unlit,
# two-sided flat shapes in their vertex colour (pale gulls, dark rooks, brown geese, darker wing tips).
def build_birds():
    mat = get_material("M_Birds")
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE)
    mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    mat.set_editor_property("two_sided", True)
    mat.set_editor_property("used_with_static_lighting", False)
    g = G(mat)
    g.out(g.node(unreal.MaterialExpressionVertexColor), MP.MP_EMISSIVE_COLOR)
    g.finish()
    return mat


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


def make_wildlife_instances(sprite, shadow):
    """Wildlife (ASRWildlife): the stag and the hind, on the troops' card and layout; nothing on them takes a team colour."""
    for beast in ("Deer", "Doe"):
        make_instance("MI_UnitSprite_" + beast, sprite, textures={
            "SpriteSheet": CHAR + "T_%s_Color" % beast, "TeamMask": CHAR + "T_%s_TeamMask" % beast, "NormalSheet": CHAR + "T_%s_Normal" % beast})
        make_instance("MI_UnitSpriteShadow_" + beast, shadow, textures={"SpriteSheet": CHAR + "T_%s_Color" % beast})


def make_sprite_instances(sprite, shadow):
    for troop in ("Shieldbearer", "Archer", "Miner", "Farmer", "Builder", "Scout", "Medic"):
        make_instance("MI_UnitSprite_" + troop, sprite, textures={
            "SpriteSheet": CHAR + "T_%s_Color" % troop, "TeamMask": CHAR + "T_%s_TeamMask" % troop, "NormalSheet": CHAR + "T_%s_Normal" % troop})
        make_instance("MI_UnitSpriteShadow_" + troop, shadow, textures={"SpriteSheet": CHAR + "T_%s_Color" % troop})
    make_wildlife_instances(sprite, shadow)
    # the arrow: one 44 x 9 frame, no normal sheet (one even normal), no billboard correction (the code orients its card)
    arrow = {"SheetCells": lin(1, 1, 0, 0), "CellPx": lin(44, 9, 0, 0)}
    make_instance("MI_ArrowSprite", sprite, scalars={"NormalStrength": 0.0, "Billboard": 0.0}, vectors=arrow,
                  textures={"SpriteSheet": CHAR + "T_Arrow_Color", "TeamMask": CHAR + "T_Arrow_TeamMask"})
    make_instance("MI_ArrowShadow", shadow, vectors=arrow, textures={"SpriteSheet": CHAR + "T_Arrow_Color"})
    # horse and catapult: 256 px cells at the same cm per pixel (the code scales their cards 1.6x), pivot row 184
    big = {"CellPx": lin(256, 256, 0, 0)}
    for troop in ("Horseman", "Catapult"):
        make_instance("MI_UnitSprite_" + troop, sprite, scalars={"PivotV": 184.0 / 256.0}, vectors=big, textures={
            "SpriteSheet": CHAR + "T_%s_Color" % troop, "TeamMask": CHAR + "T_%s_TeamMask" % troop, "NormalSheet": CHAR + "T_%s_Normal" % troop})
        make_instance("MI_UnitSpriteShadow_" + troop, shadow, scalars={"PivotV": 184.0 / 256.0}, vectors=big, textures={"SpriteSheet": CHAR + "T_%s_Color" % troop})
    # the catapult stone: one 20 x 20 frame on a small camera-facing card
    stone = {"SheetCells": lin(1, 1, 0, 0), "CellPx": lin(20, 20, 0, 0)}
    make_instance("MI_StoneSprite", sprite, scalars={"NormalStrength": 0.0, "Billboard": 0.0, "PivotV": 0.5}, vectors=stone,
                  textures={"SpriteSheet": CHAR + "T_Stone_Color", "TeamMask": CHAR + "T_Stone_TeamMask"})
    # battlefield effects: a strip of frames, shown flat (no relight: fire and smoke carry their own light)
    for fx, (w, h, n, pv) in {"Fire": (64, 96, 8, 88), "Smoke": (64, 96, 8, 88), "Dust": (64, 40, 6, 33),
                              "Debris": (96, 96, 6, 60), "Impact": (128, 96, 6, 78)}.items():
        make_instance("MI_FX_" + fx, sprite, scalars={"NormalStrength": 0.0, "Billboard": 0.0, "Relight": 0.0, "PivotV": pv / float(h)},
                      vectors={"SheetCells": lin(n, 1, 0, 0), "CellPx": lin(w, h, 0, 0)},
                      textures={"SpriteSheet": CHAR + "T_FX_" + fx, "TeamMask": CHAR + "T_Stone_TeamMask"})


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
// soot: a burning building blackens from its wall heads and roofs down (UV1.x = cm below the head), in whole texels,
// in drifting patches. Burn arrives per building (custom primitive data 4, ASRBuilding::StepFire).
float ember = 0.0;
if (Burn > 0.0)
{
	float up01 = saturate(1.0 - UV1.x / 240.0);
	float s = Burn * (0.5 + 0.85 * up01) + (bl - 0.5) * 0.9;
	float lv = floor(saturate(s * 1.7 - 0.2 + (hx - 0.5) * 0.4) * 3.0 + 0.5) / 3.0;
	col = lerp(col, col * float3(0.13, 0.115, 0.11), lv * 0.92);
	// a few texels in the worst of it still glow, winking
	ember = step(0.99, px.h(tc + 17.0)) * step(0.66, lv) * saturate(Burn * 2.0 - 0.6) * (0.5 + 0.5 * sin(Time * 5.0 + hx * 40.0));
}
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
OutEmissive = c.rgb * mask * GlowMask * Glow + float3(2.4, 0.5, 0.05) * ember;
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
col *= lerp(1.0, 0.32, saturate(Burn * 1.3));                       // cloth, thatch and crops singe as the building burns
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
    # barracks, archery range, and the damaged / ruined states (Tools/blender/bldkit.py)
    "RoofTile": ("opaque", "T_Bld_RoofTile", (64, 64), "T_Bld_RoofTile_N", {"Damp": 0.0, "Bleach": 0.0}, {}),
    "Target": ("opaque", "T_Bld_Target", (32, 32), None, {"Damp": 0.0, "Bleach": 0.0, "Roughness": 0.9}, {}),
    "Char": ("opaque", "T_Bld_Char", (64, 64), None, {"Damp": 0.0, "Bleach": 0.0, "Moss": 0.0, "Roughness": 1.0, "Specular": 0.1}, {}),
    "Scorch": ("card", "T_Bld_Scorch", (256, 128), None, {"UpNormal": 0.0, "SwayAmount": 0.0, "SwaySpeed": 0.0}, {}),
    "Water": ("opaque", "T_Bld_Water", (32, 32), None, {"Damp": 0.0, "Bleach": 0.0, "Moss": 0.0, "Roughness": 0.3, "Specular": 0.6}, {}),  # stable trough
    # the level banner (bldkit.Kit.level_flag): lit mostly from above so the numeral reads on the shaded front
    "Slate": ("opaque", "T_Bld_Slate", (64, 64), "T_Bld_Slate_N", {"Damp": 0.0, "Bleach": 0.0, "Moss": 0.0, "Roughness": 0.6, "Specular": 0.45}, {}),
    "Iron": ("opaque", "T_Bld_Iron", (32, 32), None, {"Damp": 0.0, "Bleach": 0.0, "Moss": 0.0, "Roughness": 0.5, "Specular": 0.55}, {}),
    "StoneDark": ("opaque", "T_Bld_StoneDark", (128, 128), "T_Bld_StoneDark_N", dict(_STONE, Moss=0.45), {}),
    "Timber": ("opaque", "T_Bld_Timber", (64, 64), "T_Bld_Timber_N", {"Damp": 0.4, "Bleach": 0.15, "Moss": 0.1}, {}),
    "LevelFlag": ("card", "T_Bld_LevelFlag", (256, 64), None, {"TeamMask": 1.0, "UpNormal": 0.55, "SwayAmount": 1.6, "SwaySpeed": 2.0}, {}),
}


def build_building():
    """M_Building (opaque) and M_BuildingCard (masked, two-sided), then one instance per mesh slot."""
    mat = get_material("M_Building")
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)      # (masked only for the fade near the camera)
    mat.set_editor_property("opacity_mask_clip_value", 0.5)
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
        ("Burn", g.scalar("Burn", 0.0, "Per building (custom primitive data)", cpd=4)), ("Time", g.node(unreal.MaterialExpressionTime)),
    ], "Building surface: cm UVs, team / glow mask, texel-stepped weathering, normal map in the face's UV frame",
        outputs=[("OutNormal", F3), ("OutEmissive", F3)])
    g.out(colour, MP.MP_BASE_COLOR)
    g.out(colour, MP.MP_NORMAL, "OutNormal")
    g.out(colour, MP.MP_EMISSIVE_COLOR, "OutEmissive")
    g.out(near_fade(g, P), MP.MP_OPACITY_MASK)
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
        ("Glow", g.scalar("Glow", 0.0, "Glow")), ("Burn", g.scalar("Burn", 0.0, "Per building (custom primitive data)", cpd=4)),
        ("RootShade", g.scalar("RootShade", 1.0, "Colour")), ("UpNormal", g.scalar("UpNormal", 0.0, "Colour")),
        ("Tint", g.vector("Tint", lin(1.0, 1.0, 1.0), "Colour"), "RGBA"),
    ], "Building card: cloth, crops, leaves, flame", outputs=[("OutAlpha", F1), ("OutNormal", F3), ("OutEmissive", F3)])
    weight = g.node(unreal.MaterialExpressionComponentMask, r=True, g=False, b=False, a=False)
    g.link(uv1, weight, "")
    sway = g.custom(BUILDING_SWAY, F3, [("P", P), ("Time", time), ("Weight", weight),
                                        ("Speed", g.scalar("SwaySpeed", 1.6, "Sway")), ("Amount", g.scalar("SwayAmount", 3.0, "Sway"))], "Wind sway")
    g.out(colour, MP.MP_BASE_COLOR)
    cmask = g.node(unreal.MaterialExpressionMultiply)
    g.link(colour, cmask, "A", "OutAlpha")
    g.link(near_fade(g, P), cmask, "B")
    g.out(cmask, MP.MP_OPACITY_MASK)
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
if not ONLY or "rock" in ONLY or "prop" in ONLY:
    rock = build_rock()
    make_instance("MI_Rock_Ruin", rock, scalars={"Moss": 0.6, "MossSlope": 0.8, "Tile": 1100.0}, vectors={"Tint": lin(1.05, 0.98, 0.86)})   # standing stones, barrows, relics: a paler dressed stone
if not ONLY or "prop" in ONLY:
    prop = build_prop()
    make_instance("MI_Prop_Rock", prop, scalars={"Moss": 1.0, "MossSlope": 0.84, "Roughness": 0.86, "Lichen": 0.35},
                  vectors={"SizeA": lin(64, 64, 0, 0), "Tint": lin(0.8, 0.78, 0.72)}, textures={"TexA": "T_Rock"})
    make_instance("MI_Prop_Sandstone", prop, scalars={"Moss": 0.0, "Roughness": 0.8, "Lichen": 0.3, "DampHeight": 110.0},
                  vectors={"SizeA": lin(128, 64, 0, 0)}, textures={"TexA": "T_Sandstone"})
    make_instance("MI_Prop_Wood", prop, scalars={"Roughness": 0.8, "FootShade": 0.25, "Relief": 1.6, "Bleach": 0.3, "DampHeight": 45.0},
                  vectors={"SizeA": lin(64, 32, 0, 0)}, textures={"TexA": "T_Wood"})
    make_instance("MI_Prop_Log", prop, scalars={"Moss": 0.0, "Roughness": 0.85},
                  vectors={"SizeA": lin(16, 16, 0, 0), "SizeB": lin(32, 64, 0, 0)}, textures={"TexA": "T_LogEnd", "TexB": "T_Bark"})
    make_instance("MI_Prop_LogMossy", prop, scalars={"Moss": 1.0, "MossSlope": 0.55, "Roughness": 0.88},         # fallen timber in the woods: moss along the top
                  vectors={"SizeA": lin(16, 16, 0, 0), "SizeB": lin(32, 64, 0, 0), "Tint": lin(0.8, 0.78, 0.72)}, textures={"TexA": "T_LogEnd", "TexB": "T_Bark"})
    make_instance("MI_Prop_Bone", prop, scalars={"Moss": 0.3, "MossSlope": 0.9, "Roughness": 0.7},        # the wyrm's bones: old ivory, a little moss
                  vectors={"SizeA": lin(64, 64, 0, 0), "Tint": lin(1.3, 1.24, 1.06)}, textures={"TexA": "T_Rock"})
if not ONLY or "atmosphere" in ONLY or "birds" in ONLY:
    build_birds()
if not ONLY or "atmosphere" in ONLY or "waterfall" in ONLY:
    build_waterfall()
if ONLY and "wildlife" in ONLY and "sprite" not in ONLY:      # only the deer's instances, on the sprite materials as they stand
    make_wildlife_instances(eal.load_asset(DIR + "/M_UnitSprite"), eal.load_asset(DIR + "/M_UnitSpriteShadow"))
if not ONLY or "atmosphere" in ONLY:
    build_cloud_shadow()
    mist = build_mist()
    make_instance("MI_Mist_Valley", mist, scalars={"UseMap": 0.0, "Scale": 1500.0, "Cover": 0.34, "Soft": 0.5, "Strength": 0.3})
    make_instance("MI_Mist_Ground", mist, scalars={"UseMap": 0.0, "Ground": 1.0, "Scale": 900.0, "Cover": 0.42, "Soft": 0.45, "Strength": 0.24, "FadeDistance": 110.0, "Lift": 75.0},
                  vectors={"Wind": lin(16.0, 34.0, 0.0, 0.0)})
    make_instance("MI_Mist_Spray", mist, scalars={"UseMap": 0.0, "Scale": 230.0, "Cover": 0.25, "Soft": 0.5, "Strength": 0.42, "FadeDistance": 90.0},
                  vectors={"Wind": lin(60.0, 95.0, 0.0, 0.0), "Colour": lin(0.8, 0.84, 0.86)})
if not ONLY or "foliage" in ONLY:
    foliage = build_foliage()
    # the broadleaves (Tools/world/props.py > broadleaf, Tools/textures/gen_forest_textures.py): the firs' material with
    # a leafy clump for the bough tier; less sunk in shade under each clump, a stronger glow through the leaves
    make_instance("MI_Foliage_Oak", foliage, scalars={"ShadeFloor": 0.34, "Subsurface": 0.7, "SwayAmount": 6.0, "SwaySpeed": 0.9},
                  vectors={"TipTint": lin(1.14, 1.1, 0.8)}, textures={"Needles": "T_Leaves"})
    make_instance("MI_Foliage_Birch", foliage, scalars={"ShadeFloor": 0.42, "Subsurface": 0.85, "SwayAmount": 8.0, "SwaySpeed": 1.3},
                  vectors={"TipTint": lin(1.12, 1.08, 0.82)}, textures={"Needles": "T_LeavesBirch", "Bark": "T_BarkBirch"})
    make_instance("MI_Foliage_Maple", foliage, scalars={"ShadeFloor": 0.36, "Subsurface": 0.8, "SwayAmount": 6.0, "SwaySpeed": 1.0},
                  vectors={"TipTint": lin(1.16, 1.04, 0.8)}, textures={"Needles": "T_LeavesMaple"})
if not ONLY or "card" in ONLY:
    cardm = build_card()
    make_instance("MI_Card_Under", cardm, scalars={"RootShade": 0.55, "SwayAmount": 2.0, "SwaySpeed": 1.3},      # the forest floor's cards (T_Undergrowth)
                  vectors={"Size": lin(160, 32, 0, 0), "Tint": lin(0.84, 0.84, 0.84)}, textures={"Tex": "T_Undergrowth"})
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

# ---- the second map's own instances: its splat map, its water map and their world squares (map "two" is the parents'
# defaults). Tools/build_battlefield_visuals.py puts them on the meshes under /Game/SR/Meshes4.
if not ONLY or "terrain" in ONLY or "water" in ONLY or "atmosphere" in ONLY or "maps" in ONLY:
    for _map, _sfx in MAP_SFX.items():
        if not _sfx or not eal.does_asset_exist(TEX + "T_Splat" + _sfx):
            continue
        _data_map("T_WaterMap" + _sfx)
        _data_map("T_WaterFlow" + _sfx)
        _data_map("T_Forest" + _sfx)
        _rect, _flow = _water_info(_sfx)
        _f = _falls(_sfx)
        make_instance("MI_Terrain" + _sfx, eal.load_asset(DIR + "/M_Terrain"), scalars={"RockLine": _relief(_sfx)[0], "SnowLine": _relief(_sfx)[1]},
                      vectors={"SplatRect": lin(*_splat_rect(_sfx))}, textures={"Splat": "T_Splat" + _sfx, "FlowMap": "T_WaterFlow" + _sfx, "ForestMap": "T_Forest" + _sfx})
        make_instance("MI_Water" + _sfx, eal.load_asset(DIR + "/M_Water"), vectors={"MapRect": lin(*_rect), "Fall0": _f[0], "Fall1": _f[1], "Fall2": _f[2], "Fall3": _f[3]},
                      textures={"WaterMap": "T_WaterMap" + _sfx, "FlowMap": "T_WaterFlow" + _sfx})
        make_instance("MI_Mist" + _sfx, eal.load_asset(DIR + "/M_Mist"), vectors={"MapRect": lin(*_rect)}, textures={"Map": "T_WaterMap" + _sfx})
        make_instance("MI_Mist_Ground" + _sfx, eal.load_asset(DIR + "/MI_Mist_Ground"), vectors={"MapRect": lin(*_rect)}, textures={"Map": "T_WaterMap" + _sfx})
