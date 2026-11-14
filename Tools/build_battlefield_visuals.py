"""Dresses /Game/Maps/L_Battlefield from the generated world: terraced terrain, rocks, conifers,
grass, the ruin, water, then lighting, fog and post-process. Deterministic and re-runnable:
everything it owns lives in the outliner folders Terrain / Props / Water / Lighting and is rebuilt.

Pipeline (see Docs/VISUAL_CONTRACT.md):
  Tools/.venv/bin/python Tools/textures/gen_world_textures.py     # pixel-art textures  -> SourceArt/Textures
  Tools/.venv/bin/python Tools/world/gen_battlefield.py           # meshes, splat map, layout -> SourceArt
  Tools/ue_py.py Tools/import_world_assets.py                     # into /Game/SR/Textures, /Game/SR/Meshes
  Tools/ue_py.py Tools/build_visual_materials.py                  # /Game/SR/Materials
  Tools/ue_py.py Tools/build_battlefield_visuals.py               # this file: the level
One part only:  Tools/ue_py.py -c "PARTS=['lighting']; exec(open('<abs path to this file>').read())"
Parts: world (terrain + props + water + buildings), buildings (only re-place the buildings), lighting.

Gameplay rules honoured (enforced by the generator): the +/-12000 cm play area keeps both kingdoms' aprons,
the spawn areas, the roads, the fords and the island flat; walkable terraces step <= 40 cm (the ridges, knolls and
tors are taller on purpose: they block); blocking rocks, trunks, the fir-wood belts and ruin pieces are single
convex boxes (tag SRBlocker); the river blocks by its bed being below -30 cm, its fords and bridges are ground;
foliage and dressing have no collision.
"""
import json
import os
import unreal

PARTS = globals().get("PARTS", ["world", "lighting"])
MAP = "/Game/Maps/L_Battlefield"
MAT = "/Game/SR/Materials/"
MESH = "/Game/SR/Meshes/"
ROOT = os.path.abspath(unreal.Paths.project_dir())

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
eal = unreal.EditorAssetLibrary
load = eal.load_asset
CUBE = load("/Engine/BasicShapes/Cube")

MATERIAL_FOR = [            # first matching mesh-name prefix wins
    ("SM_T_", "M_Terrain"), ("SM_Water", "M_Water"), ("SM_Conifer_", "M_Foliage"), ("SM_Tuft_", "M_Card"),
    ("SM_BannerCloth", "MI_Card_Banner"), ("SM_BannerPole", "MI_Prop_Wood"), ("SM_Fence_", "MI_Prop_Wood"),
    ("SM_Log", "MI_Prop_Log"), ("SM_Stump", "MI_Prop_Log"), ("SM_Ruin_", "MI_Prop_Sandstone"),
    ("SM_Rock_", "MI_Prop_Rock"), ("SM_Menhir_", "MI_Prop_Rock"), ("SM_GoldVein", "MI_Bld_Ore"),
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


def add_ism(owner, mesh, name, shadow=True, hism=False, cull=0.0, sway=False):
    """One instanced component. hism: hierarchical (per-cluster culling, for the big families). cull: fade instances out
    beyond this distance (cm, 0 = never). sway: the material moves vertices (wind): keep its shadow cached rigidly (no
    per-frame virtual shadow map invalidation, which flickers) and stop evaluating the sway far from the camera."""
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
def build_world():
    with open(os.path.join(ROOT, "SourceArt", "World", "layout.json")) as f:
        layout = json.load(f)
    assign_materials()
    for folder in ("Greybox", "Terrain", "Props", "Water", "Buildings"):
        clear_folder(folder)

    # terrain: WorldStatic, complex-as-simple collision set on the assets at import
    for t in layout["terrain"]:
        mesh_actor(load(MESH + t["mesh"]), t["pos"], 0.0, t["mesh"][5:], t["folder"], collide=True)
    w = layout["water"]
    # one sheet for the river, its channels and the far lake. No collision: the grid's ground trace must pass through it
    # to the bed (deep: below -30 cm = water, blocked; a ford's bed is at -24 cm = wet but walkable).
    mesh_actor(load(MESH + w["mesh"]), w["pos"], 0.0, "River", "Water", collide=False, shadow=False)

    # single actors: rocks over their collision boxes, the ruin, fences, logs
    for a in layout["actors"]:
        mesh_actor(load(MESH + a["mesh"]), a["pos"], a["yaw"], a["label"], a["folder"], collide=False, shadow=a["mesh"] != "SM_BannerCloth")
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
    families = {"Conifers": ("SM_Conifer_", True, 0.0, True), "Grass": ("SM_Tuft_", False, 13000.0, True),
                "Stones": ("SM_Rock_", True, 18000.0, False), "Deadwood": ("SM_Log", True, 18000.0, False)}
    total = 0
    for label, (prefix, shadow, cull, sway) in families.items():
        owner = eas.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, 0))
        owner.set_actor_label(label)
        owner.set_folder_path("Props/Foliage" if label in ("Conifers", "Grass") else "Props/Rocks")
        for mesh_name, items in sorted(layout["instances"].items()):
            if not mesh_name.startswith(prefix):
                continue
            comp = add_ism(owner, load(MESH + mesh_name), mesh_name[3:], shadow, hism=True, cull=cull, sway=sway)
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
LOOK = dict(
    sun_pitch=-42.0, sun_yaw=75.0,              # light travels toward screen right and a little up-screen
    sun_lux=10.5, sun_color=(255, 214, 165), sun_source_angle=1.8, sun_shafts=11.0,
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
           vignette_intensity=0.5,
           # grade: warm highlights, teal-cool shadows, blacks a touch lifted, saturation held back, gentle contrast
           color_saturation=V4(0.9, 0.9, 0.9, 1.0),
           color_contrast=V4(1.0, 1.0, 1.0, 1.0),
           color_gain_shadows=V4(0.88, 1.0, 1.12, 1.0),
           color_gain_highlights=V4(1.08, 1.0, 0.88, 1.0),
           color_offset_shadows=V4(0.0, 0.004, 0.008, 0.0),
           color_saturation_shadows=V4(0.9, 0.9, 0.9, 1.0),
           film_toe=0.4, film_slope=0.84, film_shoulder=0.3,
           color_offset=V4(0.006, 0.008, 0.012, 0.0),
           film_grain_intensity=0.12,
           scene_fringe_intensity=0.35,
           motion_blur_amount=0.0)
    print("lighting done")


# ------------------------------------------------------------------ run
if "world" in PARTS:
    build_world()
elif "buildings" in PARTS:
    with open(os.path.join(ROOT, "SourceArt", "World", "layout.json")) as f:
        build_buildings(json.load(f))
if "lighting" in PARTS:
    build_lighting()
les.save_current_level()
print("saved", MAP)
