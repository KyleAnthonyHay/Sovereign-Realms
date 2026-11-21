"""Red deer: the wildlife of the realm (ASRWildlife). A stag with a full head of antlers; char_doe.py is the hind.

A quadruped on the horse's rig plan (char_horseman.py, h_* bones, legs on IK with hoof targets on the ground) at
about four fifths of the pony's size and much lighter in the leg: a russet coat, a pale rump patch and scut, dark
muzzle and stockings, big ears. Rendered in the troops' 160 px cell at their 1.75 cm per pixel.

The sheet keeps the troops' six blocks (make_sheets.py) so the same card, material and frame rules serve, but the
blocks mean other things for an animal (ASRWildlife reads them):
    spawn   graze: head down in the grass, cropping (6 frames, looped)
    idle    standing: breathing, an ear and the scut flicking (8, looped)
    walk    the walk, a four-beat gait (8, by distance, 96 cm a cycle)
    attack  the bolt: a bounding gallop, scut up (8, by distance, 200 cm a cycle)
    hit     the start: head thrown up, the frozen stare before it runs (3)
    death   looking round: the head swings one way and the other (8, looped)
"""

import math

from mathutils import Vector

import srkit as K
from srkit import E, V, capsule, ellipsoid, lathe, place, tube, bezier

NAME = "deer"
BODY_HEIGHT_CM = 128.0
STAG = True

S = 0.82                                     # against the pony


def P(x, y, z):
    return Vector((x * S, y * S, z * S))


BODY_C = P(0, 0.08, 0.92)                    # barrel centre = h_body pivot
# leg joints, left side: front shoulder / knee / fetlock, hind hip / hock / fetlock
F_SH, F_KN, F_FT = P(0.125, -0.40, 0.84), P(0.125, -0.47, 0.48), P(0.125, -0.41, 0.12)
H_HP, H_HK, H_FT = P(0.14, 0.50, 0.86), P(0.14, 0.66, 0.47), P(0.14, 0.57, 0.12)
LEGS = {"hf": (F_SH, F_KN, F_FT, -1.0), "hh": (H_HP, H_HK, H_FT, 1.0)}      # last = pole direction along Y

IK_CHAINS = tuple((l + "_upper" + s, l + "_lower" + s, l + "_hoof" + s, "ik_" + l + s, "pole_" + l + s)
                  for l in ("hf", "hh") for s in (".L", ".R"))
IK_PREFIXES = ()                             # no biped limbs on this rig

NECK_A, NECK_B = P(0, -0.40, 1.04), P(0, -0.64, 1.50)
HEAD_A, HEAD_B = P(0, -0.63, 1.53), P(0, -0.93, 1.36)


def bones():
    B = [("root", (0, 0, 0), (0, 0.15, 0), None, True),
         ("h_body", tuple(BODY_C), tuple(P(0, -0.2, 0.92)), "root", True),
         ("h_neck", tuple(NECK_A), tuple(NECK_B), "h_body", True),
         ("h_head", tuple(HEAD_A), tuple(HEAD_B), "h_neck", True),
         ("h_tail", tuple(P(0, 0.64, 1.10)), tuple(P(0, 0.78, 0.98)), "h_body", True)]
    for s, sx in ((".L", 1), (".R", -1)):
        for l, (a, b, c, pd) in LEGS.items():
            def m(v):
                return (v.x * sx, v.y, v.z)
            toe = Vector((c.x, c.y - 0.07, 0.025))
            B += [(l + "_upper" + s, m(a), m(b), "h_body", True),
                  (l + "_lower" + s, m(b), m(c), l + "_upper" + s, True),
                  (l + "_hoof" + s, m(c), m(toe), l + "_lower" + s, True),
                  ("ik_" + l + s, m(c), m(toe), "root", False),
                  ("pole_" + l + s, m(b + Vector((0, pd, 0))), m(b + Vector((0, pd * 1.1, 0))), "root", False)]
    return B


