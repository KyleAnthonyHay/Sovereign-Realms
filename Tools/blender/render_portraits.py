"""The HUD's unit portraits: head-and-shoulders close-ups of the voxel characters, one framing, light and background for
all, packed side by side into SourceArt/UI/T_UI_Portraits.png (128 px cells, transparent background) for AVLHUD.

    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python Tools/blender/render_portraits.py \
        [-- [--samples N] [--gpu] [--only Spy,Jonathan]]
    python3 Tools/ue_py.py Tools/ue/import_ui.py        (then, in the editor: the atlas into /Game/Voxel/UI)

The cells, in order (AVLHUD's EVLPortrait): King David, Swordsman, Archer, Spy, Builder, Jonathan. The characters are assembled
from their part jsons as Tools/blender/render_style_refs.py does (its studio light and framing are reused).
"""
import os
import sys

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# render_style_refs runs its main() on import: give it a name it renders nothing for, keep our own flags
_ARGV = sys.argv[:]
SAMPLES = int(_ARGV[_ARGV.index("--samples") + 1]) if "--samples" in _ARGV else 64
sys.argv = [sys.argv[0], "--", "__nothing__", "--samples", str(SAMPLES)] + (["--gpu"] if "--gpu" in _ARGV else [])
import render_style_refs as R  # noqa: E402
sys.argv = _ARGV
import voxlib as V  # noqa: E402

CELL = 128          # pixels per portrait in the atlas
RENDER = 384        # rendered at this size, then scaled down (smooth edges, crisp voxels)
ORDER = [("SM_KingB", "King"), ("SM_Swordsman", "Swordsman"), ("SM_Archer", "Archer"), ("SM_Spy", "Spy"), ("SM_Builder", "Builder"),
         ("SM_Jonathan", "Jonathan")]
HEAD_PARTS = ("Head", "HoodA", "HoodB", "Chest", "ArmL", "ArmR", "Cape", "Quiver", "Pack")
AZ, EL = 22.0, 6.0  # a little from the figure's left (the light's side), nearly level
OUT = os.path.join(V.ROOT, "SourceArt", "UI", "T_UI_Portraits.png")


def clear():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)


def portrait(rig, dst):
    clear()
    R.studio(floor_z=0.0)
    root, obs = R.place_character(rig)
    bpy.context.view_layer.update()
    import json
    neck = json.load(open(os.path.join(V.MESHES, rig + ".json")))["parts"]["Head"]["pivot"][2]
    head = R.world_points([o for o in obs if any(n in o.name for n in ("Head", "Hood"))] or obs)
    # the head fills the top of the cell; the frame reaches down to the shoulders (a point under the neck joint), as
    # wide as that needs: every portrait the same framing whatever the shoulders, cape or hood
    lo, hi = head.min(axis=0), head.max(axis=0)
    c = (lo + hi) / 2.0
    keep = np.vstack([head, [[c[0], c[1], neck - 0.24]]])
    scene = bpy.context.scene
    scene.render.film_transparent = True
    for ob in bpy.data.objects:
        if ob.get("catcher"):
            ob.hide_render = True
    R.frame(keep, AZ, EL, (RENDER, RENDER), 0.80, 0.90, 85.0)
    scene.render.filepath = dst
    bpy.ops.render.render(write_still=True)
    print("rendered", rig, dst)


def old_cells():
    """The cells of the atlas as it stands (--only keeps the others as they are)."""
    if not os.path.exists(OUT):
        return []
    img = bpy.data.images.load(OUT)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    a = px.reshape(h, w, 4)
    return [a[:, i * CELL:(i + 1) * CELL].copy() for i in range(w // CELL)] if h == CELL else []


def main():
    tmp = os.path.join(R.TMP, "portraits")
    os.makedirs(tmp, exist_ok=True)
    # --only Spy,Jonathan: render only those cells and keep the rest of the atlas (when a figure's parts are not all
    # exported on this machine, or one character has changed)
    only = set(_ARGV[_ARGV.index("--only") + 1].split(",")) if "--only" in _ARGV else None
    old = old_cells() if only else []
    cells = []
    for i, (rig, name) in enumerate(ORDER):
        if only is not None and name not in only and i < len(old):
            cells.append(old[i])
            print("kept", name)
            continue
        p = os.path.join(tmp, name + ".png")
        portrait(rig, p)
        img = bpy.data.images.load(p)
        img.scale(CELL, CELL)
        px = np.empty(CELL * CELL * 4, np.float32)
        img.pixels.foreach_get(px)
        cells.append(px.reshape(CELL, CELL, 4))
        bpy.data.images.remove(img)
    atlas = np.concatenate(cells, axis=1)                       # one row, left to right
    h, w = atlas.shape[:2]
    out = bpy.data.images.new("T_UI_Portraits", w, h, alpha=True)
    out.alpha_mode = "STRAIGHT"
    out.pixels.foreach_set(atlas.ravel())
    out.filepath_raw = OUT
    out.file_format = "PNG"
    out.save()
    print("wrote", OUT, w, h)


main()
