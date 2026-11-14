"""Sovereign Realms character kit for Blender (bpy): scripted modelling, rigging and posing.

Conventions
-----------
* Units are metres. The character stands on z = 0, faces -Y, its left side is +X.
* A character is ONE mesh, rigidly skinned: every primitive is bound to exactly one bone.
* All rotations given to the posing API are expressed in the armature's rest axes
  (x = character left, y = back, z = up), not in Blender's per-bone axes, so
  E(10, 0, 0) on the spine always means "lean forward ten degrees".
"""

import math

import bmesh
import bpy
from mathutils import Matrix, Quaternion, Vector

import srmats

# --------------------------------------------------------------------------- maths

def V(*a):
    if len(a) == 1:
        return Vector(a[0])
    return Vector(a)


def E(rx=0.0, ry=0.0, rz=0.0):
    """Rotation from degrees about the armature axes: twist (z) applied last, then pitch (x), then roll (y)."""
    q = (Matrix.Rotation(math.radians(rz), 3, "Z")
         @ Matrix.Rotation(math.radians(rx), 3, "X")
         @ Matrix.Rotation(math.radians(ry), 3, "Y")).to_quaternion()
    return q


def aim(d, s, d0=(0, -1, 0), s0=(0, 0, 1)):
    """Rotation that takes rest direction d0 to d and rest secondary direction s0 as close to s as possible."""
    def frame(a, b):
        a = Vector(a).normalized()
        b = Vector(b)
        b = (b - a * b.dot(a))
        if b.length < 1e-6:
            b = a.orthogonal()
        b.normalize()
        c = a.cross(b)
        return Matrix((a, b, c)).transposed()
    return (frame(d, s) @ frame(d0, s0).transposed()).to_quaternion()


def lerp(a, b, t):
    return a + (b - a) * t


def smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def rot_m(rx=0.0, ry=0.0, rz=0.0):
    return E(rx, ry, rz).to_matrix().to_4x4()


def place(pos=(0, 0, 0), rx=0.0, ry=0.0, rz=0.0, scale=(1, 1, 1)):
    m = Matrix.Translation(Vector(pos)) @ rot_m(rx, ry, rz)
    if scale != (1, 1, 1):
        m = m @ Matrix.Diagonal((scale[0], scale[1], scale[2], 1.0))
    return m


def _basis(axis, up=None):
    z = Vector(axis).normalized()
    up = Vector(up) if up is not None else Vector((0, 0, 1))
    if abs(z.dot(up)) > 0.995:
        up = Vector((0, 1, 0)) if abs(z.y) < 0.9 else Vector((1, 0, 0))
    x = up.cross(z).normalized()
    y = z.cross(x)
    return x, y, z


# --------------------------------------------------------------------------- primitives
# Every primitive returns (verts, faces). Rings run counter-clockwise seen from the
# direction the rows advance in; normals are recalculated at the end anyway.

def grid_surface(rows, cap_start=True, cap_end=True, wrap=False):
    """rows: list of rings (lists of Vectors) or single Vectors (poles). wrap joins the last row to the first."""
    verts, faces, index = [], [], []
    for r in rows:
        if isinstance(r, Vector):
            index.append([len(verts)])
            verts.append(r)
        else:
            index.append(list(range(len(verts), len(verts) + len(r))))
            verts.extend(r)
    pairs = list(zip(index[:-1], index[1:]))
    if wrap:
        pairs.append((index[-1], index[0]))
        cap_start = cap_end = False
    for a, b in pairs:
        if len(a) == 1 and len(b) == 1:
            continue
        if len(a) == 1:
            n = len(b)
            for j in range(n):
                faces.append([a[0], b[(j + 1) % n], b[j]])
        elif len(b) == 1:
            n = len(a)
            for j in range(n):
                faces.append([a[j], a[(j + 1) % n], b[0]])
        else:
            n = len(a)
            for j in range(n):
                faces.append([a[j], a[(j + 1) % n], b[(j + 1) % n], b[j]])
    if cap_start and len(index[0]) > 2:
        faces.append(list(reversed(index[0])))
    if cap_end and len(index[-1]) > 2:
        faces.append(list(index[-1]))
    return verts, faces


