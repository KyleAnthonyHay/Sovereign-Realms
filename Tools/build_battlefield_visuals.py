"""Dresses a battle map's level from the generated world: the land, rocks, conifers, grass, the ruins and
landmarks, water, then lighting, fog and post-process. Deterministic and re-runnable: everything it owns lives in
the outliner folders Terrain / Props / Water / Buildings / Lighting / Atmosphere / Map and is rebuilt.

  MAP = "two"  (default)  /Game/Maps/L_Battlefield    from SourceArt/World/layout.json,  meshes /Game/SR/Meshes
  MAP = "four"            /Game/Maps/L_Battlefield4   from SourceArt/World/layout4.json, meshes /Game/SR/Meshes4
  Tools/ue_py.py -c "MAP='four'; exec(open('<abs path to this file>').read())"
The level is opened (made, if it does not exist yet) before it is dressed, and saved after. Each level carries one
ASRMapInfo (folder Map) with the map's own numbers from the layout's "map": the game reads its bounds, starts,
camera height and minimap from it (Source/SovereignRealms/Battle/SRMapInfo.h).

Pipeline (see Docs/VISUAL_CONTRACT.md):
  Tools/.venv/bin/python Tools/textures/gen_world_textures.py     # pixel-art textures  -> SourceArt/Textures
  Tools/.venv/bin/python Tools/world/gen_battlefield.py           # meshes, splat map, layout -> SourceArt
  Tools/ue_py.py Tools/import_world_assets.py                     # into /Game/SR/Textures, /Game/SR/Meshes (Meshes4)
  Tools/ue_py.py Tools/build_visual_materials.py                  # /Game/SR/Materials
  Tools/ue_py.py Tools/build_battlefield_visuals.py               # this file: the level
One part only:  Tools/ue_py.py -c "PARTS=['lighting']; exec(open('<abs path to this file>').read())"
Parts: materials (only put the materials back on the generated meshes: needed after every mesh re-import, which resets
them to the default grey), world (terrain + props + water + buildings), buildings (only re-place the buildings), lighting, atmosphere
(river, valley and ground mist, the falls' spray, the haze over the meres, cloud shadows: the outliner folder
Atmosphere; the birds are ASRBirds, spawned at run time).

Gameplay rules honoured (enforced by the generator, Tools/world/gen_battlefield.py): the land is one smooth surface;
ground troops walk is no steeper than about 1 in 5, a barrier is a mountainside; the kingdoms' tables, the benches
and the pads under veins and ruins are level; blocking rocks, trunks and ruin pieces are single convex boxes (tag
SRBlocker); water sheets carry the tag SRWater (the grid measures the depth under them: deeper than 14 cm is a
wall, a ford's bed lies 8 cm under); relics carry SRRelic and old towers SRRuinTower; foliage and dressing have no
collision.
"""
import json
import os
import unreal

PARTS = globals().get("PARTS", ["world", "lighting", "atmosphere"])
MAP_ID = globals().get("MAP", "two")
SFX = {"two": "", "four": "4"}[MAP_ID]
MAP = "/Game/Maps/L_Battlefield" + SFX
MAT = "/Game/SR/Materials/"
MESH = "/Game/SR/Meshes%s/" % SFX
TEXTURES = "/Game/SR/Textures/"
ROOT = os.path.abspath(unreal.Paths.project_dir())
LAYOUT = os.path.join(ROOT, "SourceArt", "World", "layout%s.json" % SFX)

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
eal = unreal.EditorAssetLibrary
load = eal.load_asset
CUBE = load("/Engine/BasicShapes/Cube")

