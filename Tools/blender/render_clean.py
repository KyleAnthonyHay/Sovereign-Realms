"""Clean PNGs of every unit, structure and ship of the game: the subject alone on a TRANSPARENT background (no ground,
no backdrop, no label, no shadow), for the web site, the store page, the wiki, thumbnails and AI image prompts.
The light and the camera are those of the style references (Tools/blender/render_style_refs.py, whose studio and
framing are reused), so the pictures match them.

    Windows   & "C:\\Program Files\\Blender Foundation\\Blender 5.3\\blender.exe" -b --factory-startup --python Tools\\blender\\render_clean.py
    Mac       /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python Tools/blender/render_clean.py

    ... render_clean.py -- King_David Castle          only these (file names without .png; several allowed)
    ... render_clean.py -- units | structures | ships | port | scenery | enemy      a whole group
    ... render_clean.py -- --list                     what there is (nothing is rendered)
    ... render_clean.py -- --index                    only write index.html again from the PNGs that are there

Writes References/Clean/<Name>.png (RGBA, about 1200 px on the long side, cropped to the subject with an even margin
of 7.5 %: the subject fills 85 % of the long side) and References/Clean/index.html (all of them with their names, on a
checkerboard). Everything takes about 15 minutes on a desktop CPU at the default 64 samples.

What is in it (ITEMS below; the names are the game's own: UVLBattle's building names, the units' display names)
  units       King David (King B, Tools/blender/assets/king_b.py: the figure the game uses, with the new face and
              beard), Jonathan, Swordsman, Archer, Spy, Builder, Farmer (the man and the woman): EVLUnitKind and
              AVLFarmer. They wear the game's unit materials (unit_material below: MI_King_<slot> of
              Tools/ue/import_king.py, the white paint texture on every slot, so steel is light grey and gold is
              yellow), not voxlib's building materials. (Enemy_King_David is the king an AI-against-AI match gives the enemy, vl.AIvsAI.King 1: in
              a normal match the enemy has no king.) A three-quarter view, the figure turned 35 degrees, in its rest pose, every part at its joint.
  enemy       Enemy_<Name>: the enemy's look, where it differs. A unit's green cloth turns red (TEAM_SWAP of
              Tools/ue/build_special_materials.py, repeated here on the vertex colours); a building's cloth (its
              banners and flags) is painted in the team colour (MI_Vox_cloth_Enemy). A unit or building without such
              cloth (the Builder, the Farmers, the Gold Mine...) has no enemy picture: it looks the same on both sides.
  structures  Castle, Town Hall, Barracks, Archery Range, Farm (its three variants A, B, C), Gold Mine, Watch Tower,
              Granary, Treasury, with the props their sidecars list (dummies, wheat, sheep). A building's model does NOT
              change with its level in this game (UVLBattle::ApplyLevel changes its health and numbers only), so there
              is one picture of each, not one per level.
  ships       Troop Ship, Grain Ship (SM_Boat: the grain ship took the rowing boat's place, there is no other boat).
  port        Dock, Port Arch, Port Crane, Port Tower, Port Warehouse.
  scenery     Bridge, Windmill, Gold Mine Hill (the mound a mine is set into).
  Buildings and ships are seen from the front left, 35 degrees down: the game's three-quarter angle (a ship is
  turned bow first).

Where the meshes come from. The glTFs are not in git (SourceArt/Meshes/*.gltf is ignored: they are generated). A mesh
that is in SourceArt/Meshes is used as it is; one that is missing is built from its generator (GENERATORS below) into
Saved/CleanBuild, a copy of the tools and textures that is outside git, so that SourceArt/Meshes is never written by
this script. On a fresh clone the first run therefore builds every mesh first (some minutes more).
    --rebuild     build every mesh that is asked for again from its generator, and use those (when a generator
                  changed and SourceArt/Meshes was not rebuilt: King David is always the current king_b.py this way)
    --no-build    never build: leave out what has no mesh

Other options
    --samples N   Cycles samples (default 64)        --size N     pixels on the long side (default 1200)
    --margin F    the margin, a share of the long side (default 0.075)
    --shadow      keep the soft ground shadow, in the alpha channel (off: the subject alone)
    --out DIR     another folder than References/Clean
    --gpu         as render_style_refs.py (Metal on the Mac; the CPU otherwise)

The renders run one at a time. If the file C:\\Dev\\ThermalWatchdog\\OVERHEAT.flag (or $VL_THERMAL_FLAG) exists, the
script stops before the next one.
"""
import html
import json
import math
import os
import shutil
import subprocess
import sys

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_ARGV = sys.argv[:]
ARGS = _ARGV[_ARGV.index("--") + 1:] if "--" in _ARGV else []
VALUED = ("--samples", "--size", "--margin", "--out")