def ellipsoid(r=(1, 1, 1), seg=16, rings=10, e1=1.0, e2=1.0):
    """Ellipsoid, or a rounded box when e1 / e2 < 1 (superellipsoid exponents)."""
    def c(w, e):
        v = math.cos(w)
        return math.copysign(abs(v) ** e, v)

    def s(w, e):
        v = math.sin(w)
        return math.copysign(abs(v) ** e, v)

    rows = [Vector((0, 0, -r[2]))]
    for i in range(1, rings):
        v = -math.pi / 2 + math.pi * i / rings
        rows.append([Vector((r[0] * c(v, e1) * c(u, e2), r[1] * c(v, e1) * s(u, e2), r[2] * s(v, e1)))
                     for u in (2 * math.pi * j / seg for j in range(seg))])
    rows.append(Vector((0, 0, r[2])))
    return grid_surface(rows)


def capsule(p0, p1, r0, r1=None, seg=12, caps=3, squash=(1, 1), up=None):
    """Tapered limb from p0 to p1 with rounded ends. squash scales the section along its (x, y) axes."""
    r1 = r0 if r1 is None else r1
    p0, p1 = Vector(p0), Vector(p1)
    x, y, z = _basis(p1 - p0, up)

    def ring(c, r):
        return [c + (x * math.cos(u) * squash[0] + y * math.sin(u) * squash[1]) * r
                for u in (2 * math.pi * j / seg for j in range(seg))]

    rows = [p0 - z * r0 * min(squash)]
    for i in range(1, caps + 1):
        a = math.pi / 2 * (1 - i / caps)
        rows.append(ring(p0 - z * r0 * math.sin(a) * min(squash), r0 * math.cos(a)))
    for i in range(caps, -1, -1):
        a = math.pi / 2 * (1 - i / caps)
        if i == caps:
            rows.append(ring(p1, r1))
        else:
            rows.append(ring(p1 + z * r1 * math.sin(a) * min(squash), r1 * math.cos(a)))
    rows[-1] = p1 + z * r1 * min(squash)
    return grid_surface(rows)


def lathe(profile, seg=20, sx=1.0, sy=1.0, arc=None, thick=0.0, wrap=False):
    """Surface of revolution about +Z. profile = [(radius, z), ...] bottom to top or any order.
    arc=(a0, a1) in degrees with thick > 0 gives a closed shell segment instead of a full turn
    (0 degrees is +X, 90 is +Y, so the front of a character is around 270)."""
    rows = []
    if arc is None:
        for r, z in profile:
            if r < 1e-6:
                rows.append(Vector((0, 0, z)))
            else:
                rows.append([Vector((r * sx * math.cos(u), r * sy * math.sin(u), z))
                             for u in (2 * math.pi * j / seg for j in range(seg))])
        return grid_surface(rows, wrap=wrap)
    a0, a1 = math.radians(arc[0]), math.radians(arc[1])
    for r, z in profile:
        outer = [Vector((r * sx * math.cos(u), r * sy * math.sin(u), z))
                 for u in (a0 + (a1 - a0) * j / seg for j in range(seg + 1))]
        ri = max(r - thick, 1e-4)
        inner = [Vector((ri * sx * math.cos(u), ri * sy * math.sin(u), z))
                 for u in (a0 + (a1 - a0) * j / seg for j in range(seg + 1))]
        rows.append(outer + list(reversed(inner)))
    return grid_surface(rows)


def tube(points, radii, seg=8, squash=(1, 1), up=None, twist=0.0):
    """Sweep a (squashed) circle along a polyline. radii is a number or one per point."""
    pts = [Vector(p) for p in points]
    if not isinstance(radii, (list, tuple)):
        radii = [radii] * len(pts)
    tangents = []
    for i in range(len(pts)):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        tangents.append((b - a).normalized())
    x, y, z = _basis(tangents[0], up)
    rows = []
    for i, (p, t, r) in enumerate(zip(pts, tangents, radii)):
        # parallel transport of the frame
        x = (x - t * x.dot(t))
        if x.length < 1e-6:
            x = t.orthogonal()
        x.normalize()
        y = t.cross(x)
        if r < 1e-6:
            rows.append(p.copy())
            continue
        tw = twist * i / max(len(pts) - 1, 1)
        rows.append([p + (x * math.cos(u + tw) * squash[0] + y * math.sin(u + tw) * squash[1]) * r
                     for u in (2 * math.pi * j / seg for j in range(seg))])
    return grid_surface(rows)


