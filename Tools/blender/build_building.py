"""Build one building from script: meshes -> .blend, glTF for Unreal, metadata, preview renders.

    /Applications/Blender.app/Contents/MacOS/Blender -b -P Tools/blender/build_building.py -- castle [options]

    --state s[,s]        which meshes to build: complete, site, damaged, ruin, or all (default: all the module has)
    --no-render          skip the preview renders
    --zooms 0.5,0,1      game zoom levels to render the finished mesh at (0 = zoomed in, 1 = zoomed out; default 0.5,0.12,1)
    --team r,g,b         preview team colour (linear; default the player's blue)
    --yaw deg            turn the building in the preview, as the level may place it
    --level n[,n]        which levels to build (default: all the module has, LEVELS; level 1 is the plain names)
    --levels-only        render only the per-level previews (<name>_L<n>.png)
    --level-zoom z       game zoom of the per-level previews (default 0.9; aimed 40% up the level-1 building)

A building with levels (LEVELS = n in its module) also has SM_Bld_<Name>_L<k> and SM_Bld_<Name>_L<k>_Damaged for each
level k >= 2 (kit.level tells the module which); site and ruin are shared by every level.

A building has up to four meshes with one origin, orientation and footprint (bldkit.STATES): the finished one and,
for modules that list them in STATES, its construction site, its battle-damaged form and its ruin.

Writes
    SourceArt/Buildings/blender/<name>.blend          every state as an object, preview materials, game camera and sun
    SourceArt/Buildings/<MESH>.gltf + .bin            the finished mesh, what Unreal imports (Tools/import_buildings.py)
    SourceArt/Buildings/<MESH>_Site|_Damaged|_Ruin    the other states
    SourceArt/Buildings/<name>.json                   footprint, collision boxes, sockets, bounds, triangle count of the
                                                      finished mesh; "states": mesh, triangles, bounds, slots of the others
    Saved/BuildingPreview/<name>_z<zoom>.png          the finished mesh from the game camera (quick look only: judge in engine)
    Saved/BuildingPreview/<name>_<state>.png          every state from the tactical camera (pitch 54, far); the site is
                                                      shown round the finished mesh half risen out of the ground
The building modules are Tools/blender/bld_<name>.py: each has build(kit) or build(kit, state), NAME / MESH and
optionally STATES.
"""
import importlib
import json
import math
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


