"""Builds /Game/Maps/L_VoxelVillage from SourceArt/layout.json (run inside the editor, not during PIE):

    python3 Tools/ue_py.py Tools/ue/build_level.py

Everything in the level is made here, so the script can be run again after any change: it clears the level and
places the light, sky, fog, post-process, the postcard camera, the terrain tiles, the water, every instance of the
layout and a lamp at every lantern.

Axes: the layout is in metres with +Y north (Blender); Unreal is centimetres with +Y south: (x, y, z) -> (100x, -100y, 100z),
and a counter-clockwise yaw becomes its negative.
"""
import json
import math
import os

import unreal

ROOT = os.path.abspath(unreal.Paths.project_dir())
SRC = os.path.join(ROOT, "SourceArt")
MAP = "/Game/Maps/L_VoxelVillage"
MESH = "/Game/Voxel/Meshes/"
LOOK = globals().get("LOOK") or {}

eal = unreal.EditorAssetLibrary
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

# ---- the look (LOOK overrides any of these from the command line while tuning)
P = dict(
    sun_bearing=100.0,          # where the sun stands: degrees clockwise from north
    sun_elevation=42.0,
    sun_lux=5.5,
    sun_color=(1.0, 0.85, 0.64),
    sun_shafts=1.6,            # volumetric scattering of the sun (god rays through the trees)
    sky_intensity=2.8,
    sky_tint=(1.0, 0.94, 0.86),
    fog_density=0.012,
    fog_falloff=0.12,
    fog_color=(0.50, 0.42, 0.30),
    fog_albedo=(1.0, 0.92, 0.78),
    fog_extinction=1.0,
    exposure=0.6,
    bloom=0.75,
    bloom_threshold=-1.0,
    saturation=0.92,
    contrast=1.0,
    white_temp=6100.0,
    vignette=0.45,
    lamp_lumens=9.0,          # per litre of glow voxels... see lamps()
    lamp_radius=480.0,
    lamp_color=(1.0, 0.76, 0.48),
)
P.update(LOOK)


def vec(x, y, z):
    return unreal.Vector(x * 100.0, -y * 100.0, z * 100.0)


def lin(c, a=1.0):
    return unreal.LinearColor(c[0], c[1], c[2], a)


def load_or_new_level():
    if eal.does_asset_exist(MAP):
        les.load_level(MAP)
    else:
        les.new_level(MAP)
    for a in eas.get_all_level_actors():
        if isinstance(a, (unreal.WorldSettings, unreal.Brush)) and not isinstance(a, unreal.Volume):
            continue
        try:
            eas.destroy_actor(a)
        except Exception:
            pass


def spawn(cls, loc=None, rot=None, label=None, folder=None):
    a = eas.spawn_actor_from_class(cls, loc or unreal.Vector(0, 0, 0), rot or unreal.Rotator(0, 0, 0))
    if label:
        a.set_actor_label(label)
    if folder:
        a.set_folder_path(folder)
    return a


