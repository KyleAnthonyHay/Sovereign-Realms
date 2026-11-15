"""Sculpted mountain height fields for the battlefield's backdrop, made with Blender's A.N.T. Landscape extension
(ridged multifractal noise, then its hydraulic / thermal eroder). Writes one 97 x 97 height grid per peak:

    /Applications/Blender.app/Contents/MacOS/Blender -b --python Tools/blender/build_mountains.py
    -> SourceArt/World/Mountains/peak_<n>.npy     heights 0..1, edges at 0 (float32)

Tools/world/gen_battlefield.py turns the grids into faceted meshes (SM_T_Peak_*) in the game's own UV and material
conventions, so nothing from Blender but the shape reaches the game. Needs the extension once:

    Blender --online-mode --command extension install antlandscape --enable

A.N.T. Landscape is GPL-2.0-or-later (a tool; its output carries no licence). See SourceArt/World/Mountains/CREDITS.md.
"""
import os
import sys

import bpy
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "SourceArt", "World", "Mountains")
N = 96                      # quads per side
# (seed, noise type, noise size, eroder passes): a few characters, from one sharp horn to a long broken ridge
PEAKS = [
    (11, "ridged_multi_fractal", 0.9, 2),
    (23, "ridged_multi_fractal", 1.3, 2),
    (37, "hetero_terrain", 0.8, 3),
    (41, "hybrid_multi_fractal", 1.0, 2),
    (58, "ridged_multi_fractal", 0.7, 1),
    (73, "shattered_hterrain", 1.1, 2),
]


def grid_of(obj):
    co = np.zeros(len(obj.data.vertices) * 3, np.float32)
    obj.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    order = np.lexsort((co[:, 0], co[:, 1]))            # rows by y, then x
    return co[order, 2].reshape(N + 1, N + 1)


def main():
    if not hasattr(bpy.ops.mesh, "landscape_add"):
        try:
            bpy.ops.preferences.addon_enable(module="bl_ext.blender_org.antlandscape")
        except Exception as e:
            print("A.N.T. Landscape is not installed:", e)
            sys.exit(1)
    os.makedirs(OUT, exist_ok=True)
    for i, (seed, kind, size, passes) in enumerate(PEAKS):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.preferences.addon_enable(module="bl_ext.blender_org.antlandscape")
        bpy.ops.mesh.landscape_add(
            ant_terrain_name="Peak", at_cursor=False, smooth_mesh=False, tri_face=False,
            subdivision_x=N + 1, subdivision_y=N + 1, mesh_size=2.0, mesh_size_x=2.0, mesh_size_y=2.0,
            random_seed=seed, noise_size=size, noise_type=kind, basis_type="PERLIN_NEW",
            noise_depth=8, amplitude=0.5, frequency=2.0, dimension=1.0, lacunarity=2.0, offset=1.0, gain=1.0,
            height=0.6, height_offset=0.12, edge_falloff="3", falloff_x=2.6, falloff_y=2.6, edge_level=0.0,
            maximum=2.0, minimum=0.0, refresh=True)
        obj = bpy.context.object
        eroded = False
        try:
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)
            bpy.ops.mesh.eroder(Iterations=passes, IterRiver=30, IterAva=6, IterDiffuse=3, Ef=0.0, Kd=0.1, Kt=0.9,
                                Kr=0.012, Kv=0.0, userainmap=False, Ks=0.5, Kdep=0.1, Kz=0.3, Kc=0.9, Ka=1.0, Kev=0.5,
                                numexpr=False, smooth=False)
            eroded = True
        except Exception as e:                           # the eroder is optional polish: the noise alone still works
            print("eroder skipped for peak %d: %s" % (i, e))
        h = grid_of(obj).astype(np.float32)
        h -= np.percentile(h[[0, -1], :], 50)            # the skirt sits at 0
        h = np.clip(h, 0.0, None)
        edge = np.minimum.outer(np.minimum(np.arange(N + 1), N - np.arange(N + 1)), np.minimum(np.arange(N + 1), N - np.arange(N + 1)))
        h *= np.clip(edge / 6.0, 0.0, 1.0)               # pinned to the ground all round
        h /= max(float(h.max()), 1e-6)
        np.save(os.path.join(OUT, "peak_%d.npy" % i), h)
        print("peak %d: %s seed %d, eroded %s, mean %.3f" % (i, kind, seed, eroded, float(h.mean())))


main()