def sheet(grid, thick):
    """Closed slab from a grid of points [row][col] (rows advance along the sheet)."""
    nr, nc = len(grid), len(grid[0])
    g = [[Vector(p) for p in row] for row in grid]
    rows = []
    for i in range(nr):
        outer, inner = [], []
        for j in range(nc):
            du = g[i][min(j + 1, nc - 1)] - g[i][max(j - 1, 0)]
            dv = g[min(i + 1, nr - 1)][j] - g[max(i - 1, 0)][j]
            n = du.cross(dv)
            n = n.normalized() if n.length > 1e-9 else Vector((0, 0, 1))
            outer.append(g[i][j] + n * thick * 0.5)
            inner.append(g[i][j] - n * thick * 0.5)
        rows.append(outer + list(reversed(inner)))
    return grid_surface(rows)


def bezier(p0, p1, p2, p3, n):
    p0, p1, p2, p3 = (Vector(p) for p in (p0, p1, p2, p3))
    out = []
    for i in range(n + 1):
        t = i / n
        out.append(p0 * (1 - t) ** 3 + p1 * 3 * t * (1 - t) ** 2 + p2 * 3 * t * t * (1 - t) + p3 * t ** 3)
    return out


# --------------------------------------------------------------------------- mesh builder

class Builder:
    """Collects primitives; every primitive is bound to one bone and one material."""

    def __init__(self, name):
        self.name = name
        self.verts, self.faces = [], []
        self.fmat, self.fsmooth, self.vbone = [], [], []
        self.mat_names = []

    def _mat(self, name):
        if name not in srmats.BY_NAME:
            raise KeyError("unknown material " + name)
        if name not in self.mat_names:
            self.mat_names.append(name)
        return self.mat_names.index(name)

    def add(self, prim, mat, bone, M=None, smooth=True, mirror=False):
        """Add a primitive. mirror=True adds the X-mirrored copy as well, bound to the .R twin of a .L bone."""
        verts, faces = prim
        self._add(verts, faces, mat, bone, M, smooth)
        if mirror:
            mm = Matrix.Diagonal((-1, 1, 1, 1))
            mbone = bone[:-2] + ".R" if bone.endswith(".L") else bone
            self._add(verts, faces, mat, mbone, (mm @ M) if M is not None else mm, smooth)

    def _add(self, verts, faces, mat, bone, M, smooth):
        base = len(self.verts)
        mi = self._mat(mat)
        for v in verts:
            pv = (M @ v) if M is not None else v
            self.verts.append(tuple(pv))
            self.vbone.append(bone(pv) if callable(bone) else bone)
        for f in faces:
            self.faces.append([base + i for i in f])
            self.fmat.append(mi)
            self.fsmooth.append(smooth)

    def build(self, armature_obj, collection):
        me = bpy.data.meshes.new(self.name + "_mesh")
        me.from_pydata(self.verts, [], self.faces)
        me.update()
        for n in self.mat_names:
            me.materials.append(get_material(n))
        me.polygons.foreach_set("material_index", self.fmat)
        me.polygons.foreach_set("use_smooth", self.fsmooth)
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(self.name, me)
        collection.objects.link(ob)
        groups = {}
        for i, b in enumerate(self.vbone):
            groups.setdefault(b, []).append(i)
        bone_names = {b.name for b in armature_obj.data.bones}
        for b, idx in groups.items():
            if b not in bone_names:
                raise KeyError("primitive bound to unknown bone " + b)
            ob.vertex_groups.new(name=b).add(idx, 1.0, "REPLACE")
        mod = ob.modifiers.new("Armature", "ARMATURE")
        mod.object = armature_obj
        ob.parent = armature_obj
        return ob


# --------------------------------------------------------------------------- materials

def get_material(name):
    full = "SR_" + name
    m = bpy.data.materials.get(full)
    if m:
        return m
    d = srmats.BY_NAME[name]
    m = bpy.data.materials.new(full)
    m.use_nodes = True
    rgb = [srmats.srgb_to_linear(c) for c in srmats.hex_to_rgb(d["base"])]
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = d["rough"]
    bsdf.inputs["Metallic"].default_value = d["metal"]
    m.diffuse_color = (*rgb, 1.0)
    m.roughness = d["rough"]
    m.metallic = d["metal"]
    m["sr_id"] = d["id"]
    m["sr_team"] = bool(d["team"])
    return m


# --------------------------------------------------------------------------- rig

