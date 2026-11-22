"""Builds /Game/Maps/L_RealmV2 from SourceArt/realmv2.json (Tools/blender/realmv2_layout.py +
assets/realmv2_terrain.py): the third battle map, with the town's light and look (run inside the editor, not during
PIE). Written from the second battle map's builder; the level is made the same way and carries the same contract:

    python3 Tools/ue_py.py Tools/ue/build_realmv2.py          (sh Tools/realmv2_rebuild.sh does everything)

Import first (editor open): the ground tiles in SourceArt/Meshes/realmv2_tiles.json, SM_RealmV2Water,
SM_RealmV2Sea, SM_RealmV2Barrier, SM_Ruin_*, SM_Port_*.

  tags Selectable, Name:<kind>, Team:0|1|Neutral   every building: the player's (0), the enemy's (1); Neutral: the nine
                      bridges and the three far mines (north-west, centre-east, south-east)
  tag TeamStart:0 / TeamStart:1    a TargetPoint in front of each castle (the PlayerStart stands on TeamStart:0)
  tag Rally:0 / Rally:1            a TargetPoint on each side's main road, where its troops gather
  tags NorthCrossing, SouthCrossing, Ruins    a TargetPoint in each contested zone (terrain only: nothing captures them yet)
  tag Ground          every ground tile (the path grid stands on them)
  tag Water           SM_RealmV2Water, SM_RealmV2Sea: collision only for the path grid's own queries
  tag Barrier         SM_RealmV2Barrier: hidden walls that block pawns and nothing else: the rivers' banks, the creek,
                      the rims of the plateau, the terraces, the bluffs and the towers' hills
  actor Forest        an AVLForest: every tree and all the undergrowth as instanced components
  actor Sky           an AVLSky: the clouds round the mountain and beyond the edges, the flocks of birds
The enemy's cloth (banners, flags) is MI_Vox_cloth_Enemy.
"""
import json
import math
import os

import unreal

ROOT = os.path.abspath(unreal.Paths.project_dir())
L = {"NO_MAIN": True, "__name__": "build_level", "LOOK": globals().get("LOOK") or {}}
exec(open(os.path.join(ROOT, "Tools", "ue", "build_level.py")).read(), L)
L["MAP"] = "/Game/Maps/L_RealmV2"
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
    a = place("SM_RealmV2Backdrop", 0, 0, 0, folder="Terrain")
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
    a = place("SM_RealmV2Barrier", 0, 0, 0, folder="Bounds")
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


