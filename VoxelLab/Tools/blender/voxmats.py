"""The voxel materials of the Sovereign Realms voxel style: one table shared by the Blender side (voxlib.py), the
texture generator (voxtex.py) and the Unreal importer (Tools/ue/import_assets.py).

A voxel has a material (what it is made of) and a tint colour. Each face of a voxel is drawn with a "slot": a tiling
64 x 64 pixel-art texture (T_Vox_<slot>.png). Most materials use one slot on every face; a few use different slots on
top, sides and bottom (grass on dirt, the end grain of a log).

  jitter       how much the brightness varies from cell to cell (0 .. 1)
  cell         size of those cells in metres (0 = one voxel)
  warm         how much the tint also shifts between cooler/darker and warmer/lighter
  emissive     light given off (0 = none); Unreal multiplies the texture by this
  rough, metal surface response
"""

TEXEL = 0.0625          # metres per texel everywhere: 8 texels on a 50 cm block
TEX_SIZE = 64           # the tiling textures are 64 x 64 texels = 4 m

#        name            slots (top, side, bottom)                     jitter cell  warm  emissive rough metal
_TABLE = [
    ("stone",        ("stone", "stone", "stone"),                      0.05, 0.5, 0.02, 0.0, 0.92, 0.0),
    ("brick",        ("brick", "brick", "brick"),                      0.04, 0.25, 0.02, 0.0, 0.92, 0.0),
    ("cobble",       ("cobble", "cobble", "cobble"),                   0.03, 0.5, 0.02, 0.0, 0.90, 0.0),
    ("grass",        ("grass", "grass_side", "dirt"),                  0.03, 0.5, 0.02, 0.0, 0.95, 0.0),
    ("dirt",         ("dirt", "dirt", "dirt"),                         0.04, 0.5, 0.02, 0.0, 0.95, 0.0),
    ("plank",        ("plank", "plank", "plank"),                      0.05, 0.5, 0.02, 0.0, 0.85, 0.0),
    ("beam",         ("beam", "beam", "beam"),                         0.05, 0.5, 0.02, 0.0, 0.85, 0.0),
    ("post",         ("beam", "beam_v", "beam"),                       0.05, 0.5, 0.02, 0.0, 0.85, 0.0),
    ("log",          ("log_end", "bark", "log_end"),                   0.06, 0.25, 0.03, 0.0, 0.92, 0.0),
    ("roof",         ("roof", "roof", "roof"),                         0.04, 0.25, 0.02, 0.0, 0.85, 0.0),
    ("plaster",      ("plaster", "plaster", "plaster"),                0.03, 0.5, 0.01, 0.0, 0.95, 0.0),
    ("leaves",       ("leaves", "leaves", "leaves"),                   0.07, 0.0, 0.05, 0.0, 0.90, 0.0),
    ("wheat",        ("wheat_top", "wheat", "wheat"),                  0.10, 0.0, 0.05, 0.0, 0.90, 0.0),
    ("hay",          ("hay", "hay", "hay"),                            0.06, 0.5, 0.03, 0.0, 0.92, 0.0),
    ("wool",         ("wool", "wool", "wool"),                         0.04, 0.0, 0.00, 0.0, 0.95, 0.0),
    ("paint",        ("paint", "paint", "paint"),                      0.03, 0.0, 0.00, 0.0, 0.85, 0.0),
    ("glow",         ("glow", "glow", "glow"),                         0.00, 0.0, 0.00, 2.4, 0.60, 0.0),
    ("window",       ("window", "window", "window"),                   0.00, 0.0, 0.00, 2.6, 0.50, 0.0),
    ("metal",        ("metal", "metal", "metal"),                      0.05, 0.0, 0.00, 0.0, 0.50, 0.30),
    ("gold",         ("gold", "gold", "gold"),                         0.06, 0.0, 0.03, 0.0, 0.42, 0.40),
    ("moss",         ("moss", "moss", "moss"),                         0.06, 0.0, 0.04, 0.0, 0.95, 0.0),
    ("mossy_stone",  ("moss", "stone_mossy", "stone"),                 0.05, 0.5, 0.02, 0.0, 0.92, 0.0),
    ("ore",          ("ore", "ore", "ore"),                            0.05, 0.5, 0.02, 0.0, 0.80, 0.0),
    ("gravel",       ("gravel", "gravel", "gravel"),                   0.06, 0.5, 0.02, 0.0, 0.90, 0.0),
    ("water",        ("water", "water", "water"),                      0.03, 0.0, 0.00, 0.0, 0.15, 0.0),
]

MATS = {}               # name -> dict
IDS = {}                # name -> id (1 ..)
NAMES = [None]          # id -> name
for _i, (_n, _slots, _j, _c, _w, _e, _r, _m) in enumerate(_TABLE):
    MATS[_n] = dict(id=_i + 1, name=_n, slots=_slots, jitter=_j, cell=_c, warm=_w, emissive=_e, rough=_r, metal=_m)
    IDS[_n] = _i + 1
    NAMES.append(_n)

SLOTS = sorted({s for m in MATS.values() for s in m["slots"]} | {"cloth"})     # cloth: painted voxels marked hang() / fly()

# per slot: (emissive, roughness, metallic), for the material instances
SLOT_SURFACE = {}
for _m in MATS.values():
    for _s in _m["slots"]:
        SLOT_SURFACE.setdefault(_s, (_m["emissive"], _m["rough"], _m["metal"]))
SLOT_SURFACE["cloth"] = (0.0, 0.9, 0.0)

# The shared colours ('#rrggbb', as seen on screen) for tinted voxels: v.box(..., "paint", color=PAL["banner"])
PAL = {
    "banner": "#2f6b25", "banner_dark": "#245420", "banner_light": "#3f8530",
    "gold": "#e9b62c", "gold_dark": "#c08c1c", "gold_light": "#f8d75a",
    "cream": "#eadfc0", "cream_dark": "#cfc09a", "canvas": "#e6d7a6",
    "red": "#c23a2a", "red_dark": "#8e2a20", "white": "#f3efe6", "black": "#2a2622",
    "iron": "#4c4a50", "steel": "#a9adb4", "steel_dark": "#7c8088",
    "skin": "#b06a3a", "skin_dark": "#8e5230", "hair": "#2b211c",
    "wood": "#a8682a", "wood_dark": "#6a4220", "wood_light": "#c88a3c",
    "leaf": "#7ab428", "leaf_dark": "#4f861c", "leaf_light": "#a4d23c",
    "flower_white": "#f6f2e4", "flower_yellow": "#f6c832", "flower_orange": "#f08a24", "flower_pink": "#e68aa0",
    "lantern": "#ffb347", "lantern_hot": "#ffd98a", "fire": "#ff9a2e",
    "wool": "#f2eee2", "sheep_face": "#d8cdb6", "target_red": "#cf3b2e", "target_white": "#f0ece0",
}
