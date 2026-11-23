"""Imports the interface art (the main game's icon atlas and title lettering) into /Game/Voxel/UI (run inside the editor):

    python3 Tools/ue_py.py Tools/ue/import_ui.py

  SourceArt/UI/T_UI_Icons.png   the icon atlas (Tools/ui/gen_ui_art.py in the deprecated first draft, see git history: 8 x 7 icons of 16 px in 18 px
                                cells, and their enemy-red twins under them)
  SourceArt/UI/T_UI_Title.png   the title screen's lettering
  SourceArt/UI/T_UI_Portraits.png  the units' portraits (Tools/blender/render_portraits.py)
UI textures: point filtered, uncompressed, no mips, clamped, never streamed. Re-running re-imports in place.
"""
import glob
import os
import unreal

ROOT = os.path.abspath(unreal.Paths.project_dir())
DST = "/Game/Voxel/UI"
eal = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()

paths = sorted(glob.glob(os.path.join(ROOT, "SourceArt", "UI", "*.png")))
tasks = []
for path in paths:
    t = unreal.AssetImportTask()
    t.filename = path
    t.destination_path = DST
    t.automated = True
    t.replace_existing = True
    t.save = False
    t.factory = unreal.TextureFactory()
    tasks.append(t)
tools.import_asset_tasks(tasks)
for path in paths:
    name = os.path.splitext(os.path.basename(path))[0]
    tex = eal.load_asset(DST + "/" + name)
    if tex is None:
        print("FAILED", name)
        continue
    tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_EDITOR_ICON)
    tex.set_editor_property("srgb", True)
    # the pixel-art atlas and lettering point filtered; the rendered portraits smooth
    tex.set_editor_property("filter", unreal.TextureFilter.TF_BILINEAR if "Portraits" in name else unreal.TextureFilter.TF_NEAREST)
    tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_UI)
    tex.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
    tex.set_editor_property("never_stream", True)
    tex.set_editor_property("address_x", unreal.TextureAddress.TA_CLAMP)
    tex.set_editor_property("address_y", unreal.TextureAddress.TA_CLAMP)
    eal.save_loaded_asset(tex, False)
    print("imported", DST + "/" + name, tex.blueprint_get_size_x(), tex.blueprint_get_size_y())
