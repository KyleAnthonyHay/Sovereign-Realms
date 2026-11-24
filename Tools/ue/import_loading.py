"""Imports the loading screen's art into /Game/Voxel/UI (run inside the editor):

    python Tools/ue_py.py Tools/ue/import_loading.py

  SourceArt/UI/T_UI_KingRun.png       King David running, 8 frames (Tools/blender/assets/king_run_sprite.py)
  SourceArt/UI/T_UI_KingCrouchRun.png ... and running crouched, ducking (the same script)
  SourceArt/UI/T_UI_RunnerProps.png   what he jumps on the loading screen (the same script)
  SourceArt/UI/T_UI_Emblem.png        the emblem at 256 px (the same script, from References/Branding)
Only these four (Tools/ue/import_ui.py re-imports everything in SourceArt/UI, the atlases too). UI textures: uncompressed,
no mips, clamped, never streamed, UI group; the sprites point filtered, the emblem smooth. Re-running re-imports in place.
"""
import os
import unreal

ROOT = os.path.abspath(unreal.Paths.project_dir())
DST = "/Game/Voxel/UI"
NAMES = {"T_UI_KingRun": unreal.TextureFilter.TF_NEAREST, "T_UI_KingCrouchRun": unreal.TextureFilter.TF_NEAREST, "T_UI_RunnerProps": unreal.TextureFilter.TF_NEAREST,
         "T_UI_Emblem": unreal.TextureFilter.TF_BILINEAR}
eal = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()

tasks = []
for name in NAMES:
    t = unreal.AssetImportTask()
    t.filename = os.path.join(ROOT, "SourceArt", "UI", name + ".png")
    t.destination_path = DST
    t.automated = True
    t.replace_existing = True
    t.save = False
    t.factory = unreal.TextureFactory()
    tasks.append(t)
tools.import_asset_tasks(tasks)
for name, filt in NAMES.items():
    tex = eal.load_asset(DST + "/" + name)
    if tex is None:
        print("FAILED", name)
        continue
    tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_EDITOR_ICON)
    tex.set_editor_property("srgb", True)
    tex.set_editor_property("filter", filt)
    tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_UI)
    tex.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
    tex.set_editor_property("never_stream", True)
    tex.set_editor_property("address_x", unreal.TextureAddress.TA_CLAMP)
    tex.set_editor_property("address_y", unreal.TextureAddress.TA_CLAMP)
    eal.save_loaded_asset(tex, False)
    print("imported", DST + "/" + name, tex.blueprint_get_size_x(), tex.blueprint_get_size_y())
