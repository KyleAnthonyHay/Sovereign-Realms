"""Catapult: a bronze-age stone thrower on four spoked wheels, with a crew of two.

A timber frame, a twisted-rope torsion bundle between bronze washers, one throwing arm with a cup, an A-frame
with a padded stop bar, a windlass at the rear. Team colour: a round shield hung on each side, a banner on the
stop bar, and the crew's headcloths, sashes and hems.

One armature: the machine (frame, uprights, arm, stone, windlass, four wheels, banner, chips, smear) and two
srcrew.Fig figures, a_ on the left and b_ on the right, who stand at the rear in every state so nothing pops
between animations. Rendered in a 256 px cell at the troops' 1.75 cm per pixel.

Crew poses are authored once, for the left man; the right man gets the mirror image (see crew()).
"""

import math

from mathutils import Matrix, Quaternion, Vector

import srkit as K
import srcrew
from srkit import E, V, aim, capsule, ellipsoid, lathe, place, sheet, tube

NAME = "catapult"
BODY_HEIGHT_CM = 200.0
RENDER = dict(cell=256, pivot=(128, 184))
IK_PREFIXES = ("a_", "b_")

WR = 0.395                                    # wheel radius: 124 cm of travel = 3 x 60 degrees, the spoke spacing
WHEELS = {"wheel_fl": (0.66, -0.60), "wheel_fr": (-0.66, -0.60), "wheel_rl": (0.66, 0.60), "wheel_rr": (-0.66, 0.60)}
PV = Vector((0, 0.12, 0.60))                  # arm pivot, in the torsion bundle
ARM_D = Vector((0, -0.42, 0.96)).normalized() # arm direction at rest, leaning on the stop bar
ARM_L = 1.42
TIP = PV + ARM_D * ARM_L
COCK = -105.6                                 # arm rotation when wound back: 8 degrees above the horizontal
CUP_N = E(-COCK, 0, 0) @ Vector((0, 0, 1))    # the cup's opening at rest, so that it faces up when cocked
STONE_C = TIP + CUP_N * 0.12
WL = Vector((0, 0.80, 0.76))                  # windlass axis
CREW_Y = 1.28
CA = srcrew.Fig("a_", (0.50, CREW_Y, 0))
CB = srcrew.Fig("b_", (-0.50, CREW_Y, 0))
CHIP_C = Vector((0.36, -0.52, 1.0))


def bones():
    B = [("root", (0, 0, 0), (0, 0.15, 0), None, True),
         ("frame", (0, 0, 0.56), (0, -0.3, 0.56), "root", True),
         ("uprights", (0, -0.30, 0.62), (0, -0.44, 1.58), "frame", True),
         ("banner", (0, -0.535, 1.52), (0, -0.535, 1.2), "uprights", True),
         ("arm", tuple(PV), tuple(TIP), "frame", True),
         ("stone", tuple(STONE_C), tuple(STONE_C + Vector((0, 0, 0.1))), "arm", True),
         ("windlass", tuple(WL), tuple(WL + Vector((0, 0.1, 0))), "frame", True),
         ("chips", tuple(CHIP_C), tuple(CHIP_C + Vector((0, 0, 0.1))), "root", True),
         ("smear", tuple(PV), tuple(PV + Vector((0, 0, 0.1))), "frame", True)]
    for n, (x, y) in WHEELS.items():
        B.append((n, (x, y, WR), (x, y + 0.1, WR), "frame", True))
    return B + CA.bones() + CB.bones()


def box(half):
    return ellipsoid(half, seg=12, rings=8, e1=0.28, e2=0.28)


