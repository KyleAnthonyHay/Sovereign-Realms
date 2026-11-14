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
Parts: world (terrain + props + water), lighting.

Gameplay rules honoured (enforced by the generator): the +/-3000 cm play area keeps both spawn
areas and the lane flat; terraces inside it step <= 40 cm; blocking rocks and ruin pieces are single
convex boxes (tag SRBlocker); foliage and dressing have no collision.
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
    ("SM_Rock_", "MI_Prop_Rock"), ("SM_Menhir_", "MI_Prop_Rock"),
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


def add_ism(owner, mesh, name, shadow=True):
    root = sds.k2_gather_subobject_data_for_instance(owner)[0]
    p = unreal.AddNewSubobjectParams()
    p.set_editor_property("parent_handle", root)
    p.set_editor_property("new_class", unreal.InstancedStaticMeshComponent)
    handle, _ = sds.add_new_subobject(p)
    sds.rename_subobject(handle, unreal.Text(name))
    comp = [c for c in owner.get_components_by_class(unreal.InstancedStaticMeshComponent) if c.get_instance_count() == 0 and c.static_mesh is None][0]
    comp.set_static_mesh(mesh)
    comp.set_collision_profile_name("NoCollision")
    comp.set_editor_property("cast_shadow", shadow)
    comp.set_editor_property("mobility", unreal.ComponentMobility.STATIC)
    return comp


# ------------------------------------------------------------------ world
def build_world():
    with open(os.path.join(ROOT, "SourceArt", "World", "layout.json")) as f:
        layout = json.load(f)
    assign_materials()
    for folder in ("Greybox", "Terrain", "Props", "Water"):
        clear_folder(folder)

    # terrain: WorldStatic, complex-as-simple collision set on the assets at import
    for t in layout["terrain"]:
        mesh_actor(load(MESH + t["mesh"]), t["pos"], 0.0, t["mesh"][5:], t["folder"], collide=True)
    w = layout["water"]
    mesh_actor(load(MESH + w["mesh"]), w["pos"], 0.0, "Pond", "Water", collide=False, shadow=False)

    # single actors: rocks over their collision boxes, the ruin, fences, logs
    for a in layout["actors"]:
        mesh_actor(load(MESH + a["mesh"]), a["pos"], a["yaw"], a["label"], a["folder"], collide=False, shadow=a["mesh"] != "SM_BannerCloth")
    for b in layout["blockers"]:
        s = b["size"]
        folder = "Props/Rocks" if b["label"].startswith("Rock_") else ("Props/Foliage" if b["label"].startswith("Fir_") else "Props/Ruin")
        box = eas.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(*b["pos"]), unreal.Rotator(0, 0, b["yaw"]))
        box.set_actor_label(b["label"])
        box.set_folder_path(folder)
        c = box.static_mesh_component
        c.set_static_mesh(CUBE)
        box.set_actor_scale3d(unreal.Vector(s[0] / 100.0, s[1] / 100.0, s[2] / 100.0))
        c.set_editor_property("visible", False)            # collision only: one convex box per obstacle
        c.set_editor_property("cast_shadow", False)
        box.tags = ["SRBlocker"]

    # instanced dressing, one actor per family
    families = {"Conifers": ("SM_Conifer_", True), "Grass": ("SM_Tuft_", False), "Stones": ("SM_Rock_", True), "Deadwood": ("SM_Log", True)}
    total = 0
    for label, (prefix, shadow) in families.items():
        owner = eas.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, 0))
        owner.set_actor_label(label)
        owner.set_folder_path("Props/Foliage" if label in ("Conifers", "Grass") else "Props/Rocks")
        for mesh_name, items in sorted(layout["instances"].items()):
            if not mesh_name.startswith(prefix):
                continue
            comp = add_ism(owner, load(MESH + mesh_name), mesh_name[3:], shadow)
            xfs = [unreal.Transform(unreal.Vector(x, y, z), unreal.Rotator(0, 0, yaw), unreal.Vector(s, s, s)) for x, y, z, yaw, s in items]
            comp.add_instances(xfs, False, True)
            total += len(xfs)
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
LOOK = dict(
    sun_pitch=-33.0, sun_yaw=75.0,              # light travels toward screen right and a little up-screen
    sun_lux=11.0, sun_color=(255, 214, 165), sun_source_angle=1.8, sun_shafts=11.0,
    sky_intensity=7.5, sky_color=(205, 225, 255), sky_fog=0.3,
    fog_density=0.55, fog_falloff=0.3, fog_albedo=(255, 242, 224), fog_phase=0.35, fog_extinction=1.0,
    exposure_bias=-0.6,
)


def build_lighting():
    V4 = unreal.Vector4
    L = LOOK
    # Sun: low and warm, from screen left, raking across the field toward screen right and slightly up-screen.
    # Terrace faces that turn toward it light up, the rest sit in cool sky fill; long shadows cross the lane.
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
if "lighting" in PARTS:
    build_lighting()
les.save_current_level()
print("saved", MAP)