def opt(name, default, cast):
    return cast(ARGS[ARGS.index(name) + 1]) if name in ARGS else default


SAMPLES = opt("--samples", 64, int)
SIZE = opt("--size", 1200, int)
MARGIN = opt("--margin", 0.075, float)
SHADOW = "--shadow" in ARGS
REBUILD = "--rebuild" in ARGS
NO_BUILD = "--no-build" in ARGS
ONLY = [a for i, a in enumerate(ARGS) if not a.startswith("--") and (i == 0 or ARGS[i - 1] not in VALUED)]

# render_style_refs runs its main() on import: give it a name it renders nothing for (as render_portraits.py does)
sys.argv = [_ARGV[0], "--", "__nothing__", "--samples", str(SAMPLES)] + (["--gpu"] if "--gpu" in ARGS else [])
import render_style_refs as R  # noqa: E402
sys.argv = _ARGV
import voxlib as V  # noqa: E402

ROOT = V.ROOT
OUT = os.path.abspath(opt("--out", os.path.join(ROOT, "References", "Clean"), str))
SRC = V.MESHES                                              # SourceArt/Meshes: read, never written
BUILD_ROOT = os.path.join(ROOT, "Saved", "CleanBuild")      # outside git (Saved/ is ignored)
BUILT = os.path.join(BUILD_ROOT, "SourceArt", "Meshes")
THERMAL_FLAG = os.environ.get("VL_THERMAL_FLAG", r"C:\Dev\ThermalWatchdog\OVERHEAT.flag")

# file name (without .png), the game's name, group, kind, the rig's json (a unit) or the mesh (anything else)
ITEMS = [
    ("King_David", "King David", "units", "unit", "SM_KingB"),
    ("Jonathan", "Jonathan", "units", "unit", "SM_Jonathan"),
    ("Swordsman", "Swordsman", "units", "unit", "SM_Swordsman"),
    ("Archer", "Archer", "units", "unit", "SM_Archer"),
    ("Spy", "Spy", "units", "unit", "SM_Spy"),
    ("Builder", "Builder", "units", "unit", "SM_Builder"),
    ("Farmer_Man", "Farmer (man)", "units", "unit", "SM_FarmerMan"),
    ("Farmer_Woman", "Farmer (woman)", "units", "unit", "SM_FarmerWoman"),
    ("Castle", "Castle", "structures", "building", "SM_Castle"),
    ("Town_Hall", "Town Hall", "structures", "building", "SM_TownHall"),
    ("Barracks", "Barracks", "structures", "building", "SM_BarracksYard"),
    ("Archery_Range", "Archery Range", "structures", "building", "SM_ArcheryHall"),
    ("Farm_A", "Farm (variant A)", "structures", "building", "SM_Farmstead_A"),
    ("Farm_B", "Farm (variant B)", "structures", "building", "SM_Farmstead_B"),
    ("Farm_C", "Farm (variant C)", "structures", "building", "SM_Farmstead_C"),
    ("Gold_Mine", "Gold Mine", "structures", "building", "SM_MineCliff"),
    ("Watch_Tower", "Watch Tower", "structures", "building", "SM_WatchTower"),
    ("Granary", "Granary", "structures", "building", "SM_Granary"),
    ("Treasury", "Treasury", "structures", "building", "SM_Treasury"),
    ("Troop_Ship", "Troop Ship", "ships", "ship", "SM_TroopShip"),
    ("Grain_Ship", "Grain Ship", "ships", "ship", "SM_Boat"),
    ("Dock", "Dock", "port", "building", "SM_Dock"),
    ("Port_Arch", "Port Arch", "port", "building", "SM_Port_Arch"),
    ("Port_Crane", "Port Crane", "port", "building", "SM_Port_Crane"),
    ("Port_Tower", "Port Tower", "port", "building", "SM_Port_Tower"),
    ("Port_Warehouse", "Port Warehouse", "port", "building", "SM_Port_Warehouse"),
    ("Bridge", "Bridge", "scenery", "building", "SM_Bridge"),
    ("Windmill", "Windmill", "scenery", "building", "SM_Windmill"),
    ("Gold_Mine_Hill", "Gold Mine Hill", "scenery", "building", "SM_MineMound"),
]
GROUPS = [("units", "Units"), ("enemy", "The enemy's look (where it differs)"), ("structures", "Structures"),
          ("ships", "Ships"), ("port", "Port"), ("scenery", "Scenery")]