def build_mesh(b):
    # ---------------------------------------------------------------- frame
    for sx in (1, -1):
        b.add(box((0.078, 1.0, 0.082)), "wood", "frame", place((sx * 0.42, 0, 0.56)))
        for y in (-0.60, 0.60):
            b.add(box((0.07, 0.10, 0.07)), "leather_dark", "frame", place((sx * 0.42, y, 0.455)))
        # torsion washer and its lever pin, outside the beam
        b.add(lathe([(0.0, -0.03), (0.15, -0.03), (0.16, 0.0), (0.15, 0.03), (0.0, 0.03)], seg=14), "bronze", "frame",
              place((sx * 0.515, 0.12, 0.60), ry=90))
        b.add(capsule((sx * 0.55, 0.12, 0.47), (sx * 0.55, 0.12, 0.73), 0.024, seg=6, caps=2), "bronze_dark", "frame")
        # team shield hung on the side
        S = place((sx * 0.50, -0.20, 0.66), ry=sx * 90)
        b.add(lathe([(0.0, -0.01), (0.17, -0.01), (0.17, 0.02), (0.0, 0.02)], seg=18), "bronze", "frame", S)
        b.add(lathe([(0.0, 0.018), (0.145, 0.018), (0.13, 0.04), (0.0, 0.055)], seg=18), "team", "frame", S)
        b.add(ellipsoid((0.05, 0.05, 0.04), seg=10, rings=6), "bronze", "frame", S @ place((0, 0, 0.05)))
    for y in (-0.93, 0.93):
        b.add(box((0.52, 0.075, 0.075)), "wood", "frame", place((0, y, 0.56)))
    for y in (-0.60, 0.60):
        b.add(capsule((-0.74, y, WR), (0.74, y, WR), 0.042, seg=8, caps=2), "leather_dark", "frame")
    b.add(lathe([(0.0, -0.345), (0.125, -0.345), (0.135, -0.2), (0.125, 0.0), (0.135, 0.2), (0.125, 0.345), (0.0, 0.345)],
                seg=14), "rope", "frame", place(PV, ry=90))
    b.add(box((0.34, 0.5, 0.025)), "wood", "frame", place((0, -0.42, 0.50)))                 # deck planks, front half

    # ---------------------------------------------------------------- uprights and the padded stop bar
    for sx in (1, -1):
        b.add(capsule((sx * 0.42, -0.30, 0.62), (sx * 0.40, -0.44, 1.60), 0.068, 0.06, seg=10), "wood", "uprights")
        b.add(capsule((sx * 0.42, -0.90, 0.62), (sx * 0.40, -0.48, 1.42), 0.05, seg=8), "wood", "uprights")
        b.add(capsule((sx * 0.42, 0.34, 0.64), (sx * 0.40, -0.40, 1.30), 0.042, seg=8), "wood", "uprights")
        b.add(lathe([(0.078, -0.03), (0.078, 0.03)], seg=10), "rope", "uprights", place((sx * 0.40, -0.44, 1.52)))
    b.add(box((0.52, 0.07, 0.078)), "wood", "uprights", place((0, -0.44, 1.60)))
    b.add(ellipsoid((0.27, 0.10, 0.115), seg=14, rings=8), "linen", "uprights", place((0, -0.345, 1.585)))
    for x in (-0.17, 0.17):
        b.add(lathe([(0.118, -0.016), (0.118, 0.016)], seg=12, sx=0.9), "rope", "uprights", place((x, -0.35, 1.585), ry=90))
    # banner hanging from the front of the bar
    g = [[V(-0.2, -0.535, 1.56), V(0.2, -0.535, 1.56)], [V(-0.2, -0.545, 1.36), V(0.2, -0.545, 1.36)],
         [V(-0.2, -0.54, 1.22), V(0.2, -0.54, 1.22)]]
    b.add(sheet(g, 0.03), "team", "banner")
    b.add(sheet([[V(-0.2, -0.542, 1.225), V(0.2, -0.542, 1.225)], [V(-0.2, -0.54, 1.16), V(0.0, -0.54, 1.10),
                                                                   V(0.2, -0.54, 1.16)][::2]], 0.034), "team_trim", "banner")

    # ---------------------------------------------------------------- arm, cup, stone
    b.add(tube([PV - ARM_D * 0.10, PV + ARM_D * 0.5, TIP - ARM_D * 0.05], [0.07, 0.062, 0.046], seg=10), "wood", "arm")
    for t in (0.22, 0.5, 0.78):
        c = PV + ARM_D * ARM_L * t
        Mr = Matrix.Translation(c) @ aim(ARM_D, (0, -1, 0), d0=(0, 0, 1), s0=(0, -1, 0)).to_matrix().to_4x4()
        b.add(lathe([(0.074 - 0.02 * t, -0.03), (0.074 - 0.02 * t, 0.03)], seg=10), "rope" if t != 0.5 else "bronze", "arm", Mr)
    Mc = Matrix.Translation(TIP) @ aim(CUP_N, (1, 0, 0), d0=(0, 0, 1), s0=(1, 0, 0)).to_matrix().to_4x4()
    b.add(lathe([(0.0, -0.045), (0.10, -0.035), (0.155, 0.02), (0.165, 0.05), (0.14, 0.045), (0.09, 0.0), (0.0, -0.01)],
                seg=14), "wood", "arm", Mc)
    b.add(lathe([(0.15, 0.03), (0.172, 0.04), (0.172, 0.062), (0.15, 0.058)], seg=14, wrap=True), "bronze", "arm", Mc)
    b.add(ellipsoid((0.125, 0.115, 0.105), seg=10, rings=7, e1=0.85, e2=0.9), "stone", "stone", place(STONE_C, rx=20, rz=30))

    # ---------------------------------------------------------------- windlass with four handspikes at each end
    b.add(capsule((-0.60, WL.y, WL.z), (0.60, WL.y, WL.z), 0.062, seg=10, caps=2), "wood", "windlass")
    b.add(lathe([(0.075, -0.2), (0.075, 0.2)], seg=10), "rope", "windlass", place(WL, ry=90))
    for sx in (1, -1):
        b.add(box((0.06, 0.07, 0.07)), "leather_dark", "frame", place((sx * 0.42, WL.y, 0.675)))
        for k in range(4):
            a = math.radians(45 + 90 * k)
            c = V(sx * 0.57, WL.y, WL.z)
            b.add(capsule(c, c + V(0, math.cos(a) * 0.21, math.sin(a) * 0.21), 0.022, seg=6, caps=2), "wood", "windlass")

    # ---------------------------------------------------------------- wheels: felloe, six spokes, bronze hub
    for n, (x, y) in WHEELS.items():
        sx = 1 if x > 0 else -1
        M = place((x, y, WR), ry=90)
        b.add(lathe([(0.30, -0.042), (WR, -0.042), (WR, 0.042), (0.30, 0.042)], seg=24, wrap=True), "wood", n, M)
        for k in range(6):
            a = math.radians(60 * k)
            b.add(capsule((0, 0, 0), (0.31 * math.cos(a), 0.31 * math.sin(a), 0), 0.033, seg=6, caps=1), "wood", n, M)
        b.add(lathe([(0.0, -0.06), (0.085, -0.06), (0.085, 0.06), (0.05, 0.085), (0.0, 0.09)], seg=12), "bronze", n,
              place((x, y, WR), ry=sx * 90))

    # ---------------------------------------------------------------- splinters (hit / death), scaled away otherwise
    for k, (dx, dy, dz, mat) in enumerate(((0.0, 0.0, 0.0, "wood"), (0.14, -0.06, 0.10, "straw"), (-0.12, 0.05, 0.14, "wood"),
                                           (0.06, 0.12, -0.10, "straw"), (-0.08, -0.12, -0.06, "wood"), (0.16, 0.08, 0.02, "wood"),
                                           (-0.02, -0.04, 0.2, "straw"))):
        c = CHIP_C + V(dx, dy, dz)
        d = V(math.sin(k * 2.3), math.cos(k * 1.7), math.sin(k * 1.1 + 1)).normalized() * 0.075
        b.add(capsule(c - d, c + d, 0.03, 0.012, seg=5, caps=1), mat, "chips")

    # ---------------------------------------------------------------- release smear: the arc the cup just swept
    grid = []
    for i in range(13):
        t = i / 12
        ph = math.radians(-78 + 70 * t)                                    # angle from the rest direction, back = negative
        d = E(math.degrees(ph), 0, 0) @ ARM_D
        w = 0.05 + 0.34 * t ** 1.4
        grid.append([PV + d * (ARM_L + 0.14), PV + d * (ARM_L + 0.14 - w)])
    b.add(sheet(grid, 0.16), "smear", "smear")

    CA.build(b, "crew", beard="beard")
    CB.build(b, "crew", beard="hair")


