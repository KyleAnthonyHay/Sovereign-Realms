"""Imports the generated source art into the project (run inside the editor):

    Tools/ue_py.py Tools/import_world_assets.py

  SourceArt/Textures/*.png           -> /Game/SR/Textures   (pixel art: nearest filter, uncompressed, sRGB;
                                                              *_N and T_Splat are linear data)
  SourceArt/Meshes/battlefield.gltf  -> /Game/SR/Meshes     (one static mesh per glTF node)

Re-running re-imports in place, so references in the level and in materials survive. Meshes that
the generator no longer produces are deleted. Set PARTS = ["textures"] or ["meshes"] to do one half.
Materials are assigned to the meshes afterwards by Tools/build_battlefield_visuals.py (they may not
exist yet on a first run).
"""
import glob
import os
import unreal

PARTS = globals().get("PARTS", ["textures", "meshes"])
ROOT = os.path.abspath(unreal.Paths.project_dir())
TEX_SRC = os.path.join(ROOT, "SourceArt", "Textures")
TEX_DST = "/Game/SR/Textures"
MESH_SRC = os.path.join(ROOT, "SourceArt", "Meshes", "battlefield.gltf")
MESH_DST = "/Game/SR/Meshes"
eal = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()


def import_textures():
    tasks = []
    for path in sorted(glob.glob(os.path.join(TEX_SRC, "*.png"))):
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
    for path in sorted(glob.glob(os.path.join(TEX_SRC, "*.png"))):
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
        data = name.endswith("_N") or name == "T_Splat"
        w, h = tex.blueprint_get_size_x(), tex.blueprint_get_size_y()
        pot = (w & (w - 1)) == 0 and (h & (h - 1)) == 0
        # Uncompressed BGRA8 so the palette stays exact. The asset is point filtered; the world materials sample
        # it through their own anti-aliased texel filter (see build_visual_materials.py), which uses the mip chain
        # only once texels are smaller than a screen pixel. Sprite strips and the splat map carry no mips.
        tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP if data
                                else unreal.TextureCompressionSettings.TC_EDITOR_ICON)
        tex.set_editor_property("srgb", not data)
        tex.set_editor_property("filter", unreal.TextureFilter.TF_BILINEAR if name == "T_Splat" else unreal.TextureFilter.TF_NEAREST)
        tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_PIXELS2D)
        tex.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_SIMPLE_AVERAGE if (pot and name != "T_Splat")
                                else unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
        tex.set_editor_property("never_stream", True)
        if name == "T_Splat":
            tex.set_editor_property("address_x", unreal.TextureAddress.TA_CLAMP)
            tex.set_editor_property("address_y", unreal.TextureAddress.TA_CLAMP)
        eal.save_loaded_asset(tex, False)
        n += 1
    print("textures:", n)


def import_meshes():
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
        if name.startswith("SM_T_"):
            # units find the ground and the cliffs with line traces against simple collision: use the render mesh for it
            body = sm.get_editor_property("body_setup")
            body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        eal.save_loaded_asset(sm, False)
    stale = 0
    for a in eal.list_assets(MESH_DST, False):
        nm = a.split("/")[-1].split(".")[0]
        if nm not in names:
            eal.delete_asset(a)
            stale += 1
    print("meshes:", len(names), "stale removed:", stale)


if "textures" in PARTS:
    import_textures()
if "meshes" in PARTS:
    import_meshes()
