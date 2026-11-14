"""Shieldbearer: heavy infantry of a bronze-age Levantine kingdom.

Conical bronze helmet with cheek guards, nasal bar and a team-coloured horsehair plume; banded bronze scale
cuirass over a linen kilt with a team hem; leather shoulder caps; team short cape; bronze greaves; a big round
team shield with bronze rim and boss on the left arm; a broad leaf-bladed bronze short sword in the right hand.
"""

import math

from mathutils import Matrix, Vector

import srkit as K
from srkit import E, V, aim, capsule, ellipsoid, lathe, place, sheet, tube, bezier

NAME = "shieldbearer"
BODY_HEIGHT_CM = 142.0

P = dict(
    pelvis=0.53, waist=0.64, chest=0.80, neck=1.00,
    hip=(0.105, 0.0, 0.56), knee=(0.125, -0.03, 0.315), ankle=(0.14, 0.0, 0.09), foot_len=0.19,
    shoulder=(0.275, 0.0, 0.925), elbow=(0.32, 0.035, 0.735), wrist=(0.335, -0.005, 0.565),
)

FIST_L = Vector((0.338, -0.013, 0.50))     # centre of the left fist at rest
SHIELD_R = 0.285
PROPS = {"shield": "hand.L", "weapon": "hand.R"}


def bones():
    B = K.humanoid_bones(P)
    wr = Vector(P["wrist"])
    el = Vector(P["elbow"])
    tail = wr + (wr - el).normalized() * 0.10
    B += [
        ("shield", tuple(wr), tuple(tail), "root", True),
        ("weapon", (-wr.x, wr.y, wr.z), (-tail.x, tail.y, tail.z), "root", True),
        ("plume", (0, 0.02, 1.42), (0, 0.24, 1.36), "head", True),
        ("cape", (0, 0.13, 0.97), (0, 0.17, 0.62), "chest", True),
        ("kilt", (0, 0, 0.64), (0, 0, 0.42), "hips", True),
        ("smear", (0, 0, 0.9), (0, 0, 1.0), "root", True),
    ]
    return B


