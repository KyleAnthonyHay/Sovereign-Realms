"""Prop and structure meshes for the world generator (gen_battlefield.py): firs, grass cards, boulders, the gold vein,
standing stones, fences, logs, the old kingdom's ruins, watch posts, and the landmarks (the colossus, obelisks, the
wyrm's bones, the field of swords, barrows, jetties). Everything is built from the same few pieces (boxes, prisms,
convex-hull rocks) in the materials' conventions (meshlib.py): no art is drawn here, only shapes that take the
existing pixel-art textures.
"""
import math

import numpy as np
from scipy.spatial import ConvexHull

from meshlib import Mesh, planar_uv

TEXEL = 4.0
rng = np.random.default_rng(20262)


def U(a, b):
    return float(rng.uniform(a, b))


def hull_rock(name, size, points=16, seed=0, flat_base=True, into=None, offset=(0, 0, 0), yaw=0.0):
    """Chunky faceted boulder: the convex hull of a few jittered points, flat shaded, planar UVs per facet."""
    r = np.random.default_rng(seed)
    sx, sy, sz = size
    v = r.normal(size=(points, 3))
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    v *= r.uniform(0.78, 1.0, size=(points, 1))
    v[:, :2] /= np.maximum(np.linalg.norm(v[:, :2], axis=1, keepdims=True), 0.4) ** 0.55    # steep sides, flatter crown
    v[:, 2] = np.clip(v[:, 2], -0.35, 1.0)                       # sits on the ground, not a ball
    v = v * np.array([sx, sy, sz * 1.25]) * 0.5
    v[:, 2] -= v[:, 2].min() + 6.0
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    rot = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    v = v @ rot.T + np.array(offset)
    hull = ConvexHull(v)
    m = into if into is not None else Mesh(name)
    uvo = (float(r.uniform(0, 256)), float(r.uniform(0, 256)))
    for simplex, eq in zip(hull.simplices, hull.equations):
        p0, p1, p2 = v[simplex[0]], v[simplex[1]], v[simplex[2]]
        n = eq[:3]
        if np.dot(np.cross(p1 - p0, p2 - p0), n) < 0:
            p1, p2 = p2, p1
        uvs = [np.asarray(planar_uv(p, n)) + uvo for p in (p0, p1, p2)]
        m.flat_tri(p0, p1, p2, uvs=uvs, normal=n)
    return m


def conifer(name, height, radius, seed, lod=0):
    """Layered fir: drooping bough skirts over a dark core, one mesh, one material.
    UV0 in cm for the needle / bark textures. UV1 = (shade 0..1, sway weight). COLOR.b = 1 on bark.
    lod 1: every other tier (each twice as deep) and six-sided, for the far view."""
    r = np.random.default_rng(seed)
    m = Mesh(name)
    bare = height * 0.13
    trunk_r = max(height * 0.02, 9.0)
    NEED_W, NEED_H = 64 * TEXEL, 48 * TEXEL
    # trunk (bark): hexagonal, runs up inside the boughs
    sides = 6 if lod == 0 else 4
    top_z = height * 0.55
    for i in range(sides):
        a0, a1 = 2 * math.pi * i / sides, 2 * math.pi * (i + 1) / sides
        circ = 2 * math.pi * trunk_r
        for (za, zb, ra, rb) in [(-12.0, top_z, trunk_r * 1.15, trunk_r * 0.6)]:
            p = [(math.cos(a0) * ra, math.sin(a0) * ra, za), (math.cos(a1) * ra, math.sin(a1) * ra, za),
                 (math.cos(a1) * rb, math.sin(a1) * rb, zb), (math.cos(a0) * rb, math.sin(a0) * rb, zb)]
            nn = [(math.cos(a), math.sin(a), 0.15) for a in (a0, a1, a1, a0)]
            uv = [(circ * i / sides, -za), (circ * (i + 1) / sides, -za), (circ * (i + 1) / sides, -zb), (circ * i / sides, -zb)]
            ids = [m.vert(pp, n_, u_, (0.85, 0.0), (1, 1, 1, 1)) for pp, n_, u_ in zip(p, nn, uv)]
            m.quad(*ids)
    # bough tiers, bottom to top
    tiers = max(int(round((height - bare) / (62.0 if lod == 0 else 150.0))), 4 if lod == 0 else 3)
    dz = (height - bare) / (tiers + 0.6)
    for t in range(tiers):
        f = t / float(tiers - 1)
        rim_r = radius * (1.0 - f) ** 0.85 + radius * 0.07
        rim_r *= float(r.uniform(0.84, 1.12)) * (1.06 if t % 2 else 0.95)
        z_rim = bare + t * dz - dz * 0.25 * (1.0 - f)                 # lower boughs droop more
        z_top = bare + t * dz + dz * 1.55
        top_r = rim_r * 0.22
        if t == tiers - 1:
            top_r, z_top = 0.5, height
        slant = math.hypot(rim_r - top_r, z_top - z_rim)
        segs = (11 if rim_r > 90 else (9 if rim_r > 45 else 7)) if lod == 0 else 6
        reps = max(int(round(2 * math.pi * rim_r / NEED_W)), 1)
        u_off = float(r.uniform(0, NEED_W))
        v_rim = NEED_H - 0.5 * TEXEL
        v_top = max(v_rim - slant, 0.0)
        shade_rim = 0.72 + 0.28 * f                                   # dark base, lit crown
        shade_top = shade_rim * 0.25                                  # under the tier above
        rot = float(r.uniform(0, 2 * math.pi))
        for i in range(segs):
            ids = []
            for a_i, rad, z, v_, sh in [(i, rim_r, z_rim, v_rim, shade_rim), (i + 1, rim_r, z_rim, v_rim, shade_rim),
                                        (i + 1, top_r, z_top, v_top, shade_top), (i, top_r, z_top, v_top, shade_top)]:
                a = rot + 2 * math.pi * a_i / segs
                wob = 1.0 + ((0.13 if a_i % 2 else -0.09) + 0.05 * math.sin(a_i * 2.3 + t) if rad == rim_r else 0.0)
                nx, ny = math.cos(a), math.sin(a)
                nvec = np.array([nx * 0.78, ny * 0.78, 0.62])
                nvec /= np.linalg.norm(nvec)
                ids.append(m.vert((nx * rad * wob, ny * rad * wob, z), nvec,
                                  (u_off + NEED_W * reps * a_i / segs, v_), (sh, min(z / height, 1.0)), (1, 1, 0, 1)))
            m.quad(*ids)
    return m