# name: (head, tail, parent, deform). Filled per character from a proportions dict.
def humanoid_bones(P):
    """Bone table for a stocky humanoid. P holds joint positions (left side, mirrored for the right)."""
    hip, knee, ankle = Vector(P["hip"]), Vector(P["knee"]), Vector(P["ankle"])
    sh, el, wr = Vector(P["shoulder"]), Vector(P["elbow"]), Vector(P["wrist"])
    toe = Vector((ankle.x, ankle.y - P["foot_len"], 0.02))
    hand_tail = wr + (wr - el).normalized() * 0.10
    B = [
        ("root", (0, 0, 0), (0, 0.15, 0), None, True),
        ("hips", (0, 0, P["pelvis"]), (0, 0, P["waist"]), "root", True),
        ("spine", (0, 0, P["waist"]), (0, 0, P["chest"]), "hips", True),
        ("chest", (0, 0, P["chest"]), (0, 0, P["neck"]), "spine", True),
        ("head", (0, 0, P["neck"]), (0, 0, P["neck"] + 0.30), "chest", True),
    ]
    for side, sx in ((".L", 1), (".R", -1)):
        def m(v):
            return (v.x * sx, v.y, v.z)
        B += [
            ("upper_leg" + side, m(hip), m(knee), "hips", True),
            ("lower_leg" + side, m(knee), m(ankle), "upper_leg" + side, True),
            ("foot" + side, m(ankle), m(toe), "lower_leg" + side, True),
            ("upper_arm" + side, m(sh), m(el), "chest", True),
            ("lower_arm" + side, m(el), m(wr), "upper_arm" + side, True),
            ("hand" + side, m(wr), m(hand_tail), "lower_arm" + side, True),
            # controls
            ("ik_foot" + side, m(ankle), m(toe), "root", False),
            ("pole_knee" + side, m(Vector((knee.x, knee.y - 1.0, knee.z))),
             m(Vector((knee.x, knee.y - 1.1, knee.z))), "root", False),
            ("ik_hand" + side, m(wr), m(hand_tail), "chest", False),
            ("pole_elbow" + side, m(Vector((el.x + 0.25, el.y + 0.9, el.z - 0.2))),
             m(Vector((el.x + 0.25, el.y + 1.0, el.z - 0.2))), "chest", False),
        ]
    return B


def _signed_angle(u, v, normal):
    a = u.angle(v)
    if u.cross(v).angle(normal) < 1:
        a = -a
    return a


def _pole_angle(base, ik, pole_loc):
    pole_normal = (ik.tail_local - base.head_local).cross(pole_loc - base.head_local)
    projected = pole_normal.cross(base.tail_local - base.head_local)
    return _signed_angle(base.x_axis_arm, projected, base.tail_local - base.head_local)