def build_mesh(b):
    # ---------------------------------------------------------------- legs
    hip, knee, ankle = V(P["hip"]), V(P["knee"]), V(P["ankle"])
    b.add(capsule(hip, knee, 0.098, 0.082, seg=14), "skin", "upper_leg.L", mirror=True)
    # greave: bronze shin with a knee cop and a dark leather strap
    b.add(capsule(knee, ankle + V(0, 0, 0.03), 0.086, 0.072, seg=14), "bronze", "lower_leg.L", mirror=True)
    b.add(ellipsoid((0.07, 0.055, 0.07), seg=12, rings=8), "bronze", "lower_leg.L",
          place(knee + V(0, -0.052, 0.008)), mirror=True)
    b.add(lathe([(0.092, -0.016), (0.092, 0.016)], seg=14), "leather_dark", "lower_leg.L",
          place(knee + V(0.004, 0.012, -0.085)), mirror=True)
    # boot
    b.add(ellipsoid((0.082, 0.08, 0.07), seg=12, rings=8), "leather", "foot.L",
          place(ankle + V(0, 0.01, -0.012)), mirror=True)
    b.add(ellipsoid((0.08, 0.135, 0.058), seg=14, rings=8, e1=0.7, e2=0.8), "leather", "foot.L",
          place(V(ankle.x, -0.065, 0.058)), mirror=True)
    b.add(ellipsoid((0.086, 0.142, 0.02), seg=14, rings=6, e1=0.5, e2=0.8), "leather_dark", "foot.L",
          place(V(ankle.x, -0.065, 0.018)), mirror=True)

    # ---------------------------------------------------------------- hips, kilt, belt
    b.add(ellipsoid((0.18, 0.13, 0.10), seg=16, rings=8), "linen", "hips", place((0, 0, 0.57)))
    b.add(lathe([(0.0, 0.67), (0.18, 0.67), (0.205, 0.57), (0.238, 0.475), (0.244, 0.465), (0.0, 0.465)],
                seg=24, sy=0.80), "linen", "kilt")
    b.add(lathe([(0.0, 0.468), (0.245, 0.468), (0.258, 0.422), (0.252, 0.408), (0.0, 0.408)],
                seg=24, sy=0.80), "team", "kilt")
    # front apron: leather strap with a bronze disc, hanging from the belt
    b.add(sheet([[V(-0.05, -0.160, 0.66), V(0.05, -0.160, 0.66)],
                 [V(-0.056, -0.190, 0.57), V(0.056, -0.190, 0.57)],
                 [V(-0.046, -0.214, 0.47), V(0.046, -0.214, 0.47)]], 0.024), "leather", "kilt")
    b.add(ellipsoid((0.04, 0.018, 0.04), seg=10, rings=6), "bronze", "kilt", place((0, -0.212, 0.525)))
    b.add(lathe([(0.0, 0.615), (0.19, 0.615), (0.197, 0.648), (0.19, 0.682), (0.0, 0.682)], seg=24, sy=0.78),
          "leather_dark", "hips")
    b.add(ellipsoid((0.045, 0.02, 0.038), seg=10, rings=6), "bronze", "hips", place((0, -0.152, 0.65)))

    # ---------------------------------------------------------------- cuirass: overlapping bronze scale bands
    rows = [(0.188, 0.200, 0.668, 0.742, "spine", "scale_b"),
            (0.204, 0.218, 0.730, 0.806, "spine", "scale_a"),
            (0.222, 0.232, 0.794, 0.868, "chest", "scale_b"),
            (0.234, 0.238, 0.856, 0.928, "chest", "scale_a"),
            (0.232, 0.224, 0.916, 0.972, "chest", "scale_b")]
    for r0, r1, z0, z1, bone, mat in rows:
        b.add(lathe([(0.0, z0), (r0 + 0.014, z0), (r0 + 0.018, z0 + 0.014), (r1, z1), (0.0, z1)], seg=24, sy=0.70),
              mat, bone)
    # leather yoke over the shoulders, neck
    b.add(ellipsoid((0.215, 0.14, 0.062), seg=18, rings=8), "leather", "chest", place((0, 0.0, 0.968)))
    b.add(capsule((0, 0, 0.96), (0, -0.005, 1.04), 0.078, 0.072, seg=12), "skin", "chest")

    # ---------------------------------------------------------------- arms
    sh, el, wr = V(P["shoulder"]), V(P["elbow"]), V(P["wrist"])
    b.add(ellipsoid((0.112, 0.115, 0.095), seg=14, rings=8), "leather", "upper_arm.L",
          place(sh + V(0.012, 0, 0.014)), mirror=True)
    b.add(lathe([(0.0, -0.012), (0.12, -0.012), (0.125, 0.006), (0.0, 0.014)], seg=14), "bronze", "upper_arm.L",
          place(sh + V(0.016, 0, -0.05), ry=-12), mirror=True)
    mid = sh.lerp(el, 0.45)
    b.add(capsule(sh, mid, 0.088, 0.086, seg=12), "linen", "upper_arm.L", mirror=True)
    b.add(capsule(mid, el, 0.076, 0.07, seg=12), "skin", "upper_arm.L", mirror=True)
    b.add(capsule(el, wr, 0.07, 0.062, seg=12), "skin", "lower_arm.L", mirror=True)
    b0, b1 = el.lerp(wr, 0.25), el.lerp(wr, 0.95)
    b.add(capsule(b0, b1, 0.08, 0.074, seg=12, caps=2), "leather", "lower_arm.L", mirror=True)
    for t in (0.32, 0.88):
        c = el.lerp(wr, t)
        ax = (wr - el).normalized()
        M = Matrix.Translation(c) @ aim(ax, (0, -1, 0), d0=(0, 0, 1), s0=(0, -1, 0)).to_matrix().to_4x4()
        b.add(lathe([(0.086, -0.014), (0.086, 0.014)], seg=12), "bronze", "lower_arm.L", M, mirror=True)
    fist = wr + (wr - el).normalized() * 0.065
    b.add(ellipsoid((0.084, 0.09, 0.086), seg=12, rings=8, e1=0.8, e2=0.85), "skin", "hand.L",
          place(fist), mirror=True)

    # ---------------------------------------------------------------- head
    hz = 1.14
    b.add(ellipsoid((0.148, 0.156, 0.155), seg=18, rings=12), "skin", "head", place((0, -0.005, hz)))
    b.add(ellipsoid((0.04, 0.05, 0.05), seg=10, rings=6), "skin", "head", place((0, -0.160, hz - 0.022)))
    b.add(ellipsoid((0.028, 0.02, 0.022), seg=8, rings=6), "eye", "head", place((0.062, -0.142, hz + 0.014)),
          mirror=True)
    b.add(capsule((0.026, -0.156, hz + 0.040), (0.10, -0.132, hz + 0.054), 0.014, 0.012, seg=8, caps=2), "hair",
          "head", mirror=True)
    # beard: a full auburn mass round the jaw, chin pushed forward, and a moustache bar
    b.add(ellipsoid((0.142, 0.118, 0.085), seg=16, rings=10), "beard", "head", place((0, -0.05, hz - 0.118), rx=-8))
    b.add(ellipsoid((0.092, 0.075, 0.075), seg=12, rings=8), "beard", "head", place((0, -0.128, hz - 0.14)))
    b.add(capsule((-0.058, -0.158, hz - 0.066), (0.058, -0.158, hz - 0.066), 0.021, seg=8, caps=2), "beard", "head")
    # helmet: open-faced conical cap with a brow band, short ear flaps, a neck guard and a nasal bar
    hm = place((0, 0.0, 0))
    hb = hz + 0.072          # bottom of the brow band
    b.add(lathe([(0.0, hb + 0.015), (0.172, hb + 0.015), (0.176, hb + 0.045), (0.162, hb + 0.10),
                 (0.124, hb + 0.16), (0.07, hb + 0.205), (0.036, hb + 0.225), (0.028, hb + 0.238),
                 (0.036, hb + 0.252), (0.0, hb + 0.266)], seg=24, sy=1.04), "bronze", "head", hm)
    b.add(lathe([(0.0, hb), (0.182, hb), (0.186, hb + 0.024), (0.181, hb + 0.048), (0.0, hb + 0.048)],
                seg=24, sy=1.04), "bronze_dark", "head", hm)
    flap = [(0.160, hz - 0.07), (0.178, hz - 0.03), (0.182, hb + 0.01)]
    b.add(lathe(flap, seg=5, sy=1.04, arc=(322, 384), thick=0.03), "bronze", "head", hm)
    b.add(lathe(flap, seg=5, sy=1.04, arc=(156, 218), thick=0.03), "bronze", "head", hm)
    b.add(lathe([(0.158, hz - 0.075), (0.18, hz - 0.03), (0.183, hb + 0.01)], seg=8, sy=1.04, arc=(24, 156),
                thick=0.03), "bronze_dark", "head", hm)
    b.add(capsule((0, -0.186, hb + 0.03), (0, -0.188, hz - 0.0), 0.02, 0.015, seg=8, caps=2, squash=(1, 0.6)),
          "bronze", "head")
    # four darker ribs from the brow band to the apex
    prof = [(0.180, hb + 0.045), (0.166, hb + 0.10), (0.128, hb + 0.16), (0.074, hb + 0.205), (0.04, hb + 0.226)]
    for ang in (0, 90, 180, 270):
        ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        b.add(tube([V(r * ca, 1.04 * r * sa, z) for r, z in prof], 0.017, seg=6), "bronze_dark", "head")
    # plume: horsehair tail from the apex, falling back
    pts = bezier((0, 0.0, hb + 0.25), (0, 0.05, hb + 0.35), (0, 0.24, hb + 0.31), (0, 0.27, hb + 0.06), 8)
    rad = [0.026, 0.042, 0.054, 0.060, 0.060, 0.055, 0.046, 0.032, 0.012]
    b.add(tube(pts, rad, seg=10, squash=(0.75, 1.0)), "team", "plume")

    # ---------------------------------------------------------------- short cape (team) with folds and a pale hem
    def cape_rows(spec, fold):
        grid = []
        for z, rx, ry, a in spec:
            row = []
            for j in range(17):
                t = j / 16
                ang = math.radians(90 - a + 2 * a * t)
                k = 1.0 + fold * math.cos(t * math.pi * 2 * 3.5) * (0.97 - z) / 0.45
                row.append(V(rx * k * math.cos(ang), ry * k * math.sin(ang) + 0.012, z))
            grid.append(row)
        return grid
    b.add(sheet(cape_rows([(1.0, 0.215, 0.150, 62), (0.93, 0.238, 0.190, 64), (0.82, 0.248, 0.212, 60),
                           (0.71, 0.255, 0.232, 56), (0.64, 0.262, 0.248, 54)], 0.11), 0.03), "team", "cape")
    b.add(sheet(cape_rows([(0.645, 0.264, 0.250, 54), (0.60, 0.270, 0.258, 53)], 0.11), 0.034), "team_trim", "cape")
    # clasp cord across the collar bones
    b.add(tube([V(-0.19, -0.07, 0.99), V(-0.09, -0.128, 0.968), V(0.09, -0.128, 0.968), V(0.19, -0.07, 0.99)],
               0.018, seg=6), "team_trim", "chest")

    # ---------------------------------------------------------------- shield (centre grip), built at the rest fist
    S = place(FIST_L + V(0, -0.085, 0), rx=90)      # local +Z of the lathe -> -Y (the shield's face)
    R = SHIELD_R
    b.add(lathe([(0.0, -0.022), (R, -0.022), (R, 0.018), (0.0, 0.018)], seg=28), "wood", "shield", S)
    b.add(lathe([(0.0, 0.016), (R - 0.02, 0.016), (R - 0.03, 0.04), (R * 0.62, 0.066), (R * 0.3, 0.082), (0.0, 0.088)],
                seg=28), "team", "shield", S)
    b.add(lathe([(R - 0.045, 0.014), (R - 0.045, 0.048), (R - 0.012, 0.058), (R + 0.022, 0.044), (R + 0.026, 0.0),
                 (R + 0.012, -0.028), (R - 0.045, -0.028)], seg=28, wrap=True), "bronze", "shield", S)
    b.add(lathe([(R * 0.54, 0.060), (R * 0.54, 0.082), (R * 0.66, 0.076), (R * 0.66, 0.05)], seg=28, wrap=True),
          "team_trim", "shield", S)
    b.add(ellipsoid((0.085, 0.085, 0.07), seg=14, rings=8), "bronze", "shield", S @ place((0, 0, 0.082)))

    # ---------------------------------------------------------------- sword in the right fist
    f = V(-FIST_L.x, FIST_L.y, FIST_L.z)
    b.add(capsule(f + V(0, 0.085, 0), f + V(0, -0.085, 0), 0.024, seg=8, caps=2), "leather_dark", "weapon")
    b.add(ellipsoid((0.036, 0.036, 0.036), seg=8, rings=6), "bronze", "weapon", place(f + V(0, 0.108, 0)))
    b.add(capsule(f + V(0, -0.10, 0.075), f + V(0, -0.10, -0.075), 0.025, seg=8, caps=2), "bronze_dark", "weapon")
    ys = [-0.105, -0.18, -0.29, -0.40, -0.50, -0.59, -0.66]
    hw = [0.040, 0.043, 0.056, 0.068, 0.060, 0.036, 0.0]
    b.add(tube([f + V(0, y, 0) for y in ys], hw, seg=6, squash=(0.42, 1.0), up=(0, 0, 1)), "blade", "weapon")

    # ---------------------------------------------------------------- strike smear: the arc the blade tip just cut
    # Built in character space where the strike frame puts the blade; scaled away on every other frame.
    C, R = V(-0.13, -0.30, 0.86), 0.97
    upv = V(-0.5, 0, 1).normalized()          # a diagonal cut: high on the sword side, low across the body
    grid = []
    for i in range(15):
        t = i / 14
        th = math.radians(100 - 118 * t)
        w = 0.24 * t ** 1.5 * (1 - max(0.0, (t - 0.88) / 0.12) ** 2) + 0.004
        fwd = V(0.06, -1, 0).normalized()
        row = []
        for r in (R, R - w):
            row.append(C + (fwd * math.cos(th) + upv * math.sin(th)) * r)
        grid.append(row)
    b.add(sheet(grid, 0.05), "smear", "smear")
    # the underside of the kilt, seen when he lies on his back
    b.add(lathe([(0.0, 0.404), (0.25, 0.404), (0.0, 0.400)], seg=24, sy=0.80), "leather_dark", "kilt")


