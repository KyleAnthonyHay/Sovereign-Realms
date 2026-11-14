"""Imports the building meshes into the project (run inside the editor):

    Tools/ue_py.py Tools/import_buildings.py

  SourceArt/Buildings/<name>.gltf  -> /Game/SR/Buildings/SM_Bld_<Name>   (Tools/blender/build_building.py writes them)

Each mesh slot is named after its surface ("Bld_Ashlar", ...) and gets /Game/SR/Materials/MI_Bld_<slot>
(Tools/build_visual_materials.py, part "building"). The meshes carry no collision: a building blocks movement
through the boxes in its <name>.json, which the level builder / ASRBuilding create. Import the textures first:
    Tools/ue_py.py -c "PARTS=['textures']; exec(open(r'<repo>/Tools/import_world_assets.py').read())"
"""
import glob
import os
import unreal

ROOT = os.path.abspath(unreal.Paths.project_dir())
SRC = os.path.join(ROOT, "SourceArt", "Buildings")
DST = "/Game/SR/Buildings"
MAT = "/Game/SR/Materials/"
eal = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
ONLY = globals().get("ONLY")           # e.g. ["castle"]


def pipeline():
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
    me.set_editor_property("combine_static_meshes", True)
    cm = pipe.get_editor_property("common_meshes_properties")
    cm.set_editor_property("recompute_normals", False)
    cm.set_editor_property("recompute_tangents", True)
    cm.set_editor_property("use_full_precision_u_vs", True)      # UV0 is in centimetres
    cm.set_editor_property("remove_degenerates", False)
    cm.set_editor_property("vertex_color_import_option", unreal.InterchangeVertexColorImportOption.IVCIO_REPLACE)
    override = unreal.InterchangePipelineStackOverride()
    override.add_pipeline(pipe)
    return override


n = 0
for path in sorted(glob.glob(os.path.join(SRC, "*.gltf"))):
    name = os.path.splitext(os.path.basename(path))[0]
    if ONLY and name not in ONLY:
        continue
    task = unreal.AssetImportTask()
    task.filename = path
    task.destination_path = DST
    task.automated = True
    task.replace_existing = True
    task.save = False
    task.options = pipeline()
    tools.import_asset_tasks([task])
    for p in [str(x) for x in task.get_editor_property("imported_object_paths")]:
        sm = unreal.load_object(None, p)
        if not isinstance(sm, unreal.StaticMesh):
            continue
        mats = sm.get_editor_property("static_materials")
        missing = []
        for i, m in enumerate(mats):
            slot = str(m.get_editor_property("material_slot_name"))
            key = slot[4:] if slot.startswith("Bld_") else slot
            mi = eal.load_asset(MAT + "MI_Bld_" + key)
            if mi is None:
                missing.append(slot)
                continue
            sm.set_material(i, mi)
        body = sm.get_editor_property("body_setup")
        if body:
            body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_DEFAULT)
        eal.save_loaded_asset(sm, False)
        b = sm.get_bounding_box()
        print("%s: %d slots, bounds (%.0f %.0f %.0f)..(%.0f %.0f %.0f)%s" % (sm.get_name(), len(mats), b.min.x, b.min.y, b.min.z, b.max.x, b.max.y, b.max.z,
                                                                          (" MISSING MATERIALS " + ",".join(missing)) if missing else ""))
        n += 1
print("buildings imported:", n)
