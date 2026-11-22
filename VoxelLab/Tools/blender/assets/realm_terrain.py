"""The realm's ground, water, backdrop and barriers (References/Remake/battlefield.png). As assets/town_terrain.py.

    Blender -b --factory-startup --python Tools/blender/assets/realm_terrain.py -- [--no-render] [--only ground,water,sea,backdrop,barrier]

Reads the plan from realm_layout.py (heights, surfaces and the hazard map on the quarter-block grid) and exports
  SM_RealmGround_<i>_<j>  26 m tiles of the ground (the open sea bed is left out: the level puts one flat slab there).
                          The map is meshed in 104 m blocks (the whole grid at once would not fit in memory), and flat
                          faces are joined two by two into half-metre quads wherever nothing tells them apart (same
                          tint cell, no corner shading): about a third of the faces, the same picture
  SM_RealmWater           the river: the upper reach, the gorge and its two channels, the lower gorge, the three falls
  SM_RealmSea             the sea, one sheet of 2 m voxels, 640 m square (holes under the land)
  SM_RealmBackdrop        what lies beyond the playable edge, 2 m voxels, no collision: the land running on to the north
                          and the east into wooded slopes and snowy mountains, rock stacks far out at sea
  SM_RealmBarrier         walls nobody sees, half a metre thick, along the edge of everything a unit must not enter
                          (the river's banks, the falls' tops, the cliff's rim over the sea, the island's rocks, the
                          sea round the dock): the level makes them block pawns only. The bridges and the dock's
                          planks are left open.
The water meshes are exported WITH collision: the level turns it off for everything but the path grid's own queries,
which is how the grid knows where water lies (Source/VoxelLab/VLGrid.cpp).
"""
import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import voxlib as V
import realm_layout as L
from voxlib import Vox, IDS

TILE = 26.0
BLOCK = 104.0        # the ground is meshed in blocks of this size (4 x 4 tiles)
FAR = 440.0          # the sea and the backdrop reach this far from the middle
BV = 2.0             # the backdrop's and the sea's voxel
WALL_TOP = L.TOP + 3.0
# (the rock stacks that stood out at sea here, in the backdrop's 2 m blocks, read as a coarse version of the islands up
# close: References/Remake/lod_coarse_bad.png, owner 2026-11-21. The islands are the plan's ISLETS, in the ground's own
# quarter blocks.)
FAR_ISLES = []
NEAR_BARE = 70.0     # metres beyond the playable edge with no 2 m leaf blocks (they read as coarse trees from the overview)


def dilate(mask, k):
    out = mask.copy()
    for ax in (0, 1):
        acc = out.copy()
        for sh in range(1, k + 1):
            acc |= np.roll(out, sh, axis=ax) | np.roll(out, -sh, axis=ax)
        out = acc
    return out


