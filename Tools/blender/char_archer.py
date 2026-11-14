"""Archer: light skirmisher of a bronze-age Levantine kingdom.

Team-coloured headcloth held by a dark cord, with a drape over the neck; sleeveless linen tunic with a team sash
and hem; leather quiver strap, bracer and leg wraps; quiver of arrows on the back; tall composite recurve bow in
the left hand. No metal on the body and no shield, so it can never be mistaken for the Shieldbearer.
"""

import math

from mathutils import Matrix, Vector

import srkit as K
from srkit import E, V, aim, capsule, ellipsoid, lathe, place, sheet, tube, bezier

NAME = "archer"
BODY_HEIGHT_CM = 134.0

P = dict(
    pelvis=0.52, waist=0.62, chest=0.77, neck=0.955,
    hip=(0.092, 0.0, 0.545), knee=(0.108, -0.028, 0.305), ankle=(0.12, 0.0, 0.085), foot_len=0.17,
    shoulder=(0.225, 0.0, 0.885), elbow=(0.262, 0.032, 0.705), wrist=(0.275, -0.005, 0.545),
)

FIST_L = Vector((0.2775, -0.012, 0.487))
PROPS = {"bow": "hand.L"}
BRACE = 0.125            # grip to string at rest
NOCK_Z = 0.49            # string nock height on each limb, from the grip


def bones():
    B = K.humanoid_bones(P)
    wr, el = Vector(P["wrist"]), Vector(P["elbow"])
    tail = wr + (wr - el).normalized() * 0.10
    g = FIST_L + Vector((0, -0.01, 0))
    B += [
        ("bow", tuple(wr), tuple(tail), "root", True),
        ("bow_top", tuple(g + Vector((0, 0.01, 0.10))), tuple(g + Vector((0, 0.10, 0.44))), "bow", True),
        ("bow_bot", tuple(g + Vector((0, 0.01, -0.10))), tuple(g + Vector((0, 0.10, -0.44))), "bow", True),
        ("string", tuple(g + Vector((0, BRACE, 0))), tuple(g + Vector((0, BRACE + 0.1, 0))), "bow", True),
        ("arrow", tuple(g + Vector((0, BRACE, 0))), tuple(g + Vector((0, BRACE - 0.3, 0))), "string", True),
        ("quiver", (0, 0.15, 0.80), (-0.12, 0.17, 1.0), "chest", True),
        ("tail", (0, 0.12, 1.08), (0, 0.17, 0.88), "head", True),
        ("sash_tail", (0.13, -0.12, 0.63), (0.15, -0.15, 0.43), "hips", True),
        ("skirt", (0, 0, 0.62), (0, 0, 0.42), "hips", True),
    ]
    return B