def sky_material(name, tint):
    """An unlit material for the sky's cubes (M_VoxSky: a colour, a little darker underneath) and an instance of it.
    Unlit, so a cloud in the mountain's shadow stays white and a bird stays a dark mark against the sky."""
    mel = unreal.MaterialEditingLibrary
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    base = "/Game/Voxel/Materials/M_VoxSky"
    if eal.does_asset_exist(base):
        mat = eal.load_asset(base)
    else:
        mat = tools.create_asset("M_VoxSky", "/Game/Voxel/Materials", unreal.Material, unreal.MaterialFactoryNew())
        mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
        col = mel.create_material_expression(mat, unreal.MaterialExpressionVectorParameter, -700, 0)
        col.set_editor_property("parameter_name", "Tint")
        col.set_editor_property("default_value", unreal.LinearColor(1, 1, 1, 1))
        nrm = mel.create_material_expression(mat, unreal.MaterialExpressionVertexNormalWS, -900, 250)
        msk = mel.create_material_expression(mat, unreal.MaterialExpressionComponentMask, -700, 250)
        msk.set_editor_property("r", False); msk.set_editor_property("g", False); msk.set_editor_property("b", True); msk.set_editor_property("a", False)
        mad = mel.create_material_expression(mat, unreal.MaterialExpressionMultiply, -500, 250)
        mad.set_editor_property("const_b", 0.14)
        add = mel.create_material_expression(mat, unreal.MaterialExpressionAdd, -350, 250)
        add.set_editor_property("const_b", 0.86)
        out = mel.create_material_expression(mat, unreal.MaterialExpressionMultiply, -200, 0)
        mel.connect_material_expressions(nrm, "", msk, "")
        mel.connect_material_expressions(msk, "", mad, "A")
        mel.connect_material_expressions(mad, "", add, "A")
        mel.connect_material_expressions(col, "", out, "A")
        mel.connect_material_expressions(add, "", out, "B")
        mel.connect_material_property(out, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
        mel.set_material_usage(mat, unreal.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES)
        mel.recompile_material(mat)
        eal.save_loaded_asset(mat, False)
    path = "/Game/Voxel/Materials/" + name
    mi = eal.load_asset(path) if eal.does_asset_exist(path) else tools.create_asset(name, "/Game/Voxel/Materials", unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(mi, mat)
    mel.set_material_instance_vector_parameter_value(mi, "Tint", unreal.LinearColor(tint[0], tint[1], tint[2], 1.0))
    mel.update_material_instance(mi)
    eal.save_loaded_asset(mi, False)
    return mi


def sky(layout):
    """The clouds and the birds (AVLSky): where the plan puts them (realmv2_layout._sky)."""
    sk = layout.get("sky")
    if not sk:
        return 0, 0
    a = spawn(unreal.VLSky, unreal.Vector(0, 0, 0), None, "Sky", "Ambience")
    a.set_editor_property("cloud_centres", [vec(c[0], c[1], c[2]) for c in sk["clouds"]])
    a.set_editor_property("cloud_sizes", [unreal.Vector(c[3] * 100.0, c[4] * 100.0, c[5] * 100.0) for c in sk["clouds"]])
    a.set_editor_property("flock_centres", [vec(f[0], f[1], f[2]) for f in sk["flocks"]])
    a.set_editor_property("flock_radii", [f[3] * 100.0 for f in sk["flocks"]])
    a.set_editor_property("birds_per_flock", int(sk.get("birds_per_flock", 6)))
    a.set_editor_property("cloud_material", sky_material("MI_Vox_cloud", (0.93, 0.95, 0.98)))
    a.set_editor_property("bird_material", sky_material("MI_Vox_bird", (0.035, 0.033, 0.03)))
    return len(sk["clouds"]), len(sk["flocks"]) * int(sk.get("birds_per_flock", 6))


def seabed(terrain):
    """One flat slab under the open sea (the voxel ground stops a few metres out from the cliffs)."""
    cube = eal.load_asset("/Engine/BasicShapes/Cube")
    a = eas.spawn_actor_from_object(cube, vec(0, 0, terrain["seabed"] - 0.55), unreal.Rotator(0, 0, 0))
    a.set_actor_scale3d(unreal.Vector(1400.0, 1400.0, 1.0))
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
    layout = json.load(open(os.path.join(SRC, "realmv2.json")))
    L["load_or_new_level"]()
    L["lighting"]()
    far_shadows()
    L["postcard"](layout)
    for t in json.load(open(os.path.join(SRC, "Meshes", "realmv2_tiles.json"))):
        a = place(t, 0, 0, 0, folder="Terrain")
        if a:
            a.tags = [unreal.Name("Ground")]
    water("SM_RealmV2Water")
    water("SM_RealmV2Sea")
    seabed(layout["terrain"])
    _forest, in_wood, wood_kinds = forest(layout)
    has_barrier = barrier() is not None
    red = eal.load_asset("/Game/Voxel/Materials/MI_Vox_cloth_Enemy") if eal.does_asset_exist("/Game/Voxel/Materials/MI_Vox_cloth_Enemy") else None
    placed, skipped, nlamps, teams, nred = 0, {}, 0, {}, 0
    with unreal.ScopedSlowTask(len(layout["instances"]), "Placing Realm v2") as task:
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
            if it.get("cloth") == 1 and red:                    # (the enemy port's ship: its sail and banners in red)
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
    nclouds, nbirds = sky(layout)
    les.save_current_level()
    print("realm v2 built: %d clouds, %d birds; forest %d trees + %d plants in %d instanced kinds; %d placed, %d lamps, %d chimneys, %d mote swarms, teams %s, %d markers, barrier %s, %d red cloth slots, missing: %s" % (
        nclouds, nbirds, in_wood["trees"], in_wood["plants"], wood_kinds, placed, nlamps, nsmoke, nmotes, teams, len(layout.get("markers", [])), "yes" if has_barrier else "NO", nred,
        ", ".join("%s x%d" % kv for kv in sorted(skipped.items())) or "none"))


main()
