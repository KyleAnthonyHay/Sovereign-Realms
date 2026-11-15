"""Imports the troop sprite sheets, the arrow sprite and the card meshes (run inside the editor):

    Tools/.venv/bin/python Tools/sprites/gen_sprite_cards.py      # cards.gltf, arrow_*.png (offline, once)
    Tools/ue_py.py Tools/import_character_sprites.py
    Tools/ue_py.py -c "ONLY=['sprite']; exec(open('<abs path>/Tools/build_visual_materials.py').read())"

  SourceArt/Characters/<name>_color.png     -> /Game/SR/Characters/T_<Name>_Color      sRGB, uncompressed BGRA8 (exact palette)
  SourceArt/Characters/<name>_teammask.png  -> /Game/SR/Characters/T_<Name>_TeamMask   linear, 8-bit grey
  SourceArt/Characters/<name>_normal.png    -> /Game/SR/Characters/T_<Name>_Normal     linear, uncompressed BGRA8
  SourceArt/Characters/cards.gltf           -> /Game/SR/Characters/SM_UnitCard, SM_ArrowCard

All textures: nearest filter, no mips, never streamed, group 2D Pixels. The sheets are 3840 x 2560 (not powers
of two) and are never minified below about one texel per screen pixel, so they carry no mip chain; the sprite
material anti-aliases texel edges itself. The normal sheet is NOT imported as a normal map: BC5 would smear
the hard pixel edges and re-derive blue. It is already in Unreal's convention (R = screen right, G = screen
down, B = toward the camera), so the green channel is not flipped; the material expands it with * 2 - 1.
Re-running re-imports in place, so material and code references survive.
"""
import os
import unreal

ROOT = os.path.abspath(unreal.Paths.project_dir())
SRC = os.path.join(ROOT, "SourceArt", "Characters")
DST = "/Game/SR/Characters"
eal = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
TC = unreal.TextureCompressionSettings

# source file stem -> (asset name, kind)
SHEETS = []
for troop in ("shieldbearer", "archer", "arrow", "miner", "farmer", "horseman", "catapult", "stone", "builder", "scout"):
    cap = troop.capitalize()
    SHEETS.append((troop + "_color", "T_%s_Color" % cap, "color"))
    SHEETS.append((troop + "_teammask", "T_%s_TeamMask" % cap, "mask"))
    if troop not in ("arrow", "stone"):
        SHEETS.append((troop + "_normal", "T_%s_Normal" % cap, "normal"))
# battlefield effects (SourceArt/FX, Tools/blender/make_fx.py): one strip each
for fx in ("fire", "smoke", "dust", "debris", "impact"):
    SHEETS.append(("../FX/fx_" + fx, "T_FX_" + fx.capitalize(), "color"))


def import_textures():
    tasks = []
    for stem, name, _ in SHEETS:
        t = unreal.AssetImportTask()
        t.filename = os.path.join(SRC, stem + ".png")
        t.destination_path = DST
        t.destination_name = name
        t.automated = True
        t.replace_existing = True
        t.save = False
        t.factory = unreal.TextureFactory()
        tasks.append(t)
    tools.import_asset_tasks(tasks)
    for stem, name, kind in SHEETS:
        tex = eal.load_asset(DST + "/" + name)
        if tex is None:
            print("FAILED", stem)
            continue
        tex.set_editor_property("compression_settings", {"color": TC.TC_EDITOR_ICON, "mask": TC.TC_GRAYSCALE,
                                                         "normal": TC.TC_VECTOR_DISPLACEMENTMAP}[kind])
        tex.set_editor_property("srgb", kind == "color")
        tex.set_editor_property("flip_green_channel", False)
        tex.set_editor_property("filter", unreal.TextureFilter.TF_NEAREST)
        tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_PIXELS2D)
        tex.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
        tex.set_editor_property("never_stream", True)
        tex.set_editor_property("address_x", unreal.TextureAddress.TA_CLAMP)
        tex.set_editor_property("address_y", unreal.TextureAddress.TA_CLAMP)
        eal.save_loaded_asset(tex, False)
        print("texture", name, tex.blueprint_get_size_x(), "x", tex.blueprint_get_size_y(), kind)


def import_cards():
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
    override = unreal.InterchangePipelineStackOverride()
    override.add_pipeline(pipe)
    task = unreal.AssetImportTask()
    task.filename = os.path.join(SRC, "cards.gltf")
    task.destination_path = DST
    task.automated = True
    task.replace_existing = True
    task.save = False
    task.options = override
    tools.import_asset_tasks([task])
    for p in [str(p) for p in task.get_editor_property("imported_object_paths")]:
        sm = unreal.load_object(None, p)
        if isinstance(sm, unreal.StaticMesh):
            b = sm.get_bounds()
            eal.save_loaded_asset(sm, False)
            print("mesh", sm.get_name(), "origin", b.origin, "extent", b.box_extent)


if not eal.does_directory_exist(DST):
    eal.make_directory(DST)
import_textures()
import_cards()