# ---------------------------------------------------------------------------------------- broadleaves (the woods)
LEAF_W, LEAF_H = 64 * TEXEL, 48 * TEXEL


def leaf_clump(m, r, centre, rad, rise, segs, shade, sway, height):
    """One clump of a broadleaf crown: three short skirts of leaves one over another, closing to a cap (a fir's bough
    tiers, rounded into a dome). Each skirt is the leaf texture laid like T_Needles (v from under the skirt above to
    its own ragged hanging rim), wrapped as many times as its own girth needs, so the leaves keep their size and
    never draw out into streaks toward the top. UV1 = (shade, sway weight); COLOR.b = 0 (leaves)."""
    cx, cy, cz = centre
    v_rim = LEAF_H - 0.5 * TEXEL
    # (rim radius, rim height, top radius, top height) as shares of the clump's radius and rise
    tiers = [(1.0, 0.0, 0.66, 0.58), (0.74, 0.4, 0.38, 0.88), (0.46, 0.72, 0.0, 1.0)]
    for t, (fr0, fz0, fr1, fz1) in enumerate(tiers):
        n = max(segs - 2 * t, 5)
        rot = float(r.uniform(0, 2 * math.pi))
        r0, r1 = rad * fr0, rad * fr1
        z0, z1 = cz + rise * fz0, cz + rise * fz1
        slant = math.hypot(r0 - r1, z1 - z0)
        reps = max(int(round(2 * math.pi * r0 / LEAF_W)), 1)
        u_off = float(r.uniform(0, LEAF_W))
        v_top = max(v_rim - slant, 0.0)
        sh_rim, sh_top = shade * (0.66 + 0.17 * t), shade * (0.5 + 0.17 * t)        # lit rims over the shade under each skirt
        if t == len(tiers) - 1:
            sh_top = shade
        for i in range(n):
            ids = []
            for a_i, rr, z, v_, sh in [(i, r0, z0, v_rim, sh_rim), (i + 1, r0, z0, v_rim, sh_rim), (i + 1, r1, z1, v_top, sh_top), (i, r1, z1, v_top, sh_top)]:
                a = rot + 2 * math.pi * a_i / n
                rim = rr == r0
                wob = 1.0 + ((0.14 if a_i % 2 else -0.1) + 0.06 * math.sin(a_i * 2.3 + t) if rim else 0.0)
                dip = -rise * 0.07 * (1 if a_i % 2 else -1) if rim else 0.0
                nx, ny = math.cos(a), math.sin(a)
                nvec = np.array([nx * 0.7, ny * 0.7, 0.5 + 0.35 * t])
                nvec /= np.linalg.norm(nvec)
                ids.append(m.vert((cx + nx * rr * wob, cy + ny * rr * wob, z + dip), nvec, (u_off + LEAF_W * reps * a_i / n, v_),
                                  (sh, min(max(z / height, 0.0), 1.0) * sway), (1, 1, 0, 1)))
            m.quad(*ids)


