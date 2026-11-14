"""Horse Rider: light cavalry of a bronze-age Levantine kingdom.

A stocky bay pony (black mane, tail and stockings, pale blaze) under a team saddle cloth with a pale border, and
a rider with no stirrups: bronze skullcap with a team horsehair crest, leather jerkin over a short linen tunic
with a team sash and hem, a small round team shield on the left arm and a long bronze-headed spear in the right.

One armature: the horse (h_* bones, legs on IK with hoof targets on the ground) and the rider (srcrew.Fig hanging
from h_body, so every horse move carries him). Rendered in a 256 px cell at the troops' 1.75 cm per pixel.
"""

import math

from mathutils import Matrix, Vector

import srkit as K
import srcrew
from srkit import E, V, aim, capsule, ellipsoid, lathe, place, sheet, tube, bezier

NAME = "horseman"
BODY_HEIGHT_CM = 202.0
RENDER = dict(cell=256, pivot=(128, 184))

SEAT = 0.66                                  # how far the rider's feet-origin is lifted to sit him on the back
RIDER = srcrew.Fig("", (0, 0, SEAT), root="h_body")
BODY_C = Vector((0, 0.08, 0.92))             # barrel centre = h_body pivot

# leg joints, left side: front shoulder / knee / fetlock, hind hip / hock / fetlock
F_SH, F_KN, F_FT = Vector((0.15, -0.40, 0.84)), Vector((0.15, -0.47, 0.48)), Vector((0.15, -0.41, 0.13))
H_HP, H_HK, H_FT = Vector((0.17, 0.50, 0.86)), Vector((0.17, 0.66, 0.47)), Vector((0.17, 0.57, 0.13))
LEGS = {"hf": (F_SH, F_KN, F_FT, -1.0), "hh": (H_HP, H_HK, H_FT, 1.0)}      # last = pole direction along Y

IK_CHAINS = tuple((l + "_upper" + s, l + "_lower" + s, l + "_hoof" + s, "ik_" + l + s, "pole_" + l + s)
                  for l in ("hf", "hh") for s in (".L", ".R"))
SPEAR_FWD, SPEAR_BACK = 1.22, 0.78


def bones():
    B = [("root", (0, 0, 0), (0, 0.15, 0), None, True),
         ("h_body", tuple(BODY_C), (0, -0.2, 0.92), "root", True),
         ("h_neck", (0, -0.42, 1.02), (0, -0.72, 1.44), "h_body", True),
         ("h_head", (0, -0.70, 1.47), (0, -1.0, 1.2), "h_neck", True),
         ("h_tail", (0, 0.66, 1.05), (0, 0.9, 0.8), "h_body", True)]
    for s, sx in ((".L", 1), (".R", -1)):
        for l, (a, b, c, pd) in LEGS.items():
            def m(v):
                return (v.x * sx, v.y, v.z)
            toe = Vector((c.x, c.y - 0.09, 0.03))
            B += [(l + "_upper" + s, m(a), m(b), "h_body", True),
                  (l + "_lower" + s, m(b), m(c), l + "_upper" + s, True),
                  (l + "_hoof" + s, m(c), m(toe), l + "_lower" + s, True),
                  ("ik_" + l + s, m(c), m(toe), "root", False),
                  ("pole_" + l + s, m(b + Vector((0, pd, 0))), m(b + Vector((0, pd * 1.1, 0))), "root", False)]
    B += RIDER.bones()
    f = srcrew.FIST_R + RIDER.O
    B += [("smear", tuple(f), tuple(f + Vector((0, -0.1, 0))), "hand.R", True)]
    return B


