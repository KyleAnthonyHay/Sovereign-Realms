"""The town's ground and water (References/Remake/town.png): an island of stepped grass on earth and rock, cliffs to the
sea, cobbled paths and flights of steps, plank paths between the farm plots, the river's bed.

    Blender -b --factory-startup --python Tools/blender/assets/town_terrain.py -- [--no-render]

Reads the plan from town_layout.py (heights and surfaces on the quarter-block grid) and exports
  SM_TownGround_<i>_<j>   28 m tiles of the ground (the open sea bed is left out: the level puts one flat slab there)
  SM_TownWater            the pond, the upper river, the two falls, the gorge pool, the lily pond (quarter-block voxels)
  SM_TownSea              the sea round the island, one sheet of 1 m voxels
The water meshes are exported WITH collision: the level turns it off for everything but the path grid's own queries,
which is how the grid knows where water lies (Source/VoxelLab/VLGrid.cpp).
"""
import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import voxlib as V
import town_layout as L
from voxlib import Vox, IDS

TOP = 8.0


def dilate(mask, k):
    out = mask.copy()
    for ax in (0, 1):
        acc = out.copy()
        for sh in range(1, k + 1):
            acc |= np.roll(out, sh, axis=ax) | np.roll(out, -sh, axis=ax)
        out = acc
    return out


def split(vox, name, chunk=28.0, drop_below=None):
    """voxlib.split, without the faces nobody can ever see: the undersides (every vertex at or under drop_below)."""
    a = vox.mesh_arrays()
    off = np.array(vox.offset, np.float32)
    keep = np.ones(len(a["verts"]), bool)
    if drop_below is not None:
        keep = (a["verts"][:, :, 2] + off[2]).max(axis=1) > drop_below + 1e-4
    centre = a["verts"].mean(axis=1) + off
    ci = np.floor(centre[:, 0] / chunk).astype(np.int64) if chunk else np.zeros(len(centre), np.int64)
    cj = np.floor(centre[:, 1] / chunk).astype(np.int64) if chunk else np.zeros(len(centre), np.int64)
    out = []
    for i in sorted(set(ci[keep].tolist())):
        for j in sorted(set(cj[keep & (ci == i)].tolist())):
            m = keep & (ci == i) & (cj == j)
            out.append(V.mesh_object("%s_%d_%d" % (name, i - ci.min(), j - cj.min()), a["verts"][m] + off, a["uvs"][m], a["cols"][m],
                                     a["tris"][m], a["slot"][m], list(a["slots"]), [], None, a["alpha"][m]))
    return out


def build_terrain(G, s):
    N = L.N
    h = G["h"]
    nz = int((TOP - L.ZMIN) / L.CELL)
    v = Vox(N, N, nz, L.CELL, origin=(N / 2.0, N / 2.0, -L.ZMIN / L.CELL), name="town", seed=4)
    top = np.round((h - L.ZMIN) / L.CELL).astype(np.int32)                  # number of solid voxels in each column
    # the open sea has no ground of its own (nobody sees it under the water): only the bed within a few metres of land
    open_sea = G["sea"] & ~dilate(~G["sea"], 14)
    top[open_sea] = 0
    K = np.arange(nz, dtype=np.int32)[None, None, :]
    solid = K < top[:, :, None]
    depth = top[:, :, None] - 1 - K                                         # 0 = the surface voxel
    surf_ids = np.array([IDS[n] for n in L.SURF], np.uint8)
    # the top quarter block is the surface; under it about a metre and a half of earth, then rock (as on the picture's cliffs)
    earth = 5 + (L.hash2(np.floor(G["X"] / 1.0), np.floor(G["Y"] / 1.0), 3) * 3).astype(np.int32)
    m = np.where(solid, np.where(depth == 0, surf_ids[s][:, :, None], np.where(depth <= earth[:, :, None], IDS["dirt"], IDS["stone"])), 0).astype(np.uint8)
    v.m[:] = m
    del m
    # stone under steps and cobbles; mossy blocks on the cliff tops
    hard = np.isin(s, (L.STONE, L.MOSSY))
    v.m[solid & hard[:, :, None] & (depth >= 1)] = IDS["stone"]
    low = np.minimum.reduce([np.roll(top, 2, 0), np.roll(top, -2, 0), np.roll(top, 2, 1), np.roll(top, -2, 1)])
    cliff = (top - low) >= 9                                                # a drop of more than two metres beside it
    blocky = L.hash2(np.floor(G["X"] / 0.5), np.floor(G["Y"] / 0.5), 7) > 0.72
    v.m[solid & cliff[:, :, None] & (depth == 0) & (s == 0)[:, :, None] & blocky[:, :, None]] = IDS["mossy_stone"]
    return v


