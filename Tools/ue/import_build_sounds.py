"""Imports only the building sounds (VLConstruction.cpp) into /Game/Voxel/Audio, as import_audio.py does its one-shots
(run inside the editor; import_audio.py imports them too, with everything else):

    python3 Tools/ue_py.py Tools/ue/import_build_sounds.py
"""
import glob
import os

import unreal

ROOT = os.path.abspath(unreal.Paths.project_dir())
DST = "/Game/Voxel/Audio"
tools = unreal.AssetToolsHelpers.get_asset_tools()
files = [p for p in sorted(glob.glob(os.path.join(ROOT, "SourceArt", "Audio", "*.wav")))
         if os.path.basename(p).startswith(("S_BuildPlace", "S_BuildHammer", "S_Woodwork", "S_BuildComplete"))]
tasks = []
for p in files:
    t = unreal.AssetImportTask()
    t.filename = p
    t.destination_path = DST
    t.automated = True
    t.replace_existing = True
    t.save = True
    tasks.append(t)
tools.import_asset_tasks(tasks)
n = 0
for t in tasks:
    for path in t.get_editor_property("imported_object_paths"):
        w = unreal.load_object(None, str(path))
        if isinstance(w, unreal.SoundWave):
            w.set_editor_property("looping", False)
            try:
                w.set_editor_property("loading_behavior", unreal.SoundWaveLoadingBehavior.FORCE_INLINE)
            except Exception:
                pass
            unreal.EditorAssetLibrary.save_loaded_asset(w, False)
            n += 1
print("build sounds imported:", n)
