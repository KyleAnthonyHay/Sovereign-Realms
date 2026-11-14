#!/usr/bin/env python3
"""Offline generator for the battlefield diorama: terrain meshes, props, the ground splat map and
the placement list. Deterministic. Unreal only imports and places what this writes.

  Tools/.venv/bin/python Tools/world/gen_battlefield.py
  -> SourceArt/Meshes/battlefield.gltf (+ .bin)   every static mesh, Unreal axes, cm (the buildings are separate:
                                                   Tools/blender/build_building.py; BUILDINGS below places them)
     SourceArt/Textures/T_Splat.png               ground blend map (see SPLAT below)
     SourceArt/World/layout.json                  where everything goes
     Saved/WorldPreview/map.png                   top-down preview (+X up, like the game camera)
  then, in the editor:  Tools/ue_py.py Tools/build_battlefield_visuals.py

Rules honoured (Docs/VISUAL_CONTRACT.md): play area +/-3000 cm; both spawn areas and the lane
between them stay flat; ledges inside the play area that units should climb are <= 40 cm; taller
tiers stay outside the bound (except the small blocking knolls); blocking rocks keep their old
positions and convex footprints.
"""
import json
import math
import os
import sys
import zlib

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from scipy.spatial import ConvexHull
from shapely import affinity
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union
import mapbox_earcut as earcut

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from meshlib import Mesh, planar_uv, write_gltf  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEXEL = 4.0                     # cm per texel, everywhere
BOUND = 3000.0                  # playable half extent
# dressed world: the low camera sees far up-screen (+X), a little behind the near bound, wide at the back
WX0, WX1, WY0, WY1 = -5200.0, 12600.0, -9600.0, 9600.0
PLAYER_START, ENEMY_START = (-1300.0, 0.0), (1500.0, 200.0)
SPLAT_ORIGIN, SPLAT_SIZE, SPLAT_RES = (-5600.0, -6144.0), 12288.0, 1024      # world square the splat map covers
HM_RES = 8.0                    # heightmap raster, cm per cell

rng = np.random.default_rng(20261)


def U(a, b):
    return float(rng.uniform(a, b))


# ============================================================================================ shapes
def rounded_box(cx, cy, w, h, rot, r):
    r = min(r, w * 0.45, h * 0.45)
    b = box(-w / 2 + r, -h / 2 + r, w / 2 - r, h / 2 - r).buffer(r, 3)
    return affinity.translate(affinity.rotate(b, rot, origin=(0, 0)), cx, cy)


def largest(geom, min_area=0.0, all_parts=False):
    if geom.is_empty:
        return [] if all_parts else None
    parts = list(geom.geoms) if isinstance(geom, MultiPolygon) or geom.geom_type == "GeometryCollection" else [geom]
    parts = [p for p in parts if p.geom_type == "Polygon" and p.area > min_area]
    parts.sort(key=lambda p: -p.area)
    if all_parts:
        return parts
    return parts[0] if parts else None


def chunk_shape(cx, cy, rx, ry, lobes=5):
    """A hand-cut plateau outline: a few overlapping rounded slabs at odd angles, necks opened up,
    notches closed, then simplified so the edge is made of short straight cuts."""
    parts = [rounded_box(cx, cy, rx * 1.55, ry * 1.55, U(-28, 28), min(rx, ry) * 0.42)]
    for _ in range(lobes):
        a = U(0, 2 * math.pi)
        px, py = cx + math.cos(a) * rx * U(0.45, 0.9), cy + math.sin(a) * ry * U(0.45, 0.9)
        parts.append(rounded_box(px, py, rx * U(0.55, 1.0), ry * U(0.55, 1.0), U(0, 90), min(rx, ry) * U(0.15, 0.3)))
    g = unary_union(parts)
    g = g.buffer(-30, 2).buffer(30, 2).buffer(22, 2).buffer(-22, 2)
    g = largest(g)
    return g.simplify(9.0) if g is not None else None


def clean(geom, min_area=6000.0):
    """Open thin slivers, drop crumbs, simplify. Returns a list of polygons."""
    if geom is None or geom.is_empty:
        return []
    g = geom.buffer(-38, 2).buffer(38, 2)
    out = []
    for p in largest(g, min_area, all_parts=True):
        p = p.simplify(8.0)
        if p.is_valid and p.area > min_area:
            out.append(p)
    return out


# ============================================================================================ terrain model
TIERS = []          # dicts: poly, top, below, group (mesh name), walk (bool), kind
GROUPS = {}         # mesh name -> folder


def add_tier(poly, top, below, group, folder):
    TIERS.append({"poly": poly, "top": float(top), "below": float(below), "group": group})
    GROUPS[group] = folder


def stack(name, folder, base_polys, steps, keep_out=None, shrink=(0.55, 0.78), ledge=(55.0, 95.0), split=0.3):
    """Builds a stepped hill: each tier is cut from the one below, set in by at least a ledge and
    pushed off-centre, so cliffs stack on one side and broad steps run out on another."""
    current = list(base_polys)
    z = 0.0
    for i, step in enumerate(steps):
        nxt = []
        for poly in current:
            if i == 0:
                cand = [poly]
            else:
                lg = ledge[i] if isinstance(ledge, list) else ledge
                inner = largest(poly.buffer(-U(*lg), 2))
                if inner is None or inner.area < 30000:
                    continue
                minx, miny, maxx, maxy = inner.bounds
                w, h = maxx - minx, maxy - miny
                blobs = []
                for _ in range(2 if (rng.random() < split and min(w, h) > 700) else 1):
                    pt = inner.representative_point() if rng.random() < 0.3 else Point(U(minx + w * 0.25, maxx - w * 0.25), U(miny + h * 0.25, maxy - h * 0.25))
                    s = U(*shrink)
                    blobs.append(chunk_shape(pt.x, pt.y, w * 0.5 * s, h * 0.5 * s, lobes=4))
                cand = clean(inner.intersection(unary_union([b for b in blobs if b is not None])), 25000.0)
            for c in cand:
                if keep_out is not None and i >= keep_out[1]:
                    cc = clean(c.difference(keep_out[0]), 25000.0)
                else:
                    cc = [c]
                for p in cc:
                    add_tier(p, z + step, z, name, folder)
                    nxt.append(p)
        if not nxt:
            break
        current = nxt
        z += step


def rasterize_heights():
    w = int((WY1 - WY0) / HM_RES)
    h = int((WX1 - WX0) / HM_RES)
    img = Image.new("F", (w, h), 0.0)
    d = ImageDraw.Draw(img)

    def ring_px(ring):
        return [((y - WY0) / HM_RES, (x - WX0) / HM_RES) for x, y in ring.coords]

    if LAKE is not None:
        d.polygon(ring_px(LAKE.exterior), fill=LAKE_BED)
    for t in sorted(TIERS, key=lambda t: t["top"]):
        d.polygon(ring_px(t["poly"].exterior), fill=t["top"])
    return np.array(img)


def height_at(x, y):
    r = int((x - WX0) / HM_RES)
    c = int((y - WY0) / HM_RES)
    if r < 0 or c < 0 or r >= HM.shape[0] or c >= HM.shape[1]:
        return 0.0
    return float(HM[r, c])


def flat_around(x, y, r):
    z = height_at(x, y)
    for k in range(8):
        a = k * math.pi / 4
        if abs(height_at(x + math.cos(a) * r, y + math.sin(a) * r) - z) > 1.0:
            return False
    return True


