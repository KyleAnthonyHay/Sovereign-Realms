"""Builds /Game/Maps/L_Town from SourceArt/town.json (Tools/blender/town_layout.py + assets/town_terrain.py): the island
town of References/Remake/town.png, with the same light and look as the village (run inside the editor, not during PIE):

    python3 Tools/ue_py.py Tools/ue/build_town.py

Import first (editor open): the ground tiles in SourceArt/Meshes/town_tiles.json, SM_TownWater, SM_TownSea, and the
town's own assets (SM_Windmill, SM_Windmill_Sails, SM_Dock, SM_Boat, SM_HayCart).

What the game reads from the level (Source/VoxelLab):
  tag Ground          the terrain tiles (the path grid stops looking for floors under them)
  tag Water           the water meshes: no collision for anyone, but the path grid asks them where water lies
  tag Spin            the windmill's sails (AVLGameMode turns them)
  tag Lookout:z;x0;y0;x1;y1   on the watch tower: its platform's floor height and free area (metres, the mesh's own
                      space, from SM_WatchTower.json), where garrisoned archers stand
  tags Selectable, Name:<name>   as in the village (the barracks and the archery range train troops)
"""
import json
import math
import os

import unreal

ROOT = os.path.abspath(unreal.Paths.project_dir())
L = {"NO_MAIN": True, "__name__": "build_level", "LOOK": globals().get("LOOK") or {}}
exec(open(os.path.join(ROOT, "Tools", "ue", "build_level.py")).read(), L)
L["MAP"] = "/Game/Maps/L_Town"
L["SELECTABLE"].update({"SM_Windmill": "Windmill", "SM_Dock": "Dock"})
SRC = L["SRC"]
vec, spawn, place, lamps, meta = L["vec"], L["spawn"], L["place"], L["lamps"], L["meta"]
eas, eal, les = L["eas"], L["eal"], L["les"]


# chimney tops of the town's own buildings (metres, the mesh's own space), for the smoke
SMOKE = {"SM_BarracksYard": [(-6.7, 6.3, 7.95)]}


def water(name):
    a = place(name, 0, 0, 0, folder="Terrain")
    if a is None:
        return None
    a.tags = [unreal.Name("Water")]
    c = a.static_mesh_component
    c.set_collision_enabled(unreal.CollisionEnabled.QUERY_ONLY)
    c.set_collision_object_type(unreal.CollisionChannel.ECC_WORLD_DYNAMIC)
    c.set_collision_response_to_all_channels(unreal.CollisionResponseType.ECR_IGNORE)
    c.set_editor_property("cast_shadow", False)
    return a


def seabed(terrain):
    """One flat slab under the open sea (the voxel ground stops a few metres out from the cliffs)."""
    cube = eal.load_asset("/Engine/BasicShapes/Cube")
    a = eas.spawn_actor_from_object(cube, vec(0, 0, terrain["seabed"] - 0.55), unreal.Rotator(0, 0, 0))
    a.set_actor_scale3d(unreal.Vector(2600.0 / 100.0 * 10, 2600.0 / 100.0 * 10, 1.0))
    a.set_folder_path("Terrain")
    a.set_actor_label("Seabed")
    c = a.static_mesh_component
    mi = eal.load_asset("/Game/Voxel/Materials/MI_Vox_gravel")
    if mi:
        c.set_material(0, mi)
    c.set_editor_property("cast_shadow", False)


def main():
    if globals().get("LIGHT_ONLY"):
        L["relight"]()
        return
    layout = json.load(open(os.path.join(SRC, "town.json")))
    L["load_or_new_level"]()
    L["lighting"]()
    L["postcard"](layout)
    for t in json.load(open(os.path.join(SRC, "Meshes", "town_tiles.json"))):
        a = place(t, 0, 0, 0, folder="Terrain")
        if a:
            a.tags = [unreal.Name("Ground")]
    water("SM_TownWater")
    water("SM_TownSea")
    seabed(layout["terrain"])
    placed, skipped, nlamps = 0, {}, 0
    with unreal.ScopedSlowTask(len(layout["instances"]), "Placing the town") as task:
        task.make_dialog(False)
        for it in layout["instances"]:
            task.enter_progress_frame(1)
            x, y, z = it["pos"]
            sc = it.get("scale3") or [it.get("scale", 1.0)] * 3
            a = place(it["mesh"], x, y, z, it.get("yaw", 0.0), sc, "Town/" + it.get("group", "village").capitalize())
            if a is None:
                skipped[it["mesh"]] = skipped.get(it["mesh"], 0) + 1
                continue
            placed += 1
            tags = list(a.tags)
            for t in it.get("tags", []):
                tags.append(unreal.Name(t))
                if t == "Spin":
                    a.static_mesh_component.set_mobility(unreal.ComponentMobility.MOVABLE)
            lk = meta(it["mesh"]).get("lookout")
            if lk:
                s = it.get("scale", 1.0)
                tags.append(unreal.Name("Lookout:%.3f;%.3f;%.3f;%.3f;%.3f" % ((lk["floor_z"] * s,) + tuple(v * s for v in lk["free"]))))
            a.tags = tags
            nlamps += lamps(it["mesh"], x, y, z, it.get("yaw", 0.0), sc, "Lamps")
    L["walls"](layout["terrain"]["half"] - 1.0)
    nsmoke, nmotes = L["ambience"](layout, L["LAMP_POINTS"])
    extra = []
    for it in layout["instances"]:
        for (lx, ly, lz) in SMOKE.get(it["mesh"], []):
            a = math.radians(it.get("yaw", 0.0))
            extra.append(vec(it["pos"][0] + lx * math.cos(a) - ly * math.sin(a), it["pos"][1] + lx * math.sin(a) + ly * math.cos(a), it["pos"][2] + lz))
    for amb in eas.get_all_level_actors():
        if isinstance(amb, unreal.VLAmbience):
            amb.set_editor_property("smoke_sources", list(amb.get_editor_property("smoke_sources")) + extra)
            nsmoke += len(extra)
    les.save_current_level()
    print("town built: %d placed, %d lamps, %d chimneys, %d mote swarms, missing: %s" % (
        placed, nlamps, nsmoke, nmotes, ", ".join("%s x%d" % kv for kv in sorted(skipped.items())) or "none"))


main()