# the groups an enemy picture is tried for (the port and the scenery belong to no side)
ENEMY_OF = ("units", "structures", "ships")

# generator (Tools/blender/assets/<name>.py), its arguments after --no-render, the meshes it makes (a prefix)
GENERATORS = [
    ("king_b", [], ["SM_KingB_"]),
    ("jonathan", [], ["SM_Jonathan_"]),
    ("troop_swordsman", [], ["SM_Swordsman_"]),
    ("troop_archer", [], ["SM_Archer_"]),
    ("troop_spy", [], ["SM_Spy_"]),
    ("troop_builder", [], ["SM_Builder_"]),
    ("troop_farmer_man", [], ["SM_FarmerMan_"]),
    ("troop_farmer_woman", [], ["SM_FarmerWoman_"]),
    ("castle", [], ["SM_Castle"]),
    ("townhall", [], ["SM_TownHall"]),
    ("barracks_yard", [], ["SM_BarracksYard"]),
    ("barracks", [], ["SM_TrainingDummy"]),                 # (the old barracks' script makes the yard's dummies)
    ("archery_hall", [], ["SM_ArcheryHall"]),
    ("farmstead", ["--variants", "all"], ["SM_Farmstead_", "SM_Chicken", "SM_Pig"]),
    ("farm", [], ["SM_Sheep", "SM_Wheat"]),
    ("range_mine", [], ["SM_MineCliff", "SM_MineCart", "SM_Target", "SM_ArrowBarrel"]),
    ("watch_tower", [], ["SM_WatchTower"]),
    ("granary", [], ["SM_Granary"]),
    ("treasury", [], ["SM_Treasury"]),
    ("troopship", [], ["SM_TroopShip"]),
    ("dock", [], ["SM_Dock", "SM_Boat"]),
    ("ports", [], ["SM_Port_"]),
    ("props", [], ["SM_Bridge", "SM_Barrel", "SM_Crate", "SM_CrateStack"]),
    ("windmill", [], ["SM_Windmill"]),
    ("mine_mound", [], ["SM_MineMound"]),
]

CHAR_VIEW = dict(az=0.0, el=8.0, lens=85.0)         # the figure is turned, the camera and the lights stay
CHAR_YAW = 35.0
BUILDING_VIEW = dict(az=-35.0, el=35.0, lens=60.0)  # from the front left, 35 degrees down
SHIP_YAW = 180.0                                    # a ship is turned bow first (its mesh has the bow at +X)
TEAM_TINT = (0.8, 0.06, 0.05)                       # MI_Vox_cloth_Enemy's TeamTint (linear)


# ------------------------------------------------------------------------------------------------------- meshes

def mesh_dir(name):
    """The folder a mesh (its .gltf and .json) is read from, or None."""
    order = (BUILT, SRC) if REBUILD else (SRC, BUILT)
    for d in order:
        if os.path.exists(os.path.join(d, name + ".gltf")):
            return d
    return None


def sidecar(name, at=None):
    """A mesh's json, from where its glTF is (a rig's json has no glTF of its own: `at` names one of its parts)."""
    d = mesh_dir(at or name)
    for folder in ([d] if d else []) + [SRC, BUILT]:
        p = os.path.join(folder, name + ".json")
        if os.path.exists(p):
            return json.load(open(p))
    return {}


