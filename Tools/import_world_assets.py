"""Imports the generated source art into the project (run inside the editor):

    Tools/ue_py.py Tools/import_world_assets.py                                       (map "two")
    Tools/ue_py.py -c "MAP='four'; exec(open('<abs path to this file>').read())"      (map "four"; MAP='all': both)

  SourceArt/Textures/*.png            -> /Game/SR/Textures   (pixel art: nearest filter, uncompressed, sRGB;
                                                               *_N, T_Splat*, T_WaterMap* and T_WaterFlow* are linear data)
  SourceArt/Textures/PolyHaven/*/*.jpg, SourceArt/Textures/Nature/*.png
                                      -> /Game/SR/Textures/Nature   (photographic CC0 textures and the water's ripple /
                                                               foam textures: ordinary filtered, mipped, compressed;
                                                               PARTS = ["nature"] for these alone; Docs/ASSET_CREDITS.md)
  SourceArt/Meshes/battlefield.gltf   -> /Game/SR/Meshes     (map "two": one static mesh per glTF node)
  SourceArt/Meshes/battlefield4.gltf  -> /Game/SR/Meshes4    (map "four": its own land, water and props, so the two
                                                               maps' assets never overwrite each other)

Re-running re-imports in place, so references in the level and in materials survive. Meshes that
the generator no longer produces are deleted. Set PARTS = ["textures"] or ["meshes"] to do one half, and
TEX_PREFIX = "T_Bld_" to touch only the building textures.
Materials are assigned to the meshes afterwards by Tools/build_battlefield_visuals.py (they may not
exist yet on a first run).
"""
import glob
import os
import unreal

PARTS = globals().get("PARTS", ["textures", "meshes"])
TEX_PREFIX = globals().get("TEX_PREFIX", "")        # e.g. "T_Bld_": only (re)import textures whose name starts with it
ROOT = os.path.abspath(unreal.Paths.project_dir())
TEX_SRC = os.path.join(ROOT, "SourceArt", "Textures")
TEX_DST = "/Game/SR/Textures"
MAP = globals().get("MAP", "two")                    # "two", "four" or "all": which map's meshes
MAP_SFX = {"two": "", "four": "4"}
LOD1_SCREEN = 0.3                                    # a tree drops to its far-view mesh under this share of the screen (about the default zoom's far half)
eal = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()


def import_textures():
    tasks = []
    sources = sorted(glob.glob(os.path.join(TEX_SRC, TEX_PREFIX + "*.png")))
    for path in sources:
        t = unreal.AssetImportTask()
        t.filename = path
        t.destination_path = TEX_DST
        t.automated = True
        t.replace_existing = True
        t.save = False
        t.factory = unreal.TextureFactory()
        tasks.append(t)
    tools.import_asset_tasks(tasks)
    n = 0
    for path in sources:
        name = os.path.splitext(os.path.basename(path))[0]
        tex = eal.load_asset(TEX_DST + "/" + name)
        if tex is None:
            print("FAILED", name)
            continue
        if name == "T_LensDirt":                      # the one texture that is not pixel art: ordinary filtered, compressed
            tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_DEFAULT)
            tex.set_editor_property("srgb", True)
            tex.set_editor_property("filter", unreal.TextureFilter.TF_BILINEAR)
            tex.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
            eal.save_loaded_asset(tex, False)
            n += 1
            continue
        splat = name.startswith("T_Splat")
        data = name.endswith("_N") or splat or name.startswith(("T_WaterMap", "T_WaterFlow", "T_Forest"))
        w, h = tex.blueprint_get_size_x(), tex.blueprint_get_size_y()
        pot = (w & (w - 1)) == 0 and (h & (h - 1)) == 0
        # Uncompressed BGRA8 so the palette stays exact. The asset is point filtered; the world materials sample
        # it through their own anti-aliased texel filter (see build_visual_materials.py), which uses the mip chain
        # only once texels are smaller than a screen pixel. Sprite strips and the splat map carry no mips.
        tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP if data
                                else unreal.TextureCompressionSettings.TC_EDITOR_ICON)
        tex.set_editor_property("srgb", not data)
        tex.set_editor_property("filter", unreal.TextureFilter.TF_BILINEAR if (splat or name.startswith(("T_WaterMap", "T_WaterFlow", "T_Forest"))) else unreal.TextureFilter.TF_NEAREST)
        tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_PIXELS2D)
        tex.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_SIMPLE_AVERAGE if (pot and not splat and not name.startswith(("T_WaterMap", "T_WaterFlow", "T_Forest")))
                                else unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
        tex.set_editor_property("never_stream", True)
        if splat or name.startswith(("T_WaterMap", "T_WaterFlow", "T_Forest")):
            tex.set_editor_property("address_x", unreal.TextureAddress.TA_CLAMP)
            tex.set_editor_property("address_y", unreal.TextureAddress.TA_CLAMP)
        eal.save_loaded_asset(tex, False)
        if (tex.blueprint_get_size_x() <= 32 and os.path.getsize(path) > 20000) or splat or name.startswith(("T_WaterMap", "T_WaterFlow", "T_Forest")) or name.startswith("T_MinimapBase"):
            # A texture just imported can stay a placeholder in memory, whatever size it reports (the materials then
            # read an empty map: cobbles everywhere, pale dithered water, a blank minimap). Changing a property and
            # saving again makes it build; the maps' own data maps always get this.
            keep = tex.get_editor_property("filter")
            tex.set_editor_property("filter", unreal.TextureFilter.TF_BILINEAR if keep == unreal.TextureFilter.TF_NEAREST else unreal.TextureFilter.TF_NEAREST)
            tex.set_editor_property("filter", keep)
            eal.save_loaded_asset(tex, False)
        n += 1
    print("textures:", n)


