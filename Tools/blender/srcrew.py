"""A light human figure that can share an armature with something else: the horseman's rider, the catapult's crew.

Same build as the workers (132 cm, stocky, big head and fists). A Fig has a bone-name prefix and an origin, so
several can live in one rig (srkit.humanoid_bones(prefix=..., origin=...), Rig(ik_prefixes=...)).

All positions given to Fig.pose are in the figure's own space (feet at the origin, facing -Y, left = +X) plus the
optional `at` offset; they are expressed in the rest frame of the bone the figure hangs from, so a rider posed
this way is carried by his mount for free.
"""

import math

from mathutils import Matrix, Quaternion, Vector

import srkit as K
from srkit import E, V, aim, capsule, ellipsoid, lathe, place, sheet, tube  # noqa: F401

BODY_HEIGHT_CM = 132.0

P = dict(
    pelvis=0.52, waist=0.62, chest=0.77, neck=0.955,
    hip=(0.092, 0.0, 0.545), knee=(0.108, -0.028, 0.305), ankle=(0.12, 0.0, 0.085), foot_len=0.17,
    shoulder=(0.225, 0.0, 0.885), elbow=(0.262, 0.032, 0.705), wrist=(0.275, -0.005, 0.545),
)
FIST_L = Vector((0.2775, -0.012, 0.487))
FIST_R = Vector((-FIST_L.x, FIST_L.y, FIST_L.z))
WRIST_L = Vector(P["wrist"])
WRIST_R = Vector((-WRIST_L.x, WRIST_L.y, WRIST_L.z))
MIRROR = Matrix.Diagonal((-1, 1, 1, 1))