MATERIAL_FOR = [            # first matching mesh-name prefix wins. (The second map has its own terrain and water instances:
    # its splat map and water map, and the world squares they cover.)
    ("SM_T_", "MI_Terrain4" if SFX else "M_Terrain"), ("SM_Waterfall", "M_Waterfall"), ("SM_Water", "MI_Water4" if SFX else "M_Water"),
    ("SM_Conifer_", "M_Foliage"), ("SM_Tuft_", "M_Card"),
    # the woods: broadleaves and shrubs (the firs' material with a leafy clump), the forest floor's cards, mossed timber
    ("SM_Tree_Birch", "MI_Foliage_Birch"), ("SM_Tree_Maple", "MI_Foliage_Maple"), ("SM_Tree_", "MI_Foliage_Oak"), ("SM_Bush_", "MI_Foliage_Oak"),
    ("SM_Under_", "MI_Card_Under"), ("SM_Log_", "MI_Prop_LogMossy"),
    ("SM_Bones_", "MI_Prop_Bone"), ("SM_Relic_", "MI_Prop_Rock"), ("SM_Barrow_", "MI_Prop_Rock"), ("SM_Aqueduct", "MI_Prop_Sandstone"),
    ("SM_Spear", "MI_Prop_Wood"), ("SM_Shield", "MI_Prop_Wood"), ("SM_Cart_", "MI_Prop_Wood"), ("SM_Jetty", "MI_Prop_Wood"),
    ("SM_BannerCloth", "MI_Card_Banner"), ("SM_BannerPole", "MI_Prop_Wood"), ("SM_Fence_", "MI_Prop_Wood"),
    ("SM_Log", "MI_Prop_Log"), ("SM_Stump", "MI_Prop_Log"), ("SM_Ruin_", "MI_Prop_Sandstone"),
    # boulders, scree and standing stones are the mountains' own rock (M_Rock: photographic, world-aligned, lichened)
    ("SM_Rock_", "M_Rock"), ("SM_Menhir_", "MI_Rock_Ruin"), ("SM_GoldVein", "MI_Bld_Ore"),
    ("SM_WatchPost", "MI_Prop_Wood"), ("SM_Dolmen", "MI_Rock_Ruin"), ("SM_Cairn", "M_Rock"),
]


def clear_folder(prefix):
    for a in eas.get_all_level_actors():
        if str(a.get_folder_path()).startswith(prefix):
            eas.destroy_actor(a)


def assign_materials():
    """Puts the right material on every generated mesh asset (slot 0), so actors need no overrides."""
    cache = {}
    n = 0
    for path in eal.list_assets(MESH[:-1], False):
        name = path.split("/")[-1].split(".")[0]
        for prefix, mat in MATERIAL_FOR:
            if name.startswith(prefix):
                sm = load(path)
                m = cache.setdefault(mat, load(MAT + mat))
                if sm.get_material(0) != m:
                    sm.set_material(0, m)
                    eal.save_loaded_asset(sm, False)
                    n += 1
                break
        else:
            print("no material rule for", name)
    print("materials assigned:", n)


def mesh_actor(mesh, loc, yaw, label, folder, collide, shadow=True, scale=1.0):
    if mesh is None:
        print("missing mesh for", label, "(run Tools/import_world_assets.py for this map)")
        return None
    a = eas.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(*loc), unreal.Rotator(0, 0, yaw))
    a.set_actor_label(label)
    a.set_folder_path(folder)
    c = a.static_mesh_component
    c.set_static_mesh(mesh)
    if scale != 1.0:
        a.set_actor_scale3d(unreal.Vector(scale, scale, scale))
    if not collide:
        c.set_collision_profile_name("NoCollision")     # contract: dressing must not be WorldStatic
    c.set_editor_property("cast_shadow", shadow)
    return a


def add_ism(owner, mesh, name, shadow=True, hism=False, cull=0.0, sway=False, lit_scene=True):
    """One instanced component. hism: hierarchical (per-cluster culling, for the big families). cull: fade instances out
    beyond this distance (cm, 0 = never). sway: the material moves vertices (wind): keep its shadow cached rigidly (no
    per-frame virtual shadow map invalidation, which flickers) and stop evaluating the sway far from the camera.
    lit_scene=False: keep the instances out of Lumen's scene and the distance fields (the grass: 160 thousand cards
    that cast no shadow and occlude nothing worth tracing)."""
    root = sds.k2_gather_subobject_data_for_instance(owner)[0]
    p = unreal.AddNewSubobjectParams()
    p.set_editor_property("parent_handle", root)
    cls = unreal.HierarchicalInstancedStaticMeshComponent if hism else unreal.InstancedStaticMeshComponent
    p.set_editor_property("new_class", cls)
    handle, _ = sds.add_new_subobject(p)
    sds.rename_subobject(handle, unreal.Text(name))
    comp = [c for c in owner.get_components_by_class(cls) if c.get_instance_count() == 0 and c.static_mesh is None][0]
    if cull > 0.0:
        comp.set_editor_property("instance_start_cull_distance", int(cull * 0.8))
        comp.set_editor_property("instance_end_cull_distance", int(cull))
    if sway:
        comp.set_editor_property("shadow_cache_invalidation_behavior", unreal.ShadowCacheInvalidationBehavior.RIGID)
        comp.set_editor_property("world_position_offset_disable_distance", 9000)
    if not lit_scene:
        comp.set_editor_property("affect_distance_field_lighting", False)
        comp.set_editor_property("affect_dynamic_indirect_lighting", False)
    comp.set_static_mesh(mesh)
    comp.set_collision_profile_name("NoCollision")
    comp.set_editor_property("cast_shadow", shadow)
    comp.set_editor_property("mobility", unreal.ComponentMobility.STATIC)
    return comp