def lighting():
    b, e = math.radians(P["sun_bearing"]), math.radians(P["sun_elevation"])
    # the light travels away from the sun: Blender direction (-sin b cos e, -cos b cos e, -sin e) -> Unreal (x, -y, z)
    dx, dy, dz = -math.sin(b) * math.cos(e), math.cos(b) * math.cos(e), -math.sin(e)
    yaw = math.degrees(math.atan2(dy, dx))
    sun = spawn(unreal.DirectionalLight, unreal.Vector(0, 0, 3000), unreal.Rotator(roll=0, pitch=-P["sun_elevation"], yaw=yaw), "Sun", "Light")
    lc = sun.get_component_by_class(unreal.DirectionalLightComponent)
    lc.set_mobility(unreal.ComponentMobility.MOVABLE)
    lc.set_editor_property("intensity", P["sun_lux"])
    lc.set_editor_property("light_color", lin(P["sun_color"]).to_rgbe() if False else unreal.Color(int(P["sun_color"][2] * 255), int(P["sun_color"][1] * 255), int(P["sun_color"][0] * 255), 255))
    lc.set_editor_property("atmosphere_sun_light", True)
    lc.set_editor_property("volumetric_scattering_intensity", P["sun_shafts"])
    lc.set_editor_property("light_source_angle", 2.2)
    lc.set_editor_property("cast_shadows", True)
    for k, v in (("dynamic_shadow_distance_movable_light", 30000.0), ("shadow_sharpen", 0.0)):
        try:
            lc.set_editor_property(k, v)
        except Exception:
            pass

    spawn(unreal.SkyAtmosphere, label="SkyAtmosphere", folder="Light")
    sky = spawn(unreal.SkyLight, unreal.Vector(0, 0, 2000), label="SkyLight", folder="Light")
    sc = sky.get_component_by_class(unreal.SkyLightComponent)
    sc.set_mobility(unreal.ComponentMobility.MOVABLE)
    sc.set_editor_property("real_time_capture", True)        # (cheap without volumetric clouds: they were 3.5 ms of it)
    sc.set_editor_property("intensity", P["sky_intensity"])
    sc.set_editor_property("light_color", unreal.Color(int(P["sky_tint"][2] * 255), int(P["sky_tint"][1] * 255), int(P["sky_tint"][0] * 255), 255))

    fog = spawn(unreal.ExponentialHeightFog, unreal.Vector(0, 0, 0), label="Fog", folder="Light")
    fc = fog.get_component_by_class(unreal.ExponentialHeightFogComponent)
    fc.set_editor_property("fog_density", P["fog_density"])
    fc.set_editor_property("fog_height_falloff", P["fog_falloff"])
    fc.set_editor_property("fog_inscattering_luminance", lin(P["fog_color"]))
    fc.set_editor_property("enable_volumetric_fog", True)
    fc.set_editor_property("volumetric_fog_scattering_distribution", 0.72)
    fc.set_editor_property("volumetric_fog_albedo", unreal.Color(int(P["fog_albedo"][2] * 255), int(P["fog_albedo"][1] * 255), int(P["fog_albedo"][0] * 255), 255))
    fc.set_editor_property("volumetric_fog_extinction_scale", P["fog_extinction"])
    fc.set_editor_property("volumetric_fog_distance", 12000.0)

    ppv = spawn(unreal.PostProcessVolume, label="Look", folder="Light")
    ppv.set_editor_property("unbound", True)
    s = ppv.get_editor_property("settings")

    def setp(name, value):
        s.set_editor_property("override_" + name, True)
        s.set_editor_property(name, value)

    setp("auto_exposure_method", unreal.AutoExposureMethod.AEM_MANUAL)
    setp("auto_exposure_bias", P["exposure"])
    try:
        setp("auto_exposure_apply_physical_camera_exposure", False)
    except Exception:
        pass
    setp("bloom_intensity", P["bloom"])
    setp("bloom_threshold", P["bloom_threshold"])
    setp("vignette_intensity", P["vignette"])
    setp("white_temp", P["white_temp"])
    setp("color_saturation", unreal.Vector4(P["saturation"], P["saturation"], P["saturation"], 1.0))
    setp("color_contrast", unreal.Vector4(P["contrast"], P["contrast"], P["contrast"], 1.0))
    setp("motion_blur_amount", 0.0)
    try:
        setp("lumen_scene_detail", 2.0)
        setp("lumen_final_gather_quality", 2.0)
    except Exception:
        pass
    sil = eal.load_asset("/Game/Voxel/Materials/M_Silhouette")           # the hero shows through trees and buildings
    if sil:
        s.set_editor_property("weighted_blendables", unreal.WeightedBlendables(array=[unreal.WeightedBlendable(weight=1.0, object=sil)]))
    ppv.set_editor_property("settings", s)


def postcard(layout):
    cam = layout["camera"]
    px, py, pz = cam["pos"]
    a = math.radians(cam["az"])
    # looking direction in Blender (-sin a, cos a) -> Unreal (x, -y)
    yaw = math.degrees(math.atan2(-math.cos(a), -math.sin(a)))
    actor = spawn(unreal.CameraActor, vec(px, py, pz), unreal.Rotator(roll=0, pitch=-cam["el"], yaw=yaw), "PostcardCamera", "Cameras")
    actor.tags = [unreal.Name("Postcard")]
    cc = actor.get_component_by_class(unreal.CameraComponent)
    cc.set_editor_property("field_of_view", cam["hfov"])
    cc.set_editor_property("aspect_ratio", cam["width"] / float(cam["height"]))
    cc.set_editor_property("constrain_aspect_ratio", True)
    sp = layout["spawn"]
    start = spawn(unreal.PlayerStart, vec(sp["pos"][0], sp["pos"][1], sp["pos"][2] + 1.2), unreal.Rotator(roll=0, pitch=0, yaw=-sp["yaw"]), "KingStart", "Cameras")
    return actor, start


_mesh_cache = {}
_meta_cache = {}


def mesh(name):
    if name not in _mesh_cache:
        p = MESH + name
        _mesh_cache[name] = eal.load_asset(p) if eal.does_asset_exist(p) else None
    return _mesh_cache[name]


def meta(name):
    if name not in _meta_cache:
        p = os.path.join(SRC, "Meshes", name + ".json")
        _meta_cache[name] = json.load(open(p)) if os.path.exists(p) else {}
    return _meta_cache[name]


