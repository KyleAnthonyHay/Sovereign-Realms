"""Brings the voxel art into the project (run inside the editor):

    python3 Tools/ue_py.py Tools/ue/import_assets.py
    python3 Tools/ue_py.py -c "PARTS=['meshes']; ONLY=['SM_Barracks']; exec(open(r'<abs>/Tools/ue/import_assets.py').read())"

  SourceArt/Textures/T_Vox_<slot>.png -> /Game/Voxel/Textures      (nearest filtering, uncompressed: pixel art)
  M_Voxel + MI_Vox_<slot>             -> /Game/Voxel/Materials     (texture x vertex colour; glow for the lit slots)
  SourceArt/Meshes/<name>.gltf        -> /Game/Voxel/Meshes        (slots get their MI_Vox_<slot>; collision from <name>.json)

PARTS: any of 'textures', 'materials', 'meshes' (default: all). ONLY: mesh names to (re)import.
"""
import glob
import json
import os
import sys

import unreal

ROOT = os.path.abspath(unreal.Paths.project_dir())
sys.path.insert(0, os.path.join(ROOT, "Tools", "blender"))
import importlib
import voxmats
importlib.reload(voxmats)

PARTS = globals().get("PARTS") or ["textures", "materials", "meshes"]
ONLY = globals().get("ONLY")
TEX_DIR = "/Game/Voxel/Textures"
MAT_DIR = "/Game/Voxel/Materials"
MESH_DIR = "/Game/Voxel/Meshes"
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
MP = unreal.MaterialProperty


def import_textures():
    paths = sorted(glob.glob(os.path.join(ROOT, "SourceArt", "Textures", "T_Vox_*.png")))
    tasks = []
    for p in paths:
        t = unreal.AssetImportTask()
        t.filename = p
        t.destination_path = TEX_DIR
        t.automated = True
        t.replace_existing = True
        t.save = False
        tasks.append(t)
    tools.import_asset_tasks(tasks)
    n = 0
    for p in paths:
        name = os.path.splitext(os.path.basename(p))[0]
        tex = eal.load_asset(TEX_DIR + "/" + name)
        if not tex:
            print("texture missing after import:", name)
            continue
        tex.set_editor_property("filter", unreal.TextureFilter.TF_NEAREST)
        tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_EDITOR_ICON)
        tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_PIXELS2D)
        tex.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
        tex.set_editor_property("srgb", True)
        tex.set_editor_property("never_stream", True)
        eal.save_loaded_asset(tex, False)
        n += 1
    # A texture re-imported over a loaded one can be left as a blank placeholder (white surfaces in the level) although
    # it reports the right size. Changing a property forces its platform data to be rebuilt: do that for all of them.
    for p in paths:
        tex = eal.load_asset(TEX_DIR + "/" + os.path.splitext(os.path.basename(p))[0])
        if tex:
            tex.set_editor_property("srgb", False)
            tex.set_editor_property("srgb", True)
            eal.save_loaded_asset(tex, False)
    print("textures:", n)