def build_mesh(b):
    # ---------------------------------------------------------------- horse: barrel, chest, rump
    M = place(BODY_C, rx=90)                     # lathe axis -> -Y: local z = -(y - 0.08), local y = up
    b.add(lathe([(0.0, -0.56), (0.17, -0.54), (0.245, -0.42), (0.262, -0.2), (0.246, 0.05), (0.256, 0.3),
                 (0.235, 0.46), (0.15, 0.57), (0.0, 0.6)], seg=22, sx=0.9), "horse", "h_body", M)
    b.add(ellipsoid((0.215, 0.20, 0.27), seg=16, rings=10), "horse", "h_body", place((0, -0.40, 0.93)))
    b.add(ellipsoid((0.235, 0.25, 0.26), seg=16, rings=10), "horse", "h_body", place((0, 0.46, 0.95)))
    # ---------------------------------------------------------------- neck, mane, head
    b.add(capsule((0, -0.40, 1.02), (0, -0.70, 1.43), 0.175, 0.115, seg=14, squash=(0.72, 1.0)), "horse", "h_neck")
    mane = [V(0, -0.24, 1.14), V(0, -0.36, 1.26), V(0, -0.47, 1.39), V(0, -0.57, 1.50), V(0, -0.65, 1.57),
            V(0, -0.74, 1.585), V(0, -0.80, 1.52)]
    b.add(tube(mane, [0.03, 0.055, 0.06, 0.06, 0.055, 0.045, 0.02], seg=8, squash=(0.6, 1.0)), "hair", "h_neck")
    b.add(capsule((0, -0.69, 1.48), (0, -0.98, 1.215), 0.118, 0.082, seg=14, squash=(0.8, 1.0)), "horse", "h_head")
    b.add(ellipsoid((0.105, 0.11, 0.10), seg=12, rings=8), "horse", "h_head", place((0, -0.74, 1.40)))      # jaw
    b.add(ellipsoid((0.072, 0.07, 0.066), seg=10, rings=8), "hair", "h_head", place((0, -1.005, 1.19)))      # muzzle
    b.add(ellipsoid((0.034, 0.105, 0.03), seg=10, rings=6), "linen", "h_head", place((0, -0.865, 1.388), rx=43))  # blaze
    b.add(ellipsoid((0.022, 0.03, 0.028), seg=8, rings=6), "eye", "h_head", place((0.088, -0.77, 1.445)), mirror=True)
    b.add(capsule((0.062, -0.675, 1.555), (0.085, -0.69, 1.685), 0.04, 0.012, seg=8, caps=2), "horse", "h_head", mirror=True)
    ax = (V(0, -0.98, 1.215) - V(0, -0.69, 1.48)).normalized()
    for t, r in ((0.72, 0.098), ):
        c = V(0, -0.69, 1.48) + ax * 0.395 * t
        Mb = Matrix.Translation(c) @ aim(ax, (0, -1, 0), d0=(0, 0, 1), s0=(0, -1, 0)).to_matrix().to_4x4()
        b.add(lathe([(r, -0.016), (r, 0.016)], seg=14, sx=0.84), "leather_dark", "h_head", Mb)
    b.add(tube([V(0.085, -0.90, 1.31), V(0.105, -0.76, 1.44), V(0.07, -0.67, 1.56)], 0.014, seg=6), "leather_dark",
          "h_head", mirror=True)
    # ---------------------------------------------------------------- tail
    pts = bezier((0, 0.66, 1.06), (0, 0.88, 1.10), (0, 0.93, 0.76), (0, 0.87, 0.38), 7)
    b.add(tube(pts, [0.045, 0.065, 0.082, 0.09, 0.09, 0.08, 0.06, 0.02], seg=8, squash=(0.8, 1.0)), "hair", "h_tail")
    # ---------------------------------------------------------------- legs: bay above the knee, black stockings
    b.add(capsule(F_SH + V(0, 0, 0.06), F_KN, 0.10, 0.062, seg=12), "horse", "hf_upper.L", mirror=True)
    b.add(capsule(F_KN, F_FT, 0.056, 0.05, seg=10), "hair", "hf_lower.L", mirror=True)
    b.add(ellipsoid((0.066, 0.064, 0.06), seg=10, rings=6), "horse", "hf_upper.L", place(F_KN), mirror=True)
    b.add(ellipsoid((0.12, 0.19, 0.20), seg=12, rings=8), "horse", "hh_upper.L", place(H_HP + V(-0.01, 0.02, 0.0)), mirror=True)
    b.add(capsule(H_HP, H_HK, 0.105, 0.06, seg=12), "horse", "hh_upper.L", mirror=True)
    b.add(capsule(H_HK, H_FT, 0.056, 0.05, seg=10), "hair", "hh_lower.L", mirror=True)
    for l, (a, bb, c, pd) in LEGS.items():
        b.add(lathe([(0.0, 0.0), (0.074, 0.0), (0.07, 0.03), (0.056, 0.105), (0.0, 0.115)], seg=12, sy=1.15), "leather_dark",
              l + "_hoof.L", place((c.x, c.y - 0.03, 0.0)), mirror=True)
    # ---------------------------------------------------------------- tack: team saddle cloth, girth, breast strap
    b.add(lathe([(0.288, -0.27), (0.288, 0.33)], seg=18, sx=0.9, arc=(-32, 212), thick=0.034), "team", "h_body", M)
    for z0, z1 in ((-0.30, -0.245), (0.305, 0.36)):
        b.add(lathe([(0.296, z0), (0.296, z1)], seg=18, sx=0.9, arc=(-34, 214), thick=0.04), "team_trim", "h_body", M)
    for a0, a1 in ((-40, -29), (209, 220)):
        b.add(lathe([(0.296, -0.30), (0.296, 0.36)], seg=3, sx=0.9, arc=(a0, a1), thick=0.04), "team_trim", "h_body", M)
    b.add(lathe([(0.275, 0.05), (0.275, 0.12)], seg=20, sx=0.9, arc=(180, 360), thick=0.03), "leather_dark", "h_body", M)
    b.add(tube([V(0.225, -0.20, 1.02), V(0.215, -0.46, 0.97), V(0.10, -0.60, 0.94), V(-0.10, -0.60, 0.94),
                V(-0.215, -0.46, 0.97), V(-0.225, -0.20, 1.02)], 0.026, seg=6), "leather_dark", "h_body")
    b.add(ellipsoid((0.05, 0.025, 0.05), seg=10, rings=6), "bronze", "h_body", place((0, -0.625, 0.94)))

    # ---------------------------------------------------------------- rider
    RIDER.build(b, "rider")
    fa = lambda prim, mat, bone, M=None: RIDER.add(b, prim, mat, bone, M)  # noqa: E731
    # small round shield at the left fist, face toward -Y
    S = place(srcrew.FIST_L + V(0, -0.075, 0), rx=90)
    R = 0.215
    fa(lathe([(0.0, -0.02), (R, -0.02), (R, 0.016), (0.0, 0.016)], seg=22), "wood", "hand.L", S)
    fa(lathe([(0.0, 0.014), (R - 0.02, 0.014), (R - 0.03, 0.036), (R * 0.6, 0.058), (0.0, 0.07)], seg=22), "team", "hand.L", S)
    fa(lathe([(R - 0.04, 0.012), (R - 0.04, 0.042), (R - 0.01, 0.05), (R + 0.02, 0.038), (R + 0.024, 0.0),
              (R + 0.01, -0.026), (R - 0.04, -0.026)], seg=22, wrap=True), "bronze", "hand.L", S)
    fa(ellipsoid((0.07, 0.07, 0.058), seg=12, rings=8), "bronze", "hand.L", S @ place((0, 0, 0.066)))
    # spear along -Y through the right fist
    f = srcrew.FIST_R
    fa(capsule(f + V(0, SPEAR_BACK, 0), f + V(0, -SPEAR_FWD + 0.27, 0), 0.021, seg=8, caps=2), "wood", "hand.R")
    ys = [-SPEAR_FWD + 0.30, -SPEAR_FWD + 0.24, -SPEAR_FWD + 0.14, -SPEAR_FWD + 0.05, -SPEAR_FWD]
    fa(tube([f + V(0, y, 0) for y in ys], [0.03, 0.05, 0.058, 0.04, 0.0], seg=6, squash=(0.5, 1.0), up=(0, 0, 1)), "blade", "hand.R")
    fa(lathe([(0.034, -0.02), (0.034, 0.02)], seg=8), "bronze_dark", "hand.R", place(f + V(0, -SPEAR_FWD + 0.31, 0), rx=90))
    fa(capsule(f + V(0, SPEAR_BACK, 0), f + V(0, SPEAR_BACK + 0.07, 0), 0.026, 0.008, seg=8, caps=2), "bronze_dark", "hand.R")
    # thrust streak: a cone round the last metre of the shaft, scaled away on every frame but the strike
    fa(tube([f + V(0, -0.22, 0), f + V(0, -0.6, 0), f + V(0, -SPEAR_FWD + 0.1, 0)], [0.004, 0.045, 0.085], seg=8,
            squash=(1.0, 0.7)), "smear", "smear")


