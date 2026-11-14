"""Mesh building + glTF export helpers for the offline world generator (gen_battlefield.py).

All geometry is authored in Unreal coordinates (cm, X forward, Y right, Z up). The glTF writer
converts to glTF's metre / Y-up frame so Interchange brings it back exactly.

Vertex conventions shared with the materials (Tools/build_visual_materials.py):
  UV0  surface coordinates in CENTIMETRES (the material divides by texel size * texture size), so
       texel density is the same on every mesh. Cliff walls: u = distance along the outline,
       v = depth below the turf edge.
  UV1  two free scalars per vertex (walls: x = total wall height; foliage: x = shade, y = sway).
  COLOR flags only (0 or 1): R, G, B meaning is per material (see each builder).
"""
import json
import os
import struct

import numpy as np


class Mesh:
    def __init__(self, name):
        self.name = name
        self.p, self.n, self.uv0, self.uv1, self.col, self.idx = [], [], [], [], [], []

    def vert(self, p, n, uv0=(0.0, 0.0), uv1=(0.0, 0.0), col=(1.0, 1.0, 1.0, 1.0)):
        self.p.append((float(p[0]), float(p[1]), float(p[2])))
        self.n.append((float(n[0]), float(n[1]), float(n[2])))
        self.uv0.append((float(uv0[0]), float(uv0[1])))
        self.uv1.append((float(uv1[0]), float(uv1[1])))
        self.col.append(tuple(float(c) for c in col))
        return len(self.p) - 1

    def tri(self, a, b, c):
        """Counter-clockwise seen from outside, in Unreal axes treated as right-handed."""
        self.idx.append((a, b, c))

    def quad(self, a, b, c, d):
        self.tri(a, b, c)
        self.tri(a, c, d)

    def flat_tri(self, p0, p1, p2, uvs=None, uv1=(0.0, 0.0), col=(1, 1, 1, 1), normal=None):
        p0, p1, p2 = (np.asarray(p, float) for p in (p0, p1, p2))
        n = normal
        if n is None:
            n = np.cross(p1 - p0, p2 - p0)
            ln = np.linalg.norm(n)
            if ln < 1e-9:
                return
            n = n / ln
        if uvs is None:
            uvs = [planar_uv(p, n) for p in (p0, p1, p2)]
        ids = [self.vert(p, n, uv, uv1, col) for p, uv in zip((p0, p1, p2), uvs)]
        self.tri(*ids)

    def flat_poly(self, pts, uv1=(0.0, 0.0), col=(1, 1, 1, 1), uv_offset=(0.0, 0.0), uvs=None):
        """Convex planar polygon, CCW from outside, flat shaded, planar UVs in cm."""
        pts = [np.asarray(p, float) for p in pts]
        n = np.cross(pts[1] - pts[0], pts[2] - pts[0])
        n = n / max(np.linalg.norm(n), 1e-9)
        if uvs is None:
            uvs = [np.asarray(planar_uv(p, n)) + uv_offset for p in pts]
        ids = [self.vert(p, n, uv, uv1, col) for p, uv in zip(pts, uvs)]
        for i in range(1, len(ids) - 1):
            self.tri(ids[0], ids[i], ids[i + 1])

    def box(self, lo, hi, col=(1, 1, 1, 1), uv_offset=(0.0, 0.0), bottom=False):
        x0, y0, z0 = lo
        x1, y1, z1 = hi
        self.flat_poly([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], col=col, uv_offset=uv_offset)        # top
        self.flat_poly([(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)], col=col, uv_offset=uv_offset)        # -Y
        self.flat_poly([(x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1)], col=col, uv_offset=uv_offset)        # +Y
        self.flat_poly([(x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1)], col=col, uv_offset=uv_offset)        # -X
        self.flat_poly([(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)], col=col, uv_offset=uv_offset)        # +X
        if bottom:
            self.flat_poly([(x0, y1, z0), (x1, y1, z0), (x1, y0, z0), (x0, y0, z0)], col=col, uv_offset=uv_offset)

    def transformed(self, name, yaw_deg=0.0, offset=(0, 0, 0)):
        """A copy rotated about Z and moved (UVs untouched: they are surface coordinates)."""
        m = Mesh(name)
        c, s = np.cos(np.radians(yaw_deg)), np.sin(np.radians(yaw_deg))
        rot = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
        m.p = [tuple(rot @ np.array(p) + np.array(offset)) for p in self.p]
        m.n = [tuple(rot @ np.array(n)) for n in self.n]
        m.uv0, m.uv1, m.col, m.idx = list(self.uv0), list(self.uv1), list(self.col), list(self.idx)
        return m

    def append(self, other):
        base = len(self.p)
        self.p += other.p; self.n += other.n; self.uv0 += other.uv0; self.uv1 += other.uv1; self.col += other.col
        self.idx += [(a + base, b + base, c + base) for a, b, c in other.idx]

    def recenter(self):
        """Moves the vertices so the mesh pivot is the XY centre of its bounds at Z = 0; returns the pivot."""
        a = np.array(self.p)
        c = np.array([(a[:, 0].min() + a[:, 0].max()) * 0.5, (a[:, 1].min() + a[:, 1].max()) * 0.5, 0.0])
        c = np.round(c)
        self.p = [tuple(row) for row in (a - c)]
        return tuple(float(v) for v in c)

    def empty(self):
        return not self.idx