# ------------------------------------------------------------------ buildings
TEAM_COLORS = {0: (0.05, 0.22, 0.80), 1: (0.72, 0.07, 0.05)}      # the Sovereign Feel defaults; ASRBuilding re-applies the live ones
BLD = "/Game/SR/Buildings/"


def build_buildings(layout):
    """Places the kingdoms' buildings (layout.json "buildings", from BUILDINGS in gen_battlefield.py) in the folder
    Buildings. With the game module's ASRBuilding class available each is one actor that knows its type, team,
    footprint and sockets and builds its own blocking boxes; otherwise a static mesh plus invisible blocker boxes."""
    clear_folder("Buildings")
    cls = None
    try:
        cls = unreal.load_class(None, "/Script/SovereignRealms.SRBuilding")
    except Exception:
        cls = None
    for b in layout.get("buildings", []):
        mesh = load(BLD + b["mesh"])
        if mesh is None:
            print("missing building mesh", b["mesh"], "(run Tools/import_buildings.py)")
            continue
        loc, rot = unreal.Vector(*b["pos"]), unreal.Rotator(0, 0, b["yaw"])
        team = TEAM_COLORS[b["team"]]
        if cls is not None:
            a = eas.spawn_actor_from_class(cls, loc, rot)
            a.set_actor_label(b["label"])
            a.set_folder_path("Buildings")
            a.set_editor_property("building_type", getattr(unreal.SRBuildingType, b["type"].upper()))
            a.set_editor_property("team", unreal.SRTeam.PLAYER if b["team"] == 0 else unreal.SRTeam.ENEMY)
            a.set_editor_property("building_mesh", mesh)
            fp = b["footprint"]
            a.set_editor_property("footprint_min", unreal.Vector2D(fp[0], fp[1]))
            a.set_editor_property("footprint_max", unreal.Vector2D(fp[2], fp[3]))
            a.set_editor_property("block_height", b["colliders"][0]["size"][2])
            a.set_editor_property("ring_radius", b["ring_radius"])
            sk = b["sockets"]
            for prop, key in (("gate_offset", "gate"), ("rally_offset", "rally"), ("label_offset", "label"), ("popup_offset", "popup")):
                if key in sk:
                    a.set_editor_property(prop, unreal.Vector(*sk[key]))
            a.call_method("RefreshBuilding")
            continue
        a = mesh_actor(mesh, b["pos"], b["yaw"], b["label"], "Buildings", collide=False)
        a.static_mesh_component.set_default_custom_primitive_data_vector4(0, unreal.Vector4(team[0], team[1], team[2], 1.0))
        for i, c in enumerate(b["colliders"]):
            box = eas.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
            box.set_actor_label("%s_Collision%s" % (b["label"], "" if i == 0 else "_%d" % i))
            box.set_folder_path("Buildings")
            box.static_mesh_component.set_static_mesh(CUBE)
            box.attach_to_actor(a, "", unreal.AttachmentRule.KEEP_RELATIVE, unreal.AttachmentRule.KEEP_RELATIVE, unreal.AttachmentRule.KEEP_WORLD, False)
            box.set_actor_relative_location(unreal.Vector(*c["centre"]), False, False)
            box.set_actor_relative_rotation(unreal.Rotator(0, 0, c["yaw"]), False, False)
            box.set_actor_scale3d(unreal.Vector(c["size"][0] / 100.0, c["size"][1] / 100.0, c["size"][2] / 100.0))
            box.static_mesh_component.set_editor_property("visible", False)
            box.static_mesh_component.set_editor_property("cast_shadow", False)
            box.tags = ["SRBlocker"]
    print("buildings placed:", len(layout.get("buildings", [])), "as", "ASRBuilding" if cls is not None else "static meshes")


