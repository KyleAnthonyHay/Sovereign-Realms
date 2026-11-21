"""Builds the fire's and the falling leaves' materials under /Game/SR/Materials (run inside the editor):

    Tools/ue_py.py Tools/build_fx_materials.py              (ONLY = ['fire'] or ['leaves'] for one family)

  M_FX_Flame    the flames on a burning building (ASRBuildingFire, Source/SovereignRealms/FX/SRFire.cpp)
  M_FX_Smoke    its smoke, and the dust and smoke of a collapse
  M_FX_Embers   the sparks carried up off it
  M_Leaves      the falling leaves (ASRLeaves, FX/SRLeaves.cpp)

All four are drawn on camera-facing quads the C++ moves each frame (procedural meshes); the materials do the rest:
the flame's tongues, the smoke's billows and the sparks are worked out per chunky cell from value noise and the clock,
so nothing is a flipbook and no two fires match. What the mesh hands the material:

  UV0           the quad, 0..1 (v = 0 at its top)
  UV1.x         a seed, 0..1, the quad's own       UV1.y   flame: how much of the seat burns; smoke: its age 0..1;
                                                           embers: how many
  COLOR         flame: R = strength, G = 1 on the broad base tongue; smoke: R = opacity, G = lit from below by the
                fire, B = 0 pale dust .. 1 black smoke; embers: R = strength; leaves: the leaf's own colour

Without these materials the game falls back to the old sprite fire (ASRBuilding::UsesNewFire) and sheds no leaves.
The graph helpers (G, lin, get_material, the SRPix / SRNat shader helpers) are build_visual_materials.py's own: its
head is run here, none of its materials are rebuilt.
"""
import os
import re
import unreal

_src = open(os.path.join(os.path.abspath(unreal.Paths.project_dir()), "Tools", "build_visual_materials.py")).read()
exec(_src[:_src.index("# ----------------------------------------------------------------------------- grey test blocks")])
NAT = re.search(r'^NAT = r"""(.*?)"""', _src, re.S | re.M).group(1)

# ----------------------------------------------------------------------------- fire
FLAME_CODE = PIX + NAT + r"""
float2 g = (floor(UV * Cells.xy) + 0.5) / Cells.xy;                // chunky cells, like every texel in the world
float y = 1.0 - g.y;                                               // 0 at the root .. 1 at the tip
float x = (g.x - 0.5) * 2.0;
float t = Time * Speed * lerp(1.25, 1.0, VC.g) + Seed * 61.0;
x += (nt.v(float2(y * 2.6 - t * 0.9, Seed * 17.0)) - 0.5) * 1.1 * y;                       // the tongues lean and whip
x += (nt.v(float2(y * 6.0 - t * 2.2, Seed * 5.0 + 3.0)) - 0.5) * 0.35 * y;
float n = nt.v(float2(x * 2.4 + Seed * 9.0, y * 2.8 - t * 1.7)) * 0.55 + nt.v(float2(x * 6.0 + 3.0, y * 6.5 - t * 3.1)) * 0.45;
float width = lerp(1.0, 0.4, y);                                    // broad at the root, licking up into separate tongues
float body = saturate(1.0 - abs(x) / width);
float f = body * 0.85 + n * 1.55 - y * 1.45 - 0.62;
f *= smoothstep(0.0, 0.06, y) * smoothstep(0.0, 0.25, body) * lerp(0.7, 1.0, Lit);
float3 col = Red.rgb;
float a = 0.0;
if (f > 0.06) a = 0.75;
if (f > 0.2) { col = Orange.rgb; a = 1.0; }
if (f > 0.42) col = Yellow.rgb;
if (f > 0.7) col = Core.rgb;
OutOpacity = a * saturate(VC.r * 3.0);
return col * Glow * (0.85 + 0.3 * n);
"""

