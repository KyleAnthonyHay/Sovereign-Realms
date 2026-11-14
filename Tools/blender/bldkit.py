"""Sovereign Realms building kit for Blender (bpy / bmesh): scripted modelling of the castle, farm and mine.

Authoring frame
---------------
Everything is authored in UNREAL coordinates and centimetres: +X is away from the game camera (up the screen),
+Y is screen right, +Z is up. A building's front faces -X. The kit converts to Blender on the way in
(metres, y negated, winding flipped), and the glTF exporter + Interchange bring it back exactly.

Vertex contract (shared with M_Building / M_BuildingCard in Tools/build_visual_materials.py)
-------------------------------------------------------------------------------------------
* UV0 is in CENTIMETRES; the material divides by the texel size (4 cm) and the texture size, so every face
  has the world's texel density. Walls: u = distance round the footprint (continuous through corners),
  v = -z, so stone courses line up on every face of every piece of a building. Tops: (y, -x), the terrain's
  frame. Slopes: planar in the face.
* UV1.x: opaque faces -> centimetres below the top of the wall the face belongs to (sun-bleached heads),
  9999 where that means nothing. Card faces -> sway weight 0..1 (0 = fixed edge).
* Vertex colour R: baked shade 0..1 (1 = none), multiplied in by the material.
* One mesh per building, one material slot per surface. Slot names are the keys of MATERIALS below; the
  Unreal import maps slot "Bld_X" to /Game/SR/Materials/MI_Bld_X.
"""
import math
import os
import random

import bmesh
import bpy
from mathutils import Matrix, Vector

TEXEL = 4.0
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEX_DIR = os.path.join(ROOT, "SourceArt", "Textures")
NO_TOP = 9999.0

# slot name -> (texture, kind). kind: opaque | card (alpha = hole) ; "team" marks slots whose alpha-153 texels
# take the team colour, "glow" those that glint. Mirrored in Tools/build_visual_materials.py (BUILDING_SLOTS).
MATERIALS = {
    "Bld_Ashlar": ("T_Bld_Ashlar", "opaque"),
    "Bld_AshlarLarge": ("T_Bld_AshlarLarge", "opaque"),
    "Bld_Trim": ("T_Bld_Trim", "opaque"),
    "Bld_Mudbrick": ("T_Bld_Mudbrick", "opaque"),
    "Bld_Plaster": ("T_Bld_Plaster", "opaque"),
    "Bld_RoofClay": ("T_Bld_RoofClay", "opaque"),
    "Bld_Beam": ("T_Bld_Beam", "opaque"),
    "Bld_Planks": ("T_Bld_Planks", "opaque"),
    "Bld_Door": ("T_Bld_Door", "opaque"),
    "Bld_Shutter": ("T_Bld_Shutter", "opaque"),
    "Bld_Thatch": ("T_Bld_Thatch", "opaque"),
    "Bld_Soil": ("T_Bld_Soil", "opaque"),
    "Bld_Frieze": ("T_Bld_Frieze", "opaque team"),
    "Bld_Bronze": ("T_Bld_Bronze", "opaque"),
    "Bld_Ore": ("T_Bld_Ore", "opaque glow"),
    "Bld_Pot": ("T_Bld_Pot", "opaque"),
    "Bld_Dark": ("T_Bld_Dark", "opaque"),
    "Bld_Dirt": ("T_Dirt", "opaque"),
    "Bld_Bark": ("T_Bark", "opaque"),
    "Bld_LeafCore": ("T_Bld_Leaves", "opaque"),
    "Bld_Leaves": ("T_Bld_Leaves", "card"),
    "Bld_Wheat": ("T_Bld_Wheat", "card"),
    "Bld_Banner": ("T_Bld_Banner", "card team"),
    "Bld_Awning": ("T_Bld_Awning", "card team"),
    "Bld_Flame": ("T_Bld_Flame", "card glow"),
    "Bld_Rock": ("T_Rock", "opaque"),
    "Bld_Gold": ("T_Bld_Gold", "opaque glow"),
    "Bld_Cobble": ("T_Cobble", "opaque"),
    "Bld_Cliff": ("T_Cliff", "opaque"),
    "Bld_Turf": ("T_Grass", "opaque"),
}


def convex_ring(points):
    """2D convex hull of (x, y) points as a CCW ring in the kit's sense (the order rect() uses)."""
    pts = sorted(set((round(p[0], 3), round(p[1], 3)) for p in points))
    if len(pts) < 3:
        return pts

    def half(seq):
        out = []
        for p in seq:
            while len(out) >= 2 and (out[-1][0] - out[-2][0]) * (p[1] - out[-2][1]) - (out[-1][1] - out[-2][1]) * (p[0] - out[-2][0]) <= 0:
                out.pop()
            out.append(p)
        return out[:-1]
    return half(pts) + half(reversed(pts))


def clip_ring(ring, axis, limit, keep_less):
    """Clips a convex ring against x or y = limit (axis 0 or 1), keeping the side below (keep_less) or above."""
    out = []
    n = len(ring)
    inside = lambda p: (p[axis] <= limit + 1e-6) if keep_less else (p[axis] >= limit - 1e-6)
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        if inside(a):
            out.append(a)
        if inside(a) != inside(b):
            t = (limit - a[axis]) / (b[axis] - a[axis])
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return out


def V3(p):
    return Vector((float(p[0]), float(p[1]), float(p[2])))


def rot_matrix(yaw=0.0, pitch=0.0, roll=0.0):
    """Unreal-style: yaw about Z, pitch about Y, roll about X (degrees), applied roll first."""
    return (Matrix.Rotation(math.radians(yaw), 3, "Z") @ Matrix.Rotation(math.radians(pitch), 3, "Y")
            @ Matrix.Rotation(math.radians(roll), 3, "X"))


def rect(x0, y0, x1, y1):
    """Counter-clockwise footprint ring (seen from above), starting at the far-left corner so the wall seam
    (where u wraps) sits on the back of the building."""
    return [(x1, y0), (x1, y1), (x0, y1), (x0, y0)]


def ngon(cx, cy, r, sides, rot=0.0):
    return [(cx + r * math.cos(math.radians(rot) + 2 * math.pi * i / sides), cy + r * math.sin(math.radians(rot) + 2 * math.pi * i / sides))
            for i in range(sides)]


