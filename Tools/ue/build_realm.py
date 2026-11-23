"""Builds /Game/Maps/L_Realm from SourceArt/realm.json (Tools/blender/realm_layout.py + assets/realm_terrain.py): the
battle map of References/Remake/battlefield.png, with the town's light and look (run inside the editor, not during PIE):

    python3 Tools/ue_py.py Tools/ue/build_realm.py          (sh Tools/realm_rebuild.sh does everything)

Import first (editor open): the ground tiles in SourceArt/Meshes/realm_tiles.json, SM_RealmWater, SM_RealmSea,
SM_RealmBackdrop, SM_RealmBarrier.

What the game reads from the level (Source/SovereignRealms), on top of what build_town.py lists (Ground, Water, Lookout, ...):
  tags Selectable, Name:<kind>, Team:0|1|Neutral   every building: the player's (0), the enemy's (1), the two contested
                      gold mines and the bridges (Neutral). The same list is in realm.json, "teams".
  tag TeamStart:0 / TeamStart:1    a TargetPoint in front of each castle (the PlayerStart stands on TeamStart:0)
  tag Rally:0 / Rally:1            a TargetPoint where each side's first troops stand (realm_layout.RALLY0 / RALLY1). No barracks
                      or archery range is placed: they are built in the game. Each side has two gold mines.
  tag Barrier         SM_RealmBarrier: hidden walls that block pawns and nothing else (no trace, no camera, no arrow):
                      the river, the sea, the cliff's rim, the island's rocks. The path grid's capsule test sees them.
  tag Backdrop        SM_RealmBackdrop: the mountains and woods beyond the edge (no collision). (The woods on the
                      mountain, the highland and the ridge are the forest's own trees now, not SM_RealmWoods.)
  actor Forest        an AVLForest (Source/SovereignRealms/VLForest.h): every tree (trunk + crown) and all the undergrowth as
                      instanced components, one per mesh, not an actor each. AVLForest::ClearTrees takes trees away
                      for a building. The trees' meshes need their LOD 1 (Tools/ue/tree_lods.py).
The enemy's cloth (banners, flags) is MI_Vox_cloth_Enemy: red (Tools/ue/build_special_materials.py, PARTS=["sway"]).
"""
import json
import math
import os

import unreal

ROOT = os.path.abspath(unreal.Paths.project_dir())
L = {"NO_MAIN": True, "__name__": "build_level", "LOOK": globals().get("LOOK") or {}}
exec(open(os.path.join(ROOT, "Tools", "ue", "build_level.py")).read(), L)
L["MAP"] = "/Game/Maps/L_Realm"
L["SELECTABLE"].update({"SM_Dock": "Dock"})
SRC = L["SRC"]
vec, spawn, place, lamps, meta = L["vec"], L["spawn"], L["place"], L["lamps"], L["meta"]
eas, eal, les = L["eas"], L["eal"], L["les"]
CR, CC = unreal.CollisionResponseType, unreal.CollisionChannel

# chimney tops of the buildings (metres, the mesh's own space), for the smoke
SMOKE = {"SM_BarracksYard": [(-6.7, 6.3, 7.95)]}


def water(name):
    a = place(name, 0, 0, 0, folder="Terrain")
    if a is None:
        return None
    a.tags = [unreal.Name("Water")]
    c = a.static_mesh_component
    c.set_editor_property("use_default_collision", False)     # else the mesh asset's BlockAll comes back when the level is loaded
    c.set_collision_enabled(unreal.CollisionEnabled.QUERY_ONLY)
    c.set_collision_object_type(CC.ECC_WORLD_DYNAMIC)
    c.set_collision_response_to_all_channels(CR.ECR_IGNORE)
    c.set_editor_property("cast_shadow", False)
    return a


def backdrop():
    a = place("SM_RealmBackdrop", 0, 0, 0, folder="Terrain")
    if a is None:
        return None
    a.tags = [unreal.Name("Backdrop")]
    c = a.static_mesh_component
    c.set_editor_property("use_default_collision", False)     # else the mesh asset's BlockAll comes back when the level is loaded
    c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    c.set_editor_property("cast_shadow", False)
    c.set_editor_property("affect_distance_field_lighting", False)
    c.set_editor_property("affect_dynamic_indirect_lighting", False)
    return a