def merge_quads(a, vox):
    """Joins flat faces two by two: four quads of one voxel that fill a 2 x 2 block of their plane, look the same way,
    have the same material and the same colour at every corner (the same tint cell, no corner shading) become one
    quad. The texture is laid out in world space, so the picture does not change. Works on mesh_arrays' dict."""
    v = a["verts"]
    F = len(v)
    if F == 0:
        return a
    vmin, vmax = v.min(axis=1), v.max(axis=1)
    axis = np.argmin(vmax - vmin, axis=1)
    t = a["tris"]
    r = np.arange(F)
    n = np.cross(v[r, t[:, 1]] - v[r, t[:, 0]], v[r, t[:, 2]] - v[r, t[:, 0]])
    sign = (n[r, axis] > 0).astype(np.int64)
    q = np.round(vmin / vox).astype(np.int64)
    UA, VA = np.array([1, 0, 0]), np.array([2, 2, 1])
    ua, va = UA[axis], VA[axis]
    qu, qv, qw = q[r, ua], q[r, va], q[r, axis]
    c = a["cols"]
    plain = ((c.max(axis=1) - c.min(axis=1)).max(axis=1) < 1e-5) & (np.abs(a["alpha"]).max(axis=1) < 1e-6)
    O = 1 << 14
    key = (((((axis * 2 + sign) * 64 + a["slot"]) * (2 * O) + (qw + O)) * (2 * O) + (qu // 2 + O)) * (2 * O)) + (qv // 2 + O)
    sub = (qu & 1) + 2 * (qv & 1)
    idx = np.flatnonzero(plain)
    order = idx[np.lexsort((sub[idx], key[idx]))]
    k = key[order]
    start = np.flatnonzero(np.concatenate([[True], k[1:] != k[:-1]]))
    length = np.diff(np.concatenate([start, [len(k)]]))
    four = start[length == 4]
    if len(four) == 0:
        return a
    g = order[four[:, None] + np.arange(4)[None, :]]                        # (G, 4) faces, the block's low corner first
    same = (np.abs(c[g][:, :, 0, :] - c[g][:, :1, 0, :]).max(axis=(1, 2)) < 1e-5)
    g = g[same]
    first = g[:, 0]
    tv = v[first]
    base = vmin[first][:, None, :]
    nv = base + (tv - base) * 2.0
    d = nv - tv
    G = np.arange(len(first))
    uv = a["uvs"][first].copy()
    scale = 1.0 / (V.TEXEL * V.TEX_SIZE)
    uv[:, :, 0] += d[G[:, None], np.arange(4)[None, :], ua[first][:, None]] * scale
    uv[:, :, 1] += d[G[:, None], np.arange(4)[None, :], va[first][:, None]] * scale
    keep = np.ones(F, bool)
    keep[g.reshape(-1)] = False
    return dict(verts=np.concatenate([v[keep], nv]), uvs=np.concatenate([a["uvs"][keep], uv]), cols=np.concatenate([c[keep], c[first]]),
                tris=np.concatenate([t[keep], t[first]]), slot=np.concatenate([a["slot"][keep], a["slot"][first]]), slots=a["slots"],
                alpha=np.concatenate([a["alpha"][keep], a["alpha"][first]]))


def tiles_of(a, name, chunk, base, collection=None):
    """Mesh objects from face arrays, one per chunk x chunk metre tile: <name>_<i>_<j>, counted from the map's corner."""
    centre = a["verts"].mean(axis=1)
    ci = np.floor((centre[:, 0] + base) / chunk).astype(np.int64)
    cj = np.floor((centre[:, 1] + base) / chunk).astype(np.int64)
    out = []
    for i in sorted(set(ci.tolist())):
        for j in sorted(set(cj[ci == i].tolist())):
            m = (ci == i) & (cj == j)
            out.append(V.mesh_object("%s_%d_%d" % (name, i, j), a["verts"][m], a["uvs"][m], a["cols"][m], a["tris"][m], a["slot"][m],
                                     list(a["slots"]), [], collection, a["alpha"][m]))
    return out


def split(vox, name, chunk=TILE, drop_below=None):
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
    """The ground's face arrays, block by block (yields one dict per 104 m block that has any ground)."""
    N = L.N
    h = G["h"]
    nz = int((L.TOP - L.ZMIN) / L.CELL)
    top = np.round((h - L.ZMIN) / L.CELL).astype(np.int16)                  # number of solid voxels in each column
    # the open sea has no ground of its own (nobody sees it under the water): only the bed within a few metres of land
    open_sea = G["sea"] & ~dilate(~G["sea"], 14)
    top[open_sea] = 0
    surf_ids = np.array([IDS[n] for n in L.SURF], np.uint8)
    earth = (5 + (L.hash2(np.floor(G["X"] / 1.0), np.floor(G["Y"] / 1.0), 3) * 3)).astype(np.int16)
    hard = np.isin(s, (L.STONE, L.MOSSY))
    low = np.minimum.reduce([np.roll(top, 2, 0), np.roll(top, -2, 0), np.roll(top, 2, 1), np.roll(top, -2, 1)])
    cliff = (top - low) >= 9                                                # a drop of more than two metres beside it
    blocky = L.hash2(np.floor(G["X"] / 0.5), np.floor(G["Y"] / 0.5), 7) > 0.72
    mossy_top = cliff & (s == 0) & blocky
    dirt, stone, mossy = IDS["dirt"], IDS["stone"], IDS["mossy_stone"]
    nb = int(round(BLOCK / L.CELL))
    PAD = 4                                                                 # (even: the tint cells of neighbouring blocks line up)
    K = np.arange(nz, dtype=np.int16)[None, None, :]
    for bi in range(0, N, nb):
        for bj in range(0, N, nb):
            i0, i1, j0, j1 = max(bi - PAD, 0), min(bi + nb + PAD, N), max(bj - PAD, 0), min(bj + nb + PAD, N)
            sl = (slice(i0, i1), slice(j0, j1))
            t = top[sl]
            if int(t[bi - i0:bi - i0 + nb, bj - j0:bj - j0 + nb].max()) == 0:
                continue
            v = Vox(i1 - i0, j1 - j0, nz, L.CELL, origin=(N / 2.0 - i0, N / 2.0 - j0, -L.ZMIN / L.CELL), name="realm", seed=4)
            depth = t[:, :, None] - 1 - K                                   # 0 = the surface voxel
            layer = np.where(depth == 0, surf_ids[s[sl]][:, :, None], np.where((depth <= earth[sl][:, :, None]) & ~hard[sl][:, :, None], dirt, stone)).astype(np.uint8)
            layer[(depth == 0) & mossy_top[sl][:, :, None]] = mossy
            v.m[:] = np.where(depth >= 0, layer, 0)
            del depth, layer
            a = v.mesh_arrays()
            del v
            if a is None:
                continue
            c = a["verts"].mean(axis=1)
            x0, y0 = -L.HALF + bi * L.CELL, -L.HALF + bj * L.CELL
            keep = (c[:, 0] >= x0) & (c[:, 0] < x0 + BLOCK) & (c[:, 1] >= y0) & (c[:, 1] < y0 + BLOCK) & (a["verts"][:, :, 2].max(axis=1) > L.ZMIN + 1e-4)
            a = dict(a, **{k: a[k][keep] for k in ("verts", "uvs", "cols", "tris", "slot", "alpha")})
            before = len(a["verts"])
            a = merge_quads(a, L.CELL)
            print("ground block %d %d: %d faces, %d after joining" % (bi // nb, bj // nb, before, len(a["verts"])))
            yield a


def build_water(G):
    """The fresh water on the quarter-block grid: each sheet's surface a quarter block below its banks, and the falls."""
    N, vox = L.N, L.CELL
    z0 = L.SEA - 0.5
    nz = int((L.UP + 0.5 - z0) / vox)
    # only the river's part of the map (the whole grid, 36 layers deep, is far more than it needs)
    wet = dilate(G["water_up"] | G["water_mid"] | G["water_low"], 8)
    ii, jj = np.flatnonzero(wet.any(axis=1)), np.flatnonzero(wet.any(axis=0))
    i0, i1, j0, j1 = (int(ii[0]) // 2) * 2, int(ii[-1]) + 1, (int(jj[0]) // 2) * 2, int(jj[-1]) + 1
    sl = (slice(i0, i1), slice(j0, j1))
    w = Vox(i1 - i0, j1 - j0, nz, vox, origin=(N / 2.0 - i0, N / 2.0 - j0, -z0 / vox), name="realm_water", seed=2)
    h, X, Y = G["h"][sl], G["X"][sl], G["Y"][sl]
    up, mid, low, land = G["water_up"][sl], G["water_mid"][sl], G["water_low"][sl], G["land"][sl]
    c1 = (up & dilate(mid, 3)) | (mid & dilate(up, 2))                      # the first fall: off the highland into the gorge
    c2 = (mid & dilate(low, 3)) | (low & dilate(mid, 2))                    # the second: into the lower gorge
    c3 = (low & dilate(~land, 3)) | (~land & dilate(low, 2))                # the third: into the sea
    streak = L.hash2(np.floor(X / 0.25), np.floor(Y / 0.25), 31) > 0.52
    foam_h = L.hash2(np.floor(X / 0.25), np.floor(Y / 0.25), 37) > 0.62
    falls = ((c1, L.MID, L.UP, mid), (c2, L.LOW, L.MID, low), (c3, L.SEA, L.LOW, None))
    for k in range(nz):
        zc = z0 + (k + 0.5) * vox
        above = zc > h
        fill = (up & above & (zc < L.UP)) | (mid & above & (zc < L.MID)) | (low & above & (zc < L.LOW))
        for (cur, lo, hi, _pool) in falls:
            fill |= cur & (zc > lo - 0.25) & (zc < hi)
        w.m[:, :, k] = np.where(fill, IDS["water"], 0)
    # white water: streaks down the falls, foam where they land
    K = np.arange(nz)[None, None, :]
    zc = z0 + (K + 0.5) * vox
    for (cur, lo, hi, pool) in falls:
        w.where((cur & streak)[:, :, None] & (zc > lo) & (zc < hi) & (w.m > 0), "paint", "#eaf6ff")
        foam = dilate(cur, 5) & ~cur & foam_h
        if pool is not None:
            w.where((foam & pool)[:, :, None] & (zc > lo - 0.25) & (zc < lo) & (w.m > 0), "paint", "#f4fbff")
        else:                                                   # on the sea (another mesh): a thin white skin over it
            w.where((foam & ~land)[:, :, None] & (zc > lo) & (zc < lo + 0.25), "paint", "#f4fbff")
    print("fall curtains: %d, %d and %d cells" % (int(c1.sum()), int(c2.sum()), int(c3.sum())))
    return w


def far_grid():
    n = int(2 * FAR / BV)
    a = -FAR + (np.arange(n) + 0.5) * BV
    X, Y = np.meshgrid(a, a, indexing="ij")
    return n, X, Y


def far_land(G, X, Y):
    """The backdrop's ground: heights (metres) beyond the playable square, and where it is land at all."""
    i = np.clip(((X + L.HALF) / L.CELL).astype(int), 0, L.N - 1)
    j = np.clip(((Y + L.HALF) / L.CELL).astype(int), 0, L.N - 1)
    outside = (np.abs(X) > L.HALF) | (np.abs(Y) > L.HALF)
    edge = G["h"][i, j]                                                     # the playable ground's height at the nearest edge cell
    ex, ey = np.maximum(X - L.HALF, 0.0), np.maximum(Y - L.HALF, 0.0)
    e = np.hypot(ex, ey)
    n_big = L.noise2(X, Y, 90.0, 205)
    n_mid = L.noise2(X, Y, 34.0, 207)
    n_small = L.noise2(X, Y, 12.0, 209)
    coast_w = -184.0 + (n_mid - 0.5) * 14.0
    coast_s = -116.0 + (n_mid - 0.5) * 14.0
    land = outside & (((Y > L.HALF) & (X > coast_w)) | ((X > L.HALF) & (Y > coast_s))) & (edge > L.SEA + 0.5)
    ramp = np.minimum(e, 210.0)
    hb = np.maximum(edge, 3.0) + ramp * (0.10 + 0.75 * n_big ** 1.6) + (n_mid - 0.5) * np.minimum(e, 60.0) * 0.5 + (n_small - 0.5) * np.minimum(e, 30.0) * 0.25
    hb = np.maximum(hb, np.maximum(edge, 1.0))
    # rock stacks far out at sea
    isle = np.zeros(X.shape, bool)
    for (x, y, r, top) in FAR_ISLES:
        d = np.hypot(X - x, Y - y) + (n_small - 0.5) * 6.0
        m = d < r
        isle |= m
        hb = np.where(m, L.SEA + top * (1.0 - (d / r) ** 2) + 1.0, hb)
    return land | isle, hb, e, n_small


def build_backdrop(G):
    n, X, Y = far_grid()
    land, hb, e, n_small = far_land(G, X, Y)
    z0 = L.ZMIN
    nz = int((104.0 - z0) / BV)
    b = Vox(n, n, nz, BV, origin=(n / 2.0, n / 2.0, -z0 / BV), name="realm_backdrop", seed=9)
    top = np.clip(np.round((hb - z0) / BV), 1, nz - 3).astype(np.int32)
    top[~land] = 0
    K = np.arange(nz, dtype=np.int32)[None, None, :]
    depth = top[:, :, None] - 1 - K
    solid = depth >= 0
    hz = z0 + top * BV
    low = np.minimum.reduce([np.roll(top, 1, 0), np.roll(top, -1, 0), np.roll(top, 1, 1), np.roll(top, -1, 1)])
    steep = (top - low) >= 3
    snow = hz > 40.0 + (n_small - 0.5) * 14.0
    rock = (steep | (hz > 30.0 + (n_small - 0.5) * 10.0)) & ~snow
    b.m[:] = np.where(solid, np.where((depth == 0)[:, :, :] & ~rock[:, :, None], IDS["grass"], IDS["stone"]), 0).astype(np.uint8)
    b.where(solid & (depth <= 1) & snow[:, :, None], "paint", "#f2f6fb")
    # the distant forest: blocks of leaves on the wooded slopes (two tints)
    hh = L.hash2(np.floor(X / BV), np.floor(Y / BV), 77)
    wooded = land & ~rock & ~snow & (hz < 30.0) & (L.noise2(X, Y, 22.0, 211) > 0.36) & (e > NEAR_BARE)
    for (lo, hi, tall, col) in ((0.5, 0.78, 1, "#5d8f3a"), (0.78, 1.01, 2, "#4c7d33")):
        tree = wooded & (hh >= lo) & (hh < hi)
        b.where(tree[:, :, None] & (K >= top[:, :, None]) & (K < top[:, :, None] + tall), "leaves", col)
    return b


def build_sea(G):
    """One sheet of 2 m water voxels with holes under the land (the playable land and the backdrop's)."""
    n, X, Y = far_grid()
    sea = Vox(n, n, 1, BV, origin=(n / 2.0, n / 2.0, 1.0 - L.SEA / BV), name="realm_sea", seed=6)      # top face at SEA
    i = np.clip(((X + L.HALF) / L.CELL).astype(int), 0, L.N - 1)
    j = np.clip(((Y + L.HALF) / L.CELL).astype(int), 0, L.N - 1)
    inside = (np.abs(X) < L.HALF) & (np.abs(Y) < L.HALF)
    inland = inside & (G["dc"][i, j] > 6.0)
    land, hb, e, _n = far_land(G, X, Y)
    inland |= dilate(land, 0) & ~dilate(~land, 2) & ~inside
    sea.m[:, :, 0] = np.where(inland, 0, IDS["water"])
    return sea


def build_barrier(G):
    """Thin walls on the edge of the hazard map (50 cm cells), as one mesh of tall quads."""
    hz = G["hazard"]
    H = hz[0::2, 0::2] & hz[1::2, 0::2] & hz[0::2, 1::2] & hz[1::2, 1::2]
    n = H.shape[0]
    safe = ~H
    near = safe.copy()
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            near |= np.roll(np.roll(safe, di, 0), dj, 1)
    band = H & near
    band[0, :] = band[-1, :] = band[:, 0] = band[:, -1] = False
    c = 0.5
    z0, z1 = L.ZMIN, WALL_TOP
    quads = []

    def runs(row):
        idx = np.flatnonzero(row)
        if len(idx) == 0:
            return []
        cut = np.flatnonzero(np.diff(idx) > 1)
        starts = np.concatenate([[idx[0]], idx[cut + 1]])
        ends = np.concatenate([idx[cut], [idx[-1]]])
        return list(zip(starts.tolist(), (ends + 1).tolist()))

    for sign in (1, -1):
        fx = band & ~np.roll(band, -sign, 0)                 # faces looking along +x / -x: runs along y
        for i in range(n):
            xf = -L.HALF + (i + (1 if sign > 0 else 0)) * c
            for (a, b) in runs(fx[i]):
                y0, y1 = -L.HALF + a * c, -L.HALF + b * c
                q = [(xf, y0, z0), (xf, y1, z0), (xf, y1, z1), (xf, y0, z1)]
                quads.append(q if sign > 0 else [q[0], q[3], q[2], q[1]])
        fy = band & ~np.roll(band, -sign, 1)                 # along +y / -y: runs along x
        for j in range(n):
            yf = -L.HALF + (j + (1 if sign > 0 else 0)) * c
            for (a, b) in runs(fy[:, j]):
                x0, x1 = -L.HALF + a * c, -L.HALF + b * c
                q = [(x0, yf, z0), (x0, yf, z1), (x1, yf, z1), (x1, yf, z0)]
                quads.append(q if sign > 0 else [q[0], q[3], q[2], q[1]])
    F = len(quads)
    verts = np.array(quads, np.float32)
    uvs = np.zeros((F, 4, 2), np.float32)
    cols = np.ones((F, 4, 3), np.float32)
    tris = np.tile(np.array([0, 1, 2, 0, 2, 3]), (F, 1))
    ob = V.mesh_object("SM_RealmBarrier", verts, uvs, cols, tris, np.zeros(F, np.int32), ["stone"], [], None, np.zeros((F, 4), np.float32))
    print("barrier: %d cells of wall (%.0f m), %d quads" % (int(band.sum()), band.sum() * c, F))
    return ob


def bpy_remove(ob):
    import bpy
    me = ob.data
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.meshes.remove(me)


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    only = args[args.index("--only") + 1].split(",") if "--only" in args else ["ground", "water", "sea", "backdrop", "barrier"]
    V.reset_scene()
    layout, G, s = L.build()
    report = []
    if "ground" in only:
        import glob
        for old in glob.glob(os.path.join(V.MESHES, "SM_RealmGround_*")):   # (the tiles of an earlier, other-sized map)
            os.remove(old)
        names, faces = [], 0
        for a in build_terrain(G, s):
            for ob in tiles_of(a, "SM_RealmGround", TILE, L.HALF):
                V.export_gltf(ob)
                names.append(ob.name)
                faces += ob["voxel_faces"]
                bpy_remove(ob)
        with open(os.path.join(V.MESHES, "realm_tiles.json"), "w") as f:
            json.dump(names, f)
        report.append("ground %d tiles, %d faces" % (len(names), faces))
    if "water" in only:
        wob = build_water(G).to_object("SM_RealmWater")
        V.export_gltf(wob)
        report.append("water %d faces" % wob["voxel_faces"])
    if "sea" in only:
        sob = split(build_sea(G), "SM_RealmSea", None, drop_below=L.SEA - BV + 0.01)[0]
        sob.name = sob.data.name = "SM_RealmSea"
        V.export_gltf(sob)
        report.append("sea %d faces" % sob["voxel_faces"])
    if "backdrop" in only:
        bob = split(build_backdrop(G), "SM_RealmBackdrop", None, drop_below=L.ZMIN)[0]
        bob.name = bob.data.name = "SM_RealmBackdrop"
        V.export_gltf(bob, collision="none")
        report.append("backdrop %d faces" % bob["voxel_faces"])
    if "barrier" in only:
        V.export_gltf(build_barrier(G), collision="complex")
    print("realm terrain: " + "; ".join(report))
    if "--no-render" not in args:
        V.render(os.path.join(V.PREVIEWS, "realm_terrain.png"), target=(L.C.TARGET[0], L.C.TARGET[1], 0), az=L.C.AZ, el=L.C.EL, dist=640, lens=58,
                 res=(1672, 941), samples=24, ground=False)


main()