SMOKE_CODE = PIX + NAT + r"""
float2 g = (floor(UV * Cells) + 0.5) / Cells;
float2 c = (g - 0.5) * 2.0;
float age = Age;
float2 sp = c * 1.6 + Seed * float2(37.0, 91.0);
float roll = Time * 0.42 + age * 1.2;
float n = nt.v(sp + float2(0.0, roll)) * 0.6 + nt.v(sp * 2.4 + 5.0 + float2(roll * 0.7, roll * 1.6)) * 0.4;       // it rolls as it rises
float d = 1.0 - length(c) - (0.5 - n) * 0.85;                       // a billowing edge
float a = floor(saturate(d * 3.2) * 4.0 + 0.5) / 4.0;               // in flat steps
float lit = saturate(0.5 - c.y * 0.55 - c.x * 0.3 + (n - 0.5) * 0.9);   // lit from above and from the sun's side
lit = floor(lit * 4.0 + 0.5) / 4.0;
float3 col = lerp(lerp(DustDark.rgb, DustLit.rgb, lit), lerp(SmokeDark.rgb, SmokeLit.rgb, lit), VC.b);
col += Ember.rgb * VC.g * saturate(0.55 + c.y * 0.8) * (0.4 + n);    // the fire under it lights its belly
OutOpacity = a * VC.r * Strength;
return col;
"""

EMBER_CODE = PIX + r"""
float2 g = floor(UV * Cells.xy);
float y = 1.0 - (g.y + 0.5) / Cells.y;                              // 0 at the fire .. 1 at the top
float x = ((g.x + 0.5) / Cells.x - 0.5) * 2.0;
float on = 0.0, heat = 0.0;
for (int L = 0; L < 2; ++L)
{
	float sp = Speed * (1.0 + L * 0.7);
	float sway = floor(sin(Time * 1.3 + g.y * 0.21 + L * 2.0 + Seed * 20.0) * 3.0 * y);      // they waver as they climb
	float2 p = float2(g.x + sway, g.y + floor(Time * sp)) + Seed * 113.0 + L * 57.0;
	float h = px.h(p), h2 = px.h(p + 31.7);
	float alive = step(1.0 - Density * VC.r, h) * step(y, 0.2 + h2 * 0.8) * step(0.3, px.h(p + floor(Time * 9.0) * 7.3));
	on = max(on, alive);
	heat = max(heat, alive * (1.0 - y / (0.2 + h2 * 0.8)));
}
on *= step(abs(x), 0.12 + y * 0.88);                                 // out of the fire's own width, spreading
OutOpacity = on;
return lerp(Cool.rgb, Hot.rgb, heat) * Glow * on;
"""


def _fx_material(name):
    mat = get_material(name)
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    mat.set_editor_property("two_sided", True)
    return mat


def _quad_inputs(g):
    uv1 = g.node(unreal.MaterialExpressionTextureCoordinate, coordinate_index=1)
    seed = g.node(unreal.MaterialExpressionComponentMask, r=True, g=False, b=False, a=False)
    par = g.node(unreal.MaterialExpressionComponentMask, r=False, g=True, b=False, a=False)
    g.link(uv1, seed, "")
    g.link(uv1, par, "")
    return g.node(unreal.MaterialExpressionTextureCoordinate, coordinate_index=0), seed, par, g.node(unreal.MaterialExpressionVertexColor)