class Fig:
    def __init__(self, prefix="", origin=(0, 0, 0), root="root"):
        self.pre, self.O, self.root = prefix, Vector(origin), root
        self.T = Matrix.Translation(self.O)

    def n(self, bone):
        return self.pre + bone

    def bones(self, add_root=False):
        return K.humanoid_bones(P, prefix=self.pre, root=self.root, origin=tuple(self.O), add_root=add_root)

    def control_names(self):
        return [self.pre + b for b in ("hips", "spine", "chest", "head", "ik_foot.L", "ik_foot.R", "pole_knee.L",
                                       "pole_knee.R", "ik_hand.L", "ik_hand.R", "pole_elbow.L", "pole_elbow.R")]

    # ------------------------------------------------------------------------------------------- mesh
    def add(self, b, prim, mat, bone, M=None, mirror=False, smooth=True):
        M = M if M is not None else Matrix.Identity(4)
        b.add(prim, mat, self.pre + bone, self.T @ M, smooth)
        if mirror:
            mb = bone[:-2] + ".R" if bone.endswith(".L") else bone
            b.add(prim, mat, self.pre + mb, self.T @ MIRROR @ M, smooth)

    def build(self, b, style="crew", beard="beard"):
        """style 'crew': team headcloth, long tunic with a team hem, bare forearms.
        style 'rider': bronze cap with a team crest, leather jerkin, short tunic (it sits on a horse)."""
        rider = style == "rider"
        a = lambda prim, mat, bone, M=None, mirror=False: self.add(b, prim, mat, bone, M, mirror)  # noqa: E731
        hip, knee, ankle = V(P["hip"]), V(P["knee"]), V(P["ankle"])
        a(capsule(hip, knee, 0.086, 0.072, seg=12), "skin", "upper_leg.L", mirror=True)
        a(capsule(knee, ankle + V(0, 0, 0.02), 0.072, 0.058, seg=12), "skin", "lower_leg.L", mirror=True)
        a(capsule(knee.lerp(ankle, 0.25), ankle + V(0, 0, 0.03), 0.076, 0.064, seg=12, caps=2), "leather",
          "lower_leg.L", mirror=True)
        a(ellipsoid((0.072, 0.072, 0.064), seg=12, rings=8), "leather", "foot.L", place(ankle + V(0, 0.008, -0.012)), mirror=True)
        a(ellipsoid((0.07, 0.124, 0.052), seg=12, rings=8, e1=0.7, e2=0.8), "leather", "foot.L",
          place(V(ankle.x, -0.058, 0.052)), mirror=True)
        a(ellipsoid((0.075, 0.13, 0.018), seg=12, rings=6, e1=0.5, e2=0.8), "leather_dark", "foot.L",
          place(V(ankle.x, -0.058, 0.016)), mirror=True)

        # tunic
        a(ellipsoid((0.16, 0.12, 0.095), seg=16, rings=8), "linen", "hips", place((0, 0, 0.56)))
        if rider:
            a(lathe([(0.0, 0.65), (0.165, 0.65), (0.19, 0.56), (0.205, 0.50), (0.0, 0.50)], seg=20, sy=0.8), "linen", "hips")
            a(lathe([(0.0, 0.505), (0.207, 0.505), (0.212, 0.47), (0.0, 0.465)], seg=20, sy=0.8), "team", "hips")
        else:
            a(lathe([(0.0, 0.65), (0.165, 0.65), (0.19, 0.56), (0.22, 0.45), (0.224, 0.42), (0.0, 0.42)], seg=20, sy=0.8), "linen", "hips")
            a(lathe([(0.0, 0.425), (0.225, 0.425), (0.232, 0.39), (0.226, 0.38), (0.0, 0.38)], seg=20, sy=0.8), "team", "hips")
            a(lathe([(0.0, 0.376), (0.226, 0.376), (0.0, 0.372)], seg=20, sy=0.8), "leather_dark", "hips")
        body = "leather" if rider else "linen"
        a(lathe([(0.0, 0.63), (0.17, 0.63), (0.176, 0.70), (0.186, 0.775), (0.0, 0.775)], seg=20, sy=0.74), body, "spine")
        a(lathe([(0.0, 0.765), (0.188, 0.765), (0.198, 0.84), (0.19, 0.9), (0.15, 0.94), (0.0, 0.95)], seg=20, sy=0.74), body, "chest")
        a(capsule((0, 0, 0.92), (0, -0.005, 1.0), 0.07, 0.066, seg=12), "skin", "chest")
        a(lathe([(0.0, 0.60), (0.176, 0.60), (0.184, 0.632), (0.176, 0.664), (0.0, 0.664)], seg=20, sy=0.78), "team", "hips")
        if rider:
            a(ellipsoid((0.05, 0.02, 0.05), seg=10, rings=6), "bronze", "chest", place((0, -0.142, 0.84)))
            a(tube([V(-0.15, -0.08, 0.93), V(0.0, -0.148, 0.84), V(0.15, -0.08, 0.93)], 0.018, seg=6), "leather_dark", "chest")
        else:
            a(sheet([[V(0.095, -0.12, 0.62), V(0.155, -0.10, 0.62)],
                     [V(0.10, -0.15, 0.53), V(0.168, -0.128, 0.53)]], 0.026), "team", "hips")

        # arms
        sh, el, wr = V(P["shoulder"]), V(P["elbow"]), V(P["wrist"])
        a(ellipsoid((0.086, 0.09, 0.075), seg=12, rings=8), "linen", "upper_arm.L", place(sh + V(0.004, 0, 0.012)), mirror=True)
        a(capsule(sh, el, 0.07, 0.064, seg=12), "linen", "upper_arm.L", mirror=True)
        a(capsule(el, wr, 0.058, 0.05, seg=12), "skin", "lower_arm.L", mirror=True)
        if rider:
            a(capsule(el.lerp(wr, 0.3), el.lerp(wr, 0.95), 0.064, 0.058, seg=12, caps=2), "leather", "lower_arm.L", mirror=True)
        fist = wr + (wr - el).normalized() * 0.058
        a(ellipsoid((0.07, 0.076, 0.073), seg=12, rings=8, e1=0.8, e2=0.85), "skin", "hand.L", place(fist), mirror=True)

        # head
        hz = 1.105
        a(ellipsoid((0.14, 0.148, 0.148), seg=18, rings=12), "skin", "head", place((0, -0.005, hz)))
        a(ellipsoid((0.036, 0.046, 0.046), seg=10, rings=6), "skin", "head", place((0, -0.152, hz - 0.02)))
        a(ellipsoid((0.026, 0.019, 0.021), seg=8, rings=6), "eye", "head", place((0.058, -0.136, hz + 0.012)), mirror=True)
        a(capsule((0.024, -0.148, hz + 0.036), (0.094, -0.126, hz + 0.046), 0.013, 0.011, seg=8, caps=2), "hair", "head", mirror=True)
        a(ellipsoid((0.13, 0.11, 0.07), seg=16, rings=8), beard, "head", place((0, -0.05, hz - 0.115), rx=-10))
        a(ellipsoid((0.15, 0.15, 0.12), seg=16, rings=8), "hair", "head", place((0, 0.02, hz + 0.03)))
        if rider:
            # bronze skullcap with a dark brow band and a team horsehair crest running front to back
            cap = place((0, 0.004, hz + 0.02), rx=-6)
            a(lathe([(0.0, 0.035), (0.158, 0.035), (0.162, 0.075), (0.146, 0.125), (0.1, 0.165), (0.04, 0.185), (0.0, 0.19)],
                    seg=22, sy=1.04), "bronze", "head", cap)
            a(lathe([(0.0, 0.02), (0.166, 0.02), (0.17, 0.045), (0.166, 0.07), (0.0, 0.07)], seg=22, sy=1.04), "bronze_dark", "head", cap)
            pts = K.bezier((0, -0.10, hz + 0.19), (0, -0.02, hz + 0.30), (0, 0.16, hz + 0.27), (0, 0.22, hz + 0.02), 7)
            a(tube(pts, [0.022, 0.04, 0.05, 0.054, 0.052, 0.046, 0.036, 0.014], seg=8, squash=(0.6, 1.0)), "team", "head")
        else:
            # team headcloth held by a dark cord, a short drape over the nape
            cap = place((0, 0.006, hz + 0.02), rx=-8)
            a(lathe([(0.0, 0.0), (0.158, 0.0), (0.164, 0.05), (0.15, 0.11), (0.1, 0.15), (0.0, 0.16)], seg=22, sy=1.04), "team", "head", cap)
            a(lathe([(0.0, 0.02), (0.168, 0.02), (0.17, 0.04), (0.166, 0.055), (0.0, 0.055)], seg=22, sy=1.04), "leather_dark", "head", cap)
            a(sheet([[V(-0.12, 0.10, hz + 0.04), V(0.0, 0.16, hz + 0.04), V(0.12, 0.10, hz + 0.04)],
                     [V(-0.13, 0.12, hz - 0.12), V(0.0, 0.185, hz - 0.12), V(0.13, 0.12, hz - 0.12)]], 0.03), "team", "head")

    # ------------------------------------------------------------------------------------------- posing
    def _delta(self, rig, bone, spec):
        h = rig.rest_head[bone]
        t = Vector(spec.get("loc", (0, 0, 0)))
        r = spec.get("rot", Quaternion()).to_matrix().to_4x4()
        return Matrix.Translation(h + t) @ r @ Matrix.Translation(-h)

    def chest_matrix(self, rig, pose):
        m = Matrix.Identity(4)
        for bname in ("hips", "spine", "chest"):
            m = m @ self._delta(rig, self.pre + bname, pose.get(self.pre + bname, {}))
        return m

    def pose(self, rig, hips, spine, chest, head, footL, footR, handL, handR, at=(0, 0, 0),
             kneeL=(0.2, -1.0, 0.3), kneeR=(-0.2, -1.0, 0.3), elbowL=(0.9, 0.5, 0.4), elbowR=(-0.9, 0.6, 0.5)):
        """hips = (loc, rot); spine / chest = rot; head = (yaw, pitch[, roll]) or a rotation; feet and hands =
        (pos, rot) with pos in figure space (+ at). Hand pos is the WRIST. Returns a pose dict with prefixed names."""
        n, O = self.n, self.O + Vector(at)
        A_ = Vector(at)
        p = {}
        p[n("hips")] = {"loc": tuple(Vector(hips[0]) + A_), "rot": hips[1]}
        p[n("spine")] = {"rot": spine}
        p[n("chest")] = {"rot": chest}
        for side, f, k in ((".L", footL, kneeL), (".R", footR, kneeR)):
            p[n("ik_foot" + side)] = {"pos": tuple(Vector(f[0]) + O), "rot": f[1]}
            p[n("pole_knee" + side)] = {"pos": tuple(Vector(k) + O)}
        m = self.chest_matrix(rig, p)
        mi, qi = m.inverted(), m.to_quaternion().inverted()
        for side, h, e in ((".L", handL, elbowL), (".R", handR, elbowR)):
            p[n("ik_hand" + side)] = {"pos": tuple(mi @ (Vector(h[0]) + O)),
                                      "rot": qi @ (h[1] if len(h) > 1 else Quaternion())}
            p[n("pole_elbow" + side)] = {"pos": tuple(mi @ (Vector(e) + O))}
        if isinstance(head, tuple):
            f = m.to_3x3() @ Vector((0, -1, 0))
            cy = math.degrees(math.atan2(f.x, -f.y))
            cp = math.degrees(math.asin(max(-1.0, min(1.0, -f.z))))
            p[n("head")] = {"rot": E(head[1] - 0.75 * cp, head[2] if len(head) > 2 else 0.0, head[0] - cy)}
        else:
            p[n("head")] = {"rot": head}
        return p


def grip(fist_pos, q, right=True):
    """Wrist position that puts the fist at fist_pos when the hand has rotation q."""
    off = (FIST_R - WRIST_R) if right else (FIST_L - WRIST_L)
    return tuple(Vector(fist_pos) - q @ off)