# ------------------------------------------------------------------------------------------------ poses
import sranim as A  # noqa: E402
from srkit import pose_lerp, pose_merge  # noqa: E402

STEP = 0.155          # 8 walk frames = 124 cm, the troops' WalkCycleDistance
WHEEL_DEG = math.degrees(STEP / WR)            # 22.5 degrees per frame
FEET = (((0.13, -0.05, 0.085), (0, 6)), ((-0.13, 0.05, 0.085), (0, -10)))
HANDS = (((0.285, -0.02, 0.56),), ((-0.285, -0.02, 0.56),))
KNEES = ((0.2, -1.0, 0.3), (-0.2, -1.0, 0.3))
ELBOWS = ((0.9, 0.5, 0.4), (-0.9, 0.6, 0.5))


def crew(rig, fig, hips=((0, 0, 0), (0, 0, 0)), spine=(0, 0, 0), chest=(0, 0, 0), look=(0, -6), feet=FEET,
         hands=HANDS, knees=KNEES, elbows=ELBOWS, at=(0, 0, 0), turn=0.0):
    """Pose one crewman. Everything is authored for the LEFT man (a_): his left hand is the outer one, the machine
    is on his right. For b_ the pose is mirrored. Rotations are (rx, ry, rz) tuples or quaternions; feet are
    (pos, (rx, rz)); hands are (wrist,) or (wrist, pointing direction). turn swings the whole figure about its
    own vertical axis; at moves it."""
    mir = fig is CB
    Q = lambda r: r if isinstance(r, Quaternion) else E(*r)  # noqa: E731

    def mq(q):
        return Quaternion((q.w, q.x, -q.y, -q.z)) if mir else q

    def mp(v):
        v = Vector(v)
        return Vector((-v.x, v.y, v.z)) if mir else v

    T = E(0, 0, -turn if mir else turn)
    Tm = T.to_matrix()
    tp = lambda v: Tm @ mp(v)  # noqa: E731
    fl, fr = feet
    hl, hr = hands
    kl, kr = knees
    el, er = elbows
    if mir:
        fl, fr, hl, hr, kl, kr, el, er = fr, fl, hr, hl, kr, kl, er, el

    def foot(f):
        return (tp(f[0]), T @ mq(f[1] if isinstance(f[1], Quaternion) else E(f[1][0], 0, f[1][1])))

    def hand(h):
        return (tp(h[0]), aim(tp(h[1]), (0, 0, 1)) if len(h) > 1 else T)

    if isinstance(look, tuple):
        lk = ((-look[0] if mir else look[0]) + (-turn if mir else turn), look[1],
              (-look[2] if mir else look[2]) if len(look) > 2 else 0.0)
    else:
        lk = mq(look)
    return fig.pose(rig, (tp(hips[0]), T @ mq(Q(hips[1]))), mq(Q(spine)), mq(Q(chest)), lk, foot(fl), foot(fr),
                    hand(hl), hand(hr), at=tuple(mp(at)), kneeL=tuple(tp(kl)), kneeR=tuple(tp(kr)),
                    elbowL=tuple(tp(el)), elbowR=tuple(tp(er)))