class Rig:
    def __init__(self, name, bones, collection):
        self.name = name
        arm = bpy.data.armatures.new(name + "_rig")
        ob = bpy.data.objects.new(name + "_armature", arm)
        collection.objects.link(ob)
        bpy.context.view_layer.objects.active = ob
        ob.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        for bname, head, tail, parent, deform in bones:
            eb = arm.edit_bones.new(bname)
            eb.head, eb.tail = Vector(head), Vector(tail)
            eb.roll = 0.0
            eb.use_deform = deform
            if parent:
                eb.parent = arm.edit_bones[parent]
        bpy.ops.object.mode_set(mode="OBJECT")
        self.ob = ob
        self.rest = {b.name: b.matrix_local.copy() for b in arm.bones}
        self.rest3 = {k: m.to_3x3() for k, m in self.rest.items()}
        self.rest_head = {b.name: b.head_local.copy() for b in arm.bones}
        self.parent = {b.name: (b.parent.name if b.parent else None) for b in arm.bones}
        for pb in ob.pose.bones:
            pb.rotation_mode = "QUATERNION"
        self.detach = {}      # prop bone -> constraint name
        self._limb_ik()
        ob.animation_data_create()
        self.actions = {}
        self.action = None

    # -- constraints
    def _limb_ik(self):
        pb, bones = self.ob.pose.bones, self.ob.data.bones

        class _B:
            def __init__(s, b):
                s.head_local, s.tail_local = b.head_local, b.tail_local
                s.x_axis_arm = b.matrix_local.to_3x3().col[0].copy()

        for side in (".L", ".R"):
            for upper, lower, end, target, pole in (
                    ("upper_leg", "lower_leg", "foot", "ik_foot", "pole_knee"),
                    ("upper_arm", "lower_arm", "hand", "ik_hand", "pole_elbow")):
                c = pb[lower + side].constraints.new("IK")
                c.name = "IK"
                c.target = self.ob
                c.subtarget = target + side
                c.pole_target = self.ob
                c.pole_subtarget = pole + side
                c.pole_angle = _pole_angle(_B(bones[upper + side]), _B(bones[lower + side]),
                                           bones[pole + side].head_local)
                c.chain_count = 2
                c.use_stretch = False
                c.iterations = 200
                r = pb[end + side].constraints.new("COPY_ROTATION")
                r.name = "Follow"
                r.target = self.ob
                r.subtarget = target + side

    def attach_prop(self, prop_bone, socket_bone):
        """prop_bone (child of root, same rest matrix as socket_bone) follows socket_bone while influence = 1."""
        c = self.ob.pose.bones[prop_bone].constraints.new("COPY_TRANSFORMS")
        c.name = "Grip"
        c.target = self.ob
        c.subtarget = socket_bone
        self.detach[prop_bone] = "Grip"

    # -- actions and keys
    def new_action(self, name, frames, loop=False, **props):
        act = bpy.data.actions.new(name)
        act.use_fake_user = True
        act["sr_frames"] = frames
        act["sr_loop"] = loop
        for k, v in props.items():
            act["sr_" + k] = v
        self.reset_pose()
        self.ob.animation_data.action = act
        self.actions[name] = act
        self.action = act
        return act

    def reset_pose(self):
        for pb in self.ob.pose.bones:
            pb.matrix_basis = Matrix.Identity(4)
            if pb.name in self.detach:
                pb.constraints[self.detach[pb.name]].influence = 1.0

    def key_all(self, poses):
        for i, p in enumerate(poses):
            self.key(p, i)

    def key(self, pose, frame):
        """pose: {bone: {'rot': Quaternion, 'loc': delta xyz, 'pos': absolute rest-space xyz, 'scale': s, 'free': 0/1}}"""
        pbs = self.ob.pose.bones
        for name, spec in pose.items():
            pb = pbs[name]
            B = self.rest3[name]
            Bi = B.inverted()
            loc = Vector((0, 0, 0))
            if "pos" in spec:
                loc = Vector(spec["pos"]) - self.rest_head[name]
            if "loc" in spec:
                loc = loc + Vector(spec["loc"])
            q = spec.get("rot", Quaternion())
            pb.location = Bi @ loc
            pb.rotation_quaternion = (Bi @ q.to_matrix() @ B).to_quaternion()
            s = spec.get("scale", 1.0)
            pb.scale = (s, s, s) if not isinstance(s, (tuple, list)) else s
            pb.keyframe_insert("location", frame=frame)
            pb.keyframe_insert("rotation_quaternion", frame=frame)
            pb.keyframe_insert("scale", frame=frame)
            if name in self.detach:
                c = pb.constraints[self.detach[name]]
                c.influence = 0.0 if spec.get("free", 0) else 1.0
                c.keyframe_insert("influence", frame=frame)

    def bone_matrix(self, bone, frame):
        """Evaluated armature-space matrix of a bone at a frame of the current action."""
        bpy.context.scene.frame_set(frame)
        bpy.context.view_layer.update()
        return self.ob.pose.bones[bone].matrix.copy()

    def finish_actions(self):
        """Constant interpolation is wrong for the FBX; keep Blender's default bezier but make loops cyclic-safe."""
        self.reset_pose()
        self.ob.animation_data.action = None


def pose_merge(base, *overrides):
    out = {k: dict(v) for k, v in base.items()}
    for o in overrides:
        for k, v in o.items():
            out.setdefault(k, {}).update(v)
    return out


def pose_lerp(a, b, t):
    """Blend two complete poses (same bones). Positions lerp, rotations slerp."""
    out = {}
    for k in a:
        sa, sb = a[k], b.get(k, a[k])
        d = {}
        for key in set(sa) | set(sb):
            va, vb = sa.get(key), sb.get(key)
            if va is None:
                va = Quaternion() if key == "rot" else ((0, 0, 0) if key in ("loc",) else vb)
            if vb is None:
                vb = Quaternion() if key == "rot" else ((0, 0, 0) if key in ("loc",) else va)
            if key == "rot":
                d[key] = va.slerp(vb, t)
            elif key in ("pos", "loc"):
                d[key] = tuple(Vector(va).lerp(Vector(vb), t))
            elif key == "scale":
                d[key] = va + (vb - va) * t
            else:
                d[key] = va if t < 0.5 else vb
        out[k] = d
    return out


# --------------------------------------------------------------------------- scene

def new_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 1.0
    sc.render.fps = 12
    col = bpy.data.collections.new("Character")
    sc.collection.children.link(col)
    return sc, col