NO_SHADOW = ("SM_GrassTuft", "SM_Flowers", "SM_LilyPad")
# what can be selected from the overview, and what it is called
SELECTABLE = {"SM_TownHall": "Town Hall", "SM_Barracks": "Barracks", "SM_ArcheryRange": "Archery Range", "SM_MineCliff": "Gold Mine",
              "SM_FarmCottage_A": "Farm", "SM_FarmCottage_B": "Farm", "SM_Castle": "Castle", "SM_Bridge": "Bridge",
              "SM_PlazaBanner": "Village Banner",
              "SM_BarracksYard": "Barracks", "SM_ArcheryHall": "Archery Range", "SM_Farmstead": "Farm", "SM_WatchTower": "Watch Tower"}
NO_COLLIDE_GROUPS = ("plants",)


def place(name, x, y, z, yaw=0.0, scale=(1.0, 1.0, 1.0), folder="Village", label=None):
    sm = mesh(name)
    if sm is None:
        return None
    a = eas.spawn_actor_from_object(sm, vec(x, y, z), unreal.Rotator(roll=0, pitch=0, yaw=-yaw))
    a.set_actor_scale3d(unreal.Vector(scale[0], scale[1], scale[2]))
    a.set_folder_path(folder)
    if label:
        a.set_actor_label(label)
    c = a.static_mesh_component
    c.set_mobility(unreal.ComponentMobility.STATIC)
    if name.startswith(NO_SHADOW):
        c.set_editor_property("cast_shadow", False)
    if name in SELECTABLE:
        a.tags = [unreal.Name("Selectable"), unreal.Name("Name:" + SELECTABLE[name])]
    if name == "SM_TrainingDummy":                         # the king's sword knocks them about (AVLKing::HitDummies)
        a.tags = [unreal.Name("Dummy")]
        c.set_mobility(unreal.ComponentMobility.MOVABLE)
        c.set_editor_property("affect_distance_field_lighting", False)
    if name.startswith(("SM_GrassTuft", "SM_Flowers", "SM_Wheat")):
        try:                                               # the wind sway stops far from the camera, where it cannot be seen
            c.set_editor_property("world_position_offset_disable_distance", 6000)
        except Exception:
            pass
    if name.endswith("_Leaves"):           # (SM_Tree_* and the taller SM_Tree2_*)
        a.tags = [unreal.Name("Canopy")]                  # AVLKing stops drawing a crown that hides him from the camera
        c.set_mobility(unreal.ComponentMobility.STATIONARY)
        # crowns shade the ground from the sun but do not shut out the sky: under dense forest the bounce light would
        # otherwise be black. The reference's forest floor is bright and dappled.
        c.set_editor_property("affect_distance_field_lighting", False)
        c.set_editor_property("affect_dynamic_indirect_lighting", False)
    if meta(name).get("collision", "complex") == "none":
        c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    return a


def lamps(name, x, y, z, yaw, scale, folder):
    n = 0
    ca, sa = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    for (lx, ly, lz, vol) in meta(name).get("lights", []):
        if vol < 0.004:
            continue
        lx, ly, lz = lx * scale[0], ly * scale[1], lz * scale[2]
        wx, wy = x + lx * ca - ly * sa, y + lx * sa + ly * ca
        LAMP_POINTS.append((wx, wy, z + lz))
        a = spawn(unreal.PointLight, vec(wx, wy, z + lz), None, None, folder)
        lc = a.get_component_by_class(unreal.PointLightComponent)
        lc.set_mobility(unreal.ComponentMobility.STATIONARY)
        size = min(1.0, max(0.25, (vol / 0.12) ** 0.5))
        lc.set_editor_property("intensity_units", unreal.LightUnits.CANDELAS)
        lc.set_editor_property("intensity", P["lamp_lumens"] * size)
        lc.set_editor_property("attenuation_radius", P["lamp_radius"] * (0.6 + 0.4 * size))
        lc.set_editor_property("light_color", unreal.Color(int(P["lamp_color"][2] * 255), int(P["lamp_color"][1] * 255), int(P["lamp_color"][0] * 255), 255))
        lc.set_editor_property("source_radius", 12.0)
        lc.set_editor_property("cast_shadows", False)
        lc.set_editor_property("volumetric_scattering_intensity", 0.6)
        n += 1
    return n


def special_instance(name, tex, tint, emissive):
    mel = unreal.MaterialEditingLibrary
    path = "/Game/Voxel/Materials/" + name
    mi = eal.load_asset(path) if eal.does_asset_exist(path) else unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        name, "/Game/Voxel/Materials", unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(mi, eal.load_asset("/Game/Voxel/Materials/M_Voxel"))
    mel.set_material_instance_texture_parameter_value(mi, "Tex", eal.load_asset("/Game/Voxel/Textures/" + tex))
    mel.set_material_instance_vector_parameter_value(mi, "Tint", lin(tint))
    mel.set_material_instance_scalar_parameter_value(mi, "Emissive", emissive)
    mel.update_material_instance(mi)
    eal.save_loaded_asset(mi, False)
    return mi