# ------------------------------------------------------------------------------------------------ poses
import sranim as A  # noqa: E402
from srkit import pose_lerp, pose_merge  # noqa: E402

STEP = 0.28            # ground per gallop frame: 8 frames = 224 cm per stride
REST = {"fl": Vector((F_FT.x, F_FT.y, F_FT.z)), "fr": Vector((-F_FT.x, F_FT.y, F_FT.z)),
        "hl": Vector((H_FT.x, H_FT.y, H_FT.z)), "hr": Vector((-H_FT.x, H_FT.y, H_FT.z))}
HOOF_BONE = {"fl": "ik_hf.L", "fr": "ik_hf.R", "hl": "ik_hh.L", "hr": "ik_hh.R"}
STAND = {"fl": ((0, -0.04, 0), 0), "fr": ((0, 0.03, 0), 0), "hl": ((0, 0.03, 0), 0), "hr": ((0, -0.05, 0), 0)}
R_FOOT_L = ((0.30, -0.12, 0.20), E(28, 0, 12))
R_FOOT_R = ((-0.30, -0.12, 0.20), E(28, 0, -12))


def ab(key, pos):
    """Hoof offset that puts hoof `key` at an absolute armature-space position."""
    return tuple(Vector(pos) - REST[key])


def make(rig, body=((0, 0, -0.012), (0, 0, 0)), neck=0.0, head=0.0, tail=0.0, neck_yaw=0.0, hooves=None,
         hips=((0, 0, 0), (0, 0, 0)), spine=(2, 0, 0), chest=(0, 0, 0), look=(0, -6),
         shield=((0.30, -0.20, 0.70), (0.45, -1, 0.05)), spear=((-0.34, -0.10, 0.66), (-0.05, -0.22, 1)),
         elbowL=(0.9, 0.5, 0.4), elbowR=(-0.9, 0.6, 0.5), smear=False, feet=None):
    """One full pose. Horse: body = (loc, (pitch, roll, yaw)), neck / head / tail in degrees (positive = forward
    and down; tail positive = streaming back), hooves = {fl, fr, hl, hr: (offset from the standing spot, curl)}.
    Rider (in the horse's frame): hips = (loc, (rx, ry, rz)), shield = (wrist, facing), spear = (fist, direction)."""
    p = {"root": {}, "h_body": {"loc": body[0], "rot": E(*body[1])}, "h_neck": {"rot": E(neck, 0, neck_yaw)},
         "h_head": {"rot": E(head, 0, 0)}, "h_tail": {"rot": E(tail, 0, 0)},
         "smear": {"scale": 1.0 if smear else 0.001}}
    hv = dict(STAND)
    hv.update(hooves or {})
    for k, (off, curl) in hv.items():
        p[HOOF_BONE[k]] = {"loc": tuple(off), "rot": E(curl, 0, 0)}
    for s in (".L", ".R"):
        p["pole_hf" + s] = {}
        p["pole_hh" + s] = {}
    qs = aim(spear[1], (0, 0, 1))
    fl, fr = feet or (R_FOOT_L, R_FOOT_R)
    p.update(RIDER.pose(rig, (hips[0], E(*hips[1])), E(*spine), E(*chest), look, fl, fr,
                        (shield[0], aim(shield[1], (0, 0, 1))), (srcrew.grip(spear[0], qs), qs),
                        kneeL=(0.9, -1.0, 0.7), kneeR=(-0.9, -1.0, 0.7), elbowL=elbowL, elbowR=elbowR))
    return p