def inset_ring(ring, d):
    """Moves every edge of a convex CCW ring inward by d (mitred corners)."""
    n = len(ring)
    out = []
    for i in range(n):
        p0, p1, p2 = Vector(ring[i - 1]), Vector(ring[i]), Vector(ring[(i + 1) % n])
        e0, e1 = (p1 - p0).normalized(), (p2 - p1).normalized()
        n0, n1 = Vector((-e0.y, e0.x)), Vector((-e1.y, e1.x))          # inward normals of a CCW ring
        m = (n0 + n1)
        m = m / max(m.dot(n0), 1e-6)
        out.append(tuple(p1 + m * d))
    return out


class Kit:
    def __init__(self, name, seed=1):
        self.name = name
        self.faces = []            # (slot, [Vector], [(u, v)], [w], shade)
        self.rng = random.Random(seed)
        self._off = Vector((0, 0, 0))
        self._yaw = 0.0
        self.colliders = []        # (centre, size, yaw) boxes, cm, for the import script
        self.sockets = {}          # named points (gate, rally ...) for gameplay

    # ------------------------------------------------------------------ placement of sub-assemblies
    def at(self, offset=(0, 0, 0), yaw=0.0):
        kit = self

        class _Ctx:
            def __enter__(self_):
                self_.saved = (kit._off.copy(), kit._yaw)
                kit._off = kit._off + rot_matrix(kit._yaw) @ V3(offset)
                kit._yaw += yaw

            def __exit__(self_, *a):
                kit._off, kit._yaw = self_.saved
        return _Ctx()

    def _w(self, p):
        """Local point -> building space."""
        return rot_matrix(self._yaw) @ V3(p) + self._off

    def U(self, a, b):
        return self.rng.uniform(a, b)

    # ------------------------------------------------------------------ faces
    def poly(self, slot, pts, uvs=None, w=NO_TOP, shade=1.0, uvo=(0.0, 0.0), local=True):
        """Convex planar polygon, counter-clockwise seen from outside. Without `uvs`: planar UVs in cm
        (walls u along / v = -z, tops (y, -x), slopes in the face)."""
        P = [self._w(p) for p in pts] if local else [V3(p) for p in pts]
        if uvs is None:
            n = (P[1] - P[0]).cross(P[2] - P[0])
            if n.length < 1e-9:
                return
            n.normalize()
            uvs = [self.planar_uv(p, n, uvo) for p in P]
        if w == NO_TOP and "card" in MATERIALS.get(slot, ("", ""))[1]:
            w = 0.0                                        # on card slots UV1.x is the sway weight
        ws = w if isinstance(w, (list, tuple)) else [w] * len(P)
        self.faces.append((slot, P, [tuple(u) for u in uvs], list(ws), shade))

    @staticmethod
    def planar_uv(p, n, uvo=(0.0, 0.0)):
        if abs(n.z) > 0.92:
            return (p.y + uvo[0], -p.x + uvo[1])
        t = n.cross(Vector((0, 0, 1))).normalized()       # the viewer's right
        if abs(n.z) < 0.35:
            return (p.dot(t) + uvo[0], -p.z + uvo[1])
        b = t.cross(n)                                      # up the face
        return (p.dot(t) + uvo[0], -p.dot(b) + uvo[1])

    # ------------------------------------------------------------------ walls
    def wall(self, slot, ring, z0, z1, inset=0.0, u0=0.0, openings=None, bleach=True, v0=None, skip=()):
        """Walls round a convex CCW footprint from z0 up to z1, leaning in by `inset` (a batter) at the top.
        u runs continuously round the ring (increasing toward the viewer's right on every face, so the textures'
        lit top-left edges stay top-left), v = -z (or z1 - z + v0 when v0 is given: bands whose texture has a top).
        openings: {edge index: [dict(a, b, z0, z1, depth, back=slot or None, back_uv=(u, v), reveal=slot)]} cut
        real recesses; a..b are distances along the edge from its first corner (the viewer's RIGHT end of the
        face). Returns the top ring."""
        openings = openings or {}
        top = inset_ring(ring, inset) if inset else list(ring)
        n = len(ring)
        s = u0
        zoff = self._off.z
        H = z1 - z0

        def vv(z):
            return (z1 - z + v0) if v0 is not None else -(z + zoff)

        for i in range(n):
            p0, p1 = Vector(ring[i]), Vector(ring[(i + 1) % n])
            q0, q1 = Vector(top[i]), Vector(top[(i + 1) % n])
            d = p1 - p0
            L = d.length
            if L < 1e-6:
                continue
            d /= L
            nrm = Vector((d.y, -d.x))                       # outward
            if i in skip:
                s += L
                continue
            ops = openings.get(i, [])
            ss = sorted(set([0.0, L] + [o["a"] for o in ops] + [o["b"] for o in ops]))
            zs = sorted(set([z0, z1] + [o["z0"] for o in ops] + [o["z1"] for o in ops]))

            def P(sv, z, depth=0.0):
                f = (z - z0) / H if H else 0.0
                if sv <= 1e-6:
                    b = p0.lerp(q0, f)
                elif sv >= L - 1e-6:
                    b = p1.lerp(q1, f)
                else:
                    b = p0 + d * sv - nrm * (inset * f)
                b = b - nrm * depth
                return (b.x, b.y, z)

            def opening(ai, zi):
                if ai < 0 or zi < 0 or ai >= len(ss) - 1 or zi >= len(zs) - 1:
                    return None
                sc, zc = (ss[ai] + ss[ai + 1]) * 0.5, (zs[zi] + zs[zi + 1]) * 0.5
                for o in ops:
                    if o["a"] < sc < o["b"] and o["z0"] < zc < o["z1"]:
                        return o
                return None

            for ai in range(len(ss) - 1):
                for zi in range(len(zs) - 1):
                    sa, sb, za, zb = ss[ai], ss[ai + 1], zs[zi], zs[zi + 1]
                    o = opening(ai, zi)
                    if o is None:
                        corners = [(sa, za), (sb, za), (sb, zb), (sa, zb)]
                        self.poly(slot, [P(a, z) for a, z in corners], [(-(s + a), vv(z)) for a, z in corners],
                                  [((z1 - z) if bleach else NO_TOP) for a, z in corners])
                        continue
                    dep = o.get("depth", 24.0)
                    rs = o.get("reveal", slot)
                    sh = o.get("shade", 0.8)
                    if opening(ai - 1, zi) is None:          # jamb at sa, facing along the edge
                        self.poly(rs, [P(sa, za), P(sa, za, dep), P(sa, zb, dep), P(sa, zb)], shade=sh)
                    if opening(ai + 1, zi) is None:          # jamb at sb
                        self.poly(rs, [P(sb, za), P(sb, zb), P(sb, zb, dep), P(sb, za, dep)], shade=sh)
                    if opening(ai, zi - 1) is None and not o.get("no_sill"):          # sill
                        self.poly(rs, [P(sa, za), P(sb, za), P(sb, za, dep), P(sa, za, dep)], shade=sh)
                    if opening(ai, zi + 1) is None:          # head
                        self.poly(rs, [P(sa, zb), P(sa, zb, dep), P(sb, zb, dep), P(sb, zb)], shade=sh * 0.8)
            for o in ops:                                    # one back face per opening
                if o.get("back"):
                    dep = o.get("depth", 24.0)
                    bu, bv = o.get("back_uv", (0.0, 0.0))
                    corners = [(o["a"], o["z0"]), (o["b"], o["z0"]), (o["b"], o["z1"]), (o["a"], o["z1"])]
                    uv = [(o["b"] - a + bu, o["z1"] - z + bv) for a, z in corners]
                    self.poly(o["back"], [P(a, z, dep) for a, z in corners], uv, shade=o.get("back_shade", 0.85))
            s += L
        return top

    def cap(self, slot, ring, z, uvo=(0.0, 0.0), shade=1.0, down=False):
        pts = [(x, y, z) for x, y in ring]
        if down:
            pts.reverse()
        self.poly(slot, pts, uvo=uvo, shade=shade)

    def box(self, slot, lo, hi, top=None, inset=0.0, v0=None, bleach=False, bottom=False, u0=None, shade=1.0, openings=None, skip=()):
        """Axis-aligned block. `top` = slot of the upper face (default: same). v0 given -> v counts down from the
        block's own top edge (trim, frieze)."""
        ring = rect(lo[0], lo[1], hi[0], hi[1])
        tr = self.wall(slot, ring, lo[2], hi[2], inset=inset, u0=self.U(0, 512) if u0 is None else u0, bleach=bleach, v0=v0,
                       openings=openings, skip=skip)
        self.cap(top or slot, tr, hi[2], uvo=(self.U(0, 256), self.U(0, 256)) if top is None else (0.0, 0.0))
        if bottom:
            self.cap(slot, ring, lo[2], down=True, shade=0.7)
        return tr

    def prism(self, slot, ring, z0, z1, top=None, inset=0.0, v0=None, bleach=False, u0=0.0, openings=None, cap=True):
        tr = self.wall(slot, ring, z0, z1, inset=inset, u0=u0, bleach=bleach, v0=v0, openings=openings)
        if cap:
            self.cap(top or slot, tr, z1)
        return tr

    def obox(self, slot, centre, size, yaw=0.0, pitch=0.0, roll=0.0, top=None, uvo=None, grain="x"):
        """Oriented box. UVs are planar in the box's own frame (texels stay square on a tilted piece).
        grain: which local axis the texture's u follows on the long faces (timber: along the piece)."""
        hx, hy, hz = size[0] / 2.0, size[1] / 2.0, size[2] / 2.0
        R = rot_matrix(yaw, pitch, roll)
        c = V3(centre)
        uo = uvo if uvo is not None else (self.U(0, 256), self.U(0, 256))
        faces = [  # (normal axis, sign, corners in local, u axis, v axis)
            ((0, 0, 1), [(-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)]),
            ((0, 0, -1), [(-hx, hy, -hz), (hx, hy, -hz), (hx, -hy, -hz), (-hx, -hy, -hz)]),
            ((0, -1, 0), [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, -hy, hz), (-hx, -hy, hz)]),
            ((0, 1, 0), [(hx, hy, -hz), (-hx, hy, -hz), (-hx, hy, hz), (hx, hy, hz)]),
            ((-1, 0, 0), [(-hx, hy, -hz), (-hx, -hy, -hz), (-hx, -hy, hz), (-hx, hy, hz)]),
            ((1, 0, 0), [(hx, -hy, -hz), (hx, hy, -hz), (hx, hy, hz), (hx, -hy, hz)]),
        ]
        for nrm, corners in faces:
            uv = []
            for (x, y, z) in corners:
                if grain == "x":
                    u, v = (x, y) if nrm[2] else ((x, -z) if nrm[1] else (y, -z))
                elif grain == "y":
                    u, v = (y, x) if nrm[2] else ((x, -z) if nrm[1] else (y, -z))
                    if nrm[1]:
                        u, v = z, x
                else:                                        # "z": upright timber, grain runs up the piece
                    u, v = (x, y) if nrm[2] else ((z, x) if nrm[1] else (z, y))
                uv.append((u + uo[0], v + uo[1]))
            s = top if (top and nrm == (0, 0, 1)) else slot
            self.poly(s, [R @ Vector(p) + c for p in corners], uv)

    def cyl(self, slot, c0, c1, r0, r1=None, sides=8, caps=True, cap_slot=None, grain="axis", uvo=None):
        """Tapered prism between two points. grain 'axis': u along the piece (timber); 'ring': u round it."""
        r1 = r0 if r1 is None else r1
        a, b = V3(c0), V3(c1)
        axis = b - a
        length = axis.length
        axis.normalize()
        ref = Vector((0, 0, 1)) if abs(axis.z) < 0.9 else Vector((1, 0, 0))
        e1 = axis.cross(ref).normalized()
        e2 = axis.cross(e1)
        uo = uvo if uvo is not None else (self.U(0, 64), self.U(0, 64))
        circ = 2 * math.pi * max(r0, r1)
        for i in range(sides):
            a0, a1 = 2 * math.pi * i / sides, 2 * math.pi * (i + 1) / sides
            d0, d1 = e1 * math.cos(a0) + e2 * math.sin(a0), e1 * math.cos(a1) + e2 * math.sin(a1)
            pts = [a + d0 * r0, a + d1 * r0, b + d1 * r1, b + d0 * r1]
            if grain == "axis":
                uv = [(0, circ * i / sides), (0, circ * (i + 1) / sides), (length, circ * (i + 1) / sides), (length, circ * i / sides)]
            else:
                uv = [(circ * i / sides, length), (circ * (i + 1) / sides, length), (circ * (i + 1) / sides, 0), (circ * i / sides, 0)]
            uv = [(u + uo[0], v + uo[1]) for u, v in uv]
            if (pts[1] - pts[0]).cross(pts[2] - pts[0]).dot(d0 + d1) < 0:
                pts.reverse(); uv.reverse()
            self.poly(slot, pts, uv)
        if caps:
            for centre, rad, sign in ((a, r0, -1.0), (b, r1, 1.0)):
                if rad < 0.5:
                    continue
                pts = [centre + (e1 * math.cos(2 * math.pi * i / sides) + e2 * math.sin(2 * math.pi * i / sides)) * rad for i in range(sides)]
                uv = [(math.cos(2 * math.pi * i / sides) * rad + uo[0], math.sin(2 * math.pi * i / sides) * rad + uo[1]) for i in range(sides)]
                if (pts[1] - pts[0]).cross(pts[2] - pts[0]).dot(axis * sign) < 0:
                    pts.reverse(); uv.reverse()
                self.poly(cap_slot or slot, pts, uv)

    def lathe(self, slot, centre, profile, sides=8, top=None, rot=0.0, uvo=(0.0, 0.0)):
        """Surface of revolution about Z through `centre`; profile = [(radius, z)] from the bottom up.
        u runs round the piece (at the widest radius' density), v down the profile from its top."""
        c = V3(centre)
        rmax = max(r for r, _ in profile)
        circ = 2 * math.pi * rmax
        circ = max(round(circ / 32.0), 1) * 32.0             # close the seam on a whole number of 8-texel repeats
        dist = [0.0]
        for (ra, za), (rb, zb) in zip(profile[:-1], profile[1:]):
            dist.append(dist[-1] + math.hypot(rb - ra, zb - za))
        total = dist[-1]
        for k in range(len(profile) - 1):
            (ra, za), (rb, zb) = profile[k], profile[k + 1]
            for i in range(sides):
                a0, a1 = math.radians(rot) + 2 * math.pi * i / sides, math.radians(rot) + 2 * math.pi * (i + 1) / sides
                pts, uv = [], []
                for ang, r, z, dd, ii in ((a0, ra, za, dist[k], i), (a1, ra, za, dist[k], i + 1), (a1, rb, zb, dist[k + 1], i + 1), (a0, rb, zb, dist[k + 1], i)):
                    pts.append(c + Vector((math.cos(ang) * r, math.sin(ang) * r, z)))
                    uv.append((circ * ii / sides + uvo[0], total - dd + uvo[1]))
                if ra < 0.5:
                    pts, uv = pts[1:], uv[1:]
                elif rb < 0.5:
                    pts, uv = pts[:3], uv[:3]
                self.poly(slot, pts, uv)
        r_top, z_top = profile[-1]
        if r_top >= 0.5 and top is not False:
            self.poly(top or slot, [c + Vector((math.cos(math.radians(rot) + 2 * math.pi * i / sides) * r_top,
                                                math.sin(math.radians(rot) + 2 * math.pi * i / sides) * r_top, z_top)) for i in range(sides)])

    def hull(self, slot, points, uvo=None, w=NO_TOP):
        """Convex hull of a point cloud, flat shaded, planar UVs per facet (boulders, heaps, canopies)."""
        bm = bmesh.new()
        for p in points:
            bm.verts.new(self._w(p))
        res = bmesh.ops.convex_hull(bm, input=bm.verts)
        bm.faces.ensure_lookup_table()
        centre = sum((v.co for v in bm.verts), Vector()) / max(len(bm.verts), 1)
        uo = uvo if uvo is not None else (self.U(0, 256), self.U(0, 256))
        for f in bm.faces:
            pts = [v.co.copy() for v in f.verts]
            n = (pts[1] - pts[0]).cross(pts[2] - pts[0])
            if n.dot(pts[0] - centre) < 0:
                pts.reverse()
            self.poly(slot, pts, uvo=uo, local=False, w=w)
        bm.free()

    def blob(self, slot, centre, size, points=14, flat=True, squash=0.55, lo=None, hi=None, w=NO_TOP):
        """A chunky faceted lump: hull of jittered points on an ellipsoid (optionally clamped to a box lo..hi)."""
        c = V3(centre)
        pts = []
        for _ in range(points):
            v = Vector((self.rng.gauss(0, 1), self.rng.gauss(0, 1), self.rng.gauss(0, 1)))
            v.normalize()
            v *= self.U(0.78, 1.0)
            xy = max(math.hypot(v.x, v.y), 0.4) ** squash
            v.x /= xy; v.y /= xy
            if flat:
                v.z = max(v.z, -0.3)
            p = c + Vector((v.x * size[0] * 0.5, v.y * size[1] * 0.5, v.z * size[2] * 0.5))
            if lo is not None:
                p = Vector((max(p.x, lo[0]), max(p.y, lo[1]), max(p.z, lo[2])))
            if hi is not None:
                p = Vector((min(p.x, hi[0]), min(p.y, hi[1]), min(p.z, hi[2])))
            pts.append(p)
        self.hull(slot, pts, w=w)

    def quad(self, slot, pts, uvs, w=NO_TOP, shade=1.0):
        self.poly(slot, pts, uvs, w, shade)

    def card(self, slot, p0, p1, height, tex_h, u0=0.0, sway=True, lean=0.0):
        """Upright card from ground point p0 to p1 (cm), `height` tall; v = 0 at the texture's top row.
        tex_h: texture height in cm (so the roots sit on the bottom row)."""
        a, b = V3(p0), V3(p1)
        L = (b - a).length
        up = Vector((lean, 0, height))
        pts = [a, b, b + up, a + up]
        uv = [(u0, tex_h), (u0 + L, tex_h), (u0 + L, tex_h - height), (u0, tex_h - height)]
        self.poly(slot, pts, uv, w=[0.0, 0.0, 1.0, 1.0] if sway else 0.0)

    # ------------------------------------------------------------------ common building parts
    def crenels(self, slot, ring, z, height=56.0, width=48.0, gap=36.0, thick=28.0, cap=None, broken=0.0, edges=None, skip_spans=None):
        """Merlons along the edges of a CCW ring, standing on z, flush with the outer face. A merlon sits on each
        corner. `broken`: chance a merlon has lost its upper courses."""
        n = len(ring)
        for i in range(n):
            if edges is not None and i not in edges:
                continue
            p0, p1 = Vector(ring[i]), Vector(ring[(i + 1) % n])
            d = p1 - p0
            L = d.length
            d /= L
            inward = Vector((-d.y, d.x))
            count = max(int(round((L + gap) / (width + gap))), 2)
            step = (L - width) / (count - 1)
            for k in range(count):
                s0 = k * step
                if skip_spans and any(a < s0 + width * 0.5 < b for a, b in skip_spans.get(i, [])):
                    continue
                h = height
                if broken and self.rng.random() < broken and 0 < k < count - 1:
                    h = height - 24.0
                c = p0 + d * (s0 + width / 2) + inward * (thick / 2)
                yaw = math.degrees(math.atan2(d.y, d.x))
                self.obox_wall(slot, (c.x, c.y, z), (width, thick, h), yaw, cap=cap)

    def obox_wall(self, slot, base, size, yaw, cap=None, cap_h=8.0, bleach=True):
        """A small upright block (merlon, pier) whose faces keep the wall mapping (v = -z)."""
        w, t, h = size
        with self.at(base, yaw):
            body_h = h - (cap_h if cap else 0.0)
            ring = rect(-w / 2, -t / 2, w / 2, t / 2)
            self.wall(slot, ring, 0.0, body_h, u0=self.U(0, 512), bleach=bleach)
            if cap:
                r2 = rect(-w / 2 - 3, -t / 2 - 3, w / 2 + 3, t / 2 + 3)
                self.cap(cap, r2, body_h, down=True, shade=0.7)
                self.wall(cap, r2, body_h, h, v0=0.0, bleach=False, u0=self.U(0, 256))
                self.cap(cap, r2, h)
            else:
                self.cap(slot, ring, h)

    def band(self, slot, ring, z0, z1, out=8.0, u0=0.0, under=True):
        """A projecting course (string course, coping) round a ring; texture top-aligned."""
        r2 = inset_ring(ring, -out)
        self.wall(slot, r2, z0, z1, v0=0.0, bleach=False, u0=u0)
        self.cap(slot, r2, z1)
        if under:
            self.cap(slot, r2, z0, down=True, shade=0.6)
        return r2

    def beam_ends(self, slot, p0, p1, z, count, size=(20.0, 20.0), out=28.0):
        """Roof-beam ends (vigas) poking out of a wall between p0 and p1 (points on the wall face, CCW order)."""
        a, b = Vector(p0), Vector(p1)
        d = (b - a)
        L = d.length
        d /= L
        nrm = Vector((d.y, -d.x))
        yaw = math.degrees(math.atan2(nrm.y, nrm.x))
        for k in range(count):
            c = a + d * (L * (k + 0.5) / count) + nrm * (out / 2 - 2)
            self.obox(slot, (c.x, c.y, z), (out + 4, size[0], size[1]), yaw=yaw)

    def pole_banner(self, pos, height=420.0, cloth_w=64.0, cloth_h=192.0, yaw=0.0, arm=44.0, slot="Bld_Banner"):
        """A banner pole with a cross arm; the cloth hangs facing the building's front (-X after yaw)."""
        with self.at(pos, yaw):
            self.cyl("Bld_Beam", (0, 0, -4), (0, 0, height), 6.0, 5.0, sides=6)
            self.cyl("Bld_Bronze", (0, 0, height), (0, 0, height + 14), 7.0, 0.6, sides=6)
            self.obox("Bld_Beam", (0, 0, height - 20), (6, cloth_w + 16, 6), grain="y")
            self.hang_cloth((-4, -cloth_w / 2, height - 24), (-4, cloth_w / 2, height - 24), cloth_h, slot)

    def hang_cloth(self, a, b, drop, slot="Bld_Banner", u0=0.0):
        """Cloth hanging from the line a -> b (left to right as seen from the front), `drop` cm long."""
        a, b = V3(a), V3(b)
        L = (b - a).length
        pts = [a - Vector((0, 0, drop)), b - Vector((0, 0, drop)), b, a]
        # seen from -X the line runs toward +Y = screen right: u increases along it
        uv = [(u0, drop), (u0 + L, drop), (u0 + L, 0.0), (u0, 0.0)]
        self.poly(slot, [pts[1], pts[0], pts[3], pts[2]], [uv[1], uv[0], uv[3], uv[2]], w=[1.0, 1.0, 0.0, 0.0])

    def pot(self, pos, scale=1.0, slot="Bld_Pot", sides=8):
        s = scale
        prof = [(10 * s, 0), (20 * s, 8 * s), (26 * s, 26 * s), (24 * s, 44 * s), (14 * s, 56 * s), (11 * s, 60 * s), (15 * s, 66 * s)]
        self.lathe(slot, pos, prof, sides=sides, top="Bld_Dark", rot=self.U(0, 45))

    def basket(self, pos, r=22.0, h=26.0, fill=None):
        self.lathe("Bld_Thatch", pos, [(r * 0.7, 0), (r, h * 0.6), (r, h)], sides=8, top=fill or "Bld_Dark", rot=self.U(0, 45))

    def crate(self, pos, size=(56, 56, 44), yaw=0.0, fill=None):
        c = (pos[0], pos[1], pos[2] + size[2] / 2)
        self.obox("Bld_Planks", c, size, yaw=yaw, top=fill)
        for sx in (-1, 1):
            for sy in (-1, 1):
                R = rot_matrix(yaw)
                p = R @ Vector((sx * (size[0] / 2 - 2), sy * (size[1] / 2 - 2), 0)) + V3(c)
                self.obox("Bld_Beam", p, (7, 7, size[2] + 4), yaw=yaw, grain="z")

    def brazier(self, pos, h=84.0):
        with self.at(pos):
            for k in range(3):
                a = math.radians(90 + 120 * k)
                self.cyl("Bld_Bronze", (math.cos(a) * 20, math.sin(a) * 20, 0), (math.cos(a) * 6, math.sin(a) * 6, h - 12), 2.6, sides=4)
            self.lathe("Bld_Bronze", (0, 0, h - 16), [(6, 0), (20, 8), (26, 18), (27, 22)], sides=8, top="Bld_Dark")
            for yaw in (0.0, 90.0):
                R = rot_matrix(yaw)
                a, b = R @ Vector((0, -32, 0)), R @ Vector((0, 32, 0))
                z = h + 2
                pts = [(a.x, a.y, z), (b.x, b.y, z), (b.x, b.y, z + 64), (a.x, a.y, z + 64)]
                self.poly("Bld_Flame", pts, [(0, 64), (64, 64), (64, 0), (0, 0)], w=[0.0, 0.0, 1.0, 1.0])

    def steps(self, slot, x0, x1, y0, y1, z0, z1, count, top=None):
        """Steps rising toward +X (from x0 at z0 to x1 at z1)."""
        rise = (z1 - z0) / count
        run = (x1 - x0) / count
        for k in range(count):
            self.box(slot, (x0 + run * k, y0, z0), (x1, y1, z0 + rise * (k + 1)), top=top)


    # ------------------------------------------------------------------ more building parts
    def parapet(self, slot, ring, z_floor, z_top, thick=26.0, floor="Bld_RoofClay", top=None, u0=0.0):
        """The inside of a wall head: a ledge `thick` wide at z_top round the ring, its inner face down to
        z_floor, and the floor. The outer face is the caller's wall. Returns the inner ring."""
        inner = inset_ring(ring, thick)
        n = len(ring)
        for i in range(n):
            a, b = ring[i], ring[(i + 1) % n]
            c, d = inner[(i + 1) % n], inner[i]
            self.poly(top or slot, [(a[0], a[1], z_top), (b[0], b[1], z_top), (c[0], c[1], z_top), (d[0], d[1], z_top)])
        self.wall(slot, list(reversed(inner)), z_floor, z_top, u0=u0, bleach=False)
        self.cap(floor, inner, z_floor)
        return inner

    def stepped_merlons(self, slot, ring, z, width=56.0, gap=28.0, thick=26.0, h1=28.0, h2=24.0, edges=None,
                        skip_spans=None, broken=0.0, cap=None):
        """Crow-stepped merlons (a low block carrying a narrower one), flush with the outer face of a CCW ring."""
        n = len(ring)
        for i in range(n):
            if edges is not None and i not in edges:
                continue
            p0, p1 = Vector(ring[i]), Vector(ring[(i + 1) % n])
            d = p1 - p0
            L = d.length
            d /= L
            inward = Vector((-d.y, d.x))
            count = max(int(round((L + gap) / (width + gap))), 2)
            step = (L - width) / (count - 1)
            yaw = math.degrees(math.atan2(d.y, d.x))
            for k in range(count):
                s0 = k * step
                if skip_spans and any(a < s0 + width * 0.5 < b for a, b in skip_spans.get(i, [])):
                    continue
                c = p0 + d * (s0 + width / 2) + inward * (thick / 2)
                self.obox_wall(slot, (c.x, c.y, z), (width, thick, h1), yaw)
                if broken and self.rng.random() < broken and 0 < k < count - 1:
                    continue
                self.obox_wall(slot, (c.x, c.y, z + h1), (width * 0.5, thick, h2), yaw, cap=cap, cap_h=6.0)

    def patch(self, slot, origin, right, up, w, h, cells=12.0, fill=0.62, out=3.0, sway=0.0):
        """An irregular patch of small cards on a surface (creeper on a wall): `origin` is its lower middle,
        `right` / `up` unit vectors in the surface with right x up = its outward normal (a wall facing -X:
        right (0, -1, 0), up (0, 0, 1)), `out` cm proud of it. Denser at the bottom."""
        o, r, u = V3(origin), V3(right).normalized(), V3(up).normalized()
        nrm = r.cross(u)
        if nrm.length < 1e-6:
            return
        cols, rows = max(int(w / cells), 1), max(int(h / cells), 1)
        uo = (self.U(0, 256), self.U(0, 256))
        for j in range(rows):
            for i in range(cols):
                fx = (i + 0.5) / cols - 0.5
                fy = (j + 0.5) / rows
                keep = fill * (1.15 - fy) * (1.0 - abs(fx) * (0.6 + fy))
                if self.rng.random() > keep * 1.6:
                    continue
                x0, y0 = fx * w - cells / 2, j * cells
                pts = [o + r * x0 + u * y0, o + r * (x0 + cells) + u * y0, o + r * (x0 + cells) + u * (y0 + cells), o + r * x0 + u * (y0 + cells)]
                pts = [p + nrm * out for p in pts]
                uv = [(x0 + uo[0], -y0 + uo[1]), (x0 + cells + uo[0], -y0 + uo[1]), (x0 + cells + uo[0], -(y0 + cells) + uo[1]), (x0 + uo[0], -(y0 + cells) + uo[1])]
                self.poly(slot, pts, uv, w=sway)

    def tree(self, pos, height=330.0, spread=150.0, lean=(18.0, -10.0), blobs=5):
        """An olive: a short twisted trunk forking into two limbs, a canopy of chunky leaf lumps."""
        with self.at(pos):
            th = height * 0.42
            mid = (lean[0] * 0.4, lean[1] * 0.4, th * 0.55)
            top = (lean[0], lean[1], th)
            self.cyl("Bld_Bark", (0, 0, -4), mid, 17.0, 13.0, sides=6, grain="ring")
            self.cyl("Bld_Bark", mid, top, 13.0, 10.0, sides=6, grain="ring")
            limbs = [(lean[0] + spread * 0.32, lean[1] + spread * 0.2, th + height * 0.22), (lean[0] - spread * 0.3, lean[1] - spread * 0.25, th + height * 0.2)]
            for l in limbs:
                self.cyl("Bld_Bark", top, l, 9.0, 5.0, sides=5, grain="ring")
            cz = th + height * 0.3
            centres = [(lean[0], lean[1], cz + height * 0.12, 1.0)]
            for k in range(blobs - 1):
                a = 2 * math.pi * k / (blobs - 1) + self.U(-0.3, 0.3)
                centres.append((lean[0] + math.cos(a) * spread * 0.4, lean[1] + math.sin(a) * spread * 0.4, cz + self.U(-0.06, 0.06) * height, self.U(0.66, 0.84)))
            for cx, cy, cz2, f in centres:
                s = spread * f
                c = (cx, cy, cz2)
                self.blob("Bld_LeafCore", c, (s, s, s * 0.7), points=12, flat=False, squash=0.3)
                # masked shell: a slightly larger lump whose gaps show the dark core
                self.blob("Bld_Leaves", c, (s * 1.14, s * 1.14, s * 0.82), points=11, flat=False, squash=0.3, w=0.25)

    def sack(self, pos, scale=1.0, yaw=0.0, slot="Bld_Thatch"):
        s = scale
        with self.at(pos, yaw):
            self.blob(slot, (0, 0, 14 * s), (46 * s, 34 * s, 34 * s), points=10, flat=True, squash=0.4)

    def wheel(self, centre, radius=34.0, thick=8.0, axis="y", sides=10):
        """A solid plank wheel with a bronze hub, standing on its rim."""
        c = V3(centre)
        a = Vector((0, 1, 0)) if axis == "y" else Vector((1, 0, 0))
        self.cyl("Bld_Planks", c - a * thick / 2, c + a * thick / 2, radius, sides=sides, grain="ring")
        self.cyl("Bld_Bronze", c - a * (thick / 2 + 3), c + a * (thick / 2 + 3), radius * 0.24, sides=6, grain="ring")

    def ladder(self, foot, top, width=36.0, rungs=6):
        a, b = V3(foot), V3(top)
        side = (b - a).cross(Vector((0, 0, 1)))
        if side.length < 1e-6:
            side = Vector((0, 1, 0))
        side.normalize()
        for s in (-1, 1):
            self.cyl("Bld_Beam", a + side * s * width / 2, b + side * s * width / 2, 3.5, sides=4)
        for k in range(rungs):
            f = (k + 0.7) / (rungs + 0.4)
            p = a.lerp(b, f)
            self.cyl("Bld_Beam", p - side * (width / 2 + 3), p + side * (width / 2 + 3), 2.6, sides=4)

    def rope(self, a, b, r=2.0):
        self.cyl("Bld_Thatch", a, b, r, sides=4)

    # ------------------------------------------------------------------ output
    def collider(self, lo, hi, yaw=0.0):
        self.colliders.append({"centre": [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2],
                               "size": [hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]], "yaw": yaw})

    def build_object(self, team=(0.05, 0.22, 0.80)):
        slots = []
        for f in self.faces:
            if f[0] not in slots:
                slots.append(f[0])
        me = bpy.data.meshes.new(self.name)
        bm = bmesh.new()
        uv0 = bm.loops.layers.uv.new("UV0")
        uv1 = bm.loops.layers.uv.new("UV1")
        col = bm.loops.layers.float_color.new("Col")
        for slot, P, uvs, ws, shade in self.faces:
            verts = [bm.verts.new((p.x / 100.0, -p.y / 100.0, p.z / 100.0)) for p in P]
            verts.reverse()                                   # y is mirrored: flip the winding
            try:
                face = bm.faces.new(verts)
            except ValueError:
                continue
            face.material_index = slots.index(slot)
            face.smooth = False
            for loop, (u, v), w in zip(face.loops, reversed(uvs), reversed(ws)):
                loop[uv0].uv = (u, 1.0 - v)                    # the glTF exporter writes (u, 1 - v)
                loop[uv1].uv = (w, 0.0)
                loop[col] = (shade, shade, shade, 1.0)
        bm.to_mesh(me)
        bm.free()
        for s in slots:
            me.materials.append(make_material(s, team))
        ob = bpy.data.objects.new(self.name, me)
        bpy.context.scene.collection.objects.link(ob)
        me.color_attributes.active_color = me.color_attributes["Col"]
        me.color_attributes.render_color_index = 0
        me.uv_layers.active = me.uv_layers["UV0"]
        return ob

    def stats(self):
        tris = sum(len(f[1]) - 2 for f in self.faces)
        P = [p for f in self.faces for p in f[1]]
        lo = [min(p[i] for p in P) for i in range(3)]
        hi = [max(p[i] for p in P) for i in range(3)]
        return tris, lo, hi