def level_mesh(mod, level, state):
    """SM_Bld_<Name>[_L<n>][_State]: level 1 keeps the plain names."""
    return mod.MESH + ("_L%d" % level if level > 1 else "") + K.STATE_SUFFIX[state]


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    name = args[0]
    mod = importlib.import_module("bld_" + name)
    zooms = [float(z) for z in opt(args, "--zooms", "0.5,0.12,1").split(",")]
    team = tuple(float(v) for v in opt(args, "--team", "0.05,0.22,0.80").split(","))
    yaw = float(opt(args, "--yaw", "0"))
    have = getattr(mod, "STATES", ("complete",))
    want = opt(args, "--state", "all")
    states = [s for s in have if want == "all" or s in want.split(",")]
    top_level = getattr(mod, "LEVELS", 1)
    want_lv = opt(args, "--level", "all")
    levels = [n for n in range(1, top_level + 1) if want_lv == "all" or str(n) in want_lv.split(",")]
    # level 1 has every state; the higher levels only their own finished and damaged meshes (one site, one ruin)
    jobs = [(n, s) for n in levels for s in states if n == 1 or s in K.LEVEL_STATES]
    full = set(states) == set(have) and len(levels) == top_level

    scene = K.reset_scene()
    os.makedirs(os.path.join(OUT, "blender"), exist_ok=True)
    meta_path = os.path.join(OUT, name + ".json")
    old = json.load(open(meta_path)) if os.path.exists(meta_path) else {}
    meta = old if (1, "complete") not in jobs else {}
    objs = {}
    for level, state in jobs:
        mesh = level_mesh(mod, level, state)
        kit = K.Kit(mesh, seed=getattr(mod, "SEED", 1), state=state, level=level)
        if len(have) > 1:
            mod.build(kit, state)
        else:
            mod.build(kit)
        ob = objs[(level, state)] = kit.build_object(team)
        tris, lo, hi = kit.stats()
        info = {"mesh": mesh, "triangles": tris,
                "bounds": {"min": [round(v, 1) for v in lo], "max": [round(v, 1) for v in hi]},
                "slots": sorted(set(f[0] for f in kit.faces))}
        if level == 1 and state == "complete":
            meta = {
                "name": name, "mesh": mesh, "triangles": tris, "bounds": info["bounds"],
                "colliders": kit.colliders, "sockets": {k: [round(c, 1) for c in v] for k, v in kit.sockets.items()},
                "footprint": getattr(mod, "FOOTPRINT", None), "ring_radius": getattr(mod, "RING_RADIUS", None),
                "slots": info["slots"],
            }
            for key in ("states", "levels"):
                if key in old:
                    meta[key] = old[key]
        elif level == 1:
            meta.setdefault("states", {})[state] = info
        else:
            if state == "complete":
                info["sockets"] = {k: [round(c, 1) for c in v] for k, v in kit.sockets.items()}
            meta.setdefault("levels", {}).setdefault(str(level), {})[state] = info
        K.export_gltf(ob, os.path.join(OUT, mesh + ".gltf"))          # the file name becomes the asset name
        print("built %s: %d triangles, bounds %s .. %s, slots %d" % (mesh, tris, info["bounds"]["min"], info["bounds"]["max"], len(info["slots"])))
    if "states" in meta:
        meta["states"] = {s: meta["states"][s] for s in K.STATES if s in meta["states"]}
    if "levels" in meta:
        meta["levels"] = {k: meta["levels"][k] for k in sorted(meta["levels"], key=int) if int(k) <= top_level}
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=1)

    focus = getattr(mod, "PREVIEW_FOCUS", (0.0, 0.0, 0.0))
    K.setup_preview(scene, focus=focus, zoom=zooms[0])
    for i, p in enumerate(getattr(mod, "PREVIEW_FIGURES", [(-700, 150), (-760, 260)])):
        K.troop_standin(p, team)
    first = jobs[0]
    for key, ob in objs.items():
        if yaw:
            ob.rotation_euler[2] = -math.radians(yaw)
        ob.hide_render = ob.hide_viewport = key != first
    if full:                                                           # a partial build must not replace the full .blend
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "blender", name + ".blend"), compress=True)
    if "--no-render" in args:
        return
    os.makedirs(PREVIEW, exist_ok=True)

    def show(*visible):
        for key, ob in objs.items():
            ob.hide_render = key not in visible
            ob.location[2] = 0.0

    if (1, "complete") in objs and "--levels-only" not in args:
        show((1, "complete"))
        for z in zooms:
            K.setup_preview(scene, focus=focus, zoom=z)
            K.render(scene, os.path.join(PREVIEW, "%s_z%s.png" % (name, ("%.2f" % z).replace(".", ""))))
    if top_level > 1:                                                  # every level from the game camera, middle zoom
        top = meta["bounds"]["max"][2] if "bounds" in meta else 600.0
        K.setup_preview(scene, focus=(focus[0], focus[1], focus[2] + top * 0.4), zoom=float(opt(args, "--level-zoom", "0.9")))
        for level in levels:
            if (level, "complete") in objs:
                show((level, "complete"))
                K.render(scene, os.path.join(PREVIEW, "%s_L%d.png" % (name, level)))
    if len(have) > 1 and "--levels-only" not in args:
        radius = getattr(mod, "RING_RADIUS", 400.0)
        top = meta["bounds"]["max"][2]
        K.setup_preview(scene, focus=(focus[0], focus[1], top * 0.4), pitch=54.0, dist=max(radius * 3.2, top * 1.5, 1400.0))
        for level, state in jobs:
            show((level, state))
            if state == "site" and (1, "complete") in objs:            # the building half risen inside its scaffold
                show((1, "site"), (1, "complete"))
                objs[(1, "complete")].location[2] = -0.5 * top / 100.0
            K.render(scene, os.path.join(PREVIEW, "%s_%s.png" % (name, state) if level == 1 else "%s_L%d_%s.png" % (name, level, state)))
        show(first)

main()