def machine(frame=((0, 0, 0), (0, 0, 0)), arm=(0, 0, 0), wheels=0.0, stone=False, windlass=0.0, uprights=(0, 0, 0),
            banner=0.0, chips=None, smear=False, loose=None):
    """arm = (wind-back, roll, yaw): 0 leans on the stop bar, COCK is wound right back. wheels = rolling angle.
    chips = (loc, scale) or None. loose = {wheel: (loc, (rx, ry, rz))} for wheels that have come off."""
    p = {"root": {}, "frame": {"loc": frame[0], "rot": E(*frame[1])}, "arm": {"rot": E(*arm)},
         "uprights": {"rot": E(*uprights)}, "banner": {"rot": E(banner, 0, 0)},
         "stone": {"scale": 1.0 if stone else 0.001}, "windlass": {"rot": E(windlass, 0, 0)},
         "smear": {"scale": 1.0 if smear else 0.001},
         "chips": {"loc": chips[0], "scale": chips[1], "rot": E(chips[1] * 40, 0, chips[1] * 25)} if chips
         else {"loc": (0, 0, 0), "scale": 0.001}}
    for n in WHEELS:
        if loose and n in loose:
            p[n] = {"loc": loose[n][0], "rot": E(*loose[n][1])}
        else:
            p[n] = {"loc": (0, 0, 0), "rot": E(wheels, 0, 0)}
    return p


def full(rig, m, a, b_):
    p = dict(m)
    p.update(crew(rig, CA, **a))
    p.update(crew(rig, CB, **b_))
    return p


