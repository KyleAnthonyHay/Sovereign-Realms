"""Builds /Game/Maps/L_Flatlands from SourceArt/flatlands.json (Tools/blender/assets/flatlands.py): every building
side by side on a flat field, with its name in front, the same light and look as the village (run inside the editor):

    python3 Tools/ue_py.py Tools/ue/build_flatlands.py

The ground tiles SM_Flat_* and the pond's water SM_FlatPond must be imported first:
    python3 Tools/ue_py.py -c "PARTS=['meshes']; ONLY=[...the names in SourceArt/Meshes/flat_tiles.json..., 'SM_FlatPond']; exec(open(r'<abs>/Tools/ue/import_assets.py').read())"
The line-up's figures are the units' own parts (/Game/Voxel/King, /Game/Voxel/Troops/<Kind>: import_king.py), each
placed at its pivot, static, in the pose it was modelled in.
"""
import json
import math
import os

import unreal

ROOT = os.path.abspath(unreal.Paths.project_dir())
L = {"NO_MAIN": True, "__name__": "build_level"}
exec(open(os.path.join(ROOT, "Tools", "ue", "build_level.py")).read(), L)
L["MAP"] = "/Game/Maps/L_Flatlands"
L["SELECTABLE"].update({"SM_Treasury": "Treasury", "SM_Granary": "Granary"})
SRC = L["SRC"]
vec, spawn, place, lamps = L["vec"], L["spawn"], L["place"], L["lamps"]
eas, eal, les = L["eas"], L["eal"], L["les"]


def camera(plan):
    cam = plan["camera"]
    a, e = math.radians(cam["az"]), math.radians(cam["el"])
    tx, ty, tz = cam["target"]
    d = cam["dist"]
    # the camera stands back from the target against its looking direction, Blender (-sin a, cos a)
    px = tx + math.sin(a) * math.cos(e) * d
    py = ty - math.cos(a) * math.cos(e) * d
    pz = tz + math.sin(e) * d
    yaw = math.degrees(math.atan2(-math.cos(a), -math.sin(a)))
    actor = spawn(unreal.CameraActor, vec(px, py, pz), unreal.Rotator(roll=0, pitch=-cam["el"], yaw=yaw), "PostcardCamera", "Cameras")
    actor.tags = [unreal.Name("Postcard")]
    cc = actor.get_component_by_class(unreal.CameraComponent)
    cc.set_editor_property("field_of_view", cam["hfov"])
    cc.set_editor_property("aspect_ratio", cam["width"] / float(cam["height"]))
    cc.set_editor_property("constrain_aspect_ratio", True)
    sp = plan["spawn"]
    spawn(unreal.PlayerStart, vec(sp["pos"][0], sp["pos"][1], sp["pos"][2] + 1.2), unreal.Rotator(roll=0, pitch=0, yaw=-sp["yaw"]), "KingStart", "Cameras")


def label(lb):
    """The building's name, standing at the roadside, readable from the road (it faces -Y, Unreal +Y)."""
    x, y, z = lb["pos"]
    a = spawn(unreal.TextRenderActor, vec(x, y, z + 0.45), unreal.Rotator(roll=0, pitch=50.0, yaw=90.0), "Label " + lb["text"], "Labels")
    t = a.text_render
    t.set_editor_property("text", lb["text"])
    t.set_editor_property("world_size", 120.0)
    t.set_editor_property("horizontal_alignment", unreal.HorizTextAligment.EHTA_CENTER)
    t.set_editor_property("vertical_alignment", unreal.VerticalTextAligment.EVRTA_TEXT_BOTTOM)
    t.set_editor_property("text_render_color", unreal.Color(r=255, g=214, b=110, a=255))
    t.set_editor_property("cast_shadow", False)
    # a little stone plinth under it
    plinth = place("SM_Rock_B", x, y + 0.2, 0.0, 0.0, (1.0, 0.6, 0.35), folder="Labels")
    if plinth:
        plinth.static_mesh_component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)


def water(name):
    """The pond's water: no collision but queries (as the realm's river: tag Water)."""
    a = place(name, 0, 0, 0, folder="Ground")
    if a is None:
        return None
    a.tags = [unreal.Name("Water")]
    c = a.static_mesh_component
    c.set_editor_property("use_default_collision", False)
    c.set_collision_enabled(unreal.CollisionEnabled.QUERY_ONLY)
    c.set_collision_object_type(unreal.CollisionChannel.ECC_WORLD_DYNAMIC)
    c.set_collision_response_to_all_channels(unreal.CollisionResponseType.ECR_IGNORE)
    c.set_editor_property("cast_shadow", False)
    return a