def bark_limb(m, c0, c1, r0, r1, sides=6):
    """A tapering trunk or bough between two points (smooth shaded, bark: COLOR.b = 1)."""
    c0, c1 = np.asarray(c0, float), np.asarray(c1, float)
    ax = c1 - c0
    ln = float(np.linalg.norm(ax))
    ax /= max(ln, 1e-6)
    ref = np.array([0.0, 0.0, 1.0]) if abs(ax[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    u = np.cross(ax, ref); u /= np.linalg.norm(u)
    v = np.cross(ax, u)
    circ = 2 * math.pi * r0
    for i in range(sides):
        ids = []
        for a_i, c, rr, vv in [(i, c0, r0, 0.0), (i + 1, c0, r0, 0.0), (i + 1, c1, r1, ln), (i, c1, r1, ln)]:
            a = 2 * math.pi * a_i / sides
            d = u * math.cos(a) + v * math.sin(a)
            ids.append(m.vert(c + d * rr, d, (circ * a_i / sides, -vv), (0.85, 0.0), (1, 1, 1, 1)))
        m.quad(*ids)


def broadleaf(name, height, radius, seed, form="oak", lod=0):
    """A broadleaf tree in the firs' idiom: a bark trunk and boughs under a crown of leafy clumps. form: 'oak' (a wide
    round head), 'maple' (a tall egg), 'birch' (slender, the white stem showing between small clumps). lod 1: fewer,
    coarser clumps for the far view."""
    r = np.random.default_rng(seed)
    m = Mesh(name)
    segs = 9 if lod == 0 else 6
    if form == "birch":
        bare, trunk_r = height * 0.24, max(height * 0.016, 7.0)
        lean = (float(r.uniform(-0.05, 0.05)) * height, float(r.uniform(-0.05, 0.05)) * height)
        bark_limb(m, (0, 0, -12), (lean[0], lean[1], height * 0.86), trunk_r * 1.2, trunk_r * 0.35)
        n = 7 if lod == 0 else 4
        for k in range(n):
            f = k / float(n - 1)
            z = bare + (height * 0.93 - bare) * f
            rr = radius * (0.62 + 0.5 * math.sin(math.pi * min(f * 1.15, 1.0))) * float(r.uniform(0.8, 1.1))
            a = float(r.uniform(0, 2 * math.pi))
            off = radius * 0.42 * (1.0 - f)
            leaf_clump(m, r, (lean[0] * f + math.cos(a) * off, lean[1] * f + math.sin(a) * off, z - rr * 0.35), rr, rr * 0.95, segs, 0.62 + 0.38 * f, 1.0, height)
        return m
    tall = 1.0 if form == "oak" else 1.32
    bare = height * (0.26 if form == "oak" else 0.2)
    trunk_r = max(height * 0.03, 12.0)
    fork = height * (0.46 if form == "oak" else 0.5)
    bark_limb(m, (0, 0, -14), (0, 0, fork), trunk_r * 1.25, trunk_r * 0.7, sides=7 if lod == 0 else 5)
    # the lower ring of clumps on boughs out from the fork, then a middle ring, then the crown's cap
    crown_h = height - bare
    rings = [(5 if lod == 0 else 3, 0.62, 0.0, 0.56, 0.6), (4 if lod == 0 else 2, 0.36, 0.34, 0.54, 0.8), (1, 0.0, 0.6, 0.6, 1.0)]
    for count, out, up, size, shade in rings:
        a0 = float(r.uniform(0, 2 * math.pi))
        for k in range(count):
            a = a0 + 2 * math.pi * k / count + float(r.uniform(-0.3, 0.3))
            d = radius * out * float(r.uniform(0.85, 1.12))
            rr = radius * size * float(r.uniform(0.86, 1.14))
            rise = rr * 0.78 * tall
            z = bare + crown_h * up * float(r.uniform(0.9, 1.1)) + (0.0 if count > 1 else 0.0)
            z = min(z, height - rise)
            c = (math.cos(a) * d, math.sin(a) * d, z)
            leaf_clump(m, r, c, rr, rise, segs, shade * float(r.uniform(0.92, 1.0)), 1.0, height)
            if lod == 0 and count > 1:
                bark_limb(m, (0, 0, fork * float(r.uniform(0.78, 1.0))), (c[0] * 0.8, c[1] * 0.8, z + rise * 0.25), trunk_r * 0.5, trunk_r * 0.2, sides=4)
    if lod == 0:
        bark_limb(m, (0, 0, fork), (0, 0, height - radius * 0.3), trunk_r * 0.7, trunk_r * 0.25, sides=5)
    return m


def bush(name, height, radius, seed, lod=0):
    """A shrub: three or four leafy clumps on the ground (no stem worth showing, no blocker)."""
    r = np.random.default_rng(seed)
    m = Mesh(name)
    n = 4 if lod == 0 else 2
    for k in range(n):
        a = 2 * math.pi * k / n + float(r.uniform(-0.4, 0.4))
        d = radius * (0.42 if k else 0.0)
        rr = radius * float(r.uniform(0.55, 0.75)) * (1.15 if k == 0 else 1.0)
        leaf_clump(m, r, (math.cos(a) * d, math.sin(a) * d, height * (0.2 if k else 0.36)), rr, height * (0.55 if k else 0.64), 7 if lod == 0 else 5,
                   0.7 + 0.3 * (k == 0), 0.6, height)
    return m


def snag(name, height, seed):
    """A dead tree: a bare grey-barked stem with a few broken boughs."""
    r = np.random.default_rng(seed)
    m = Mesh(name)
    tr = max(height * 0.035, 12.0)
    top = (float(r.uniform(-30, 30)), float(r.uniform(-30, 30)), height)
    bark_limb(m, (0, 0, -14), top, tr * 1.25, tr * 0.3, sides=6)
    for k in range(4):
        f = 0.42 + 0.13 * k
        a = float(r.uniform(0, 2 * math.pi))
        L = height * float(r.uniform(0.16, 0.3))
        base = (top[0] * f, top[1] * f, height * f)
        bark_limb(m, base, (base[0] + math.cos(a) * L, base[1] + math.sin(a) * L, base[2] + L * float(r.uniform(0.3, 0.8))), tr * 0.4, tr * 0.1, sides=4)
    return m


def tree_lods(build, name, *args, **kw):
    """A tree and its far-view mesh (<name>_LOD1: Tools/import_world_assets.py makes it the first's LOD 1 and drops it)."""
    return [build(name, *args, **kw), build(name + "_LOD1", *args, lod=1, **kw)]


def build_forest_meshes():
    out = []
    for i, (h, rad) in enumerate([(640, 300), (840, 390), (1060, 480)]):
        out += tree_lods(broadleaf, "SM_Tree_Oak_%s" % "ABC"[i], h, rad, 500 + i, form="oak")
    for i, (h, rad) in enumerate([(680, 250), (900, 320)]):
        out += tree_lods(broadleaf, "SM_Tree_Maple_%s" % "AB"[i], h, rad, 520 + i, form="maple")
    for i, (h, rad) in enumerate([(720, 150), (940, 185)]):
        out += tree_lods(broadleaf, "SM_Tree_Birch_%s" % "AB"[i], h, rad, 540 + i, form="birch")
    out.append(snag("SM_Tree_Snag", 560, 560))
    for i, (h, rad) in enumerate([(150, 120), (230, 170)]):
        out += tree_lods(bush, "SM_Bush_%s" % "AB"[i], h, rad, 570 + i)
    # the forest floor's cards (T_Undergrowth, 160 x 32 texels): bracken, bramble, toadstools, bluebells, sapling, dead bracken
    for nm, x0, w in [("SM_Under_Bracken", 0, 32), ("SM_Under_Bramble", 32, 32), ("SM_Under_Toadstool", 64, 16), ("SM_Under_Bluebell", 80, 16),
                      ("SM_Under_Sapling", 96, 32), ("SM_Under_DeadBracken", 128, 32)]:
        out.append(card(nm, x0, w, 32, 160.0))
    # fallen timber: a mossy log, a broken one, a stump with a root flare (bark sides, ringed ends, moss on top)
    lg = Mesh("SM_Log_Mossy")
    prism(lg, (0, -190, 30), (0, 190, 36), 34, 8, col=(1, 1, 0, 1), cap_col=(1, 1, 1, 1), cap_uv_tile=64.0)
    prism(lg, (10, 40, 44), (95, 120, 96), 9, 5, col=(1, 1, 0, 1), cap_col=(1, 1, 1, 1), cap_uv_tile=64.0)
    out.append(lg)
    lg = Mesh("SM_Log_Broken")
    prism(lg, (0, -120, 22), (0, 40, 26), 26, 8, col=(1, 1, 0, 1), cap_col=(1, 1, 1, 1), cap_uv_tile=64.0)
    prism(lg, (30, 70, 20), (-20, 190, 24), 24, 8, col=(1, 1, 0, 1), cap_col=(1, 1, 1, 1), cap_uv_tile=64.0)
    out.append(lg)
    st = Mesh("SM_Log_Stump")
    prism(st, (0, 0, -8), (0, 0, 22), 44, 8, col=(1, 1, 0, 1))
    prism(st, (0, 0, 22), (0, 0, 58), 32, 8, col=(1, 1, 0, 1), cap_col=(1, 1, 1, 1), cap_uv_tile=64.0)
    out.append(st)
    return out


def card(name, cell_x0, cell_w, cell_h, tex_w, lean=0.12):
    """A foliage sprite card facing the camera side (-X), leaning back a little. UV0 normalised 0..1.
    Normals point up so the card takes the same light as the turf it stands in."""
    m = Mesh(name)
    w, h = cell_w * TEXEL, cell_h * TEXEL
    u0, u1 = cell_x0 / tex_w, (cell_x0 + cell_w) / tex_w
    for yaw in (0.0, 62.0):
        c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        pts = []
        for (ly, lz) in [(-w / 2, 0.0), (w / 2, 0.0), (w / 2, h), (-w / 2, h)]:
            lx = lz * lean
            pts.append((lx * c - ly * s, lx * s + ly * c, lz))
        uv = [(u0, 1.0), (u1, 1.0), (u1, 0.0), (u0, 0.0)]
        ids = [m.vert(p, (0, 0, 1), u_, (1.0, p[2] / h), (1, 1, 1, 1)) for p, u_ in zip(pts, uv)]
        m.quad(*ids)
    return m


def prism(m, c0, c1, radius, sides, col=(1, 1, 1, 1), cap_col=None, cap_uv_tile=None):
    """N-gon prism between two points (any direction). Side UVs in cm; caps optional with centred UVs."""
    c0, c1 = np.array(c0, float), np.array(c1, float)
    axis = c1 - c0
    length = np.linalg.norm(axis)
    axis /= length
    ref = np.array([0, 0, 1.0]) if abs(axis[2]) < 0.9 else np.array([1.0, 0, 0])
    e1 = np.cross(axis, ref); e1 /= np.linalg.norm(e1)
    e2 = np.cross(axis, e1)
    circ = 2 * math.pi * radius
    ring = [(math.cos(2 * math.pi * i / sides), math.sin(2 * math.pi * i / sides)) for i in range(sides + 1)]
    for i in range(sides):
        (ca, sa), (cb, sb) = ring[i], ring[i + 1]
        da, db = e1 * ca + e2 * sa, e1 * cb + e2 * sb
        p = [c0 + da * radius, c0 + db * radius, c1 + db * radius, c1 + da * radius]
        nn = [da, db, db, da]
        uv = [(0.0, circ * i / sides), (0.0, circ * (i + 1) / sides), (length, circ * (i + 1) / sides), (length, circ * i / sides)]
        ids = [m.vert(pp, n_, u_, (1.0, 0.0), col) for pp, n_, u_ in zip(p, nn, uv)]
        # orient outward
        if np.dot(np.cross(p[1] - p[0], p[2] - p[0]), da) > 0:
            m.quad(*ids)
        else:
            m.quad(ids[0], ids[3], ids[2], ids[1])
    if cap_col is not None:
        for centre, sign in ((c0, -1.0), (c1, 1.0)):
            nvec = axis * sign
            ids = []
            for (ca, sa) in ring[:-1]:
                d = e1 * ca + e2 * sa
                half = cap_uv_tile * 0.5
                ids.append(m.vert(centre + d * radius, nvec, (half + ca * radius, half + sa * radius), (1.0, 0.0), cap_col))
            for i in range(1, sides - 1):
                p0, p1, p2 = (np.array(m.p[ids[k]]) for k in (0, i, i + 1))
                if np.dot(np.cross(p1 - p0, p2 - p0), nvec) > 0:
                    m.tri(ids[0], ids[i], ids[i + 1])
                else:
                    m.tri(ids[0], ids[i + 1], ids[i])


def tilted_box(m, centre, size, yaw=0.0, pitch=0.0, roll=0.0, col=(1, 1, 1, 1)):
    """Box of `size` about `centre`, rotated yaw (Z), pitch (Y), roll (X) in degrees. Planar UVs taken before rotating."""
    b = Mesh("tmp")
    hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2
    b.box((-hx, -hy, -hz), (hx, hy, hz), col=col, uv_offset=(U(0, 256), U(0, 256)), bottom=True)
    cy, sy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    cp, sp = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))
    cr, sr = math.cos(math.radians(roll)), math.sin(math.radians(roll))
    rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
    rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
    rot = rz @ ry @ rx
    b.p = [tuple(rot @ np.array(p) + np.array(centre)) for p in b.p]
    b.n = [tuple(rot @ np.array(n)) for n in b.n]
    m.append(b)