def import_meshes(sfx):
    MESH_SRC = os.path.join(ROOT, "SourceArt", "Meshes", "battlefield%s.gltf" % sfx)
    MESH_DST = "/Game/SR/Meshes" + sfx
    pipe = unreal.InterchangeGenericAssetsPipeline()
    pipe.set_editor_property("asset_type_sub_folders", False)
    pipe.set_editor_property("scene_name_sub_folder", False)
    mp = pipe.get_editor_property("material_pipeline")
    mp.set_editor_property("import_materials", False)
    mp.get_editor_property("texture_pipeline").set_editor_property("import_textures", False)
    me = pipe.get_editor_property("mesh_pipeline")
    me.set_editor_property("collision", False)
    me.set_editor_property("build_nanite", False)
    me.set_editor_property("generate_lightmap_u_vs", False)
    cm = pipe.get_editor_property("common_meshes_properties")
    cm.set_editor_property("recompute_normals", False)
    cm.set_editor_property("recompute_tangents", True)
    cm.set_editor_property("use_full_precision_u_vs", True)      # UV0 is in centimetres: half floats would smear it
    cm.set_editor_property("remove_degenerates", False)
    cm.set_editor_property("vertex_color_import_option", unreal.InterchangeVertexColorImportOption.IVCIO_REPLACE)
    override = unreal.InterchangePipelineStackOverride()
    override.add_pipeline(pipe)
    task = unreal.AssetImportTask()
    task.filename = MESH_SRC
    task.destination_path = MESH_DST
    task.automated = True
    task.replace_existing = True
    task.save = False
    task.options = override
    tools.import_asset_tasks([task])
    paths = [str(p) for p in task.get_editor_property("imported_object_paths")]
    names = set()
    for p in paths:
        sm = unreal.load_object(None, p)
        if not isinstance(sm, unreal.StaticMesh):
            continue
        name = sm.get_name()
        names.add(name)
        if name.startswith("SM_T_") or name.startswith("SM_Water"):
            # units find the ground with line traces against simple collision: use the render mesh for it. The water
            # sheets too: the walkability grid traces them (alone, by component) to measure how deep the water is.
            body = sm.get_editor_property("body_setup")
            body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        eal.save_loaded_asset(sm, False)
    # the trees' far-view meshes (<name>_LOD1, Tools/world/props.py > tree_lods) become LOD 1 of <name> and are dropped
    smes = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    lods = 0
    for name in sorted(n for n in names if n.endswith("_LOD1")):
        base, far = eal.load_asset(MESH_DST + "/" + name[:-5]), eal.load_asset(MESH_DST + "/" + name)
        names.discard(name)
        if base is None or far is None:
            continue
        try:
            if smes.set_lod_from_static_mesh(base, 1, far, 0, True) >= 0:
                try:
                    base.set_editor_property("auto_compute_lod_screen_size", False)
                except Exception:
                    pass
                smes.set_lod_screen_sizes(base, [1.0, LOD1_SCREEN])
                eal.save_loaded_asset(base, False)
                lods += 1
        except Exception as ex:
            print("LOD", name, ex)
    if lods:
        print("far-view LODs set:", lods)
    stale = 0
    for a in (eal.list_assets(MESH_DST, False) if names else []):     # (an import that brought nothing in deletes nothing)
        nm = a.split("/")[-1].split(".")[0]
        if nm not in names:
            eal.delete_asset(a)
            stale += 1
    print("meshes %s:" % MESH_DST, len(names), "stale removed:", stale)