def figure(fg):
    """One figure of the line-up: each of its parts (its mesh's origin is its joint) at its pivot, in the pose it was
    modelled in, facing -Y (Unreal +Y: toward the road and the camera). No collision. A small name in front."""
    x, y, z = fg["pos"]
    n = 0
    for pt in fg["parts"]:
        path = fg["folder"] + "/" + pt["mesh"]
        sm = eal.load_asset(path) if eal.does_asset_exist(path) else None
        if sm is None:
            continue
        px, py, pz = pt["pivot"]
        a = eas.spawn_actor_from_object(sm, vec(x + px, y + py, z + pz), unreal.Rotator(roll=0, pitch=0, yaw=0))
        a.set_folder_path("Lineup/" + fg["name"])
        c = a.static_mesh_component
        c.set_mobility(unreal.ComponentMobility.STATIC)
        c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        n += 1
    t = spawn(unreal.TextRenderActor, vec(x, y - 1.1, z + 0.05), unreal.Rotator(roll=0, pitch=60.0, yaw=90.0), "Name " + fg["name"], "Lineup")
    tr = t.text_render
    tr.set_editor_property("text", fg["name"])
    tr.set_editor_property("world_size", 26.0)
    tr.set_editor_property("horizontal_alignment", unreal.HorizTextAligment.EHTA_CENTER)
    tr.set_editor_property("vertical_alignment", unreal.VerticalTextAligment.EVRTA_TEXT_BOTTOM)
    tr.set_editor_property("text_render_color", unreal.Color(r=255, g=226, b=150, a=255))
    tr.set_editor_property("cast_shadow", False)
    return n


def bounds_walls(g):
    cube = eal.load_asset("/Engine/BasicShapes/Cube")
    hw, hd, cy = g["w"] / 2.0 - 1.0, g["d"] / 2.0 - 1.0, g["cy"]
    for (x, y, sx, sy) in ((hw, cy, 1, 2 * hd + 2), (-hw, cy, 1, 2 * hd + 2), (0, cy + hd, 2 * hw + 2, 1), (0, cy - hd, 2 * hw + 2, 1)):
        a = eas.spawn_actor_from_object(cube, vec(x, y, 10.0), unreal.Rotator(0, 0, 0))
        a.set_actor_scale3d(unreal.Vector(sx, sy, 40.0))
        a.set_folder_path("Bounds")
        a.set_actor_hidden_in_game(True)
        # a hidden wall stops pawns only: clicks, arrows and the camera pass (UVLGrid::ApplyLevelCollision sets the same at play)
        a.tags = [unreal.Name("Barrier")]
        a.static_mesh_component.set_editor_property("use_default_collision", False)
        a.static_mesh_component.set_collision_response_to_all_channels(unreal.CollisionResponseType.ECR_IGNORE)
        a.static_mesh_component.set_collision_response_to_channel(unreal.CollisionChannel.ECC_PAWN, unreal.CollisionResponseType.ECR_BLOCK)
        a.static_mesh_component.set_editor_property("cast_shadow", False)
        a.static_mesh_component.set_visibility(False)


def main():
    plan = json.load(open(os.path.join(SRC, "flatlands.json")))
    L["load_or_new_level"]()
    L["lighting"]()
    camera(plan)
    for t in json.load(open(os.path.join(SRC, "Meshes", "flat_tiles.json"))):
        place(t, 0, 0, 0, folder="Ground")
    if plan.get("water"):
        water(plan["water"]["mesh"])
    placed, nl, missing = 0, 0, set()
    for it in plan["instances"]:
        x, y, z = it["pos"]
        sc = [it.get("scale", 1.0)] * 3
        a = place(it["mesh"], x, y, z, it.get("yaw", 0.0), sc, "Field/" + it.get("group", "village").capitalize())
        if a is None:
            missing.add(it["mesh"])
            continue
        placed += 1
        nl += lamps(it["mesh"], x, y, z, it.get("yaw", 0.0), sc, "Lamps")
    for lb in plan["labels"]:
        label(lb)
    nf = sum(figure(fg) for fg in plan.get("figures", []))
    bounds_walls(plan["ground"])
    les.save_current_level()
    print("flatlands built: %d placed, %d lamps, %d labels, %d figures (%d parts), missing: %s" % (
        placed, nl, len(plan["labels"]), len(plan.get("figures", [])), nf, ", ".join(sorted(missing)) or "none"))


main()