# ------------------------------------------------------------------------------------------------ poses
import sranim as A  # noqa: E402
from srkit import pose_lerp, pose_merge  # noqa: E402

WRIST_L = Vector(P["wrist"])
WRIST_R = Vector((-WRIST_L.x, WRIST_L.y, WRIST_L.z))
SHIELD_C = FIST_L + Vector((0, -0.085, 0))
FIST_R = Vector((-FIST_L.x, FIST_L.y, FIST_L.z))
STEP = 0.155          # ground travelled per walk frame: 8 frames = 124 cm = WalkCycleDistance (Sovereign Feel > Animation)


def sword(d, edge=(0, 0, -1)):
    """Hand rotation that points the blade along d with its cutting edge toward `edge`."""
    return aim(d, edge, s0=(0, 0, -1))


def face(d, up=(0, 0, 1)):
    """Hand rotation that points the shield's face along d."""
    return aim(d, up)


def free_shield(centre, d, up=(0, 1, 0)):
    q = face(d, up)
    return {"pos": tuple(Vector(centre) - q @ (SHIELD_C - WRIST_L)), "rot": q, "free": 1}


def free_sword(grip, d, edge=(0, 0, -1)):
    q = sword(d, edge)
    return {"pos": tuple(Vector(grip) - q @ (FIST_R - WRIST_R)), "rot": q, "free": 1}