# ---------------------------------------------------------------------- Blender preview materials
def make_material(slot, team=(0.05, 0.22, 0.80)):
    """A Blender material that previews the Unreal one: nearest-sampled texture at 4 cm per texel from the
    cm UVs, team tint / glow through the alpha mask, alpha holes on the card slots."""
    if slot in bpy.data.materials:
        return bpy.data.materials[slot]
    tex_name, kind = MATERIALS[slot]
    m = bpy.data.materials.new(slot)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 0.85
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.15
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    path = os.path.join(TEX_DIR, tex_name + ".png")
    img = bpy.data.images.load(path, check_existing=True)
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.interpolation = "Closest"
    tex.extension = "REPEAT"
    uv = nt.nodes.new("ShaderNodeUVMap")
    uv.uv_map = "UV0"
    mp = nt.nodes.new("ShaderNodeMapping")
    sx, sy = 1.0 / (img.size[0] * TEXEL), 1.0 / (img.size[1] * TEXEL)
    mp.inputs["Scale"].default_value = (sx, sy, 1.0)
    mp.inputs["Location"].default_value = (0.0, 1.0 - sy, 0.0)       # uv.y holds 1 - v_cm
    nt.links.new(uv.outputs[0], mp.inputs[0])
    nt.links.new(mp.outputs[0], tex.inputs[0])
    colour = tex.outputs["Color"]
    vc = nt.nodes.new("ShaderNodeVertexColor")
    vc.layer_name = "Col"
    mul = nt.nodes.new("ShaderNodeMix"); mul.data_type = "RGBA"; mul.blend_type = "MULTIPLY"
    mul.inputs[0].default_value = 1.0
    nt.links.new(colour, mul.inputs[6]); nt.links.new(vc.outputs["Color"], mul.inputs[7])
    colour = mul.outputs[2]
    if "team" in kind or "glow" in kind:
        # mask = texels with alpha about 0.6
        a = nt.nodes.new("ShaderNodeMath"); a.operation = "COMPARE"
        a.inputs[1].default_value = 0.6; a.inputs[2].default_value = 0.12
        nt.links.new(tex.outputs["Alpha"], a.inputs[0])
        if "team" in kind:
            tint = nt.nodes.new("ShaderNodeMix"); tint.data_type = "RGBA"; tint.blend_type = "MULTIPLY"
            tint.inputs[7].default_value = (team[0] * 2, team[1] * 2, team[2] * 2, 1.0)
            nt.links.new(a.outputs[0], tint.inputs[0]); nt.links.new(colour, tint.inputs[6])
            colour = tint.outputs[2]
        else:
            em = nt.nodes.new("ShaderNodeMix"); em.data_type = "RGBA"
            em.inputs[6].default_value = (0, 0, 0, 1)
            nt.links.new(a.outputs[0], em.inputs[0]); nt.links.new(tex.outputs["Color"], em.inputs[7])
            nt.links.new(em.outputs[2], bsdf.inputs["Emission Color"])
            bsdf.inputs["Emission Strength"].default_value = 3.0 if slot != "Bld_Flame" else 0.0
    if slot == "Bld_Flame":
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = 6.0
    nt.links.new(colour, bsdf.inputs["Base Color"])
    if "card" in kind:
        gt = nt.nodes.new("ShaderNodeMath"); gt.operation = "GREATER_THAN"; gt.inputs[1].default_value = 0.3
        nt.links.new(tex.outputs["Alpha"], gt.inputs[0])
        nt.links.new(gt.outputs[0], bsdf.inputs["Alpha"])
        m.use_backface_culling = False
        if hasattr(m, "surface_render_method"):
            m.surface_render_method = "DITHERED"
        if hasattr(m, "blend_method"):
            m.blend_method = "CLIP"
    else:
        m.use_backface_culling = True                        # as in the game: an inside-out face must show as a hole
    if slot == "Bld_Dark":
        bsdf.inputs["Roughness"].default_value = 1.0
    return m


