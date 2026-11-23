"""Gives the units' parts and the buildings their far levels of detail (run inside the editor, not during PIE):

    python3 Tools/ue_py.py Tools/ue/voxel_lods.py 900
    some of them:   python3 Tools/ue_py.py -c "ONLY=['SM_Castle']; exec(open(r'<abs>/Tools/ue/voxel_lods.py').read())"

SourceArt/Meshes/LOD/<mesh>_L1.gltf / _L2.gltf (Tools/blender/assets/voxel_lods.py; lods.json lists them) become LOD 1
and LOD 2 of the mesh of that name in /Game/Voxel/King, /Game/Voxel/Troops/<Kind> or /Game/Voxel/Meshes. The files are
imported into /Game/Voxel/LODTmp, copied into the mesh and deleted again: nothing new is cooked but the levels.
Every level keeps the mesh's own material slots (checked here, section by section): the enemy's red cloth, the
placement ghost and the hurt flash set materials by slot.

Where a level is drawn. The engine picks it for each part on its own, from the share of the screen's height that the
part's bounding sphere takes, times 90 / the camera's field of view (its LODDistanceFactor: 3 in the overview's 30
degrees, 2.25 in the hero view's 40; measured, PIE). A part's sizes are set from how tall a whole unit (UNIT_H) stands
on the screen in the overview, so that all the parts of a figure change at the same distance, however small they are:
    units      LOD 1 below UNIT[0] of the screen's height (2.5 cm cubes), LOD 2 below UNIT[1] (5 cm cubes).
               0.09 / 0.04: LOD 1 from 70 m in the overview (zoom 0.27; its usual zoom 0.32 is 91 m) and 39 m in the
               hero view, LOD 2 from 158 m (zoom 0.45) and 88 m. The hero and whoever stands near him: LOD 0.
    the king   KING_SHARE: half those sizes (there is one of him, and he is looked at)
    buildings  LOD 1 where a unit beside it would be below BUILDING[0] of the screen's height (0.02: 317 m, zoom 0.67)
Importing a mesh again drops its levels: import_king.py runs this for the parts it imported; after import_assets.py
of a building run it by hand (ONLY=[...]).
"""
import json
import os

import unreal

ROOT = os.path.abspath(unreal.Paths.project_dir())
SRC = os.path.join(ROOT, "SourceArt", "Meshes", "LOD")
TMP = "/Game/Voxel/LODTmp"
FOLDERS = ["/Game/Voxel/King", "/Game/Voxel/Troops/Swordsman", "/Game/Voxel/Troops/Archer", "/Game/Voxel/Troops/Spy",
           "/Game/Voxel/Troops/Builder", "/Game/Voxel/Meshes"]
ONLY = globals().get("ONLY")
UNIT = globals().get("UNIT") or [0.09, 0.04]            # a unit's height as a share of the screen's (overview), below which LOD 1 / LOD 2 is drawn
KING_SHARE = globals().get("KING_SHARE") or [0.045, 0.02]     # ... King David's parts (SM_King*)
BUILDING = globals().get("BUILDING") or [0.02]          # the same, for a unit standing beside the building
UNIT_H = 175.0
LENS = 90.0 / 30.0                                      # the engine's LODDistanceFactor in the overview (90 / its field of view)

eal = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
sms = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)


def lod_pipeline():
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


def find(name):
    for folder in FOLDERS:
        if eal.does_asset_exist(folder + "/" + name):
            return eal.load_asset(folder + "/" + name)
    return None


def slot_names(sm):
    return [str(m.get_editor_property("material_slot_name")) for m in sm.get_editor_property("static_materials")]