def build_mesh(b):
    # ---------------------------------------------------------------- legs: bare, with leather wraps and sandal boots
    hip, knee, ankle = V(P["hip"]), V(P["knee"]), V(P["ankle"])
    b.add(capsule(hip, knee, 0.084, 0.07, seg=14), "skin", "upper_leg.L", mirror=True)
    b.add(capsule(knee, ankle + V(0, 0, 0.02), 0.07, 0.056, seg=14), "skin", "lower_leg.L", mirror=True)
    for t, r in ((0.45, 0.071), (0.72, 0.066)):
        c = knee.lerp(ankle, t)
        b.add(lathe([(r, -0.022), (r + 0.003, 0.0), (r, 0.022)], seg=12), "leather", "lower_leg.L", place(c),
              mirror=True)
    b.add(ellipsoid((0.07, 0.07, 0.062), seg=12, rings=8), "leather", "foot.L", place(ankle + V(0, 0.008, -0.012)),
          mirror=True)
    b.add(ellipsoid((0.068, 0.122, 0.05), seg=14, rings=8, e1=0.7, e2=0.8), "leather", "foot.L",
          place(V(ankle.x, -0.058, 0.052)), mirror=True)
    b.add(ellipsoid((0.073, 0.128, 0.018), seg=14, rings=6, e1=0.5, e2=0.8), "leather_dark", "foot.L",
          place(V(ankle.x, -0.058, 0.016)), mirror=True)

    # ---------------------------------------------------------------- tunic: skirt, torso, sash
    b.add(ellipsoid((0.16, 0.118, 0.095), seg=16, rings=8), "linen", "hips", place((0, 0, 0.56)))
    b.add(lathe([(0.0, 0.65), (0.162, 0.65), (0.186, 0.56), (0.214, 0.475), (0.218, 0.465), (0.0, 0.465)],
                seg=24, sy=0.78), "linen", "skirt")
    b.add(lathe([(0.0, 0.468), (0.219, 0.468), (0.229, 0.432), (0.224, 0.42), (0.0, 0.42)], seg=24, sy=0.78),
          "team", "skirt")
    b.add(lathe([(0.0, 0.416), (0.222, 0.416), (0.0, 0.412)], seg=24, sy=0.78), "leather_dark", "skirt")
    b.add(lathe([(0.0, 0.63), (0.166, 0.63), (0.172, 0.70), (0.182, 0.775), (0.0, 0.775)], seg=24, sy=0.72),
          "linen", "spine")
    b.add(lathe([(0.0, 0.765), (0.184, 0.765), (0.196, 0.84), (0.19, 0.90), (0.15, 0.94), (0.0, 0.95)],
                seg=24, sy=0.72), "linen", "chest")
    b.add(ellipsoid((0.075, 0.04, 0.06), seg=12, rings=8), "skin", "chest", place((0, -0.118, 0.905), rx=-18))
    b.add(capsule((0, 0, 0.92), (0, -0.005, 1.0), 0.068, 0.064, seg=12), "skin", "chest")
    # sash: team band with a knot and a hanging tail on the left hip
    b.add(lathe([(0.0, 0.60), (0.172, 0.60), (0.18, 0.632), (0.172, 0.664), (0.0, 0.664)], seg=24, sy=0.76),
          "team", "hips")
    b.add(ellipsoid((0.045, 0.035, 0.04), seg=10, rings=6), "team", "hips", place((0.125, -0.11, 0.635)))
    b.add(sheet([[V(0.095, -0.118, 0.62), V(0.155, -0.10, 0.62)],
                 [V(0.10, -0.150, 0.53), V(0.168, -0.128, 0.53)],
                 [V(0.108, -0.166, 0.44), V(0.168, -0.146, 0.44)]], 0.026), "team", "sash_tail")
    # quiver strap from the right shoulder to the left hip
    b.add(tube([V(-0.15, 0.04, 0.945), V(-0.115, -0.105, 0.90), V(0.0, -0.142, 0.80), V(0.11, -0.128, 0.70),
                V(0.17, -0.06, 0.66)], 0.021, seg=6, squash=(1.0, 0.6)), "leather_dark", "chest")

    # ---------------------------------------------------------------- arms
    sh, el, wr = V(P["shoulder"]), V(P["elbow"]), V(P["wrist"])
    b.add(ellipsoid((0.086, 0.09, 0.075), seg=14, rings=8), "linen", "upper_arm.L", place(sh + V(0.004, 0, 0.012)),
          mirror=True)
    b.add(capsule(sh, el, 0.066, 0.058, seg=12), "skin", "upper_arm.L", mirror=True)
    b.add(capsule(el, wr, 0.058, 0.05, seg=12), "skin", "lower_arm.L", mirror=True)
    b.add(capsule(el.lerp(wr, 0.3), el.lerp(wr, 0.95), 0.066, 0.06, seg=12, caps=2), "leather", "lower_arm.L")
    fist = wr + (wr - el).normalized() * 0.058
    b.add(ellipsoid((0.07, 0.076, 0.073), seg=12, rings=8, e1=0.8, e2=0.85), "skin", "hand.L", place(fist),
          mirror=True)

    # ---------------------------------------------------------------- head
    hz = 1.105
    b.add(ellipsoid((0.14, 0.148, 0.148), seg=18, rings=12), "skin", "head", place((0, -0.005, hz)))
    b.add(ellipsoid((0.036, 0.046, 0.046), seg=10, rings=6), "skin", "head", place((0, -0.152, hz - 0.02)))
    b.add(ellipsoid((0.026, 0.019, 0.021), seg=8, rings=6), "eye", "head", place((0.058, -0.136, hz + 0.012)),
          mirror=True)
    b.add(capsule((0.024, -0.148, hz + 0.036), (0.094, -0.126, hz + 0.046), 0.013, 0.011, seg=8, caps=2), "hair",
          "head", mirror=True)
    # short dark beard along the jaw and a little hair at the temples
    b.add(ellipsoid((0.128, 0.105, 0.062), seg=16, rings=8), "hair", "head", place((0, -0.05, hz - 0.118), rx=-10))
    b.add(ellipsoid((0.06, 0.05, 0.05), seg=10, rings=6), "hair", "head", place((0, -0.128, hz - 0.128)))
    b.add(ellipsoid((0.03, 0.05, 0.06), seg=8, rings=6), "hair", "head", place((0.132, -0.04, hz + 0.0)), mirror=True)
    # headcloth: a dome tilted back so it sits on the brow and covers the nape, a cord round it, a drape behind
    hm = place((0, 0.004, hz + 0.01), rx=-16)
    b.add(lathe([(0.0, 0.03), (0.156, 0.03), (0.163, 0.06), (0.152, 0.115), (0.11, 0.158), (0.05, 0.178), (0.0, 0.182)],
                seg=24, sy=1.05), "team", "head", hm)
    b.add(lathe([(0.0, 0.022), (0.166, 0.022), (0.171, 0.045), (0.166, 0.068), (0.0, 0.068)], seg=24, sy=1.05),
          "leather_dark", "head", hm)
    grid = []
    for z, rx, ry, a in [(hz + 0.02, 0.15, 0.155, 70), (hz - 0.06, 0.16, 0.168, 66), (hz - 0.13, 0.168, 0.172, 58),
                         (hz - 0.20, 0.17, 0.176, 50), (hz - 0.255, 0.165, 0.18, 44)]:
        row = []
        for j in range(11):
            t = j / 10
            ang = math.radians(90 - a + 2 * a * t)
            row.append(V(rx * math.cos(ang), ry * math.sin(ang) + 0.012, z))
        grid.append(row)
    b.add(sheet(grid, 0.03), "team", "tail")

    # ---------------------------------------------------------------- quiver on the back, fletchings at the right shoulder
    q0, q1 = V(0.13, 0.165, 0.62), V(-0.13, 0.175, 1.0)
    b.add(capsule(q0, q1, 0.062, 0.07, seg=12, caps=2), "leather", "quiver")
    ax = (q1 - q0).normalized()
    M = Matrix.Translation(q1 + ax * 0.01) @ aim(ax, (0, 1, 0), d0=(0, 0, 1), s0=(0, 1, 0)).to_matrix().to_4x4()
    b.add(lathe([(0.076, -0.02), (0.08, 0.0), (0.076, 0.02)], seg=12), "leather_dark", "quiver", M)
    for dx, dy, ln in ((-0.03, 0.0, 0.13), (0.028, -0.02, 0.11), (0.0, 0.03, 0.15)):
        base = q1 + ax * 0.02 + V(dx, dy, 0)
        b.add(capsule(base, base + ax * ln, 0.012, 0.012, seg=6, caps=1), "shaft", "quiver")
        b.add(capsule(base + ax * (ln - 0.05), base + ax * (ln + 0.02), 0.026, 0.02, seg=6, caps=2,
                      squash=(1.0, 0.5)), "feather", "quiver")

    # ---------------------------------------------------------------- bow, built at the rest left fist
    g = FIST_L + V(0, -0.01, 0)

    def limb(sign):
        pts, rad = [], []
        for i in range(11):
            t = i / 10
            z = 0.06 + t * 0.52
            # belly sweeps back toward the archer, the tip recurves forward again
            y = 0.02 + 0.145 * math.sin(min(t / 0.8, 1.0) * math.pi / 2) - 0.085 * max(t - 0.72, 0.0) / 0.28
            pts.append(g + V(0, y, sign * z))
            rad.append(0.036 * (1 - 0.45 * t))
        return pts, rad

    def bow_bone(top, bot):
        def f(p):
            dz = p.z - g.z
            return top if dz > 0.10 else (bot if dz < -0.10 else "bow")
        return f

    for sign, bone in ((1, "bow_top"), (-1, "bow_bot")):
        pts, rad = limb(sign)
        b.add(tube(pts, rad, seg=8, squash=(1.0, 0.62), up=(1, 0, 0)), "wood", bone)
        b.add(ellipsoid((0.024, 0.026, 0.034), seg=8, rings=6), "feather", bone, place(pts[-1]))
    b.add(capsule(g + V(0, 0.012, -0.085), g + V(0, 0.012, 0.085), 0.034, seg=10, caps=2), "leather_dark", "bow")
    nock_y = BRACE
    top, bot = g + V(0, nock_y - 0.012, NOCK_Z + 0.05), g + V(0, nock_y - 0.012, -NOCK_Z - 0.05)
    mid = g + V(0, nock_y, 0)

    def string_bone(end):
        def f(p):
            return end if abs(p.z - g.z) > 0.2 else "string"
        return f

    b.add(tube([top, mid], 0.0105, seg=6), "string", string_bone("bow_top"))
    b.add(tube([mid, bot], 0.0105, seg=6), "string", string_bone("bow_bot"))

    # ---------------------------------------------------------------- arrow on the string (scaled away when not in use)
    a0 = mid
    b.add(capsule(a0, a0 + V(0, -0.52, 0), 0.0105, seg=6, caps=1), "shaft", "arrow")
    b.add(tube([a0 + V(0, -0.50, 0), a0 + V(0, -0.53, 0), a0 + V(0, -0.60, 0)], [0.012, 0.028, 0.0], seg=6,
               squash=(1.0, 0.45)), "bronze", "arrow")
    b.add(capsule(a0 + V(0, -0.02, 0), a0 + V(0, -0.11, 0), 0.03, 0.022, seg=6, caps=2, squash=(1.0, 0.3)),
          "feather", "arrow")