# ------------------------------------------------------------------ world
def build_map_info(layout):
    """The level's ASRMapInfo: the map's own numbers (the game copies them over the global settings when the map
    starts: ASRMapInfo::ApplyToSettings)."""
    clear_folder("Map")
    m = layout["map"]
    cls = unreal.load_class(None, "/Script/SovereignRealms.SRMapInfo")
    a = eas.spawn_actor_from_class(cls, unreal.Vector(0, 0, 0))
    a.set_actor_label("MapInfo")
    a.set_folder_path("Map")
    a.set_editor_property("map_id", m["id"])
    a.set_editor_property("display_name", m["name"])
    a.set_editor_property("half_extent", unreal.Vector2D(m["half_extent"], m["half_extent"]))
    a.set_editor_property("player_start", unreal.Vector2D(*m["starts"]["player"]))
    a.set_editor_property("enemy_start", unreal.Vector2D(*m["starts"]["enemy"]))
    a.set_editor_property("focus_height_max", m["focus_height_max"])
    a.set_editor_property("ground_trace_top", m["trace_top"])
    a.set_editor_property("ground_trace_bottom", m["trace_bottom"])
    a.set_editor_property("minimap_base", load(TEXTURES + m["minimap"]))
    print("map info: %s, +/-%.0f cm, camera rides the ground up to %.0f, traces from %.0f" % (m["id"], m["half_extent"], m["focus_height_max"], m["trace_top"]))


def build_world():
    with open(LAYOUT) as f:
        layout = json.load(f)
    assign_materials()
    for folder in ("Greybox", "Terrain", "Props", "Water", "Buildings", "Atmosphere/Birds"):   # (Atmosphere/Birds: clears the old static flocks)
        clear_folder(folder)
    build_map_info(layout)

    # terrain: WorldStatic, complex-as-simple collision set on the assets at import
    for t in layout["terrain"]:
        mesh_actor(load(MESH + t["mesh"]), t["pos"], 0.0, t["mesh"][5:], t["folder"], collide=True)
    w = layout["water"]
    # One sheet for the rivers and the lakes they run into, one for each tarn and mere at its own height. No collision
    # in the level: every ground trace must pass through water to its bed. The tag SRWater is how the walkability grid
    # finds them: it traces each sheet by itself and calls the water under it deep (a wall) past 14 cm, a ford under.
    for i, e in enumerate([w] + w.get("extra", [])):
        a = mesh_actor(load(MESH + e["mesh"]), e["pos"], 0.0, "River" if i == 0 else "%s_%d" % (e.get("name", "water").title(), i), "Water", collide=False, shadow=False)
        if a is not None:
            a.tags = ["SRWater"]
    for i, e in enumerate(w.get("falls", [])):                  # the falls off the tarns' rims
        mesh_actor(load(MESH + e["mesh"]), e["pos"], 0.0, "Waterfall_%d" % i, "Water", collide=False, shadow=False)

    # single actors: rocks over their collision boxes, the ruins and landmarks, fences, logs. "tags": SRRelic (a relic:
    # a Relic Tower can be raised on it) and SRRuinTower (an old tower: a Watchtower), read by USRGridSubsystem::Build.
    for a in layout["actors"]:
        actor = mesh_actor(load(MESH + a["mesh"]), a["pos"], a["yaw"], a["label"], a["folder"], collide=False, shadow=a["mesh"] != "SM_BannerCloth", scale=a.get("scale", 1.0))
        if actor is not None and a.get("tags"):
            actor.tags = a["tags"]
    # blockers: one hidden, colliding cube instance per obstacle (rock, trunk, ruin piece), all in one actor so a large
    # map does not need thousands of actors. WorldStatic + BlockAll: the units' wall traces see them.
    owner = eas.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, 0))
    owner.set_actor_label("Blockers")
    owner.set_folder_path("Props/Blockers")
    owner.tags = ["SRBlocker"]
    comp = add_ism(owner, CUBE, "BlockerBoxes", False)
    comp.set_collision_profile_name("BlockAll")
    comp.set_editor_property("visible", False)
    comp.set_editor_property("hidden_in_game", True)
    xfs = [unreal.Transform(unreal.Vector(*b["pos"]), unreal.Rotator(0, 0, b["yaw"]), unreal.Vector(b["size"][0] / 100.0, b["size"][1] / 100.0, b["size"][2] / 100.0))
           for b in layout["blockers"]]
    comp.add_instances(xfs, False, True)

    # instanced dressing, one actor per family
    # name: (mesh prefix, casts shadow, cull distance cm, sways). The camera tops out about 7800 cm from its focus; grass and
    # pebbles past ~2/3 of the far view are lost in haze and blur, trees stay to the horizon.
    families = {"Conifers": ("SM_Conifer_", True, 0.0, True), "Broadleaves": ("SM_Tree_", True, 0.0, True), "Shrubs": ("SM_Bush_", True, 20000.0, True),
                "Grass": ("SM_Tuft_", False, 13000.0, True), "Undergrowth": ("SM_Under_", False, 13000.0, True),
                "Stones": ("SM_Rock_", True, 18000.0, False), "Deadwood": ("SM_Log", True, 18000.0, False)}
    total = 0
    for label, (prefix, shadow, cull, sway) in families.items():
        owner = eas.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, 0))
        owner.set_actor_label(label)
        owner.set_folder_path("Props/Foliage" if label in ("Conifers", "Broadleaves", "Shrubs", "Grass", "Undergrowth") else "Props/Rocks")
        if label in ("Conifers", "Broadleaves"):
            owner.tags = ["SRTrees"]                            # ASRLeaves reads the trees it sheds leaves from off these
        for mesh_name, items in sorted(layout["instances"].items()):
            if not mesh_name.startswith(prefix):
                continue
            comp = add_ism(owner, load(MESH + mesh_name), mesh_name[3:], shadow, hism=True, cull=cull, sway=sway, lit_scene=label not in ("Grass", "Undergrowth"))
            xfs = [unreal.Transform(unreal.Vector(x, y, z), unreal.Rotator(0, 0, yaw), unreal.Vector(s, s, s)) for x, y, z, yaw, s in items]
            comp.add_instances(xfs, False, True)
            total += len(xfs)
    build_buildings(layout)
    print("terrain actors %d, single actors %d, blockers %d, instances %d" % (len(layout["terrain"]), len(layout["actors"]), len(layout["blockers"]), total))