def meshes_of(kind, src):
    """Every mesh an item needs (a unit's parts; a building, its props and its extras)."""
    if kind == "unit":
        return [p["mesh"] for p in sidecar(src, src + "_Body").get("parts", {}).values()]
    out = [src] + sorted(set(p["mesh"] for p in sidecar(src).get("props", [])))
    if src == "SM_Windmill":
        out.append("SM_Windmill_Sails")
    return out


def generator_of(mesh):
    return [g for g in GENERATORS if any(mesh == p or (p.endswith("_") and mesh.startswith(p)) or mesh.startswith(p + "_") for p in g[2])]


def mirror():
    """Saved/CleanBuild: the generators, the textures and the sidecars, copied, so that a generator run there writes
    its meshes there (voxlib takes the project's root from where it lies)."""
    def copy_all(src, dst, ext, keep=False):
        os.makedirs(dst, exist_ok=True)
        for f in os.listdir(src):
            if f.endswith(ext) and not (keep and os.path.exists(os.path.join(dst, f))):
                shutil.copy2(os.path.join(src, f), os.path.join(dst, f))
    copy_all(HERE, os.path.join(BUILD_ROOT, "Tools", "blender"), ".py")
    copy_all(os.path.join(HERE, "assets"), os.path.join(BUILD_ROOT, "Tools", "blender", "assets"), ".py")
    copy_all(V.TEXTURES, os.path.join(BUILD_ROOT, "SourceArt", "Textures"), ".png")
    copy_all(SRC, BUILT, ".json", keep=True)                  # (a sidecar built there is newer than the project's)
    copy_all(os.path.join(ROOT, "SourceArt"), os.path.join(BUILD_ROOT, "SourceArt"), ".json")
    os.makedirs(os.path.join(BUILD_ROOT, "SourceArt", "Previews"), exist_ok=True)
    os.makedirs(os.path.join(BUILD_ROOT, "logs"), exist_ok=True)


def build(todo):
    """Run the generators that make the meshes of `todo` (--no-render), one after the other, in Saved/CleanBuild."""
    gens = []
    for m in todo:
        for g in generator_of(m):
            if g not in gens:
                gens.append(g)
    if not gens:
        return
    mirror()
    for name, extra, _ in [g for g in GENERATORS if g in gens]:
        if overheated():
            return
        script = os.path.join(BUILD_ROOT, "Tools", "blender", "assets", name + ".py")
        log = os.path.join(BUILD_ROOT, "logs", name + ".log")
        print("building %s (log: %s)" % (name, log), flush=True)
        with open(log, "w") as f:
            code = subprocess.call([bpy.app.binary_path, "-b", "--factory-startup", "--python", script, "--", "--no-render"] + extra,
                                   stdout=f, stderr=subprocess.STDOUT)
        if code or "Traceback" in open(log, errors="replace").read():
            print("  %s FAILED (exit %d): see the log" % (name, code))


def import_gltf(name):
    """R.import_gltf, from the folder the mesh is in."""
    was = V.MESHES
    V.MESHES = mesh_dir(name)
    try:
        return R.import_gltf(name)
    finally:
        V.MESHES = was


_props = {}


def place_props(mesh):
    """The instances a building's sidecar lists (R.place_props, each prop from the folder it is in)."""
    out = []
    for pr in sidecar(mesh).get("props", []):
        name = pr["mesh"]
        if mesh_dir(name) is None:
            continue
        if name not in _props:
            _props[name] = import_gltf(name)
            for o in _props[name]:
                o.hide_render = o.hide_viewport = True
        for o in _props[name]:
            c = o.copy()
            bpy.context.scene.collection.objects.link(c)
            c.hide_render = c.hide_viewport = False
            k = float(pr.get("scale", 1.0))
            c.location = pr["pos"]
            c.rotation_euler = (0.0, 0.0, math.radians(float(pr.get("yaw", 0.0))))
            c.scale = (k, k, k)
            out.append(c)
    return out


