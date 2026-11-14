"""Build one building from script: mesh -> .blend, glTF for Unreal, metadata, preview renders.

    /Applications/Blender.app/Contents/MacOS/Blender -b -P Tools/blender/build_building.py -- castle [options]

    --no-render          skip the preview renders
    --zooms 0.5,0,1      game zoom levels to render (0 = zoomed in, 1 = zoomed out; default 0.5,0.12,1)
    --team r,g,b         preview team colour (linear; default the player's blue)
    --yaw deg            turn the building in the preview, as the level may place it

Writes
    SourceArt/Buildings/blender/<name>.blend     the model, with preview materials, the game camera and sun
    SourceArt/Buildings/<name>.gltf + .bin       what Unreal imports (Tools/import_buildings.py)
    SourceArt/Buildings/<name>.json              footprint, collision boxes, sockets, bounds, triangle count
    Saved/BuildingPreview/<name>_z<zoom>.png     renders from the game camera (quick look only: judge in engine)
The building modules are Tools/blender/bld_<name>.py: each has build(kit) and NAME / MESH.
"""
import importlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ROOT, "SourceArt", "Buildings")
PREVIEW = os.path.join(ROOT, "Saved", "BuildingPreview")

import bpy  # noqa: E402

import bldkit as K  # noqa: E402


def opt(args, name, default):
    return args[args.index(name) + 1] if name in args else default


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    name = args[0]
    mod = importlib.import_module("bld_" + name)
    zooms = [float(z) for z in opt(args, "--zooms", "0.5,0.12,1").split(",")]
    team = tuple(float(v) for v in opt(args, "--team", "0.05,0.22,0.80").split(","))
    yaw = float(opt(args, "--yaw", "0"))

    scene = K.reset_scene()
    kit = K.Kit(mod.MESH, seed=getattr(mod, "SEED", 1))
    mod.build(kit)
    ob = kit.build_object(team)
    tris, lo, hi = kit.stats()
    meta = {
        "name": name, "mesh": mod.MESH, "triangles": tris,
        "bounds": {"min": [round(v, 1) for v in lo], "max": [round(v, 1) for v in hi]},
        "colliders": kit.colliders, "sockets": {k: [round(c, 1) for c in v] for k, v in kit.sockets.items()},
        "footprint": getattr(mod, "FOOTPRINT", None), "ring_radius": getattr(mod, "RING_RADIUS", None),
        "slots": sorted(set(f[0] for f in kit.faces)),
    }
    os.makedirs(os.path.join(OUT, "blender"), exist_ok=True)
    with open(os.path.join(OUT, name + ".json"), "w") as f:
        json.dump(meta, f, indent=1)
    K.export_gltf(ob, os.path.join(OUT, name + ".gltf"))

    focus = getattr(mod, "PREVIEW_FOCUS", (0.0, 0.0, 0.0))
    K.setup_preview(scene, focus=focus, zoom=zooms[0])
    for i, p in enumerate(getattr(mod, "PREVIEW_FIGURES", [(-700, 150), (-760, 260)])):
        K.troop_standin(p, team)
    if yaw:
        import math
        ob.rotation_euler[2] = -math.radians(yaw)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "blender", name + ".blend"), compress=True)
    print("saved %s: %d triangles, bounds %s .. %s, slots %d" % (name, tris, meta["bounds"]["min"], meta["bounds"]["max"], len(meta["slots"])))
    if "--no-render" not in args:
        os.makedirs(PREVIEW, exist_ok=True)
        for z in zooms:
            K.setup_preview(scene, focus=focus, zoom=z)
            K.render(scene, os.path.join(PREVIEW, "%s_z%s.png" % (name, ("%.2f" % z).replace(".", ""))))


main()