# ------------------------------------------------------------------ lighting
def find_or_spawn(cls, label, folder="Lighting", loc=unreal.Vector(0, 0, 1000)):
    for a in eas.get_all_level_actors():
        if a.get_actor_label() == label and isinstance(a, cls):
            a.set_folder_path(folder)
            return a
    a = eas.spawn_actor_from_class(cls, loc)
    a.set_actor_label(label)
    a.set_folder_path(folder)
    return a


def set_pp(volume, **values):
    """Sets post-process fields and ticks their override flags."""
    s = volume.settings
    for k, v in values.items():
        s.set_editor_property("override_" + k, True)
        s.set_editor_property(k, v)
    volume.settings = s


# Every look value in one place, so a retune is one edit and one `PARTS=['lighting']` run.
# Sun height: 42 degrees above the horizon (it was 33). At 33 a shadow was 1.5x as long as its caster and trees, ridges
# and castles laid near-black bars across the lanes; at 42 it is 1.1x. The sky fill is up by a quarter so that shadowed
# ground sits near 35-40% of lit ground and blue troops stay readable in it; the sun is a touch lower in lux and the
# exposure bias a touch lower because the higher sun puts more light on flat ground (sin 42 / sin 33 = 1.23). The warm
# sun colour, the haze and the grade are unchanged: still late afternoon, just not the last ten minutes of it.
# Natural-world pass: the ground now carries real colour variation, so the grade lets it through (saturation 0.9 ->
# 0.98, contrast 1.0 -> 1.05), the sun is a shade more golden and the vignette lighter.
LOOK = dict(
    sun_pitch=-42.0, sun_yaw=75.0,              # light travels toward screen right and a little up-screen
    sun_lux=11.0, sun_color=(255, 209, 154), sun_source_angle=1.8, sun_shafts=11.0,
    sky_intensity=9.5, sky_color=(208, 226, 255), sky_fog=0.3,
    fog_density=0.2, fog_falloff=0.3, fog_albedo=(255, 242, 224), fog_phase=0.35, fog_extinction=0.55,
    exposure_bias=-0.7,
)