def build_fire():
    mat = _fx_material("M_FX_Flame")
    g = G(mat)
    uv, seed, par, vc = _quad_inputs(g)
    rgb = g.custom(FLAME_CODE, F3, [
        ("UV", uv), ("Seed", seed), ("Lit", par), ("VC", vc, ""), ("Time", g.node(unreal.MaterialExpressionTime)),
        ("Cells", g.vector("Cells", lin(22.0, 34.0, 0.0, 0.0), "Flame"), "RGBA"), ("Speed", g.scalar("Speed", 1.15, "Flame")), ("Glow", g.scalar("Glow", 2.6, "Flame")),
        ("Core", g.vector("Core", lin(1.0, 0.86, 0.5), "Flame"), "RGB"), ("Yellow", g.vector("Yellow", lin(1.0, 0.56, 0.1), "Flame"), "RGB"),
        ("Orange", g.vector("Orange", lin(0.95, 0.24, 0.03), "Flame"), "RGB"), ("Red", g.vector("Red", lin(0.42, 0.05, 0.01), "Flame"), "RGB"),
    ], "Flame: whipping tongues in four hot steps", outputs=[("OutOpacity", F1)])
    g.out(rgb, MP.MP_EMISSIVE_COLOR)
    g.out(rgb, MP.MP_OPACITY, "OutOpacity")
    g.finish()

    mat = _fx_material("M_FX_Smoke")
    g = G(mat)
    uv, seed, par, vc = _quad_inputs(g)
    rgb = g.custom(SMOKE_CODE, F3, [
        ("UV", uv), ("Seed", seed), ("Age", par), ("VC", vc, ""), ("Time", g.node(unreal.MaterialExpressionTime)),
        ("Cells", g.scalar("Cells", 34.0, "Smoke")), ("Strength", g.scalar("Strength", 0.88, "Smoke")),
        # (unlit: these are the colours on screen under the level's 11 lux sun, not albedos)
        ("SmokeLit", g.vector("SmokeLit", lin(0.13, 0.115, 0.1), "Smoke"), "RGB"), ("SmokeDark", g.vector("SmokeDark", lin(0.008, 0.0075, 0.009), "Smoke"), "RGB"),
        ("DustLit", g.vector("DustLit", lin(0.34, 0.29, 0.21), "Smoke"), "RGB"), ("DustDark", g.vector("DustDark", lin(0.11, 0.09, 0.065), "Smoke"), "RGB"),
        ("Ember", g.vector("Ember", lin(0.55, 0.13, 0.015), "Smoke"), "RGB"),
    ], "Smoke: a billowing puff in flat steps, lit from above, glowing from the fire under it", outputs=[("OutOpacity", F1)])
    g.out(rgb, MP.MP_EMISSIVE_COLOR)
    g.out(rgb, MP.MP_OPACITY, "OutOpacity")
    g.finish()

    mat = _fx_material("M_FX_Embers")
    g = G(mat)
    uv, seed, par, vc = _quad_inputs(g)
    rgb = g.custom(EMBER_CODE, F3, [
        ("UV", uv), ("Seed", seed), ("VC", vc, ""), ("Time", g.node(unreal.MaterialExpressionTime)),
        ("Cells", g.vector("Cells", lin(84.0, 190.0, 0.0, 0.0), "Embers"), "RGBA"), ("Speed", g.scalar("Speed", 46.0, "Embers")),
        ("Density", g.scalar("Density", 0.022, "Embers")), ("Glow", g.scalar("Glow", 5.0, "Embers")),
        ("Hot", g.vector("Hot", lin(1.0, 0.7, 0.25), "Embers"), "RGB"), ("Cool", g.vector("Cool", lin(0.8, 0.14, 0.02), "Embers"), "RGB"),
    ], "Embers: sparks climbing off the fire, cooling as they go", outputs=[("OutOpacity", F1)])
    g.out(rgb, MP.MP_EMISSIVE_COLOR)
    g.out(rgb, MP.MP_OPACITY, "OutOpacity")
    g.finish()


# ----------------------------------------------------------------------------- leaves
LEAF_CODE = r"""
float2 c = UV * 2.0 - 1.0;
float w = 0.92 * pow(saturate(1.0 - c.x * c.x), 0.6) * (0.75 + 0.25 * c.x);       // a pointed oval, broader toward the stalk
OutMask = step(abs(c.y), w);
float rib = step(abs(c.y), 0.08);
return VC.rgb * (1.0 - 0.3 * rib) * (0.86 + 0.28 * step(0.0, c.y));
"""


def build_leaves():
    mat = get_material("M_Leaves")
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
    mat.set_editor_property("two_sided", True)
    mat.set_editor_property("tangent_space_normal", False)
    mat.set_editor_property("opacity_mask_clip_value", 0.5)
    g = G(mat)
    rgb = g.custom(LEAF_CODE, F3, [("UV", g.node(unreal.MaterialExpressionTextureCoordinate, coordinate_index=0)), ("VC", g.node(unreal.MaterialExpressionVertexColor), "")],
                   "Leaf: a pointed oval with a midrib, in the leaf's own colour", outputs=[("OutMask", F1)])
    g.out(rgb, MP.MP_BASE_COLOR)
    g.out(rgb, MP.MP_OPACITY_MASK, "OutMask")
    g.out(g.const3(0.0, 0.0, 1.0), MP.MP_NORMAL)          # lit like the ground it falls to, whichever way it tumbles
    g.out(g.scalar("Roughness", 0.8, "Surface"), MP.MP_ROUGHNESS)
    g.out(g.const(0.15), MP.MP_SPECULAR)
    g.finish()


ONLY = globals().get("ONLY")
if not ONLY or "fire" in ONLY:
    build_fire()
if not ONLY or "leaves" in ONLY:
    build_leaves()