def build_water(G):
    """The fresh water on the quarter-block grid: each sheet's surface a quarter block below its banks, and the falls."""
    N, vox = L.N, L.CELL
    h = G["h"]
    z0 = L.SEA - 0.5
    nz = int((1.25 - z0) / vox)
    w = Vox(N, N, nz, vox, origin=(N / 2.0, N / 2.0, -z0 / vox), name="town_water", seed=2)
    K = np.arange(nz)[None, None, :]
    zc = z0 + (K + 0.5) * vox
    above = zc > h[:, :, None]
    fill = (G["water_up"][:, :, None] & above & (zc < L.UPPER)) | (G["water_mid"][:, :, None] & above & (zc < L.POOL)) \
        | (G["water_lily"][:, :, None] & above & (zc < L.LILY))
    # the first fall: where the upper river reaches the edge of the terrace, a curtain down to the pool
    c1 = (G["water_up"] & dilate(G["water_mid"], 3)) | (G["water_mid"] & dilate(G["water_up"], 2))
    fill |= c1[:, :, None] & (zc > L.POOL - 0.25) & (zc < L.UPPER)
    # the second: where the gorge opens on the sea
    c2 = (G["water_mid"] & dilate(~G["land"], 3)) | (~G["land"] & dilate(G["water_mid"], 2))
    fill |= c2[:, :, None] & (zc > L.SEA - 0.25) & (zc < L.POOL)
    w.m[fill] = IDS["water"]
    # white water: streaks down the falls, foam where they land
    X, Y = G["X"], G["Y"]
    streak = L.hash2(np.floor(X / 0.25), np.floor(Y / 0.25), 31) > 0.52
    for (cur, lo, hi) in ((c1, L.POOL, L.UPPER), (c2, L.SEA, L.POOL)):
        w.where((cur & streak)[:, :, None] & (zc > lo) & (zc < hi) & (w.m > 0), "paint", "#eaf6ff")
        foam = dilate(cur, 5) & ~cur & (L.hash2(np.floor(X / 0.25), np.floor(Y / 0.25), 37) > 0.62)
        if lo == L.POOL:
            w.where((foam & G["water_mid"])[:, :, None] & (zc > lo - 0.25) & (zc < lo) & (w.m > 0), "paint", "#f4fbff")
        else:                                                   # on the sea (another mesh): a thin white skin over it
            w.where((foam & ~G["land"])[:, :, None] & (zc > lo) & (zc < lo + 0.25), "paint", "#f4fbff")
    print("fall curtains: %d and %d cells" % (int(c1.sum()), int(c2.sum())))
    return w


def build_sea(G):
    """One sheet of 1 m water voxels, 256 m square, with a hole under the middle of the island."""
    half, vox = 128, 1.0
    n = int(2 * half / vox)
    sea = Vox(n, n, 1, vox, origin=(n / 2.0, n / 2.0, 1.0 - L.SEA / vox), name="town_sea", seed=6)      # top face at SEA
    a = -half + (np.arange(n) + 0.5) * vox
    X, Y = np.meshgrid(a, a, indexing="ij")
    i = np.clip(((X + L.HALF) / L.CELL).astype(int), 0, L.N - 1)
    j = np.clip(((Y + L.HALF) / L.CELL).astype(int), 0, L.N - 1)
    inland = (np.abs(X) < L.HALF) & (np.abs(Y) < L.HALF) & (G["dc"][i, j] > 4.0)
    sea.m[:, :, 0] = np.where(inland, 0, IDS["water"])
    return sea


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    V.reset_scene()
    layout, G, s = L.build()
    v = build_terrain(G, s)
    tiles = split(v, "SM_TownGround", 28.0, drop_below=L.ZMIN)
    for ob in tiles:
        V.export_gltf(ob)
    del v
    wob = build_water(G).to_object("SM_TownWater")
    V.export_gltf(wob)
    sob = split(build_sea(G), "SM_TownSea", None, drop_below=L.SEA - 0.5)[0]
    sob.name = sob.data.name = "SM_TownSea"
    V.export_gltf(sob)
    with open(os.path.join(V.MESHES, "town_tiles.json"), "w") as f:
        json.dump([o.name for o in tiles], f)
    print("town ground: %d tiles, %d faces; water %d faces; sea %d faces" % (len(tiles), sum(o["voxel_faces"] for o in tiles), wob["voxel_faces"], sob["voxel_faces"]))
    if "--no-render" not in args:
        V.render(os.path.join(V.PREVIEWS, "town_terrain.png"), target=(L.C.TARGET[0], L.C.TARGET[1], 0), az=L.C.AZ, el=L.C.EL, dist=180, lens=58,
                 res=(1672, 941), samples=24, ground=False)


main()
