"""Material table shared by the Blender build / render scripts and the 2D post step.

Pure Python (no bpy, no numpy) so both interpreters can import it.

Every material has
  id     index written to the 'matid' AOV (decoded in the reduce step)
  base   sRGB hex used for the Principled BSDF in the .blend / FBX
  rough, metal   Principled parameters (only used for the 3D look and the FBX)
  ramp   the curated pixel-art ramp, dark -> light. The sprite colour of a pixel is
         ramp[band], where band comes from the rendered lighting value.
  spec   (strength, shininess) of the extra highlight added to the lighting value
  gain, bias     per-material contrast tweak of the lighting value before banding
  team   True if the region is tinted by TeamColor (ramp is then a neutral grey ramp)
  thin   True for wire-like parts (bowstring, arrow) that must survive downsampling
  accent True for tiny parts that must not be removed by the orphan-pixel cleanup
  fx     True for effect shapes (the strike smear): no outline, no interior lines
  tex    optional cell pattern multiplied into the lighting pass (scale armour)
"""

OUTLINE = "#1b1220"          # hue-shifted near-black (dark plum), used for the silhouette
OUTLINE_TEAM_GREY = "#3c3c3c"  # outline next to team regions: tinted, so it becomes dark navy / maroon

MATERIALS = [
    dict(name="skin", base="#b87650", rough=0.75, metal=0.0, spec=(0.10, 8), bias=0.06,
         ramp=["#3a1f2e", "#5c2f34", "#86483a", "#ad6846", "#cc8c5c", "#e6b47e"]),
    dict(name="hair", base="#33241f", rough=0.9, metal=0.0, spec=(0.05, 6),
         ramp=["#1a1218", "#2b1d1f", "#412d28", "#594032"]),
    dict(name="beard", base="#6e3f26", rough=0.9, metal=0.0, spec=(0.05, 6), bias=0.04,
         ramp=["#2a171a", "#4c2820", "#723e25", "#9a5c30"]),
    dict(name="eye", base="#140e14", rough=1.0, metal=0.0, accent=True,
         ramp=["#1b1220"]),
    dict(name="linen", base="#c9bfa4", rough=0.95, metal=0.0, spec=(0.0, 4),
         ramp=["#453d50", "#6a606c", "#928884", "#b8ad9a", "#d9cfb2", "#f1e9cd"]),
    dict(name="leather", base="#6d4630", rough=0.7, metal=0.0, spec=(0.12, 10),
         ramp=["#21151a", "#382320", "#553428", "#744a31", "#93643d", "#b38253"]),
    dict(name="leather_dark", base="#3f2c26", rough=0.75, metal=0.0, spec=(0.10, 10),
         ramp=["#1a1218", "#2b1d1f", "#412d28", "#594032", "#755642"]),
    dict(name="bronze", base="#b0843a", rough=0.32, metal=1.0, spec=(0.5, 40), gain=1.3, bias=-0.03,
         ramp=["#2a1c22", "#463027", "#6a4a2b", "#8e6a36", "#b08b4a", "#d0b06c", "#f0dfa8"]),
    dict(name="bronze_dark", base="#7d5c2e", rough=0.45, metal=1.0, spec=(0.35, 16), gain=1.1, bias=-0.03,
         ramp=["#251a20", "#3a2a26", "#56402a", "#745832", "#927443", "#b49860"]),
    # cuirass scale rows: same metal as bronze / bronze_dark, with a scale pattern in the lighting pass
    dict(name="scale_a", base="#8a6a36", rough=0.4, metal=1.0, spec=(0.35, 24), gain=1.25, bias=-0.02,
         tex=dict(size=0.05, edge=0.45, cell=0.30),
         ramp=["#2a1c22", "#463027", "#6a4a2b", "#8e6a36", "#b08b4a", "#d0b06c"]),
    dict(name="scale_b", base="#6e5430", rough=0.45, metal=1.0, spec=(0.3, 20), gain=1.2, bias=-0.03,
         tex=dict(size=0.05, edge=0.45, cell=0.30),
         ramp=["#251a20", "#3a2a26", "#56402a", "#745832", "#927443", "#b49860"]),
    dict(name="blade", base="#c79a48", rough=0.25, metal=1.0, spec=(0.5, 14), gain=1.1, bias=0.06,
         ramp=["#463027", "#6a4a2b", "#8e6a36", "#b08b4a", "#d0b06c", "#f0dfa8"]),
    dict(name="wood", base="#6a4530", rough=0.6, metal=0.0, spec=(0.15, 12),
         ramp=["#21151a", "#382320", "#553428", "#744a31", "#93643d", "#b38253"]),
    dict(name="team", base="#2f55b8", rough=0.85, metal=0.0, spec=(0.04, 6), team=True,
         ramp=["#383838", "#4f4f4f", "#686868", "#808080", "#989898", "#b0b0b0"]),
    dict(name="team_trim", base="#5d7fd6", rough=0.8, metal=0.0, spec=(0.04, 6), team=True,
         ramp=["#808080", "#989898", "#b0b0b0", "#cccccc", "#e8e8e8"]),
    dict(name="feather", base="#d8ceb4", rough=0.9, metal=0.0, accent=True,
         ramp=["#7d7370", "#b3a994", "#e4dabc"]),
    # workers (miners, farmhands): woven straw (hats, baskets), ore lumps with gold flecks, iron tool heads
    dict(name="straw", base="#c8a45a", rough=0.9, metal=0.0, spec=(0.04, 6),
         ramp=["#3d2a1e", "#62452a", "#8c6a38", "#b8924c", "#d8b866", "#f0d88e"]),
    dict(name="ore", base="#4e4642", rough=0.85, metal=0.0, spec=(0.08, 8),
         tex=dict(size=0.035, edge=0.35, cell=0.45),
         ramp=["#1b1418", "#2e2628", "#463d3c", "#615753", "#7d726a"]),
    dict(name="gold", base="#e6b43c", rough=0.25, metal=1.0, spec=(0.6, 30), gain=1.3, accent=True,
         ramp=["#6a4a2b", "#b08b4a", "#e2b84e", "#fff0a0"]),
    dict(name="iron", base="#6c6a6a", rough=0.4, metal=1.0, spec=(0.4, 20), gain=1.1,
         ramp=["#1d1a20", "#33303a", "#4f4c54", "#6f6c70", "#949090", "#bdb8b0"]),
    # motion smear on the strike frame: flat, unshaded, no outline
    dict(name="smear", base="#fff6da", rough=1.0, metal=0.0, accent=True, fx=True,
         ramp=["#f3e6c0", "#fffbea"]),
    dict(name="string", base="#d6ccb0", rough=0.9, metal=0.0, thin=True, accent=True,
         ramp=["#9a907e", "#e2d9bd"]),
    dict(name="shaft", base="#8a6a48", rough=0.8, metal=0.0, thin=True, accent=True,
         ramp=["#553428", "#744a31", "#93643d"]),
]

for _i, _m in enumerate(MATERIALS):
    _m["id"] = _i
    _m.setdefault("spec", (0.0, 4))
    _m.setdefault("gain", 1.0)
    _m.setdefault("bias", 0.0)
    _m.setdefault("team", False)
    _m.setdefault("thin", False)
    _m.setdefault("accent", False)
    _m.setdefault("tex", None)
    _m.setdefault("fx", False)

BY_NAME = {m["name"]: m for m in MATERIALS}


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def srgb_to_linear(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def id_color(i):
    """Exact, well separated colour for material index i (written to the matid AOV)."""
    # 4 levels per channel -> 64 codes; index 0 is reserved for 'nothing'.
    k = i + 1
    return ((k & 3) / 3.0, ((k >> 2) & 3) / 3.0, ((k >> 4) & 3) / 3.0)
