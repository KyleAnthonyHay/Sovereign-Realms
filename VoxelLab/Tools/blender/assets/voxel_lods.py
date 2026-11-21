"""Coarser levels of detail for the units' parts and the buildings: SourceArt/Meshes/LOD/<mesh>_L1.gltf (_L2.gltf).

    Blender -b --factory-startup --python Tools/blender/assets/voxel_lods.py -- [--set units,buildings] [--only SM_Archer_Head,SM_Castle] [--render]

A swordsman is 63k triangles (his head alone 19k: bevelled cubes of 1.25 cm), a barracks 139k; far away each is a few
dozen pixels. Every mesh is read back from its own exported file (SourceArt/Meshes/<mesh>.gltf, so the scripts that
made it do not have to be run again) and built again out of plain cubes on a coarser grid:

    units       LOD 1 of 2.5 cm cubes (2 u), LOD 2 of 5 cm cubes (4 u)
    buildings   LOD 1 of 0.25 m cubes (their voxel is 0.125 m)

How (rebuild): the mesh's surface is sampled into a fine grid (a quarter of the new cube), the outside is flooded from
the border, and what the flood cannot reach is the solid. A cube of the new grid is solid where half of it is. What is
thinner than a cube (a bow string, a cape's panel, a blade, a banner) would be lost by that, or come out two cubes
thick where it straddles two: each thin run of cells is given whole to the cube that holds its middle, so a panel
stays one cube thick and a string stays a string. Each face takes the mean colour (with the baked shading), the
commonest material and the wind weight (vertex alpha) of the surface it stands for; a level uses only the material
slots of the mesh it is made from, under the same names, so the engine maps them to the same slots.

Tools/ue/voxel_lods.py makes these the LODs of the meshes in the editor (and decides where each is drawn);
SourceArt/Meshes/LOD/lods.json is the list it reads.
"""
import json
import os
import sys
import time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import voxlib as V

import bpy

OUT = os.path.join(V.MESHES, "LOD")
U = 0.0125
UNITS = ["SM_KingB", "SM_Swordsman", "SM_Archer", "SM_Spy", "SM_Builder"]          # SourceArt/Meshes/<name>.json: their parts
BUILDINGS = ["SM_Castle", "SM_TownHall", "SM_Barracks", "SM_BarracksYard", "SM_ArcheryHall", "SM_ArcheryRange", "SM_WatchTower",
             "SM_MineCliff", "SM_Farmstead", "SM_Farmstead_A", "SM_Farmstead_B", "SM_Farmstead_C", "SM_FarmCottage_A",
             "SM_FarmCottage_B", "SM_Dock", "SM_Windmill", "SM_Bridge", "SM_Treasury"]
LEVELS = {"units": [2 * U, 4 * U], "buildings": [0.25]}        # the cube of each level
TOL = {"units": 0.04, "buildings": 0.03}       # how unlike (square root of the linear colour) two faces joined into one may be
K = 4                           # fine cells along a cube's edge
WORTH = 0.75                    # a level is kept where it has at most this share of the triangles of the level before


def read(path):
    """-> corners (T, 3, 3), their colours (T, 3, 4) linear + alpha, uvs (T, 3, 2), slot of each triangle (T,), slot names"""
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
    col = np.ones((T, 3, 4), np.float32)
    attr = me.color_attributes[0] if len(me.color_attributes) else None
    if attr is not None:
        size = len(me.loops) if attr.domain == "CORNER" else len(me.vertices)
        raw = np.zeros(size * 4, np.float32)
        attr.data.foreach_get("color", raw)
        col = raw.reshape(-1, 4)[tl if attr.domain == "CORNER" else tv].reshape(T, 3, 4)
    uv = np.zeros((T, 3, 2), np.float32)
    if len(me.uv_layers):
        raw = np.zeros(len(me.loops) * 2, np.float32)
        me.uv_layers[0].data.foreach_get("uv", raw)
        uv = raw.reshape(-1, 2)[tl].reshape(T, 3, 2)
    names = [s.material.name.split(".")[0].replace("MI_Vox_", "").replace("Vox_", "") if s.material else "paint" for s in ob.material_slots] or ["paint"]
    return co[tv].reshape(T, 3, 3), col, uv, np.clip(mi, 0, len(names) - 1), names


