"""King David's parts -> /Game/Voxel/King, and the data asset the character reads (run inside the editor):

    python3 Tools/ue_py.py Tools/ue/import_king.py
    troops (their own folder and data asset; the King's are left alone):
    python3 Tools/ue_py.py -c "KING='SM_Swordsman'; DST='/Game/Voxel/Troops/Swordsman'; DA='DA_Swordsman'; exec(open(r'<abs>/Tools/ue/import_king.py').read())"

  SourceArt/Meshes/SM_King_<Part>.gltf  (Tools/blender/assets/king.py; each mesh's origin is its joint)
  SourceArt/Meshes/SM_King.json         {"height", "radius", "parts": {"Body": {"mesh", "pivot": [x, y, z] metres, Blender axes}, ...}}
  -> /Game/Voxel/King/DA_King (VLCharacterData): AVLKing builds the figure from it and swings the parts in code.
He is modelled facing -Y in Blender, which is +Y in Unreal; the character's forward is +X, so MeshYaw = -90.
"""
import json
import os

import unreal

ROOT = os.path.abspath(unreal.Paths.project_dir())
SRC = os.path.join(ROOT, "SourceArt", "Meshes")
DST = globals().get("DST") or "/Game/Voxel/King"
DA = globals().get("DA") or "DA_King"
MAT_DIR = "/Game/Voxel/Materials"
eal = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()

KING = globals().get("KING") or "SM_King"          # which build: SM_King, SM_KingA, SM_KingB (the json's name)
with open(os.path.join(SRC, KING + ".json")) as f:
    info = json.load(f)


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


mel = unreal.MaterialEditingLibrary