def animate(rig):
    sin, cos, pi = math.sin, math.cos, math.pi
    stand = dict(hips=((0, 0, -0.02), (0, 0, 0)), spine=(1, 0, 0), look=(8, -6), turn=8,
                 hands=(HANDS[0], ((-0.17, -0.31, 0.70), (0, -1, -0.3))), elbows=(ELBOWS[0], (-0.9, 0.3, 0.6)))
    stand_b = dict(stand, look=(-10, -6), hands=(((0.30, -0.10, 0.74), (0.3, -1, 0.6)), stand["hands"][1]),
                   elbows=((0.9, 0.2, 0.2), stand["elbows"][1]))          # fist on his hip
    G = full(rig, machine(), stand, stand_b)

    # ---------------------------------------------------------------- idle: the crew breathe, the banner stirs
    rig.new_action("idle", 8, loop=True, drive="time", fps=5.0)
    for i in range(8):
        j = (i + 3) % 8
        a = dict(stand, hips=((0, 0, -0.02 + A.IDLE_UP[i] * A.PX_Z), (0, 0, 0)), look=(8 + 6 * A.IDLE_TILT[i], -6))
        bb = dict(stand_b, hips=((0, 0, -0.02 + A.IDLE_UP[j] * A.PX_Z), (0, 0, 0)), look=(-10 - 8 * A.IDLE_TILT[j], -6))
        rig.key(full(rig, machine(banner=4 * A.IDLE_SWAY[i]), a, bb), i)

    # ---------------------------------------------------------------- walk: rolled forward, both men pushing
    rig.new_action("walk", 8, loop=True, drive="distance", cycle_cm=STEP * 800, contact_frames=[0, 4],
                   roles=["contact", "down", "passing", "up", "contact", "down", "passing", "up"])

    def pusher(i):
        ph = i / 8
        body = A.run_body(i % 8, bob=0.016, drop=-0.085, lean=34.0, sway=0.008, yaw=5.0, roll=2.0)
        fl = A.run_legs(ph, STEP, 0.085, lift=0.085, side=1, foot_x=0.11)
        fr = A.run_legs(ph + 0.5, STEP, 0.085, lift=0.085, side=-1, foot_x=0.11)
        off = Vector((0, 0.16, 0))
        bob = body["hips"]["loc"][2] + 0.085
        return dict(hips=(tuple(Vector(body["hips"]["loc"]) + Vector((0, -0.10, 0))), body["hips"]["rot"]),
                    spine=body["spine"]["rot"], chest=body["chest"]["rot"], look=(0, -2), at=(-0.06, 0.22, 0),
                    feet=((tuple(Vector(fl["pos"]) + off), fl["rot"]), (tuple(Vector(fr["pos"]) + off), fr["rot"])),
                    hands=(((0.17, -0.565, 0.70 + bob * 0.3), (0, -1, 0.5)), ((-0.17, -0.565, 0.70 + bob * 0.3), (0, -1, 0.5))),
                    elbows=((0.9, 0.3, 0.2), (-0.9, 0.3, 0.2)), knees=((0.16, -1.0, 0.3), (-0.16, -1.0, 0.3)))

    for i in range(8):
        a, bb = pusher(i), pusher(i + 4)
        m = machine(wheels=WHEEL_DEG * i, banner=10 + 6 * cos(4 * pi * i / 8 - 1.5),
                    frame=((0, 0, 0.004 * cos(4 * pi * i / 8)), (0, 0, 0)))
        rig.key(full(rig, m, a, bb), i)

    # ---------------------------------------------------------------- attack: wind the arm down, load, loose
    rig.new_action("attack", 8, drive="attack_phase", strike_frame=5, windup_frames=[0, 1, 2, 3, 4],
                   recovery_frames=[5, 6, 7], windup_phase_map=[0.0, 0.20, 0.42, 0.64, 0.84],
                   recovery_phase_map=[0.0, 0.30, 0.62], projectile_origin_cm=[5.0, 0.0, 210.0],
                   release_frame=5)

    def cranker(th, lean):
        """Both hands on a handspike of the windlass; th = where round the turn (degrees)."""
        c = Vector((0.07, WL.y - CREW_Y, WL.z))
        r = math.radians(th)
        h = c + Vector((0, -cos(r) * 0.17, sin(r) * 0.17))
        return dict(hips=((0, -0.10, -0.07 - 0.03 * sin(r)), (10 + lean, 0, -6)), spine=(10 + lean, 0, -4), chest=(6, 0, -6),
                    look=(-10, 6), feet=(((0.14, -0.16, 0.085), (0, 4)), ((-0.12, 0.10, 0.085), (0, -14))),
                    hands=((tuple(h + Vector((0.07, 0, 0))), (-0.3, -1, 0)), (tuple(h + Vector((-0.05, 0, 0))), (0.3, -1, 0))),
                    elbows=((0.9, 0.4, 0.3), (-0.9, 0.4, 0.3)))

    loader = dict(hips=((-0.10, 0.05, -0.05), (6, 0, -38)), spine=(8, 0, -10), chest=(4, 0, -12), look=(-60, 14),
                  feet=(((0.10, -0.06, 0.085), (0, -20)), ((-0.16, 0.10, 0.085), (0, -50))),
                  hands=(((-0.26, 0.10, 0.98), (-1, 0.2, -0.2)), ((-0.30, 0.34, 0.98), (-1, -0.2, -0.2))),
                  elbows=((0.6, 0.8, 0.6), (-0.2, 1.2, 0.6)))
    puller = dict(hips=((0.05, 0.10, -0.08), (-8, 0, -10)), spine=(-8, 0, -4), chest=(-6, 0, -4), look=(-14, -4),
                  feet=(((0.15, -0.14, 0.085), (0, 4)), ((-0.10, 0.20, 0.085), (0, -16))),
                  hands=(((0.10, -0.22, 0.80), (-0.4, -1, 0)), ((-0.06, -0.20, 0.78), (0.2, -1, 0))),
                  elbows=((0.9, 0.5, 0.3), (-0.9, 0.5, 0.3)))
    brace = dict(hips=((0.06, 0.10, -0.10), (4, 0, 8)), spine=(8, 0, 4), chest=(6, 0, 4), look=(-10, 10),
                 feet=(((0.16, -0.02, 0.085), (0, 10)), ((-0.10, 0.18, 0.085), (0, -10))),
                 hands=(((0.30, -0.12, 0.98), (0.2, -0.3, 1)), ((-0.22, -0.16, 0.98), (-0.2, -0.3, 1))),
                 elbows=((1.0, 0.2, 0.2), (-1.0, 0.2, 0.2)))                 # hands up by his ears
    watch = dict(hips=((0.02, 0.04, -0.01), (-4, 0, 0)), spine=(-5, 0, 0), chest=(-4, 0, 0), look=(0, -32),
                 feet=FEET, hands=(((0.30, -0.08, 0.60),), ((-0.30, -0.04, 0.62),)))
    flinch = dict(hips=((0.03, 0.08, -0.06), (-6, 0, 4)), spine=(-8, 0, 2), chest=(-6, 0, 0), look=(-6, -20),
                  feet=(((0.14, -0.03, 0.085), (0, 6)), ((-0.12, 0.16, 0.085), (0, -10))),
                  hands=(((0.34, -0.12, 0.84), (0.3, -0.6, 1)), ((-0.30, -0.10, 0.80), (-0.3, -0.6, 1))))
    arm_a = [-22, -52, -82, COCK, COCK - 1.5, -17, 3, 0]
    keys = [
        full(rig, machine(arm=(arm_a[0], 0, 0), windlass=0), cranker(20, 0), cranker(200, 0)),
        full(rig, machine(arm=(arm_a[1], 0, 0), windlass=90), cranker(110, 4), cranker(290, 4)),
        full(rig, machine(arm=(arm_a[2], 0, 0), windlass=180), cranker(200, 0), cranker(20, 0)),
        full(rig, machine(arm=(arm_a[3], 0, 0), windlass=270, stone=True, frame=((0, 0, -0.006), (-0.6, 0, 0))),
             cranker(290, 6), loader),
        full(rig, machine(arm=(arm_a[4], 0, 0), windlass=275, stone=True, frame=((0, 0, -0.008), (-0.8, 0, 0))),
             puller, brace),
        full(rig, machine(arm=(arm_a[5], 0, 0), windlass=180, smear=True, frame=((0, -0.03, 0.01), (3.0, 0, 0)), banner=-30),
             flinch, brace),
        full(rig, machine(arm=(arm_a[6], 0, 0), windlass=20, frame=((0, -0.05, 0.03), (-2.5, 0, 0)), uprights=(3, 0, 0),
                          banner=38), watch, watch),
        full(rig, machine(arm=(arm_a[7], 0, 0), frame=((0, -0.02, 0.0), (0.8, 0, 0)), banner=-12),
             dict(watch, look=(0, -24)), dict(watch, look=(0, -24))),
    ]
    rig.key_all(keys)

    # ---------------------------------------------------------------- hit: the frame shudders, splinters fly
    rig.new_action("hit", 3, drive="time", fps=18.0)
    h0 = full(rig, machine(frame=((0.035, 0.05, 0.0), (-2.5, 3.5, 0)), arm=(-4, 0, 0), chips=((0.0, -0.02, 0.0), 1.0), banner=25),
              flinch, dict(flinch, look=(10, -16)))
    h1 = full(rig, machine(frame=((-0.02, -0.02, 0.0), (1.2, -1.8, 0)), arm=(1, 0, 0), chips=((0.10, -0.12, 0.12), 1.7), banner=-15),
              pose_dict_lerp(flinch, stand, 0.5), pose_dict_lerp(flinch, stand_b, 0.4))
    h2 = full(rig, machine(frame=((0.006, 0.0, 0.0), (-0.4, 0.6, 0)), chips=((0.20, -0.24, 0.02), 2.3), banner=6),
              pose_dict_lerp(flinch, stand, 0.85), pose_dict_lerp(flinch, stand_b, 0.8))
    rig.key_all([h0, h1, h2])

    # ---------------------------------------------------------------- spawn: the crew straighten up and the arm
    # swings up onto the stop bar with a thump
    rig.new_action("spawn", 6, drive="time", fps=12.0, active_frame=5)
    crouch = dict(hips=((0, 0.0, -0.20), (10, 0, 0)), spine=(14, 0, 0), chest=(8, 0, 0), look=(0, 12),
                  feet=FEET, hands=(((0.22, -0.30, 0.50), (0, -1, -0.3)), ((-0.20, -0.32, 0.50), (0, -1, -0.3))))
    tall = dict(hips=((0, 0.0, 0.0), (-3, 0, 0)), spine=(-4, 0, 0), chest=(-3, 0, 0), look=(0, -16), feet=FEET,
                hands=(((0.32, -0.06, 0.66),), ((-0.30, -0.10, 0.70),)))
    sp = [
        full(rig, machine(arm=(COCK, 0, 0), frame=((0, 0, -0.01), (0, 0, 0))), crouch, crouch),
        full(rig, machine(arm=(-74, 0, 0), smear=False), pose_dict_lerp(crouch, tall, 0.3), pose_dict_lerp(crouch, tall, 0.2)),
        full(rig, machine(arm=(-30, 0, 0), frame=((0, -0.01, 0.0), (1.5, 0, 0))), pose_dict_lerp(crouch, tall, 0.75),
             pose_dict_lerp(crouch, tall, 0.6)),
        full(rig, machine(arm=(3, 0, 0), frame=((0, -0.04, 0.025), (-2.2, 0, 0)), uprights=(3, 0, 0), banner=34), tall, tall),
        full(rig, machine(arm=(0, 0, 0), frame=((0, -0.01, 0.0), (0.7, 0, 0)), banner=-14), pose_dict_lerp(tall, stand, 0.7),
             pose_dict_lerp(tall, stand_b, 0.6)),
        G,
    ]
    rig.key_all(sp)

    # ---------------------------------------------------------------- death: a wheel goes, the frame drops and
    # tilts, the uprights fall forward, the arm slumps, the crew are thrown down either side
    rig.new_action("death", 8, drive="time", fps=12.0, hold_last=True)
    c0 = dict(hips=((0, 0.08, -0.03), (-12, 0, -4)), spine=(-14, 0, 0), chest=(-10, 0, 4), look=(6, -30, 8),
              feet=(((0.13, -0.05, 0.085), (0, 6)), ((-0.13, 0.18, 0.085), (0, -12))),
              hands=(((0.40, -0.10, 0.86),), ((-0.40, 0.05, 0.90),)))
    c2 = dict(hips=((0.02, 0.17, -0.22), (2, 0, 6)), spine=(6, 0, 4), chest=(10, 0, 4), look=(-12, 26, -8),
              feet=(((0.13, -0.02, 0.085), (0, 8)), ((-0.13, 0.25, 0.085), (0, -20))),
              hands=(((0.45, -0.02, 0.45),), ((-0.42, 0.14, 0.42),)))
    c4 = dict(hips=((0.02, 0.14, -0.34), (-58, 0, 10)), spine=(-6, 0, 2), chest=(-4, 0, 0), look=E(-20, 0, 0),
              feet=(((0.14, 0.08, 0.11), (15, 10)), ((-0.12, 0.22, 0.09), (55, -15))),
              hands=(((0.42, 0.36, 0.56),), ((-0.42, 0.40, 0.60),)),
              knees=((0.25, -0.6, 1.0), (-0.3, -0.6, 1.0)), elbows=((1.2, 0.2, 0.3), (-1.2, 0.3, 0.3)))
    c5 = dict(hips=((0.02, 0.10, -0.345), (-90, 0, 12)), spine=(5, 0, 2), chest=(6, 0, 0), look=E(16, 0, -10),
              feet=(((0.16, -0.12, 0.20), (-50, 15)), ((-0.12, 0.02, 0.16), (-20, -10))),
              hands=(((0.46, 0.44, 0.15),), ((-0.44, 0.52, 0.17),)),
              knees=((0.3, -0.1, 1.5), (-0.3, 0.1, 1.5)), elbows=((1.2, 0.2, 0.3), (-1.2, 0.3, 0.3)))
    c7 = dict(hips=((0.02, 0.10, -0.36), (-92, 0, 12)), spine=(-2, 0, 3), chest=(-2, 0, 0), look=E(-4, 6, -32),
              feet=(((0.17, -0.19, 0.078), (-62, 30)), ((-0.11, 0.0, 0.09), (0, -15))),
              hands=(((0.44, 0.48, 0.085),), ((-0.40, 0.60, 0.085),)),
              knees=((0.3, -0.1, 1.5), (-0.35, 0.1, 1.5)), elbows=((1.2, 0.2, 0.3), (-1.2, 0.3, 0.3)))

    def fall(seq, turn, at):
        out = []
        for k, (u, v, t) in enumerate(seq):
            d = pose_dict_lerp(u, v, t) if v is not None else dict(u)
            f = min(1.0, k / 3.0)
            d["turn"] = turn * f
            d["at"] = tuple(Vector(at) * f)
            out.append(d)
        return out

    fa = fall([(c0, None, 0), (c0, c2, 0.6), (c2, None, 0), (c2, c4, 0.6), (c4, None, 0), (c5, None, 0), (c5, c7, 0.7),
               (c7, None, 0)], -72, (0.16, 0.0, 0))
    fb = fall([(flinch, None, 0), (c0, None, 0), (c0, c2, 0.7), (c2, None, 0), (c2, c4, 0.7), (c4, c5, 0.6), (c5, None, 0),
               (c7, None, 0)], -58, (0.10, -0.10, 0))
    mk = [
        machine(frame=((0.04, 0.06, 0.02), (-4, 5, 0)), arm=(-8, 0, 0), chips=((0, 0, 0), 1.0), banner=30),
        machine(frame=((0.02, 0.0, -0.06), (4, 7, 0)), arm=(-24, 6, 0), uprights=(18, 0, 5), chips=((0.1, -0.12, 0.14), 1.8),
                loose={"wheel_fl": ((0.14, -0.04, -0.03), (0, 24, 0))}, banner=-20),
        machine(frame=((0.0, -0.03, -0.16), (7, 11, 0)), arm=(-52, 18, 0), uprights=(50, 0, 9), chips=((0.2, -0.26, 0.04), 2.4),
                loose={"wheel_fl": ((0.30, -0.12, -0.14), (0, 58, 0)), "wheel_rr": ((-0.03, 0, 0), (0, -9, 0))}, banner=-50),
        machine(frame=((0.0, -0.04, -0.27), (5, 10, 0)), arm=(-82, 32, 0), uprights=(80, 0, 12),
                loose={"wheel_fl": ((0.44, -0.2, -0.22), (0, 86, 0)), "wheel_fr": ((-0.08, 0, -0.03), (0, -24, 0)),
                       "wheel_rr": ((-0.05, 0, 0), (0, -14, 0))}, banner=-70),
        machine(frame=((0.0, -0.04, -0.345), (2, 7, 0)), arm=(-100, 40, 0), uprights=(95, 0, 14), chips=((0.0, 0.3, -0.5), 1.4),
                loose={"wheel_fl": ((0.46, -0.22, -0.20), (0, 92, 0)), "wheel_fr": ((-0.22, -0.04, -0.06), (0, -64, 0)),
                       "wheel_rl": ((0.10, 0.08, -0.02), (0, 28, 0)), "wheel_rr": ((-0.07, 0, 0), (0, -17, 0))}, banner=-85),
        machine(frame=((0.0, -0.04, -0.33), (2.5, 6, 0)), arm=(-104, 42, 0), uprights=(92, 0, 14), chips=((0.1, 0.42, -0.72), 2.0),
                loose={"wheel_fl": ((0.46, -0.22, -0.21), (0, 88, 0)), "wheel_fr": ((-0.36, -0.08, -0.12), (0, -90, 0)),
                       "wheel_rl": ((0.26, 0.18, -0.08), (0, 80, 8)), "wheel_rr": ((-0.08, 0, 0), (0, -18, 0))}, banner=-88),
    ]
    last = machine(frame=((0.0, -0.04, -0.34), (2.2, 6, 0)), arm=(-105, 42, 0), uprights=(94, 0, 14),
                   loose={"wheel_fl": ((0.46, -0.22, -0.21), (0, 89, 0)), "wheel_fr": ((-0.38, -0.08, -0.13), (0, -88, 0)),
                          "wheel_rl": ((0.30, 0.20, -0.10), (0, 88, 8)), "wheel_rr": ((-0.08, 0, 0), (0, -18, 0))}, banner=-88)
    mk += [last, last]
    rig.key_all([full(rig, mk[i], fa[i], fb[i]) for i in range(8)])


def pose_dict_lerp(u, v, t):
    """Blend two crew() argument dicts (not posed yet): positions and angles linearly."""
    def mix(a, b):
        if isinstance(a, Quaternion) or isinstance(b, Quaternion):
            qa = a if isinstance(a, Quaternion) else E(*a)
            qb = b if isinstance(b, Quaternion) else E(*b)
            return qa.slerp(qb, t)
        if isinstance(a, (int, float)):
            return a + (b - a) * t
        if len(a) != len(b):
            return a if t < 0.5 else b
        return tuple(mix(x, y) for x, y in zip(a, b))
    out = {}
    base = dict(hips=((0, 0, 0), (0, 0, 0)), spine=(0, 0, 0), chest=(0, 0, 0), look=(0, -6), feet=FEET, hands=HANDS,
                knees=KNEES, elbows=ELBOWS, at=(0, 0, 0), turn=0.0)
    for k in base:
        a, b = u.get(k, base[k]), v.get(k, base[k])
        if k == "look" and isinstance(a, tuple) and isinstance(b, tuple):
            a, b = (tuple(a) + (0,))[:3], (tuple(b) + (0,))[:3]
        out[k] = mix(a, b)
    return out
