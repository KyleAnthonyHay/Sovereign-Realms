"""Sounds -> /Game/Voxel/Audio (run inside the editor):

    python3 Tools/ue_py.py Tools/ue/import_audio.py

  VoxelLab/SourceArt/Audio/*.wav             this project's own: S_Step_<Surface>_<n> (the steps cut from the recordings in
                                             Raw/ by Tools/audio/slice_steps.py; Raw/ itself is not imported), S_OrderMove
  ../SourceArt/Audio/S_Music_1..8, S_AmbientLoop, S_WindLoop, S_Birds*, S_MarchLoop   the main game's soundtrack and ambience
Loops are flagged looping; the songs stream. One-shots (steps, the order click) do not loop and are kept decoded-ready
in memory (ForceInline), so that a step never waits on a load. The sword's sounds (S_SwordSwing*, S_TargetThunk*: copies
of the main game's, in this project's SourceArt/Audio) are one-shots too. Step assets whose .wav is gone (a surface that now has
fewer variations, the old S_Footstep_* placeholders) are deleted.
"""
import glob
import os

import unreal

ROOT = os.path.abspath(unreal.Paths.project_dir())
MAIN = os.path.abspath(os.path.join(ROOT, "..", "SourceArt", "Audio"))
DST = "/Game/Voxel/Audio"
eal = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()

files = sorted(glob.glob(os.path.join(ROOT, "SourceArt", "Audio", "*.wav")))      # (not Raw/: the top folder only)
ONE_SHOTS = ("S_Step_", "S_OrderMove", "S_SwordSwing", "S_TargetThunk", "S_BowRelease", "S_ArrowFly", "S_ArrowHit")
for name in ["S_AmbientLoop", "S_WindLoop", "S_MarchLoop", "S_Birds", "S_Birds_2", "S_Birds_3"] + ["S_Music_%d" % i for i in range(1, 9)]:
    p = os.path.join(MAIN, name + ".wav")
    if os.path.exists(p):
        files.append(p)
tasks = []
for p in files:
    t = unreal.AssetImportTask()
    t.filename = p
    t.destination_path = DST
    t.automated = True
    t.replace_existing = True
    t.save = False
    tasks.append(t)
tools.import_asset_tasks(tasks)
n = 0
for p in files:
    name = os.path.splitext(os.path.basename(p))[0]
    s = eal.load_asset(DST + "/" + name)
    if not s:
        print("missing after import:", name)
        continue
    s.set_editor_property("looping", name.endswith("Loop"))
    if name.startswith(ONE_SHOTS):
        s.set_editor_property("loading_behavior", unreal.SoundWaveLoadingBehavior.FORCE_INLINE)
    if name.startswith("S_Music"):
        try:
            s.set_editor_property("loading_behavior", unreal.SoundWaveLoadingBehavior.FORCE_INLINE if False else unreal.SoundWaveLoadingBehavior.RETAIN_ON_LOAD)
        except Exception:
            pass
    eal.save_loaded_asset(s, False)
    n += 1
have = set(os.path.splitext(os.path.basename(p))[0] for p in files)
for path in eal.list_assets(DST, False, False):
    name = path.split("/")[-1].split(".")[0]
    if name.startswith(("S_Step_", "S_Footstep_")) and name not in have:
        print("deleted", name, eal.delete_asset(path.split(".")[0]))
print("audio imported:", n)
