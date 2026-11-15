#!/usr/bin/env python3
"""Offline generator for the battlefield diorama: terrain meshes, props, the ground splat map and
the placement list. Deterministic. Unreal only imports and places what this writes.

  Tools/.venv/bin/python Tools/world/gen_battlefield.py            (about 3 minutes)
  Tools/.venv/bin/python Tools/world/gen_battlefield.py --plan     (20 s: only the previews under Saved/, for layout work)
  -> SourceArt/Meshes/battlefield.gltf (+ .bin)   every static mesh, Unreal axes, cm (the buildings are separate:
                                                   Tools/blender/build_building.py; BUILDINGS below places them)
     SourceArt/Textures/T_Splat.png               ground blend map (see build_splat_fields)
     SourceArt/Textures/T_WaterMap.png            water data map for M_Water (see build_water_map)
     SourceArt/Textures/T_MinimapBase.png         the HUD minimap's base
     SourceArt/World/layout.json                  where everything goes (+ veins, river, fords, bridges, lanes)
     Saved/WorldPreview/map.png                   top-down preview (+X up, like the game camera)
     Saved/MapPreview/layout.png, report.txt      the plan as the walkability grid will read it, and its checks
  then, in the editor:  Tools/ue_py.py Tools/import_world_assets.py, build_visual_materials.py, build_battlefield_visuals.py

The field (see "the map's shape" below): two kingdoms in opposite corners, a river between them crossed only at two
fords and over the shrine island's two bridges, three lanes parted by a fir-wood belt and a rock ridge on each side,
a highland with two veins toward each far corner, the heights (a flat-topped hill with two ramps) beside each kingdom,
and mountains on the corners and edges. Point-symmetric: the enemy's half is the player's turned 180 degrees.

Rules honoured (Docs/VISUAL_CONTRACT.md): play area +/-14000 cm; both kingdoms' aprons, the spawn areas, the roads,
the fords and the island stay flat; ledges units should climb are <= 40 cm and ramps no steeper than 1 in 4; anything
taller blocks on purpose (ridge, knolls, crags, bluffs, tors, mountains, the heights' cliff); deep water has its bed
below -30 cm (the grid's water test), a ford's bed is above it. In-field ground stays under 8000 cm (the grid's trace).
Mountain shapes: SourceArt/World/Mountains/peak_<n>.npy (Tools/blender/build_mountains.py, A.N.T. Landscape).
  --probe=x,y prints the walkability grid round a spot (with --plan), for "why can't they get there".
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
BOUND = 14000.0                 # playable half extent (+/-3000, then +/-12000; the mountain pass added a 20 m ring)
CORE = 12000.0                  # the old bound: the kingdoms, the river, the lanes and the highlands were laid out inside it
# dressed world: the low camera sees far up-screen (+X), a little behind the near bound, wide at the back
WX0, WX1, WY0, WY1 = -17500.0, 23000.0, -20500.0, 20500.0
FAST = "--plan" in sys.argv     # planning run: coarse splat, thin grass, writes only the previews under Saved/ (about 4x quicker)
SPLAT_ORIGIN, SPLAT_SIZE, SPLAT_RES = (-18000.0, -22528.0), 45056.0, (1024 if FAST else 4096)     # world square the splat map covers
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


def add_tier(poly, top, below, group, folder, massif=None):
    """massif = (full top, full below, x of the mountain's centre): a mountain's tier, whose height depends on where
    the mountain stands (see near_squash); the twin across the map is re-scaled for its own position."""
    t = {"poly": poly, "top": float(top), "below": float(below), "group": group}
    if massif is not None:
        t["massif"] = massif
    TIERS.append(t)
    GROUPS[group] = folder


MOUNTAIN_FOOT = 120.0           # a mountain's first step, never squashed: always too tall to climb


def near_squash(x):
    """Mountains inside the field keep their plan on both halves of the map (fairness) but not their height: toward the
    camera's side (-X) they are squashed, so nothing tall stands between the camera and the troops; the far side
    (+X, the top of the screen) carries the full peaks."""
    return float(np.clip(0.3 + 0.7 * (x + BOUND) / (1.6 * BOUND), 0.3, 1.0))


def squashed(z, x):
    return z if z <= MOUNTAIN_FOOT else MOUNTAIN_FOOT + (z - MOUNTAIN_FOOT) * near_squash(x)


def mountain(name, folder, x, y, rx, ry, height, clip=None, inside=None, lobes=6, squash=False, split=0.3):
    """A stepped mountain: a broad cut base, then many tall narrow-ledged tiers that step in off-centre, so sheer faces
    stack up on one side and the summit is small. Steps grow taller toward the top. Returns the base polygons."""
    shape = chunk_shape(x, y, rx, ry, lobes)
    if shape is None:
        return []
    if clip is not None:
        shape = shape.difference(clip)
    if inside is not None:
        shape = shape.intersection(inside)
    base = clean(shape, 120000.0)[:2]
    if not base:
        return []
    n = int(np.clip(round(height / 230.0), 3, 13))
    w = np.linspace(0.75, 1.45, n) * np.array([U(0.8, 1.2) for _ in range(n)])
    steps = [MOUNTAIN_FOOT] + list((height - MOUNTAIN_FOOT) * w / w.sum())
    n0 = len(TIERS)
    stack(name, folder, base, steps, shrink=(0.9, 1.12), ledge=(38.0, 120.0), split=split)
    for t in TIERS[n0:]:
        if squash:
            t["massif"] = (t["top"], t["below"], x)
            t["top"], t["below"] = squashed(t["top"], x), squashed(t["below"], x)
    return base


RAMPS = []          # dicts: name, folder, left / right (edge points, bottom -> top), z (height at each), s (run), poly


def ring_path(ring, start, length, ccw=True, step=50.0):
    """Points every `step` cm along a closed ring, from arc length `start`, for `length` cm (wraps round)."""
    n = max(int(round(length / step)), 2)
    out = []
    for k in range(n + 1):
        p = ring.interpolate((start + (1.0 if ccw else -1.0) * length * k / n) % ring.length)
        out.append((p.x, p.y))
    return out


def add_ramp(name, folder, path, width, rise, run):
    """A ramp of earth along `path` (bottom first): it climbs `rise` cm over the first `run` cm and runs level after
    that (the landing where it meets the high ground). Troops walk it: keep rise / run under 0.25 (a grid cell may
    differ from its neighbour by StepHeight, 45 cm, diagonals included). Returns its footprint."""
    pts = np.array(path, float)
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    z = rise * np.clip(s / run, 0.0, 1.0)
    tan = np.gradient(pts, axis=0)
    tan /= np.maximum(np.linalg.norm(tan, axis=1, keepdims=True), 1e-9)
    nrm = np.stack([-tan[:, 1], tan[:, 0]], 1)                    # to the left of the way up
    left, right = pts + nrm * width * 0.5, pts - nrm * width * 0.5
    quads = [Polygon([left[i], right[i], right[i + 1], left[i + 1]]).buffer(0) for i in range(len(pts) - 1)]
    poly = largest(unary_union([q.buffer(1.0) for q in quads if not q.is_empty]))
    RAMPS.append({"name": name, "folder": folder, "left": left, "right": right, "z": z, "s": s, "poly": poly})
    GROUPS[name] = folder
    return poly


def mirror_ramp(r):
    m = dict(r, name=r["name"] + "m", left=-r["left"], right=-r["right"], poly=rot180(r["poly"]))
    RAMPS.append(m)
    GROUPS[m["name"]] = m["folder"]


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
        for part in LAKE.geoms:
            d.polygon(ring_px(part.exterior), fill=LAKE_BED)
        for part in LAKE.geoms:
            for hole in part.interiors:                        # islands
                d.polygon(ring_px(hole), fill=0.0)
    for t in sorted(TIERS, key=lambda t: t["top"]):
        d.polygon(ring_px(t["poly"].exterior), fill=t["top"])
        for hole in t["poly"].interiors:                       # a tier cut round something lower inside it
            d.polygon(ring_px(hole), fill=t["below"])
    for r in RAMPS:                                            # ramps last: short level treads (the mesh is a true slope)
        L, R, z = r["left"], r["right"], r["z"]
        for i in range(len(z) - 1):
            quad = [L[i], R[i], R[i + 1], L[i + 1]]
            d.polygon([((y - WY0) / HM_RES, (x - WX0) / HM_RES) for x, y in quad], fill=float(z[i] + z[i + 1]) * 0.5)
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


def add_wall(mesh, ring, top, bottom, solid_left=True, smooth_deg=38.0, rock=0.0):
    """Wall along a ring with the solid on its left (exterior rings CCW, holes CW).
    UV0 = (distance along the outline, depth below the top) in cm; UV1.x = wall height; UV1.y = 1 on a crag or mountain
    face (M_Terrain gives it living rock instead of the terraces' coursed strata)."""
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
        a = mesh.vert((p0[0], p0[1], top), (n0[0], n0[1], 0), (s * scale, 0.0), (height, rock))
        b = mesh.vert((p1[0], p1[1], top), (n1[0], n1[1], 0), (s1 * scale, 0.0), (height, rock))
        c = mesh.vert((p1[0], p1[1], bottom), (n1[0], n1[1], 0), (s1 * scale, height), (height, rock))
        d = mesh.vert((p0[0], p0[1], bottom), (n0[0], n0[1], 0), (s * scale, height), (height, rock))
        mesh.quad(a, d, c, b)       # CCW seen from outside
        s = s1


def add_ramp_mesh(m, r):
    """The ramp's sloping top and its two retaining walls (same UV rules as add_cap / add_wall)."""
    L, R, z, s = r["left"], r["right"], r["z"], r["s"]
    foot = -8.0
    for i in range(len(z) - 1):
        ds = max(s[i + 1] - s[i], 1e-6)
        fwd = (L[i + 1] + R[i + 1] - L[i] - R[i]) * 0.5
        fwd /= max(np.linalg.norm(fwd), 1e-9)
        slope = (z[i + 1] - z[i]) / ds
        nv = np.array([-fwd[0] * slope, -fwd[1] * slope, 1.0])
        nv /= np.linalg.norm(nv)
        quad = [(L[i], z[i]), (R[i], z[i]), (R[i + 1], z[i + 1]), (L[i + 1], z[i + 1])]
        ids = [m.vert((p[0], p[1], zz), nv, (p[1], -p[0])) for p, zz in quad]
        for a, b, c in ((0, 1, 2), (0, 2, 3)):
            pa, pb, pc = quad[a][0], quad[b][0], quad[c][0]
            if (pb[0] - pa[0]) * (pc[1] - pa[1]) - (pb[1] - pa[1]) * (pc[0] - pa[0]) > 0:
                m.tri(ids[a], ids[b], ids[c])
            else:
                m.tri(ids[a], ids[c], ids[b])
        if max(z[i], z[i + 1]) < 1.0:
            continue
        for p0, p1, z0, z1, s0, s1 in ((R[i], R[i + 1], z[i], z[i + 1], s[i], s[i + 1]), (L[i + 1], L[i], z[i + 1], z[i], s[i + 1], s[i])):
            e = p1 - p0
            out = np.array([e[1], -e[0]]) / max(np.linalg.norm(e), 1e-9)          # away from the ramp (it lies to the left of p0 -> p1)
            h0, h1 = z0 - foot, z1 - foot
            a = m.vert((p0[0], p0[1], z0), (out[0], out[1], 0), (s0, 0.0), (h0, 0.0))
            b = m.vert((p1[0], p1[1], z1), (out[0], out[1], 0), (s1, 0.0), (h1, 0.0))
            c = m.vert((p1[0], p1[1], foot), (out[0], out[1], 0), (s1, h1), (h1, 0.0))
            d = m.vert((p0[0], p0[1], foot), (out[0], out[1], 0), (s0, h0), (h0, 0.0))
            m.quad(a, d, c, b)


def build_terrain_meshes():
    meshes = {}
    for t in TIERS:
        m = meshes.setdefault(t["group"], Mesh(t["group"]))
        rock = 1.0 if (t["top"] - t["below"] >= 100.0 or t["top"] >= 250.0) else 0.0      # anything taller than a terrace step is a rock face
        add_cap(m, t["poly"], t["top"])
        add_wall(m, ring_ccw(list(t["poly"].exterior.coords)), t["top"], t["below"] - 8.0, rock=rock)
        for hole in t["poly"].interiors:
            add_wall(m, ring_ccw(list(hole.coords), False), t["top"], t["below"] - 8.0, rock=rock)
    for r in RAMPS:
        add_ramp_mesh(meshes.setdefault(r["name"], Mesh(r["name"])), r)
    return meshes


def peak_mesh(name, grid, size, height, yaw=0.0):
    """A sculpted backdrop mountain from an A.N.T. Landscape height grid (Tools/blender/build_mountains.py): faceted
    like the boulders, in the terrain material's conventions (flat faces take the world-aligned ground; steep ones take
    the cliff texture with u along the face and v = depth below the summit)."""
    # cut the sculpted slope into ledges and rock steps, like every other hill here: level shelves about 4.5 m apart
    # (they keep a tenth of their slope) joined by sheer risers
    steps = max(int(round(height / 450.0)), 3)
    q = grid * steps
    f = q - np.floor(q)
    grid = 0.9 * (np.floor(q) + np.clip((f - 0.78) / 0.22, 0.0, 1.0)) / steps + 0.1 * grid
    n = grid.shape[0]
    c, sn_ = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    ax = (np.arange(n) / (n - 1) - 0.5) * size
    X0, Y0 = np.meshgrid(ax, ax, indexing="ij")
    X, Y, Z = X0 * c - Y0 * sn_, X0 * sn_ + Y0 * c, grid * height - 12.0
    m = Mesh(name)
    for i in range(n - 1):
        for j in range(n - 1):
            p = [np.array((X[a, b], Y[a, b], Z[a, b])) for a, b in ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1))]
            if max(q[2] for q in p) < -8.0:
                continue
            for tri in ((p[0], p[1], p[2]), (p[0], p[2], p[3])) if (i + j) % 2 else ((p[0], p[1], p[3]), (p[1], p[2], p[3])):
                nv = np.cross(tri[1] - tri[0], tri[2] - tri[0])
                ln = np.linalg.norm(nv)
                if ln < 1e-6:
                    continue
                nv /= ln
                if nv[2] < 0:
                    tri, nv = (tri[0], tri[2], tri[1]), -nv
                if nv[2] > 0.5:
                    uvs = [(q[1], -q[0]) for q in tri]
                else:
                    t = np.array([-nv[1], nv[0], 0.0])
                    t /= max(np.linalg.norm(t), 1e-9)
                    uvs = [(float(np.dot(q, t)), float(height - q[2])) for q in tri]
                m.flat_tri(tri[0], tri[1], tri[2], uvs=uvs, uv1=(height, 1.0), normal=nv)
    return m


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


# ============================================================================================ layout
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


# ---- kingdoms: opposite corners (player bottom-left of the screen, enemy top-right), each with open ground all round
P_ANCHOR, E_ANCHOR = (-7000.0, -6400.0), (7000.0, 6400.0)
# Buildings on the field: (type, x, y, yaw, team 0 player / 1 enemy, label). Types are the models under
# SourceArt/Buildings (Tools/blender/build_building.py); <type>.json gives the blocking footprint and the sockets.
# A building's front (gate, adit, yard) faces -X at yaw 0, toward the game camera.
BUILDINGS = [
    ("castle", P_ANCHOR[0], P_ANCHOR[1], 0.0, 0, "Castle_Player"),
    ("farm", P_ANCHOR[0] + 250.0, P_ANCHOR[1] + 2500.0, 0.0, 0, "Farm_Player"),
    ("mine", P_ANCHOR[0] + 450.0, P_ANCHOR[1] - 2500.0, 0.0, 0, "Mine_Player"),
    ("castle", E_ANCHOR[0], E_ANCHOR[1], 0.0, 1, "Castle_Enemy"),
    ("farm", E_ANCHOR[0] - 250.0, E_ANCHOR[1] - 2500.0, 0.0, 1, "Farm_Enemy"),
    ("mine", E_ANCHOR[0] - 450.0, E_ANCHOR[1] + 2500.0, 0.0, 1, "Mine_Enemy"),
]
# Troops start in front of each castle, on the side facing the other kingdom.
PLAYER_START = (P_ANCHOR[0] + 1500.0, P_ANCHOR[1] + 1400.0)
ENEMY_START = (E_ANCHOR[0] - 1500.0, E_ANCHOR[1] - 1400.0)


# ---- the map's shape. Everything that matters to play is point-symmetric about the centre (a half turn swaps the
# kingdoms): it is authored or scattered for the player's half and turned 180 degrees for the enemy's.
def mir(p):
    """The same spot seen from the other kingdom."""
    return (-p[0], -p[1])


