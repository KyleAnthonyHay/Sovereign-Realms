"""The village ground: stepped grass on dirt and stone, cobbled paths, the river bed, and the water.

    Blender -b --factory-startup --python Tools/blender/assets/terrain.py -- [--no-render]

Reads the plan from village_layout.py (heights and surfaces on a 0.5 m grid) and exports
  SM_Terrain_<i>_<j>   24 m tiles of the ground (0.5 m voxels: 8 texels to a block)
  SM_Water             the pond, river and stream as one sheet of water voxels, with the fall
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import voxlib as V
import village_layout as L
from voxlib import Vox, IDS


def build_terrain():
    layout, (X, Y, h, s, water_low, water_high) = L.build()
    N = L.N
    nz = int((7.0 - L.ZMIN) / L.CELL)
    v = Vox(N, N, nz, L.CELL, origin=(N / 2.0, N / 2.0, -L.ZMIN / L.CELL), name="terrain", seed=4)
    top = np.round((h - L.ZMIN) / L.CELL).astype(np.int32)                 # number of solid voxels in each column
    K = np.arange(nz, dtype=np.int32)[None, None, :]
    solid = K < top[:, :, None]
    depth = top[:, :, None] - 1 - K                                         # 0 = the surface voxel
    surf_ids = np.array([IDS[n] for n in L.SURF], np.uint8)
    # the top quarter block is the surface (turf, cobbles, gravel); under it earth, then rock
    m = np.where(solid, np.where(depth == 0, surf_ids[s][:, :, None], np.where(depth <= 5, IDS["dirt"], IDS["stone"])), 0).astype(np.uint8)
    v.m[:] = m
    del m
    # where the ground drops 1.25 m or more beside a column, its face is rock rather than earth
    low = np.minimum.reduce([np.roll(top, 2, 0), np.roll(top, -2, 0), np.roll(top, 2, 1), np.roll(top, -2, 1)])
    cliff = (top - low) >= 5
    rock = solid & cliff[:, :, None] & (depth >= 1)
    v.m[rock] = IDS["stone"]
    blocky = (L.hash2(np.floor(X / 0.5), np.floor(Y / 0.5), 7) > 0.6)
    mossy = solid & cliff[:, :, None] & (depth == 0) & (s == 0)[:, :, None] & blocky[:, :, None]
    v.m[mossy] = IDS["mossy_stone"]
    return v, (X, Y, h, s, water_low, water_high)


def build_water(h, water_low, water_high):
    """Water on the same quarter-block grid: its surface sits a quarter block below the banks."""
    N = L.N
    vox = L.CELL
    z0 = -2.0
    nz = int((L.WATER_HIGH - z0) / vox)
    w = Vox(N, N, nz, vox, origin=(N / 2.0, N / 2.0, -z0 / vox), name="water", seed=2)
    K = np.arange(nz)[None, None, :]
    zc = z0 + (K + 0.5) * vox
    fill = (water_low[:, :, None] & (zc > h[:, :, None]) & (zc < L.WATER_LOW)) | (water_high[:, :, None] & (zc > h[:, :, None]) & (zc < L.WATER_HIGH))
    w.m[fill] = IDS["water"]
    # the fall: a curtain of water from the stream's surface down to the pond, where the stream reaches the pond's edge
    Xs = (np.arange(N) + 0.5) * vox - L.HALF
    XX, YY = np.meshgrid(Xs, Xs, indexing="ij")
    near = np.hypot(XX - L.FALL[0], YY - L.FALL[1]) < 2.3                 # the fall between its rocks
    lower = np.zeros_like(water_low)
    for ax, sh in ((0, 1), (0, -1), (1, 1), (1, -1)):
        for step in (1, 2, 3):
            lower |= np.roll(water_low, sh * step, axis=ax)
    curtain = water_high & near & lower
    fall = curtain[:, :, None] & (zc > L.WATER_LOW - 0.25) & (zc < L.WATER_HIGH)
    w.m[fall] = IDS["water"]
    print("fall curtain cells:", int(curtain.sum()))
    return w


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    V.reset_scene()
    v, (X, Y, h, s, water_low, water_high) = build_terrain()
    tiles = V.split(v, "SM_Terrain", 28.0)
    for ob in tiles:
        V.export_gltf(ob)
    w = build_water(h, water_low, water_high)
    wob = w.to_object("SM_Water")
    V.export_gltf(wob, collision="none")
    import json
    with open(os.path.join(V.MESHES, "terrain_tiles.json"), "w") as f:
        json.dump([o.name for o in tiles], f)
    print("terrain: %d tiles, %d faces; water %d faces" % (len(tiles), sum(o["voxel_faces"] for o in tiles), wob["voxel_faces"]))
    if "--no-render" not in args:
        V.render(os.path.join(V.PREVIEWS, "terrain.png"), target=(0, 0, 0), az=28, el=36, dist=100, lens=85, res=(1600, 900), samples=32, ground=False)


main()