# ------------------------------------------------------------------ natural-world textures (photographic, CC0)
# SourceArt/Textures/PolyHaven/<asset>/<asset>_{diff,nor_gl}_<res>.jpg and SourceArt/Textures/Nature/*.png (made by
# Tools/textures/gen_nature_textures.py) -> /Game/SR/Textures/Nature/T_N_<Name>_{D,N}. Ordinary filtered, mipped,
# compressed textures (not pixel art): M_Terrain and M_Water sample them at the world's texel grid themselves.
# Sources and licences: Docs/ASSET_CREDITS.md.
NATURE = {"rock_face_03": "RockFace", "cliff_side": "Cliff", "mossy_rock": "MossRock", "aerial_grass_rock": "AerialGrass", "leafy_grass": "Grass",
          "brown_mud_leaves_01": "Mud", "river_small_rocks": "Pebbles", "aerial_rocks_02": "AerialRock", "forrest_ground_01": "Forest"}
NATURE_DST = TEX_DST + "/Nature"


def import_nature():
    jobs = []                                                   # (source file, asset name, is normal map, is data)
    for folder, name in NATURE.items():
        for kind, sfx in (("diff", "D"), ("nor_gl", "N")):
            found = glob.glob(os.path.join(TEX_SRC, "PolyHaven", folder, "%s_%s_*.jpg" % (folder, kind)))
            if found:
                jobs.append((found[0], "T_N_%s_%s" % (name, sfx), kind == "nor_gl", False))
    for path in sorted(glob.glob(os.path.join(TEX_SRC, "Nature", "*.png"))):
        nm = os.path.splitext(os.path.basename(path))[0]
        jobs.append((path, nm, nm.endswith("_N"), not nm.endswith("_N")))
    tasks = []
    for path, name, _, _ in jobs:
        t = unreal.AssetImportTask()
        t.filename, t.destination_path, t.destination_name = path, NATURE_DST, name
        t.automated, t.replace_existing, t.save = True, True, False
        t.factory = unreal.TextureFactory()
        tasks.append(t)
    tools.import_asset_tasks(tasks)
    n = 0
    for path, name, normal, data in jobs:
        tex = eal.load_asset(NATURE_DST + "/" + name)
        if tex is None:
            print("FAILED", name)
            continue
        tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP if normal else
                                (unreal.TextureCompressionSettings.TC_MASKS if data else unreal.TextureCompressionSettings.TC_DEFAULT))
        tex.set_editor_property("srgb", not (normal or data))
        tex.set_editor_property("flip_green_channel", bool(normal and "PolyHaven" in path))     # theirs are OpenGL (+Y up)
        tex.set_editor_property("filter", unreal.TextureFilter.TF_DEFAULT)
        tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD_NORMAL_MAP if normal else unreal.TextureGroup.TEXTUREGROUP_WORLD)
        tex.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_FROM_TEXTURE_GROUP)
        tex.set_editor_property("never_stream", True)
        eal.save_loaded_asset(tex, False)
        n += 1
    print("nature textures:", n)


if "textures" in PARTS:
    import_textures()
    if not TEX_PREFIX:
        import_nature()
if "nature" in PARTS:
    import_nature()
if "meshes" in PARTS:
    for m in (list(MAP_SFX) if MAP == "all" else [MAP]):
        import_meshes(MAP_SFX[m])
