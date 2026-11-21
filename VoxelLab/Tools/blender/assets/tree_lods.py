"""A second level of detail for the tall trees: SM_Tree2_<A..D>_Trunk_L1 / _Leaves_L1.

    Blender -b --factory-startup --python Tools/blender/assets/tree_lods.py -- [--only A,B] [--render]

A forest of the full trees is far too much to draw (a D is 10k faces, an A 100k). Each tree is read back from its own
exported mesh (SourceArt/Meshes/SM_Tree2_<k>_<part>.gltf, so trees_tall.py does not have to be run again) and built
again out of blocks twice the size: crowns of half-metre cubes (the trees' are 0.25 m), trunks of 0.25 m voxels
(0.125 m). A block is solid where at least two of the eight voxels it replaces showed a face, plus whatever those
enclose; it takes their commonest material and their mean colour. About a tenth of the faces. The textures are laid
out in world space, so from where the engine switches to it (some 40 m: Tools/ue/tree_lods.py makes it LOD 1 of the
tree's mesh) the difference is the size of the crown's lumps, not its colour.
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import voxlib as V
from voxlib import Vox, IDS, MATS

import bpy

FINE = {"Trunk": 0.125, "Leaves": 0.25}        # the voxel the tree was made of
MIN_SHOWING = {"Trunk": 2, "Leaves": 2}        # how many of a block's eight voxels must have shown a face


def lin_to_srgb(c):
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1.0 / 2.4) - 0.055)


def slot_material(slot):
    """The voxel material a mesh slot was drawn with (the first whose top / side / bottom slots name it)."""
    for name, m in MATS.items():
        if slot in m["slots"]:
            return IDS[name]
    return IDS["leaves"]


def read(path):
    """-> triangle centres pushed a little inside their voxel (T, 3), colours (T, 3) linear, material ids (T,)"""
    V.reset_scene()
    bpy.ops.import_scene.gltf(filepath=path)
    ob = [o for o in bpy.context.scene.objects if o.type == "MESH"][0]
    me = ob.data
    me.calc_loop_triangles()
    T = len(me.loop_triangles)
    co = np.zeros(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    M = np.array(ob.matrix_world, np.float32)
    co = co @ M[:3, :3].T + M[:3, 3]
    tv = np.zeros(T * 3, np.int32)
    me.loop_triangles.foreach_get("vertices", tv)
    tl = np.zeros(T * 3, np.int32)
    me.loop_triangles.foreach_get("loops", tl)
    mi = np.zeros(T, np.int32)
    me.loop_triangles.foreach_get("material_index", mi)
    p = co[tv].reshape(T, 3, 3)
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
    inside = p.mean(axis=1) - n * 0.02
    attr = me.color_attributes[0] if len(me.color_attributes) else None
    col = np.ones((T, 3), np.float32) * 0.6
    if attr is not None:
        size = len(me.loops) if attr.domain == "CORNER" else len(me.vertices)
        raw = np.zeros(size * 4, np.float32)
        attr.data.foreach_get("color", raw)
        raw = raw.reshape(-1, 4)[:, :3]
        c3 = raw[tl if attr.domain == "CORNER" else tv].reshape(T, 3, 3)
        col = c3[np.arange(T), np.argmax(c3.sum(axis=2), axis=1)]            # the brightest corner: the least corner shading
    names = [s.material.name.split(".")[0].replace("MI_Vox_", "").replace("Vox_", "") if s.material else "leaves" for s in ob.material_slots] or ["leaves"]
    mats = np.array([slot_material(s) for s in names], np.int32)
    return inside, col, mats[np.clip(mi, 0, len(mats) - 1)], names


def rebuild(kind, part):
    name = "SM_Tree2_%s_%s" % (kind, part)
    inside, col, mat, slots = read(os.path.join(V.MESHES, name + ".gltf"))
    f = FINE[part]
    v = f * 2.0
    lo = np.floor(inside.min(axis=0) / v) * v - v
    fi = np.floor((inside - lo) / f).astype(np.int64)                       # the voxel each face belonged to
    nf = (fi.max(axis=0) + 1 + 3) // 2 * 2
    fine = np.zeros(tuple(nf), bool)
    fine[fi[:, 0], fi[:, 1], fi[:, 2]] = True
    n = tuple(int(x) // 2 for x in nf)
    showing = fine.reshape(n[0], 2, n[1], 2, n[2], 2).sum(axis=(1, 3, 5))
    solid = showing >= MIN_SHOWING[part]
    # what the shell encloses: everything the outside cannot reach
    outside = np.zeros(n, bool)
    outside[0], outside[-1], outside[:, 0], outside[:, -1], outside[:, :, 0], outside[:, :, -1] = True, True, True, True, True, True
    outside &= ~solid
    while True:
        grow = outside.copy()
        for ax in range(3):
            grow |= np.roll(outside, 1, ax) | np.roll(outside, -1, ax)
        grow &= ~solid
        if grow.sum() == outside.sum():
            break
        outside = grow
    filled = ~outside
    # colour and material of each block: from the faces that fell in it
    ci = fi // 2
    flat = (ci[:, 0] * n[1] + ci[:, 1]) * n[2] + ci[:, 2]
    cnt = np.bincount(flat, minlength=n[0] * n[1] * n[2]).astype(np.float32)
    rgb = np.stack([np.bincount(flat, weights=col[:, k], minlength=len(cnt)) for k in range(3)], axis=1) / np.maximum(cnt, 1.0)[:, None]
    ids = sorted(set(mat.tolist()))
    votes = np.stack([np.bincount(flat[mat == i], minlength=len(cnt)) for i in ids], axis=1)
    best = np.array(ids, np.uint8)[np.argmax(votes, axis=1)].reshape(n)
    have = (cnt > 0).reshape(n)
    rgb = rgb.reshape(n + (3,))
    mean = col.mean(axis=0)
    main = np.uint8(max(ids, key=lambda i: int((mat == i).sum())))
    vox = Vox(n[0], n[1], n[2], v, origin=tuple(float(x) for x in (-lo / v)), name=name + "_L1", seed=3)
    vox.m[:] = np.where(filled, np.where(have, best, main), 0)
    vox.c[:] = np.round(lin_to_srgb(np.where(have[..., None], rgb, mean[None, None, None, :])) * 255.0).astype(np.uint8)
    V.reset_scene()
    a = vox.mesh_arrays()
    # only the tree's own material slots (a block's top may ask for another: a log's end): LOD 1 shares LOD 0's materials
    names = [s if s in slots else ("bark" if "bark" in slots else slots[0]) for s in a["slots"]]
    uniq = [s for s in slots if s in names]
    remap = np.array([uniq.index(s) for s in names], np.int32)
    ob = V.mesh_object(name + "_L1", a["verts"], a["uvs"], a["cols"], a["tris"], remap[a["slot"]], uniq, [], None, a["alpha"])
    V.export_gltf(ob, collision="none")
    print("LOD %s: %d triangles -> %d faces (%d blocks of %.3f m); slots %s" % (name, len(inside), ob["voxel_faces"], int(filled.sum()), v, slots))
    return ob


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    only = args[args.index("--only") + 1].split(",") if "--only" in args else list("ABCD")
    for k in only:
        for part in ("Trunk", "Leaves"):
            rebuild(k, part)
    if "--render" in args:
        V.reset_scene()
        for i, k in enumerate(only):
            for part in ("Trunk", "Leaves"):
                for j, suffix in enumerate(("", "_L1")):
                    bpy.ops.import_scene.gltf(filepath=os.path.join(V.MESHES, "SM_Tree2_%s_%s%s.gltf" % (k, part, suffix)))
                    for o in bpy.context.selected_objects:
                        o.location.x += i * 18.0
                        o.location.y += j * 20.0
        V.render(os.path.join(V.PREVIEWS, "tree_lods.png"), target=(27, 10, 6), az=-20, el=22, dist=95, lens=58, res=(1672, 941), samples=16)


main()