def blank():
    return {b: {} for b in ("root", "hips", "spine", "chest", "head", "ik_foot.L", "ik_foot.R", "pole_knee.L",
                            "pole_knee.R", "ik_hand.L", "ik_hand.R", "pole_elbow.L", "pole_elbow.R", "shield",
                            "weapon", "plume", "cape", "kilt")} | {"smear": {"scale": 0.001}}


def make(rig, hips, spine, chest, head, footL, footR, shield, swd, kneeL=(0.32, -1.0, 0.3), kneeR=(-0.65, -0.85, 0.3),
         elbowL=(1.0, 0.1, 0.45), elbowR=(-1.0, 0.75, 0.6), plume=0.0, cape=0.0, kilt=0.0):
    """One full pose. hips = (loc, rot); spine / chest = rot; head = (yaw, pitch[, roll]) in character space or a
    rotation; feet = (pos, rot); shield = (hand pos, facing dir) and swd = (hand pos, blade dir[, edge]) in
    character space."""
    p = blank()
    p["hips"] = {"loc": hips[0], "rot": hips[1]}
    p["spine"] = {"rot": spine}
    p["chest"] = {"rot": chest}
    p["ik_foot.L"] = {"pos": footL[0], "rot": footL[1]}
    p["ik_foot.R"] = {"pos": footR[0], "rot": footR[1]}
    p["pole_knee.L"] = {"pos": kneeL}
    p["pole_knee.R"] = {"pos": kneeR}
    A.hands(rig, p, {
        "ik_hand.L": {"pos": shield[0], "rot": face(shield[1], shield[2] if len(shield) > 2 else (0, 0, 1))},
        "ik_hand.R": {"pos": swd[0], "rot": sword(swd[1], swd[2] if len(swd) > 2 else (0, 0, -1))},
        "pole_elbow.L": {"pos": elbowL}, "pole_elbow.R": {"pos": elbowR}})
    if isinstance(head, tuple):
        A.look(rig, p, yaw=head[0], pitch=head[1], roll=head[2] if len(head) > 2 else 0.0)
    else:
        p["head"] = {"rot": head}
    p["plume"] = {"rot": E(plume, 0, 0)}
    p["cape"] = {"rot": E(cape, 0, 0)}
    p["kilt"] = {"rot": E(kilt, 0, 0)}
    return p