def build_lighting():
    V4 = unreal.Vector4
    L = LOOK
    # Sun: warm, from screen left, raking across the field toward screen right and slightly up-screen.
    # Terrace faces that turn toward it light up, the rest sit in cool sky fill; shadows about as long as their casters.
    sun = find_or_spawn(unreal.DirectionalLight, "Sun")
    sun.set_actor_rotation(unreal.Rotator(0, L["sun_pitch"], L["sun_yaw"]), False)      # roll, pitch, yaw
    lc = sun.light_component
    lc.set_mobility(unreal.ComponentMobility.MOVABLE)
    lc.set_editor_property("intensity", L["sun_lux"])
    lc.set_editor_property("light_color", unreal.Color(r=L["sun_color"][0], g=L["sun_color"][1], b=L["sun_color"][2], a=255))
    lc.set_editor_property("light_source_angle", L["sun_source_angle"])    # wider than the real sun: softer, miniature-scale penumbrae
    lc.set_editor_property("atmosphere_sun_light", True)
    lc.set_editor_property("volumetric_scattering_intensity", L["sun_shafts"])   # how hard the sun lights the haze: the light shafts
    lc.set_editor_property("cast_shadows", True)

    sky = find_or_spawn(unreal.SkyLight, "SkyLight")
    sc = sky.light_component
    sc.set_mobility(unreal.ComponentMobility.MOVABLE)
    sc.set_editor_property("real_time_capture", True)
    sc.set_editor_property("intensity", L["sky_intensity"])
    sc.set_editor_property("light_color", unreal.Color(r=L["sky_color"][0], g=L["sky_color"][1], b=L["sky_color"][2], a=255))   # cool fill
    sc.set_editor_property("volumetric_scattering_intensity", L["sky_fog"])

    find_or_spawn(unreal.SkyAtmosphere, "SkyAtmosphere", loc=unreal.Vector(0, 0, 0))

    # Haze. Volumetric, so the sun's shadows cut shafts through it. The game camera moves its start distance to
    # just past the focus point every frame (Sovereign Feel > Visuals > Haze), which is why it can be this thick
    # without ever sitting on the troops.
    fog = find_or_spawn(unreal.ExponentialHeightFog, "HeightFog", loc=unreal.Vector(0, 0, 0))
    fog.set_actor_location(unreal.Vector(0, 0, 0), False, False)
    fc = fog.component
    fc.set_editor_property("fog_density", L["fog_density"])
    fc.set_editor_property("fog_height_falloff", L["fog_falloff"])
    fc.set_editor_property("fog_inscattering_luminance", unreal.LinearColor(0.0, 0.0, 0.0))
    fc.set_editor_property("directional_inscattering_luminance", unreal.LinearColor(0.0, 0.0, 0.0))
    fc.set_editor_property("start_distance", 1600.0)                       # editor preview; the game camera overrides these three
    fc.set_editor_property("volumetric_fog_start_distance", 1600.0)
    fc.set_editor_property("volumetric_fog_near_fade_in_distance", 1100.0)
    fc.set_editor_property("enable_volumetric_fog", True)
    fc.set_editor_property("volumetric_fog_scattering_distribution", L["fog_phase"])
    fc.set_editor_property("volumetric_fog_albedo", unreal.Color(r=L["fog_albedo"][0], g=L["fog_albedo"][1], b=L["fog_albedo"][2], a=255))
    fc.set_editor_property("volumetric_fog_extinction_scale", L["fog_extinction"])
    fc.set_editor_property("volumetric_fog_distance", 16000.0)

    pp = find_or_spawn(unreal.PostProcessVolume, "PostProcess", loc=unreal.Vector(0, 0, 0))
    pp.set_editor_property("unbound", True)
    pp.set_editor_property("priority", 0.0)
    dirt = load("/Game/SR/Textures/T_LensDirt")
    set_pp(pp,
           # exposure: fixed, never adapts (auto exposure is also off project-wide)
           auto_exposure_method=unreal.AutoExposureMethod.AEM_MANUAL,
           auto_exposure_apply_physical_camera_exposure=False,
           auto_exposure_bias=L["exposure_bias"],
           # bloom: wide and soft, so the lit haze and the highlights glow; a little dirt on the lens
           bloom_method=unreal.BloomMethod.BM_SOG,
           bloom_intensity=1.3, bloom_threshold=-1.0, bloom_size_scale=6.0,
           bloom_dirt_mask=dirt, bloom_dirt_mask_intensity=6.0, bloom_dirt_mask_tint=unreal.LinearColor(1.0, 0.9, 0.75),
           lens_flare_intensity=0.25, lens_flare_bokeh_size=4.0, lens_flare_threshold=6.0,
           vignette_intensity=0.42,
           # grade: warm highlights, teal-cool shadows, blacks a touch lifted, saturation held back, gentle contrast
           color_saturation=V4(0.98, 0.98, 0.98, 1.0),
           color_contrast=V4(1.05, 1.05, 1.05, 1.0),
           color_gain_shadows=V4(0.88, 1.0, 1.12, 1.0),
           color_gain_highlights=V4(1.1, 1.01, 0.87, 1.0),
           color_offset_shadows=V4(0.0, 0.004, 0.008, 0.0),
           color_saturation_shadows=V4(0.9, 0.9, 0.9, 1.0),
           film_toe=0.4, film_slope=0.84, film_shoulder=0.3,
           color_offset=V4(0.006, 0.008, 0.012, 0.0),
           film_grain_intensity=0.12,
           scene_fringe_intensity=0.35,
           motion_blur_amount=0.0)
    print("lighting done")