def build_mesh(b, stag=None):
    stag = STAG if stag is None else stag
    # ---------------------------------------------------------------- barrel: deep chest, tucked belly, round rump
    M = place(BODY_C, rx=90)                     # lathe axis -> -Y
    b.add(lathe([(0.0, -0.46), (0.11, -0.44), (0.165, -0.34), (0.178, -0.16), (0.16, 0.04), (0.158, 0.24),
                 (0.15, 0.37), (0.10, 0.46), (0.0, 0.49)], seg=20, sx=0.84), "horse", "h_body", M)
    b.add(ellipsoid((0.145, 0.15, 0.20), seg=14, rings=9), "horse", "h_body", place(P(0, -0.40, 0.94)))
    b.add(ellipsoid((0.155, 0.17, 0.19), seg=14, rings=9), "horse", "h_body", place(P(0, 0.46, 0.96)))
    b.add(ellipsoid((0.105, 0.06, 0.125), seg=12, rings=8), "linen", "h_body", place(P(0, 0.635, 0.985)))        # rump patch
    b.add(ellipsoid((0.10, 0.20, 0.05), seg=12, rings=6), "linen", "h_body", place(P(0, 0.06, 0.72)))            # pale belly
    # ---------------------------------------------------------------- neck, head, ears
    b.add(capsule(NECK_A, NECK_B, 0.105 if stag else 0.085, 0.062 if stag else 0.052, seg=12, squash=(0.74, 1.0)), "horse", "h_neck")
    if stag:                                                                                                   # the stag's dark ruff
        b.add(capsule(NECK_A + V(0, -0.02, -0.07), NECK_A + V(0, -0.13, 0.12), 0.085, 0.06, seg=10, squash=(0.8, 1.0)), "hair", "h_neck")
    b.add(capsule(HEAD_A, HEAD_B, 0.068, 0.038, seg=12, squash=(0.82, 1.0)), "horse", "h_head")
    b.add(ellipsoid((0.066, 0.075, 0.066), seg=12, rings=8), "horse", "h_head", place(HEAD_A + V(0, -0.025, -0.03)))
    b.add(ellipsoid((0.036, 0.034, 0.032), seg=10, rings=6), "hair", "h_head", place(HEAD_B + V(0, -0.012, -0.004)))   # muzzle
    b.add(ellipsoid((0.017, 0.022, 0.02), seg=8, rings=6), "eye", "h_head", place(HEAD_A + V(0.056, -0.075, 0.0)), mirror=True)
    ear0 = HEAD_A + V(0.045, 0.02, 0.045)
    b.add(capsule(ear0, ear0 + V(0.115, 0.05, 0.085), 0.034, 0.012, seg=8, caps=2, squash=(1.0, 0.5)), "horse", "h_head", mirror=True)
    b.add(capsule(ear0 + V(0.02, 0.0, 0.012), ear0 + V(0.095, 0.03, 0.072), 0.017, 0.006, seg=6, caps=2, squash=(1.0, 0.4)), "linen", "h_head", mirror=True)
    # ---------------------------------------------------------------- antlers: a swept beam with four tines
    if stag:
        a0 = HEAD_A + V(0.034, -0.01, 0.06)
        beam = [a0, a0 + V(0.065, 0.055, 0.15), a0 + V(0.145, 0.12, 0.30), a0 + V(0.175, 0.13, 0.45), a0 + V(0.13, 0.10, 0.56)]
        b.add(tube(beam, [0.021, 0.019, 0.017, 0.014, 0.006], seg=6), "feather", "h_head", mirror=True)
        for base, tip, r in ((a0 + V(0.012, 0.0, 0.03), a0 + V(0.035, -0.17, 0.10), 0.014),          # brow tine
                             (beam[1], beam[1] + V(0.045, -0.16, 0.09), 0.013),                       # bez
                             (beam[2], beam[2] + V(0.07, -0.13, 0.10), 0.012),                        # trez
                             (beam[3], beam[3] + V(0.085, -0.02, 0.10), 0.011)):                      # crown fork
            b.add(tube([base, (base + tip) * 0.5 + V(0, 0, 0.012), tip], [r, r * 0.8, 0.004], seg=5), "feather", "h_head", mirror=True)
    # ---------------------------------------------------------------- scut: short, white beneath
    pts = bezier(tuple(P(0, 0.64, 1.10)), tuple(P(0, 0.72, 1.10)), tuple(P(0, 0.78, 1.02)), tuple(P(0, 0.78, 0.92)), 4)
    b.add(tube(pts, [0.03, 0.04, 0.04, 0.03, 0.012], seg=7, squash=(0.9, 1.0)), "linen", "h_tail")
    b.add(tube([p + V(0, -0.012, 0.012) for p in pts[:4]], [0.024, 0.03, 0.03, 0.02], seg=6, squash=(0.9, 0.7)), "horse", "h_tail")
    # ---------------------------------------------------------------- legs: slender, dark below the knee
    b.add(capsule(F_SH + V(0, 0, 0.05), F_KN, 0.062, 0.034, seg=10), "horse", "hf_upper.L", mirror=True)
    b.add(capsule(F_KN, F_FT, 0.03, 0.026, seg=8), "leather_dark", "hf_lower.L", mirror=True)
    b.add(ellipsoid((0.036, 0.036, 0.034), seg=8, rings=6), "horse", "hf_upper.L", place(F_KN), mirror=True)
    b.add(ellipsoid((0.085, 0.14, 0.15), seg=10, rings=8), "horse", "hh_upper.L", place(H_HP + V(-0.01, 0.015, 0.0)), mirror=True)
    b.add(capsule(H_HP, H_HK, 0.07, 0.036, seg=10), "horse", "hh_upper.L", mirror=True)
    b.add(capsule(H_HK, H_FT, 0.031, 0.026, seg=8), "leather_dark", "hh_lower.L", mirror=True)
    for l, (a, bb, c, pd) in LEGS.items():
        b.add(lathe([(0.0, 0.0), (0.04, 0.0), (0.038, 0.025), (0.03, 0.08), (0.0, 0.09)], seg=10, sy=1.2), "hair",
              l + "_hoof.L", place((c.x, c.y - 0.02, 0.0)), mirror=True)