FOOT_L = ((0.20, -0.13, 0.09), E(0, 0, 8))
FOOT_R = ((-0.21, 0.11, 0.09), E(0, 0, -32))


def guard(rig):
    """Ready stance: shield side forward, knees bent, shield up at the left, sword cocked at the right shoulder."""
    return make(rig, ((0, 0, -0.05), E(0, 0, -12)), E(3, 0, -3), E(0, 0, -5), (0, -10), FOOT_L, FOOT_R,
                ((0.25, -0.36, 0.76), (0.10, -1, 0.06)), ((-0.47, 0.04, 0.82), (-0.36, -0.2, 1), (0, -1, -0.3)))


def animate(rig):
    G = guard(rig)
    sin, cos, pi = math.sin, math.cos, math.pi

    # ---------------------------------------------------------------- idle: breathing, weight shift, weapon settle
    rig.new_action("idle", 8, loop=True, drive="time", fps=6.0)
    for i in range(8):
        p = pose_merge(G)
        p["hips"] = {"loc": (0, 0, -0.05 + A.IDLE_UP[i] * A.PX_Z), "rot": E(0, 0, -12)}
        hl, hr = dict(G["ik_hand.L"]), dict(G["ik_hand.R"])
        lag = A.IDLE_HAND_LAG[i] * A.PX_Z
        hl["pos"] = tuple(Vector(hl["pos"]) + Vector((0, 0, lag)))
        hr["pos"] = tuple(Vector(hr["pos"]) + Vector((0, 0, lag)))
        hr["rot"] = E(4.0 * A.IDLE_TILT[i], 0, 0) @ hr["rot"]
        p["ik_hand.L"], p["ik_hand.R"] = hl, hr
        p["plume"] = {"rot": E(5 * A.IDLE_SWAY[i], 0, 0)}
        p["cape"] = {"rot": E(1.5 * A.IDLE_SWAY[i], 0, 0)}
        rig.key(p, i)

    # ---------------------------------------------------------------- walk: a heavy jog, shield leading
    rig.new_action("walk", 8, loop=True, drive="distance", cycle_cm=STEP * 800,
                   contact_frames=[0, 4], roles=["contact L", "down", "passing", "up", "contact R", "down",
                                                 "passing", "up"])
    for i in range(8):
        ph = i / 8
        body = A.run_body(i, bob=0.026, drop=-0.058, lean=10.0, sway=0.014, yaw=8.0, roll=3.5)
        body["hips"]["rot"] = E(0, 0, -7) @ body["hips"]["rot"]
        fl = A.run_legs(ph, STEP, 0.09, lift=0.12, side=1, foot_x=0.15)
        fr = A.run_legs(ph + 0.5, STEP, 0.09, lift=0.12, side=-1, foot_x=0.15)
        lag = -0.026 * cos(4 * pi * ph - pi / 2 - 0.9)
        c1, c2 = cos(2 * pi * ph), cos(4 * pi * ph)
        p = make(rig, (body["hips"]["loc"], body["hips"]["rot"]), body["spine"]["rot"], body["chest"]["rot"],
                 (0, -7), (fl["pos"], fl["rot"]), (fr["pos"], fr["rot"]),
                 ((0.24, -0.33 + 0.02 * c1, 0.74 + lag), (0.12, -1, 0.05)),
                 ((-0.45, 0.03 - 0.10 * c1, 0.80 + lag * 1.3), (-0.3, -0.28 - 0.22 * c1, 1), (0, -1, -0.3)),
                 kneeL=(0.22, -1.0, 0.3), kneeR=(-0.22, -1.0, 0.3),
                 plume=10 + 9 * cos(4 * pi * ph - 2.6), cape=8 + 4 * cos(4 * pi * ph - 2.2),
                 kilt=3 * cos(4 * pi * ph - 1.0))
        rig.key(p, i)

    # ---------------------------------------------------------------- attack: coil, lunging cut, recover
    rig.new_action("attack", 8, drive="attack_phase", strike_frame=3, windup_frames=[0, 1, 2],
                   recovery_frames=[3, 4, 5, 6, 7], windup_phase_map=[0.0, 0.30, 0.62],
                   recovery_phase_map=[0.0, 0.22, 0.42, 0.62, 0.82])
    a0 = make(rig, ((0, 0.03, -0.055), E(0, 0, -18)), E(1, 0, -6), E(0, 0, -8), (0, -9), FOOT_L, FOOT_R,
              ((0.20, -0.42, 0.80), (0.05, -1, 0.08)), ((-0.46, 0.14, 1.0), (-0.2, 0.3, 1), (0, -1, 0)),
              plume=-3, cape=-3)
    a1 = make(rig, ((0, 0.07, -0.07), E(-2, 0, -25)), E(-3, 0, -10), E(-3, 0, -14), (2, -8),
              ((0.20, -0.17, 0.115), E(-8, 0, 8)), FOOT_R,
              ((0.16, -0.45, 0.84), (0.0, -1, 0.1)), ((-0.40, 0.30, 1.15), (-0.32, 0.4, 0.85), (0, 0.6, -1)),
              elbowR=(-1.2, 0.3, 1.0), plume=-8, cape=-6)
    a2 = make(rig, ((0, 0.085, -0.08), E(-3, 0, -29)), E(-4, 0, -12), E(-5, 0, -17), (3, -8),
              ((0.20, -0.25, 0.13), E(-12, 0, 8)), FOOT_R,
              ((0.15, -0.46, 0.85), (0.0, -1, 0.12)), ((-0.36, 0.35, 1.19), (-0.30, 0.62, 0.72), (0, 0.5, -1)),
              elbowR=(-1.2, 0.3, 1.0), plume=-10, cape=-8)
    a3 = make(rig, ((0, -0.13, -0.105), E(7, 0, 8)), E(9, 0, 10), E(5, 0, 14), (0, -4),
              ((0.19, -0.40, 0.09), E(0, 0, 6)), ((-0.21, 0.12, 0.118), E(30, 0, -28)),
              ((0.34, -0.24, 0.72), (0.55, -0.82, 0.1)), ((-0.13, -0.60, 0.80), (0.10, -0.93, -0.35)),
              kneeL=(0.25, -1.2, 0.3), elbowR=(-1.0, 0.2, 0.3), plume=20, cape=3, kilt=6)
    a3["smear"] = {"scale": 1.0}
    a4 = make(rig, ((0, -0.15, -0.125), E(11, 0, 14)), E(12, 0, 13), E(8, 0, 17), (0, -2),
              ((0.19, -0.40, 0.09), E(0, 0, 6)), ((-0.21, 0.12, 0.125), E(36, 0, -28)),
              ((0.42, -0.10, 0.72), (0.8, -0.6, 0.0)), ((0.05, -0.50, 0.50), (0.5, -0.72, -0.48)),
              kneeL=(0.25, -1.2, 0.3), elbowR=(-1.0, 0.2, 0.3), plume=10, cape=4, kilt=4)
    a5 = make(rig, ((0, -0.09, -0.09), E(6, 0, 2)), E(6, 0, 2), E(3, 0, 2), (0, -7),
              ((0.19, -0.36, 0.09), E(0, 0, 6)), ((-0.21, 0.12, 0.10), E(12, 0, -30)),
              ((0.36, -0.22, 0.74), (0.5, -0.86, 0.05)), ((-0.24, -0.38, 0.62), (0.05, -0.9, 0.3)),
              plume=-6, cape=8)
    a6 = pose_lerp(a5, G, 0.62)
    a6["hips"]["loc"] = (0, 0.02, -0.06)
    a7 = pose_lerp(a6, G, 0.8)
    rig.key_all([a0, a1, a2, a3, a4, a5, a6, a7])

    # ---------------------------------------------------------------- hit: sharp recoil, hunch, back to guard
    rig.new_action("hit", 3, drive="time", fps=18.0)
    h0 = make(rig, ((0, 0.075, -0.035), E(-9, 0, -6)), E(-11, 0, -1), E(-8, 0, 2), (4, -24, 6),
              FOOT_L, ((-0.21, 0.21, 0.09), E(0, 0, -32)),
              ((0.30, -0.25, 0.88), (0.2, -1, 0.5)), ((-0.56, 0.18, 0.94), (-0.6, 0.1, 1), (0, -1, -0.3)),
              plume=24, cape=-7)
    h1 = pose_lerp(h0, G, 0.6)
    h1["hips"] = {"loc": (0, 0.03, -0.075), "rot": E(3, 0, -11)}
    h1["spine"] = {"rot": E(9, 0, -3)}
    A.look(rig, h1, yaw=0, pitch=-2)
    h1["plume"] = {"rot": E(-12, 0, 0)}
    h2 = pose_lerp(h1, G, 0.7)
    rig.key_all([h0, h1, h2])

    # ---------------------------------------------------------------- spawn: rises from a crouch, sets guard
    rig.new_action("spawn", 6, drive="time", fps=14.0, active_frame=5)
    s0 = make(rig, ((0, 0.02, -0.23), E(10, 0, -14)), E(15, 0, -4), E(9, 0, -6), (0, 12), FOOT_L, FOOT_R,
              ((0.14, -0.40, 0.50), (0.0, -1, 0.15)), ((-0.43, 0.02, 0.44), (-0.1, -0.75, -0.55)),
              plume=14, cape=6)
    s3 = make(rig, ((0, 0.0, -0.012), E(-3, 0, -12)), E(-4, 0, -3), E(-4, 0, -5), (0, -17), FOOT_L, FOOT_R,
              ((0.33, -0.27, 0.80), (0.3, -1, 0.1)), ((-0.50, -0.02, 1.08), (-0.2, -0.1, 1), (0, -1, -0.2)),
              plume=-14, cape=-8)
    s4 = pose_lerp(G, s0, 0.10)
    s4["plume"] = {"rot": E(10, 0, 0)}
    rig.key_all([s0, pose_lerp(s0, s3, 0.30), pose_lerp(s0, s3, 0.78), s3, s4, G])

    # ---------------------------------------------------------------- death: stagger, buckle, topple back, settle
    rig.new_action("death", 8, drive="time", fps=12.0, hold_last=True)
    up = (0.0, -0.1, 1.5)
    d0 = make(rig, ((0, 0.08, -0.03), E(-12, 0, -4)), E(-14, 0, 2), E(-10, 0, 6), (6, -30, 8),
              FOOT_L, ((-0.21, 0.22, 0.09), E(0, 0, -32)),
              ((0.36, -0.20, 0.92), (0.3, -1, 0.6)), ((-0.60, 0.20, 1.0), (-0.6, 0.2, 1), (0, -1, -0.3)),
              plume=26, cape=-8)
    d1 = make(rig, ((0.02, 0.15, -0.07), E(-7, 0, 4)), E(-5, 0, 4), E(3, 0, 6), (-8, 8, -6),
              ((0.20, -0.04, 0.09), E(0, 0, 8)), ((-0.20, 0.31, 0.09), E(0, 0, -30)),
              ((0.52, -0.06, 0.62), (0.7, -0.6, -0.2)), ((-0.54, 0.20, 0.56), (-0.3, -0.2, -1), (0, -1, 0.2)),
              plume=-10, cape=10)
    d2 = make(rig, ((0.02, 0.17, -0.22), E(2, 0, 6)), E(6, 0, 4), E(10, 0, 4), (-12, 26, -8),
              ((0.20, -0.02, 0.09), E(0, 0, 8)), ((-0.20, 0.31, 0.09), E(0, 0, -30)),
              ((0.54, -0.02, 0.42), (0.8, -0.4, -0.4)), ((-0.50, 0.16, 0.40), (-0.2, -0.3, -1)),
              plume=14, cape=4)
    d2["weapon"] = free_sword((-0.52, 0.18, 0.30), (-0.25, -0.5, -0.8))
    d3 = make(rig, ((0.02, 0.20, -0.33), E(-22, 0, 8)), E(-8, 0, 2), E(-6, 0, 0), (-10, -14, -6),
              ((0.20, 0.34, 0.07), E(75, 0, 8)), ((-0.20, 0.50, 0.07), E(75, 0, -20)),
              ((0.50, 0.10, 0.36), (0.8, -0.3, 0.3)), ((-0.48, 0.26, 0.36), (-0.2, -0.3, -1)),
              kneeL=(0.25, -1.0, -0.3), kneeR=(-0.3, -1.0, -0.3), plume=-16, cape=-6)
    d3["weapon"] = free_sword((-0.53, 0.14, 0.06), (-0.4, -0.9, -0.08), (0.9, -0.4, -0.2))
    d3["shield"] = free_shield((0.56, 0.05, 0.30), (0.8, -0.3, 0.5), (0, 0, 1))
    d4 = make(rig, ((0.02, 0.14, -0.34), E(-58, 0, 10)), E(-6, 0, 2), E(-4, 0, 0), (-8, -30, 0),
              ((0.21, 0.08, 0.11), E(15, 0, 10)), ((-0.19, 0.22, 0.09), E(55, 0, -15)),
              ((0.50, 0.36, 0.58), (0.5, 0.2, 0.8)), ((-0.50, 0.40, 0.62), (-0.4, 0.2, 0.9)),
              kneeL=(0.25, -0.6, 1.0), kneeR=(-0.3, -0.6, 1.0), elbowL=(1.2, 0.2, 0.3), elbowR=(-1.2, 0.3, 0.3),
              plume=-20, cape=-10)
    d4["weapon"] = free_sword((-0.53, 0.12, 0.09), (-0.37, -0.9, 0.04), (0.9, -0.37, 0.1))
    d4["shield"] = free_shield((0.60, 0.13, 0.17), (0.5, -0.15, 0.85), (0, 0, 1))
    d5 = make(rig, ((0.02, 0.10, -0.345), E(-90, 0, 12)), E(5, 0, 2), E(6, 0, 0), E(16, 0, -10),
              ((0.23, -0.12, 0.20), E(-50, 0, 15)), ((-0.16, 0.02, 0.16), E(-20, 0, -10)),
              ((0.54, 0.44, 0.17), (0.5, 0.2, 0.8)), ((-0.52, 0.52, 0.19), (-0.4, 0.2, 0.9)),
              kneeL=(0.3, -0.1, 1.5), kneeR=(-0.3, 0.1, 1.5), elbowL=(1.2, 0.2, 0.3), elbowR=(-1.2, 0.3, 0.3),
              plume=10, cape=0)
    d5["weapon"] = free_sword((-0.52, 0.10, 0.04), (-0.35, -0.93, 0.0), (0.93, -0.35, 0.0))
    d5["shield"] = free_shield((0.63, 0.19, 0.075), (0.22, -0.05, 1.0), (0, 1, 0))
    d7 = make(rig, ((0.02, 0.10, -0.36), E(-92, 0, 12)), E(-2, 0, 3), E(-2, 0, 0), E(-4, 6, -32),
              ((0.24, -0.19, 0.078), E(-62, 0, 30)), ((-0.15, 0.0, 0.09), E(0, 0, -15)),
              ((0.52, 0.48, 0.09), (0.5, 0.2, 0.8)), ((-0.48, 0.60, 0.09), (-0.4, 0.2, 0.9)),
              kneeL=(0.3, -0.1, 1.5), kneeR=(-0.35, 0.1, 1.5), elbowL=(1.2, 0.2, 0.3), elbowR=(-1.2, 0.3, 0.3),
              plume=0, cape=0)
    d7["weapon"] = free_sword((-0.52, 0.10, 0.04), (-0.35, -0.93, 0.0), (0.93, -0.35, 0.0))
    d7["shield"] = free_shield((0.63, 0.20, 0.06), (0.12, 0.0, 1.0), (0, 1, 0))
    d6 = pose_lerp(d5, d7, 0.7)
    d6["shield"] = free_shield((0.63, 0.20, 0.065), (0.04, 0.06, 1.0), (0, 1, 0))
    rig.key_all([d0, d1, d2, d3, d4, d5, d6, d7])