# ------------------------------------------------------------------------------------------------ poses
import sranim as A  # noqa: E402
from srkit import pose_lerp, pose_merge  # noqa: E402

WRIST_L = Vector(P["wrist"])
GRIP = FIST_L + Vector((0, -0.01, 0))
STEP = 0.155          # ground travelled per walk frame: 8 frames = 124 cm = 2 x StrideLength (62 cm)


def blank():
    return {b: {} for b in ("root", "hips", "spine", "chest", "head", "ik_foot.L", "ik_foot.R", "pole_knee.L",
                            "pole_knee.R", "ik_hand.L", "ik_hand.R", "pole_elbow.L", "pole_elbow.R", "bow",
                            "bow_top", "bow_bot", "string", "arrow", "quiver", "tail", "sash_tail", "skirt")}


def free_bow(grip, d, up):
    q = aim(d, up)
    return {"pos": tuple(Vector(grip) - q @ (GRIP - WRIST_L)), "rot": q, "free": 1}


def make(rig, hips, spine, chest, head, footL, footR, bow, rhand, draw=0.0, flex=0.0, arrow=False,
         kneeL=(0.2, -1.0, 0.3), kneeR=(-0.7, -0.8, 0.3), elbowL=(0.9, 0.5, 0.4), elbowR=(-0.9, 0.7, 0.5),
         quiver=0.0, tail=0.0, sash=0.0, skirt=0.0):
    """One full pose. bow = (hand pos, arrow direction, upper-limb direction) in character space; rhand is a
    character-space point, or 'nock' to put the draw hand on the string."""
    p = blank()
    p["hips"] = {"loc": hips[0], "rot": hips[1]}
    p["spine"] = {"rot": spine}
    p["chest"] = {"rot": chest}
    p["ik_foot.L"] = {"pos": footL[0], "rot": footL[1]}
    p["ik_foot.R"] = {"pos": footR[0], "rot": footR[1]}
    p["pole_knee.L"] = {"pos": kneeL}
    p["pole_knee.R"] = {"pos": kneeR}
    q = aim(bow[1], bow[2])
    if isinstance(rhand, str):
        rp = Vector(bow[0]) + q @ ((GRIP - WRIST_L) + Vector((0, BRACE + draw + 0.035, -0.02)))
        rq = q
    else:
        rp, rq = Vector(rhand), E(0, 0, 0)
    A.hands(rig, p, {"ik_hand.L": {"pos": bow[0], "rot": q}, "ik_hand.R": {"pos": tuple(rp), "rot": rq},
                     "pole_elbow.L": {"pos": elbowL}, "pole_elbow.R": {"pos": elbowR}})
    p["string"] = {"loc": (0, draw, 0)}
    p["bow_top"] = {"rot": E(-flex, 0, 0)}
    p["bow_bot"] = {"rot": E(flex, 0, 0)}
    p["arrow"] = {"scale": 1.0 if arrow else 0.001}
    if isinstance(head, tuple):
        A.look(rig, p, yaw=head[0], pitch=head[1], roll=head[2] if len(head) > 2 else 0.0)
    else:
        p["head"] = {"rot": head}
    p["quiver"] = {"rot": E(quiver, 0, 0)}
    p["tail"] = {"rot": E(tail, 0, 0)}
    p["sash_tail"] = {"rot": E(sash, 0, 0)}
    p["skirt"] = {"rot": E(skirt, 0, 0)}
    return p