def gallop_hoof(p, lift):
    """Hoof offset for phase p of an 8-frame gallop; 0 = this hoof's contact. On the ground for p = 0, 1/8, 2/8,
    moving back exactly STEP per frame (the distance the body covers), then folded up and swung forward."""
    p %= 1.0
    if p <= 0.25 + 1e-6:
        dy = -STEP + STEP * (p / 0.125)
        return (0, dy, 0.0), (-8.0 if p < 0.06 else (0.0 if p < 0.19 else 28.0))
    u = (p - 0.25) / 0.75
    dy = STEP * math.cos(math.pi * u)
    dz = 0.02 + lift * math.sin(math.pi * min(u / 0.92, 1.0)) ** 0.8
    return (0, dy, dz), 75.0 * math.sin(math.pi * u) ** 0.7


def animate(rig):
    sin, cos, pi = math.sin, math.cos, math.pi
    G = make(rig)

    # ---------------------------------------------------------------- idle: breathing, head nod, tail swish
    rig.new_action("idle", 8, loop=True, drive="time", fps=6.0)
    for i in range(8):
        up, lag = A.IDLE_UP[i] * A.PX_Z, A.IDLE_HAND_LAG[i] * A.PX_Z
        p = make(rig, body=((0, 0, -0.012 + up), (0, 0, 0)), neck=3.0 * A.IDLE_TILT[i], head=2.0 * A.IDLE_SWAY[i],
                 tail=-4 + 7 * A.IDLE_SWAY[i],
                 shield=((0.30, -0.20, 0.70 + lag), (0.45, -1, 0.05)),
                 spear=((-0.34, -0.10, 0.66 + lag), (-0.05, -0.22 - 0.02 * A.IDLE_TILT[i], 1)))
        rig.key(p, i)

    # ---------------------------------------------------------------- walk: a gallop. Hinds land on 0 and 1,
    # fores on 3 and 4, frame 7 is the gathered suspension.
    rig.new_action("walk", 8, loop=True, drive="distance", cycle_cm=STEP * 800, contact_frames=[0, 1, 3, 4],
                   roles=["hind L down", "hind R down", "hinds drive", "fore L down", "fore R down", "fores drive",
                          "lift off", "suspension"])
    for i in range(8):
        ph = i / 8
        hv = {"hl": gallop_hoof(ph, 0.20), "hr": gallop_hoof(ph - 0.125, 0.20),
              "fl": gallop_hoof(ph - 0.375, 0.30), "fr": gallop_hoof(ph - 0.5, 0.30)}
        z = -0.05 + 0.04 * cos(2 * pi * (ph - 0.875))
        pitch = -6.0 * cos(2 * pi * (ph - 0.03))
        rb = 0.018 * cos(2 * pi * (ph - 0.05))
        p = make(rig, body=((0, 0, z), (pitch, 0, 0)), neck=12 + 7 * cos(2 * pi * (ph - 0.55)),
                 head=-6 + 4 * cos(2 * pi * (ph - 0.65)), tail=58 + 10 * cos(2 * pi * (ph - 0.3)), hooves=hv,
                 hips=((0, -0.02, rb), (6, 0, 0)), spine=(10, 0, 0), chest=(6, 0, -4), look=(0, -4),
                 shield=((0.29, -0.27, 0.72 + rb), (0.4, -1, 0.1)),
                 spear=((-0.33, -0.20, 0.70 + rb * 1.5), (0.0, -1, 0.26 + 0.04 * cos(2 * pi * (ph - 0.2)))))
        rig.key(p, i)

    # ---------------------------------------------------------------- attack: gather, overhand thrust, recover
    rig.new_action("attack", 8, drive="attack_phase", strike_frame=3, windup_frames=[0, 1, 2],
                   recovery_frames=[3, 4, 5, 6, 7], windup_phase_map=[0.0, 0.30, 0.62],
                   recovery_phase_map=[0.0, 0.22, 0.42, 0.62, 0.82])
    eR = (-1.2, 0.6, 1.2)
    a0 = make(rig, body=((0, 0.04, -0.02), (-3, 0, 0)), neck=-6, tail=6,
              chest=(0, 0, -10), spear=((-0.36, -0.04, 0.98), (0.0, -1, -0.04)), elbowR=eR)
    a1 = make(rig, body=((0, 0.09, -0.01), (-8, 0, 0)), neck=-12, head=-4, tail=10,
              hooves={"fl": ((0, -0.05, 0.18), 45)},
              spine=(-4, 0, -8), chest=(-2, 0, -20), spear=((-0.37, 0.10, 1.04), (0.05, -1, -0.12)), elbowR=eR,
              shield=((0.26, -0.26, 0.74), (0.3, -1, 0.1)))
    a2 = make(rig, body=((0, 0.12, 0.0), (-12, 0, 0)), neck=-16, head=-6, tail=14,
              hooves={"fl": ((0, -0.10, 0.32), 65), "fr": ((0, -0.04, 0.20), 50)},
              spine=(-6, 0, -10), chest=(-3, 0, -26), spear=((-0.36, 0.17, 1.08), (0.08, -1, -0.18)), elbowR=eR,
              shield=((0.24, -0.28, 0.76), (0.25, -1, 0.12)))
    a3 = make(rig, body=((0, -0.20, -0.07), (6, 0, 0)), neck=18, head=8, tail=36,
              hooves={"fl": ((0, -0.30, 0), 0), "fr": ((0, -0.18, 0), 0)},
              hips=((0, -0.05, 0), (8, 0, 4)), spine=(14, 0, 6), chest=(8, 0, 14), look=(0, 2),
              spear=((-0.13, -0.60, 0.76), (0.05, -1, -0.31)), elbowR=(-1.0, 0.2, 0.4), smear=True,
              shield=((0.36, -0.10, 0.70), (0.7, -0.7, 0.0)))
    a4 = make(rig, body=((0, -0.17, -0.06), (4, 0, 0)), neck=14, head=4, tail=20,
              hooves={"fl": ((0, -0.30, 0), 0), "fr": ((0, -0.18, 0), 0)},
              hips=((0, -0.04, 0), (7, 0, 4)), spine=(12, 0, 5), chest=(7, 0, 12), look=(0, 0),
              spear=((-0.14, -0.55, 0.73), (0.05, -1, -0.29)), elbowR=(-1.0, 0.2, 0.4),
              shield=((0.36, -0.12, 0.70), (0.7, -0.7, 0.0)))
    a5 = make(rig, body=((0, -0.08, -0.03), (1, 0, 0)), neck=4, tail=-6,
              hooves={"fl": ((0, -0.20, 0.10), 30), "fr": ((0, -0.10, 0), 0)},
              spine=(6, 0, 2), chest=(3, 0, 4), spear=((-0.28, -0.32, 0.72), (0.0, -1, 0.12)))
    a6 = pose_lerp(a5, G, 0.6)
    a7 = pose_lerp(a6, G, 0.8)
    rig.key_all([a0, a1, a2, a3, a4, a5, a6, a7])

    # ---------------------------------------------------------------- hit: the horse throws its head up and shies
    rig.new_action("hit", 3, drive="time", fps=18.0)
    h0 = make(rig, body=((0.02, 0.07, 0.0), (-6, 3, 0)), neck=-20, head=-10, tail=30,
              hooves={"fl": ((0, -0.04, 0.14), 35)},
              spine=(-12, 0, 0), chest=(-8, 0, 2), look=(5, -22, 6),
              spear=((-0.40, 0.0, 0.76), (-0.2, -0.1, 1)), shield=((0.34, -0.12, 0.84), (0.4, -1, 0.4)))
    h1 = pose_lerp(h0, G, 0.6)
    h2 = pose_lerp(h1, G, 0.7)
    rig.key_all([h0, h1, h2])

    # ---------------------------------------------------------------- spawn: rears, paws the air, drops, settles
    rig.new_action("spawn", 6, drive="time", fps=14.0, active_frame=5)
    up_spear = lambda z: ((-0.36, -0.06, z), (0.0, -0.35, 1))  # noqa: E731
    s0 = make(rig, body=((0, 0.10, 0.0), (-28, 0, 0)), neck=-8, head=14, tail=18,
              hooves={"fl": ((0, -0.10, 0.52), 55), "fr": ((0, -0.22, 0.72), 65)},
              spine=(16, 0, 0), chest=(8, 0, 0), look=(0, 4), spear=up_spear(0.96))
    s1 = make(rig, body=((0, 0.12, 0.02), (-35, 0, 0)), neck=-10, head=18, tail=26,
              hooves={"fl": ((0, -0.24, 0.84), 70), "fr": ((0, -0.06, 0.62), 45)},
              spine=(18, 0, 0), chest=(9, 0, 0), look=(0, 6), spear=up_spear(1.04))
    s2 = make(rig, body=((0, 0.08, 0.0), (-22, 0, 0)), neck=-4, head=10, tail=10,
              hooves={"fl": ((0, -0.16, 0.44), 45), "fr": ((0, -0.20, 0.50), 45)},
              spine=(12, 0, 0), chest=(6, 0, 0), look=(0, 0), spear=up_spear(0.98))
    s3 = make(rig, body=((0, -0.05, -0.07), (5, 0, 0)), neck=14, head=4, tail=-10,
              hooves={"fl": ((0, -0.12, 0), 0), "fr": ((0, -0.05, 0), 0)},
              spine=(8, 0, 0), chest=(4, 0, 0), spear=((-0.34, -0.12, 0.70), (-0.03, -0.3, 1)))
    s4 = pose_lerp(G, s3, 0.25)
    rig.key_all([s0, s1, s2, s3, s4, G])

    # ---------------------------------------------------------------- death: shot from under him. The horse
    # buckles in front, rolls onto its left side, and the rider goes down with it, sprawled along its back.
    rig.new_action("death", 8, drive="time", fps=12.0, hold_last=True)
    d0 = make(rig, body=((0, 0.06, 0.0), (-8, 0, 0)), neck=-22, head=-12, tail=34,
              hooves={"fl": ((0, -0.05, 0.20), 45)},
              spine=(-14, 0, 0), chest=(-10, 0, 4), look=(6, -28, 8),
              spear=((-0.42, 0.05, 0.80), (-0.3, 0.1, 1)), shield=((0.36, -0.10, 0.86), (0.4, -1, 0.5)))
    d1 = make(rig, body=((0, -0.06, -0.15), (13, 10, 0)), neck=14, head=20, tail=10,
              hooves={"fl": ((0, 0.16, 0.08), 75), "fr": ((0, 0.10, 0.05), 65)},
              spine=(14, 0, 0), chest=(10, 0, 0), look=(0, 14),
              spear=((-0.36, -0.20, 0.62), (-0.1, -1, -0.3)), shield=((0.34, -0.22, 0.62), (0.5, -0.8, -0.3)))
    d2 = make(rig, body=((0.05, -0.12, -0.38), (18, 30, 0)), neck=28, head=20, tail=0,
              hooves={"fl": ((0, 0.20, 0.06), 85), "fr": ((0, 0.15, 0.05), 85)},
              hips=((0.03, 0, 0.03), (0, -8, 0)), spine=(10, 0, 4), chest=(8, 0, 4), look=(0, 20),
              spear=((-0.40, -0.16, 0.66), (-0.2, -1, -0.1)), shield=((0.38, -0.16, 0.64), (0.7, -0.6, 0)))
    d3 = make(rig, body=((0.12, -0.12, -0.56), (8, 62, 0)), neck=22, head=14, tail=-8, neck_yaw=6,
              hooves={"fl": (ab("fl", (-0.45, -0.35, 0.12)), 60), "fr": (ab("fr", (-0.52, -0.20, 0.26)), 60),
                      "hl": (ab("hl", (-0.40, 0.62, 0.10)), 20), "hr": (ab("hr", (-0.52, 0.74, 0.26)), 20)},
              hips=((0.06, 0, 0.08), (0, -6, 4)), spine=(4, 0, 10), chest=(2, 0, 8), look=(10, 0, 10),
              spear=((-0.46, -0.05, 0.84), (-0.1, -1, 0.1)), shield=((0.42, -0.06, 0.76), (0.6, -0.5, 0.5)),
              elbowL=(1.2, 0.2, 0.8), elbowR=(-1.2, 0.2, 0.9))
    lying = dict(hips=((0.09, 0, 0.14), (0, -4, 8)), spine=(-4, 0, 14), chest=(-4, 0, 10), look=(20, -8, 16),
                 spear=((-0.40, 0.02, 1.00), (0.0, -1, 0.0)), shield=((0.44, -0.02, 0.86), (0.2, -0.3, 1)),
                 elbowL=(1.2, 0.2, 0.9), elbowR=(-1.2, 0.2, 1.0))
    d4 = make(rig, body=((0.15, -0.10, -0.655), (0, 94, 0)), neck=16, head=8, tail=-16, neck_yaw=8,
              hooves={"fl": (ab("fl", (-0.80, -0.55, 0.22)), 30), "fr": (ab("fr", (-0.78, -0.30, 0.46)), 30),
                      "hl": (ab("hl", (-0.80, 0.52, 0.22)), 10), "hr": (ab("hr", (-0.78, 0.82, 0.46)), 10)}, **lying)
    d5 = make(rig, body=((0.15, -0.10, -0.69), (0, 88, 0)), neck=20, head=10, tail=-10, neck_yaw=12,
              hooves={"fl": (ab("fl", (-0.66, -0.56, 0.10)), 30), "fr": (ab("fr", (-0.56, -0.62, 0.30)), 50),
                      "hl": (ab("hl", (-0.74, 0.42, 0.10)), 0), "hr": (ab("hr", (-0.66, 0.66, 0.30)), 20)}, **lying)
    d7 = make(rig, body=((0.15, -0.10, -0.69), (0, 90, 0)), neck=26, head=12, tail=-6, neck_yaw=17,
              hooves={"fl": (ab("fl", (-0.58, -0.60, 0.08)), 45), "fr": (ab("fr", (-0.46, -0.68, 0.26)), 70),
                      "hl": (ab("hl", (-0.70, 0.36, 0.08)), 10), "hr": (ab("hr", (-0.58, 0.60, 0.26)), 30)},
              **dict(lying, look=(26, -4, 22), spear=((-0.38, 0.0, 1.02), (0.05, -1, 0.0))))
    d6 = pose_lerp(d5, d7, 0.6)
    rig.key_all([d0, d1, d2, d3, d4, d5, d6, d7])