def barrier():
    """The hidden walls: they block pawns (and the path grid's capsule test, which asks for what blocks a pawn) and
    nothing else, so clicks, arrows, the camera and the grid's floor traces go through them."""
    a = place("SM_RealmBarrier", 0, 0, 0, folder="Bounds")
    if a is None:
        return None
    a.tags = [unreal.Name("Barrier")]
    a.set_actor_hidden_in_game(True)
    c = a.static_mesh_component
    c.set_editor_property("use_default_collision", False)     # else the mesh asset's BlockAll comes back when the level is loaded
    c.set_collision_enabled(unreal.CollisionEnabled.QUERY_AND_PHYSICS)
    c.set_collision_object_type(CC.ECC_WORLD_STATIC)
    c.set_collision_response_to_all_channels(CR.ECR_IGNORE)
    c.set_collision_response_to_channel(CC.ECC_PAWN, CR.ECR_BLOCK)
    c.set_editor_property("cast_shadow", False)
    c.set_editor_property("affect_distance_field_lighting", False)
    c.set_editor_property("affect_dynamic_indirect_lighting", False)
    c.set_visibility(False)
    return a


# the forest's instanced kinds: what is culled far from the view (metres; they fade out over the last 15 %; the trees
# and the bushes never are). The overview is 190 m from what it looks at halfway out, 345 m at 0.7 and 680 m all the way
# out, and the top of the view is further than that: at 230 / 260 m (as it was) the grass and the flowers went as soon
# as one pulled back a little. They are cheap that far away: Tools/ue/plant_lods.py gives them a LOD 1 of an eighth of
# the triangles. The farms' crops, sheep and vegetable beds are single actors with no cull distance: always drawn.
CULL = {"SM_GrassTuft": 400.0, "SM_Flowers": 440.0, "SM_LilyPad": 500.0}
NO_SHADOW = ("SM_GrassTuft", "SM_Flowers", "SM_LilyPad")


def in_forest(it):
    return it["mesh"].startswith("SM_Tree") or it.get("group") == "plants"


def forest(layout):
    """Every tree and all the undergrowth as instanced components of one AVLForest actor."""
    kinds = {}
    for it in layout["instances"]:
        if in_forest(it):
            sc = it.get("scale", 1.0)
            kinds.setdefault(it["mesh"], []).append(unreal.Transform(location=vec(*it["pos"]), rotation=unreal.Rotator(roll=0, pitch=0, yaw=-it.get("yaw", 0.0)),
                                                                     scale=unreal.Vector(sc, sc, sc)))
    a = spawn(unreal.VLForest, unreal.Vector(0, 0, 0), None, "Forest", "Realm")
    reach = layout.get("trees", {}).get("clear", {})
    n = {"trees": 0, "plants": 0}
    for name in sorted(kinds):
        sm = L["mesh"](name)
        if sm is None:
            continue
        cull = next((v for k, v in CULL.items() if name.startswith(k)), 0.0) * 100.0
        if name.startswith("SM_Tree"):
            trunk = name.endswith("_Trunk")
            r = reach.get(name.split("_")[2], 1.5) * 100.0
            c = a.add_kind(sm, kinds[name], unreal.VLForestPart.TRUNK if trunk else unreal.VLForestPart.CROWN, r, trunk, True, cull)
            n["trees"] += len(kinds[name]) if trunk else 0
        else:
            c = a.add_kind(sm, kinds[name], unreal.VLForestPart.UNDERGROWTH, 0.0, False, not name.startswith(NO_SHADOW), cull)
            n["plants"] += len(kinds[name])
            if c and name.startswith(("SM_GrassTuft", "SM_Flowers")):
                c.set_editor_property("world_position_offset_disable_distance", 6000)
    return a, n, len(kinds)


def far_shadows():
    """The overview pulls back to 680 m over this map: the sun's shadows must reach as far (the town's stop at 300 m)."""
    for a in eas.get_all_level_actors():
        if isinstance(a, unreal.DirectionalLight):
            a.get_component_by_class(unreal.DirectionalLightComponent).set_editor_property("dynamic_shadow_distance_movable_light", 110000.0)


