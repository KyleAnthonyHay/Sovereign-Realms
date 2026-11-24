"""Realm v2's ground, water, backdrop and barriers (the third battle map, L_RealmV2). As assets/highland_terrain.py,
which this was written from.

    Blender -b --factory-startup --python Tools/blender/assets/realmv2_terrain.py -- [--no-render] [--only ground,water,sea,barrier]

Reads the plan from realmv2_layout.py (heights, surfaces, the hazard map and the water's levels on the quarter-block
grid) and exports
  SM_RealmV2Ground_<i>_<j>  32 m tiles of the ground, meshed in 64 m blocks (each only as tall as its own ground: the
                          mountain's blocks are 115 m of voxels, the plain's a dozen). Flat faces are joined two by
                          two where nothing tells them apart. Snow is white paint on the heights' treads
  SM_RealmV2Water         every sheet of fresh water at its own level (the rivers, the two reaches above the north
                          falls, the creek's pond, pool and brook) and the falls between them
  SM_RealmV2Sea           the sea round the island, one sheet of 2 m voxels 3400 m square with holes under the land,
                          its flat faces joined (merge_far). Nothing lies beyond it: no backdrop
  SM_RealmV2Barrier       walls nobody sees, half a metre thick, along the edge of the plan's hazard map (the rivers'
                          banks, the creek, the rims of the plateau, the terraces, the bluffs and the towers' hills):
                          the level makes them block pawns only. The bridges, the ramps, the stairs and the slabs
                          over the creek are left open.
The water mesh is exported WITH collision: the level turns it off for everything but the path grid's own queries,
which is how the grid knows where water lies (Source/SovereignRealms/VLGrid.cpp).
"""
import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import voxlib as V
import realmv2_layout as L
from voxlib import Vox, IDS

TILE = 32.0
BLOCK = 64.0         # the ground is meshed in blocks of this size (2 x 2 tiles)
FAR = 1700.0         # the sea reaches this far from the middle (the overview all the way out, panned to the map's edge, sees about 1.7 km)
BV = 2.0             # the sea's voxel
WALL_TOP = 30.0      # the hidden walls' top (they stand where people walk: the upper terrace is at 22 m)
SNOW = "#f2f6fb"
# The ground's further levels of detail (Tools/ue/realmv2_lods.py): the same shape with its flat faces joined into
# quads of up to 1 m (LOD 1) and 4 m (LOD 2). Not a coarser ground: no height changes; see merge_far.
FAR_PASSES = (2, 4)


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