FOOT_L = ((0.15, -0.14, 0.085), E(0, 0, 0))
FOOT_R = ((-0.17, 0.11, 0.085), E(0, 0, -40))
BOW_READY = ((0.19, -0.36, 0.72), (0.10, -1, -0.12), (0.22, -0.18, 1))


def guard(rig):
    """Ready stance: side-on, bow upright in front of the left hip, draw hand loose by the right hip."""
    return make(rig, ((0, 0, -0.035), E(0, 0, -22)), E(2, 0, -4), E(0, 0, -6), (0, -9), FOOT_L, FOOT_R,
                BOW_READY, (-0.33, 0.02, 0.66))


def animate(rig):
    G = guard(rig)
    sin, cos, pi = math.sin, math.cos, math.pi

    # ---------------------------------------------------------------- idle
    rig.new_action("idle", 8, loop=True, drive="time", fps=6.0)
    for i in range(8):
        p = pose_merge(G)
        p["hips"] = {"loc": (0, 0, -0.035 + A.IDLE_UP[i] * A.PX_Z), "rot": E(0, 0, -22)}
        hl, hr = dict(G["ik_hand.L"]), dict(G["ik_hand.R"])
        lag = A.IDLE_HAND_LAG[i] * A.PX_Z
        hl["pos"] = tuple(Vector(hl["pos"]) + Vector((0, 0, lag)))
        hl["rot"] = E(0, 3.0 * A.IDLE_TILT[i], 0) @ hl["rot"]
        hr["pos"] = tuple(Vector(hr["pos"]) + Vector((0, 0, -lag)))
        p["ik_hand.L"], p["ik_hand.R"] = hl, hr
        p["tail"] = {"rot": E(3 * A.IDLE_SWAY[i], 0, 0)}
        p["sash_tail"] = {"rot": E(4 * A.IDLE_SWAY[i], 0, 0)}
        rig.key(p, i)

    # ---------------------------------------------------------------- walk: a light run, bow carried low
    rig.new_action("walk", 8, loop=True, drive="distance", cycle_cm=STEP * 800,
                   contact_frames=[0, 4], roles=["contact L", "down", "passing", "up", "contact R", "down",
                                                 "passing", "up"])
    for i in range(8):
        ph = i / 8
        body = A.run_body(i, bob=0.028, drop=-0.05, lean=12.0, sway=0.012, yaw=10.0, roll=4.0)
        fl = A.run_legs(ph, STEP, 0.085, lift=0.14, side=1, foot_x=0.115)
        fr = A.run_legs(ph + 0.5, STEP, 0.085, lift=0.14, side=-1, foot_x=0.115)
        lag = -0.028 * cos(4 * pi * ph - pi / 2 - 0.9)
        c1 = cos(2 * pi * ph)
        p = make(rig, (body["hips"]["loc"], body["hips"]["rot"]), body["spine"]["rot"], body["chest"]["rot"],
                 (0, -6), (fl["pos"], fl["rot"]), (fr["pos"], fr["rot"]),
                 ((0.30, -0.10 + 0.10 * c1, 0.66 + lag), (0.12, -0.85, -0.45 - 0.12 * c1), (0.12, -0.5, 0.85)),
                 (-0.30, -0.05 - 0.13 * c1, 0.70 + lag - 0.03 * c1),
                 kneeL=(0.16, -1.0, 0.3), kneeR=(-0.16, -1.0, 0.3), elbowL=(0.9, 0.9, 0.5),
                 quiver=3 * cos(4 * pi * ph - 2.0), tail=12 + 8 * cos(4 * pi * ph - 2.4),
                 sash=10 + 10 * cos(4 * pi * ph - 2.0), skirt=3 * cos(4 * pi * ph - 1.0))
        rig.key(p, i)

    # ---------------------------------------------------------------- attack: nock, draw to the cheek, release
    rig.new_action("attack", 8, drive="attack_phase", strike_frame=5, windup_frames=[0, 1, 2, 3, 4],
                   recovery_frames=[5, 6, 7], windup_phase_map=[0.0, 0.18, 0.38, 0.58, 0.80],
                   recovery_phase_map=[0.0, 0.34, 0.68], projectile_origin_cm=[62.0, 0.0, 98.0])
    aim_up = (0.34, 0, 1)            # the bow is canted, so it never goes fully edge-on to the camera
    eR = (-0.5, 1.2, 1.15)
    a0 = make(rig, ((0, 0.0, -0.04), E(0, 0, -20)), E(1, 0, -4), E(0, 0, -4), (0, -6), FOOT_L, FOOT_R,
              ((-0.02, -0.30, 0.80), (-0.06, -1, 0.0), (0.30, -0.05, 1)), "nock", draw=0.0, arrow=True, elbowR=eR)
    a1 = make(rig, ((0, 0.01, -0.04), E(0, 0, -34)), E(0, 0, -7), E(-1, 0, -9), (0, -7), FOOT_L, FOOT_R,
              ((0.08, -0.34, 0.90), (0.0, -1, 0.02), aim_up), "nock", draw=0.10, flex=3, arrow=True, elbowR=eR)
    a2 = make(rig, ((0, 0.02, -0.04), E(-1, 0, -48)), E(-2, 0, -9), E(-2, 0, -11), (0, -7), FOOT_L, FOOT_R,
              ((0.07, -0.46, 0.96), (0.0, -1, 0.03), aim_up), "nock", draw=0.22, flex=7, arrow=True, elbowR=eR)
    a3 = make(rig, ((0, 0.03, -0.045), E(-2, 0, -56)), E(-3, 0, -14), E(-3, 0, -16), (0, -7), FOOT_L, FOOT_R,
              ((0.06, -0.55, 0.98), (0.0, -1, 0.03), aim_up), "nock", draw=0.32, flex=10, arrow=True, elbowR=eR,
              tail=-4)
    a4 = make(rig, ((0, 0.036, -0.05), E(-3, 0, -57)), E(-3, 0, -14), E(-4, 0, -16), (0, -7), FOOT_L, FOOT_R,
              ((0.06, -0.555, 0.975), (0.0, -1, 0.03), aim_up), "nock", draw=0.345, flex=11, arrow=True, elbowR=eR,
              tail=-5)
    a5 = make(rig, ((0, 0.015, -0.03), E(0, 0, -62)), E(-2, 0, -15), E(-3, 0, -19), (0, -8), FOOT_L, FOOT_R,
              ((0.06, -0.59, 0.99), (0.0, -1, -0.36), aim_up), (-0.16, 0.20, 1.04), draw=-0.035, flex=-4,
              elbowR=(-0.9, 1.4, 1.1), tail=12, sash=-8)
    a6 = make(rig, ((0, 0.01, -0.035), E(0, 0, -54)), E(0, 0, -13), E(-1, 0, -15), (0, -9), FOOT_L, FOOT_R,
              ((0.08, -0.57, 0.94), (0.02, -1, -0.62), aim_up), (-0.24, 0.20, 0.92), draw=0.02, flex=1,
              elbowR=(-0.9, 1.3, 0.9), tail=-4, sash=6)
    a7 = pose_lerp(a6, G, 0.55)
    a7["string"] = {"loc": (0, -0.008, 0)}
    rig.key_all([a0, a1, a2, a3, a4, a5, a6, a7])

    # ---------------------------------------------------------------- hit
    rig.new_action("hit", 3, drive="time", fps=18.0)
    h0 = make(rig, ((0, 0.08, -0.03), E(-10, 0, -18)), E(-12, 0, -2), E(-8, 0, 0), (4, -24, 8),
              FOOT_L, ((-0.17, 0.22, 0.085), E(0, 0, -40)),
              ((0.36, -0.22, 0.84), (0.3, -1, 0.3), (0.3, 0.2, 1)), (-0.42, 0.14, 0.82),
              tail=-14, sash=-10, quiver=-6)
    h1 = pose_lerp(h0, G, 0.6)
    h1["hips"] = {"loc": (0, 0.03, -0.06), "rot": E(3, 0, -21)}
    h1["spine"] = {"rot": E(9, 0, -4)}
    A.look(rig, h1, yaw=0, pitch=-2)
    h1["tail"] = {"rot": E(10, 0, 0)}
    h2 = pose_lerp(h1, G, 0.7)
    rig.key_all([h0, h1, h2])

    # ---------------------------------------------------------------- spawn: rises from one knee, bow comes up
    rig.new_action("spawn", 6, drive="time", fps=14.0, active_frame=5)
    s0 = make(rig, ((0, 0.03, -0.21), E(12, 0, -24)), E(15, 0, -4), E(9, 0, -6), (0, 14), FOOT_L, FOOT_R,
              ((0.20, -0.36, 0.46), (0.3, -0.9, -0.3), (0.5, -0.5, 0.7)), (-0.26, -0.12, 0.40), tail=10)
    s3 = make(rig, ((0, 0.0, -0.005), E(-3, 0, -22)), E(-4, 0, -4), E(-4, 0, -6), (0, -16), FOOT_L, FOOT_R,
              ((0.22, -0.34, 0.82), (0.05, -1, 0.05), (0.12, -0.05, 1)), (-0.36, 0.04, 0.72), tail=-10, sash=-8)
    s4 = pose_lerp(G, s0, 0.10)
    s4["tail"] = {"rot": E(8, 0, 0)}
    rig.key_all([s0, pose_lerp(s0, s3, 0.30), pose_lerp(s0, s3, 0.78), s3, s4, G])

    # ---------------------------------------------------------------- death: clutches, folds, falls on his face
    rig.new_action("death", 8, drive="time", fps=12.0, hold_last=True)
    dn = (0.0, 0.1, -1.2)
    d0 = make(rig, ((0, 0.09, -0.03), E(-12, 0, -18)), E(-14, 0, 0), E(-10, 0, 4), (6, -30, 8),
              FOOT_L, ((-0.17, 0.23, 0.085), E(0, 0, -40)),
              ((0.40, -0.20, 0.88), (0.3, -1, 0.4), (0.4, 0.3, 1)), (-0.46, 0.16, 0.86), tail=-16, sash=-10)
    d1 = make(rig, ((0.0, 0.10, -0.08), E(8, 0, -10)), E(10, 0, 2), E(10, 0, 4), (0, 16),
              FOOT_L, ((-0.17, 0.23, 0.085), E(0, 0, -40)),
              ((0.42, -0.12, 0.52), (0.5, -0.6, -0.6), (0.6, 0.0, 0.8)), (-0.04, -0.16, 0.76), tail=12, sash=8)
    d2 = make(rig, ((0.0, 0.06, -0.21), E(14, 0, -6)), E(14, 0, 2), E(12, 0, 4), (0, 26),
              ((0.15, -0.08, 0.085), E(0, 0, 0)), ((-0.17, 0.23, 0.085), E(20, 0, -30)),
              ((0.40, -0.16, 0.34), (0.5, -0.6, -0.6), (0.6, 0.0, 0.8)), (-0.04, -0.22, 0.60), tail=6, sash=4)
    d2["bow"] = free_bow((0.46, -0.22, 0.30), (0.6, -0.5, -0.6), (0.6, -0.2, 0.75))
    d3 = make(rig, ((0.0, 0.0, -0.315), E(24, 0, -4)), E(12, 0, 0), E(10, 0, 2), (0, 30),
              ((0.14, 0.30, 0.07), E(78, 0, 8)), ((-0.16, 0.40, 0.07), E(78, 0, -18)),
              ((0.32, -0.30, 0.26), (0.5, -0.6, -0.6), (0.6, 0.0, 0.8)), (-0.10, -0.30, 0.40),
              kneeL=(0.2, -1.0, -0.3), kneeR=(-0.25, -1.0, -0.3), tail=4)
    d3["bow"] = free_bow((0.50, -0.30, 0.10), (0.8, -0.2, -0.3), (0.2, -0.9, 0.35))
    d4 = make(rig, ((0.0, -0.09, -0.36), E(56, 0, -6)), E(8, 0, 0), E(4, 0, 0), (0, 6),
              ((0.14, 0.27, 0.07), E(120, 0, 10)), ((-0.16, 0.36, 0.07), E(120, 0, -18)),
              ((0.30, -0.56, 0.22), (0.3, -0.9, -0.2), (0.2, 0, 1)), (-0.24, -0.52, 0.22),
              kneeL=(0.2, -0.6, -1.0), kneeR=(-0.25, -0.6, -1.0), elbowL=(1.2, -0.2, 0.5), elbowR=(-1.2, -0.2, 0.5),
              tail=-18, quiver=-8)
    d4["bow"] = free_bow((0.52, -0.32, 0.05), (0.9, -0.1, -0.05), (0.1, -0.95, 0.1))
    d5 = make(rig, ((0.0, -0.16, -0.37), E(86, 0, -10)), E(-7, 0, 0), E(-5, 0, 0), E(-26, 0, 35),
              ((0.14, 0.26, 0.11), E(150, 0, 10)), ((-0.16, 0.30, 0.14), E(140, 0, -18)),
              ((0.32, -0.64, 0.12), (0.3, -0.9, 0.0), (0.2, 0, 1)), (-0.30, -0.54, 0.13),
              kneeL=(0.2, 0.05, -1.2), kneeR=(-0.25, 0.05, -1.2), elbowL=(1.2, -0.2, 0.5), elbowR=(-1.2, -0.2, 0.5),
              tail=16, quiver=10)
    d5["bow"] = free_bow((0.53, -0.33, 0.035), (0.92, -0.05, 0.0), (0.05, -0.99, 0.0))
    d7 = make(rig, ((0.0, -0.16, -0.38), E(90, 0, -12)), E(-2, 0, -2), E(0, 0, 0), E(-16, 4, 58),
              ((0.14, 0.27, 0.075), E(168, 0, 14)), ((-0.19, 0.20, 0.075), E(160, 0, -35)),
              ((0.34, -0.62, 0.085), (0.3, -0.9, 0.0), (0.2, 0, 1)), (-0.36, -0.40, 0.085),
              kneeL=(0.2, 0.05, -1.2), kneeR=(-0.8, 0.0, -0.6), elbowL=(1.2, -0.2, 0.3), elbowR=(-1.2, -0.1, 0.3),
              tail=0, quiver=0)
    d7["bow"] = free_bow((0.53, -0.33, 0.035), (0.92, -0.05, 0.0), (0.05, -0.99, 0.0))
    d6 = pose_lerp(d5, d7, 0.7)
    rig.key_all([d0, d1, d2, d3, d4, d5, d6, d7])