# ------------------------------------------------------------------------------------------------ poses
import sranim as A  # noqa: E402
from srkit import pose_lerp  # noqa: E402

HOOF_BONE = {"fl": "ik_hf.L", "fr": "ik_hf.R", "hl": "ik_hh.L", "hr": "ik_hh.R"}
STAND = {"fl": ((0, -0.03, 0), 0), "fr": ((0, 0.025, 0), 0), "hl": ((0, 0.025, 0), 0), "hr": ((0, -0.04, 0), 0)}
WALK_STEP = 0.12       # ground per walk frame: 8 frames = 96 cm a cycle
RUN_STEP = 0.25        # ground per gallop frame: 8 frames = 200 cm a bound


def make(rig, body=((0, 0, -0.01), (0, 0, 0)), neck=0.0, head=0.0, tail=0.0, neck_yaw=0.0, head_yaw=0.0, hooves=None):
    """One pose: body = (loc, (pitch, roll, yaw)); neck / head in degrees (positive = forward and down); tail
    positive = lifted; hooves = {fl, fr, hl, hr: (offset from the standing spot, curl)}."""
    p = {"root": {}, "h_body": {"loc": body[0], "rot": E(*body[1])}, "h_neck": {"rot": E(neck, 0, neck_yaw)},
         "h_head": {"rot": E(head, 0, head_yaw)}, "h_tail": {"rot": E(-tail, 0, 0)}}
    hv = dict(STAND)
    hv.update(hooves or {})
    for k, (off, curl) in hv.items():
        p[HOOF_BONE[k]] = {"loc": tuple(off), "rot": E(curl, 0, 0)}
    for s in (".L", ".R"):
        p["pole_hf" + s] = {}
        p["pole_hh" + s] = {}
    return p


def walk_hoof(p, lift):
    """Hoof offset for phase p of the 8-frame walk; 0 = this hoof's contact. Five frames on the ground moving back
    exactly WALK_STEP a frame (what the body covers), three in the air swinging forward."""
    p %= 1.0
    if p <= 0.625 + 1e-6:
        return (0, -2.5 * WALK_STEP + WALK_STEP * (p * 8.0), 0.0), 0.0
    u = (p - 0.625) / 0.375
    dy = 2.5 * WALK_STEP - 5.0 * WALK_STEP * (0.5 - 0.5 * math.cos(math.pi * u))
    return (0, dy, 0.02 + lift * math.sin(math.pi * u)), 55.0 * math.sin(math.pi * u)


def gallop_hoof(p, lift):
    """Hoof offset for phase p of the 8-frame bound (see char_horseman.gallop_hoof): two frames on the ground."""
    p %= 1.0
    if p <= 0.25 + 1e-6:
        dy = -RUN_STEP + RUN_STEP * (p / 0.125)
        return (0, dy, 0.0), (-8.0 if p < 0.06 else (0.0 if p < 0.19 else 28.0))
    u = (p - 0.25) / 0.75
    dy = RUN_STEP * math.cos(math.pi * u)
    dz = 0.02 + lift * math.sin(math.pi * min(u / 0.92, 1.0)) ** 0.8
    return (0, dy, dz), 80.0 * math.sin(math.pi * u) ** 0.7