def ambience(layout, lamp_points):
    """Chimney smoke and drifting motes (AVLAmbience). Chimney tops come from SourceArt/extras.json:
    {"SM_TownHall": {"smoke": [[x, y, z], ...]}} in the mesh's own space (metres, Blender axes)."""
    extras = {}
    ep = os.path.join(SRC, "extras.json")
    if os.path.exists(ep):
        extras = json.load(open(ep))
    smoke = []
    for it in layout["instances"]:
        for (lx, ly, lz) in extras.get(it["mesh"], {}).get("smoke", []):
            yaw = math.radians(it.get("yaw", 0.0))
            sc = it.get("scale", 1.0)
            x = it["pos"][0] + (lx * math.cos(yaw) - ly * math.sin(yaw)) * sc
            y = it["pos"][1] + (lx * math.sin(yaw) + ly * math.cos(yaw)) * sc
            smoke.append(vec(x, y, it["pos"][2] + lz * sc))
    motes = [vec(p[0], p[1], p[2] - 1.2) for p in lamp_points[::2]]
    for key in ("plaza", "glade"):
        px, py = layout["places"][key]
        motes.append(vec(px, py, 0.2))
    a = spawn(unreal.VLAmbience, unreal.Vector(0, 0, 0), None, "Ambience", "Ambience")
    a.set_editor_property("smoke_sources", smoke)
    a.set_editor_property("mote_centres", motes)
    a.set_editor_property("mote_material", special_instance("MI_Vox_mote", "T_Vox_glow", (1.0, 0.82, 0.40), 9.0))
    a.set_editor_property("smoke_material", special_instance("MI_Vox_smoke", "T_Vox_paint", (0.80, 0.78, 0.74), 0.0))
    return len(smoke), len(motes)


LAMP_POINTS = []


def walls(half):
    cube = eal.load_asset("/Engine/BasicShapes/Cube")
    for (x, y, sx, sy) in ((half, 0, 1, 2 * half + 2), (-half, 0, 1, 2 * half + 2), (0, half, 2 * half + 2, 1), (0, -half, 2 * half + 2, 1)):
        a = eas.spawn_actor_from_object(cube, vec(x, y, 10.0), unreal.Rotator(0, 0, 0))
        a.set_actor_scale3d(unreal.Vector(sx, sy, 40.0))
        a.set_folder_path("Bounds")
        a.set_actor_hidden_in_game(True)
        a.static_mesh_component.set_editor_property("cast_shadow", False)
        a.static_mesh_component.set_visibility(False)


def relight():
    """Only replace the light, sky, fog and post-process (while tuning the look): LIGHT_ONLY=True."""
    for a in eas.get_all_level_actors():
        if str(a.get_folder_path()) == "Light":
            eas.destroy_actor(a)
    lighting()
    les.save_current_level()
    print("relit:", {k: P[k] for k in sorted(LOOK)})


def main():
    if globals().get("LIGHT_ONLY"):
        relight()
        return
    with open(os.path.join(SRC, "layout.json")) as f:
        layout = json.load(f)
    load_or_new_level()
    lighting()
    postcard(layout)
    tiles = json.load(open(os.path.join(SRC, "Meshes", "terrain_tiles.json")))
    for t in tiles:
        place(t, 0, 0, 0, folder="Terrain")
    place("SM_Water", 0, 0, 0, folder="Terrain")
    placed, skipped, nlamps = 0, {}, 0
    with unreal.ScopedSlowTask(len(layout["instances"]), "Placing the village") as task:
        task.make_dialog(False)
        for it in layout["instances"]:
            task.enter_progress_frame(1)
            x, y, z = it["pos"]
            sc = it.get("scale3") or [it.get("scale", 1.0)] * 3
            folder = "Village/" + it.get("group", "village").capitalize()
            a = place(it["mesh"], x, y, z, it.get("yaw", 0.0), sc, folder)
            if a is None:
                skipped[it["mesh"]] = skipped.get(it["mesh"], 0) + 1
                continue
            placed += 1
            nlamps += lamps(it["mesh"], x, y, z, it.get("yaw", 0.0), sc, "Lamps")
    walls(layout["terrain"]["half"] - 1.0)
    nsmoke, nmotes = ambience(layout, LAMP_POINTS)
    les.save_current_level()
    print("level built: %d placed, %d lamps, %d chimneys, %d mote swarms, %d kinds missing: %s" % (
        placed, nlamps, nsmoke, nmotes, len(skipped), ", ".join(sorted(skipped))))


if not globals().get("NO_MAIN"):          # Tools/ue/build_flatlands.py borrows the functions above
    main()