def rot180(geom):
    return affinity.rotate(geom, 180.0, origin=(0, 0))


# The river runs between the kingdoms from the hills beyond the far-left corner (a lake there feeds it) down to the near
# edge, right of centre. Laid out in river coordinates: s = distance upstream from the map centre, n = offset toward the
# enemy's bank. It parts round an island at the centre (two channels) and is deep everywhere except at two fords.
RIVER_AXIS = (0.8160, -0.5780)          # upstream
RIVER_PERP = (0.5780, 0.8160)           # toward the enemy's bank
FLOW_DIR = (-RIVER_AXIS[0], -RIVER_AXIS[1])


def sn(s, n):
    return (s * RIVER_AXIS[0] + n * RIVER_PERP[0], s * RIVER_AXIS[1] + n * RIVER_PERP[1])


def to_sn(x, y):
    return (x * RIVER_AXIS[0] + y * RIVER_AXIS[1], x * RIVER_PERP[0] + y * RIVER_PERP[1])


ISLE_S = 2900.0                         # the channels part and meet again this far up / down stream of the centre
RIVER_UP_KEYS = [(ISLE_S, 0), (3900, -450), (5100, 200), (6300, 520), (7300, 220), (8600, -420), (10000, -380), (11400, 350),
                 (12900, 450), (14700, 0), (16500, -500), (18300, -1200), (20200, -1700), (22000, -1900), (24500, -2100), (27000, -2000)]
CHANNEL_KEYS = [(ISLE_S, 0), (2000, -1050), (750, -1650), (-750, -1650), (-2000, -1050), (-ISLE_S, 0)]   # round the player's side
RIVER_UP = catmull([sn(*k) for k in RIVER_UP_KEYS], per=8)
RIVER_DOWN = [mir(p) for p in RIVER_UP]
CHANNEL_P = catmull([sn(*k) for k in CHANNEL_KEYS], per=8)
CHANNEL_E = [mir(p) for p in CHANNEL_P]
RIVER_HALF, CHANNEL_HALF = 300.0, 235.0  # half widths, cm: 6 m of deep water, 4.7 m in each channel
FORD_A = sn(7300, 220)                   # upstream ford (top-left lane); FORD_B is its twin downstream
FORD_B = mir(FORD_A)
FORD_HALF, FORD_RIVER_HALF = 700.0, 450.0   # a ford is 14 m wide along the river, which spreads to 9 m there
BRIDGE_HALF = 350.0                      # the two bridges onto the island are 7 m wide
LAKE_BED, LAKE_SURFACE, FORD_BED = -170.0, -16.0, -24.0
# The walkability grid (USRGridSubsystem) traces the ground: anything below -30 cm is water and blocked. Deep water has
# its bed at LAKE_BED; a ford's bed is FORD_BED, 8 cm under the surface: wet, walkable, and the water material paints it
# as pale gravel. The bridges are terrain slabs at ground level over the channels. No collision on the water sheet.

# Separating belts on the player's side (their twins stand on the enemy's): a fir wood between the centre lane and the
# top-left lane, a rock ridge between the centre lane and the bottom-right lane. Each stops short of the kingdom's apron,
# has one opening part-way and leaves a second between its end and the river bank.
# Seen from the player's castle the lanes leave at about 10 degrees (top-left), 42 (centre) and 85 (bottom-right) from +X;
# the wood runs out at about 17 and the ridge at 70, each from the apron's edge toward the river between the island and a
# ford, keeping clear of the island's channel. The wood has an opening part-way and its last stretch runs along the river,
# leaving a riverside meadow between the island and the ford; the ridge (39 m) is unbroken.
WOOD_KEYS = [(-3400.0, -5350.0), (-1300.0, -4750.0), (632.0, -4124.0), (2064.0, -4525.0), (3179.0, -4335.0), (3910.0, -3995.0)]
RIDGE_KEYS = [(-5717.0, -2876.0), (-5150.0, -1200.0), (-4700.0, 400.0), (-4250.0, 1700.0), (-3800.0, 2500.0)]
WOOD_ANGLE, RIDGE_ANGLE = 17.0, 70.0
BELT_GAP, BELT_RIVER_GAP, WOOD_HALF = 1300.0, 1300.0, 300.0
# The highlands: a stepped rocky upland in the far-left corner on the player's bank (twin: near-right corner on the
# enemy's), each with two veins. The other kingdom reaches it through the ford next to it.
HIGHLAND_P = (8900.0, -9300.0)
HIGHLAND_R = (2700.0, 2400.0)
# The heights: each kingdom's own high ground, a flat-topped hill beside its apron (the player's is near-right of the
# castle, behind the stone lane; its twin stands beside the enemy's). A sheer cliff all round, PLATEAU_H tall, climbed by
# two earth ramps that hug the cliff: the home ramp starts on the castle's side, the field ramp on the side of the lane
# and ford B. The top is level building ground and carries the kingdom's safe gold vein.
PLATEAU_P = (-11500.0, -2150.0)
PLATEAU_R = (2000.0, 2500.0)
PLATEAU_H = 440.0
RAMP_WIDTH, RAMP_RUN, RAMP_LANDING = 900.0, 2200.0, 550.0      # 1 in 5 along the middle line
RAMP_HOME = (-28.0, False)       # (bearing of its foot from the hill's centre, degrees from +X; climbs counter-clockwise?)
RAMP_FIELD = (52.0, True)        # both feet are on the hill's front, toward the castle and toward the lane; the heads are round its sides
PLATEAU_VEIN = (PLATEAU_P[0] - 250.0, PLATEAU_P[1] + 350.0)
# Mountains inside the field, player's half (twins on the enemy's): (x, y, rx, ry, full height). They stand in the ring the
# map gained and on its corners; the camera's side is squashed (near_squash), so their twins up-screen are the tall ones.
MASSIFS = [(12400.0, -12500.0, 2600.0, 2500.0, 2600.0),        # the far-left corner, behind the player's highland
           (-13800.0, 3700.0, 1450.0, 2400.0, 2200.0),         # near edge, right of the heights (twin: far edge, top centre)
           (-13900.0, -9700.0, 1400.0, 2300.0, 1900.0),        # near edge, behind the castle (twin: behind the enemy's)
           (2100.0, -13500.0, 2500.0, 1250.0, 1700.0),         # left edge, off the wooded lane
           (-5800.0, -13600.0, 1900.0, 1150.0, 1300.0)]        # left edge, behind the home mine
# Set dressing that needs level ground kept for it, player's half (twinned): ruins (an arch, wall and pillar) beside the
# king's road, on the wooded lane and by ford B; broken towers on the plain, under the highland and in the back corner;
# stone circles on the highland and in the quiet ground right of the heights. (x, y, yaw) / (x, y).
RUIN_SITES = [(-2300.0, -3500.0, 35.0), (1700.0, -7000.0, -10.0), (-8100.0, 3100.0, 75.0)]
TOWER_SITES = [(-3200.0, -700.0), (6600.0, -9500.0), (-11800.0, -11200.0)]
CIRCLE_SITES = [(9750.0, -8450.0), (-11900.0, 5600.0)]


def sites_keep():
    return unary_union([Point(x, y).buffer(820.0) for x, y, _ in RUIN_SITES] + [Point(x, y).buffer(560.0) for x, y in TOWER_SITES] +
                       [Point(x, y).buffer(800.0) for x, y in CIRCLE_SITES])


PLATEAU_POLY = None   # the player's heights (outline of the top)
RAMP_FEET = []        # where the player's two ramps start (x, y), home first

# Gold veins: the only places a mine can be built (layout.json "veins"; ASRBuilding placement rules read them).
ISLE_VEIN = sn(1450, 0)
GOLD_VEINS = [(P_ANCHOR[0] + 450.0, P_ANCHOR[1] - 2500.0), (E_ANCHOR[0] - 450.0, E_ANCHOR[1] + 2500.0),      # home (under the starting mines)
              PLATEAU_VEIN, (-PLATEAU_VEIN[0], -PLATEAU_VEIN[1]),                                            # safe expansion each: on the heights
              ISLE_VEIN, mir(ISLE_VEIN),                                                                     # contested: the shrine island
              (7900.0, -7900.0), (10000.0, -10000.0), (-7900.0, 7900.0), (-10000.0, 10000.0)]               # the highlands

# Roads. The king's road: from the near edge into the player's castle court, across the field and the island (two
# bridges), into the enemy court and away up-screen into the hills. Two earth roads take the flank lanes, one over each
# ford; a spur climbs from each to its highland.
ROAD_MAIN_KEYS = [(-7950.0, -6400.0), (-7700.0, -5000.0), (-6200.0, -4500.0), (-4300.0, -3300.0), (-2600.0, -2400.0), (-1150.0, -1350.0), (0.0, 0.0),
                  (1150.0, 1350.0), (2600.0, 2400.0), (4300.0, 3300.0), (5600.0, 4700.0), (6000.0, 5700.0), (6050.0, 6400.0)]
ROAD_MAIN = catmull([(-17500, -7300), (-15500, -7200), (-11500, -6900), (-9200, -6700)] + ROAD_MAIN_KEYS + [(5850, 7600), (6300, 9600), (7300, 11800), (9300, 14800), (12500, 17000), (17600, 18000), (22000, 19200)])
ROAD_TL_KEYS = [(-5600.0, -5300.0), (-2700.0, -6100.0), (400.0, -6300.0), (3300.0, -6000.0), FORD_A, (6900.0, -1700.0), (7200.0, 800.0), (6400.0, 2300.0), (5500.0, 3600.0), (5300.0, 4400.0)]
ROAD_TL = catmull(ROAD_TL_KEYS)                                     # top-left lane: player -> ford A -> enemy
ROAD_BR = [mir(p) for p in ROAD_TL][::-1]                           # bottom-right lane: player -> ford B -> enemy
ROAD_SPUR_P = catmull([(3300.0, -6000.0), (5600.0, -7000.0), (7900.0, -7900.0), (10000.0, -10000.0)])
ROAD_SPUR_E = [mir(p) for p in ROAD_SPUR_P]
FLANK_ROADS = [ROAD_TL, ROAD_BR, ROAD_SPUR_P, ROAD_SPUR_E]

LAKE = None           # all water: the river, its channels and the lake beyond the far-left corner (MultiPolygon)
ISLAND = None         # the river island (Polygon)
FORD_POLYS = []       # the two fords' beds (Polygon)
BRIDGE_POLYS = []     # the two bridge decks (Polygon)
SIDE_P = None         # the ground on the player's side of the river (Polygon)
WOOD_PARTS, RIDGE_PARTS, BELT_GAPS = [], [], []      # player's side: LineStrings, and the openings' centres
HIGHLAND_POLY = None  # player's highland (lower tier outline)

# the river's middle line as a table n(s), for "which bank is this point on"
_tab = sorted([to_sn(*p) for p in RIVER_DOWN] + [to_sn(*p) for p in RIVER_UP])
_TAB_S = np.array([t[0] for t in _tab] )
_TAB_N = np.array([t[1] for t in _tab])


def side_n(x, y):
    """Signed distance across the river from its middle line (cm, roughly): negative on the player's bank. Works on arrays."""
    s = x * RIVER_AXIS[0] + y * RIVER_AXIS[1]
    return x * RIVER_PERP[0] + y * RIVER_PERP[1] - np.interp(s, _TAB_S, _TAB_N)


def zone_of(x, y):
    """Region of the map, the same for both kingdoms (a point on the enemy's bank is judged from the enemy's castle):
    home (the apron), wood (the fir-wood flank: top-left lane for the player), plain (centre lane), stone (the rocky
    flank: bottom-right lane), highland, back (behind the castle)."""
    if side_n(x, y) > 0:
        x, y = -x, -y
    if ((x - HIGHLAND_P[0]) / HIGHLAND_R[0]) ** 2 + ((y - HIGHLAND_P[1]) / HIGHLAND_R[1]) ** 2 < 1.0:
        return "highland"
    dx, dy = x - P_ANCHOR[0], y - P_ANCHOR[1]
    if math.hypot(dx, dy) < 3400.0:
        return "home"
    a = math.degrees(math.atan2(dy, dx))
    if a < -25.0 or a > 115.0:
        return "back"
    return "wood" if a < WOOD_ANGLE else ("plain" if a < RIDGE_ANGLE else "stone")


def _line_parts(geom, min_len=250.0):
    if geom.is_empty:
        return []
    parts = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
    return [p for p in parts if p.geom_type == "LineString" and p.length > min_len]


def plan_water():
    """The river polygon (wobbled banks, cut like the plateaus), the island, the fords, the bridges."""
    global LAKE, ISLAND, SIDE_P
    r = np.random.default_rng(77)
    up, ch = LineString(RIVER_UP), LineString(CHANNEL_P)
    parts = [up.buffer(RIVER_HALF, 3), ch.buffer(CHANNEL_HALF, 3), Point(sn(ISLE_S, 0)).buffer(RIVER_HALF + 110, 3)]
    d_ford = up.project(Point(FORD_A))
    for line, half in ((up, RIVER_HALF), (ch, CHANNEL_HALF)):               # uneven banks
        d = 60.0
        while d < line.length:
            p = line.interpolate(d)
            if line is ch or abs(d - d_ford) > FORD_HALF + 500.0:
                k = float(r.uniform(0.82, 1.22)) if line is up else float(r.uniform(0.9, 1.12))
                parts.append(Point(p.x + float(r.normal(0, 45)), p.y + float(r.normal(0, 45))).buffer(half * k, 2))
            d += float(r.uniform(190, 330))
    from shapely.ops import substring
    parts.append(substring(up, d_ford - FORD_HALF - 260.0, d_ford + FORD_HALF + 260.0).buffer(FORD_RIVER_HALF, 3))    # the river spreads at the ford
    half = unary_union(parts)
    far_lake = unary_union([chunk_shape(CORE + 4200, -CORE - 1800, 2200, 2600, 6), rounded_box(CORE + 2600, -CORE - 400, 1300, 1500, 20, 420),
                            chunk_shape(CORE + 7400, -CORE - 3300, 2600, 2400, 6)])
    water = unary_union([half, rot180(half), far_lake]).intersection(box(WX0, WY0, WX1, WY1))
    water = water.buffer(-40, 2).buffer(40, 2)
    LAKE = MultiPolygon([p.simplify(8.0) for p in largest(water, 200000.0, all_parts=True)])
    holes = [Polygon(i) for part in LAKE.geoms for i in part.interiors]
    ISLAND = max(holes, key=lambda h: h.area)
    # fords: the stretch of river FORD_HALF either side of the crossing
    i = min(range(1, len(RIVER_UP) - 1), key=lambda k: math.hypot(RIVER_UP[k][0] - FORD_A[0], RIVER_UP[k][1] - FORD_A[1]))
    t = np.array(RIVER_UP[i + 1]) - np.array(RIVER_UP[i - 1])
    t /= np.linalg.norm(t)
    c = np.array(FORD_A)
    strip = LineString([tuple(c - t * FORD_HALF), tuple(c + t * FORD_HALF)]).buffer(1600, cap_style=2)
    ford = largest(strip.intersection(LAKE))
    FORD_POLYS[:] = [ford, rot180(ford)]
    # bridges: where the king's road crosses the two channels
    road = LineString(ROAD_MAIN)
    cross = [g for g in _line_parts(road.intersection(LAKE), 50.0) if g.centroid.distance(Point(0, 0)) < 3000 and side_n(g.centroid.x, g.centroid.y) < 0]
    a, b = np.array(cross[0].coords[0]), np.array(cross[0].coords[-1])
    dvec = (b - a) / np.linalg.norm(b - a)
    deck = LineString([tuple(a - dvec * 70.0), tuple(b + dvec * 70.0)]).buffer(BRIDGE_HALF, cap_style=2)
    BRIDGE_POLYS[:] = [deck, rot180(deck)]
    # the player's bank: everything on the near-left side of the river's middle line
    mid = [sn(-60000, _TAB_N[0])] + [sn(s, n) for s, n in zip(_TAB_S, _TAB_N)] + [sn(60000, _TAB_N[-1])]
    SIDE_P = Polygon(mid + [sn(60000, -90000), sn(-60000, -90000)]).buffer(0)