# ------------------------------------------------------------------ atmosphere
PLANE = load("/Engine/BasicShapes/Plane")


def local_fog(label, loc, radius, radial, height, falloff, albedo):
    """A Local Fog Volume (analytic, cheap, lit by the sun and the sky): a ball of haze `radius` cm across its middle,
    thickest low down. A volume is a 5 m sphere at scale 1."""
    cls = getattr(unreal, "LocalFogVolume", None)
    if cls is None:
        return None
    a = eas.spawn_actor_from_class(cls, unreal.Vector(*loc))
    a.set_actor_label(label)
    a.set_folder_path("Atmosphere/Mist/Haze")
    a.set_actor_scale3d(unreal.Vector(radius / 500.0, radius / 500.0, radius / 500.0 * 0.45))
    c = a.get_component_by_class(unreal.LocalFogVolumeComponent)
    for k, v in (("radial_fog_extinction", radial), ("height_fog_extinction", height), ("height_fog_falloff", falloff), ("height_fog_offset", -0.3),
                 ("fog_phase_g", 0.35), ("fog_albedo", unreal.LinearColor(*albedo)), ("fog_emissive", unreal.LinearColor(0.0, 0.0, 0.0))):
        try:
            c.set_editor_property(k, v)
        except Exception as ex:
            print("local fog:", k, ex)
    return a