# ============================================================================================ terrain meshes
def ring_ccw(coords, ccw=True):
    pts = [(float(x), float(y)) for x, y in coords[:-1]]
    area = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        area += x0 * y1 - x1 * y0
    if (area > 0) != ccw:
        pts.reverse()
    return pts


def add_cap(mesh, poly, z):
    rings = [ring_ccw(list(poly.exterior.coords))] + [ring_ccw(list(r.coords), False) for r in poly.interiors]
    verts = np.array([p for r in rings for p in r], np.float64)
    ends = np.cumsum([len(r) for r in rings]).astype(np.uint32)
    tris = earcut.triangulate_float64(verts, ends).reshape(-1, 3)
    base = [mesh.vert((x, y, z), (0, 0, 1), (y, -x)) for x, y in verts]
    for a, b, c in tris:
        # earcut keeps the input orientation; make sure the triangle faces up
        pa, pb, pc = verts[a], verts[b], verts[c]
        if (pb[0] - pa[0]) * (pc[1] - pa[1]) - (pb[1] - pa[1]) * (pc[0] - pa[0]) > 0:
            mesh.tri(base[a], base[b], base[c])
        else:
            mesh.tri(base[a], base[c], base[b])


def add_wall(mesh, ring, top, bottom, solid_left=True, smooth_deg=38.0):
    """Wall along a ring with the solid on its left (exterior rings CCW, holes CW).
    UV0 = (distance along the outline, depth below the top) in cm; UV1.x = wall height."""
    pts = ring
    n = len(pts)
    seg = [np.array(pts[(i + 1) % n]) - np.array(pts[i]) for i in range(n)]
    seg_len = [float(np.linalg.norm(s)) for s in seg]
    nrm = [np.array([s[1], -s[0]]) / max(l, 1e-6) for s, l in zip(seg, seg_len)]       # away from the solid
    total = sum(seg_len)
    tile = 128 * TEXEL
    scale = (max(round(total / tile), 1) * tile) / total if total > tile * 0.75 else 1.0   # close the loop on a whole tile
    cos_t = math.cos(math.radians(smooth_deg))
    height = top - bottom
    s = 0.0
    for i in range(n):
        if seg_len[i] < 1e-4:
            continue
        p0, p1 = pts[i], pts[(i + 1) % n]
        prev_n, next_n = nrm[(i - 1) % n], nrm[(i + 1) % n]
        n0 = nrm[i] + prev_n if float(np.dot(nrm[i], prev_n)) > cos_t else nrm[i]
        n1 = nrm[i] + next_n if float(np.dot(nrm[i], next_n)) > cos_t else nrm[i]
        n0 = n0 / np.linalg.norm(n0); n1 = n1 / np.linalg.norm(n1)
        s1 = s + seg_len[i]
        a = mesh.vert((p0[0], p0[1], top), (n0[0], n0[1], 0), (s * scale, 0.0), (height, 0.0))
        b = mesh.vert((p1[0], p1[1], top), (n1[0], n1[1], 0), (s1 * scale, 0.0), (height, 0.0))
        c = mesh.vert((p1[0], p1[1], bottom), (n1[0], n1[1], 0), (s1 * scale, height), (height, 0.0))
        d = mesh.vert((p0[0], p0[1], bottom), (n0[0], n0[1], 0), (s * scale, height), (height, 0.0))
        mesh.quad(a, d, c, b)       # CCW seen from outside
        s = s1


def build_terrain_meshes():
    meshes = {}
    for t in TIERS:
        m = meshes.setdefault(t["group"], Mesh(t["group"]))
        add_cap(m, t["poly"], t["top"])
        add_wall(m, ring_ccw(list(t["poly"].exterior.coords)), t["top"], t["below"] - 8.0)
    return meshes


# ============================================================================================ props
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