def plan_belts():
    """Cuts the wood and ridge lines to length (clear of the river bank) and opens the gap in each."""
    for keys, out, frac in ((WOOD_KEYS, WOOD_PARTS, 0.38), (RIDGE_KEYS, RIDGE_PARTS, None)):
        line = LineString(catmull(keys, per=6))
        parts = _line_parts(line.difference(LAKE.buffer(BELT_RIVER_GAP + WOOD_HALF)))
        line = min(parts, key=lambda l: l.distance(Point(keys[0])))        # the stretch from the apron to the bank
        if frac is None:
            out[:] = [line]
            continue
        g = line.interpolate(frac, normalized=True)
        BELT_GAPS.append((g.x, g.y))
        out[:] = _line_parts(line.difference(g.buffer(BELT_GAP * 0.5 + WOOD_HALF)))
    print("belts: wood %s m, ridge %s m" % (" + ".join("%.0f" % (l.length / 100) for l in WOOD_PARTS), " + ".join("%.0f" % (l.length / 100) for l in RIDGE_PARTS)))


def lane_keepout():
    """Ground that must stay flat and clear: both kingdoms and their aprons, both spawn areas, the king's road, the flank
    roads, the fords' approaches, the island, the belts' openings and the gold veins."""
    lane = LineString(ROAD_MAIN_KEYS).buffer(560)
    flank = unary_union([LineString(r).buffer(400) for r in FLANK_ROADS])
    spawns = unary_union([Point(PLAYER_START).buffer(900), Point(ENEMY_START).buffer(900)])
    kingdoms = unary_union([Point(x, y).buffer(1250 if k == "castle" else 950) for k, x, y, *_ in BUILDINGS])
    veins = unary_union([Point(x, y).buffer(800) for x, y in GOLD_VEINS])
    # room to build round each castle: a broad flat apron the player's farms and mines can go on
    aprons = unary_union([Point(P_ANCHOR).buffer(3400), Point(E_ANCHOR).buffer(3400)])
    fords = unary_union([Point(FORD_A).buffer(1500), Point(FORD_B).buffer(1500)])
    gaps = unary_union([Point(g).buffer(BELT_GAP * 0.5 + 150) for g in BELT_GAPS] + [Point(mir(g)).buffer(BELT_GAP * 0.5 + 150) for g in BELT_GAPS])
    heads = unary_union([b.buffer(700) for b in BRIDGE_POLYS])
    return unary_union([lane, flank, spawns, kingdoms, veins, aprons, fords, gaps, heads, ISLAND.buffer(250)])


TREE_LINE, ROCK_LINE, SNOW_LINE = 1300.0, 950.0, 2700.0      # cm: no firs above the first; M_Terrain's bare rock and snow start at the others
BLOCK_ROCKS = []      # name, x, y, (sx, sy, sz), yaw : blocking boulders (gameplay collision box each)
KNOLLS = []           # (x, y, rx, ry, height): blocking knolls with a tree or two
FIELD_TERRACES = []   # (x, y, rx, ry, walkable 40 cm steps, core steps)
FIELD_FIRS = []       # (x, y, kind): single firs on the player's side, each with a trunk blocker (and a twin)
CORE_TOPS = []        # (x, y) on top of each bluff, for trees
# Dressing by region, player's side (the enemy's is its mirror image): (zone, terraces, knolls, boulders, single firs).
# Far fewer than the old uniform scatter: the belts, the river and the highlands give the field its shape.
FIELD_SPEC = [("plain", 6, 2, 2, 8), ("wood", 8, 7, 4, 0), ("stone", 7, 5, 8, 5), ("back", 5, 4, 3, 6)]


def plan_field(keep, keep_open):
    """Scatters the in-field dressing over the player's half (Poisson-ish, with keep-outs), by region. `keep` also
    excludes the highland (terraces and knolls); `keep_open` does not (its boulders and firs)."""
    from shapely.prepared import prep
    taken = []
    keep_p = {}

    def kept(x, y, pad, which):
        if (pad, which) not in keep_p:
            keep_p[(pad, which)] = prep((keep if which else keep_open).buffer(pad))
        return keep_p[(pad, which)].contains(Point(x, y))

    def free(x, y, r, pad, which):
        if abs(x) > BOUND - r * 0.6 - 150 or abs(y) > BOUND - r * 0.6 - 150:
            return False
        if side_n(x, y) > -(r + 250.0) or kept(x, y, pad, which):
            return False
        return all((x - tx) ** 2 + (y - ty) ** 2 > (r + tr) ** 2 for tx, ty, tr in taken)

    def scatter(n, rmin, rmax, pad, zone, which=True, tries=30000):
        out = []
        for _ in range(tries):
            if len(out) >= n:
                break
            r = U(rmin, rmax)
            x, y = U(-BOUND, BOUND), U(-BOUND, BOUND)
            if zone_of(x, y) == zone and free(x, y, r, pad, which):
                taken.append((x, y, r))
                out.append((x, y, r))
        return out

    ri = 0
    for zone, n_ter, n_knoll, n_rock, n_fir in FIELD_SPEC:
        for x, y, r in scatter(n_ter, 420 if zone == "plain" else 450, 800 if zone == "plain" else 1000, 300.0, zone):
            if zone == "plain":                                # low single steps only: the centre lane stays open
                tiers, core = 1, []
            else:
                tiers = int(rng.integers(1, 3))
                core = [] if rng.random() < (0.2 if zone == "stone" else 0.4) else [U(90, 170) for _ in range(int(rng.integers(1, 4)))]
            FIELD_TERRACES.append((x, y, r * U(0.8, 1.1), r * U(0.75, 1.05), tiers, core))
        for x, y, r in scatter(n_knoll, 220, 320, 150.0, zone):
            crag = zone != "plain" and rng.random() < 0.55          # a rock crag, two or three times a knoll's height
            KNOLLS.append((x, y, r * U(0.9, 1.1) * (1.25 if crag else 1.0), r * U(0.9, 1.1) * (1.25 if crag else 1.0), U(260, 430) if crag else U(95, 140)))
        for x, y, r in scatter(n_rock, 170, 240, 120.0, zone):
            BLOCK_ROCKS.append(("Rock_%02d" % ri, x, y, (U(200, 320), U(170, 240), U(130, 210)), U(-60, 60)))
            ri += 1
        for x, y, r in scatter(n_fir, 90, 120, 80.0, zone):
            FIELD_FIRS.append((x, y, "ABBCC"[int(rng.integers(0, 5))]))
    for x, y, r in scatter(8, 170, 240, 120.0, "highland", which=False):       # the upland is strewn with boulders
        BLOCK_ROCKS.append(("Rock_%02d" % ri, x, y, (U(220, 340), U(180, 260), U(140, 230)), U(-60, 60)))
        ri += 1
    for x, y, r in scatter(3, 90, 120, 80.0, "highland", which=False):
        FIELD_FIRS.append((x, y, "AAB"[int(rng.integers(0, 3))]))


def build_ridge():
    """The rock ridge: a chain of cut slabs along RIDGE_PARTS, about 1.7 m at the foot (too tall to climb), a crest on
    that and a broken line of teeth on the crest: about 5 m of rock between the centre lane and the stone lane."""
    stop = unary_union([Point(g).buffer(BELT_GAP * 0.5) for g in BELT_GAPS] + [LAKE.buffer(BELT_RIVER_GAP), Point(P_ANCHOR).buffer(3550)])
    polys = []
    for k, line in enumerate(RIDGE_PARTS):
        blobs, d = [], 0.0
        while d <= line.length:
            p = line.interpolate(d)
            blobs.append(chunk_shape(p.x + U(-50, 50), p.y + U(-50, 50), U(250, 340), U(230, 320), 3))
            d += U(260, 360)
        body = unary_union([b for b in blobs if b is not None]).intersection(line.buffer(370)).difference(stop)
        for j, poly in enumerate(clean(body, 60000.0)):
            name = "SM_T_Ridge_%d%d" % (k, j)
            foot = U(150.0, 185.0)
            add_tier(poly, foot, 0.0, name, "Terrain/Ridges")
            polys.append(poly)
            for crest in clean(poly.buffer(-U(70, 95), 2), 30000.0):
                top = foot + U(150, 210)
                add_tier(crest, top, foot, name, "Terrain/Ridges")
                for spire in clean(crest.buffer(-U(75, 110), 2), 26000.0):          # a broken line of teeth along the crest
                    cut = unary_union([chunk_shape(spire.centroid.x + U(-500, 500), spire.centroid.y + U(-700, 700), U(260, 420), U(300, 520), 3) for _ in range(3)])
                    for tooth in clean(spire.intersection(cut), 22000.0):
                        add_tier(tooth, top + U(130, 230), top, name, "Terrain/Ridges")
                for _ in range(max(int(crest.area / 500000.0), 1)):
                    pt = crest.buffer(-60).representative_point() if rng.random() < 0.5 else crest.centroid
                    if crest.buffer(-50).contains(pt):
                        CORE_TOPS.append((pt.x + U(-20, 20), pt.y + U(-20, 20)))
    return polys


def build_highland(keep_base):
    """The player's highland: two broad walkable steps (40 cm each) with the veins on the upper one and a few rock tors."""
    global HIGHLAND_POLY
    hx, hy = HIGHLAND_P
    veins = [v for v in GOLD_VEINS if zone_of(*v) == "highland" and side_n(*v) < 0]
    limit = SIDE_P.difference(LAKE.buffer(560)).intersection(box(-BOUND + 150, -BOUND + 150, BOUND - 150, BOUND - 150))
    t1 = unary_union([chunk_shape(hx, hy, HIGHLAND_R[0] * 0.92, HIGHLAND_R[1] * 0.92, 7)] + [Point(v).buffer(1300) for v in veins]).intersection(limit)
    t1 = largest(t1.buffer(-60, 2).buffer(60, 2)).simplify(9.0)
    HIGHLAND_POLY = t1
    add_tier(t1, 40.0, 0.0, "SM_T_Highland_0", "Terrain/Highland")
    inner = unary_union([chunk_shape(hx + U(-150, 150), hy + U(-150, 150), HIGHLAND_R[0] * 0.66, HIGHLAND_R[1] * 0.66, 6)] + [Point(v).buffer(980) for v in veins])
    t2 = largest(inner.intersection(t1.buffer(-U(280, 380), 2)).buffer(-50, 2).buffer(50, 2)).simplify(9.0)
    add_tier(t2, 80.0, 40.0, "SM_T_Highland_0", "Terrain/Highland")
    clear = unary_union([Point(v).buffer(1150) for v in veins] + [LineString(ROAD_SPUR_P).buffer(330), sites_keep()])
    room = t2.buffer(-420, 2).difference(clear)
    made = []
    for _ in range(400):
        if len(made) >= 5 or room.is_empty:
            break
        minx, miny, maxx, maxy = room.bounds
        x, y = U(minx, maxx), U(miny, maxy)
        if not room.contains(Point(x, y)) or any(math.hypot(x - mx, y - my) < 1100 for mx, my in made):
            continue
        made.append((x, y))
        tor = chunk_shape(x, y, U(260, 400), U(240, 360), 4)
        if tor is None:
            continue
        tor = tor.intersection(t2.buffer(-120, 2)).difference(clear)
        for poly in clean(tor, 40000.0)[:1]:
            h = U(170, 260)
            name = "SM_T_Tor_%d" % len(made)
            add_tier(poly, 80.0 + h, 80.0, name, "Terrain/Highland")
            for top in clean(poly.buffer(-U(60, 90), 2), 20000.0)[:1]:
                h2 = U(150, 240)
                add_tier(top, 80.0 + h + h2, 80.0 + h, name, "Terrain/Highland")
                CORE_TOPS.append((top.representative_point().x, top.representative_point().y))
                for tip in clean(top.buffer(-U(55, 80), 2), 16000.0)[:1]:
                    add_tier(tip, 80.0 + h + h2 + U(120, 200), 80.0 + h + h2, name, "Terrain/Highland")
    return t1


def build_plateau():
    """The player's heights (see PLATEAU_P): one sheer-sided flat top and the two ramps up to it. Returns the ground it
    and its approaches take up (kept clear of everything else)."""
    global PLATEAU_POLY
    from shapely.geometry.polygon import orient
    cx, cy = PLATEAU_P
    limit = box(-BOUND + 320, -BOUND + 320, BOUND - 320, BOUND - 320).difference(unary_union([
        Point(P_ANCHOR).buffer(3400.0 + RAMP_WIDTH * 0.5), LAKE.buffer(1100.0), LineString(ROAD_BR).buffer(420.0 + RAMP_WIDTH + 120.0)]))
    shape = chunk_shape(cx, cy, PLATEAU_R[0], PLATEAU_R[1], 6)
    shape = largest(shape.buffer(450, 6).buffer(-450, 6).intersection(limit))
    shape = orient(largest(shape.buffer(-320, 6).buffer(320, 6)).simplify(6.0), 1.0)      # rounded, so a ramp can hug it
    ring = orient(shape.buffer(RAMP_WIDTH * 0.5 - 90.0, 8), 1.0).exterior
    ramps = []
    for i, (bearing, ccw) in enumerate((RAMP_HOME, RAMP_FIELD)):
        a = math.radians(bearing)
        start = ring.project(Point(cx + 9000.0 * math.cos(a), cy + 9000.0 * math.sin(a)))
        path = ring_path(ring, start, RAMP_RUN + RAMP_LANDING, ccw)
        ramps.append(add_ramp("SM_T_Ramp_%d" % i, "Terrain/Heights", path, RAMP_WIDTH, PLATEAU_H, RAMP_RUN))
        RAMP_FEET.append(path[0])
    # the top is cut 2 cm short of the ramps' real edges, so cap laps cap: a seam there would be a slot down to the ground
    # under the hill, and a troop's ground trace that found it would drop the troop inside
    cut = unary_union(ramps)
    top = largest(shape.difference(cut.buffer(-3.0)))
    PLATEAU_POLY = top
    add_tier(top, PLATEAU_H, 0.0, "SM_T_Heights", "Terrain/Heights")
    # rock buttresses against the cliff's back and a couple of crown rocks on the rim there (the sides without ramps)
    clear = unary_union([cut.buffer(260.0), Point(PLATEAU_VEIN).buffer(1000.0)])
    for k, bearing in enumerate((150.0, 178.0, 205.0, 232.0, 262.0, 22.0)):
        a = math.radians(bearing + U(-8, 8))
        far = Point(cx + 9000.0 * math.cos(a), cy + 9000.0 * math.sin(a))
        rim = shape.exterior.interpolate(shape.exterior.project(far))
        blob = chunk_shape(rim.x, rim.y, U(360, 520), U(360, 520), 4)
        if blob is None:
            continue
        for b in clean(blob.difference(shape.buffer(-4.0)).difference(clear).intersection(limit.buffer(250.0)), 40000.0)[:1]:
            h = U(150, 270)
            add_tier(b, h, 0.0, "SM_T_HeightsRock_%d" % k, "Terrain/Heights")
            for b2 in clean(b.buffer(-U(60, 90), 2).intersection(shape.buffer(170.0)), 20000.0)[:1]:
                add_tier(b2, min(h + U(110, 170), PLATEAU_H - 40.0), h, "SM_T_HeightsRock_%d" % k, "Terrain/Heights")
        if k in (1, 3):
            for c in clean(blob.intersection(top.buffer(-30.0)).intersection(rim.buffer(330.0)).difference(clear), 30000.0)[:1]:
                h = U(130, 210)
                add_tier(c, PLATEAU_H + h, PLATEAU_H, "SM_T_HeightsRock_%d" % k, "Terrain/Heights")
                for c2 in clean(c.buffer(-U(50, 70), 2), 14000.0)[:1]:
                    add_tier(c2, PLATEAU_H + h + U(110, 180), PLATEAU_H + h, "SM_T_HeightsRock_%d" % k, "Terrain/Heights")
                    CORE_TOPS.append((c2.representative_point().x, c2.representative_point().y))
    return unary_union([shape.buffer(RAMP_WIDTH + 260.0)] + [Point(f).buffer(1000.0) for f in RAMP_FEET])


def build_massifs(keep):
    """The mountains inside the field on the player's half (MASSIFS). Returns their base polygons."""
    polys = []
    for i, (x, y, rx, ry, h) in enumerate(MASSIFS):
        polys += mountain("SM_T_Massif_%d" % i, "Terrain/Mountains", x, y, rx, ry, h, clip=keep, inside=SIDE_P.buffer(-150.0), squash=True)
    return polys


PEAKS = []          # sculpted backdrop mountains: (height grid index, x, y, footprint cm, height cm, yaw)


