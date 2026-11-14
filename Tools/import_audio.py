"""Imports SourceArt/Audio/S_*.wav into /Game/SR/Audio (run inside the editor: Tools/ue_py.py Tools/import_audio.py).
Loops (ambient bed, music) are flagged looping; everything else plays once. Re-running re-imports in place."""
import glob
import os
import unreal

ROOT = os.path.abspath(unreal.Paths.project_dir())
SRC = os.path.join(ROOT, "SourceArt", "Audio")
DST = "/Game/SR/Audio"
eal = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()

tasks = []
for path in sorted(glob.glob(os.path.join(SRC, "S_*.wav"))):
    t = unreal.AssetImportTask()
    t.filename = path
    t.destination_path = DST
    t.destination_name = os.path.splitext(os.path.basename(path))[0]
    t.automated = True
    t.replace_existing = True
    t.save = False
    tasks.append(t)
tools.import_asset_tasks(tasks)
n = 0
for t in tasks:
    name = t.destination_name
    wave = eal.load_asset(DST + "/" + name)
    if wave is None:
        print("FAILED", name)
        continue
    wave.set_editor_property("looping", name in ("S_AmbientLoop", "S_MusicLoop"))
    eal.save_loaded_asset(wave, False)
    n += 1
print("sounds imported:", n)
