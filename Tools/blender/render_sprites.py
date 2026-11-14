"""Render a built character to reduced sprite cells (one .npz per character).

    Blender -b SourceArt/Characters/blender/<name>.blend -P Tools/blender/render_sprites.py -- \
        [--elev 30] [--cm-per-px 1.75] [--cell 160] [--pivot 80,118] [--ss 4] [--samples 24] \
        [--anims idle,walk] [--facings S,E] [--frames 0,3] [--out path.npz] [--beauty dir]

Every frame is rendered once with all materials swapped to white clay plus a material-id AOV; the lighting,
normal, depth, AO and id passes are then collapsed to the sprite grid (srrender.reduce_cell). Colour, palette,
outline and sheet assembly happen afterwards in Tools/blender/make_sheets.py (plain Python, no Blender).
"""

import json
import math
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
OUT = os.path.normpath(os.path.join(HERE, "..", "..", "SourceArt", "Characters"))

import bpy  # noqa: E402
import numpy as np  # noqa: E402

import srmats  # noqa: E402
import srrender  # noqa: E402

ANIM_ORDER = ["spawn", "idle", "walk", "attack", "hit", "death"]


def arg(args, key, default, cast=str):
    return cast(args[args.index(key) + 1]) if key in args else default


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    sc = bpy.context.scene
    name = sc["sr_character"]
    d = dict(srrender.DEFAULTS)
    d["elev"] = arg(args, "--elev", d["elev"], float)
    d["cm_per_px"] = arg(args, "--cm-per-px", d["cm_per_px"], float)
    d["cell"] = arg(args, "--cell", d["cell"], int)
    d["ss"] = arg(args, "--ss", d["ss"], int)
    d["samples"] = arg(args, "--samples", d["samples"], int)
    if "--pivot" in args:
        d["pivot"] = tuple(int(v) for v in arg(args, "--pivot", "").split(","))
    cam = srrender.setup(sc, **d)
    srrender.setup_passes(sc)
    srrender.set_clay(True)
    bpy.context.view_layer.update()            # matrix_world of the new camera / lights is stale until this
    axes = srrender.camera_axes(cam)

    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    actions = {a.name: a for a in bpy.data.actions}
    anims = arg(args, "--anims", None)
    anims = anims.split(",") if anims else [a for a in ANIM_ORDER if a in actions]
    facings = arg(args, "--facings", None)
    facings = facings.split(",") if facings else srrender.FACINGS
    only = arg(args, "--frames", None)
    only = [int(v) for v in only.split(",")] if only else None
    out = arg(args, "--out", os.path.join(OUT, "_build", name + "_cells.npz"))
    os.makedirs(os.path.dirname(out), exist_ok=True)

    tmp = tempfile.mkdtemp(prefix="sr_render_")
    exr = os.path.join(tmp, "frame.exr")
    sc.render.filepath = exr
    cells, index = [], []
    t0 = time.time()
    for an in anims:
        act = actions[an]
        arm.animation_data.action = act
        n = int(act["sr_frames"])
        for fc in facings:
            arm.rotation_euler = (0.0, 0.0, math.radians(srrender.FACING_ANGLE[fc]))
            for fr in range(n):
                if only is not None and fr not in only:
                    continue
                sc.frame_set(fr)
                bpy.ops.render.render(write_still=True)
                cells.append(srrender.reduce_cell(srrender.read_exr(exr), d["ss"], axes))
                index.append([an, fc, fr])
        print("rendered", an, n, "frames, %.1fs" % (time.time() - t0), flush=True)
    arm.rotation_euler = (0, 0, 0)

    key = bpy.data.objects["SR_Key"]
    to_light = -(key.matrix_world.to_3x3() @ __import__("mathutils").Vector((0, 0, -1)))
    meta = dict(name=name, index=index, render=d, facings=srrender.FACINGS,
                body_height_cm=float(sc["sr_body_height_cm"]),
                key_dir_cam=[float(v) for v in (axes @ np.array(to_light, dtype=np.float32))],
                actions={a: dict(frames=int(actions[a]["sr_frames"]), loop=bool(actions[a]["sr_loop"]),
                                 **{k[3:]: (v if isinstance(v, (int, float, str)) else list(v))
                                    for k, v in actions[a].items() if k.startswith("sr_") and k not in ("sr_frames", "sr_loop")})
                         for a in actions})
    np.savez_compressed(out, meta=json.dumps(meta), **{k: np.stack([c[k] for c in cells]) for k in cells[0]})
    print("wrote", out, len(cells), "cells, %.1fs" % (time.time() - t0))


main()