def build_layout():
    global HM
    play = box(-BOUND, -BOUND, BOUND, BOUND)
    tall_zone_out = play.buffer(95, join_style=2)              # tiers taller than a step stay outside this
    road_poly = unary_union([LineString(ROAD_MAIN).buffer(180)] + [LineString(r).buffer(140) for r in FLANK_ROADS])

    lake_out = LAKE.buffer(110)
    wood_poly = unary_union([l.buffer(WOOD_HALF) for l in WOOD_PARTS])
    keep_base = unary_union([lane_keepout(), lake_out, wood_poly.buffer(160), sites_keep()])

    # ---- the player's half: ridge, highland, then the scattered dressing; all of it is mirrored for the enemy below
    n0 = len(TIERS)
    ridge_polys = build_ridge()
    keep_base = unary_union([keep_base] + [p.buffer(220) for p in ridge_polys])
    highland = build_highland(keep_base)
    keep_base = unary_union([keep_base, build_plateau()])
    keep = unary_union([keep_base, highland.buffer(200)])
    massifs = build_massifs(keep)
    keep_base = unary_union([keep_base] + [m.buffer(260) for m in massifs])
    keep = unary_union([keep, keep_base])
    plan_field(keep, keep_base)
    rock_clear_p = unary_union([Point(x, y).buffer(max(s[0], s[1]) * 0.5 + 150) for _, x, y, s, _ in BLOCK_ROCKS])

    # field terraces (walkable: 36-40 cm steps)
    for i, (x, y, rx, ry, tiers, core) in enumerate(FIELD_TERRACES):
        shape = chunk_shape(x, y, rx, ry, 5)
        shape = shape.intersection(SIDE_P).difference(unary_union([keep, rock_clear_p, road_poly.buffer(30)]))
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

    # blocking knolls
    for i, (x, y, rx, ry, h) in enumerate(KNOLLS):
        shape = chunk_shape(x, y, rx, ry, 3).intersection(SIDE_P).difference(unary_union([keep, road_poly]))
        base = clean(shape, 30000.0)
        if base:
            steps = [h * 0.62, h * 0.38] if h < 200.0 else [h * 0.4, h * 0.34, h * 0.26]
            stack("SM_T_Knoll_%02d" % i, "Terrain/Knolls", base[:1], steps, shrink=(0.7, 0.9), ledge=(34.0, 60.0), split=0.0)

    # ---- the enemy's half: the same, turned 180 degrees about the centre
    for t in TIERS[n0:]:
        if "massif" in t:                                       # the same plan, the height its own place allows
            full_top, full_below, mx = t["massif"]
            add_tier(rot180(t["poly"]), squashed(full_top, -mx), squashed(full_below, -mx), t["group"] + "m", GROUPS[t["group"]])
        else:
            add_tier(rot180(t["poly"]), t["top"], t["below"], t["group"] + "m", GROUPS[t["group"]])
    for r in list(RAMPS):
        mirror_ramp(r)
    KNOLLS.extend([(-x, -y, rx, ry, h) for x, y, rx, ry, h in list(KNOLLS)])
    CORE_TOPS.extend([mir(p) for p in list(CORE_TOPS)])
    BLOCK_ROCKS.extend([(name + "m", -x, -y, size, yaw) for name, x, y, size, yaw in list(BLOCK_ROCKS)])
    rock_clear = unary_union([Point(x, y).buffer(max(s[0], s[1]) * 0.5 + 150) for _, x, y, s, _ in BLOCK_ROCKS])
    keep = unary_union([keep, rot180(keep)])

    # ---- the centre: the shrine's paved dais on the island, the bridge decks, the fords' beds
    dais = Polygon([(620.0 * math.cos(math.radians(11.25 + 22.5 * k)), 620.0 * math.sin(math.radians(11.25 + 22.5 * k))) for k in range(16)])
    add_tier(dais, 24.0, 0.0, "SM_T_Shrine", "Terrain/Shrine")
    for i, deck in enumerate(BRIDGE_POLYS):                    # a stone slab from bank to bank, its underside just clear of the water
        add_tier(deck, 0.0, LAKE_SURFACE + 10.0, "SM_T_Bridge_%d" % i, "Terrain/Bridges")
    for i, ford in enumerate(FORD_POLYS):
        add_tier(ford, FORD_BED, LAKE_BED, "SM_T_Ford_%d" % i, "Terrain/Shore")

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

    B = BOUND
    k = 0
    # far side (top of screen): a low rank of cut steps at the field's edge, then two ranks of mountains, each taller
    for y in np.arange(-B - 2600, B + 2601, 1250):
        ring_stack("SM_T_Far_%02d" % k, B + 720 + U(-120, 160), y + U(-200, 200), U(780, 1050), U(620, 800), [U(90, 210) for _ in range(int(rng.integers(4, 7)))])
        k += 1
    # The sculpted peaks (A.N.T. Landscape height grids, Tools/blender/build_mountains.py): the mountain wall along the far
    # edge and at the far end of each flank. The camera never sees a horizon (it looks down at 30 to 58 degrees), only
    # some 35 m past the far edge and 45 m past a flank, so the peaks stand right at the field's edge with their skirts
    # on the first rank of steps; nothing is built farther out than can be seen. (grid, x, y, footprint, height, yaw)
    PEAKS[:] = [(0, B + 3300.0, -5200.0, 7200.0, 5600.0, 20.0), (2, B + 3900.0, 2000.0, 8400.0, 6800.0, 100.0), (4, B + 3300.0, 9000.0, 7000.0, 5200.0, 250.0),
                (5, 4800.0, -(B + 2900.0), 5800.0, 3800.0, 60.0), (1, 3200.0, B + 2900.0, 5800.0, 3600.0, 140.0), (3, -3800.0, -(B + 2700.0), 5000.0, 1500.0, 0.0),
                (3, -2800.0, B + 2600.0, 4800.0, 1400.0, 200.0)]
    under_peak = lambda x, y: any(math.hypot(x - px_, y - py_) < size * 0.36 for _, px_, py_, size, _, _ in PEAKS)
    outside = unary_union([lake_out, road_poly, keep, tall_zone_out])
    for y in np.arange(-B - 3000, B + 3001, 1700):
        if not under_peak(B + 2500, y):
            mountain("SM_T_Far_%02d" % k, "Terrain/Mountains", B + 2500 + U(-200, 250), y + U(-250, 250), U(1250, 1650), U(950, 1250), U(1700, 2700), clip=outside)
        k += 1
    # flanks (screen left and right): steps at the edge, mountains behind them that grow toward the far side
    for side in (-1, 1):
        for x in np.arange(-B + 300, B + 1, 1150):
            far = (x + B) / (2 * B)
            n = int(rng.integers(2, 4)) + (1 if far > 0.5 else 0)
            ring_stack("SM_T_Flank_%02d" % k, x + U(-200, 200), side * (B + 900 + U(-150, 250)), U(620, 900), U(700, 950), [U(60, 110) * (0.8 + far) for _ in range(n)])
            k += 1
        for x in np.arange(-B + 1000, B + 1001, 1700):
            far = float(np.clip((x + B) / (2 * B), 0.0, 1.0))
            if not under_peak(x, side * (B + 2450)):
                mountain("SM_T_Flank_%02d" % k, "Terrain/Mountains", x + U(-250, 250), side * (B + 2450 + U(-150, 250)), U(1050, 1400), U(950, 1250),
                         U(450, 700) + 2300.0 * far * U(0.8, 1.2), clip=outside)
            k += 1
    # near side (bottom of screen): low steps only, so nothing hides the field from the camera
    for y in np.arange(-B - 1200, B + 1201, 1200):
        ring_stack("SM_T_Near_%02d" % k, -B - 900 + U(-200, 150), y + U(-250, 250), U(560, 800), U(600, 850), [U(34, 48)] if rng.random() < 0.6 else [])
        k += 1
    HM = rasterize_heights()

    # ---- blocking rocks: gameplay footprints, visible stone is a unique mesh per rock
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

    # ---- gold veins: an ore outcrop at each (dressing; the gameplay vein is the layout point)
    for i, (x, y) in enumerate(GOLD_VEINS):
        actor("SM_GoldVein", x, y, U(0, 360), "ore", "GoldVein_%02d" % i, "Props/Veins", z=height_at(x, y))

    place_props(keep, road_poly, rock_clear)


def on_road(x, y, pad=0.0):
    return ROAD_DIST(x, y) < 160.0 + pad