# A unit's slots in the game (MI_King_<slot>, Tools/ue/import_king.py): (metallic, roughness, tint). Its colours are all
# in its vertex colours, so EVERY slot has the plain white paint texture: the buildings' dark metal and yellow gold
# textures (voxlib's preview materials, right for a building) would multiply its steel to black and its gold to orange.
UNIT_SURFACE = {"gold": (0.55, 0.38, (1.25, 1.15, 1.0)), "metal": (0.35, 0.42, (1.45, 1.45, 1.5)), "wool": (0.0, 0.95, (1.0, 1.0, 1.0))}
UNIT_DEFAULT = (0.0, 0.85, (1.0, 1.0, 1.0))


def unit_material(slot, layer):
    """The game's material of a unit's slot: paint texture x vertex colour x tint, its metallic and roughness."""
    name = "Unit_" + slot
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    metal, rough, tint = UNIT_SURFACE.get(slot, UNIT_DEFAULT)
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    tex = nt.nodes.new("ShaderNodeTexImage")
    path = os.path.join(V.TEXTURES, "T_Vox_paint.png")
    if os.path.exists(path):
        tex.image = bpy.data.images.load(path, check_existing=True)
    tex.interpolation = "Closest"
    col = nt.nodes.new("ShaderNodeVertexColor")
    col.layer_name = layer
    mul = nt.nodes.new("ShaderNodeMixRGB")
    mul.blend_type = "MULTIPLY"
    mul.inputs[0].default_value = 1.0
    nt.links.new(tex.outputs["Color"], mul.inputs[1])
    nt.links.new(col.outputs["Color"], mul.inputs[2])
    tnt = nt.nodes.new("ShaderNodeMixRGB")
    tnt.blend_type = "MULTIPLY"
    tnt.inputs[0].default_value = 1.0
    tnt.inputs[2].default_value = (*tint, 1.0)
    nt.links.new(mul.outputs[0], tnt.inputs[1])
    nt.links.new(tnt.outputs[0], bsdf.inputs["Base Color"])
    bsdf.inputs["Metallic"].default_value = metal
    bsdf.inputs["Roughness"].default_value = rough
    if slot == "glow":                                           # a lantern's light (Emissive 6 in the game, with bloom)
        nt.links.new(tnt.outputs[0], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = 1.8
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    return mat


def place_unit(rig):
    """The figure in its rest pose (R.place_character): every part at its own pivot, turned CHAR_YAW."""
    root = bpy.data.objects.new(rig + "_root", None)
    bpy.context.scene.collection.objects.link(root)
    obs = []
    for part in sidecar(rig, rig + "_Body")["parts"].values():
        for o in import_gltf(part["mesh"]):
            o.parent = None
            o.location = part["pivot"]
            o.rotation_euler = (0.0, 0.0, 0.0)
            o.parent = root
            obs.append(o)
            layer = o.data.color_attributes[0].name if o.data.color_attributes else "Col"
            for i, m in enumerate(o.data.materials):             # voxlib's building materials -> the units' own
                if m is not None and m.name.startswith("Vox_"):
                    o.data.materials[i] = unit_material(m.name[4:].split(".")[0], layer)
    root.rotation_euler = (0.0, 0.0, math.radians(CHAR_YAW))
    return obs


def place_building(mesh, turn=0.0):
    obs = import_gltf(mesh)
    if mesh == "SM_Windmill":
        hub = sidecar(mesh).get("hub")
        if hub and mesh_dir("SM_Windmill_Sails"):
            for s in import_gltf("SM_Windmill_Sails"):
                s.location = hub
                s.rotation_euler = (0.0, math.radians(45.0), 0.0)
                obs.append(s)
    obs += place_props(mesh)
    if turn:
        root = bpy.data.objects.new(mesh + "_root", None)
        bpy.context.scene.collection.objects.link(root)
        for o in obs:
            if o.parent is None:
                o.parent = root
        root.rotation_euler = (0.0, 0.0, math.radians(turn))
    return obs


# ------------------------------------------------------------------------------------------------------- the enemy

def is_cloth(material):
    n = material.name.lower() if material else ""
    return "paint" in n or "cloth" in n or "sway" in n


def team_swap(c):
    """TEAM_SWAP of Tools/ue/build_special_materials.py (Mix 1): green cloth, hue about 50..170 degrees, to a red of
    like brightness. c: (n, 3) linear colours. Returns the colours and each one's weight."""
    def smooth(a, b, x):
        t = np.clip((x - a) / (b - a), 0.0, 1.0)
        return t * t * (3.0 - 2.0 * t)
    r, g, b = c[:, 0], c[:, 1], c[:, 2]
    mx, mn = c.max(axis=1), c.min(axis=1)
    dl = mx - mn
    ok = dl > 1.0e-4
    d = np.where(ok, dl, 1.0)
    h = np.where(mx == g, 2.0 + (b - r) / d, np.where(mx == r, (g - b) / d, 4.0 + (r - g) / d))
    h = np.mod(h / 6.0 + 1.0, 1.0) * 360.0
    s = dl / np.maximum(mx, 1.0e-6)
    w = smooth(48.0, 53.0, h) * (1.0 - smooth(160.0, 175.0, h)) * smooth(0.18, 0.32, s) * ok
    h2 = np.mod((4.0 - (h - 80.0) * 0.15) / 360.0 + 1.0, 1.0)
    k = np.clip(np.abs(np.mod(h2[:, None] + np.array([0.0, 2.0 / 3.0, 1.0 / 3.0])[None, :], 1.0) * 6.0 - 3.0) - 1.0, 0.0, 1.0)
    red = np.minimum(mx * 1.5, 1.0)[:, None] * (1.0 + (k - 1.0) * np.clip(s * 1.1 + 0.08, 0.0, 1.0)[:, None])
    return c + (red - c) * w[:, None], w


def enemy_unit(obs):
    """Repaints the vertex colours of the figure's cloth slots as M_VoxUnit's TeamMix 1 does. Returns the share of the
    figure's corners that changed (0: it has no green cloth, the enemy's looks the same)."""
    changed = total = 0
    for me in set(o.data for o in obs):
        if not me.color_attributes:
            continue
        attr = me.color_attributes[0]
        n = len(attr.data)
        col = np.empty(n * 4, np.float32)
        attr.data.foreach_get("color", col)
        col = col.reshape(-1, 4)
        cloth = np.array([is_cloth(m) for m in me.materials] or [False])
        mat = np.empty(len(me.polygons), np.int32)
        me.polygons.foreach_get("material_index", mat)
        if attr.domain == "CORNER":
            loops = np.empty(len(me.polygons), np.int32)
            me.polygons.foreach_get("loop_total", loops)
            mask = np.repeat(cloth[np.clip(mat, 0, len(cloth) - 1)], loops)
        else:
            mask = np.full(n, bool(cloth.any()))
        new, w = team_swap(col[:, :3].astype(np.float64))
        w = w * mask
        col[:, :3] = np.where(mask[:, None], new, col[:, :3])
        attr.data.foreach_set("color", col.ravel())
        me.update()
        changed += int((w > 0.5).sum())
        total += n
    return changed / max(total, 1)


def enemy_building(obs):
    """The cloth slots (banners, flags) in the team colour, as MI_Vox_cloth_Enemy: light and dark kept, the hue the
    enemy's red. Returns how many slots were changed."""
    count = 0
    for o in obs:
        for i, m in enumerate(o.data.materials):
            if m is None or "cloth" not in m.name.lower():
                continue
            if not m.get("enemy"):
                red = bpy.data.materials.get(m.name + "_Enemy")
                if red is None:
                    red = m.copy()
                    red.name = m.name + "_Enemy"
                    red["enemy"] = True
                    nt = red.node_tree
                    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
                    base = bsdf.inputs["Base Color"].links[0].from_socket
                    dot = nt.nodes.new("ShaderNodeVectorMath")
                    dot.operation = "DOT_PRODUCT"
                    dot.inputs[1].default_value = (0.3, 0.59, 0.11)
                    nt.links.new(base, dot.inputs[0])
                    lum = nt.nodes.new("ShaderNodeMath")
                    lum.operation = "MULTIPLY_ADD"
                    lum.use_clamp = True
                    lum.inputs[1].default_value = 3.0
                    lum.inputs[2].default_value = 0.12
                    nt.links.new(dot.outputs["Value"], lum.inputs[0])
                    tint = nt.nodes.new("ShaderNodeVectorMath")
                    tint.operation = "SCALE"
                    tint.inputs[0].default_value = TEAM_TINT
                    nt.links.new(lum.outputs[0], tint.inputs["Scale"])
                    nt.links.new(tint.outputs["Vector"], bsdf.inputs["Base Color"])
                o.data.materials[i] = red
            count += 1
    return count


# ------------------------------------------------------------------------------------------------------- render

def overheated():
    if os.path.exists(THERMAL_FLAG):
        print("OVERHEAT flag present (%s): stopping" % THERMAL_FLAG)
        return True
    return False


def trim(src, dst):
    """Crop the render to the subject (its alpha) with an even margin of transparent pixels, and save it as RGBA."""
    img = bpy.data.images.load(src)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(h, w, 4)
    bpy.data.images.remove(img)
    solid = px[:, :, 3] > (4.0 / 255.0)
    if not solid.any():
        print("nothing rendered:", dst)
        return None
    ys, xs = np.where(solid.any(axis=1))[0], np.where(solid.any(axis=0))[0]
    x0, x1, y0, y1 = xs[0], xs[-1] + 1, ys[0], ys[-1] + 1
    m = int(round(max(x1 - x0, y1 - y0) * MARGIN / (1.0 - 2.0 * MARGIN)))
    out = np.zeros((y1 - y0 + 2 * m, x1 - x0 + 2 * m, 4), np.float32)
    out[m:m + y1 - y0, m:m + x1 - x0] = px[y0:y1, x0:x1]
    out[out[:, :, 3] <= 0.0] = 0.0
    oh, ow = out.shape[:2]
    o = bpy.data.images.new("clean", ow, oh, alpha=True)
    o.alpha_mode = "STRAIGHT"
    o.pixels.foreach_set(out.ravel())
    o.filepath_raw = dst
    o.file_format = "PNG"
    o.save()
    bpy.data.images.remove(o)
    print("wrote %s (%d x %d)" % (dst, ow, oh), flush=True)
    return ow, oh


def shoot(obs, view, dst):
    scene = bpy.context.scene
    pts = R.world_points(obs)
    catcher = bpy.data.objects["Catcher"]
    catcher.location.z = float(pts[:, 2].min()) - 0.002
    catcher.hide_render = not SHADOW
    fill = 1.0 - 2.0 * MARGIN
    R.frame(pts, view["az"], view["el"], (SIZE, SIZE), fill, fill, view["lens"])
    tmp = os.path.join(R.TMP, os.path.basename(dst))
    scene.render.film_transparent = True
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.filepath = tmp
    bpy.ops.render.render(write_still=True)
    return trim(tmp, dst)


def render_item(fname, kind, src, enemy=False):
    """Renders one item (or its enemy look). Returns False when there is nothing to show (no enemy look)."""
    V.reset_scene()
    _props.clear()
    R.studio(0.0)
    obs = place_unit(src) if kind == "unit" else place_building(src, SHIP_YAW if kind == "ship" else 0.0)
    view = CHAR_VIEW if kind == "unit" else BUILDING_VIEW
    if enemy:
        if kind == "unit":
            share = enemy_unit(obs)
            if share < 0.005:
                return False
        elif not enemy_building(obs):
            return False
        fname = "Enemy_" + fname
    shoot(obs, view, os.path.join(OUT, fname + ".png"))
    return True


# ------------------------------------------------------------------------------------------------------- index

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sovereign Realms: clean renders</title>
<style>
body { margin: 0; padding: 24px; background: #1d1f24; color: #e8e8ea; font: 15px/1.4 system-ui, sans-serif; }
h1 { font-size: 22px; margin: 0 0 4px; } h2 { font-size: 17px; margin: 28px 0 10px; color: #d8c48a; }
p { margin: 0 0 8px; color: #a8a9ad; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 14px; }
a.card { display: block; text-decoration: none; color: inherit; border-radius: 8px; overflow: hidden; background: #2a2d34; }
.pic { height: 220px; display: flex; align-items: center; justify-content: center;
  background: conic-gradient(#c9cbd1 25%, #e6e7ea 0 50%, #c9cbd1 0 75%, #e6e7ea 0) 0 0 / 20px 20px; }
.pic img { max-width: 100%; max-height: 100%; display: block; }
.name { padding: 8px 10px 2px; font-weight: 600; } .file { padding: 0 10px 9px; color: #9a9ca2; font-size: 12px; }
</style></head><body>
<h1>Sovereign Realms: clean renders</h1>
<p>Every unit, structure and ship, alone on a transparent background (the checkerboard is this page's). Made by
<code>Tools/blender/render_clean.py</code>; a building's model does not change with its level.</p>
%s
</body></html>
"""


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


def write_index():
    """index.html: every picture that is in the folder, by group, with the game's name."""
    cards = {g: [] for g, _ in GROUPS}
    for fname, label, group, _, _ in ITEMS:
        for pre, lab, grp in (("", label, group), ("Enemy_", "Enemy " + label, "enemy")):
            p = os.path.join(OUT, pre + fname + ".png")
            if os.path.exists(p):
                w, h = png_size(p)
                cards[grp].append('<a class="card" href="%s"><div class="pic"><img src="%s" alt="%s" loading="lazy"></div>'
                                  '<div class="name">%s</div><div class="file">%s &middot; %d &times; %d</div></a>'
                                  % (pre + fname + ".png", pre + fname + ".png", html.escape(lab), html.escape(lab), pre + fname + ".png", w, h))
    body = "".join('<h2>%s</h2>\n<div class="grid">\n%s\n</div>\n' % (title, "\n".join(cards[g])) for g, title in GROUPS if cards[g])
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(PAGE.replace("%s", body))
    print("wrote %s (%d pictures)" % (os.path.join(OUT, "index.html"), sum(len(c) for c in cards.values())))


# ------------------------------------------------------------------------------------------------------- main

def wanted(fname, group, enemy):
    if not ONLY:
        return True
    name = ("Enemy_" if enemy else "") + fname
    return name in ONLY or (enemy and "enemy" in ONLY) or (not enemy and group in ONLY) or "all" in ONLY


def main():
    known = [f for f, *_ in ITEMS] + ["Enemy_" + f for f, _, g, _, _ in ITEMS if g in ENEMY_OF] + [g for g, _ in GROUPS] + ["all"]
    for n in ONLY:
        if n not in known:
            print("unknown name: %s (see --list)" % n)
    if "--list" in ARGS:
        for g, title in GROUPS:
            print("%-11s %s" % (g, " ".join(f for f, _, grp, _, _ in ITEMS if grp == g) or "Enemy_<Name> of a unit, structure or ship"))
        return
    os.makedirs(OUT, exist_ok=True)
    if "--index" in ARGS:
        write_index()
        return
    jobs = [(it, e) for it in ITEMS for e in (False, True) if (not e or it[2] in ENEMY_OF) and wanted(it[0], it[2], e)]
    # the meshes: those that are missing (all of them with --rebuild) are built outside SourceArt/Meshes first
    need = []
    for (fname, _, _, kind, src), _ in jobs:
        for m in meshes_of(kind, src) or [src + "_Body"]:
            if m not in need:
                need.append(m)
    if not NO_BUILD:
        build(need if REBUILD else [m for m in need if mesh_dir(m) is None])
    os.makedirs(R.TMP, exist_ok=True)
    done, same, missing = [], [], []
    for (fname, label, group, kind, src), enemy in jobs:
        if overheated():
            missing.append(("Enemy_" if enemy else "") + fname + " (stopped: overheat)")
            continue
        lack = [m for m in (meshes_of(kind, src) or [src + "_Body"]) if mesh_dir(m) is None]
        if lack:
            if not enemy:
                missing.append("%s (no mesh: %s)" % (fname, ", ".join(lack[:4]) + (" ..." if len(lack) > 4 else "")))
            continue
        if render_item(fname, kind, src, enemy):
            done.append(("Enemy_" if enemy else "") + fname)
        elif enemy:
            same.append(fname)
            stale = os.path.join(OUT, "Enemy_" + fname + ".png")
            if os.path.exists(stale):
                os.remove(stale)
    shutil.rmtree(R.TMP, ignore_errors=True)
    write_index()
    print("rendered %d: %s" % (len(done), " ".join(done)))
    if same:
        print("no enemy picture (the same on both sides): %s" % " ".join(same))
    if missing:
        print("NOT rendered: %s" % "; ".join(missing))


main()