def conifer(name, height, radius, seed):
    """Layered fir: drooping bough skirts over a dark core, one mesh, one material.
    UV0 in cm for the needle / bark textures. UV1 = (shade 0..1, sway weight). COLOR.b = 1 on bark."""
    r = np.random.default_rng(seed)
    m = Mesh(name)
    bare = height * 0.13
    trunk_r = max(height * 0.02, 9.0)
    NEED_W, NEED_H = 64 * TEXEL, 48 * TEXEL
    # trunk (bark): hexagonal, runs up inside the boughs
    sides = 6
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
    tiers = max(int(round((height - bare) / 62.0)), 4)
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
        segs = 11 if rim_r > 90 else (9 if rim_r > 45 else 7)
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
        out.append(conifer("SM_Conifer_%s" % "ABCDE"[i], h, rad, 100 + i))
    # sprite cards from T_Tufts (96 x 24 texels): tall grass, short grass, dry reeds, fern, flowers
    for nm, x0, w in [("SM_Tuft_Tall", 0, 16), ("SM_Tuft_Short", 16, 16), ("SM_Tuft_Dry", 32, 16), ("SM_Tuft_Fern", 48, 24), ("SM_Tuft_Flower", 72, 24)]:
        out.append(card(nm, x0, w, 24, 96.0))
    # generic rocks
    for i, (sz, pts) in enumerate([((44, 36, 34), 11), ((62, 48, 46), 12), ((54, 54, 40), 12),
                                   ((130, 105, 80), 15), ((170, 120, 95), 15), ((150, 150, 120), 16),
                                   ((280, 210, 170), 17), ((330, 250, 200), 18), ((260, 260, 230), 18)]):
        out.append(hull_rock("SM_Rock_%s%d" % ("SML"[i // 3], i % 3), sz, pts, seed=300 + i))
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
    return out


# ============================================================================================ layout
LAKE = None
LAKE_BED, LAKE_SURFACE = -170.0, -48.0
INSTANCES = {}      # mesh -> list of [x, y, z, yaw, scale]
ACTORS = []         # dicts: mesh, pos, yaw, mat, label, folder
BLOCKERS = []       # dicts: label, pos, size, yaw


def inst(mesh, x, y, yaw=None, scale=1.0, z=None, sink=0.0):
    INSTANCES.setdefault(mesh, []).append([round(x, 1), round(y, 1), round((height_at(x, y) if z is None else z) - sink, 1),
                                           round(U(0, 360) if yaw is None else yaw, 1), round(scale, 3)])


def actor(mesh, x, y, yaw, mat, label, folder, z=None):
    ACTORS.append({"mesh": mesh, "pos": [round(x, 1), round(y, 1), round(height_at(x, y) if z is None else z, 1)],
                   "yaw": round(yaw, 1), "mat": mat, "label": label, "folder": folder})


def catmull(points, per=14):
    pts = [points[0]] + list(points) + [points[-1]]
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = (np.array(p, float) for p in pts[i - 1:i + 3])
        for k in range(per):
            t = k / per
            out.append(tuple(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3)))
    out.append(tuple(points[-1]))
    return out


ROAD_MAIN = catmull([(-5200, -420), (-4000, -380), (-3000, -260), (-2000, -70), (-1300, 30), (-500, 150), (250, 90), (900, 260),
                     (1500, 230), (2300, 400), (3000, 640), (3700, 880), (4500, 1080), (5600, 1380), (7200, 1500)])
ROAD_BRANCH = catmull([(2300, 400), (2750, 60), (3050, -500), (3300, -1000)])
ROAD_SIDE = catmull([(-500, 150), (-650, -420), (-560, -860)])          # spur to the in-field ruin


def lane_keepout():
    """Ground that must stay flat: both spawn areas, the lane between them, and the blocking rocks."""
    lane = LineString([(-1900, 0), PLAYER_START, (100, 110), ENEMY_START, (2100, 230)]).buffer(540)
    spawns = unary_union([Point(PLAYER_START).buffer(680), Point(ENEMY_START).buffer(680)])
    return unary_union([lane, spawns])


BLOCK_ROCKS = [  # name, x, y, (sx, sy, sz), yaw : gameplay footprints, unchanged from the first pass
    ("Rock_Centre", 150, -260, (230, 190, 150), 20),
    ("Rock_East", -250, 820, (300, 220, 210), -35),
    ("Rock_West", 650, -900, (260, 260, 180), 50),
    ("Rock_SW", -1900, -1350, (210, 170, 130), 70),
    ("Rock_NE", 2150, 1250, (240, 200, 160), -15),
]
# blocking knolls inside the play area: (x, y, rx, ry, height); each carries a tree or two
KNOLLS = [(-2650, 2500, 250, 230, 120), (2650, -2550, 270, 250, 135), (2780, 820, 220, 240, 115), (-2750, -2400, 240, 230, 110),
          (350, -2800, 230, 210, 105), (-1350, 2780, 230, 240, 125), (1550, 2820, 250, 230, 120), (2800, 2700, 260, 250, 140),
          (-2330, 640, 190, 200, 96), (-2420, -720, 200, 190, 104)]
# field terraces: (x, y, rx, ry, walkable 40 cm steps, core steps). The walkable steps are an apron troops can
# climb; a core is a taller bluff standing on it (blocks movement, carries trees) for the ones well off the lane.
FIELD_TERRACES = [(-250, 1800, 800, 660, 2, [90, 70]), (950, -1900, 740, 800, 2, [100, 75, 60]), (-2250, -1650, 520, 580, 2, [85]),
                  (2380, -1150, 500, 560, 1, [95, 70]), (-2100, 1800, 520, 580, 1, [90, 65]), (2250, 1980, 640, 640, 2, [100, 80]),
                  (-950, -2450, 600, 460, 1, [90, 70]), (780, 2520, 520, 440, 1, [85, 60]),
                  (-760, -1010, 400, 430, 2, []), (-820, 1050, 330, 360, 1, []), (1700, -620, 300, 330, 1, []), (560, 1180, 330, 300, 2, [])]
CORE_TOPS = []      # (x, y) on top of each bluff, for trees


def build_layout():
    global LAKE, HM
    play = box(-BOUND, -BOUND, BOUND, BOUND)
    tall_zone_out = play.buffer(95, join_style=2)              # tiers taller than a step stay outside this
    road_poly = unary_union([LineString(ROAD_MAIN).buffer(180), LineString(ROAD_BRANCH).buffer(150)])
    keep = lane_keepout()
    rock_clear = unary_union([Point(x, y).buffer(max(s[0], s[1]) * 0.5 + 150) for _, x, y, s, _ in BLOCK_ROCKS])

    # ---- lake: far-left, outside the play area
    lake = unary_union([chunk_shape(4650, -2700, 1150, 1350, 6), rounded_box(3650, -1350, 700, 900, 20, 260), rounded_box(5900, -3600, 1500, 1700, 10, 500)])
    lake = lake.difference(play.buffer(150, join_style=2)).buffer(-40, 2).buffer(40, 2)
    LAKE = largest(lake).simplify(10.0)
    lake_out = LAKE.buffer(110)

    # ---- field terraces (walkable: 36-40 cm steps)
    for i, (x, y, rx, ry, tiers, core) in enumerate(FIELD_TERRACES):
        shape = chunk_shape(x, y, rx, ry, 5)
        shape = shape.difference(unary_union([keep, rock_clear, road_poly.buffer(30)]))
        base = clean(shape, 60000.0)
        if not base:
            continue
        # 40 cm steps (units climb <= 45). Ledges are often narrow, so two steps read as one taller terrace face.
        name = "SM_T_Field_%02d" % i
        stack(name, "Terrain/FieldTerraces", base[:1], [40.0] * tiers + core, shrink=(0.62, 0.9),
              ledge=[(26.0, 110.0)] * tiers + [(110.0, 190.0)] + [(45.0, 90.0)] * len(core), split=0.2)
        if core:
            tops = [t for t in TIERS if t["group"] == name and t["top"] > 40.0 * tiers + 1]
            if tops:
                best = max(tops, key=lambda t: t["top"])
                CORE_TOPS.append((best["poly"].representative_point().x, best["poly"].representative_point().y))
                low = min(tops, key=lambda t: t["top"])
                c = low["poly"].centroid
                CORE_TOPS.append((c.x + U(-60, 60), c.y + U(-60, 60)))

    # ---- blocking knolls
    for i, (x, y, rx, ry, h) in enumerate(KNOLLS):
        shape = chunk_shape(x, y, rx, ry, 3).difference(unary_union([keep, road_poly]))
        base = clean(shape, 30000.0)
        if base:
            stack("SM_T_Knoll_%02d" % i, "Terrain/Knolls", base[:1], [h * 0.62, h * 0.38], shrink=(0.7, 0.9), ledge=(34.0, 60.0), split=0.0)

    # ---- plateaus framing the field. Far side rises in many steps; near side stays low.
    def ring_stack(name, x, y, rx, ry, steps, apron=True):
        shape = chunk_shape(x, y, rx, ry, 6)
        if shape is None:
            return
        shape = shape.difference(unary_union([lake_out, road_poly, keep]))
        base = clean(shape, 90000.0)
        if not base:
            return
        if apron:      # first step is a walkable apron that may lap into the field; everything above stays out
            stack(name, "Terrain/Plateaus", base[:2], [U(34, 40)] + steps, keep_out=(tall_zone_out, 1))
        else:
            base = clean(shape.difference(tall_zone_out), 90000.0)
            if base:
                stack(name, "Terrain/Plateaus", base[:2], steps)

    k = 0
    # far side (top of screen): two ranks, the back one taller
    for y in np.arange(-2600, 5601, 1250):
        ring_stack("SM_T_Far_%02d" % k, 3720 + U(-120, 160), y + U(-200, 200), U(780, 1050), U(620, 800), [U(60, 130) for _ in range(int(rng.integers(4, 7)))])
        k += 1
    for y in np.arange(-900, 6001, 1500):
        ring_stack("SM_T_Far_%02d" % k, 5300 + U(-200, 250), y + U(-250, 250), U(1000, 1350), U(800, 1000), [U(90, 190) for _ in range(int(rng.integers(5, 8)))], apron=False)
        k += 1
    # flanks (screen left and right)
    for side in (-1, 1):
        for x in np.arange(-2700, 3001, 1150):
            far = (x + 3000) / 6000.0
            n = int(rng.integers(2, 4)) + (1 if far > 0.5 else 0)
            ring_stack("SM_T_Flank_%02d" % k, x + U(-200, 200), side * (3900 + U(-150, 250)), U(620, 900), U(700, 950), [U(50, 105) for _ in range(n)])
            k += 1
        for x in np.arange(-2000, 4001, 1500):
            ring_stack("SM_T_Flank_%02d" % k, x + U(-250, 250), side * (5250 + U(-150, 250)), U(900, 1200), U(800, 1050), [U(80, 160) for _ in range(int(rng.integers(3, 6)))], apron=False)
            k += 1
    # near side (bottom of screen): low steps only, so nothing hides the field from the camera
    for y in np.arange(-4200, 4201, 1200):
        ring_stack("SM_T_Near_%02d" % k, -3900 + U(-200, 150), y + U(-250, 250), U(560, 800), U(600, 850), [U(34, 48)] if rng.random() < 0.6 else [])
        k += 1
    # far backdrop: big simple hills that fade into the haze
    for i, (x, y, rx, ry, steps) in enumerate([(8300, -6000, 1700, 2300, [260, 300, 320]), (8900, -1500, 1500, 2400, [300, 360, 300, 260]),
                                               (8500, 3300, 1600, 2300, [280, 320, 340]), (9200, 7400, 1700, 2000, [300, 340, 300]),
                                               (11000, -3800, 1300, 3000, [420, 460, 420]), (11200, 2400, 1300, 3300, [460, 480, 440, 300]),
                                               (7200, 7600, 1100, 1500, [200, 240]), (7000, -7600, 1100, 1500, [220, 240])]):
        shape = chunk_shape(x, y, rx, ry, 6)
        base = clean(shape.difference(lake_out), 90000.0)
        if base:
            stack("SM_T_Backdrop_%02d" % i, "Terrain/Backdrop", base[:1], steps, shrink=(0.62, 0.85), ledge=(120.0, 260.0), split=0.4)

    HM = rasterize_heights()

    # ---- blocking rocks: gameplay footprints as before, visible stone is a unique mesh per rock
    for name, x, y, size, yaw in BLOCK_ROCKS:
        z = height_at(x, y)
        BLOCKERS.append({"label": name + "_Collision", "pos": [x, y, z + size[2] * 0.5 - 12.0], "size": list(size), "yaw": yaw})
        actor("SM_" + name, x, y, 0.0, "rock", name, "Props/Rocks", z=z)
        for _ in range(int(rng.integers(3, 6))):               # scree at its foot
            a, d = U(0, 2 * math.pi), max(size[0], size[1]) * U(0.62, 0.95)
            inst("SM_Rock_S%d" % rng.integers(0, 3), x + math.cos(a) * d, y + math.sin(a) * d, sink=4.0)
        for _ in range(3):
            a, d = U(0, 2 * math.pi), max(size[0], size[1]) * U(0.6, 0.85)
            inst("SM_Tuft_Fern", x + math.cos(a) * d, y + math.sin(a) * d, yaw=U(-30, 30))

    place_props(keep, road_poly, rock_clear)


def on_road(x, y, pad=0.0):
    return ROAD_DIST(x, y) < 160.0 + pad


def place_props(keep, road_poly, rock_clear):
    play_in = lambda x, y, m=0.0: abs(x) < BOUND + m and abs(y) < BOUND + m
    from shapely.prepared import prep
    lake_cache = {}

    def in_lake(x, y, m=0.0):
        if m not in lake_cache:
            lake_cache[m] = prep(LAKE.buffer(m) if m else LAKE)
        return lake_cache[m].contains(Point(x, y))

    # ---- conifers. Inside the play area only on the blocking knolls; outside in stands that thicken up-screen.
    trees = []

    def tree(x, y, kind=None, force=False):
        if not force:
            if in_lake(x, y, 90) or on_road(x, y, 40):
                return False
            if not flat_around(x, y, 55):
                return False
            if any((x - tx) ** 2 + (y - ty) ** 2 < 150 ** 2 for tx, ty in trees):
                return False
        if kind is None:
            # nothing tall on the camera side of the field; tall firs at the back
            if x < -BOUND:
                return False
            kind = "ABCDE"[int(rng.choice(5, p=[0.12, 0.26, 0.3, 0.22, 0.10]))]
        inst("SM_Conifer_" + kind, x, y, scale=U(0.92, 1.08), sink=6.0)
        trees.append((x, y))
        return True

    for (x, y, rx, ry, h) in KNOLLS:
        tall = "C" if abs(x) < 2500 else "D"
        if x < -2000 and abs(y) < 1200:
            tall = "D"                                         # the two behind the player's start frame the default view
        tree(x + U(-30, 30), y + U(-30, 30), tall, force=True)
        if rng.random() < 0.6:
            tree(x + U(-70, 70), y + rx * 0.45 * (1 if rng.random() < 0.5 else -1), "A", force=True)
    # a few firs inside the play area, off the lane: each gets one small convex blocker at the trunk
    for i, (x, y, kind) in enumerate([(-1050, 1560, "C"), (-880, 1730, "B"), (420, 1900, "C"), (-2050, 1820, "B"), (1180, -1700, "C"),
                                      (1340, -1880, "B"), (-2300, -1620, "C"), (2420, -1180, "B"), (2300, 2050, "D"), (2120, 1900, "B"),
                                      (-1000, -2500, "C"), (760, 2560, "B"), (-880, -1180, "B"), (640, 1240, "A"),
                                      (-190, 970, "C"), (-40, 1060, "B"), (130, -650, "C"), (-10, -770, "B"), (330, 760, "B"),
                                      (-2130, -360, "C"), (-2090, 420, "B"), (1750, 900, "C"), (1900, -520, "B"), (1050, 820, "A")]):
        if tree(x, y, kind, force=True):
            BLOCKERS.append({"label": "Fir_%02d_Collision" % i, "pos": [x, y, height_at(x, y) + 90.0], "size": [46, 46, 200], "yaw": 0})
    for (x, y) in CORE_TOPS:
        tree(x, y, "ABC"[int(rng.integers(0, 3))], force=True)
    for _ in range(26):                                        # loose stones in the field (ankle high: dressing only)
        cx, cy = U(-2800, 2800), U(-2800, 2800)
        if keep.contains(Point(cx, cy)) or on_road(cx, cy, 30):
            continue
        for _ in range(int(rng.integers(2, 5))):
            inst("SM_Rock_S%d" % rng.integers(0, 3), cx + float(rng.normal(0, 45)), cy + float(rng.normal(0, 45)), sink=9.0)
    stands = []
    for _ in range(150):
        x, y = U(-3000, 6900), U(-6300, 6300)
        if play_in(x, y, 240):
            continue
        stands.append((x, y, int(rng.integers(4, 10)), U(240, 520)))
    stands += [(3500, 1700, 9, 420), (3450, 2900, 8, 420), (3550, -200, 7, 360), (3900, 300, 8, 380), (-2400, 3500, 8, 400), (-800, 3450, 7, 380),
               (800, 3500, 8, 420), (2300, 3600, 8, 400), (1200, -3500, 7, 380), (-1000, -3550, 6, 360), (2600, -3550, 6, 360), (-2600, -3600, 6, 380),
               (4300, 2300, 10, 520), (4700, 800, 9, 480), (5200, 3300, 10, 560), (4900, -700, 8, 420)]
    for cx, cy, num, spread in stands:
        for _ in range(num):
            a, d = U(0, 2 * math.pi), spread * math.sqrt(U(0.02, 1.0))
            x, y = cx + math.cos(a) * d, cy + math.sin(a) * d
            if play_in(x, y, 150):
                continue
            if tree(x, y) and rng.random() < 0.5:
                a2 = U(0, 2 * math.pi)
                fx, fy = x + math.cos(a2) * U(80, 170), y + math.sin(a2) * U(80, 170)
                if not on_road(fx, fy) and not in_lake(fx, fy, 30) and not (play_in(fx, fy) and keep.contains(Point(fx, fy))):
                    inst("SM_Tuft_Fern", fx, fy, yaw=U(-35, 35))
    for i in range(60):                                        # backdrop hills: big firs, sparse
        x, y = U(7000, 12000), U(-8800, 8800)
        if height_at(x, y) > 100 and flat_around(x, y, 80):
            inst("SM_Conifer_" + "DE"[int(rng.integers(0, 2))], x, y, scale=U(1.1, 1.5), sink=6.0)

    # ---- cliff-foot dressing: rocks, ferns, the odd log, wherever a wall meets lower ground
    feet = 0
    for t in TIERS:
        if t["top"] - t["below"] < 30 or t["group"].startswith("SM_T_Backdrop"):
            continue
        ring = t["poly"].exterior
        d = U(0, 300)
        while d < ring.length:
            p = ring.interpolate(d)
            p2 = ring.interpolate(min(d + 5.0, ring.length))
            ex, ey = p2.x - p.x, p2.y - p.y
            ln = math.hypot(ex, ey) or 1.0
            nx, ny = ey / ln, -ex / ln                         # outward for a CCW ring
            if t["poly"].exterior.is_ccw is False:
                nx, ny = -nx, -ny
            off = U(26, 70)
            x, y = p.x + nx * off, p.y + ny * off
            d += U(170, 520)
            if x < WX0 + 200 or x > 6800 or abs(y) > 6300 or in_lake(x, y, 20) or on_road(x, y, -60):
                continue
            if play_in(x, y) and (keep.contains(Point(x, y)) or rock_clear.contains(Point(x, y))):
                continue
            if abs(height_at(x, y) - t["below"]) > 1.0:
                continue
            roll = rng.random()
            if roll < 0.34:
                inst("SM_Rock_S%d" % rng.integers(0, 3), x, y, sink=5.0)
            elif roll < 0.42 and not play_in(x, y, 60):
                inst("SM_Rock_M%d" % rng.integers(0, 3), x, y, sink=10.0)
            elif roll < 0.72:
                inst("SM_Tuft_Fern", x, y, yaw=U(-35, 35))
            elif roll < 0.95:
                for _ in range(int(rng.integers(2, 5))):
                    inst("SM_Tuft_Tall", x + U(-30, 30), y + U(-30, 30), yaw=U(-30, 30))
            elif not play_in(x, y, 80):
                inst("SM_Log", x + nx * 40, y + ny * 40, yaw=math.degrees(math.atan2(ey, ex)) - 90 + U(-25, 25))
            feet += 1

    # ---- outcrops outside the play area (decoration only)
    for i in range(34):
        for _ in range(30):
            x, y = U(-4300, 6800), U(-6200, 6200)
            if not play_in(x, y, 320) and not in_lake(x, y, 200) and not on_road(x, y, 120) and flat_around(x, y, 150):
                break
        else:
            continue
        big = "SM_Rock_%s%d" % ("M" if (x < -BOUND or rng.random() < 0.45) else "L", rng.integers(0, 3))
        inst(big, x, y, sink=12.0)
        for _ in range(int(rng.integers(2, 5))):
            a, d = U(0, 2 * math.pi), U(110, 220)
            inst("SM_Rock_S%d" % rng.integers(0, 3), x + math.cos(a) * d, y + math.sin(a) * d, sink=4.0)

    # ---- grass: blade cards in clumps over the turf (units wade through them; no collision, no shadow)
    n = 0
    for _ in range(3400):
        cx, cy = U(-4300, 6600), U(-5600, 5600)
        if in_lake(cx, cy, 10):
            continue
        dry = SPLAT_DRY(cx, cy)
        road = ROAD_DIST(cx, cy)
        if road < 170:
            continue
        kind = "SM_Tuft_Dry" if rng.random() < dry * 0.6 else ("SM_Tuft_Tall" if rng.random() < 0.55 else "SM_Tuft_Short")
        in_field = play_in(cx, cy)
        count = int(rng.integers(2, 6)) if in_field else int(rng.integers(3, 8))
        for _ in range(count):
            x, y = cx + float(rng.normal(0, 34)), cy + float(rng.normal(0, 34))
            if ROAD_DIST(x, y) < 160 or in_lake(x, y):
                continue
            inst(kind, x, y, yaw=U(-32, 32), scale=1.0)
            n += 1
    for _ in range(46):                                        # flower patches
        cx, cy = U(-3600, 5200), U(-4800, 4800)
        if in_lake(cx, cy, 40) or ROAD_DIST(cx, cy) < 260:
            continue
        for _ in range(int(rng.integers(2, 5))):
            inst("SM_Tuft_Flower", cx + float(rng.normal(0, 50)), cy + float(rng.normal(0, 50)), yaw=U(-30, 30))

    # ---- the in-field ruin (blocking: one convex box each) and the far gate ruin
    def ruin_piece(mesh, x, y, yaw, label, block=None):
        actor(mesh, x, y, yaw, "sandstone", label, "Props/Ruin")
        if block:
            z = height_at(x, y)
            BLOCKERS.append({"label": label + "_Collision", "pos": [x, y, z + block[2] * 0.5 - 6.0], "size": list(block), "yaw": yaw})

    rx_, ry_ = -560.0, -900.0
    ruin_piece("SM_Ruin_Pillar", rx_ + 120, ry_ - 150, 8, "Ruin_Pillar_A", (88, 88, 320))
    ruin_piece("SM_Ruin_PillarBroken", rx_ + 130, ry_ + 170, -6, "Ruin_Pillar_B", (88, 88, 190))
    ruin_piece("SM_Ruin_Wall", rx_ - 60, ry_ - 20, 4, "Ruin_Wall", (60, 370, 190))
    ruin_piece("SM_Ruin_Block", rx_ + 200, ry_ + 40, 35, "Ruin_Block_A")
    ruin_piece("SM_Ruin_Block", rx_ + 60, ry_ + 300, -50, "Ruin_Block_B")
    actor("SM_BannerPole", rx_ + 150, ry_ - 60, 0, "wood", "Ruin_BannerPole", "Props/Ruin")
    actor("SM_BannerCloth", rx_ + 150, ry_ - 60, 0, "banner", "Ruin_Banner", "Props/Ruin")
    for i, (dx, dy, mesh) in enumerate([(-190, -330, "SM_Menhir_1"), (-230, 280, "SM_Menhir_2")]):
        actor(mesh, rx_ + dx, ry_ + dy, U(0, 360), "rock", "Ruin_Stone_%d" % i, "Props/Ruin")
    gx, gy = 3560.0, 860.0                                     # gate on the road where it leaves the field
    ruin_piece("SM_Ruin_Pillar", gx, gy - 300, 4, "Gate_Pillar_A")
    ruin_piece("SM_Ruin_Pillar", gx + 40, gy + 330, -5, "Gate_Pillar_B")
    ruin_piece("SM_Ruin_Wall", gx + 20, gy - 560, 2, "Gate_Wall_A")
    ruin_piece("SM_Ruin_Wall", gx + 70, gy + 600, 184, "Gate_Wall_B")
    ruin_piece("SM_Ruin_Block", gx - 150, gy - 200, 70, "Gate_Block")
    actor("SM_BannerPole", gx - 30, gy + 250, 0, "wood", "Gate_BannerPole", "Props/Ruin")
    actor("SM_BannerCloth", gx - 30, gy + 250, 0, "banner", "Gate_Banner", "Props/Ruin")
    for i, (x, y) in enumerate([(3300, -2050), (3420, -2330), (3250, -2600)]):      # standing stones by the water
        actor("SM_Menhir_%d" % (i % 3), x, y, U(0, 360), "rock", "Shore_Stone_%d" % i, "Props/Rocks")

    # ---- fences, stumps and logs: bits of an old boundary near the player's start and along the road
    for i, (x, y, yaw, kind) in enumerate([(-2060, -520, 6, "A"), (-2080, -280, -4, "B"), (-2030, 430, 3, "A"), (-2000, 680, 12, "B"),
                                           (-1750, 900, 70, "A"), (700, 620, 80, "B"), (2500, 760, 100, "A"), (2700, 830, 105, "B"),
                                           (-3300, -700, 0, "A"), (-3300, -940, 5, "B"), (-3350, 300, -6, "A")]):
        actor("SM_Fence_" + kind, x, y, yaw, "wood", "Fence_%02d" % i, "Props/Fences")
    for i, (x, y) in enumerate([(-1650, -640), (-2250, 250), (380, 760), (1950, -350), (-3200, 1500), (3300, 1500)]):
        actor("SM_Stump", x, y, U(0, 360), "log", "Stump_%d" % i, "Props/Logs")
    for i, (x, y, yaw) in enumerate([(-1560, 700, 25), (1120, -420, -40), (-2600, -150, 80), (2850, -1500, 10)]):
        actor("SM_Log", x, y, yaw, "log", "Log_%d" % i, "Props/Logs")
    print("tufts %d, cliff-foot props %d, trees %d" % (n, feet, len(trees)))


# ============================================================================================ kingdoms
# Buildings on the field: (type, x, y, yaw, team 0 player / 1 enemy, label). Types are the models under
# SourceArt/Buildings (Tools/blender/build_building.py); <type>.json gives the blocking footprint and the sockets.
# A building's front (gate, adit, yard) faces -X at yaw 0, toward the game camera.
BUILDINGS = [
    ("castle", -2000.0, -1300.0, 0.0, 0, "Castle_Player"),
    ("mine", -2570.0, -2550.0, 0.0, 0, "Mine_Player"),
    ("farm", -2500.0, 620.0, 0.0, 0, "Farm_Player"),
    ("castle", 2250.0, -1100.0, 0.0, 1, "Castle_Enemy"),
]
# Terrain that stood where a kingdom now is. It is still generated (so every random draw downstream is unchanged and
# the rest of the world stays exactly as it was) and removed afterwards by apply_kingdoms().
KINGDOM_REMOVES = {"SM_T_Field_02", "SM_T_Field_03", "SM_T_Knoll_03", "SM_T_Knoll_08", "SM_T_Knoll_09"}
KINGDOM_REMOVE_ROCKS = {"Rock_SW"}
# footpaths (bare earth), world polylines: the castle court to the road, the road to the farm yard, the court to the mine
KINGDOM_PATHS = [
    [(-2760, -1300), (-2800, -900), (-2740, -520), (-2640, -240)],
    [(-2960, -250), (-3010, 60), (-2960, 380)],
    [(-2800, -1560), (-2960, -1900), (-3010, -2330), (-2960, -2550)],
    [(1420, -1100), (1280, -600), (1330, -60)],
]
_META = {}


def building_meta(kind):
    if kind not in _META:
        with open(os.path.join(ROOT, "SourceArt", "Buildings", kind + ".json")) as f:
            _META[kind] = json.load(f)
    return _META[kind]


def to_world(x, y, yaw, p):
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    return (x + p[0] * c - p[1] * s, y + p[0] * s + p[1] * c)


def footprint_poly(kind, x, y, yaw, pad=0.0):
    x0, y0, x1, y1 = building_meta(kind)["footprint"]
    b = box(x0 - pad, y0 - pad, x1 + pad, y1 + pad)
    return affinity.translate(affinity.rotate(b, yaw, origin=(0, 0)), x, y)


def court_poly(kind, x, y, yaw):
    """The paved court before a castle gate (local x in front of the footprint)."""
    x0, y0, x1, y1 = building_meta(kind)["footprint"]
    b = box(x0 - 400, -340, x0 + 10, 340)
    return affinity.translate(affinity.rotate(b, yaw, origin=(0, 0)), x, y)


def apply_kingdoms():
    """Clears the ground for the buildings after the world has been generated: removes / trims terraces, re-seats or
    drops the dressing that stood there, and returns the placements for the level builder."""
    global HM
    from shapely.prepared import prep
    feet = [footprint_poly(k, x, y, yaw) for k, x, y, yaw, team, label in BUILDINGS]
    courts = [court_poly(k, x, y, yaw) for k, x, y, yaw, team, label in BUILDINGS if k == "castle"]
    paths = [LineString(p).buffer(95) for p in KINGDOM_PATHS]
    flat = unary_union([f.buffer(230, 3) for f in feet] + [c.buffer(120, 3) for c in courts])     # no ledges this close
    clear = unary_union([f.buffer(70, 3) for f in feet] + [c.buffer(20, 3) for c in courts] + paths)  # no dressing here
    old = HM
    kept = []
    for t in TIERS:
        if t["group"] in KINGDOM_REMOVES:
            continue
        if t["poly"].intersects(flat) and not t["poly"].interiors:
            for p in clean(t["poly"].difference(flat), 20000.0):
                if not p.interiors:
                    kept.append(dict(t, poly=p))
            continue
        kept.append(t)
    TIERS[:] = kept
    live = set(t["group"] for t in TIERS)
    for g in list(GROUPS):
        if g not in live:
            del GROUPS[g]
    HM = rasterize_heights()

    def old_h(x, y):
        r, c = int((x - WX0) / HM_RES), int((y - WY0) / HM_RES)
        return float(old[r, c]) if 0 <= r < old.shape[0] and 0 <= c < old.shape[1] else 0.0

    inside = prep(clear)
    dropped = moved = 0
    gone_trees = []
    for mesh, lst in INSTANCES.items():
        out = []
        for it in lst:
            x, y = it[0], it[1]
            dz = old_h(x, y) - height_at(x, y)
            if inside.contains(Point(x, y)) or (abs(dz) > 0.5 and mesh.startswith("SM_Conifer")):
                dropped += 1
                if mesh.startswith("SM_Conifer"):
                    gone_trees.append((x, y))
                continue
            if abs(dz) > 0.5:
                it[2] = round(it[2] - dz, 1)
                moved += 1
            out.append(it)
        lst[:] = out
    for lst, key in ((ACTORS, "label"), (BLOCKERS, "label")):
        out = []
        for a in lst:
            x, y = a["pos"][0], a["pos"][1]
            name = a[key].replace("_Collision", "")
            if inside.contains(Point(x, y)) or name in KINGDOM_REMOVE_ROCKS:
                dropped += 1
                continue
            if name.startswith("Fir_") and any(abs(x - tx) < 1 and abs(y - ty) < 1 for tx, ty in gone_trees):
                continue
            dz = old_h(x, y) - height_at(x, y)
            if abs(dz) > 0.5:
                a["pos"][2] = round(a["pos"][2] - dz, 1)
            out.append(a)
        lst[:] = out
    placed = []
    for kind, x, y, yaw, team, label in BUILDINGS:
        meta = building_meta(kind)
        worst = max(height_at(px, py) for px, py in footprint_poly(kind, x, y, yaw, 40.0).exterior.coords)
        if worst > 0.5:
            print("WARNING: ground under %s is not flat (%.0f cm)" % (label, worst))
        placed.append({"type": kind, "mesh": meta["mesh"], "label": label, "team": team, "pos": [x, y, 0.0], "yaw": yaw,
                       "footprint": meta["footprint"], "ring_radius": meta["ring_radius"],
                       "colliders": meta["colliders"], "sockets": meta["sockets"]})
    # two firs to frame the opening view again, where the knolls behind the player's start used to carry them
    for (x, y, kind) in ((-2360.0, -420.0, "B"), (-1960.0, 1250.0, "D"), (-2740.0, -640.0, "A")):
        if not inside.contains(Point(x, y)):
            inst("SM_Conifer_" + kind, x, y, yaw=37.0, scale=1.0, sink=6.0)
            BLOCKERS.append({"label": "Fir_K%d_Collision" % int(abs(x + y)), "pos": [x, y, height_at(x, y) + 90.0], "size": [46, 46, 200], "yaw": 0})
    print("kingdoms: %d buildings, dressing dropped %d, re-seated %d" % (len(placed), dropped, moved))
    return placed


# ============================================================================================ splat map
def splat_grid():
    px = SPLAT_SIZE / SPLAT_RES
    xs = SPLAT_ORIGIN[0] + (np.arange(SPLAT_RES) + 0.5) * px        # image column -> world X
    ys = SPLAT_ORIGIN[1] + (np.arange(SPLAT_RES) + 0.5) * px        # image row    -> world Y
    return np.meshgrid(xs, ys)


def dist_to_polyline(X, Y, pts):
    best = np.full(X.shape, 1e9, np.float32)
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        dx, dy = x1 - x0, y1 - y0
        L2 = dx * dx + dy * dy
        if L2 < 1e-6:
            continue
        t = np.clip(((X - x0) * dx + (Y - y0) * dy) / L2, 0.0, 1.0)
        d = np.hypot(X - (x0 + t * dx), Y - (y0 + t * dy))
        best = np.minimum(best, d)
    return best


def smooth_noise(shape, cell, seed):
    r = np.random.default_rng(seed)
    small = r.random((shape[0] // cell + 2, shape[1] // cell + 2)).astype(np.float32)
    return ndimage.zoom(small, cell, order=3)[:shape[0], :shape[1]]


def build_splat_fields():
    """R = road (0 turf .. 0.5 bare earth .. 1 set stones), G = moss, B = dry straw, A = baked shade (1 = none)."""
    X, Y = splat_grid()
    shape = X.shape
    wob = (smooth_noise(shape, 24, 1) - 0.5) * 150.0 + (smooth_noise(shape, 7, 2) - 0.5) * 50.0
    d_main = dist_to_polyline(X, Y, ROAD_MAIN) + wob
    d_branch = dist_to_polyline(X, Y, ROAD_BRANCH) + wob
    d_side = dist_to_polyline(X, Y, ROAD_SIDE) + wob
    road_d = np.minimum(d_main, d_branch + 25.0)

    def band(d, core, edge):
        return np.clip((edge - d) / (edge - core), 0.0, 1.0)

    paved = np.clip((smooth_noise(shape, 30, 8) - 0.34) * 5.0, 0.0, 1.0)             # the old paving survives in stretches
    R = band(road_d, 55.0, 105.0) * 0.5 * paved + band(road_d, 100.0, 165.0) * 0.5   # stones inside ~55, earth out to ~165
    R = np.maximum(R, band(d_side, 40.0, 120.0) * 0.52)                               # footpath: earth only
    worn = smooth_noise(shape, 40, 3)
    for (cx, cy, rad) in [(PLAYER_START[0], PLAYER_START[1], 520.0), (ENEMY_START[0], ENEMY_START[1], 520.0), (-560.0, -900.0, 330.0), (3560.0, 860.0, 520.0)]:
        dd = np.hypot(X - cx, Y - cy)
        R = np.maximum(R, np.clip((rad - dd) / rad, 0, 1) * (0.25 + worn * 0.45))      # trampled ground at camps and ruins
    R = np.maximum(R, np.clip((worn - 0.83) * 4.0, 0, 0.5))                           # a few bare scuffs
    # kingdoms: packed earth under and round each building, a cobbled court before a castle gate, footpaths
    wob2 = wob * 0.35
    paved2 = np.clip((smooth_noise(shape, 12, 9) - 0.22) * 4.0, 0.0, 1.0)
    for kind, bx, by, yaw, team, label in BUILDINGS:
        x0, y0, x1, y1 = building_meta(kind)["footprint"]
        c, sn = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        lx, ly = (X - bx) * c + (Y - by) * sn, -(X - bx) * sn + (Y - by) * c

        def rect_d(ax0, ay0, ax1, ay1):
            dx = np.maximum(np.maximum(ax0 - lx, lx - ax1), 0.0)
            dy = np.maximum(np.maximum(ay0 - ly, ly - ay1), 0.0)
            return np.hypot(dx, dy) + wob2

        R = np.maximum(R, band(rect_d(x0, y0, x1, y1), 30.0, 150.0) * (0.5 + worn * 0.08))
        if kind == "castle":
            R = np.maximum(R, band(rect_d(x0 - 380, -300, x0 + 20, 300), 0.0, 70.0) * (0.56 + 0.44 * paved2))
        elif kind == "mine":
            R = np.maximum(R, band(rect_d(x0 - 60, -150, x0 + 300, 150), 0.0, 60.0) * (0.56 + 0.3 * paved2))
    for pts in KINGDOM_PATHS:
        R = np.maximum(R, band(dist_to_polyline(X, Y, pts) + wob2, 34.0, 100.0) * 0.56)
    moss = smooth_noise(shape, 50, 4) * 0.75 + smooth_noise(shape, 14, 5) * 0.25
    dry = smooth_noise(shape, 60, 6) * 0.7 + smooth_noise(shape, 18, 7) * 0.3
    return X, Y, R, moss, dry, road_d


def finish_splat(X, Y, R, moss, dry):
    px = SPLAT_SIZE / SPLAT_RES
    # terrain height at splat resolution, to bake shade at cliff feet and damp moss there
    rows = np.clip(((X - WX0) / HM_RES).astype(int), 0, HM.shape[0] - 1)
    cols = np.clip(((Y - WY0) / HM_RES).astype(int), 0, HM.shape[1] - 1)
    hgt = HM[rows, cols]
    near_max = ndimage.maximum_filter(hgt, size=int(110 / px) * 2 + 1)
    foot = np.clip((near_max - hgt) / 150.0, 0.0, 1.0)
    foot = ndimage.gaussian_filter(foot, 2.2)
    shade = 1.0 - np.clip(foot * 0.3, 0.0, 0.15)
    G = np.clip((moss - 0.42) * 2.6, 0, 1)
    G = np.clip(G + foot * 0.4, 0, 1)                         # moss gathers under cliffs
    B = np.clip((dry - 0.6) * 3.2, 0, 1) * (1.0 - G)
    # the open battle lane is drier and more worn than the terraces
    img = np.dstack([R, G, B, shade])
    return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)


# ============================================================================================ preview
def write_preview(splat, path):
    x0, x1, y0, y1 = -4600, 7200, -6200, 6200
    scale = 0.1
    w, h = int((y1 - y0) * scale), int((x1 - x0) * scale)
    xs = x1 - (np.arange(h) + 0.5) / scale
    ys = y0 + (np.arange(w) + 0.5) / scale
    Yg, Xg = np.meshgrid(ys, xs)

    def hm(X, Y):
        r = np.clip(((X - WX0) / HM_RES).astype(int), 0, HM.shape[0] - 1)
        c = np.clip(((Y - WY0) / HM_RES).astype(int), 0, HM.shape[1] - 1)
        return HM[r, c]

    z = hm(Xg, Yg)
    si = np.clip(((Xg - SPLAT_ORIGIN[0]) / SPLAT_SIZE * SPLAT_RES).astype(int), 0, SPLAT_RES - 1)
    sj = np.clip(((Yg - SPLAT_ORIGIN[1]) / SPLAT_SIZE * SPLAT_RES).astype(int), 0, SPLAT_RES - 1)
    sp = splat[sj, si].astype(np.float32) / 255.0
    col = np.array([96, 112, 52], np.float32) * (1 - sp[..., 1:2] * 0.3) + np.array([40, 30, 0], np.float32) * sp[..., 2:3]
    col = col * (1 - sp[..., 0:1]) + np.array([150, 120, 85], np.float32) * sp[..., 0:1]
    col = col * (0.75 + np.clip(z, 0, 900)[..., None] / 900.0 * 0.9) * sp[..., 3:4]
    zs = hm(Xg - 14, Yg + 14)                                  # cheap relief
    col = np.where((zs > z + 5)[..., None], col * 0.55, np.where((zs < z - 5)[..., None], col * 1.25, col))
    col = np.where((z < -1)[..., None], np.array([40, 90, 100], np.float32), col)
    img = Image.fromarray(np.clip(col, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)

    def P(x, y):
        return ((y - y0) * scale, (x1 - x) * scale)

    d.rectangle([P(BOUND, -BOUND), P(-BOUND, BOUND)], outline=(255, 255, 255))
    for mesh, lst in INSTANCES.items():
        if mesh.startswith("SM_Conifer"):
            for x, y, z, yaw, s in lst:
                cx, cy = P(x, y)
                d.ellipse([cx - 7, cy - 7, cx + 7, cy + 7], fill=(25, 60, 30), outline=(10, 30, 15))
        elif mesh.startswith("SM_Rock"):
            for x, y, z, yaw, s in lst:
                cx, cy = P(x, y)
                rr = 2 if "_S" in mesh else (5 if "_M" in mesh else 9)
                d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(150, 145, 130))
    for b in BLOCKERS:
        cx, cy = P(b["pos"][0], b["pos"][1])
        d.rectangle([cx - 8, cy - 8, cx + 8, cy + 8], outline=(255, 60, 40))
    for a in ACTORS:
        cx, cy = P(a["pos"][0], a["pos"][1])
        d.rectangle([cx - 3, cy - 3, cx + 3, cy + 3], outline=(255, 220, 90))
    for kind, bx, by, yaw, team, label in BUILDINGS:
        d.polygon([P(x, y) for x, y in footprint_poly(kind, bx, by, yaw).exterior.coords], outline=(90, 150, 255) if team == 0 else (255, 90, 70))
    for (x, y), c in ((PLAYER_START, (80, 140, 255)), (ENEMY_START, (255, 80, 60))):
        cx, cy = P(x, y)
        d.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], outline=c, width=3)
    img.save(path)


# ============================================================================================ main
def main():
    global ROAD_DIST, SPLAT_DRY, HM
    X, Y, R, moss, dry, road_d = build_splat_fields()
    px = SPLAT_SIZE / SPLAT_RES

    def sample(arr, x, y, default):
        i = int((x - SPLAT_ORIGIN[0]) / px); j = int((y - SPLAT_ORIGIN[1]) / px)
        if 0 <= i < SPLAT_RES and 0 <= j < SPLAT_RES:
            return float(arr[j, i])
        return default

    ROAD_DIST = lambda x, y: sample(road_d, x, y, 9999.0)
    dry_amt = np.clip((dry - 0.6) * 3.2, 0, 1)
    SPLAT_DRY = lambda x, y: sample(dry_amt, x, y, 0.0)

    build_layout()
    buildings = apply_kingdoms()

    # ---- meshes
    meshes = []
    layout_terrain = []
    terrain = build_terrain_meshes()
    for name, m in terrain.items():
        pivot = m.recenter()
        meshes.append(m)
        layout_terrain.append({"mesh": name, "pos": list(pivot), "folder": GROUPS[name]})
    # ground: chunked caps (the lake cut out of it) + the shore wall + the lake bed + the water sheet
    world = box(WX0, WY0, WX1, WY1)
    ground = world.difference(LAKE)
    cell = 2500.0
    gi = 0
    for cx in np.arange(WX0, WX1, cell):
        for cy in np.arange(WY0, WY1, cell):
            piece = ground.intersection(box(cx - 1, cy - 1, cx + cell + 1, cy + cell + 1))
            for p in largest(piece, 10.0, all_parts=True):
                m = Mesh("SM_T_Ground_%02d" % gi)
                add_cap(m, p, 0.0)
                pivot = m.recenter()
                meshes.append(m)
                layout_terrain.append({"mesh": m.name, "pos": list(pivot), "folder": "Terrain/Ground"})
                gi += 1
    shore = Mesh("SM_T_Shore")
    add_wall(shore, ring_ccw(list(LAKE.exterior.coords), False), 0.0, LAKE_BED)
    add_cap(shore, LAKE.buffer(30), LAKE_BED)
    pivot = shore.recenter()
    meshes.append(shore)
    layout_terrain.append({"mesh": "SM_T_Shore", "pos": list(pivot), "folder": "Terrain/Shore"})
    water = Mesh("SM_Water")
    add_cap(water, LAKE.buffer(30), LAKE_SURFACE)
    wpivot = water.recenter()
    meshes.append(water)

    for name, x, y, size, yaw in BLOCK_ROCKS:                 # unique boulders over the collision boxes
        if name in KINGDOM_REMOVE_ROCKS:
            continue
        m = Mesh("SM_" + name)
        hull_rock(None, (size[0] * 1.22, size[1] * 1.22, size[2] * 1.15), 17, seed=zlib.crc32(name.encode()) % 1000, into=m, yaw=yaw)
        r2 = np.random.default_rng(zlib.crc32(name.encode()) % 977)
        for _ in range(int(r2.integers(2, 4))):
            a = math.radians(yaw) + r2.uniform(0, 2 * math.pi)
            k = r2.uniform(0.38, 0.55)
            hull_rock(None, (size[0] * k * 1.2, size[1] * k * 1.1, size[2] * k), 13, seed=int(r2.integers(1e6)), into=m,
                      offset=(math.cos(a) * size[0] * 0.5, math.sin(a) * size[1] * 0.5, 0.0), yaw=r2.uniform(0, 180))
        meshes.append(m)
    meshes += build_prop_meshes()

    out_mesh = os.path.join(ROOT, "SourceArt", "Meshes")
    os.makedirs(out_mesh, exist_ok=True)
    count = write_gltf(os.path.join(out_mesh, "battlefield.gltf"), meshes)
    tris = sum(len(m.idx) for m in meshes)

    # ---- splat
    splat = finish_splat(X, Y, R, moss, dry)
    Image.fromarray(splat).save(os.path.join(ROOT, "SourceArt", "Textures", "T_Splat.png"))

    # ---- layout
    layout = {
        "texel_cm": TEXEL, "bound": BOUND,
        "splat": {"origin": list(SPLAT_ORIGIN), "size": SPLAT_SIZE},
        "terrain": layout_terrain,
        "water": {"mesh": "SM_Water", "pos": list(wpivot), "surface": LAKE_SURFACE},
        "instances": INSTANCES, "actors": ACTORS, "blockers": BLOCKERS, "buildings": buildings,
    }
    os.makedirs(os.path.join(ROOT, "SourceArt", "World"), exist_ok=True)
    with open(os.path.join(ROOT, "SourceArt", "World", "layout.json"), "w") as f:
        json.dump(layout, f, separators=(",", ":"))
    os.makedirs(os.path.join(ROOT, "Saved", "WorldPreview"), exist_ok=True)
    write_preview(splat, os.path.join(ROOT, "Saved", "WorldPreview", "map.png"))
    print("meshes %d (%d tris), tiers %d, instances %d, actors %d, blockers %d" % (
        count, tris, len(TIERS), sum(len(v) for v in INSTANCES.values()), len(ACTORS), len(BLOCKERS)))


if __name__ == "__main__":
    main()