def place_props(keep, road_poly, rock_clear):
    B = BOUND
    play_in = lambda x, y, m=0.0: abs(x) < B + m and abs(y) < B + m
    from shapely.prepared import prep
    lake_cache = {}
    keep_prep = prep(keep)

    def in_lake(x, y, m=0.0):
        if m not in lake_cache:
            lake_cache[m] = prep(LAKE.buffer(m) if m else LAKE)
        return lake_cache[m].contains(Point(x, y))

    # ---- conifers. Inside the play area on the knolls, bluffs and as scattered single firs; outside in stands.
    trees = []

    def tree(x, y, kind=None, force=False):
        if not force:
            if in_lake(x, y, 90) or on_road(x, y, 40) or height_at(x, y) > TREE_LINE:
                return False
            if not flat_around(x, y, 55):
                return False
            if any((x - tx) ** 2 + (y - ty) ** 2 < 150 ** 2 for tx, ty in trees[-400:]):
                return False
        if kind is None:
            if x < -B:                                         # nothing tall on the camera side of the field
                return False
            kind = "ABCDE"[int(rng.choice(5, p=[0.12, 0.26, 0.3, 0.22, 0.10]))]
        inst("SM_Conifer_" + kind, x, y, scale=U(0.92, 1.08), sink=6.0)
        trees.append((x, y))
        return True

    for (x, y, rx, ry, h) in KNOLLS:
        if height_at(x, y) < 50.0:                             # the knoll was cut away by a keep-out
            continue
        tree(x + U(-30, 30), y + U(-30, 30), "CD"[int(rng.integers(0, 2))], force=True)
        if rng.random() < 0.6:
            tree(x + U(-70, 70), y + rx * 0.45 * (1 if rng.random() < 0.5 else -1), "A", force=True)

    # Blocking trees inside the field always come in pairs, one each side of the map (both stand or neither does).
    def trunk_ok(x, y, pad, check_keep):
        if not play_in(x, y, -80) or in_lake(x, y, 110) or on_road(x, y, pad) or not flat_around(x, y, 60):
            return False
        if check_keep and keep_prep.contains(Point(x, y)):
            return False
        return all((x - tx) ** 2 + (y - ty) ** 2 >= 150 ** 2 for tx, ty in trees)

    def tree_pair(x, y, kind, label, pad=60.0, check_keep=True):
        if not trunk_ok(x, y, pad, check_keep) or not trunk_ok(-x, -y, pad, check_keep):
            return False
        s = U(0.92, 1.08)
        for k, (px_, py_) in enumerate(((x, y), (-x, -y))):
            inst("SM_Conifer_" + kind, px_, py_, scale=s, sink=6.0)
            trees.append((px_, py_))
            BLOCKERS.append({"label": "%s%s_Collision" % (label, "m" if k else ""), "pos": [round(px_, 1), round(py_, 1), height_at(px_, py_) + 90.0], "size": [46, 46, 200], "yaw": 0})
            if rng.random() < 0.5:
                a2 = U(0, 2 * math.pi)
                fx, fy = px_ + math.cos(a2) * U(80, 170), py_ + math.sin(a2) * U(80, 170)
                if not on_road(fx, fy) and not in_lake(fx, fy, 30):
                    inst("SM_Tuft_Fern", fx, fy, yaw=U(-35, 35))
        return True

    for i, (x, y, kind) in enumerate(FIELD_FIRS):              # single firs in the field: one small trunk blocker each
        tree_pair(x, y, kind, "Fir_%03d" % i, check_keep=False)
    for (x, y) in CORE_TOPS:
        if height_at(x, y) > 50.0:
            tree(x, y, "ABC"[int(rng.integers(0, 3))], force=True)

    # ---- the fir-wood belts: a thicket no troop can pass (one row of hidden blocker boxes along its middle line), low
    # firs so the lanes behind stay in view. Player's side, and its twin.
    belt_n = 0
    for k, line in enumerate(WOOD_PARTS):
        body = line.buffer(WOOD_HALF).difference(unary_union([Point(g).buffer(BELT_GAP * 0.5) for g in BELT_GAPS] + [LAKE.buffer(BELT_RIVER_GAP)]))
        n_box = max(int(math.ceil(line.length / 300.0)), 1)
        for j in range(n_box + 1):
            d = line.length * j / n_box
            p, p2 = line.interpolate(d), line.interpolate(min(d + 20.0, line.length))
            p0 = line.interpolate(max(d - 20.0, 0.0))
            yaw = math.degrees(math.atan2(p2.y - p0.y, p2.x - p0.x))
            for sgn, tag in ((1.0, ""), (-1.0, "m")):
                BLOCKERS.append({"label": "Wood_%d_%02d%s_Collision" % (k, j, tag), "pos": [round(sgn * p.x, 1), round(sgn * p.y, 1), 100.0],
                                 "size": [line.length / n_box + 70.0, 2.0 * WOOD_HALF - 90.0, 220.0], "yaw": round(yaw, 1)})
        local = []
        minx, miny, maxx, maxy = body.bounds
        body_p = prep(body)
        for _ in range(int(body.area / 9000.0)):
            x, y = U(minx, maxx), U(miny, maxy)
            if not body_p.contains(Point(x, y)) or any((x - tx) ** 2 + (y - ty) ** 2 < 150 ** 2 for tx, ty in local):
                continue
            local.append((x, y))
            kind, s = "AABBBC"[int(rng.integers(0, 6))], U(0.92, 1.08)
            for px_, py_ in ((x, y), (-x, -y)):
                inst("SM_Conifer_" + kind, px_, py_, scale=s, sink=6.0)
                trees.append((px_, py_))
                if rng.random() < 0.6:
                    a2 = U(0, 2 * math.pi)
                    inst("SM_Tuft_Fern", px_ + math.cos(a2) * U(70, 150), py_ + math.sin(a2) * U(70, 150), yaw=U(-35, 35))
            belt_n += 2

    # ---- stands of firs inside the field (trunk blockers; pairs): thick on the wooded flank, a few behind each castle
    # and along the field's edges
    stand_n = 0
    for zone, count, pick in (("wood", 20, None), ("back", 6, None), (None, 26, "edge")):
        made = 0
        for _ in range(4000):
            if made >= count:
                break
            cx, cy = U(-B + 500, B - 500), U(-B + 500, B - 500)
            if side_n(cx, cy) > -500.0 or keep_prep.contains(Point(cx, cy)):
                continue
            if pick == "edge":
                if abs(abs(cx) - B) > 1600 and abs(abs(cy) - B) > 1600:
                    continue
            elif zone_of(cx, cy) != zone:
                continue
            made += 1
            spread = U(300, 520)
            for _ in range(int(rng.integers(5, 10))):
                a, d = U(0, 2 * math.pi), spread * math.sqrt(U(0.02, 1.0))
                x, y = cx + math.cos(a) * d, cy + math.sin(a) * d
                if side_n(x, y) > -200.0:
                    continue
                kind = "ABCDE"[int(rng.choice(5, p=[0.2, 0.32, 0.3, 0.14, 0.04]))]
                if tree_pair(x, y, kind, "Stand_%04d" % stand_n):
                    stand_n += 1

    for _ in range(110):                                       # loose stones in the field (ankle high: dressing only)
        cx, cy = U(-B + 200, B - 200), U(-B + 200, B - 200)
        if keep_prep.contains(Point(cx, cy)) or on_road(cx, cy, 30) or in_lake(cx, cy, 120):
            continue
        for _ in range(int(rng.integers(2, 5))):
            inst("SM_Rock_S%d" % rng.integers(0, 3), cx + float(rng.normal(0, 45)), cy + float(rng.normal(0, 45)), sink=9.0)

    # ---- stands beyond the field (dressing only, no collision)
    stands = []
    for _ in range(520):
        x, y = U(-B, B + 4000), U(-B - 3400, B + 3400)
        if play_in(x, y, 240):
            continue
        stands.append((x, y, int(rng.integers(4, 10)), U(240, 520)))
    for cx, cy, num, spread in stands:
        for _ in range(num):
            a, d = U(0, 2 * math.pi), spread * math.sqrt(U(0.02, 1.0))
            x, y = cx + math.cos(a) * d, cy + math.sin(a) * d
            if play_in(x, y, 60):
                continue
            if tree(x, y) and rng.random() < 0.5:
                a2 = U(0, 2 * math.pi)
                fx, fy = x + math.cos(a2) * U(80, 170), y + math.sin(a2) * U(80, 170)
                if not on_road(fx, fy) and not in_lake(fx, fy, 30) and not play_in(fx, fy):
                    inst("SM_Tuft_Fern", fx, fy, yaw=U(-35, 35))
    print("belt firs %d, stand firs %d" % (belt_n, stand_n * 2))
    for i in range(160):                                       # the far ranges: big firs, sparse
        x, y = U(B + 1500, B + 4200), U(-B - 3500, B + 3500)
        if 100 < height_at(x, y) < TREE_LINE and flat_around(x, y, 80) and not any(math.hypot(x - px_, y - py_) < size * 0.42 for _, px_, py_, size, _, _ in PEAKS):
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
            if x < WX0 + 200 or x > B + 3800 or abs(y) > B + 3300 or in_lake(x, y, 20) or on_road(x, y, -60):
                continue
            if play_in(x, y) and (keep_prep.contains(Point(x, y)) or rock_clear.contains(Point(x, y))):
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
    for i in range(110):
        for _ in range(30):
            x, y = U(-B - 1300, B + 3800), U(-B - 3200, B + 3200)
            if not play_in(x, y, 320) and not in_lake(x, y, 200) and not on_road(x, y, 120) and flat_around(x, y, 150):
                break
        else:
            continue
        big = "SM_Rock_%s%d" % ("M" if (x < -B or rng.random() < 0.45) else "L", rng.integers(0, 3))
        inst(big, x, y, sink=12.0)
        for _ in range(int(rng.integers(2, 5))):
            a, d = U(0, 2 * math.pi), U(110, 220)
            inst("SM_Rock_S%d" % rng.integers(0, 3), x + math.cos(a) * d, y + math.sin(a) * d, sink=4.0)

    # ---- grass: blade cards in clumps over the turf (units wade through them; no collision, no shadow). Denser in
    # the field, sparser in the dressing beyond it (seen only far off, through haze and blur).
    n = 0
    ramp_prep = prep(unary_union([r["poly"] for r in RAMPS]).buffer(20.0))
    for k_ in range(3500 if FAST else 35000):
        if k_ < (2600 if FAST else 26000):
            cx, cy = U(-B - 300, B + 300), U(-B - 300, B + 300)
        else:
            cx, cy = U(-B - 1300, B + 3600), U(-B - 2800, B + 2800)
            if play_in(cx, cy):
                continue
        if in_lake(cx, cy, 10) or height_at(cx, cy) > ROCK_LINE or ramp_prep.contains(Point(cx, cy)):
            continue
        dry = SPLAT_DRY(cx, cy)
        road = ROAD_DIST(cx, cy)
        if road < 170:
            continue
        kind = "SM_Tuft_Dry" if rng.random() < dry * 0.6 else ("SM_Tuft_Tall" if rng.random() < 0.55 else "SM_Tuft_Short")
        count = int(rng.integers(2, 5))
        for _ in range(count):
            x, y = cx + float(rng.normal(0, 34)), cy + float(rng.normal(0, 34))
            if ROAD_DIST(x, y) < 160 or in_lake(x, y) or ramp_prep.contains(Point(x, y)):
                continue
            inst(kind, x, y, yaw=U(-32, 32), scale=1.0)
            n += 1
    for _ in range(180):                                       # flower patches
        cx, cy = U(-B, B + 2000), U(-B - 1000, B + 1000)
        if in_lake(cx, cy, 40) or ROAD_DIST(cx, cy) < 260 or height_at(cx, cy) > ROCK_LINE:
            continue
        for _ in range(int(rng.integers(2, 5))):
            inst("SM_Tuft_Flower", cx + float(rng.normal(0, 50)), cy + float(rng.normal(0, 50)), yaw=U(-30, 30))

    # ---- ruins (blocking pieces: one convex box each)
    def ruin_piece(mesh, x, y, yaw, label, block=None):
        actor(mesh, x, y, yaw, "sandstone", label, "Props/Ruin")
        if block:
            z = height_at(x, y)
            BLOCKERS.append({"label": label + "_Collision", "pos": [x, y, z + block[2] * 0.5 - 6.0], "size": list(block), "yaw": yaw})

    def both(fn, x, y, *args):
        """Places a piece and its twin across the centre."""
        fn(x, y, "", *args)
        fn(-x, -y, "m", *args)

    # The shrine on the river island, the map's landmark: a paved dais (terrain, 24 cm) ringed by standing stones, with
    # pillars where the king's road enters and leaves it. The stones block; the road and the sides toward the veins stay open.
    road_ang = math.degrees(math.atan2(ROAD_MAIN_KEYS[7][1] - ROAD_MAIN_KEYS[5][1], ROAD_MAIN_KEYS[7][0] - ROAD_MAIN_KEYS[5][0]))
    for i, off in enumerate((45.0, 70.0, 110.0, 135.0)):
        a = math.radians(road_ang + off)

        def stone(x, y, tag, i=i, a=a):
            mesh = "SM_Menhir_%d" % (i % 3)
            yaw = math.degrees(a) + 90.0 + (180.0 if tag else 0.0)
            actor(mesh, x, y, yaw, "rock", "Shrine_Stone_%d%s" % (i, tag), "Props/Ruin")
            BLOCKERS.append({"label": "Shrine_Stone_%d%s_Collision" % (i, tag), "pos": [x, y, height_at(x, y) + 100.0], "size": [84, 64, 220], "yaw": yaw})
        both(stone, 780.0 * math.cos(a), 780.0 * math.sin(a))
    for i, (off, mesh, hgt) in enumerate(((21.0, "SM_Ruin_Pillar", 320), (-21.0, "SM_Ruin_PillarBroken", 190))):
        a = math.radians(road_ang + off)
        both(lambda x, y, tag, i=i, mesh=mesh, hgt=hgt: ruin_piece(mesh, x, y, road_ang + (180.0 if tag else 0.0), "Shrine_Pillar_%d%s" % (i, tag), (88, 88, hgt)),
             700.0 * math.cos(a), 700.0 * math.sin(a))
    c_, s_ = math.cos(math.radians(road_ang)), math.sin(math.radians(road_ang))
    for i, (along, across, yaw) in enumerate(((120.0, 300.0, 35.0), (-60.0, 380.0, -50.0), (260.0, 430.0, 8.0))):      # fallen blocks beside the road (dressing)
        both(lambda x, y, tag, i=i, yaw=yaw: ruin_piece("SM_Ruin_Block", x, y, road_ang + yaw + (180.0 if tag else 0.0), "Shrine_Block_%d%s" % (i, tag)),
             along * c_ - across * s_, along * s_ + across * c_)

    def banner(x, y, tag):
        actor("SM_BannerPole", x, y, 0, "wood", "Shrine_BannerPole" + tag, "Props/Ruin")
        actor("SM_BannerCloth", x, y, 0, "banner", "Shrine_Banner" + tag, "Props/Ruin")
    both(banner, 470.0 * math.cos(math.radians(road_ang + 90.0)), 470.0 * math.sin(math.radians(road_ang + 90.0)))

    # The bridges: a pillar pair at each end (blocking, on the banks beside the deck) and kerb stones along the slab.
    deck = BRIDGE_POLYS[0]
    mrr = deck.minimum_rotated_rectangle
    cs = list(mrr.exterior.coords)[:4]
    e0, e1 = np.array(cs[1]) - np.array(cs[0]), np.array(cs[2]) - np.array(cs[1])
    if abs(np.linalg.norm(e0) - 2 * BRIDGE_HALF) < abs(np.linalg.norm(e1) - 2 * BRIDGE_HALF):
        e0, e1 = e1, e0                                         # e0 runs along the bridge
    span = float(np.linalg.norm(e0))
    dvec, pvec = e0 / span, e1 / np.linalg.norm(e1)
    mid_ = np.array([deck.centroid.x, deck.centroid.y])
    deck_yaw = math.degrees(math.atan2(dvec[1], dvec[0]))
    n_p = 0
    for end in (-1.0, 1.0):
        for sd in (-1.0, 1.0):
            p = mid_ + dvec * end * (span * 0.5 + 60.0) + pvec * sd * (BRIDGE_HALF + 80.0)
            if in_lake(p[0], p[1], 60) or in_lake(-p[0], -p[1], 60):
                p = mid_ + dvec * end * (span * 0.5 + 170.0) + pvec * sd * (BRIDGE_HALF + 80.0)
            mesh, hgt = (("SM_Ruin_Pillar", 320) if (end * sd) > 0 else ("SM_Ruin_PillarBroken", 190))
            both(lambda x, y, tag, mesh=mesh, hgt=hgt, n_p=n_p: ruin_piece(mesh, x, y, deck_yaw + (180.0 if tag else 0.0), "Bridge_Pillar_%d%s" % (n_p, tag), (88, 88, hgt)), p[0], p[1])
            n_p += 1
    n_k = 0
    runs = max(int(span // 300.0), 1)                           # a low parapet along each side of the deck (dressing: the
    for sd in (-1.0, 1.0):                                      # water beside it already stops a troop), one run left out
        for j in range(runs):
            if (sd > 0 and j == 1) or (sd < 0 and j == runs - 1):
                n_k += 1
                continue                                        # fallen into the stream
            p = mid_ + dvec * (-0.5 * runs * 300.0 + 150.0 + j * 300.0) + pvec * sd * (BRIDGE_HALF - 22.0)
            both(lambda x, y, tag, n_k=n_k: actor("SM_Ruin_Parapet", x, y, deck_yaw - 90.0 + (180.0 if tag else 0.0), "sandstone", "Bridge_Parapet_%d%s" % (n_k, tag), "Props/Ruin", z=0.0), p[0], p[1])
            n_k += 1

    gx, gy = 6700.0, 10400.0                                   # gate on the road where it leaves the field for the hills (dressing)
    ruin_piece("SM_Ruin_Pillar", gx, gy - 300, 4, "Gate_Pillar_A")
    ruin_piece("SM_Ruin_Pillar", gx + 40, gy + 330, -5, "Gate_Pillar_B")
    ruin_piece("SM_Ruin_Wall", gx + 20, gy - 560, 2, "Gate_Wall_A")
    ruin_piece("SM_Ruin_Wall", gx + 70, gy + 600, 184, "Gate_Wall_B")
    actor("SM_BannerPole", gx - 30, gy + 250, 0, "wood", "Gate_BannerPole", "Props/Ruin")
    actor("SM_BannerCloth", gx - 30, gy + 250, 0, "banner", "Gate_Banner", "Props/Ruin")

    # The fords: a standing stone at each corner of the crossing, on the banks (dressing: they mark it from afar).
    ford = FORD_POLYS[0]
    fr = list(ford.minimum_rotated_rectangle.exterior.coords)[:4]
    fc = np.array([ford.centroid.x, ford.centroid.y])
    for i, corner in enumerate(fr):
        v = np.array(corner) - fc
        p = fc + v * (1.0 + 190.0 / max(np.linalg.norm(v), 1.0))
        if in_lake(p[0], p[1], 40) or in_lake(-p[0], -p[1], 40):
            continue
        both(lambda x, y, tag, i=i: actor("SM_Menhir_%d" % (i % 3), x, y, U(0, 360), "rock", "Ford_Stone_%d%s" % (i, tag), "Props/Rocks"), p[0], p[1])

    # Reeds and long grass along the banks (not at the fords or the bridge heads).
    quiet = prep(unary_union([f.buffer(260) for f in FORD_POLYS] + [b.buffer(260) for b in BRIDGE_POLYS]))
    reeds = 0
    for part in LAKE.geoms:
        for ring in [part.exterior] + list(part.interiors):
            d = U(0, 80)
            while d < ring.length:
                p = ring.interpolate(d)
                q = ring.interpolate(min(d + 10.0, ring.length))
                d += U(60, 150)
                if not play_in(p.x, p.y, 400) or quiet.contains(p) or rng.random() < 0.4:
                    continue
                ex, ey = q.x - p.x, q.y - p.y
                ln = math.hypot(ex, ey) or 1.0
                nx, ny = ey / ln, -ex / ln
                if in_lake(p.x + nx * 40, p.y + ny * 40):
                    nx, ny = -nx, -ny
                kind = "SM_Tuft_Dry" if rng.random() < 0.65 else "SM_Tuft_Tall"
                for _ in range(int(rng.integers(2, 6))):
                    off = U(12, 75)
                    x, y = p.x + nx * off + U(-35, 35), p.y + ny * off + U(-35, 35)
                    if in_lake(x, y, 4) or abs(height_at(x, y)) > 1.0:
                        continue
                    inst(kind, x, y, yaw=U(-32, 32), scale=1.0)
                    reeds += 1
    print("reeds %d" % reeds)

    place_structures(play_in, in_lake, both, ruin_piece)

    # ---- fences, stumps and logs round the kingdoms and along the road
    def scatter_near(cx, cy, rmin, rmax):
        for _ in range(40):
            a, d = U(0, 2 * math.pi), U(rmin, rmax)
            x, y = cx + math.cos(a) * d, cy + math.sin(a) * d
            if not on_road(x, y, 80) and not in_lake(x, y, 60) and flat_around(x, y, 80):
                return x, y
        return None

    fi = 0
    for k_, x, y, yaw, team, label in BUILDINGS:
        if k_ != "castle":
            continue
        for _ in range(5):
            p = scatter_near(x, y, 1700, 3000)
            if p:
                actor("SM_Fence_" + "AB"[fi % 2], p[0], p[1], U(0, 180), "wood", "Fence_%02d" % fi, "Props/Fences")
                fi += 1
        for j in range(3):
            p = scatter_near(x, y, 1600, 3200)
            if p:
                actor("SM_Stump", p[0], p[1], U(0, 360), "log", "Stump_%s_%d" % (label, j), "Props/Logs")
        p = scatter_near(x, y, 1800, 3200)
        if p:
            actor("SM_Log", p[0], p[1], U(0, 180), "log", "Log_%s" % label, "Props/Logs")
    print("tufts %d, cliff-foot props %d, trees %d" % (n, feet, len(trees)))


STRUCTURES = []       # (kind, x, y) of everything place_structures put down on the player's half, for the report


def place_structures(play_in, in_lake, both, ruin_piece):
    """Set dressing with a purpose: watch posts where a lane narrows, the old kingdom's ruins along the roads, a stone
    circle on each highland, a fallen bridge on the river, cairns as waymarks. Everything is placed for the player's half
    and twinned; pieces that block are single boxes like every other obstacle. Nothing goes on a road, an apron, a ramp
    or the top of the heights."""
    from shapely.prepared import prep
    heights = prep(unary_union([PLATEAU_POLY.buffer(RAMP_WIDTH + 200.0), rot180(PLATEAU_POLY).buffer(RAMP_WIDTH + 200.0)]))

    why = {}

    def clear(x, y, r):
        def no(reason):
            why[reason] = why.get(reason, 0) + 1
            return False
        if not play_in(x, y, -r - 200) or in_lake(x, y, r + 130) or heights.contains(Point(x, y)):
            return no("edge / water / heights")
        if on_road(x, y, r + 40):
            return no("road")
        if not flat_around(x, y, r) or not flat_around(x, y, r * 0.5) or not flat_around(x, y, r + 60):
            return no("ground not level")
        if min(math.hypot(x - P_ANCHOR[0], y - P_ANCHOR[1]), math.hypot(x - E_ANCHOR[0], y - E_ANCHOR[1])) < 3750.0:
            return no("apron")
        if any(math.hypot(x - vx, y - vy) < r + 900.0 for vx, vy in GOLD_VEINS):
            return no("vein")
        if not all(math.hypot(b["pos"][0] - x, b["pos"][1] - y) > r + 110.0 + max(b["size"][0], b["size"][1]) * 0.5 for b in BLOCKERS):
            return no("obstacle")
        return True

    def site(x, y, r, spread=450.0, tries=500):
        """A clear level spot near (x, y) whose twin across the map is clear as well (looks wider the longer it takes)."""
        for k in range(tries):
            sp = spread * (1.0 + 2.0 * k / tries)
            px_, py_ = (x, y) if k == 0 else (x + U(-sp, sp), y + U(-sp, sp))
            if side_n(px_, py_) < -(r + 200.0) and clear(px_, py_, r) and clear(-px_, -py_, r):
                return px_, py_
        return None

    def block(label, x, y, size, yaw):
        BLOCKERS.append({"label": label + "_Collision", "pos": [round(x, 1), round(y, 1), height_at(x, y) + size[2] * 0.5 - 6.0], "size": list(size), "yaw": round(yaw, 1)})

    def watch_post(x, y, tag, i=0, yaw=0.0):
        actor("SM_WatchPost", x, y, yaw + (180.0 if tag else 0.0), "wood", "WatchPost_%d%s" % (i, tag), "Props/Structures")
        block("WatchPost_%d%s" % (i, tag), x, y, (230, 230, 420), yaw)

    def tower(x, y, tag, i=0, yaw=0.0):
        actor("SM_Ruin_Tower", x, y, yaw + (180.0 if tag else 0.0), "sandstone", "RuinTower_%d%s" % (i, tag), "Props/Ruin")
        block("RuinTower_%d%s" % (i, tag), x, y, (410, 410, 420), yaw)

    def ruin(x, y, tag, i=0, yaw=0.0):
        """An arch with a run of wall, a broken pillar and fallen blocks round it."""
        t = yaw + (180.0 if tag else 0.0)
        c, sn_ = math.cos(math.radians(t)), math.sin(math.radians(t))
        at = lambda lx, ly: (x + lx * c - ly * sn_, y + lx * sn_ + ly * c)
        actor("SM_Ruin_Arch", x, y, t, "sandstone", "Ruin_%d_Arch%s" % (i, tag), "Props/Ruin")
        for j, ly in enumerate((-190.0, 190.0)):
            block("Ruin_%d_Arch%d%s" % (i, j, tag), *at(0.0, ly), (88, 88, 320), t)
        wx, wy = at(30.0, 470.0)
        ruin_piece("SM_Ruin_Wall", wx, wy, t + 8.0, "Ruin_%d_Wall%s" % (i, tag), (60, 372, 170))
        bx, by = at(-60.0, -430.0)
        ruin_piece("SM_Ruin_PillarBroken", bx, by, t + 30.0, "Ruin_%d_Pillar%s" % (i, tag), (88, 88, 190))
        for j, (lx, ly, yw) in enumerate(((150.0, -60.0, 35.0), (-170.0, 250.0, -40.0), (210.0, 330.0, 12.0))):
            ruin_piece("SM_Ruin_Block", *at(lx, ly), t + yw, "Ruin_%d_Block%d%s" % (i, j, tag))

    def circle(x, y, tag, i=0):
        """A ring of standing stones round a dolmen."""
        turn = 180.0 if tag else 0.0
        actor("SM_Dolmen", x, y, 20.0 + turn, "rock", "Circle_%d_Dolmen%s" % (i, tag), "Props/Rocks")
        block("Circle_%d_Dolmen%s" % (i, tag), x, y, (300, 280, 200), 20.0 + turn)
        for j in range(7):
            if j == 2:
                continue                                        # one stone has fallen: the way in
            a = math.radians(turn + 12.0 + j * 360.0 / 7.0)
            sx, sy = x + 380.0 * math.cos(a), y + 380.0 * math.sin(a)
            yw = math.degrees(a) + 90.0
            actor("SM_Menhir_%d" % (j % 3), sx, sy, yw, "rock", "Circle_%d_Stone%d%s" % (i, j, tag), "Props/Rocks")
            block("Circle_%d_Stone%d%s" % (i, j, tag), sx, sy, (84, 64, 220), yw)

    def cairn(x, y, tag, i=0):
        actor("SM_Cairn", x, y, (i * 67.0) % 360.0, "rock", "Cairn_%d%s" % (i, tag), "Props/Rocks")

    def put(kind, fn, want, r, spread=450.0, **kw):
        why.clear()
        p = site(want[0], want[1], r, spread)
        if p is None:
            print("  no room for %s near (%.0f, %.0f): %s" % (kind, want[0], want[1], why))
            return False
        both(lambda x, y, tag: fn(x, y, tag, **kw), p[0], p[1])
        STRUCTURES.append((kind, p[0], p[1]))
        return True

    # watch posts: the player's bank of ford A, the foot of each ramp, the wood belt's opening, the king's road at the apron
    up = np.array(RIVER_AXIS)
    ford = np.array(FORD_A) - np.array(RIVER_PERP) * (FORD_RIVER_HALF + 520.0) + up * (FORD_HALF + 330.0)
    wants = [tuple(ford), BELT_GAPS[0] if BELT_GAPS else (-1000.0, -4700.0), (-3900.0, -3900.0)]
    for fx, fy in RAMP_FEET[1:]:                               # the field ramp's foot (the home ramp's is on the apron: building ground)
        d = np.array([fx - PLATEAU_P[0], fy - PLATEAU_P[1]])
        d /= np.linalg.norm(d)
        wants.append((fx + d[0] * (RAMP_WIDTH * 0.5 + 420.0), fy + d[1] * (RAMP_WIDTH * 0.5 + 420.0)))
    for i, want in enumerate(wants):
        put("watch post", watch_post, want, 150.0, i=i, yaw=float(rng.integers(0, 4)) * 90.0)
    # ruins: beside the king's road in the plain, on the wooded lane, where the stone lane meets ford B's bank; a broken tower
    # on the plain and one looking down from the highland
    for i, (x, y, yaw) in enumerate(RUIN_SITES):
        put("ruin", ruin, (x, y), 500.0, 300.0, i=i, yaw=yaw)
    for i, want in enumerate(TOWER_SITES):
        put("ruined tower", tower, want, 300.0, 250.0, i=i, yaw=float(rng.integers(0, 4)) * 90.0 + U(-12, 12))
    # stone circles: one on the highland, one in the quiet ground behind the heights
    for i, want in enumerate(CIRCLE_SITES):
        put("stone circle", circle, want, 470.0, 300.0, i=i)
    # cairns: waymarks at the ramps' heads and feet, along the highland spur and at the fords (dressing, no collision)
    ci = 0
    for r in RAMPS[:2]:
        for idx in (0, -1):
            for edge in (r["left"], r["right"]):
                e = edge[idx]
                o = (edge[idx] - (r["left"][idx] + r["right"][idx]) * 0.5)
                o = o / max(np.linalg.norm(o), 1e-9) * 120.0
                x, y = e[0] + o[0], e[1] + o[1]
                if abs(height_at(x, y) - height_at(x + 40.0, y + 40.0)) < 1.0 and abs(height_at(x, y) - height_at(x - 40.0, y - 40.0)) < 1.0:
                    both(lambda x, y, tag, ci=ci: cairn(x, y, tag, i=ci), x, y)
                    ci += 1
    for want in ((5600.0, -7000.0), (3300.0, -6000.0), tuple(np.array(FORD_A) - np.array(RIVER_PERP) * (FORD_RIVER_HALF + 380.0) - up * (FORD_HALF + 200.0)), (-9300.0, -8600.0), (-12600.0, 800.0)):
        for _ in range(30):
            x, y = want[0] + U(-260, 260), want[1] + U(-260, 260)
            if side_n(x, y) < -250.0 and not on_road(x, y, 70) and not in_lake(x, y, 120) and flat_around(x, y, 90) and not heights.contains(Point(x, y)):
                both(lambda x, y, tag, ci=ci: cairn(x, y, tag, i=ci), x, y)
                STRUCTURES.append(("cairn", x, y))
                ci += 1
                break
    # the fallen bridge: upstream of the island, where the old road crossed before the fords were found. An abutment on
    # each bank, a pier in the stream, the spans gone: nobody crosses here.
    line = LineString(RIVER_UP)
    d0 = line.project(Point(sn(5100.0, 200.0)))
    pc, pn = line.interpolate(d0), line.interpolate(d0 + 30.0)
    tx_, ty_ = pn.x - pc.x, pn.y - pc.y
    ln = math.hypot(tx_, ty_)
    nx_, ny_ = -ty_ / ln, tx_ / ln
    ends = []
    for sgn in (-1.0, 1.0):
        off = RIVER_HALF * 0.8
        while in_lake(pc.x + sgn * nx_ * off, pc.y + sgn * ny_ * off, 150.0) and off < 1400.0:
            off += 20.0
        ends.append((pc.x + sgn * nx_ * off, pc.y + sgn * ny_ * off, math.degrees(math.atan2(-sgn * ny_, -sgn * nx_))))
    if all(not on_road(x, y, 200) and flat_around(x, y, 120) for x, y, _ in ends):
        for j, (x, y, yaw) in enumerate(ends):
            def abutment(x, y, tag, j=j, yaw=yaw):
                actor("SM_Ruin_BridgeEnd", x, y, yaw + (180.0 if tag else 0.0), "sandstone", "OldBridge_End%d%s" % (j, tag), "Props/Ruin", z=0.0)
                c, sn_ = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
                bx, by = x - 75.0 * c * (-1.0 if tag else 1.0), y - 75.0 * sn_ * (-1.0 if tag else 1.0)
                BLOCKERS.append({"label": "OldBridge_End%d%s_Collision" % (j, tag), "pos": [round(bx, 1), round(by, 1), 60.0], "size": [240, 310, 130], "yaw": round(yaw, 1)})
            both(abutment, x, y)
        both(lambda x, y, tag: actor("SM_Ruin_Pier", x, y, math.degrees(math.atan2(ny_, nx_)) + (180.0 if tag else 0.0), "sandstone", "OldBridge_Pier" + tag, "Props/Ruin", z=0.0), pc.x, pc.y)
        STRUCTURES.append(("fallen bridge", pc.x, pc.y))
    print("structures: " + ", ".join("%d %s" % (sum(1 for k, _, _ in STRUCTURES if k == kind), kind) for kind in sorted(set(k for k, _, _ in STRUCTURES))) + " (each twinned)")


# ============================================================================================ kingdoms
# The kingdoms are planned with the field now (BUILDINGS above): nothing to remove afterwards.
KINGDOM_REMOVES = set()
KINGDOM_REMOVE_ROCKS = set()


def _kingdom_paths():
    """Footpaths (bare earth): each castle court to its farm yard and its mine adit."""
    out = []
    for team in (0, 1):
        c = [b for b in BUILDINGS if b[4] == team and b[0] == "castle"][0]
        court = (c[1] - 780.0, c[2])
        for b in BUILDINGS:
            if b[4] == team and b[0] != "castle":
                front = (b[1] - 520.0, b[2])
                mid = (min(court[0], front[0]) - 250.0, (court[1] + front[1]) * 0.5)
                out.append([court, mid, front])
    return out


KINGDOM_PATHS = _kingdom_paths()

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
    live = set(t["group"] for t in TIERS) | set(r["name"] for r in RAMPS)
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
            if name.startswith("GoldVein"):
                out.append(a)                       # a vein stays (a mine stands on it; if the mine falls it can be rebuilt)
                continue
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
    d_flank = raster_dist(FLANK_ROADS, lines=True)[0] + wob
    road_d = np.minimum(d_main, d_flank + 25.0)

    def band(d, core, edge):
        return np.clip((edge - d) / (edge - core), 0.0, 1.0)

    paved = np.clip((smooth_noise(shape, 30, 8) - 0.34) * 5.0, 0.0, 1.0)             # the old paving survives in stretches
    paved = np.maximum(paved, np.clip((3100.0 - np.hypot(X, Y)) / 500.0, 0.0, 1.0))  # and is whole across the island and its bridges
    R = band(d_main, 55.0, 105.0) * 0.5 * paved + band(d_main, 100.0, 165.0) * 0.5   # stones inside ~55, earth out to ~165
    R = np.maximum(R, band(d_flank, 40.0, 120.0) * 0.52)                              # flank roads: earth only
    worn = smooth_noise(shape, 40, 3)
    for (cx, cy, rad) in [(PLAYER_START[0], PLAYER_START[1], 620.0), (ENEMY_START[0], ENEMY_START[1], 620.0), (6700.0, 10400.0, 520.0)] + [(x, y, 420.0) for x, y in GOLD_VEINS]:
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

    # ---- regions (see zone_of): the same for both kingdoms, so judged on the player's side and mirrored
    sd = side_n(X, Y)
    Xm, Ym = np.where(sd > 0, -X, X), np.where(sd > 0, -Y, Y)
    ang = np.degrees(np.arctan2(Ym - P_ANCHOR[1], Xm - P_ANCHOR[0])) + (smooth_noise(shape, 36, 11) - 0.5) * 10.0
    far = np.clip((np.hypot(Xm - P_ANCHOR[0], Ym - P_ANCHOR[1]) - 2600.0) / 1200.0, 0.0, 1.0)
    field = np.clip((BOUND + 500.0 - np.maximum(np.abs(X), np.abs(Y))) / 600.0, 0.0, 1.0)
    hl = np.clip((1.06 - np.hypot((Xm - HIGHLAND_P[0]) / HIGHLAND_R[0], (Ym - HIGHLAND_P[1]) / HIGHLAND_R[1]) + (worn - 0.5) * 0.12) / 0.14, 0.0, 1.0) * field
    plain = np.clip((ang - WOOD_ANGLE + 2.0) / 5.0, 0, 1) * np.clip((RIDGE_ANGLE + 2.0 - ang) / 5.0, 0, 1) * far * field * (1.0 - hl)
    wood = np.clip((ang + 27.0) / 5.0, 0, 1) * np.clip((WOOD_ANGLE + 2.0 - ang) / 5.0, 0, 1) * far * field * (1.0 - hl)
    stone = np.clip((ang - RIDGE_ANGLE + 2.0) / 5.0, 0, 1) * np.clip((117.0 - ang) / 5.0, 0, 1) * far * field * (1.0 - hl)
    d_bank, water = raster_dist(list(LAKE.geoms))
    belts = [l.buffer(WOOD_HALF) for l in WOOD_PARTS]
    d_belt = raster_dist(belts + [rot180(b) for b in belts])[0]
    bank = band(d_bank + wob * 0.25, 60.0, 520.0)                  # a lush strip along the water
    belt = band(d_belt + wob * 0.4, 120.0, 420.0)                  # mossy floor under the fir belts
    moss = moss + 0.14 * wood + 0.5 * belt + 0.42 * bank - 0.35 * hl
    dry = dry + 0.22 * plain + 0.1 * stone + 0.42 * hl - 0.6 * belt - 0.5 * bank     # straw-gold plain, parched upland
    R = np.maximum(R, hl * np.clip((worn - 0.5) * 1.5, 0.0, 0.45))                    # bare, stony ground on the highlands
    R = np.maximum(R, stone * np.clip((worn - 0.68) * 2.0, 0.0, 0.45))
    R = np.maximum(R, band(d_bank + wob2 * 0.6, 25.0, 90.0) * 0.46)                   # mud at the water's edge
    d_ford = raster_dist(FORD_POLYS)[0]
    R = np.maximum(R, band(d_ford + wob2, 120.0, 520.0) * (0.56 + 0.44 * paved2))     # gravel bars on a ford's banks and bed
    R = np.maximum(R, band(raster_dist(BRIDGE_POLYS)[0], 0.0, 60.0))                  # the bridge slabs: set stone
    R = np.maximum(R, band(np.hypot(X, Y), 600.0, 640.0) * (0.62 + 0.38 * paved2))    # the shrine's dais
    return X, Y, R, moss, dry, road_d


def splat_heights(X, Y, R, moss, dry):
    """The parts of the splat that need the layout: the ramps are trodden earth, the tops of the heights are dry, worn
    upland like the highlands. Returns (R, moss, dry)."""
    shape = X.shape
    wob = (smooth_noise(shape, 16, 21) - 0.5) * 70.0
    worn = smooth_noise(shape, 40, 3)
    mids = [[tuple(p) for p in (r["left"] + r["right"]) * 0.5] for r in RAMPS]
    d_ramp = raster_dist(mids, lines=True)[0] + wob
    R = np.maximum(R, np.clip((RAMP_WIDTH * 0.5 - 60.0 - d_ramp) / 150.0, 0.0, 1.0) * 0.53)
    tops = [PLATEAU_POLY, rot180(PLATEAU_POLY)]
    d_top, on_top = raster_dist(tops)
    inset = ndimage.distance_transform_edt(on_top).astype(np.float32) * (SPLAT_SIZE / SPLAT_RES)
    top = np.clip((inset + wob) / 160.0, 0.0, 1.0)
    dry = dry + 0.3 * top
    moss = moss - 0.3 * top
    R = np.maximum(R, top * np.clip((worn - 0.56) * 1.6, 0.0, 0.45))
    for r in RAMPS:                                             # a worn landing where each ramp arrives
        hx, hy = (r["left"][-1] + r["right"][-1]) * 0.5
        dd = np.hypot(X - hx, Y - hy)
        R = np.maximum(R, np.clip((700.0 - dd) / 700.0, 0, 1) * (0.3 + worn * 0.4))
        fx, fy = (r["left"][0] + r["right"][0]) * 0.5
        dd = np.hypot(X - fx, Y - fy)
        R = np.maximum(R, np.clip((800.0 - dd) / 800.0, 0, 1) * (0.3 + worn * 0.4))
    return R, moss, dry


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
def write_preview(splat, path, minimap=0):
    """The annotated planning preview, or (minimap = N) the HUD's N x N minimap base: exactly the +/-BOUND play
    square, +X up and +Y right like the game camera, terrain, water, woods and rocks only (the HUD draws buildings,
    troops and veins live on top). Imported as /Game/SR/Textures/T_MinimapBase."""
    x0, x1, y0, y1 = -BOUND - 1600, BOUND + 4000, -BOUND - 3000, BOUND + 3000
    scale = 0.04
    if minimap:
        x0, x1, y0, y1 = -BOUND, BOUND, -BOUND, BOUND
        scale = minimap / (2.0 * BOUND)
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
    rock = np.clip((z - ROCK_LINE + 150.0) / 300.0, 0.0, 1.0)[..., None]             # bare rock, then snow, on the mountains
    col = col * (1.0 - rock) + np.array([128, 124, 108], np.float32) * (0.8 + np.clip(z, 0, 3000)[..., None] / 3000.0 * 0.5) * rock
    col = np.where((z > SNOW_LINE)[..., None], np.array([226, 232, 238], np.float32), col)
    zs = hm(Xg - (60 if minimap else 14), Yg + (60 if minimap else 14))   # cheap relief
    col = np.where((zs > z + 5)[..., None], col * 0.55, np.where((zs < z - 5)[..., None], col * 1.25, col))
    col = np.where((z < -1)[..., None], np.array([118, 150, 138], np.float32), col)     # a ford's gravel showing through
    col = np.where((z < -30)[..., None], np.array([40, 90, 100], np.float32), col)
    img = Image.fromarray(np.clip(col, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)

    def P(x, y):
        return ((y - y0) * scale, (x1 - x) * scale)

    if not minimap:
        d.rectangle([P(BOUND, -BOUND), P(-BOUND, BOUND)], outline=(255, 255, 255))
    k = scale / 0.04
    for mesh, lst in INSTANCES.items():
        if mesh.startswith("SM_Conifer"):
            for x, y, z, yaw, s in lst:
                cx, cy = P(x, y)
                r = max(7 * k, 1.0)
                d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(25, 60, 30), outline=(10, 30, 15) if not minimap else None)
        elif mesh.startswith("SM_Rock"):
            for x, y, z, yaw, s in lst:
                cx, cy = P(x, y)
                rr = (2 if "_S" in mesh else (5 if "_M" in mesh else 9)) * k
                if rr >= 0.8:
                    d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(150, 145, 130))
    if minimap:
        img.save(path)
        return
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


# ============================================================================================ checks and the plan view
def walk_grid():
    """The field as USRGridSubsystem will sample it: 1 m cells over +/-BOUND, ground height from the height map; a cell
    is blocked where the ground is below -30 cm (water) or under a hidden blocker box (grown by half a cell). Also
    returns the cells under the level's buildings. Arrays are indexed [ix, iy]."""
    n = int(2 * BOUND / 100.0)
    c = -BOUND + (np.arange(n) + 0.5) * 100.0
    Xc, Yc = np.meshgrid(c, c, indexing="ij")
    H = HM[((Xc - WX0) / HM_RES).astype(int), ((Yc - WY0) / HM_RES).astype(int)]
    blocked = H < -30.0
    for b in BLOCKERS:
        ex, ey = b["size"][0] * 0.5 + 50.0, b["size"][1] * 0.5 + 50.0
        rad = math.hypot(ex, ey)
        cx, cy = b["pos"][0], b["pos"][1]
        i0, i1 = max(int((cx - rad + BOUND) / 100.0), 0), min(int((cx + rad + BOUND) / 100.0), n - 1)
        j0, j1 = max(int((cy - rad + BOUND) / 100.0), 0), min(int((cy + rad + BOUND) / 100.0), n - 1)
        if i1 < i0 or j1 < j0:
            continue
        ca, sa = math.cos(math.radians(b["yaw"])), math.sin(math.radians(b["yaw"]))
        dx, dy = Xc[i0:i1 + 1, j0:j1 + 1] - cx, Yc[i0:i1 + 1, j0:j1 + 1] - cy
        blocked[i0:i1 + 1, j0:j1 + 1] |= (np.abs(dx * ca + dy * sa) <= ex) & (np.abs(-dx * sa + dy * ca) <= ey)
    built = np.zeros_like(blocked)
    for kind, x, y, yaw, team, label in BUILDINGS:
        x0, y0, x1, y1 = building_meta(kind)["footprint"]
        built |= (Xc >= x + x0) & (Xc <= x + x1) & (Yc >= y + y0) & (Yc <= y + y1)
    return Xc, Yc, H, blocked, built


def flood(H, blocked, start, step=45.0):
    """Cells a troop can walk to from `start` (4-neighbour moves, climbing at most `step` cm): distance in cells, -1 = never."""
    n = H.shape[0]
    dist = np.full(H.shape, -1, np.int32)
    i, j = int((start[0] + BOUND) / 100.0), int((start[1] + BOUND) / 100.0)
    if blocked[i, j]:
        return dist
    dist[i, j] = 0
    front = [(i, j)]
    while front:
        nxt = []
        for i, j in front:
            for a, b in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
                if 0 <= a < n and 0 <= b < n and dist[a, b] < 0 and not blocked[a, b] and abs(H[a, b] - H[i, j]) <= step:
                    dist[a, b] = dist[i, j] + 1
                    nxt.append((a, b))
        front = nxt
    return dist


def validate():
    """Checks the layout the way the game will use it and prints a report. Returns (lines, grid) for the plan view."""
    from shapely.prepared import prep
    Xc, Yc, H, blocked, built = walk_grid()
    solid = blocked | built
    n = H.shape[0]
    out = []

    def cells_in(poly):
        m = np.zeros(H.shape, bool)
        minx, miny, maxx, maxy = poly.bounds
        pp = prep(poly)
        for i in range(max(int((minx + BOUND) / 100.0), 0), min(int((maxx + BOUND) / 100.0) + 1, n)):
            for j in range(max(int((miny + BOUND) / 100.0), 0), min(int((maxy + BOUND) / 100.0) + 1, n)):
                m[i, j] = pp.contains(Point(Xc[i, j], Yc[i, j]))
        return m

    crossings = {"ford A (top-left)": cells_in(FORD_POLYS[0]), "ford B (bottom-right)": cells_in(FORD_POLYS[1]),
                 "island bridges": cells_in(BRIDGE_POLYS[0]) | cells_in(BRIDGE_POLYS[1])}
    ej = (int((ENEMY_START[0] + BOUND) / 100.0), int((ENEMY_START[1] + BOUND) / 100.0))
    d_all = flood(H, solid, PLAYER_START)
    out.append("player start -> enemy start: %s" % ("%d m on foot" % d_all[ej] if d_all[ej] >= 0 else "NO ROUTE"))
    for name, mask in crossings.items():
        others = np.zeros(H.shape, bool)
        for k, m in crossings.items():
            if k != name:
                others |= m
        d = flood(H, solid | others, PLAYER_START)
        wet = int((mask & ~solid).sum())
        out.append("  only %-22s %s (%d walkable cells on it)" % (name + ":", "%d m" % d[ej] if d[ej] >= 0 else "NO ROUTE", wet))
    every = np.zeros(H.shape, bool)
    for m in crossings.values():
        every |= m
    out.append("  all crossings closed:      %s" % ("river holds" if flood(H, solid | every, PLAYER_START)[ej] < 0 else "LEAK: the river can be crossed elsewhere"))
    inside = (np.abs(Xc) < BOUND - 500) & (np.abs(Yc) < BOUND - 500)
    cut_off = int(((d_all < 0) & ~solid & inside).sum())
    out.append("walkable cells cut off from the player's start (inside the edge strip): %d" % cut_off)
    # fairness: the walkable mask and the heights against their own half turn
    walk = ~blocked
    diff = walk != walk[::-1, ::-1]
    reach = d_all >= 0                                          # heights are compared where troops can stand (mountains differ on purpose)
    hdiff = (np.abs(H - H[::-1, ::-1]) > 20.0) & reach & reach[::-1, ::-1]
    out.append("symmetry: %d of %d cells differ in walkability under a half turn (%d away from the 5 m edge strip), %d differ in height by more than 20 cm (%d inside)" % (
        int(diff.sum()), n * n, int((diff & inside).sum()), int(hdiff.sum()), int((hdiff & inside).sum())))

    def footprint_ok(kind, x, y, margin=True):
        x0, y0, x1, y1 = building_meta(kind)["footprint"]
        m = (Xc >= x + x0) & (Xc <= x + x1) & (Yc >= y + y0) & (Yc <= y + y1)
        if not m.any() or blocked[m].any() or (H[m].max() - H[m].min()) > 30.0:
            return False
        if margin:
            g = (Xc >= x + x0 - 100) & (Xc <= x + x1 + 100) & (Yc >= y + y0 - 100) & (Yc <= y + y1 + 100)
            if built[g].any():
                return False
        return bool((np.abs(Xc[m]) < BOUND).all() and x + x0 > -BOUND and x + x1 < BOUND and y + y0 > -BOUND and y + y1 < BOUND)

    for i, (x, y) in enumerate(GOLD_VEINS):
        ok = footprint_ok("mine", x, y, margin=i >= 2)
        reach = d_all[int((x + BOUND) / 100.0) - 6, int((y + BOUND) / 100.0)] >= 0
        out.append("vein %d at (%6.0f, %6.0f) z %3.0f, %-8s: mine %s, %s" % (i, x, y, height_at(x, y), zone_of(x, y), "fits" if ok else "DOES NOT FIT",
                                                                              "reachable" if reach else "UNREACHABLE"))
    for team, anchor in ((0, P_ANCHOR), (1, E_ANCHOR)):
        counts = {}
        for kind in ("farm", "castle"):                        # castle footprint stands in for the largest thing built (barracks)
            c = 0
            for x in np.arange(anchor[0] - 3800, anchor[0] + 3801, 200.0):
                for y in np.arange(anchor[1] - 3800, anchor[1] + 3801, 200.0):
                    if math.hypot(x - anchor[0], y - anchor[1]) <= 3800 and footprint_ok(kind, x, y):
                        c += 1
            counts[kind] = c
        out.append("%s castle territory (38 m): %d farm-sized and %d castle-sized building spots on a 2 m raster" % ("player" if team == 0 else "enemy", counts["farm"], counts["castle"]))
    # the heights: each ramp alone must reach the top, and the top must take buildings
    for team, sg, start in ((0, 1.0, PLAYER_START), (1, -1.0, ENEMY_START)):
        top = PLATEAU_POLY if team == 0 else rot180(PLATEAU_POLY)
        ramps = [cells_in(r["poly"]) for r in RAMPS if r["name"].endswith("m") == (team == 1)]
        tc = (int((sg * PLATEAU_P[0] + BOUND) / 100.0), int((sg * PLATEAU_P[1] + BOUND) / 100.0))
        legs = []
        for k, name in enumerate(("home ramp", "field ramp")):
            d = flood(H, solid | ramps[1 - k], start)
            legs.append("%s %s" % (name, "%d m" % d[tc] if d[tc] >= 0 else "NO WAY UP"))
        d = flood(H, solid | ramps[0] | ramps[1], start)
        legs.append("ramps closed: %s" % ("cliff holds" if d[tc] < 0 else "LEAK"))
        minx, miny, maxx, maxy = top.bounds
        tp = prep(top.buffer(-60.0))
        spots = {}
        for kind in ("farm", "castle"):
            c = 0
            x0, y0, x1, y1 = building_meta(kind)["footprint"]
            for x in np.arange(minx, maxx, 200.0):
                for y in np.arange(miny, maxy, 200.0):
                    if tp.contains(box(x + x0, y + y0, x + x1, y + y1)) and footprint_ok(kind, x, y):
                        c += 1
            spots[kind] = c
        out.append("%s heights (top %.0f cm, %.0f m2): from the start by %s; %d farm-sized and %d castle-sized building spots on top" % (
            "player" if team == 0 else "enemy", H[tc], top.area / 10000.0, ", ".join(legs), spots["farm"], spots["castle"]))
    slope = max(float(np.max(np.abs(np.diff(r["z"])) / np.maximum(np.diff(r["s"]), 1e-6))) for r in RAMPS)
    out.append("ramps: %d, %.0f cm wide, steepest %.2f along the middle line (a grid cell may rise 45 cm per 100)" % (len(RAMPS), RAMP_WIDTH, slope))
    tall = H[(np.abs(Xc) < BOUND) & (np.abs(Yc) < BOUND)]
    out.append("relief inside the field: highest ground %.0f cm; %.1f%% of it above 1.5 m, %.1f%% above 5 m" % (float(tall.max()), 100.0 * float((tall > 150).mean()), 100.0 * float((tall > 500).mean())))
    for arg in sys.argv:                                       # --probe=x,y : the grid round a spot (height in dm; # blocked, . unreachable)
        if arg.startswith("--probe="):
            px_, py_ = (float(v) for v in arg[8:].split(","))
            ci, cj = int((px_ + BOUND) / 100.0), int((py_ + BOUND) / 100.0)
            print("grid round (%.0f, %.0f), +X up, +Y right:" % (px_, py_))
            for i in range(ci + 9, ci - 10, -1):
                print(" ".join(("  #" if solid[i, j] else ("%3d" % round(H[i, j] / 10.0) if d_all[i, j] >= 0 else "%2d." % round(H[i, j] / 10.0))) for j in range(cj - 12, cj + 13)))
    for line in out:
        print(line)
    return out, (Xc, Yc, H, blocked, built, d_all)


ZONE_TINT = {"home": (132, 142, 84), "back": (118, 132, 80), "wood": (92, 122, 76), "plain": (158, 156, 92), "stone": (146, 140, 112), "highland": (172, 152, 112)}


def write_layout_preview(path, grid, report):
    """Saved/MapPreview/layout.png: the plan of the field as the game will read it (+X up, +Y right, like the camera):
    regions, river, fords, bridges, belts and their gaps, blocked ground, veins, kingdoms, roads."""
    from PIL import ImageFont
    Xc, Yc, H, blocked, built, d_all = grid
    S = 0.05
    half = BOUND + 1000.0
    S = 1300.0 / (2 * half)                                    # the plan stays 1300 px across whatever the map's size
    w = int(2 * half * S)
    xs = half - (np.arange(w) + 0.5) / S
    ys = -half + (np.arange(w) + 0.5) / S
    Yg, Xg = np.meshgrid(ys, xs)
    z = HM[np.clip(((Xg - WX0) / HM_RES).astype(int), 0, HM.shape[0] - 1), np.clip(((Yg - WY0) / HM_RES).astype(int), 0, HM.shape[1] - 1)]
    col = np.zeros((w, w, 3), np.float32)
    zc = {}
    for i in range(0, w, 4):                                   # region tint, on a coarse raster
        for j in range(0, w, 4):
            col[i:i + 4, j:j + 4] = ZONE_TINT[zone_of(float(Xg[i, j]), float(Yg[i, j]))]
    col *= (1.0 + np.clip(z, 0, 300)[..., None] / 300.0 * 0.45 + np.clip(z - 300, 0, 2400)[..., None] / 2400.0 * 0.5)
    zs = HM[np.clip(((Xg - 30 - WX0) / HM_RES).astype(int), 0, HM.shape[0] - 1), np.clip(((Yg + 30 - WY0) / HM_RES).astype(int), 0, HM.shape[1] - 1)]
    col = np.where((zs > z + 45)[..., None], col * 0.45, np.where((zs < z - 45)[..., None], col * 1.2, np.where((np.abs(zs - z) > 5)[..., None], col * 0.82, col)))
    col = np.where((z < -1)[..., None], np.array([170, 205, 200], np.float32), col)       # ford: pale
    col = np.where((z < -30)[..., None], np.array([44, 96, 132], np.float32), col)        # deep water
    gi = np.clip(((Xg + BOUND) / 100.0).astype(int), 0, H.shape[0] - 1)
    gj = np.clip(((Yg + BOUND) / 100.0).astype(int), 0, H.shape[0] - 1)
    ingrid = (np.abs(Xg) < BOUND) & (np.abs(Yg) < BOUND)
    blk = blocked[gi, gj] & ingrid & (z >= -30)
    col = np.where(blk[..., None], col * 0.35 + np.array([150, 40, 30], np.float32) * 0.65, col)
    lost = (d_all[gi, gj] < 0) & ~blocked[gi, gj] & ~built[gi, gj] & ingrid
    col = np.where((lost & (z > 50))[..., None], np.array([112, 100, 86], np.float32) * (0.8 + np.clip(z, 0, 300)[..., None] / 600.0 + np.clip(z - 300, 0, 2400)[..., None] / 2400.0 * 0.9), col)   # bluffs, knolls, ridge, mountains
    col = np.where((lost & (z <= 50))[..., None], col * 0.4 + np.array([230, 40, 230], np.float32) * 0.6, col)                               # a pocket nobody can reach
    col = np.where(ingrid[..., None], col, col * 0.55)
    img = Image.fromarray(np.clip(col, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    font, small = ImageFont.load_default(size=17), ImageFont.load_default(size=13)

    def P(x, y):
        return ((y + half) * S, (half - x) * S)

    def label(x, y, text, fill=(255, 255, 255), f=None, anchor="mm"):
        px_, py_ = P(x, y)
        f = f or font
        for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1), (1, 1), (-1, -1)):
            d.text((px_ + ox, py_ + oy), text, fill=(0, 0, 0), font=f, anchor=anchor)
        d.text((px_, py_), text, fill=fill, font=f, anchor=anchor)

    for mesh, lst in INSTANCES.items():
        if mesh.startswith("SM_Conifer"):
            for x, y, zz, yaw, s in lst:
                cx, cy = P(x, y)
                d.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=(22, 62, 30))
    d.line([P(x, y) for x, y in ROAD_MAIN], fill=(232, 208, 150), width=4)
    for r in FLANK_ROADS:
        pts = [P(x, y) for x, y in r]
        for k in range(0, len(pts) - 1, 2):
            d.line(pts[k:k + 2], fill=(214, 180, 120), width=3)
    d.rectangle([P(BOUND, -BOUND), P(-BOUND, BOUND)], outline=(255, 255, 255))
    for g in BELT_GAPS + [mir(g) for g in BELT_GAPS]:
        cx, cy = P(*g)
        d.ellipse([cx - BELT_GAP * 0.5 * S, cy - BELT_GAP * 0.5 * S, cx + BELT_GAP * 0.5 * S, cy + BELT_GAP * 0.5 * S], outline=(255, 255, 255))
        label(g[0] - 520, g[1], "gap 13 m", f=small)
    for kind, bx, by, yaw, team, lab in BUILDINGS:
        c = (70, 130, 255) if team == 0 else (255, 70, 50)
        d.polygon([P(x, y) for x, y in footprint_poly(kind, bx, by, yaw).exterior.coords], fill=c, outline=(255, 255, 255))
        if kind == "castle":
            for rad, wd in ((3400.0, 1), (3800.0, 1)):
                cx, cy = P(bx, by)
                d.ellipse([cx - rad * S, cy - rad * S, cx + rad * S, cy + rad * S], outline=c, width=wd)
    for (x, y), c in ((PLAYER_START, (70, 130, 255)), (ENEMY_START, (255, 70, 50))):
        cx, cy = P(x, y)
        d.ellipse([cx - 9, cy - 9, cx + 9, cy + 9], outline=c, width=3)
    for i, (x, y) in enumerate(GOLD_VEINS):
        cx, cy = P(x, y)
        d.polygon([(cx, cy - 11), (cx + 11, cy), (cx, cy + 11), (cx - 11, cy)], fill=(255, 205, 40), outline=(60, 40, 0))
        label(x - 420, y, "vein %d" % i, fill=(255, 225, 120), f=small)
    label(FORD_A[0] + 900, FORD_A[1] - 300, "FORD A  14 m")
    label(FORD_B[0] - 900, FORD_B[1] + 300, "FORD B  14 m")
    for b in BRIDGE_POLYS:
        label(b.centroid.x * 1.45, b.centroid.y * 1.45, "bridge 7 m", f=small)
    label(0, 0, "SHRINE ISLE")
    label(-1400, -2500, "CENTRE LANE: king's road, open plain", f=small)
    label(1400, 2500, "CENTRE LANE", f=small)
    label(-700, -6500, "TOP-LEFT LANE (wooded flank)", f=small)
    label(7900, 800, "TOP-LEFT LANE (rocky flank)", f=small)
    label(-7900, -800, "BOTTOM-RIGHT LANE (rocky flank)", f=small)
    label(700, 6500, "BOTTOM-RIGHT LANE (wooded flank)", f=small)
    for r in RAMPS:
        mid = (r["left"] + r["right"]) * 0.5
        d.line([P(x, y) for x, y in mid], fill=(250, 240, 170), width=3)
        fx, fy = P(*mid[0])
        d.ellipse([fx - 5, fy - 5, fx + 5, fy + 5], fill=(250, 240, 170), outline=(0, 0, 0))
    label(PLATEAU_P[0] + 600, PLATEAU_P[1], "THE HEIGHTS (player)", fill=(190, 215, 255))
    label(-PLATEAU_P[0] - 600, -PLATEAU_P[1], "THE HEIGHTS (enemy)", fill=(255, 200, 190))
    label(PLATEAU_P[0] - 300, PLATEAU_P[1], "%.1f m, 2 ramps" % (PLATEAU_H / 100.0), f=small)
    label(-PLATEAU_P[0] + 300, -PLATEAU_P[1], "%.1f m, 2 ramps" % (PLATEAU_H / 100.0), f=small)
    for x, y, rx, ry, h in MASSIFS:
        for sg in (1.0, -1.0):
            mx, my = float(np.clip(sg * x, -BOUND + 900, BOUND - 900)), float(np.clip(sg * y, -BOUND + 900, BOUND - 900))
            label(mx, my, "mountain %.0f m" % (squashed(h, sg * x) / 100.0), fill=(235, 235, 235), f=small)
    label(HIGHLAND_P[0] + 1700, HIGHLAND_P[1], "HIGHLAND (player's bank)")
    label(-HIGHLAND_P[0] - 1700, -HIGHLAND_P[1], "HIGHLAND (enemy's bank)")
    for parts, text, c in ((WOOD_PARTS, "fir-wood belt", (190, 255, 190)), (RIDGE_PARTS, "ridge", (255, 235, 200))):
        m = parts[0].interpolate(0.5, normalized=True)
        label(m.x + 420, m.y, text, fill=c, f=small)
        label(-m.x - 420, -m.y, text, fill=c, f=small)
    label(P_ANCHOR[0] - 1100, P_ANCHOR[1], "PLAYER", fill=(150, 190, 255))
    label(E_ANCHOR[0] + 1100, E_ANCHOR[1], "ENEMY", fill=(255, 160, 150))
    y0 = 8
    for text, c in (("deep water (blocked)", (44, 96, 132)), ("ford (walkable)", (170, 205, 200)), ("blocker boxes (rocks, trunks, wood belt, stones)", (150, 40, 30)),
                    ("ground too high to climb (ridge, knolls, bluffs, tors)", (112, 100, 86)), ("magenta: flat ground nobody can reach", (230, 40, 230)), ("circles: apron 34 m, territory 38 m; +X is up, +Y right", (255, 255, 255))):
        d.rectangle([8, y0, 22, y0 + 14], fill=c, outline=(0, 0, 0))
        d.text((28, y0), text, fill=(255, 255, 255), font=small)
        y0 += 18
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path)