def give_lods(name, entry):
    dst = find(name)
    if not dst:
        return "%s: no such mesh" % name, 0, 0
    if sms.get_lod_count(dst) > 1:
        sms.remove_lods(dst)
    own = dst.get_editor_property("static_materials")
    own_names = slot_names(dst)
    by_slot = {n: m.get_editor_property("material_interface") for n, m in zip(own_names, own)}
    share = (KING_SHARE if name.startswith("SM_King") else UNIT) if entry.get("set") == "units" else BUILDING
    radius = dst.get_bounds().sphere_radius
    sizes, notes, index = [1.0], [], 0
    for lv in entry["levels"]:
        if lv["level"] > len(share):
            continue
        path = os.path.join(SRC, lv["file"])
        if not os.path.exists(path):
            notes.append("no " + lv["file"])
            continue
        task = unreal.AssetImportTask()
        task.filename = path
        task.destination_path = TMP
        task.automated = True
        task.replace_existing = True
        task.save = False
        task.options = lod_pipeline()
        tools.import_asset_tasks([task])
        src = eal.load_asset(TMP + "/" + os.path.splitext(lv["file"])[0])
        if not src:
            notes.append("import failed: " + lv["file"])
            continue
        # the level's slots carry the mesh's own materials, so that the copy finds them among the mesh's slots
        mats = []
        for m in src.get_editor_property("static_materials"):
            slot = str(m.get_editor_property("material_slot_name"))
            mats.append(unreal.StaticMaterial(material_interface=by_slot.get(slot), material_slot_name=m.get_editor_property("material_slot_name"),
                                              uv_channel_data=m.get_editor_property("uv_channel_data")))
            if slot not in by_slot:
                notes.append("slot %s is not one of the mesh's" % slot)
        src.set_editor_property("static_materials", mats)
        want = slot_names(src)
        index = sms.set_lod_from_static_mesh(dst, index + 1, src, 0, True)
        if index < 0:
            notes.append("LOD from %s failed" % lv["file"])
            break
        for section, slot in enumerate(want):                     # each section on the slot of its name
            if slot in own_names and sms.get_lod_material_slot(dst, index, section) != own_names.index(slot):
                sms.set_lod_material_slot(dst, own_names.index(slot), index, section)
        size = LENS * 2.0 * radius / UNIT_H * share[lv["level"] - 1]
        sizes.append(size if len(sizes) == 1 else min(0.95 * sizes[-1], size))
    if slot_names(dst) != own_names:
        notes.append("SLOTS CHANGED: %s -> %s" % (own_names, slot_names(dst)))
    if len(sizes) > 1:
        sizes[0] = max(1.0, 2.0 * sizes[1])
        sms.set_lod_screen_sizes(dst, sizes)
    eal.save_loaded_asset(dst, False)
    n = sms.get_lod_count(dst)
    tris = [dst.get_num_triangles(i) for i in range(n)]
    line = "%s: %s triangles at screen sizes %s (radius %.0f cm)%s" % (
        name, " / ".join(str(t) for t in tris), " / ".join("%.4f" % s for s in sizes), radius, ("  !! " + "; ".join(notes)) if notes else "")
    return line, tris[0], tris


with open(os.path.join(SRC, "lods.json")) as fh:
    book = json.load(fh)
out, totals, bad = [], {}, 0
names = [n for n in book if not ONLY or n in ONLY]
with unreal.ScopedSlowTask(len(names), "LODs") as slow:
    slow.make_dialog(False)
    for name in names:
        slow.enter_progress_frame(1)
        line, _, tris = give_lods(name, book[name])
        out.append(line)
        bad += "!!" in line or tris == 0
        if tris:
            key = name.split("_")[1] if book[name].get("set") == "units" else "buildings"
            t = totals.setdefault(key, [0, 0, 0])
            for i in range(3):
                t[i] += tris[min(i, len(tris) - 1)]
if eal.does_directory_exist(TMP):
    eal.delete_directory(TMP)
print("voxel LODs:\n" + "\n".join(out))
print("voxel LODs, triangles at LOD 0 / 1 / 2: " + "; ".join("%s %d / %d / %d" % (k, v[0], v[1], v[2]) for k, v in totals.items()))
print("voxel LODs: %d meshes, %d with problems" % (len(names), bad))