def build_atmosphere():
    """Mist and the sun's cloud shadows (folder Atmosphere/Mist; the birds are ASRBirds, spawned at run time).
    River mist is the water mesh again, a hand above the surface, in M_Mist (it thins out at the banks by T_WaterMap).
    Valley mist is a level sheet per entry of layout "atmosphere" > "mist" [x, y, z, radius, height] in MI_Mist_Valley.
    Ground mist is the land's chunks again in MI_Mist_Ground (Atmosphere/Mist/Ground); spray sheets and a Local Fog
    Volume stand at each fall's foot (layout "water" > "falls" > "foot"), a Local Fog Volume over each mere."""
    clear_folder("Atmosphere/Mist")
    with open(LAYOUT) as f:
        layout = json.load(f)
    mist, valley = load(MAT + ("MI_Mist4" if SFX else "M_Mist")), load(MAT + "MI_Mist_Valley")
    n = 0
    if mist is not None:
        w = layout["water"]
        for k, lift in enumerate((52.0, 96.0)):                 # two thin layers read as depth when the camera tilts
            a = mesh_actor(load(MESH + w["mesh"]), (w["pos"][0], w["pos"][1], w["pos"][2] + lift), 0.0, "RiverMist_%d" % k, "Atmosphere/Mist", collide=False, shadow=False)
            a.static_mesh_component.set_material(0, mist)
            a.static_mesh_component.set_editor_property("translucency_sort_priority", k)
            n += 1
        for i, (x, y, z, radius, height) in enumerate(layout.get("atmosphere", {}).get("mist", [])):
            a = mesh_actor(PLANE, (x, y, z + height), float(i * 37 % 360), "ValleyMist_%02d" % i, "Atmosphere/Mist", collide=False, shadow=False)
            a.set_actor_scale3d(unreal.Vector(radius * 2.0 / 100.0, radius * 2.0 / 100.0, 1.0))
            a.static_mesh_component.set_material(0, valley)
            n += 1
        # ground mist: the land's own meshes again in MI_Mist_Ground, which lifts them a hand and shows them only
        # where mist pools (the hollows, the water's margins: T_WaterMap.a), so it lies in the dips and follows the slopes
        ground = load(MAT + "MI_Mist_Ground" + SFX)
        for t in (layout["terrain"] if ground is not None else []):
            if t["folder"] != "Terrain/Land" or not t.get("mist", True):      # (only the chunks with somewhere for it to lie)
                continue
            a = mesh_actor(load(MESH + t["mesh"]), t["pos"], 0.0, "GroundMist_" + t["mesh"][10:], "Atmosphere/Mist/Ground", collide=False, shadow=False)
            c = a.static_mesh_component
            c.set_material(0, ground)
            c.set_editor_property("affect_distance_field_lighting", False)
            c.set_editor_property("affect_dynamic_indirect_lighting", False)
            c.set_editor_property("visible_in_ray_tracing", False)
            c.set_editor_property("translucency_sort_priority", -1)
            n += 1
        # the falls: spray standing at the foot (three sheets of fast, fine mist) in a soft ball of lit haze
        spray = load(MAT + "MI_Mist_Spray")
        for i, f in enumerate(w.get("falls", [])):
            fx, fy, fz = f["foot"]
            width = f.get("width", 240.0)
            for k, (lift, rad) in enumerate(((35.0, 2.6), (120.0, 2.0), (230.0, 1.4))):
                a = mesh_actor(PLANE, (fx, fy, fz + lift), float(k * 47), "FallSpray_%d_%d" % (i, k), "Atmosphere/Mist/Falls", collide=False, shadow=False)
                a.set_actor_scale3d(unreal.Vector(width * rad * 2.0 / 100.0, width * rad * 2.0 / 100.0, 1.0))
                a.static_mesh_component.set_material(0, spray)
                a.static_mesh_component.set_editor_property("translucency_sort_priority", 2 + k)
                n += 1
            local_fog("FallHaze_%d" % i, (fx, fy, fz + 150.0), width * 3.4, radial=0.06, height=0.22, falloff=600.0, albedo=(0.86, 0.9, 0.93))
        # the meres in their hollows: a real depth of haze over each
        for i, e in enumerate(w.get("extra", [])):
            if e.get("name") == "mere":
                local_fog("MereHaze_%d" % i, (e["pos"][0], e["pos"][1], e["surface"] + 120.0), 2100.0, radial=0.02, height=0.14, falloff=420.0, albedo=(0.8, 0.86, 0.9))
    else:
        print("no M_Mist (run Tools/build_visual_materials.py)")
    sun = find_or_spawn(unreal.DirectionalLight, "Sun")
    cloud = load(MAT + "M_CloudShadow")
    if cloud is not None:
        sun.light_component.set_editor_property("light_function_material", cloud)
        sun.light_component.set_editor_property("light_function_fade_distance", 200000.0)
    else:
        print("no M_CloudShadow (run Tools/build_visual_materials.py)")
    print("atmosphere: %d mist sheets, cloud shadows %s" % (n, "on" if cloud is not None else "off"))


# ------------------------------------------------------------------ run
# open the map's level (make it the first time)
if not eal.does_asset_exist(MAP):
    if not les.new_level(MAP):
        raise RuntimeError("could not create " + MAP)
    print("created", MAP)
else:
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if world is None or world.get_path_name().split(".")[0] != MAP:
        les.load_level(MAP)
if "materials" in PARTS:          # after a mesh re-import alone (it resets the meshes' material slots): put the materials back
    assign_materials()
if "world" in PARTS:
    build_world()
elif "buildings" in PARTS:
    with open(LAYOUT) as f:
        build_buildings(json.load(f))
elif "mapinfo" in PARTS:
    with open(LAYOUT) as f:
        build_map_info(json.load(f))
if "lighting" in PARTS:
    build_lighting()
if "atmosphere" in PARTS:
    build_atmosphere()
les.save_current_level()
print("saved", MAP)