def raster_dist(geoms, lines=False):
    """Distance in cm from every splat texel to the nearest of `geoms` (polygons, filled; or polylines), and the mask."""
    px = SPLAT_SIZE / SPLAT_RES
    img = Image.new("L", (SPLAT_RES, SPLAT_RES), 0)
    d = ImageDraw.Draw(img)

    def to_px(pts):
        return [((x - SPLAT_ORIGIN[0]) / px - 0.5, (y - SPLAT_ORIGIN[1]) / px - 0.5) for x, y in pts]

    for g in geoms:
        if lines:
            d.line(to_px(g), fill=255, width=1)
        else:
            d.polygon(to_px(g.exterior.coords), fill=255)
    if not lines:
        for g in geoms:
            for hole in g.interiors:
                d.polygon(to_px(hole.coords), fill=0)
    mask = np.array(img) > 0
    return ndimage.distance_transform_edt(~mask).astype(np.float32) * px, mask


def build_water_map():
    """T_WaterMap, read by M_Water. World-aligned over the same square as the splat map, half its resolution.
    R = distance in from the bank (0 at the bank .. 1 at 256 cm and beyond), G = ford (1 over a ford's gravel bed),
    B = current (1 in the river, 0 out in the still lake beyond the field)."""
    px = SPLAT_SIZE / SPLAT_RES
    _, water = raster_dist(list(LAKE.geoms))
    d_in = np.maximum(ndimage.distance_transform_edt(water).astype(np.float32) * px - px * 0.5, 0.0)
    d_ford, _ = raster_dist(FORD_POLYS)
    ford = np.clip(1.0 - d_ford / 160.0, 0.0, 1.0) * water
    d_riv, _ = raster_dist([RIVER_UP, RIVER_DOWN, CHANNEL_P, CHANNEL_E], lines=True)
    cur = np.clip(1.0 - (d_riv - 700.0) / 900.0, 0.0, 1.0)
    img = np.dstack([np.clip(d_in / 256.0, 0, 1), ford, cur, np.ones_like(cur)])
    h = SPLAT_RES // 2
    img = img.reshape(h, 2, h, 2, 4).mean(axis=(1, 3))
    return (img * 255 + 0.5).astype(np.uint8)