def samples(P, col, mat, step):
    """Points all over the triangles, no further apart than step: -> position, normal, colour + alpha, slot, area"""
    e = np.stack([np.linalg.norm(P[:, 1] - P[:, 0], axis=1), np.linalg.norm(P[:, 2] - P[:, 1], axis=1), np.linalg.norm(P[:, 0] - P[:, 2], axis=1)], axis=1)
    n = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
    area = np.linalg.norm(n, axis=1) * 0.5
    n = n / np.maximum(area[:, None] * 2.0, 1e-12)
    m = np.clip(np.ceil(e.max(axis=1) / step), 1, 512).astype(np.int32)
    out = [[], [], [], [], []]
    for mm in np.unique(m):
        I = np.nonzero((m == mm) & (area > 1e-12))[0]
        if not len(I):
            continue
        b = [((i + 1 / 3) / mm, (j + 1 / 3) / mm) for i in range(mm) for j in range(mm - i)]
        b += [((i + 2 / 3) / mm, (j + 2 / 3) / mm) for i in range(mm - 1) for j in range(mm - 1 - i)]
        b = np.array(b, np.float32)
        w = np.stack([1.0 - b[:, 0] - b[:, 1], b[:, 0], b[:, 1]], axis=1)             # (S, 3)
        for lo in range(0, len(I), max(1, 2000000 // len(b))):
            J = I[lo:lo + max(1, 2000000 // len(b))]
            out[0].append(np.einsum("sk,tkc->tsc", w, P[J]).reshape(-1, 3))
            out[1].append(np.repeat(n[J], len(b), axis=0))
            out[2].append(np.einsum("sk,tkc->tsc", w, col[J]).reshape(-1, 4))
            out[3].append(np.repeat(mat[J], len(b)))
            out[4].append(np.repeat(area[J] / len(b), len(b)))
    return [np.concatenate(o) for o in out]


def shift(a, axis, d):
    """a moved d cells along axis (what leaves is lost, what comes in is False / 0)"""
    out = np.zeros_like(a)
    src = [slice(None)] * 3
    dst = [slice(None)] * 3
    if d > 0:
        src[axis], dst[axis] = slice(0, -d), slice(d, None)
    elif d < 0:
        src[axis], dst[axis] = slice(-d, None), slice(0, d)
    out[tuple(dst)] = a[tuple(src)]
    return out


def flood_outside(solid):
    """The cells the border can reach without crossing a solid one (6 neighbours)."""
    n = solid.shape
    blocked = np.ones((n[0] + 2, n[1] + 2, n[2] + 2), bool)
    blocked[1:-1, 1:-1, 1:-1] = solid
    seen = np.zeros(blocked.shape, bool)
    border = np.zeros(blocked.shape, bool)
    border[1:-1, 1:-1, 1:-1] = True
    border[2:-2, 2:-2, 2:-2] = False
    start = border & ~blocked
    seen |= start
    flat_blocked = blocked.reshape(-1)
    flat_seen = seen.reshape(-1)
    front = np.flatnonzero(start.reshape(-1))
    sy, sx = n[2] + 2, (n[1] + 2) * (n[2] + 2)
    while len(front):
        nb = np.concatenate([front + 1, front - 1, front + sy, front - sy, front + sx, front - sx])
        nb = nb[~flat_blocked[nb] & ~flat_seen[nb]]
        nb = np.unique(nb)
        flat_seen[nb] = True
        front = nb
    return seen[1:-1, 1:-1, 1:-1]


def run_middle(solid, axis, k):
    """For each cell the cube (along axis) it counts for: its own, or, in a run of solid cells shorter than k, the
    cube that holds the run's middle."""
    n = solid.shape[axis]
    shape = [1, 1, 1]
    shape[axis] = n
    idx = np.broadcast_to(np.arange(n, dtype=np.int32).reshape(shape), solid.shape)
    start = np.maximum.accumulate(np.where(solid, 0, idx + 1), axis=axis)
    rev = np.flip(solid, axis)
    end = n - 1 - np.flip(np.maximum.accumulate(np.where(rev, 0, idx + 1), axis=axis), axis)
    return np.where(end - start + 1 < k, (start + end) // 2, idx) // k


def coarse_solid(filled, k):
    """Which cubes (k fine cells a side) are solid: -> (n / k) bools"""
    n = tuple(s // k for s in filled.shape)
    fill = filled.reshape(n[0], k, n[1], k, n[2], k).sum(axis=(1, 3, 5))
    solid = fill * 2 >= k ** 3
    # thin things: what no cube of k cells fits in (the opening takes it away), further than k / 2 from what stays
    er = filled
    for ax in range(3):
        acc = er.copy()
        for d in range(1, k):
            acc &= shift(er, ax, -d)
        er = acc
    op = er
    for ax in range(3):
        acc = op.copy()
        for d in range(1, k):
            acc |= shift(op, ax, d)
        op = acc
    near = op
    r = k // 2
    for ax in range(3):
        acc = near.copy()
        for d in range(1, r + 1):
            acc |= shift(near, ax, d) | shift(near, ax, -d)
        near = acc
    thin = filled & ~near
    if thin.any():
        t = [run_middle(filled, ax, k)[thin] for ax in range(3)]
        flat = (t[0].astype(np.int64) * n[1] + t[1]) * n[2] + t[2]
        count = np.bincount(flat, minlength=n[0] * n[1] * n[2]).reshape(n)
        solid |= count >= 2
    return solid


def greedy(present, rgb, slot, flat, tol):
    """Rectangles covering the faces of one layer: cells with the same slot and wind weight whose colour is within
    tol of the first one's (compared as the eye does: the square root). -> (u0, v0, w, h, mean colour, slot)"""
    g = np.sqrt(np.clip(rgb, 0.0, None))
    free = present.copy()
    nu, nv = present.shape
    out = []
    for u0, v0 in np.argwhere(present):
        if not free[u0, v0]:
            continue
        s0, a0, c0 = slot[u0, v0], flat[u0, v0], g[u0, v0]
        row = free[u0, v0:] & (slot[u0, v0:] == s0) & (flat[u0, v0:] == a0) & (np.abs(g[u0, v0:] - c0).max(axis=-1) <= tol)
        h = int(np.argmin(row)) if not row.all() else len(row)
        w = 1
        while u0 + w < nu:
            sl = slice(v0, v0 + h)
            if not (free[u0 + w, sl] & (slot[u0 + w, sl] == s0) & (flat[u0 + w, sl] == a0) & (np.abs(g[u0 + w, sl] - c0).max(axis=-1) <= tol)).all():
                break
            w += 1
        free[u0:u0 + w, v0:v0 + h] = False
        out.append((u0, v0, w, h, rgb[u0:u0 + w, v0:v0 + h].reshape(-1, 3).mean(axis=0), s0))
    return out


DIRS = [(0, 1), (0, -1), (1, 1), (1, -1), (2, 1), (2, -1)]


def rebuild(name, v, level, src, tol):
    """One level of one mesh -> the Blender object (or None where nothing is left), its triangle count"""
    P, col, uv, mat, slots = src
    f = v / K
    # the source's own grid (a building's voxels): the new cubes sit on it
    half = v / 2.0
    flat = P.reshape(-1, 3)
    off = np.zeros(3, np.float32)
    for ax in range(3):
        q = np.round(np.mod(flat[:, ax], half) / half * 16.0).astype(np.int64) % 16
        off[ax] = np.bincount(q, minlength=16).argmax() / 16.0 * half
    lo = off + np.floor((flat.min(axis=0) - off) / v) * v - v
    n = tuple(int(x) for x in np.ceil((flat.max(axis=0) - lo) / v).astype(np.int64) + 2)
    nf = tuple(x * K for x in n)
    sp, sn, sc, sm, sw = samples(P, col, mat, f * 0.5)
    cell = np.floor((sp - sn * (f * 0.25) - lo) / f).astype(np.int64)
    cell = np.clip(cell, 0, np.array(nf) - 1)
    shell = np.zeros(nf, bool)
    shell[cell[:, 0], cell[:, 1], cell[:, 2]] = True
    outside = flood_outside(shell)
    filled = ~outside
    solid = coarse_solid(filled, K)
    if not solid.any():
        return None, 0
    # what each cube's faces look like: from the samples that the outside sees
    oc = np.clip(np.floor((sp + sn * (f * 0.75) - lo) / f).astype(np.int64), 0, np.array(nf) - 1)
    seen = outside[oc[:, 0], oc[:, 1], oc[:, 2]]
    if seen.sum() < 0.05 * len(seen):
        seen[:] = True
    cb = (cell[seen] // K)
    ax = np.abs(sn[seen]).argmax(axis=1)
    d = ax * 2 + (sn[seen][np.arange(len(ax)), ax] < 0)
    w = sw[seen].astype(np.float64)
    nm = len(slots)
    C = 5 + nm                                              # weight, r, g, b, alpha, a vote per slot
    N = n[0] * n[1] * n[2]
    key = ((cb[:, 0] * n[1] + cb[:, 1]) * n[2] + cb[:, 2]) * 6 + d
    D = np.zeros((N * 6, C), np.float64)
    D[:, 0] = np.bincount(key, weights=w, minlength=N * 6)
    for c in range(4):
        D[:, 1 + c] = np.bincount(key, weights=w * sc[seen][:, c], minlength=N * 6)
    votes = np.bincount(key * nm + sm[seen], weights=w, minlength=N * 6 * nm).reshape(N * 6, nm)
    D[:, 5:] = votes
    D = D.reshape(n + (6, C))
    A = D.sum(axis=3)                                       # all directions
    G = A.copy()                                            # ... spread to the cubes with nothing of their own
    for _ in range(10):
        empty = G[..., 0] <= 0
        if not empty.any():
            break
        grow = np.zeros_like(G)
        for axx in range(3):
            grow += shift(G, axx, 1) + shift(G, axx, -1)
        G = np.where(empty[..., None], grow, G)
    total = A.reshape(-1, C).sum(axis=0)
    # wind weight at the grid's corners (so that neighbouring faces move together): the mean of the cubes around
    Gp = np.pad(G[..., [0, 4]], ((1, 1), (1, 1), (1, 1), (0, 0)))
    corner = np.zeros((n[0] + 1, n[1] + 1, n[2] + 1, 2))
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                corner += Gp[dx:dx + n[0] + 1, dy:dy + n[1] + 1, dz:dz + n[2] + 1]
    corner_alpha = np.where(corner[..., 0] > 0, corner[..., 1] / np.maximum(corner[..., 0], 1e-12), total[4] / max(total[0], 1e-12))
    e = np.abs(P[:, 1] - P[:, 0]).sum(axis=1)
    ue = np.abs(uv[:, 1] - uv[:, 0]).sum(axis=1)
    ok = e > 1e-6
    uv_scale = float(np.median(ue[ok] / e[ok])) if ok.any() else 1.0
    Vt, UVt, Ct, St, At = [], [], [], [], []
    sp_ = np.pad(solid, 1)
    for di, (axis, sign) in enumerate(DIRS):
        dd = [0, 0, 0]
        dd[axis] = sign
        nb = sp_[1 + dd[0]:1 + dd[0] + n[0], 1 + dd[1]:1 + dd[1] + n[1], 1 + dd[2]:1 + dd[2] + n[2]]
        face = solid & ~nb
        idx = np.argwhere(face)
        if not len(idx):
            continue
        F = len(idx)
        out_ = np.clip(idx + np.array(dd), 0, np.array(n) - 1)
        in_ = np.clip(idx - np.array(dd), 0, np.array(n) - 1)
        acc = D[idx[:, 0], idx[:, 1], idx[:, 2], di]
        for alt in (D[out_[:, 0], out_[:, 1], out_[:, 2], di], D[in_[:, 0], in_[:, 1], in_[:, 2], di], A[idx[:, 0], idx[:, 1], idx[:, 2]],
                    G[idx[:, 0], idx[:, 1], idx[:, 2]], np.broadcast_to(total, (F, C))):
            acc = np.where(acc[:, :1] > 0, acc, alt)
        ua, va = [(1, 2), (0, 2), (0, 1)][axis]
        # faces side by side that look alike become one rectangle (greedy, layer by layer)
        rgb = np.zeros(n + (3,), np.float32)
        rgb[idx[:, 0], idx[:, 1], idx[:, 2]] = acc[:, 1:4] / np.maximum(acc[:, :1], 1e-12)
        slot = np.zeros(n, np.int32)
        slot[idx[:, 0], idx[:, 1], idx[:, 2]] = acc[:, 5:].argmax(axis=1)
        plane = 1 if sign > 0 else 0
        ca = np.moveaxis(corner_alpha, (axis, ua, va), (0, 1, 2))
        fm = np.moveaxis(face, (axis, ua, va), (0, 1, 2))
        rg = np.moveaxis(rgb, (axis, ua, va), (0, 1, 2))
        sl = np.moveaxis(slot, (axis, ua, va), (0, 1, 2))
        rects = []
        for layer in np.unique(idx[:, axis]):
            a4 = ca[layer + plane]
            a4 = np.stack([a4[:-1, :-1], a4[1:, :-1], a4[1:, 1:], a4[:-1, 1:]], axis=-1)
            flat = np.where(np.ptp(a4, axis=-1) < 1e-4, np.round(a4[..., 0] * 1000.0), -1.0 - np.arange(a4[..., 0].size).reshape(a4.shape[:2]))
            for (u0, v0, w, h, c, s) in greedy(fm[layer], rg[layer], sl[layer], flat, tol):
                rects.append((layer, u0, v0, w, h, c[0], c[1], c[2], s))
        R = np.array(rects, np.float64)
        F = len(R)
        pos = np.zeros((F, 4, 3), np.float32)
        for kk, (cu, cv) in enumerate([(0, 0), (1, 0), (1, 1), (0, 1)]):
            pos[:, kk, axis] = R[:, 0] + plane
            pos[:, kk, ua] = R[:, 1] + cu * R[:, 3]
            pos[:, kk, va] = R[:, 2] + cv * R[:, 4]
        right_handed = (axis, ua, va) in ((0, 1, 2), (2, 0, 1))
        pos = pos[:, [0, 1, 2, 3] if (right_handed == (sign > 0)) else [0, 3, 2, 1]]
        pi = np.round(pos).astype(np.int64)
        world = pos * v + lo
        Vt.append(world)
        UVt.append(np.stack([world[:, :, ua], world[:, :, va]], axis=-1) * uv_scale)
        Ct.append(np.repeat(R[:, None, 5:8], 4, axis=1).astype(np.float32))
        St.append(R[:, 8].astype(np.int32))
        At.append(corner_alpha[pi[..., 0], pi[..., 1], pi[..., 2]])
    verts = np.concatenate(Vt)
    F = len(verts)
    tris = np.tile(np.array([0, 1, 2, 0, 2, 3]), (F, 1))
    V.reset_scene()
    ob = V.mesh_object("%s_L%d" % (name, level), verts, np.concatenate(UVt), np.concatenate(Ct), tris, np.concatenate(St).astype(np.int32),
                       list(slots), [], None, np.concatenate(At).astype(np.float32))
    return ob, F * 2


def unit_meshes(kind):
    with open(os.path.join(V.MESHES, kind + ".json")) as fh:
        return [d["mesh"] for d in json.load(fh)["parts"].values()]


def render(only):
    """SourceArt/Previews/lods_<unit>.png: each unit as exported and at each level, side by side."""
    with open(os.path.join(OUT, "lods.json")) as fh:
        book = json.load(fh)
    for kind in UNITS:
        with open(os.path.join(V.MESHES, kind + ".json")) as fh:
            parts = json.load(fh)["parts"]
        if only and not any(d["mesh"] in only for d in parts.values()):
            continue
        V.reset_scene()
        for col_i in range(3):
            for d in parts.values():
                levels = book.get(d["mesh"], {}).get("levels", [])
                path = os.path.join(V.MESHES, d["mesh"] + ".gltf")
                for lv in levels:
                    if lv["level"] <= col_i:
                        path = os.path.join(OUT, lv["file"])
                if not os.path.exists(path):
                    continue
                bpy.ops.import_scene.gltf(filepath=path)
                for o in bpy.context.selected_objects:
                    o.location = (d["pivot"][0] + col_i * 1.6, d["pivot"][1], d["pivot"][2])
        V.render(os.path.join(V.PREVIEWS, "lods_%s.png" % kind), target=(1.6, 0, 0.9), az=-25, el=12, dist=9.0, lens=85, res=(2400, 1100), samples=16)
        V.reset_scene()
        for col_i in range(3):
            for d in parts.values():
                levels = book.get(d["mesh"], {}).get("levels", [])
                path = os.path.join(V.MESHES, d["mesh"] + ".gltf")
                for lv in levels:
                    if lv["level"] <= col_i:
                        path = os.path.join(OUT, lv["file"])
                if not os.path.exists(path):
                    continue
                bpy.ops.import_scene.gltf(filepath=path)
                for o in bpy.context.selected_objects:
                    o.location = (d["pivot"][0] + col_i * 1.6, d["pivot"][1], d["pivot"][2])
        V.render(os.path.join(V.PREVIEWS, "lods_%s_back.png" % kind), target=(1.6, 0, 0.9), az=155, el=12, dist=9.0, lens=85, res=(2400, 1100), samples=16)
    for name in BUILDINGS:
        if (only and name not in only) or name not in book or not book[name]["levels"]:
            continue
        V.reset_scene()
        with open(os.path.join(V.MESHES, name + ".json")) as fh:
            b = json.load(fh)["bounds"]
        wide = b[1][0] - b[0][0] + 2.0
        for i, path in enumerate([os.path.join(V.MESHES, name + ".gltf"), os.path.join(OUT, book[name]["levels"][0]["file"])]):
            bpy.ops.import_scene.gltf(filepath=path)
            for o in bpy.context.selected_objects:
                o.location.x += i * wide
        V.render(os.path.join(V.PREVIEWS, "lods_%s.png" % name), target=(wide / 2.0, 0, (b[1][2] + b[0][2]) / 2.0), az=-25, el=25, dist=wide * 4.0, lens=85,
                 res=(2400, 1100), samples=16)


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    sets = args[args.index("--set") + 1].split(",") if "--set" in args else ["units", "buildings"]
    only = args[args.index("--only") + 1].split(",") if "--only" in args else None
    os.makedirs(OUT, exist_ok=True)
    book_path = os.path.join(OUT, "lods.json")
    book = {}
    if os.path.exists(book_path):
        with open(book_path) as fh:
            book = json.load(fh)
    todo = []
    for s in sets:
        names = [m for k in UNITS for m in unit_meshes(k)] if s == "units" else list(BUILDINGS)
        todo += [(s, m) for m in names if not only or m in only]
    t0 = time.time()
    for s, name in todo:
        path = os.path.join(V.MESHES, name + ".gltf")
        if not os.path.exists(path):
            print("LOD %s: no %s" % (name, path))
            continue
        src = read(path)
        before = len(src[0])
        entry = dict(set=s, triangles=before, levels=[])
        last = before
        for i, v in enumerate(LEVELS[s]):
            ob, tris = rebuild(name, v, i + 1, src, TOL[s])
            if ob is None or tris > WORTH * last:
                continue                                    # (a hand of 300 triangles: nothing to gain; the next level may)
            file = "%s_L%d.gltf" % (name, i + 1)
            V.export_gltf(ob, path=os.path.join(OUT, file), collision="none", extra=dict(lod_of=name, voxel=v, triangles=tris))
            entry["levels"].append(dict(level=i + 1, file=file, voxel=v, triangles=tris, slots=[m.name.replace("Vox_", "") for m in ob.data.materials]))
            last = tris
        book[name] = entry
        print("LOD %s: %d triangles -> %s (slots %s)" % (name, before, ", ".join("L%d %d" % (lv["level"], lv["triangles"]) for lv in entry["levels"]) or "kept as it is", src[4]))
    with open(book_path, "w") as fh:
        json.dump(book, fh, indent=1)
    done = [book[m] for _, m in todo if m in book]
    print("LOD total: %d meshes, %d triangles -> L1 %d, L2 %d (%.0f s)" % (
        len(done), sum(e["triangles"] for e in done),
        sum(next((lv["triangles"] for lv in e["levels"] if lv["level"] == 1), e["triangles"]) for e in done),
        sum(min([lv["triangles"] for lv in e["levels"]] + [e["triangles"]]) for e in done), time.time() - t0))
    if "--render" in args:
        render(only)


main()