def merge_far(a, vox, passes):
    """The same faces for far away: flat faces of one plane, one way and one material joined two by two, along one
    direction and then the other, `passes` times over (so strips one voxel wide are joined too; 2 passes: quads of up
    to 4 x 4 voxels; 4: of 16 x 16), whatever their tint and corner shading: the joined face takes their mean colour.
    The shape is exactly the ground's; what goes is the block-to-block tint and the shading in the corners, which are a
    pixel or two where these are drawn. Takes mesh_arrays' dict as it comes from the mesher (every face one voxel)."""
    v, uvs, cols, tris, slot, alpha = a["verts"].copy(), a["uvs"].copy(), a["cols"], a["tris"], a["slot"], a["alpha"]
    ok = np.abs(alpha).max(axis=1) < 1e-6
    cols = np.repeat(cols.mean(axis=1, keepdims=True), 4, axis=1)
    F = len(v)
    r = np.arange(F)
    vmin, vmax = v.min(axis=1), v.max(axis=1)
    axis = np.argmin(vmax - vmin, axis=1)
    n = np.cross(v[r, tris[:, 1]] - v[r, tris[:, 0]], v[r, tris[:, 2]] - v[r, tris[:, 0]])
    sign = (n[r, axis] > 0).astype(np.int64)
    UA, VA = np.array([1, 0, 0]), np.array([2, 2, 1])
    dirs = np.stack([UA[axis], VA[axis]], axis=1)                           # each face's two in-plane axes
    q = np.round(vmin / vox).astype(np.int64)
    pos = np.stack([q[r, dirs[:, 0]], q[r, dirs[:, 1]]], axis=1)             # its low corner, in voxels
    plane = (((axis * 2 + sign) * 64 + slot) << 17) + (q[r, axis] + (1 << 16))
    ext = np.ones((F, 2), np.int64)                                         # its size, in voxels
    scale = 1.0 / (V.TEXEL * V.TEX_SIZE)
    O = 1 << 16
    for p in range(passes):
        cur = 1 << p
        for d in (0, 1):
            e = 1 - d
            cand = np.flatnonzero(ok & (ext[:, d] == cur) & (pos[:, d] % cur == 0))
            if len(cand) < 2:
                continue
            key = ((((plane[cand] << 6) + ext[cand, e]) << 17) + (pos[cand, e] + O) << 17) + (pos[cand, d] // (2 * cur) + O)
            half = (pos[cand, d] // cur) & 1
            srt = np.lexsort((half, key))
            order, k = cand[srt], key[srt]
            pair = np.flatnonzero((k[1:] == k[:-1]))
            # (a key has at most two faces: its low and its high half)
            lo, hi = order[pair], order[pair + 1]
            good = (((pos[lo, d] // cur) & 1) == 0) & (((pos[hi, d] // cur) & 1) == 1)
            lo, hi = lo[good], hi[good]
            if len(lo) == 0:
                continue
            ax3 = dirs[lo, d]                                               # the world axis they are joined along
            G = np.arange(len(lo))
            base = v[lo].min(axis=1)
            grow = v[lo].copy()
            far_side = grow[G[:, None], np.arange(4)[None, :], ax3[:, None]] > base[G, ax3][:, None] + 1e-6
            add = np.where(far_side, cur * vox, 0.0)
            grow[G[:, None], np.arange(4)[None, :], ax3[:, None]] += add
            ucol = np.where(ax3 == UA[axis[lo]], 0, 1)
            uvn = uvs[lo].copy()
            uvn[G[:, None], np.arange(4)[None, :], ucol[:, None]] += add * scale
            v[lo] = grow
            uvs[lo] = uvn
            cols[lo] = (cols[lo] + cols[hi]) * 0.5
            ext[lo, d] = 2 * cur
            ok[hi] = False
            dead = np.zeros(len(v), bool)
            dead[hi] = True
            keep = ~dead
            v, uvs, cols, tris, slot, alpha, ok = v[keep], uvs[keep], cols[keep], tris[keep], slot[keep], alpha[keep], ok[keep]
            axis, dirs, pos, plane, ext = axis[keep], dirs[keep], pos[keep], plane[keep], ext[keep]
    return dict(verts=v, uvs=uvs, cols=cols, tris=tris, slot=slot, slots=a["slots"], alpha=alpha)


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
    """The ground's face arrays, block by block (yields one dict per block)."""
    N = L.N
    h = G["h"]
    top = np.round((h - L.ZMIN) / L.CELL).astype(np.int16)                  # number of solid voxels in each column
    # the open sea has no ground of its own (the level puts one flat slab there): only the bed within a few metres of land
    top[G["sea"] & ~dilate(~G["sea"], 14)] = 0
    surf_ids = np.array([IDS["paint" if n == "snow" else n] for n in L.SURF], np.uint8)
    earth = (5 + (L.hash2(np.floor(G["X"] / 1.0), np.floor(G["Y"] / 1.0), 3) * 3)).astype(np.int16)
    hard = np.isin(s, (L.STONE, L.MOSSY, L.SNOW))
    snow = s == L.SNOW
    low = np.minimum.reduce([np.roll(top, 2, 0), np.roll(top, -2, 0), np.roll(top, 2, 1), np.roll(top, -2, 1)])
    cliff = (top - low) >= 9                                                # a drop of more than two metres beside it
    blocky = L.hash2(np.floor(G["X"] / 0.5), np.floor(G["Y"] / 0.5), 7) > 0.72
    mossy_top = cliff & (s == 0) & blocky
    dirt, stone, mossy = IDS["dirt"], IDS["stone"], IDS["mossy_stone"]
    white = np.array(V.rgb(SNOW), np.uint8)
    nb = int(round(BLOCK / L.CELL))
    PAD = 4                                                                 # (even: the tint cells of neighbouring blocks line up)
    for bi in range(0, N, nb):
        for bj in range(0, N, nb):
            i0, i1, j0, j1 = max(bi - PAD, 0), min(bi + nb + PAD, N), max(bj - PAD, 0), min(bj + nb + PAD, N)
            sl = (slice(i0, i1), slice(j0, j1))
            t = top[sl]
            nz = int(t.max()) + 2
            if int(t[bi - i0:bi - i0 + nb, bj - j0:bj - j0 + nb].max()) == 0:
                continue
            K = np.arange(nz, dtype=np.int16)[None, None, :]
            v = Vox(i1 - i0, j1 - j0, nz, L.CELL, origin=(N / 2.0 - i0, N / 2.0 - j0, -L.ZMIN / L.CELL), name="realmv2", seed=4)
            depth = t[:, :, None] - 1 - K                                   # 0 = the surface voxel
            layer = np.where(depth == 0, surf_ids[s[sl]][:, :, None], np.where((depth <= earth[sl][:, :, None]) & ~hard[sl][:, :, None], dirt, stone)).astype(np.uint8)
            layer[(depth == 0) & mossy_top[sl][:, :, None]] = mossy
            v.m[:] = np.where(depth >= 0, layer, 0)
            if snow[sl].any():
                v.c[(depth == 0) & snow[sl][:, :, None]] = white
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
            far1, far2 = merge_far(a, L.CELL, FAR_PASSES[0]), merge_far(a, L.CELL, FAR_PASSES[1])
            a = merge_quads(a, L.CELL)
            print("ground block %d %d: %d faces, %d after joining, %d / %d far" % (bi // nb, bj // nb, before, len(a["verts"]), len(far1["verts"]), len(far2["verts"])))
            yield a, far1, far2


def build_water(G):
    """The fresh water on the quarter-block grid: every sheet a quarter block below its banks, at its own level
    (G["wz"]), and the falls between sheets of different levels. Meshed in 60 m pieces and joined into one mesh."""
    N, vox = L.N, L.CELL
    wz = np.nan_to_num(G["wz"], nan=-1e9)
    z0 = L.WAT - 2.0
    sheets = [(lvl, np.abs(wz - lvl) < 0.01) for lvl in (L.WAT, L.BROOK, L.POND)]
    by = dict(sheets)
    streak = L.hash2(np.floor(G["X"] / 0.25), np.floor(G["Y"] / 0.25), 31) > 0.52
    foam_h = L.hash2(np.floor(G["X"] / 0.25), np.floor(G["Y"] / 0.25), 37) > 0.62
    falls = []
    for hi, lo in ((L.POND, L.BROOK), (L.BROOK, L.WAT)):
        c = (by[lo] & dilate(by[hi], 3)) | (by[hi] & dilate(by[lo], 2))
        falls.append((c, lo, hi, by[lo], dilate(c, 5) & ~c & foam_h))
    wet = dilate(G["wet"], 8)
    nb, PAD = 240, 4
    parts, slots = [], []
    for bi in range(0, N, nb):
        for bj in range(0, N, nb):
            if not wet[bi:bi + nb, bj:bj + nb].any():
                continue
            i0, i1, j0, j1 = max(bi - PAD, 0), min(bi + nb + PAD, N), max(bj - PAD, 0), min(bj + nb + PAD, N)
            sl = (slice(i0, i1), slice(j0, j1))
            top = max([lvl for lvl, m in sheets if m[sl].any()] + [hi for (c, lo, hi, _p, _f) in falls if c[sl].any()] + [L.WAT])
            nz = int((top + 0.5 - z0) / vox)
            zc3 = z0 + (np.arange(nz)[None, None, :] + 0.5) * vox
            w = Vox(i1 - i0, j1 - j0, nz, vox, origin=(N / 2.0 - i0, N / 2.0 - j0, -z0 / vox), name="realmv2_water", seed=2)
            h = G["h"][sl][:, :, None]
            fill = np.zeros(w.m.shape, bool)
            for lvl, m in sheets:
                if m[sl].any():
                    fill |= m[sl][:, :, None] & (zc3 > h) & (zc3 < lvl)
            for (cur, lo, hi, _pool, _foam) in falls:
                if cur[sl].any():
                    fill |= cur[sl][:, :, None] & (zc3 > lo - 0.25) & (zc3 < hi)
            w.m[:] = np.where(fill, IDS["water"], 0)
            for (cur, lo, hi, pool, foam) in falls:                         # white water: streaks down the falls, foam where they land
                if not (cur[sl].any() or foam[sl].any()):
                    continue
                w.where((cur[sl] & streak[sl])[:, :, None] & (zc3 > lo) & (zc3 < hi) & (w.m > 0), "paint", "#eaf6ff")
                w.where((foam[sl] & pool[sl])[:, :, None] & (zc3 > lo - 0.25) & (zc3 < lo) & (w.m > 0), "paint", "#f4fbff")
            a = w.mesh_arrays()
            del w
            if a is None:
                continue
            c = a["verts"].mean(axis=1)
            x0, y0 = -L.HALF + bi * vox, -L.HALF + bj * vox
            keep = (c[:, 0] >= x0) & (c[:, 0] < x0 + nb * vox) & (c[:, 1] >= y0) & (c[:, 1] < y0 + nb * vox)
            # (the water's undersides lie on its bed: nobody ever sees them)
            vv, tt, rr = a["verts"], a["tris"], np.arange(len(a["verts"]))
            keep &= np.cross(vv[rr, tt[:, 1]] - vv[rr, tt[:, 0]], vv[rr, tt[:, 2]] - vv[rr, tt[:, 0]])[:, 2] > -1e-9
            lut = []
            for name in a["slots"]:
                if name not in slots:
                    slots.append(name)
                lut.append(slots.index(name))
            a["slot"] = np.array(lut, np.int32)[a["slot"]]
            parts.append({k: a[k][keep] for k in ("verts", "uvs", "cols", "tris", "slot", "alpha")})
    print("fall curtains: %s cells" % ", ".join(str(int(f[0].sum())) for f in falls))
    j = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    return V.mesh_object("SM_RealmV2Water", j["verts"], j["uvs"], j["cols"], j["tris"], j["slot"], slots, [], None, j["alpha"])


def build_sea(G):
    """The sea: one sheet of 2 m water voxels, its top at the sea's level, with holes under the land; its flat faces
    joined (they are all one plane). -> face arrays."""
    n = int(2 * FAR / BV)
    c = -FAR + (np.arange(n) + 0.5) * BV
    X, Y = np.meshgrid(c, c, indexing="ij")
    sea = Vox(n, n, 1, BV, origin=(n / 2.0, n / 2.0, 1.0 - L.SEA / BV), name="realmv2_sea", seed=6)
    i = np.clip(((X + L.HALF) / L.CELL).astype(int), 0, L.N - 1)
    j = np.clip(((Y + L.HALF) / L.CELL).astype(int), 0, L.N - 1)
    inside = (np.abs(X) < L.HALF) & (np.abs(Y) < L.HALF)
    inland = inside & (G["dc"][i, j] > 6.0)
    sea.m[:, :, 0] = np.where(inland, 0, IDS["water"])
    a = sea.mesh_arrays()
    a["verts"] = a["verts"] + np.array(sea.offset, np.float32)
    v, t, r = a["verts"], a["tris"], np.arange(len(a["verts"]))
    up = np.cross(v[r, t[:, 1]] - v[r, t[:, 0]], v[r, t[:, 2]] - v[r, t[:, 0]])[:, 2] > 1e-9      # (only its top is ever seen)
    a = dict(a, **{k: a[k][up] for k in ("verts", "uvs", "cols", "tris", "slot", "alpha")})
    return merge_far(a, BV, 5)


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
    ob = V.mesh_object("SM_RealmV2Barrier", verts, uvs, cols, tris, np.zeros(F, np.int32), ["stone"], [], None, np.zeros((F, 4), np.float32))
    print("barrier: %d cells of wall (%.0f m), %d quads" % (int(band.sum()), band.sum() * c, F))
    return ob


def bpy_remove(ob):
    import bpy
    me = ob.data
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.meshes.remove(me)


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    only = args[args.index("--only") + 1].split(",") if "--only" in args else ["ground", "water", "sea", "barrier"]
    V.reset_scene()
    layout, G, s = L.build()
    report = []
    if "ground" in only:
        import glob
        for old in glob.glob(os.path.join(V.MESHES, "SM_RealmV2Ground_*")):   # (the tiles of an earlier, other-sized map)
            os.remove(old)
        names, faces, far_faces = [], 0, [0, 0]
        for a, far1, far2 in build_terrain(G, s):
            for ob in tiles_of(a, "SM_RealmV2Ground", TILE, L.HALF):
                V.export_gltf(ob)
                names.append(ob.name)
                faces += ob["voxel_faces"]
                bpy_remove(ob)
            for k, far in enumerate((far1, far2)):
                for ob in tiles_of(far, "SM_RealmV2Ground", TILE, L.HALF):
                    ob.name = ob.data.name = ob.name + "_L%d" % (k + 1)
                    V.export_gltf(ob, collision="none")
                    far_faces[k] += ob["voxel_faces"]
                    bpy_remove(ob)
        with open(os.path.join(V.MESHES, "realmv2_tiles.json"), "w") as f:
            json.dump(names, f)
        report.append("ground %d tiles, %d faces (LOD 1: %d, LOD 2: %d)" % (len(names), faces, far_faces[0], far_faces[1]))
    if "water" in only:
        wob = build_water(G)
        V.export_gltf(wob)
        report.append("water %d faces" % wob["voxel_faces"])
    if "sea" in only:
        a = build_sea(G)
        sob = V.mesh_object("SM_RealmV2Sea", a["verts"], a["uvs"], a["cols"], a["tris"], a["slot"], list(a["slots"]), [], None, a["alpha"])
        V.export_gltf(sob)
        report.append("sea %d faces" % sob["voxel_faces"])
    if "barrier" in only:
        V.export_gltf(build_barrier(G), collision="complex")
    print("realmv2 terrain: " + "; ".join(report))
    if "--no-render" not in args:
        V.render(os.path.join(V.PREVIEWS, "realmv2_terrain.png"), target=(L.C.TARGET[0], L.C.TARGET[1], 0), az=L.C.AZ, el=L.C.EL, dist=990, lens=58,
                 res=(1672, 941), samples=24, ground=False)


main()