def plan_atmosphere():
    """Where the level builder puts the air. Mist: level sheets [x, y, z, radius, height above z] at the foot of the far
    mountain wall, the flanks' far ends and over the lake (the river's own mist needs no plan: it is the water mesh,
    raised).
    The birds are not planned here: ASRBirds flies them round the map at run time."""
    r = np.random.default_rng(909)
    mist = [[CORE + 4600.0, -CORE - 1800.0, LAKE_SURFACE, 3800.0, 160.0]]                # the lake the river rises in
    for y in np.arange(-BOUND + 1500, BOUND, 3600.0):                                   # the foot of the far mountain wall
        mist.append([BOUND + 900.0 + float(r.uniform(-200, 300)), float(y + r.uniform(-500, 500)), 0.0, float(r.uniform(1700, 2300)), float(r.uniform(260, 420))])
    for side in (-1.0, 1.0):
        for x in (2500.0, 8500.0):
            mist.append([x + float(r.uniform(-500, 500)), side * (BOUND + 1100.0), 0.0, float(r.uniform(1600, 2100)), float(r.uniform(240, 380))])
    return {"mist": mist}


# ============================================================================================ main
def main():
    global ROAD_DIST, SPLAT_DRY, HM
    plan_water()
    plan_belts()
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
    R, moss, dry = splat_heights(X, Y, R, moss, dry)
    buildings = apply_kingdoms()
    report, grid = validate()
    write_layout_preview(os.path.join(ROOT, "Saved", "MapPreview", "layout.png"), grid, report)
    with open(os.path.join(ROOT, "Saved", "MapPreview", "report.txt"), "w") as f:
        f.write("\n".join(report) + "\n")
    if FAST:
        os.makedirs(os.path.join(ROOT, "Saved", "WorldPreview"), exist_ok=True)
        write_preview(finish_splat(X, Y, R, moss, dry), os.path.join(ROOT, "Saved", "WorldPreview", "map.png"))
        print("plan only: nothing written to SourceArt")
        return

    if "--minimap" in sys.argv:                                # only the HUD's minimap base; nothing else is rewritten
        write_preview(finish_splat(X, Y, R, moss, dry), os.path.join(ROOT, "SourceArt", "Textures", "T_MinimapBase.png"), minimap=512)
        print("minimap written")
        return

    # ---- meshes
    meshes = []
    layout_terrain = []
    terrain = build_terrain_meshes()
    for name, m in terrain.items():
        pivot = m.recenter()
        meshes.append(m)
        layout_terrain.append({"mesh": name, "pos": list(pivot), "folder": GROUPS[name]})
    for i, (gi_, x, y, size, height, yaw) in enumerate(PEAKS):  # sculpted backdrop peaks (Tools/blender/build_mountains.py)
        path = os.path.join(ROOT, "SourceArt", "World", "Mountains", "peak_%d.npy" % gi_)
        if not os.path.exists(path):
            print("no %s: run Tools/blender/build_mountains.py (the skyline goes without this peak)" % os.path.basename(path))
            continue
        m = peak_mesh("SM_T_Peak_%02d" % i, np.load(path), size, height, yaw)
        meshes.append(m)
        layout_terrain.append({"mesh": m.name, "pos": [x, y, 0.0], "folder": "Terrain/Peaks"})
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
    for part in LAKE.geoms:
        add_wall(shore, ring_ccw(list(part.exterior.coords), False), 0.0, LAKE_BED)
        for hole in part.interiors:                            # the island's banks
            add_wall(shore, ring_ccw(list(hole.coords), True), 0.0, LAKE_BED)
        for cap in largest(part.buffer(30), 10.0, all_parts=True):
            add_cap(shore, cap, LAKE_BED)
    pivot = shore.recenter()
    meshes.append(shore)
    layout_terrain.append({"mesh": "SM_T_Shore", "pos": list(pivot), "folder": "Terrain/Shore"})
    water = Mesh("SM_Water")
    for cap in largest(LAKE.buffer(30), 10.0, all_parts=True):
        add_cap(water, cap, LAKE_SURFACE)
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
    Image.fromarray(build_water_map()).save(os.path.join(ROOT, "SourceArt", "Textures", "T_WaterMap.png"))

    # ---- layout
    layout = {
        "texel_cm": TEXEL, "bound": BOUND,
        "splat": {"origin": list(SPLAT_ORIGIN), "size": SPLAT_SIZE},
        "terrain": layout_terrain,
        # water: one sheet over the river, its channels and the far lake. "map" is the world square T_WaterMap covers
        # (the splat map's); "flow" the downstream direction the material slides its ripples along.
        "water": {"mesh": "SM_Water", "pos": list(wpivot), "surface": LAKE_SURFACE, "bed": LAKE_BED, "ford_bed": FORD_BED,
                  "map": {"origin": list(SPLAT_ORIGIN), "size": SPLAT_SIZE}, "flow": [FLOW_DIR[0], FLOW_DIR[1]]},
        # the map's structure, for the minimap, the AI or anything else that wants it (nothing in C++ needs it to play)
        "river": {"centre": [[round(x, 1), round(y, 1)] for x, y in RIVER_DOWN[::-1] + RIVER_UP],
                  "channels": [[[round(x, 1), round(y, 1)] for x, y in c] for c in (CHANNEL_P, CHANNEL_E)],
                  "fords": [{"pos": [round(f.centroid.x, 1), round(f.centroid.y, 1)], "width": 2 * FORD_HALF} for f in FORD_POLYS],
                  "bridges": [{"pos": [round(b.centroid.x, 1), round(b.centroid.y, 1)], "width": 2 * BRIDGE_HALF} for b in BRIDGE_POLYS]},
        "lanes": {"centre": [[x, y] for x, y in ROAD_MAIN_KEYS], "top_left": [[round(x, 1), round(y, 1)] for x, y in ROAD_TL_KEYS],
                  "bottom_right": [[round(-x, 1), round(-y, 1)] for x, y in ROAD_TL_KEYS[::-1]]},
        "landmark": {"name": "shrine", "pos": [0.0, 0.0], "radius": 780.0},
        "belt_gaps": [[round(x, 1), round(y, 1)] for x, y in BELT_GAPS + [mir(g) for g in BELT_GAPS]],
        "instances": INSTANCES, "actors": ACTORS, "blockers": BLOCKERS, "buildings": buildings,
        "veins": [[x, y, round(height_at(x, y), 1)] for x, y in GOLD_VEINS],
        # each kingdom's heights: the top's centre and height, and its two ramps (foot and head of the middle line)
        "heights": [{"team": team, "pos": [sg * PLATEAU_P[0], sg * PLATEAU_P[1], PLATEAU_H],
                     "ramps": [{"foot": [round(sg * float(v), 1) for v in (r["left"][0] + r["right"][0]) * 0.5],
                                "head": [round(sg * float(v), 1) for v in (r["left"][-1] + r["right"][-1]) * 0.5]} for r in RAMPS[:2]]}
                    for team, sg in ((0, 1.0), (1, -1.0))],
        "relief": {"tree_line": TREE_LINE, "rock_line": ROCK_LINE, "snow_line": SNOW_LINE},
        "atmosphere": plan_atmosphere(),
        "starts": {"player": list(PLAYER_START), "enemy": list(ENEMY_START)},
    }
    os.makedirs(os.path.join(ROOT, "SourceArt", "World"), exist_ok=True)
    with open(os.path.join(ROOT, "SourceArt", "World", "layout.json"), "w") as f:
        json.dump(layout, f, separators=(",", ":"))
    os.makedirs(os.path.join(ROOT, "Saved", "WorldPreview"), exist_ok=True)
    write_preview(splat, os.path.join(ROOT, "Saved", "WorldPreview", "map.png"))
    write_preview(splat, os.path.join(ROOT, "SourceArt", "Textures", "T_MinimapBase.png"), minimap=512)
    print("meshes %d (%d tris), tiers %d, instances %d, actors %d, blockers %d" % (
        count, tris, len(TIERS), sum(len(v) for v in INSTANCES.values()), len(ACTORS), len(BLOCKERS)))


if __name__ == "__main__":
    main()