def animate(rig):
    cos, pi = math.cos, math.pi
    G = make(rig)

    # ---------------------------------------------------------------- idle: breathing, an ear turn, a flick of the scut
    rig.new_action("idle", 8, loop=True, drive="time", fps=5.0)
    for i in range(8):
        up = A.IDLE_UP[i] * A.PX_Z
        rig.key(make(rig, body=((0, 0, -0.01 + up), (0, 0, 0)), neck=-4 + 2.5 * A.IDLE_TILT[i], head=2.0 * A.IDLE_SWAY[i],
                     tail=18 if i in (5, 6) else 0, head_yaw=4.0 * A.IDLE_TILT[i]), i)

    # ---------------------------------------------------------------- walk: hind left, fore left, hind right, fore right
    rig.new_action("walk", 8, loop=True, drive="distance", cycle_cm=WALK_STEP * 800, contact_frames=[0, 2, 4, 6],
                   roles=["hind L down", "", "fore L down", "", "hind R down", "", "fore R down", ""])
    for i in range(8):
        ph = i / 8
        hv = {"hl": walk_hoof(ph, 0.09), "fl": walk_hoof(ph - 0.25, 0.11), "hr": walk_hoof(ph - 0.5, 0.09), "fr": walk_hoof(ph - 0.75, 0.11)}
        z = -0.015 + 0.012 * cos(4 * pi * ph)
        rig.key(make(rig, body=((0, 0, z), (1.5 * cos(4 * pi * (ph - 0.1)), 0, 0)), neck=10 + 5 * cos(4 * pi * (ph - 0.15)),
                     head=4 + 3 * cos(4 * pi * (ph - 0.3)), tail=4, hooves=hv), i)

    # ---------------------------------------------------------------- attack block = the bolt. Hinds land on 0 and 1,
    # fores on 3 and 4, frame 7 is the gathered leap; the scut stands up white.
    rig.new_action("attack", 8, loop=True, drive="distance", cycle_cm=RUN_STEP * 800, contact_frames=[0, 1, 3, 4],
                   roles=["hind L down", "hind R down", "hinds drive", "fore L down", "fore R down", "fores drive", "lift off", "leap"])
    for i in range(8):
        ph = i / 8
        hv = {"hl": gallop_hoof(ph, 0.22), "hr": gallop_hoof(ph - 0.125, 0.22), "fl": gallop_hoof(ph - 0.375, 0.30), "fr": gallop_hoof(ph - 0.5, 0.30)}
        z = -0.02 + 0.075 * cos(2 * pi * (ph - 0.875))
        pitch = -8.0 * cos(2 * pi * (ph - 0.03))
        rig.key(make(rig, body=((0, 0, z), (pitch, 0, 0)), neck=16 + 8 * cos(2 * pi * (ph - 0.55)),
                     head=-10 + 4 * cos(2 * pi * (ph - 0.65)), tail=75, hooves=hv), i)

    # ---------------------------------------------------------------- hit block = the start: head up, frozen
    rig.new_action("hit", 3, drive="time", fps=8.0)
    h0 = make(rig, body=((0, 0.03, -0.05), (-3, 0, 0)), neck=-10, head=-6, tail=40, hooves={"fl": ((0, -0.03, 0.06), 25)})
    h1 = make(rig, body=((0, 0.02, -0.01), (-2, 0, 0)), neck=-17, head=-4, tail=60)
    h2 = make(rig, body=((0, 0.01, 0.0), (-1, 0, 0)), neck=-19, head=-2, tail=70)
    rig.key_all([h0, h1, h2])

    # ---------------------------------------------------------------- spawn block = grazing: head down, cropping
    rig.new_action("spawn", 6, loop=True, drive="time", fps=4.0)
    for i, (bob, step) in enumerate(((0, 0.0), (5, 0.0), (0, 0.0), (6, 0.0), (-3, 0.05), (3, 0.05))):
        rig.key(make(rig, body=((0, -0.01, -0.035), (7, 0, 0)), neck=90 + bob, head=32 + bob * 0.8, tail=6 if i == 3 else 0,
                     hooves={"fl": ((0, -0.10 - step, 0), 0), "fr": ((0, 0.05, 0), 0)}), i)

    # ---------------------------------------------------------------- death block = looking round
    rig.new_action("death", 8, loop=True, drive="time", fps=3.0)
    for i, yaw in enumerate((0, 16, 30, 30, 14, -6, -26, -26)):
        rig.key(make(rig, body=((0, 0, -0.01), (0, 0, 0)), neck=-12, head=-2, neck_yaw=yaw * 0.6, head_yaw=yaw * 0.5,
                     tail=20 if i in (2, 6) else 0), i)