# ---------------------------------------------------------------------- scene, preview, export
def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return bpy.context.scene


def setup_preview(scene, focus=(0.0, 0.0, 0.0), zoom=0.5, ground=3000.0, res=(1920, 1080), yaw=0.0):
    """The game camera (Docs/VISUAL_CONTRACT.md: yaw 0, FOV 50, pitch -30..-46, distance 950..3600 geometric)
    and the game's sun, so a render shows roughly what the building will look like in the level.
    `yaw` turns the BUILDING's parent empty, as the level will place it."""
    dist = 950.0 * (3600.0 / 950.0) ** zoom
    pitch = 30.0 + 16.0 * zoom
    f = V3(focus)
    cam_d = bpy.data.cameras.get("GameCamera") or bpy.data.cameras.new("GameCamera")
    cam_d.sensor_fit = "HORIZONTAL"
    cam_d.angle = math.radians(50.0)
    cam_d.clip_start, cam_d.clip_end = 0.5, 500.0
    cam = bpy.data.objects.get("GameCamera")
    if cam is None:
        cam = bpy.data.objects.new("GameCamera", cam_d)
        scene.collection.objects.link(cam)
    p = math.radians(pitch)
    look = Vector((math.cos(p), 0.0, -math.sin(p)))                  # UE: along +X, downward. Blender x = UE x
    pos = Vector((f.x, -f.y, f.z)) / 100.0 - look * dist / 100.0
    cam.location = pos
    cam.rotation_euler = (-look).to_track_quat("Z", "Y").to_euler()
    scene.camera = cam
    if "GameSun" not in bpy.data.objects:
        sd = bpy.data.lights.new("GameSun", "SUN")
        sd.energy = 5.0
        sd.color = (1.0, 0.82, 0.62)
        sd.angle = math.radians(1.8)
        sun = bpy.data.objects.new("GameSun", sd)
        scene.collection.objects.link(sun)
        travel = Vector((0.22, -0.81, -0.54))                         # UE (0.22, 0.81, -0.54), y negated
        sun.rotation_euler = (-travel.normalized()).to_track_quat("Z", "Y").to_euler()
        world = bpy.data.worlds.new("GameSky")
        scene.world = world
        world.use_nodes = True
        bg = world.node_tree.nodes.get("Background")
        bg.inputs[0].default_value = (0.42, 0.55, 0.85, 1.0)
        bg.inputs[1].default_value = 0.55
        # turf under the building, in the terrain's world-aligned frame
        g = Kit("PreviewGround")
        h = ground
        g.faces.append(("Ground", [Vector((-h, -h, 0)), Vector((h, -h, 0)), Vector((h, h, 0)), Vector((-h, h, 0))],
                        [(-h, h), (-h, -h), (h, -h), (h, h)], [NO_TOP] * 4, 1.0))
        MATERIALS["Ground"] = ("T_Grass", "opaque")
        gob = g.build_object()
        gob.hide_select = True
    r = scene.render
    r.engine = "BLENDER_EEVEE"
    r.resolution_x, r.resolution_y = res
    r.film_transparent = False
    r.image_settings.file_format = "PNG"
    ee = scene.eevee
    ee.taa_render_samples = 16
    for attr, val in (("use_shadows", True), ("use_raytracing", True), ("use_gtao", True)):
        if hasattr(ee, attr):
            try:
                setattr(ee, attr, val)
            except Exception:
                pass
    try:
        scene.view_settings.view_transform = "Standard"
    except Exception:
        pass
    return cam


def render(scene, path):
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("rendered", path)


def troop_standin(pos, team=(0.05, 0.22, 0.80)):
    """A 1.4 m figure-sized block for scale in previews (never exported)."""
    k = Kit("ScaleFigure")
    MATERIALS["Figure"] = ("T_Bld_Awning", "card team")
    x, y = pos
    k.obox("Figure", (x, y, 50), (36, 50, 100))
    k.obox("Figure", (x, y, 120), (30, 30, 40))
    return k.build_object(team)


def export_gltf(ob, path):
    for o in bpy.context.scene.objects:
        o.select_set(o is ob)
    bpy.context.view_layer.objects.active = ob
    kw = dict(filepath=path, export_format="GLTF_SEPARATE", use_selection=True, export_apply=True, export_yup=True,
              export_texcoords=True, export_normals=True, export_materials="EXPORT", export_image_format="NONE",
              export_animations=False, export_skins=False, export_morph=False, export_cameras=False, export_lights=False)
    try:
        bpy.ops.export_scene.gltf(export_vertex_color="ACTIVE", export_all_vertex_colors=False, **kw)
    except TypeError:
        bpy.ops.export_scene.gltf(**kw)
    print("exported", path)