def seabed(terrain):
    """One flat slab under the open sea (the voxel ground stops a few metres out from the cliffs)."""
    cube = eal.load_asset("/Engine/BasicShapes/Cube")
    a = eas.spawn_actor_from_object(cube, vec(0, 0, terrain["seabed"] - 0.55), unreal.Rotator(0, 0, 0))
    a.set_actor_scale3d(unreal.Vector(1100.0, 1100.0, 1.0))
    a.set_folder_path("Terrain")
    a.set_actor_label("Seabed")
    c = a.static_mesh_component
    mi = eal.load_asset("/Game/Voxel/Materials/MI_Vox_gravel")
    if mi:
        c.set_material(0, mi)
    c.set_editor_property("cast_shadow", False)


def marker(tag, pos, yaw):
    a = spawn(unreal.TargetPoint, vec(pos[0], pos[1], pos[2] + 0.1), unreal.Rotator(roll=0, pitch=0, yaw=-yaw), tag.replace(":", "_"), "Markers")
    a.tags = [unreal.Name(tag)]
    return a


def main():
    if globals().get("LIGHT_ONLY"):
        L["relight"]()
        return
    layout = json.load(open(os.path.join(SRC, "realm.json")))
    L["load_or_new_level"]()
    L["lighting"]()
    far_shadows()
    L["postcard"](layout)
    for t in json.load(open(os.path.join(SRC, "Meshes", "realm_tiles.json"))):
        a = place(t, 0, 0, 0, folder="Terrain")
        if a:
            a.tags = [unreal.Name("Ground")]
    water("SM_RealmWater")
    water("SM_RealmSea")
    seabed(layout["terrain"])
    backdrop()
    _forest, in_wood, wood_kinds = forest(layout)
    has_barrier = barrier() is not None
    red = eal.load_asset("/Game/Voxel/Materials/MI_Vox_cloth_Enemy") if eal.does_asset_exist("/Game/Voxel/Materials/MI_Vox_cloth_Enemy") else None
    placed, skipped, nlamps, teams, nred = 0, {}, 0, {}, 0
    with unreal.ScopedSlowTask(len(layout["instances"]), "Placing the realm") as task:
        task.make_dialog(False)
        for it in layout["instances"]:
            task.enter_progress_frame(1)
            if in_forest(it):
                continue
            x, y, z = it["pos"]
            sc = it.get("scale3") or [it.get("scale", 1.0)] * 3
            a = place(it["mesh"], x, y, z, it.get("yaw", 0.0), sc, "Realm/" + it.get("group", "village").capitalize())
            if a is None:
                skipped[it["mesh"]] = skipped.get(it["mesh"], 0) + 1
                continue
            placed += 1
            tags = list(a.tags)
            for t in it.get("tags", []):
                tags.append(unreal.Name(t))
            if "team" in it:
                tags.append(unreal.Name("Team:%s" % it["team"]))
                teams[str(it["team"])] = teams.get(str(it["team"]), 0) + 1
                if it["team"] == 1 and red:
                    c = a.static_mesh_component
                    for i, slot in enumerate(c.get_material_slot_names()):
                        if "cloth" in str(slot).lower():
                            c.set_material(i, red)
                            nred += 1
            lk = meta(it["mesh"]).get("lookout")
            if lk:
                s = it.get("scale", 1.0)
                tags.append(unreal.Name("Lookout:%.3f;%.3f;%.3f;%.3f;%.3f" % ((lk["floor_z"] * s,) + tuple(v * s for v in lk["free"]))))
            a.tags = tags
            nlamps += lamps(it["mesh"], x, y, z, it.get("yaw", 0.0), sc, "Lamps")
    for m in layout.get("markers", []):
        marker(m["tag"], m["pos"], m.get("yaw", 0.0))
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
    print("realm built: forest %d trees + %d plants in %d instanced kinds; %d placed, %d lamps, %d chimneys, %d mote swarms, teams %s, %d markers, barrier %s, %d red cloth slots, missing: %s" % (
        in_wood["trees"], in_wood["plants"], wood_kinds, placed, nlamps, nsmoke, nmotes, teams, len(layout.get("markers", [])), "yes" if has_barrier else "NO", nred,
        ", ".join("%s x%d" % kv for kv in sorted(skipped.items())) or "none"))


main()