def build_materials():
    path = MAT_DIR + "/M_Voxel"
    if eal.does_asset_exist(path):
        mat = eal.load_asset(path)
        mel.delete_all_material_expressions(mat)
    else:
        mat = tools.create_asset("M_Voxel", MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())

    def node(cls, x, y, **props):
        e = mel.create_material_expression(mat, cls, x, y)
        for k, v in props.items():
            e.set_editor_property(k, v)
        return e

    tex = node(unreal.MaterialExpressionTextureSampleParameter2D, -900, -200, parameter_name="Tex",
               texture=eal.load_asset(TEX_DIR + "/T_Vox_stone"))
    vc = node(unreal.MaterialExpressionVertexColor, -900, 100)
    tint = node(unreal.MaterialExpressionVectorParameter, -900, 300, parameter_name="Tint", default_value=unreal.LinearColor(1, 1, 1, 1))
    mul = node(unreal.MaterialExpressionMultiply, -600, -100)
    mul2 = node(unreal.MaterialExpressionMultiply, -400, -100)
    mel.connect_material_expressions(tex, "RGB", mul, "A")
    mel.connect_material_expressions(vc, "", mul, "B")
    mel.connect_material_expressions(mul, "", mul2, "A")
    mel.connect_material_expressions(tint, "", mul2, "B")
    mel.connect_material_property(mul2, "", MP.MP_BASE_COLOR)
    rough = node(unreal.MaterialExpressionScalarParameter, -400, 150, parameter_name="Roughness", default_value=0.9)
    metal = node(unreal.MaterialExpressionScalarParameter, -400, 250, parameter_name="Metallic", default_value=0.0)
    spec = node(unreal.MaterialExpressionScalarParameter, -400, 350, parameter_name="Specular", default_value=0.25)
    mel.connect_material_property(rough, "", MP.MP_ROUGHNESS)
    mel.connect_material_property(metal, "", MP.MP_METALLIC)
    mel.connect_material_property(spec, "", MP.MP_SPECULAR)
    em = node(unreal.MaterialExpressionScalarParameter, -400, 480, parameter_name="Emissive", default_value=0.0)
    emul = node(unreal.MaterialExpressionMultiply, -200, 420)
    mel.connect_material_expressions(mul2, "", emul, "A")
    mel.connect_material_expressions(em, "", emul, "B")
    mel.connect_material_property(emul, "", MP.MP_EMISSIVE_COLOR)
    mel.recompile_material(mat)
    eal.save_loaded_asset(mat, False)

    n = 0
    for slot in voxmats.SLOTS:
        name = "MI_Vox_" + slot
        p = MAT_DIR + "/" + name
        mi = eal.load_asset(p) if eal.does_asset_exist(p) else tools.create_asset(name, MAT_DIR, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        # Tools/ue/build_special_materials.py. (Leaves stay on M_Voxel: the wind material M_VoxLeaves makes the shadow
        # maps redraw every tree each frame; build_special_materials.py with PARTS=["leaves"] switches it on.)
        if slot == "cloth":
            continue                                        # MI_Vox_cloth is M_VoxSway's (build_special_materials.py)
        special = {"water": "M_VoxWater"}.get(slot)
        parent = eal.load_asset(MAT_DIR + "/" + special) if special and eal.does_asset_exist(MAT_DIR + "/" + special) else mat
        mel.set_material_instance_parent(mi, parent)
        tex_asset = eal.load_asset(TEX_DIR + "/T_Vox_" + slot)
        if tex_asset:
            mel.set_material_instance_texture_parameter_value(mi, "Tex", tex_asset)
        em_v, rough_v, metal_v = voxmats.SLOT_SURFACE.get(slot, (0.0, 0.9, 0.0))
        mel.set_material_instance_scalar_parameter_value(mi, "Emissive", em_v)
        mel.set_material_instance_scalar_parameter_value(mi, "Roughness", rough_v)
        mel.set_material_instance_scalar_parameter_value(mi, "Metallic", metal_v)
        mel.update_material_instance(mi)
        eal.save_loaded_asset(mi, False)
        n += 1
    print("materials: M_Voxel +", n, "instances")


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
    cm = pipe.get_editor_property("common_meshes_properties")
    cm.set_editor_property("recompute_normals", False)
    cm.set_editor_property("recompute_tangents", True)
    cm.set_editor_property("use_full_precision_u_vs", True)
    cm.set_editor_property("remove_degenerates", False)
    cm.set_editor_property("vertex_color_import_option", unreal.InterchangeVertexColorImportOption.IVCIO_REPLACE)
    override = unreal.InterchangePipelineStackOverride()
    override.add_pipeline(pipe)
    return override


SWAYING = ("SM_GrassTuft", "SM_Flowers", "SM_Wheat")


def import_meshes():
    n = 0
    for path in sorted(glob.glob(os.path.join(ROOT, "SourceArt", "Meshes", "*.gltf"))):
        name = os.path.splitext(os.path.basename(path))[0]
        if ONLY and name not in ONLY:
            continue
        meta = {}
        mpath = os.path.splitext(path)[0] + ".json"
        if os.path.exists(mpath):
            with open(mpath) as f:
                meta = json.load(f)
        task = unreal.AssetImportTask()
        task.filename = path
        task.destination_path = MESH_DIR
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
            new, missing = [], []
            for m in mats:
                slot = str(m.get_editor_property("material_slot_name"))
                key = slot[4:] if slot.startswith("Vox_") else slot
                # grass, flowers and wheat sway: their own instances of M_VoxSway (weight = height above the root)
                mi = eal.load_asset(MAT_DIR + "/MI_Sway_" + key) if name.startswith(SWAYING) else None
                mi = mi or eal.load_asset(MAT_DIR + "/MI_Vox_" + key)
                if mi is None:
                    missing.append(slot)
                    mi = m.get_editor_property("material_interface")
                new.append(unreal.StaticMaterial(material_interface=mi, material_slot_name=m.get_editor_property("material_slot_name"),
                                                 uv_channel_data=m.get_editor_property("uv_channel_data")))
            sm.set_editor_property("static_materials", new)
            body = sm.get_editor_property("body_setup")
            if body:
                collision = meta.get("collision", "complex")
                flag = unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE if collision == "complex" else unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX
                body.set_editor_property("collision_trace_flag", flag)
            eal.save_loaded_asset(sm, False)
            b = sm.get_bounding_box()
            print("%s: %d slots, %d tris, bounds (%.0f %.0f %.0f)..(%.0f %.0f %.0f)%s" % (
                sm.get_name(), len(mats), sm.get_num_triangles(0), b.min.x, b.min.y, b.min.z, b.max.x, b.max.y, b.max.z,
                (" MISSING " + ",".join(missing)) if missing else ""))
            n += 1
    print("meshes imported:", n)


if "textures" in PARTS:
    import_textures()
if "materials" in PARTS:
    build_materials()
if "meshes" in PARTS:
    import_meshes()