def planar_uv(p, n):
    """Planar projection in the facet's own plane (cm): u runs horizontally, v runs down the face."""
    n = np.asarray(n, float)
    if abs(n[2]) > 0.92:
        return (p[1], -p[0])                        # top / bottom faces: same frame as the terrain tops
    t = np.cross((0.0, 0.0, 1.0), n)
    t /= np.linalg.norm(t)
    b = np.cross(n, t)                              # points up the face
    return (float(np.dot(p, t)), float(-np.dot(p, b)))


def write_gltf(path, meshes):
    """One glTF (+ .bin) holding every mesh as its own node. One placeholder material: Interchange
    rejects primitives without one; the import script never imports it and assigns the real materials."""
    buf = bytearray()
    views, accessors, gl_meshes, nodes = [], [], [], []

    def add(arr, target, comp, typ, minmax=False):
        nonlocal buf
        while len(buf) % 4:
            buf += b"\0"
        off = len(buf)
        raw = arr.tobytes()
        buf += raw
        views.append({"buffer": 0, "byteOffset": off, "byteLength": len(raw), "target": target})
        acc = {"bufferView": len(views) - 1, "componentType": comp, "count": int(arr.shape[0]), "type": typ}
        if minmax:
            acc["min"] = [float(v) for v in arr.min(axis=0)]
            acc["max"] = [float(v) for v in arr.max(axis=0)]
        accessors.append(acc)
        return len(accessors) - 1

    for m in meshes:
        if m.empty():
            continue
        p = np.array(m.p, np.float32)
        n = np.array(m.n, np.float32)
        pos = np.stack([p[:, 0], p[:, 2], p[:, 1]], 1) / 100.0          # UE (x, y, z) cm -> glTF (x, z, y) m
        nrm = np.stack([n[:, 0], n[:, 2], n[:, 1]], 1)
        nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
        idx = np.array(m.idx, np.uint32)[:, [0, 2, 1]].reshape(-1)      # the axis swap mirrors, so flip the winding
        col = np.clip(np.array(m.col, np.float32), 0.0, 1.0)
        attrs = {
            "POSITION": add(pos.astype(np.float32), 34962, 5126, "VEC3", True),
            "NORMAL": add(nrm.astype(np.float32), 34962, 5126, "VEC3"),
            "TEXCOORD_0": add(np.array(m.uv0, np.float32), 34962, 5126, "VEC2"),
            "TEXCOORD_1": add(np.array(m.uv1, np.float32), 34962, 5126, "VEC2"),
            "COLOR_0": add(col, 34962, 5126, "VEC4"),
        }
        gl_meshes.append({"name": m.name, "primitives": [{"attributes": attrs, "indices": add(idx, 34963, 5125, "SCALAR"), "mode": 4, "material": 0}]})
        nodes.append({"name": m.name, "mesh": len(gl_meshes) - 1})

    bin_name = os.path.splitext(os.path.basename(path))[0] + ".bin"
    doc = {"asset": {"version": "2.0", "generator": "Sovereign Realms gen_battlefield.py"},
           "scene": 0, "scenes": [{"nodes": list(range(len(nodes)))}], "nodes": nodes, "meshes": gl_meshes,
           "materials": [{"name": "SR", "pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1], "metallicFactor": 0, "roughnessFactor": 1}}],
           "accessors": accessors, "bufferViews": views, "buffers": [{"uri": bin_name, "byteLength": len(buf)}]}
    with open(path, "w") as f:
        json.dump(doc, f)
    with open(os.path.join(os.path.dirname(path), bin_name), "wb") as f:
        f.write(bytes(buf))
    return len(nodes)