def king_material(slot):
    """The king's colours are all in his vertex colours, so every slot uses the plain white 'paint' texture: the dark
    metal and yellow gold textures of the buildings would multiply his armour to black and his gold to orange.
    Gold and steel still get a metallic sheen."""
    key = slot[4:] if slot.startswith("Vox_") else slot
    name = "MI_King_" + key
    path = MAT_DIR + "/" + name
    mi = eal.load_asset(path) if eal.does_asset_exist(path) else tools.create_asset(
        name, MAT_DIR, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(mi, eal.load_asset(MAT_DIR + "/M_Voxel"))
    mel.set_material_instance_texture_parameter_value(mi, "Tex", eal.load_asset("/Game/Voxel/Textures/T_Vox_paint"))
    metal, rough, tint = {"gold": (0.55, 0.38, (1.25, 1.15, 1.0)), "metal": (0.35, 0.42, (1.45, 1.45, 1.5)),
                          "wool": (0.0, 0.95, (1.0, 1.0, 1.0))}.get(key, (0.0, 0.85, (1.0, 1.0, 1.0)))
    mel.set_material_instance_scalar_parameter_value(mi, "Metallic", metal)
    mel.set_material_instance_scalar_parameter_value(mi, "Roughness", rough)
    mel.set_material_instance_scalar_parameter_value(mi, "Emissive", 0.0)
    mel.set_material_instance_vector_parameter_value(mi, "Tint", unreal.LinearColor(tint[0], tint[1], tint[2], 1.0))
    mel.update_material_instance(mi)
    eal.save_loaded_asset(mi, False)
    return mi


def flash_material():
    """M_KingFlash: unlit white, drawn over him as an overlay when he is hurt; "Flash" (0..1) is how much of it shows."""
    path = MAT_DIR + "/M_KingFlash"
    if eal.does_asset_exist(path):
        mat = eal.load_asset(path)
        mel.delete_all_material_expressions(mat)
    else:
        mat = tools.create_asset("M_KingFlash", MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
    mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    col = mel.create_material_expression(mat, unreal.MaterialExpressionVectorParameter, -500, 0)
    col.set_editor_property("parameter_name", "Color")
    col.set_editor_property("default_value", unreal.LinearColor(1.6, 1.6, 1.6, 1.0))
    amt = mel.create_material_expression(mat, unreal.MaterialExpressionScalarParameter, -500, 250)
    amt.set_editor_property("parameter_name", "Flash")
    amt.set_editor_property("default_value", 1.0)
    mel.connect_material_property(col, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.connect_material_property(amt, "", unreal.MaterialProperty.MP_OPACITY)
    mel.recompile_material(mat)
    eal.save_loaded_asset(mat, False)
    return mat


parts = []
for part, d in info["parts"].items():
    path = os.path.join(SRC, d["mesh"] + ".gltf")
    if not os.path.exists(path):
        print("missing", path)
        continue
    task = unreal.AssetImportTask()
    task.filename = path
    task.destination_path = DST
    task.automated = True
    task.replace_existing = True
    task.save = False
    task.options = pipeline()
    tools.import_asset_tasks([task])
    sm = eal.load_asset(DST + "/" + d["mesh"])
    if not sm:
        print("import failed", d["mesh"])
        continue
    new = []
    for m in sm.get_editor_property("static_materials"):
        slot = str(m.get_editor_property("material_slot_name"))
        mi = king_material(slot)
        new.append(unreal.StaticMaterial(material_interface=mi, material_slot_name=m.get_editor_property("material_slot_name"),
                                         uv_channel_data=m.get_editor_property("uv_channel_data")))
    sm.set_editor_property("static_materials", new)
    eal.save_loaded_asset(sm, False)
    x, y, z = d["pivot"]
    # Blender (x, y, z) metres, facing -Y  ->  character space cm, X forward, Y right, Z up:  forward = -y, right = -x
    p = unreal.VLPart()
    p.set_editor_property("name", part)
    p.set_editor_property("parent", d.get("parent", "") or "None")
    p.set_editor_property("mesh", sm)
    p.set_editor_property("pivot", unreal.Vector(-y * 100.0, -x * 100.0, z * 100.0))
    parts.append(p)
    b = sm.get_bounding_box()
    print("%s: pivot (%.0f %.0f %.0f), bounds (%.0f %.0f %.0f)..(%.0f %.0f %.0f)" % (part, -y * 100, -x * 100, z * 100, b.min.x, b.min.y, b.min.z, b.max.x, b.max.y, b.max.z))

path = DST + "/" + DA
if eal.does_asset_exist(path):
    da = eal.load_asset(path)
else:
    factory = unreal.DataAssetFactory()
    factory.set_editor_property("data_asset_class", unreal.VLCharacterData)
    da = tools.create_asset(DA, DST, unreal.VLCharacterData, factory)
da.set_editor_property("parts", parts)
da.set_editor_property("height", float(info.get("height", 1.7)) * 100.0)
da.set_editor_property("radius", float(info.get("radius", 0.42)) * 100.0)
da.set_editor_property("mesh_yaw", float(info.get("mesh_yaw", -90.0)))
da.set_editor_property("stride_length", float(info.get("stride", 1.8)) * 100.0)
da.set_editor_property("elbow_rest_l", float(info.get("elbow_l", 0.0)))
da.set_editor_property("elbow_rest_r", float(info.get("elbow_r", 0.0)))
da.set_editor_property("cape_cols", int(info.get("cape", {}).get("cols", 0)))
da.set_editor_property("cape_rows", int(info.get("cape", {}).get("rows", 0)))
da.set_editor_property("flash_material", flash_material())
def dust_parent():
    """M_VoxDust: flat colour from "Tint" (no texture, no vertex colour: the engine cube the dust is drawn with has none,
    which turned the puffs black on M_Voxel), a little "Emissive" of its own so it stays pale in shadow."""
    path = MAT_DIR + "/M_VoxDust"
    if eal.does_asset_exist(path):
        mat = eal.load_asset(path)
        mel.delete_all_material_expressions(mat)
    else:
        mat = tools.create_asset("M_VoxDust", MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
    mat.set_editor_property("used_with_instanced_static_meshes", True)     # drawn as instanced cubes (else: the grey default)
    tint = mel.create_material_expression(mat, unreal.MaterialExpressionVectorParameter, -600, 0)
    tint.set_editor_property("parameter_name", "Tint")
    tint.set_editor_property("default_value", unreal.LinearColor(0.97, 0.96, 0.93, 1.0))
    em = mel.create_material_expression(mat, unreal.MaterialExpressionScalarParameter, -600, 250)
    em.set_editor_property("parameter_name", "Emissive")
    em.set_editor_property("default_value", 0.45)
    mul = mel.create_material_expression(mat, unreal.MaterialExpressionMultiply, -300, 200)
    mel.connect_material_expressions(tint, "", mul, "A")
    mel.connect_material_expressions(em, "", mul, "B")
    rough = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -300, 400)
    rough.set_editor_property("r", 1.0)
    mel.connect_material_property(tint, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(mul, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.recompile_material(mat)
    eal.save_loaded_asset(mat, False)
    return mat


dust_path = MAT_DIR + "/MI_KingDust"
if not eal.does_asset_exist(dust_path):
    dust = tools.create_asset("MI_KingDust", MAT_DIR, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
else:
    dust = eal.load_asset(dust_path)
mel.set_material_instance_parent(dust, dust_parent())
mel.set_material_instance_scalar_parameter_value(dust, "Emissive", 0.45)
mel.set_material_instance_vector_parameter_value(dust, "Tint", unreal.LinearColor(0.97, 0.96, 0.93, 1.0))
mel.update_material_instance(dust)
eal.save_loaded_asset(dust, False)
da.set_editor_property("dust_material", dust)
# The sword: modelled in his fist; "sword.delta" (Blender axes) turns it about the grip into the scabbard. Blender
# (x, y, z) facing -Y is character space (-y, -x, z): that swap is a reflection, so the turn becomes M D M^T there.
sw = info.get("sword")
if sw and "Sword" in info["parts"]:
    import math
    M = [[0.0, -1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]
    D = sw["delta"]
    MD = [[sum(M[i][k] * D[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    R = [[sum(MD[i][k] * M[j][k] for k in range(3)) for j in range(3)] for i in range(3)]       # M D M^T
    tr = R[0][0] + R[1][1] + R[2][2]
    if tr > 0:
        q = 0.5 / math.sqrt(tr + 1.0)
        w, x, y, z = 0.25 / q, (R[2][1] - R[1][2]) * q, (R[0][2] - R[2][0]) * q, (R[1][0] - R[0][1]) * q
    elif R[0][0] > R[1][1] and R[0][0] > R[2][2]:
        q = 2.0 * math.sqrt(1.0 + R[0][0] - R[1][1] - R[2][2])
        w, x, y, z = (R[2][1] - R[1][2]) / q, 0.25 * q, (R[0][1] + R[1][0]) / q, (R[0][2] + R[2][0]) / q
    elif R[1][1] > R[2][2]:
        q = 2.0 * math.sqrt(1.0 + R[1][1] - R[0][0] - R[2][2])
        w, x, y, z = (R[0][2] - R[2][0]) / q, (R[0][1] + R[1][0]) / q, 0.25 * q, (R[1][2] + R[2][1]) / q
    else:
        q = 2.0 * math.sqrt(1.0 + R[2][2] - R[0][0] - R[1][1])
        w, x, y, z = (R[1][0] - R[0][1]) / q, (R[0][2] + R[2][0]) / q, (R[1][2] + R[2][1]) / q, 0.25 * q
    # check: the quaternion turns the blade's direction in the fist onto the scabbard's
    bd = sw["blade_dir"]
    bd_c = [-bd[1], -bd[0], bd[2]]
    sd = sw["sheath_dir"]
    sd_c = [-sd[1], -sd[0], sd[2]]
    turned = unreal.Quat(x, y, z, w).rotate_vector(unreal.Vector(*bd_c))
    err = math.sqrt((turned.x - sd_c[0]) ** 2 + (turned.y - sd_c[1]) ** 2 + (turned.z - sd_c[2]) ** 2)
    sp = sw["sheath_pos"]
    # a troop's sword never leaves the hand: no scabbard ("has_sheath": false in its json)
    da.set_editor_property("has_sheath", bool(sw.get("has_sheath", info.get("has_sheath", True))))
    da.set_editor_property("sword_blade_dir", unreal.Vector(*bd_c))
    da.set_editor_property("sword_sheath_pos", unreal.Vector(-sp[1] * 100.0, -sp[0] * 100.0, sp[2] * 100.0))
    da.set_editor_property("sword_sheath_quat", unreal.Vector4(x, y, z, w))
    print("sword: sheathed at (%.0f, %.0f, %.0f) cm, turn check error %.4f" % (-sp[1] * 100, -sp[0] * 100, sp[2] * 100, err))
else:
    da.set_editor_property("has_sheath", False)
eal.save_loaded_asset(da, False)
print("%s: %d parts, height %.0f" % (DA, len(parts), da.get_editor_property("height")))