def build_prop_meshes():
    out = []
    # conifers: (height, radius)
    for i, (h, rad) in enumerate([(430, 115), (640, 150), (820, 185), (1020, 225), (1250, 265)]):
        out += tree_lods(conifer, "SM_Conifer_%s" % "ABCDE"[i], h, rad, 100 + i)
    out += build_forest_meshes()
    # sprite cards from T_Tufts (96 x 24 texels): tall grass, short grass, dry reeds, fern, flowers
    for nm, x0, w in [("SM_Tuft_Tall", 0, 16), ("SM_Tuft_Short", 16, 16), ("SM_Tuft_Dry", 32, 16), ("SM_Tuft_Fern", 48, 24), ("SM_Tuft_Flower", 72, 24)]:
        out.append(card(nm, x0, w, 24, 96.0))
    # generic rocks
    for i, (sz, pts) in enumerate([((44, 36, 34), 11), ((62, 48, 46), 12), ((54, 54, 40), 12),
                                   ((130, 105, 80), 15), ((170, 120, 95), 15), ((150, 150, 120), 16),
                                   ((280, 210, 170), 17), ((330, 250, 200), 18), ((260, 260, 230), 18)]):
        out.append(hull_rock("SM_Rock_%s%d" % ("SML"[i // 3], i % 3), sz, pts, seed=300 + i))
    # gold vein: a low ore outcrop (MI_Bld_Ore: dark stone with gold glints) with loose ore chunks round it
    gv = Mesh("SM_GoldVein")
    hull_rock(None, (300, 240, 150), 17, seed=377, into=gv, yaw=10)
    for j, (dx, dy, k) in enumerate([(150, 110, 0.45), (-140, 90, 0.38), (60, -150, 0.42), (-90, -120, 0.3), (190, -40, 0.28)]):
        hull_rock(None, (300 * k, 240 * k, 150 * k * 1.1), 12, seed=380 + j, into=gv, offset=(dx, dy, 0.0), yaw=j * 47.0)
    out.append(gv)
    # standing stones (rock skin)
    for i, (w, d, h) in enumerate([(70, 46, 250), (62, 50, 190), (80, 54, 130)]):
        m = hull_rock("SM_Menhir_%d" % i, (w, d, h * 1.6), 14, seed=340 + i)
        out.append(m)
    # fence: posts + rails along Y, 240 cm; B has lost a rail and leans
    wood = (1, 1, 1, 1)
    f = Mesh("SM_Fence_A")
    for y in (-110, 0, 110):
        f.box((-7, y - 7, -6), (7, y + 7, 96 + U(-6, 6)), col=wood, uv_offset=(U(0, 99), U(0, 99)))
    for z in (38, 72):
        tilted_box(f, (0, 0, z), (6, 236, 12), col=wood)
    out.append(f)
    f = Mesh("SM_Fence_B")
    tilted_box(f, (0, -110, 45), (14, 14, 100), roll=-8, col=wood)
    tilted_box(f, (0, 0, 44), (14, 14, 96), roll=5, pitch=6, col=wood)
    tilted_box(f, (0, 110, 30), (14, 14, 70), roll=14, col=wood)
    tilted_box(f, (0, -52, 66), (6, 124, 12), roll=-4, col=wood)
    tilted_box(f, (4, 20, 30), (6, 230, 12), roll=9, col=wood)
    out.append(f)
    # log and stump: bark sides (COLOR.b = 0), ringed ends (COLOR.b = 1)
    lg = Mesh("SM_Log")
    prism(lg, (0, -135, 26), (0, 135, 30), 28, 8, col=(1, 1, 0, 1), cap_col=(1, 1, 1, 1), cap_uv_tile=64.0)
    out.append(lg)
    st = Mesh("SM_Stump")
    prism(st, (0, 0, -6), (0, 0, 46), 30, 8, col=(1, 1, 0, 1), cap_col=(1, 1, 1, 1), cap_uv_tile=64.0)
    out.append(st)
    # ruin pieces (sandstone): pillar with base and broken top, a stepped wall run, a fallen block
    p = Mesh("SM_Ruin_Pillar")
    p.box((-44, -44, -6), (44, 44, 22), uv_offset=(U(0, 99), U(0, 99)))
    p.box((-32, -32, 22), (32, 32, 300), uv_offset=(U(0, 99), U(0, 99)))
    p.box((-40, -40, 300), (40, 40, 322), uv_offset=(U(0, 99), U(0, 99)))
    out.append(p)
    p = Mesh("SM_Ruin_PillarBroken")
    p.box((-44, -44, -6), (44, 44, 22), uv_offset=(U(0, 99), U(0, 99)))
    p.box((-32, -32, 22), (32, 32, 150), uv_offset=(U(0, 99), U(0, 99)))
    p.box((-32, -32, 150), (4, 20, 186), uv_offset=(U(0, 99), U(0, 99)))
    out.append(p)
    w = Mesh("SM_Ruin_Wall")
    x = -180
    for seg_w, seg_h in [(64, 96), (64, 160), (64, 192), (64, 128), (48, 64), (56, 32)]:
        w.box((-26, x, -6), (26, x + seg_w, seg_h), uv_offset=(0.0, 0.0))
        x += seg_w
    out.append(w)
    b = Mesh("SM_Ruin_Block")
    tilted_box(b, (0, 0, 14), (64, 96, 32), yaw=0, roll=4)
    out.append(b)
    # banner pole: wood pole + crossbar (planks), cloth card (two-sided material)
    pole = Mesh("SM_BannerPole")
    prism(pole, (0, 0, -6), (0, 0, 460), 6.5, 6, col=wood)
    tilted_box(pole, (0, 0, 420), (6, 84, 6), col=wood)
    out.append(pole)
    cl = Mesh("SM_BannerCloth")
    wdt, hgt = 16 * TEXEL, 40 * TEXEL
    pts = [(1.0, -wdt / 2, 416 - hgt), (1.0, wdt / 2, 416 - hgt), (1.0, wdt / 2, 416), (1.0, -wdt / 2, 416)]
    uv = [(0, 1), (1, 1), (1, 0), (0, 0)]
    ids = [cl.vert(pp, (-1, 0, 0.2), u_, (1.0, 1.0 - u_[1] * 0.0), (1, 1, 1, 1)) for pp, u_ in zip(pts, uv)]
    cl.quad(ids[0], ids[3], ids[2], ids[1])
    out.append(cl)
    out += build_structure_meshes()
    out += build_landmark_meshes()
    return out


def build_structure_meshes():
    """Set dressing added with the mountain pass: a timber watch post, more of the old kingdom's ruins (an arch, a broken
    tower, a fallen bridge), a dolmen and cairns, and the bridges' parapets (the birds are ASRBirds, made at run time)."""
    out = []
    wood = (1, 1, 1, 1)
    # watch post: four splayed legs, two rings of girts, braces, a railed deck under a pyramid roof, a ladder. 7 m.
    w = Mesh("SM_WatchPost")
    for sx in (-1, 1):
        for sy in (-1, 1):
            prism(w, (sx * 100, sy * 100, -8), (sx * 74, sy * 74, 430), 9, 6, col=wood)
            w.box((sx * 96 - 5, sy * 96 - 5, 440), (sx * 96 + 5, sy * 96 + 5, 610), col=wood, uv_offset=(U(0, 99), U(0, 99)))
    for z, half in ((150, 92), (300, 82)):
        for sgn in (-1, 1):
            tilted_box(w, (sgn * half, 0, z), (8, 2 * half + 10, 10), col=wood)
            tilted_box(w, (0, sgn * half, z), (2 * half + 10, 8, 10), col=wood)
    for sgn in (-1, 1):                                        # one brace per side, alternating lean
        tilted_box(w, (sgn * 87, 0, 225), (7, 236, 9), roll=sgn * 38, col=wood)
        tilted_box(w, (0, sgn * 87, 225), (236, 7, 9), pitch=sgn * 38, col=wood)
    tilted_box(w, (0, 0, 435), (224, 224, 10), col=wood)       # deck
    for sgn in (-1, 1):
        tilted_box(w, (sgn * 96, 0, 520), (6, 196, 9), col=wood)
        tilted_box(w, (0, sgn * 96, 520), (196, 6, 9), col=wood)
    apex, e, zr = (0.0, 0.0, 715.0), 132.0, 604.0
    cn = [(-e, -e, zr), (e, -e, zr), (e, e, zr), (-e, e, zr)]
    for i in range(4):
        w.flat_poly([cn[i], cn[(i + 1) % 4], apex], col=wood, uv_offset=(U(0, 99), U(0, 99)))
    w.flat_poly([cn[3], cn[2], cn[1], cn[0]], col=wood)       # the roof's underside
    for sgn in (-1, 1):                                        # ladder up the camera side
        tilted_box(w, (-128, sgn * 22, 215), (6, 6, 450), pitch=-7, col=wood)
    for z in range(40, 430, 45):
        tilted_box(w, (-128 + (215 - z) * 0.123, 0, z), (5, 44, 5), col=wood)
    out.append(w)
    # ruined arch: two piers and what is left of the lintel
    a = Mesh("SM_Ruin_Arch")
    for sy in (-1, 1):
        a.box((-48, sy * 190 - 48, -6), (48, sy * 190 + 48, 24), uv_offset=(U(0, 99), U(0, 99)))
        a.box((-36, sy * 190 - 36, 24), (36, sy * 190 + 36, 330 if sy < 0 else 300), uv_offset=(U(0, 99), U(0, 99)))
    a.box((-42, -236, 330), (42, 40, 386), uv_offset=(U(0, 99), U(0, 99)))        # the lintel, broken short of the far pier
    a.box((-42, -236, 386), (42, -120, 412), uv_offset=(U(0, 99), U(0, 99)))
    tilted_box(a, (70, 120, 20), (70, 150, 44), yaw=24, roll=7)                   # its other half, on the ground
    out.append(a)
    # broken tower: a square shell with ragged walls, open to the sky
    t = Mesh("SM_Ruin_Tower")
    half, thick = 190.0, 46.0
    t.box((-half - 16, -half - 16, -6), (half + 16, half + 16, 26), uv_offset=(U(0, 99), U(0, 99)))
    for side, hs in enumerate(((520, 560, 470, 390, 300), (300, 230, 180, 120, 150), (150, 210, 320, 400, 470), (470, 520, 560, 590, 520))):
        n = len(hs)
        for i, h in enumerate(hs):
            a0, a1 = -half + 2 * half * i / n, -half + 2 * half * (i + 1) / n
            lo, hi = {0: ((half - thick, a0, 26), (half, a1, h)), 1: ((a0, half - thick, 26), (a1, half, h)),
                      2: ((-half, a0, 26), (-half + thick, a1, h)), 3: ((a0, -half, 26), (a1, -half + thick, h))}[side]
            t.box(lo, hi, uv_offset=(U(0, 99), 0.0))
    tilted_box(t, (-250, 60, 16), (64, 96, 32), yaw=40, roll=5)
    tilted_box(t, (-40, -265, 16), (64, 110, 32), yaw=-20, roll=-6)
    out.append(t)
    # the fallen bridge: an abutment on the bank (local +X runs out over the water), one span on a pier, the next span gone
    b = Mesh("SM_Ruin_BridgeEnd")
    b.box((-190, -150, -6), (40, 150, 118), uv_offset=(U(0, 99), U(0, 99)))
    b.box((40, -120, 84), (150, 120, 118), uv_offset=(U(0, 99), U(0, 99)))
    b.box((96, -132, -190), (160, 132, 84), uv_offset=(U(0, 99), U(0, 99)))
    tilted_box(b, (196, -20, 88), (90, 190, 32), pitch=20, yaw=4)
    for sy in (-1, 1):
        b.box((-190, sy * 150 - (20 if sy > 0 else 0), 118), (150 if sy > 0 else 60, sy * 150 + (0 if sy > 0 else 20), 164), uv_offset=(U(0, 99), U(0, 99)))
    out.append(b)
    pr = Mesh("SM_Ruin_Pier")                                  # a pier left standing in the stream
    pr.box((-70, -140, -190), (70, 140, 60), uv_offset=(U(0, 99), U(0, 99)))
    pr.box((-84, -154, 60), (84, 154, 86), uv_offset=(U(0, 99), U(0, 99)))
    tilted_box(pr, (10, -40, 104), (90, 130, 36), yaw=18, roll=9)
    out.append(pr)
    # bridge parapet: one 3 m run of low wall with a capped post at one end (laid end to end along a deck)
    pp = Mesh("SM_Ruin_Parapet")
    pp.box((-13, -150, -4), (13, 122, 44), uv_offset=(U(0, 99), U(0, 99)))
    pp.box((-18, 122, -4), (18, 150, 66), uv_offset=(U(0, 99), U(0, 99)))
    out.append(pp)
    # dolmen: three uprights and a capstone (rock skin)
    d = Mesh("SM_Dolmen")
    for j, (dx, dy, yaw) in enumerate(((-90, -70, 10), (95, -60, -25), (0, 105, 80))):
        hull_rock(None, (70, 110, 200), 12, seed=520 + j, into=d, offset=(dx, dy, 0.0), yaw=yaw)
    hull_rock(None, (330, 300, 66), 15, seed=529, into=d, offset=(0, -5, 150.0), yaw=15)
    out.append(d)
    # cairn: a waymark of piled stones
    c = Mesh("SM_Cairn")
    for j, (dx, dy, dz, k) in enumerate(((0, 0, 0, 1.0), (34, 20, 0, 0.7), (-30, 26, 0, 0.66), (4, -34, 0, 0.7), (4, 4, 40, 0.72), (-2, 2, 74, 0.48), (2, 0, 100, 0.3))):
        hull_rock(None, (84 * k, 76 * k, 62 * k), 11, seed=540 + j, into=c, offset=(dx, dy, dz), yaw=j * 53.0)
    out.append(c)
    return out


def frustum(m, lo, hi, z0, z1, uvo=(0.0, 0.0), cap=True):
    """A four-sided tapering block: half-widths `lo` (x, y) at z0 and `hi` at z1 (an obelisk's shaft, a statue's leg)."""
    c0 = [(-lo[0], -lo[1], z0), (lo[0], -lo[1], z0), (lo[0], lo[1], z0), (-lo[0], lo[1], z0)]
    c1 = [(-hi[0], -hi[1], z1), (hi[0], -hi[1], z1), (hi[0], hi[1], z1), (-hi[0], hi[1], z1)]
    for i in range(4):
        j = (i + 1) % 4
        m.flat_poly([c0[i], c0[j], c1[j], c1[i]], uv_offset=uvo)
    if cap:
        m.flat_poly(c1, uv_offset=uvo)


def moved(mesh, offset=(0, 0, 0), yaw=0.0):
    return mesh.transformed(mesh.name, yaw, offset)


def build_landmark_meshes():
    """The landmarks: what the old kingdom and older things left on the field. Sandstone (SM_Ruin_*), bone (SM_Bones_*),
    iron and stone (SM_Relic_*, SM_Barrow_*), timber (SM_Spear, SM_Shield, SM_Cart_*, SM_Jetty)."""
    out = []
    # obelisk: a plinth, a tapering shaft, a pyramid cap. 6.4 m.
    o = Mesh("SM_Ruin_Obelisk")
    o.box((-62, -62, -8), (62, 62, 34), uv_offset=(U(0, 99), U(0, 99)))
    frustum(o, (44, 44), (27, 27), 34, 560, uvo=(U(0, 99), 0.0), cap=False)
    frustum(o, (27, 27), (1, 1), 560, 640, uvo=(U(0, 99), 0.0))
    out.append(o)
    o = Mesh("SM_Ruin_ObeliskBroken")                           # snapped a third of the way up; the rest lies beside it
    o.box((-62, -62, -8), (62, 62, 34), uv_offset=(U(0, 99), U(0, 99)))
    frustum(o, (44, 44), (38, 38), 34, 210, uvo=(U(0, 99), 0.0))
    o.box((-38, -38, 210), (6, 30, 246), uv_offset=(U(0, 99), U(0, 99)))
    tilted_box(o, (150, 60, 30), (64, 300, 60), yaw=28, roll=4)
    tilted_box(o, (60, 330, 22), (48, 110, 44), yaw=-16, roll=-7)
    out.append(o)
    # the colossus: a king of the old realm, broken off at the knees; his head and a hand lie in the grass. 4.4 m as it stands.
    c = Mesh("SM_Ruin_Colossus")
    c.box((-170, -230, -8), (170, 230, 62), uv_offset=(U(0, 99), U(0, 99)))
    c.box((-150, -210, 62), (150, 210, 84), uv_offset=(U(0, 99), U(0, 99)))
    for sy, top in ((-1, 440.0), (1, 300.0)):
        leg = Mesh("leg")
        leg.box((-74, -50, 84), (58, 50, 122), uv_offset=(U(0, 99), U(0, 99)))            # the foot
        frustum(leg, (46, 44), (40, 40), 122, top, uvo=(U(0, 99), 0.0))
        if sy > 0:
            leg.box((-40, -40, top), (10, 20, top + 34), uv_offset=(U(0, 99), U(0, 99)))    # the break
        c.append(moved(leg, (10, sy * 96, 0)))
    c.box((40, -150, 84), (120, 150, 240), uv_offset=(U(0, 99), U(0, 99)))               # what is left of the robe behind the legs
    c.box((60, -110, 240), (120, 60, 330), uv_offset=(U(0, 99), U(0, 99)))
    hull_rock(None, (190, 170, 210), 15, seed=611, into=c, offset=(-330, 150, 0.0), yaw=20)     # the head
    tilted_box(c, (-385, 150, 150), (60, 150, 26), yaw=20, roll=6)                         # its crown's band
    tilted_box(c, (-300, -190, 26), (70, 190, 52), yaw=-35, roll=5)                         # a forearm
    hull_rock(None, (90, 80, 70), 11, seed=612, into=c, offset=(-390, -260, 0.0), yaw=50)
    out.append(c)
    # the wyrm's bones: a rib (half an arch: set in pairs), a run of spine, the skull
    r = Mesh("SM_Bones_Rib")
    n, rad = 7, 250.0
    for k in range(n):
        a0, a1 = math.radians(4 + k * 15.0), math.radians(4 + (k + 1) * 15.0)
        am = 0.5 * (a0 + a1)
        cy, cz = rad - rad * math.cos(am), rad * math.sin(am)                               # from the ground at y = 0 up and over toward +y
        seg = 2.0 * rad * math.sin((a1 - a0) * 0.5) + 6.0
        thick = 30.0 - 2.6 * k
        tilted_box(r, (0, cy, cz - 10), (thick, thick * 0.8, seg), roll=-math.degrees(am))
    out.append(r)
    s = Mesh("SM_Bones_Spine")
    for k in range(5):
        y = -160 + k * 80
        tilted_box(s, (0, y, 34 + (k % 2) * 4), (56, 60, 50), roll=U(-5, 5), yaw=U(-6, 6))
        tilted_box(s, (0, y, 78), (16, 34, 50), roll=U(-8, 8))
    out.append(s)
    k = Mesh("SM_Bones_Skull")
    hull_rock(None, (210, 300, 190), 16, seed=621, into=k, offset=(0, 0, 0.0), yaw=0)
    hull_rock(None, (150, 260, 110), 13, seed=622, into=k, offset=(0, -250, 0.0), yaw=0)        # the snout
    for sx in (-1, 1):
        prism(k, (sx * 70, 90, 150), (sx * 190, 250, 330), 20, 6)
        prism(k, (sx * 190, 250, 330), (sx * 200, 300, 430), 11, 6)
        tilted_box(k, (sx * 62, -330, 26), (20, 150, 30), yaw=sx * 8)                        # the jaw, fallen open
    out.append(k)
    # the field of swords: a great-sword left standing in the ground, a spear, a shield, a broken cart
    w = Mesh("SM_Relic_Sword")
    tilted_box(w, (0, 0, 96), (5, 22, 200), roll=7, pitch=4)
    tilted_box(w, (0, -24, 198), (9, 78, 12), roll=7, pitch=4)
    tilted_box(w, (0, -30, 232), (7, 9, 56), roll=7, pitch=4)
    tilted_box(w, (0, -35, 264), (13, 15, 12), roll=7, pitch=4)
    out.append(w)
    w = Mesh("SM_Relic_SwordFallen")
    tilted_box(w, (0, 0, 60), (5, 20, 150), roll=38, pitch=-6)
    tilted_box(w, (0, -74, 118), (9, 70, 11), roll=38, pitch=-6)
    tilted_box(w, (0, -98, 142), (7, 9, 50), roll=38, pitch=-6)
    out.append(w)
    sp = Mesh("SM_Spear")
    prism(sp, (0, 0, -10), (26, 34, 250), 3.6, 5)
    prism(sp, (26, 34, 250), (30, 39, 292), 6.0, 4)
    prism(sp, (60, -40, -10), (40, -72, 190), 3.6, 5)
    out.append(sp)
    sh = Mesh("SM_Shield")
    prism(sh, (0, 0, 44), (22, 0, 60), 46, 8, cap_col=(1, 1, 1, 1), cap_uv_tile=96.0)
    prism(sh, (20, 0, 58), (30, 0, 66), 12, 6, cap_col=(1, 1, 1, 1), cap_uv_tile=32.0)
    out.append(sh)
    ct = Mesh("SM_Cart_Wreck")
    tilted_box(ct, (0, 0, 62), (150, 250, 12), roll=9, pitch=-5)
    for sx in (-1, 1):
        tilted_box(ct, (sx * 72, 0, 86), (8, 250, 44), roll=9, pitch=-5)
    tilted_box(ct, (0, 190, 52), (10, 180, 10), roll=16, yaw=6)
    prism(ct, (-92, -30, 58), (-104, -30, 58), 58, 8, cap_col=(1, 1, 1, 1), cap_uv_tile=120.0)       # one wheel still on
    prism(ct, (150, 120, 4), (150, 120, 16), 58, 8, cap_col=(1, 1, 1, 1), cap_uv_tile=120.0)         # the other in the grass
    out.append(ct)
    # jetty: planks on posts, running out along local +X from the bank (its deck 40 cm over the ground it starts on)
    j = Mesh("SM_Jetty")
    for k in range(10):
        j.box((k * 62 - 20, -70 + U(-4, 4), 34), (k * 62 + 36, 70 + U(-4, 4), 42), uv_offset=(U(0, 99), U(0, 99)))
    for x in (0, 190, 380, 570):
        for sy in (-1, 1):
            prism(j, (x, sy * 60, -230), (x, sy * 60, 70 if x in (0, 570) else 40), 8, 6)
    for sy in (-1, 1):
        j.box((-20, sy * 62 - 5, 22), (590, sy * 62 + 5, 34), uv_offset=(U(0, 99), U(0, 99)))
    out.append(j)
    # barrow door: the stone doorway into a burial mound (two uprights, a lintel, the blocking slab), facing local -X
    b = Mesh("SM_Barrow_Door")
    for sy in (-1, 1):
        hull_rock(None, (80, 70, 250), 12, seed=630 + sy, into=b, offset=(0, sy * 105, 0.0), yaw=sy * 12)
    hull_rock(None, (110, 330, 70), 14, seed=633, into=b, offset=(0, 0, 150.0), yaw=4)
    hull_rock(None, (60, 150, 190), 12, seed=634, into=b, offset=(40, 6, 0.0), yaw=-6)
    out.append(b)
    return out


def aqueduct_mesh(name, piers, top, missing=()):
    """A ruined aqueduct: square piers from the ground up to `top`, joined by the water channel's deck; spans listed in
    `missing` (index of the span after pier i) have fallen. `piers`: [(x, y, ground z)] in world cm."""
    m = Mesh(name)
    half = 85.0
    for i, (x, y, z) in enumerate(piers):
        full = not (i in missing and (i - 1) in missing)
        h = top if full else z + (top - z) * 0.55
        m.box((x - half, y - half, z - 60.0), (x + half, y + half, h - 60.0), uv_offset=(U(0, 99), 0.0))
        m.box((x - half - 16, y - half - 16, h - 60.0), (x + half + 16, y + half + 16, h - 36.0), uv_offset=(U(0, 99), U(0, 99)))
    for i in range(len(piers) - 1):
        if i in missing:
            continue
        (x0, y0, _), (x1, y1, _) = piers[i], piers[i + 1]
        ln = math.hypot(x1 - x0, y1 - y0)
        yaw = math.degrees(math.atan2(y1 - y0, x1 - x0))
        cx, cy = (x0 + x1) * 0.5, (y0 + y1) * 0.5
        tilted_box(m, (cx, cy, top - 6.0), (ln + 2 * half, 2 * half - 20, 60.0), yaw=yaw)             # the deck
        for sd in (-1, 1):                                                                         # the channel's walls
            ox, oy = -math.sin(math.radians(yaw)) * sd * (half - 26), math.cos(math.radians(yaw)) * sd * (half - 26)
            tilted_box(m, (cx + ox, cy + oy, top + 44.0), (ln + 2 * half, 22, 40.0), yaw=yaw)
        for t in (0.25, 0.75):                                                                     # haunches under the deck, toward each pier
            px, py = x0 + (x1 - x0) * (0.12 if t < 0.5 else 0.88), y0 + (y1 - y0) * (0.12 if t < 0.5 else 0.88)
            tilted_box(m, (px, py, top - 76.0), (ln * 0.2, 2 * half - 40, 80.0), yaw=yaw, pitch=(22 if t < 0.5 else -22))
    return m
