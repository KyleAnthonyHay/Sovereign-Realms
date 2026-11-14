"""Imports the interface art into /Game/SR/UI and the minimap base into /Game/SR/Textures (run inside the editor):

    Tools/ue_py.py Tools/import_ui_assets.py

  SourceArt/UI/*.png                       -> /Game/SR/UI        (Tools/ui/gen_ui_art.py)
  SourceArt/Textures/T_MinimapBase.png     -> /Game/SR/Textures  (Tools/world/gen_battlefield.py --minimap)
All are UI textures: point filtered, uncompressed, no mips, clamped, never streamed. Re-running re-imports in place.
"""
import glob
import os
import unreal

ROOT = os.path.abspath(unreal.Paths.project_dir())
eal = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()

jobs = [(p, "/Game/SR/UI") for p in sorted(glob.glob(os.path.join(ROOT, "SourceArt", "UI", "*.png")))]
jobs.append((os.path.join(ROOT, "SourceArt", "Textures", "T_MinimapBase.png"), "/Game/SR/Textures"))
tasks = []
for path, dst in jobs:
    t = unreal.AssetImportTask()
    t.filename = path
    t.destination_path = dst
    t.automated = True
    t.replace_existing = True
    t.save = False
    t.factory = unreal.TextureFactory()
    tasks.append(t)
tools.import_asset_tasks(tasks)
for path, dst in jobs:
    name = os.path.splitext(os.path.basename(path))[0]
    tex = eal.load_asset(dst + "/" + name)
    if tex is None:
        print("FAILED", name)
        continue
    minimap = name == "T_MinimapBase"
    tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_EDITOR_ICON)
    tex.set_editor_property("srgb", True)
    tex.set_editor_property("filter", unreal.TextureFilter.TF_BILINEAR if minimap else unreal.TextureFilter.TF_NEAREST)
    tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_UI)
    tex.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
    tex.set_editor_property("never_stream", True)
    tex.set_editor_property("address_x", unreal.TextureAddress.TA_CLAMP)
    tex.set_editor_property("address_y", unreal.TextureAddress.TA_CLAMP)
    eal.save_loaded_asset(tex, False)
    print("imported", dst + "/" + name, tex.blueprint_get_size_x(), tex.blueprint_get_size_y())
